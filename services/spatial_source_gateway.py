from __future__ import annotations

from typing import Any

from services.map_service import ParcelProvider, ProviderMeta, normalizeParcelInput


class SpatialSourceGateway:
    """Single integration layer for external spatial sources (WFS/official providers)."""

    def __init__(self, config: dict[str, Any]):
        self.config = config or {}

    def fetch_parcel_candidates(self, *, nr_dzialki: str, obreb: str, miejscowosc: str) -> tuple[list[dict[str, Any]], ProviderMeta, dict[str, Any]]:
        normalized = normalizeParcelInput(nr_dzialki or "", obreb or "", miejscowosc or "")
        parcel_provider = ParcelProvider(self.config.get("parcels", {}))
        candidates, meta = parcel_provider.resolve_candidates(normalized)
        return candidates, meta, normalized
