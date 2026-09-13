from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from backend.config import settings

class Base(DeclarativeBase):
    pass

engine = create_engine(settings.database_url, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with Session() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
