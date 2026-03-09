import json
import os
import sqlite3
from unittest.mock import patch

from app import create_app
from services.site_context_ai_adapter import buildSiteContextForAI


def _setup_app(tmp_path):
    map_cfg = tmp_path / "map.config.json"
    map_cfg.write_text(json.dumps({"parcels": {"provider": "stub"}, "context": {}, "utilities": {}}), encoding="utf-8")
    previous_map_config = os.environ.get("MAP_CONFIG_PATH")
    os.environ["MAP_CONFIG_PATH"] = str(map_cfg)
    db_path = tmp_path / "test.db"
    app = create_app({"TESTING": True, "DB_PATH": str(db_path)})
    return app, str(db_path), previous_map_config


def _restore_map_config(previous):
    if previous is None:
        os.environ.pop("MAP_CONFIG_PATH", None)
    else:
        os.environ["MAP_CONFIG_PATH"] = previous


def _parcel():
    return {
        "id": "stub-123-0001",
        "parcelId": "stub-123-0001",
        "parcelNumber": "123/4",
        "precinct": "0001",
        "cadastralUnit": "Warszawa",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[21.0000, 52.0000], [21.0010, 52.0000], [21.0010, 52.0010], [21.0000, 52.0010], [21.0000, 52.0000]]],
        },
    }


def test_integration_import_creates_and_persists_layers_and_readback(tmp_path):
    app, db_path, previous = _setup_app(tmp_path)
    client = app.test_client()
    try:
        fake_session_layers = {
            "buildings": [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[21.0002, 52.0002], [21.0004, 52.0002], [21.0004, 52.0004], [21.0002, 52.0004], [21.0002, 52.0002]]]}, "properties": {"id": "b1"}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[21.0011, 52.0002], [21.0012, 52.0002], [21.0012, 52.0003], [21.0011, 52.0003], [21.0011, 52.0002]]]}, "properties": {"id": "b2"}},
            ],
            "roads": [],
            "utilities": [
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[21.0000, 52.0000], [21.0010, 52.0010]]}, "properties": {"id": "u1"}}
            ],
        }
        fake_resolve = {
            "sessionId": "session-1",
            "warnings": [],
            "plot": {"type": "Feature", "geometry": _parcel()["geometry"], "properties": {"id": "stub-123-0001"}},
            "buffer": {"type": "Feature", "geometry": _parcel()["geometry"], "properties": {"bufferMeters": 30}},
            "bbox4326": [21.0, 52.0, 21.001, 52.001],
            "sources": {},
            "candidates": [],
            "wmsOverlays": [],
        }

        with patch("services.map_service.MapService.resolve", return_value=fake_resolve), patch(
            "services.map_service.MapService.get_session_features", return_value=fake_session_layers
        ):
            import_resp = client.post("/api/projects/1/site-context/import", json={"parcel": _parcel(), "siteAnalysisBufferMeters": 5000})

        assert import_resp.status_code in (201, 207)
        payload = import_resp.get_json()
        layers = {layer["layerKey"]: layer for layer in payload["siteContext"]["layers"]}

        # mapowanie warstw + klasyfikacja budynków
        assert layers["road_edge"]["status"] in {"loaded", "empty"}
        assert layers["existing_building"]["status"] == "loaded"
        assert layers["adjacent_building"]["status"] == "loaded"
        assert len(layers["existing_building"]["features"]) == 1
        assert len(layers["adjacent_building"]["features"]) == 1

        # warstwy pochodne i analiza
        assert layers["utility_protection_zone"]["status"] in {"loaded", "derived"}
        assert layers["offset_from_boundary_zone"]["status"] in {"loaded", "derived"}
        assert layers["buildable_area"]["status"] in {"loaded", "derived"}
        assert payload["siteContext"]["analysisResult"]["buildableArea"] is not None

        # puste i niedostępne warstwy
        assert any(layer["status"] == "empty" for layer in payload["siteContext"]["layers"])
        assert any(layer["status"] == "unavailable" for layer in payload["siteContext"]["layers"])

        # odczyt projektu zwraca warstwy
        get_resp = client.get("/api/projects/1/site-context")
        assert get_resp.status_code == 200
        readback = get_resp.get_json()
        assert readback["layers"]
        assert any(layer["layerKey"] == "existing_building" for layer in readback["layers"])

        # warstwy są zapisane w DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) as cnt FROM site_layers WHERE projectId = ?", (1,)).fetchone()
        assert row["cnt"] > 0
        conn.close()

    finally:
        _restore_map_config(previous)


def test_ai_adapter_serializes_expected_payload_shape():
    site_context = {
        "projectId": 1,
        "id": "ctx-1",
        "primaryParcelId": "parcel-1",
        "siteBoundary": {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]]},
        "analysisBufferMeters": 30,
        "layers": [
            {
                "layerKey": "plot_boundary",
                "label": "Plot",
                "status": "loaded",
                "sourceType": "parcel",
                "geometryType": "Polygon",
                "metadata": {"group": "core"},
                "features": [{"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}, "properties": {"a": 1}}],
            },
            {
                "layerKey": "buildable_area",
                "label": "Buildable",
                "status": "derived",
                "sourceType": "analysis",
                "geometryType": "Polygon",
                "metadata": {"group": "analysis"},
                "features": [{"geometry": {"type": "Polygon", "coordinates": [[[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5], [0, 0]]]}, "properties": {}}],
            },
            {"layerKey": "adjacent_building", "status": "empty", "sourceType": "context", "geometryType": "Polygon", "features": []},
        ],
        "objects": [
            {
                "id": "obj-1",
                "layerKey": "adjacent_building",
                "objectType": "Polygon",
                "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [1.5, 1], [1.5, 1.5], [1, 1.5], [1, 1]]]},
                "properties": {},
                "withinPlot": False,
                "withinSiteBoundary": True,
                "intersectsPlot": False,
                "sourceMetadata": {"collision": False, "plotRelation": "site_context"},
            }
        ],
        "analysisResult": {
            "constraints": [{"type": "no_build_zone"}],
            "observations": ["obs"],
            "warnings": ["warn"],
            "buildableArea": 12.3,
            "buildingCandidates": [{"geometry": {"type": "Point", "coordinates": [0.2, 0.2]}}],
        },
    }

    ai_payload = buildSiteContextForAI(site_context)

    assert ai_payload["projectId"] == 1
    assert ai_payload["siteContextId"] == "ctx-1"
    assert ai_payload["parcel"]["primaryParcelId"] == "parcel-1"
    assert len(ai_payload["layers"]) == 2  # bez pustej warstwy
    assert ai_payload["analysisLayers"]
    assert ai_payload["analysisSummary"]["hasBuildableArea"] is True
    assert ai_payload["analysisSummary"]["candidateCount"] == 1
    assert ai_payload["importantObjects"]
