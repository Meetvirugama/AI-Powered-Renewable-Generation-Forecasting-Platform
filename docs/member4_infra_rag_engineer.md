# Member 4 — Infra + RAG Engineer
## Execution Plan: Senior Engineer Level
### AI-Powered Renewable Generation Forecasting Platform

---

> **You are the team's unblocker on Day 1 and the team's lifeline on Day 14.** Nobody can run the stack until your `docker compose up` works, nobody can demo until your deployment is live, and the single most "AI-looking" feature to a judge — the copilot that cites a CERC clause — is yours end to end.
>
> You also own the one guardrail the project's credibility rests on: **the LLM must never originate a ₹ number.** Member 1 computes money. You explain it. If your copilot ever prints a rupee figure the DSM engine did not produce, the project's core claim collapses.

---

## Your Stack

```
Docker + docker compose      # local stack — the thing everyone runs
PostgreSQL 15 + pgvector     # vector store (same DB Member 2 uses)
PyMuPDF (fitz)               # PDF text + page extraction
FlagEmbedding                # bge-m3 embeddings (1024-dim)
rank_bm25                    # sparse keyword retrieval
LangGraph                    # copilot state machine
LiteLLM                      # Groq primary → Gemini fallback routing
FastAPI                      # your one route: POST /rag/query
AWS: EC2, RDS, S3, CloudFront, ALB, ECR, SSM, EventBridge, CloudWatch
GitHub Actions + OIDC        # CI/CD, no long-lived AWS keys
Terraform                    # infra-as-code (written LAST — see Day 13)
Google Colab                 # notebook 10 — offline index build on GPU
```

---

## Read This Before Day 1: You Are On The Critical Path Twice

Your work has two "everyone waits on me" moments. Plan around them.

| Moment | Who is blocked | Deadline | Mitigation |
|---|---|---|---|
| `docker compose up` doesn't work | Member 2 can't develop against Postgres; Member 1 can't test the DSM engine against a real DB | **End of Day 1** | Ship the stack with a *stub* backend if Member 2's `main.py` isn't ready. Postgres + pgvector alone unblocks people. |
| `POST /rag/query` contract undefined | Member 3 can't build `RAGCopilot.jsx`; Member 2 can't wire the route | **End of Day 1** | Publish the JSON contract (below) on Day 1 and a **mock endpoint returning canned JSON on Day 2**, long before real RAG works. |

### Publish these three artefacts on Day 1, before you write any RAG code

1. `docker-compose.yml` that comes up clean on a fresh clone
2. `.env.example` with every variable name the app will ever read
3. `docs/api_rag_contract.md` — the frozen request/response shape below

Freeze this contract on Day 1 and do not change field names after Day 3. Member 3 builds against it blind.

```jsonc
// POST /rag/query   — REQUEST
{
  "question": "Why was block 52 penalised?",
  "plant_id": "GJ_SOLAR_A",          // optional
  "block_no": 52,                     // optional
  "date": "2026-09-12",               // optional
  "rule_year": 2026,                  // optional, default from settings.yaml
  "engine_context": {                 // optional — Member 2 injects DSM engine output
    "penalty_inr": 18240.0,
    "deviation_pct": -14.2,
    "schedule_mw": 42.5,
    "actual_mw": 36.4,
    "x_value": 0.7,
    "frequency_band": "49.95-50.05",
    "rule_version": "CERC_DSM_2026"
  }
}

// POST /rag/query   — RESPONSE (200)
{
  "answer": "Block 52 was penalised ₹18,240 because actual injection fell ...",
  "citations": [
    {
      "doc": "CERC_DSM_Amendment_2026",
      "clause": "Regulation 7(2)(b)",
      "section": "Deviation charges for sellers",
      "page": 14,
      "url": "https://cercind.gov.in/...",
      "snippet": "Where the actual injection deviates ..."
    }
  ],
  "engine_values": {                  // echoed VERBATIM from engine_context
    "penalty_inr": 18240.0,
    "deviation_pct": -14.2
  },
  "meta": {
    "model": "groq/llama-3.3-70b-versatile",
    "cached": false,
    "latency_ms": 1840,
    "retrieved_chunks": 5,
    "guardrail": "pass"               // pass | numbers_stripped | fallback_template
  }
}

// ERROR (502 — all LLM providers down)
{ "detail": "copilot_unavailable", "fallback_answer": "<deterministic template>" }
```

> **Design rule:** `engine_values` is copied from the request, never re-derived. The frontend renders ₹ from `engine_values` and treats `answer` as prose only. This makes "the LLM never computes money" structurally true, not just a prompt instruction.

---

## Day-by-Day Plan

| Day | Deliverable | Hard blocker for |
|---|---|---|
| 1 | Dockerfile + docker-compose + .env.example + RAG contract frozen | Everyone |
| 2 | PDF corpus acquired, `ingest.py` clause-aware chunker, **mock /rag/query** | Member 3 |
| 3 | `embed.py`, pgvector schema, Colab notebook 10, index built | — |
| 4 | `retriever.py` — BM25 + pgvector + RRF fusion + eval set | — |
| 5 | LiteLLM wired: Groq primary, Gemini fallback, retries | — |
| 6 | `copilot.py` — LangGraph graph, prompt, citation validation | — |
| 7 | `cache.py` + **₹ guardrail validator** + `generate_briefing()` | Member 2 (pipeline step 8) |
| 8 | Real `POST /rag/query` wired with Member 2, integration tested | Member 3 |
| 9 | AWS: EC2 + RDS + pgvector + S3 + SSM, backend live | — |
| 10 | CloudFront + S3 frontend + ALB — one HTTPS URL for the demo | Member 3 |
| 11 | `ci.yml` — ruff + pytest + docker build + trivy + ECR push | — |
| 12 | `deploy.yml` — OIDC → ECR → SSM RunCommand → health check | — |
| 13 | EventBridge daily trigger, CloudWatch alarms, Terraform captured | Member 2 |
| 14 | Full E2E rehearsal, demo failover drill, cost shutdown plan | Everyone |

---

## Day 1 — The Stack Everyone Runs

### Step 1: `Dockerfile` (multi-stage, model weights baked)

The single biggest infra mistake available to you is downloading a 2.2 GB embedding model at container start. Bake it into a cached layer.

```dockerfile
# Dockerfile
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl coinor-cbc git \
 && rm -rf /var/lib/apt/lists/*

# ---------- deps layer (changes rarely) ----------
FROM base AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# ---------- model layer (changes never) ----------
FROM deps AS models
RUN python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('BAAI/bge-m3', cache_dir='/models'); \
snapshot_download('BAAI/bge-reranker-base', cache_dir='/models')"

# ---------- app layer (changes constantly) ----------
FROM models AS runtime
WORKDIR /app
RUN useradd -m -u 1000 appuser
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser config/ ./config/
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Why that layer order:** app code changes 50× a day, deps change 3× total, model weights change zero times. Docker rebuilds from the first changed layer onward. Get this wrong and every teammate's rebuild costs 6 minutes instead of 12 seconds.

Expected image size ≈ 4.5 GB. Fine for ECR and t3.large. Escape hatch is in the Decision Log.

### Step 2: `docker-compose.yml`

```yaml
services:
  db:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_USER: renewable
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devpassword}
      POSTGRES_DB: renewable
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./infra/docker/init_db.sql:/docker-entrypoint-initdb.d/00_init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U renewable -d renewable"]
      interval: 5s
      timeout: 3s
      retries: 20

  backend:
    build: { context: ., dockerfile: Dockerfile }
    env_file: .env
    environment:
      DATABASE_URL: postgresql+psycopg2://renewable:${POSTGRES_PASSWORD:-devpassword}@db:5432/renewable
    ports: ["8000:8000"]
    volumes:
      - ./backend:/app/backend      # hot reload in dev; REMOVE in the prod compose file
      - ./config:/app/config
      - ./regulations:/app/regulations:ro
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped

  frontend:                          # dev convenience only; prod frontend goes to S3
    image: node:20-alpine
    working_dir: /app
    command: sh -c "npm ci && npm run dev -- --host 0.0.0.0"
    environment:
      VITE_API_BASE_URL: http://localhost:8000
    volumes: ["./frontend:/app"]
    ports: ["5173:5173"]
    profiles: ["dev"]                # docker compose --profile dev up

volumes:
  pgdata:
```

```sql
-- infra/docker/init_db.sql   (runs once, on first volume creation)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

> **Gotcha that will cost you an hour:** `init_db.sql` runs *only* when the `pgdata` volume is empty. If you add it after someone already started the DB, they must `docker compose down -v`. Announce this in writing on Day 1.

### Step 3: `.env.example` — every variable, from day one

