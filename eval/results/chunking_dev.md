# Chunking experiment results (dev set)

Embedding model: `text-embedding-3-small` (hosted API, via Qdrant). Top-k retrieved: 10. Hit = >= 70% passage coverage. min_tokens (heading strategy, held fixed in this sweep): 20. MRR is over the top-10 retrieved (0 if no hit within top-10). embedding_tokens is the TRUE full-corpus total for that config (recomputed locally via tiktoken from chunks.jsonl, independent of caching -- several configs were already cached from earlier debugging attempts when this run executed, so the run's own cache-miss count would have understated the real cost). embedding_cost_usd is empty because EMBEDDING_COST_PER_1M_TOKENS isn't set in .env.

| config | method | recall@1 | recall@5 | recall@10 | mrr | n_chunks | avg_chunk_tokens | build_time_seconds | embedding_tokens | embedding_cost_usd |
|---|---|---|---|---|---|---|---|---|---|---|
| heading_mt256_min20 | vector | 0.3846 | 0.6538 | 0.7308 | 0.495 | 3478 | 151.5 | 5.95 | 591132 |  |
| heading_mt256_min20 | bm25 | 0.2692 | 0.5 | 0.6154 | 0.3846 | 3478 | 151.5 | 5.95 | 591132 |  |
| heading_mt512_min20 | vector | 0.4231 | 0.7308 | 0.7692 | 0.5603 | 2756 | 191.3 | 5.05 | 577562 |  |
| heading_mt512_min20 | bm25 | 0.2308 | 0.7308 | 0.8077 | 0.4194 | 2756 | 191.3 | 5.05 | 577562 |  |
| heading_mt1024_min20 | vector | 0.4231 | 0.7308 | 0.7692 | 0.5645 | 2564 | 205.6 | 4.88 | 573836 |  |
| heading_mt1024_min20 | bm25 | 0.2308 | 0.7692 | 0.8462 | 0.4311 | 2564 | 205.6 | 4.88 | 573836 |  |
| fixed_mt256_ov0 | vector | 0.4231 | 0.6923 | 0.7692 | 0.5279 | 2427 | 217.3 | 4.28 | 569972 |  |
| fixed_mt256_ov0 | bm25 | 0.2308 | 0.5 | 0.5385 | 0.3401 | 2427 | 217.3 | 4.28 | 569972 |  |
| fixed_mt256_ov38 | vector | 0.3846 | 0.6154 | 0.7692 | 0.496 | 3504 | 212.4 | 6.11 | 806979 |  |
| fixed_mt256_ov38 | bm25 | 0.3462 | 0.5 | 0.5385 | 0.4029 | 3504 | 212.4 | 6.11 | 806979 |  |
| fixed_mt512_ov0 | vector | 0.3846 | 0.6923 | 0.8077 | 0.5162 | 1199 | 439.9 | 16.6 | 548247 |  |
| fixed_mt512_ov0 | bm25 | 0.3846 | 0.6154 | 0.7692 | 0.4946 | 1199 | 439.9 | 16.6 | 548247 |  |
| fixed_mt512_ov77 | vector | 0.4231 | 0.7692 | 0.8077 | 0.5734 | 1617 | 442.3 | 17.31 | 743715 |  |
| fixed_mt512_ov77 | bm25 | 0.3077 | 0.6154 | 0.8077 | 0.4516 | 1617 | 442.3 | 17.31 | 743715 |  |

## multi_sheet / comparative: extra_sources passage hit rate @10
Reported separately — not part of the recall numbers above, which use only each question's primary source_passage.

| config | method | extra-passage hit rate | n extra passages |
|---|---|---|---|
| heading_mt256_min20 | vector | 50.0% | 10 |
| heading_mt256_min20 | bm25 | 10.0% | 10 |
| heading_mt512_min20 | vector | 50.0% | 10 |
| heading_mt512_min20 | bm25 | 30.0% | 10 |
| heading_mt1024_min20 | vector | 50.0% | 10 |
| heading_mt1024_min20 | bm25 | 30.0% | 10 |
| fixed_mt256_ov0 | vector | 50.0% | 10 |
| fixed_mt256_ov0 | bm25 | 40.0% | 10 |
| fixed_mt256_ov38 | vector | 50.0% | 10 |
| fixed_mt256_ov38 | bm25 | 20.0% | 10 |
| fixed_mt512_ov0 | vector | 70.0% | 10 |
| fixed_mt512_ov0 | bm25 | 70.0% | 10 |
| fixed_mt512_ov77 | vector | 60.0% | 10 |
| fixed_mt512_ov77 | bm25 | 40.0% | 10 |

