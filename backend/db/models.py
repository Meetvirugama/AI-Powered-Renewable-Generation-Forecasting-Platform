from sqlalchemy import String, Float, Integer, Boolean, Text, DateTime, Date, ForeignKey, Index, JSON, BigInteger
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from datetime import datetime, date
from typing import Optional, Any
import uuid

class Base(DeclarativeBase):
    pass


# bge-m3 produces 1024-dim dense vectors. Postgres gets a real pgvector column;
# SQLite (used by the test suite) falls back to TEXT so create_all() still works.
EMBEDDING_DIM = 1024
EmbeddingType = Vector(EMBEDDING_DIM).with_variant(Text(), "sqlite")


class Plant(Base):
    __tablename__ = 'plants'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    avc_mw: Mapped[float] = mapped_column(Float)
    pool_id: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON)


class WeatherForecast(Base):
    __tablename__ = 'weather_forecasts'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String, ForeignKey('plants.id'))
    issue_time: Mapped[datetime] = mapped_column(DateTime)
    valid_time: Mapped[datetime] = mapped_column(DateTime)
    ghi_w_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dni_w_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dhi_w_m2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_10m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_80m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_120m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temp_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cloud_cover: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('ix_weather_forecast_plant_valid', 'plant_id', 'valid_time'),
    )


class Forecast(Base):
    __tablename__ = 'forecasts'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String, ForeignKey('plants.id'))
    run_id: Mapped[str] = mapped_column(String)
    valid_time: Mapped[datetime] = mapped_column(DateTime)
    block_no: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String)
    p05: Mapped[float] = mapped_column(Float)
    p10: Mapped[float] = mapped_column(Float)
    p25: Mapped[float] = mapped_column(Float)
    p50: Mapped[float] = mapped_column(Float)
    p75: Mapped[float] = mapped_column(Float)
    p90: Mapped[float] = mapped_column(Float)
    p95: Mapped[float] = mapped_column(Float)
    calibrated: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index('ix_forecast_plant_valid', 'plant_id', 'valid_time'),
    )


class Schedule(Base):
    __tablename__ = 'schedules'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String, ForeignKey('plants.id'))
    schedule_date: Mapped[date] = mapped_column(Date)
    block_no: Mapped[int] = mapped_column(Integer)
    schedule_type: Mapped[str] = mapped_column(String)
    schedule_mw: Mapped[float] = mapped_column(Float)
    run_id: Mapped[str] = mapped_column(String)

    __table_args__ = (
        Index('ix_schedule_plant_date', 'plant_id', 'schedule_date'),
    )


class DSMResult(Base):
    __tablename__ = 'dsm_results'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String, ForeignKey('plants.id'))
    run_id: Mapped[str] = mapped_column(String)
    valid_time: Mapped[datetime] = mapped_column(DateTime)
    block_no: Mapped[int] = mapped_column(Integer)
    schedule_mw: Mapped[float] = mapped_column(Float)
    expected_penalty_inr: Mapped[float] = mapped_column(Float)
    p50_penalty_inr: Mapped[float] = mapped_column(Float)
    optimised_penalty_inr: Mapped[float] = mapped_column(Float)
    rule_version: Mapped[str] = mapped_column(String)
    x_value: Mapped[float] = mapped_column(Float)
    savings_inr: Mapped[float] = mapped_column(Float)


class Action(Base):
    __tablename__ = 'actions'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String, ForeignKey('plants.id'))
    run_id: Mapped[str] = mapped_column(String)
    valid_time: Mapped[datetime] = mapped_column(DateTime)
    block_no: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String)
    action_mw: Mapped[float] = mapped_column(Float)
    soc_mwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PoolingResult(Base):
    __tablename__ = 'pooling_results'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[str] = mapped_column(String)
    run_id: Mapped[str] = mapped_column(String)
    schedule_date: Mapped[date] = mapped_column(Date)
    individual_penalty_inr: Mapped[float] = mapped_column(Float)
    pooled_penalty_inr: Mapped[float] = mapped_column(Float)
    savings_pct: Mapped[float] = mapped_column(Float)


class RegulationChunk(Base):
    __tablename__ = 'regulation_chunks'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_name: Mapped[str] = mapped_column(String)
    section: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    clause: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    chunk_text: Mapped[str] = mapped_column(Text)

    # Deterministic id from (doc, clause, page, chunk_index) so re-running the
    # offline ingest is idempotent instead of duplicating the corpus.
    chunk_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    embedding: Mapped[Optional[Any]] = mapped_column(EmbeddingType, nullable=True)
    # Which model produced `embedding`. Query-time embeddings MUST come from the
    # same model; a mismatch returns plausible-looking but meaningless neighbours.
    embed_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (
        # Unique INDEX rather than a unique CONSTRAINT: SQLite (test suite)
        # cannot ALTER a constraint into an existing table, and a unique index
        # enforces exactly the same thing on both backends.
        Index('uq_regulation_chunks_chunk_id', 'chunk_id', unique=True),
        Index('ix_regulation_chunks_doc', 'doc_name'),
    )


class BacktestMetric(Base):
    __tablename__ = 'backtest_metrics'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[str] = mapped_column(String)
    model_name: Mapped[str] = mapped_column(String)
    run_date: Mapped[date] = mapped_column(Date)
    horizon_h: Mapped[int] = mapped_column(Integer)
    mae_mw: Mapped[float] = mapped_column(Float)
    rmse_mw: Mapped[float] = mapped_column(Float)
    pinball_p10: Mapped[float] = mapped_column(Float)
    pinball_p50: Mapped[float] = mapped_column(Float)
    pinball_p90: Mapped[float] = mapped_column(Float)
    crps: Mapped[float] = mapped_column(Float)
    picp_80: Mapped[float] = mapped_column(Float)
    skill_vs_persistence: Mapped[float] = mapped_column(Float)


class JobRun(Base):
    __tablename__ = 'job_runs'
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String)
    plants_processed: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
