import json
import math
import os
import shutil
import subprocess
import time
from collections import defaultdict

import ezdxf
from ezdxf import colors


INSUNITS_SCALE = {
    1: ("inch", 0.0254),
    2: ("foot", 0.3048),
    3: ("mile", 1609.344),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    7: ("km", 1000.0),
    8: ("microinch", 0.0000254),
    9: ("mil", 0.0000254),
    10: ("yard", 0.9144),
    11: ("angstrom", 1e-10),
    12: ("nanometer", 1e-9),
    13: ("micron", 1e-6),
    14: ("dm", 0.1),
    15: ("dam", 10.0),
    16: ("hm", 100.0),
    17: ("gm", 1_000_000_000.0),
    18: ("au", 149_597_870_700.0),
    19: ("ly", 9_460_730_472_580_800.0),
    20: ("pc", 30_856_775_814_913_700.0),
}


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounds_from_points(points):
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for x, y in points:
        if x is None or y is None:
            continue
        min_x = min(min_x, x)
        max_x = max(max_x, x)
        min_y = min(min_y, y)
        max_y = max(max_y, y)
    if not math.isfinite(min_x):
        return None
    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


def _merge_bounds(bounds_list):
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for bounds in bounds_list:
        if not bounds:
            continue
        min_x = min(min_x, bounds["minX"])
        min_y = min(min_y, bounds["minY"])
        max_x = max(max_x, bounds["maxX"])
        max_y = max(max_y, bounds["maxY"])
    if not math.isfinite(min_x):
        return None
    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


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


def _polygon_area(points):
    if not points or len(points) < 3:
        return 0.0
    area = 0.0
    for i, pt in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        area += pt["x"] * nxt["y"] - nxt["x"] * pt["y"]
    return abs(area) * 0.5


def _polygon_perimeter(points):
    if not points or len(points) < 2:
        return 0.0
    per = 0.0
    for i, pt in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        per += math.hypot(nxt["x"] - pt["x"], nxt["y"] - pt["y"])
    return per


def _polygon_centroid(points):
    if not points:
        return {"x": 0.0, "y": 0.0}
    cx = 0.0
    cy = 0.0
    for pt in points:
        cx += pt["x"]
        cy += pt["y"]
    count = len(points)
    return {"x": cx / count, "y": cy / count}


def _distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _layer_name_score(layer_name):
    name = (layer_name or "").lower()
    if any(token in name for token in ("dzialk", "działk", "parcel", "plot", "granica", "boundary")):
        return 2
    if any(token in name for token in ("droga", "road", "street")):
        return 0
    if any(token in name for token in ("budynek", "building", "sasiad", "sąsiad")):
        return 0
    return 0


def _build_ai_hints(layers_payload, bbox):
    map_area = 0.0
    if bbox:
        map_area = max(0.0, (bbox["maxX"] - bbox["minX"]) * (bbox["maxY"] - bbox["minY"]))
    min_plot_area = max(25.0, map_area * 0.002)

    text_points = []
    for layer in layers_payload:
        for entity in layer.get("entities", []):
            if entity.get("t") == "text":
                text_points.append(
                    {
                        "x": entity.get("x", 0.0),
                        "y": entity.get("y", 0.0),
                        "text": entity.get("text", ""),
                    }
                )

    layer_hints = []
    polygon_features = []

    for layer in layers_payload:
        closed_polys = []
        for entity in layer.get("entities", []):
            if entity.get("t") == "polyline" and entity.get("closed"):
                closed_polys.append(entity)

        total_area = 0.0
        total_perimeter = 0.0

        for poly in closed_polys:
            pts = poly.get("pts", [])
            area = _polygon_area(pts)
            per = _polygon_perimeter(pts)
            centroid = _polygon_centroid(pts)
            if text_points:
                nearest_text = min(text_points, key=lambda t: _distance(centroid, t))
                nearest_dist = _distance(centroid, nearest_text)
                nearest_label = nearest_text.get("text")
            else:
                nearest_dist = None
                nearest_label = None

            polygon_features.append(
                {
                    "layer": layer.get("name"),
                    "area": area,
                    "perimeter": per,
                    "vertices": len(pts),
                    "centroid": centroid,
                    "nearestTextDistance": nearest_dist,
                    "nearestTextSample": nearest_label,
                }
            )
            total_area += area
            total_perimeter += per

        name_score = _layer_name_score(layer.get("name"))
        closed_count = len(closed_polys)
        avg_area = total_area / closed_count if closed_count else 0.0
        score = name_score
        reasons = []

        if name_score >= 2:
            score += 2
            reasons.append("nazwa warstwy sugeruje działki")
        if closed_count:
            score += 1
            reasons.append(f"{closed_count} zamkniętych polilinii")
        if avg_area >= min_plot_area:
            score += 1
            reasons.append("obszary powyżej progu")

        layer_hints.append(
            {
                "layer": layer.get("name"),
                "score": score,
                "closedPolylines": closed_count,
                "avgArea": avg_area,
                "reasons": reasons,
            }
        )

    layer_hints.sort(key=lambda item: item["score"], reverse=True)

    return {
        "heuristicVersion": "v1",
        "minPlotArea": min_plot_area,
        "layerHints": layer_hints[:8],
        "polygonFeatures": polygon_features[:200],
    }


