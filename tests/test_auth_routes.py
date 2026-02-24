from app import create_app


def _build_client(tmp_path):
    db_path = tmp_path / "auth-test.db"
    app = create_app({"TESTING": True, "DB_PATH": str(db_path)})
    return app.test_client()


def test_register_and_login_success(tmp_path):
    client = _build_client(tmp_path)

    register = client.post(
        "/api/auth/register",
        json={"fullName": "Jan Kowalski", "email": "jan@example.com", "password": "tajne123"},
    )
    assert register.status_code == 201
    assert register.get_json()["user"]["email"] == "jan@example.com"

    login = client.post(
        "/api/auth/login",
        json={"email": "jan@example.com", "password": "tajne123"},
    )
    assert login.status_code == 200
    payload = login.get_json()
    assert payload["ok"] is True
    assert payload["user"]["fullName"] == "Jan Kowalski"


def test_register_duplicate_email(tmp_path):
    client = _build_client(tmp_path)

    payload = {"fullName": "Jan Kowalski", "email": "dupe@example.com", "password": "tajne123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    duplicate = client.post("/api/auth/register", json=payload)
    assert duplicate.status_code == 409


def test_login_invalid_password(tmp_path):
    client = _build_client(tmp_path)

    client.post(
        "/api/auth/register",
        json={"fullName": "Anna Nowak", "email": "anna@example.com", "password": "tajne123"},
    )

    invalid = client.post(
        "/api/auth/login",
        json={"email": "anna@example.com", "password": "zlehaslo"},
    )
    assert invalid.status_code == 401
