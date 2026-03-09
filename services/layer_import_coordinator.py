from __future__ import annotations

from typing import Any

from services.site_layer_definitions import ALL_SITE_LAYER_KEYS, SITE_LAYER_DEFINITIONS


DIRECT_IMPORT_LAYER_KEYS = {
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

MANUAL_PLACEHOLDER_LAYER_KEYS = {
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


class LayerImportCoordinator:
    """Decides import strategy for each defined layer."""

    def plan(self, selected_layer_keys: list[str] | None = None) -> dict[str, Any]:
        selected = set(selected_layer_keys or [])
        planned_layers: list[dict[str, Any]] = []
        direct = []
        empty = []
        derived = []
        placeholders = []
        unavailable = []

        for key in ALL_SITE_LAYER_KEYS:
            definition = SITE_LAYER_DEFINITIONS[key]
            if key in {"plot_boundary", "site_boundary"}:
                strategy = "core_geometry"
                target_status = "loaded"
                geometry_scope = "plot_boundary" if key == "plot_boundary" else "site_boundary"
            elif key in DIRECT_IMPORT_LAYER_KEYS:
                strategy = "try_direct_import"
                target_status = "loaded"
                geometry_scope = "plot_boundary" if key in {"land_use_boundary"} else "site_boundary"
                direct.append(key)
            elif key in MANUAL_PLACEHOLDER_LAYER_KEYS:
                strategy = "manual_placeholder"
                target_status = "manual_placeholder"
                geometry_scope = "site_boundary"
                placeholders.append(key)
            elif definition.canBeDerived:
                strategy = "derive_later"
                target_status = "derived"
                geometry_scope = "site_boundary"
                derived.append(key)
            elif selected and key not in selected:
                strategy = "create_empty"
                target_status = "empty"
                geometry_scope = "site_boundary"
                empty.append(key)
            else:
                strategy = "source_unavailable"
                target_status = "unavailable"
                geometry_scope = "site_boundary"
                unavailable.append(key)

            planned_layers.append(
                {
                    "layerKey": key,
                    "strategy": strategy,
                    "targetStatus": target_status,
                    "geometryScope": geometry_scope,
                    "sourcePreference": definition.sourcePreference,
                    "geometryType": definition.geometryType,
                }
            )

        return {
            "layers": planned_layers,
            "directImport": direct,
            "empty": empty,
            "derivedLater": derived,
            "manualPlaceholder": placeholders,
            "unavailable": unavailable,
        }
