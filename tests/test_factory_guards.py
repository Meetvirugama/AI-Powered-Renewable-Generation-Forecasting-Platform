"""The factory must never silently downgrade to a mock.

Why this matters more than it looks: the mock forecast engine emits a plausible
seeded sine wave, the real DSM engine prices it into real rupee figures, and the
dashboard renders those exactly as it renders genuine ones. Before this guard,
`FORECAST_ENGINE_TYPE=production` with a missing module logged one warning and
served synthetic data indistinguishable from real output.
"""
from __future__ import annotations

import pytest

from backend.modules.factory import (
    CompositeEngine,
    ProductionEngineUnavailable,
    active_engines,
    get_forecast_engine,
    get_rag_copilot,
    get_schedule_optimizer,
)
from backend.modules.forecast.mock_engine import MockForecastEngine
from backend.modules.optimize.mock_optimizer import MockScheduleOptimizer


def test_default_is_mock_and_says_so(monkeypatch):
    monkeypatch.delenv("FORECAST_ENGINE_TYPE", raising=False)
    monkeypatch.delenv("OPTIMIZER_TYPE", raising=False)
    engine = get_forecast_engine()
    # get_forecast_engine now returns a CompositeEngine that wraps the solar
    # and wind engines. The solar engine must be the mock when unconfigured.
    assert isinstance(engine, CompositeEngine), "expected CompositeEngine wrapper"
    assert isinstance(engine._solar, MockForecastEngine)
    assert isinstance(get_schedule_optimizer(), MockScheduleOptimizer)


def test_explicit_mock_is_honoured(monkeypatch):
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "mock")
    engine = get_forecast_engine()
    assert isinstance(engine, CompositeEngine)
    assert isinstance(engine._solar, MockForecastEngine)


def test_production_optimizer_is_constructible(monkeypatch):
    """schedule_optimizer.py exists now, so production must build, not raise."""
    monkeypatch.setenv("OPTIMIZER_TYPE", "production")
    from backend.modules.optimize.schedule_optimizer import ProductionScheduleOptimizer

    assert isinstance(get_schedule_optimizer(), ProductionScheduleOptimizer)


def test_a_broken_production_engine_still_raises_rather_than_mocking(monkeypatch):
    """The fail-fast guard itself, exercised without needing a missing module.

    This is the behaviour that matters: whatever the reason a production engine
    cannot be built, the factory must refuse rather than hand back a mock whose
    synthetic output the DSM engine would price into real rupee figures.
    """
    import backend.modules.optimize.schedule_optimizer as module

    def explode(*_args, **_kwargs):
        raise RuntimeError("simulated load failure")

    monkeypatch.setattr(module, "ProductionScheduleOptimizer", explode)
    monkeypatch.setenv("OPTIMIZER_TYPE", "production")

    with pytest.raises(ProductionEngineUnavailable) as exc:
        get_schedule_optimizer()
    message = str(exc.value)
    assert "OPTIMIZER_TYPE=production" in message
    assert "OPTIMIZER_TYPE=mock" in message, "the error should say how to proceed"


def test_production_forecast_engine_is_constructible(monkeypatch):
    """The LightGBM engine must load without error; it becomes the solar branch
    of the CompositeEngine that get_forecast_engine() returns."""
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "production")
    from backend.modules.forecast.lgbm_model import LGBMForecastEngine

    engine = get_forecast_engine()
    assert isinstance(engine, CompositeEngine)
    assert isinstance(engine._solar, LGBMForecastEngine)


def test_active_engines_reports_configuration(monkeypatch):
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "production")
    monkeypatch.setenv("OPTIMIZER_TYPE", "mock")
    monkeypatch.setenv("RAG_COPILOT_TYPE", "mock")
    assert active_engines() == {
        "forecast": "production",
        "optimizer": "mock",
        "rag_copilot": "mock",
    }


def test_health_endpoint_discloses_synthetic_engines(client, monkeypatch):
    """A judge asking 'are these numbers real?' must be able to check."""
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "mock")
    monkeypatch.setenv("OPTIMIZER_TYPE", "mock")
    monkeypatch.setenv("RAG_COPILOT_TYPE", "mock")

    body = client.get("/health").json()
    assert body["status"] == "healthy"
    assert body["engines"]["forecast"] == "mock"
    assert set(body["serving_synthetic_data"]) == {"forecast", "optimizer", "rag_copilot"}


def test_health_reports_nothing_synthetic_when_all_production(client, monkeypatch):
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "production")
    monkeypatch.setenv("OPTIMIZER_TYPE", "production")
    monkeypatch.setenv("RAG_COPILOT_TYPE", "production")

    body = client.get("/health").json()
    assert body["serving_synthetic_data"] == []
    # And it should surface whether the models behind that claim actually loaded.
    assert "forecast_models" in body


def test_rag_copilot_default_is_mock(monkeypatch):
    monkeypatch.setenv("RAG_COPILOT_TYPE", "mock")
    get_rag_copilot.cache_clear()
    from backend.modules.rag.mock_copilot import MockRAGCopilot

    assert isinstance(get_rag_copilot(), MockRAGCopilot)
    get_rag_copilot.cache_clear()


# ------------------------------------------------- deployment-shaped env values
def test_inline_comment_in_env_does_not_silently_downgrade(monkeypatch):
    """systemd's EnvironmentFile= keeps inline comments; python-dotenv strips them.

    The same .env line therefore reads as `production` locally and
    `production   # mock | production` under systemd. Unnormalised, that matches
    no branch and quietly serves the mock -- the exact failure this module
    exists to prevent. Observed live on the Azure deployment.
    """
    monkeypatch.setenv("OPTIMIZER_TYPE", "production          # mock | production")
    from backend.modules.optimize.schedule_optimizer import ProductionScheduleOptimizer

    assert isinstance(get_schedule_optimizer(), ProductionScheduleOptimizer)


def test_active_engines_reports_the_normalised_value(monkeypatch):
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "mock          # mock | production")
    monkeypatch.setenv("OPTIMIZER_TYPE", "production   # comment")
    monkeypatch.setenv("RAG_COPILOT_TYPE", "mock")
    assert active_engines() == {
        "forecast": "mock",
        "optimizer": "production",
        "rag_copilot": "mock",
    }


def test_blank_env_value_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("OPTIMIZER_TYPE", "   # only a comment")
    assert isinstance(get_schedule_optimizer(), MockScheduleOptimizer)
