import sqlite3
import io

from app import create_app


def build_test_client(tmp_path):
    upload_dir = tmp_path / "uploads"
    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": str(tmp_path / "test.db"),
            "DOCUMENT_UPLOAD_FOLDER": str(upload_dir),
            "DOCUMENT_MAX_SIZE_MB": 1,
        }
    )
    return app.test_client()


def test_document_upload_validation(tmp_path):
    client = build_test_client(tmp_path)
    data = {
        "file": (io.BytesIO(b"not allowed"), "bad.txt"),
        "type": "MPZP_WYPIS",
    }
    response = client.post("/api/documents", data=data, content_type="multipart/form-data")
    assert response.status_code == 400


def test_document_save_fields_and_preview(tmp_path):
    client = build_test_client(tmp_path)
    payload = {
        "file": (io.BytesIO(b"%PDF-1.4 test"), "wypis.pdf"),
        "type": "MPZP_WYPIS",
    }
    upload_response = client.post(
        "/api/documents",
        data=payload,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 201
    document_id = upload_response.get_json()["documentId"]

    fields_payload = {
        "parcelId": "12/3",
        "fields": {
            "przeznaczenie_podstawowe": "MN",
            "max_wysokosc": {"value": 10, "unit": "m"},
        }
    }
    save_response = client.post(
        f"/api/documents/{document_id}/data",
        json=fields_payload,
    )
    assert save_response.status_code == 200

    detail_response = client.get(f"/api/documents/{document_id}")
    data = detail_response.get_json()
    assert data["extractedData"][0]["fields"]["przeznaczenie_podstawowe"] == "MN"

    preview_response = client.get(f"/api/documents/{document_id}/file")
    assert preview_response.status_code == 200


def test_document_save_fields_syncs_mpzp_to_project_plot_parameters(tmp_path):
    client = build_test_client(tmp_path)
    payload = {
        "file": (io.BytesIO(b"%PDF-1.4 test"), "wypis.pdf"),
        "type": "MPZP_WYPIS",
    }
    upload_response = client.post(
        "/api/documents",
        data=payload,
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 201
    document_id = upload_response.get_json()["documentId"]

    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        now = "2026-01-01T10:00:00Z"
        conn.execute(
            """
            INSERT INTO projects (code, name, createdAt, updatedAt)
            VALUES (?, ?, ?, ?)
            """,
            ("PRJ-MPZP-1", "Projekt MPZP", now, now),
        )
        project_id = conn.execute("SELECT id FROM projects WHERE code = ?", ("PRJ-MPZP-1",)).fetchone()[0]
        conn.execute(
            """
            INSERT INTO project_plots (projectId, parcelId, externalParcelRef, createdAt)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, "12/3", "12/3", now),
        )
        conn.commit()

    save_response = client.post(
        f"/api/documents/{document_id}/data",
        json={
            "parcelId": "12/3",
            "projectId": project_id,
            "fields": {
                "przeznaczenie_podstawowe": "MN",
                "max_wysokosc": {"value": 10, "unit": "m"},
            },
        },
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["projectPlotParametersSynced"] == 2

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT key, value, valueType FROM project_plot_parameters
            ORDER BY key ASC
            """
        ).fetchall()

    assert rows[0][0] == "mpzp.max_wysokosc"
    assert rows[0][2] == "JSON"
    assert rows[1][0] == "mpzp.przeznaczenie_podstawowe"
    assert rows[1][1] == "MN"


def test_document_save_fields_uses_demo_project_when_project_id_missing(tmp_path):
    client = build_test_client(tmp_path)
    payload = {
        "file": (io.BytesIO(b"%PDF-1.4 test"), "wypis.pdf"),
        "type": "MPZP_WYPIS",
    }
    upload_response = client.post(
        "/api/documents",
        data=payload,
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documentId"]

    save_response = client.post(
        f"/api/documents/{document_id}/data",
        json={
            "parcelId": "_global",
            "fields": {
                "przeznaczenie_podstawowe": "MN",
                "min_pow_biol_czynna": {"value": 40, "unit": "%"},
            },
        },
    )
    assert save_response.status_code == 200
    assert save_response.get_json()["projectPlotParametersSynced"] == 2

    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT key, valueType FROM project_plot_parameters
            WHERE key IN ('mpzp.przeznaczenie_podstawowe', 'mpzp.min_pow_biol_czynna')
            ORDER BY key ASC
            """
        ).fetchall()

    assert rows[0][0] == "mpzp.min_pow_biol_czynna"
    assert rows[0][1] == "JSON"
    assert rows[1][0] == "mpzp.przeznaczenie_podstawowe"
    assert rows[1][1] == "TEXT"


def test_demo_project_endpoint_returns_and_updates_demo_project(tmp_path):
    client = build_test_client(tmp_path)

    get_response = client.get("/api/projects/demo")
    assert get_response.status_code == 200
    payload = get_response.get_json()
    assert payload["project"]["code"] == "DEMO"
    assert len(payload["plots"]) >= 1

    patch_response = client.patch(
        "/api/projects/demo",
        json={
            "name": "Projekt demo edytowany",
            "investorName": "Nowy inwestor",
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.get_json()
    assert patched["project"]["name"] == "Projekt demo edytowany"
    assert patched["project"]["investorName"] == "Nowy inwestor"


def test_parcel_geometry_is_saved_to_demo_project_plot(tmp_path):
    client = build_test_client(tmp_path)

    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 0], [10, 8], [0, 8], [0, 0]]],
    }
    create_response = client.post(
        "/api/parcels",
        json={"parcelId": "99/7", "geometry": geometry},
    )
    assert create_response.status_code == 201

    demo_response = client.get("/api/projects/demo")
    assert demo_response.status_code == 200
    payload = demo_response.get_json()

    plot = next((item for item in payload["plots"] if item["parcelId"] == "99/7"), None)
    assert plot is not None
    assert plot["geometry"]["type"] == "Polygon"
    assert plot["geometry"]["coordinates"][0][0] == [0, 0]
