from __future__ import annotations

from services.network_core import RetryExecutor
from services.parcel_domain import DiagnosticInfo, GeometryPayload, ParcelQuery, ProviderResult
from services.parcel_orchestrator import ResolveParcelUseCase


class _FakeProvider:
    def __init__(self, results):
        self.results = list(results)

    def resolve(self, query, route_mode="AUTO"):
        item = self.results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeMonitoring:
    def __init__(self):
        self.data = {}

    def record(self, provider, ok, error_code=""):
        self.data.setdefault(provider, []).append((ok, error_code))


class _FakeKieg:
    def resolve_preview(self, query):
        return {"ok": True}


def _success(provider_name="ULDK"):
    return ProviderResult(
        ok=True,
        status="SUCCESS",
        provider=provider_name,
        canonical_parcel_id="141201_1.0001.6509",
        geometry=GeometryPayload(format="GeoJSON", srid=4326, data={"type": "Point", "coordinates": [21.0, 52.0]}),
        diagnostics=DiagnosticInfo(network_route="AUTO", attempts=1, latency_ms=10, provider=provider_name),
    )


def test_retry_executor_does_not_retry_proxy_403():
    executor = RetryExecutor(retries=(0.0, 0.2, 0.5))
    calls = {"n": 0}

    def _run():
        calls["n"] += 1
        raise RuntimeError("Tunnel connection failed: 403 Forbidden")

    try:
        executor.execute(_run)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError")

    assert calls["n"] == 1


def test_orchestrator_returns_success_partial_when_fallback_wfs_succeeds():
    uldk = _FakeProvider([RuntimeError("upstream timeout")])
    wfs = _FakeProvider([_success("WFS")])
    monitoring = _FakeMonitoring()
    use_case = ResolveParcelUseCase(uldk=uldk, wfs=wfs, kieg=_FakeKieg(), monitoring=monitoring)

    result = use_case.execute(ParcelQuery(parcel_number="6509", precinct="0001", cadastral_unit="Warszawa"))

    assert result.status == "SUCCESS_PARTIAL"
    assert "FALLBACK_USED" in result.quality_flags


def test_orchestrator_returns_infra_error_when_all_upstreams_fail():
    uldk = _FakeProvider([RuntimeError("upstream timeout")])
    wfs = _FakeProvider([RuntimeError("wfs down")])
    monitoring = _FakeMonitoring()
    use_case = ResolveParcelUseCase(uldk=uldk, wfs=wfs, kieg=_FakeKieg(), monitoring=monitoring)

    result = use_case.execute(ParcelQuery(parcel_number="6509", precinct="0001", cadastral_unit="Warszawa"))

    assert result.status == "INFRA_ERROR"
    assert "UPSTREAM_UNAVAILABLE" in result.quality_flags
