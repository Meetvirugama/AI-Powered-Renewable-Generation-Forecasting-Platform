# Frontend Implementation Plan

Workstream: Member 3 (frontend), executed by the Antigravity agent, reviewed by Claude Code.
Chain of command and handoff format: `.agents/skills/dual-agent-protocol/SKILL.md`.

> **Build status as of PR #8 merge:** Sprints 0–9 scaffolded and committed to `frontend/`.
> All components exist; browser verification and Sprint 10 hardening remain.
> See `docs/roadmap.md` for the current completion picture.


---

## Decisions — settled, do not relitigate

| | Decision |
|---|---|
| Base template | **TailAdmin free React** (MIT), adopted as-is rather than fought |
| Stack | React 19 · TypeScript 5.7 · Vite 6 · Tailwind v4 · react-router 7 |
| Charts | **ApexCharts 4 only.** No Recharts, no Chart.js, no second library |
| Map | **react-leaflet** — added. TailAdmin's jvectormap cannot place lat/lon pins |
| Theme | Dark renewable-grid ground, lime accent. Tokens in `.agents/skills/visual-design-system/SKILL.md` |
| Light mode | Out of scope |

`sendit.zip` contributed the visual language — near-black ground, lime accent, Inter,
soft rounding. Its landing-page density (`py-20`, `rounded-3xl`) is **not** carried over;
this is a data-dense operations console.

## Prune on install

TailAdmin ships components this project never uses. Remove in Sprint 0, before any
feature work, or they become permanent:

```
@fullcalendar/*  react-dnd  react-dnd-html5-backend  react-dropzone
swiper  flatpickr  @react-jvectormap/core  @react-jvectormap/world
```

Keep: `apexcharts`, `react-apexcharts`, `clsx`, `tailwind-merge`, `react-router`,
`react-helmet-async`. Add: `react-leaflet`, `leaflet`, `axios`.

## Target structure

```
frontend/
  src/
    api/        client.ts · endpoints.ts        axios, one fn per endpoint, no React
    types/      api.ts                          mirrors backend response shapes
    hooks/      useDashboard · usePlants · useDSM · useOptimize · usePooling · useRAG
    mocks/      dashboard.json etc.             swappable behind the hooks, never inline
    lib/        format.ts (inr, blockToIST) · apexTheme.ts (shared chart defaults)
    components/
      layout/     Sidebar · Topbar · PlantSelector · DateControl · RuleYearControl
      tiles/      StatTile · BriefingCard
      charts/     ForecastFanChart · RiskHeatmap · ScheduleComparison
      actions/    ActionCards
      pooling/    PoolingToggle
      map/        PlantMap
      copilot/    RAGCopilot
    pages/      Dashboard · PlantDetail · Backtest
    index.css   @theme tokens — the only place hex values exist
```

## Sprint sequence

Each sprint is one Antigravity handoff. **Claude Code reviews before the next starts.**
Nothing is merged on the executor's own judgement.

| # | Sprint | Depends on | Ships | Status |
|---|---|---|---|---|
| 0 | Scaffold and theme | — | Dark themed TailAdmin shell running | ✅ Built |
| 1 | API layer | 0 | Typed client, hooks, mocks, health banner | ✅ Built |
| 2 | App shell and global controls | 1 | Sidebar, topbar, plant/date/rule-year selectors | ✅ Built |
| 3 | Stat tiles and briefing | 2 | First real rupee figures on screen | ✅ Built |
| 4 | Forecast fan chart | 3 | P05–P95 bands, P50, optimised step line | ✅ Built |
| 5 | Risk heatmap | 4 | 96-block penalty heatmap | ✅ Built |
| 6 | Schedule comparison and action cards | 5 | Naive vs optimised, action feed | ✅ Built |
| 7 | Regulation slider and pooling toggle | 6 | The two what-if interactions | ✅ Built |
| 8 | Plant map | 2 | Gujarat map, 4 pins, click to select | ✅ Built |
| 9 | RAG copilot | 2 | Chat panel with clause citations | ✅ Built |
| 10 | Pages, responsive, demo hardening | all | PlantDetail, Backtest, 400px, error states | ⏳ Remaining |

Sprints 8 and 9 depend only on Sprint 2, so they can run in parallel with 4–7.


---

## Sprint 0 — Scaffold and theme

