# Demo script — 3 minutes

Plant on screen: **Gujarat Solar A** (50 MW), date 2026-06-15, CERC rule year 2026,
X-trajectory value 0.85. All figures below are the real mock values shipped in
`frontend/src/mocks/dashboard.json`, `optimize.json` and `rag.json` — quote these, do
not round or invent.

---

### 0:00–0:20 — The problem

**Say:** "Solar and wind output swings with cloud cover and wind speed. In India, a
generator submits a day-ahead schedule to the grid operator, and under CERC's Deviation
Settlement Mechanism, if actual generation misses that schedule, the generator pays a
penalty in rupees — not a warning, a real cash charge, block by block, every 15 minutes.
This is a money problem before it's a weather problem."

**Click:** land on the Dashboard, let the header (plant name, date, CERC 2026, X=0.85)
sit for a beat.

### 0:20–0:50 — The forecast

**Say:** "Here's the forecast fan for today. We don't predict one number — we predict a
distribution, P05 to P95. A point forecast tells you what's likely; it hides how wrong
you could be. When being wrong costs rupees, the width of that band is the thing you
actually need to see and price."

**Click:** point at the Forecast fan chart panel — the three nested bands, the P50 line,
the dashed optimised schedule step-line running through it.

### 0:50–1:30 — The money

**Say:** "Expected penalty for today, from the DSM engine: ₹22,583. Optimising the
schedule instead of submitting the naive median forecast saves ₹10,146 — 31% off.
That's the whole product in one sentence: the optimiser doesn't pick the schedule
closest to the P50 forecast, it picks the schedule that minimises *expected* rupee
penalty across the full P05–P95 distribution. Those are different schedules, and the gap
between them is real money."

**Click:** point at the stat tiles (Expected penalty, Saved by optimising), then the
naive-vs-optimised bar panel.

### 1:30–2:00 — The risk heatmap

**Say:** "96 blocks, 15 minutes each, one full day. Brighter means costlier. An operator
can see in one glance which hours of the day carry the deviation risk — here, midday,
when solar output is highest and hardest to pin down exactly."

**Click:** point at the Risk heatmap panel.

### 2:00–2:30 — Portfolio pooling

**Say:** "Gujarat Solar A sits in a pool with two other plants. Pooled together,
deviations partly cancel out — one plant over-injects while another under-injects. For
this pool, pooling individual penalties of ₹81,750 down to ₹51,912 saves
₹29,839 — a 36.5% reduction, just from netting exposure across plants."

**Click:** point at the Portfolio pooling panel and its per-plant allocation chips.

### 2:30–3:00 — The regulatory copilot (land this last)

**Say:** "Every rupee figure on this screen comes from a deterministic CERC DSM engine —
not the language model. The copilot's job is only to explain and cite the exact clause —
Regulation 7.2, Regulation 5.1 — in plain language. There's a server-side guardrail that
strips any number the LLM tries to state that the engine didn't produce. That's the
credibility claim: you can trust every rupee number on this screen because a human-
readable regulation, not a language model, produced it."

**Click:** open the copilot panel, ask about a block's penalty, point at the citation
badges and the guardrail status.

---

## Numbers to quote

| Metric | Value | Shown in |
|---|---|---|
| Expected penalty (today) | ₹22,583 | Stat tile "Expected penalty" |
| Naive submission cost | ₹32,729 | Sub-label under the same tile, and the schedule comparison bar |
| Saved by optimising | ₹10,146 (31.0%) | Stat tile "Saved by optimising", schedule comparison delta |
| Worst single block | ₹635, block 31 (07:30 IST) | Stat tile "Worst block" |
| Blocks over the ±10% solar band | 0 / 96 | Stat tile "Blocks over band" |
| Action cards issued | 4 (2 curtailment, 2 reserve flag) | Recommended grid actions panel |
| Largest single action | Curtailment, block 52, 6.15 MW, ₹475 at risk | Action card |
| Pool | GJ_POOL_1 (Solar A, Solar B, Wind C) | Pooling panel |
| Individual → pooled penalty | ₹81,750 → ₹51,912 | Pooling panel |
| Pooled saving | ₹29,839 (36.5%) | Pooling panel |
| Copilot demo query (block 54) | ₹386 expected penalty, 2.2% deviation — inside tolerance band, guardrail: pass | Copilot panel |

Every figure above is read directly from src/mocks/{dashboard,optimize,rag}.json — the
stat tiles, schedule-comparison bars and copilot panel all draw from the same
optimise/dashboard fixtures, so nothing here should contradict what is on screen.


## If a judge asks

**"Why probabilistic instead of a point forecast?"**
Because the penalty function is convex and asymmetric around the schedule you commit to.
A point estimate throws away exactly the information — the spread — that the optimiser
needs to pick the schedule with the lowest *expected* cost. Two forecasts with the same
median can have very different optimal schedules if their spreads differ.

**"How do you know the LLM isn't inventing rupee values?"**
Every response from `/rag/query` carries a `meta.guardrail` field. If the model states a
number the DSM engine didn't supply, the guardrail strips it and the field flips to
`numbers_stripped`, which we surface on screen rather than hide. The only source of truth
for a ₹ figure anywhere in this app is the deterministic engine response.

**"What happens when the 2026 CERC rules change?"**
The X-trajectory already models that: it runs from 1.00 in 2026 down to 0.00 by 2031 as
the transitional relief phases out. The rule-year selector lets an operator compare
2024, 2026, and 2031 rule sets side by side against the same forecast.

**"Is this real regulation?"**
Yes. CERC's Deviation Settlement Mechanism is a real, currently-in-force framework for
Indian grid balancing. The 2026 order amending it is under legal challenge in the Delhi
High Court, which is why the product supports both the 2024 and 2026 rule sets rather
than assuming the newer one survives unchanged.

**"What's mocked versus real?"**
The API contract, the DSM math shapes, and the UI are all real. The forecast numbers
currently come from a mock forecast engine behind the same interface the real ML models
will use — see Known gaps below.

## Known gaps — say these before a judge finds them

- The real ML models (LightGBM quantile regression, Chronos-2) live in
  `prediction_bundle/`, but the forecast and optimisation endpoints are still served by
  a mock engine behind the same API contract. Swapping in the real models is a backend
  config change, not a frontend one.
- The mock forecast engine has a known keying bug (`plant_id`/`asset_type` vs the
  `id`/`type` fields callers actually pass), so every plant is seeded identically right
  now and the wind plant renders the same solar-shaped bell curve as the solar plants.
  This is a backend fixture issue, already flagged to that owner, not a frontend defect.
- Only the main Dashboard route is fully wired end to end today. The plant map and the
  RAG copilot panel exist as built components but aren't dropped into the live dashboard
  yet, and the planned PlantDetail and Backtest pages are still stubs. Scoped, known, and
  next in line — not a surprise if a judge clicks around outside the happy path.
