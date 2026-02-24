from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
import unicodedata

from shapely.geometry import LineString, Polygon
from shapely.geometry import mapping as shapely_mapping
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

try:
    from shapely import make_valid as shapely_make_valid
except ImportError:  # pragma: no cover - shapely<2
    shapely_make_valid = None


LAYER_KEYWORDS = (
    "dzialka",
    "działka",
    "dzialki",
    "granica",
    "granice",
    "boundary",
    "parcel",
    "plot",
    "egb",
    "egib",
    "kontur",
)


@dataclass
class BoundaryCandidate:
    uid: str
    layer: str
    geometry: Polygon
    area: float
    bbox: tuple[float, float, float, float]
    vertex_count: int
    score: float
    source: str

    def to_geojson(self):
        return shapely_mapping(self.geometry)


@dataclass
class BoundaryExtractionResult:
    candidates: list[BoundaryCandidate]
    confidence: float
    bounds: tuple[float, float, float, float] | None
    layer_summary: dict


def _strip_diacritics(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char)
    )


def _layer_score(layer_name: str) -> float:
    name = (layer_name or "").lower()
    name_plain = _strip_diacritics(name)
    if any(token in name or token in name_plain for token in LAYER_KEYWORDS):
        return 2.0
    return 0.0


def _area_ratio_score(area_ratio: float) -> float:
    if area_ratio <= 0:
        return 0.0
    if area_ratio > 0.9:
        return -0.4
    if area_ratio < 0.0001:
        return -0.4
    if 0.01 <= area_ratio <= 0.6:
        return 0.4
    if 0.0001 <= area_ratio < 0.01:
        return 0.15
    return 0.1


def _compactness_score(polygon: Polygon) -> float:
    perimeter = polygon.length
    if perimeter <= 0:
        return 0.0
    compactness = 4 * math.pi * polygon.area / (perimeter * perimeter)
    if compactness < 0.05:
        return -0.2
    if compactness > 0.7:
        return 0.25
    if compactness > 0.2:
        return 0.15
    return 0.0


def _bbox_from_points(points):
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _ensure_valid_polygon(points_or_polygon):
    if isinstance(points_or_polygon, Polygon):
        polygon = points_or_polygon
    else:
        points = list(points_or_polygon)
        if len(points) < 3:
            return None
        if points[0] != points[-1]:
            points = points + [points[0]]
        polygon = Polygon(points)
    if polygon.is_empty:
        return None
    if not polygon.is_valid:
        if shapely_make_valid:
            polygon = shapely_make_valid(polygon)
        else:
            polygon = polygon.buffer(0)
    if polygon.is_empty:
        return None
    if polygon.geom_type == "GeometryCollection":
        polygons = []
        for geom in polygon.geoms:
            if geom.is_empty:
                continue
            if geom.geom_type == "Polygon":
                polygons.append(geom)
            elif geom.geom_type == "MultiPolygon":
                polygons.extend(list(geom.geoms))
        if not polygons:
            return None
        polygon = max(polygons, key=lambda g: g.area)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda g: g.area)
    if polygon.area <= 0:
        return None
    return polygon


def _flatten_entity(entity, distance: float) -> list[tuple[float, float]]:
    try:
        return [(pt[0], pt[1]) for pt in entity.flattening(distance)]
    except Exception:
        return []


def _snap_point(pt: tuple[float, float], eps: float) -> tuple[float, float]:
    if eps <= 0:
        return pt
    return (round(pt[0] / eps) * eps, round(pt[1] / eps) * eps)


def _add_segments_from_points(
    segments: list[tuple[tuple[float, float], tuple[float, float], str]],
    points: list[tuple[float, float]],
    closed: bool,
    layer: str,
):
    if len(points) < 2:
        return
    for idx in range(len(points) - 1):
        segments.append((points[idx], points[idx + 1], layer))
    if closed and points[0] != points[-1]:
        segments.append((points[-1], points[0], layer))


