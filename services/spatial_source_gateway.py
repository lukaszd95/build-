from __future__ import annotations

import logging
from typing import Any

from services.map_service import ParcelProvider, ProviderMeta, normalizeParcelInput
from services.parcel_domain import ParcelQuery
from services.parcel_providers import PowiatWFSProvider, ULDKProvider

logger = logging.getLogger(__name__)


class SpatialSourceGateway:
    """Single integration layer for parcel lookup (ULDK primary; WFS expert fallback only)."""

    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        parcels_cfg = self.config.get("parcels") or {}
        providers_cfg = self.config.get("providers") or {}
        uldk_cfg = dict(providers_cfg.get("uldk") or {})
        self.uldk = ULDKProvider(uldk_cfg)
        self.wfs = PowiatWFSProvider({"provider": "wfs", "wfs": parcels_cfg.get("wfs") or {}})
        self.wfs_expert_fallback = bool((providers_cfg.get("wfs") or {}).get("expert_fallback_enabled", False))

    def fetch_parcel_candidates(self, *, nr_dzialki: str, obreb: str, miejscowosc: str) -> tuple[list[dict[str, Any]], ProviderMeta, dict[str, Any]]:
        normalized = normalizeParcelInput(nr_dzialki or "", obreb or "", miejscowosc or "")
        if str((self.config.get("parcels") or {}).get("provider") or "").lower() == "stub":
            parcel_provider = ParcelProvider(self.config.get("parcels", {}))
            candidates, meta = parcel_provider.resolve_candidates(normalized)
            return candidates, meta, normalized

        query = ParcelQuery(
            parcel_id=nr_dzialki.strip() if self._looks_like_parcel_id(nr_dzialki) else "",
            parcel_number="" if self._looks_like_parcel_id(nr_dzialki) else nr_dzialki.strip(),
            precinct=obreb.strip(),
            cadastral_unit=miejscowosc.strip(),
        )

        uldk_result = self.uldk.resolve(query, route_mode="AUTO")
        if uldk_result.ok:
            candidate = {
                "id": uldk_result.canonical_parcel_id,
                "parcelNumber": normalized.get("nrCanonical") or nr_dzialki,
                "obreb": normalized.get("obrebCanonical") or obreb,
                "miejscowosc": miejscowosc,
                "geometry": (uldk_result.geometry.data if uldk_result.geometry else {}) or {},
            }
            meta = ProviderMeta(
                sourceName="ULDK",
                dataType="vector",
                licenseNote="Dane referencyjne ULDK (GUGiK).",
                accuracyNote="Geometria działki pobrana z ULDK i przekonwertowana do GeoJSON po stronie backendu.",
                warnings=[],
            )
            self._log_runtime(provider="ULDK", query=query, fallback_used=False, wfs_called=False)
            return [candidate], meta, normalized

        if uldk_result.status == "PARCEL_NOT_FOUND":
            meta = ProviderMeta(
                sourceName="ULDK",
                dataType="vector",
                licenseNote="Dane referencyjne ULDK (GUGiK).",
                accuracyNote="Brak geometrii dla podanego zapytania.",
                warnings=["Nie znaleziono działki w ULDK."],
            )
            self._log_runtime(provider="ULDK", query=query, fallback_used=False, wfs_called=False)
            return [], meta, normalized

        if not self.wfs_expert_fallback:
            meta = ProviderMeta(
                sourceName="ULDK",
                dataType="vector",
                licenseNote="Dane referencyjne ULDK (GUGiK).",
                accuracyNote="ULDK tymczasowo niedostępne.",
                warnings=["Tryb domyślny: bez fallback WFS dla wyszukiwania geometrii działki."],
            )
            self._log_runtime(provider="ULDK", query=query, fallback_used=False, wfs_called=False)
            return [], meta, normalized

        wfs_result = self.wfs.resolve(query, route_mode="AUTO")
        if not wfs_result.ok:
            self._log_runtime(provider="WFS", query=query, fallback_used=True, wfs_called=True)
            return [], ProviderMeta(sourceName="WFS", dataType="vector", licenseNote="Dane WFS Geoportalu.", accuracyNote="Fallback ekspercki po błędzie ULDK.", warnings=["Brak wyników z eksperckiego fallback WFS."]), normalized

        candidate = {
            "id": wfs_result.canonical_parcel_id,
            "parcelNumber": normalized.get("nrCanonical") or nr_dzialki,
            "obreb": normalized.get("obrebCanonical") or obreb,
            "miejscowosc": miejscowosc,
            "geometry": (wfs_result.geometry.data if wfs_result.geometry else {}) or {},
        }
        meta = ProviderMeta(
            sourceName="WFS",
            dataType="vector",
            licenseNote="Dane WFS Geoportalu.",
            accuracyNote="Fallback ekspercki po błędzie ULDK.",
            warnings=["ULDK niedostępne — użyto fallback WFS w trybie eksperckim."],
        )
        self._log_runtime(provider="WFS", query=query, fallback_used=True, wfs_called=True)
        return [candidate], meta, normalized

    def _log_runtime(self, *, provider: str, query: ParcelQuery, fallback_used: bool, wfs_called: bool) -> None:
        uldk_request = "GetParcelById" if query.parcel_id else "GetParcelByIdOrNr"
        logger.info(
            "parcel.search.runtime provider=%s uldk_request=%s requested_result_fields=%s requested_srid=%s fallback_used=%s wfs_called=%s",
            provider,
            uldk_request,
            "id,geom_wkb,geom_wkt",
            self.uldk.source_srid,
            fallback_used,
            wfs_called,
        )

    @staticmethod
    def _looks_like_parcel_id(value: str) -> bool:
        candidate = (value or "").strip()
        return bool(candidate and "_" in candidate and "." in candidate)
