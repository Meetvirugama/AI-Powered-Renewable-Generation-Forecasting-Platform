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
FORECAST_ENGINE_TYPE=mock          # models rejected by the physics gate
OPTIMIZER_TYPE=production          # real grid-search optimiser
RAG_COPILOT_TYPE=mock              # no corpus loaded yet
CORS_ORIGINS=*
```

Verified live on this deployment:

- Schedule optimisation: **₹5,025.71 saved, 25.0%** vs declaring P50
- Portfolio pooling: **₹86,427 → ₹62,515, 27.67%**
- 13 endpoints serving, 202 MB resident of 16 GB

### To switch the copilot on

1. Put the CERC/IEGC PDFs in `regulations/` and fill in `sources.json`
2. Add `GROQ_API_KEY` to `.env` (free at console.groq.com)
3. `venv/bin/python scripts/build_index.py --truncate`
4. Set `RAG_COPILOT_TYPE=production` and restart

The 2.2 GB embedding model is optional — BM25-only retrieval works without it, at the cost of
missing questions that do not share vocabulary with the regulation text.

---

## Cost

Roughly ₹200–250/day for the `D4as_v4`. **Deallocate it after judging** — a stopped VM still bills
for its disk, a deallocated one does not:

```bash
az vm deallocate --resource-group <rg> --name Hackout
```
