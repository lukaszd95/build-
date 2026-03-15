from __future__ import annotations

import os
import time
import urllib.error
from dataclasses import dataclass
from typing import Callable, TypeVar

from services.map_service import classify_wfs_connection_error

T = TypeVar("T")


@dataclass
class ConnectionProfile:
    mode: str
    proxy_enabled: bool


class ConnectionProfileResolver:
    def resolve(self, requested_mode: str = "AUTO") -> ConnectionProfile:
        mode = (requested_mode or "AUTO").upper()
        has_proxy = bool(os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy"))
        if mode == "DIRECT":
            return ConnectionProfile(mode="DIRECT", proxy_enabled=False)
        if mode == "PROXY":
            return ConnectionProfile(mode="PROXY", proxy_enabled=True)
        return ConnectionProfile(mode="AUTO", proxy_enabled=has_proxy)


class PreflightRunner:
    def run(self, provider_name: str, profile: ConnectionProfile) -> dict[str, str | bool]:
        return {"ok": True, "provider": provider_name, "route": "PROXY" if profile.proxy_enabled else "DIRECT"}


class RetryExecutor:
    def __init__(self, retries: tuple[float, ...] = (0.0, 0.2, 0.5)):
        self.retries = retries

    @staticmethod
    def should_retry(exc: Exception) -> bool:
        if isinstance(exc, ValueError):
            return False
        text = str(exc).upper()
        if "INVALID_INPUT" in text or "PARCEL_NOT_FOUND" in text:
            return False
        code = classify_wfs_connection_error(exc)
        if code in {"PROXY_CONNECT_403"}:
            return False
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in {429, 500, 502, 503, 504}
        return code in {"TCP_TIMEOUT", "NETWORK_UNREACHABLE", "TCP_BLOCKED", "NETWORK_ERROR"}

    def execute(self, fn: Callable[[], T]) -> tuple[T, int]:
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(self.retries, start=1):
            if backoff > 0:
                time.sleep(backoff)
            try:
                return fn(), attempt
            except Exception as exc:
                last_exc = exc
                if attempt >= len(self.retries) or not self.should_retry(exc):
                    raise
        assert last_exc is not None
        raise last_exc


class CircuitBreakerRegistry:
    def __init__(self, threshold: int = 5):
        self.threshold = threshold
        self.failures: dict[str, int] = {}

    def allow(self, key: str) -> bool:
        return self.failures.get(key, 0) < self.threshold

    def record_failure(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1

    def record_success(self, key: str) -> None:
        self.failures[key] = 0
