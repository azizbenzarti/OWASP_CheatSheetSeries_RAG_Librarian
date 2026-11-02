# Deploying on Render (free plan, lite images)

Two Render web services from `render.yaml`, and the vectors in a free Qdrant
Cloud cluster:

```
browser -> owasp-librarian-ui (Dockerfile.ui, Streamlit)
               -> owasp-librarian-api (Dockerfile.api-lite, FastAPI, ONNX reranker)
                      -> Qdrant Cloud (vectors)   -> OpenAI (query embedding + answer)
```

The lite API runs the **same pipeline** as the main Docker setup: the same
chunks (byte-identical, built inside the image), the same hybrid retrieval,
and the same reranker model on onnxruntime instead of torch (identical
top-5 on 30/30 dev questions, `eval/results/reranker_parity_dev.md`).

## Know the limits first (free plan)

Measured locally with Render-like limits (`docker --memory 512m --cpus
0.1`), not on Render itself:

| | free (0.1 CPU) | starter (0.5 CPU) | main setup, 2 vCPU VM |
|---|---|---|---|
| seconds per question | 50-100 s | 10-12 s | ~4 s |
| peak RAM (512 MB limit) | ~350 MB | ~320 MB | n/a |

- **Slow:** the CPU reranker dominates. The UI waits up to 300 s
  (`ASK_TIMEOUT_S` in `render.yaml`).
- **Sleeps:** after 15 minutes without traffic each service stops. The
  next visitor waits for it to start again (~30-60 s) before the question
  even begins.
- **No disk:** `data/logs/*.jsonl` and `/stats` reset at every restart and
  sleep. Every request and feedback event is also printed to stdout as one
  JSON line (`{"event": "requests", ...}` / `{"event": "feedback", ...}`),
  so the Render log viewer keeps them. Download them there before
  reporting real-user numbers.
- **Public API:** the API URL is public too, and every `/ask` spends the
  OpenAI key. Set a monthly budget limit on the OpenAI project.

To make it faster, change `plan: free` to `plan: starter` for the API in
`render.yaml` (paid, ~10-12 s). `RERANKER_ONNX_FILE=onnx/model_quint8_avx2.onnx`
uses the 8-bit model (~25% faster on top). It is **not** identical to the
evaluated reranker (different top-5 on 7/30 dev questions,
`eval/results/reranker_parity_dev_int8.md`), so if you use it, say so in
the report.

## 1. Qdrant Cloud: create the cluster (5 min)

1. Sign up at <https://cloud.qdrant.io>, then **Create cluster**, Free tier
   (1 GB; our vectors use ~17 MB). Pick a region near Render's (e.g.
   Frankfurt, if you pick Frankfurt on Render).
2. Copy the **cluster URL** (`https://xxxx.<region>.cloud.qdrant.io`) and
   create an **API key**. Keep both out of chat, issues and the repo.

## 2. Upload the vectors once (from your laptop, ~1 min, $0)

This runs the normal index build with Qdrant Cloud as the target. The
embeddings are already in the local cache volume, so no OpenAI call is
made. The local stack must have been started once (`docker compose up`).

PowerShell, repo root:

```powershell
$env:QDRANT_URL = "https://xxxx.<region>.cloud.qdrant.io:6333"
$env:QDRANT_API_KEY = Read-Host "Qdrant API key"
docker compose run --rm -e QDRANT_URL -e QDRANT_API_KEY -e ENSURE_INDEX=0 api `
  python -m src.indexing.build --strategy heading --max-tokens 512 --overlap 0 --min-tokens 20
Remove-Item Env:QDRANT_API_KEY
```

The printed manifest should show `"qdrant_collection": "chunks_heading_mt512"`,
`"n_chunks": 2756` and `"embedding_cache_hits": 2756` (all from cache, no
OpenAI cost). This only
changes the cloud cluster; the local Qdrant is untouched.

## 3. Render: deploy the Blueprint (10 min, plus ~5 min build)

1. Sign up at <https://render.com> with GitHub. Render needs access to the
   repo: it belongs to `azizbenzarti`, so either Aziz connects it from his
   account, or you deploy from a fork.
2. **New, Blueprint**, pick the repo and branch `main`. Render reads
   `render.yaml` and shows both services.
3. Fill in the secrets it asks for:
   - API: `EMBEDDING_API_KEY` (the OpenAI key), `QDRANT_URL` (with `:6333`),
     `QDRANT_API_KEY`.
   - UI: `API_URL`. Use the API's URL, `https://owasp-librarian-api.onrender.com`
     (Render shows it on the API service page; it can differ if the name
     is taken).
4. **Apply.** The API build fetches the corpus and builds the chunks inside
   the image (~5 min the first time).

## 4. Check it

```bash
curl -s https://owasp-librarian-api.onrender.com/health
# {"status":"ok","index_loaded":true,"model":"gpt-4o-mini","qdrant":"ok","chunks":2756,"rerank":true}
```

`"qdrant": "out of sync"` means the cloud collection doesn't match the
chunks: redo step 2. A 503 with an `error` means a missing or wrong
variable: check the API's logs in Render.

Then open `https://owasp-librarian-ui.onrender.com`. That is the URL for the
README and the report. The first question after a sleep is the slowest.

## Updating

Every push to `main` redeploys both services automatically. The vectors
only need re-uploading (step 2) if the corpus commit or the chunking config
changes.
