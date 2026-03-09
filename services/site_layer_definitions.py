from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SiteLayerKey = Literal[
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
]


@dataclass(frozen=True)
class SiteLayerDefinition:
    layerKey: SiteLayerKey
    label: str
    group: str
    defaultVisibility: bool
    defaultLocked: bool
    sourcePreference: str
    geometryType: str
    canBeDerived: bool
    sortOrder: int


_SITE_LAYER_ROWS: list[tuple[SiteLayerKey, str, str, bool, bool, str, str, bool]] = [
    ("plot_boundary", "Granica działki", "Granice i obszary bazowe", True, True, "parcel_provider", "Polygon", False),
    ("land_use_boundary", "Granica przeznaczenia terenu", "Granice i obszary bazowe", True, True, "planning_docs", "Polygon", False),
    ("site_boundary", "Obszar opracowania", "Granice i obszary bazowe", True, True, "derived", "Polygon", True),
    ("building_setback_line", "Linia odsunięcia zabudowy", "Ograniczenia zabudowy", True, True, "planning_docs", "LineString", False),
    ("mandatory_building_line", "Obowiązująca linia zabudowy", "Ograniczenia zabudowy", True, True, "planning_docs", "LineString", False),
    ("offset_from_boundary_zone", "Strefa odsunięcia od granicy", "Ograniczenia zabudowy", True, True, "derived", "Polygon", True),
    ("no_build_zone", "Strefa zakazu zabudowy", "Ograniczenia zabudowy", True, True, "planning_docs", "Polygon", False),
    ("limited_build_zone", "Strefa ograniczonej zabudowy", "Ograniczenia zabudowy", True, True, "planning_docs", "Polygon", False),
    ("road_edge", "Krawędź drogi", "Drogi i dostęp", True, True, "reference", "LineString", False),
    ("road_centerline", "Oś drogi", "Drogi i dostęp", True, True, "reference", "LineString", False),
    ("road_right_of_way", "Pas drogowy", "Drogi i dostęp", True, True, "reference", "Polygon", False),
    ("access_point", "Punkt dostępu", "Drogi i dostęp", True, True, "derived", "Point", True),
    ("driveway", "Dojazd", "Drogi i dostęp", True, True, "derived", "LineString", True),
    ("fire_access_route", "Droga pożarowa", "Drogi i dostęp", True, True, "derived", "LineString", True),
    ("parking_zone", "Strefa parkingowa", "Drogi i dostęp", True, True, "derived", "Polygon", True),
    ("elevation_point", "Punkt wysokościowy", "Teren i wysokości", True, True, "reference", "Point", False),
    ("contour_line", "Warstwica", "Teren i wysokości", True, True, "reference", "LineString", False),
    ("terrain_break_line", "Linia załamania terenu", "Teren i wysokości", True, True, "reference", "LineString", False),
    ("slope_zone", "Strefa spadku", "Teren i wysokości", True, True, "derived", "Polygon", True),
    ("embankment", "Nasyp", "Teren i wysokości", True, True, "reference", "LineString", False),
    ("cut_slope", "Wykop / skarpa", "Teren i wysokości", True, True, "reference", "LineString", False),
    ("retaining_wall", "Mur oporowy", "Teren i wysokości", True, True, "reference", "LineString", False),
    ("existing_building", "Istniejący budynek", "Istniejące obiekty", True, True, "reference", "Polygon", False),
    ("adjacent_building", "Budynek sąsiedni", "Istniejące obiekty", True, True, "reference", "Polygon", False),
    ("outbuilding", "Budynek pomocniczy", "Istniejące obiekty", True, True, "reference", "Polygon", False),
    ("canopy_structure", "Wiata", "Istniejące obiekty", True, True, "reference", "Polygon", False),
    ("fence_line", "Ogrodzenie", "Istniejące obiekty", True, True, "reference", "LineString", False),
    ("gate", "Brama", "Istniejące obiekty", True, True, "reference", "Point", False),
    ("water_pipe", "Sieć wodociągowa", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("sanitary_sewer", "Kanalizacja sanitarna", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("storm_sewer", "Kanalizacja deszczowa", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("gas_pipe", "Gazociąg", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("power_line_underground", "Kabel energetyczny podziemny", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("power_line_overhead", "Linia energetyczna napowietrzna", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("telecom_line", "Sieć teletechniczna", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("utility_connection", "Przyłącze", "Sieci uzbrojenia", True, True, "reference", "LineString", False),
    ("utility_node", "Obiekt punktowy sieci", "Sieci uzbrojenia", True, True, "reference", "Point", False),
    ("transformer_station", "Stacja transformatorowa", "Sieci uzbrojenia", True, True, "reference", "Polygon", False),
    ("utility_protection_zone", "Strefa ochronna sieci", "Sieci uzbrojenia", True, True, "derived", "Polygon", True),
    ("watercourse", "Ciek wodny", "Woda i odwodnienie", True, True, "reference", "LineString", False),
    ("drainage_ditch", "Rów odwadniający", "Woda i odwodnienie", True, True, "reference", "LineString", False),
    ("pond", "Zbiornik wodny", "Woda i odwodnienie", True, True, "reference", "Polygon", False),
    ("flood_zone", "Strefa zalewowa", "Woda i odwodnienie", True, True, "reference", "Polygon", False),
    ("soakaway_zone", "Strefa retencji", "Woda i odwodnienie", True, True, "derived", "Polygon", True),
    ("tree", "Drzewo", "Zieleń", True, True, "reference", "Point", False),
    ("tree_canopy", "Korona drzewa", "Zieleń", True, True, "reference", "Polygon", False),
    ("root_protection_zone", "Strefa ochrony korzeni", "Zieleń", True, True, "derived", "Polygon", True),
    ("shrub_area", "Krzewy", "Zieleń", True, True, "reference", "Polygon", False),
    ("protected_tree", "Drzewo chronione", "Zieleń", True, True, "reference", "Point", False),
    ("biologically_active_area", "Powierzchnia biologicznie czynna", "Zieleń", True, True, "derived", "Polygon", True),
    ("forest_boundary", "Granica lasu", "Zieleń", True, True, "reference", "LineString", False),
    ("conservation_zone", "Strefa ochrony konserwatorskiej", "Strefy ochronne", True, True, "reference", "Polygon", False),
    ("environmental_protection_zone", "Strefa ochrony środowiskowej", "Strefy ochronne", True, True, "reference", "Polygon", False),
    ("noise_impact_zone", "Strefa hałasu", "Strefy ochronne", True, True, "derived", "Polygon", True),
    ("height_limit_zone", "Strefa ograniczenia wysokości", "Strefy ochronne", True, True, "planning_docs", "Polygon", False),
    ("special_restriction_zone", "Strefa szczególnych ograniczeń", "Strefy ochronne", True, True, "planning_docs", "Polygon", False),
    ("buildable_area", "Obszar możliwej zabudowy", "Wynik analizy", True, True, "analysis", "Polygon", True),
    ("max_building_envelope", "Maksymalna obwiednia zabudowy", "Wynik analizy", True, True, "analysis", "Polygon", True),
    ("preferred_building_zone", "Preferowana strefa zabudowy", "Wynik analizy", True, True, "analysis", "Polygon", True),
    ("building_candidate", "Kandydat zabudowy", "Wynik analizy", True, True, "analysis", "Polygon", True),
]

SITE_LAYER_DEFINITIONS: dict[SiteLayerKey, SiteLayerDefinition] = {
    row[0]: SiteLayerDefinition(
        layerKey=row[0],
        label=row[1],
        group=row[2],
        defaultVisibility=row[3],
        defaultLocked=row[4],
        sourcePreference=row[5],
        geometryType=row[6],
        canBeDerived=row[7],
        sortOrder=index,
    )
    for index, row in enumerate(_SITE_LAYER_ROWS)
}

ALL_SITE_LAYER_KEYS: list[SiteLayerKey] = [row[0] for row in _SITE_LAYER_ROWS]
