from __future__ import annotations

from dataclasses import dataclass

from shapely.affinity import scale as shapely_scale
from shapely.affinity import translate as shapely_translate
from shapely.geometry.base import BaseGeometry


@dataclass
class NormalizedCandidate:
    uid: str
    layer: str
    geometry: BaseGeometry
    area: float
    bbox: tuple[float, float, float, float]
    vertex_count: int
    score: float

    def to_geojson(self):
        from shapely.geometry import mapping as shapely_mapping

        return shapely_mapping(self.geometry)


def normalize_candidates(candidates, unit_scale: float):
    scaled = []
    for candidate in candidates:
        geom = shapely_scale(candidate.geometry, xfact=unit_scale, yfact=unit_scale, origin=(0, 0))
        scaled.append(
            NormalizedCandidate(
                uid=candidate.uid,
                layer=candidate.layer,
                geometry=geom,
                area=geom.area,
                bbox=geom.bounds,
                vertex_count=candidate.vertex_count,
                score=candidate.score,
            )
        )

    if not scaled:
        return [], None, None

    minx = min(candidate.bbox[0] for candidate in scaled)
    miny = min(candidate.bbox[1] for candidate in scaled)
    maxx = max(candidate.bbox[2] for candidate in scaled)
    maxy = max(candidate.bbox[3] for candidate in scaled)

    translated = []
    for candidate in scaled:
        geom = shapely_translate(candidate.geometry, xoff=-minx, yoff=-miny)
        translated.append(
            NormalizedCandidate(
                uid=candidate.uid,
                layer=candidate.layer,
                geometry=geom,
                area=geom.area,
                bbox=geom.bounds,
                vertex_count=candidate.vertex_count,
                score=candidate.score,
            )
        )

    transform = {"scale": unit_scale, "translate": {"x": -minx, "y": -miny}}
    bounds = (0.0, 0.0, maxx - minx, maxy - miny)
    return translated, transform, bounds
