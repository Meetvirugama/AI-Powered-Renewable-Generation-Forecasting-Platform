# Runbook

Pre-flight checks, known failure modes, and what to do about each. Written for the live Azure
deployment. Read it before a demo, not during one.

For how the deployment is built, see [deployment_azure.md](deployment_azure.md). The AWS
equivalents of these commands are in [deployment.md](deployment.md).

---

## Quick reference

```bash
API=https://57.159.24.68.nip.io

curl -s $API/health     | jq '.engines, .serving_synthetic_data, .forecast_models.status'
curl -s $API/rag/health | jq '.chunks, .bm25_loaded, .llm.usable, .warning'

ssh -i Hackout_key.pem azureuser@57.159.24.68
sudo journalctl -u renewable-api -n 100 --no-pager
sudo systemctl restart renewable-api

gh workflow run deploy.yml                      # redeploy main
```

---

## Pre-flight, 30 minutes before

| Check | Expected | If not |
|---|---|---|
| `/health` → `status` | `healthy` | Service down or still starting. Check the journal. |
| `/health` → `serving_synthetic_data` | `[]` | An engine is in mock mode. Check `.env` on the VM. |
| `/health` → `forecast_models.status` | `ok`, 9 models loaded | Model files missing or rejected by the physics gate. |
| `/rag/health` → `chunks` | 179 or more | Corpus not loaded. Run `scripts/build_index.py --truncate`. |
| `/rag/health` → `llm.usable` | both models listed | A provider has no working key. |
| `/rag/health` → `warning` | absent | Corpus and query embedding models disagree. See failure mode 1. |
| Dashboard on Vercel | panels load, no console errors | See failure mode 4. |

Then open the dashboard once and ask the copilot one question. That warms the weather cache and
the response cache, so the first judge does not pay for either.

Keep the laptop fallback ready: `docker compose up` with `.env` in mock mode, and the local
frontend with `VITE_USE_MOCKS=true`. Venue wifi fails. Know which tab to switch to.

---

## Rehearsal

Run it end to end at least twice, timed.

| # | Action | Expected |
|---|---|---|
| 1 | Open the dashboard in a private window | Overview loads in a few seconds |
| 2 | Pick a plant on the map | Every panel re-fetches for that plant |
| 3 | Forecast page, switch 24 → 72 h | Fan chart redraws with wider bands |
| 4 | Change the rule year 2026 → 2031 | Heatmap re-colours, penalty rises |
| 5 | Actions page, move the battery slider | `battery_saving_inr` appears separately from the schedule saving |
| 6 | Toggle pooling | Individual vs pooled totals and allocation |
| 7 | Copilot: "Why is block 52 risky?" | Cited answer, citation badges open real CERC links |
| 8 | Copilot: "What will my penalty be next Tuesday?" | No rupee figure invented; guardrail status visible |

Step 8 is the demonstration that matters most. A general chatbot makes up a number there.

---

## Failover drill

Break each of these on purpose before the demo, on the real deployment.

| Break | Expected | If not |
|---|---|---|
| Remove the Groq keys | Answers continue from Gemini; `meta.llm_model` shows it | Fallback order in `backend/modules/rag/llm.py` |
| Remove every LLM key | `200` with `guardrail: fallback_template`, engine figures still correct | `guardrail.deterministic_fallback` |
| Stop `renewable-api` | Frontend shows error states, not a blank page | Frontend error handling |
| Block Open-Meteo | Forecast routes return a clear error, not invented weather | `weather_provider` returns empty on failure by design |

The first two are also covered by `tests/test_rag_copilot.py` and `tests/test_llm_key_rotation.py`.
Tests prove the code degrades; the drill proves the deployment does.

---

## Failure modes

Ranked by how much damage they do before anyone notices.

### 1. Embedding model mismatch

**Symptom.** Answers and citations look well-formed and are unrelated to the question. Nothing
errors.

**Cause.** The corpus was embedded with one model and queries use another.

**Detect.** `curl -s $API/rag/health | jq '.embed_models, .live_embed_model, .warning'`

**Fix.** Rebuild the index with the model the server uses. In production the service refuses to
start on a mismatch, which is intended. Production currently runs BM25-only with no stored
embeddings, so this cannot occur until dense embeddings are loaded.

### 2. An engine silently in mock mode

**Symptom.** Everything works, and `serving_synthetic_data` is not empty.

**Cause.** Usually the `.env` on the VM. systemd's `EnvironmentFile=` does not strip inline
comments, so `FORECAST_ENGINE_TYPE=production  # note` once arrived as a value that matched
nothing. The factory now strips comments, but a typo still reads as `mock`.

**Fix.** Correct `.env`, `sudo systemctl restart renewable-api`, re-check `/health`.

### 3. Rate limits during the demo

**Symptom.** The first few copilot answers are quick, then slow down or fall back.

**Mitigation already in place.** Several keys per provider with rotation on quota errors, Gemini
as fallback, a one-hour response cache, and the deterministic template as a last resort.

**On the day.** Ask teammates not to use the copilot while judges are.

### 4. Dashboard panels stay empty

**Causes, in order of likelihood.**

1. `VITE_API_BASE_URL` on Vercel is wrong or still `http://`. An HTTPS page cannot call an HTTP
   API; the browser blocks it as mixed content.
2. The API is down. Check `/health`.
3. CORS. The server runs `CORS_ORIGINS=*`; if that has been tightened, the Vercel domain must be
   in the list.

### 5. Forecast requests fail

**Cause.** Open-Meteo unreachable from the VM. The production forecast engine refuses to
forecast without weather rather than predicting from the clock alone.

**Fast rollback.** Set `FORECAST_ENGINE_TYPE=mock` and restart. `/health` will then list
`forecast` under `serving_synthetic_data`, and it should be said out loud in the demo.

### 6. A dependency install dies halfway

**Cause.** A long `pip install` over SSH is killed when the session drops, leaving a broken venv.

**Fix.** Detach it:

```bash
nohup bash -c 'venv/bin/python -m pip install -r requirements.txt > /tmp/pip.log 2>&1; \
  echo $? > /tmp/pip.done' >/dev/null 2>&1 &
cat /tmp/pip.done 2>/dev/null && tail -5 /tmp/pip.log
```

### 7. A deploy leaves the API down

The deploy workflow already rolls back automatically when `/health` does not come up within two
minutes, and prints the failed release's logs in the Actions run. If it happens anyway:

```bash
cd ~/AI-Powered-Renewable-Generation-Forecasting-Platform
git reset --hard <last-good-sha>
sudo systemctl restart renewable-api
curl -fsS localhost:8000/health
```

---

## Running the pipeline by hand

There is no scheduler on the Azure deployment.

```bash
curl -s -X POST $API/pipeline/run -H "X-API-Key: $PIPELINE_API_KEY" \
  -H 'content-type: application/json' -d '{}'
# -> 202 {"run_id": "..."}

curl -s $API/pipeline/status/<run_id> | jq
```

---

## After the demo

Deallocate the VM. Shutting it down from inside the OS leaves it allocated and billing for
compute; deallocating releases it. Disks bill either way.

```bash
az vm deallocate --resource-group <rg> --name Hackout
```

Leave the Vercel frontend up; it costs nothing and is the link people will click later.
