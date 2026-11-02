# Generation eval (dev set)

Generator: `gpt-5-nano`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 5, reasoning_effort=minimal. Query embeddings uncached (real API call each time).

**Sample size**: 26 answerable + 4 unanswerable questions. One answerable question is ~3.8 points; one unanswerable is 25 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| **overall accuracy** | 0.9833 | all questions: correctness on answerable, refused-or-not on unanswerable |
| correctness | 0.9808 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.9615 | share graded fully `correct` |
| faithfulness (claims) | 0.9924 | claims supported by any given source |
| fully faithful answers | 0.9615 | answers with every claim supported |
| citation accuracy | 1.0 | cited claims supported by the source they cite |
| gold passage in context | 0.8846 | retrieval: gold passage among the sources given |
| gold passage cited | 0.8462 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 1.0 | want 1.0 |
| false refusals | 0.0 | refused an answerable question; want 0 |
| latency p50 / p95 | 3709.8 / 6156.4 ms | `Librarian.ask`, warm process |
| tokens in / out | 1935.3333 / 168.3 | generator call, per request (tiktoken) |
| cost per request | $0.000165 | generator + query embedding, list prices; $0.17 per 1,000 requests |

Refusal reasons: `declined_in_text` 1, `model_declined` 3