```
TASK: Stand up frontend/ from TailAdmin React, prune unused deps, install design tokens.
OWNS: frontend/** (new)
CONTRACT: none
DONE WHEN: npm run dev serves the TailAdmin shell on :5173 in the dark lime theme;
           npx tsc -b exits 0; npm ls shows none of the pruned packages;
           index.css @theme carries every token from the design-system skill;
           Inter loads; no console errors.
DO NOT: build any project component, touch any API, or add a chart.
```

**Review focus:** tokens complete and spelled exactly as the skill defines them; no hex
outside `index.css`; pruned deps gone from `package.json` *and* the lockfile; Tailwind v4
`@theme` syntax, not a v3 `tailwind.config.js`.

## Sprint 1 — API layer

```
TASK: Typed API client, response types, resource hooks, mock fixtures, health banner.
OWNS: src/api/** src/types/** src/hooks/** src/mocks/** src/lib/format.ts
CONTRACT: all endpoints in AGENTS.md; GET /health and GET /rag/health for the banner.
DONE WHEN: every endpoint has a typed fn and a hook exposing {data,loading,error,refetch};
           VITE_API_BASE_URL drives baseURL; VITE_USE_MOCKS toggles fixtures behind the
           same hook interface; inr/inrCompact/blockToIST unit-tested against
           the strings 12,34,567 and 12.3L; hooks verified against a live uvicorn.
DO NOT: render anything. No component imports axios — ever.
```

**Review focus:** `block_no` is 1-indexed against 0-indexed arrays — the off-by-one that
silently shifts the whole day by 15 minutes. Types must mirror the backend exactly, not
loosely. Mocks sit behind the hook, never inside a component.

## Sprint 2 — App shell and global controls

```
TASK: Sidebar, topbar, and the three global controls that drive every panel.
OWNS: src/components/layout/** src/pages/Dashboard.tsx (shell only) src/App.tsx
CONTRACT: GET /plants
DONE WHEN: routes /, /plant/:id, /backtest resolve; PlantSelector lists the 4 seeded
           plants with solar/wind identity colour; date and rule-year (2024/2026/2031)
           controls hold state and are readable by child panels; backend-down shows the
           health banner rather than a white screen.
DO NOT: build charts or tiles. Panels are labelled placeholders this sprint.
```

**Review focus:** selector state lifted high enough that one change re-drives every panel;
rule-year options match the three shipped YAMLs, not invented years.

## Sprint 3 — Stat tiles and briefing

```
TASK: Headline row — expected penalty, savings, savings %, rule version and X value —
      plus the briefing card.
OWNS: src/components/tiles/**
CONTRACT: GET /dashboard/{plant_id}?date   (one call, not seven)
DONE WHEN: four tiles render live values in Indian digit grouping with tabular figures;
           savings tile is lime and carries both sign and percentage; briefing renders
           title, summary and risk_level; skeletons match final tile dimensions so layout
           does not jump; zero penalty renders as a success state, not an empty tile.
DO NOT: compute any rupee value client-side. Every figure comes from the response.
```

**Review focus:** the honesty rule. Any arithmetic on a rupee value is a reject.

## Sprint 4 — Forecast fan chart

```
TASK: ForecastFanChart — the product's signature visual.
OWNS: src/components/charts/ForecastFanChart.tsx src/lib/apexTheme.ts
CONTRACT: dashboard.forecast.blocks[96] and optimize.optimised_schedule
DONE WHEN: ApexCharts rangeArea renders three nested bands (P05-P95, P10-P90, P25-P75)
           palest outward, P50 as a solid line above them, optimised schedule as a
           dashed stepline; x axis in IST with hourly ticks on desktop and two-hourly
           under 768px; night blocks visible not cropped; transparent chart background;
           grid drawn in --border.
DO NOT: introduce a second chart library. Do not smooth the schedule line.
```

**Review focus:** band ordering and opacity — bands sit behind the line, not over it.
Apex painting a white rectangle behind a dark chart. Animation cost on 96 points.

## Sprint 5 — Risk heatmap

```
TASK: RiskHeatmap — 96 blocks of penalty at a glance.
OWNS: src/components/charts/RiskHeatmap.tsx
CONTRACT: dashboard.dsm_summary.blocks[96]
DONE WHEN: ApexCharts heatmap, 4 rows by 24 hour columns, rose --pen-0..--pen-5 ramp;
           tooltip shows block number, IST time, penalty and deviation %;
           under 640px becomes a horizontal scroll strip rather than shrunken dots;
           colour is never the only signal.
DO NOT: use a green-to-red scale. Do not invent colour stops outside the token ramp.
```

**Review focus:** ramp direction — brighter must mean worse on a dark ground.