```bash
# ---- Database ----
DATABASE_URL=postgresql+psycopg2://renewable:devpassword@localhost:5432/renewable
POSTGRES_PASSWORD=devpassword

# ---- App ----
APP_ENV=local                      # local | prod
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,https://<cloudfront-id>.cloudfront.net

# ---- Auth ----
PIPELINE_API_KEY=change_me_local

# ---- LLM / RAG ----
GROQ_API_KEY=
GEMINI_API_KEY=
RAG_PRIMARY_MODEL=groq/llama-3.3-70b-versatile
RAG_FALLBACK_MODEL=gemini/gemini-1.5-flash
RAG_EMBED_MODEL=BAAI/bge-m3
RAG_RERANK_MODEL=BAAI/bge-reranker-base
RAG_TOP_K_DENSE=20
RAG_TOP_K_SPARSE=20
RAG_TOP_K_FINAL=5
RAG_CACHE_TTL_SECONDS=3600
RAG_ENABLE_RERANKER=true
HF_HOME=/models

# ---- DSM ----
DSM_RULE_CONFIG=config/dsm_rules_2026.yaml

# ---- AWS (prod only; read from SSM on EC2) ----
AWS_REGION=ap-south-1
S3_BUCKET_DATA=
S3_BUCKET_MODELS=
```

### Step 4: Repo hygiene (15 minutes — you own it)

```bash
# Branch protection — do this before anyone pushes to main
gh api -X PUT repos/:owner/:repo/branches/main/protection \
  -f required_pull_request_reviews.required_approving_review_count=1 \
  -f enforce_admins=false \
  -f required_status_checks.strict=true \
  -f 'required_status_checks.contexts[]=ci'

# Branch convention the team follows
# feat/m4-rag-retriever   fix/m2-forecast-tz   chore/m4-ci
```

Verify `.gitignore` covers `.env`, `*.pkl`, `*.pt`, `models/`, `node_modules/`, `__pycache__/`, `.terraform/`, `*.tfstate*`. **Do commit the regulation PDFs** — they are the corpus and the build must be reproducible.

### Day 1 exit criteria
- [ ] Teammate on a fresh clone runs `cp .env.example .env && docker compose up` and gets a healthy Postgres
- [ ] `psql` confirms the `vector` extension is present
- [ ] `docs/api_rag_contract.md` committed and posted in the team channel
- [ ] Branch protection on

---

## Day 2 — Regulation Corpus + Clause-Aware Chunking

### Step 1: Acquire the PDFs (do this first — sourcing can eat an hour)

```
regulations/
  CERC_DSM_Regulations_2024.pdf        # cercind.gov.in — DSM Regulations, 2024
  CERC_DSM_Amendment_2026.pdf          # amendment: X-trajectory, tightened bands
  IEGC_2023.pdf                        # Indian Electricity Grid Code, 2023
  sources.json                         # file -> {title, url, published, sha256}
```

`sources.json` is not optional. Every citation you render needs a real URL, and a judge who clicks a dead link kills your credibility faster than a wrong number does.

```bash
python - <<'PY'
import hashlib, json, pathlib
out = {}
for p in pathlib.Path("regulations").glob("*.pdf"):
    out[p.name] = {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                   "bytes": p.stat().st_size, "url": "FILL_ME", "title": "FILL_ME",
                   "effective_date": "FILL_ME"}
pathlib.Path("regulations/sources.json").write_text(json.dumps(out, indent=2))
PY
```

### Step 2: `backend/modules/rag/ingest.py`

A naive 512-character splitter will cut "Regulation 7(2)(b)" in half and your citations become garbage. Split on **legal structure first**, then size-bound *within* a clause.

```python
# backend/modules/rag/ingest.py
"""Clause-aware PDF ingestion for CERC/IEGC regulation documents.

Structure-first chunking: split on regulation/clause headings, then size-bound
within a clause. A chunk never spans two clauses, so the clause id attached to a
chunk is always the clause the text actually came from.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

import fitz  # PyMuPDF

# Ordered most-specific → least-specific. First match wins.
CLAUSE_PATTERNS = [
    re.compile(r"^\s*(?P<id>\d{1,2}(?:\.\d{1,2}){1,3})\s+(?P<title>[A-Z][^\n]{0,120})"),
    re.compile(r"^\s*(?P<id>Regulation\s+\d{1,2}(?:\(\w{1,3}\))*)\s*[.:\-–]?\s*(?P<title>[^\n]{0,120})", re.I),
    re.compile(r"^\s*(?P<id>Clause\s+\d{1,2}(?:\.\d{1,2})*)\s*[.:\-–]?\s*(?P<title>[^\n]{0,120})", re.I),
    re.compile(r"^\s*(?P<id>CHAPTER\s+[IVXLC]+)\s*[.:\-–—]?\s*(?P<title>[^\n]{0,120})"),
]

MAX_CHARS = 1800        # ≈ 450 tokens of English legal text
OVERLAP_CHARS = 200
MIN_CHARS = 120         # drops headers, footers, page numbers


@dataclass
class Chunk:
    doc_name: str
    section: str
    clause: str
    page_no: int
    source_url: str
    effective_date: str | None
    chunk_text: str
    chunk_index: int

    def stable_id(self) -> str:
        return f"{self.doc_name}::{self.clause}::{self.page_no}::{self.chunk_index}"


def _match_heading(line: str) -> tuple[str, str] | None:
    for pat in CLAUSE_PATTERNS:
        m = pat.match(line)
        if m:
            return m.group("id").strip(), (m.groupdict().get("title") or "").strip()
    return None


def _clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)              # de-hyphenate wrapped words
    text = re.sub(r"(?<![.\n])\n(?![A-Z0-9\n])", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _window(text: str, limit: int = MAX_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Size-bound a single clause, preferring sentence boundaries."""
    if len(text) <= limit:
        return [text]
    parts, start = [], 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            cut = max(text.rfind(". ", start + limit // 2, end),
                      text.rfind(";\n", start + limit // 2, end))
            if cut > 0:
                end = cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]


def ingest_pdf(pdf_path: Path, doc_meta: dict) -> list[Chunk]:
    doc = fitz.open(pdf_path)
    chunks: list[Chunk] = []
    cur_clause, cur_section = "PREAMBLE", "PREAMBLE"
    buf: list[str] = []
    buf_page, idx = 1, 0

    def flush():
        nonlocal buf, idx
        body = _clean("\n".join(buf))
        buf = []
        if len(body) < MIN_CHARS:
            return
        for piece in _window(body):
            chunks.append(Chunk(doc_name=doc_meta["doc_name"], section=cur_section,
                                clause=cur_clause, page_no=buf_page,
                                source_url=doc_meta.get("url", ""),
                                effective_date=doc_meta.get("effective_date"),
                                chunk_text=piece, chunk_index=idx))
            idx += 1

    for page_no, page in enumerate(doc, start=1):
        for line in page.get_text("text").split("\n"):
            hit = _match_heading(line)
            if hit:
                flush()
                cur_clause, title = hit
                if title:
                    cur_section = title[:120]
                buf_page = page_no
                buf.append(line)
            else:
                if not buf:
                    buf_page = page_no
                buf.append(line)
    flush()
    doc.close()
    return chunks


def ingest_all(reg_dir: Path = Path("regulations")) -> list[Chunk]:
    sources = json.loads((reg_dir / "sources.json").read_text())
    out: list[Chunk] = []
    for pdf in sorted(reg_dir.glob("*.pdf")):
        meta = sources.get(pdf.name, {})
        meta.setdefault("doc_name", pdf.stem)
        out.extend(ingest_pdf(pdf, meta))
    return out


if __name__ == "__main__":
    cs = ingest_all()
    print(f"{len(cs)} chunks")
    Path("regulations/chunks.jsonl").write_text(
        "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in cs))
```

### Step 3: Validate the chunker BEFORE you embed anything

Embedding garbage is the classic wasted afternoon. Spend 20 minutes here.

```python
import collections, json
chunks = [json.loads(l) for l in open("regulations/chunks.jsonl")]

print("total:", len(chunks))                                  # expect ~600–2000
print("by doc:", collections.Counter(c["doc_name"] for c in chunks))
print("unmatched:", sum(c["clause"] == "PREAMBLE" for c in chunks))   # want < 15%
print("median chars:", sorted(len(c["chunk_text"]) for c in chunks)[len(chunks)//2])

# THE test that matters: can you find the deviation-charge clause?
hits = [c for c in chunks if "deviation" in c["chunk_text"].lower()
        and "charge" in c["chunk_text"].lower()]
for h in hits[:3]:
    print(h["doc_name"], h["clause"], "p", h["page_no"], "|", h["chunk_text"][:200])
```

If `unmatched` exceeds ~30%, the PDF uses a numbering style you haven't handled — add a pattern, don't lower your standard. If `page.get_text()` returns empty strings, the PDF is image-only and needs OCR (`pytesseract`). **Discover that on Day 2, not Day 10.**

