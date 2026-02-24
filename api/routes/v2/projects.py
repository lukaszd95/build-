from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.utils import secure_filename

from config.database import db_session
from db.models import CostEstimate, CostItem, DesignAsset, MPZPConditions, Project
from .auth import auth_required

bp = Blueprint("projects_v2", __name__, url_prefix="/api")


def _project_query(db):
    return db.query(Project).filter(Project.user_id == g.current_user_id, Project.deleted_at.is_(None))


def _serialize_project(project: Project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _project_or_404(db, project_id: int):
    project = _project_query(db).filter(Project.id == project_id).first()
    if not project:
        return None, (jsonify({"error": "NOT_FOUND"}), 404)
    return project, None


@bp.get("/projects")
@auth_required
def list_projects():
    with db_session() as db:
        projects = _project_query(db).order_by(Project.created_at.desc()).all()
        return jsonify([_serialize_project(item) for item in projects])


@bp.post("/projects")
@auth_required
def create_project():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "NAME_REQUIRED"}), 400

    with db_session() as db:
        project = Project(user_id=g.current_user_id, name=name, description=payload.get("description"), status=payload.get("status") or "draft")
        db.add(project)
        db.flush()
        return jsonify(_serialize_project(project)), 201


@bp.get("/projects/<int:project_id>")
@auth_required
def get_project(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        return jsonify(_serialize_project(project))


@bp.patch("/projects/<int:project_id>")
@auth_required
def update_project(project_id: int):
    payload = request.get_json(silent=True) or {}
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        if "name" in payload:
            project.name = (payload.get("name") or project.name).strip()
        if "description" in payload:
            project.description = payload.get("description")
        if "status" in payload:
            project.status = payload.get("status") or project.status
        db.flush()
        return jsonify(_serialize_project(project))


@bp.delete("/projects/<int:project_id>")
@auth_required
def delete_project(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        project.deleted_at = datetime.now(timezone.utc)
        db.flush()
        return jsonify({"ok": True})


@bp.get("/projects/<int:project_id>/mpzp")
@bp.post("/projects/<int:project_id>/mpzp")
@bp.patch("/projects/<int:project_id>/mpzp")
@auth_required
def upsert_mpzp(project_id: int):
    payload = request.get_json(silent=True) or {}
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        mpzp = project.mpzp_conditions or MPZPConditions(project_id=project.id)
        for field in [
            "max_height", "max_area", "building_line", "roof_angle", "biologically_active_area", "allowed_functions",
            "parking_min", "intensity_min", "intensity_max", "frontage_min", "floors_max", "basement_allowed", "extra_data",
        ]:
            if field in payload:
                setattr(mpzp, field, payload.get(field))
        if project.mpzp_conditions is None:
            db.add(mpzp)
        db.flush()
        return jsonify({"id": mpzp.id, "project_id": mpzp.project_id, **{f: getattr(mpzp, f) for f in payload.keys() if hasattr(mpzp, f)}})


@bp.delete("/projects/<int:project_id>/mpzp")
@auth_required
def delete_mpzp(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        if project.mpzp_conditions:
            db.delete(project.mpzp_conditions)
        return jsonify({"ok": True})


@bp.get("/projects/<int:project_id>/cost-estimate")
@auth_required
def get_estimate(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        estimate = project.cost_estimate
        if not estimate:
            return jsonify({"items": [], "summary": None})
        items = [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "total": float(item.total),
            }
            for item in estimate.items
        ]
        return jsonify({
            "id": estimate.id,
            "currency": estimate.currency,
            "net_total": float(estimate.net_total),
            "gross_total": float(estimate.gross_total),
            "contingency_pct": float(estimate.contingency_pct) if estimate.contingency_pct is not None else None,
            "items": items,
        })


@bp.post("/projects/<int:project_id>/cost-estimate/items")
@auth_required
def create_cost_item(project_id: int):
    payload = request.get_json(silent=True) or {}
    required = ["name", "category", "unit", "quantity", "unit_price"]
    if any(payload.get(key) in (None, "") for key in required):
        return jsonify({"error": "INVALID_PAYLOAD"}), 400

    qty = Decimal(str(payload["quantity"]))
    unit_price = Decimal(str(payload["unit_price"]))
    total = Decimal(str(payload.get("total"))) if payload.get("total") is not None else qty * unit_price

    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        estimate = project.cost_estimate
        if not estimate:
            estimate = CostEstimate(project_id=project.id)
            db.add(estimate)
            db.flush()
        item = CostItem(
            estimate_id=estimate.id,
            name=payload["name"],
            category=payload["category"],
            unit=payload["unit"],
            quantity=qty,
            unit_price=unit_price,
            total=total,
        )
        db.add(item)
        estimate.net_total = (estimate.net_total or 0) + total
        estimate.gross_total = estimate.net_total
        db.flush()
        return jsonify({"id": item.id, "total": float(item.total)}), 201


@bp.patch("/projects/<int:project_id>/cost-estimate/items/<int:item_id>")
@auth_required
def update_cost_item(project_id: int, item_id: int):
    payload = request.get_json(silent=True) or {}
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        estimate = project.cost_estimate
        if not estimate:
            return jsonify({"error": "NOT_FOUND"}), 404
        item = db.query(CostItem).filter(CostItem.id == item_id, CostItem.estimate_id == estimate.id).first()
        if not item:
            return jsonify({"error": "NOT_FOUND"}), 404
        for field in ["name", "category", "unit"]:
            if field in payload:
                setattr(item, field, payload.get(field))
        if "quantity" in payload:
            item.quantity = Decimal(str(payload["quantity"]))
        if "unit_price" in payload:
            item.unit_price = Decimal(str(payload["unit_price"]))
        item.total = item.quantity * item.unit_price
        estimate.net_total = sum(Decimal(str(i.total)) for i in estimate.items)
        estimate.gross_total = estimate.net_total
        db.flush()
        return jsonify({"id": item.id, "total": float(item.total)})


@bp.delete("/projects/<int:project_id>/cost-estimate/items/<int:item_id>")
@auth_required
def delete_cost_item(project_id: int, item_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        estimate = project.cost_estimate
        if not estimate:
            return jsonify({"error": "NOT_FOUND"}), 404
        item = db.query(CostItem).filter(CostItem.id == item_id, CostItem.estimate_id == estimate.id).first()
        if not item:
            return jsonify({"error": "NOT_FOUND"}), 404
        db.delete(item)
        db.flush()
        estimate.net_total = sum(Decimal(str(i.total)) for i in estimate.items)
        estimate.gross_total = estimate.net_total
        return jsonify({"ok": True})


@bp.get("/projects/<int:project_id>/design-assets")
@auth_required
def list_assets(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        rows = db.query(DesignAsset).filter(DesignAsset.project_id == project.id, DesignAsset.deleted_at.is_(None)).all()
        return jsonify([
            {
                "id": row.id,
                "dimension": row.dimension,
                "kind": row.kind,
                "file_path": row.file_path,
                "version": row.version,
                "status": row.status,
                "is_current": row.is_current,
            }
            for row in rows
        ])


@bp.post("/projects/<int:project_id>/design-assets")
@auth_required
def create_asset(project_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err

        dimension = request.form.get("dimension")
        kind = request.form.get("kind") or "generic"
        version = int(request.form.get("version") or 1)
        status = request.form.get("status") or "draft"
        upload = request.files.get("file")
        if dimension not in {"2D", "3D"} or not upload:
            return jsonify({"error": "INVALID_PAYLOAD"}), 400

        filename = secure_filename(upload.filename or "asset.bin")
        folder = Path(current_app.config.get("ASSET_UPLOAD_FOLDER", "uploads/assets")) / str(project.id)
        folder.mkdir(parents=True, exist_ok=True)
        target_path = folder / filename
        upload.save(target_path)

        db.query(DesignAsset).filter(
            DesignAsset.project_id == project.id,
            DesignAsset.dimension == dimension,
            DesignAsset.is_current.is_(True),
        ).update({"is_current": False})

        asset = DesignAsset(
            project_id=project.id,
            dimension=dimension,
            kind=kind,
            file_path=str(target_path),
            version=version,
            status=status,
            is_current=True,
        )
        db.add(asset)
        db.flush()
        return jsonify({"id": asset.id, "file_path": asset.file_path}), 201


@bp.delete("/projects/<int:project_id>/design-assets/<int:asset_id>")
@auth_required
def delete_asset(project_id: int, asset_id: int):
    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        asset = db.query(DesignAsset).filter(DesignAsset.project_id == project.id, DesignAsset.id == asset_id).first()
        if not asset:
            return jsonify({"error": "NOT_FOUND"}), 404
        asset.deleted_at = datetime.now(timezone.utc)
        return jsonify({"ok": True})
