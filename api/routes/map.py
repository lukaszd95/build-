import io
import json
import os
import time
from collections import defaultdict

from flask import Blueprint, Response, current_app, jsonify, request
try:
    import mapbox_vector_tile
except Exception:
    mapbox_vector_tile = None

from services.map_service import MapService
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


def register_map_routes(app):
    bp = Blueprint("map", __name__, url_prefix="/api/map")

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
            result = service.resolve(payload)
            return jsonify(result)
        except RuntimeError as exc:
            if str(exc) == "PARCEL_PROVIDER_NOT_CONFIGURED":
                return jsonify({"error": str(exc)}), 503
            return jsonify({"error": str(exc)}), 500
        except Exception as exc:
            return jsonify({"error": str(exc), "manualMode": True}), 404

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
