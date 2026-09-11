# ── Stage 1: builder ────────────────────────────────────────────────────────
# Installs all Python dependencies and pre-bakes the two HuggingFace models
# into the image so the runtime stage never downloads them on cold start.
# Downloading ~130 MB from HuggingFace on a Render free-tier cold start will
# time out; baking them in is non-negotiable for a reliable demo.
FROM python:3.11-slim AS builder

WORKDIR /build

# System deps needed to compile some wheels (e.g. tree-sitter C extension).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

# Copy only the packaging manifest first so Docker can cache the pip layer
# separately from application code changes.
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -e "." \
 && pip install --no-cache-dir huggingface_hub

# Pre-bake embedding and reranking models into the image.
# These are loaded at runtime via sentence_transformers.SentenceTransformer
# and sentence_transformers.CrossEncoder respectively, both of which check
# the HuggingFace cache directory before hitting the network.
RUN python - <<'PYEOF'
from sentence_transformers import SentenceTransformer, CrossEncoder
SentenceTransformer("BAAI/bge-small-en-v1.5")
CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
PYEOF


# ── Stage 2: runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for container security.
# --create-home ensures /home/dda exists so Streamlit can write its
# metrics cache to /home/dda/.streamlit without a PermissionError.
RUN groupadd --gid 1001 dda && useradd --uid 1001 --gid dda --create-home dda

WORKDIR /app

# Copy the installed package and cached models from the builder stage.
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.cache/huggingface /home/dda/.cache/huggingface

# Copy application source.
COPY src/ ./src/
COPY evals/ ./evals/
COPY scripts/ ./scripts/
# Streamlit config — disables usage stats so it never tries to write
# machine-id files before /home/dda/.streamlit permissions are set.
COPY .streamlit/ /home/dda/.streamlit/

# Runtime data directories (mounted as volumes in production).
# Create /home/dda/.streamlit explicitly so Streamlit's metrics util
# doesn't race to create it and hit a permission error on first request.
RUN mkdir -p data/kb/raw data/kb/chunks \
 && mkdir -p /home/dda/.streamlit \
 && chown -R dda:dda /app /home/dda

USER dda

ENV PYTHONPATH=/app/src
ENV HF_HOME=/home/dda/.cache/huggingface

EXPOSE 8000

# Default: run the FastAPI backend. Override CMD for Streamlit or CLI.
# PORT is set by Render; default 8000 for docker-compose and local runs.
CMD ["sh", "-c", "uvicorn dda.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
