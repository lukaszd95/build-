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


def ensure_users_is_admin_column() -> None:
    """Backfill users.is_admin for legacy databases created before admin role support."""

    inspector = inspect(engine)
    if not inspector.has_table("users"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_admin" in existing_columns:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))


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
        "roof_type_allowed": "TEXT",
        "roof_slope_min_deg": "NUMERIC(5,2)",
        "roof_slope_max_deg": "NUMERIC(5,2)",
        "ridge_direction_required": "TEXT",
        "roof_cover_material_limits": "TEXT",
        "facade_roof_color_limits": "TEXT",
        "parking_required_info": "TEXT",
        "parking_spaces_per_unit": "NUMERIC(10,2)",
        "parking_spaces_per_100sqm_services": "NUMERIC(10,2)",
        "parking_disability_requirement": "TEXT",
        "conservation_protection_zone": "TEXT",
        "nature_protection_zone": "TEXT",
        "noise_emission_limits": "TEXT",
        "parcel_tab_id": "INTEGER",
    }

    with engine.begin() as connection:
        for column_name, column_type in desired_columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE mpzp_conditions ADD COLUMN {column_name} {column_type}"))

    _drop_legacy_mpzp_project_unique_constraint_if_needed()


    if not inspector.has_table("parcel_tabs"):
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE parcel_tabs (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES projects_v2(id) ON DELETE CASCADE,
                    label VARCHAR(120) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_parcel_tabs_project_id ON parcel_tabs(project_id)"))

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


def _drop_legacy_mpzp_project_unique_constraint_if_needed() -> None:
    inspector = inspect(engine)
    if not inspector.has_table("mpzp_conditions"):
        return

    if DATABASE_URL.startswith("sqlite"):
        _drop_legacy_mpzp_project_unique_constraint_sqlite()
        return

    if DATABASE_URL.startswith("postgres"):
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE mpzp_conditions DROP CONSTRAINT IF EXISTS mpzp_conditions_project_id_key"))


def _drop_legacy_mpzp_project_unique_constraint_sqlite() -> None:
    with engine.begin() as connection:
        indexes = connection.execute(text("PRAGMA index_list('mpzp_conditions')")).mappings().all()
        has_legacy_unique = False
        for index in indexes:
            if not index.get("unique"):
                continue
            index_name = index.get("name")
            if not index_name:
                continue
            index_columns = connection.execute(text(f"PRAGMA index_info('{index_name}')")).mappings().all()
            names = [column.get("name") for column in index_columns]
            if names == ["project_id"]:
                has_legacy_unique = True
                break

        if not has_legacy_unique:
            return

        table_info = connection.execute(text("PRAGMA table_info('mpzp_conditions')")).mappings().all()
        if not table_info:
            return

        column_defs = []
        column_names = []
        for column in table_info:
            name = column["name"]
            col_type = column["type"] or ""
            default = column["dflt_value"]
            not_null = bool(column["notnull"])
            is_pk = bool(column["pk"])

            definition = f'"{name}" {col_type}'.strip()
            if is_pk:
                definition += " PRIMARY KEY"
            elif not_null:
                definition += " NOT NULL"
            if default is not None:
                definition += f" DEFAULT {default}"
            column_defs.append(definition)
            column_names.append(f'"{name}"')

        columns_sql = ", ".join(column_defs)
        select_columns_sql = ", ".join(column_names)
        connection.execute(text("ALTER TABLE mpzp_conditions RENAME TO mpzp_conditions_legacy_unique"))
        connection.execute(text(f"CREATE TABLE mpzp_conditions ({columns_sql})"))
        connection.execute(
            text(
                f"INSERT INTO mpzp_conditions ({select_columns_sql}) "
                f"SELECT {select_columns_sql} FROM mpzp_conditions_legacy_unique"
            )
        )
        connection.execute(text("DROP TABLE mpzp_conditions_legacy_unique"))


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
