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
from services.parcel_domain import ParcelQuery
from services.parcel_orchestrator import ResolveParcelUseCase
from services.parcel_providers import KIEGProvider, MonitoringProvider, PowiatWFSProvider, ULDKProvider
from utils.db import get_db


rate_limit_store = defaultdict(list)


def _as_bool(raw: str | None, *, default: bool = False) -> bool:
    if raw is None:
        return default
    value = str(raw).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}

def _load_map_config():
    path = os.getenv("MAP_CONFIG_PATH", "config/map.config.json")
    if not os.path.exists(path):
        return _apply_geoportal_env_overrides({})
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return _apply_geoportal_env_overrides(cfg)


def _apply_geoportal_env_overrides(cfg: dict) -> dict:
    cfg = dict(cfg or {})
    parcels = dict(cfg.get("parcels") or {})
    wfs = dict(parcels.get("wfs") or {})

    env_url = (os.getenv("GEO_WFS_URL") or "").strip()
    env_type = (os.getenv("GEO_WFS_TYPENAME") or "").strip()
    timeout_ms = (os.getenv("GEO_WFS_TIMEOUT_MS") or "").strip()

    if env_url:
        wfs["url"] = env_url
    if env_type:
        wfs["typeName"] = env_type
    if timeout_ms:
        try:
            wfs["timeout"] = max(float(timeout_ms) / 1000.0, 1.0)
        except ValueError:
            pass

    parcels["wfs"] = wfs
    parcels.setdefault("provider", "wfs")
    cfg["parcels"] = parcels
    return cfg


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




def _build_orchestrator(cfg):
    parcels_cfg = cfg.get("parcels") or {}
    uldk_cfg = dict((cfg.get("providers") or {}).get("uldk") or {})
    uldk_cfg.setdefault("url", os.getenv("GEO_ULDK_URL", "https://uldk.gugik.gov.pl"))
    uldk_cfg.setdefault("timeout", float(os.getenv("GEO_ULDK_TIMEOUT_S", "8")))
    providers_cfg = cfg.get("providers") or {}
    wfs_expert_fallback = _as_bool(
        os.getenv("GEO_WFS_EXPERT_FALLBACK"),
        default=bool((providers_cfg.get("wfs") or {}).get("expert_fallback_enabled", False)),
    )
    return ResolveParcelUseCase(
        uldk=ULDKProvider(uldk_cfg),
        wfs=PowiatWFSProvider({"provider": "wfs", "wfs": parcels_cfg.get("wfs") or {}}),
        kieg=KIEGProvider(),
        monitoring=MonitoringProvider(),
        wfs_expert_fallback_enabled=wfs_expert_fallback,
    )

def _build_parcel_provider(cfg):
    from services.map_service import ParcelProvider

    parcels_cfg = cfg.get("parcels") or {}
    return ParcelProvider(parcels_cfg)


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


def _validate_parcel_search_params(params: dict[str, str]) -> tuple[bool, str | None]:
    parcel_number = (params.get("parcelNumber") or params.get("parcelId") or "").strip()
    if not parcel_number:
        return False, "Nieprawidłowe parametry wyszukiwania działki"
    return True, None


def _error_response(exc: Exception):
    code = str(exc)
    cause_detail = str(exc.__cause__).strip() if getattr(exc, "__cause__", None) else ""
    detail = cause_detail or code.strip()

    def _payload(error_code: str, message: str, status_code: int):
        return jsonify({"error": error_code, "message": message}), status_code

    mapping = {
        "MISSING_PARCEL": ("Brak działki w zapytaniu.", 400),
        "MISSING_PARCEL_NUMBER": ("Brak numeru działki.", 400),
        "INVALID_PARCEL_SEARCH_PARAMS": ("Nieprawidłowe parametry wyszukiwania działki", 400),
        "PARCEL_NOT_FOUND": ("Nie znaleziono działki.", 404),
        "MULTIPLE_PARCEL_MATCHES": ("Wiele działek pasuje do zapytania.", 409),
        "MISSING_GEOMETRY": ("Brak geometrii działki.", 422),
        "PARCEL_PROVIDER_NOT_CONFIGURED": ("Brak konfiguracji źródła przestrzennego.", 503),
        "EXTERNAL_SOURCE_ERROR": ("Usługa Geoportalu jest tymczasowo niedostępna. Spróbuj ponownie za chwilę.", 502),
        "EXTERNAL_SOURCE_UNAVAILABLE": ("Usługa Geoportalu jest tymczasowo niedostępna. Spróbuj ponownie za chwilę.", 502),
    }
    if code in mapping:
        message, status = mapping[code]
        if code in {"EXTERNAL_SOURCE_ERROR", "EXTERNAL_SOURCE_UNAVAILABLE"}:
            detail_lower = detail.lower()
            if "pusty wynik" in detail_lower:
                message = "Nie znaleziono działki dla podanych danych."
            elif "html" in detail_lower:
                message = "Usługa działek chwilowo niedostępna."
            elif "nieoczekiwaną odpowiedź" in detail_lower:
                message = "Źródło danych zwróciło nieoczekiwaną odpowiedź."
            else:
                message = "Usługa Geoportalu jest tymczasowo niedostępna. Spróbuj ponownie za chwilę."
        if code.startswith("EXTERNAL_SOURCE"):
            current_app.logger.error("parcel.search.external_mapped_error code=%s detail=%s", code, detail)
        return _payload(code, message, status)
    lowered = code.lower()
    if "timeout" in lowered:
        current_app.logger.error("parcel.search.external_mapped_error code=EXTERNAL_SOURCE_TIMEOUT detail=%s", detail)
        return _payload(
            "EXTERNAL_SOURCE_TIMEOUT",
            "Przekroczono czas odpowiedzi zewnętrznej usługi Geoportalu. Spróbuj ponownie za chwilę.",
            504,
        )
    if "wfs" in lowered or "geoportal" in lowered:
        mapped_code = "EXTERNAL_SOURCE_UNAVAILABLE" if "target" in lowered and "is not reachable" in lowered else "EXTERNAL_SOURCE_ERROR"
        current_app.logger.error("parcel.search.external_mapped_error code=%s detail=%s", mapped_code, detail)
        return _payload(
            mapped_code,
            "Usługa Geoportalu jest tymczasowo niedostępna. Spróbuj ponownie za chwilę.",
            502,
        )
    return _payload(code or "IMPORT_FAILED", "Nie udało się przetworzyć żądania.", 500)


