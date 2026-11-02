# Week 8 optimisation report

**Target (from the brief):** cut cost per request *or* p95 latency by 50%,
losing at most 2 points of accuracy on our own eval, measured before and
after on the same test set.

**Result: target not met.** The only change that halves cost (generator
`gpt-4o-mini` -> `gpt-5-nano`) lost 2.3 and 3.9 points of overall accuracy
in two test runs, so we kept `gpt-4o-mini` in production. Halving p95
latency is not reachable with this architecture (see "Why latency can't be
halved"). Everything below was measured; nothing is estimated unless it
says so.

## How we measured

- Harness: `eval/generation_eval.py`. It runs the deployed pipeline (the
  same `Librarian` the API serves) on every question, then an LLM judge
  (`gpt-4.1-mini`, a stronger model than the generator) grades each answer
  against the human-reviewed reference. Query embeddings bypass every cache,
  so each run pays a real embedding call.
- **Overall accuracy** = one score over all questions: correct=1 /
  partial=0.5 / incorrect or refused=0 on answerable questions, plus 1 for
  refusing (0 for answering) each unanswerable question. This is the number
  the "at most 2 points" rule is checked on. Refusing is part of accuracy:
  a confident answer to a question the cheat sheets don't cover is a wrong
  answer.
- Cost per request = billed input/output tokens of the generator call (from
  the API's `usage`) x list price, plus the query embedding. Prices used
  (USD per 1M tokens): gpt-4o-mini 0.15 / 0.60, gpt-5-nano 0.05 / 0.40,
  text-embedding-3-small 0.02. Check them against OpenAI's pricing page
  before quoting.
- **Tuning on dev, decisions on test.** dev (26 answerable + 4 unanswerable)
  is for trying ideas. test (76 + 13) is for before/after. On dev, one
  answerable question is ~3.8 points; on test, one question of either kind
  is ~1.1 points of overall accuracy.
- **Disclosure.** The test set was run three times during Week 8: before,
  nano, nano + rule. The refusal rule (below) was designed after looking at
  nano's test failures, so its test result is slightly optimistic, not
  pessimistic. We stopped there rather than keep tuning on test.

## Baseline: where the time and money go

Test set, `gpt-4o-mini`, hybrid + MiniLM rerank of top 20 -> top 5 sources:

| stage | p50 | p95 |
|---|---|---|
| query embedding (OpenAI API) | 0.44 s | 1.41 s |
| BM25 | 0.001 s | 0.002 s |
| cross-encoder rerank (CPU, in the container) | 1.61 s | 2.53 s |
| generation (OpenAI API) | 1.55 s | 2.60 s |
| **total** | **3.75 s** | **5.58 s** |

Cost: 1,827 input + 84 output tokens per request = **$0.000325**. Input is
84% of that: the system prompt plus five ~290-token passages.

## Experiments

dev rows are for direction only; the two decision rows are on test.

| run | overall acc. | correctness | IDK on unanswerable | false refusals | p50 / p95 | tokens in / out | cost / request |
|---|---|---|---|---|---|---|---|
| dev: baseline | 0.900 | 0.923 | 3/4 | 0/26 | 3.3 / 5.5 s | 1936 / 97 | $0.000350 |
| dev: top 3 sources instead of 5 | 0.850 | 0.865 | 3/4 | 0/26 | 3.4 / 7.3 s | 1349 / 91 | $0.000257 (-27%) |
| dev: rerank 10 candidates instead of 20 | 0.833 | 0.846 | 3/4 | 1/26 | 2.8 / 4.8 s | 1942 / 98 | $0.000350 |
| dev: no reranker | 0.867 | 0.885 | 3/4 | 1/26 | 2.0 / 5.7 s | 1955 / 97 | $0.000352 |
| dev: gpt-5-nano (reasoning=minimal) | 0.950 | 0.942 | 4/4 | 1/26 | 3.2 / 11.9 s | 1935 / 164 | $0.000163 (-53%) |
| dev: gpt-5-nano + prompt reminder | 0.867 | 0.962 | 1/4 | 0/26 | 4.4 / 7.7 s | 2055 / 161 | $0.000168 |
| dev: gpt-5-nano + refusal-in-text rule | 0.983 | 0.981 | 4/4 | 0/26 | 3.7 / 6.2 s | 1935 / 168 | $0.000165 (-53%) |
| **test: before** (gpt-4o-mini) | **0.865** | 0.868 | 11/13 | 2/76 | 3.7 / 5.6 s | 1827 / 84 | **$0.000325** |
| **test: gpt-5-nano** | 0.843 (**-2.2**) | 0.895 | 7/13 | 4/76 | 4.1 / 7.0 s | 1826 / 135 | $0.000146 (**-55%**) |
| **test: gpt-5-nano + rule** | 0.826 (**-3.9**) | 0.849 | 9/13 | 5/76 | 4.3 / 6.9 s | 1826 / 130 | $0.000144 (**-56%**) |

Per-question results for every row are in
`eval/results/generation_{dev,test}_<tag>.{md,csv,jsonl}`, with the
`_failures.md` file listing each wrong, partial or unsupported answer.

### What each lever did

**Fewer sources (top 3).** Cuts input tokens by 30% but cost only 27%, far
from 50%, and lost 5 points on dev: "gold passage cited" fell from 0.88 to
0.81, i.e. the passage that answers the question is sometimes ranked 4th or
5th. Rejected.

**Shrinking or skipping the reranker.** Removing it saves ~1.6 s of CPU at
p50 but doesn't change cost (the reranker runs locally and is free), and it
lowered accuracy on dev (0.867 and 0.833 vs 0.900). p95 barely moved,
because p95 is dominated by the two network calls. Rejected.

**gpt-5-nano instead of gpt-4o-mini.** The only lever that halves cost: a
third of the input price outweighs its extra hidden reasoning tokens (out
84 -> ~135). On dev it looked better than the baseline. On test it failed
the way dev was too small to show (4 unanswerable questions): it answered 4
more of the 13 questions the corpus doesn't cover. Reading those answers
showed the cause. Nano usually *knew*: it wrote "the provided sources do not
describe end-to-end encryption for WebSocket messages..." but set
`answerable: true`, so our refusal logic never fired. It also dropped the
`[n]` markers more often (`no_valid_citations` refusals of answerable
questions).

**Prompt reminder (rejected).** Restating the refusal and citation rules at
the end of the system prompt made it worse on dev (1/4 refusals). Nano
started writing "the question cannot be answered from these sources.
Missing detail: ..." as an *answer*.

**Refusal-in-text rule (kept as a safety net).** `src/generation/answer.py`
now also refuses (`declined_in_text`) when the answer's first sentence says
the sources don't cover the question ("The provided sources do not ...").
Checked offline on 341 saved answers before enabling it: it caught 4 real
refusals and hit 0 real answers. On the second test run it turned 3 prose
refusals into proper "I don't know"s (9/13 vs 7/13). It never fires on
`gpt-4o-mini` output, so production behaviour is unchanged, but it protects
against the failure if the model is ever swapped.

**Why nano still failed with the rule.** Correctness on answerable questions
moved from 0.895 to 0.849 between two runs with the same model (the rule
only touches refusals). That 4.6-point swing is nano's own run-to-run
variance, more than twice the 2-point budget. We can't promise "at most 2
points lost" with a model whose own noise is bigger than that.

## Why latency can't be halved

Halving p95 means 5.58 s -> 2.79 s. The generation call alone has a p95 of
2.60 s and the embedding call 1.41 s. Both are network calls to OpenAI that
we don't control, and they already add up to more than the target before
any retrieval. Dropping the reranker entirely, the largest local cost, gave
5.7 s p95 on dev: no improvement at p95. Only latency we don't own is left.

Things that would help, not done: streaming the answer (lower
time-to-first-word, same end-to-end p95); a GPU or ONNX/quantised reranker
(only matters at p50).

## Decision

| | before | after Week 8 |
|---|---|---|
| generator | gpt-4o-mini | gpt-4o-mini (unchanged) |
| refusal rules | 4 | 5 (+ `declined_in_text` safety net) |
| cost / request | $0.000325 | $0.000325 |
| overall accuracy (test) | 0.865 | 0.865 |

We chose accuracy, and specifically refusal behaviour, over a 55% cost cut.
For a security assistant a confident answer to an uncovered question is
the most harmful failure, and nano made 2-4 more of them per 13 such
questions. At our scale the saving is $0.18 per 1,000 questions (see the
cost model).

## Cost model

Measured per request: **$0.000325** with gpt-4o-mini, **$0.000146** with
gpt-5-nano. The query embedding is ~$0.0000004 (20 tokens), negligible.
Plus a VM for Qdrant + API + UI (2 vCPU / 4 GB, ~$25/month at list price,
see `docs/deploy.md`).

Traffic is an **assumption**: ~200 questions/day today (a class of users
during the project), so 20,000/day at 100x.

| | today (200/day) | 100x (20,000/day) |
|---|---|---|
| OpenAI, gpt-4o-mini | $0.07/day, ~$2/month | $6.50/day, ~$195/month |
| OpenAI, gpt-5-nano | $0.03/day, ~$1/month | $2.92/day, ~$88/month |
| hosting | 1 VM, ~$25/month | 20,000/day is ~0.23 req/s on average, ~1-2 req/s at peak. The CPU reranker (~1.6 s per question) saturates 2 vCPU at about 1 req/s, so 2 VMs or a 4-8 vCPU VM, ~$50-100/month |
| **total** | **~$27/month** (hosting is 93%) | **~$250-300/month** (tokens are ~70%) |

At today's scale the model choice doesn't matter: hosting dominates. At
100x, generation tokens dominate and nano would save ~$110/month. That's
where it becomes worth fixing nano's refusals properly (more unanswerable
questions to tune on, a cascade to gpt-4o-mini when nano refuses or cites
nothing), and worth caching repeated questions (identical questions skip
retrieval and generation entirely; the saving equals the repeat rate,
which the request log will show once real users arrive).
