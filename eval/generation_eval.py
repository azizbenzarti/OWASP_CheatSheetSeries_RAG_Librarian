"""
Generation eval: runs the deployed pipeline (hybrid + rerank top 5 ->
generator -> citation check, i.e. the same Librarian the API serves) over
an eval split and grades every answer. Defaults to data/dev.jsonl; pass
--split test only for final / Week-8 before-after numbers (data/SPLIT.md).

Metrics (retrieval and generation kept apart, per the brief):
  - correctness     LLM judge vs the human-reviewed reference answer:
                    correct=1, partial=0.5, incorrect=0. A refusal on an
                    answerable question counts as 0.
  - faithfulness    share of the answer's claims supported by ANY of the
                    sources the model was given (no outside knowledge).
  - citation acc.   share of cited claims supported by the source(s) they
                    actually cite -- "does the cited chunk really say that?"
  - gold cited      a cited chunk contains the gold passage (same >= 70%
                    coverage hit as eval/retrieval_eval.py). A good answer
                    from the wrong passage shows up here, not in correctness.
  - "I don't know"  refusals on unanswerable questions (want all) and on
                    answerable ones (false refusals, want none).
  - latency p50/p95 of Librarian.ask, and an estimated cost per request from
                    the exact prompts sent (tiktoken) x per-token prices.

The judge is a stronger model than the generator (default gpt-4.1-mini,
the strongest non-reasoning model our OpenAI project can use) and sees
only the question, reference answer, the system's answer and the sources;
it is told not to use outside knowledge. Judge cost is not part of the
per-request cost (it is an eval cost only).

Sample size: dev has 26 answerable + 4 unanswerable questions, so one
question is ~3.8 points on answerable metrics and 25 points on the
unanswerable refusal rate. Don't read small differences as a winner.

Usage (repo root or the api container; Qdrant up, index built, .env filled):
    python eval/generation_eval.py                      # dev, deployed generator
    python eval/generation_eval.py --generator gemini   # compare with Gemini
Writes eval/results/generation_<split>.{md,csv,jsonl} and
generation_<split>_failures.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking_experiment import HIT_THRESHOLD, RESULTS_DIR, coverage, normalize  # noqa: E402

from src.generation import Answer, Librarian  # noqa: E402

SPLITS = {"dev": ROOT / "data" / "dev.jsonl", "test": ROOT / "data" / "test.jsonl"}
TOP_K = 5  # what the API sends to the model
# USD per 1M tokens (input, output). Check current prices before quoting these in the report.
PRICES = {
    "gpt-4o-mini": (0.15, 0.60), "gpt-4.1-mini": (0.40, 1.60), "gpt-5-nano": (0.05, 0.40),
    "gpt-5-mini": (0.25, 2.00), "text-embedding-3-small": (0.02, 0.0),
}
SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}

JUDGE_PROMPT = """\
You grade answers produced by a retrieval-augmented assistant over the OWASP Cheat Sheet Series.

You receive: the question, a human-reviewed reference answer, the assistant's answer with [n] \
citation markers, and the numbered sources the assistant was given. Judge ONLY from this text; \
do not use outside knowledge, even if you know something to be true.

1. Split the assistant's answer into atomic claims (each factual statement or recommendation). \
Skip connective phrases, and statements that the sources do not cover part of the question.
2. For each claim give:
   - citations: the [n] numbers attached to that claim (empty list if none);
   - supported_by_cited: true only if the cited source(s) state or directly imply the claim \
(false if it has no citation);
   - supported_by_sources: true if ANY of the given sources states or directly implies it.
3. correctness, against the reference answer: "correct" if the answer conveys the reference's \
key point(s) without contradicting it (extra correct detail is fine); "partial" if it gets some \
but misses or blurs a key point; "incorrect" if it misses the main point or contradicts it.
4. rationale: one or two sentences explaining the correctness grade.\
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "integer"}},
                    "supported_by_cited": {"type": "boolean"},
                    "supported_by_sources": {"type": "boolean"},
                },
                "required": ["claim", "citations", "supported_by_cited", "supported_by_sources"],
                "additionalProperties": False,
            },
        },
        "correctness": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
        "rationale": {"type": "string"},
    },
    "required": ["claims", "correctness", "rationale"],
    "additionalProperties": False,
}


def pct(values: list[float], p: float) -> float | None:
    """Same percentile as eval/retrieval_eval.py, None for no data."""
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def openai_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMBEDDING_API_KEY")
    if not key:
        sys.exit("needs OPENAI_API_KEY or EMBEDDING_API_KEY in .env")
    return OpenAI(api_key=key, max_retries=5)


