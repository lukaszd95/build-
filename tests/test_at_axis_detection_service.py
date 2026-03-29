from services.at_axis_detection_service import ATAxisDetectionService


def _line(x1, y1, x2, y2, angle, stroke=1.0, source="pdf_vector"):
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "angle": angle,
        "length": ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5,
        "strokeWidth": stroke,
        "sourceType": source,
    }


def test_detects_axes_for_grid_and_labels():
    svc = ATAxisDetectionService({"AT_AXIS_MIN_CONFIDENCE": 0.2})
    lines = [
        _line(10, 20, 390, 20, 0),
        _line(10, 90, 390, 90, 0),
        _line(40, 10, 40, 290, 90),
        _line(180, 10, 180, 290, 90),
    ]
    result = svc.detect_axes(lines, 400, 300, page_text="A B 1 2")
    assert len(result["axes"]) >= 4
    assert any(axis["axisDirection"] == "horizontal" for axis in result["axes"])
    assert any(axis["axisDirection"] == "vertical" for axis in result["axes"])
    assert any(axis["axisLabel"] for axis in result["axes"])


def test_merges_collinear_segments_into_single_axis():
    svc = ATAxisDetectionService({"AT_AXIS_MIN_CONFIDENCE": 0.2})
    lines = [
        _line(10, 50, 130, 50, 0),
        _line(133, 50, 260, 50, 0),
        _line(263, 50, 390, 50, 0),
        _line(20, 10, 20, 290, 90),
    ]
    result = svc.detect_axes(lines, 400, 300, page_text="A 1")
    merged = [axis for axis in result["axes"] if axis["axisDirection"] == "horizontal"]
    assert merged
    assert any(axis["builtFromSegments"] for axis in merged)


def test_short_or_thick_lines_reduce_detection():
    svc = ATAxisDetectionService({"AT_AXIS_MIN_CONFIDENCE": 0.6})
    lines = [
        _line(10, 20, 80, 20, 0, stroke=3.0),
        _line(10, 40, 90, 40, 0, stroke=3.0),
        _line(10, 60, 95, 60, 0, stroke=3.0),
    ]
    result = svc.detect_axes(lines, 400, 300, page_text="pom. 01")
    assert result["axes"] == []