def _select_parcel_layers(layers_payload, ai_hints):
    hints_by_layer = {
        hint["layer"]: hint
        for hint in ai_hints.get("layerHints", [])
        if hint.get("layer")
    }

    candidates = []
    for layer in layers_payload:
        closed_polys = [
            entity
            for entity in layer.get("entities", [])
            if entity.get("t") == "polyline" and entity.get("closed")
        ]
        if not closed_polys:
            continue
        hint = hints_by_layer.get(layer.get("name"), {})
        candidates.append(
            {
                "name": layer.get("name"),
                "score": hint.get("score", 0),
                "closedCount": len(closed_polys),
                "entities": closed_polys,
                "reasons": hint.get("reasons", []),
            }
        )

    if not candidates:
        return []

    best_score = max(item["score"] for item in candidates)
    if best_score > 0:
        selected = [item for item in candidates if item["score"] == best_score]
    else:
        best_closed = max(item["closedCount"] for item in candidates)
        selected = [item for item in candidates if item["closedCount"] == best_closed]

    return selected


def detect_units_and_scale(doc, raw_bounds):
    insunits = doc.header.get("$INSUNITS", 0)
    if insunits in INSUNITS_SCALE:
        unit_name, scale = INSUNITS_SCALE[insunits]
        return {
            "unitsDetected": unit_name,
            "unitScaleToMeters": scale,
            "heuristic": False,
        }

    if not raw_bounds:
        return {
            "unitsDetected": "unitless",
            "unitScaleToMeters": 1.0,
            "heuristic": True,
        }

    width = raw_bounds["maxX"] - raw_bounds["minX"]
    height = raw_bounds["maxY"] - raw_bounds["minY"]
    size = max(abs(width), abs(height))

    if size > 10_000:
        unit_name = "mm"
        scale = 0.001
    elif size > 1_000:
        unit_name = "cm"
        scale = 0.01
    elif size >= 1:
        unit_name = "m"
        scale = 1.0
    else:
        unit_name = "m"
        scale = 1.0

    return {
        "unitsDetected": unit_name,
        "unitScaleToMeters": scale,
        "heuristic": True,
    }


def _approximate_arc(center, radius, start_angle, end_angle, segments=32):
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    while end_rad < start_rad:
        end_rad += math.tau

    sweep = end_rad - start_rad
    segments = max(8, int(segments * (sweep / math.tau)))
    points = []
    for i in range(segments + 1):
        t = start_rad + sweep * (i / segments)
        points.append((center[0] + radius * math.cos(t), center[1] + radius * math.sin(t)))
    return points


