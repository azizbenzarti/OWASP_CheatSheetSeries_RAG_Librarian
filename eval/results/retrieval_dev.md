# Retrieval ablation (dev set)

Index: `/home/azizbzt/Desktop/ai-projects/RAG/data/index/heading_mt512_min20`. Top-k=10. Hit = >= 70% passage coverage. Search latency includes the query-embedding call (and the rerank pass, for hybrid+rerank rows). Hybrid = RRF (k=60) over top-50 of each retriever; hybrid+rerank reranks hybrid's top 20 with a cross-encoder, two models compared.

**Sample size**: 26 answerable dev questions -> one question is ~3.8 points of recall. Don't read a difference smaller than that as a winner.

| mode | recall@1 | recall@5 | recall@10 | mrr | search_p50_ms | search_p95_ms |
|---|---|---|---|---|---|---|
| bm25 | 0.2308 | 0.7308 | 0.8077 | 0.4194 | 0.4 | 0.8 |
| vector | 0.4231 | 0.7692 | 0.8077 | 0.5795 | 7.7 | 9.4 |
| hybrid | 0.5 | 0.7692 | 0.8462 | 0.6321 | 8.1 | 9.4 |
| hybrid+rerank | 0.3846 | 0.8462 | 0.9615 | 0.5876 | 784.8 | 897.4 |
| hybrid+rerank (bge-reranker-base) | 0.4231 | 0.9231 | 0.9615 | 0.6292 | 4579.7 | 4823.2 |

# "I don't know" calibration (dev set)

### Top vector cosine score (mode=vector, pure cosine, comparable across queries)

- answerable (n=26): min=0.458 p25=0.570 median=0.632 p75=0.677 max=0.748
- unanswerable (n=4): min=0.522 p25=0.539 median=0.543 p75=0.546 max=0.622

### Top reranker score (hybrid top-20, then cross-encoder/ms-marco-MiniLM-L-6-v2)

- answerable (n=26): min=-3.609 p25=-0.920 median=0.790 p75=2.759 max=4.091
- unanswerable (n=4): min=-6.364 p25=-2.652 median=-0.675 p75=1.302 max=1.501

Proposed vector threshold: 0.458 -> catches 0/4 unanswerable, wrongly rejects 0/26 answerable. Clean separation: False.
Proposed reranker threshold: -3.609 -> catches 1/4 unanswerable, wrongly rejects 0/26 answerable. Clean separation: False.

reranker score separates better on this dev set.

Neither separates cleanly -- expected with only 4 unanswerable dev questions to calibrate against. Recommendation: leave refusal to the generation step (it has the whole answer, not just a retrieval score, to judge from); keep this threshold only as a cheap backup gate, not the primary 'I don't know' mechanism. Do not tune this further on data/test.jsonl.

# Cached vs uncached query-embedding latency (dev set)

Cached = in-process + on-disk embedding cache both active (production default). Uncached = both bypassed, forcing a real OpenAI embeddings.create() call every time (src/indexing/embed.py's use_cache=False / Retriever.from_config(cache_queries=False)). BM25 isn't shown: it never calls the embedding API.

| mode | cached_p50_ms | cached_p95_ms | uncached_p50_ms | uncached_p95_ms |
|---|---|---|---|---|
| vector | 4.5 | 7.2 | 521.9 | 1537.0 |
| hybrid | 4.3 | 6.2 | 411.7 | 787.6 |
| hybrid+rerank | 651.5 | 721.1 | 1025.0 | 1496.3 |
