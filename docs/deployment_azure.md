# Azure Deployment — live runbook

**Status: live.** Backend running on an Azure VM behind Caddy with a real Let's Encrypt
certificate.

| | |
|---|---|
| **HTTPS API** | `https://57.159.24.68.nip.io` |
| **Swagger UI** | `https://57.159.24.68.nip.io/docs` |
| **HTTP (fallback)** | `http://57.159.24.68` |
| **Host** | Azure `Standard_D4as_v4`, Ubuntu 24.04, 4 vCPU / 16 GB |
| **SSH** | `ssh -i Hackout_key.pem azureuser@57.159.24.68` |
| **Database** | Supabase PostgreSQL (external, already migrated) |

---

## Why `nip.io` and not the bare IP

`nip.io` resolves `57.159.24.68.nip.io` back to `57.159.24.68`, which gives Let's Encrypt a real
hostname to issue a certificate against. **Certificates cannot be issued for a bare IP address.**

That matters because the frontend is served over HTTPS on Vercel, and a browser blocks an HTTPS
page from calling an HTTP API — mixed content. Without a certificate the dashboard would load and
every panel would sit empty with console errors, which looks exactly like a backend outage.

No domain purchase, no Route 53, no DNS propagation wait.

---

## Architecture

```
Browser (HTTPS)
   │
   ├── Vercel ──────────────► React frontend
   │
   └── https://57.159.24.68.nip.io
          │
       Caddy :443  (auto-renewing Let's Encrypt cert)
          │  reverse_proxy
       uvicorn :8000  (systemd: renewable-api, 2 workers)
          │
       Supabase PostgreSQL
```

Two systemd units, both `enabled` so they survive a reboot:

| Unit | Role |
|---|---|
| `renewable-api` | uvicorn on :8000, `Restart=always` |
| `caddy` | TLS termination + reverse proxy on :80/:443 |

---

## Frontend wiring

Set this in the Vercel project's environment variables and redeploy:

```
VITE_API_BASE_URL=https://57.159.24.68.nip.io
```

`CORS_ORIGINS=*` on the server, so any origin can call the API. That is deliberate for the demo —
the API holds no cookie session, and the one sensitive route (`POST /pipeline/run`) is protected by
`X-API-Key` rather than by origin. Tighten it to the Vercel domain afterwards.

---

## Operating it

```bash
# status and logs
systemctl status renewable-api
sudo journalctl -u renewable-api -f
sudo journalctl -u caddy -n 50

# restart after a config or .env change
sudo systemctl restart renewable-api

# deploy a new version
cd ~/AI-Powered-Renewable-Generation-Forecasting-Platform
git pull origin main
venv/bin/pip install -r requirements.txt      # only if requirements changed
sudo systemctl restart renewable-api
```

### Health checks

```bash
curl https://57.159.24.68.nip.io/health       # engines + serving_synthetic_data
curl https://57.159.24.68.nip.io/rag/health   # corpus size, embed model, provider keys
```

`/health` reports which engines are synthetic. Check it before demoing, not during.

---

## The trap that cost an hour, recorded so it does not recur

`.env` shipped with inline comments:

```bash
OPTIMIZER_TYPE=mock          # mock | production
```

**python-dotenv strips that comment. systemd's `EnvironmentFile=` does not.** So the identical file
gives `mock` when the app loads `.env` itself and `mock          # mock | production` under
systemd — and because systemd's environment wins, `/health` reported:

```json
"engines": {"optimizer": "mock          # mock | production"}
```

Setting it to `production` would have produced `production          # mock | production`, which
matches no branch, so the factory would have **silently served the mock** — the exact failure the
fail-fast guard exists to prevent, slipping past it because the string never equalled
`"production"`.

Fixed in two places: the comments were stripped from the server's `.env`, and
`factory._engine_mode()` now normalises the value so no future deployment can hit it.

---

## Long-running installs over SSH

`pip install -r requirements.txt` takes several minutes and the SSH session drops before it
finishes, killing the install half-done — which is how the venv ended up with 193 packages and no
`pyyaml`. Detach it instead:

```bash
nohup bash -c 'venv/bin/python -m pip install -r requirements.txt > /tmp/pip.log 2>&1; \
  echo $? > /tmp/pip.done' >/dev/null 2>&1 &

# then poll
cat /tmp/pip.done 2>/dev/null && tail -5 /tmp/pip.log
```

`screen` or `tmux` work equally well.

---

## Current configuration

```bash
FORECAST_ENGINE_TYPE=production
OPTIMIZER_TYPE=production
RAG_COPILOT_TYPE=production
CORS_ORIGINS=*
```

Keep the real `.env` free of inline comments; see the trap above.

