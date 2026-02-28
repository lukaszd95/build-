from pathlib import Path
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

if DATABASE_URL.startswith("sqlite:///"):
    sqlite_path = DATABASE_URL.replace("sqlite:///", "", 1)
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


@contextmanager
def db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
