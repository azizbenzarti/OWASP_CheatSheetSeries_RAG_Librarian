# Retrieval ablation (dev set)

Index: `data/index/heading_mt512_min20`. Top-k=10. Hit = >= 70% passage coverage. Search latency includes the query-embedding call (and the rerank pass, for hybrid+rerank rows). Hybrid = RRF (k=60) over top-50 of each retriever; hybrid+rerank reranks hybrid's top 20 with a cross-encoder, two models compared.

**Sample size**: 26 answerable dev questions -> one question is ~3.8 points of recall. Don't read a difference smaller than that as a winner.

| mode | recall@1 | recall@5 | recall@10 | mrr | search_p50_ms | search_p95_ms |
|---|---|---|---|---|---|---|
| bm25 | 0.2308 | 0.7308 | 0.8077 | 0.4194 | 0.6 | 1.0 |
| vector | 0.4231 | 0.7308 | 0.7692 | 0.5603 | 10.1 | 13.2 |
| hybrid | 0.5 | 0.7692 | 0.8462 | 0.6321 | 8.6 | 10.7 |
| hybrid+rerank | 0.3462 | 0.8846 | 0.9615 | 0.5638 | 8061.5 | 8206.6 |
| hybrid+rerank (ms-marco-MiniLM-L-6-v2) | 0.3462 | 0.8077 | 0.9231 | 0.5533 | 1521.6 | 1615.0 |

# "I don't know" calibration (dev set)

### Top vector cosine score (mode=vector, pure cosine, comparable across queries)

- answerable (n=26): min=0.458 p25=0.570 median=0.632 p75=0.677 max=0.748
- unanswerable (n=4): min=0.522 p25=0.539 median=0.543 p75=0.546 max=0.622

### Top reranker score (hybrid top-20, then BAAI/bge-reranker-base)

- answerable (n=26): min=0.113 p25=0.627 median=0.824 p75=0.932 max=0.981
- unanswerable (n=4): min=0.011 p25=0.107 median=0.145 p75=0.184 max=0.236

Proposed vector threshold: 0.458 -> catches 0/4 unanswerable, wrongly rejects 0/26 answerable. Clean separation: False.
Proposed reranker threshold: 0.252 -> catches 4/4 unanswerable, wrongly rejects 1/26 answerable. Clean separation: False.

reranker score separates better on this dev set.

Neither separates cleanly -- expected with only 4 unanswerable dev questions to calibrate against. Recommendation: leave refusal to the generation step (it has the whole answer, not just a retrieval score, to judge from); keep this threshold only as a cheap backup gate, not the primary 'I don't know' mechanism. Do not tune this further on data/test.jsonl.