def _collect_segments(doc, flatten_distance: float):
    segments = []
    points_all = []
    layer_summary = {}
    closed_polygons = []
    queue = list(doc.modelspace())
    while queue:
        entity = queue.pop(0)
        layer = entity.dxf.layer
        summary = layer_summary.setdefault(layer, {"has_hatch": False, "entity_types": set()})
        summary["entity_types"].add(entity.dxftype())
        if entity.dxftype() == "INSERT":
            try:
                queue.extend(list(entity.virtual_entities()))
            except Exception:
                continue
            continue
        if entity.dxftype() == "HATCH":
            summary["has_hatch"] = True
            for path in getattr(entity, "paths", []):
                try:
                    vertices = [(v[0], v[1]) for v in path.vertices]
                except Exception:
                    vertices = []
                if len(vertices) >= 3:
                    _add_segments_from_points(segments, vertices, True, layer)
                    points_all.extend(vertices)
            continue
        if entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
            pts = _flatten_entity(entity, distance=flatten_distance)
            if not pts:
                if entity.dxftype() == "LWPOLYLINE":
                    pts = [(pt[0], pt[1]) for pt in entity.get_points("xy")]
                    closed = bool(entity.closed)
                else:
                    pts = [(pt[0], pt[1]) for pt in entity.points()]
                    closed = bool(getattr(entity, "is_closed", False) or getattr(entity, "closed", False))
            else:
                closed = bool(getattr(entity, "is_closed", False) or getattr(entity, "closed", False))
            if closed and len(pts) >= 3:
                polygon = _ensure_valid_polygon(pts)
                if polygon:
                    closed_polygons.append((polygon, layer))
            _add_segments_from_points(segments, pts, closed, layer)
            points_all.extend(pts)
            continue
        if entity.dxftype() == "LINE":
            start = (entity.dxf.start.x, entity.dxf.start.y)
            end = (entity.dxf.end.x, entity.dxf.end.y)
            segments.append((start, end, layer))
            points_all.extend([start, end])
            continue
        if entity.dxftype() in ("CIRCLE", "ARC", "SPLINE", "ELLIPSE"):
            pts = _flatten_entity(entity, distance=flatten_distance)
            closed = entity.dxftype() in ("CIRCLE", "ELLIPSE")
            _add_segments_from_points(segments, pts, closed, layer)
            points_all.extend(pts)

    bounds = None
    if points_all:
        bounds = _bbox_from_points(points_all)

    return segments, bounds, layer_summary, closed_polygons


def _polygonize_segments(
    segments: list[tuple[tuple[float, float], tuple[float, float], str]],
    eps_snap: float,
):
    if not segments:
        return []
    snapped_segments = []
    for start, end, layer in segments:
        start_snap = _snap_point(start, eps_snap)
        end_snap = _snap_point(end, eps_snap)
        if start_snap == end_snap:
            continue
        snapped_segments.append((start_snap, end_snap, layer))

    if not snapped_segments:
        return []

    lines = [LineString([start, end]) for start, end, _ in snapped_segments]
    unioned = unary_union(lines)
    polygons = list(polygonize(unioned))
    if not polygons:
        return []

    tree = STRtree(lines)
    line_meta = {id(line): snapped_segments[idx][2] for idx, line in enumerate(lines)}
    line_length = {id(line): line.length for line in lines}

    results = []
    for polygon in polygons:
        boundary = polygon.boundary
        layer_lengths: dict[str, float] = {}
        for item in tree.query(boundary):
            line = item if hasattr(item, "intersects") else lines[int(item)]
            if not (line.intersects(boundary) or line.distance(boundary) <= eps_snap * 1.5):
                continue
            layer = line_meta.get(id(line), "unknown")
            layer_lengths[layer] = layer_lengths.get(layer, 0.0) + line_length.get(id(line), 0.0)
        if layer_lengths:
            best_layer = max(layer_lengths.items(), key=lambda item: item[1])[0]
        else:
            best_layer = "unknown"
        results.append((polygon, best_layer))
    return results


