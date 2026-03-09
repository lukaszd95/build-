import json
import os
import time
from collections import defaultdict

from flask import Blueprint, Response, current_app, jsonify, request
try:
    import mapbox_vector_tile
except Exception:
    mapbox_vector_tile = None

from services.layer_import_coordinator import LayerImportCoordinator
from services.map_service import MapService
from services.parcel_lookup_service import ParcelLookupService
from services.site_context_import_service import SiteContextImportService
from services.spatial_source_gateway import SpatialSourceGateway
from utils.db import get_db


rate_limit_store = defaultdict(list)


def _load_map_config():
    path = os.getenv("MAP_CONFIG_PATH", "config/map.config.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _validate_config(cfg):
    if not cfg.get("parcels", {}).get("provider"):
        return False, "PARCEL_PROVIDER_NOT_CONFIGURED"
    return True, None


def _rate_limit(key: str, max_calls=30, window_s=60):
    now = time.time()
    calls = rate_limit_store[key]
    rate_limit_store[key] = [c for c in calls if now - c < window_s]
    if len(rate_limit_store[key]) >= max_calls:
        return False
    rate_limit_store[key].append(now)
    return True


def _build_site_context_import_service(db, cfg):
    gateway = SpatialSourceGateway(cfg)
    parcel_lookup = ParcelLookupService(gateway)
    map_service = MapService(db, cfg)
    coordinator = LayerImportCoordinator()
    return SiteContextImportService(parcel_lookup=parcel_lookup, map_service=map_service, layer_coordinator=coordinator)


def _search_payload_from_request_args() -> dict[str, str]:
    return {
        "parcelId": (request.args.get("parcelId") or "").strip(),
        "parcelNumber": (request.args.get("parcelNumber") or request.args.get("nrDzialki") or "").strip(),
        "precinct": (request.args.get("precinct") or request.args.get("obreb") or "").strip(),
        "cadastralUnit": (request.args.get("cadastralUnit") or request.args.get("miejscowosc") or request.args.get("municipality") or "").strip(),
        "municipality": (request.args.get("municipality") or "").strip(),
        "county": (request.args.get("county") or "").strip(),
        "voivodeship": (request.args.get("voivodeship") or "").strip(),
    }


def _error_response(exc: Exception):
    code = str(exc)
    mapping = {
        "MISSING_PARCEL": ("Brak działki w zapytaniu.", 400),
        "MISSING_PARCEL_NUMBER": ("Brak numeru działki.", 400),
        "PARCEL_NOT_FOUND": ("Nie znaleziono działki.", 404),
        "MULTIPLE_PARCEL_MATCHES": ("Wiele działek pasuje do zapytania.", 409),
        "MISSING_GEOMETRY": ("Brak geometrii działki.", 422),
        "PARCEL_PROVIDER_NOT_CONFIGURED": ("Brak konfiguracji źródła przestrzennego.", 503),
    }
    if code in mapping:
        message, status = mapping[code]
        return jsonify({"error": code, "message": message}), status
    lowered = code.lower()
    if "timeout" in lowered:
        return jsonify({"error": "EXTERNAL_SOURCE_TIMEOUT", "message": "Przekroczono czas odpowiedzi źródła zewnętrznego."}), 504
    if "wfs" in lowered or "geoportal" in lowered:
        return jsonify({"error": "EXTERNAL_SOURCE_ERROR", "message": "Problem ze źródłem danych przestrzennych."}), 502
    return jsonify({"error": code or "IMPORT_FAILED", "message": "Nie udało się przetworzyć żądania."}), 500


def register_map_routes(app):
    bp = Blueprint("map", __name__, url_prefix="/api/map")
    bp_public = Blueprint("site_context_api", __name__, url_prefix="/api")

    @bp.route("/parcel/resolve", methods=["POST"])
    def resolve_parcel():
        if not _rate_limit(request.remote_addr or "anon"):
            return jsonify({"error": "RATE_LIMITED"}), 429
        cfg = _load_map_config()
        valid, error = _validate_config(cfg)
        if not valid:
            return jsonify({"error": error}), 503

        db = get_db(current_app.config["DB_PATH"])
        service = MapService(db, cfg)
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(service.resolve(payload))
        except Exception as exc:
            return _error_response(exc)

    @bp_public.route("/site-context/parcels/search", methods=["GET"])
    @bp.route("/site-context/parcels/search", methods=["GET"])
    @bp_public.route("/parcels/search", methods=["GET"])
    @bp.route("/parcels/search", methods=["GET"])
    def search_parcels():
        cfg = _load_map_config()
        valid, error = _validate_config(cfg)
        if not valid:
            return jsonify({"error": error}), 503
        params = _search_payload_from_request_args()
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, cfg)
        try:
            return jsonify(
                service.search_parcels(
                    parcel_number=params["parcelNumber"] or params["parcelId"],
                    precinct=params["precinct"],
                    cadastral_unit=params["cadastralUnit"],
                )
            )
        except Exception as exc:
            return _error_response(exc)

    @bp_public.route("/site-context/parcels/<path:parcel_id>/preview", methods=["GET"])
    @bp.route("/site-context/parcels/<path:parcel_id>/preview", methods=["GET"])
    @bp_public.route("/parcels/<path:parcel_id>", methods=["GET"])
    @bp.route("/parcels/<path:parcel_id>", methods=["GET"])
    def parcel_preview(parcel_id: str):
        cfg = _load_map_config()
        valid, error = _validate_config(cfg)
        if not valid:
            return jsonify({"error": error}), 503
        params = _search_payload_from_request_args()
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, cfg)
        try:
            return jsonify(
                service.get_parcel_preview(
                    parcel_id=parcel_id,
                    parcel_number=params["parcelNumber"],
                    precinct=params["precinct"],
                    cadastral_unit=params["cadastralUnit"],
                )
            )
        except Exception as exc:
            return _error_response(exc)

    @bp_public.route("/projects/<int:project_id>/site-context/import", methods=["POST"])
    @bp.route("/projects/<int:project_id>/site-context/import", methods=["POST"])
    @bp_public.route("/projects/<int:project_id>/planning-documents/import-parcel", methods=["POST"])
    @bp.route("/projects/<int:project_id>/planning-documents/import-parcel", methods=["POST"])
    def import_site_context(project_id: int):
        cfg = _load_map_config()
        valid, error = _validate_config(cfg)
        if not valid:
            return jsonify({"error": error}), 503
        payload = request.get_json(silent=True) or {}
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, cfg)
        try:
            result = service.import_site_context(project_id=project_id, payload=payload)
            status = 207 if result.get("partialImport") else 201
            return jsonify(result), status
        except Exception as exc:
            return _error_response(exc)

    @bp_public.route("/projects/<int:project_id>/site-context", methods=["GET"])
    @bp.route("/projects/<int:project_id>/site-context", methods=["GET"])
    def get_site_context(project_id: int):
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, _load_map_config())
        payload = service.get_site_context(project_id=project_id)
        if not payload:
            return jsonify({"error": "SITE_CONTEXT_NOT_FOUND", "message": "Brak zapisanego kontekstu działki."}), 404
        return jsonify(payload)

    @bp_public.route("/projects/<int:project_id>/site-context/recompute-analysis", methods=["POST"])
    @bp.route("/projects/<int:project_id>/site-context/recompute-analysis", methods=["POST"])
    def recompute_analysis(project_id: int):
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, _load_map_config())
        try:
            return jsonify(service.recompute_analysis(project_id=project_id))
        except Exception as exc:
            return _error_response(exc)

    @bp_public.route("/projects/<int:project_id>/site-context/reimport", methods=["POST"])
    @bp.route("/projects/<int:project_id>/site-context/reimport", methods=["POST"])
    def reimport_site_context(project_id: int):
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, _load_map_config())
        try:
            return jsonify(service.reimport(project_id=project_id))
        except Exception as exc:
            return _error_response(exc)

    @bp.route("/tiles/<int:z>/<int:x>/<int:y>.mvt", methods=["GET"])
    def tiles(z, x, y):
        session_id = request.args.get("sessionId")
        if not session_id:
            return jsonify({"error": "sessionId is required"}), 400

        db = get_db(current_app.config["DB_PATH"])
        service = MapService(db, _load_map_config())
        grouped = service.get_session_features(session_id)
        if mapbox_vector_tile is None:
            tile_data = json.dumps(grouped).encode("utf-8")
        else:
            tile_data = mapbox_vector_tile.encode([{"name": layer, "features": feats} for layer, feats in grouped.items()])
        return Response(tile_data, mimetype="application/x-protobuf")

    @bp.route("/export", methods=["GET"])
    def export_session():
        session_id = request.args.get("sessionId")
        fmt = request.args.get("format", "geojson")
        if fmt != "geojson":
            return jsonify({"error": "UNSUPPORTED_FORMAT"}), 400
        db = get_db(current_app.config["DB_PATH"])
        service = MapService(db, _load_map_config())
        grouped = service.get_session_features(session_id)
        features = []
        for layer, fts in grouped.items():
            for ft in fts:
                ft["properties"] = {**(ft.get("properties") or {}), "layer": layer}
                features.append(ft)
        return jsonify({"type": "FeatureCollection", "features": features})

    app.register_blueprint(bp)
    app.register_blueprint(bp_public)
