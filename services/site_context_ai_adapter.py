from __future__ import annotations

from typing import Any

from services.site_layer_definitions import SITE_LAYER_DEFINITIONS


def buildSiteContextForAI(site_context: dict[str, Any]) -> dict[str, Any]:
    layers = site_context.get("layers") or []
    objects = site_context.get("objects") or []
    analysis = site_context.get("analysisResult") or {}

    layers_with_data = []
    for layer in layers:
        features = layer.get("features") or []
        if not features:
            continue
        definition = SITE_LAYER_DEFINITIONS.get(layer.get("layerKey"))
        layers_with_data.append(
            {
                "layerKey": layer.get("layerKey"),
                "label": layer.get("label") or (definition.label if definition else layer.get("layerKey")),
                "group": (definition.group if definition else None) or layer.get("metadata", {}).get("group"),
                "status": layer.get("status"),
                "sourceType": layer.get("sourceType"),
                "featureCount": len(features),
                "geometryType": layer.get("geometryType"),
                "semanticTags": {
                    "isDerived": layer.get("status") in {"derived", "loaded"} and str(layer.get("sourceType")) in {"derived", "analysis"},
                    "isPlaceholder": layer.get("status") == "manual_placeholder",
                },
                "features": [
                    {
                        "geometry": ft.get("geometry"),
                        "properties": ft.get("properties") or {},
                    }
                    for ft in features
                ],
            }
        )

    important_objects = []
    for obj in objects:
        if not (
            obj.get("withinPlot")
            or obj.get("intersectsPlot")
            or obj.get("sourceMetadata", {}).get("collision")
            or obj.get("layerKey") in {"adjacent_building", "no_build_zone", "flood_zone", "utility_protection_zone", "limited_build_zone"}
        ):
            continue
        important_objects.append(
            {
                "id": obj.get("id"),
                "layerKey": obj.get("layerKey"),
                "objectType": obj.get("objectType"),
                "geometry": obj.get("geometry"),
                "properties": obj.get("properties") or {},
                "relations": {
                    "withinPlot": obj.get("withinPlot"),
                    "withinSiteBoundary": obj.get("withinSiteBoundary"),
                    "intersectsPlot": obj.get("intersectsPlot"),
                    "collision": obj.get("sourceMetadata", {}).get("collision", False),
                    "plotRelation": obj.get("sourceMetadata", {}).get("plotRelation"),
                },
            }
        )

    return {
        "projectId": site_context.get("projectId"),
        "siteContextId": site_context.get("id"),
        "parcel": {
            "primaryParcelId": site_context.get("primaryParcelId"),
            "geometry": next((layer.get("features", [{}])[0].get("geometry") for layer in layers if layer.get("layerKey") == "plot_boundary" and layer.get("features")), None),
        },
        "siteBoundary": site_context.get("siteBoundary"),
        "analysisBufferMeters": site_context.get("analysisBufferMeters"),
        "layers": layers_with_data,
        "analysisLayers": [
            layer for layer in layers_with_data if layer.get("layerKey") in {"buildable_area", "max_building_envelope", "preferred_building_zone", "building_candidate"}
        ],
        "constraints": analysis.get("constraints") or [],
        "observations": analysis.get("observations") or [],
        "warnings": analysis.get("warnings") or [],
        "importantObjects": important_objects,
        "analysisSummary": {
            "buildableArea": analysis.get("buildableArea"),
            "hasBuildableArea": bool((analysis.get("buildableArea") or 0) > 0),
            "candidateCount": len(analysis.get("buildingCandidates") or []),
        },
        "disclaimer": "Dane semantyczne do wsparcia projektowania AI; wynik nie stanowi formalnej interpretacji prawnej.",
    }
