---
name: component-sourcing
description: Use before building or styling any UI component. Defines the search order across the shadcn, Magic UI, React Bits, and Aceternity MCP registries, when to hand-roll instead, and how to keep the four libraries from fighting each other.
---

# Component sourcing

Six MCP servers are wired into this repo. Search them before writing a component by
hand — hand-rolled animation is where hackathon time disappears.

## Search order

Work down this list. Stop at the first level that answers the need.

1. **`shadcn`** — structural primitives: Button, Card, Dialog, Tabs, Select, Slider,
   Table, Sheet, Skeleton, Sonner. **This is the base layer.** Magic UI and Aceternity
   both assume shadcn conventions (`cn()` util, CSS variables, Radix under the hood).
   Install shadcn first; everything else layers on top.
2. **`magicui`** — polished motion effects with real substance: `bento-grid`,
   `animated-list`, `number-ticker`, `animated-circular-progress-bar`, `marquee`,
   `animated-beam`. 78 registry items. Best signal-to-noise of the three effect libs.
3. **`reactbits`** — categories: Animations, Backgrounds, Text Animations, Components,
   Buttons, Forms, Loaders. Reach for backgrounds and text treatments.
4. **`aceternityui`** — large hero/marketing-scale effects. Use sparingly; most of it is
   landing-page scale and will overwhelm a dense operations dashboard.
5. **Hand-roll** — only when nothing above fits, or the component is data-bound and
   project-specific (the fan chart, the 96-block heatmap). Say so explicitly when you do.

`context7` is not a component source — it is for **API accuracy**. Query it before
writing Recharts, react-leaflet, Tailwind, or Framer Motion code so props and options
are real rather than plausible.

## Rules that prevent breakage

- **One animation engine.** These libraries mostly use `motion` / `framer-motion`.
  Do not add a second animation runtime alongside it.
- **Install through the shadcn CLI where a registry supports it** so files land in
  `src/components/ui/` with the project's import alias, instead of pasted blobs.
- **Read the component before installing it.** Registry code executes in your app;
  check it does not phone home, inline a remote script, or pull an unpinned CDN asset.
- **No new top-level dependency without the lead's sign-off** (see
  [dual-agent-protocol](../dual-agent-protocol/SKILL.md)). Four component libraries
  already overlap heavily; a fifth is almost never the answer.
- **Strip the marketing.** Registry components ship with demo copy, gradients and
  hero spacing. This is a grid-operations dashboard: dense, calm, legible at a glance.
  Keep the mechanism, drop the flourish.

## Fit for this project

| Need | Source |
|---|---|
| Plant selector, tabs, dialogs, sliders | shadcn |
| ₹ savings figure that counts up | magicui `number-ticker` |
| Action-card feed | magicui `animated-list` |
| Dashboard tile layout | magicui `bento-grid` |
| Loading states while API resolves | shadcn `skeleton` |
| Forecast fan chart, risk heatmap | hand-roll on Recharts — no registry has these |

## Licensing

shadcn, Magic UI, React Bits and Aceternity are permissively licensed for use in your
own product. Two of the four MCP servers (`reactbits`, `aceternityui`) are third-party
wrappers, not published by the library authors — the components they return are still
the real upstream components, but verify anything surprising against the library's own
docs site before shipping it.