def _is_external_source_status(status_code: int, payload: dict[str, str] | None) -> bool:
    if status_code not in {502, 504}:
        return False
    error_code = (payload or {}).get("error")
    return error_code in {"EXTERNAL_SOURCE_ERROR", "EXTERNAL_SOURCE_UNAVAILABLE", "EXTERNAL_SOURCE_TIMEOUT"}


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
        current_app.logger.info("parcel.search.request params=%s", {k: params.get(k) for k in ["parcelNumber", "parcelId", "precinct", "cadastralUnit"]})
        valid_params, validation_message = _validate_parcel_search_params(params)
        if not valid_params:
            return jsonify({"error": validation_message}), 400
        db = get_db(current_app.config["DB_PATH"])
        service = _build_site_context_import_service(db, cfg)
        normalized_params = {
            "parcel_number": params["parcelNumber"] or params["parcelId"],
            "precinct": params["precinct"],
            "cadastral_unit": params["cadastralUnit"],
        }
        current_app.logger.info("parcel.search.normalized params=%s", normalized_params)
        try:
            result = service.search_parcels(**normalized_params)
            current_app.logger.info("parcel.search.response status=200 count=%s", len(result.get("items") or []))
            return jsonify(result)
        except Exception as exc:
            status_payload = _error_response(exc)
            response, status_code = status_payload
            error_payload = response.get_json(silent=True) or {}
            legacy_parcel_search = request.path.endswith("/api/parcels/search")

            if legacy_parcel_search and _is_external_source_status(status_code, error_payload):
                degraded = {
                    "items": [],
                    "sources": {
                        "parcel": {
                            "sourceName": "unavailable",
                            "dataType": "vector",
                            "licenseNote": "Źródło tymczasowo niedostępne.",
                            "accuracyNote": "Brak danych z serwisu zewnętrznego.",
                            "requestUrl": "",
                            "statusCode": status_code,
                            "contentType": "",
                            "detectedFormat": "unknown",
                            "parserUsed": "none",
                            "errorType": error_payload.get("error") or "external_source_error",
                            "errorMessage": error_payload.get("message") or "",
                            "warnings": [error_payload.get("message") or "Problem ze źródłem danych przestrzennych."],
                        }
                    },
                    "empty": True,
                    "degraded": True,
                    "error": error_payload.get("error"),
                    "message": error_payload.get("message"),
                }
                current_app.logger.warning("parcel.search.degraded status=%s error=%s", status_code, exc)
                return jsonify(degraded), 200

            current_app.logger.exception("parcel.search.error status=%s error=%s", status_code, exc)
            return status_payload

    @bp_public.route("/parcels/resolve", methods=["POST"])
    @bp.route("/parcels/resolve", methods=["POST"])
    def resolve_parcel_orchestrated():
        cfg = _load_map_config()
        orchestrator = _build_orchestrator(cfg)
        payload = request.get_json(silent=True) or {}
        query = ParcelQuery(
            parcel_id=(payload.get("parcel_id") or payload.get("parcelId") or "").strip(),
            parcel_number=(payload.get("parcel_number") or payload.get("parcelNumber") or "").strip(),
            precinct=(payload.get("precinct") or payload.get("obreb") or "").strip(),
            cadastral_unit=(payload.get("cadastral_unit") or payload.get("cadastralUnit") or payload.get("municipality") or "").strip(),
            coordinates=tuple(payload.get("coordinates")) if isinstance(payload.get("coordinates"), (list, tuple)) and len(payload.get("coordinates")) == 2 else None,
        )
        result = orchestrator.execute(
            query,
            route_mode=(payload.get("route_mode") or "AUTO"),
            correlation_id=(request.headers.get("X-Correlation-ID") or "").strip(),
        )
        http_status = 200
        if result.status == "INVALID_INPUT":
            http_status = 400
        elif result.status == "NOT_FOUND":
            http_status = 404
        elif result.status == "INFRA_ERROR":
            http_status = 503
        return jsonify(result.to_dict()), http_status

    @bp_public.route("/site-context/geoportal/health", methods=["GET"])
    @bp.route("/site-context/geoportal/health", methods=["GET"])
    @bp_public.route("/geoportal/health", methods=["GET"])
    @bp.route("/geoportal/health", methods=["GET"])
    def geoportal_health():
        cfg = _load_map_config()
        provider = _build_parcel_provider(cfg)
        result = provider.diagnose_wfs_connectivity()
        status = 200 if result.get("ok") else 503
        current_app.logger.info("geoportal.health result=%s", result)
        return jsonify(result), status

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
            return jsonify(None), 200
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
