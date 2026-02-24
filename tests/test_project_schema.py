import sqlite3

import pytest
from flask import Flask

from utils.db import init_db


def test_project_management_tables_are_created(tmp_path):
    app = Flask(__name__)
    db_path = tmp_path / "schema.db"
    app.config["DB_PATH"] = str(db_path)

    init_db(app)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "projects" in tables
    assert "project_plots" in tables
    assert "project_plot_parameters" in tables
    assert "project_files" in tables
    assert "project_requirements" in tables
    assert "cost_estimates" in tables
    assert "cost_estimate_items" in tables
    assert "project_designs" in tables


def test_project_plots_external_reference_is_unique_per_project(tmp_path):
    app = Flask(__name__)
    db_path = tmp_path / "schema.db"
    app.config["DB_PATH"] = str(db_path)

    init_db(app)

    with sqlite3.connect(db_path) as conn:
        now = "2026-01-01T10:00:00Z"
        conn.execute(
            """
            INSERT INTO projects (code, name, createdAt, updatedAt)
            VALUES (?, ?, ?, ?)
            """,
            ("PRJ-001", "Osiedle testowe", now, now),
        )
        project_id = conn.execute("SELECT id FROM projects WHERE code = ?", ("PRJ-001",)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO project_plots (projectId, externalParcelRef, createdAt)
            VALUES (?, ?, ?)
            """,
            (project_id, "123/4", now),
        )

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO project_plots (projectId, externalParcelRef, createdAt)
                VALUES (?, ?, ?)
                """,
                (project_id, "123/4", now),
            )


def test_demo_project_is_seeded_with_default_plot(tmp_path):
    app = Flask(__name__)
    db_path = tmp_path / "schema.db"
    app.config["DB_PATH"] = str(db_path)

    init_db(app)

    with sqlite3.connect(db_path) as conn:
        demo = conn.execute(
            "SELECT id, code, name FROM projects WHERE code = ?",
            ("DEMO",),
        ).fetchone()
        assert demo is not None
        plot = conn.execute(
            "SELECT parcelId, externalParcelRef FROM project_plots WHERE projectId = ?",
            (demo[0],),
        ).fetchone()

    assert plot is not None
    assert plot[0] == "_global"
    assert plot[1] == "_global"
