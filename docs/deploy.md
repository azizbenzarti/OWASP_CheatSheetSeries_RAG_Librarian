# Deploying The Librarian

The whole service is one `docker compose up`: Qdrant, the API and the
Streamlit UI. Deploying means running that on a machine with a public IP,
with only the UI reachable from the internet.

## What the server needs

| | minimum | why |
|---|---|---|
| OS | Ubuntu 22.04/24.04, x86_64 | the image uses CPU-only torch wheels for x86_64 |
| CPU / RAM | 2 vCPU, 4 GB RAM | the reranker runs on CPU (~1-2 s per question); 2 GB is not enough |
| Disk | 20 GB | image ~2.2 GB, build cache, index + Qdrant volume < 1 GB |
| Ports open | 22 (SSH), 8501 (UI), or 80 | nothing else; Qdrant and the API are bound to 127.0.0.1 |

Any provider works (university VM, Azure for Students, DigitalOcean via the
GitHub Student Pack, ...). A 2 vCPU / 4 GB VM costs about $20-25/month at
list price.

## First deployment

```bash
# 1. Docker (official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

# 2. The code
git clone https://github.com/azizbenzarti/OWASP_CheatSheetSeries_RAG_Librarian.git
cd OWASP_CheatSheetSeries_RAG_Librarian

# 3. Secrets: type the key into the file on the server, never paste it anywhere else
cp .env.example .env
nano .env        # EMBEDDING_API_KEY=..., EMBEDDING_MODEL=text-embedding-3-small
chmod 600 .env

# 4. Run (first start: builds the image ~10 min, then fetches the corpus and
#    builds the index ~2 min, ~$0.02 of embeddings)
docker compose up -d --build
docker compose logs -f api      # wait for "Application startup complete"
```

Check it:

```bash
curl -s localhost:8000/health   # {"status":"ok", ... "chunks":2756, "rerank":true}
curl -sI localhost:8501 | head -1
```

Then open `http://<server-ip>:8501` from your own machine. That is the URL
for the README and the report.

To serve it on port 80 instead of 8501, add `- "80:8501"` under the `ui`
service's `ports`. For HTTPS with a domain name, put Caddy in front
(`caddy reverse-proxy --from your.domain --to localhost:8501` gets a
certificate automatically).

## Firewall

Open only SSH and the UI port in the provider's firewall / security group.
On the VM itself:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 8501/tcp && sudo ufw enable
```

Docker's published ports bypass ufw, which is why Qdrant (6333/6334) and
the API (8000) are bound to `127.0.0.1` in `docker-compose.yml` rather than
relying on the firewall.

## Day to day

| task | command |
|---|---|
| update to the latest `main` | `git pull && docker compose up -d --build` |
| see logs | `docker compose logs -f api` (or `ui`) |
| usage numbers for the report | `curl -s localhost:8000/stats` |
| real-user questions and feedback | `data/logs/requests.jsonl`, `data/logs/feedback.jsonl` |
| restart | `docker compose restart api` |
| stop | `docker compose down` (volumes, i.e. the index, are kept) |

The index survives restarts and updates (Docker volumes). It is rebuilt only
if the `index_data` or `qdrant_data` volume is deleted.

## Before sharing the URL

- Empty `data/logs/` so `/stats` counts only real users.
- Set a monthly budget limit on the OpenAI project: the UI is public, and
  every question costs ~$0.0003. There is no login and no rate limit.
- The logs store questions and answers, never IP addresses or user ids
  (no personal data, per the brief). Tell users not to type personal data
  into questions.
