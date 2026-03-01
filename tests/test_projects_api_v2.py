import importlib
import os


def _bootstrap_app(tmp_path):
    db_path = tmp_path / "v2.sqlite"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret"

    import config.database as database
    import db.models as models
    import app as app_module

    importlib.reload(database)
    importlib.reload(models)
    importlib.reload(app_module)

    database.Base.metadata.create_all(database.engine)
    return app_module.create_app({"TESTING": True})


def test_project_crud_is_user_scoped(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    register_res = client.post("/api/auth/register", json={"email": "a@a.pl", "password": "secret1"})
    assert register_res.status_code == 201
    create_res = client.post(
        "/api/projects",
        json={"name": "Projekt A"},
    )
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    fetch_res = client.get(f"/api/projects/{project_id}")
    assert fetch_res.status_code == 200
    assert fetch_res.get_json()["name"] == "Projekt A"


def test_projects_require_auth(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    response = client.get("/api/projects")
    assert response.status_code == 401


def test_project_detail_is_scoped_to_owner(tmp_path):
    app = _bootstrap_app(tmp_path)
    client_owner = app.test_client()
    client_other = app.test_client()

    assert client_owner.post("/api/auth/register", json={"email": "owner@a.pl", "password": "secret1"}).status_code == 201
    create_res = client_owner.post("/api/projects", json={"name": "Prywatny projekt"})
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    assert client_other.post("/api/auth/register", json={"email": "other@a.pl", "password": "secret1"}).status_code == 201
    forbidden_res = client_other.get(f"/api/projects/{project_id}")
    assert forbidden_res.status_code == 404


def test_mpzp_identification_is_project_scoped_and_defaults_empty(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp@a.pl", "password": "secret1"}).status_code == 201

    first = client.post("/api/projects", json={"name": "Projekt 1"})
    second = client.post("/api/projects", json={"name": "Projekt 2"})
    assert first.status_code == 201
    assert second.status_code == 201

    first_id = first.get_json()["id"]
    second_id = second.get_json()["id"]

    first_mpzp = client.get(f"/api/projects/{first_id}/mpzp")
    assert first_mpzp.status_code == 200
    assert first_mpzp.get_json()["plot_number"] is None
    assert first_mpzp.get_json()["cadastral_district"] is None
    assert first_mpzp.get_json()["street"] is None
    assert first_mpzp.get_json()["city"] is None

    update_first = client.patch(
        f"/api/projects/{first_id}/mpzp",
        json={
            "plot_number": "12/4",
            "cadastral_district": "0001",
            "street": "Leśna",
            "city": "Warszawa",
        },
    )
    assert update_first.status_code == 200

    first_after = client.get(f"/api/projects/{first_id}/mpzp")
    second_after = client.get(f"/api/projects/{second_id}/mpzp")

    assert first_after.get_json()["plot_number"] == "12/4"
    assert first_after.get_json()["cadastral_district"] == "0001"
    assert first_after.get_json()["street"] == "Leśna"
    assert first_after.get_json()["city"] == "Warszawa"

    assert second_after.get_json()["plot_number"] is None
    assert second_after.get_json()["cadastral_district"] is None
    assert second_after.get_json()["street"] is None
    assert second_after.get_json()["city"] is None


def test_mpzp_identification_normalizes_strings_and_validates_length(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp2@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt 1"})
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    update_ok = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "plot_number": " 12/9 ",
            "cadastral_district": " 0007 ",
            "street": "  Leśna ",
            "city": "  Warszawa ",
        },
    )
    assert update_ok.status_code == 200
    payload = update_ok.get_json()
    assert payload["plot_number"] == "12/9"
    assert payload["cadastral_district"] == "0007"
    assert payload["street"] == "Leśna"
    assert payload["city"] == "Warszawa"

    too_long = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"street": "x" * 256},
    )
    assert too_long.status_code == 400
    assert too_long.get_json()["error"] == "FIELD_TOO_LONG"
    assert too_long.get_json()["field"] == "street"


def test_mpzp_land_use_fields_patch_and_persist(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp3@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt land use"})
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "land_use_primary": "MN",
            "land_use_allowed": "Usługi nieuciążliwe",
            "land_use_forbidden": "Produkcja",
            "services_allowed": True,
            "nuisance_services_forbidden": False,
        },
    )
    assert update.status_code == 200
    payload = update.get_json()
    assert payload["land_use_primary"] == "MN"
    assert payload["land_use_allowed"] == "Usługi nieuciążliwe"
    assert payload["land_use_forbidden"] == "Produkcja"
    assert payload["services_allowed"] is True
    assert payload["nuisance_services_forbidden"] is False

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    assert refetched.status_code == 200
    body = refetched.get_json()
    assert body["land_use_primary"] == "MN"
    assert body["land_use_allowed"] == "Usługi nieuciążliwe"
    assert body["land_use_forbidden"] == "Produkcja"
    assert body["services_allowed"] is True
    assert body["nuisance_services_forbidden"] is False


def test_mpzp_land_use_boolean_validation(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp4@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt walidacja"})
    project_id = create_res.get_json()["id"]

    bad_update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"services_allowed": "yes"},
    )
    assert bad_update.status_code == 400
    assert bad_update.get_json()["error"] == "INVALID_BOOLEAN"
    assert bad_update.get_json()["field"] == "services_allowed"


def test_mpzp_parcel_area_and_land_uses_are_persisted_in_same_record(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp5@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt ewidencja"})
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "plot_number": "11/2",
            "parcelAreaTotal": 1234.56,
            "landUses": [
                {"symbol": "R", "area": 800.0},
                {"symbol": "B", "area": 434.56},
            ],
        },
    )
    assert update.status_code == 200
    payload = update.get_json()
    assert payload["plot_number"] == "11/2"
    assert payload["parcel_area_total"] == 1234.56
    assert payload["land_uses"] == [
        {"id": payload["land_uses"][0]["id"], "symbol": "R", "area": 800.0},
        {"id": payload["land_uses"][1]["id"], "symbol": "B", "area": 434.56},
    ]

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    assert refetched.status_code == 200
    body = refetched.get_json()
    assert body["plot_number"] == "11/2"
    assert body["parcel_area_total"] == 1234.56
    assert [item["symbol"] for item in body["land_uses"]] == ["R", "B"]
    assert [item["area"] for item in body["land_uses"]] == [800.0, 434.56]


def test_mpzp_land_uses_replace_all_and_transaction_rollback_on_validation_error(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp6@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt replace"})
    project_id = create_res.get_json()["id"]

    first_update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "parcel_area_total": 1000,
            "land_uses": [{"symbol": "R", "area": 1000}],
        },
    )
    assert first_update.status_code == 200

    second_update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "parcel_area_total": 500,
            "land_uses": [{"symbol": "X" * 100, "area": 500}],
        },
    )
    assert second_update.status_code == 400
    assert second_update.get_json()["error"] == "FIELD_TOO_LONG"

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    body = refetched.get_json()
    assert body["parcel_area_total"] == 1000.0
    assert body["land_uses"] and body["land_uses"][0]["symbol"] == "R"
    assert body["land_uses"][0]["area"] == 1000.0
