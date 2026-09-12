import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.db.models import Base
from backend.db.session import get_db
from backend.db.seed import seed_plants
from backend.main import app
from backend.core.config import get_settings

TEST_DB_URL = 'sqlite:///:memory:'

@pytest.fixture(scope='session')
def engine():
    engine = create_engine(TEST_DB_URL, connect_args={'check_same_thread': False})
    Base.metadata.create_all(bind=engine)
    return engine

@pytest.fixture(scope='function')
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionTest = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionTest()
    
    seed_plants(session)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope='function')
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
