# AGENTS.md

Shared context for every AI agent on this repo (Antigravity, Claude Code, Gemini CLI).
Antigravity reads this natively; `CLAUDE.md` imports it. **Edit this file, not the copies.**

---

## Project

AI-Powered Renewable Generation Forecasting Platform — DSM-aware decision & scheduling
platform for Indian grid operators. Hackout 2026.

Chain: forecast P05–P95 → price ₹ CERC DSM penalty → optimise day-ahead schedule →
emit grid action cards → explain with cited CERC clauses.

Repo: `github.com/Meetvirugama/AI-Powered-Renewable-Generation-Forecasting-Platform`

## Layout

```
backend/      FastAPI app — DONE (mocked ML behind a swappable factory)
config/       DSM rule YAMLs (2024/2026/2031), plants.yaml
docs/         planning docs; docs/openapi.json is the API contract
              docs/frontend_developer_guide.md — as-built frontend reference
tests/        pytest suite
frontend/     React 19 dashboard — Sprints 0–9 COMPLETE, Sprint 10 (polish) remaining
              All 8 components, 5 pages, 11 hooks wired to the live API.
```

## Team ownership

| Member | Name | Scope |
|---|---|---|
| 1 | **Meet Virugama** | ML forecasting + DSM engine math |
| 2 | **Gaurav Rathod** | Backend API, DB, pipeline |
| 3 | **Shane Christian** | **Frontend (this workstream)** |
| 4 | **Madhav Thesiya** | Infra, Docker, AWS, RAG copilot |

Agents working here are supporting Member 3. **Do not edit `backend/`, `config/`, or
`docs/` without explicit instruction** — those belong to other members and
concurrent edits cause merge conflicts during the hackathon.

## Frontend stack — decided, do not relitigate

Base template: **TailAdmin free React** (MIT) — `github.com/TailAdmin/free-react-tailwind-admin-dashboard`.
Adopted as-is rather than fought.

```
React 19 · TypeScript 5.7 · Vite 6 · Tailwind CSS v4 · react-router 7
ApexCharts 4 (react-apexcharts)   ← the only chart library
react-leaflet                     ← added; TailAdmin's jvectormap cannot do lat/lon pins
```

Theme: **dark-first with a lime accent**, taken from `sendit.zip`
(`--bg #0d0e11`, `--surface #1a1c22`, `--accent #cff245`, Inter, heavy rounding).
Tokens and colour scales: `.agents/skills/dsm-chart-conventions/SKILL.md`.

Prune on install — TailAdmin ships `@fullcalendar/*`, `react-dnd`, `react-dropzone`,
`swiper`, `flatpickr` and `@react-jvectormap/*`. None are used here.

Planned components: `PlantMap`, `ForecastFanChart`, `RiskHeatmap`, `ScheduleComparison`,
`RegulationSlider`, `PoolingToggle`, `ActionCards`, `RAGCopilot`.
Pages: `Dashboard`, `PlantDetail`, `Backtest`.

Sprint plan: `docs/frontend_implementation_plan.md`.

## Backend API contract

Base URL dev: `http://localhost:8000`. CORS already allows `:5173` and `:3000`.
Full schema: `docs/openapi.json`.

| Method | Path | Returns |
|---|---|---|
| GET | `/plants` | `{plants[], total}` — id, name, type, lat, lon, avc_mw, pool_id |
| GET | `/plants/{id}` | single plant |
| GET | `/forecast?plant_id&date` | `{plant_id, date, model_name, blocks[96]}` |
| POST | `/dsm` | per-block ₹ penalty + `x_value`, `rule_version` |
| POST | `/optimize` | naive vs optimised ₹, both schedules, battery, action cards |
| POST | `/pooling` | individual vs pooled ₹ + per-plant allocations |
| GET | `/dashboard/{plant_id}?date` | **all of the above in one response** |
| POST | `/rag/query` | `{answer, citations[], engine_values, meta}` |
| POST | `/pipeline/run` | needs `X-API-Key` header — not a frontend concern |
| GET | `/health` | liveness |

`GET /dashboard/{plant_id}` is the primary frontend hook — one fetch fills the whole
dashboard. Use the granular endpoints only for slider/toggle re-fetches.

### Shapes worth memorising

