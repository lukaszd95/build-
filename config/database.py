from pathlib import Path
import os
from contextlib import contextmanager
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import declarative_base, sessionmaker


def _normalize_database_url(raw_url: str) -> str:
    """Normalize DB URL from env.

    For PostgreSQL credentials, percent-encode username/password so special
    characters from `.env` (e.g. Polish letters) don't break psycopg2 DSN
    decoding on Windows/PyCharm setups.
    """

    database_url = (raw_url or "").strip().strip('"').strip("'")
    if not database_url:
        return "sqlite:///data/app.db"

    lowered = database_url.lower()
    if not (lowered.startswith("postgresql://") or lowered.startswith("postgres://")):
        return database_url

    parsed = urlsplit(database_url)
    if parsed.username is None and parsed.password is None:
        return database_url

    username = quote(parsed.username or "", safe="")
    password = quote(parsed.password or "", safe="")
    auth = username
    if parsed.password is not None:
        auth = f"{auth}:{password}"

    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    netloc = f"{auth}@{host}" if auth else host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


DATABASE_URL = _normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///data/app.db"))

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
