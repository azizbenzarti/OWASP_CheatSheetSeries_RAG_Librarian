"""
The local half of the index build, with no API call and no Qdrant write:
chunks.jsonl, the BM25 index and manifest.json, for a deployment whose
vectors already live in a hosted Qdrant (docs/deploy-render.md).

build.py's build_index() does chunk -> embed -> upsert -> BM25 -> write in
one go. This reuses its own functions for every step except embed/upsert,
so the chunks are byte-for-byte the ones whose vectors were uploaded
(same pinned corpus commit, same chunker, deterministic chunk_ids). The
Retriever then checks at startup that Qdrant holds one point per chunk.

Usage (corpus fetched first, EMBEDDING_MODEL set -- it is only used to pick
the tokenizer for chunk sizes, nothing is sent to the API):
    python -m src.indexing.build_local [--strategy heading --max-tokens 512 --overlap 0 --min-tokens 20]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import bm25s

from ..indexing.vectordb import collection_name as vdb_collection_name
from .build import INDEX_DIR, build_chunks, config_name, tokenize_for_bm25


def build_local(strategy: str, max_tokens: int, overlap: int, min_tokens: int, embedding_model: str):
    chunks = build_chunks(strategy, max_tokens, overlap, min_tokens, embedding_model)
    out = INDEX_DIR / config_name(strategy, max_tokens, overlap, min_tokens)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    bm25_index = bm25s.BM25()
    bm25_index.index([tokenize_for_bm25(c["embed_text"]) for c in chunks], show_progress=False)
    bm25_index.save(str(out / "bm25"), corpus=None, show_progress=False)

    manifest = {
        "embedding_model": embedding_model,
        "qdrant_collection": vdb_collection_name(strategy, max_tokens, overlap),
        "strategy": strategy, "max_tokens": max_tokens, "overlap": overlap, "min_tokens": min_tokens,
        "n_chunks": len(chunks),
        "built_by": "src.indexing.build_local (no embeddings; vectors already in Qdrant)",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out, len(chunks)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", choices=["heading", "fixed"], default="heading")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=0)
    ap.add_argument("--min-tokens", type=int, default=20)
    args = ap.parse_args()
    model = os.environ.get("EMBEDDING_MODEL")
    if not model:
        raise SystemExit("EMBEDDING_MODEL must be set (it picks the tokenizer used for chunk sizes).")
    out, n = build_local(args.strategy, args.max_tokens, args.overlap, args.min_tokens, model)
    print(f"built {n} chunks + BM25 at {out} (no embeddings, no Qdrant writes)")


if __name__ == "__main__":
    main()
