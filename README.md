# ⚡ AI-Powered Renewable Generation Forecasting Platform
### DSM-Aware Decision & Scheduling Platform

> **Predict → Quantify Risk → Price in ₹ → Optimise → Act → Explain with Citations**

---

## 🎯 What This Project Does

Solar and wind power output fluctuates constantly with weather, time of day, and season — making it difficult for grid operators and utilities to plan capacity, schedule backup power, or avoid costly deviation penalties.

This platform solves that problem end-to-end:

1. **Ingests** live weather forecasts (Open-Meteo) and historical generation data (NASA POWER)
2. **Forecasts** solar/wind output for the next 24–72 hours as a full probability distribution (P05 → P95) using LightGBM quantile regression + Amazon Chronos-2
3. **Prices the uncertainty** into expected ₹ DSM penalties using CERC 2024/2026 rules for renewable generators
4. **Optimises** the day-ahead schedule to minimise expected ₹ penalty using grid-search + battery LP
5. **Flags grid actions** — curtailment, storage dispatch, reserve activation — with ₹ impact estimates
6. **Explains** every decision in plain language, citing exact CERC clauses via a RAG-powered AI copilot

---

## 🏆 What Makes This Unique

| Layer | What We Do |
|---|---|
| Probabilistic Forecast | P05–P95 uncertainty bands, not just a point estimate |
| ₹ Penalty Pricing | CERC 2024/2026 seller-side DSM with X-trajectory |
| Schedule Optimisation | Min-₹ schedule + 96-block battery LP |
| Portfolio Pooling | 30–65% penalty reduction by pooling plants |
| Regulatory AI Copilot | CERC clause citations — LLM never invents ₹ numbers |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Physics | pvlib |
| ML Forecasting | LightGBM (quantile), Chronos-2-small |
| Optimisation | NumPy grid search + PuLP/CBC |
| Backend | FastAPI + Python 3.11 |
| Database | PostgreSQL 15 + pgvector |
| RAG | bge-m3 + BM25 + LangGraph + LiteLLM (Groq / Gemini) |
| Frontend | React 18 + Recharts + Leaflet + Tailwind CSS |
| Cloud | AWS EC2, RDS, S3, CloudFront, EventBridge, ECR |
| CI/CD | GitHub Actions (OIDC) |

---

## 🚀 Quick Start

```bash
cp .env.example .env
docker compose up          # Postgres + pgvector + API on :8000
```

The copilot starts in `mock` mode so a fresh clone needs no API keys. For the real
thing, set `RAG_COPILOT_TYPE=production` and `GROQ_API_KEY`, install
`requirements-ml.txt`, and build the regulation index:

```bash
python scripts/build_index.py --dry-run     # validate the chunker first
python scripts/build_index.py --truncate
python scripts/eval_retrieval.py --verbose  # recall@5 target: >= 0.7
```

Full instructions: [docs/deployment.md](./docs/deployment.md).

---

## 📁 Repository Structure

```
├── backend/              # FastAPI app, ML modules, DSM engine, API routes
├── frontend/             # React dashboard
├── colab_notebooks/      # Offline training notebooks (Google Colab T4)
├── config/               # DSM YAML rules (2024, 2026, 2031), plant configs
├── regulations/          # CERC DSM PDFs for RAG ingestion
├── tests/                # Unit tests
├── infra/                # Terraform (AWS) + Docker configs
├── docs/                 # Planning, architecture, team execution plans
└── .github/workflows/    # CI/CD pipelines
```

---

## 📄 Planning Documents

All planning documents are in [`/docs`](./docs/):

| Document | Description |
|---|---|
| [Project Understanding](./docs/project_understanding.md) | Problem analysis, reference repos, regulatory context |
| [Implementation Plan](./docs/implementation_plan.md) | Full end-to-end technical blueprint |
| [Team Division Plan](./docs/team_plan.md) | 4-member roles, dependency map, handoff schedule |
| [Team Execution Plans](./docs/team_execution_plans_nocode.md) | Detailed per-member task breakdown |
| [ML Engineer Deep Dive](./docs/member1_ml_engineer.md) | ML engineering guide for forecasting + DSM engine |
| [Infra + RAG Deep Dive](./docs/member4_infra_rag_engineer.md) | Docker, AWS, CI/CD and the regulatory RAG copilot (Member 4) |
| [RAG API Contract](./docs/api_rag_contract.md) | Frozen `/rag/query` request/response shape |
| [Deployment](./docs/deployment.md) | Local stack, AWS provisioning, CI/CD, cost control |
| [Runbook](./docs/runbook.md) | Demo-day pre-flight, failover drill, failure modes |

---

## ⚖️ Regulatory Disclosures

- DSM parameters follow the **2026 CERC order**, under legal challenge in the Delhi High Court. Both rule sets available via UI slider.
- All ₹ values computed by our **deterministic DSM engine**, never by the LLM.
- Wind power curve fitted on CARE Wind Farm A (CC BY-SA 4.0), extrapolated to Gujarat sites.

---

Built for **Hackout 2026** — National Level Hackathon.
