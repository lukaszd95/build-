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
