from shapely import wkb
from shapely.geometry import Point
from unittest.mock import patch

from services.parcel_domain import ParcelQuery
from services.parcel_providers import ULDKProvider


def test_parse_uldk_payload_with_json_geom_wkt():
    provider = ULDKProvider({"source_srid": 2180})
    parcel_id, source_wkb, source_wkt = provider._parse_uldk_payload('{"id":"141201_1.0001.6509","geom_wkt":"POINT (600000 500000)"}')

    assert parcel_id == "141201_1.0001.6509"
    assert source_wkb == ""
    assert source_wkt == "POINT (600000 500000)"


def test_geometry_to_geojson_supports_wkb_and_local_conversion():
    provider = ULDKProvider({"source_srid": 4326})
    geom_hex = wkb.dumps(Point(21.0, 52.0), hex=True)

    geojson = provider._geometry_to_geojson(source_wkb=geom_hex, source_wkt="", source_srid=4326)

    assert geojson is not None
    assert geojson["type"] == "Point"
    assert geojson["coordinates"] == (21.0, 52.0)


def test_resolve_request_name_is_getparcelbyid_for_parcel_id(monkeypatch):
    provider = ULDKProvider({"source_srid": 2180})
    seen = {}

    def fake_request(*, req_path, query_params):
        seen["req_path"] = req_path
        seen["query_params"] = dict(query_params)
        return '{"id":"141201_1.0001.6509","geom_wkt":"POINT (600000 500000)"}'

    monkeypatch.setattr(provider, "_request_uldk", fake_request)

    result = provider.resolve(ParcelQuery(parcel_id="141201_1.0001.6509"))

    assert result.ok is True
    assert seen["req_path"] == "GetParcelById"
    assert seen["query_params"]["result"] == "id,geom_wkb,geom_wkt"
    assert seen["query_params"]["srid"] == "2180"


def test_resolve_request_name_is_getparcelbyidornr_for_number_and_precinct(monkeypatch):
    provider = ULDKProvider({"source_srid": 2180})
    seen = {}

    def fake_request(*, req_path, query_params):
        seen["req_path"] = req_path
        seen["query_params"] = dict(query_params)
        return '{"id":"141201_1.0001.6509","geom_wkt":"POINT (600000 500000)"}'

    monkeypatch.setattr(provider, "_request_uldk", fake_request)

    result = provider.resolve(ParcelQuery(parcel_number="6509", precinct="0001", cadastral_unit="Warszawa"))

    assert result.ok is True
    assert seen["req_path"] == "GetParcelByIdOrNr"
    assert seen["query_params"]["result"] == "id,geom_wkb,geom_wkt"
    assert seen["query_params"]["srid"] == "2180"


def test_reprojection_from_2180_to_4326_applied_exactly_once():
    provider = ULDKProvider({"source_srid": 2180})
    source_wkt = "POINT (600000 500000)"

    from services import parcel_providers as module

    call_count = {"n": 0}
    original_transform = module.shp_transform

    def counting_transform(func, geom):
        call_count["n"] += 1
        return original_transform(func, geom)

    with patch.object(module, "shp_transform", side_effect=counting_transform):
        geojson = provider._geometry_to_geojson(source_wkb="", source_wkt=source_wkt, source_srid=2180)

    assert geojson is not None
    assert geojson["type"] == "Point"
    lon, lat = geojson["coordinates"]
    assert -180 <= lon <= 180
    assert -90 <= lat <= 90
    assert call_count["n"] == 1
