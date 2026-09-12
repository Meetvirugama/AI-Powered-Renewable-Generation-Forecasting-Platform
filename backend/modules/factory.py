import os
import logging
from functools import lru_cache
from typing import Protocol, Optional, Any, List, Dict

from backend.core.config import get_settings
from backend.modules.forecast.mock_engine import MockForecastEngine
from backend.modules.optimize.mock_optimizer import MockScheduleOptimizer
from backend.modules.rag.mock_copilot import MockRAGCopilot

logger = logging.getLogger('renewable_platform')

class ForecastEngineProtocol(Protocol):
    def generate_forecast(self, plant: dict, date_str: str, num_blocks: int = 96) -> List[dict]:
        ...

class ScheduleOptimizerProtocol(Protocol):
    def optimize_day_ahead(
        self,
        forecast_blocks: List[dict],
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
        plant_id: Optional[str] = None,
        block_no: Optional[int] = None,
        rule_year: Optional[int] = None,
        context: Optional[dict] = None
    ) -> dict:
        ...

def get_forecast_engine() -> ForecastEngineProtocol:
    engine_type = os.getenv('FORECAST_ENGINE_TYPE', 'mock').lower()
    if engine_type == 'production':
        try:
            from backend.modules.forecast.lgbm_model import LGBMForecastEngine
            return LGBMForecastEngine()
        except ImportError:
            logger.warning('Production forecast engine not found, falling back to MockForecastEngine.')
    return MockForecastEngine()

def get_schedule_optimizer() -> ScheduleOptimizerProtocol:
    opt_type = os.getenv('OPTIMIZER_TYPE', 'mock').lower()
    if opt_type == 'production':
        try:
            from backend.modules.optimize.schedule_optimizer import ProductionScheduleOptimizer
            return ProductionScheduleOptimizer()
        except ImportError:
            logger.warning('Production optimizer not found, falling back to MockScheduleOptimizer.')
    return MockScheduleOptimizer()

@lru_cache(maxsize=1)
def get_rag_copilot() -> RAGCopilotProtocol:
    """Cached: the production copilot loads a large embedding model at
    construction, so it must be built once per process, not once per request."""
    rag_type = os.getenv('RAG_COPILOT_TYPE', 'mock').lower()
    if rag_type == 'production':
        try:
            from backend.modules.rag.copilot import RAGCopilot
            return RAGCopilot()
        except ImportError:
            logger.warning('Production RAG copilot not found, falling back to MockRAGCopilot.')
    return MockRAGCopilot()
