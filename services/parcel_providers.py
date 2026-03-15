from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

from shapely import wkb, wkt
from shapely.geometry import mapping
from shapely.ops import transform as shp_transform

try:
    from pyproj import Transformer
except Exception:  # pragma: no cover
    Transformer = None

from services.map_service import ParcelProvider, normalizeParcelInput
from services.parcel_domain import DiagnosticInfo, GeometryPayload, ParcelQuery, ProviderResult

logger = logging.getLogger(__name__)


class ULDKProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        self.url = (self.config.get("url") or "https://uldk.gugik.gov.pl/").rstrip("/")
        self.timeout = float(self.config.get("timeout", 10))
        self.source_srid = int(self.config.get("source_srid", 2180))

    def resolve(self, query: ParcelQuery, *, route_mode: str = "AUTO") -> ProviderResult:
        started = time.time()
        if not query.parcel_id and not query.parcel_number:
            return ProviderResult(
                ok=False,
                status="INVALID_INPUT",
                provider="ULDK",
                diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", error_code="INVALID_INPUT", error_message="parcel_id lub parcel_number wymagane"),
            )

        if query.parcel_id:
            req_path = "GetParcelById"
            query_params = {
                "id": query.parcel_id,
                "result": "id,geom_wkb,geom_wkt",
                "srid": str(self.source_srid),
            }
        else:
            if not query.precinct:
                return ProviderResult(
                    ok=False,
                    status="INVALID_INPUT",
                    provider="ULDK",
                    diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", error_code="INVALID_INPUT", error_message="precinct wymagany dla wyszukiwania po numerze"),
                )
            normalized = normalizeParcelInput(query.parcel_number, query.precinct, query.cadastral_unit)
            req_path = "GetParcelByIdOrNr"
            query_params = {
                "voivodeship": "",
                "county": "",
                "commune": query.cadastral_unit,
                "precinct": normalized.get("obrebCanonical") or query.precinct,
                "parcel": normalized.get("nrCanonical") or query.parcel_number,
                "result": "id,geom_wkb,geom_wkt",
                "srid": str(self.source_srid),
            }

        logger.info(
            "parcel.search.runtime provider=%s uldk_request=%s requested_result_fields=%s requested_srid=%s fallback_used=%s wfs_called=%s",
            "ULDK",
            req_path,
            query_params.get("result", ""),
            query_params.get("srid", ""),
            False,
            False,
        )
        payload = self._request_uldk(req_path=req_path, query_params=query_params)
        canonical_id, source_wkb, source_wkt = self._parse_uldk_payload(payload, requested_parcel_id=query.parcel_id)
        geometry = self._geometry_to_geojson(source_wkb=source_wkb, source_wkt=source_wkt, source_srid=self.source_srid)

        if not canonical_id:
            return ProviderResult(
                ok=False,
                status="PARCEL_NOT_FOUND",
                provider="ULDK",
                diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", latency_ms=int((time.time() - started) * 1000), error_code="PARCEL_NOT_FOUND"),
            )

        quality_flags: list[str] = []
        if not geometry:
            quality_flags.append("ATTRIBUTES_PARTIAL")

        return ProviderResult(
            ok=True,
            status="SUCCESS_PARTIAL" if quality_flags else "SUCCESS",
            provider="ULDK",
            canonical_parcel_id=canonical_id,
            geometry=GeometryPayload(
                format="GeoJSON",
                srid=4326,
                data=geometry or {},
                source_srid=self.source_srid,
                source_wkt=source_wkt or "",
            ),
            diagnostics=DiagnosticInfo(network_route=route_mode, provider="ULDK", latency_ms=int((time.time() - started) * 1000)),
            quality_flags=quality_flags,
        )

    def _request_uldk(self, *, req_path: str, query_params: dict[str, Any]) -> str:
        request_url = f"{self.url}/{req_path}?{urllib.parse.urlencode(query_params)}"
        request = urllib.request.Request(request_url, headers={"Accept": "application/json, text/plain, */*"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    @staticmethod
    def _parse_uldk_payload(payload: str, *, requested_parcel_id: str = "") -> tuple[str, str, str]:
        text = (payload or "").strip()
        if not text:
            return "", "", ""

        if text.startswith("{"):
            data = json.loads(text)
            parcel_id = str(data.get("id") or requested_parcel_id or "").strip()
            source_wkb = str(data.get("geom_wkb") or "").strip()
            source_wkt = str(data.get("geom_wkt") or data.get("wkt") or "").strip()
            return parcel_id, source_wkb, source_wkt

        parts = [p.strip() for p in text.replace("|", ";").split(";") if p.strip()]
        parcel_id = requested_parcel_id
        source_wkb = ""
        source_wkt = ""
        for part in parts:
            upper = part.upper()
            if any(upper.startswith(prefix) for prefix in ("POINT", "LINESTRING", "POLYGON", "MULTI", "GEOMETRYCOLLECTION")):
                source_wkt = part
                continue
            if ULDKProvider._looks_like_hex_wkb(part):
                source_wkb = part
                continue
            if ("_" in part or "." in part) and not parcel_id:
                parcel_id = part

        if not parcel_id and parts:
            parcel_id = parts[0]
        return parcel_id, source_wkb, source_wkt

    @staticmethod
    def _looks_like_hex_wkb(value: str) -> bool:
        candidate = (value or "").strip()
        if len(candidate) < 10 or len(candidate) % 2 != 0:
            return False
        try:
            int(candidate[:10], 16)
            bytes.fromhex(candidate)
            return True
        except Exception:
            return False

    @staticmethod
    def _geometry_to_geojson(*, source_wkb: str, source_wkt: str, source_srid: int) -> dict[str, Any] | None:
        geom = None
        try:
            if source_wkb:
                geom = wkb.loads(bytes.fromhex(source_wkb))
            elif source_wkt:
                geom = wkt.loads(source_wkt)
        except Exception:
            geom = None

        if geom is None:
            return None

        if source_srid != 4326 and Transformer is not None:
            try:
                transformer = Transformer.from_crs(f"EPSG:{source_srid}", "EPSG:4326", always_xy=True)
                geom = shp_transform(transformer.transform, geom)
            except Exception:
                pass

        return mapping(geom)


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