class RecordingGenerator:
    """Wraps the real generator and keeps the exact prompts and output of
    the last call, for token counting. Does not change what is sent."""

    def __init__(self, inner) -> None:
        self.inner, self.model, self.last = inner, getattr(inner, "model", None), None

    def __call__(self, system_prompt: str, user_prompt: str) -> str | None:
        out = self.inner(system_prompt, user_prompt)
        self.last = (system_prompt, user_prompt, out or "")
        return out


def build_librarian(generator: str, rerank: bool = True) -> tuple[Librarian, RecordingGenerator]:
    """Same wiring as the API (src/api/main.py): retriever + MiniLM reranker
    + the chosen generator. Query embeddings bypass every cache
    (cache_queries=False) so latency is a real API call each time, even
    when the same questions were run before."""
    from src.retrieval.reranker import make_reranker
    from src.retrieval.retriever import Retriever

    if generator == "gemini":
        from src.generation.gemini import GeminiGenerator

        inner = GeminiGenerator()
    else:
        from src.api.openai_generator import OpenAIGenerator

        inner = OpenAIGenerator()
    rec = RecordingGenerator(inner)
    retriever = Retriever.from_config(reranker=make_reranker() if rerank else None, cache_queries=False)
    return Librarian(retriever, rec, rec.model), rec


def gold_passages(row: dict) -> list[str]:
    passages = [row["source_passage"]] + [e["source_passage"] for e in row.get("extra_sources") or []]
    return [normalize(p) for p in passages if p]


def judge(client, model: str, row: dict, ans: Answer, chunk_text: dict[str, str]) -> dict:
    sources = "\n\n".join(
        f"[{s.number}] {s.title} > {s.section_path}\n{chunk_text[s.chunk_id]}" for s in ans.sources
    )
    user = (f"QUESTION:\n{row['question']}\n\nREFERENCE ANSWER:\n{row['answer']}\n\n"
            f"ASSISTANT ANSWER:\n{ans.answer}\n\nSOURCES:\n{sources}")
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": "grade", "schema": JUDGE_SCHEMA, "strict": True}},
    )
    return json.loads(resp.choices[0].message.content)


def token_counter(model: str):
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")
    return lambda text: len(enc.encode(text))


def evaluate(
    rows: list[dict], librarian: Librarian, rec: RecordingGenerator, judge_model: str,
    top_k: int = TOP_K, rerank_candidates: int = 20,
) -> list[dict]:
    client = openai_client()
    chunk_text = {cid: c["text"] for cid, c in librarian.retriever.chunks_by_id.items()}
    count = token_counter(rec.model or "gpt-4o-mini")
    results = []
    for i, row in enumerate(rows, 1):
        rec.last = None
        if hasattr(rec.inner, "last_usage"):
            rec.inner.last_usage = None
        t = time.perf_counter()
        ans = librarian.ask(row["question"], top_k=top_k, rerank_candidates=rerank_candidates)
        latency_ms = (time.perf_counter() - t) * 1000

        usage = rec.last and getattr(rec.inner, "last_usage", None)
        gold = gold_passages(row) if row["answerable"] else []

        def hits(sources) -> bool:
            return any(coverage(normalize(chunk_text[s.chunk_id]), g) >= HIT_THRESHOLD for s in sources for g in gold)

        r = {
            "id": row["id"], "type": row["type"], "gold_answerable": row["answerable"],
            "question": row["question"], "reference": row["answer"],
            "answerable": ans.answerable, "refusal_reason": ans.refusal_reason, "answer": ans.answer,
            "cited": [s.number for s in ans.citations], "invalid_citations": ans.invalid_citations,
            "gold_in_context": hits(ans.sources) if gold else None,
            "gold_cited": hits(ans.citations) if gold and ans.answerable else None,
            "latency_ms": round(latency_ms, 1), "timings_ms": ans.timings_ms,
            # Billed usage from the API when the generator reports it (includes
            # hidden reasoning tokens); else a tiktoken count of the exact text.
            "input_tokens": usage["input_tokens"] if usage else (count(rec.last[0] + rec.last[1]) if rec.last else 0),
            "output_tokens": usage["output_tokens"] if usage else (count(rec.last[2]) if rec.last else 0),
            "embed_tokens": count(row["question"]),
        }
        if ans.answerable:
            g = judge(client, judge_model, row, ans, chunk_text)
            claims = g["claims"]
            cited = [c for c in claims if c["citations"]]
            r.update({
                "correctness": g["correctness"], "rationale": g["rationale"], "n_claims": len(claims),
                "faithfulness": mean([float(c["supported_by_sources"]) for c in claims]) if claims else 1.0,
                "citation_accuracy": mean([float(c["supported_by_cited"]) for c in cited]),
                "unsupported_claims": [c["claim"] for c in claims if not c["supported_by_sources"]],
                "miscited_claims": [c["claim"] for c in cited if not c["supported_by_cited"]],
                "n_cited_claims": len(cited), "n_cited_supported": sum(c["supported_by_cited"] for c in cited),
                "n_supported": sum(c["supported_by_sources"] for c in claims),
            })
        elif row["answerable"]:
            r.update({"correctness": "incorrect", "rationale": f"refused ({ans.refusal_reason})"})
        print(f"[{i}/{len(rows)}] {row['id']} answerable={ans.answerable} "
              f"{r.get('correctness', '-')} faith={r.get('faithfulness', '-')} {latency_ms:.0f}ms", flush=True)
        results.append(r)
    return results