def _filter_candidates(candidates, map_area):
    min_area = max(1.0, map_area * 0.0005)
    filtered = []
    for candidate in candidates:
        if candidate.area < min_area:
            continue
        if candidate.vertex_count > 10000:
            continue
        filtered.append(candidate)
    return filtered or candidates


def extract_boundaries(doc, preferred_layer: str | None = None) -> BoundaryExtractionResult:
    flatten_distance = 0.02
    segments, bounds, layer_summary, closed_polygons = _collect_segments(
        doc, flatten_distance=flatten_distance
    )
    if bounds:
        diag = math.hypot(bounds[2] - bounds[0], bounds[3] - bounds[1])
    else:
        diag = 0.0
    eps_snap = max(0.01, diag * 1e-6)

    candidates = []
    for polygon, layer in closed_polygons:
        polygon = _ensure_valid_polygon(polygon)
        if not polygon:
            continue
        bbox = polygon.bounds
        candidates.append(
            BoundaryCandidate(
                uid=str(uuid.uuid4()),
                layer=layer,
                geometry=polygon,
                area=polygon.area,
                bbox=bbox,
                vertex_count=len(polygon.exterior.coords),
                score=0.0,
                source="closed-polyline",
            )
        )

    def is_duplicate(polygon):
        for existing in candidates:
            try:
                if polygon.equals(existing.geometry):
                    return True
            except Exception:
                continue
        return False

    for polygon, layer in _polygonize_segments(segments, eps_snap):
        polygon = _ensure_valid_polygon(polygon)
        if not polygon:
            continue
        if is_duplicate(polygon):
            continue
        bbox = polygon.bounds
        candidates.append(
            BoundaryCandidate(
                uid=str(uuid.uuid4()),
                layer=layer,
                geometry=polygon,
                area=polygon.area,
                bbox=bbox,
                vertex_count=len(polygon.exterior.coords),
                score=0.0,
                source="line-loop",
            )
        )

    map_area = 0.0
    if bounds:
        map_area = abs((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
    candidates = _filter_candidates(candidates, map_area)

    if not candidates:
        return BoundaryExtractionResult([], 0.0, bounds, layer_summary)

    max_area = max(candidate.area for candidate in candidates) if candidates else 1.0
    ranked = []
    source_weights = {"closed-polyline": 1.0, "line-loop": 0.8}
    for candidate in candidates:
        layer_score = _layer_score(candidate.layer)
        hatch_penalty = -0.3 if layer_summary.get(candidate.layer, {}).get("has_hatch") else 0.1
        area_score = candidate.area / max_area if max_area else 0.0
        area_ratio = candidate.area / map_area if map_area else 0.0
        area_ratio_score = _area_ratio_score(area_ratio)
        compactness_score = _compactness_score(candidate.geometry)
        preferred_bonus = 1.0 if preferred_layer and candidate.layer == preferred_layer else 0.0
        source_score = source_weights.get(candidate.source, 0.0)
        score = (
            layer_score
            + source_score
            + area_score
            + area_ratio_score
            + compactness_score
            + hatch_penalty
            + preferred_bonus
        )
        ranked.append(candidate.__class__(
            uid=candidate.uid,
            layer=candidate.layer,
            geometry=candidate.geometry,
            area=candidate.area,
            bbox=candidate.bbox,
            vertex_count=candidate.vertex_count,
            score=score,
            source=candidate.source,
        ))

    ranked.sort(key=lambda c: c.score, reverse=True)

    confidence = 0.5
    if len(ranked) == 1:
        confidence = 1.0 if _layer_score(ranked[0].layer) > 0 else 0.85
    else:
        diff = ranked[0].score - ranked[1].score
        confidence = min(0.95, 0.5 + diff / 2)
        if _layer_score(ranked[0].layer) > 0:
            confidence = min(1.0, confidence + 0.1)
    if preferred_layer and ranked and ranked[0].layer == preferred_layer:
        confidence = max(confidence, 0.85)

    return BoundaryExtractionResult(ranked, confidence, bounds, layer_summary)
