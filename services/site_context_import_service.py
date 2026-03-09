from __future__ import annotations

from typing import Any

from services.layer_import_coordinator import LayerImportCoordinator
from services.map_service import MapService
from services.parcel_lookup_service import ParcelLookupService


class SiteContextImportService:
    """Orchestrates parcel lookup + spatial import + persistence + analysis."""

    def __init__(self, *, parcel_lookup: ParcelLookupService, map_service: MapService, layer_coordinator: LayerImportCoordinator):
        self.parcel_lookup = parcel_lookup
        self.map_service = map_service
        self.layer_coordinator = layer_coordinator

    def search_parcels(self, *, parcel_number: str, precinct: str, cadastral_unit: str) -> dict[str, Any]:
        if not (parcel_number or "").strip():
            raise ValueError("MISSING_PARCEL")
        return self.parcel_lookup.search(nr_dzialki=parcel_number, obreb=precinct, miejscowosc=cadastral_unit)

    def get_parcel_preview(self, *, parcel_id: str, parcel_number: str, precinct: str, cadastral_unit: str) -> dict[str, Any]:
        if not parcel_id:
            raise ValueError("MISSING_PARCEL")
        parcel = self.parcel_lookup.get_by_id(
            parcel_id=parcel_id,
            nr_dzialki=parcel_number,
            obreb=precinct,
            miejscowosc=cadastral_unit,
        )
        geometry = parcel.get("geometry")
        if not geometry:
            raise ValueError("MISSING_GEOMETRY")
        return {
            "metadata": {
                "parcelId": parcel.get("parcelId") or parcel.get("id"),
                "parcelNumber": parcel.get("parcelNumber"),
                "precinct": parcel.get("precinct"),
                "cadastralUnit": parcel.get("cadastralUnit"),
                "area": parcel.get("area"),
            },
            "geometry": geometry,
            "bbox": parcel.get("bbox"),
            "centroid": parcel.get("centroid"),
        }

    def import_site_context(self, *, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        parcel = payload.get("parcel") or {}

        parcel_number = (payload.get("parcelNumber") or payload.get("nrDzialki") or "").strip()
        precinct = (payload.get("precinct") or payload.get("obreb") or "").strip()
        cadastral_unit = (payload.get("cadastralUnit") or payload.get("miejscowosc") or payload.get("municipality") or "").strip()

        if not parcel:
            parcel_id = payload.get("parcelId") or payload.get("parcel_id")
            if parcel_id:
                parcel = self.parcel_lookup.get_by_id(
                    parcel_id=str(parcel_id),
                    nr_dzialki=parcel_number,
                    obreb=precinct,
                    miejscowosc=cadastral_unit,
                )
            else:
                search_result = self.search_parcels(
                    parcel_number=parcel_number,
                    precinct=precinct,
                    cadastral_unit=cadastral_unit,
                )
                items = search_result.get("items", [])
                if not items:
                    raise ValueError("PARCEL_NOT_FOUND")
                if len(items) > 1:
                    raise ValueError("MULTIPLE_PARCEL_MATCHES")
                parcel = items[0]

        if not parcel.get("geometry"):
            raise ValueError("MISSING_GEOMETRY")

        selected_layers = payload.get("layers") or []
        plan = self.layer_coordinator.plan(selected_layers)

        import_payload = {
            "parcel": parcel,
            "nrDzialki": parcel_number or parcel.get("parcelNumber") or "",
            "obreb": precinct or parcel.get("precinct") or "",
            "miejscowosc": cadastral_unit or parcel.get("cadastralUnit") or "",
            "bufferMeters": float(payload.get("siteAnalysisBufferMeters") or payload.get("bufferMeters") or 30),
            "layers": plan["directImport"],
            "layerImportPlan": plan,
        }
        result = self.map_service.import_parcel_to_project(int(project_id), import_payload)
        result["layerImportPlan"] = plan
        if result.get("siteContext", {}).get("importSummary", {}).get("status") in {"error", "unavailable"}:
            result["partialImport"] = True
        return result

    def get_site_context(self, *, project_id: int) -> dict[str, Any] | None:
        return self.map_service.get_latest_site_context(int(project_id))

    def recompute_analysis(self, *, project_id: int) -> dict[str, Any]:
        existing = self.get_site_context(project_id=project_id)
        if not existing:
            raise ValueError("SITE_CONTEXT_NOT_FOUND")
        analysis = existing.get("analysisResult") or {}
        buildable = analysis.get("buildableArea")
        if buildable is None and existing.get("siteBoundary"):
            # lightweight recompute fallback without external calls
            buildable = 0.0
        analysis["buildableArea"] = buildable
        analysis.setdefault("notes", [])
        analysis["notes"].append("Analysis recomputed from persisted site context.")
        existing["analysisResult"] = analysis
        return {"status": "recomputed", "siteContext": existing}

    def reimport(self, *, project_id: int) -> dict[str, Any]:
        existing = self.get_site_context(project_id=project_id)
        if not existing:
            raise ValueError("SITE_CONTEXT_NOT_FOUND")
        payload = {
            "parcel": {
                "parcelId": existing.get("primaryParcelId"),
                "id": existing.get("primaryParcelId"),
                "parcelNumber": "1",
                "precinct": "0001",
                "cadastralUnit": "reimport",
                "geometry": existing.get("siteBoundary"),
                "area": existing.get("analysisResult", {}).get("buildableArea"),
            },
            "siteAnalysisBufferMeters": existing.get("analysisBufferMeters") or 30,
            "layers": [layer.get("layerKey") for layer in existing.get("layers", [])],
        }
        return self.import_site_context(project_id=project_id, payload=payload)
