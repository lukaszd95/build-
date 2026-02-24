from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import ezdxf
from ezdxf import colors
from shapely.affinity import scale as shapely_scale
from shapely.affinity import translate as shapely_translate

from services.boundary_extractor import extract_boundaries
from services.dxf_parser import detect_units

logger = logging.getLogger("plot-pipeline")


@dataclass
class ParsedCadData:
    doc: ezdxf.EzdxfDocument
    raw_entities: list[dict[str, Any]]
    layer_summary: dict[str, dict[str, Any]]
    bounds: tuple[float, float, float, float] | None


def parse_file(file_path: str) -> ParsedCadData:
    doc = ezdxf.readfile(file_path)
    layer_colors = {layer.dxf.name: layer.color for layer in doc.layers}

    raw_entities: list[dict[str, Any]] = []
    layer_summary: dict[str, dict[str, Any]] = {}
    points = []

    for entity in doc.modelspace():
        etype = entity.dxftype()
        layer = getattr(entity.dxf, "layer", "0") or "0"
        summary = layer_summary.setdefault(
            layer,
            {
                "entityCount": 0,
                "entityTypes": defaultdict(int),
                "lineTypes": set(),
                "colors": set(),
                "blockNames": set(),
                "attributes": set(),
            },
        )
        summary["entityCount"] += 1
        summary["entityTypes"][etype] += 1

        line_type = getattr(entity.dxf, "linetype", None)
        if line_type:
            summary["lineTypes"].add(line_type)

        color = _entity_color_hex(entity, layer_colors.get(layer, 0))
        if color:
            summary["colors"].add(color)

        if etype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            pts = [(start.x, start.y), (end.x, end.y)]
            points.extend(pts)
            raw_entities.append(
                {
                    "t": "line",
                    "layer": layer,
                    "points": pts,
                    "color": color,
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            continue

        if etype == "LWPOLYLINE":
            pts = [(pt[0], pt[1]) for pt in entity.get_points("xy")]
            if len(pts) >= 2:
                points.extend(pts)
                raw_entities.append(
                    {
                        "t": "polyline",
                        "layer": layer,
                        "points": pts,
                        "closed": bool(entity.closed),
                        "color": color,
                        "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                    }
                )
            continue

        if etype == "POLYLINE":
            pts = [(pt.x, pt.y) for pt in entity.points()]
            if len(pts) >= 2:
                points.extend(pts)
                raw_entities.append(
                    {
                        "t": "polyline",
                        "layer": layer,
                        "points": pts,
                        "closed": bool(getattr(entity, "is_closed", False)),
                        "color": color,
                        "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                    }
                )
            continue

        if etype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            pts = _approximate_arc((center.x, center.y), radius, entity.dxf.start_angle, entity.dxf.end_angle)
            points.extend(pts)
            raw_entities.append(
                {
                    "t": "arc",
                    "layer": layer,
                    "points": pts,
                    "color": color,
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            continue

        if etype == "SPLINE":
            pts = _flatten_entity(entity, distance=0.5)
            if len(pts) >= 2:
                points.extend(pts)
                raw_entities.append(
                    {
                        "t": "arc",
                        "layer": layer,
                        "points": pts,
                        "color": color,
                        "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                    }
                )
            continue

        if etype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            points.append((center.x + radius, center.y))
            points.append((center.x - radius, center.y))
            points.append((center.x, center.y + radius))
            points.append((center.x, center.y - radius))
            raw_entities.append(
                {
                    "t": "circle",
                    "layer": layer,
                    "center": (center.x, center.y),
                    "radius": radius,
                    "color": color,
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            continue

        if etype in ("TEXT", "MTEXT"):
            insert = entity.dxf.insert
            text = entity.plain_text() if etype == "MTEXT" else entity.dxf.text
            height = _safe_float(getattr(entity.dxf, "height", None)) or 0
            rotation = _safe_float(getattr(entity.dxf, "rotation", None)) or 0
            points.append((insert.x, insert.y))
            raw_entities.append(
                {
                    "t": "text",
                    "layer": layer,
                    "point": (insert.x, insert.y),
                    "text": text,
                    "height": height,
                    "rotation": rotation,
                    "color": color,
                }
            )
            continue

        if etype == "INSERT":
            block_name = getattr(entity.dxf, "name", None)
            if block_name:
                summary["blockNames"].add(block_name)
            for attrib in entity.attribs:
                tag = getattr(attrib.dxf, "tag", None)
                if tag:
                    summary["attributes"].add(tag)
            continue

    bounds = _bounds_from_points(points)
    logger.debug("Parsed CAD entities: layers=%s entities=%s", len(layer_summary), len(raw_entities))

    return ParsedCadData(doc=doc, raw_entities=raw_entities, layer_summary=layer_summary, bounds=bounds)


def detect_units_from_doc(doc, bounds):
    unit_name, scale, source = detect_units(doc, bounds)
    return {
        "unitName": unit_name,
        "unitScaleToMeters": scale,
        "unitsSource": source,
        "heuristic": source == "heuristic",
    }


def normalize_entities(raw_entities: list[dict[str, Any]], scale: float, bounds):
    offset_x = bounds[0] if bounds else 0.0
    offset_y = bounds[1] if bounds else 0.0

    layers = defaultdict(list)
    layer_counts = defaultdict(int)

    def transform_point(pt):
        return {
            "x": (pt[0] - offset_x) * scale,
            "y": (pt[1] - offset_y) * scale,
        }

    for entity in raw_entities:
        layer_name = entity.get("layer") or "0"
        if entity["t"] in ("line", "polyline", "arc"):
            pts = [transform_point(pt) for pt in entity["points"]]
            bounds = _bounds_from_points([(p["x"], p["y"]) for p in pts])
            layers[layer_name].append(
                {
                    "t": entity["t"],
                    "pts": pts,
                    "closed": entity.get("closed", False),
                    "color": entity.get("color"),
                    "lw": entity.get("lw") or 1,
                    "bbox": _bounds_dict(bounds),
                }
            )
            layer_counts[layer_name] += 1
            continue

        if entity["t"] == "circle":
            center = transform_point(entity["center"])
            radius = entity["radius"] * scale
            bounds = {
                "minX": center["x"] - radius,
                "minY": center["y"] - radius,
                "maxX": center["x"] + radius,
                "maxY": center["y"] + radius,
            }
            layers[layer_name].append(
                {
                    "t": "circle",
                    "x": center["x"],
                    "y": center["y"],
                    "r": radius,
                    "color": entity.get("color"),
                    "lw": entity.get("lw") or 1,
                    "bbox": bounds,
                }
            )
            layer_counts[layer_name] += 1
            continue

        if entity["t"] == "text":
            point = transform_point(entity["point"])
            layers[layer_name].append(
                {
                    "t": "text",
                    "x": point["x"],
                    "y": point["y"],
                    "text": entity.get("text", ""),
                    "h": (entity.get("height") or 0) * scale,
                    "rot": entity.get("rotation", 0),
                    "color": entity.get("color"),
                    "bbox": {
                        "minX": point["x"],
                        "minY": point["y"],
                        "maxX": point["x"],
                        "maxY": point["y"],
                    },
                }
            )
            layer_counts[layer_name] += 1
            continue

    layers_payload = []
    for layer_name, entities in sorted(layers.items()):
        layers_payload.append(
            {
                "name": layer_name,
                "visible": True,
                "opacity": 0.7,
                "entities": entities,
                "entityCount": layer_counts[layer_name],
            }
        )

    scaled_bounds = None
    if bounds:
        scaled_bounds = {
            "minX": (bounds[0] - offset_x) * scale,
            "minY": (bounds[1] - offset_y) * scale,
            "maxX": (bounds[2] - offset_x) * scale,
            "maxY": (bounds[3] - offset_y) * scale,
        }

    return {
        "layers": layers_payload,
        "entityCount": sum(layer_counts.values()),
        "bbox": scaled_bounds,
        "transform": {"scale": scale, "translate": {"x": -offset_x, "y": -offset_y}},
    }


def extract_parcel_boundaries(doc, preferred_layer: str | None = None):
    extraction = extract_boundaries(doc, preferred_layer=preferred_layer)
    return extraction


def select_main_boundary(candidates):
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.area)


def normalize_boundary_candidates(candidates, scale: float, bounds):
    if not candidates:
        return []
    offset_x = bounds[0] if bounds else 0.0
    offset_y = bounds[1] if bounds else 0.0

    normalized = []
    for candidate in candidates:
        geom = shapely_scale(candidate.geometry, xfact=scale, yfact=scale, origin=(0, 0))
        geom = shapely_translate(geom, xoff=-offset_x * scale, yoff=-offset_y * scale)
        normalized.append(
            {
                "uid": candidate.uid,
                "layer": candidate.layer,
                "geometry": geom,
                "area": geom.area,
                "bbox": geom.bounds,
                "vertexCount": candidate.vertex_count,
                "score": candidate.score,
                "source": candidate.source,
            }
        )
    return normalized


def summarize_layers(layer_summary: dict[str, dict[str, Any]]):
    summary = []
    for layer_name, data in sorted(layer_summary.items()):
        summary.append(
            {
                "name": layer_name,
                "entityCount": data.get("entityCount", 0),
                "entityTypes": dict(data.get("entityTypes", {})),
                "lineTypes": sorted(data.get("lineTypes", [])),
                "colors": sorted(data.get("colors", [])),
                "blockNames": sorted(data.get("blockNames", [])),
                "attributes": sorted(data.get("attributes", [])),
            }
        )
    return summary


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounds_from_points(points):
    if not points:
        return None
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for x, y in points:
        if x is None or y is None:
            continue
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)
    if not math.isfinite(min_x):
        return None
    return min_x, min_y, max_x, max_y


def _bounds_dict(bounds):
    if not bounds:
        return None
    return {
        "minX": bounds[0],
        "minY": bounds[1],
        "maxX": bounds[2],
        "maxY": bounds[3],
    }


def _hex_from_rgb(rgb):
    if not rgb:
        return None
    r, g, b = rgb
    if r >= 250 and g >= 250 and b >= 250:
        return "#000000"
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def _entity_color_hex(entity, layer_color):
    true_color = getattr(entity.dxf, "true_color", None)
    if true_color:
        return _hex_from_rgb(colors.int2rgb(true_color))

    aci = getattr(entity.dxf, "color", None)
    if aci and aci not in (0, 256):
        return _hex_from_rgb(colors.aci2rgb(aci))

    if layer_color and layer_color not in (0, 256):
        return _hex_from_rgb(colors.aci2rgb(layer_color))
    return None


def _approximate_arc(center, radius, start_angle, end_angle, segments=32):
    start_rad = math.radians(float(start_angle))
    end_rad = math.radians(float(end_angle))
    while end_rad < start_rad:
        end_rad += math.tau

    sweep = end_rad - start_rad
    segments = max(8, int(segments * (sweep / math.tau)))
    points = []
    for i in range(segments + 1):
        t = start_rad + sweep * (i / segments)
        points.append((center[0] + radius * math.cos(t), center[1] + radius * math.sin(t)))
    return points


def _flatten_entity(entity, distance: float):
    try:
        return [(pt[0], pt[1]) for pt in entity.flattening(distance)]
    except Exception:
        return []
