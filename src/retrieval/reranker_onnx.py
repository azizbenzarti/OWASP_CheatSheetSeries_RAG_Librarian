"""
Torch-free version of reranker.py for the lite deployment image (Render,
docs/deploy-render.md): the SAME model, cross-encoder/ms-marco-MiniLM-L-6-v2,
run with onnxruntime instead of torch + sentence-transformers.

The ONNX file is the one the model's maintainers publish in the same Hugging
Face repo (onnx/model.onnx, full precision), so the weights are identical;
only the runtime changes. Inputs are built exactly like CrossEncoderReranker:
the "section_path\\n\\ntext" breadcrumb, pairs truncated longest-first to
max_length=384, raw logits as rerank_score. Parity with the torch reranker
was measured on dev (eval/reranker_parity.py, results in
docs/optimisation.md) before it was used anywhere.

Why: torch + sentence-transformers need ~1.5 GB of RAM and a ~2 GB image;
onnxruntime + tokenizers run the same model in a few hundred MB, which fits
the 512 MB instances of hosts like Render.

Select it with RERANKER_BACKEND=onnx (src/api/main.py).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .retriever import RetrievedChunk

# Same values as reranker.py, repeated because importing reranker.py would
# import sentence-transformers (and torch), which the lite image doesn't
# have. tests/test_reranker_onnx.py checks they stay equal.
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_MAX_LENGTH = 384
# RERANKER_ONNX_FILE picks another export from the same repo, e.g.
# onnx/model_quint8_avx2.onnx (8-bit, smaller and faster; parity measured separately).
ONNX_FILE = os.environ.get("RERANKER_ONNX_FILE") or "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"


def download_model(repo: str = DEFAULT_RERANKER_MODEL) -> Path:
    """Fetch (or reuse from the Hugging Face cache) the tokenizer and ONNX
    weights; returns the local snapshot directory. The lite Dockerfile calls
    this at build time, so containers start offline (HF_HUB_OFFLINE=1)."""
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo, allow_patterns=[ONNX_FILE, TOKENIZER_FILE, "config.json"]))


class OnnxCrossEncoderReranker:
    """Callable matching retriever.py's Reranker type, like
    CrossEncoderReranker: (query, chunks) -> chunks sorted by score, with the
    score stored as rerank_score."""

    def __init__(self, model_name: str | None = None, max_length: int | None = None) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        self.model_name = model_name or os.environ.get("RERANKER_MODEL") or DEFAULT_RERANKER_MODEL
        if max_length is None:
            env_value = os.environ.get("RERANKER_MAX_LENGTH")
            max_length = int(env_value) if env_value else DEFAULT_MAX_LENGTH
        self.max_length = max_length

        # Pairs per forward pass. All 20 candidates at 384 tokens in one pass
        # needed > 512 MB and got the container OOM-killed in a Render-sized
        # (512 MB) simulation; scores are per pair, so batching doesn't change them.
        self.batch_size = int(os.environ.get("RERANKER_BATCH_SIZE") or 4)

        model_dir = download_model(self.model_name)
        self.tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE))
        self.tokenizer.enable_truncation(max_length=max_length, strategy="longest_first")
        self.tokenizer.enable_padding()  # pad each batch to its longest pair, like the torch path
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        # No memory arena: give activation buffers back after each pass
        # instead of keeping the peak reserved for the life of the process.
        options.enable_cpu_mem_arena = False
        threads = os.environ.get("RERANKER_THREADS")
        if threads:  # on a CPU quota (PaaS) one thread can beat several fighting over it
            options.intra_op_num_threads = int(threads)
        self.session = ort.InferenceSession(str(model_dir / ONNX_FILE), options, providers=["CPUExecutionProvider"])
        self._input_names = {i.name for i in self.session.get_inputs()}

    def score(self, query: str, documents: list[str]) -> list[float]:
        scores: list[float] = []
        for start in range(0, len(documents), self.batch_size):
            batch = documents[start:start + self.batch_size]
            encodings = self.tokenizer.encode_batch([(query, d) for d in batch])
            feeds = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
            }
            [logits] = self.session.run(None, {k: v for k, v in feeds.items() if k in self._input_names})
            scores += [float(x) for x in logits.reshape(len(batch), -1)[:, 0]]
        return scores

    def __call__(self, query: str, chunks: "list[RetrievedChunk]") -> "list[RetrievedChunk]":
        if not chunks:
            return chunks
        scores = self.score(query, [f"{c.section_path}\n\n{c.text}" for c in chunks])  # same breadcrumb as reranker.py
        for c, s in zip(chunks, scores):
            c.rerank_score = s
        return sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
