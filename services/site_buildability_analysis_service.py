from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import GeometryCollection, mapping, shape
from shapely.validation import make_valid


@dataclass
class SiteBuildabilityAnalysisResult:
    buildable_area_geometry: dict[str, Any] | None
    max_building_envelope_geometry: dict[str, Any] | None
    preferred_building_zone_geometry: dict[str, Any] | None
    building_candidates: list[dict[str, Any]]
    constraints: list[dict[str, Any]]
    observations: list[str]
    warnings: list[str]
    notes: list[str]


class SiteBuildabilityAnalysisService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.preferred_shrink_m = float(self.config.get("preferredZoneShrinkMeters", 1.5))

    def compute(self, *, plot_boundary: dict[str, Any], layers: dict[str, list[dict[str, Any]]]) -> SiteBuildabilityAnalysisResult:
        plot_geom = make_valid(shape(plot_boundary))

        restricted_layer_keys = [
            "no_build_zone",
            "offset_from_boundary_zone",
            "utility_protection_zone",
            "root_protection_zone",
            "flood_zone",
            "limited_build_zone",
            "embankment",
            "cut_slope",
            "special_restriction_zone",
            "environmental_protection_zone",
            "conservation_zone",
            "noise_impact_zone",
            "height_limit_zone",
        ]
        restricted_geoms = []
        constraints = []
        for key in restricted_layer_keys:
            geoms = self._layer_geoms(layers.get(key, []))
            if geoms:
                restricted_geoms.extend(geoms)
            constraints.append({"type": key, "count": len(geoms)})

        # additional collision areas from colliding utilities
        utility_collision = []
        for key in [
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
        ]:
            for ft in layers.get(key, []):
                props = (ft or {}).get("properties") or {}
                if props.get("isCollision") or props.get("plotRelation") == "collision":
                    geom = self._feature_geom(ft)
                    if geom is not None:
                        utility_collision.append(geom)
        if utility_collision:
            constraints.append({"type": "utility_collision", "count": len(utility_collision)})
            restricted_geoms.extend(utility_collision)

        restricted_union = self._union_or_empty(restricted_geoms)
        buildable_geom = make_valid(plot_geom.difference(restricted_union)) if not restricted_union.is_empty else plot_geom
        if buildable_geom.is_empty:
            buildable_geom = GeometryCollection()

        max_envelope = buildable_geom if not buildable_geom.is_empty else plot_geom
        shrink = self._distance_for_geom(self.preferred_shrink_m, plot_geom)
        preferred_zone = make_valid(buildable_geom.buffer(-shrink)) if not buildable_geom.is_empty else GeometryCollection()
        if not preferred_zone.is_empty:
            preferred_zone = make_valid(preferred_zone.intersection(buildable_geom))
        elif not max_envelope.is_empty:
            preferred_zone = max_envelope

        buildable_area = float(buildable_geom.area) if not buildable_geom.is_empty else 0.0
        observations = ["Wynik ma charakter referencyjny i projektowy, nie formalno-prawny."]
        warnings = []
        notes = ["Analiza bazuje na geometrii dostępnych warstw i heurystykach przestrzennych."]
        if buildable_area <= 0:
            warnings.append("Nie wykryto dodatniego obszaru możliwej zabudowy.")
            notes.append("Zwrócono obwiednię fallback równą granicy działki.")

        candidates = []
        if not preferred_zone.is_empty:
            candidates.append({
                "name": "preferred",
                "geometry": mapping(preferred_zone),
                "score": 0.9,
                "reason": "Strefa preferowana po odsunięciu od ograniczeń i kolizji.",
            })
        elif not max_envelope.is_empty:
            candidates.append({
                "name": "fallback",
                "geometry": mapping(max_envelope),
                "score": 0.6,
                "reason": "Brak preferowanej strefy, użyto maksymalnej obwiedni.",
            })

        return SiteBuildabilityAnalysisResult(
            buildable_area_geometry=None if buildable_geom.is_empty else mapping(buildable_geom),
            max_building_envelope_geometry=None if max_envelope.is_empty else mapping(max_envelope),
            preferred_building_zone_geometry=None if preferred_zone.is_empty else mapping(preferred_zone),
            building_candidates=candidates,
            constraints=constraints,
            observations=observations,
            warnings=warnings,
            notes=notes,
        )

    def _distance_for_geom(self, distance: float, reference_geom: Any) -> float:
        try:
            minx, miny, maxx, maxy = reference_geom.bounds
            span = min(abs(maxx - minx), abs(maxy - miny))
            if span <= 0:
                return max(distance, 0.0)
            if span < 1.0:
                return min(max(distance, 0.0), span * 0.2)
            return max(distance, 0.0)
        except Exception:
            return max(distance, 0.0)

    def _feature_geom(self, feature: dict[str, Any]) -> Any | None:
        geometry = (feature or {}).get("geometry")
        if not isinstance(geometry, dict):
            return None
        try:
            return make_valid(shape(geometry))
        except Exception:
            return None

    def _layer_geoms(self, features: list[dict[str, Any]]) -> list[Any]:
        out = []
        for ft in features or []:
            geom = self._feature_geom(ft)
            if geom is not None and not geom.is_empty:
                out.append(geom)
        return out

    def _union_or_empty(self, geoms: list[Any]) -> Any:
        if not geoms:
            return GeometryCollection()
        union = geoms[0]
        for geom in geoms[1:]:
            union = make_valid(union.union(geom))
        return union
