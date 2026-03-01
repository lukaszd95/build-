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
