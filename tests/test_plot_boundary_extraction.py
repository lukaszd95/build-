import ezdxf

from services.boundary_extractor import extract_boundaries
from services.dxf_parser import read_dxf


def _write_doc(tmp_path, builder):
    doc = ezdxf.new()
    msp = doc.modelspace()
    builder(msp)
    path = tmp_path / "sample.dxf"
    doc.saveas(path)
    return path


def test_closed_polyline_boundary(tmp_path):
    def build(msp):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "DZIALKA"})

    path = _write_doc(tmp_path, build)
    doc = read_dxf(str(path))
    result = extract_boundaries(doc)
    assert len(result.candidates) == 1


def test_stitch_lines_into_boundary(tmp_path):
    def build(msp):
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "GRANICA"})
        msp.add_line((10, 0), (10, 10), dxfattribs={"layer": "GRANICA"})
        msp.add_line((10, 10), (0, 10), dxfattribs={"layer": "GRANICA"})
        msp.add_line((0, 10), (0, 0), dxfattribs={"layer": "GRANICA"})

    path = _write_doc(tmp_path, build)
    doc = read_dxf(str(path))
    result = extract_boundaries(doc)
    assert len(result.candidates) == 1


def test_ambiguous_candidates(tmp_path):
    def build(msp):
        msp.add_lwpolyline([(0, 0), (8, 0), (8, 8), (0, 8)], close=True, dxfattribs={"layer": "LAYER_A"})
        msp.add_lwpolyline([(20, 0), (28, 0), (28, 8), (20, 8)], close=True, dxfattribs={"layer": "LAYER_B"})

    path = _write_doc(tmp_path, build)
    doc = read_dxf(str(path))
    result = extract_boundaries(doc)
    assert len(result.candidates) == 2
    assert result.confidence < 0.8
