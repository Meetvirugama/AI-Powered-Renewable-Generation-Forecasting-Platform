# syntax=docker/dockerfile:1
#
# Layer order is the whole design here. App code changes ~50x a day,
# dependencies change a handful of times over the sprint, and the model weights
# never change at all. Docker rebuilds from the first changed layer onward, so
# weights go in early and code goes in last. Get this backwards and every
# teammate's rebuild costs six minutes instead of twelve seconds.
#
# BAKE_MODELS build arg (default true):
#   true  -- bge-m3 + bge-reranker-base are downloaded and baked into the image.
#            Cold start is ~12 s instead of ~90 s; container works with no internet.
#            Use this for production ECR images.
#   false -- model layer is skipped. Image is ~500 MB instead of ~12 GB.
#            CI uses this: there is no point proving the weights download on every
#            PR. The image still boots (RAG_COPILOT_TYPE=mock), and ruff+tests
#            already ran in the test job. Build time drops from 14 min to <2 min.
#
# Expected production image size ~4.5 GB. Fine for ECR and a t3.large.

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1

# coinor-cbc is the solver behind PuLP for the 96-block battery LP (Member 1).
# curl is used by the healthcheck below.
#
# build-essential is deliberately NOT installed. Every dependency in
# requirements-ml.txt ships a manylinux wheel, so nothing needs a compiler --
# and build-essential pulls gcc-14 and g++-14 (~35 MB of the slowest packages on
# the Debian mirror, and the ones that timed out when this was first built).
# Dropping it removes ~300 MB from the image and the flakiest step in the build.
# If a future dependency needs to compile, add it back here rather than
# wondering why the build suddenly fails.
RUN printf 'Acquire::Retries "5";\nAcquire::http::Timeout "30";\n' \
        > /etc/apt/apt.conf.d/80-retries \
    && apt-get update && apt-get install -y --no-install-recommends \
        curl \
        coinor-cbc \
    && rm -rf /var/lib/apt/lists/*


# ---------- dependency layer (changes a few times per sprint) ----------
FROM base AS deps
WORKDIR /app
COPY requirements.txt requirements-ml.txt ./

# torch comes from PyTorch's CPU wheel index, not PyPI. PyPI's default torch
# wheel bundles the CUDA runtime and the nvidia-* packages -- ~2.5 GB installed,
# every byte of it dead weight on a t3.large, which has no GPU. The +cpu build is
# ~180 MB. Installing it first satisfies the pin in requirements-ml.txt before
# pip resolves torch there, so it never pulls the CUDA build over the top.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
    && pip install -r requirements-ml.txt


# ---------- model layer (changes never; skipped in CI via BAKE_MODELS=false) ----------
FROM deps AS models-true
# Both models are pinned by name in .env; changing either one invalidates this
# layer on purpose, because a changed embedding model means the index must be
# rebuilt anyway.
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3', cache_dir='/models'); \
snapshot_download('BAAI/bge-reranker-base', cache_dir='/models')"

# Thin alias used when BAKE_MODELS=false: identical to deps, no model weights.
FROM deps AS models-false
RUN mkdir -p /models

# The ARG selects which stage to use. "true" is the safe default so a plain
# `docker build .` produces a production-ready image without any extra flag.
ARG BAKE_MODELS=true
FROM models-${BAKE_MODELS} AS models


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
# When BAKE_MODELS=false (CI) the production copilot is not loaded, so 30s is fine.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
