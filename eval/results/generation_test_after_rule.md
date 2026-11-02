# Generation eval (test set)

Generator: `gpt-5-nano`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 5, reasoning_effort=minimal. Query embeddings uncached (real API call each time).

**Sample size**: 76 answerable + 13 unanswerable questions. One answerable question is ~1.3 points; one unanswerable is 8 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| **overall accuracy** | 0.8258 | all questions: correctness on answerable, refused-or-not on unanswerable |
| correctness | 0.8487 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.8026 | share graded fully `correct` |
| faithfulness (claims) | 0.9873 | claims supported by any given source |
| fully faithful answers | 0.9467 | answers with every claim supported |
| citation accuracy | 0.9936 | cited claims supported by the source they cite |
| gold passage in context | 0.8026 | retrieval: gold passage among the sources given |
| gold passage cited | 0.7887 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 0.6923 | want 1.0 |
| false refusals | 0.0658 | refused an answerable question; want 0 |
| latency p50 / p95 | 4255.1 / 6935.6 ms | `Librarian.ask`, warm process |
| tokens in / out | 1825.5393 / 130.3258 | generator call, per request (tiktoken) |
| cost per request | $0.000144 | generator + query embedding, list prices; $0.14 per 1,000 requests |

Refusal reasons: `declined_in_text` 3, `model_declined` 7, `no_valid_citations` 4
