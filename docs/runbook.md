# Runbook — demo day, failure modes, and what to do about them

**Owner:** Member 4. Read this before judging, not during it.

> **See also:** `docs/deployment.md` — provisioning, CI/CD, and cost teardown.

## Quick Reference (5 commands to know cold)

```bash
# 1. Check backend health
curl -fsS https://<cloudfront>/api/health | jq

# 2. Check RAG readiness (chunks must be non-zero, no warning key)
curl -fsS https://<cloudfront>/api/rag/health | jq '.chunks, .warning, .llm.usable'

# 3. Get on the box (no SSH key, no port 22)
aws ssm start-session --target <instance-id>

# 4. Tail backend logs
docker compose -f docker-compose.prod.yml logs --tail 100 backend

# 5. Emergency rollback
IMAGE_TAG=<previous-sha> docker compose -f docker-compose.prod.yml up -d --no-deps backend
```

**Five failover scenarios to rehearse the day before:** Rogue Groq key · both keys revoked · backend stopped · corpus truncated · wifi dead. See [Failover drill](#failover-drill--break-it-on-purpose-the-day-before).

---


## Pre-flight (run 30 minutes before judging)

```bash
BACKEND=https://<cloudfront-domain>

curl -fsS $BACKEND/api/health | jq
curl -fsS $BACKEND/api/rag/health | jq
```

| Check | Expected | If wrong |
|---|---|---|
| `/health` | `{"status": "healthy"}` | Container is down or still loading. `docker compose logs backend`. |
| `rag/health.chunks` | non-zero | Corpus never loaded. Run `scripts/build_index.py`. |
| `rag/health.warning` | **absent** | Index/query embedding models disagree — see below. This is the dangerous one. |
| `rag/health.llm.usable` | at least one model | No API key reached the container. Re-run `fetch_secrets.sh`. |
| `rag/health.bm25_loaded` | `true` | Sparse retrieval is off; hybrid is running on dense alone. |

And have **rung 1 running on a laptop** with a seeded database, with the tab open. Know which
URL to switch to within fifteen seconds.

---

## End-to-end rehearsal

Run this three times, timed. It is the demo script.

| # | Action | Expected |
|---|---|---|
| 1 | Open the CloudFront URL in a fresh incognito window | dashboard loads < 3 s |
| 2 | Select `GJ_SOLAR_A` | fan chart renders |
| 3 | Drag the regulation slider 2026 → 2031 | heatmap re-colours |
| 4 | Toggle pooling on | savings % appears |
| 5 | Ask *"Why was block 52 penalised?"* | cited answer < 4 s |
| 6 | Click a citation badge | opens the real CERC URL |
| 7 | Ask *"What will my penalty be next Tuesday?"* | **refuses to invent a ₹ figure** |
| 8 | `POST /pipeline/run` manually | 202 + run_id, and a `job_runs` row |

Step 7 is the one that separates this from every other RAG demo in the room. A naive chatbot
confabulates a number there. Show the refusal, then show `meta.guardrail` explaining why.

---

## Failover drill — break it on purpose, the day before

| Break | Expected behaviour | If it does not |
|---|---|---|
| Revoke the Groq key | answers continue via Gemini; `meta.llm_model` shows gemini | check fallback order in `llm.py` |
| Revoke both keys | 200 with `guardrail: fallback_template`; engine ₹ figures still shown | `guardrail.deterministic_fallback()` |
| Stop the backend container | frontend shows an error state, not a white screen | Member 3's error boundary |
| `TRUNCATE regulation_chunks` | `/rag/health` reports 0 chunks; copilot degrades, does not crash | empty-retrieval path in `copilot.n_retrieve` |
| Kill wifi | switch to the laptop stack | rung 1 must already be running |

All five are covered by automated tests (`tests/test_rag_copilot.py`), but run them against
the deployed stack anyway — the tests prove the code degrades, not that the deployment does.

---

## Failure modes, ranked by how much damage they do

### 1. Embedding model mismatch — silent and total

**Symptom:** answers look fine, citations look fine, and they are unrelated to the question.
Nothing errors.

**Cause:** the corpus was embedded with one model and queries use another. Nearest neighbours
in two different embedding spaces are noise.

**Detect:**
```bash
curl -s $BACKEND/api/rag/health | jq '.embed_models, .live_embed_model, .warning'
```

**Fix:** make `RAG_EMBED_MODEL` on the server match what built the index, or rebuild the index.
In production the server refuses to start on a mismatch (`verify_corpus_model`), which is
deliberate: failing to boot is much better than serving confident nonsense.

### 2. Groq rate limit during judging

**Symptom:** first few questions are fast, then latency spikes or answers fall back.

**Cause:** Groq's free tier is roughly 30 requests/minute per org. Four teammates testing while
a judge types will hit it.

**Mitigations, already in place:** the response cache (identical question + rule year + engine
values is free), pre-generated briefings from the nightly pipeline, and the Gemini fallback.

**On the day:** warm the cache by running the rehearsal script once, and ask teammates to stop
hitting the copilot during judging.

### 3. Container restart loop after deploy

**Symptom:** deploy reports success; the site 502s; the container keeps restarting.

**Cause:** the healthcheck `start-period` is shorter than the bge-m3 load (~90 s), so Docker
marks a still-loading container unhealthy and kills it, forever.

**Fix:** `start-period` is 90 s in both the Dockerfile and `docker-compose.prod.yml`, and the
ALB target group tolerates 5 × 30 s. If this recurs, the model is loading slower than that —
check memory pressure before raising the timeout.

### 4. Every dashboard panel spins forever

**Cause:** CORS. The CloudFront domain is not in `CORS_ORIGINS`.

```bash
aws ssm put-parameter --name /renewable/cors_origins --type SecureString \
    --value "https://<cloudfront-domain>" --overwrite
# then redeploy, or on the box: bash infra/docker/fetch_secrets.sh && docker compose -f docker-compose.prod.yml up -d
```

### 5. Refresh on a deep link returns AccessDenied

**Cause:** SPA routing. CloudFront must map 403 and 404 → `/index.html` with status 200.
`02_cloudfront.sh` sets this; check it survived a distribution edit.

### 6. Out of memory

**Symptom:** the container dies with no stack trace.

**Cause:** bge-m3 (~2.2 GB) + reranker + two uvicorn workers on 8 GB.

**Fast mitigation:** `RAG_ENABLE_RERANKER=false` frees ~300 MB and about a second per query.
RRF alone is decent. Then restart.

---

## Getting onto the box

There is no SSH key and no port 22.

```bash
aws ssm start-session --target <instance-id>

sudo -i
cd /opt/renewable
docker compose -f docker-compose.prod.yml logs --tail 100 backend
docker compose -f docker-compose.prod.yml ps
```

Every session is recorded in CloudTrail, which is the point.

---

## Rollback

```bash
# Redeploy a known-good image tag
gh workflow run deploy.yml

# Or by hand on the box
cd /opt/renewable
IMAGE_TAG=<previous-sha> docker compose -f docker-compose.prod.yml up -d --no-deps backend
curl -fsS localhost:8000/health
```

ECR keeps the last 10 images (lifecycle policy), so there is always something to roll back to.

---

## Alarms and what each one means

| Alarm | Means | Do |
|---|---|---|
| `renewable-llm-all-failed` | both providers failing | answers are fallback templates; check keys and quotas |
| `renewable-backend-5xx` | backend erroring | logs first, then roll back |
| `renewable-pipeline-failed` | nightly run failed | tomorrow's dashboard will be empty; re-run by hand |
| `renewable-ec2-memory-high` | >85% for 10 min | disable the reranker, restart |

---

## After judging

```bash
aws ec2 stop-instances --instance-ids <id>
aws rds create-db-snapshot --db-instance-identifier renewable-db \
    --db-snapshot-identifier renewable-final
aws rds delete-db-instance --db-instance-identifier renewable-db --skip-final-snapshot
```

Leave CloudFront and S3 up — under Rs 10/day, and it is the portfolio link.
