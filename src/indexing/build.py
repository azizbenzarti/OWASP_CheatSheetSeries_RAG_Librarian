"""
Build the chunks + BM25 index + Qdrant collection for one chunking config.

chunks.jsonl and manifest.json are still the source of truth for chunk
text/metadata and build stats; embeddings themselves live in Qdrant now,
not in a local embeddings.npy (see docs/design.md, "Index choice").
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import bm25s

from .chunk import chunk_document, make_token_counter
from .embed import EmbeddingConfig, EmbeddingStats, embed_texts
from .load import load_all_documents
from .vectordb import collection_name as vdb_collection_name
from .vectordb import ensure_collection, get_client, upsert_chunks, vector_search as vdb_vector_search

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_DIR = ROOT / "data" / "index"

# Lowercase + keep hyphenated security terms as one token (x-frame-options,
# sha-256, argon2id) instead of a generic tokenizer that splits on "-".
_BM25_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-]*")


def tokenize_for_bm25(text: str) -> list[str]:
    return _BM25_TOKEN_RE.findall(text.lower())


def config_name(strategy: str, max_tokens: int, overlap: int, min_tokens: int) -> str:
    if strategy == "heading":
        return f"heading_mt{max_tokens}_min{min_tokens}"
    return f"fixed_mt{max_tokens}_ov{overlap}"


def build_chunks(strategy: str, max_tokens: int, overlap: int, min_tokens: int, model_name: str) -> list[dict]:
    count_tokens = make_token_counter(model_name)
    chunks: list[dict] = []
    for doc in load_all_documents():
        chunks.extend(chunk_document(doc, strategy, max_tokens, overlap, min_tokens, count_tokens))
    return chunks


def build_index(
    strategy: str,
    max_tokens: int,
    overlap: int,
    min_tokens: int,
    embed_config: EmbeddingConfig,
    out_dir: Path | None = None,
) -> Path:
    t0 = time.time()
    chunks = build_chunks(strategy, max_tokens, overlap, min_tokens, embed_config.model)
    embed_texts_list = [c["embed_text"] for c in chunks]

    stats = EmbeddingStats(embed_config.cost_per_1m_tokens)
    vectors = embed_texts(embed_texts_list, embed_config, stats=stats)

    qdrant = get_client()
    collection = vdb_collection_name(strategy, max_tokens, overlap)
    ensure_collection(qdrant, collection, vector_size=len(vectors[0]))
    upsert_chunks(qdrant, collection, chunks, vectors)

    bm25_index = bm25s.BM25()
    bm25_index.index([tokenize_for_bm25(t) for t in embed_texts_list], show_progress=False)

    out = out_dir or (INDEX_DIR / config_name(strategy, max_tokens, overlap, min_tokens))
    out.mkdir(parents=True, exist_ok=True)

    with (out / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    # corpus=None: chunk text/ids already live in chunks.jsonl, no need for
    # bm25s to save a second copy of them.
    bm25_index.save(str(out / "bm25"), corpus=None, show_progress=False)

    manifest = {
        "embedding_model": embed_config.model,
        "qdrant_collection": collection,
        "vector_size": len(vectors[0]),
        "strategy": strategy,
        "max_tokens": max_tokens,
        "overlap": overlap,
        "min_tokens": min_tokens,
        "commit": chunks[0]["commit"] if chunks else None,
        "n_chunks": len(chunks),
        "n_documents": len({c["source_file"] for c in chunks}),
        "build_time_seconds": round(time.time() - t0, 2),
        **stats.as_dict(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def load_chunks(index_dir: Path) -> list[dict]:
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def vector_search(collection: str, embed_config: EmbeddingConfig, query: str, k: int = 10) -> list[dict]:
    """For manual testing only. Returns the top-k chunk payloads with a '_score' field."""
    qdrant = get_client()
    [query_vector] = embed_texts([query], embed_config, show_progress=False)
    return vdb_vector_search(qdrant, collection, query_vector, k=k)


def bm25_search(index_dir: Path, query: str, k: int = 10) -> list[dict]:
    """For manual testing only. Returns the top-k chunks with a '_score' field."""
    chunks = load_chunks(index_dir)
    bm25_index = bm25s.BM25.load(str(index_dir / "bm25"), load_corpus=False)
    q_tokens = tokenize_for_bm25(query)
    doc_ids, scores = bm25_index.retrieve([q_tokens], corpus=list(range(len(chunks))), k=k, show_progress=False)
    return [{**chunks[i], "_score": float(s)} for i, s in zip(doc_ids[0], scores[0])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["heading", "fixed"], default="heading")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=0)
    parser.add_argument("--min-tokens", type=int, default=20)
    args = parser.parse_args()

    embed_config = EmbeddingConfig()  # reads EMBEDDING_* from .env; stops clearly if EMBEDDING_MODEL is unset
    out = build_index(args.strategy, args.max_tokens, args.overlap, args.min_tokens, embed_config)
    manifest = json.loads((out / "manifest.json").read_text())
    print(f"built index at {out}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
