# Generation eval (dev set)

Generator: `gpt-4o-mini`. Judge: `gpt-4.1-mini`. Config: hybrid + MiniLM rerank of top 20 -> top 3. Query embeddings uncached (real API call each time).

**Sample size**: 26 answerable + 4 unanswerable questions. One answerable question is ~3.8 points; one unanswerable is 25 points of the refusal rate.

| metric | value | what it means |
|---|---|---|
| correctness | 0.8654 | judge vs reference, correct=1 / partial=0.5 / incorrect or refused=0, over answerable |
| strict correct | 0.7308 | share graded fully `correct` |
| faithfulness (claims) | 0.9789 | claims supported by any given source |
| fully faithful answers | 0.9259 | answers with every claim supported |
| citation accuracy | 0.9892 | cited claims supported by the source they cite |
| gold passage in context | 0.8077 | retrieval: gold passage among the sources given |
| gold passage cited | 0.8077 | of answered answerable questions, a cited source holds the gold passage |
| "I don't know" on unanswerable | 0.75 | want 1.0 |
| false refusals | 0.0 | refused an answerable question; want 0 |
| latency p50 / p95 | 3436.5 / 7336.6 ms | `Librarian.ask`, warm process |
| tokens in / out | 1348.8667 / 90.7 | generator call, per request (tiktoken) |
| cost per request | $0.000257 | generator + query embedding, list prices; $0.26 per 1,000 requests |

Refusal reasons: `model_declined` 3
