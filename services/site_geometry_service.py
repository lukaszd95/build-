from __future__ import annotations

from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform
from shapely.validation import make_valid

try:
    from pyproj import Transformer
except Exception:
    Transformer = None


def createSiteBoundaryFromPlot(plotGeometry: dict[str, Any], bufferMeters: float = 30) -> dict[str, Any]:
    """Create analytical site boundary (buffer) from plot geometry."""
    plot_geom_4326 = make_valid(shape(plotGeometry))
    if Transformer is not None:
        to_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True).transform
        to_4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
        plot_2180 = shp_transform(to_2180, plot_geom_4326)
        buffer_2180 = plot_2180.buffer(float(bufferMeters or 30))
        buffer_4326 = shp_transform(to_4326, buffer_2180)
    else:
        deg_buffer = float(bufferMeters or 30) / 111_320.0
        buffer_4326 = plot_geom_4326.buffer(deg_buffer)
    return mapping(buffer_4326)
