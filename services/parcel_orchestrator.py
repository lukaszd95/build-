from __future__ import annotations

import time
import uuid
from typing import Any

from services.network_core import CircuitBreakerRegistry, ConnectionProfileResolver, PreflightRunner, RetryExecutor
from services.parcel_domain import ParcelQuery, ParcelResult
from services.parcel_providers import KIEGProvider, MonitoringProvider, PowiatWFSProvider, ULDKProvider


class ResolveParcelUseCase:
    def __init__(self, *, uldk: ULDKProvider, wfs: PowiatWFSProvider, kieg: KIEGProvider, monitoring: MonitoringProvider, wfs_expert_fallback_enabled: bool = False):
        self.uldk = uldk
        self.wfs = wfs
        self.kieg = kieg
        self.monitoring = monitoring
        self.wfs_expert_fallback_enabled = wfs_expert_fallback_enabled
        self.profile_resolver = ConnectionProfileResolver()
        self.preflight = PreflightRunner()
        self.retry = RetryExecutor(retries=(0.0, 0.2, 0.5))
        self.breaker = CircuitBreakerRegistry(threshold=5)
        self.cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _cache_key(self, query: ParcelQuery) -> str:
        return f"{query.parcel_id}|{query.parcel_number}|{query.precinct}|{query.cadastral_unit}"

    def _cache_get(self, key: str, ttl_s: int = 3600) -> dict[str, Any] | None:
        hit = self.cache.get(key)
        if not hit:
            return None
        ts, payload = hit
        if time.time() - ts > ttl_s:
            return None
        return payload

    def _cache_set(self, key: str, payload: dict[str, Any]) -> None:
        self.cache[key] = (time.time(), payload)

    def execute(self, query: ParcelQuery, *, route_mode: str = "AUTO", correlation_id: str = "") -> ParcelResult:
        request_id = correlation_id or str(uuid.uuid4())
        key = self._cache_key(query)
        cached = self._cache_get(key)
        if cached:
            return ParcelResult(
                request_id=request_id,
                status="SUCCESS_PARTIAL",
                canonical_parcel_id=cached.get("canonical_parcel_id", ""),
                input={"type": "cache", "raw": query.parcel_id or query.parcel_number},
                geometry=cached.get("geometry"),
                source={"primary_provider": "CACHE", "fallback_used": False, "route_mode": route_mode},
                quality_flags=["STALE_CACHE"],
                diagnostics={"network_route": route_mode, "attempts": 0, "latency_ms": 0},
            )

        profile = self.profile_resolver.resolve(route_mode)
        _ = self.preflight.run("ULDK", profile)

        if not self.breaker.allow("ULDK"):
            return ParcelResult(
                request_id=request_id,
                status="INFRA_ERROR",
                input={"type": "parcel_id" if query.parcel_id else "parcel_number", "raw": query.parcel_id or query.parcel_number},
                quality_flags=["CIRCUIT_OPEN"],
                diagnostics={"network_route": profile.mode, "attempts": 0, "latency_ms": 0},
            )

        attempts = 0
        started = time.time()

        def call_uldk():
            return self.uldk.resolve(query, route_mode=profile.mode)

        try:
            uldk_result, attempts = self.retry.execute(call_uldk)
            self.monitoring.record("ULDK", uldk_result.ok, uldk_result.diagnostics.error_code)
            if uldk_result.ok:
                self.breaker.record_success("ULDK")
                geometry = uldk_result.geometry
                quality_flags = list(uldk_result.quality_flags)

                # enrichment WFS tylko w trybie eksperckim (np. dodatkowe atrybuty/walidacja).
                if (not geometry or not geometry.data) and self.wfs_expert_fallback_enabled:
                    try:
                        wfs_result = self.wfs.resolve(query, route_mode=profile.mode)
                        self.monitoring.record("WFS", wfs_result.ok, wfs_result.diagnostics.error_code)
                        if wfs_result.ok and wfs_result.geometry:
                            geometry = wfs_result.geometry
                            quality_flags.append("FALLBACK_USED")
                    except Exception:
                        quality_flags.append("ATTRIBUTES_PARTIAL")

                status = "SUCCESS_PARTIAL" if quality_flags else "SUCCESS"
                result = ParcelResult(
                    request_id=request_id,
                    status=status,
                    canonical_parcel_id=uldk_result.canonical_parcel_id,
                    input={"type": "parcel_id" if query.parcel_id else "parcel_number", "raw": query.parcel_id or query.parcel_number},
                    geometry=geometry,
                    source={"primary_provider": "ULDK", "fallback_used": "FALLBACK_USED" in quality_flags, "route_mode": profile.mode},
                    quality_flags=quality_flags,
                    diagnostics={"network_route": profile.mode, "attempts": attempts, "latency_ms": int((time.time() - started) * 1000)},
                )
                self._cache_set(key, {"canonical_parcel_id": result.canonical_parcel_id, "geometry": result.geometry})
                return result

            if uldk_result.status == "PARCEL_NOT_FOUND":
                return ParcelResult(
                    request_id=request_id,
                    status="NOT_FOUND",
                    input={"type": "parcel_id" if query.parcel_id else "parcel_number", "raw": query.parcel_id or query.parcel_number},
                    diagnostics={"network_route": profile.mode, "attempts": attempts, "latency_ms": int((time.time() - started) * 1000)},
                )
        except Exception as exc:
            self.breaker.record_failure("ULDK")
            self.monitoring.record("ULDK", False, "UPSTREAM_UNAVAILABLE")
            # fallback do WFS tylko w trybie eksperckim
            if self.wfs_expert_fallback_enabled:
                try:
                    wfs_result = self.wfs.resolve(query, route_mode="direct_fallback" if profile.proxy_enabled else profile.mode)
                    self.monitoring.record("WFS", wfs_result.ok, wfs_result.diagnostics.error_code)
                    if wfs_result.ok:
                        result = ParcelResult(
                            request_id=request_id,
                            status="SUCCESS_PARTIAL",
                            canonical_parcel_id=wfs_result.canonical_parcel_id,
                            input={"type": "parcel_id" if query.parcel_id else "parcel_number", "raw": query.parcel_id or query.parcel_number},
                            geometry=wfs_result.geometry,
                            source={"primary_provider": "ULDK", "fallback_used": True, "route_mode": "direct_fallback" if profile.proxy_enabled else profile.mode},
                            quality_flags=["FALLBACK_USED"],
                            diagnostics={"network_route": "direct_fallback" if profile.proxy_enabled else profile.mode, "attempts": attempts or 1, "latency_ms": int((time.time() - started) * 1000), "error": str(exc)},
                        )
                        self._cache_set(key, {"canonical_parcel_id": result.canonical_parcel_id, "geometry": result.geometry})
                        return result
                except Exception:
                    pass

            cached = self._cache_get(key, ttl_s=86400)
            if cached:
                return ParcelResult(
                    request_id=request_id,
                    status="SUCCESS_PARTIAL",
                    canonical_parcel_id=cached.get("canonical_parcel_id", ""),
                    input={"type": "cache", "raw": query.parcel_id or query.parcel_number},
                    geometry=cached.get("geometry"),
                    source={"primary_provider": "CACHE", "fallback_used": self.wfs_expert_fallback_enabled, "route_mode": profile.mode},
                    quality_flags=["STALE_CACHE_RETURNED"] + (["FALLBACK_USED"] if self.wfs_expert_fallback_enabled else []),
                    diagnostics={"network_route": profile.mode, "attempts": attempts or 1, "latency_ms": int((time.time() - started) * 1000), "error": str(exc)},
                )

            return ParcelResult(
                request_id=request_id,
                status="INFRA_ERROR",
                input={"type": "parcel_id" if query.parcel_id else "parcel_number", "raw": query.parcel_id or query.parcel_number},
                source={"primary_provider": "ULDK", "fallback_used": self.wfs_expert_fallback_enabled, "route_mode": profile.mode},
                quality_flags=["UPSTREAM_UNAVAILABLE"],
                diagnostics={"network_route": profile.mode, "attempts": attempts or 1, "latency_ms": int((time.time() - started) * 1000), "error": str(exc)},
            )

        return ParcelResult(
            request_id=request_id,
            status="INVALID_INPUT",
            input={"type": "unknown", "raw": ""},
            diagnostics={"network_route": profile.mode, "attempts": attempts, "latency_ms": int((time.time() - started) * 1000)},
        )
