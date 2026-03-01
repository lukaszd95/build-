from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.utils import secure_filename

from config.database import db_session
from db.models import CostEstimate, CostItem, DesignAsset, MPZPConditions, MPZPLandUseRegisterItem, Project
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






def _serialize_land_use_item(item: MPZPLandUseRegisterItem):
    return {
        "id": item.id,
        "symbol": item.category_symbol,
        "area": float(item.area),
    }


def _normalize_decimal_non_negative(value, *, field: str):
    if value is None or value == "":
        return None
    normalized = str(value).strip().replace(",", ".")
    try:
        decimal_value = Decimal(normalized).quantize(Decimal("0.01"))
    except Exception as exc:
        raise ValueError(f"INVALID_NUMBER:{field}") from exc
    if decimal_value < 0:
        raise ValueError(f"NEGATIVE_NUMBER:{field}")
    return decimal_value


def _normalize_non_negative_int(value, *, field: str):
    if value is None or value == "":
        return None
    try:
        parsed = int(str(value).strip())
    except Exception as exc:
        raise ValueError(f"INVALID_INTEGER:{field}") from exc
    if parsed < 0:
        raise ValueError(f"NEGATIVE_INTEGER:{field}")
    return parsed


def _normalize_land_uses(raw_land_uses):
    if raw_land_uses is None:
        return None
    if not isinstance(raw_land_uses, list):
        raise ValueError("INVALID_LAND_USES")

    normalized = []
    for index, raw_item in enumerate(raw_land_uses):
        if not isinstance(raw_item, dict):
            raise ValueError(f"INVALID_LAND_USE_ITEM:{index}")
        symbol = str(raw_item.get("symbol") or "").strip()
        if not symbol:
            raise ValueError(f"INVALID_LAND_USE_SYMBOL:{index}")
        if len(symbol) > 64:
            raise ValueError(f"FIELD_TOO_LONG:landUses[{index}].symbol")
        area = _normalize_decimal_non_negative(raw_item.get("area"), field=f"landUses[{index}].area")
        if area is None:
            raise ValueError(f"INVALID_NUMBER:landUses[{index}].area")
        normalized.append({"symbol": symbol, "area": area})
    return normalized

