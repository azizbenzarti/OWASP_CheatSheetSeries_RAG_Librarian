"""
Retrieval ablation on data/dev.jsonl ONLY (data/test.jsonl is never opened):
bm25 vs vector vs hybrid (RRF) vs hybrid+rerank, using the online Retriever
against the already-built index. Same hit definition as
eval/chunking_experiment.py (>= 70% passage coverage), so numbers are
directly comparable with eval/results/chunking_dev.md.

hybrid+rerank is run with TWO reranker models (BAAI/bge-reranker-base, the
default, and the smaller/faster cross-encoder/ms-marco-MiniLM-L-6-v2), both
reported, per docs/design.md's Week-8 interest in a cheaper reranker.

Also writes:
  - eval/results/retrieval_dev_failures.md: questions hybrid+rerank misses
    that another mode hits, and questions every mode misses, with each
    mode's top-3 section_paths. q021/q109 are flagged as known label/passage
    issues (see docs/design.md), not retriever bugs.
  - "I don't know" calibration: top vector cosine score AND top reranker
    score, answerable vs unanswerable, with a proposed min-score threshold.

Sample size: only 26 answerable dev questions, so one question is worth
about 1/26 = 3.8 percentage points of recall. Differences smaller than
that between two modes/configs are noise, not a winner -- said explicitly
wherever this script compares two numbers.

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
from src.retrieval.reranker import DEFAULT_RERANKER_MODEL, make_reranker  # noqa: E402
from src.retrieval.retriever import DEFAULT_INDEX_DIR, MODES, Retriever  # noqa: E402

RERANK_CANDIDATES = 20  # hybrid's top 20 go to the reranker (per docs/design.md)
SECOND_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
KNOWN_ISSUES = {
    "q021": "passage spans a sub-heading boundary -- no chunking config can contain it whole (docs/design.md)",
    "q109": "primary passage is a generic intro that never mentions the topic (MCP); the real answer is in "
    "extra_sources, which this hit-check doesn't credit (docs/design.md)",
}


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def run_mode(retriever: Retriever, questions: list[dict], mode: str, top_k: int, candidates: int | None = None):
    """One (retriever config, mode) combination over every dev question.
    Returns (metrics dict, {question id: hit flags per rank}, {question id: top-3 (section_path, source_file)},
    {question id: (top vector_score, top rerank_score)} -- reranking is slow, so the calibration step reuses
    this instead of re-running the reranker a second time over the same 26 answerable questions)."""
    flags_by_id: dict[str, list[bool]] = {}
    top3_by_id: dict[str, list[tuple[str, str]]] = {}
    top_scores_by_id: dict[str, tuple[float | None, float | None]] = {}
    latencies = []
    kwargs = {"candidates": candidates} if candidates is not None else {}
    for q in questions:
        res = retriever.retrieve(q["question"], top_k=top_k, mode=mode, **kwargs)
        latencies.append(res.timings_ms.get("total_ms", 0.0))
        flags_by_id[q["id"]] = hit_flags([{"text": c.text} for c in res.chunks], normalize(q["source_passage"]))
        top3_by_id[q["id"]] = [(c.section_path, c.source_file) for c in res.chunks[:3]]
        top_scores_by_id[q["id"]] = (
            (res.chunks[0].vector_score, res.chunks[0].rerank_score) if res.chunks else (None, None)
        )
    r1, r5, r10, mrr = recall_and_mrr([flags_by_id[q["id"]] for q in questions])
    metrics = {
        "recall@1": round(r1, 4), "recall@5": round(r5, 4), "recall@10": round(r10, 4), "mrr": round(mrr, 4),
        "search_p50_ms": round(statistics.median(latencies), 1), "search_p95_ms": round(pct(latencies, 95), 1),
    }
    return metrics, flags_by_id, top3_by_id, top_scores_by_id


def write_csv(rows: list[dict]) -> None:
    path = RESULTS_DIR / "retrieval_dev.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path}")


def write_markdown(rows: list[dict], index_dir: str, top_k: int, n_answerable: int) -> None:
    header = list(rows[0])
    lines = [
        "# Retrieval ablation (dev set)\n",
        f"Index: `{index_dir}`. Top-k={top_k}. Hit = >= {HIT_THRESHOLD:.0%} passage coverage. "
        "Search latency includes the query-embedding call (and the rerank pass, for hybrid+rerank rows). "
        f"Hybrid = RRF (k=60) over top-50 of each retriever; hybrid+rerank reranks hybrid's top "
        f"{RERANK_CANDIDATES} with a cross-encoder, two models compared.\n",
        f"**Sample size**: {n_answerable} answerable dev questions -> one question is ~"
        f"{100 / n_answerable:.1f} points of recall. Don't read a difference smaller than that as a winner.\n",
        "| " + " | ".join(header) + " |", "|" + "---|" * len(header),
        *["| " + " | ".join(str(r[h]) for h in header) + " |" for r in rows],
    ]
    (RESULTS_DIR / "retrieval_dev.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {RESULTS_DIR / 'retrieval_dev.md'}")


def write_failures(
    questions: list[dict],
    flags_by_mode: dict[str, dict[str, list[bool]]],
    top3_by_mode: dict[str, dict[str, list[tuple[str, str]]]],
    primary_rerank_label: str,
) -> None:
    by_id = {q["id"]: q for q in questions}
    all_modes = list(flags_by_mode.keys())

    def hit(mode: str, qid: str) -> bool:
        return any(flags_by_mode[mode][qid])

    rerank_misses_others_hit = [
        qid for qid in by_id if not hit(primary_rerank_label, qid) and any(hit(m, qid) for m in all_modes if m != primary_rerank_label)
    ]
    everyone_misses = [qid for qid in by_id if not any(hit(m, qid) for m in all_modes)]

    def section(title: str, qids: list[str]) -> list[str]:
        out = [f"## {title}\n"]
        if not qids:
            out.append("None.\n")
            return out
        for qid in qids:
            q = by_id[qid]
            note = f" **Known issue**: {KNOWN_ISSUES[qid]}" if qid in KNOWN_ISSUES else ""
            out.append(f"### {qid} ({q['type']}, {q['category']}){note}")
            out.append(f"> {q['question']}")
            out.append(f"Expected source: `{q['source_file']}` > {q['source_section']}\n")
            for mode in all_modes:
                hit_mark = "HIT" if hit(mode, qid) else "miss"
                top3 = ", ".join(f"{sp} ({sf})" for sp, sf in top3_by_mode[mode][qid]) or "(no results)"
                out.append(f"- **{mode}** [{hit_mark}]: {top3}")
            out.append("")
        return out

    lines = ["# Retrieval failure diagnostics (dev set)\n"]
    lines += section(f"{primary_rerank_label} misses, another mode hits", rerank_misses_others_hit)
    lines += section("Every mode misses", everyone_misses)

    path = RESULTS_DIR / "retrieval_dev_failures.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(rerank_misses_others_hit)} rerank-only misses, {len(everyone_misses)} universal misses)")


def write_calibration(
    answerable: list[dict],
    unanswerable: list[dict],
    vector_scores_answerable: dict[str, tuple[float | None, float | None]],
    rerank_scores_answerable: dict[str, tuple[float | None, float | None]],
    vector_retriever: Retriever,
    rerank_retriever: Retriever,
) -> None:
    # Reranking 26 questions already cost ~minutes once in the main ablation
    # loop; reuse those top scores for the answerable group instead of
    # re-running retrieval a second time. Only the 4 unanswerable questions
    # (outside that loop, which only covers answerable ones) are fresh calls.
    def fresh_vector_scores(qs: list[dict]) -> list[float]:
        out = []
        for q in qs:
            res = vector_retriever.retrieve(q["question"], top_k=1, mode="vector")
            out.append(res.chunks[0].vector_score if res.chunks else 0.0)
        return out

    def fresh_rerank_scores(qs: list[dict]) -> list[float]:
        out = []
        for q in qs:
            res = rerank_retriever.retrieve(q["question"], top_k=1, mode="hybrid", candidates=RERANK_CANDIDATES)
            out.append(res.chunks[0].rerank_score if res.chunks and res.chunks[0].rerank_score is not None else 0.0)
        return out

    vec_ans = [vector_scores_answerable[q["id"]][0] or 0.0 for q in answerable]
    rer_ans = [rerank_scores_answerable[q["id"]][1] or 0.0 for q in answerable]
    vec_un = fresh_vector_scores(unanswerable)
    rer_un = fresh_rerank_scores(unanswerable)

    def describe(label: str, ans: list[float], un: list[float]) -> str:
        lines = [f"### {label}\n"]
        for group_label, values in (("answerable", ans), ("unanswerable", un)):
            if values:
                lines.append(
                    f"- {group_label} (n={len(values)}): min={min(values):.3f} p25={pct(values,25):.3f} "
                    f"median={statistics.median(values):.3f} p75={pct(values,75):.3f} max={max(values):.3f}"
                )
        return "\n".join(lines)

    def best_threshold(ans: list[float], un: list[float]) -> tuple[float, int, int, bool]:
        """Try every score in the combined set as a candidate threshold
        (reject if top score < threshold); keep the one that catches the
        most unanswerable questions minus the answerable ones it wrongly
        rejects. Returns (threshold, caught, wrongly_rejected, clean_separation)."""
        if not un or not ans:
            return 0.0, 0, 0, False
        candidates = sorted(set(ans) | set(un))
        best = (float("-inf"), None)
        for t in candidates:
            caught = sum(1 for s in un if s < t)
            wrongly_rejected = sum(1 for s in ans if s < t)
            net = caught - wrongly_rejected
            if net > best[0]:
                best = (net, (t, caught, wrongly_rejected))
        _, (t, caught, wrongly_rejected) = best
        clean = max(un) < min(ans)
        return t, caught, wrongly_rejected, clean

    vec_t, vec_caught, vec_wrong, vec_clean = best_threshold(vec_ans, vec_un)
    rer_t, rer_caught, rer_wrong, rer_clean = best_threshold(rer_ans, rer_un)

    lines = [
        "\n# \"I don't know\" calibration (dev set)\n",
        describe("Top vector cosine score (mode=vector, pure cosine, comparable across queries)", vec_ans, vec_un),
        "",
        describe(f"Top reranker score (hybrid top-{RERANK_CANDIDATES}, then {DEFAULT_RERANKER_MODEL})", rer_ans, rer_un),
        "",
        f"Proposed vector threshold: {vec_t:.3f} -> catches {vec_caught}/{len(vec_un)} unanswerable, "
        f"wrongly rejects {vec_wrong}/{len(vec_ans)} answerable. Clean separation: {vec_clean}.",
        f"Proposed reranker threshold: {rer_t:.3f} -> catches {rer_caught}/{len(rer_un)} unanswerable, "
        f"wrongly rejects {rer_wrong}/{len(rer_ans)} answerable. Clean separation: {rer_clean}.",
    ]
    better = "reranker" if (rer_caught - rer_wrong) > (vec_caught - vec_wrong) else "vector"
    lines.append(f"\n{better} score separates better on this dev set.")
    if not vec_clean and not rer_clean:
        lines.append(
            f"\nNeither separates cleanly -- expected with only {len(unanswerable)} unanswerable dev questions "
            "to calibrate against. Recommendation: leave refusal to the generation step (it has the whole "
            "answer, not just a retrieval score, to judge from); keep this threshold only as a cheap backup "
            "gate, not the primary 'I don't know' mechanism. Do not tune this further on data/test.jsonl."
        )
    text = "\n".join(lines) + "\n"
    print(text)
    with (RESULTS_DIR / "retrieval_dev.md").open("a", encoding="utf-8") as f:
        f.write(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index-dir", default=None)
    ap.add_argument("-k", "--top-k", type=int, default=10)
    args = ap.parse_args()

    rows = [json.loads(line) for line in DEV_PATH.open(encoding="utf-8")]
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    print(f"dev: {len(answerable)} answerable, {len(unanswerable)} unanswerable "
          f"(1 question ~= {100/len(answerable):.1f} points of recall)", flush=True)

    base_retriever = Retriever.from_config(args.index_dir)

    out_rows = []
    flags_by_mode: dict[str, dict[str, list[bool]]] = {}
    top3_by_mode: dict[str, dict[str, list[tuple[str, str]]]] = {}

    top_scores_by_mode: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for mode in MODES:
        metrics, flags, top3, top_scores = run_mode(base_retriever, answerable, mode, args.top_k)
        out_rows.append({"mode": mode, **metrics})
        flags_by_mode[mode], top3_by_mode[mode], top_scores_by_mode[mode] = flags, top3, top_scores
        print(out_rows[-1], flush=True)

    primary_rerank_label = None
    primary_rerank_retriever = None
    primary_rerank_top_scores = None
    for model_name in (DEFAULT_RERANKER_MODEL, SECOND_RERANKER_MODEL):
        label = "hybrid+rerank" if model_name == DEFAULT_RERANKER_MODEL else f"hybrid+rerank ({model_name.split('/')[-1]})"
        print(f"loading reranker {model_name} ...", flush=True)
        rerank_retriever = Retriever.from_config(args.index_dir, reranker=make_reranker(model_name))
        metrics, flags, top3, top_scores = run_mode(rerank_retriever, answerable, "hybrid", args.top_k, candidates=RERANK_CANDIDATES)
        if model_name == DEFAULT_RERANKER_MODEL:
            primary_rerank_label, primary_rerank_retriever, primary_rerank_top_scores = label, rerank_retriever, top_scores
        out_rows.append({"mode": label, **metrics})
        flags_by_mode[label], top3_by_mode[label] = flags, top3
        print(out_rows[-1], flush=True)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(out_rows)
    write_markdown(out_rows, str(args.index_dir or DEFAULT_INDEX_DIR), args.top_k, len(answerable))
    write_failures(answerable, flags_by_mode, top3_by_mode, primary_rerank_label)
    write_calibration(
        answerable, unanswerable, top_scores_by_mode["vector"], primary_rerank_top_scores,
        base_retriever, primary_rerank_retriever,
    )


if __name__ == "__main__":
    main()
