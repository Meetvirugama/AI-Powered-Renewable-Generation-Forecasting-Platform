from typing import Generator
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from backend.core.config import get_settings

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None

def init_db(db_url: str | None = None) -> Engine:
    """
    Initialize and return the SQLAlchemy engine lazily.
    Supports both SQLite and PostgreSQL configurations.
    """
    global _engine, _SessionFactory
    if _engine is None:
        settings = get_settings()
        url = db_url or settings.database_url
        if url.startswith("sqlite"):
            _engine = create_engine(
                url,
                echo=False,
                connect_args={"check_same_thread": False}
            )
        else:
            _engine = create_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10
            )
        _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    return _engine

def SessionLocal() -> Session:
    """
    Callable session factory that returns a new Session instance.
    Initializes the engine if not already initialized.
    """
    global _SessionFactory
    if _SessionFactory is None:
        init_db()
    return _SessionFactory()

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
