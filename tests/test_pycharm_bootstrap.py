from scripts.pycharm_bootstrap import _resolve_database_url


def test_resolve_database_url_uses_sqlite_by_default():
    assert _resolve_database_url({"DATABASE_URL": "postgresql://user:pass@localhost/db"}) == "sqlite:///data/app.db"


def test_resolve_database_url_can_opt_in_to_env_database_url():
    env = {
        "DATABASE_URL": "postgresql://user:pass@localhost/db",
        "BOOTSTRAP_USE_ENV_DATABASE": "1",
    }
    assert _resolve_database_url(env) == "postgresql://user:pass@localhost/db"
