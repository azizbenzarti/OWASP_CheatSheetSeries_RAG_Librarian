"""
Online retrieval: question in, ranked chunks (with metadata) out.

This module only READS what the offline pipeline (src/indexing/) already
built; it never rebuilds, re-chunks or re-embeds the corpus:

  * chunk text + metadata   <- data/index/<config>/chunks.jsonl   (build.load_chunks)
  * keyword index           <- data/index/<config>/bm25/          (bm25s, same tokenizer as build.py)
  * vector index            <- Qdrant collection named in manifest.json
  * query embedding         <- embed.embed_texts() with the same EmbeddingConfig / model

Modes (so the ablation table in the report can be produced from one class):
  "bm25"   keyword only
  "vector" Qdrant only
  "hybrid" both, fused with Reciprocal Rank Fusion (RRF)

Reranking ("hybrid+rerank" in the ablation) isn't a 4th mode string -- it's
whatever Reranker callable is attached at construction time (see
reranker.py). Pass candidates=20 alongside mode="hybrid" on a
reranker-equipped instance to match "rerank the top 20" (candidates controls
how deep each retriever searches before fusion, which is also how many
fused candidates reach the reranker -- see `retrieve()` below).

Usage:
    retriever = Retriever.from_config()                # loads once, reuse it
    result = retriever.retrieve("how should I store passwords?", top_k=5)
    for c in result.chunks: print(c.chunk_id, c.score)
    prompt_context = format_context(result.chunks)     # hand to the generator

CLI:  python -m src.retrieval "how should I store passwords?"
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_INDEX_DIR = ROOT / "data" / "index" / "heading_mt512_min20"  # the chosen config (docs/design.md)

MODES = ("bm25", "vector", "hybrid")
RRF_K = 60  # standard RRF constant (Cormack et al. 2009); damps the influence of top ranks
DEFAULT_CANDIDATES = 50  # how deep each retriever looks before fusion
OWASP_URL = "https://cheatsheetseries.owasp.org/cheatsheets/{name}.html"

Filters = dict[str, Any]  # keys: source_file (str | list[str]), has_code (bool), has_table (bool)
Reranker = Callable[[str, "list[RetrievedChunk]"], "list[RetrievedChunk]"]


# --------------------------------------------------------------------- #
# data structures
# --------------------------------------------------------------------- #


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_file: str
    title: str
    section_path: str
    text: str
    score: float  # final ranking score: RRF for hybrid, cosine for vector, BM25 for bm25, cross-encoder score if reranked
    rank: int  # 1-based position in the returned list
    source_url: str
    n_tokens: int = 0
    has_code: bool = False
    has_table: bool = False
    # Per-retriever diagnostics (None if that retriever didn't return the chunk).
    # vector_score is cosine similarity, the one score that is comparable
    # across queries, so it is what an "I don't know" threshold should use.
    vector_score: float | None = None
    vector_rank: int | None = None
    bm25_score: float | None = None
    bm25_rank: int | None = None
    # Set only when a reranker is attached (see reranker.py). vector_rank/
    # bm25_rank above are untouched by reranking, so comparing them against
    # the post-rerank `rank` shows exactly what reranking moved.
    rerank_score: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalResult:
    query: str
    mode: str
    chunks: list[RetrievedChunk]
    timings_ms: dict[str, float] = field(default_factory=dict)
    # Set when retrieval deliberately returned nothing (the generator should say "I don't know").
    no_answer_reason: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "mode": self.mode,
            "no_answer_reason": self.no_answer_reason,
            "timings_ms": self.timings_ms,
            "chunks": [c.to_dict() for c in self.chunks],
        }


# --------------------------------------------------------------------- #
# pure helpers (no I/O, unit-tested in tests/test_retriever.py)
# --------------------------------------------------------------------- #


def matches_filters(chunk: dict, filters: Filters | None) -> bool:
    """Python-side version of the Qdrant payload filter, used for BM25
    (which has no metadata filtering of its own)."""
    if not filters:
        return True
    for key, wanted in filters.items():
        value = chunk.get(key)
        if isinstance(wanted, (list, tuple, set)):
            if value not in wanted:
                return False
        elif value != wanted:
            return False
    return True


def rrf_fuse(
    rankings: dict[str, Sequence[str]],
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. `rankings` maps a retriever name to its
    best-first list of chunk_ids. score(d) = sum_r weight_r / (k + rank_r(d)).
    Only ranks are used, so BM25 scores and cosine similarities (which live
    on different scales) never need normalising. Ties break on the best
    individual rank, then chunk_id, so output is deterministic."""
    weights = weights or {}
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for name, ids in rankings.items():
        w = weights.get(name, 1.0)
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + w / (k + rank)
            best_rank[chunk_id] = min(best_rank.get(chunk_id, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], kv[0]))


