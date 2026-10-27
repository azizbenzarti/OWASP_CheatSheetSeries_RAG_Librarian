"""
Chunking experiment: for each (strategy, max_tokens, overlap) config, build
chunks + a Qdrant collection (vector search) + an in-memory BM25 index, then
measure retrieval quality against data/dev.jsonl ONLY. data/test.jsonl is
never opened by this script.

A retrieved chunk counts as a hit for a target passage if, after whitespace
normalization, it covers at least 70% of the passage (measured as the
longest common contiguous substring between chunk text and passage, divided
by passage length). A fully-contained passage scores 100% coverage, so this
single check already covers plain "contains" as a special case; it also
handles a passage that the chunker split across a chunk boundary, where a
chunk holds most-but-not-all of it.

Each config is built via build.py's build_index() -- the same function
scripts/build_index.sh uses -- so every config this script runs also lands
as a persisted data/index/<config>/ directory (chunks.jsonl, manifest.json,
bm25/) that eval/check_index.py can later be pointed at directly, and so
there's exactly one place that knows how to build a config, not two.
Qdrant collections are recreated fresh per config (see vectordb.py's
ensure_collection) so results never pick up stale points from a previous
run.
"""
from __future__ import annotations

import csv
import difflib
import json
import re
import sys
from pathlib import Path

import bm25s

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from indexing.build import build_index, config_name, load_chunks, tokenize_for_bm25  # noqa: E402
from indexing.embed import EmbeddingConfig, embed_texts  # noqa: E402
from indexing.vectordb import get_client  # noqa: E402
from indexing.vectordb import vector_search as vdb_vector_search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEV_PATH = ROOT / "data" / "dev.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"

MIN_TOKENS = 20  # fixed for every heading config here; only max_tokens is swept
TOP_K = 10
HIT_THRESHOLD = 0.70

CONFIGS = [
    ("heading", 256, 0),
    ("heading", 512, 0),
    ("heading", 1024, 0),
    ("fixed", 256, 0),
    ("fixed", 256, round(256 * 0.15)),
    ("fixed", 512, 0),
    ("fixed", 512, round(512 * 0.15)),
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def coverage(chunk_text_norm: str, passage_norm: str) -> float:
    if not passage_norm:
        return 0.0
    sm = difflib.SequenceMatcher(None, chunk_text_norm, passage_norm, autojunk=False)
    match = sm.find_longest_match(0, len(chunk_text_norm), 0, len(passage_norm))
    return match.size / len(passage_norm)


def load_dev_questions() -> list[dict]:
    rows = [json.loads(line) for line in DEV_PATH.open(encoding="utf-8")]
    return [r for r in rows if r["answerable"]]  # unanswerable questions have no passage to check


def build_config(strategy: str, max_tokens: int, overlap: int, embed_config: EmbeddingConfig) -> dict:
    """Build (or rebuild -- build_index()/ensure_collection() upsert in
    place) one config via build.py, then load the chunks + BM25 index back
    from what it just wrote to disk, for querying here."""
    out_dir = build_index(strategy, max_tokens, overlap, MIN_TOKENS, embed_config)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    chunks = load_chunks(out_dir)
    bm25_index = bm25s.BM25.load(str(out_dir / "bm25"), load_corpus=False)

    return {
        "out_dir": out_dir,
        "manifest": manifest,
        "collection": manifest["qdrant_collection"],
        "bm25_index": bm25_index,
        "chunks": chunks,
        "chunks_by_id": {c["chunk_id"]: c for c in chunks},
        "n_chunks": manifest["n_chunks"],
        "avg_tokens": (sum(c["n_tokens"] for c in chunks) / len(chunks)) if chunks else 0.0,
        "build_time": manifest["build_time_seconds"],
    }


def vector_top_chunks(built, qdrant, embed_config, query, k) -> list[dict]:
    [query_vector] = embed_texts([query], embed_config, show_progress=False)
    hits = vdb_vector_search(qdrant, built["collection"], query_vector, k=k)
    return [built["chunks_by_id"][h["chunk_id"]] for h in hits]


def bm25_top_chunks(built, query, k) -> list[dict]:
    q_tokens = tokenize_for_bm25(query)
    k = min(k, built["n_chunks"])
    doc_ids, _ = built["bm25_index"].retrieve(
        [q_tokens], corpus=list(range(built["n_chunks"])), k=k, show_progress=False
    )
    return [built["chunks"][i] for i in doc_ids[0]]


def hit_flags(retrieved_chunks: list[dict], passage_norm: str) -> list[bool]:
    return [coverage(normalize(c["text"]), passage_norm) >= HIT_THRESHOLD for c in retrieved_chunks]


def recall_and_mrr(hit_flags_per_question: list[list[bool]]) -> tuple[float, float, float, float]:
    n = len(hit_flags_per_question)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0

    def recall_at(k: int) -> float:
        return sum(any(flags[:k]) for flags in hit_flags_per_question) / n

    mrr_total = 0.0
    for flags in hit_flags_per_question:
        for rank, hit in enumerate(flags, start=1):
            if hit:
                mrr_total += 1.0 / rank
                break
    return recall_at(1), recall_at(5), recall_at(10), mrr_total / n


def run() -> None:
    questions = load_dev_questions()
    print(f"dev answerable questions: {len(questions)}", flush=True)

    embed_config = EmbeddingConfig()  # stops clearly if EMBEDDING_MODEL/EMBEDDING_API_KEY are unset
    qdrant = get_client()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_rows: list[dict] = []
    still_failing = {q["id"] for q in questions}
    extra_passage_stats: list[tuple[str, str, float, int]] = []

    for strategy, max_tokens, overlap in CONFIGS:
        label = config_name(strategy, max_tokens, overlap, MIN_TOKENS)
        print(f"building {label} ...", flush=True)
        built = build_config(strategy, max_tokens, overlap, embed_config)
        m = built["manifest"]
        print(
            f"  {built['n_chunks']} chunks, avg {built['avg_tokens']:.0f} tokens, "
            f"built in {built['build_time']:.1f}s, {m['embedding_tokens']} tokens embedded "
            f"({m['embedding_cache_hits']} cache hits, {m['embedding_cache_misses']} misses)",
            flush=True,
        )

        for method in ("vector", "bm25"):
            hit_flags_per_question: list[list[bool]] = []
            extra_hits, extra_total = 0, 0

            for q in questions:
                retrieved = (
                    vector_top_chunks(built, qdrant, embed_config, q["question"], TOP_K)
                    if method == "vector"
                    else bm25_top_chunks(built, q["question"], TOP_K)
                )

                primary_flags = hit_flags(retrieved, normalize(q["source_passage"]))
                hit_flags_per_question.append(primary_flags)
                if any(primary_flags):
                    still_failing.discard(q["id"])

                for extra in q.get("extra_sources") or []:
                    extra_flags = hit_flags(retrieved, normalize(extra["source_passage"]))
                    extra_total += 1
                    if any(extra_flags):
                        extra_hits += 1

            r1, r5, r10, mrr = recall_and_mrr(hit_flags_per_question)
            csv_rows.append(
                {
                    "config": label,
                    "method": method,
                    "recall@1": round(r1, 4),
                    "recall@5": round(r5, 4),
                    "recall@10": round(r10, 4),
                    "mrr": round(mrr, 4),
                    "n_chunks": built["n_chunks"],
                    "avg_chunk_tokens": round(built["avg_tokens"], 1),
                    "build_time_seconds": round(built["build_time"], 2),
                    "embedding_tokens": m["embedding_tokens"],
                    "embedding_cost_usd": m["embedding_cost_usd"],
                }
            )
            if extra_total:
                extra_passage_stats.append((label, method, extra_hits / extra_total, extra_total))

    write_csv(csv_rows)
    write_markdown(csv_rows, extra_passage_stats, embed_config.model)
    write_failures(still_failing, questions)


def write_csv(rows: list[dict]) -> None:
    path = RESULTS_DIR / "chunking_dev.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path}")


