# Reranker parity: ONNX vs torch (dev set)

Model `cross-encoder/ms-marco-MiniLM-L-6-v2`, max_length 384, hybrid top-20 candidates, 30 questions (26 answerable).

- score difference (raw logits): max 1.08352, mean 0.201165
- same top-1: 29/30; same top-5 set: 23/30; same top-5 order: 12/30

| backend | recall@1 | recall@5 | recall@10 | mrr | rerank p50 | rerank p95 |
|---|---|---|---|---|---|---|
| torch | 0.3846 | 0.8462 | 0.9615 | 0.5876 | 1449 ms | 1730 ms |
| onnx | 0.4231 | 0.8846 | 0.9615 | 0.6177 | 1828 ms | 2128 ms |
