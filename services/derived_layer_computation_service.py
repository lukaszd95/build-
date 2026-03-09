from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import GeometryCollection, shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid


@dataclass
class DerivedLayerComputationResult:
    layers: dict[str, list[dict[str, Any]]]
    errors: list[str]


class DerivedLayerComputationService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.offset_m = float(self.config.get("offsetFromBoundaryMeters", 4.0))
        self.utility_buffer_m = {
            "water_pipe": float(self.config.get("utilityBufferByType", {}).get("water_pipe", 1.5)),
            "sanitary_sewer": float(self.config.get("utilityBufferByType", {}).get("sanitary_sewer", 2.0)),
            "storm_sewer": float(self.config.get("utilityBufferByType", {}).get("storm_sewer", 2.0)),
            "gas_pipe": float(self.config.get("utilityBufferByType", {}).get("gas_pipe", 3.0)),
            "power_line_underground": float(self.config.get("utilityBufferByType", {}).get("power_line_underground", 1.5)),
            "power_line_overhead": float(self.config.get("utilityBufferByType", {}).get("power_line_overhead", 4.0)),
            "telecom_line": float(self.config.get("utilityBufferByType", {}).get("telecom_line", 1.0)),
            "utility_connection": float(self.config.get("utilityBufferByType", {}).get("utility_connection", 1.0)),
            "utility_node": float(self.config.get("utilityBufferByType", {}).get("utility_node", 1.0)),
            "transformer_station": float(self.config.get("utilityBufferByType", {}).get("transformer_station", 2.0)),
        }
        self.tree_canopy_placeholder_m = float(self.config.get("treeCanopyPlaceholderMeters", 2.0))
        self.root_zone_buffer_m = float(self.config.get("rootProtectionExtraMeters", 1.5))


    def _distance_for_geom(self, distance: float, reference_geom: Any) -> float:
        try:
            minx, miny, maxx, maxy = reference_geom.bounds
            span = min(abs(maxx - minx), abs(maxy - miny))
            if span <= 0:
                return max(distance, 0.0)
            # For geographic-like coordinates keep conservative relative buffers.
            if span < 1.0:
                return min(max(distance, 0.0), span * 0.2)
            return max(distance, 0.0)
        except Exception:
            return max(distance, 0.0)

    def compute(
        self,
        *,
        plot_boundary: dict[str, Any],
        site_boundary: dict[str, Any],
        layers: dict[str, list[dict[str, Any]]],
    ) -> DerivedLayerComputationResult:
        errors: list[str] = []
        result: dict[str, list[dict[str, Any]]] = {}

        try:
            plot_geom = make_valid(shape(plot_boundary))
            site_geom = make_valid(shape(site_boundary))
        except Exception as exc:
            return DerivedLayerComputationResult(layers={}, errors=[f"base geometry error: {exc}"])

        # 1) offset_from_boundary_zone
        try:
            offset_distance = self._distance_for_geom(self.offset_m, plot_geom)
            inner = make_valid(plot_geom.buffer(-offset_distance))
            if inner.is_empty:
                offset_zone = plot_geom
            else:
                offset_zone = make_valid(plot_geom.difference(inner))
            result["offset_from_boundary_zone"] = self._to_features(offset_zone, {"derived": True, "type": "offset_from_boundary_zone"})
        except Exception as exc:
            errors.append(f"offset_from_boundary_zone: {exc}")
            result["offset_from_boundary_zone"] = []

        # 2) utility_protection_zone
        try:
            buffered = []
            for layer_key, distance in self.utility_buffer_m.items():
                for ft in layers.get(layer_key, []):
                    geom = self._feature_geom(ft)
                    if geom is None:
                        continue
                    buffered.append(geom.buffer(self._distance_for_geom(distance, site_geom)))
            utility_zone = unary_union(buffered) if buffered else GeometryCollection()
            if not utility_zone.is_empty:
                utility_zone = make_valid(utility_zone.intersection(site_geom))
            result["utility_protection_zone"] = self._to_features(utility_zone, {"derived": True, "type": "utility_protection_zone"})
        except Exception as exc:
            errors.append(f"utility_protection_zone: {exc}")
            result["utility_protection_zone"] = []

        # 3) tree_canopy
        tree_canopy_geoms = []
        try:
            for ft in layers.get("tree", []):
                geom = self._feature_geom(ft)
                if geom is None:
                    continue
                props = (ft or {}).get("properties") or {}
                radius = props.get("canopyRadius") or props.get("crownRadius") or props.get("treeCrownRadius")
                if radius is None:
                    radius = self.tree_canopy_placeholder_m
                tree_canopy_geoms.append(geom.buffer(self._distance_for_geom(float(radius), site_geom)))
            canopies = unary_union(tree_canopy_geoms) if tree_canopy_geoms else GeometryCollection()
            result["tree_canopy"] = self._to_features(canopies, {"derived": True, "type": "tree_canopy"})
        except Exception as exc:
            errors.append(f"tree_canopy: {exc}")
            result["tree_canopy"] = []

        # 4) root_protection_zone
        try:
            root_base = unary_union(tree_canopy_geoms) if tree_canopy_geoms else GeometryCollection()
            root_distance = self._distance_for_geom(self.root_zone_buffer_m, site_geom)
            root_zone = make_valid(root_base.buffer(root_distance)) if not root_base.is_empty else GeometryCollection()
            result["root_protection_zone"] = self._to_features(root_zone, {"derived": True, "type": "root_protection_zone"})
        except Exception as exc:
            errors.append(f"root_protection_zone: {exc}")
            result["root_protection_zone"] = []

        # 5) limited_build_zone
        try:
            constraint_geoms = []
            for lk in [
                "offset_from_boundary_zone",
                "utility_protection_zone",
                "root_protection_zone",
                "no_build_zone",
                "flood_zone",
                "embankment",
                "cut_slope",
            ]:
                if lk in result:
                    source_features = result.get(lk, [])
                else:
                    source_features = layers.get(lk, [])
                for ft in source_features:
                    geom = self._feature_geom(ft)
                    if geom is not None:
                        constraint_geoms.append(geom)
            limited = unary_union(constraint_geoms) if constraint_geoms else GeometryCollection()
            limited = make_valid(limited.intersection(plot_geom)) if not limited.is_empty else GeometryCollection()
            result["limited_build_zone"] = self._to_features(limited, {"derived": True, "type": "limited_build_zone"})
        except Exception as exc:
            errors.append(f"limited_build_zone: {exc}")
            result["limited_build_zone"] = []

        return DerivedLayerComputationResult(layers=result, errors=errors)

    def _feature_geom(self, feature: dict[str, Any]) -> Any | None:
        geometry = (feature or {}).get("geometry")
        if not isinstance(geometry, dict):
            return None
        try:
            return make_valid(shape(geometry))
        except Exception:
            return None

    def _to_features(self, geometry: Any, props: dict[str, Any]) -> list[dict[str, Any]]:
        if geometry is None or geometry.is_empty:
            return []
        if hasattr(geometry, "geoms") and geometry.geom_type.startswith("Multi"):
            return [{"type": "Feature", "geometry": mapping(geom), "properties": dict(props)} for geom in geometry.geoms if not geom.is_empty]
        if geometry.geom_type == "GeometryCollection":
            return [{"type": "Feature", "geometry": mapping(geom), "properties": dict(props)} for geom in geometry.geoms if not geom.is_empty]
        return [{"type": "Feature", "geometry": mapping(geometry), "properties": dict(props)}]
