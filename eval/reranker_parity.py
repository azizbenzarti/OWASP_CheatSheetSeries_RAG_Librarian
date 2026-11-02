"""
Parity check: the ONNX reranker (src/retrieval/reranker_onnx.py) against the
torch one (src/retrieval/reranker.py) on the dev set, before the ONNX one is
used anywhere.

For every dev question it takes hybrid's top-20 candidates (exactly what the
reranker sees in production), scores them with both backends and compares:
  - scores: max / mean absolute difference of the raw logits
  - ranking: is the top-5 the same set, in the same order?
  - recall@1/@5 (answerable questions, same >= 70% coverage hit as
    eval/retrieval_eval.py)
  - latency of the rerank call itself, p50/p95, both backends

Needs both torch and onnxruntime installed (the full image + `pip install
onnxruntime`), Qdrant up and the index built.
Usage: python eval/reranker_parity.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking_experiment import DEV_PATH, RESULTS_DIR, hit_flags, normalize, recall_and_mrr  # noqa: E402

from src.retrieval.reranker import make_reranker  # noqa: E402
from src.retrieval.reranker_onnx import OnnxCrossEncoderReranker  # noqa: E402
from src.retrieval.retriever import Retriever  # noqa: E402

CANDIDATES = 20


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> None:
    rows = [json.loads(line) for line in DEV_PATH.open(encoding="utf-8")]
    retriever = Retriever.from_config()  # no reranker: we rerank the same candidates twice ourselves
    backends = {"torch": make_reranker(), "onnx": OnnxCrossEncoderReranker()}

    diffs: list[float] = []
    same_top5_set = same_top5_order = same_top1 = 0
    flags: dict[str, list[list[bool]]] = {"torch": [], "onnx": []}
    latency: dict[str, list[float]] = {"torch": [], "onnx": []}
    for row in rows:
        candidates = retriever.retrieve(row["question"], top_k=CANDIDATES, mode="hybrid", candidates=CANDIDATES).chunks
        ranked = {}
        for name, rerank in backends.items():
            fresh = [type(c)(**{**c.to_dict(), "rerank_score": None}) for c in candidates]
            t = time.perf_counter()
            ranked[name] = rerank(row["question"], fresh)
            latency[name].append((time.perf_counter() - t) * 1000)
        by_id = {c.chunk_id: c.rerank_score for c in ranked["onnx"]}
        diffs += [abs(c.rerank_score - by_id[c.chunk_id]) for c in ranked["torch"]]
        t5, o5 = [c.chunk_id for c in ranked["torch"][:5]], [c.chunk_id for c in ranked["onnx"][:5]]
        same_top5_set += set(t5) == set(o5)
        same_top5_order += t5 == o5
        same_top1 += t5[0] == o5[0]
        if row["answerable"]:
            passage = normalize(row["source_passage"])
            for name in backends:
                flags[name].append(hit_flags([c.to_dict() for c in ranked[name][:10]], passage))

    n = len(rows)
    lines = [
        "# Reranker parity: ONNX vs torch (dev set)", "",
        f"Model `cross-encoder/ms-marco-MiniLM-L-6-v2`, max_length 384, hybrid top-{CANDIDATES} candidates, "
        f"{n} questions ({len(flags['torch'])} answerable).", "",
        f"- score difference (raw logits): max {max(diffs):.5f}, mean {sum(diffs) / len(diffs):.6f}",
        f"- same top-1: {same_top1}/{n}; same top-5 set: {same_top5_set}/{n}; same top-5 order: {same_top5_order}/{n}", "",
        "| backend | recall@1 | recall@5 | recall@10 | mrr | rerank p50 | rerank p95 |", "|---|---|---|---|---|---|---|",
    ]
    for name in backends:
        r1, r5, r10, mrr = recall_and_mrr(flags[name])
        lines.append(f"| {name} | {r1:.4f} | {r5:.4f} | {r10:.4f} | {mrr:.4f} | "
                     f"{pct(latency[name], 50):.0f} ms | {pct(latency[name], 95):.0f} ms |")
    text = "\n".join(lines) + "\n"
    print(text)
    (RESULTS_DIR / "reranker_parity_dev.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
