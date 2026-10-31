"""
Retrieval ablation on data/dev.jsonl ONLY (data/test.jsonl is never opened):
bm25 vs vector vs hybrid (RRF), using the online Retriever against the
already-built index. Same hit definition as eval/chunking_experiment.py
(>= 70% passage coverage), so numbers are directly comparable with
eval/results/chunking_dev.md.

Also prints the distribution of the top cosine similarity for answerable vs
unanswerable dev questions, to help pick `min_vector_score` for the
"I don't know" gate (no value is guessed here).

Usage (repo root, Qdrant up, .env filled, data/index/ present):
    python eval/retrieval_eval.py [--index-dir data/index/heading_mt512_min20] [-k 10]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking_experiment import (  # noqa: E402  (reuse the project's own hit logic)
    DEV_PATH, HIT_THRESHOLD, RESULTS_DIR, hit_flags, normalize, recall_and_mrr,
)
from src.retrieval.retriever import MODES, Retriever  # noqa: E402


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index-dir", default=None)
    ap.add_argument("-k", "--top-k", type=int, default=10)
    args = ap.parse_args()

    rows = [json.loads(line) for line in DEV_PATH.open(encoding="utf-8")]
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    retriever = Retriever.from_config(args.index_dir)
    print(f"dev: {len(answerable)} answerable, {len(unanswerable)} unanswerable", flush=True)

    out_rows = []
    for mode in MODES:
        flags_all, latencies = [], []
        for q in answerable:
            res = retriever.retrieve(q["question"], top_k=args.top_k, mode=mode)
            latencies.append(res.timings_ms.get("total_ms", 0.0))
            flags_all.append(hit_flags([{"text": c.text} for c in res.chunks], normalize(q["source_passage"])))
        r1, r5, r10, mrr = recall_and_mrr(flags_all)
        out_rows.append({
            "mode": mode, "recall@1": round(r1, 4), "recall@5": round(r5, 4),
            "recall@10": round(r10, 4), "mrr": round(mrr, 4),
            "search_p50_ms": round(statistics.median(latencies), 1),
            "search_p95_ms": round(pct(latencies, 95), 1),
        })
        print(out_rows[-1], flush=True)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with (RESULTS_DIR / "retrieval_dev.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        w.writeheader()
        w.writerows(out_rows)
    header = list(out_rows[0])
    lines = [
        "# Retrieval ablation (dev set)\n",
        f"Index: `{args.index_dir or 'default'}`. Top-k={args.top_k}. Hit = >= {HIT_THRESHOLD:.0%} passage coverage. "
        "Search latency includes the query-embedding call. Hybrid = RRF (k=60) over top-50 of each retriever.\n",
        "| " + " | ".join(header) + " |", "|" + "---|" * len(header),
        *["| " + " | ".join(str(r[h]) for h in header) + " |" for r in out_rows],
    ]
    (RESULTS_DIR / "retrieval_dev.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- "I don't know" calibration: top cosine similarity per question ---
    def top_scores(qs):
        out = []
        for q in qs:
            res = retriever.retrieve(q["question"], top_k=1, mode="vector")
            out.append(res.chunks[0].vector_score if res.chunks else 0.0)
        return out

    for label, qs in (("answerable", answerable), ("unanswerable", unanswerable)):
        if qs:
            s = top_scores(qs)
            print(f"top cosine, {label} (n={len(s)}): min={min(s):.3f} p25={pct(s,25):.3f} "
                  f"median={statistics.median(s):.3f} p75={pct(s,75):.3f} max={max(s):.3f}")
    print("Pick min_vector_score between the two distributions; only 'unanswerable' dev rows should fall below it.")


if __name__ == "__main__":
    main()
