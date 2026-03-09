from shapely.geometry import shape

from services.site_geometry_service import createSiteBoundaryFromPlot


def test_create_site_boundary_from_plot_returns_polygon_and_expands_area():
    plot = {
        "type": "Polygon",
        "coordinates": [[[21.0, 52.0], [21.001, 52.0], [21.001, 52.001], [21.0, 52.001], [21.0, 52.0]]],
    }
    boundary = createSiteBoundaryFromPlot(plot, 30)
    assert boundary["type"] in ("Polygon", "MultiPolygon")
    assert shape(boundary).area > shape(plot).area
