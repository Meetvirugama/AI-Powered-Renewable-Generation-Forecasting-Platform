"""Post-generation enforcement of the invariant: the LLM never originates a number.

A prompt instruction is a request, not a guarantee. This module enforces it in
code, after generation, so the claim is structurally true rather than
aspirational: every numeric token in the answer must trace back either to the
ENGINE_RESULT payload the DSM engine produced, or to a regulation extract that
was actually retrieved. Anything else is neutralised and the response is labelled
`numbers_stripped` so the UI can badge it.

Currency figures get no benefit of the doubt. A bare "52" can be a block number;
"Rs 25,000" can only be money, and money that the engine did not compute does not
leave this server.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("renewable_platform")

# Optional currency marker, then the number itself in group("num").
#
# The grouped-digits branch requires at least one comma. With `*` it would also
# match a bare "18240" -- and because alternation is leftmost-first, it would
# match only the first three digits of it ("182"), silently redacting a figure
# the engine really did produce.
NUM = re.compile(
    r"(?<![\w.])(?P<cur>₹\s*|Rs\.?\s*|INR\s*)?"
    r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
)
CITE = re.compile(r"\[([^\]|]+)\|([^\]|]+)\|\s*p\.?\s*(\d+)\s*\]", re.I)

REDACTION = "[value not computed by the engine]"

# Block numbers (1-288), small ordinals and calendar years are structural, not
# claims about money, so they do not need to trace to the engine.
_SAFE_SMALL = {str(i) for i in range(0, 289)} | {str(y) for y in range(2000, 2051)}


def _canon(tok: str) -> str:
    """Normalise a numeric token so 18,240 / 18240.0 / 18240.00 all compare equal."""
    tok = tok.replace(",", "").lstrip("+")
    if "." in tok:
        tok = tok.rstrip("0").rstrip(".")
    return tok or "0"


def _engine_numbers(engine: dict) -> set[str]:
    allowed: set[str] = set()
    for value in (engine or {}).values():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        magnitude = abs(value)
        for form in (f"{value}", f"{magnitude}", f"{magnitude:.1f}", f"{magnitude:.2f}", f"{int(magnitude)}"):
            allowed.add(_canon(form))
    return allowed


def _retrieved_numbers(retrieved: list | None) -> set[str]:
    allowed: set[str] = set()
    for chunk in retrieved or []:
        text = getattr(chunk, "chunk_text", "") or ""
        for m in NUM.finditer(text):
            allowed.add(_canon(m.group("num")))
    return allowed


def enforce(answer: str, engine: dict, retrieved: list | None = None) -> tuple[str, str]:
    """Strip untraceable numbers from `answer`.

    Returns (safe_answer, status) where status is 'pass' or 'numbers_stripped'.
    """
    if not answer:
        return answer, "pass"

    traceable = _engine_numbers(engine) | _retrieved_numbers(retrieved)
    stripped: list[str] = []

    def repl(m: re.Match) -> str:
        token = _canon(m.group("num"))
        is_currency = bool(m.group("cur"))
        if token in traceable:
            return m.group(0)
        # A bare small integer is a block/year/ordinal; a rupee figure never is.
        if not is_currency and token in _SAFE_SMALL:
            return m.group(0)
        stripped.append(m.group(0).strip())
        return REDACTION

    safe = NUM.sub(repl, answer)
    if stripped:
        logger.warning("guardrail stripped untraceable numbers: %s", stripped)
        return safe, "numbers_stripped"
    return safe, "pass"


def _citation_key(doc: str, clause: str) -> tuple[str, str]:
    return (doc or "").lower().strip(), (clause or "").lower().strip()


def validate_citations(answer: str, retrieved: list) -> list[dict]:
    """Keep only citations that correspond to a chunk that was actually retrieved.

    A citation the model produced from memory is dropped outright: a plausible
    citation pointing at a clause we never read is worse than no citation, because
    a judge will click it.
    """
    retrieved = retrieved or []
    by_clause = {_citation_key(r.doc_name, r.clause): r for r in retrieved}
    by_doc_page = {((r.doc_name or "").lower().strip(), r.page_no): r for r in retrieved}

    out: list[dict] = []
    seen: set[int] = set()
    for doc, clause, page in CITE.findall(answer or ""):
        match = by_clause.get(_citation_key(doc, clause))
        if match is None:
            # The model rendered the clause label slightly differently; fall back
            # to doc + page, which is still an extract we genuinely retrieved.
            try:
                match = by_doc_page.get(((doc or "").lower().strip(), int(page)))
            except (TypeError, ValueError):
                match = None
        if match is not None and match.chunk_id not in seen:
            seen.add(match.chunk_id)
            out.append(match.as_citation())

    if not out:
        # The model forgot to cite, or invented every citation. Attach the top
        # retrieved extracts so the answer is still checkable against a source.
        out = [r.as_citation() for r in retrieved[:3]]
    return out


def deterministic_fallback(question: str, engine: dict, retrieved: list | None = None) -> str:
    """Answer used when every LLM provider is down. No model, no risk, still useful.

    The engine numbers are the part that matters to an operator, and they are
    available without an LLM. This is why a total provider outage degrades the
    demo instead of ending it.
    """
    parts: list[str] = []
    deviation = (engine or {}).get("deviation_pct")
    penalty = (engine or {}).get("penalty_inr")

    if deviation is not None:
        direction = "under" if deviation < 0 else "over"
        parts.append(
            f"The block deviates {deviation}% from the declared schedule ({direction}-injection)."
        )
    if penalty is not None:
        parts.append(f"The deviation charge computed by the DSM engine is ₹{penalty:,.0f}.")
    if retrieved:
        top = retrieved[0]
        parts.append(f"Applicable provision: {top.clause} of {top.doc_name} (p.{top.page_no}).")
    if not parts:
        parts.append(
            "No engine result was supplied for this question, so no figures can be stated."
        )
    parts.append(
        "The AI explainer is temporarily unavailable; the figures above come from the "
        "deterministic DSM engine, not from a language model."
    )
    return " ".join(parts)
