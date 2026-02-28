from config.database import _normalize_database_url


def test_normalize_database_url_keeps_sqlite_unchanged():
    assert _normalize_database_url("sqlite:///data/app.db") == "sqlite:///data/app.db"


def test_normalize_database_url_encodes_postgres_credentials():
    raw = "postgresql://użytkownik:h@sło@localhost:5432/mydb"
    normalized = _normalize_database_url(raw)
    assert normalized == "postgresql://u%C5%BCytkownik:h%40s%C5%82o@localhost:5432/mydb"


def test_normalize_database_url_handles_wrapping_quotes():
    raw = "'postgres://user:pa ss@localhost/db'"
    normalized = _normalize_database_url(raw)
    assert normalized == "postgres://user:pa%20ss@localhost/db"


def test_normalize_database_url_repairs_non_utf8_percent_encoding():
    raw = "postgresql://user:has%B3o@localhost:5432/mydb"
    normalized = _normalize_database_url(raw)
    assert normalized == "postgresql://user:has%C5%82o@localhost:5432/mydb"
