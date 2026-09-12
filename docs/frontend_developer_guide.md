# Frontend Developer Guide

> **Status:** Sprints 0–9 complete. All 8 planned components and 5 pages are built and
> wired to the live FastAPI backend. Sprint 10 (polish, responsive, demo hardening) is
> the only remaining work.
>
> This document is the single authoritative reference for anyone working on `frontend/`.

---

## 1. Stack and tooling

| Layer | Technology | Notes |
|---|---|---|
| UI framework | **React 19** | Concurrent features enabled |
| Language | **TypeScript 5.7** | Strict mode; every component is typed |
| Build tool | **Vite 6** | `npm run dev` → `:5173`; HMR on save |
| Styling | **Tailwind CSS v4** | `@theme` tokens in `index.css` — no `tailwind.config.js` |
| Routing | **react-router 7** | Nested layout routes |
| HTTP client | **axios 1** | One `apiClient` instance in `api/client.ts` |
| Charts | **ApexCharts 4** (`react-apexcharts`) | **The only chart library. Never add a second.** |
| Map | **react-leaflet 5** | `leaflet` 1.9 peer |
| Fonts | **Inter** (Google Fonts CDN) | Loaded in `index.css` |
| Metadata | **react-helmet-async** | `<PageMeta>` wrapper |

> **Base template**: TailAdmin free React (MIT). Pruned deps (FullCalendar, DnD, Dropzone,
> Swiper, Flatpickr, jvectormap) must NOT be re-added.

---

## 2. Design tokens

All colour, radius, gap, and font values live **exclusively** in `frontend/src/index.css`
under `@theme`. Never write a raw hex value anywhere else.

| Token | Value | Meaning |
|---|---|---|
| `--color-bg` | `#0B0F0E` | Page background |
| `--color-surface` | `#131917` | Card / panel |
| `--color-surface-2` | `#1B2321` | Active nav, hover |
| `--color-border` | `#2A3330` | All borders |
| `--color-text` | `#E9EFEC` | Primary text |
| `--color-text-muted` | `#93A29C` | Sub-labels |
| `--color-accent` | `#CFF245` | Lime accent |
| `--color-accent-dim` | `#A8C936` | Hover on accent |
| `--color-on-accent` | `#0B0F0E` | Text on lime bg |
| `--color-pen-0..pen-5` | `#1B2321` to `#FF5C7A` | DSM penalty ramp |
| `--color-dev-under` | `#6EA8FF` | Under-deviation |
| `--color-dev-zero` | `#2A3330` | Zero deviation |
| `--color-dev-over` | `#FF9F45` | Over-deviation / mock badge |
| `--color-solar` | `#F5B33C` | Solar plant identity |
| `--color-wind` | `#5EC8C8` | Wind plant identity |
| `--radius-card` | `16px` | Panel corners |
| `--radius-control` | `10px` | Buttons, inputs |
| `--radius-chip` | `8px` | Tags, badges |
| `--gap-grid` | `12px` | Grid gutter |
| `--gap-section` | `24px` | Between panels |

---

## 3. Directory layout

```
frontend/src/
  api/
    client.ts        Axios instance — baseURL = VITE_API_BASE_URL || localhost:8000
    endpoints.ts     One typed fn per endpoint, all take optional AbortSignal
  types/
    api.ts           TypeScript interfaces mirroring backend Pydantic schemas exactly
  hooks/             One hook per resource (see §5)
  mocks/             JSON fixtures for VITE_USE_MOCKS=true
  lib/
    format.ts        inr(), inrCompact(), blockToIST() — tested
    apexTheme.ts     Shared ApexCharts defaults
  context/
    DashboardContext.tsx   plantId + ruleYear global state
    SidebarContext.tsx     Sidebar expand/collapse state
  layout/
    AppLayout.tsx    Root layout: Sidebar + Backdrop + main area
    AppHeader.tsx    Mobile hamburger + top bar
    AppSidebar.tsx   Collapsible sidebar with 5 nav links
    Backdrop.tsx     Mobile sidebar overlay
    DashboardShell.tsx  PlantSelector + RuleYearControl + <Outlet>
  components/
    common/          PageMeta.tsx, ScrollToTop.tsx
    layout/          PlantSelector.tsx, RuleYearControl.tsx
    tiles/           StatTile.tsx, BriefingCard.tsx
    charts/          ForecastFanChart.tsx, RiskHeatmap.tsx, ScheduleComparison.tsx
    actions/         ActionCards.tsx
    pooling/         PoolingToggle.tsx
    map/             PlantMap.tsx
    copilot/         RAGCopilot.tsx
  pages/
    Home.tsx         /home — landing page (no sidebar)
    Overview.tsx     /     — main dashboard
    Forecast.tsx     /forecast
    Risk.tsx         /risk
    Actions.tsx      /actions
    Copilot.tsx      /copilot
```

