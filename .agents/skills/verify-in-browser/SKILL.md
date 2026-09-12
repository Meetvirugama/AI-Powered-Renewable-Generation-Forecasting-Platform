---
name: verify-in-browser
description: Use before claiming any UI work is done, working, or fixed. Requires actually loading the page in Chrome via the chrome-devtools MCP server and observing the result - console clean, data rendered, responsive at phone width - rather than asserting completion from the code alone.
---

# Verify in browser

Code that compiles is not code that works. In a two-agent workflow a false "done" is
expensive: the lead reviews something that was never run, and the defect surfaces during
the demo instead.

**Evidence before assertions. Always.**

## Procedure

1. Dev server running: `npm run dev` (Vite → `http://localhost:5173`).
2. Backend running: `uvicorn backend.main:app --reload` (→ `:8000`). If it is not up,
   say so — do not verify against mocks and report it as verified against the API.
3. Drive Chrome through the **`chrome-devtools`** MCP server:
   - `navigate_page` to the route under test
   - `list_console_messages` — **must be clean.** React key warnings and unhandled
     promise rejections count as failures, not noise.
   - `list_network_requests` — confirm the expected API call fired, returned 200, and
     that no request is 404ing silently.
   - `take_screenshot` — actually look at it. Overlapping text, a chart collapsed to
     zero height, and a permanent skeleton all compile perfectly.
   - `resize_page` to **400×800** and screenshot again.

## Done means

- [ ] Route loads, no console errors or warnings
- [ ] Real data rendered — not a skeleton, not zeroes, not `NaN` or `undefined`
- [ ] All 96 blocks present where a full day is expected
- [ ] ₹ values in Indian grouping (`₹12,34,567`) and non-zero where expected
- [ ] Loading, error and empty states each reachable and each correct
- [ ] No horizontal page scroll at 400px width
- [ ] Backend stopped → visible error state, not a white screen

## Reporting

State what you observed, not what you intended:

> Verified: `/dashboard/GJ_SOLAR_A` at 1440px and 400px. Console clean. `GET /dashboard`
> returned 200 in 340ms, 96 blocks. Fan chart, heatmap, 3 action cards rendered.
> Not verified: pooling toggle — `POST /pooling` returns 500 for `GJ_POOL_2`
> (single-plant pool). Screenshot attached.

If a check was skipped, name it as skipped. If something failed, quote the error text
exactly. Never write "should work" — either it was observed or it was not.
