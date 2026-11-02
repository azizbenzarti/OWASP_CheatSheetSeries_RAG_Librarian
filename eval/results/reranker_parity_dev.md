# Reranker parity: ONNX vs torch (dev set)

Model `cross-encoder/ms-marco-MiniLM-L-6-v2`, max_length 384, hybrid top-20 candidates, 30 questions (26 answerable).

- score difference (raw logits): max 0.00001, mean 0.000002
- same top-1: 30/30; same top-5 set: 30/30; same top-5 order: 30/30

| backend | recall@1 | recall@5 | recall@10 | mrr | rerank p50 | rerank p95 |
|---|---|---|---|---|---|---|
| torch | 0.3846 | 0.8462 | 0.9615 | 0.5876 | 1441 ms | 1869 ms |
| onnx | 0.3846 | 0.8462 | 0.9615 | 0.5876 | 2015 ms | 2988 ms |
