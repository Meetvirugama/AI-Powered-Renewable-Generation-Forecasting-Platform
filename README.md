# VidyutVaani

**Renewable generation forecasting and penalty optimisation for Indian power plants.**

[![ci](https://github.com/Meetvirugama/AI-Powered-Renewable-Generation-Forecasting-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/Meetvirugama/AI-Powered-Renewable-Generation-Forecasting-Platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)
![React](https://img.shields.io/badge/react-19-149ECA)

Built for Hackout 2026.

## Overview

Solar and wind plants in India must submit a day-ahead schedule of how much power they will
produce in every 15-minute block. If actual output misses the schedule, the plant pays a penalty
under CERC's Deviation Settlement Mechanism (DSM).

VidyutVaani forecasts output, calculates the penalty in rupees, and recommends the schedule that
keeps that penalty as low as possible.

## Features

- **Probabilistic forecast**: a low, median and high estimate for each block, 24 to 72 hours ahead
- **Penalty calculation**: the actual CERC rules for 2024, 2026 and 2031
- **Schedule optimisation**: picks the schedule with the lowest expected penalty
- **Portfolio pooling**: shows the savings from settling several plants together
- **AI assistant**: explains results with citations to the regulation, and never invents numbers

## How it works

```mermaid
flowchart LR
    A["Weather forecast"] --> B["Generation forecast"]
    B --> C["Penalty in ₹"]
    C --> D["Optimised schedule"]
    D --> E["Recommended actions"]
    C --> F["AI assistant"]
```

## Results

Measured on the live system, 13 September 2026:

| Metric | Result |
|---|---|
| Forecast accuracy vs. baseline | 21.5% to 32.5% better |
| Penalty saved by optimising one plant | 15.5% |
| Penalty saved by pooling three plants | 25.6% |
| Plants covered | 101 in Gujarat |

Savings vary with the weather. The solar model is trained on one plant's data over 30 days, so
accuracy on other plants is not yet verified.

## Tech stack

| Area | Technology |
|---|---|
| Backend | Python, FastAPI, PostgreSQL |
| Machine learning | LightGBM |
| AI assistant | LangGraph, LiteLLM (Groq, Gemini) |
| Frontend | React, TypeScript, Tailwind CSS, ApexCharts |
| Hosting | Azure, Vercel, GitHub Actions |

## Getting started

```bash
# Backend
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn backend.main:app --reload     # http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

The default settings use sample data, so no database or API keys are needed.

## Documentation

- [System architecture](docs/system_architecture.md)
- [Deployment](docs/deployment_azure.md)
- [ML pipeline](docs/ml_pipeline.md)
- [Runbook](docs/runbook.md)
- [Roadmap](docs/roadmap.md)

## Team

| Name | Role |
|---|---|
| Meet Virugama | Machine learning |
| Gaurav Rathod | Backend |
| Shane Christian | Frontend |
| Madhav Thesiya | Infrastructure and AI assistant |
