from services.site_layer_definitions import ALL_SITE_LAYER_KEYS, SITE_LAYER_DEFINITIONS


def test_site_layer_keys_exact_set():
    expected = {
        "plot_boundary",
        "land_use_boundary",
        "site_boundary",
        "building_setback_line",
        "mandatory_building_line",
        "offset_from_boundary_zone",
        "no_build_zone",
        "limited_build_zone",
        "road_edge",
        "road_centerline",
        "road_right_of_way",
        "access_point",
        "driveway",
        "fire_access_route",
        "parking_zone",
        "elevation_point",
        "contour_line",
        "terrain_break_line",
        "slope_zone",
        "embankment",
        "cut_slope",
        "retaining_wall",
        "existing_building",
        "adjacent_building",
        "outbuilding",
        "canopy_structure",
        "fence_line",
        "gate",
        "water_pipe",
        "sanitary_sewer",
        "storm_sewer",
        "gas_pipe",
        "power_line_underground",
        "power_line_overhead",
        "telecom_line",
        "utility_connection",
        "utility_node",
        "transformer_station",
        "utility_protection_zone",
        "watercourse",
        "drainage_ditch",
        "pond",
        "flood_zone",
        "soakaway_zone",
        "tree",
        "tree_canopy",
        "root_protection_zone",
        "shrub_area",
        "protected_tree",
        "biologically_active_area",
        "forest_boundary",
        "conservation_zone",
        "environmental_protection_zone",
        "noise_impact_zone",
        "height_limit_zone",
        "special_restriction_zone",
        "buildable_area",
        "max_building_envelope",
        "preferred_building_zone",
        "building_candidate",
    }
    assert set(ALL_SITE_LAYER_KEYS) == expected
    assert set(SITE_LAYER_DEFINITIONS.keys()) == expected


def test_definitions_have_required_fields():
    for index, key in enumerate(ALL_SITE_LAYER_KEYS):
        row = SITE_LAYER_DEFINITIONS[key]
        assert row.layerKey == key
        assert row.label
        assert row.group
        assert isinstance(row.defaultVisibility, bool)
        assert isinstance(row.defaultLocked, bool)
        assert row.sourcePreference
        assert row.geometryType
        assert isinstance(row.canBeDerived, bool)
        assert isinstance(row.sortOrder, int)
        assert row.sortOrder == index
