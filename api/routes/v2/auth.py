import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import bcrypt
except ModuleNotFoundError:  # pragma: no cover
    bcrypt = None
from itsdangerous import BadSignature, BadTimeSignature, SignatureExpired, URLSafeTimedSerializer

try:
    import jwt
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal local setups
    jwt = None

from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from config.database import db_session, engine
from db.models import User

bp = Blueprint("auth_v2", __name__, url_prefix="/api")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "24"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "auth_token")
JWT_DECODE_ERRORS = (jwt.InvalidTokenError,) if jwt is not None else ()


class _InvalidTokenError(Exception):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(JWT_SECRET, salt="auth-token")


def _encode_token(payload: dict) -> str:
    if jwt is not None:
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    payload_without_exp = {k: v for k, v in payload.items() if k != "exp"}
    return _serializer().dumps(payload_without_exp)


def _decode_token(token: str) -> dict:
    if jwt is not None:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    try:
        return _serializer().loads(token, max_age=JWT_TTL_HOURS * 3600)
    except (SignatureExpired, BadTimeSignature, BadSignature) as exc:
        raise _InvalidTokenError from exc


def _token_for_user(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS),
    }
    return _encode_token(payload)


def _serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.full_name,
        "is_admin": bool(user.is_admin),
    }


def _hash_password(password: str) -> str:
    if bcrypt is not None:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return generate_password_hash(password)


def _check_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if bcrypt is not None and password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    return check_password_hash(password_hash, password)


def _build_auth_response(user: User, status_code: int = 200):
    token = _token_for_user(user)
    response = jsonify({"user": _serialize_user(user)})
    response.status_code = status_code
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        secure=False,
        samesite="Lax",
        max_age=JWT_TTL_HOURS * 3600,
        path="/",
    )
    return response


def ensure_default_admin_user() -> None:
    if not inspect(engine).has_table("users"):
        return
    try:
        with db_session() as db:
            admin = db.query(User).filter(User.email == "admin").first()
            if admin:
                if not admin.is_admin:
                    admin.is_admin = True
                    db.flush()
                return

            user = User(
                email="admin",
                password_hash=_hash_password("admin"),
                full_name="Administrator",
                is_admin=True,
            )
            db.add(user)
            db.flush()
    except OperationalError:
        return


def _clear_auth_cookie(response):
    response.set_cookie(AUTH_COOKIE_NAME, "", expires=0, httponly=True, secure=False, samesite="Lax", path="/")


def _extract_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1]
    return request.cookies.get(AUTH_COOKIE_NAME)


def get_current_user_id() -> int | None:
    token = _extract_token()
    if not token:
        return None
    try:
        payload = _decode_token(token)
        return int(payload["sub"])
    except (_InvalidTokenError, KeyError, ValueError, *JWT_DECODE_ERRORS):
        return None


def auth_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        current_user_id = get_current_user_id()
        if not current_user_id:
            return jsonify({"error": "UNAUTHORIZED"}), 401
        g.current_user_id = current_user_id
        return handler(*args, **kwargs)

    return wrapper


@bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = (data.get("name") or data.get("full_name") or data.get("fullName") or "").strip() or None

    if not email or "@" not in email:
        return jsonify({"error": "INVALID_EMAIL"}), 400
    if len(password) < 6:
        return jsonify({"error": "PASSWORD_TOO_SHORT"}), 400

    with db_session() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return jsonify({"error": "EMAIL_ALREADY_EXISTS"}), 409
        user = User(email=email, password_hash=_hash_password(password), full_name=full_name)
        db.add(user)
        db.flush()
        return _build_auth_response(user, status_code=201)


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    raw_identifier = (data.get("email") or data.get("login") or data.get("identifier") or "").strip()
    identifier = raw_identifier.lower()
    password = data.get("password") or ""

    with db_session() as db:
        user = db.query(User).filter(User.email == identifier).first()
        if not user and identifier == "admin":
            user = db.query(User).filter(User.email == "admin", User.is_admin.is_(True)).first()
        if not user or not _check_password(password, user.password_hash):
            return jsonify({"error": "INVALID_CREDENTIALS"}), 401
        return _build_auth_response(user)


@bp.post("/auth/logout")
def logout():
    response = jsonify({"ok": True})
    _clear_auth_cookie(response)
    return response


@bp.get("/auth/me")
@auth_required
def me():
    with db_session() as db:
        user = db.query(User).filter(User.id == g.current_user_id).first()
        if not user:
            return jsonify({"error": "NOT_FOUND"}), 404
        return jsonify({"user": _serialize_user(user)})
