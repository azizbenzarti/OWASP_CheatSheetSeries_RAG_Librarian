# Generation eval (dev set)

Generator: `gpt-5-nano`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 5, reasoning_effort=minimal. Query embeddings uncached (real API call each time).

**Sample size**: 26 answerable + 4 unanswerable questions. One answerable question is ~3.8 points; one unanswerable is 25 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| correctness | 0.9423 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.9231 | share graded fully `correct` |
| faithfulness (claims) | 1.0 | claims supported by any given source |
| fully faithful answers | 1.0 | answers with every claim supported |
| citation accuracy | 1.0 | cited claims supported by the source they cite |
| gold passage in context | 0.8846 | retrieval: gold passage among the sources given |
| gold passage cited | 0.88 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 1.0 | want 1.0 |
| false refusals | 0.0385 | refused an answerable question; want 0 |
| latency p50 / p95 | 3247.3 / 11894.6 ms | `Librarian.ask`, warm process |
| tokens in / out | 1935.3333 / 163.7667 | generator call, per request (tiktoken) |
| cost per request | $0.000163 | generator + query embedding, list prices; $0.16 per 1,000 requests |

Refusal reasons: `model_declined` 3, `no_valid_citations` 2