def summarize(results: list[dict], model: str | None) -> dict:
    ans_rows = [r for r in results if r["gold_answerable"]]
    unans_rows = [r for r in results if not r["gold_answerable"]]
    answered = [r for r in results if r["answerable"]]
    answered_gold = [r for r in ans_rows if r["answerable"]]
    claims = sum(r["n_claims"] for r in answered)
    cited_claims = sum(r["n_cited_claims"] for r in answered)
    lat = [r["latency_ms"] for r in results]

    p_in, p_out = PRICES.get(model or "", (None, None))
    e_in, _ = PRICES["text-embedding-3-small"]
    cost = None
    if p_in is not None:
        per = [(r["input_tokens"] * p_in + r["output_tokens"] * p_out + r["embed_tokens"] * e_in) / 1e6 for r in results]
        cost = sum(per) / len(per)
    return {
        "n": len(results), "n_answerable": len(ans_rows), "n_unanswerable": len(unans_rows),
        "correctness": mean([SCORE[r["correctness"]] for r in ans_rows]),
        "strict_correct": mean([float(r["correctness"] == "correct") for r in ans_rows]),
        "faithfulness_claims": round(sum(r["n_supported"] for r in answered) / claims, 4) if claims else None,
        "fully_faithful_answers": mean([float(r["faithfulness"] == 1.0) for r in answered]),
        "citation_accuracy": round(sum(r["n_cited_supported"] for r in answered) / cited_claims, 4) if cited_claims else None,
        "gold_in_context": mean([float(r["gold_in_context"]) for r in ans_rows]),
        "gold_cited_when_answered": mean([float(r["gold_cited"]) for r in answered_gold]),
        "idk_on_unanswerable": mean([float(not r["answerable"]) for r in unans_rows]),
        "false_refusals": mean([float(not r["answerable"]) for r in ans_rows]),
        "latency_p50_ms": pct(lat, 50), "latency_p95_ms": pct(lat, 95),
        "avg_input_tokens": mean([r["input_tokens"] for r in results]),
        "avg_output_tokens": mean([r["output_tokens"] for r in results]),
        "cost_per_request_usd": round(cost, 6) if cost is not None else None,
    }