## Sprint 6 — Schedule comparison and action cards

```
TASK: The savings argument, and the operator's to-do list.
OWNS: src/components/charts/ScheduleComparison.tsx src/components/actions/**
CONTRACT: optimize.naive_total_inr, optimised_total_inr, savings_inr, action_cards[]
DONE WHEN: grouped bars for naive-P50 versus optimised, with the delta as its own lime
           tile; action cards render type, block, mw, reason and impact with a text label
           beside every colour chip; an empty action list renders a real empty state;
           the headline figure animates once on load only.
DO NOT: make the user subtract two bars by eye to find the saving.
```

**Review focus:** `curtailment` and `reserve_flag` are the only two types the backend
emits — no invented third state.

## Sprint 7 — Regulation slider and pooling toggle

```
TASK: The two what-if interactions that prove the engine is live.
OWNS: src/components/layout/RuleYearControl.tsx src/components/pooling/**
CONTRACT: POST /dsm on year change; POST /pooling on toggle
DONE WHEN: changing rule year re-calls POST /dsm and re-renders heatmap and tiles with a
           visibly different x_value; pooling toggle switches individual versus pooled
           totals and shows savings % plus per-plant allocations; both show in-flight
           state and survive rapid toggling without a race.
DO NOT: refetch the whole dashboard for a single-slice change.
```

**Review focus:** request races on rapid toggle — a stale response overwriting a fresh
one. This is the most likely real bug in the entire build.

## Sprint 8 — Plant map

```
TASK: PlantMap — Gujarat, four plants, click to select.
OWNS: src/components/map/**
CONTRACT: GET /plants
DONE WHEN: react-leaflet centred near 23.2N 71.0E; pins coloured --solar or --wind and
           sized by avc_mw; clicking a pin selects that plant across the dashboard;
           basemap tiles are dark, not default light OSM inside a dark app.
DO NOT: use jvectormap. Do not ship a light basemap.
```

**Review focus:** Leaflet CSS import and explicit container height — the two omissions
that render a blank grey box.

## Sprint 9 — RAG copilot

```
TASK: RAGCopilot chat panel with clause citations.
OWNS: src/components/copilot/**
CONTRACT: POST /rag/query — send plant_id, block_no, rule_year and the engine's own
          numbers as context. GET /rag/health for readiness.
DONE WHEN: a question renders an answer plus citation badges (clause, doc, page) that
           link out when url is present; meta.guardrail is surfaced whenever it is not
           'pass'; a 502 renders a copilot-unavailable state; mock copilot mode is
           labelled on screen.
DO NOT: render any rupee figure produced by the copilot. The engine is the only source.
```

**Review focus:** the guardrail display. `numbers_stripped` means the model produced a
figure the engine did not; hiding that undermines the project's central claim.

## Sprint 10 — Pages, responsive, demo hardening

```
TASK: PlantDetail, Backtest, and making the whole thing survive a live demo.
OWNS: src/pages/** plus targeted fixes anywhere
DONE WHEN: every route works at 1440px and 400px with no horizontal scroll;
           loading, error and empty states reachable and correct on every panel;
           backend stopped produces graceful degradation everywhere, never a white
           screen; console clean on every route; npx tsc -b and npm run lint exit 0.
DO NOT: add features. This sprint only removes defects.
```

**Review focus:** the `verify-in-browser` checklist, run for real on every route.

---

## Risks

| Risk | Handling |
|---|---|
| **Backtest page has no API.** `backtest_metrics` exists as a table; no endpoint exposes it. | Decide in Sprint 2 — either drop the route, or ship it clearly labelled as mock. Do not fake it silently. |
| **Mock forecast bug.** `mock_engine.py` reads `plant_id`/`asset_type` but callers pass `id`/`type`, so every plant is seeded identically and `GJ_WIND_C` renders as a solar bell curve. | Not ours to patch. Flag before any demo; do not design a chart that makes it conspicuous. |
| **Real ML not wired.** `prediction_bundle/` holds models but `forecast/` and `optimize/` are still mock-only. | Frontend is unaffected — the contract is identical either way. Do not wait on it. |
| **`docs/openapi.json` is stale** — it predates `GET /rag/health`. | Treat AGENTS.md as the contract; regenerate from a running app if a discrepancy appears. |
| Tailwind v4 and React 19 against the component MCPs | Verified compatible — shadcn and Magic UI both ship v4 and React 19 support. |
| Two agents editing the same file | File ownership is declared per sprint above. `git status` before every edit. |
