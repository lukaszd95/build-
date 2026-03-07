import importlib
import os


def _build_client(tmp_path):
    db_path = tmp_path / "admin.sqlite"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["JWT_SECRET"] = "test-secret"

    import config.database as database
    import db.models as models
    import app as app_module

    importlib.reload(database)
    importlib.reload(models)
    importlib.reload(app_module)

    database.Base.metadata.create_all(database.engine)
    app = app_module.create_app({"TESTING": True})
    return app.test_client()


def test_default_admin_account_created_and_can_login(tmp_path):
    client = _build_client(tmp_path)

    login = client.post("/api/auth/login", json={"login": "admin", "password": "admin"})
    assert login.status_code == 200
    payload = login.get_json()
    assert payload["user"]["email"] == "admin"
    assert payload["user"]["is_admin"] is True


def test_admin_overview_requires_admin_role(tmp_path):
    client = _build_client(tmp_path)

    client.post(
        "/api/auth/register",
        json={"name": "U1", "email": "user1@example.com", "password": "tajne123"},
    )
    response = client.get("/api/admin/overview")
    assert response.status_code == 403


def test_admin_overview_returns_metrics(tmp_path):
    client = _build_client(tmp_path)

    client.post("/api/auth/login", json={"login": "admin", "password": "admin"})
    response = client.get("/api/admin/overview")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["metrics"]["users_count"] >= 1
    assert payload["metrics"]["admins_count"] >= 1
    assert isinstance(payload["users"], list)
    assert isinstance(payload["projects"], list)