def write_markdown(rows: list[dict], extra_passage_stats: list[tuple[str, str, float, int]], model: str) -> None:
    lines = ["# Chunking experiment results (dev set)\n"]
    lines.append(
        f"Embedding model: `{model}` (hosted API, via Qdrant). Top-k retrieved: {TOP_K}. "
        f"Hit = >= {HIT_THRESHOLD:.0%} passage coverage. min_tokens (heading strategy, held fixed "
        f"in this sweep): {MIN_TOKENS}. MRR is over the top-{TOP_K} retrieved (0 if no hit within "
        f"top-{TOP_K}). embedding_tokens/cost are per-config totals (cache hits cost nothing).\n"
    )
    header = list(rows[0].keys())
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for r in rows:
        lines.append("| " + " | ".join(str(r[h]) for h in header) + " |")
    lines.append("")

    if extra_passage_stats:
        lines.append(
            "## multi_sheet / comparative: extra_sources passage hit rate @10\n"
            "Reported separately — not part of the recall numbers above, which use only "
            "each question's primary source_passage.\n"
        )
        lines.append("| config | method | extra-passage hit rate | n extra passages |")
        lines.append("|---|---|---|---|")
        for label, method, rate, n in extra_passage_stats:
            lines.append(f"| {label} | {method} | {rate:.1%} | {n} |")
        lines.append("")

    (RESULTS_DIR / "chunking_dev.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS_DIR / 'chunking_dev.md'}")


def write_failures(failed_ids: set[str], questions: list[dict]) -> None:
    by_id = {q["id"]: q for q in questions}
    lines = ["# Dev questions with zero hits in every config and method\n"]
    if not failed_ids:
        lines.append("None — every dev question had a hit in at least one config/method.")
    for qid in sorted(failed_ids):
        q = by_id[qid]
        lines.append(f"- **{qid}** ({q['type']}, {q['category']}): {q['question']}")
        lines.append(f"  - source: `{q['source_file']}` > {q['source_section']}")
    path = RESULTS_DIR / "chunking_dev_failures.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(failed_ids)} failures)")


if __name__ == "__main__":
    run()
