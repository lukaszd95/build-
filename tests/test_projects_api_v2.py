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


def test_mpzp_building_parameters_patch_and_get_persist_in_same_record(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp7@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt parametry"})
    project_id = create_res.get_json()["id"]

    patch_res = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "plot_number": "9/1",
            "max_building_height": "12,5",
            "max_storeys_above": 3,
            "max_storeys_below": 1,
            "max_ridge_height": 11.2,
            "max_eaves_height": 7.4,
            "min_building_intensity": 0.2,
            "max_building_intensity": 1.4,
            "max_building_coverage": 45,
            "min_biologically_active_share": 35,
            "min_front_elevation_width": 10,
            "max_front_elevation_width": 18,
        },
    )
    assert patch_res.status_code == 200
    payload = patch_res.get_json()
    assert payload["plot_number"] == "9/1"
    assert payload["max_building_height"] == 12.5
    assert payload["max_storeys_above"] == 3

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    assert refetched.status_code == 200
    body = refetched.get_json()
    assert body["plot_number"] == "9/1"
    assert body["max_storeys_below"] == 1
    assert body["max_ridge_height"] == 11.2
    assert body["max_eaves_height"] == 7.4
    assert body["min_building_intensity"] == 0.2
    assert body["max_building_intensity"] == 1.4
    assert body["max_building_coverage"] == 45.0
    assert body["min_biologically_active_share"] == 35.0
    assert body["min_front_elevation_width"] == 10.0
    assert body["max_front_elevation_width"] == 18.0


def test_mpzp_building_parameters_validation(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp8@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt walidacji parametrow"})
    project_id = create_res.get_json()["id"]

    bad_storeys = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"max_storeys_above": -1},
    )
    assert bad_storeys.status_code == 400
    assert bad_storeys.get_json()["error"] == "NEGATIVE_INTEGER"

    bad_share = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"min_biologically_active_share": 120},
    )
    assert bad_share.status_code == 400
    assert bad_share.get_json()["error"] == "VALUE_OUT_OF_RANGE"


def test_mpzp_roof_architecture_patch_and_get_persist_in_same_record(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp9@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt dach"})
    project_id = create_res.get_json()["id"]

    patch_res = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "plot_number": "15/2",
            "roof_type_allowed": "Dwuspadowy",
            "roof_slope_min_deg": "25,5",
            "roof_slope_max_deg": 45,
            "ridge_direction_required": "Równoległy do drogi",
            "roof_cover_material_limits": "Dachówka",
            "facade_roof_color_limits": "Kolory stonowane",
        },
    )
    assert patch_res.status_code == 200
    payload = patch_res.get_json()
    assert payload["plot_number"] == "15/2"
    assert payload["roof_type_allowed"] == "Dwuspadowy"
    assert payload["roof_slope_min_deg"] == 25.5
    assert payload["roof_slope_max_deg"] == 45.0

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    assert refetched.status_code == 200
    body = refetched.get_json()
    assert body["plot_number"] == "15/2"
    assert body["roof_type_allowed"] == "Dwuspadowy"
    assert body["roof_slope_min_deg"] == 25.5
    assert body["roof_slope_max_deg"] == 45.0
    assert body["ridge_direction_required"] == "Równoległy do drogi"
    assert body["roof_cover_material_limits"] == "Dachówka"
    assert body["facade_roof_color_limits"] == "Kolory stonowane"


def test_mpzp_roof_architecture_validation(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp10@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt dach walidacja"})
    project_id = create_res.get_json()["id"]

    bad_angle = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"roof_slope_max_deg": 120},
    )
    assert bad_angle.status_code == 400
    assert bad_angle.get_json()["error"] == "VALUE_OUT_OF_RANGE"

    too_long_text = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"roof_cover_material_limits": "x" * 2001},
    )
    assert too_long_text.status_code == 400
    assert too_long_text.get_json()["error"] == "FIELD_TOO_LONG"


