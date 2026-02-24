import json
import os

from app import create_app
from services.map_service import normalizeParcelInput


def test_normalize_parcel_input():
    result = normalizeParcelInput(" 0123-04 ", "1", "Łódź")
    assert result["nrMain"] == "123"
    assert result["nrSub"] == "4"
    assert result["nrCanonical"] == "123/4"
    assert result["obrebCanonical"] == "0001"
    assert "lodz" in [v.lower() for v in result["miejscowoscVariants"]]


def test_resolve_and_export_and_tiles(tmp_path):
    map_cfg = tmp_path / "map.config.json"
    map_cfg.write_text(
        json.dumps(
            {
                "parcels": {"provider": "stub"},
                "context": {},
                "utilities": {},
            }
        ),
        encoding="utf-8",
    )
    previous_map_config = os.environ.get("MAP_CONFIG_PATH")
    os.environ["MAP_CONFIG_PATH"] = str(map_cfg)

    try:
        db_path = tmp_path / "test.db"
        app = create_app({"TESTING": True, "DB_PATH": str(db_path)})
        client = app.test_client()

        payload = {
            "nrDzialki": "123/4",
            "obreb": "0001",
            "miejscowosc": "Warszawa",
            "bufferMeters": 30,
        }
        resolve_resp = client.post("/api/map/parcel/resolve", json=payload)
        assert resolve_resp.status_code == 200
        data = resolve_resp.get_json()
        assert data["sessionId"]
        assert data["plot"]["type"] == "Feature"
        assert len(data["bbox4326"]) == 4

        export_resp = client.get(f"/api/map/export?sessionId={data['sessionId']}&format=geojson")
        assert export_resp.status_code == 200
        export_data = export_resp.get_json()
        assert export_data["type"] == "FeatureCollection"
        assert len(export_data["features"]) >= 1

        tiles_resp = client.get(f"/api/map/tiles/0/0/0.mvt?sessionId={data['sessionId']}")
        assert tiles_resp.status_code == 200
        assert tiles_resp.data
    finally:
        if previous_map_config is None:
            os.environ.pop("MAP_CONFIG_PATH", None)
        else:
            os.environ["MAP_CONFIG_PATH"] = previous_map_config