| Engine | Serves |
|---|---|
| Forecast | LightGBM from `prediction_bundle/models_v2` for solar (24, 48 and 72 h); power curve for wind |
| Optimiser | Per-block expected-penalty search, optional battery recourse |
| Copilot | BM25 retrieval over the CERC corpus, Groq with Gemini fallback, guardrail |

Verified live on 13 September 2026:

- `/health`: `serving_synthetic_data: []`, 9 forecast models loaded
- `/rag/health`: 179 chunks, BM25 loaded, no stored embeddings, Groq and Gemini both usable
- `/plants`: 101 plants (80 solar, 21 wind)
- Schedule optimisation, GJ_SOLAR_A: ₹12,650 → ₹10,685, 15.5% lower than declaring P50
- Portfolio pooling, GJ_POOL_1: ₹53,543 → ₹39,849, 25.6% lower

Optimisation and pooling figures depend on the day's weather and change from day to day.
They were measured before PR #37 deployed; its quantile-weighting fix lowers expected-penalty
figures across the site, so re-measure afterwards.

### Rebuilding the copilot corpus

1. Add or replace PDFs in `regulations/` and update `sources.json`
2. `venv/bin/python scripts/build_index.py --truncate`
3. `venv/bin/python scripts/eval_retrieval.py --verbose` — recall@5 should stay at or above 0.70
4. `sudo systemctl restart renewable-api` — the BM25 index is built at startup

Production runs BM25-only. The 2.2 GB bge-m3 model is optional: it helps with questions that
share no vocabulary with the regulation text, and it cannot help with documents missing from the
corpus, which is where the current retrieval misses are.

### Running the daily pipeline

This VM has no scheduler. Trigger a run by hand:

```bash
curl -X POST https://57.159.24.68.nip.io/pipeline/run   -H "X-API-Key: $PIPELINE_API_KEY" -H 'content-type: application/json' -d '{}'
```

A systemd timer calling that endpoint at 02:30 UTC (08:00 IST) is the simplest way to schedule
it. On the AWS path the same call is made by EventBridge through a Lambda; see
`infra/aws/03_observability.sh`.

---

## Cost

Roughly ₹200–250/day for the `D4as_v4`. **Deallocate it after judging** — shutting it down from
inside the OS leaves it allocated and billing for compute; deallocating releases it (disks bill
either way):

```bash
az vm deallocate --resource-group <rg> --name Hackout
```

---

## CI/CD

The pipeline was originally written for AWS (ECR + EC2 + SSM). The deployment moved to Azure, so
`deploy.yml` was rewritten and the AWS steps were removed from `ci.yml` — they were failing on
every push to `main` at `Configure AWS credentials`, because the ARN rendered as
`arn:aws:iam:::role/...` with an empty account id and no AWS secrets were ever set.

| Workflow | Trigger | Does |
|---|---|---|
| `ci` → `test` | every push | ruff + pytest, ~2 min |
| `ci` → `image` | every push | docker build + trivy scan. Publishes nothing — the live service runs from a git checkout under systemd, not from a registry image. Kept green because that image is the offline `docker compose up` fallback. |
| `deploy` | `ci` green on `main`, or manual | SSH → `git reset --hard origin/main` → conditional `pip install` → `systemctl restart` → health gate → **automatic rollback on failure** |

### Secrets to configure

Repository → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `AZURE_SSH_PRIVATE_KEY` | full contents of `Hackout_key.pem`, including the BEGIN/END lines |
| `AZURE_VM_HOST` | `57.159.24.68` |
| `AZURE_VM_USER` | `azureuser` |
| `AZURE_PUBLIC_URL` | `https://57.159.24.68.nip.io` |

Until `AZURE_SSH_PRIVATE_KEY` and `AZURE_VM_HOST` are set, the deploy job **skips cleanly with a
notice** rather than failing. A fork or a fresh clone therefore does not get a red build for
infrastructure it cannot reach.

### What the deploy job does that a bare `git pull` does not

- **Pins the host key** with `ssh-keyscan` instead of `StrictHostKeyChecking=no`, so the deploy
  cannot be silently redirected to another host.
- **Skips `pip install` when `requirements.txt` is unchanged**, which is most deploys — a full
  install every time adds minutes for nothing.
- **Gates on health** for up to two minutes, and on failure **resets to the previous commit,
  restarts, and prints the failing release's journal**. A deploy that leaves the API down is worse
  than one that never happened.
- **Prints `serving_synthetic_data`** afterwards, so which engines a release served is recorded in
  the run log rather than reconstructed later.

### Manual deploy

```bash
gh workflow run deploy.yml
```

### The AWS scripts are retained

`infra/aws/` and `infra/terraform/` still describe a complete, working AWS path — security-group
chain, OIDC with a pinned `sub` claim, EventBridge, CloudWatch alarms. They are the alternative
deployment, not dead code, and the design decisions in them still stand. `docs/deployment.md`
documents that path; this file documents the one that is live.
