# Generation eval (test set)

Generator: `gpt-4o-mini`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 5. Query embeddings uncached (real API call each time).

**Sample size**: 76 answerable + 13 unanswerable questions. One answerable question is ~1.3 points; one unanswerable is 8 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| correctness | 0.8684 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.7763 | share graded fully `correct` |
| faithfulness (claims) | 0.9918 | claims supported by any given source |
| fully faithful answers | 0.9737 | answers with every claim supported |
| citation accuracy | 0.9958 | cited claims supported by the source they cite |
| gold passage in context | 0.8026 | retrieval: gold passage among the sources given |
| gold passage cited | 0.7973 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 0.8462 | want 1.0 |
| false refusals | 0.0263 | refused an answerable question; want 0 |
| latency p50 / p95 | 3748.2 / 5578.4 ms | `Librarian.ask`, warm process |
| tokens in / out | 1826.5393 / 84.2472 | generator call, per request (tiktoken) |
| cost per request | $0.000325 | generator + query embedding, list prices; $0.33 per 1,000 requests |

Refusal reasons: `model_declined` 13
