import json
import os

from app import create_app
from services.map_service import normalizeParcelInput


def test_normalize_parcel_input():
    result = normalizeParcelInput(" 0123-04 ", "1", "Łódź")
    assert result["nrMain"] == "0123"
    assert result["nrSub"] == "04"
    assert result["nrCanonical"] == "0123/04"
    assert result["obrebCanonical"] == "1"
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

        search_resp = client.get("/api/parcels/search?nrDzialki=137&obreb=3-15-11&miejscowosc=Warszawa")
        assert search_resp.status_code == 200
        search_data = search_resp.get_json()
        assert search_data["items"]


        sc_search = client.get("/api/site-context/parcels/search?parcelNumber=137&precinct=3-15-11&cadastralUnit=Warszawa")
        assert sc_search.status_code == 200
        assert sc_search.get_json()["items"]

        bad_search = client.get("/api/site-context/parcels/search")
        assert bad_search.status_code == 400
        assert bad_search.get_json()["error"] == "Nieprawidłowe parametry wyszukiwania działki"

        preview_resp = client.get(
            f"/api/site-context/parcels/{search_data['items'][0]['parcelId']}/preview?parcelNumber=137&precinct=3-15-11&cadastralUnit=Warszawa"
        )
        assert preview_resp.status_code == 200
        preview = preview_resp.get_json()
        assert preview["geometry"]
        assert preview["metadata"]["parcelId"]

        import_resp = client.post(
            "/api/projects/1/planning-documents/import-parcel",
            json={
                "parcel": search_data["items"][0],
                "nrDzialki": "123/4",
                "obreb": "0001",
                "miejscowosc": "Warszawa",
            },
        )
        assert import_resp.status_code in (201, 207)
        import_data = import_resp.get_json()
        assert import_data["imported"]["source"] == "geoportal"
        assert import_data["siteContext"]["projectId"] == 1
        assert import_data["siteContext"]["analysisResult"]["buildableArea"] is not None
        assert import_data["siteContext"]["analysisResult"]["maxBuildingEnvelope"] is not None
        assert import_data["siteContext"]["analysisResult"]["preferredBuildingZone"] is not None
        assert isinstance(import_data["siteContext"]["analysisResult"].get("buildingCandidates"), list)
        assert isinstance(import_data["siteContext"]["layers"], list)
        site_boundary_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "site_boundary"), None)
        assert site_boundary_layer is not None
        assert site_boundary_layer["status"] == "loaded"
        assert site_boundary_layer["features"]

        derived_offset_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "offset_from_boundary_zone"), None)
        assert derived_offset_layer is not None
        assert derived_offset_layer["status"] in {"loaded", "derived"}

        derived_utility_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "utility_protection_zone"), None)
        assert derived_utility_layer is not None
        assert derived_utility_layer["status"] in {"loaded", "derived"}

        buildable_area_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "buildable_area"), None)
        assert buildable_area_layer is not None
        assert buildable_area_layer["status"] in {"loaded", "derived"}

        preferred_zone_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "preferred_building_zone"), None)
        assert preferred_zone_layer is not None
        assert preferred_zone_layer["status"] in {"loaded", "derived"}

        adjacent_layer = next((layer for layer in import_data["siteContext"]["layers"] if layer["layerKey"] == "adjacent_building"), None)
        assert adjacent_layer is not None
        assert adjacent_layer["status"] in {"loaded", "empty"}

        adjacent_objects = [obj for obj in import_data["siteContext"]["objects"] if obj["layerKey"] == "adjacent_building"]
        for obj in adjacent_objects:
            assert obj["withinPlot"] is False
            assert obj["withinSiteBoundary"] is True
            assert obj["intersectsPlot"] is False

        utility_objects = [obj for obj in import_data["siteContext"]["objects"] if obj["layerKey"] == "utility_node"]
        for obj in utility_objects:
            assert obj["sourceMetadata"].get("collision") == bool(obj["intersectsPlot"])

        tree_objects = [obj for obj in import_data["siteContext"]["objects"] if obj["layerKey"] == "tree"]
        for obj in tree_objects:
            assert obj["sourceMetadata"].get("treeContext") in {"plot", "neighborhood"}
        context_resp = client.get("/api/projects/1/site-context")
        assert context_resp.status_code == 200
        context_data = context_resp.get_json()
        assert context_data["primaryParcelId"]
        assert isinstance(context_data["objects"], list)
        assert "importSummary" in context_data
        assert context_data["importSummary"]["status"] in {"loaded", "empty", "derived", "manual_placeholder", "unavailable", "error"}

        import_v2 = client.post(
            "/api/projects/1/site-context/import",
            json={"parcelNumber": "123/4", "precinct": "0001", "cadastralUnit": "Warszawa", "siteAnalysisBufferMeters": 30},
        )
        assert import_v2.status_code in (201, 207)

        recompute_resp = client.post("/api/projects/1/site-context/recompute-analysis")
        assert recompute_resp.status_code in (200, 201, 207)

        reimport_resp = client.post("/api/projects/1/site-context/reimport")
        assert reimport_resp.status_code in (200, 201, 207)
    finally:
        if previous_map_config is None:
            os.environ.pop("MAP_CONFIG_PATH", None)
        else:
            os.environ["MAP_CONFIG_PATH"] = previous_map_config
