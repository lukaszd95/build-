import os

from flask import Blueprint, current_app, jsonify, request

from utils.db import get_db

from services.import_service import get_boundaries, handle_plot_upload, select_boundary
from services.dwg_converter import DwgConverterError

plots_bp = Blueprint("plots", __name__)


@plots_bp.route("/api/plots/upload", methods=["POST"])
def upload_plot():
    if "file" not in request.files:
        return jsonify({"error": "Brak pliku w zapytaniu."}), 400

    plot_file = request.files["file"]
    if not plot_file or not plot_file.filename:
        return jsonify({"error": "Nie wybrano pliku."}), 400

    try:
        payload = handle_plot_upload(current_app.config, plot_file)
    except (ValueError, DwgConverterError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        current_app.logger.exception("Plot upload failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify(payload), 201


@plots_bp.route("/api/plots", methods=["GET"])
def list_plots():
    db = get_db(current_app.config["DB_PATH"])
    rows = db.execute(
        "SELECT id, filename, status, createdAt, isDisabled FROM plot_import_jobs ORDER BY createdAt DESC"
    ).fetchall()
    imports = [
        {
            "id": row["id"],
            "filename": row["filename"],
            "status": row["status"],
            "createdAt": row["createdAt"],
            "isDisabled": bool(row["isDisabled"]),
        }
        for row in rows
    ]
    return jsonify({"imports": imports})


@plots_bp.route("/api/plots/<int:import_job_id>/boundaries", methods=["GET"])
def plot_boundaries(import_job_id):
    result = get_boundaries(current_app.config["DB_PATH"], import_job_id)
    if not result:
        return jsonify({"error": "Import nie istnieje."}), 404
    return jsonify(result)


@plots_bp.route("/api/plots/<int:import_job_id>/select-boundary", methods=["POST"])
def select_plot_boundary(import_job_id):
    payload = request.get_json(silent=True) or {}
    candidate_id = payload.get("candidate_id") or payload.get("candidateId")
    if not candidate_id:
        return jsonify({"error": "candidate_id jest wymagany."}), 400
    try:
        selected = select_boundary(current_app.config["DB_PATH"], import_job_id, int(candidate_id))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not selected:
        return jsonify({"error": "Import nie istnieje."}), 404
    return jsonify({"selectedBoundary": selected})


@plots_bp.route("/api/plots/<int:import_job_id>", methods=["PATCH"])
def update_plot(import_job_id):
    payload = request.get_json(silent=True) or {}
    if "isDisabled" not in payload:
        return jsonify({"error": "isDisabled jest wymagane."}), 400
    is_disabled = 1 if payload.get("isDisabled") else 0
    db = get_db(current_app.config["DB_PATH"])
    row = db.execute("SELECT id FROM plot_import_jobs WHERE id = ?", (import_job_id,)).fetchone()
    if not row:
        return jsonify({"error": "Import nie istnieje."}), 404
    db.execute("UPDATE plot_import_jobs SET isDisabled = ? WHERE id = ?", (is_disabled, import_job_id))
    db.commit()
    return jsonify({"id": import_job_id, "isDisabled": bool(is_disabled)})


@plots_bp.route("/api/plots/<int:import_job_id>", methods=["DELETE"])
def delete_plot(import_job_id):
    db = get_db(current_app.config["DB_PATH"])
    job = db.execute(
        "SELECT id, sourcePath FROM plot_import_jobs WHERE id = ?", (import_job_id,)
    ).fetchone()
    if not job:
        return jsonify({"error": "Import nie istnieje."}), 404
    db.execute("DELETE FROM plot_boundaries WHERE importJobId = ?", (import_job_id,))
    db.execute("DELETE FROM plot_import_jobs WHERE id = ?", (import_job_id,))
    db.commit()
    if job["sourcePath"]:
        try:
            os.remove(job["sourcePath"])
        except FileNotFoundError:
            pass
    return jsonify({"deleted": True})


def register_plot_routes(app):
    app.register_blueprint(plots_bp)
