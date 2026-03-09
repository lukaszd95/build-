from services.layer_import_coordinator import LayerImportCoordinator


def test_layer_import_coordinator_plans_all_layers():
    coordinator = LayerImportCoordinator()
    plan = coordinator.plan(selected_layer_keys=["plot_boundary", "existing_building"])
    layer_keys = {item["layerKey"] for item in plan["layers"]}
    assert "plot_boundary" in layer_keys
    assert "building_candidate" in layer_keys
    assert "existing_building" in plan["directImport"]
    assert "buildable_area" in plan["derivedLater"]


def test_layer_import_coordinator_assigns_required_status_strategies():
    coordinator = LayerImportCoordinator()
    plan = coordinator.plan()
    by_key = {item["layerKey"]: item for item in plan["layers"]}
    assert by_key["land_use_boundary"]["targetStatus"] == "loaded"
    assert by_key["building_setback_line"]["targetStatus"] == "manual_placeholder"
    assert by_key["buildable_area"]["targetStatus"] == "derived"
    assert by_key["adjacent_building"]["targetStatus"] == "unavailable"


def test_layer_import_coordinator_matches_command_9_layer_groups():
    coordinator = LayerImportCoordinator()
    plan = coordinator.plan()
    by_key = {item["layerKey"]: item for item in plan["layers"]}

    direct_expected = {
        "land_use_boundary",
        "road_edge",
        "road_centerline",
        "road_right_of_way",
        "elevation_point",
        "contour_line",
        "existing_building",
        "fence_line",
        "water_pipe",
        "sanitary_sewer",
        "storm_sewer",
        "gas_pipe",
        "power_line_underground",
        "power_line_overhead",
        "telecom_line",
        "utility_node",
        "transformer_station",
        "watercourse",
        "drainage_ditch",
        "pond",
        "flood_zone",
        "tree",
        "shrub_area",
        "forest_boundary",
        "conservation_zone",
        "environmental_protection_zone",
        "noise_impact_zone",
        "height_limit_zone",
        "special_restriction_zone",
    }
    placeholder_expected = {
        "building_setback_line",
        "mandatory_building_line",
        "no_build_zone",
        "access_point",
        "driveway",
        "fire_access_route",
        "parking_zone",
        "terrain_break_line",
        "slope_zone",
        "embankment",
        "cut_slope",
        "retaining_wall",
        "outbuilding",
        "canopy_structure",
        "gate",
        "utility_connection",
        "soakaway_zone",
        "protected_tree",
    }

    assert set(plan["directImport"]) == direct_expected
    assert set(plan["manualPlaceholder"]) == placeholder_expected

    for key in direct_expected:
        assert by_key[key]["strategy"] == "try_direct_import"
        assert by_key[key]["targetStatus"] == "loaded"

    for key in placeholder_expected:
        assert by_key[key]["strategy"] == "manual_placeholder"
        assert by_key[key]["targetStatus"] == "manual_placeholder"
