from __future__ import annotations

from typing import Any

from shapely.geometry import Point, shape
from shapely.validation import make_valid

from services.map_service import normalize_parcel_number
from services.spatial_source_gateway import SpatialSourceGateway


class ParcelLookupService:
    def __init__(self, gateway: SpatialSourceGateway):
        self.gateway = gateway

    def search(self, *, nr_dzialki: str, obreb: str, miejscowosc: str) -> dict[str, Any]:
        try:
            candidates, meta, normalized = self.gateway.fetch_parcel_candidates(
                nr_dzialki=nr_dzialki,
                obreb=obreb,
                miejscowosc=miejscowosc,
            )
        except TimeoutError as exc:
            raise RuntimeError("EXTERNAL_SOURCE_TIMEOUT") from exc
        except Exception as exc:
            if "timeout" in str(exc).lower():
                raise RuntimeError("EXTERNAL_SOURCE_TIMEOUT") from exc
            raise RuntimeError("EXTERNAL_SOURCE_ERROR") from exc
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in candidates:
            score = 0
            if normalize_parcel_number(item.get("parcelNumber", "")) == normalized["nrCanonical"]:
                score += 60
            item_obreb = str(item.get("obreb", "") or "").strip()
            if item_obreb and (item_obreb == normalized["obrebCanonical"] or item_obreb in normalized.get("obrebVariants", [])):
                score += 25
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)

        items = []
        for score, item in scored[:20]:
            geometry = item.get("geometry") or {}
            try:
                geom_obj = make_valid(shape(geometry))
                centroid = geom_obj.centroid
                bbox = list(geom_obj.bounds)
                area = float(geom_obj.area)
            except Exception:
                centroid = Point(0, 0)
                bbox = None
                area = None
            items.append(
                {
                    "id": item.get("id"),
                    "parcelId": item.get("id"),
                    "parcelNumber": item.get("parcelNumber"),
                    "precinct": str(item.get("obreb", "") or ""),
                    "cadastralUnit": item.get("miejscowosc") or "",
                    "geometry": geometry,
                    "centroid": {"type": "Point", "coordinates": [centroid.x, centroid.y]},
                    "bbox": bbox,
                    "area": area,
                    "matchScore": score,
                }
            )

        return {"items": items, "sources": {"parcel": meta.__dict__}, "empty": len(items) == 0}

    def get_by_id(self, *, parcel_id: str, nr_dzialki: str, obreb: str, miejscowosc: str) -> dict[str, Any]:
        result = self.search(nr_dzialki=nr_dzialki, obreb=obreb, miejscowosc=miejscowosc)
        match = next((item for item in result.get("items", []) if str(item.get("id")) == str(parcel_id)), None)
        if not match:
            raise ValueError("PARCEL_NOT_FOUND")
        return match
