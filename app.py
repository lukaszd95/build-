import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from api.routes.plots import register_plot_routes
from api.routes.map import register_map_routes
from api.routes.v2.auth import bp as auth_v2_bp, get_current_user_id
from api.routes.v2.projects import bp as projects_v2_bp
from config.database import ensure_mpzp_identification_columns
from utils.cad_import import convert_dwg_to_dxf, parse_dxf_to_json
from utils.db import create_timestamp, get_db, init_db
from utils.extraction_pipeline import (
    build_extraction_result,
    detect_format,
    extract_text_from_image,
    extract_text_from_pdf,
    process_upload,
    refresh_parcel_plan_rules,
)
from utils.llm_extraction import build_parcel_inference_from_pages
from utils.ocr import run_document_ocr
from utils.document_classifier import classifyDocument

last_cad_payload = None
executor = ThreadPoolExecutor(max_workers=2)

def _tesseract_status():
    try:
        import pytesseract
    except ModuleNotFoundError:
        return False, "Brak biblioteki pytesseract."
    try:
        version = pytesseract.get_tesseract_version()
    except (pytesseract.TesseractNotFoundError, OSError):
        return False, "Brak binarki Tesseract w systemie."
    return True, f"Wykryto Tesseract {version}."


def _ollama_status():
    base_url = os.getenv("OLLAMA_BASE_URL") or ""
    if not base_url:
        return False, "Brak konfiguracji OLLAMA_BASE_URL."
    return True, f"Skonfigurowano {base_url}."


def create_app(config_overrides=None):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["UPLOAD_FOLDER"] = os.getenv("CAD_UPLOAD_FOLDER", "uploads")
    app.config["ODA_FILE_CONVERTER"] = os.getenv("ODA_FILE_CONVERTER_PATH")
    app.config["DWG2DXF_PATH"] = os.getenv("DWG2DXF_PATH")
    app.config["CAD_DEBUG_JSON"] = os.getenv("CAD_DEBUG_JSON")
    app.config["DB_PATH"] = os.getenv("APP_DB_PATH", "data/app.db")
    app.config["DOCUMENT_UPLOAD_FOLDER"] = os.getenv("DOCUMENT_UPLOAD_FOLDER", "uploads/documents")
    app.config["DOCUMENT_MAX_SIZE_MB"] = int(os.getenv("DOCUMENT_MAX_SIZE_MB", "20"))
    app.config["PLAN_DOCUMENT_UPLOAD_FOLDER"] = os.getenv("PLAN_DOCUMENT_UPLOAD_FOLDER", "uploads/plan-documents")
    app.config["PLAN_DOCUMENT_MAX_SIZE_MB"] = int(os.getenv("PLAN_DOCUMENT_MAX_SIZE_MB", "30"))
    app.config["PLOT_UPLOAD_FOLDER"] = os.getenv("PLOT_UPLOAD_FOLDER", "uploads/plots")
    app.config["PLOT_MAX_SIZE_MB"] = int(os.getenv("PLOT_MAX_SIZE_MB", "50"))
    app.config["ASSET_UPLOAD_FOLDER"] = os.getenv("ASSET_UPLOAD_FOLDER", "uploads/assets")

    if config_overrides:
        app.config.update(config_overrides)

    init_db(app)
    register_routes(app)
    register_plot_routes(app)
    register_map_routes(app)
    app.register_blueprint(auth_v2_bp)
    app.register_blueprint(projects_v2_bp)
    ensure_mpzp_identification_columns()
    return app


def _allowed_document(filename, mime_type):
    ext = Path(filename).suffix.lower()
    allowed_by_ext = {
        ".pdf": {"application/pdf", "application/octet-stream"},
        ".png": {"image/png", "application/octet-stream"},
        ".jpg": {"image/jpeg", "application/octet-stream"},
        ".jpeg": {"image/jpeg", "application/octet-stream"},
        ".heic": {"image/heic", "image/heif", "application/octet-stream"},
        ".heif": {"image/heif", "image/heic", "application/octet-stream"},
        ".tif": {"image/tiff", "application/octet-stream"},
        ".tiff": {"image/tiff", "application/octet-stream"},
    }
    if ext not in allowed_by_ext:
        return False
    normalized_mime = (mime_type or "application/octet-stream").lower()
    return normalized_mime in allowed_by_ext[ext]


def _document_size_ok(file_storage, max_mb):
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size <= max_mb * 1024 * 1024, size


def _allowed_plan_document(filename, mime_type):
    ext = Path(filename).suffix.lower()
    allowed_mime = {
        ".pdf": {"application/pdf"},
        ".dxf": {"application/dxf", "image/vnd.dxf", "application/octet-stream"},
        ".dwg": {"application/acad", "image/vnd.dwg", "application/octet-stream"},
    }
    if ext not in allowed_mime:
        return False
    if mime_type and mime_type not in allowed_mime[ext]:
        return False
    return True