def parse_dxf_to_json(path):
    start_ts = time.time()
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    layer_colors = {}
    for layer in doc.layers:
        layer_colors[layer.dxf.name] = layer.color

    raw_entities = []
    raw_bounds_list = []
    entity_count = 0

    for entity in msp:
        etype = entity.dxftype()
        layer = getattr(entity.dxf, "layer", "0") or "0"
        layer_color = layer_colors.get(layer, 0)

        if etype == "LINE":
            start = entity.dxf.start
            end = entity.dxf.end
            points = [(start.x, start.y), (end.x, end.y)]
            raw_bounds_list.append(_bounds_from_points(points))
            raw_entities.append(
                {
                    "t": "line",
                    "layer": layer,
                    "points": points,
                    "color": _entity_color_hex(entity, layer_color),
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            entity_count += 1
            continue

        if etype == "LWPOLYLINE":
            points = [(p[0], p[1]) for p in entity.get_points("xy")]
            if len(points) < 2:
                continue
            raw_bounds_list.append(_bounds_from_points(points))
            raw_entities.append(
                {
                    "t": "polyline",
                    "layer": layer,
                    "points": points,
                    "closed": bool(entity.closed),
                    "color": _entity_color_hex(entity, layer_color),
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            entity_count += 1
            continue

        if etype == "POLYLINE":
            points = [(p.x, p.y) for p in entity.points()]
            if len(points) < 2:
                continue
            raw_bounds_list.append(_bounds_from_points(points))
            raw_entities.append(
                {
                    "t": "polyline",
                    "layer": layer,
                    "points": points,
                    "closed": bool(entity.is_closed),
                    "color": _entity_color_hex(entity, layer_color),
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            entity_count += 1
            continue

        if etype == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            raw_bounds_list.append(
                {
                    "minX": center.x - radius,
                    "minY": center.y - radius,
                    "maxX": center.x + radius,
                    "maxY": center.y + radius,
                }
            )
            raw_entities.append(
                {
                    "t": "circle",
                    "layer": layer,
                    "center": (center.x, center.y),
                    "radius": radius,
                    "color": _entity_color_hex(entity, layer_color),
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            entity_count += 1
            continue

        if etype == "ARC":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            start_angle = float(entity.dxf.start_angle)
            end_angle = float(entity.dxf.end_angle)
            points = _approximate_arc((center.x, center.y), radius, start_angle, end_angle)
            raw_bounds_list.append(_bounds_from_points(points))
            raw_entities.append(
                {
                    "t": "arc",
                    "layer": layer,
                    "points": points,
                    "color": _entity_color_hex(entity, layer_color),
                    "lw": _safe_float(getattr(entity.dxf, "lineweight", None)),
                }
            )
            entity_count += 1
            continue

        if etype in ("TEXT", "MTEXT"):
            insert = entity.dxf.insert
            text = entity.plain_text() if etype == "MTEXT" else entity.dxf.text
            height = _safe_float(getattr(entity.dxf, "height", None)) or 0
            rotation = _safe_float(getattr(entity.dxf, "rotation", None)) or 0
            raw_bounds_list.append(
                {
                    "minX": insert.x,
                    "minY": insert.y,
                    "maxX": insert.x,
                    "maxY": insert.y,
                }
            )
            raw_entities.append(
                {
                    "t": "text",
                    "layer": layer,
                    "point": (insert.x, insert.y),
                    "text": text,
                    "height": height,
                    "rotation": rotation,
                    "color": _entity_color_hex(entity, layer_color),
                }
            )
            entity_count += 1
            continue

        if etype == "INSERT":
            # MVP: brak rozwijania bloków
            continue

    raw_bounds = _merge_bounds(raw_bounds_list)
    units_info = detect_units_and_scale(doc, raw_bounds)

    scale = units_info["unitScaleToMeters"]
    if not raw_bounds:
        raw_bounds = {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}

    offset_x = raw_bounds["minX"]
    offset_y = raw_bounds["minY"]

    layers = defaultdict(list)
    layer_entity_counts = defaultdict(int)

    def transform_point(pt):
        return {
            "x": (pt[0] - offset_x) * scale,
            "y": (pt[1] - offset_y) * scale,
        }

    for entity in raw_entities:
        layer_name = entity["layer"]
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
                    "bbox": bounds,
                }
            )
            layer_entity_counts[layer_name] += 1
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
            layer_entity_counts[layer_name] += 1
            continue

        if entity["t"] == "text":
            point = transform_point(entity["point"])
            layers[layer_name].append(
                {
                    "t": "text",
                    "x": point["x"],
                    "y": point["y"],
                    "text": entity.get("text", ""),
                    "h": entity.get("height", 0) * scale,
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
            layer_entity_counts[layer_name] += 1
            continue

    layers_payload = []
    for layer_name, entities in sorted(layers.items()):
        layers_payload.append(
            {
                "name": layer_name,
                "visible": True,
                "opacity": 0.7,
                "entities": entities,
                "entityCount": layer_entity_counts[layer_name],
            }
        )

    scaled_bounds = {
        "minX": (raw_bounds["minX"] - offset_x) * scale,
        "minY": (raw_bounds["minY"] - offset_y) * scale,
        "maxX": (raw_bounds["maxX"] - offset_x) * scale,
        "maxY": (raw_bounds["maxY"] - offset_y) * scale,
    }

    elapsed_ms = int((time.time() - start_ts) * 1000)
    units_label = units_info["unitsDetected"]
    if units_info["heuristic"]:
        units_label = f"{units_label} (heurystyka)"

    ai_hints = _build_ai_hints(layers_payload, scaled_bounds)
    parcel_candidates = _select_parcel_layers(layers_payload, ai_hints)

    parcel_entities = []
    parcel_layers = []
    parcel_reasons = []
    for candidate in parcel_candidates:
        parcel_layers.append(candidate["name"])
        parcel_entities.extend(candidate["entities"])
        if candidate.get("reasons"):
            parcel_reasons.extend(candidate["reasons"])

    if parcel_entities:
        layers_payload = [
            {
                "name": "Granice działek",
                "visible": True,
                "opacity": 0.9,
                "entities": parcel_entities,
                "entityCount": len(parcel_entities),
                "sourceLayers": parcel_layers,
            }
        ]
    else:
        layers_payload = []

    return {
        "unitsDetected": units_label,
        "unitScaleToMeters": scale,
        "bbox": scaled_bounds,
        "layers": layers_payload,
        "layerCount": len(layers_payload),
        "entityCount": entity_count,
        "parcelBoundaryCount": len(parcel_entities),
        "parcelSourceLayers": parcel_layers,
        "parcelDetection": {
            "status": "ok" if parcel_entities else "empty",
            "selectedLayers": parcel_layers,
            "reasons": list(dict.fromkeys(parcel_reasons))[:6],
        },
        "parseMs": elapsed_ms,
        "aiHints": ai_hints,
    }


def convert_dwg_to_dxf(dwg_path, output_dir, oda_path=None, dwg2dxf_path=None):
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(dwg_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}.dxf")

    if oda_path and os.path.exists(oda_path):
        input_dir = os.path.dirname(dwg_path)
        command = [
            oda_path,
            input_dir,
            output_dir,
            "ACAD2018",
            "DXF",
            "0",
            "1",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"ODAFileConverter error: {result.stderr or result.stdout}"
            )
        if not os.path.exists(output_path):
            raise RuntimeError("ODAFileConverter nie wygenerował pliku DXF.")
        return output_path

    dwg2dxf = dwg2dxf_path or shutil.which("dwg2dxf")
    if dwg2dxf:
        command = [dwg2dxf, dwg_path, "-o", output_path]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"dwg2dxf error: {result.stderr or result.stdout}")
        if not os.path.exists(output_path):
            raise RuntimeError("dwg2dxf nie wygenerował pliku DXF.")
        return output_path

    raise RuntimeError(
        "Brak narzędzia do konwersji DWG → DXF. "
        "Zainstaluj ODAFileConverter lub dwg2dxf (LibreDWG) albo użyj DXF."
    )


def save_debug_snapshot(payload, debug_path):
    if not debug_path:
        return
    os.makedirs(os.path.dirname(debug_path), exist_ok=True)
    with open(debug_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
