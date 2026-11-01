"""
Cross-encoder reranker: plugs into Retriever's `reranker` slot (see
retriever.py's Reranker type). A cross-encoder scores a (query, chunk) pair
*jointly* in one forward pass -- unlike the bi-encoder cosine similarity
used for vector search, which embeds the query and each chunk separately
and compares them afterward. That joint attention is why it's more
accurate, and also why it's too slow to run over the whole index: it only
reranks a small candidate pool (the hybrid retriever's top 20), not the
full corpus.

Default model: BAAI/bge-reranker-base. Override with RERANKER_MODEL in
.env (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2 -- smaller and faster; see
docs/design.md's ablation for the quality/latency tradeoff between the two).
CPU is fine at this candidate-pool size (20 pairs per query).
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sentence_transformers import CrossEncoder

if TYPE_CHECKING:
    from .retriever import RetrievedChunk

DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-base"


class CrossEncoderReranker:
    """Callable matching retriever.py's Reranker type: (query, chunks) ->
    chunks, reordered by cross-encoder score, with that score stored on
    each chunk as rerank_score. vector_score/vector_rank/bm25_score/
    bm25_rank are untouched, so the pre-rerank picture is still there for
    diagnostics."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.environ.get("RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
        self.model = CrossEncoder(self.model_name)  # loaded once at construction, reused every call

    def __call__(self, query: str, chunks: "list[RetrievedChunk]") -> "list[RetrievedChunk]":
        if not chunks:
            return chunks
        pairs = [(query, c.text) for c in chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)  # one batched forward pass
        for c, s in zip(chunks, scores):
            c.rerank_score = float(s)
        return sorted(chunks, key=lambda c: c.rerank_score, reverse=True)


def make_reranker(model_name: str | None = None) -> CrossEncoderReranker:
    return CrossEncoderReranker(model_name)
