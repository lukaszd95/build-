import json
import os
from unittest.mock import patch

from app import create_app


def _setup_app(tmp_path):
    map_cfg = tmp_path / "map.config.json"
    map_cfg.write_text(json.dumps({"parcels": {"provider": "stub"}, "context": {}, "utilities": {}}), encoding="utf-8")
    previous_map_config = os.environ.get("MAP_CONFIG_PATH")
    os.environ["MAP_CONFIG_PATH"] = str(map_cfg)
    db_path = tmp_path / "test.db"
    app = create_app({"TESTING": True, "DB_PATH": str(db_path)})
    return app, previous_map_config


def _restore_map_config(previous):
    if previous is None:
        os.environ.pop("MAP_CONFIG_PATH", None)
    else:
        os.environ["MAP_CONFIG_PATH"] = previous


def test_parcel_search_timeout_returns_504(tmp_path):
    app, previous_map_config = _setup_app(tmp_path)
    client = app.test_client()
    try:
        with patch("services.spatial_source_gateway.SpatialSourceGateway.fetch_parcel_candidates", side_effect=TimeoutError("timed out")):
            resp = client.get("/api/site-context/parcels/search?parcelNumber=12&precinct=0001&cadastralUnit=Warszawa")
        assert resp.status_code == 504
        body = resp.get_json()
        assert body["error"] == "EXTERNAL_SOURCE_TIMEOUT"
    finally:
        _restore_map_config(previous_map_config)


def test_import_persists_partial_when_sources_or_analysis_fail(tmp_path):
    app, previous_map_config = _setup_app(tmp_path)
    client = app.test_client()
    parcel = {
        "id": "stub-123-0001",
        "parcelId": "stub-123-0001",
        "parcelNumber": "123/4",
        "precinct": "0001",
        "cadastralUnit": "Warszawa",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[21.0, 52.0], [21.01, 52.0], [21.01, 52.01], [21.0, 52.01], [21.0, 52.0]]],
        },
    }
    try:
        with patch("services.map_service.ContextProvider.fetch_context", side_effect=RuntimeError("context unavailable")), patch(
            "services.map_service.SiteBuildabilityAnalysisService.compute", side_effect=RuntimeError("analysis failed")
        ):
            resp = client.post("/api/projects/1/site-context/import", json={"parcel": parcel, "siteAnalysisBufferMeters": 30})

        assert resp.status_code == 207
        body = resp.get_json()
        assert body["partialImport"] is True
        summary = body["siteContext"]["importSummary"]
        assert summary["status"] in {"error", "unavailable"}
        assert any("SPATIAL_ANALYSIS_ERROR" in err for err in summary["partialErrors"])
        assert body["siteContext"]["primaryParcelId"] == "stub-123-0001"
    finally:
        _restore_map_config(previous_map_config)
