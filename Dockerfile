# syntax=docker/dockerfile:1
#
# Layer order is the whole design here. App code changes ~50x a day,
# dependencies change a handful of times over the sprint, and the model weights
# never change at all. Docker rebuilds from the first changed layer onward, so
# weights go in early and code goes in last. Get this backwards and every
# teammate's rebuild costs six minutes instead of twelve seconds.
#
# The other mistake this avoids: downloading 2.2 GB of embedding weights at
# container start. Baked in, cold start is ~12 s instead of ~90 s, and the
# container works with no internet -- which is exactly the situation on hackathon
# venue wifi.
#
# Expected image size ~4.5 GB. Fine for ECR and a t3.large. If that becomes a
# problem, the escape hatch is BAKE_MODELS=false plus an S3 sync at boot.

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

# coinor-cbc is the solver behind PuLP for the 96-block battery LP (Member 1).
# curl is used by the healthcheck below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        coinor-cbc \
    && rm -rf /var/lib/apt/lists/*


# ---------- dependency layer (changes a few times per sprint) ----------
FROM base AS deps
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install --upgrade pip && pip install -r requirements-ml.txt


# ---------- model layer (changes never) ----------
FROM deps AS models
# Both models are pinned by name in .env; changing either one invalidates this
# layer on purpose, because a changed embedding model means the index must be
# rebuilt anyway.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3', cache_dir='/models'); \
snapshot_download('BAAI/bge-reranker-base', cache_dir='/models')"


# ---------- application layer (changes constantly) ----------
FROM models AS runtime
WORKDIR /app

RUN useradd --create-home --uid 1000 appuser \
    # HF_HOME must be writable: the hub takes lock files next to the weights
    # even when everything it needs is already cached.
    && chown -R appuser:appuser /models

COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser regulations/ ./regulations/

USER appuser
EXPOSE 8000

# start-period is 90s because the lifespan loads bge-m3 before serving. Set it to
# the usual 10s and Docker marks a still-loading container unhealthy and
# restart-loops it forever -- a failure mode that looks like a crash and is not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
