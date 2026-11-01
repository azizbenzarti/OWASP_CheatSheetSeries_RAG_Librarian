"""
Cross-encoder reranker: plugs into Retriever's `reranker` slot (see
retriever.py's Reranker type). A cross-encoder scores a (query, chunk) pair
*jointly* in one forward pass -- unlike the bi-encoder cosine similarity
used for vector search, which embeds the query and each chunk separately
and compares them afterward. That joint attention is why it's more
accurate, and also why it's too slow to run over the whole index: it only
reranks a small candidate pool (the hybrid retriever's top 20), not the
full corpus.

Default model: cross-encoder/ms-marco-MiniLM-L-6-v2 (~22M params). Override
with RERANKER_MODEL in .env (e.g. BAAI/bge-reranker-base -- bigger, somewhat
higher recall@1/MRR, but ~10x the latency: measured well over 1 second per
query even after the tuning below, vs. MiniLM's well under 1 second: see
docs/design.md's ablation for the full before/after numbers behind this
choice, and why bge is kept as the Week-8 comparison, not the default).

Two more tuned defaults, both measured empirically on the dev set, not
guessed (see docs/design.md):
- max_length=384, not the models' own default of 512: real candidates (the
  hybrid retriever's top 20) run 103-641 tokens, and a batch is padded to
  its longest member, so a few long outliers make every pair in the batch
  pay full-length attention cost. 384 cuts that cost by ~25% with no
  recall loss (dropping to 256 goes too far and measurably hurts recall).
- Reranks the same "section_path\\n\\ntext" breadcrumb the embedding model
  sees (chunk.py's embed_text), not bare chunk text: consistently improved
  recall@1 across nearly every (model, max_length) combination tested.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sentence_transformers import CrossEncoder

if TYPE_CHECKING:
    from .retriever import RetrievedChunk

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_MAX_LENGTH = 384


class CrossEncoderReranker:
    """Callable matching retriever.py's Reranker type: (query, chunks) ->
    chunks, reordered by cross-encoder score, with that score stored on
    each chunk as rerank_score. vector_score/vector_rank/bm25_score/
    bm25_rank are untouched, so the pre-rerank picture is still there for
    diagnostics."""

    def __init__(self, model_name: str | None = None, max_length: int | None = None) -> None:
        self.model_name = model_name or os.environ.get("RERANKER_MODEL", DEFAULT_RERANKER_MODEL)
        if max_length is None:
            env_value = os.environ.get("RERANKER_MAX_LENGTH")
            max_length = int(env_value) if env_value else DEFAULT_MAX_LENGTH
        self.max_length = max_length
        self.model = CrossEncoder(self.model_name, max_length=max_length)  # loaded once, reused every call

    def __call__(self, query: str, chunks: "list[RetrievedChunk]") -> "list[RetrievedChunk]":
        if not chunks:
            return chunks
        pairs = [(query, f"{c.section_path}\n\n{c.text}") for c in chunks]
        scores = self.model.predict(pairs, show_progress_bar=False)  # one batched forward pass
        for c, s in zip(chunks, scores):
            c.rerank_score = float(s)
        return sorted(chunks, key=lambda c: c.rerank_score, reverse=True)


def make_reranker(model_name: str | None = None, max_length: int | None = None) -> CrossEncoderReranker:
    return CrossEncoderReranker(model_name, max_length)
