---
name: visual-design-system
description: Use before writing any colour, font, spacing, radius, or shadow value anywhere in the frontend. Defines the dark renewable-grid palette, the strict colour-to-meaning mapping, typography, and density scale. Every visual value in the app comes from here.
---

# Visual design system

A grid-operations product, not a landing page. Dark control-room ground, one energetic
accent, and colours that each mean exactly one thing.

**Never hardcode a hex, px radius, or font size in a component.** Everything below is a
token in `src/index.css`. If you need a value that is not here, the value is wrong or
the system needs extending — raise it, do not improvise.

## Ground

Near-black, shifted very slightly green. It hints at the domain without turning the app
into a "green website", and it makes the amber and rose data colours read cleanly.

```
--bg          #0B0F0E    page ground
--surface     #131917    card
--surface-2   #1B2321    raised, hover, table stripe
--border      #2A3330    hairlines, chart grid, dividers
--text        #E9EFEC    primary
--text-muted  #93A29C    labels, axis ticks, secondary
```

## Colour means exactly one thing

The single most common failure in a dashboard like this is one hue carrying two
meanings. Each role below owns its hue outright.

### Brand + savings — lime `#CFF245`

```
--accent      #CFF245    primary CTA, active nav, savings figures, "optimised" series
--accent-dim  #A8C936    hover / pressed
--on-accent   #0B0F0E    text on a lime fill — always the ground, never white
```

Lime is the product's argument: **money saved.** It appears on savings, on the optimised
schedule series, and on primary actions. It **never** appears on a penalty, a loss, a
warning, or an asset type. A judge who sees the brand colour on a loss figure reads the
product as confused.

### Penalty magnitude — rose, sequential

Always ≥ 0, so it ramps rather than diverges. On a dark canvas "more" is **brighter**;
ramping toward dark hides the worst blocks in the background.

```
--pen-0  #1B2321   --pen-1  #402030   --pen-2  #6B2A44
--pen-3  #9C3355   --pen-4  #CE3C63   --pen-5  #FF5C7A
```

Rose rather than red: red reads as a binary alarm, and penalty is a continuous quantity.
Rose also stays clear of solar gold.

### Deviation % — blue ↔ orange, diverging

Under- and over-injection are genuinely opposite, so the scale has a true zero centre.
Blue↔orange is the standard colourblind-safe diverging pair; red↔green is not.

```
--dev-under   #6EA8FF        --dev-zero  #2A3330        --dev-over  #FF9F45
```

### Asset identity — map pins and plant chips only

```
--solar  #F5B33C      --wind  #5EC8C8
```

Never used for a data value. Identity only, so a user can tell a wind farm from a solar
plant at a glance.

### State

```
--ok #CFF245 · --warn #FF9F45 · --danger #FF5C7A · --info #6EA8FF
```

Reuse the data hues rather than adding new ones. Never encode meaning by colour alone —
every colour chip needs a number or a text label beside it.

## Typography

**Inter**, one family. Tight tracking on headings, generous on small caps labels.

```
--font-sans  'Inter', system-ui, sans-serif

display  30px / 1.15 / 600 / -0.03em    page title
h2       20px / 1.25 / 600 / -0.02em    section
h3       15px / 1.35 / 600 / -0.01em    card title
body     14px / 1.5  / 400
small    12px / 1.4  / 400              axis ticks, captions
label    11px / 1.3  / 500 / +0.06em / uppercase
metric   28px / 1.1  / 600 / -0.02em    the big ₹ number on a stat tile
```

**Every number uses `font-variant-numeric: tabular-nums`.** Without it, ₹ figures in a
table jitter column-to-column and the whole thing looks amateur. Set it globally on
`.metric`, table cells, and axis labels.

## Density and shape

sendit is an airy landing page — `py-20`, `rounded-3xl`. A dashboard is not. Keep the
soft-rounded character, tighten everything else.

```
--r-card    16px      cards, panels, modals
--r-control 10px      buttons, inputs, chips, tabs
--r-chip     8px      badges, pills

--pad-card    20px
--gap-grid    12px
--gap-section 24px
row height    40px    table rows and list items
```

Shadows: almost none. On a dark ground, elevation comes from `--surface-2` and a
`--border` hairline, not from a blur. One shadow token exists for overlays only:

```
--shadow-overlay  0 16px 48px rgba(0,0,0,.55)
```

## Paste-ready tokens

```css
@theme {
  --color-bg: #0B0F0E;          --color-surface: #131917;
  --color-surface-2: #1B2321;   --color-border: #2A3330;
  --color-text: #E9EFEC;        --color-text-muted: #93A29C;

  --color-accent: #CFF245;      --color-accent-dim: #A8C936;
  --color-on-accent: #0B0F0E;

  --color-pen-0: #1B2321; --color-pen-1: #402030; --color-pen-2: #6B2A44;
  --color-pen-3: #9C3355; --color-pen-4: #CE3C63; --color-pen-5: #FF5C7A;

  --color-dev-under: #6EA8FF; --color-dev-zero: #2A3330; --color-dev-over: #FF9F45;
  --color-solar: #F5B33C;     --color-wind: #5EC8C8;

  --radius-card: 16px; --radius-control: 10px; --radius-chip: 8px;
  --font-sans: 'Inter', system-ui, sans-serif;
}
```

## Rules

- Contrast: body text ≥ 4.5:1, large text and axis labels ≥ 3:1 against their own
  surface. Check `--text-muted` on `--surface-2` specifically — it is the tightest pair.
- Text on a lime fill is `--on-accent` (the ground colour). White on lime fails contrast
  and looks broken.
- No gradient on a data surface. Gradients are decoration; they distort magnitude
  judgement in a chart.
- Focus ring is `--accent` at 2px with a 2px offset, on every interactive element. Do not
  remove outlines.
- Light mode is out of scope. If a light theme is ever added, it is a second full token
  set, not per-component overrides.
