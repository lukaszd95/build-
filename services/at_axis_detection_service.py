import hashlib
import math
import re
from dataclasses import dataclass


@dataclass
class ATAxisDetectionConfig:
    min_length_ratio: float = 0.45
    min_abs_length: float = 80.0
    max_axis_angle_deg: float = 12.0
    merge_gap: float = 10.0
    merge_axis_tolerance: float = 6.0
    min_confidence: float = 0.35


class ATAxisDetectionService:
    LABEL_PATTERN = re.compile(r"^(?:[A-Z]|\d+|[A-Z]\d+|[A-Z]-\d+)$")

    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.config = ATAxisDetectionConfig(
            min_length_ratio=float(cfg.get("AT_AXIS_MIN_LENGTH_RATIO", 0.45)),
            min_abs_length=float(cfg.get("AT_AXIS_MIN_ABS_LENGTH", 80.0)),
            max_axis_angle_deg=float(cfg.get("AT_AXIS_MAX_ANGLE_DEG", 12.0)),
            merge_gap=float(cfg.get("AT_AXIS_MERGE_GAP", 10.0)),
            merge_axis_tolerance=float(cfg.get("AT_AXIS_MERGE_AXIS_TOL", 6.0)),
            min_confidence=float(cfg.get("AT_AXIS_MIN_CONFIDENCE", 0.35)),
        )

    @staticmethod
    def _length(line):
        return float(line.get("length") or math.hypot(float(line.get("x2", 0)) - float(line.get("x1", 0)), float(line.get("y2", 0)) - float(line.get("y1", 0))))

    @staticmethod
    def _normalize_angle(angle):
        a = abs(float(angle or 0.0)) % 180
        return min(a, abs(180 - a))

    def _direction(self, line):
        angle = self._normalize_angle(line.get("angle", 0.0))
        if angle <= self.config.max_axis_angle_deg:
            return "horizontal"
        if abs(90 - angle) <= self.config.max_axis_angle_deg:
            return "vertical"
        return "angled"

    @staticmethod
    def _line_bounds(line):
        x1, y1, x2, y2 = (float(line.get("x1", 0)), float(line.get("y1", 0)), float(line.get("x2", 0)), float(line.get("y2", 0)))
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    def _merge_collinear(self, lines, direction):
        if direction == "horizontal":
            normalized = []
            for line in lines:
                y = (float(line.get("y1", 0)) + float(line.get("y2", 0))) / 2
                x1, x2 = sorted([float(line.get("x1", 0)), float(line.get("x2", 0))])
                normalized.append({"line": line, "axis": y, "start": x1, "end": x2})
            normalized.sort(key=lambda item: (item["axis"], item["start"]))
        else:
            normalized = []
            for line in lines:
                x = (float(line.get("x1", 0)) + float(line.get("x2", 0))) / 2
                y1, y2 = sorted([float(line.get("y1", 0)), float(line.get("y2", 0))])
                normalized.append({"line": line, "axis": x, "start": y1, "end": y2})
            normalized.sort(key=lambda item: (item["axis"], item["start"]))

        groups = []
        for item in normalized:
            placed = False
            for group in groups:
                if abs(group["axis"] - item["axis"]) > self.config.merge_axis_tolerance:
                    continue
                if item["start"] > group["end"] + self.config.merge_gap:
                    continue
                group["axis_values"].append(item["axis"])
                group["axis"] = sum(group["axis_values"]) / len(group["axis_values"])
                group["start"] = min(group["start"], item["start"])
                group["end"] = max(group["end"], item["end"])
                group["segments"].append(item["line"])
                placed = True
                break
            if not placed:
                groups.append({
                    "axis": item["axis"],
                    "axis_values": [item["axis"]],
                    "start": item["start"],
                    "end": item["end"],
                    "segments": [item["line"]],
                })

        merged = []
        for group in groups:
            if direction == "horizontal":
                x1, y1, x2, y2 = group["start"], group["axis"], group["end"], group["axis"]
            else:
                x1, y1, x2, y2 = group["axis"], group["start"], group["axis"], group["end"]
            merged.append({
                "direction": direction,
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "segments": group["segments"],
                "length": math.hypot(x2 - x1, y2 - y1),
            })
        return merged

    def _extract_label_candidates(self, page_text):
        labels = []
        for token in re.split(r"\s+", (page_text or "").upper()):
            cleaned = re.sub(r"[^A-Z0-9\-]", "", token)
            if self.LABEL_PATTERN.match(cleaned):
                labels.append(cleaned)
        # preserve order, dedupe
        out = []
        seen = set()
        for lbl in labels:
            if lbl in seen:
                continue
            seen.add(lbl)
            out.append(lbl)
        return out[:40]

    def detect_axes(self, lines, page_width, page_height, page_text="", scale_factor=None):
        page_width = float(page_width or 1.0)
        page_height = float(page_height or 1.0)
        diag = math.hypot(page_width, page_height)
        long_threshold = max(self.config.min_abs_length, self.config.min_length_ratio * max(page_width, page_height))

        horizontal = []
        vertical = []
        weakeners = {}
        for line in lines or []:
            direction = self._direction(line)
            length = self._length(line)
            if direction not in {"horizontal", "vertical"}:
                continue
            if length < max(30.0, long_threshold * 0.25):
                continue
            if direction == "horizontal":
                horizontal.append(line)
            else:
                vertical.append(line)

        merged = self._merge_collinear(horizontal, "horizontal") + self._merge_collinear(vertical, "vertical")
        labels = self._extract_label_candidates(page_text)

        counts = {"horizontal": sum(1 for m in merged if m["direction"] == "horizontal"), "vertical": sum(1 for m in merged if m["direction"] == "vertical")}
        axes = []
        for idx, axis in enumerate(merged, start=1):
            positives = []
            negatives = []
            score = 0.0
            if axis["length"] >= long_threshold:
                score += 0.35
                positives.append("very_long_line")
            else:
                score += 0.12
                negatives.append("line_shorter_than_preferred_axis")

            coverage = axis["length"] / max(1.0, (page_width if axis["direction"] == "horizontal" else page_height))
            if coverage >= 0.65:
                score += 0.2
                positives.append("covers_large_part_of_page")
            else:
                negatives.append("limited_page_coverage")

            parallel_count = counts[axis["direction"]]
            if parallel_count >= 2:
                score += 0.18
                positives.append("belongs_to_parallel_group")
            else:
                negatives.append("no_parallel_group")

            orth_count = counts["vertical" if axis["direction"] == "horizontal" else "horizontal"]
            if orth_count >= 1:
                score += 0.12
                positives.append("cross_direction_grid_detected")

            if len(axis["segments"]) > 1:
                score += 0.08
                positives.append("merged_from_collinear_segments")

            if labels:
                score += 0.06
                positives.append("page_contains_axis_like_labels")

            avg_stroke = sum(float(s.get("strokeWidth") or 1.0) for s in axis["segments"]) / max(1, len(axis["segments"]))
            if avg_stroke <= 1.5:
                score += 0.05
                positives.append("thin_line_profile")
            else:
                negatives.append("line_thickness_may_match_wall")

            confidence = max(0.0, min(0.99, round(score, 4)))
            source_types = {str(seg.get("sourceType") or "unknown") for seg in axis["segments"]}
            detection_source = "merged_segments" if len(axis["segments"]) > 1 else (next(iter(source_types)) if source_types else "unknown")
            if confidence < self.config.min_confidence:
                continue

            label_candidates = labels[:5]
            axis_label = label_candidates[0] if label_candidates else None
            axis_id = hashlib.sha1(f"{axis['direction']}:{axis['x1']:.1f}:{axis['y1']:.1f}:{axis['x2']:.1f}:{axis['y2']:.1f}".encode("utf-8")).hexdigest()[:12]
            real_length = axis["length"] * float(scale_factor) if scale_factor else None
            axes.append({
                "axisId": axis_id,
                "axisLabel": axis_label,
                "axisDirection": axis["direction"],
                "x1": round(axis["x1"], 3),
                "y1": round(axis["y1"], 3),
                "x2": round(axis["x2"], 3),
                "y2": round(axis["y2"], 3),
                "realLength": round(real_length, 3) if real_length is not None else None,
                "confidence": confidence,
                "detectionSource": detection_source,
                "detectionReason": ", ".join(positives[:3]) or "heuristic_axis_candidate",
                "supportingSignals": positives,
                "weakeningSignals": negatives,
                "scoreBreakdown": {
                    "baseLengthThreshold": long_threshold,
                    "coverageRatio": round(coverage, 4),
                    "parallelCount": parallel_count,
                    "orthogonalCount": orth_count,
                    "score": confidence,
                },
                "sourceType": detection_source,
                "hasEndpointLabel": bool(axis_label),
                "builtFromSegments": len(axis["segments"]) > 1,
                "segmentsJson": axis["segments"],
                "labelCandidates": label_candidates,
                "axisGroupId": f"{axis['direction']}_group",
                "isUserConfirmed": None,
                "userOverrideLabel": None,
                "userStatus": None,
                "userNote": None,
            })

        return {
            "axes": axes,
            "meta": {
                "inputLines": len(lines or []),
                "mergedCandidates": len(merged),
                "labelsDetected": labels[:10],
                "pageWidth": page_width,
                "pageHeight": page_height,
                "diagonal": round(diag, 3),
            },
        }
