# One image for both services: the FastAPI app (default command) and the
# Streamlit UI (docker-compose.yml overrides the command). No secrets are
# baked in: keys come from .env via env_file at run time (.dockerignore
# keeps .env out of the build context).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf

# git: scripts/fetch_corpus.sh clones the pinned corpus on first start.
# curl: the entrypoint's Qdrant wait and the compose healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the reranker weights into the image so containers start without
# downloading from Hugging Face; HF_HUB_OFFLINE then forbids any download at
# run time. To use another RERANKER_MODEL, rebuild with
# --build-arg RERANKER_MODEL=... and set the same value in .env.
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANKER_MODEL}')"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .
# Windows checkouts may have CRLF line endings, which bash can't run.
RUN sed -i 's/\r$//' scripts/*.sh \
 && chmod +x scripts/*.sh \
 && useradd --create-home --uid 1000 app \
 && mkdir -p data/index data/cache data/logs corpus \
 && chown -R app:app data corpus

USER app
EXPOSE 8000 8501
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
