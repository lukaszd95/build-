import importlib
import os


def _bootstrap_app(tmp_path):
    db_path = tmp_path / "auth_flow.sqlite"
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


def test_auth_cookie_me_and_logout(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    register_res = client.post("/api/auth/register", json={"email": "user@a.pl", "password": "secret12", "name": "Jan"})
    assert register_res.status_code == 201
    assert "auth_token=" in (register_res.headers.get("Set-Cookie") or "")

    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.get_json()["user"]["email"] == "user@a.pl"

    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200

    me_after_logout = client.get("/api/auth/me")
    assert me_after_logout.status_code == 401


def test_projects_page_requires_auth(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    projects_res = client.get("/projects", follow_redirects=False)
    assert projects_res.status_code == 302
    assert projects_res.headers["Location"].endswith("/login")


def test_projects_page_redirects_to_existing_workspace_panel(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    register_res = client.post("/api/auth/register", json={"email": "flow@a.pl", "password": "secret12"})
    assert register_res.status_code == 201

    projects_res = client.get("/projects", follow_redirects=False)
    assert projects_res.status_code == 302
    assert projects_res.headers["Location"].endswith("/app?open=projects")


def test_app_workspace_requires_auth(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    response = client.get("/app", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_app_workspace_bootstraps_authenticated_user_and_projects(tmp_path):
    app = _bootstrap_app(tmp_path)
    client = app.test_client()

    register_res = client.post(
        "/api/auth/register",
        json={"email": "jan@a.pl", "password": "secret12", "name": "Jan Kowalski"},
    )
    assert register_res.status_code == 201

    create_res = client.post("/api/projects", json={"name": "Projekt użytkownika"})
    assert create_res.status_code == 201

    workspace_res = client.get("/app")
    body = workspace_res.get_data(as_text=True)

    assert workspace_res.status_code == 200
    assert '"email": "jan@a.pl"' in body
    assert '"name": "Jan Kowalski"' in body
    assert 'const bootstrapProjects = [{"id": 1,' in body
    assert '"name": "Projekt u\\u017cytkownika"' in body
