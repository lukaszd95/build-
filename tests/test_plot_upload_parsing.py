import ezdxf
import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from services.import_service import get_boundaries, handle_plot_upload
from utils.db import init_db


def _build_app(tmp_path):
    app = Flask(__name__)
    app.config["DB_PATH"] = str(tmp_path / "test.db")
    app.config["PLOT_UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    app.config["PLOT_MAX_SIZE_MB"] = 5
    app.config["DWG2DXF_PATH"] = None
    app.config["ODA_FILE_CONVERTER"] = None
    init_db(app)
    return app


def _write_dxf(tmp_path, builder):
    doc = ezdxf.new()
    builder(doc.modelspace())
    path = tmp_path / "plot.dxf"
    doc.saveas(path)
    return path


def test_handle_plot_upload_closed_polyline(tmp_path):
    def build(msp):
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={"layer": "GRANICA"})

    path = _write_dxf(tmp_path, build)
    app = _build_app(tmp_path)

    with app.app_context():
        with open(path, "rb") as handle:
            storage = FileStorage(stream=handle, filename="plot.dxf", content_type="application/dxf")
            payload = handle_plot_upload(app.config, storage)
            details = get_boundaries(app.config["DB_PATH"], payload["importJobId"])

    assert payload["importJobId"]
    assert details["selectedBoundary"]["geometry"]["type"] == "Polygon"


def test_handle_plot_upload_no_geometry(tmp_path):
    path = _write_dxf(tmp_path, lambda _msp: None)
    app = _build_app(tmp_path)

    with app.app_context():
        with open(path, "rb") as handle:
            storage = FileStorage(stream=handle, filename="plot.dxf", content_type="application/dxf")
            with pytest.raises(ValueError, match="Nie znaleziono granic działek"):
                handle_plot_upload(app.config, storage)
