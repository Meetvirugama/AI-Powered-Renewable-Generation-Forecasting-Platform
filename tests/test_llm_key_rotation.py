"""Multi-key rotation.

Free tiers are rate-limited per key -- Groq's is roughly 30 requests/minute per
org -- and during a demo four teammates and a judge share that budget. Holding
several keys and rotating on a quota error turns a hard failure into a slightly
slower answer, instead of dropping straight to the deterministic template.
"""
from __future__ import annotations

import pytest

from backend.modules.rag import llm


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for var in ("GROQ_API_KEYS", "GROQ_API_KEY", "GEMINI_API_KEYS", "GEMINI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    llm.reset_key_cursor()
    yield
    llm.reset_key_cursor()


# ------------------------------------------------------------- key discovery
def test_plural_variable_parses_comma_separated_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "k1,k2,k3")
    assert llm._keys_for("groq/openai/gpt-oss-120b") == ["k1", "k2", "k3"]


def test_whitespace_around_keys_is_stripped(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", " k1 , k2 ,  k3  ")
    assert llm._keys_for("groq/x") == ["k1", "k2", "k3"]


def test_singular_variable_still_works(monkeypatch):
    """An existing single-key deployment must keep working untouched."""
    monkeypatch.setenv("GROQ_API_KEY", "solo")
    assert llm._keys_for("groq/x") == ["solo"]


def test_plural_and_singular_are_merged_without_duplicates(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "k1,k2")
    monkeypatch.setenv("GROQ_API_KEY", "k2")
    assert llm._keys_for("groq/x") == ["k1", "k2"]


def test_empty_entries_are_ignored(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "k1,,  ,k2,")
    assert llm._keys_for("groq/x") == ["k1", "k2"]


def test_no_keys_means_the_model_is_not_usable(monkeypatch):
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/x")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/x")
    assert llm._keys_for("groq/x") == []
    assert llm._candidates() == []


# --------------------------------------------------------- rotatable errors
@pytest.mark.parametrize(
    "message",
    [
        "Rate limit reached for model",
        "Error code: 429 - too many requests",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "Invalid API key provided",
        "401 Unauthorized",
        "API key not valid. Please pass a valid API key.",
    ],
)
def test_quota_and_credential_errors_rotate(message):
    assert llm._is_rotatable(RuntimeError(message))


@pytest.mark.parametrize(
    "message",
    ["Connection timed out", "500 internal server error", "model not found"],
)
def test_other_errors_do_not_rotate(message):
    """A timeout or a bad model name is not fixed by swapping credentials."""
    assert not llm._is_rotatable(RuntimeError(message))


# ------------------------------------------------------------- the rotation
def _fake_litellm(monkeypatch, behaviour):
    """Install a stub litellm whose completion() consults `behaviour(api_key)`."""
    import sys
    import types

    calls: list[str] = []

    def completion(**kwargs):
        key = kwargs.get("api_key", "")
        calls.append(key)
        outcome = behaviour(key)
        if isinstance(outcome, Exception):
            raise outcome
        message = types.SimpleNamespace(content=outcome)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    stub = types.SimpleNamespace(completion=completion, drop_params=True, set_verbose=False)
    monkeypatch.setitem(sys.modules, "litellm", stub)
    return calls


def test_rotates_past_a_rate_limited_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "bad1,bad2,good")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/m")

    def behaviour(key):
        return "answer" if key == "good" else RuntimeError("Rate limit reached")

    calls = _fake_litellm(monkeypatch, behaviour)
    text, model = llm.complete([{"role": "user", "content": "hi"}])

    assert text == "answer"
    assert model == "groq/m"
    assert calls == ["bad1", "bad2", "good"], "each key should be tried once, in order"


def test_a_rate_limited_key_is_not_retried_on_the_same_key(monkeypatch):
    """Retrying a key that is out of quota just burns the retry budget."""
    monkeypatch.setenv("GROQ_API_KEYS", "bad,good")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/m")

    def behaviour(key):
        return "answer" if key == "good" else RuntimeError("429 rate limit")

    calls = _fake_litellm(monkeypatch, behaviour)
    llm.complete([{"role": "user", "content": "hi"}], attempts_per_model=3)
    assert calls.count("bad") == 1


def test_a_transient_error_does_retry_the_same_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "only")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/m")

    state = {"n": 0}

    def behaviour(key):
        state["n"] += 1
        return "answer" if state["n"] > 1 else RuntimeError("Connection timed out")

    calls = _fake_litellm(monkeypatch, behaviour)
    text, _ = llm.complete([{"role": "user", "content": "hi"}], attempts_per_model=2)
    assert text == "answer"
    assert calls == ["only", "only"]


def test_next_call_resumes_from_the_key_that_worked(monkeypatch):
    """Load should spread, not restart at the exhausted first key every time."""
    monkeypatch.setenv("GROQ_API_KEYS", "a,b,c")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/m")

    def behaviour(key):
        return "answer" if key == "c" else RuntimeError("quota exceeded")

    calls = _fake_litellm(monkeypatch, behaviour)
    llm.complete([{"role": "user", "content": "hi"}])
    assert calls == ["a", "b", "c"]

    calls.clear()
    llm.complete([{"role": "user", "content": "hi"}])
    assert calls[0] == "c", "should resume from the key that last succeeded"


def test_all_keys_exhausted_raises_rather_than_returning_nothing(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "a,b")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "groq/m")
    _fake_litellm(monkeypatch, lambda key: RuntimeError("429 rate limit"))

    with pytest.raises(llm.AllProvidersFailed):
        llm.complete([{"role": "user", "content": "hi"}])


def test_falls_over_to_the_second_provider_when_the_first_is_exhausted(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "g1,g2")
    monkeypatch.setenv("GEMINI_API_KEYS", "m1")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/f")

    def behaviour(key):
        return "from gemini" if key == "m1" else RuntimeError("quota exceeded")

    _fake_litellm(monkeypatch, behaviour)
    text, model = llm.complete([{"role": "user", "content": "hi"}])
    assert text == "from gemini"
    assert model == "gemini/f"


# -------------------------------------------------------------------- health
def test_health_reports_key_counts(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEYS", "a,b,c")
    monkeypatch.setenv("GEMINI_API_KEYS", "x,y")
    monkeypatch.setenv("RAG_PRIMARY_MODEL", "groq/m")
    monkeypatch.setenv("RAG_FALLBACK_MODEL", "gemini/f")

    report = llm.health()
    assert report["redundancy"] == "dual_provider"
    assert report["keys_per_model"] == {"groq/m": 3, "gemini/f": 2}
    assert "warning" not in report
