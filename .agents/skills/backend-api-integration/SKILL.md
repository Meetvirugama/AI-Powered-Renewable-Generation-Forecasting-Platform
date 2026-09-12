---
name: backend-api-integration
description: Use before wiring any component to the FastAPI backend, adding an API call, or defining a data type. Gives the fixed layering (client → types → hook → component), the endpoint contract, and the rules that keep mock and live data swappable.
---

# Backend API integration

Backend is complete and runs offline against mocks. No Postgres needed for frontend work.

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload      # http://localhost:8000  · interactive docs at /docs
```

CORS already permits `localhost:5173` and `localhost:3000`. No backend change is
needed to develop against it — and per [dual-agent-protocol](../dual-agent-protocol/SKILL.md),
`backend/` is off limits anyway.

## Layering — never skip a layer

```
src/api/client.js      axios instance, baseURL from import.meta.env.VITE_API_BASE_URL
src/api/endpoints.js   one thin function per endpoint, no React
src/types/             JSDoc typedefs (or .ts) mirroring the response shapes
src/hooks/             one hook per resource — owns loading / error / refetch
src/components/        presentational; receives data as props
```

A component must never call `axios` directly. When a component both fetches and renders,
swapping mock for live data means editing every component instead of one hook.

## Endpoints

| Method | Path | Use for |
|---|---|---|
| GET | `/plants` | plant selector, map pins |
| GET | `/forecast?plant_id&date` | fan chart alone |
| POST | `/dsm` | regulation-year slider re-fetch |
| POST | `/optimize` | schedule comparison, action cards |
| POST | `/pooling` | pooling toggle |
| **GET** | **`/dashboard/{plant_id}?date`** | **initial page load — everything at once** |
| POST | `/rag/query` | copilot chat |
| GET | `/health` | connection banner |

**Load the dashboard with one `GET /dashboard/{plant_id}`.** Use the granular endpoints
only for interactions that change one slice — the year slider re-calls `POST /dsm`, the
pooling toggle re-calls `POST /pooling`. Do not fan out seven parallel calls on mount.

`POST /pipeline/run` needs an `X-API-Key` header. It is an ops endpoint. Never call it
from the browser and never put that key in frontend code.

## Response shapes

```
BlockForecast   block_no 1..96 · valid_time (UTC) · ist_time · p05 p10 p25 p50 p75 p90 p95
BlockDSMResult  block_no · expected_penalty_inr · p50_penalty_inr · schedule_mw · deviation_pct_at_p50
ActionCard      type ("curtailment" | "reserve_flag") · block_no · mw · reason · inr_impact
OptimizeResponse  naive_total_inr · optimised_total_inr · savings_inr · savings_pct
                  optimised_schedule[96] · naive_schedule[96] · battery_dispatch[] · action_cards[]
PoolingResponse   individual_total_inr · pooled_total_inr · savings_inr · savings_pct · allocations[]
RAGQueryResponse  answer · citations[{clause,page,doc,url,section,snippet}] · engine_values · meta
```

`meta.guardrail` is one of `pass` | `numbers_stripped` | `fallback_template`. When it is
not `pass`, show that in the UI — it means the copilot's answer was altered because it
produced a figure the DSM engine did not.

Arrays are **always 96 long** and **1-indexed by `block_no`** while JS arrays are
0-indexed. Index with `blocks.find(b => b.block_no === n)` or subtract 1 deliberately
and comment it. Off-by-one here silently shifts the entire day by 15 minutes.

## Rules

- `baseURL` comes from `VITE_API_BASE_URL`, never a hardcoded string. Prod is a
  CloudFront domain supplied later by Member 4.
- Mock fixtures live in `src/mocks/` with obvious names, behind the same hook interface
  as live calls, toggled by env — not by commented-out code.
- Handle the backend being down. It is a hackathon; it will be down. A dead API should
  produce a visible banner, not a white screen.
- `date` is `YYYY-MM-DD`. Omit it and the backend defaults to today (UTC).
- Plant ids are strings: `GJ_SOLAR_A`, `GJ_SOLAR_B`, `GJ_WIND_C`, `GJ_SOLAR_D`.
- Never render a ₹ figure the engine did not return — see
  [dsm-chart-conventions](../dsm-chart-conventions/SKILL.md).

## Known backend defect

`backend/modules/forecast/mock_engine.py` reads `plant['plant_id']` / `plant['asset_type']`
but callers pass `id` / `type`. Consequence: every plant is seeded identically and always
gets the solar profile, so **`GJ_WIND_C` renders as a solar bell curve**. Do not patch it —
it is Member 1/2's file. Design around it, and flag it before any demo where a judge
might notice the wind farm peaking at noon.
