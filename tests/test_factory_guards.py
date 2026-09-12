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
    assert isinstance(get_forecast_engine(), MockForecastEngine)
    assert isinstance(get_schedule_optimizer(), MockScheduleOptimizer)


def test_explicit_mock_is_honoured(monkeypatch):
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "mock")
    assert isinstance(get_forecast_engine(), MockForecastEngine)


def test_missing_production_optimizer_raises_not_falls_back(monkeypatch):
    """schedule_optimizer.py does not exist yet. That must be loud, not silent."""
    monkeypatch.setenv("OPTIMIZER_TYPE", "production")
    with pytest.raises(ProductionEngineUnavailable) as exc:
        get_schedule_optimizer()
    message = str(exc.value)
    assert "OPTIMIZER_TYPE=production" in message
    assert "OPTIMIZER_TYPE=mock" in message, "the error should say how to proceed"


def test_production_forecast_engine_is_constructible(monkeypatch):
    """The adapter exists now, so this must no longer raise at construction."""
    monkeypatch.setenv("FORECAST_ENGINE_TYPE", "production")
    from backend.modules.forecast.lgbm_model import LGBMForecastEngine

    assert isinstance(get_forecast_engine(), LGBMForecastEngine)


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
