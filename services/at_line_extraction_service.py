import json
import math
from dataclasses import dataclass

import fitz


@dataclass
class ExtractionConfig:
    min_length: float = 6.0
    vector_min_length: float = 0.5
    dedupe_eps: float = 1.5
    raster_scale: float = 2.0
    raster_hough_threshold: int = 40
    raster_min_line_length: int = 18
    raster_max_line_gap: int = 4


class ATLineExtractionService:
    def __init__(self, config=None):
        cfg = config or {}
        self.config = ExtractionConfig(
            min_length=float(cfg.get("AT_LINES_MIN_LENGTH", 6.0)),
            vector_min_length=float(cfg.get("AT_LINES_VECTOR_MIN_LENGTH", 0.5)),
            dedupe_eps=float(cfg.get("AT_LINES_DEDUPE_EPS", 1.5)),
            raster_scale=float(cfg.get("AT_LINES_RASTER_SCALE", 2.0)),
            raster_hough_threshold=int(cfg.get("AT_LINES_HOUGH_THRESHOLD", 40)),
            raster_min_line_length=int(cfg.get("AT_LINES_HOUGH_MIN_LINE", 18)),
            raster_max_line_gap=int(cfg.get("AT_LINES_HOUGH_MAX_GAP", 4)),
        )

    @staticmethod
    def _point(p):
        return float(p.x), float(p.y)

    def _segments_from_path_item(self, item):
        kind = item[0]
        if kind == "m":
            return []
        if kind == "l":
            p1, p2 = item[1], item[2]
            x1, y1 = self._point(p1)
            x2, y2 = self._point(p2)
            return [((x1, y1), (x2, y2), None)]
        if kind == "c":
            p0, p1, p2, p3 = item[1], item[2], item[3], item[4]
            points = [self._point(p0), self._point(p1), self._point(p2), self._point(p3)]
            segments = []
            for idx in range(len(points) - 1):
                segments.append((points[idx], points[idx + 1], points))
            return segments
        if kind == "re":
            rect = item[1]
            pts = [
                (rect.x0, rect.y0),
                (rect.x1, rect.y0),
                (rect.x1, rect.y1),
                (rect.x0, rect.y1),
            ]
            return [
                (pts[0], pts[1], [pts[0], pts[1], pts[2], pts[3], pts[0]]),
                (pts[1], pts[2], [pts[0], pts[1], pts[2], pts[3], pts[0]]),
                (pts[2], pts[3], [pts[0], pts[1], pts[2], pts[3], pts[0]]),
                (pts[3], pts[0], [pts[0], pts[1], pts[2], pts[3], pts[0]]),
            ]
        if kind == "qu":
            quad = item[1]
            pts = [(quad.ul.x, quad.ul.y), (quad.ur.x, quad.ur.y), (quad.lr.x, quad.lr.y), (quad.ll.x, quad.ll.y)]
            return [
                (pts[0], pts[1], pts + [pts[0]]),
                (pts[1], pts[2], pts + [pts[0]]),
                (pts[2], pts[3], pts + [pts[0]]),
                (pts[3], pts[0], pts + [pts[0]]),
            ]
        return []

    def _build_line(self, a, b, source_type, stroke_width=None, color=None, polyline_points=None, path_id=None, draw_order=None):
        x1, y1 = a
        x2, y2 = b
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length <= 0:
            return None
        angle = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
        return {
            "x1": round(x1, 3),
            "y1": round(y1, 3),
            "x2": round(x2, 3),
            "y2": round(y2, 3),
            "length": round(length, 3),
            "angle": round(angle, 3),
            "strokeWidth": stroke_width,
            "color": color,
            "polylinePoints": [
                {"x": round(float(px), 3), "y": round(float(py), 3)} for px, py in (polyline_points or [])
            ] if polyline_points else None,
            "sourceType": source_type,
            "pathId": path_id,
            "drawOrder": draw_order,
        }

    def extract_vector_lines(self, pdf_path, page_number):
        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            drawings = page.get_drawings()
            lines = []
            vector_object_count = 0
            for drawing_idx, drawing in enumerate(drawings):
                draw_type = str(drawing.get("type") or "").lower()
                is_stroked = "s" in draw_type or drawing.get("width") is not None
                if not is_stroked:
                    continue
                stroke = drawing.get("width")
                color = drawing.get("color")
                color_value = None
                if isinstance(color, (list, tuple)) and len(color) >= 3:
                    color_value = "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c * 255)))) for c in color[:3])
                path_id = f"path_{drawing_idx}"
                for item in drawing.get("items", []):
                    vector_object_count += 1
                    for a, b, polyline in self._segments_from_path_item(item):
                        line = self._build_line(
                            a,
                            b,
                            "pdf_vector",
                            stroke_width=stroke,
                            color=color_value,
                            polyline_points=polyline,
                            path_id=path_id,
                            draw_order=drawing_idx,
                        )
                        if line:
                            lines.append(line)
            page_w = float(page.rect.width)
            page_h = float(page.rect.height)
            return {
                "pageWidth": page_w,
                "pageHeight": page_h,
                "lines": lines,
                "meta": {
                    "vectorDrawingCount": len(drawings),
                    "vectorObjectCount": vector_object_count,
                    "nativeVectorAvailable": vector_object_count > 0,
                    "pageCoordinateSystem": {
                        "origin": "top_left",
                        "xAxis": "right",
                        "yAxis": "down",
                        "pageWidth": page_w,
                        "pageHeight": page_h,
                        "rotation": int(page.rotation or 0),
                    },
                    "viewportTransform": {"scaleX": 1.0, "scaleY": 1.0, "offsetX": 0.0, "offsetY": 0.0},
                },
            }

    def extract_raster_lines(self, pdf_path, page_number):
        try:
            import cv2
            import numpy as np
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Raster extraction unavailable: {exc}") from exc

        with fitz.open(pdf_path) as doc:
            page = doc.load_page(page_number - 1)
            matrix = fitz.Matrix(self.config.raster_scale, self.config.raster_scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            channels = pix.n
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, channels)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if channels >= 3 else img[:, :, 0]
            blur = cv2.GaussianBlur(gray, (3, 3), 0)
            edges = cv2.Canny(blur, 50, 160)
            detected = cv2.HoughLinesP(
                edges,
                rho=1,
                theta=np.pi / 180,
                threshold=self.config.raster_hough_threshold,
                minLineLength=self.config.raster_min_line_length,
                maxLineGap=self.config.raster_max_line_gap,
            )
            lines = []
            if detected is not None:
                inv = 1.0 / self.config.raster_scale
                for segment in detected:
                    x1, y1, x2, y2 = segment[0]
                    line = self._build_line((x1 * inv, y1 * inv), (x2 * inv, y2 * inv), "raster_detected")
                    if line:
                        lines.append(line)
            return {
                "pageWidth": float(page.rect.width),
                "pageHeight": float(page.rect.height),
                "lines": lines,
                "meta": {
                    "rasterResolution": {"width": pix.width, "height": pix.height},
                    "nativeVectorAvailable": False,
                },
            }

    def _is_nearly_same(self, a, b):
        eps = self.config.dedupe_eps
        same_dir = abs(a["x1"] - b["x1"]) <= eps and abs(a["y1"] - b["y1"]) <= eps and abs(a["x2"] - b["x2"]) <= eps and abs(a["y2"] - b["y2"]) <= eps
        rev_dir = abs(a["x1"] - b["x2"]) <= eps and abs(a["y1"] - b["y2"]) <= eps and abs(a["x2"] - b["x1"]) <= eps and abs(a["y2"] - b["y1"]) <= eps
        return same_dir or rev_dir

    def normalize_and_filter(self, lines, page_w, page_h, source_type):
        if not lines:
            return [], {"rejectedShort": 0, "rejectedDuplicate": 0}
        filtered = []
        rejected_short = 0
        rejected_dup = 0
        min_length = self.config.vector_min_length if source_type == "pdf_vector" else self.config.min_length
        for line in lines:
            if line["length"] < min_length:
                rejected_short += 1
                continue
            duplicate = any(self._is_nearly_same(line, prev) for prev in filtered)
            if duplicate:
                rejected_dup += 1
                continue
            line["x1"] = max(0.0, min(page_w, line["x1"]))
            line["x2"] = max(0.0, min(page_w, line["x2"]))
            line["y1"] = max(0.0, min(page_h, line["y1"]))
            line["y2"] = max(0.0, min(page_h, line["y2"]))
            filtered.append(line)
        return filtered, {"rejectedShort": rejected_short, "rejectedDuplicate": rejected_dup}

    def _bbox(self, lines):
        if not lines:
            return None
        xs = [line["x1"] for line in lines] + [line["x2"] for line in lines]
        ys = [line["y1"] for line in lines] + [line["y2"] for line in lines]
        return {
            "xMin": round(min(xs), 3),
            "yMin": round(min(ys), 3),
            "xMax": round(max(xs), 3),
            "yMax": round(max(ys), 3),
        }

    def extract_page_lines(self, pdf_path, page_number):
        vector = self.extract_vector_lines(pdf_path, page_number)
        vector_normalized, vector_rejected = self.normalize_and_filter(
            vector["lines"], vector["pageWidth"], vector["pageHeight"], "pdf_vector"
        )
        native_vector_available = bool((vector.get("meta") or {}).get("nativeVectorAvailable"))
        native_vector_used = bool(vector_normalized)
        fallback_used = False
        fallback_reason = None
        source = "pdf_vector"
        extraction = vector
        normalized = vector_normalized
        rejected = vector_rejected

        if not native_vector_used:
            fallback_used = True
            fallback_reason = "no_usable_pdf_vector_geometry"
            try:
                extraction = self.extract_raster_lines(pdf_path, page_number)
                source = "raster_detected"
                normalized, rejected = self.normalize_and_filter(
                    extraction["lines"], extraction["pageWidth"], extraction["pageHeight"], "raster_detected"
                )
            except Exception as exc:  # noqa: BLE001
                source = "pdf_vector"
                extraction = vector
                normalized = vector_normalized
                rejected = vector_rejected
                fallback_reason = f"raster_failed:{exc}"

        bbox = self._bbox(normalized)
        confidence = 0.0 if not normalized else min(0.99, 0.45 + min(len(normalized), 220) / 320)
        if source == "pdf_vector":
            confidence = min(0.99, confidence + 0.08)
        extraction_meta = extraction.get("meta") or {}
        vector_object_count = int((vector.get("meta") or {}).get("vectorObjectCount") or 0)
        vector_reason = "usable_pdf_geometry_detected" if native_vector_used else "no_vector_lines_after_normalization"
        return {
            "extractionSource": source,
            "isNativeVector": source == "pdf_vector",
            "pageWidth": extraction["pageWidth"],
            "pageHeight": extraction["pageHeight"],
            "lineCount": len(normalized),
            "lines": normalized,
            "bbox": bbox,
            "vectorObjectCount": vector_object_count,
            "extractionConfidence": round(confidence, 4),
            "vectorExtractionConfidence": round(confidence if source == "pdf_vector" else 0.0, 4),
            "fallbackUsed": fallback_used,
            "rasterFallbackUsed": fallback_used and source == "raster_detected",
            "fallbackReason": fallback_reason,
            "nativeVectorAvailable": native_vector_available,
            "nativeVectorUsed": native_vector_used,
            "vectorExtractionReason": vector_reason,
            "rejected": rejected,
            "meta": extraction_meta,
            "status": "COMPLETED" if normalized else "EMPTY",
        }

    @staticmethod
    def serialize_lines(lines):
        return json.dumps(lines, ensure_ascii=False)
