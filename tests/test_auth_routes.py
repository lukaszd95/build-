import importlib
import os


def _build_client(tmp_path):
    db_path = tmp_path / "auth-v2.sqlite"
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


def test_register_and_login_success(tmp_path):
    client = _build_client(tmp_path)

    register = client.post(
        "/api/auth/register",
        json={"name": "Jan Kowalski", "email": "jan@example.com", "password": "tajne123"},
    )
    assert register.status_code == 201
    assert register.get_json()["user"]["email"] == "jan@example.com"

    login = client.post(
        "/api/auth/login",
        json={"email": "jan@example.com", "password": "tajne123"},
    )
    assert login.status_code == 200
    payload = login.get_json()
    assert payload["user"]["name"] == "Jan Kowalski"


def test_register_duplicate_email(tmp_path):
    client = _build_client(tmp_path)

    payload = {"name": "Jan Kowalski", "email": "dupe@example.com", "password": "tajne123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409


def test_login_invalid_password(tmp_path):
    client = _build_client(tmp_path)

    client.post(
        "/api/auth/register",
        json={"name": "Anna Nowak", "email": "anna@example.com", "password": "tajne123"},
    )

    invalid = client.post(
        "/api/auth/login",
        json={"email": "anna@example.com", "password": "zlehaslo"},
    )
    assert invalid.status_code == 401
