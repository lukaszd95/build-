from services.at_scale_detection_service import ATScaleDetectionService


def test_detect_scale_patterns_from_text():
    svc = ATScaleDetectionService()
    text = """
    TABELKA RYSUNKOWA
    SKALA 1:100
    skala 1 : 50
    scale 1:200
    """
    candidates = svc.detect_scale_from_text(text)
    normalized = {entry["normalized"] for entry in candidates}
    assert "1:100" in normalized
    assert "1:50" in normalized
    assert "1:200" in normalized


def test_extract_dimension_candidates_filters_noise():
    svc = ATScaleDetectionService()
    text = "pom. 12 4200 3500 4,20m nr 5"
    dims = svc.extract_dimension_candidates(text)
    raws = " ".join(entry["raw"] for entry in dims)
    assert "4200" in raws
    assert "3500" in raws
    assert "12" not in raws


def test_infer_scale_from_multiple_dimensions():
    svc = ATScaleDetectionService()
    dims = [
        {"raw": "4200", "valueMm": 4200},
        {"raw": "3500", "valueMm": 3500},
        {"raw": "1200", "valueMm": 1200},
    ]
    lines = [
        {"length": 420},
        {"length": 350},
        {"length": 120},
        {"length": 50},
    ]
    inferred = svc.infer_scale_from_dimensions(dims, lines)
    assert inferred is not None
    assert inferred["source"] == "dimension_inferred_scale"
    assert inferred["pdfUnitToRealFactor"] > 0


def test_resolve_scale_conflict_and_manual_override():
    svc = ATScaleDetectionService()
    text_candidates = [{"raw": "Skala 1:50", "normalized": "1:50", "ratio": 50, "source": "drawing_label_scale", "confidence": 0.9}]
    inferred = {"normalized": "1:120", "ratio": 120, "pdfUnitToRealFactor": 1200, "source": "dimension_inferred_scale", "confidence": 0.66}
    resolved = svc.resolve_scale(text_candidates, inferred)
    assert resolved["scaleConflictDetected"] is True
    override = svc.resolve_scale(text_candidates, inferred, override={"ratio": 200, "pdfUnitToRealFactor": 2000, "reason": "manual"})
    assert override["scaleSource"] == "manual_override"
    assert override["scaleConfidence"] == 1.0
