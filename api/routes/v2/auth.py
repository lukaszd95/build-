import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, g, jsonify, request
from itsdangerous import BadSignature, BadTimeSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

try:
    import jwt
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal local setups
    jwt = None

from config.database import db_session
from db.models import User

bp = Blueprint("auth_v2", __name__, url_prefix="/api")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
JWT_TTL_HOURS = int(os.getenv("JWT_TTL_HOURS", "24"))
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


def auth_required(handler):
    @wraps(handler)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "UNAUTHORIZED"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = _decode_token(token)
            g.current_user_id = int(payload["sub"])
        except (_InvalidTokenError, KeyError, ValueError, *JWT_DECODE_ERRORS):
            return jsonify({"error": "UNAUTHORIZED"}), 401
        return handler(*args, **kwargs)

    return wrapper


@bp.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    full_name = data.get("full_name")

    if not email or len(password) < 6:
        return jsonify({"error": "INVALID_PAYLOAD"}), 400

    with db_session() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            return jsonify({"error": "EMAIL_ALREADY_EXISTS"}), 409
        user = User(email=email, password_hash=generate_password_hash(password), full_name=full_name)
        db.add(user)
        db.flush()
        token = _token_for_user(user)

    return jsonify({"token": token, "user": {"id": user.id, "email": user.email, "full_name": user.full_name}}), 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    with db_session() as db:
        user = db.query(User).filter(User.email == email).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({"error": "INVALID_CREDENTIALS"}), 401
        token = _token_for_user(user)
        return jsonify({"token": token, "user": {"id": user.id, "email": user.email, "full_name": user.full_name}})


@bp.get("/users/me")
@auth_required
def me():
    with db_session() as db:
        user = db.query(User).filter(User.id == g.current_user_id).first()
        if not user:
            return jsonify({"error": "NOT_FOUND"}), 404
        return jsonify({"id": user.id, "email": user.email, "full_name": user.full_name, "created_at": user.created_at.isoformat()})
