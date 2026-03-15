from unittest.mock import patch

from services.map_service import ProviderMeta
from services.parcel_domain import DiagnosticInfo, GeometryPayload, ProviderResult
from services.spatial_source_gateway import SpatialSourceGateway


def test_gateway_uses_uldk_as_primary_source():
    gateway = SpatialSourceGateway({"parcels": {"provider": "wfs", "wfs": {}}})

    uldk_result = ProviderResult(
        ok=True,
        status="SUCCESS",
        provider="ULDK",
        canonical_parcel_id="141201_1.0001.6509",
        geometry=GeometryPayload(format="GeoJSON", srid=4326, data={"type": "Point", "coordinates": [21.0, 52.0]}),
        diagnostics=DiagnosticInfo(provider="ULDK"),
    )

    with patch.object(gateway.uldk, "resolve", return_value=uldk_result) as uldk_resolve, patch.object(gateway.wfs, "resolve") as wfs_resolve:
        candidates, meta, normalized = gateway.fetch_parcel_candidates(nr_dzialki="6509", obreb="0001", miejscowosc="Warszawa")

    assert candidates
    assert candidates[0]["id"] == "141201_1.0001.6509"
    assert meta.sourceName == "ULDK"
    assert normalized["nrCanonical"] == "6509"
    uldk_resolve.assert_called_once()
    wfs_resolve.assert_not_called()


def test_gateway_disables_wfs_fallback_by_default_when_uldk_is_unavailable():
    gateway = SpatialSourceGateway({"parcels": {"provider": "wfs", "wfs": {}}})

    with patch.object(
        gateway.uldk,
        "resolve",
        return_value=ProviderResult(ok=False, status="INFRA_ERROR", provider="ULDK", diagnostics=DiagnosticInfo(provider="ULDK", error_code="UPSTREAM_UNAVAILABLE")),
    ), patch.object(gateway.wfs, "resolve") as wfs_resolve:
        candidates, meta, _normalized = gateway.fetch_parcel_candidates(nr_dzialki="6509", obreb="0001", miejscowosc="Warszawa")

    assert candidates == []
    assert isinstance(meta, ProviderMeta)
    assert meta.sourceName == "ULDK"
    assert any("bez fallback WFS" in warning for warning in meta.warnings)
    wfs_resolve.assert_not_called()


def test_gateway_uses_wfs_only_in_expert_fallback_mode():
    gateway = SpatialSourceGateway({"parcels": {"provider": "wfs", "wfs": {}}, "providers": {"wfs": {"expert_fallback_enabled": True}}})

    with patch.object(
        gateway.uldk,
        "resolve",
        return_value=ProviderResult(ok=False, status="INFRA_ERROR", provider="ULDK", diagnostics=DiagnosticInfo(provider="ULDK", error_code="UPSTREAM_UNAVAILABLE")),
    ), patch.object(
        gateway.wfs,
        "resolve",
        return_value=ProviderResult(
            ok=True,
            status="SUCCESS",
            provider="WFS",
            canonical_parcel_id="fallback-id",
            geometry=GeometryPayload(format="GeoJSON", srid=4326, data={"type": "Point", "coordinates": [20.0, 50.0]}),
            diagnostics=DiagnosticInfo(provider="WFS"),
            attributes={"sourceName": "WFS", "statusCode": 200},
        ),
    ):
        candidates, meta, _normalized = gateway.fetch_parcel_candidates(nr_dzialki="6509", obreb="0001", miejscowosc="Warszawa")

    assert candidates
    assert candidates[0]["id"] == "fallback-id"
    assert isinstance(meta, ProviderMeta)
    assert meta.sourceName == "WFS"
