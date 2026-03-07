from functools import wraps

from flask import Blueprint, g, jsonify
from sqlalchemy import func

from config.database import db_session
from db.models import Project, User
from .auth import auth_required

bp = Blueprint("admin_v2", __name__, url_prefix="/api/admin")


def admin_required(handler):
    @auth_required
    @wraps(handler)
    def wrapper(*args, **kwargs):
        with db_session() as db:
            user = db.query(User).filter(User.id == g.current_user_id).first()
            if not user or not user.is_admin:
                return jsonify({"error": "FORBIDDEN"}), 403
            g.current_admin_user = user
        return handler(*args, **kwargs)

    return wrapper


@bp.get("/overview")
@admin_required
def admin_overview():
    with db_session() as db:
        users = db.query(User).order_by(User.created_at.desc()).all()
        projects = db.query(Project).order_by(Project.created_at.desc()).all()

        users_count = db.query(func.count(User.id)).scalar() or 0
        admins_count = db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0
        projects_count = db.query(func.count(Project.id)).scalar() or 0
        active_projects_count = db.query(func.count(Project.id)).filter(Project.deleted_at.is_(None)).scalar() or 0

        return jsonify(
            {
                "metrics": {
                    "users_count": int(users_count),
                    "admins_count": int(admins_count),
                    "projects_count": int(projects_count),
                    "active_projects_count": int(active_projects_count),
                },
                "users": [
                    {
                        "id": user.id,
                        "email": user.email,
                        "full_name": user.full_name,
                        "is_admin": bool(user.is_admin),
                        "created_at": user.created_at.isoformat() if user.created_at else None,
                    }
                    for user in users
                ],
                "projects": [
                    {
                        "id": project.id,
                        "name": project.name,
                        "status": project.status,
                        "user_id": project.user_id,
                        "deleted_at": project.deleted_at.isoformat() if project.deleted_at else None,
                        "created_at": project.created_at.isoformat() if project.created_at else None,
                    }
                    for project in projects
                ],
            }
        )
