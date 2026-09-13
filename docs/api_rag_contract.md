# RAG Copilot API Contract

**Status:** frozen. **Owner:** Member 4. **Consumers:** Member 3 (dashboard), Member 2 (pipeline step 8).

## Quick Reference

| | |
|---|---|
| **Endpoint** | `POST /rag/query` |
| **Readiness check** | `GET /rag/health` |
| **Request field** | `context` (alias: `engine_context`) |
| **₹ figures** | Always render from `engine_values`, never from `answer` prose |
| **Guardrail values** | `pass` / `numbers_stripped` / `fallback_template` |
| **LLM primary** | `groq/openai/gpt-oss-120b` |
| **LLM fallback** | `gemini/gemini-3.6-flash` |
| **API keys** | Several per provider via `GROQ_API_KEYS` / `GEMINI_API_KEYS`; rotated on quota errors |
| **Total LLM outage** | Returns `200` with `guardrail: "fallback_template"` — not a 502 |

---


Field names in this document do not change. Member 3 builds against it without a running
backend, so a rename here is a broken frontend there. New *optional* fields may be added;
existing fields are never renamed, retyped, or removed.

The live schema is `backend/schemas/rag.py` and the generated OpenAPI is at `/docs`. If this
file and the code ever disagree, the code is right and this file is a bug.

---

## `POST /rag/query`

### Request

```jsonc
{
  "question": "Why was block 52 penalised?",   // required, 3-1000 chars
  "plant_id": "GJ_SOLAR_A",                    // optional
  "block_no": 52,                              // optional, 1-288
  "date": "2026-09-12",                        // optional, ISO date
  "rule_year": 2026,                           // optional, 2024-2031

  // Optional. DSM engine output for the block in question, injected by the
  // caller. Authoritative: the copilot explains these numbers and is forbidden
  // from recomputing or inventing them.
  "context": {
    "penalty_inr": 18240.0,
    "deviation_pct": -14.2,
    "schedule_mw": 42.5,
    "actual_mw": 36.4,
    "x_value": 0.7,
    "frequency_band": "49.95-50.05",
    "rule_version": "CERC_DSM_2026"
  }
}
```

`context` is a free-form object. Any numeric value placed in it becomes a number the copilot
is permitted to state; anything else it emits is stripped. Send the whole DSM engine result
rather than a curated subset — an omitted field is a figure the answer cannot mention.

> **Alias:** `engine_context` is accepted as a synonym for `context`, because the Member 4
> execution plan drafted the field under that name before the schema was written. Both
> populate the same field. `context` is canonical; prefer it in new code.

### Response `200`

```jsonc
{
  "answer": "Block 52 shows an under-injection against the declared schedule ...",

  // Only citations matching a chunk that was actually retrieved. A citation the
  // model produced from memory is dropped before the response is built, because
  // a plausible link to a clause we never read is worse than no link at all.
  "citations": [
    {
      "doc": "CERC_DSM_Regulations_2024",
      "clause": "Regulation 7(2)(b)",
      "section": "Deviation charges for sellers",
      "page": 14,
      "url": "https://cercind.gov.in/...",
      "snippet": "Where the actual injection deviates ..."
    }
  ],

  // Echoed verbatim from the request's `context`. Never re-derived.
  "engine_values": {
    "penalty_inr": 18240.0,
    "deviation_pct": -14.2
  },

  "meta": {
    "llm_model": "groq/openai/gpt-oss-120b",
    "cached": false,
    "latency_ms": 1840,
    "retrieved_chunks": 5,
    "guardrail": "pass"
  }
}
```

### `meta.guardrail`

| Value | Meaning | Suggested UI treatment |
|---|---|---|
| `pass` | Every number in `answer` traces to the engine payload or a retrieved clause. | Render normally. |
| `numbers_stripped` | The model produced a figure the engine did not. It was replaced with `[value not computed by the engine]` before the response left the server. | Badge the answer. This is the guardrail working, not an error. |
| `fallback_template` | Every LLM provider was unreachable. `answer` is a deterministic template built from `engine_values`. | Badge as "AI explainer unavailable". The figures are still correct. |

