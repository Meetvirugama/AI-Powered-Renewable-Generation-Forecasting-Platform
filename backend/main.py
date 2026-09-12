from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from backend.core.config import get_cors_origins
from backend.db.session import init_db, SessionLocal
from backend.db.models import Base
from backend.db.seed import seed_plants
from backend.api import plants, forecast, dsm, optimize, pooling, dashboard, rag, pipeline

logger = logging.getLogger("renewable_platform")

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
    yield

app = FastAPI(
    title="AI-Powered Renewable Generation Forecasting Platform API",
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
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/")
def root():
    return {
        "message": "AI-Powered Renewable Generation Forecasting Platform API",
        "docs": "/docs"
    }