### Step 4: Ship the mock `/rag/query` today (this unblocks Member 3)

```python
# backend/api/rag.py  — DAY 2 MOCK (replaced on Day 8, same shape)
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["rag"])


class RagQuery(BaseModel):
    question: str
    plant_id: str | None = None
    block_no: int | None = None
    date: str | None = None
    rule_year: int | None = None
    engine_context: dict | None = None


@router.post("/query")
async def query(body: RagQuery):
    ev = body.engine_context or {}
    return {
        "answer": ("Block 52 shows an under-injection against the declared schedule. "
                   "Under the 2026 amendment the tolerance band for solar sellers "
                   "narrows, and deviation beyond the band attracts charges referenced "
                   "to the normal rate."),
        "citations": [{"doc": "CERC_DSM_Amendment_2026", "clause": "Regulation 7(2)(b)",
                       "section": "Deviation charges for sellers", "page": 14,
                       "url": "https://cercind.gov.in/",
                       "snippet": "Where the actual injection deviates ..."}],
        "engine_values": {"penalty_inr": ev.get("penalty_inr"),
                          "deviation_pct": ev.get("deviation_pct")},
        "meta": {"model": "mock", "cached": False, "latency_ms": 12,
                 "retrieved_chunks": 0, "guardrail": "pass"},
    }
```

---

## Day 3 — Embeddings + pgvector Index (Colab Notebook 10)

### The dimension decision you must make TODAY

Member 2 freezes DB migrations around Day 2–3. `VECTOR(n)` is baked into the schema; changing it later means a migration **plus** a full re-embed. Decide now and tell him at standup.

| Model | Dim | Size | CPU query latency | Verdict |
|---|---|---|---|---|
| `BAAI/bge-m3` | 1024 | 2.2 GB | ~250–500 ms | **Default.** Multilingual, strong on legal text, matches the plan. |
| `BAAI/bge-small-en-v1.5` | 384 | 130 MB | ~25 ms | Escape hatch if t3.large memory gets tight. |

Ship with **bge-m3 / VECTOR(1024)**. Keep the dimension in `settings.yaml` so a swap is a config change plus a re-index, not a code change.

### `backend/modules/rag/embed.py`

```python
# backend/modules/rag/embed.py
"""Embedding layer. One model per process, loaded lazily, warmed at startup.

CRITICAL: the same model must embed the corpus (offline, Colab) and the query
(online, EC2). A mismatch silently returns nonsense neighbours — no error, just
bad answers. The model name is asserted against what is stored in the DB.
"""
from __future__ import annotations

import os
import threading
from functools import lru_cache

import numpy as np

_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "BAAI/bge-m3")
_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from FlagEmbedding import BGEM3FlagModel
                _model = BGEM3FlagModel(_MODEL_NAME, use_fp16=False)   # fp16 needs GPU
    return _model


def embed_passages(texts: list[str], batch_size: int = 16) -> np.ndarray:
    out = _get_model().encode(texts, batch_size=batch_size, max_length=1024)
    return np.asarray(out["dense_vecs"], dtype=np.float32)


@lru_cache(maxsize=512)
def _embed_query_cached(text: str) -> tuple[float, ...]:
    vec = _get_model().encode([text], max_length=512)["dense_vecs"][0]
    return tuple(float(x) for x in vec)


def embed_query(text: str) -> np.ndarray:
    """Query embedding with an in-process LRU — repeated demo questions cost 0 ms."""
    return np.asarray(_embed_query_cached(text.strip().lower()), dtype=np.float32)


def warmup() -> None:
    """Call from FastAPI lifespan. Pays the 8–15 s load cost before the first user."""
    embed_query("warmup")


def model_name() -> str:
    return _MODEL_NAME
```

### Colab Notebook 10 — build the index on a T4, not on your laptop

```python
# colab_notebooks/10_rag_embed.ipynb
!pip -q install pymupdf FlagEmbedding psycopg2-binary pgvector

from ingest import ingest_all          # %run the ingest.py you wrote on Day 2
chunks = ingest_all()
print(len(chunks), "chunks")

from FlagEmbedding import BGEM3FlagModel
model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
vecs = model.encode([c.chunk_text for c in chunks], batch_size=32,
                    max_length=1024)["dense_vecs"]          # ~2k chunks < 1 min on T4

import psycopg2, numpy as np
from pgvector.psycopg2 import register_vector
conn = psycopg2.connect(DATABASE_URL); register_vector(conn); cur = conn.cursor()
cur.execute("TRUNCATE regulation_chunks RESTART IDENTITY;")
for c, v in zip(chunks, vecs):
    cur.execute("""INSERT INTO regulation_chunks
        (doc_name, section, clause, page_no, source_url, effective_date,
         chunk_text, embedding, embed_model, chunk_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (chunk_id) DO NOTHING""",
        (c.doc_name, c.section, c.clause, c.page_no, c.source_url, c.effective_date,
         c.chunk_text, np.asarray(v, dtype=np.float32), "BAAI/bge-m3", c.stable_id()))
conn.commit()

# Build the ANN index AFTER the rows exist — see gotcha below
cur.execute("""CREATE INDEX IF NOT EXISTS idx_regchunks_hnsw
               ON regulation_chunks USING hnsw (embedding vector_cosine_ops)
               WITH (m = 16, ef_construction = 64);""")
cur.execute("""CREATE INDEX IF NOT EXISTS idx_regchunks_fts ON regulation_chunks
               USING gin (to_tsvector('english', chunk_text));""")
conn.commit()
```

> **Two gotchas that silently destroy retrieval quality:**
>
> 1. **Never create an `ivfflat` index on an empty table.** It clusters on data present at build time; built empty, recall collapses. The implementation plan specifies `ivfflat (lists=100)` — for a 1–3k chunk corpus, use **HNSW** instead (better recall, no training step, no `lists` tuning) or skip the index entirely (a sequential scan over 2k rows is ~5 ms). Ask Member 2 to move index creation out of the initial migration.
> 2. **Store `embed_model` on every row**, plus a `chunk_id VARCHAR UNIQUE` for idempotent re-ingest. On startup, assert the stored model equals `embed.model_name()` and refuse to serve if they differ. That check catches the nastiest RAG bug class in under a second.

