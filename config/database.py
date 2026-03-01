from pathlib import Path
import os
from contextlib import contextmanager
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit

from sqlalchemy import create_engine, inspect, text
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

    username = _normalize_auth_component(parsed.username)
    password = _normalize_auth_component(parsed.password)
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


def _normalize_auth_component(value: str | None) -> str:
    if not value:
        return ""

    raw_bytes = unquote_to_bytes(value)
    for encoding in ("utf-8", "cp1250", "latin-1"):
        try:
            decoded = raw_bytes.decode(encoding)
            return quote(decoded, safe="")
        except UnicodeDecodeError:
            continue

    return quote(value, safe="")


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


def ensure_mpzp_identification_columns() -> None:
    """Backfill MPZP identification columns when DB is on an older schema.

    This guards local/dev environments where migrations were not re-run after
    adding the parcel identification fields.
    """

    inspector = inspect(engine)
    if not inspector.has_table("mpzp_conditions"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("mpzp_conditions")}
    desired_columns = {
        "plot_number": "VARCHAR(120)",
        "cadastral_district": "VARCHAR(255)",
        "street": "VARCHAR(255)",
        "city": "VARCHAR(255)",
        "land_use_primary": "TEXT",
        "land_use_allowed": "TEXT",
        "land_use_forbidden": "TEXT",
        "services_allowed": "BOOLEAN",
        "nuisance_services_forbidden": "BOOLEAN",
        "parcel_area_total": "NUMERIC(12,2)",
        "max_building_height": "NUMERIC(10,2)",
        "max_storeys_above": "INTEGER",
        "max_storeys_below": "INTEGER",
        "max_ridge_height": "NUMERIC(10,2)",
        "max_eaves_height": "NUMERIC(10,2)",
        "min_building_intensity": "NUMERIC(10,2)",
        "max_building_intensity": "NUMERIC(10,2)",
        "max_building_coverage": "NUMERIC(10,2)",
        "min_biologically_active_share": "NUMERIC(5,2)",
        "min_front_elevation_width": "NUMERIC(10,2)",
        "max_front_elevation_width": "NUMERIC(10,2)",
    }

    with engine.begin() as connection:
        for column_name, column_type in desired_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE mpzp_conditions ADD COLUMN {column_name} {column_type}"))

    if not inspector.has_table("mpzp_land_use_register_items"):
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE mpzp_land_use_register_items (
                    id INTEGER PRIMARY KEY,
                    parent_id INTEGER NOT NULL REFERENCES mpzp_conditions(id) ON DELETE CASCADE,
                    category_symbol VARCHAR(64) NOT NULL,
                    area NUMERIC(12,2) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT ck_mpzp_land_use_register_item_area_non_negative CHECK (area >= 0)
                )
            """))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_mpzp_land_use_register_items_parent_id ON mpzp_land_use_register_items(parent_id)"))


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