def write_outputs(
    split: str, results: list[dict], summary: dict, model: str | None, judge_model: str, config: str, tag: str = "",
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    base = RESULTS_DIR / f"generation_{split}{'_' + tag if tag else ''}"
    with open(f"{base}.jsonl", "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cols = ["id", "type", "gold_answerable", "answerable", "refusal_reason", "correctness", "faithfulness",
            "citation_accuracy", "gold_in_context", "gold_cited", "n_claims", "latency_ms", "input_tokens", "output_tokens"]
    with open(f"{base}.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    s = summary
    def fmt(v):
        return "-" if v is None else v
    cost = s["cost_per_request_usd"]
    lines = [
        f"# Generation eval ({split} set)", "",
        f"Generator: `{model}`. Judge: `{judge_model}`. Config: {config}. Query embeddings uncached "
        "(real API call each time).", "",
        f"**Sample size**: {s['n_answerable']} answerable + {s['n_unanswerable']} unanswerable questions. One answerable "
        f"question is ~{100 / max(1, s['n_answerable']):.1f} points; one unanswerable is "
        f"{100 / max(1, s['n_unanswerable']):.0f} points of the refusal rate.", "",
        "| metric | value | what it means |", "|---|---|---|",
        f"| correctness | {fmt(s['correctness'])} | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |",
        f"| strict correct | {fmt(s['strict_correct'])} | share graded fully `correct` |",
        f"| faithfulness (claims) | {fmt(s['faithfulness_claims'])} | claims supported by any given source |",
        f"| fully faithful answers | {fmt(s['fully_faithful_answers'])} | answers with every claim supported |",
        f"| citation accuracy | {fmt(s['citation_accuracy'])} | cited claims supported by the source they cite |",
        f"| gold passage in context | {fmt(s['gold_in_context'])} | retrieval: gold passage among the sources given |",
        f"| gold passage cited | {fmt(s['gold_cited_when_answered'])} | of answered answerable questions, a cited source holds the gold passage |",
        f"| \"I don't know\" on unanswerable | {fmt(s['idk_on_unanswerable'])} | want 1.0 |",
        f"| false refusals | {fmt(s['false_refusals'])} | refused an answerable question; want 0 |",
        f"| latency p50 / p95 | {fmt(s['latency_p50_ms'])} / {fmt(s['latency_p95_ms'])} ms | `Librarian.ask`, warm process |",
        f"| tokens in / out | {fmt(s['avg_input_tokens'])} / {fmt(s['avg_output_tokens'])} | generator call, per request (tiktoken) |",
        f"| cost per request | {'-' if cost is None else f'${cost:.6f}'} | generator + query embedding, list prices; "
        f"{'-' if cost is None else f'${cost * 1000:.2f}'} per 1,000 requests |",
        "",
        "Refusal reasons: " + (", ".join(
            f"`{k}` {v}" for k, v in sorted(_count(r["refusal_reason"] for r in results if not r["answerable"]).items())
        ) or "none"),
    ]
    (Path(f"{base}.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")

    fail = [f"# Generation failures ({split} set)", "",
            "Every question that was refused when answerable, answered when unanswerable, graded below `correct`, "
            "or has an unsupported / mis-cited claim.", ""]
    for r in results:
        bad = (
            (r["gold_answerable"] and r.get("correctness") != "correct")
            or (not r["gold_answerable"] and r["answerable"])
            or r.get("unsupported_claims") or r.get("miscited_claims")
        )
        if not bad:
            continue
        fail += [f"## {r['id']} ({r['type']}) — {r.get('correctness', 'answered an unanswerable question')}", "",
                 f"**Q:** {r['question']}", "", f"**Reference:** {r['reference']}", "",
                 f"**Answer** ({'refused: ' + str(r['refusal_reason']) if not r['answerable'] else 'cited ' + str(r['cited'])}): {r['answer']}", "",
                 f"gold in context: {r['gold_in_context']} · gold cited: {r['gold_cited']}", ""]
        if r.get("rationale"):
            fail += [f"Judge: {r['rationale']}", ""]
        for c in r.get("unsupported_claims") or []:
            fail.append(f"- unsupported: {c}")
        for c in r.get("miscited_claims") or []:
            fail.append(f"- mis-cited: {c}")
        fail.append("")
    (Path(f"{base}_failures.md")).write_text("\n".join(fail) + "\n", encoding="utf-8")


def _count(values) -> dict:
    out: dict = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=SPLITS, default="dev")
    ap.add_argument("--generator", choices=["openai", "gemini"], default=os.environ.get("GENERATOR") or "openai")
    ap.add_argument("--gen-model", default=None, help="OpenAI generation model (overrides OPENAI_GENERATION_MODEL)")
    ap.add_argument("--reasoning-effort", default=None, help="for gpt-5*/o* generators, e.g. minimal")
    ap.add_argument("--top-k", type=int, default=TOP_K, help="sources given to the generator")
    ap.add_argument("--rerank-candidates", type=int, default=20, help="hybrid candidates the reranker scores")
    ap.add_argument("--no-rerank", action="store_true", help="plain hybrid retrieval")
    ap.add_argument("--judge-model", default="gpt-4.1-mini")
    ap.add_argument("--tag", default="", help="suffix for the output files, e.g. topk3")
    ap.add_argument("--limit", type=int, default=None, help="first N questions only (smoke run, writes nothing)")
    args = ap.parse_args()
    if args.gen_model:
        os.environ["OPENAI_GENERATION_MODEL"] = args.gen_model
    if args.reasoning_effort:
        os.environ["OPENAI_REASONING_EFFORT"] = args.reasoning_effort

    rows = [json.loads(line) for line in SPLITS[args.split].open(encoding="utf-8")][: args.limit]
    librarian, rec = build_librarian(args.generator, rerank=not args.no_rerank)
    config = (f"hybrid{'' if args.no_rerank else f' + MiniLM rerank of top {args.rerank_candidates}'} -> top "
              f"{args.top_k}{f', reasoning_effort={args.reasoning_effort}' if args.reasoning_effort else ''}")
    results = evaluate(rows, librarian, rec, args.judge_model, args.top_k, args.rerank_candidates)
    summary = summarize(results, rec.model)
    print(json.dumps({"config": config, "model": rec.model, **summary}, indent=2))
    if args.limit is None:
        write_outputs(args.split, results, summary, rec.model, args.judge_model, config, args.tag)
        print(f"wrote eval/results/generation_{args.split}{'_' + args.tag if args.tag else ''}.*")


if __name__ == "__main__":
    main()