def _plan_document_kind(filename):
    ext = Path(filename).suffix.lower()
    if ext in {".dxf", ".dwg"}:
        return "CAD"
    return "PDF"


def register_routes(app):
    def normalize_parcel_id(value):
        return value or "_global"

    def _serialize_mpzp_value(raw_value):
        if isinstance(raw_value, dict):
            return json.dumps(raw_value, ensure_ascii=False), "JSON"
        if isinstance(raw_value, list):
            return json.dumps(raw_value, ensure_ascii=False), "JSON"
        if isinstance(raw_value, bool):
            return "true" if raw_value else "false", "BOOLEAN"
        if isinstance(raw_value, int):
            return str(raw_value), "INTEGER"
        if isinstance(raw_value, float):
            return str(raw_value), "NUMBER"
        if raw_value is None:
            return None, "TEXT"
        return str(raw_value), "TEXT"

    def _resolve_demo_project_id(db):
        row = db.execute("SELECT id FROM projects WHERE code = ?", ("DEMO",)).fetchone()
        if row:
            return row["id"]
        now = create_timestamp()
        cursor = db.execute(
            """
            INSERT INTO projects (code, name, description, status, investorName, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DEMO",
                "Projekt demo",
                "Domyślny projekt demonstracyjny do edycji w aplikacji.",
                "ACTIVE",
                "Demo inwestor",
                now,
                now,
            ),
        )
        project_id = cursor.lastrowid
        db.execute(
            """
            INSERT INTO project_plots (projectId, parcelId, externalParcelRef, notes, createdAt)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, "_global", "_global", "Domyślna działka projektu demo.", now),
        )
        return project_id

    def _upsert_project_plot(db, project_id, parcel_id, geometry=None):
        if not project_id or not parcel_id:
            return None

        plot = db.execute(
            """
            SELECT * FROM project_plots
            WHERE projectId = ? AND (parcelId = ? OR externalParcelRef = ?)
            ORDER BY id ASC
            LIMIT 1
            """,
            (project_id, parcel_id, parcel_id),
        ).fetchone()

        geometry_payload = geometry
        if geometry_payload is None:
            parcel_row = db.execute(
                "SELECT geometry FROM parcels WHERE parcelId = ? ORDER BY createdAt DESC LIMIT 1",
                (parcel_id,),
            ).fetchone()
            if parcel_row and parcel_row["geometry"]:
                geometry_payload = json.loads(parcel_row["geometry"])

        if not plot:
            cursor = db.execute(
                """
                INSERT INTO project_plots (projectId, parcelId, externalParcelRef, geometryJson, notes, createdAt)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    parcel_id,
                    parcel_id,
                    json.dumps(geometry_payload) if geometry_payload else None,
                    "Działka powiązana automatycznie z projektem.",
                    create_timestamp(),
                ),
            )
            return cursor.lastrowid

        if geometry_payload is not None:
            db.execute(
                "UPDATE project_plots SET geometryJson = ? WHERE id = ?",
                (json.dumps(geometry_payload), plot["id"]),
            )
        return plot["id"]

    def _sync_mpzp_fields_to_project_plot(db, document_id, project_id, parcel_id, fields):
        if project_id is None or not parcel_id or not isinstance(fields, dict):
            return 0

        project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not project:
            return 0

        project_plot_id = _upsert_project_plot(db, project_id, parcel_id)
        if not project_plot_id:
            return 0

        synced = 0
        for key, value in fields.items():
            serialized_value, value_type = _serialize_mpzp_value(value)
            db.execute(
                """
                INSERT INTO project_plot_parameters (projectPlotId, key, value, valueType, source, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(projectPlotId, key)
                DO UPDATE SET value = excluded.value,
                              valueType = excluded.valueType,
                              source = excluded.source,
                              updatedAt = excluded.updatedAt
                """,
                (
                    project_plot_id,
                    f"mpzp.{key}",
                    serialized_value,
                    value_type,
                    f"document:{document_id}",
                    create_timestamp(),
                ),
            )
            synced += 1

        return synced

    @app.route("/")
    def index():
        return render_template("home.html")

    @app.route("/login")
    def login_page():
        if get_current_user_id():
            return "", 302, {"Location": "/projects"}
        return render_template("home.html", auth_mode="login")

    @app.route("/register")
    def register_page():
        if get_current_user_id():
            return "", 302, {"Location": "/projects"}
        return render_template("home.html", auth_mode="register")

    @app.route("/projects")
    def projects_page():
        if not get_current_user_id():
            return "", 302, {"Location": "/login"}
        return "", 302, {"Location": "/app?open=projects"}

    @app.route("/app")
    def app_workspace():
        if not get_current_user_id():
            return "", 302, {"Location": "/login"}
        return render_template("index.html")

    @app.route("/api/import-cad", methods=["POST"])
    def import_cad():
        global last_cad_payload

        if "file" not in request.files:
            return jsonify({"error": "Brak pliku w zapytaniu."}), 400

        cad_file = request.files["file"]
        if not cad_file or cad_file.filename == "":
            return jsonify({"error": "Nie wybrano pliku."}), 400

        filename = secure_filename(cad_file.filename)
        if not filename:
            return jsonify({"error": "Nieprawidłowa nazwa pliku."}), 400

        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".dxf", ".dwg"):
            return jsonify({"error": "Nieobsługiwany format. Wgraj DXF lub DWG."}), 400

        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        timestamp = int(time.time())
        stored_name = f"{Path(filename).stem}_{timestamp}{ext}"
        stored_path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
        cad_file.save(stored_path)

        try:
            if ext == ".dwg":
                dxf_path = convert_dwg_to_dxf(
                    stored_path,
                    app.config["UPLOAD_FOLDER"],
                    oda_path=app.config["ODA_FILE_CONVERTER"],
                    dwg2dxf_path=app.config["DWG2DXF_PATH"],
                )
            else:
                dxf_path = stored_path

            payload = parse_dxf_to_json(dxf_path)
            app.logger.info(
                "CAD import: units=%s scale=%s layers=%s entities=%s parseMs=%s",
                payload.get("unitsDetected"),
                payload.get("unitScaleToMeters"),
                payload.get("layerCount"),
                payload.get("entityCount"),
                payload.get("parseMs"),
            )
            last_cad_payload = payload
            return jsonify(payload)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/cad-last", methods=["GET"])
    def cad_last():
        if last_cad_payload is None:
            return jsonify({"error": "Brak zaimportowanej mapy."}), 404
        return jsonify(last_cad_payload)

    @app.route("/api/uploads", methods=["POST"])
    def create_upload():
        db = get_db(app.config["DB_PATH"])
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku w zapytaniu."}), 400

        upload_file = request.files["file"]
        upload_type = request.form.get("type")
        if not upload_type:
            return jsonify({"error": "Brak typu uploadu."}), 400

        filename = secure_filename(upload_file.filename)
        if not filename:
            return jsonify({"error": "Nieprawidłowa nazwa pliku."}), 400

        storage_dir = os.path.join(app.config["UPLOAD_FOLDER"], "documents")
        os.makedirs(storage_dir, exist_ok=True)
        timestamp = int(time.time())
        stored_name = f"{Path(filename).stem}_{timestamp}{Path(filename).suffix}"
        stored_path = os.path.join(storage_dir, stored_name)
        upload_file.save(stored_path)

        cursor = db.execute(
            """
            INSERT INTO uploads (userId, type, filename, mimeType, size, storageUrl, status, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                upload_type,
                filename,
                upload_file.mimetype or "application/octet-stream",
                os.path.getsize(stored_path),
                stored_path,
                "UPLOADED",
                create_timestamp(),
            ),
        )
        db.commit()

        return jsonify({"uploadId": cursor.lastrowid})

    @app.route("/api/uploads/<int:upload_id>", methods=["GET"])
    def get_upload(upload_id):
        db = get_db(app.config["DB_PATH"])
        upload = db.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        if not upload:
            return jsonify({"error": "Upload nie istnieje."}), 404

        fields = db.execute(
            "SELECT * FROM extracted_fields WHERE uploadId = ? ORDER BY id",
            (upload_id,),
        ).fetchall()
        response_fields = []
        for row in fields:
            value = None
            if row["value"] is not None:
                try:
                    value = json.loads(row["value"])
                except json.JSONDecodeError:
                    value = row["value"]
            response_fields.append(
                {
                    "id": row["id"],
                    "uploadId": row["uploadId"],
                    "parcelId": row["parcelId"],
                    "fieldKey": row["fieldKey"],
                    "value": value,
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "source": json.loads(row["source"]),
                    "createdAt": row["createdAt"],
                }
            )

        return jsonify(
            {
                "upload": {
                    "id": upload["id"],
                    "type": upload["type"],
                    "filename": upload["filename"],
                    "mimeType": upload["mimeType"],
                    "size": upload["size"],
                    "storageUrl": upload["storageUrl"],
                    "status": upload["status"],
                    "createdAt": upload["createdAt"],
                },
                "extractedFields": response_fields,
            }
        )

    @app.route("/api/ocr-preview", methods=["POST"], strict_slashes=False)
    def ocr_preview():
        if "file" not in request.files:
            return jsonify({"error": "Brak pliku w zapytaniu."}), 400

        upload_file = request.files["file"]
        filename = secure_filename(upload_file.filename)
        if not filename:
            return jsonify({"error": "Nieprawidłowa nazwa pliku."}), 400

        if not _allowed_document(filename, upload_file.mimetype):
            return jsonify({"error": "Nieobsługiwany format pliku. Dozwolone: PDF/JPG/PNG/HEIC/TIFF."}), 400

        os.makedirs(app.config["DOCUMENT_UPLOAD_FOLDER"], exist_ok=True)
        timestamp = int(time.time())
        stored_name = f"preview_{Path(filename).stem}_{timestamp}{Path(filename).suffix}"
        stored_path = os.path.join(app.config["DOCUMENT_UPLOAD_FOLDER"], stored_name)
        upload_file.save(stored_path)

        try:
            format_type = detect_format(filename, upload_file.mimetype or "")
            if format_type == "pdf":
                pages = extract_text_from_pdf(stored_path)
            elif format_type == "image":
                pages = extract_text_from_image(stored_path)
            else:
                pages = [{"page": 1, "text": ""}]

            try:
                parcel_inference = build_parcel_inference_from_pages(pages)
                extraction = build_extraction_result(pages, use_llm=False)
                try:
                    classification = classifyDocument(
                        stored_path,
                        mimeType=upload_file.mimetype,
                        filename=filename,
                    )
                except Exception:
                    classification = {
                        "fileType": "INNE",
                        "confidence": 0.0,
                        "evidence": [],
                        "extractedTopText": "",
                    }
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500
            parcel_numbers = parcel_inference.get("parcelNumbers") or ([] if not parcel_inference.get("parcelId") else [parcel_inference.get("parcelId")])
            parcel_id = parcel_numbers[0] if parcel_numbers else None
            obreb = parcel_inference.get("obreb")
            street = parcel_inference.get("street")
            locality = parcel_inference.get("locality")
            fields = extraction.get("fields", [])

            def _find_field(field_key):
                return next((field for field in fields if field.get("fieldKey") == field_key), None)

            def _format_value(field):
                if not field or field.get("value") is None:
                    return None
                value = field.get("value")
                unit = field.get("unit")
                if isinstance(value, dict):
                    inner_value = value.get("value")
                    inner_unit = value.get("unit") or unit
                    if inner_value is None:
                        return None
                    return f"{inner_value} {inner_unit}".strip()
                if unit:
                    return f"{value} {unit}".strip()
                return str(value)

            purpose_value = _format_value(_find_field("terrainDescription"))
            purpose_primary_value = _format_value(_find_field("primaryPurpose"))
            purpose_allowed_value = _format_value(_find_field("allowedPurpose"))
            purpose_forbidden_value = _format_value(_find_field("forbiddenPurpose"))
            max_building_height_value = _format_value(_find_field("maxBuildingHeightM"))
            max_above_ground_storeys_value = _format_value(_find_field("maxAboveGroundStoreys"))
            max_below_ground_storeys_value = _format_value(_find_field("maxBelowGroundStoreys"))
            max_ridge_height_value = _format_value(_find_field("maxRidgeHeightM"))
            max_eaves_height_value = _format_value(_find_field("maxEavesHeightM"))
            min_intensity_value = _format_value(_find_field("minBuildingIntensity"))
            max_intensity_value = _format_value(_find_field("maxBuildingIntensity"))
            max_coverage_value = _format_value(_find_field("maxBuildingCoveragePctOrM2"))
            bio_active_value = _format_value(_find_field("minBiologicallyActivePct"))
            min_facade_width_value = _format_value(_find_field("minFacadeWidthM"))
            max_facade_width_value = _format_value(_find_field("maxFacadeWidthM"))
            return jsonify(
                {
                    "parcelId": parcel_id,
                    "parcelNumbers": parcel_numbers,
                    "parcel_numbers": parcel_numbers,
                    "obreb": obreb,
                    "precinct": obreb,
                    "street": street,
                    "locality": locality,
                    "city": locality,
                    "parcelInference": parcel_inference["details"],
                    "evidence": parcel_inference["details"].get("evidence", {}),
                    "notes": parcel_inference["details"].get("notes", []),
                    "confidence": parcel_inference["details"].get("overall_confidence", 0.0),
                    "purpose": purpose_value,
                    "purposePrimary": purpose_primary_value,
                    "purposeAllowed": purpose_allowed_value,
                    "purposeForbidden": purpose_forbidden_value,
                    "maxBuildingHeight": max_building_height_value,
                    "maxAboveGroundStoreys": max_above_ground_storeys_value,
                    "maxBelowGroundStoreys": max_below_ground_storeys_value,
                    "maxRidgeHeight": max_ridge_height_value,
                    "maxEavesHeight": max_eaves_height_value,
                    "minIntensity": min_intensity_value,
                    "maxIntensity": max_intensity_value,
                    "maxCoverage": max_coverage_value,
                    "bioActive": bio_active_value,
                    "minFacadeWidth": min_facade_width_value,
                    "maxFacadeWidth": max_facade_width_value,
                    "sourceFile": filename,
                    "documentClassification": classification,
                    "fileType": classification.get("fileType"),
                    "fileTypeConfidence": classification.get("confidence"),
                    "fileTypeEvidence": classification.get("evidence", []),
                    "fileTopText": classification.get("extractedTopText", ""),
                }
            )
        finally:
            try:
                os.remove(stored_path)
            except FileNotFoundError:
                pass

    @app.route("/api/integration-status", methods=["GET"])
    def integration_status():
        tesseract_available, tesseract_message = _tesseract_status()
        ollama_available, ollama_message = _ollama_status()
        return jsonify(
            {
                "tesseract": {
                    "available": tesseract_available,
                    "message": tesseract_message,
                },
                "ollama": {
                    "available": ollama_available,
                    "message": ollama_message,
                },
            }
        )

    @app.route("/api/uploads/<int:upload_id>/process", methods=["POST"])
    def process_upload_endpoint(upload_id):
        db = get_db(app.config["DB_PATH"])
        upload = db.execute("SELECT * FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        if not upload:
            return jsonify({"error": "Upload nie istnieje."}), 404

        db.execute("UPDATE uploads SET status = ? WHERE id = ?", ("PROCESSING", upload_id))
        db.commit()

        executor.submit(process_upload, dict(upload), app.config["DB_PATH"])
        return jsonify({"status": "PROCESSING"})

    @app.route("/api/plan-documents", methods=["GET", "POST"])
    def plan_documents():
        db = get_db(app.config["DB_PATH"])
        if request.method == "POST":
            if "file" not in request.files:
                return jsonify({"error": "Brak pliku w zapytaniu."}), 400

            upload_file = request.files["file"]
            filename = secure_filename(upload_file.filename)
            if not filename:
                return jsonify({"error": "Nieprawidłowa nazwa pliku."}), 400

            if not _allowed_plan_document(filename, upload_file.mimetype):
                return jsonify({"error": "Nieobsługiwany format. Dozwolone: DWG, DXF lub PDF."}), 400

            size_ok, size = _document_size_ok(
                upload_file, app.config["PLAN_DOCUMENT_MAX_SIZE_MB"]
            )
            if not size_ok:
                return (
                    jsonify(
                        {
                            "error": f"Plik jest za duży. Maksymalny rozmiar to {app.config['PLAN_DOCUMENT_MAX_SIZE_MB']} MB."
                        }
                    ),
                    400,
                )

            storage_dir = app.config["PLAN_DOCUMENT_UPLOAD_FOLDER"]
            os.makedirs(storage_dir, exist_ok=True)
            timestamp = int(time.time())
            stored_name = f"{Path(filename).stem}_{timestamp}{Path(filename).suffix}"
            stored_path = os.path.join(storage_dir, stored_name)
            upload_file.save(stored_path)

            cursor = db.execute(
                """
                INSERT INTO plan_documents (fileName, fileUrl, mimeType, size, fileKind, uploadedAt, isDeleted)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    filename,
                    stored_path,
                    upload_file.mimetype or "application/octet-stream",
                    os.path.getsize(stored_path),
                    _plan_document_kind(filename),
                    create_timestamp(),
                ),
            )
            db.commit()
            return jsonify({"documentId": cursor.lastrowid}), 201

        rows = db.execute(
            "SELECT * FROM plan_documents WHERE isDeleted = 0 ORDER BY uploadedAt DESC"
        ).fetchall()
        documents_list = [
            {
                "id": row["id"],
                "fileName": row["fileName"],
                "fileUrl": row["fileUrl"],
                "mimeType": row["mimeType"],
                "size": row["size"],
                "fileKind": row["fileKind"],
                "uploadedAt": row["uploadedAt"],
            }
            for row in rows
        ]
        return jsonify({"documents": documents_list})

    @app.route("/api/plan-documents/<int:document_id>", methods=["DELETE"])
    def delete_plan_document(document_id):
        db = get_db(app.config["DB_PATH"])
        document = db.execute(
            "SELECT * FROM plan_documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not document or document["isDeleted"]:
            return jsonify({"error": "Plik nie istnieje."}), 404

        db.execute("UPDATE plan_documents SET isDeleted = 1 WHERE id = ?", (document_id,))
        db.commit()
        try:
            if document["fileUrl"] and os.path.exists(document["fileUrl"]):
                os.remove(document["fileUrl"])
        except OSError:
            app.logger.warning("Nie udało się usunąć pliku %s", document["fileUrl"])

        return jsonify({"status": "deleted"})

    @app.route("/api/documents", methods=["GET", "POST"])
    def documents():
        db = get_db(app.config["DB_PATH"])
        if request.method == "POST":
            if "file" not in request.files:
                return jsonify({"error": "Brak pliku w zapytaniu."}), 400

            upload_file = request.files["file"]
            document_type = request.form.get("type")
            if not document_type:
                return jsonify({"error": "Brak typu dokumentu."}), 400

            filename = secure_filename(upload_file.filename)
            if not filename:
                return jsonify({"error": "Nieprawidłowa nazwa pliku."}), 400

            if not _allowed_document(filename, upload_file.mimetype):
                return jsonify({"error": "Nieobsługiwany format. Dozwolone: PDF/JPG/PNG/HEIC/TIFF."}), 400

            size_ok, size = _document_size_ok(upload_file, app.config["DOCUMENT_MAX_SIZE_MB"])
            if not size_ok:
                return (
                    jsonify(
                        {
                            "error": f"Plik jest za duży. Maksymalny rozmiar to {app.config['DOCUMENT_MAX_SIZE_MB']} MB."
                        }
                    ),
                    400,
                )

            storage_dir = app.config["DOCUMENT_UPLOAD_FOLDER"]
            os.makedirs(storage_dir, exist_ok=True)
            timestamp = int(time.time())
            stored_name = f"{Path(filename).stem}_{timestamp}{Path(filename).suffix}"
            stored_path = os.path.join(storage_dir, stored_name)
            upload_file.save(stored_path)

            row = db.execute(
                "SELECT COALESCE(MAX(version), 0) AS maxVersion FROM documents WHERE type = ?",
                (document_type,),
            ).fetchone()
            version = (row["maxVersion"] or 0) + 1
            cursor = db.execute(
                """
                INSERT INTO documents (type, fileUrl, fileName, mimeType, size, uploadedAt, version, status, ocrStatus, isDeleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    document_type,
                    stored_path,
                    filename,
                    upload_file.mimetype or "application/octet-stream",
                    size,
                    create_timestamp(),
                    version,
                    "READY",
                    "IDLE",
                ),
            )
            db.commit()

            try:
                classification = classifyDocument(
                    stored_path,
                    mimeType=upload_file.mimetype,
                    filename=filename,
                )
            except Exception:
                classification = {
                    "fileType": "INNE",
                    "confidence": 0.0,
                    "evidence": [],
                    "extractedTopText": "",
                }
            return (
                jsonify(
                    {
                        "documentId": cursor.lastrowid,
                        "version": version,
                        "fileType": classification.get("fileType"),
                        "confidence": classification.get("confidence"),
                        "evidence": classification.get("evidence", []),
                        "extractedTopText": classification.get("extractedTopText", ""),
                    }
                ),
                201,
            )

        document_type = request.args.get("type")
        params = []
        query = "SELECT * FROM documents WHERE isDeleted = 0"
        if document_type:
            query += " AND type = ?"
            params.append(document_type)
        query += " ORDER BY uploadedAt DESC"
        rows = db.execute(query, params).fetchall()
        documents_list = [
            {
                "id": row["id"],
                "type": row["type"],
                "fileUrl": row["fileUrl"],
                "fileName": row["fileName"],
                "mimeType": row["mimeType"],
                "size": row["size"],
                "uploadedAt": row["uploadedAt"],
                "version": row["version"],
                "status": row["status"],
                "ocrStatus": row["ocrStatus"],
            }
            for row in rows
        ]
        return jsonify({"documents": documents_list})

    @app.route("/api/documents/<int:document_id>", methods=["GET", "DELETE"])
    def document_detail(document_id):
        db = get_db(app.config["DB_PATH"])
        document = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document or document["isDeleted"]:
            return jsonify({"error": "Dokument nie istnieje."}), 404

        if request.method == "DELETE":
            db.execute("UPDATE documents SET isDeleted = 1 WHERE id = ?", (document_id,))
            db.commit()
            return jsonify({"status": "deleted"})

        rows = db.execute(
            "SELECT * FROM document_extracted_data WHERE documentId = ? ORDER BY updatedAt DESC",
            (document_id,),
        ).fetchall()
        extracted_data = []
        for row in rows:
            extracted_data.append(
                {
                    "id": row["id"],
                    "documentId": row["documentId"],
                    "parcelId": row["parcelId"],
                    "fields": json.loads(row["fieldsJson"]) if row["fieldsJson"] else {},
                    "source": json.loads(row["source"]),
                    "updatedAt": row["updatedAt"],
                    "ocrConfidence": json.loads(row["ocrConfidenceJson"])
                    if row["ocrConfidenceJson"]
                    else None,
                }
            )

        return jsonify(
            {
                "document": {
                    "id": document["id"],
                    "type": document["type"],
                    "fileUrl": document["fileUrl"],
                    "fileName": document["fileName"],
                    "mimeType": document["mimeType"],
                    "size": document["size"],
                    "uploadedAt": document["uploadedAt"],
                    "version": document["version"],
                    "status": document["status"],
                    "ocrStatus": document["ocrStatus"],
                },
                "extractedData": extracted_data,
            }
        )

    @app.route("/api/documents/<int:document_id>/file", methods=["GET"])
    def document_file(document_id):
        db = get_db(app.config["DB_PATH"])
        document = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document or document["isDeleted"]:
            return jsonify({"error": "Dokument nie istnieje."}), 404
        return send_file(document["fileUrl"], as_attachment=False)

    @app.route("/api/documents/<int:document_id>/data", methods=["POST"])
    def document_data(document_id):
        db = get_db(app.config["DB_PATH"])
        document = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document or document["isDeleted"]:
            return jsonify({"error": "Dokument nie istnieje."}), 404

        payload = request.get_json(silent=True) or {}
        fields = payload.get("fields")
        source = payload.get("source", {"source": "manual"})
        parcel_id = normalize_parcel_id(payload.get("parcelId"))
        project_id = payload.get("projectId") or _resolve_demo_project_id(db)
        if not isinstance(fields, dict):
            return jsonify({"error": "fields musi być obiektem."}), 400

        db.execute(
            """
            INSERT INTO document_extracted_data (documentId, parcelId, fieldsJson, source, updatedAt, ocrConfidenceJson)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(documentId, parcelId)
            DO UPDATE SET fieldsJson = excluded.fieldsJson,
                          source = excluded.source,
                          updatedAt = excluded.updatedAt,
                          ocrConfidenceJson = excluded.ocrConfidenceJson
            """,
            (
                document_id,
                parcel_id,
                json.dumps(fields),
                json.dumps(source),
                create_timestamp(),
                json.dumps(payload.get("ocrConfidence")) if payload.get("ocrConfidence") else None,
            ),
        )
        synced_count = _sync_mpzp_fields_to_project_plot(
            db,
            document_id=document_id,
            project_id=project_id,
            parcel_id=parcel_id,
            fields=fields,
        )
        db.commit()
        return jsonify({"status": "saved", "projectPlotParametersSynced": synced_count})

    @app.route("/api/documents/<int:document_id>/ocr", methods=["POST"])
    def document_ocr(document_id):
        db = get_db(app.config["DB_PATH"])
        document = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not document or document["isDeleted"]:
            return jsonify({"error": "Dokument nie istnieje."}), 404

        payload = request.get_json(silent=True) or {}
        parcel_id = normalize_parcel_id(payload.get("parcelId"))
        db.execute(
            "UPDATE documents SET ocrStatus = ?, status = ? WHERE id = ?",
            ("PROCESSING", "PROCESSING", document_id),
        )
        db.commit()

        executor.submit(run_document_ocr, dict(document), app.config["DB_PATH"], parcel_id)
        return jsonify({"status": "processing"})

    @app.route("/api/projects/demo", methods=["GET", "PATCH"])
    def demo_project():
        db = get_db(app.config["DB_PATH"])
        project_id = _resolve_demo_project_id(db)

        if request.method == "PATCH":
            payload = request.get_json(silent=True) or {}
            editable_fields = {
                "name": payload.get("name"),
                "description": payload.get("description"),
                "status": payload.get("status"),
                "investorName": payload.get("investorName"),
            }
            updates = []
            params = []
            for key, value in editable_fields.items():
                if value is None:
                    continue
                updates.append(f"{key} = ?")
                params.append(value)
            if updates:
                updates.append("updatedAt = ?")
                params.append(create_timestamp())
                params.append(project_id)
                db.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
                db.commit()

        project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        plots_rows = db.execute(
            "SELECT * FROM project_plots WHERE projectId = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        plot_ids = [row["id"] for row in plots_rows]
        params_by_plot = {}
        if plot_ids:
            placeholders = ",".join("?" for _ in plot_ids)
            params_rows = db.execute(
                f"SELECT * FROM project_plot_parameters WHERE projectPlotId IN ({placeholders})",
                plot_ids,
            ).fetchall()
            for row in params_rows:
                params_by_plot.setdefault(row["projectPlotId"], []).append(
                    {
                        "id": row["id"],
                        "key": row["key"],
                        "value": row["value"],
                        "valueType": row["valueType"],
                        "unit": row["unit"],
                        "source": row["source"],
                        "updatedAt": row["updatedAt"],
                    }
                )

        plots = []
        for row in plots_rows:
            plots.append(
                {
                    "id": row["id"],
                    "parcelId": row["parcelId"],
                    "externalParcelRef": row["externalParcelRef"],
                    "geometry": json.loads(row["geometryJson"]) if row["geometryJson"] else None,
                    "area": row["area"],
                    "ownershipStatus": row["ownershipStatus"],
                    "notes": row["notes"],
                    "createdAt": row["createdAt"],
                    "parameters": params_by_plot.get(row["id"], []),
                }
            )

        return jsonify(
            {
                "project": {
                    "id": project["id"],
                    "code": project["code"],
                    "name": project["name"],
                    "description": project["description"],
                    "status": project["status"],
                    "investorName": project["investorName"],
                    "createdAt": project["createdAt"],
                    "updatedAt": project["updatedAt"],
                },
                "plots": plots,
            }
        )

    @app.route("/api/parcels", methods=["GET", "POST"])
    def parcels():
        db = get_db(app.config["DB_PATH"])
        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            parcel_id = payload.get("parcelId")
            if not parcel_id:
                return jsonify({"error": "parcelId jest wymagany."}), 400
            geometry = payload.get("geometry")
            db.execute(
                """
                INSERT INTO parcels (parcelId, geometry, createdAt)
                VALUES (?, ?, ?)
                """,
                (parcel_id, json.dumps(geometry) if geometry else None, create_timestamp()),
            )
            demo_project_id = _resolve_demo_project_id(db)
            _upsert_project_plot(db, demo_project_id, parcel_id, geometry=geometry)
            db.commit()
            return jsonify({"status": "created"}), 201

        parcels_rows = db.execute("SELECT * FROM parcels ORDER BY createdAt DESC").fetchall()
        parcels_list = [
            {
                "id": row["id"],
                "parcelId": row["parcelId"],
                "geometry": json.loads(row["geometry"]) if row["geometry"] else None,
                "createdAt": row["createdAt"],
            }
            for row in parcels_rows
        ]
        return jsonify({"parcels": parcels_list})

    @app.route("/api/extracted-fields/<int:field_id>/assign-parcel", methods=["POST"])
    def assign_parcel(field_id):
        db = get_db(app.config["DB_PATH"])
        payload = request.get_json(silent=True) or {}
        parcel_id = payload.get("parcelId")
        if parcel_id is None:
            return jsonify({"error": "parcelId jest wymagany."}), 400

        db.execute(
            "UPDATE extracted_fields SET parcelId = ? WHERE id = ?",
            (parcel_id, field_id),
        )
        db.commit()
        refresh_parcel_plan_rules(db, parcel_id)
        return jsonify({"status": "assigned"})

    @app.route("/api/extracted-fields/<int:field_id>", methods=["PATCH"])
    def update_extracted_field(field_id):
        db = get_db(app.config["DB_PATH"])
        payload = request.get_json(silent=True) or {}
        new_value = payload.get("value")

        row = db.execute(
            "SELECT value, status, parcelId FROM extracted_fields WHERE id = ?",
            (field_id,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Pole nie istnieje."}), 404

        db.execute(
            """
            INSERT INTO extracted_field_history (extractedFieldId, prevValue, prevStatus, changedAt)
            VALUES (?, ?, ?, ?)
            """,
            (field_id, row["value"], row["status"], create_timestamp()),
        )

        db.execute(
            """
            UPDATE extracted_fields
            SET value = ?, status = ?
            WHERE id = ?
            """,
            (json.dumps(new_value) if new_value is not None else None, "USER_EDITED", field_id),
        )
        db.commit()
        if row["parcelId"]:
            refresh_parcel_plan_rules(db, row["parcelId"])
        return jsonify({"status": "updated"})

    @app.route("/api/parcels/<parcel_id>/plan-rules", methods=["GET"])
    def get_parcel_plan_rules(parcel_id):
        db = get_db(app.config["DB_PATH"])
        row = db.execute(
            "SELECT * FROM parcel_plan_rules WHERE parcelId = ?",
            (parcel_id,),
        ).fetchone()
        if not row:
            return jsonify({"parcelId": parcel_id, "rules": {}, "provenance": {}})
        return jsonify(
            {
                "parcelId": parcel_id,
                "rules": json.loads(row["rulesJson"]),
                "provenance": json.loads(row["provenanceJson"]),
                "lastUpdatedAt": row["lastUpdatedAt"],
            }
        )


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("APP_HOST", "127.0.0.1"), port=5000, debug=True)