def format_context(chunks: Sequence[RetrievedChunk]) -> str:
    """Numbered context block for the generation prompt. The [n] labels are
    what the model should cite; map them back with chunks[n-1]."""
    blocks = []
    for i, c in enumerate(chunks, start=1):
        header = f"[{i}] {c.title} — {c.section_path}" if c.section_path else f"[{i}] {c.title}"
        blocks.append(f"{header}\nSource: {c.source_file}\n\n{c.text}")
    return "\n\n---\n\n".join(blocks)


# --------------------------------------------------------------------- #
# Retriever
# --------------------------------------------------------------------- #


class Retriever:
    """Holds everything loaded once (chunks, BM25, Qdrant client) so each
    query only pays for one embedding call + two searches.

    The constructor takes plain callables so it can be unit-tested without
    Qdrant or an API key; use Retriever.from_config() for the real wiring."""

    def __init__(
        self,
        chunks: list[dict],
        embed_query: Callable[[str], list[float]],
        vector_search: Callable[[list[float], int, Filters | None], list[dict]],
        bm25_index: Any,
        tokenize: Callable[[str], list[str]],
        reranker: Reranker | None = None,
    ) -> None:
        self.chunks = chunks
        self.chunks_by_id = {c["chunk_id"]: c for c in chunks}
        self._embed_query = embed_query
        self._vector_search = vector_search
        self._bm25 = bm25_index
        self._tokenize = tokenize
        self.reranker = reranker

    # ----- construction ------------------------------------------------ #

    @classmethod
    def from_config(cls, index_dir: Path | str | None = None, reranker: Reranker | None = None) -> "Retriever":
        """Wire up the real, already-built indexes using the offline
        pipeline's own functions and .env configuration."""
        import bm25s
        from qdrant_client.http import models as qm

        from ..indexing.build import load_chunks, tokenize_for_bm25
        from ..indexing.embed import EmbeddingConfig, embed_texts
        from ..indexing.vectordb import get_client
        from ..indexing.vectordb import vector_search as vdb_vector_search

        index_dir = Path(index_dir) if index_dir else DEFAULT_INDEX_DIR
        if not (index_dir / "chunks.jsonl").is_file():
            raise FileNotFoundError(
                f"{index_dir} has no chunks.jsonl. data/index/ is gitignored, so it only exists where "
                "the offline build was run: copy it from a teammate, or run scripts/build_index.sh "
                "(embeddings are disk-cached and Qdrant upserts are idempotent, so a rebuild is cheap)."
            )
        manifest = json.loads((index_dir / "manifest.json").read_text(encoding="utf-8"))
        chunks = load_chunks(index_dir)

        # Query and chunk vectors must come from the same model, or cosine scores are meaningless.
        embed_config = EmbeddingConfig()
        if embed_config.model != manifest["embedding_model"]:
            raise RuntimeError(
                f"EMBEDDING_MODEL in .env is {embed_config.model!r} but this index was built with "
                f"{manifest['embedding_model']!r}. Fix .env; do not mix models."
            )

        qdrant = get_client()
        collection = manifest["qdrant_collection"]
        try:
            n_points = qdrant.get_collection(collection).points_count
        except Exception as exc:  # collection missing / Qdrant down
            raise RuntimeError(
                f"Qdrant collection {collection!r} is not available ({exc}). "
                "Start it with `docker compose up -d`; if the volume is new, rerun scripts/build_index.sh."
            ) from exc
        if n_points != len(chunks):
            raise RuntimeError(
                f"Qdrant collection {collection!r} has {n_points} points but chunks.jsonl has "
                f"{len(chunks)} chunks: the two indexes are out of sync."
            )

        bm25_index = bm25s.BM25.load(str(index_dir / "bm25"), load_corpus=False)

        embed_cache: dict[str, list[float]] = {}

        def embed_query(q: str) -> list[float]:
            if q not in embed_cache:  # repeated questions skip the API call
                if len(embed_cache) >= 256:
                    embed_cache.pop(next(iter(embed_cache)))
                [embed_cache[q]] = embed_texts([q], embed_config, show_progress=False)
            return embed_cache[q]

        def vector_search(vector: list[float], k: int, filters: Filters | None) -> list[dict]:
            return vdb_vector_search(qdrant, collection, vector, k=k, filters=_to_qdrant_filter(filters, qm))

        return cls(chunks, embed_query, vector_search, bm25_index, tokenize_for_bm25, reranker)

    # ----- individual retrievers ---------------------------------------- #

    def _search_bm25(self, query: str, k: int, filters: Filters | None) -> list[tuple[str, float]]:
        tokens = self._tokenize(query)
        if not tokens:
            return []
        n = len(self.chunks)
        # bm25s has no metadata filter, so when filtering, rank the whole
        # (small, ~2.7k chunk) index and filter afterwards.
        fetch = n if filters else min(k, n)
        doc_ids, scores = self._bm25.retrieve([tokens], corpus=list(range(n)), k=fetch, show_progress=False)
        hits = []
        for i, s in zip(doc_ids[0], scores[0]):
            chunk = self.chunks[int(i)]
            if float(s) > 0 and matches_filters(chunk, filters):  # zero score = no query term matched
                hits.append((chunk["chunk_id"], float(s)))
            if len(hits) >= k:
                break
        return hits

    def _search_vector(self, query: str, k: int, filters: Filters | None) -> list[tuple[str, float]]:
        hits = self._vector_search(self._embed_query(query), k, filters)
        return [(h["chunk_id"], float(h["_score"])) for h in hits]

    # ----- public API ---------------------------------------------------- #

    def retrieve(
        self,
        question: str,
        top_k: int = 5,
        mode: str = "hybrid",
        filters: Filters | None = None,
        candidates: int = DEFAULT_CANDIDATES,
        min_vector_score: float | None = None,
        weights: dict[str, float] | None = None,
    ) -> RetrievalResult:
        """Return the top_k chunks for `question`.

        filters: e.g. {"source_file": "Password_Storage_Cheat_Sheet.md"} or {"has_code": True};
                 applied identically to both retrievers.
        min_vector_score: optional "I don't know" gate. If the best cosine
                 similarity is below it, no chunks are returned and
                 result.no_answer_reason is set. There is no default because
                 the right value must be calibrated on dev (eval/retrieval_eval.py).
        weights: optional RRF weights, e.g. {"vector": 1.0, "bm25": 0.5}.
        """
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        if not question or not question.strip():
            return RetrievalResult(question, mode, [], no_answer_reason="empty_query")

        depth = max(candidates, top_k)
        t0 = time.perf_counter()
        timings: dict[str, float] = {}
        vec_hits: list[tuple[str, float]] = []
        bm_hits: list[tuple[str, float]] = []

        if mode in ("vector", "hybrid"):
            t = time.perf_counter()
            vec_hits = self._search_vector(question, depth, filters)
            timings["vector_ms"] = (time.perf_counter() - t) * 1000
        if mode in ("bm25", "hybrid"):
            t = time.perf_counter()
            bm_hits = self._search_bm25(question, depth, filters)
            timings["bm25_ms"] = (time.perf_counter() - t) * 1000

        if min_vector_score is not None and mode != "bm25":
            best = vec_hits[0][1] if vec_hits else 0.0
            if best < min_vector_score:
                timings["total_ms"] = (time.perf_counter() - t0) * 1000
                return RetrievalResult(question, mode, [], timings, no_answer_reason="below_vector_score_threshold")

        vec_info = {cid: (s, r) for r, (cid, s) in enumerate(vec_hits, start=1)}
        bm_info = {cid: (s, r) for r, (cid, s) in enumerate(bm_hits, start=1)}

        if mode == "vector":
            ordered = [(cid, s) for cid, s in vec_hits]
        elif mode == "bm25":
            ordered = [(cid, s) for cid, s in bm_hits]
        else:
            ordered = rrf_fuse(
                {"vector": [c for c, _ in vec_hits], "bm25": [c for c, _ in bm_hits]}, weights=weights
            )

        # With a reranker, it needs a wider candidate pool than top_k to be useful.
        keep = depth if self.reranker else top_k
        results = [self._build(cid, score, vec_info.get(cid), bm_info.get(cid)) for cid, score in ordered[:keep]]

        if self.reranker and results:
            t = time.perf_counter()
            results = self.reranker(question, results)
            timings["rerank_ms"] = (time.perf_counter() - t) * 1000
            # Reranking changes what "final" means: without this, .score
            # would still show the pre-rerank hybrid/vector/bm25 score,
            # which the reranker has just reordered past -- confusing to
            # read (a lower-ranked chunk could show a higher .score).
            for c in results:
                if c.rerank_score is not None:  # guard against a reranker that forgot to set it
                    c.score = c.rerank_score
        results = results[:top_k]
        for rank, chunk in enumerate(results, start=1):
            chunk.rank = rank

        timings["total_ms"] = (time.perf_counter() - t0) * 1000
        return RetrievalResult(
            question, mode, results, {k: round(v, 2) for k, v in timings.items()},
            no_answer_reason=None if results else "no_results",
        )

    def _build(self, chunk_id: str, score: float, vec: tuple[float, int] | None, bm: tuple[float, int] | None) -> RetrievedChunk:
        c = self.chunks_by_id[chunk_id]
        return RetrievedChunk(
            chunk_id=chunk_id,
            source_file=c["source_file"],
            title=c["title"],
            section_path=c["section_path"],
            text=c["text"],
            score=score,
            rank=0,
            source_url=OWASP_URL.format(name=Path(c["source_file"]).stem),
            n_tokens=c.get("n_tokens", 0),
            has_code=c.get("has_code", False),
            has_table=c.get("has_table", False),
            vector_score=vec[0] if vec else None,
            vector_rank=vec[1] if vec else None,
            bm25_score=bm[0] if bm else None,
            bm25_rank=bm[1] if bm else None,
        )


