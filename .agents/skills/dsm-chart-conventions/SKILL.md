---
name: dsm-chart-conventions
description: Use before writing any chart, tile, ₹ figure, time axis, or colour value in this dashboard. Covers the dark lime theme tokens, Indian rupee formatting, the 96-block IST axis, and ApexCharts construction for the fan chart, risk heatmap and comparison bars.
---

# DSM dashboard chart conventions

Grid operators read this under time pressure; judges read it on a projector.
Dense, calm, unambiguous. Every rule below exists because the obvious default is wrong
for this data.

**Chart library is ApexCharts (`react-apexcharts`). One library, no exceptions.**
TailAdmin ships it, and its `rangeArea` type is purpose-built for our fan chart. Do not
introduce Recharts, Chart.js, D3-for-charting, or Victory alongside it.

## Tokens come from the design system

All colour, type, radius and spacing values live in
`.agents/skills/visual-design-system/SKILL.md`. **Read it before this file.** Never
hardcode a hex in a chart config — reference the CSS variable.

## Colour scales — three, and they are not interchangeable

**1. Penalty magnitude (₹, always ≥ 0) → `--pen-0` … `--pen-5`**, the rose sequential
ramp. On a dark canvas "more" is brighter, not darker.

**2. Deviation % (signed) → `--dev-under` / `--dev-zero` / `--dev-over`**, diverging with
a true zero centre.

**3. Savings and the optimised series → `--accent` lime.** Nothing else uses lime.

**4. Asset identity (map pins, plant chips only) → `--solar` / `--wind`.** Never a data
value.

Never encode meaning by colour alone. Every heatmap cell needs a tooltip value; every
action card needs a text label (`Curtailment`, `Reserve flag`) beside its colour chip.

## Rupee formatting

India groups digits as **₹12,34,567**, not ₹1,234,567. The US default in front of
Indian utility judges is an instant credibility hit.

```ts
export const inr = (v: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0,
  }).format(v);                                    // ₹12,34,567

export const inrCompact = (v: number) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', notation: 'compact',
    maximumFractionDigits: 1,
  }).format(v);                                    // ₹12.3L · ₹1.2Cr
```

Axis ticks and stat tiles → `inrCompact`. Tooltips and totals → `inr`. Never both in
one chart. Savings always carry sign and percentage: `−₹2.4L (−31%)`.

## Time axis

A day is **96 blocks of 15 minutes**; block 1 starts 00:00 IST.

```ts
const blockToIST = (n: number) => {
  const m = (n - 1) * 15;
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
};
```

The API returns `ist_time` per block — **prefer it over recomputing.**

- Never render 96 tick labels. Every 4th block (hourly) at desktop, every 8th below 768px.
- Axis is always IST. `valid_time` is UTC — never show it to a user.
- Solar lives in roughly blocks 25–72. **Do not auto-zoom away the night.** The flat zero
  is information; hiding it makes solar look like it runs 24 hours.

## Component construction

**ForecastFanChart** — ApexCharts `rangeArea`, three band series stacked palest→darkest
(P05–P95, P10–P90, P25–P75), plus a solid `line` series for P50 on top. The optimised
schedule overlays as a dashed line with `curve: 'stepline'` — a schedule is piecewise
constant per block, not a smooth curve. Use a single combined chart with
`chart.type: 'rangeArea'` and mixed series, not stacked separate charts.

**RiskHeatmap** — ApexCharts `heatmap`, 96 cells as 4 rows × 24 columns (hour columns,
15-min rows). Rose ramp (`--pen-0`…`--pen-5`) via `plotOptions.heatmap.colorScale.ranges`. Tooltip
shows block number, IST time, ₹ penalty, deviation %. Below 640px switch to a horizontal
scroll strip rather than shrinking cells to unreadable dots.

**ScheduleComparison** — grouped `bar`, naive-P50 ₹ vs optimised ₹, with the delta
rendered as its own stat tile in lime. The delta is the product's whole argument; never
make a judge subtract two bars by eye.

**Stat tiles** — Magic UI `number-ticker` for the headline ₹ figures. Animate once on
load, not on every re-render, and never on a value the user is trying to read mid-change.

**Zero states** — a plant with zero penalty is a *success*, not an empty chart. Render
the axes and say "No deviation penalty in this window". Never a blank panel, never a
spinner that never resolves.

## ApexCharts + dark theme gotchas

- Set `theme.mode: 'dark'` and `chart.background: 'transparent'`; otherwise Apex paints
  a white rectangle behind every chart.
- Grid and axis borders must use `--border`, not Apex defaults, or they glow.
- `chart.animations` on a 96-point series is slow on projector hardware. Cap at 300ms or
  disable for the heatmap.
- Apex renders to a fixed pixel height. Wrap every chart so it reflows, and re-render on
  container resize — a chart collapsed to 0px height still compiles.

## Honesty rules

- **Never render a ₹ value the DSM engine did not return.** No client-side penalty
  arithmetic, no interpolation between blocks, nothing lifted from the RAG copilot's
  prose. The engine is the only source of ₹ — this is the project's core credibility
  claim. Check `meta.guardrail` on RAG responses and surface it when it is not `pass`.
- **Label mock data on screen.** An unlabelled mock in a demo is how a judge concludes
  the backend does not exist.
- Every chart needs loading (skeleton at the chart's real dimensions, so layout does not
  jump), error (with the actual failure), and empty states.
