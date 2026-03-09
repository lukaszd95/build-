from shapely.geometry import shape

from services.site_buildability_analysis_service import SiteBuildabilityAnalysisService


def test_buildability_analysis_computes_geometries_candidates_and_area_reduction():
    service = SiteBuildabilityAnalysisService()
    plot = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]],
    }
    layers = {
        "no_build_zone": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [4, 1], [4, 4], [1, 4], [1, 1]]]}, "properties": {}}
        ],
        "offset_from_boundary_zone": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [20, 0], [20, 2], [0, 2], [0, 0]]]}, "properties": {}}
        ],
        "utility_protection_zone": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [12, 10], [12, 12], [10, 12], [10, 10]]]}, "properties": {}}
        ],
    }

    result = service.compute(plot_boundary=plot, layers=layers)

    assert result.buildable_area_geometry is not None
    assert result.max_building_envelope_geometry is not None
    assert result.preferred_building_zone_geometry is not None
    assert result.building_candidates
    assert any(item["type"] == "no_build_zone" for item in result.constraints)
    assert shape(result.buildable_area_geometry).area < shape(plot).area