def _serialize_mpzp(mpzp: MPZPConditions):
    return {
        "id": mpzp.id,
        "project_id": mpzp.project_id,
        "plot_number": mpzp.plot_number,
        "cadastral_district": mpzp.cadastral_district,
        "street": mpzp.street,
        "city": mpzp.city,
        "land_use_primary": mpzp.land_use_primary,
        "land_use_allowed": mpzp.land_use_allowed,
        "land_use_forbidden": mpzp.land_use_forbidden,
        "services_allowed": mpzp.services_allowed,
        "nuisance_services_forbidden": mpzp.nuisance_services_forbidden,
        "parcel_area_total": float(mpzp.parcel_area_total) if mpzp.parcel_area_total is not None else None,
        "max_building_height": float(mpzp.max_building_height) if mpzp.max_building_height is not None else None,
        "max_storeys_above": mpzp.max_storeys_above,
        "max_storeys_below": mpzp.max_storeys_below,
        "max_ridge_height": float(mpzp.max_ridge_height) if mpzp.max_ridge_height is not None else None,
        "max_eaves_height": float(mpzp.max_eaves_height) if mpzp.max_eaves_height is not None else None,
        "min_building_intensity": float(mpzp.min_building_intensity) if mpzp.min_building_intensity is not None else None,
        "max_building_intensity": float(mpzp.max_building_intensity) if mpzp.max_building_intensity is not None else None,
        "max_building_coverage": float(mpzp.max_building_coverage) if mpzp.max_building_coverage is not None else None,
        "min_biologically_active_share": float(mpzp.min_biologically_active_share) if mpzp.min_biologically_active_share is not None else None,
        "min_front_elevation_width": float(mpzp.min_front_elevation_width) if mpzp.min_front_elevation_width is not None else None,
        "max_front_elevation_width": float(mpzp.max_front_elevation_width) if mpzp.max_front_elevation_width is not None else None,
        "land_uses": [_serialize_land_use_item(item) for item in sorted(mpzp.land_use_register_items, key=lambda i: i.id)],
        "max_height": float(mpzp.max_height) if mpzp.max_height is not None else None,
        "max_area": float(mpzp.max_area) if mpzp.max_area is not None else None,
        "building_line": mpzp.building_line,
        "roof_angle": float(mpzp.roof_angle) if mpzp.roof_angle is not None else None,
        "biologically_active_area": float(mpzp.biologically_active_area) if mpzp.biologically_active_area is not None else None,
        "allowed_functions": mpzp.allowed_functions,
        "parking_min": mpzp.parking_min,
        "intensity_min": float(mpzp.intensity_min) if mpzp.intensity_min is not None else None,
        "intensity_max": float(mpzp.intensity_max) if mpzp.intensity_max is not None else None,
        "frontage_min": float(mpzp.frontage_min) if mpzp.frontage_min is not None else None,
        "floors_max": mpzp.floors_max,
        "basement_allowed": mpzp.basement_allowed,
        "extra_data": mpzp.extra_data,
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
        db.add(MPZPConditions(project_id=project.id))
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
    if "parcelAreaTotal" in payload and "parcel_area_total" not in payload:
        payload["parcel_area_total"] = payload["parcelAreaTotal"]
    if "landUses" in payload and "land_uses" not in payload:
        payload["land_uses"] = payload["landUses"]

    editable_fields = [
        "plot_number", "cadastral_district", "street", "city", "land_use_primary", "land_use_allowed",
        "land_use_forbidden", "services_allowed", "nuisance_services_forbidden", "land_uses", "parcel_area_total", "max_height", "max_area", "building_line",
        "roof_angle", "biologically_active_area", "allowed_functions", "parking_min", "intensity_min",
        "intensity_max", "frontage_min", "floors_max", "basement_allowed", "extra_data",
        "max_building_height", "max_storeys_above", "max_storeys_below", "max_ridge_height", "max_eaves_height", "min_building_intensity",
        "max_building_intensity", "max_building_coverage", "min_biologically_active_share", "min_front_elevation_width", "max_front_elevation_width",
    ]
    normalized_string_fields = {"plot_number", "cadastral_district", "street", "city"}
    normalized_text_fields = {"land_use_primary", "land_use_allowed", "land_use_forbidden"}
    nullable_boolean_fields = {"services_allowed", "nuisance_services_forbidden"}

    with db_session() as db:
        project, err = _project_or_404(db, project_id)
        if err:
            return err
        mpzp = project.mpzp_conditions or MPZPConditions(project_id=project.id)
        try:
            for field in editable_fields:
                if field not in payload:
                    continue
                value = payload.get(field)
                if field in normalized_string_fields:
                    if value is None:
                        setattr(mpzp, field, None)
                        continue
                    value = str(value).strip()
                    if len(value) > 255:
                        return jsonify({"error": "FIELD_TOO_LONG", "field": field}), 400
                    setattr(mpzp, field, value or None)
                    continue
                if field in normalized_text_fields:
                    if value is None:
                        setattr(mpzp, field, None)
                        continue
                    value = str(value).strip()
                    if len(value) > 2000:
                        return jsonify({"error": "FIELD_TOO_LONG", "field": field}), 400
                    setattr(mpzp, field, value or None)
                    continue
                if field in nullable_boolean_fields:
                    if value is None or isinstance(value, bool):
                        setattr(mpzp, field, value)
                        continue
                    return jsonify({"error": "INVALID_BOOLEAN", "field": field}), 400
                if field == "parcel_area_total":
                    try:
                        setattr(mpzp, field, _normalize_decimal_non_negative(value, field=field))
                    except ValueError as error:
                        code, bad_field = str(error).split(":", 1)
                        return jsonify({"error": code, "field": bad_field}), 400
                    continue
                if field in {
                    "max_building_height", "max_ridge_height", "max_eaves_height", "min_building_intensity", "max_building_intensity",
                    "max_building_coverage", "min_front_elevation_width", "max_front_elevation_width",
                }:
                    try:
                        setattr(mpzp, field, _normalize_decimal_non_negative(value, field=field))
                    except ValueError as error:
                        code, bad_field = str(error).split(":", 1)
                        return jsonify({"error": code, "field": bad_field}), 400
                    continue
                if field == "min_biologically_active_share":
                    try:
                        normalized_share = _normalize_decimal_non_negative(value, field=field)
                    except ValueError as error:
                        code, bad_field = str(error).split(":", 1)
                        return jsonify({"error": code, "field": bad_field}), 400
                    if normalized_share is not None and normalized_share > Decimal("100"):
                        return jsonify({"error": "VALUE_OUT_OF_RANGE", "field": field}), 400
                    setattr(mpzp, field, normalized_share)
                    continue
                if field in {"max_storeys_above", "max_storeys_below"}:
                    try:
                        setattr(mpzp, field, _normalize_non_negative_int(value, field=field))
                    except ValueError as error:
                        code, bad_field = str(error).split(":", 1)
                        return jsonify({"error": code, "field": bad_field}), 400
                    continue
                if field == "land_uses":
                    try:
                        normalized_land_uses = _normalize_land_uses(value)
                    except ValueError as error:
                        error_message = str(error)
                        if ":" in error_message:
                            code, bad_field = error_message.split(":", 1)
                            return jsonify({"error": code, "field": bad_field}), 400
                        return jsonify({"error": error_message, "field": field}), 400

                    if normalized_land_uses is not None:
                        mpzp.land_use_register_items.clear()
                        for item in normalized_land_uses:
                            mpzp.land_use_register_items.append(
                                MPZPLandUseRegisterItem(category_symbol=item["symbol"], area=item["area"])
                            )
                    continue
                setattr(mpzp, field, value)
            if project.mpzp_conditions is None:
                db.add(mpzp)
            db.flush()
            return jsonify(_serialize_mpzp(mpzp))
        except Exception:
            current_app.logger.exception("Failed to upsert MPZP identification", extra={"project_id": project_id, "user_id": g.current_user_id})
            raise


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