---

## 4. Routing

All dashboard routes nest under `<AppLayout>` → `<DashboardShell>`.
`DashboardShell` mounts `<DashboardProvider>` and renders the global plant/rule controls.

```
/home         Home          Landing hero (outside DashboardProvider)
/             Overview      Main dashboard
/forecast     Forecast      Fan chart
/risk         Risk          Heatmap + schedule comparison
/actions      Actions       Action cards + pooling toggle
/copilot      Copilot       RAG chat panel
```

---

## 5. API layer

### Architecture rule (strictly enforced)

```
api/client.ts  →  api/endpoints.ts  →  hooks/use*.ts  →  pages / components
```

**Components and pages never import axios.** They only consume hook return values.

### Hooks reference

| Hook | Endpoint | Purpose |
|---|---|---|
| `useDashboard(plantId, date?)` | `GET /dashboard/{plant_id}` | Primary fetch for every page |
| `usePlants()` | `GET /plants` | Plant list for PlantSelector |
| `useForecast(plantId, date?)` | `GET /forecast` | Stand-alone forecast |
| `useDSM(params)` | `POST /dsm` | Re-price on rule-year slider change |
| `useOptimize(params)` | `POST /optimize` | Savings, optimised schedule, action cards |
| `usePooling(params)` | `POST /pooling` | Pooling benefit |
| `useRAG()` | `POST /rag/query` | Chat query in RAGCopilot |
| `useHealth()` | `GET /health`, `GET /rag/health` | Liveness + engine badge |
| `useSidebar()` | — | Sidebar state |
| `useModal()` | — | Modal open/close |
| `useGoBack()` | — | Browser history back with `/` fallback |

All HTTP hooks return `{ data, loading, error, refetch }` and use `AbortController`
to cancel superseded in-flight requests on rapid re-renders.

### Mock mode

Set `VITE_USE_MOCKS=true` in `frontend/.env` or `.env.local`. The hook interface is
identical; `DashboardShell` renders an orange mock badge when active.

| File | Shape | Notes |
|---|---|---|
| `mocks/dashboard.json` | `DashboardResponse` | Seeded for `GJ_SOLAR_A` |
| `mocks/optimize.json` | `OptimizeResponse` | |
| `mocks/plants.json` | `PlantsResponse` | All 4 Gujarat plants |
| `mocks/rag.json` | `RAGQueryResponse` | Example CERC query |

---

## 6. Global state

### DashboardContext

`plantId` (default `"GJ_SOLAR_A"`) and `ruleYear` (default `2026`) are the two controls
that drive every panel re-fetch. Changing either re-fires all hooks that depend on them.

```tsx
const { plantId, setPlantId, ruleYear, setRuleYear } = useDashboardContext();
```

Mounted inside `DashboardShell` — `/home` is intentionally outside it.

---

## 7. Utility functions

**`lib/format.ts`**

| Function | Example |
|---|---|
| `inr(1234567)` | `"₹12,34,567"` |
| `inrCompact(1234567)` | `"₹12.3L"` |
| `blockToIST(5)` | `"01:00"` |

`block_no` is **1-indexed** (1–96). Block 1 = 00:00–00:15 IST.
Never do `array[block_no]` — use `.find(b => b.block_no === n)`.

Tests: `npm run test` (Vitest, `lib/format.test.ts`).

---

## 8. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend base URL |
| `VITE_USE_MOCKS` | `false` | `"true"` → fixtures only, no HTTP calls |

