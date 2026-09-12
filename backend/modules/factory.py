import os
import logging
from functools import lru_cache
from typing import Protocol, Any

from backend.modules.forecast.mock_engine import MockForecastEngine
from backend.modules.optimize.mock_optimizer import MockScheduleOptimizer
from backend.modules.rag.mock_copilot import MockRAGCopilot

logger = logging.getLogger('renewable_platform')

class ForecastEngineProtocol(Protocol):
    def generate_forecast(self, plant: dict, date_str: str, num_blocks: int = 96, **kwargs) -> list[dict]:
        ...

class ScheduleOptimizerProtocol(Protocol):
    def optimize_day_ahead(
        self,
        forecast_blocks: list[dict],
        avc_mw: float,
        dsm_engine: Any,
        ncd: float = 450.0,
        freq_hz: float = 50.0,
        asset_type: str = 'solar'
    ) -> dict:
        ...

class RAGCopilotProtocol(Protocol):
    def query(
        self,
        question: str,
        plant_id: str | None = None,
        block_no: int | None = None,
        rule_year: int | None = None,
        context: dict | None = None
    ) -> dict:
        ...

class ProductionEngineUnavailable(RuntimeError):
    """An engine was explicitly set to `production` but could not be built.

    This is deliberately fatal. Falling back to a mock here is the most
    dangerous failure mode in this codebase: the mock forecast engine emits a
    plausible seeded sine wave, the DSM engine prices it into real-looking rupee
    figures, and the dashboard renders them with no indication that the entire
    chain rests on synthetic input. A warning in a log nobody reads during
    judging is not a control.

    Operators who want a mock say so, by setting the variable to `mock`.
    """


def _engine_mode(env_var: str) -> str:
    """Read an engine-selection variable, tolerating an inline comment.

    python-dotenv strips `KEY=value  # comment` when the app loads .env itself,
    but systemd's EnvironmentFile= does not -- it passes the comment through as
    part of the value. The same .env file therefore yields `production` locally
    and `production          # mock | production` under systemd, which matches
    no branch and silently falls back to the mock. That is precisely the failure
    this module exists to prevent, so the value is normalised here rather than
    relying on every deployment to keep .env comment-free.
    """
    raw = os.getenv(env_var, 'mock')
    return raw.split('#', 1)[0].strip().lower() or 'mock'


def _resolve(kind: str, env_var: str, default_factory, loader):
    """Build the configured implementation, refusing to silently downgrade."""
    requested = _engine_mode(env_var)
    if requested != 'production':
        return default_factory()
    try:
        return loader()
    except Exception as exc:  # noqa: BLE001 - surface every construction failure
        raise ProductionEngineUnavailable(
            f'{env_var}=production but the production {kind} could not be loaded: '
            f'{type(exc).__name__}: {exc}. '
            f'Set {env_var}=mock to run without it, rather than serving synthetic '
            f'data as if it were real.'
        ) from exc


def active_engines() -> dict:
    """Which implementation each engine is configured to use.

    Surfaced by /health so that "this dashboard is showing synthetic numbers" is
    answerable without reading server logs.
    """
    return {
        'forecast': _engine_mode('FORECAST_ENGINE_TYPE'),
        'optimizer': _engine_mode('OPTIMIZER_TYPE'),
        'rag_copilot': _engine_mode('RAG_COPILOT_TYPE'),
    }


def get_forecast_engine() -> ForecastEngineProtocol:
    def _production():
        from backend.modules.forecast.lgbm_model import LGBMForecastEngine
        return LGBMForecastEngine()

    return _resolve('forecast engine', 'FORECAST_ENGINE_TYPE', MockForecastEngine, _production)

def get_schedule_optimizer() -> ScheduleOptimizerProtocol:
    def _production():
        from backend.modules.optimize.schedule_optimizer import ProductionScheduleOptimizer
        return ProductionScheduleOptimizer()

    return _resolve('optimizer', 'OPTIMIZER_TYPE', MockScheduleOptimizer, _production)

@lru_cache(maxsize=1)
def get_rag_copilot() -> RAGCopilotProtocol:
    """Cached: the production copilot loads a large embedding model at
    construction, so it must be built once per process, not once per request."""
    def _production():
        from backend.modules.rag.copilot import RAGCopilot
        return RAGCopilot()

    return _resolve('RAG copilot', 'RAG_COPILOT_TYPE', MockRAGCopilot, _production)
