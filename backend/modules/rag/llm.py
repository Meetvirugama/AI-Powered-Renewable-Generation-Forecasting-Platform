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

# Verified against both providers on 2026-09-12 with a real completion, not just
# a models-list call -- several models connect happily and then return an empty
# string. llama-3.3-70b-versatile is retired and no longer served by Groq.
#
# gpt-oss-120b returns clean prose and stops cleanly. Avoid qwen3.6-27b: it emits
# its <think> block into message.content, which would land verbatim in an
# operator's answer.
DEFAULT_PRIMARY = "groq/openai/gpt-oss-120b"
DEFAULT_FALLBACK = "gemini/gemini-3.6-flash"

# Provider prefix -> env vars holding its credentials. The plural form is checked
# first and may hold several comma-separated keys; see _keys_for().
_PROVIDER_KEYS = {
    "groq": ("GROQ_API_KEYS", "GROQ_API_KEY"),
    "gemini": ("GEMINI_API_KEYS", "GEMINI_API_KEY"),
    "openai": ("OPENAI_API_KEYS", "OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY"),
}

# Errors worth retrying on a *different key* rather than giving up on the
# provider: a per-key quota or a single revoked key says nothing about the
# others. Matched against the exception text because each provider SDK raises
# its own type.
_ROTATABLE = (
    "rate limit", "ratelimit", "429", "quota", "resource_exhausted",
    "invalid api key", "invalid_api_key", "unauthorized", "401", "403",
    "permission denied", "api key not valid",
)

_CONTEXT_HEADER = re.compile(r"^\[([^\]|]+)\s*\|\s*([^\]|]+)\s*\|\s*p\.(\d+)\]", re.M)


class AllProvidersFailed(RuntimeError):
    """Every configured provider failed. The caller must degrade, not propagate a 500."""


def primary_model() -> str:
    return os.getenv("RAG_PRIMARY_MODEL", DEFAULT_PRIMARY)


def fallback_model() -> str:
    return os.getenv("RAG_FALLBACK_MODEL", DEFAULT_FALLBACK)


def provider_of(model: str) -> str:
    return model.split("/", 1)[0].lower()


def _keys_for(model: str) -> list[str]:
    """Every credential configured for this model's provider, in order.

    Free tiers are rate-limited per key (Groq's is roughly 30 requests/minute per
    org), and during a demo four teammates and a judge share that budget. Holding
    several keys and rotating on a quota error turns a hard failure into a
    slightly slower answer.

    `GROQ_API_KEYS` (comma-separated) is checked before `GROQ_API_KEY`, and both
    are merged so an existing single-key deployment keeps working untouched.
    """
    provider = provider_of(model)
    env_vars = _PROVIDER_KEYS.get(provider)
    if env_vars is None:
        return [""]  # unknown provider: let LiteLLM find its own credentials

    keys: list[str] = []
    for env_var in env_vars:
        for key in os.getenv(env_var, "").split(","):
            key = key.strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def _has_key(model: str) -> bool:
    provider = provider_of(model)
    if provider not in _PROVIDER_KEYS:
        return True  # unknown provider: let LiteLLM decide
    return bool(_keys_for(model))


def _is_rotatable(exc: Exception) -> bool:
    """Would another key plausibly succeed where this one failed?"""
    text = str(exc).lower()
    return any(marker in text for marker in _ROTATABLE)


# Which key each model last succeeded with, so the next call starts there rather
# than replaying the exhausted ones. In-process only: a restart simply begins at
# the first key again, which is harmless.
_key_cursor: dict[str, int] = {}


def reset_key_cursor() -> None:
    """Forget the rotation position. Used by tests."""
    _key_cursor.clear()


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
        keys = _keys_for(model) or [""]
        # Start from wherever the last success left off, so load spreads across
        # keys instead of hammering the first one until it hits its quota.
        start = _key_cursor.get(model, 0) % len(keys)
        order = [(start + i) % len(keys) for i in range(len(keys))]

        for position, key_index in enumerate(order):
            api_key = keys[key_index] or None
            for attempt in range(attempts_per_model):
                started = time.time()
                try:
                    response = litellm.completion(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                        **({"api_key": api_key} if api_key else {}),
                    )
                    elapsed_ms = int((time.time() - started) * 1000)
                    _key_cursor[model] = key_index
                    logger.info(
                        "llm_ok model=%s key=%d/%d ms=%d",
                        model, key_index + 1, len(keys), elapsed_ms,
                    )
                    return (response.choices[0].message.content or ""), model
                except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
                    last_error = exc
                    # "llm_fail" is the literal token the CloudWatch metric
                    # filter matches on; see infra/aws/cloudwatch_alarms.sh.
                    logger.warning(
                        "llm_fail model=%s key=%d/%d attempt=%d err=%s",
                        model, key_index + 1, len(keys), attempt, exc,
                    )
                    if _is_rotatable(exc):
                        # A per-key quota or a revoked key says nothing about the
                        # other keys. Move on immediately rather than burning the
                        # retry budget on a credential that cannot work.
                        break
                    if attempt + 1 < attempts_per_model:
                        time.sleep(0.8 * (attempt + 1))

            if position + 1 < len(order):
                logger.info("rotating to the next %s key", provider_of(model))

    raise AllProvidersFailed(str(last_error))


def redundancy() -> str:
    """Whether a provider failure actually has somewhere to fail over to.

    `_candidates()` de-duplicates, so configuring the same model as primary and
    fallback collapses to a single entry: retries against the one provider
    rather than failover to a second. That is a legitimate configuration -- it
    is what you get when only one provider has a working key -- but it must not
    be mistaken for the two-provider design, because a rate-limit or outage then
    takes the copilot straight to the deterministic template.
    """
    usable = _candidates()
    if usable == ["mock"]:
        return "mock"
    if len(usable) >= 2:
        return "dual_provider"
    if len(usable) == 1:
        return "single_provider"
    return "none"


def health() -> dict:
    """Reported by GET /rag/health so a missing key is visible before the demo, not during it."""
    usable = _candidates()
    report = {
        "primary": primary_model(),
        "fallback": fallback_model(),
        "usable": usable,
        "redundancy": redundancy(),
        # How many credentials each usable model can rotate through. One key on a
        # free tier is a rate-limit away from the fallback template.
        "keys_per_model": {m: len(_keys_for(m)) for m in usable if m != "mock"},
    }
    if primary_model() == fallback_model() and usable != ["mock"]:
        report["warning"] = (
            f"primary and fallback are both {primary_model()!r}, so there is no failover. "
            "Set RAG_FALLBACK_MODEL to a different provider or model to restore it."
        )
    elif len(usable) == 1 and primary_model() != fallback_model():
        report["warning"] = (
            f"only {usable[0]!r} is usable; the other configured model has no API key, "
            "so a failure has nowhere to fail over to."
        )
    return report
