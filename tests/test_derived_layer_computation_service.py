from services.derived_layer_computation_service import DerivedLayerComputationService


def test_derived_layers_computation_returns_expected_layers():
    service = DerivedLayerComputationService()
    plot = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
    }
    site = {
        "type": "Polygon",
        "coordinates": [[[-5, -5], [15, -5], [15, 15], [-5, 15], [-5, -5]]],
    }
    layers = {
        "tree": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [2, 2]}, "properties": {}}],
        "water_pipe": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-2, 5], [12, 5]]}, "properties": {}}],
        "no_build_zone": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}, "properties": {}}],
    }

    result = service.compute(plot_boundary=plot, site_boundary=site, layers=layers)

    assert result.errors == []
    assert result.layers["offset_from_boundary_zone"]
    assert result.layers["utility_protection_zone"]
    assert result.layers["tree_canopy"]
    assert result.layers["root_protection_zone"]
    assert "limited_build_zone" in result.layers