Copy `frontend/.env.example` → `frontend/.env`. Never commit `.env`.

---

## 9. Local development

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173

npm run build        # tsc + Vite production bundle
npm run lint         # ESLint
npm run test         # Vitest
npx tsc -b           # type-check only
```

---

## 10. Component reference

### ForecastFanChart
**Props:** `blocks: BlockForecast[], optimisedSchedule?: number[], avcMw: number`
- Three nested `rangeArea` series: P05–P95 (lightest), P10–P90, P25–P75
- P50 solid line on top; optimised schedule as dashed stepline
- X-axis in IST via `blockToIST()`, hourly ticks; two-hourly below 768 px
- Transparent bg; grid in `--color-border`

### RiskHeatmap
**Props:** `blocks: BlockDSMResult[]`
- 96 cells — 4 rows × 24 hour columns (ApexCharts heatmap)
- Colour ramp: `pen-0` (safe) → `pen-5` (worst), brighter = costlier
- Tooltip: block number, IST time, penalty INR, deviation %
- Below 640 px: horizontal scroll strip

### ScheduleComparison
**Props:** `naiveTotalInr, optimisedTotalInr, savingsInr, savingsPct: number`
- Grouped bars: naive P50 vs optimised
- Savings as a separate lime tile — no mental subtraction needed

### ActionCards
**Props:** `actions: ActionCard[]`
- Types: `"curtailment"` | `"reserve_flag"` only — never invent a third
- Explicit empty state for `actions.length === 0`

### PlantMap
**Props:** `selectedPlantId: string, onSelectPlant: (id: string) => void`
- react-leaflet centred at `23.2N, 71.0E` (Gujarat)
- Pin colour: solar amber / wind teal; size by `avc_mw`
- CartoDB DarkMatter tile layer (not light OSM)
- Click → `onSelectPlant(id)` → updates `DashboardContext.plantId`

### RAGCopilot
**Props:** `plantId: string, ruleYear: number`
- Sends `{ question, plant_id, rule_year, context }` to `POST /rag/query`
- `meta.guardrail` **always** displayed when not `"pass"` — non-negotiable
- Citation badges: `clause`, `doc`, `page`; link out when `url` is set
- 502 → "Copilot unavailable" state; mock mode labelled on screen

### PoolingToggle
**Props:** `pooling: PoolingResponse | null, isPooled: boolean, onToggle: () => void`
- Toggle: individual vs pooled totals; per-plant allocation table when pooled
- `null` → "No pool membership" graceful state

### StatTile / BriefingCard
- All ₹ values passed as pre-formatted strings — no arithmetic inside tiles
- `tone="good"` renders tile in lime (used for savings)

---

## 11. Honesty rules (non-negotiable)

1. **₹ figures come from the DSM engine only** — never client-side arithmetic or copilot output.
2. **`meta.guardrail` must be displayed** when it is not `"pass"`.
3. **`serving_synthetic_data`** from `GET /health` must appear as a UI badge (Sprint 10 item).

---

## 12. Sprint 10 remaining work

| Item | Effort |
|---|---|
| `serving_synthetic_data` engine badge in header | 30 min |
| Responsive layout at 400 px — all routes | 2–3 h |
| Loading / error state audit on all pages | 1 h |
| `npx tsc -b` exits 0 | varies |
| `npm run lint` exits 0 | varies |
| `frontend/.env.production` with deployed API URL | 5 min |

Sprint 10 is **polish only** — no new features, components, or endpoints.

---

## 13. Dependency hygiene

Never add a dependency without Claude Code approval (dual-agent protocol).

**Runtime:** `react` · `react-dom` · `react-router` · `axios` · `apexcharts` ·
`react-apexcharts` · `leaflet` · `react-leaflet` · `@types/leaflet` ·
`react-helmet-async` · `clsx` · `tailwind-merge`

**Dev:** `vite` · `@vitejs/plugin-react` · `vite-plugin-svgr` · `typescript` ·
`tailwindcss` · `@tailwindcss/postcss` · `postcss` · `eslint` ·
`eslint-plugin-react-hooks` · `eslint-plugin-react-refresh` · `vitest`