**Schema delta to request from Member 2** (send it as a message, don't edit his migration yourself):

```sql
ALTER TABLE regulation_chunks ADD COLUMN embed_model VARCHAR;
ALTER TABLE regulation_chunks ADD COLUMN chunk_id   VARCHAR UNIQUE;
-- and drop the ivfflat index from the initial migration
```

### Day 3 exit criteria
- [ ] `SELECT count(*), embed_model FROM regulation_chunks GROUP BY 2;` returns your corpus
- [ ] A raw cosine query for "deviation charges for solar seller" returns a plausibly relevant clause
- [ ] The notebook re-runs against RDS unchanged (you will need this on Day 9)

---

## Day 4 — Hybrid Retrieval

### `backend/modules/rag/retriever.py`

```python
# backend/modules/rag/retriever.py
"""Hybrid retrieval: dense (pgvector) + sparse (BM25) → RRF fusion → optional rerank.

Why RRF and not score normalisation: cosine similarity and BM25 live on
incomparable scales, and normalising them needs a calibration set we do not have.
Reciprocal Rank Fusion uses rank order only, needs no tuning, and stays robust
when one retriever returns junk.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import text as sql

from backend.modules.rag import embed

TOP_K_DENSE = int(os.getenv("RAG_TOP_K_DENSE", 20))
TOP_K_SPARSE = int(os.getenv("RAG_TOP_K_SPARSE", 20))
TOP_K_FINAL = int(os.getenv("RAG_TOP_K_FINAL", 5))
RRF_K = 60
ENABLE_RERANK = os.getenv("RAG_ENABLE_RERANKER", "true").lower() == "true"

_FIELDS = ("doc_name", "clause", "section", "page_no", "source_url", "chunk_text")


@dataclass
class Retrieved:
    chunk_id: int
    doc_name: str
    clause: str
    section: str
    page_no: int
    source_url: str
    chunk_text: str
    score: float

    def as_citation(self) -> dict:
        return {"doc": self.doc_name, "clause": self.clause, "section": self.section,
                "page": self.page_no, "url": self.source_url,
                "snippet": self.chunk_text[:280]}


# ---------------- BM25 (in-memory, rebuilt at startup) ----------------
_bm25 = None
_bm25_rows: list[dict] = []
_bm25_lock = threading.Lock()
_TOKEN = re.compile(r"[a-z0-9().%]+")


def _tok(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def build_bm25(session) -> None:
    """Load the corpus into memory. ~2k chunks ≈ 6 MB. Call once at startup."""
    global _bm25, _bm25_rows
    from rank_bm25 import BM25Okapi
    rows = session.execute(sql(
        "SELECT id, doc_name, clause, section, page_no, source_url, chunk_text "
        "FROM regulation_chunks ORDER BY id")).mappings().all()
    with _bm25_lock:
        _bm25_rows = [dict(r) for r in rows]
        _bm25 = BM25Okapi([_tok(r["chunk_text"]) for r in _bm25_rows]) if _bm25_rows else None


def _sparse(query: str, k: int) -> list[Retrieved]:
    if _bm25 is None:
        return []
    scores = _bm25.get_scores(_tok(query))
    idx = np.argsort(scores)[::-1][:k]
    return [Retrieved(chunk_id=_bm25_rows[i]["id"], score=float(scores[i]),
                      **{f: _bm25_rows[i][f] for f in _FIELDS})
            for i in idx if scores[i] > 0]


# ---------------- Dense (pgvector) ----------------
def _dense(session, query: str, k: int, doc_filter: list[str] | None) -> list[Retrieved]:
    qv = embed.embed_query(query).tolist()
    params: dict = {"qv": str(qv), "k": k}
    where = ""
    if doc_filter:
        where, params["docs"] = "WHERE doc_name = ANY(:docs)", doc_filter
    rows = session.execute(sql(f"""
        SELECT id, doc_name, clause, section, page_no, source_url, chunk_text,
               1 - (embedding <=> CAST(:qv AS vector)) AS score
        FROM regulation_chunks {where}
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :k"""), params).mappings().all()
    return [Retrieved(chunk_id=r["id"], score=float(r["score"]),
                      **{f: r[f] for f in _FIELDS}) for r in rows]


# ---------------- Fusion ----------------
def _rrf(runs: list[list[Retrieved]], k: int = RRF_K) -> list[Retrieved]:
    fused: dict[int, tuple[float, Retrieved]] = {}
    for run in runs:
        for rank, item in enumerate(run, start=1):
            prev = fused.get(item.chunk_id, (0.0, item))
            fused[item.chunk_id] = (prev[0] + 1.0 / (k + rank), item)
    out = []
    for s, item in sorted(fused.values(), key=lambda t: -t[0]):
        item.score = s
        out.append(item)
    return out


# ---------------- Reranker (optional, never fatal) ----------------
_reranker = None


def _rerank(query: str, cands: list[Retrieved], k: int) -> list[Retrieved]:
    global _reranker
    if not ENABLE_RERANK or not cands:
        return cands[:k]
    try:
        if _reranker is None:
            from FlagEmbedding import FlagReranker
            _reranker = FlagReranker(os.getenv("RAG_RERANK_MODEL", "BAAI/bge-reranker-base"),
                                     use_fp16=False)
        scores = _reranker.compute_score([[query, c.chunk_text] for c in cands])
        if isinstance(scores, float):
            scores = [scores]
        for c, s in zip(cands, scores):
            c.score = float(s)
        return sorted(cands, key=lambda c: -c.score)[:k]
    except Exception:                 # a slow/broken reranker must never 500 the copilot
        return cands[:k]


def retrieve(session, query: str, *, rule_year: int | None = None,
             k: int = TOP_K_FINAL) -> list[Retrieved]:
    doc_filter = None
    if rule_year and rule_year < 2026:
        doc_filter = ["CERC_DSM_Regulations_2024", "IEGC_2023"]
    dense = _dense(session, query, TOP_K_DENSE, doc_filter)
    sparse = _sparse(query, TOP_K_SPARSE)
    fused = _rrf([dense, sparse])
    return _rerank(query, fused[: TOP_K_DENSE + TOP_K_SPARSE], k)
```

**Why the `rule_year` filter matters:** when a judge drags Member 3's regulation slider to 2024, the copilot must cite the 2024 regulations, not the 2026 amendment. That one filter is the difference between a coherent demo and one where the citation visibly contradicts the slider.

### Build a 15-question eval set — today, before you tune anything

```json
// tests/rag_eval_questions.json
[
  {"q": "What is the tolerance band for solar generators under the 2026 amendment?",
   "expect_doc": "CERC_DSM_Amendment_2026"},
  {"q": "How is deviation percentage calculated for a renewable seller?",
   "expect_doc": "CERC_DSM_Regulations_2024"},
  {"q": "What is the X trajectory and how does it change over time?"},
  {"q": "What happens when grid frequency falls below 49.85 Hz?"},
  {"q": "Can renewable generators pool deviation across plants?"}
]
```

Measure **recall@5**: does the expected doc/clause appear in the top 5? Below ~0.7 means fix the *chunker*, not the prompt. Thirty minutes of work, and it is the only objective signal you will ever have about RAG quality.

---

## Day 5 — LLM Routing (LiteLLM: Groq → Gemini)

### `backend/modules/rag/llm.py`

```python
# backend/modules/rag/llm.py
"""LiteLLM routing with explicit fallback. Groq is fast but rate-limited;
Gemini Flash is the safety net. Neither is trusted with arithmetic."""
from __future__ import annotations

import logging
import os
import time

import litellm

logger = logging.getLogger(__name__)
litellm.drop_params = True          # tolerate provider-specific param mismatches
litellm.set_verbose = False

PRIMARY = os.getenv("RAG_PRIMARY_MODEL", "groq/llama-3.3-70b-versatile")
FALLBACK = os.getenv("RAG_FALLBACK_MODEL", "gemini/gemini-1.5-flash")


class AllProvidersFailed(RuntimeError):
    pass


def complete(messages: list[dict], *, temperature: float = 0.1,
             max_tokens: int = 700, timeout: int = 25) -> tuple[str, str]:
    """Returns (text, model_used). Raises AllProvidersFailed if everything is down."""
    last_err = None
    for model in (PRIMARY, FALLBACK):
        for attempt in range(2):
            try:
                t0 = time.time()
                resp = litellm.completion(model=model, messages=messages,
                                          temperature=temperature,
                                          max_tokens=max_tokens, timeout=timeout)
                logger.info("llm_ok model=%s ms=%d", model, int((time.time() - t0) * 1000))
                return (resp.choices[0].message.content or ""), model
            except Exception as e:                                   # noqa: BLE001
                last_err = e
                logger.warning("llm_fail model=%s attempt=%d err=%s", model, attempt, e)
                time.sleep(0.8 * (attempt + 1))
    raise AllProvidersFailed(str(last_err))
```

**Temperature 0.1, not 0.7.** This is a compliance explainer, not a creative writer. Low temperature also makes your cache meaningful and your demo reproducible.

**Rate limits are a real demo risk.** Groq's free tier is roughly 30 requests/minute per org. Four teammates testing while a judge types will hit it. Mitigations in priority order: response cache (Day 7), pre-generated briefings (Day 7), Gemini fallback (today).

Verify both keys before you build a graph on top of them:

```bash
python -c "from backend.modules.rag.llm import complete; \
print(complete([{'role':'user','content':'Reply with exactly: OK'}]))"
```

---

## Day 6 — The Copilot (LangGraph)

### `backend/modules/rag/copilot.py`

```python
# backend/modules/rag/copilot.py
"""LangGraph copilot: cache → retrieve → generate → guardrail → persist.

The graph is deliberately linear. LangGraph is used for observable, testable state
transitions and a clean failure path — not for agentic tool loops. An agent that can
re-plan is a liability when every answer must be traceable to a clause.
"""
from __future__ import annotations

import datetime as _dt
import time
from typing import TypedDict

from langgraph.graph import END, StateGraph

from backend.modules.rag import cache, guardrail, llm, retriever

SYSTEM_PROMPT = """You are a regulatory explainer for an Indian renewable-energy \
grid-scheduling platform. You explain Deviation Settlement Mechanism (DSM) outcomes \
to grid operators, plant owners and traders.

ABSOLUTE RULES — violating any of these makes your answer invalid:
1. You NEVER calculate, estimate, adjust or invent a numeric value. Every rupee \
amount, megawatt value, percentage and frequency you state MUST be copied exactly \
from the ENGINE_RESULT block. If ENGINE_RESULT does not contain a number, do not \
state one — describe the mechanism qualitatively instead.
2. You cite only from the CONTEXT block. Every regulatory claim ends with a citation \
of the form [doc | clause | p.NN]. If CONTEXT does not support a claim, say the \
regulations provided do not cover it.
3. You never speculate about pending litigation, about amendments not present in \
CONTEXT, or about what the user should bid commercially.

STYLE: 3-6 sentences. Lead with the direct answer. Plain operator English, not \
legalese. No preamble, no "Based on the provided context"."""

USER_TEMPLATE = """QUESTION:
{question}

ENGINE_RESULT (computed by our deterministic DSM engine — authoritative, do not alter):
{engine_block}

CONTEXT (retrieved regulation extracts):
{context_block}
"""


class CopilotState(TypedDict, total=False):
    question: str
    rule_year: int | None
    engine_context: dict
    session: object
    cache_key: str
    cached: bool
    retrieved: list
    answer: str
    model: str
    guardrail_status: str
    citations: list
    latency_ms: int
    t0: float


def n_cache_lookup(s: CopilotState) -> CopilotState:
    s["t0"] = time.time()
    s["cache_key"] = cache.make_key(s["question"], s.get("rule_year"),
                                    s.get("engine_context") or {})
    hit = cache.get(s["cache_key"])
    if hit:
        s.update(hit)
        s["cached"] = True
    else:
        s["cached"] = False
    return s


def n_retrieve(s: CopilotState) -> CopilotState:
    s["retrieved"] = retriever.retrieve(s["session"], s["question"],
                                        rule_year=s.get("rule_year"))
    return s


def n_generate(s: CopilotState) -> CopilotState:
    ctx = "\n\n".join(f"[{r.doc_name} | {r.clause} | p.{r.page_no}]\n{r.chunk_text}"
                      for r in s["retrieved"]) or "(no regulation extracts retrieved)"
    eng = s.get("engine_context") or {}
    eng_block = ("\n".join(f"{k} = {v}" for k, v in eng.items())
                 or "(no engine values supplied — answer qualitatively, state no numbers)")
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                question=s["question"], engine_block=eng_block, context_block=ctx)}]
    try:
        text, model = llm.complete(msgs)
    except llm.AllProvidersFailed:
        text = guardrail.deterministic_fallback(s["question"], eng, s["retrieved"])
        model = "fallback_template"
    s["answer"], s["model"] = text, model
    return s


def n_guardrail(s: CopilotState) -> CopilotState:
    answer, status = guardrail.enforce(s["answer"], s.get("engine_context") or {},
                                       s["retrieved"])
    s["answer"] = answer
    s["guardrail_status"] = status
    s["citations"] = guardrail.validate_citations(answer, s["retrieved"])
    return s


def n_persist(s: CopilotState) -> CopilotState:
    s["latency_ms"] = int((time.time() - s["t0"]) * 1000)
    if not s.get("cached") and s.get("model") != "fallback_template":
        cache.put(s["cache_key"], {"answer": s["answer"], "model": s["model"],
                                   "citations": s["citations"],
                                   "guardrail_status": s["guardrail_status"],
                                   "retrieved": s["retrieved"]})
    return s


def _route_after_cache(s: CopilotState) -> str:
    return "persist" if s.get("cached") else "retrieve"


def build_graph():
    g = StateGraph(CopilotState)
    g.add_node("cache_lookup", n_cache_lookup)
    g.add_node("retrieve", n_retrieve)
    g.add_node("generate", n_generate)
    g.add_node("guardrail", n_guardrail)
    g.add_node("persist", n_persist)
    g.set_entry_point("cache_lookup")
    g.add_conditional_edges("cache_lookup", _route_after_cache,
                            {"retrieve": "retrieve", "persist": "persist"})
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "guardrail")
    g.add_edge("guardrail", "persist")
    g.add_edge("persist", END)
    return g.compile()


_GRAPH = None


def ask(session, question: str, *, rule_year: int | None = None,
        engine_context: dict | None = None) -> dict:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    out = _GRAPH.invoke({"question": question, "rule_year": rule_year,
                         "engine_context": engine_context or {}, "session": session})
    eng = engine_context or {}
    return {
        "answer": out["answer"],
        "citations": out.get("citations", []),
        "engine_values": {"penalty_inr": eng.get("penalty_inr"),
                          "deviation_pct": eng.get("deviation_pct")},
        "meta": {"model": out.get("model"), "cached": out.get("cached", False),
                 "latency_ms": out.get("latency_ms"),
                 "retrieved_chunks": len(out.get("retrieved", [])),
                 "guardrail": out.get("guardrail_status", "pass")},
    }


BRIEFING_QUESTIONS = [
    "Summarise today's deviation risk for this plant in two sentences.",
    "Which blocks carry the highest deviation exposure, and why?",
    "What action does the regulation permit to reduce this exposure?",
]


def generate_briefing(session, plant_id: str, date: str, dsm_summary: dict) -> dict:
    """Pre-generate the operator briefing in the nightly pipeline so the dashboard
    never waits on an LLM. Called by backend/modules/pipeline/daily.py (step 8)."""
    sections = []
    for q in BRIEFING_QUESTIONS:
        r = ask(session, q, rule_year=dsm_summary.get("rule_year"),
                engine_context=dsm_summary)
        sections.append({"question": q, "answer": r["answer"],
                         "citations": r["citations"]})
    return {"plant_id": plant_id, "date": date, "sections": sections,
            "generated_at": _dt.datetime.utcnow().isoformat() + "Z"}
```

---

## Day 7 — Cache + The ₹ Guardrail (Your Signature Feature)

### `backend/modules/rag/guardrail.py` — the file that protects the project's core claim

A prompt instruction is a request, not a guarantee. Enforce it in code, after generation.

```python
# backend/modules/rag/guardrail.py
"""Post-generation enforcement of the 'LLM never originates a number' invariant.

Every numeric token in the answer must trace back to the ENGINE_RESULT payload or
to a retrieved regulation extract. Untraceable numbers are neutralised, not
silently trusted. Status is surfaced to the UI via meta.guardrail.
"""
from __future__ import annotations

import re

NUM = re.compile(r"(?<![\w.])(?:₹\s*|Rs\.?\s*)?(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)")
CITE = re.compile(r"\[([^\]|]+)\|([^\]|]+)\|\s*p\.?\s*(\d+)\s*\]", re.I)

# Block numbers, years, small ordinals are always safe.
_SAFE_SMALL = {str(i) for i in range(0, 121)} | {str(y) for y in range(2000, 2051)}


def _canon(tok: str) -> str:
    tok = tok.replace(",", "")
    return tok.rstrip("0").rstrip(".") if "." in tok else tok


def _allowed_numbers(engine: dict, retrieved: list) -> set[str]:
    allowed = set(_SAFE_SMALL)
    for v in (engine or {}).values():
        if isinstance(v, (int, float)):
            for form in (f"{v}", f"{abs(v):.1f}", f"{abs(v):.2f}", f"{int(abs(v))}"):
                allowed.add(_canon(form))
    for r in retrieved or []:
        for m in NUM.finditer(r.chunk_text):
            allowed.add(_canon(m.group(1)))
    return allowed


def enforce(answer: str, engine: dict, retrieved: list | None = None) -> tuple[str, str]:
    """Returns (safe_answer, status) where status is 'pass' or 'numbers_stripped'."""
    allowed = _allowed_numbers(engine, retrieved or [])
    stripped = False

    def repl(m: re.Match) -> str:
        nonlocal stripped
        if _canon(m.group(1)) in allowed:
            return m.group(0)
        stripped = True
        return "[value not computed by the engine]"

    safe = NUM.sub(repl, answer)
    return safe, ("numbers_stripped" if stripped else "pass")


def validate_citations(answer: str, retrieved: list) -> list[dict]:
    """Keep only citations that match a chunk actually retrieved. A citation the
    model invented is dropped from the response entirely."""
    by_key = {(r.doc_name.lower().strip(), r.clause.lower().strip()): r
              for r in (retrieved or [])}
    out, seen = [], set()
    for doc, clause, _page in CITE.findall(answer):
        key = (doc.lower().strip(), clause.lower().strip())
        r = by_key.get(key)
        if r and key not in seen:
            seen.add(key)
            out.append(r.as_citation())
    if not out:                       # model forgot to cite → attach top retrieved
        out = [r.as_citation() for r in (retrieved or [])[:3]]
    return out


def deterministic_fallback(question: str, engine: dict, retrieved: list) -> str:
    """Used when every LLM provider fails. No model, no risk, still useful."""
    parts = []
    if engine.get("deviation_pct") is not None:
        d = engine["deviation_pct"]
        parts.append(f"The block deviates {d}% from the declared schedule "
                     f"({'under' if d < 0 else 'over'}-injection).")
    if engine.get("penalty_inr") is not None:
        parts.append(f"The deviation charge computed by the DSM engine is "
                     f"₹{engine['penalty_inr']:,.0f}.")
    if retrieved:
        r = retrieved[0]
        parts.append(f"Applicable provision: {r.clause} of {r.doc_name} (p.{r.page_no}).")
    parts.append("The AI explainer is temporarily unavailable; the figures above come "
                 "from the deterministic engine.")
    return " ".join(parts)
```

> **Demo this.** Ask the copilot a rupee question with no `engine_context` and show it refusing to produce a figure where a naive chatbot would confabulate one. That is a 20-second segment that separates you from every other RAG demo in the room.

### `backend/modules/rag/cache.py`

```python
# backend/modules/rag/cache.py
"""TTL response cache. In-process dict by default; swap for Redis if REDIS_URL is set.
Keyed on semantic inputs, so the same question under a different rule year or a
different penalty is a different entry."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

TTL = int(os.getenv("RAG_CACHE_TTL_SECONDS", 3600))
_store: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def make_key(question: str, rule_year, engine_context: dict) -> str:
    payload = {
        "q": " ".join(question.lower().split()),
        "y": rule_year,
        # round engine floats so tiny jitter doesn't blow the cache
        "e": {k: (round(v, 1) if isinstance(v, float) else v)
              for k, v in sorted((engine_context or {}).items())},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str)
                          .encode()).hexdigest()[:32]


def get(key: str) -> dict | None:
    with _lock:
        hit = _store.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > TTL:
            _store.pop(key, None)
            return None
        return dict(val)


def put(key: str, value: dict) -> None:
    with _lock:
        if len(_store) > 2000:
            for k, _ in sorted(_store.items(), key=lambda kv: kv[1][0])[:500]:
                _store.pop(k, None)
        _store[key] = (time.time(), dict(value))


def stats() -> dict:
    with _lock:
        return {"entries": len(_store), "ttl_s": TTL}
```

Hand Member 2 the `generate_briefing()` signature today so he can wire pipeline step 8 tomorrow.

---

## Day 8 — Wire The Real Route + Integration Test

Replace the Day 2 mock. **Do not change the response shape** — Member 3's UI is already built against it.

```python
# backend/api/rag.py  — REAL VERSION
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.modules.rag import cache, copilot, retriever

router = APIRouter(prefix="/rag", tags=["rag"])


class EngineContext(BaseModel):
    penalty_inr: float | None = None
    deviation_pct: float | None = None
    schedule_mw: float | None = None
    actual_mw: float | None = None
    x_value: float | None = None
    frequency_band: str | None = None
    rule_version: str | None = None


class RagQuery(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    plant_id: str | None = None
    block_no: int | None = Field(default=None, ge=1, le=288)
    date: str | None = None
    rule_year: int | None = Field(default=None, ge=2024, le=2031)
    engine_context: EngineContext | None = None


@router.post("/query")
def query(body: RagQuery, db: Session = Depends(get_db)):
    try:
        ctx = body.engine_context.model_dump(exclude_none=True) if body.engine_context else {}
        return copilot.ask(db, body.question, rule_year=body.rule_year, engine_context=ctx)
    except Exception as e:                                    # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"copilot_unavailable: {e}")


@router.get("/health")
def rag_health(db: Session = Depends(get_db)):
    n = db.execute(sql("SELECT count(*) FROM regulation_chunks")).scalar_one()
    models = db.execute(sql("SELECT DISTINCT embed_model FROM regulation_chunks")).scalars().all()
    return {"chunks": n, "embed_models": models, "cache": cache.stats(),
            "bm25_loaded": retriever._bm25 is not None}
```

**Startup wiring Member 2 must add to `main.py`** — send him this snippet, don't edit his file behind his back:

```python
# backend/main.py — lifespan additions
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.api import rag
from backend.db.session import SessionLocal
from backend.modules.rag import embed, retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as s:
        retriever.build_bm25(s)      # ~1 s for 2k chunks
    embed.warmup()                   # 8-15 s model load, paid once at boot
    yield


app = FastAPI(lifespan=lifespan, title="Renewable Forecasting Platform")
app.include_router(rag.router)
```

> That warmup is exactly why the Dockerfile sets `--start-period=90s`. Set it to 10 s and Docker marks a healthy container unhealthy and restart-loops it. This is the kind of bug that eats Day 13.

### Integration tests

```python
# tests/test_rag.py
from fastapi.testclient import TestClient
from backend.main import app
from backend.modules.rag.guardrail import enforce

client = TestClient(app)


def test_contract_shape():
    r = client.post("/rag/query", json={
        "question": "Why was block 52 penalised?", "rule_year": 2026,
        "engine_context": {"penalty_inr": 18240.0, "deviation_pct": -14.2}})
    assert r.status_code == 200
    b = r.json()
    assert set(b) >= {"answer", "citations", "engine_values", "meta"}
    assert b["engine_values"]["penalty_inr"] == 18240.0      # echoed, never recomputed


def test_guardrail_blocks_invented_money():
    safe, status = enforce("The penalty is approximately Rs 25,000 for this block.",
                           {"penalty_inr": 18240.0}, [])
    assert "25,000" not in safe and status == "numbers_stripped"


def test_no_numbers_without_engine_context():
    r = client.post("/rag/query", json={"question": "What will my penalty be tomorrow?"})
    assert r.status_code == 200
    assert r.json()["meta"]["guardrail"] in {"pass", "numbers_stripped"}


def test_rule_year_filters_corpus():
    r = client.post("/rag/query", json={"question": "What is the tolerance band?",
                                        "rule_year": 2024})
    assert "CERC_DSM_Amendment_2026" not in {c["doc"] for c in r.json()["citations"]}
```

---

## Day 9 — AWS: EC2 + RDS + S3 + SSM

> **Order of operations matters.** Console/CLI first, Terraform on Day 13. Writing Terraform for infra you have never stood up turns a 2-hour task into a 6-hour one. You capture it as code *after* it works — that is a deliberate senior choice, and you should say so out loud if a judge asks.

### Step 1: Network + RDS

```bash
export AWS_REGION=ap-south-1                       # Mumbai — lowest latency for judges in India

# RDS PostgreSQL 15 with pgvector available
aws rds create-db-instance \
  --db-instance-identifier renewable-db \
  --db-instance-class db.t4g.micro \
  --engine postgres --engine-version 15.7 \
  --master-username renewable \
  --master-user-password "$(openssl rand -base64 24)" \
  --allocated-storage 20 --storage-type gp3 \
  --backup-retention-period 1 --no-multi-az \
  --db-name renewable --publicly-accessible false

# After it is available, enable the extension (from EC2, not your laptop):
#   psql -h <rds-endpoint> -U renewable -d renewable -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Security-group chain — get this right the first time:

```
ALB SG           inbound 443, 80 from 0.0.0.0/0
EC2 SG           inbound 8000 from ALB SG ONLY        (no 0.0.0.0/0, ever)
RDS SG           inbound 5432 from EC2 SG ONLY
SSH              none — use SSM Session Manager, no key pairs
```

### Step 2: Secrets in SSM Parameter Store

```bash
for p in groq_api_key gemini_api_key db_password pipeline_api_key; do
  aws ssm put-parameter --name "/renewable/$p" --type SecureString \
    --value "REPLACE_ME" --overwrite
done
```

Read them at container start rather than baking them into the image:

```bash
# infra/docker/fetch_secrets.sh — runs on EC2 before docker compose up
set -euo pipefail
aws ssm get-parameters-by-path --path /renewable --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text \
| while IFS=$'\t' read -r name value; do
    echo "$(basename "$name" | tr '[:lower:]' '[:upper:]')=$value"
  done > /opt/renewable/.env
chmod 600 /opt/renewable/.env
```

### Step 3: EC2 + ECR

```bash
aws ecr create-repository --repository-name renewable-backend

# EC2: t3.large (8 GB — bge-m3 + reranker need ~3 GB resident), Amazon Linux 2023,
# IAM instance profile with: AmazonSSMManagedInstanceCore,
#   ECR pull, S3 read on your buckets, ssm:GetParameter* on /renewable/*
# user-data: install docker + compose plugin, aws cli, create /opt/renewable
```

```bash
# S3 buckets
aws s3 mb s3://renewable-data-<suffix>       # raw/ processed/ models/ regulations/
aws s3 mb s3://renewable-frontend-<suffix>   # React build (private + CloudFront OAC)
```

### Step 4: Load the vector index into RDS

Re-run Colab notebook 10 with `DATABASE_URL` pointed at RDS (through an SSM port-forward session, or run the notebook's insert cell as a script on the EC2 box). Then verify:

```bash
curl -s http://<ec2-private-ip>:8000/rag/health | jq
# {"chunks": 1487, "embed_models": ["BAAI/bge-m3"], "bm25_loaded": true, ...}
```

### Day 9 exit criteria
- [ ] `GET /health` returns 200 from inside the VPC
- [ ] `GET /rag/health` shows a non-zero chunk count in RDS
- [ ] No security group has 0.0.0.0/0 on 5432 or 8000
- [ ] No secret exists in the repo, the image, or shell history

---

## Day 10 — CloudFront + S3 + ALB (One HTTPS URL)

```
Users (HTTPS)
   ↓
CloudFront distribution  (default *.cloudfront.net cert — no domain purchase needed)
   ├── default /*     → S3 origin (React build, private bucket + OAC)
   └── /api/*         → ALB origin (origin protocol: HTTP), path pattern rewrite
                          ↓
                     ALB (HTTP :80) → target group → EC2 :8000
```

> **The shortcut that saves you three hours:** use CloudFront's default `*.cloudfront.net` certificate. Viewers get real HTTPS; CloudFront talks to the ALB over HTTP inside AWS. **You need no domain, no Route 53 zone, and no ACM validation.** Buying and validating a domain during a hackathon is a way to lose an afternoon to DNS propagation.

```bash
# Frontend deploy (Member 3 hands you the build output)
cd frontend && npm run build
aws s3 sync dist/ s3://renewable-frontend-<suffix>/ --delete
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```

Two settings that break the demo if you miss them:

1. **CORS.** Add the CloudFront domain to `CORS_ORIGINS` in the EC2 `.env` and restart the backend. Symptom if you forget: the dashboard loads, every panel shows a spinner forever, console shows CORS errors.
2. **SPA routing.** Add a CloudFront custom error response mapping 403 and 404 → `/index.html` with status 200. Symptom if you forget: the dashboard works, but a refresh on `/plant/GJ_SOLAR_A` returns AccessDenied.

Give the team the URL the moment it is live. Member 3 needs it for `.env.production`.

---

## Day 11 — CI Pipeline

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push: { branches: ["**"] }
  pull_request: { branches: [main] }

permissions:
  contents: read
  id-token: write            # required for OIDC

jobs:
  ci:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_USER: renewable
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: renewable_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U renewable"
          --health-interval 5s --health-timeout 3s --health-retries 20
    env:
      DATABASE_URL: postgresql+psycopg2://renewable:testpass@localhost:5432/renewable_test
      RAG_PRIMARY_MODEL: mock
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }

      - name: Install
        run: pip install -r requirements.txt -r requirements-dev.txt

      - name: Lint
        run: ruff check . --select E,F,W

      - name: Tests
        run: pytest tests/ -v --tb=short -m "not slow"

      - name: Build image
        run: docker build -t renewable-backend:${{ github.sha }} .

      - name: Scan image
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: renewable-backend:${{ github.sha }}
          severity: HIGH,CRITICAL
          exit-code: "0"            # report, don't block — this is a 14-day sprint

      - name: Push to ECR
        if: github.ref == 'refs/heads/main'
        run: |
          aws ecr get-login-password --region $AWS_REGION \
            | docker login --username AWS --password-stdin $ECR_REGISTRY
          docker tag renewable-backend:${{ github.sha }} $ECR_REGISTRY/renewable-backend:${{ github.sha }}
          docker tag renewable-backend:${{ github.sha }} $ECR_REGISTRY/renewable-backend:latest
          docker push --all-tags $ECR_REGISTRY/renewable-backend
```

Mark the slow model-loading tests `@pytest.mark.slow` and skip them in CI. A CI run that pulls 2.2 GB of weights on every push will get switched off by the team by Day 12 — which means you effectively have no CI.

---

## Day 12 — Deploy Pipeline (OIDC, no static keys)

### Step 1: The OIDC trust relationship (one-time)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

```json
// Trust policy for role GitHubActionsDeployRole — note the tight sub condition
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::<ACCOUNT>:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": { "token.actions.githubusercontent.com:aud": "sts.amazonaws.com" },
      "StringLike":   { "token.actions.githubusercontent.com:sub": "repo:<ORG>/<REPO>:ref:refs/heads/main" }
    }
  }]
}
```

> Without that `StringLike` condition on `sub`, **any** GitHub repository on the internet can assume your role. This is the most-copy-pasted security hole in GitHub Actions setups. Get it right and mention it in the demo — judges notice.

### Step 2: `deploy.yml`

```yaml
# .github/workflows/deploy.yml
name: deploy
on:
  workflow_run:
    workflows: ["ci"]
    types: [completed]
    branches: [main]

permissions: { contents: read, id-token: write }

jobs:
  deploy:
    if: github.event.workflow_run.conclusion == 'success'
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsDeployRole
          aws-region: ap-south-1

      - name: Roll the backend on EC2
        run: |
          CMD_ID=$(aws ssm send-command \
            --instance-ids ${{ secrets.EC2_INSTANCE_ID }} \
            --document-name AWS-RunShellScript \
            --comment "deploy ${{ github.sha }}" \
            --parameters 'commands=[
              "set -euo pipefail",
              "cd /opt/renewable",
              "bash infra/docker/fetch_secrets.sh",
              "aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin ${{ secrets.ECR_REGISTRY }}",
              "docker compose -f docker-compose.prod.yml pull backend",
              "docker compose -f docker-compose.prod.yml up -d --no-deps backend",
              "for i in $(seq 1 30); do curl -fsS http://localhost:8000/health && exit 0; sleep 5; done; exit 1"
            ]' --query 'Command.CommandId' --output text)
          aws ssm wait command-executed --command-id "$CMD_ID" \
            --instance-id ${{ secrets.EC2_INSTANCE_ID }}

      - name: Invalidate CloudFront
        run: aws cloudfront create-invalidation \
               --distribution-id ${{ secrets.CF_DISTRIBUTION_ID }} --paths "/*"
```

The 30×5 s health-check loop exists because of the embedding-model warmup. Without it, deploy reports success while the container is still loading and the next person to open the dashboard sees a 502.

---

## Day 13 — EventBridge, CloudWatch, Terraform Capture

### EventBridge → daily pipeline

```bash
aws scheduler create-schedule \
  --name renewable-daily-pipeline \
  --schedule-expression "cron(30 2 * * ? *)" \
  --schedule-expression-timezone "UTC" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn":"arn:aws:lambda:ap-south-1:<ACCT>:function:trigger-pipeline",
    "RoleArn":"arn:aws:iam::<ACCT>:role/SchedulerInvokeRole"
  }'
```

02:30 UTC = 08:00 IST, ahead of the RLDC schedule-submission cutoff. A tiny Lambda does `POST /pipeline/run` with the `X-API-Key` header read from SSM. Do not put the API key in the EventBridge target payload — target definitions are readable by anyone with console access.

**Coordinate with Member 2 today:** he owns `/pipeline/run` and the `job_runs` table; you own the trigger and the alarm on failures. Agree that the endpoint returns `202 {run_id}` immediately and runs the work in a background task — an EventBridge/Lambda target that waits 4 minutes for a synchronous pipeline will time out.

### CloudWatch alarms worth having (and only these)

| Alarm | Condition | Why |
|---|---|---|
| `pipeline-failed` | Custom metric `PipelineStatus` = failed, 1 datapoint | Tomorrow's dashboard would be empty |
| `backend-5xx` | ALB `HTTPCode_Target_5XX_Count` > 5 in 5 min | Backend is down during judging |
| `ec2-memory-high` | Memory > 85% for 10 min | bge-m3 + reranker + uvicorn workers OOM risk |
| `llm-all-failed` | Log filter on `"llm_fail"` ≥ 5 in 5 min | Both providers down → copilot on fallback |

```bash
aws logs put-metric-filter \
  --log-group-name /renewable/backend \
  --filter-name llm-failures \
  --filter-pattern '"llm_fail"' \
  --metric-transformations metricName=LLMFailures,metricNamespace=Renewable,metricValue=1
```

### Terraform — captured now, not written first

```hcl
# infra/terraform/main.tf  (structure only — import what already exists)
terraform { required_providers { aws = { source = "hashicorp/aws", version = "~> 5.0" } } }
provider "aws" { region = var.region }

module "network"   { source = "./modules/network" }
module "database"  { source = "./modules/database"  vpc_id = module.network.vpc_id }
module "compute"   { source = "./modules/compute"   vpc_id = module.network.vpc_id }
module "frontend"  { source = "./modules/frontend" }
module "scheduler" { source = "./modules/scheduler" }
```

```bash
# Import the running infra rather than recreating it — zero downtime, real state
terraform import module.compute.aws_instance.backend i-0abc123
terraform import module.database.aws_db_instance.main renewable-db
terraform plan      # must show "No changes" before you commit
```

`terraform plan` showing **no changes** against live infrastructure is the proof that your code matches reality. Commit the state to S3 with DynamoDB locking, never to git, and make sure `*.tfstate*` is in `.gitignore` — it contains the RDS password in plaintext.

---

## Day 14 — Rehearsal, Failover Drill, Cost Control

### End-to-end rehearsal script (run it three times, timed)

```
1. Open the CloudFront URL in a fresh incognito window        → dashboard loads < 3 s
2. Select GJ_SOLAR_A                                          → fan chart renders
3. Drag the regulation slider 2026 → 2031                     → heatmap re-colours
4. Toggle pooling on                                          → savings % appears
5. Ask the copilot "Why was block 52 penalised?"              → cited answer < 4 s
6. Click a citation badge                                     → opens the real CERC URL
7. Ask "What will my penalty be next Tuesday?"                → refuses to invent ₹
8. Trigger POST /pipeline/run manually                        → 202 + run_id, job_runs row
```

### Failover drill — break it on purpose, today, not during judging

| Break | Expected behaviour | Fix if it doesn't |
|---|---|---|
| Revoke the Groq key | Answers continue via Gemini, `meta.model` shows gemini | Fallback list order in `llm.py` |
| Revoke both keys | 200 with `guardrail: fallback_template`, engine numbers still shown | `deterministic_fallback()` |
| Stop the backend container | Frontend shows an error state, not a white screen | Member 3's error boundary |
| Truncate `regulation_chunks` | `/rag/health` reports 0 chunks; copilot degrades, doesn't crash | Empty-retrieval path |
| Kill Wi-Fi | **Have `docker compose up` running locally as the backup demo** | — |

**The offline demo is not optional.** Hackathon venue Wi-Fi fails. Have the entire stack running on one laptop with a seeded database, and know which URL to switch to within 15 seconds.

### Cost control

| Resource | ~₹/day | Shut down when |
|---|---|---|
| EC2 t3.large | ~₹170 | `aws ec2 stop-instances` immediately after judging |
| RDS db.t4g.micro | ~₹60 | Snapshot then delete |
| CloudFront + S3 | < ₹10 | Leave up — it's the portfolio link |
| NAT Gateway | ~₹280 | **Avoid entirely** — put EC2 in a public subnet with an ALB in front |

A NAT Gateway is the single largest accidental AWS bill in hackathon projects. You do not need one.

---

## Decision Log — The Senior Calls and Their Escape Hatches

| Decision | Chosen | Why | Escape hatch |
|---|---|---|---|
| Vector index type | **HNSW**, not ivfflat | ivfflat built on a near-empty table has terrible recall; HNSW needs no training or `lists` tuning at this corpus size | Corpus < 3k rows: drop the index entirely, seq scan is ~5 ms |
| Fusion method | **RRF**, not weighted score blend | Cosine and BM25 scales are incomparable; weights need a calibration set we don't have | Add weights on Day 13 only if the eval set shows a clear win |
| Reranker | `bge-reranker-**base**`, not `-v2-m3` | 278 MB vs 2.2 GB; on CPU, v2-m3 costs ~1 s per query — that's your whole latency budget | `RAG_ENABLE_RERANKER=false` kills it instantly; RRF alone is decent |
| Embedding model | `bge-m3` (1024-dim) | Best quality on legal text, matches the plan and the schema | `bge-small-en-v1.5` (384-dim) if memory bites — requires migration + re-embed |
| Model weights | **Baked into the image** | Cold start goes from ~90 s to ~12 s; container works with no internet | S3 + init download if the 4.5 GB image becomes an ECR problem |
| Graph shape | **Linear LangGraph**, not an agent loop | Every answer must be traceable to a clause; a re-planning agent is unauditable | None — do not add tool-calling loops |
| Infra authoring | **Console/CLI first, Terraform imported Day 13** | Writing TF for infra you've never stood up costs 3× the time | If AWS fails entirely, ship docker-compose + a tunnel |
| HTTPS | **CloudFront default cert** | No domain, no Route 53, no ACM DNS validation | Buy a domain only if there's spare time on Day 13 |
| Deploy mechanism | **SSM RunCommand** | No SSH keys in GitHub secrets, no bastion, full audit trail | `docker compose pull && up -d` over an SSM session, manually |

---

## The Fallback Ladder (Where To Stop If Time Runs Out)

Climb as far as you get. **Every rung is a working demo.** Do not start rung 3 until rung 2 is committed and green.

```
Rung 1  docker compose up on a laptop + seeded DB        ← Day 1.   Always works. Never delete this path.
Rung 2  + Cloudflare Tunnel / ngrok on port 8000         ← 10 min.  Public URL, zero AWS.
Rung 3  + EC2 running docker compose, public IP          ← Day 9.   Real cloud, no CDN.
Rung 4  + CloudFront + S3 frontend + ALB                 ← Day 10.  The demo URL.
Rung 5  + GitHub Actions CI/CD                           ← Day 11-12. "We ship on merge."
Rung 6  + EventBridge + CloudWatch + Terraform           ← Day 13.  Production story.
```

If Day 9 arrives and AWS credits haven't landed, go to rung 2 and spend the saved days making the RAG demonstrably better. A polished copilot on a tunnel beats a half-configured VPC every single time.

---

## Critical Things NEVER to Do

| ❌ WRONG | ✅ RIGHT |
|---|---|
| Let the LLM state a ₹ figure the engine didn't produce | `guardrail.enforce()` strips every untraceable number, post-generation |
| Return a citation the model wrote from memory | `validate_citations()` keeps only citations matching retrieved chunks |
| Embed the corpus with one model, queries with another | Store `embed_model` per row; assert at startup, refuse to serve on mismatch |
| Create the ivfflat/HNSW index before inserting rows | Insert first, index after — always |
| Download model weights at container start | Bake them into a cached Docker layer |
| Commit `.env`, `*.tfstate`, or an API key | SSM Parameter Store; `.gitignore` verified on Day 1 |
| Put `0.0.0.0/0` on the EC2 or RDS security group | ALB → EC2 → RDS chain only; SSM Session Manager instead of SSH |
| Store long-lived AWS keys in GitHub secrets | OIDC with a `sub` condition pinned to your repo and branch |
| Write Terraform for infra you've never deployed | Deploy by CLI, then `terraform import` and prove `plan` is clean |
| Change the `/rag/query` response shape after Day 3 | Freeze it Day 1; Member 3 builds blind against it |
| Run an LLM call inside a dashboard request path | Pre-generate briefings in the nightly pipeline; cache everything else |
| Provision a NAT Gateway | Public subnet + ALB; NAT is the biggest accidental bill in hackathon AWS |
| Discover an image-only PDF on Day 10 | Validate `get_text()` output on Day 2 |
| Demo without a local offline fallback running | Rung 1 stays alive on a laptop through the entire judging session |

---

## Handoff Checklist

### What you give Member 2 (Backend)
```
✅ docker-compose.yml + Dockerfile               (Day 1)
✅ .env.example — every var name                 (Day 1)
✅ infra/docker/init_db.sql                      (Day 1)
✅ Schema delta request: regulation_chunks
     + embed_model VARCHAR, + chunk_id VARCHAR UNIQUE, − ivfflat index   (Day 3)
✅ backend/api/rag.py — mock                     (Day 2)
✅ backend/api/rag.py — real                     (Day 8)
✅ main.py lifespan snippet (bm25 build + embed warmup)                  (Day 8)
✅ copilot.generate_briefing(session, plant_id, date, dsm_summary) -> dict (Day 7)
✅ POST /pipeline/run contract: 202 + run_id, async background execution (Day 13)
✅ EC2 deploy path + docker-compose.prod.yml                             (Day 12)
```

### What you give Member 3 (Frontend)
```
✅ docs/api_rag_contract.md — frozen request/response          (Day 1)
✅ Working mock POST /rag/query                                (Day 2)
✅ Real /rag/query at the same shape                           (Day 8)
✅ CloudFront URL for .env.production                          (Day 10)
✅ CORS origin registered for that URL                         (Day 10)
✅ S3 deploy command for `npm run build` output                (Day 10)
✅ meta.guardrail semantics so the UI can badge stripped answers (Day 7)
```

### What you need from others
```
⬅ Member 2: requirements.txt, port numbers, env var names, DB session factory  (Day 1)
⬅ Member 2: regulation_chunks table migrated                                   (Day 3)
⬅ Member 1: sample DSM engine output dict → your engine_context shape          (Day 6)
⬅ Member 1: model .pkl/.pt files to upload to S3                               (Day 9)
⬅ Member 3: frontend/dist build output                                         (Day 10)
```

---

## Your Definition of Done

- [ ] A fresh clone runs the whole stack with two commands
- [ ] `POST /rag/query` returns a cited answer in under 4 s, cached in under 100 ms
- [ ] Recall@5 ≥ 0.7 on your 15-question eval set
- [ ] The guardrail demonstrably refuses to invent a ₹ figure, on camera
- [ ] Every citation badge opens a real, live CERC/IEGC URL
- [ ] One HTTPS URL loads the full dashboard for anyone, on any network
- [ ] A push to `main` deploys itself and passes a health check
- [ ] EventBridge fired the pipeline at least once, unattended, with a `job_runs` row to prove it
- [ ] No secret anywhere in the repo, the image, or the git history
- [ ] The offline laptop demo is running and rehearsed before judging starts
