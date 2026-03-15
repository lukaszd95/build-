from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from services.map_service import ParcelProvider, normalizeParcelInput
from services.parcel_domain import DiagnosticInfo, GeometryPayload, ParcelQuery, ProviderResult


class ULDKProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        self.url = (self.config.get("url") or "https://uldk.gugik.gov.pl/").rstrip("/")
        self.timeout = float(self.config.get("timeout", 10))

    def resolve(self, query: ParcelQuery, *, route_mode: str = "AUTO") -> ProviderResult:
        started = time.time()
        if not query.parcel_id and not query.parcel_number:
            return ProviderResult(
                ok=False,
                status="INVALID_INPUT",
                provider="ULDK",
                diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", error_code="INVALID_INPUT", error_message="parcel_id lub parcel_number wymagane"),
            )

        # Minimalna ścieżka produkcyjna: żądanie by id lub fallback po numerze działki.
        if query.parcel_id:
            req_path = "GetParcelById"
            query_params = {"id": query.parcel_id, "result": "geom_wkt,teryt"}
        else:
            req_path = "GetParcelByNum"
            query_params = {"voivodeship": "", "county": "", "commune": query.cadastral_unit, "precinct": query.precinct, "parcel": query.parcel_number, "result": "geom_wkt,teryt"}

        request_url = f"{self.url}/{req_path}?{urllib.parse.urlencode(query_params)}"
        request = urllib.request.Request(request_url, headers={"Accept": "application/json, text/plain, */*"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")

        canonical_id = query.parcel_id or ""
        geom: dict[str, Any] | None = None
        if payload.strip().startswith("{"):
            data = json.loads(payload)
            canonical_id = data.get("id") or canonical_id
            geom = data.get("geometry")
        elif payload.strip() and ";" in payload:
            # defensywne parsowanie starego formatu ULDK
            parts = payload.split(";")
            canonical_id = parts[0].strip() or canonical_id
        if not canonical_id:
            return ProviderResult(
                ok=False,
                status="PARCEL_NOT_FOUND",
                provider="ULDK",
                diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", latency_ms=int((time.time() - started) * 1000), error_code="PARCEL_NOT_FOUND"),
            )

        return ProviderResult(
            ok=True,
            status="SUCCESS_PARTIAL" if not geom else "SUCCESS",
            provider="ULDK",
            canonical_parcel_id=canonical_id,
            geometry=GeometryPayload(format="GeoJSON", srid=4326, data=geom or {}),
            diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", latency_ms=int((time.time() - started) * 1000)),
            quality_flags=["ATTRIBUTES_PARTIAL"] if not geom else [],
        )


class PowiatWFSProvider:
    def __init__(self, config: dict[str, Any]):
        self.provider = ParcelProvider(config)

    def resolve(self, query: ParcelQuery, *, route_mode: str = "AUTO") -> ProviderResult:
        started = time.time()
        normalized = normalizeParcelInput(query.parcel_number or query.parcel_id, query.precinct, query.cadastral_unit)
        candidates, meta = self.provider.resolve_candidates(normalized)
        if not candidates:
            return ProviderResult(
                ok=False,
                status="PARCEL_NOT_FOUND",
                provider="WFS",
                diagnostics=DiagnosticInfo(network_route=route_mode, provider="WFS", latency_ms=int((time.time() - started) * 1000), error_code="PARCEL_NOT_FOUND"),
            )
        parcel = candidates[0]
        return ProviderResult(
            ok=True,
            status="SUCCESS",
            provider="WFS",
            canonical_parcel_id=parcel.get("parcelNumber") or normalized.get("nrCanonical") or "",
            geometry=GeometryPayload(format="GeoJSON", srid=4326, data=parcel.get("geometry") or {}),
            attributes={"sourceName": meta.sourceName, "statusCode": meta.statusCode},
            diagnostics=DiagnosticInfo(network_route=route_mode, provider="WFS", latency_ms=int((time.time() - started) * 1000)),
        )


class KIEGProvider:
    def resolve_preview(self, query: ParcelQuery) -> dict[str, Any]:
        return {"ok": True, "preview_only": True, "query": {"parcel_id": query.parcel_id, "parcel_number": query.parcel_number}}


class MonitoringProvider:
    def __init__(self):
        self.status: dict[str, dict[str, Any]] = {}

    def record(self, provider: str, ok: bool, error_code: str = "") -> None:
        info = self.status.setdefault(provider, {"success": 0, "failure": 0, "last_error": ""})
        if ok:
            info["success"] += 1
            info["last_error"] = ""
        else:
            info["failure"] += 1
            info["last_error"] = error_code

    def snapshot(self) -> dict[str, Any]:
        return self.status
