import math
import re
from statistics import median


class ATScaleDetectionService:
    SCALE_PATTERNS = [
        re.compile(r"(?i)\b(?:skala(?:\s+rysunku)?|scale|skale)\s*[:\-]?\s*(\d+)\s*:\s*(\d+)"),
        re.compile(r"\b(\d+)\s*:\s*(\d+)\b"),
    ]
    DIM_TOKEN = re.compile(r"(?<![\w/])(\d{2,5}(?:[\.,]\d{1,2})?)(?:\s?(mm|cm|m))?(?![\w/])", re.IGNORECASE)

    def detect_scale_from_text(self, page_text):
        candidates = []
        if not page_text:
            return candidates
        lowered = page_text.lower()
        for pattern in self.SCALE_PATTERNS:
            for match in pattern.finditer(page_text):
                left = int(match.group(1))
                right = int(match.group(2))
                if left <= 0 or right <= 0:
                    continue
                if left != 1:
                    continue
                raw = match.group(0).strip()
                source = "text_scale_detected"
                confidence = 0.62
                if "skala" in raw.lower() or "scale" in raw.lower():
                    source = "drawing_label_scale"
                    confidence = 0.86
                if any(tag in lowered for tag in ["tabel", "ramka", "title", "nagł", "rysunku"]):
                    source = "title_block_scale"
                    confidence = min(0.96, confidence + 0.06)
                candidates.append(
                    {
                        "raw": raw,
                        "normalized": f"1:{right}",
                        "ratio": right,
                        "source": source,
                        "confidence": round(confidence, 4),
                    }
                )
        unique = {}
        for entry in candidates:
            key = (entry["normalized"], entry["source"])
            prev = unique.get(key)
            if not prev or prev["confidence"] < entry["confidence"]:
                unique[key] = entry
        return sorted(unique.values(), key=lambda item: item["confidence"], reverse=True)

    @staticmethod
    def _to_mm(value, unit):
        if unit == "m":
            return value * 1000.0
        if unit == "cm":
            return value * 10.0
        return value

    def extract_dimension_candidates(self, page_text):
        if not page_text:
            return []
        out = []
        for match in self.DIM_TOKEN.finditer(page_text):
            raw = match.group(1)
            token = raw.replace(",", ".")
            try:
                numeric = float(token)
            except ValueError:
                continue
            if numeric <= 0:
                continue
            # Filter obvious room numbers / indexes heuristically.
            if numeric < 20:
                continue
            unit = (match.group(2) or "").lower() or None
            if unit is None:
                if numeric >= 100:
                    unit = "mm"
                else:
                    # In architectural floor plans dimensions without explicit unit
                    # are most commonly expressed in centimeters.
                    unit = "cm"
            mm_value = self._to_mm(numeric, unit)
            if mm_value < 100 or mm_value > 100000:
                continue
            out.append(
                {
                    "raw": match.group(0),
                    "value": numeric,
                    "unit": unit,
                    "valueMm": round(mm_value, 3),
                    "confidence": 0.58 if match.group(2) else 0.52,
                }
            )
        return out[:80]

    def infer_scale_from_dimensions(self, dimension_candidates, lines):
        if not dimension_candidates or not lines:
            return None
        line_lengths = sorted([float(line.get("length") or 0.0) for line in lines if float(line.get("length") or 0.0) > 0.0])
        if not line_lengths:
            return None

        factor_candidates = []
        for dim in dimension_candidates:
            mm = float(dim.get("valueMm") or 0.0)
            if mm <= 0:
                continue
            for length in line_lengths[-120:]:
                factor = mm / length
                if 0.05 <= factor <= 5000:
                    factor_candidates.append(
                        {
                            "dimension": dim,
                            "lineLength": round(length, 4),
                            "pdfUnitToRealFactor": factor,
                        }
                    )

        if not factor_candidates:
            return None

        grouped = {}
        for cand in factor_candidates:
            bucket = round(cand["pdfUnitToRealFactor"], 1)
            grouped.setdefault(bucket, []).append(cand)
        bucket, bucket_items = max(grouped.items(), key=lambda kv: len(kv[1]))
        factors = [item["pdfUnitToRealFactor"] for item in bucket_items]
        inferred_factor = median(factors)
        inferred_ratio = max(1, int(round(inferred_factor / 10.0)))
        spread = max(factors) - min(factors) if len(factors) > 1 else 0.0
        confidence = 0.44 + min(len(bucket_items), 12) * 0.035
        if spread < inferred_factor * 0.12:
            confidence += 0.12
        confidence = min(0.92, confidence)
        return {
            "normalized": f"1:{inferred_ratio}",
            "ratio": inferred_ratio,
            "pdfUnitToRealFactor": round(inferred_factor, 6),
            "source": "dimension_inferred_scale",
            "confidence": round(confidence, 4),
            "dimensionCandidatesUsed": [
                {
                    "dimensionRaw": item["dimension"]["raw"],
                    "dimensionMm": item["dimension"]["valueMm"],
                    "lineLength": item["lineLength"],
                    "factor": round(item["pdfUnitToRealFactor"], 6),
                }
                for item in bucket_items[:12]
            ],
            "consistencySpread": round(spread, 6),
        }

    def resolve_scale(self, text_candidates, inferred_scale, override=None):
        if override:
            ratio = int(override.get("ratio") or 0)
            factor = float(override.get("pdfUnitToRealFactor") or 0.0)
            return {
                "detectedScaleText": f"1:{ratio}" if ratio else None,
                "detectedScaleNormalized": f"1:{ratio}" if ratio else None,
                "scaleSource": "manual_override",
                "scaleConfidence": 1.0,
                "scaleReason": override.get("reason") or "manual_override",
                "pdfUnitToRealFactor": round(factor, 6) if factor else None,
                "scaleConflictDetected": False,
                "scaleConflictReason": None,
                "scaleConsistencyCheck": "manual_override",
                "scaleDetectedBySystem": (text_candidates[0] if text_candidates else inferred_scale) or None,
                "scaleConfirmedByUser": f"1:{ratio}" if ratio else None,
            }

        best_text = text_candidates[0] if text_candidates else None
        trusted_text_sources = {"drawing_label_scale", "title_block_scale"}
        text_is_trusted = best_text and best_text.get("source") in trusted_text_sources
        text_confident_enough = best_text and best_text["confidence"] >= 0.72
        if best_text and (not inferred_scale or text_confident_enough or text_is_trusted):
            conflict = bool(inferred_scale and abs(inferred_scale["pdfUnitToRealFactor"] - best_text["ratio"] * 10) > best_text["ratio"] * 2)
            return {
                "detectedScaleText": best_text["raw"],
                "detectedScaleNormalized": best_text["normalized"],
                "scaleSource": best_text["source"],
                "scaleConfidence": min(0.98, best_text["confidence"] + (0.08 if inferred_scale and not conflict else 0.0)),
                "scaleReason": "scale_from_text" if not conflict else "text_dimension_conflict",
                "pdfUnitToRealFactor": round(best_text["ratio"] * 10.0, 6),
                "scaleConflictDetected": conflict,
                "scaleConflictReason": "text_scale_differs_from_dimension_inference" if conflict else None,
                "scaleConsistencyCheck": "consistent" if inferred_scale and not conflict else "not_checked",
                "scaleDetectedBySystem": best_text,
                "scaleConfirmedByUser": None,
            }

        if inferred_scale:
            return {
                "detectedScaleText": inferred_scale["normalized"],
                "detectedScaleNormalized": inferred_scale["normalized"],
                "scaleSource": inferred_scale["source"],
                "scaleConfidence": inferred_scale["confidence"],
                "scaleReason": "scale_from_dimensions",
                "pdfUnitToRealFactor": inferred_scale["pdfUnitToRealFactor"],
                "scaleConflictDetected": False,
                "scaleConflictReason": None,
                "scaleConsistencyCheck": "dimension_only",
                "scaleDetectedBySystem": inferred_scale,
                "scaleConfirmedByUser": None,
            }

        return {
            "detectedScaleText": None,
            "detectedScaleNormalized": None,
            "scaleSource": "text_scale_detected",
            "scaleConfidence": 0.18,
            "scaleReason": "unable_to_resolve_scale",
            "pdfUnitToRealFactor": None,
            "scaleConflictDetected": False,
            "scaleConflictReason": None,
            "scaleConsistencyCheck": "insufficient_data",
            "scaleDetectedBySystem": None,
            "scaleConfirmedByUser": None,
        }
