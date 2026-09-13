import os
import tempfile
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['JWT_SECRET'] = 'test-secret-with-at-least-32-characters'
os.environ['FILE_ROOT'] = tempfile.mkdtemp(prefix='dashvanti-test-')
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.db import Base, get_db
from backend.main import app

@pytest.fixture
def client():
    engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine,expire_on_commit=False)
    def override():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        client.db_factory = factory
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
