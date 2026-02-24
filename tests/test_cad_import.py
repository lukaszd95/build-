import ezdxf

from services.boundary_extractor import extract_boundaries
from services.cad_pipeline import select_main_boundary
from services.dxf_parser import detect_units


def test_detect_units_from_header():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 4
    unit_name, scale, source = detect_units(doc, bounds=(0, 0, 10, 10))
    assert unit_name == "mm"
    assert scale == 0.001
    assert source == "header"


def test_detect_units_heuristic():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 0
    unit_name, scale, source = detect_units(doc, bounds=(0, 0, 20000, 1000))
    assert unit_name == "mm"
    assert scale == 0.001
    assert source == "heuristic"


def test_boundary_detection_closed_polyline():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={"layer": "GRANICA"})
    extraction = extract_boundaries(doc)
    assert extraction.candidates
    assert any(candidate.layer == "GRANICA" for candidate in extraction.candidates)
    assert any(candidate.source == "closed-polyline" for candidate in extraction.candidates)


def test_boundary_detection_line_loop_with_tolerance():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 10))
    msp.add_line((10, 10), (0, 10))
    msp.add_line((0, 10), (0.001, 0.001))
    extraction = extract_boundaries(doc)
    assert extraction.candidates
    assert any(candidate.source == "line-loop" for candidate in extraction.candidates)


def test_select_main_boundary():
    class DummyBoundary:
        def __init__(self, area):
            self.area = area

    candidates = [DummyBoundary(10), DummyBoundary(20), DummyBoundary(5)]
    selected = select_main_boundary(candidates)
    assert selected.area == 20
