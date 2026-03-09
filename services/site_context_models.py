from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ImportSummary:
    status: str
    objectsPerLayer: dict[str, int] = field(default_factory=dict)
    fetchedLayers: list[str] = field(default_factory=list)
    emptyLayers: list[str] = field(default_factory=list)
    unavailableLayers: list[str] = field(default_factory=list)
    partialErrors: list[str] = field(default_factory=list)


@dataclass
class SiteAnalysisResult:
    buildableArea: float | None = None
    maxBuildingEnvelope: dict[str, Any] | None = None
    preferredBuildingZone: dict[str, Any] | None = None
    buildingCandidates: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class SiteObject:
    id: str
    projectId: int
    siteContextId: str
    layerKey: str
    objectType: str
    geometry: dict[str, Any]
    bbox: list[float] | None
    centroid: dict[str, Any] | None
    sourceType: str
    sourceName: str
    sourceMetadata: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    withinPlot: bool | None = None
    withinSiteBoundary: bool | None = None
    intersectsPlot: bool | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class SiteLayer:
    id: str
    projectId: int
    siteContextId: str
    layerKey: str
    label: str
    status: str
    sourceType: str
    visible: bool
    locked: bool
    geometryType: str
    features: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    sortOrder: int = 0


@dataclass
class SiteContext:
    id: str
    projectId: int
    primaryParcelId: str
    siteBoundary: dict[str, Any]
    analysisBufferMeters: float
    layers: list[SiteLayer] = field(default_factory=list)
    objects: list[SiteObject] = field(default_factory=list)
    analysisResult: SiteAnalysisResult | None = None
    importSummary: ImportSummary | None = None
    createdAt: str = ""
    updatedAt: str = ""


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value