def _to_qdrant_filter(filters: Filters | None, qm: Any):
    """Translate the simple filters dict into a Qdrant Filter (payload
    indexes exist for source_file, has_code, has_table; see vectordb.py)."""
    if not filters:
        return None
    must = []
    for key, wanted in filters.items():
        if isinstance(wanted, (list, tuple, set)):
            cond = qm.MatchAny(any=list(wanted))
        else:
            cond = qm.MatchValue(value=wanted)
        must.append(qm.FieldCondition(key=key, match=cond))
    return qm.Filter(must=must)


# --------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the built OWASP index.")
    parser.add_argument("question")
    parser.add_argument("-k", "--top-k", type=int, default=5)
    parser.add_argument("--mode", choices=MODES, default="hybrid", help='ignored if --rerank is set (reranking only makes sense on "hybrid")')
    parser.add_argument("--rerank", action="store_true", help="hybrid+rerank: hybrid top 20 candidates -> cross-encoder rerank -> top-k")
    parser.add_argument("--reranker-model", default=None, help="overrides RERANKER_MODEL / the default")
    parser.add_argument("--index-dir", default=None)
    parser.add_argument("--source-file", default=None, help="restrict to one cheat sheet, e.g. Password_Storage_Cheat_Sheet.md")
    parser.add_argument("--has-code", action="store_true", help="only chunks containing a code block")
    parser.add_argument("--min-vector-score", type=float, default=None)
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    parser.add_argument("--context", action="store_true", help="print the formatted generation context")
    args = parser.parse_args()

    filters: Filters = {}
    if args.source_file:
        filters["source_file"] = args.source_file
    if args.has_code:
        filters["has_code"] = True

    reranker = None
    if args.rerank:
        from .reranker import make_reranker  # heavy import (torch); only pay for it when asked

        reranker = make_reranker(args.reranker_model)

    retriever = Retriever.from_config(args.index_dir, reranker=reranker)
    mode = "hybrid" if args.rerank else args.mode
    candidates = 20 if args.rerank else DEFAULT_CANDIDATES
    result = retriever.retrieve(
        args.question, args.top_k, mode, filters or None,
        candidates=candidates, min_vector_score=args.min_vector_score,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return
    if result.is_empty:
        print(f"No results ({result.no_answer_reason}).")
        return
    for c in result.chunks:
        extra = f"vec={c.vector_score:.3f}" if c.vector_score is not None else "vec=-"
        extra += f" bm25={c.bm25_score:.2f}" if c.bm25_score is not None else " bm25=-"
        if c.rerank_score is not None:
            extra += f" rerank={c.rerank_score:.3f}"
        print(f"{c.rank}. [{c.score:.4f}] {c.title} > {c.section_path}   ({extra})\n   {c.chunk_id}")
    print(f"\n{json.dumps(result.timings_ms)}")
    if args.context:
        print("\n" + format_context(result.chunks))