`BlockForecast`: `block_no` (1–96), `valid_time`, `ist_time`, `p05 p10 p25 p50 p75 p90 p95`
`BlockDSMResult`: `block_no`, `expected_penalty_inr`, `p50_penalty_inr`, `schedule_mw`, `deviation_pct_at_p50`
`ActionCard`: `type` (`curtailment` | `reserve_flag`), `block_no`, `mw`, `reason`, `inr_impact`
`Citation`: `clause`, `page`, `doc`, `url`, `section`, `snippet`
`RAGMeta.guardrail`: `pass` | `numbers_stripped` | `fallback_template`

A day is **96 blocks of 15 minutes**. Block 1 = 00:00 IST.

### Seed data

`GJ_SOLAR_A` 50 MW · `GJ_SOLAR_B` 75 MW · `GJ_WIND_C` 40 MW — pool `GJ_POOL_1`
`GJ_SOLAR_D` 30 MW — pool `GJ_POOL_2`
All in Gujarat. Map should centre roughly lat 23.2, lon 71.0.

Regulation slider years: **2024 / 2026 / 2031** (`rule_year` param).
X-trajectory runs 1.00 → 0.00 across 2026–2031.

## Running the backend

```bash
pip install -r requirements.txt      # not yet installed on this machine
uvicorn backend.main:app --reload    # → http://localhost:8000, docs at /docs
```

Runs fully offline against mocks — no Postgres needed for frontend work.
Mock/production selected by env: `FORECAST_ENGINE_TYPE`, `OPTIMIZER_TYPE`, `RAG_COPILOT_TYPE`.

## Known issues

- `backend/modules/forecast/mock_engine.py` reads `plant['plant_id']` / `plant['asset_type']`
  but callers pass `id` / `type`. Every plant therefore gets the same RNG seed and a solar
  profile — the wind plant renders as a solar bell curve. Backend owner's fix; do not
  patch it unilaterally. Design charts so this does not mislead a demo.
- ₹ figures must always come from the DSM engine response. The RAG copilot explains
  numbers, it never produces them. Never render an LLM-generated rupee value.

## Deny rules

- Never edit `backend/`, `config/`, `docs/`, `alembic.ini`, or DB migrations without being asked.
- Never commit or push unless explicitly told to.
- Never commit `.env`, API keys, or the CloudFront/production URL.
- Never add a frontend dependency not already in `package.json` without saying so first.
- Never fabricate forecast or penalty data in committed code — mock fixtures go in an
  obviously-named `src/mocks/` and must be swappable for live calls.

## Agent split

**Claude Code is lead. Antigravity is executor.** Full protocol, handoff format and
file-ownership rules: `.agents/skills/dual-agent-protocol/SKILL.md` — read it first.

Short version: Claude Code decides architecture, dependencies, contract interpretation
and library choice, and approves every merge. Antigravity builds to a written spec and
owns browser verification. When Antigravity hits ambiguity or would step outside its
assigned files, it stops and surfaces the question rather than deciding.

## Skills

Canonical skills live in `.agents/skills/<name>/SKILL.md` — Antigravity's native path,
and an emerging cross-tool standard. `.claude/skills/` holds generated pointer stubs so
Claude Code sees the same set. **Edit the `.agents/` copy only.**

| Skill | Read it when |
|---|---|
| `dual-agent-protocol` | start of any task, and before editing any file |
| `component-sourcing` | before building or styling any UI component |
| `dsm-chart-conventions` | before any chart, ₹ figure, time axis, or colour scale |
| `backend-api-integration` | before wiring a component to the API or adding a type |
| `verify-in-browser` | before claiming anything is done, working, or fixed |

## MCP servers

Configured in `.mcp.json` (Claude Code) and `.agents/mcp_config.json` (Antigravity).
Both files are identical — change both, or neither.

| Server | Publisher | Purpose |
|---|---|---|
| `shadcn` | official | base primitives + registry install via the shadcn CLI |
| `magicui` | official | motion components (78 registry items) |
| `reactbits` | third-party | animations, backgrounds, text effects, loaders |
| `aceternityui` | third-party | large-scale visual effects — use sparingly |
| `context7` | official (Upstash) | version-accurate library docs; query before writing Recharts / Leaflet / Tailwind code |
| `chrome-devtools` | official (Google) | drive real Chrome — console, network, screenshots, perf |

`chrome-devtools` runs with `--isolated`, so it launches a throwaway Chrome profile and
never touches the developer's logged-in browsing session. Do not remove that flag.

`reactbits` and `aceternityui` are community wrappers, not published by the library
authors. The components they return are the real upstream components; verify anything
surprising against the library's own docs before shipping it.
