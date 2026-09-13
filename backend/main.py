import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import dashboard, dsm, forecast, optimize, pipeline, plants, pooling, rag
from backend.core.config import get_cors_origins
from backend.db.models import Base
from backend.db.seed import seed_plants
from backend.db.session import SessionLocal, init_db

logger = logging.getLogger("renewable_platform")

def _warm_rag() -> None:
    """Build the BM25 index and load the embedding model before the first request.

    Both costs are paid once, at boot, rather than by whoever asks the first
    question: BM25 is ~1 s over 2k chunks and the bge-m3 load is 8-15 s. This is
    why the container healthcheck uses --start-period=90s; a shorter period marks
    a still-loading container unhealthy and Docker restart-loops it.

    Only runs for the production copilot. Nothing here is fatal: the forecasting
    routes must still serve if the regulation corpus is missing.
    """
    if os.getenv("RAG_COPILOT_TYPE", "mock").lower() != "production":
        return

    from backend.modules.rag import embed, retriever

    try:
        with SessionLocal() as db:
            chunks = retriever.build_bm25(db)
            # A model mismatch between the corpus and this process returns
            # plausible but meaningless neighbours, so fail loudly in prod.
            embed.verify_corpus_model(db)
        logger.info(f"RAG ready: {chunks} chunks indexed for sparse retrieval.")
    except Exception as e:
        logger.error(f"RAG warmup failed; copilot will degrade: {e}")
        # In production a broken corpus means the copilot would cite nothing or,
        # worse, cite against the wrong embedding space. Refuse to come up.
        if os.getenv("APP_ENV", "development").lower() in {"prod", "production"}:
            raise

    try:
        embed.warmup()
    except Exception as e:
        logger.warning(f"Embedding model warmup failed; first query will pay the load cost: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        engine = init_db()
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            count = seed_plants(db)
            logger.info(f"Initialized database and seeded {count} plants.")
    except Exception as e:
        logger.warning(f"Database initialization warning (e.g. running offline/sqlite): {e}")

    _warm_rag()
    yield

app = FastAPI(
    title="VidyutVaani API",
    version="1.0.0",
    description="REST API for Probabilistic Renewable Generation Forecasting, CERC DSM Settlement & Schedule Optimization",
    lifespan=lifespan
)

_cors_origins = get_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # A wildcard origin and credentials cannot be combined by the browser, so
    # credentials are only enabled when the origins are explicitly listed.
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(plants.router)
app.include_router(forecast.router)
app.include_router(dsm.router)
app.include_router(optimize.router)
app.include_router(pooling.router)
app.include_router(dashboard.router)
app.include_router(rag.router)
app.include_router(pipeline.router)

@app.get("/health")
def health_check():
    """Liveness, plus which engine backs each capability.

    `engines` is here so that "are these numbers real?" is answerable from the
    API itself. A mock forecast is priced by the real DSM engine into
    real-looking rupee figures, and nothing downstream distinguishes them, so
    the distinction has to be published at the source.
    """
    from backend.modules.factory import active_engines

    engines = active_engines()
    report = {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engines": engines,
        "serving_synthetic_data": sorted(k for k, v in engines.items() if v != "production"),
    }

    if engines["forecast"] == "production":
        try:
            from backend.modules.forecast.lgbm_model import LGBMForecastEngine

            report["forecast_models"] = LGBMForecastEngine().health()
        except Exception as exc:  # noqa: BLE001 - a health check never 500s
            report["forecast_models"] = {"status": "error", "error": str(exc)}

    return report

@app.get("/")
def root():
    return {
        "message": "VidyutVaani API",
        "docs": "/docs"
    }
