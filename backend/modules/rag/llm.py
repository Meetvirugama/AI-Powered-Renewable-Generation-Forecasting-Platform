"""LLM routing via LiteLLM: Groq primary, Gemini fallback, neither trusted with arithmetic.

Groq is fast but aggressively rate-limited on the free tier (roughly 30 req/min
per org -- four teammates testing while a judge types will hit it). Gemini Flash
is the safety net. If both are down the caller falls back to a deterministic
template; see guardrail.deterministic_fallback.

Temperature is 0.1, not 0.7. This is a compliance explainer, not a creative
writer, and a low temperature also makes the response cache meaningful and the
demo reproducible.

A third pseudo-provider, `mock`, returns a deterministic answer grounded in the
context block it was handed. It exists so CI and the test suite can exercise the
full graph -- retrieval, guardrail, citation validation -- with no API key and no
network.
"""
from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger("renewable_platform")

DEFAULT_PRIMARY = "groq/llama-3.3-70b-versatile"
DEFAULT_FALLBACK = "gemini/gemini-1.5-flash"

# Provider prefix -> env var that must be non-empty for that provider to be tried.
_PROVIDER_KEYS = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

_CONTEXT_HEADER = re.compile(r"^\[([^\]|]+)\s*\|\s*([^\]|]+)\s*\|\s*p\.(\d+)\]", re.M)


class AllProvidersFailed(RuntimeError):
    """Every configured provider failed. The caller must degrade, not propagate a 500."""


def primary_model() -> str:
    return os.getenv("RAG_PRIMARY_MODEL", DEFAULT_PRIMARY)


def fallback_model() -> str:
    return os.getenv("RAG_FALLBACK_MODEL", DEFAULT_FALLBACK)


def _has_key(model: str) -> bool:
    provider = model.split("/", 1)[0].lower()
    env_var = _PROVIDER_KEYS.get(provider)
    if env_var is None:
        return True  # unknown provider: let LiteLLM decide
    return bool(os.getenv(env_var, "").strip())


def _candidates() -> list[str]:
    """Configured models in priority order, skipping any whose key is absent.

    Skipping keyless providers matters during a live demo: without it, a missing
    Gemini key costs a 25 second timeout on every request before the fallback
    template is reached.
    """
    ordered: list[str] = []
    for model in (primary_model(), fallback_model()):
        if model and model not in ordered:
            ordered.append(model)
    if any(m == "mock" for m in ordered):
        return ["mock"]
    usable = [m for m in ordered if _has_key(m)]
    if not usable:
        logger.warning("no LLM provider has an API key configured (checked: %s)", ordered)
    return usable


def _mock_completion(messages: list[dict]) -> str:
    """Deterministic answer that cites whatever context it was given.

    It mirrors the shape a real answer must have -- prose plus a
    [doc | clause | p.NN] citation -- so the guardrail and the citation validator
    are genuinely exercised rather than bypassed.
    """
    user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    hit = _CONTEXT_HEADER.search(user)
    citation = f" [{hit.group(1).strip()} | {hit.group(2).strip()} | p.{hit.group(3)}]" if hit else ""
    return (
        "The declared schedule and the actual injection differ for this block, and the "
        "deviation falls outside the tolerance band that applies to the generator, which "
        "is what attracts a deviation charge under the cited provision."
        + citation
    )


def complete(
    messages: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int = 700,
    timeout: int = 25,
    attempts_per_model: int = 2,
) -> tuple[str, str]:
    """Return (text, model_used). Raises AllProvidersFailed when everything is down."""
    candidates = _candidates()
    if candidates == ["mock"]:
        return _mock_completion(messages), "mock"
    if not candidates:
        raise AllProvidersFailed("no provider configured with an API key")

    import litellm

    litellm.drop_params = True  # tolerate provider-specific parameter mismatches
    litellm.set_verbose = False

    last_error: Exception | None = None
    for model in candidates:
        for attempt in range(attempts_per_model):
            started = time.time()
            try:
                response = litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                elapsed_ms = int((time.time() - started) * 1000)
                logger.info("llm_ok model=%s ms=%d", model, elapsed_ms)
                return (response.choices[0].message.content or ""), model
            except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
                last_error = exc
                # "llm_fail" is the literal token the CloudWatch metric filter
                # matches on; see infra/aws/cloudwatch_alarms.sh.
                logger.warning("llm_fail model=%s attempt=%d err=%s", model, attempt, exc)
                if attempt + 1 < attempts_per_model:
                    time.sleep(0.8 * (attempt + 1))

    raise AllProvidersFailed(str(last_error))


def health() -> dict:
    """Reported by GET /rag/health so a missing key is visible before the demo, not during it."""
    return {
        "primary": primary_model(),
        "fallback": fallback_model(),
        "usable": _candidates(),
    }
