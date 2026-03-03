import importlib
import os

from sqlalchemy import text


def test_ensure_mpzp_identification_columns_backfills_legacy_schema(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    import config.database as database

    importlib.reload(database)

    with database.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE mpzp_conditions (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER UNIQUE,
                    max_height NUMERIC(10,2)
                )
                """
            )
        )

    database.ensure_mpzp_identification_columns()

    inspector = database.inspect(database.engine)
    columns = {column["name"] for column in inspector.get_columns("mpzp_conditions")}

    assert "plot_number" in columns
    assert "cadastral_district" in columns
    assert "street" in columns
    assert "city" in columns
    assert "land_use_primary" in columns
    assert "land_use_allowed" in columns
    assert "land_use_forbidden" in columns
    assert "services_allowed" in columns
    assert "nuisance_services_forbidden" in columns


def test_ensure_mpzp_identification_columns_removes_legacy_unique_project_constraint(tmp_path):
    db_path = tmp_path / "legacy_unique.sqlite"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    import config.database as database

    importlib.reload(database)

    with database.engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE mpzp_conditions (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER UNIQUE,
                    max_height NUMERIC(10,2)
                )
                """
            )
        )

    database.ensure_mpzp_identification_columns()

    with database.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO mpzp_conditions (id, project_id, max_height, parcel_tab_id)
                VALUES (1, 10, 12.0, 101), (2, 10, 15.0, 102)
                """
            )
        )
        rows = conn.execute(
            text("SELECT id, project_id, parcel_tab_id FROM mpzp_conditions WHERE project_id = 10 ORDER BY id")
        ).fetchall()

    assert rows == [(1, 10, 101), (2, 10, 102)]
