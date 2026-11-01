# Generation eval (test set)

Generator: `gpt-5-nano`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 5, reasoning_effort=minimal. Query embeddings uncached (real API call each time).

**Sample size**: 76 answerable + 13 unanswerable questions. One answerable question is ~1.3 points; one unanswerable is 8 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| correctness | 0.8947 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.8553 | share graded fully `correct` |
| faithfulness (claims) | 0.9939 | claims supported by any given source |
| fully faithful answers | 0.9744 | answers with every claim supported |
| citation accuracy | 1.0 | cited claims supported by the source they cite |
| gold passage in context | 0.8026 | retrieval: gold passage among the sources given |
| gold passage cited | 0.7639 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 0.5385 | want 1.0 |
| false refusals | 0.0526 | refused an answerable question; want 0 |
| latency p50 / p95 | 4066.0 / 7001.9 ms | `Librarian.ask`, warm process |
| tokens in / out | 1825.5393 / 134.7191 | generator call, per request (tiktoken) |
| cost per request | $0.000146 | generator + query embedding, list prices; $0.15 per 1,000 requests |

Refusal reasons: `model_declined` 8, `no_valid_citations` 3
