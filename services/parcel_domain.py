from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParcelQuery:
    parcel_id: str = ""
    parcel_number: str = ""
    precinct: str = ""
    cadastral_unit: str = ""
    coordinates: tuple[float, float] | None = None


@dataclass
class GeometryPayload:
    format: str = "GeoJSON"
    srid: int = 4326
    data: dict[str, Any] | None = None
    source_srid: int | None = None
    source_wkt: str = ""


@dataclass
class DiagnosticInfo:
    network_route: str = "AUTO"
    attempts: int = 0
    latency_ms: int = 0
    provider: str = ""
    error_code: str = ""
    error_message: str = ""


@dataclass
class ProviderResult:
    ok: bool
    status: str
    provider: str
    canonical_parcel_id: str = ""
    geometry: GeometryPayload | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    diagnostics: DiagnosticInfo = field(default_factory=DiagnosticInfo)
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class ParcelResult:
    request_id: str
    status: str
    canonical_parcel_id: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    geometry: GeometryPayload | None = None
    source: dict[str, Any] = field(default_factory=dict)
    quality_flags: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "request_id": self.request_id,
            "status": self.status,
            "canonical_parcel_id": self.canonical_parcel_id,
            "input": self.input,
            "source": self.source,
            "quality_flags": self.quality_flags,
            "diagnostics": self.diagnostics,
        }
        if self.geometry:
            payload["geometry"] = {
                "format": self.geometry.format,
                "srid": self.geometry.srid,
                "data": self.geometry.data or {},
            }
        else:
            payload["geometry"] = None
        return payload