### Errors

```jsonc
// 502 - the copilot could not be reached at all
{ "detail": "copilot_unavailable: <reason>" }
```

A total LLM outage is **not** a 502. It returns `200` with `guardrail: "fallback_template"`,
because the engine's numbers are still available and still useful. A 502 means the request
never reached a working copilot.

---

## Rendering rules for the frontend

These are what make "the LLM never computes money" true rather than merely claimed.

1. **Render every ₹ figure from `engine_values`, never by parsing `answer`.** Treat `answer`
   as prose. This is why `engine_values` is a verbatim echo of the request: the number on
   screen and the number the DSM engine computed are the same object, not two renderings that
   have to be kept in agreement.
2. **Render citation badges from `citations`.** Each entry has a real `url`; make the badge
   open it. A judge will click one.
3. **Show `meta.guardrail` when it is not `pass`.** A stripped answer is a feature to
   demonstrate, not a failure to hide.
4. **Pass `rule_year` whenever the regulation slider is not at its default.** Without it the
   copilot may cite a later amendment while the slider reads 2024, and the demo visibly
   contradicts itself.

---

## `GET /rag/health`

Operational readiness, not liveness. Check this before a demo, not during one. Production on
13 September 2026:

```jsonc
{
  "copilot_type": "production",
  "chunks": 179,
  "embed_models": [],                    // no stored embeddings: BM25-only retrieval
  "live_embed_model": "BAAI/bge-m3",
  "bm25_loaded": true,
  "cache": { "entries": 2, "ttl_s": 3600, "hits": 0, "misses": 2, "hit_rate": 0.0 },
  "llm": {
    "primary": "groq/openai/gpt-oss-120b",
    "fallback": "gemini/gemini-3.6-flash",
    "usable": ["groq/openai/gpt-oss-120b", "gemini/gemini-3.6-flash"],
    "redundancy": "dual_provider",
    "keys_per_model": { "groq/openai/gpt-oss-120b": 7, "gemini/gemini-3.6-flash": 5 }
  }
}
```

What to look for:

- `chunks: 0` — the corpus was never loaded. Run `scripts/build_index.py`.
- `warning` present — the corpus was embedded with a different model than this process queries
  with. Retrieval results are meaningless until the index is rebuilt. This failure is silent
  everywhere else: it returns confident, well-formatted, wrong citations.
- `usable: []` — no LLM provider has an API key. Every answer will be `fallback_template`.
- `embed_models: []` — no stored embeddings, so retrieval runs on BM25 alone. That is the current
  production configuration, not a fault.
- `bm25_loaded: false` — sparse retrieval is off; the hybrid is running on dense alone.

---

## Notes on two names that differ from the Member 4 execution plan

Recorded here so nobody "fixes" them back.

- **`meta.llm_model`, not `meta.model`.** Pydantic v2 reserves the `model_` prefix for its own
  attributes, and a field named `model` emits a protected-namespace warning. `llm_model` is
  the shipped name.
- **`context`, not `engine_context`.** The schema was written before the plan was; rather than
  rename a field Member 3 had already built against, `engine_context` is accepted as an alias.

---

## Python usage (pipeline briefings, not yet wired)

```python
from backend.modules.rag.copilot import generate_briefing

# Pre-generate the operator briefing during the nightly run. The dashboard must
# never wait on an LLM in a request path -- three generations is 6-10 seconds.
briefing = generate_briefing(
    session,
    plant_id="GJ_SOLAR_A",
    date="2026-09-12",
    dsm_summary={"penalty_inr": 18240.0, "deviation_pct": -14.2, "rule_year": 2026},
)
# -> {"plant_id", "date", "sections": [{"question", "answer", "citations", "guardrail"}], "generated_at"}
```