def test_mpzp_parking_and_environment_patch_and_get_persist_in_same_record(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp11@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt parking srodowisko"})
    project_id = create_res.get_json()["id"]

    parking_update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "parking_required_info": "Minimum 2 miejsca",
            "parking_spaces_per_unit": "1,5",
            "parking_spaces_per_100sqm_services": 3,
            "parking_disability_requirement": "Wymagane zgodnie z przepisami",
        },
    )
    assert parking_update.status_code == 200

    environment_update = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={
            "conservation_protection_zone": "Brak",
            "nature_protection_zone": "Poza strefą",
            "noise_emission_limits": "Normy dla zabudowy mieszkaniowej",
            "min_biologically_active_share": 45,
        },
    )
    assert environment_update.status_code == 200

    payload = environment_update.get_json()
    assert payload["parking_required_info"] == "Minimum 2 miejsca"
    assert payload["parking_spaces_per_unit"] == 1.5
    assert payload["parking_spaces_per_100sqm_services"] == 3.0
    assert payload["conservation_protection_zone"] == "Brak"
    assert payload["min_biologically_active_share"] == 45.0

    refetched = client.get(f"/api/projects/{project_id}/mpzp")
    assert refetched.status_code == 200
    body = refetched.get_json()
    assert body["parking_disability_requirement"] == "Wymagane zgodnie z przepisami"
    assert body["nature_protection_zone"] == "Poza strefą"
    assert body["noise_emission_limits"] == "Normy dla zabudowy mieszkaniowej"


def test_mpzp_parking_and_environment_validation(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "mpzp12@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt parking walidacja"})
    project_id = create_res.get_json()["id"]

    bad_parking = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"parking_spaces_per_unit": -1},
    )
    assert bad_parking.status_code == 400
    assert bad_parking.get_json()["error"] == "NEGATIVE_NUMBER"

    bad_text = client.patch(
        f"/api/projects/{project_id}/mpzp",
        json={"noise_emission_limits": "x" * 2001},
    )
    assert bad_text.status_code == 400
    assert bad_text.get_json()["error"] == "FIELD_TOO_LONG"


def test_parcel_tabs_have_isolated_mpzp_conditions(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "tabs1@a.pl", "password": "secret1"}).status_code == 201
    create_res = client.post("/api/projects", json={"name": "Projekt tabs"})
    assert create_res.status_code == 201
    project_id = create_res.get_json()["id"]

    tabs_res = client.get(f"/api/projects/{project_id}/parcel-tabs")
    assert tabs_res.status_code == 200
    first_tab = tabs_res.get_json()[0]

    second_tab_res = client.post(f"/api/projects/{project_id}/parcel-tabs", json={"label": "136/1"})
    assert second_tab_res.status_code == 201
    second_tab = second_tab_res.get_json()["tab"]

    update_first = client.patch(f"/api/parcel-tabs/{first_tab['id']}/mpzp-conditions", json={"plot_number": "138/1", "city": "A"})
    assert update_first.status_code == 200
    update_second = client.patch(f"/api/parcel-tabs/{second_tab['id']}/mpzp-conditions", json={"plot_number": "136/1", "city": "B"})
    assert update_second.status_code == 200

    fetched_first = client.get(f"/api/parcel-tabs/{first_tab['id']}/mpzp-conditions")
    fetched_second = client.get(f"/api/parcel-tabs/{second_tab['id']}/mpzp-conditions")
    assert fetched_first.status_code == 200
    assert fetched_second.status_code == 200
    assert fetched_first.get_json()["city"] == "A"
    assert fetched_second.get_json()["city"] == "B"


def test_legacy_project_mpzp_endpoint_maps_to_default_parcel_tab(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    assert client.post("/api/auth/register", json={"email": "tabs2@a.pl", "password": "secret1"}).status_code == 201
    project_res = client.post("/api/projects", json={"name": "Legacy"})
    project_id = project_res.get_json()["id"]

    patched = client.patch(f"/api/projects/{project_id}/mpzp", json={"city": "Warszawa"})
    assert patched.status_code == 200

    tabs_res = client.get(f"/api/projects/{project_id}/parcel-tabs")
    tab_id = tabs_res.get_json()[0]["id"]
    fetched = client.get(f"/api/parcel-tabs/{tab_id}/mpzp-conditions")
    assert fetched.status_code == 200
    assert fetched.get_json()["city"] == "Warszawa"
