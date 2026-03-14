import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error
import ssl
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from services.site_context_models import ImportSummary, SiteAnalysisResult, SiteContext, SiteLayer, SiteObject, dataclass_to_dict
from services.site_geometry_service import createSiteBoundaryFromPlot
from services.derived_layer_computation_service import DerivedLayerComputationService
from services.site_buildability_analysis_service import SiteBuildabilityAnalysisService
from services.site_layer_definitions import ALL_SITE_LAYER_KEYS, SITE_LAYER_DEFINITIONS
from services.wfs_response_parser import WfsDiagnostics, WfsServiceError, parse_wfs_payload

from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform as shp_transform
from shapely.validation import make_valid
try:
    from pyproj import Transformer
except Exception:
    Transformer = None


logger = logging.getLogger(__name__)


SEP_RE = re.compile(r"[.\-\\/]+")


def _wfs_timeout_seconds(raw_timeout: Any) -> float:
    try:
        return max(float(raw_timeout), 1.0)
    except (TypeError, ValueError):
        return 15.0


def classify_wfs_connection_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "tunnel connection failed: 403" in text:
        return "PROXY_CONNECT_403"
    if "name or service not known" in text or "temporary failure in name resolution" in text:
        return "DNS_ERROR"
    if isinstance(exc, TimeoutError) or "timed out" in text or "timeout" in text:
        return "TCP_TIMEOUT"
    if isinstance(exc, ssl.SSLError) or "ssl" in text or "certificate" in text or "tls" in text:
        return "TLS_ERROR"
    if "network is unreachable" in text or "no route to host" in text:
        return "NETWORK_UNREACHABLE"
    if "connection refused" in text or "failed to establish a new connection" in text:
        return "TCP_BLOCKED"
    return "NETWORK_ERROR"


def normalize_text_ascii(value: str) -> str:
    source = (value or "").replace("ł", "l").replace("Ł", "L")
    normalized = unicodedata.normalize("NFKD", source)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalizeParcelInput(nr_dzialki: str, obreb: str, miejscowosc: str) -> dict[str, Any]:
    raw = (nr_dzialki or "").strip().replace(" ", "")
    raw = SEP_RE.sub("/", raw)
    if "/" in raw:
        main_raw, sub_raw = raw.split("/", 1)
    else:
        main_raw, sub_raw = raw, "0"
    nr_main = main_raw.strip() or "0"
    nr_sub = sub_raw.strip() or "0"
    nr_canonical = f"{nr_main}/{nr_sub}" if nr_sub != "0" else nr_main

    obreb_raw = (obreb or "").strip()
    obreb_canonical = obreb_raw
    obreb_variants: list[str] = []
    if obreb_raw:
        obreb_variants.append(obreb_raw)
        digits_only = "".join(ch for ch in obreb_raw if ch.isdigit())
        if digits_only:
            obreb_variants.append(digits_only)
            obreb_variants.append(f"{int(digits_only):04d}")
        split_chunks = [part for part in re.split(r"[^0-9A-Za-z]+", obreb_raw) if part]
        if split_chunks:
            last_chunk = split_chunks[-1]
            if last_chunk.isdigit():
                obreb_variants.append(last_chunk)
                obreb_variants.append(f"{int(last_chunk):04d}")

    miejsc = (miejscowosc or "").strip()
    miejsc_lower = miejsc.lower()
    miejsc_ascii = normalize_text_ascii(miejsc_lower)
    variants = [v for v in [miejsc, miejsc_lower, miejsc_ascii] if v]
    return {
        "nrMain": nr_main,
        "nrSub": nr_sub,
        "nrCanonical": nr_canonical,
        "obrebCanonical": obreb_canonical,
        "obrebVariants": list(dict.fromkeys(v for v in obreb_variants if v)),
        "miejscowoscVariants": list(dict.fromkeys(variants)),
    }


def normalize_parcel_number(candidate: str) -> str:
    text = SEP_RE.sub("/", (candidate or "").strip().replace(" ", ""))
    if not text:
        return ""
    if "/" in text:
        a, b = text.split("/", 1)
        return f"{a or '0'}/{b or '0'}"
    return text or "0"


@dataclass
class ProviderMeta:
    sourceName: str
    dataType: str
    licenseNote: str
    accuracyNote: str
    warnings: list[str]
    requestUrl: str = ""
    statusCode: int | None = None
    contentType: str = ""
    detectedFormat: str = "unknown"
    parserUsed: str = "none"
    errorType: str = ""
    errorMessage: str = ""


class ParcelProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def resolve_candidates(self, normalized: dict[str, Any]) -> tuple[list[dict[str, Any]], ProviderMeta]:
        provider = self.config.get("provider", "wfs")
        if provider == "stub":
            return self._resolve_stub(normalized)
        if provider != "wfs":
            raise RuntimeError(f"Unsupported parcel provider: {provider}")
        wfs = self.config.get("wfs", {})
        features, diag = self._fetch_wfs_features(wfs, normalized)
        candidates = [self._map_feature(ft, wfs.get("mapping", {}), normalized) for ft in features]
        candidates = [candidate for candidate in candidates if candidate.get("geometry")]
        warnings = []
        if not candidates:
            warnings.append("Brak wyników z WFS dla podanych danych.")
        return candidates, ProviderMeta(
            sourceName=wfs.get("url", "WFS"),
            dataType="vector",
            licenseNote="Źródło zależne od konfiguracji dostawcy.",
            accuracyNote="Dokładność zależna od ewidencji źródłowej.",
            warnings=warnings,
            requestUrl=diag.request_url,
            statusCode=diag.status_code,
            contentType=diag.content_type,
            detectedFormat=diag.detected_format,
            parserUsed=diag.parser_used,
            errorType=diag.error_type,
            errorMessage=diag.error_message,
        )

    def _resolve_stub(self, normalized: dict[str, Any]) -> tuple[list[dict[str, Any]], ProviderMeta]:
        parcel_number = normalized.get("nrCanonical") or "1"
        obreb = normalized.get("obrebCanonical") or "0001"
        miejscowosc = (normalized.get("miejscowoscVariants") or ["Warszawa"])[0]

        # Deterministyczna geometrią testowa w EPSG:4326 (mały prostokąt).
        base_lon, base_lat = 21.0122, 52.2297
        delta = 0.0005
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [base_lon - delta, base_lat - delta],
                [base_lon + delta, base_lat - delta],
                [base_lon + delta, base_lat + delta],
                [base_lon - delta, base_lat + delta],
                [base_lon - delta, base_lat - delta],
            ]],
        }
        candidate = {
            "id": f"stub-{parcel_number}-{obreb}",
            "parcelNumber": parcel_number,
            "obreb": obreb,
            "miejscowosc": miejscowosc,
            "geometry": geometry,
        }
        return [candidate], ProviderMeta(
            sourceName="stub",
            dataType="vector",
            licenseNote="Dane testowe (stub).",
            accuracyNote="Geometria syntetyczna do testów.",
            warnings=["Użyto dostawcy stub (tryb testowy)."],
        )

    def _fetch_wfs_features(self, wfs: dict[str, Any], normalized: dict[str, Any]) -> tuple[list[dict[str, Any]], WfsDiagnostics]:
        url = wfs.get("url")
        if not url:
            raise RuntimeError("Brak konfiguracji WFS (url).")
        configured_type_name = wfs.get("typeName")
        if not configured_type_name:
            raise RuntimeError("Brak konfiguracji WFS (typeName).")
        timeout = _wfs_timeout_seconds(wfs.get("timeout", 15))
        type_names = [configured_type_name]
        discovered = self._discover_feature_type_name(url=url, requested_type_name=configured_type_name, timeout=timeout)
        if discovered and discovered not in type_names:
            type_names.append(discovered)

        cql_filter = self._build_cql_filter(wfs.get("mapping", {}), normalized)
        # Ograniczamy liczbę wariantów, żeby nie przeciążać niestabilnej usługi.
        filters_to_try = [cql_filter, None] if cql_filter else [None]

        output_formats = [
            "application/json",
            "application/geo+json",
        ]
        errors: list[str] = []
        last_diag = WfsDiagnostics(query_params={})
        for type_name in type_names:
            for output_format in output_formats:
                for current_filter in filters_to_try:
                    params = {
                        "service": "WFS",
                        "request": "GetFeature",
                        "outputFormat": output_format,
                    }
                    if wfs.get("version"):
                        params["version"] = wfs["version"]
                    if wfs.get("srsName"):
                        params["srsName"] = wfs["srsName"]
                    if wfs.get("maxFeatures"):
                        params["maxFeatures"] = str(wfs["maxFeatures"])
                    elif current_filter is None:
                        # Bez CQL ograniczamy odpowiedź, aby nie pobierać pełnej warstwy.
                        if str(params.get("version", "")).startswith("2"):
                            params["count"] = str(wfs.get("fallbackCount", 50))
                        else:
                            params["maxFeatures"] = str(wfs.get("fallbackCount", 50))
                    if current_filter:
                        params["CQL_FILTER"] = current_filter

                    type_key = "typeNames" if str(params.get("version", "")).startswith("2") else "typeName"
                    params[type_key] = type_name
                    try:
                        data, diag = self._wfs_request_json(url=url, params=params, timeout=timeout)
                        last_diag = diag
                        features = data.get("features", []) if isinstance(data, dict) else []
                        logger.info(
                            "parcel.search.external.response features=%s typeName=%s outputFormat=%s filter=%s status=%s contentType=%s detected=%s parser=%s",
                            len(features),
                            type_name,
                            output_format,
                            "yes" if current_filter else "no",
                            diag.status_code,
                            diag.content_type,
                            diag.detected_format,
                            diag.parser_used,
                        )
                        return features, diag
                    except Exception as exc:
                        if isinstance(exc, WfsServiceError) and exc.diagnostics:
                            last_diag = exc.diagnostics
                        errors.append(str(exc))
                        logger.warning(
                            "parcel.search.external.retry_failed typeName=%s outputFormat=%s filter=%s error=%s",
                            type_name,
                            output_format,
                            "yes" if current_filter else "no",
                            exc,
                        )
        last_diag.error_type = last_diag.error_type or "request_failed"
        last_diag.error_message = f"Nie udało się pobrać danych WFS: {' | '.join(errors[:3])}"
        raise RuntimeError(last_diag.error_message)

    def _wfs_request_json(self, *, url: str, params: dict[str, Any], timeout: int | float) -> tuple[dict[str, Any], WfsDiagnostics]:
        query = urllib.parse.urlencode(params, doseq=True)
        request_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        logger.info(
            "parcel.search.external.request method=GET url=%s query=%s",
            request_url,
            params,
        )
        diag = WfsDiagnostics(request_url=request_url, method="GET", query_params=params)
        request = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BuildParcelBot/1.0)",
                "Accept": "application/json, application/geo+json, application/gml+xml, text/xml;q=0.9, */*;q=0.8",
            },
        )
        retries = [0.0, 0.2, 0.5]
        for attempt, backoff_s in enumerate(retries, start=1):
            if backoff_s > 0:
                time.sleep(backoff_s)
            try:
                with self._safe_urlopen(request, timeout=timeout) as resp:
                    diag.status_code = resp.status
                    diag.content_type = str(resp.headers.get("Content-Type", ""))
                    response_headers = dict(resp.headers.items())
                    if resp.status != 200:
                        raise RuntimeError(f"WFS zwrócił status {resp.status}.")
                    payload = resp.read().decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as exc:
                diag.status_code = exc.code
                diag.content_type = str(exc.headers.get("Content-Type", "")) if exc.headers else ""
                try:
                    body_preview = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    body_preview = ""
                diag.body_snippet = body_preview[:500]
                response_headers = dict(exc.headers.items()) if exc.headers else {}
                logger.warning(
                    "parcel.search.external.http_error url=%s query=%s status=%s attempt=%s/%s responseHeaders=%s bodySnippet=%s",
                    request_url,
                    params,
                    diag.status_code,
                    attempt,
                    len(retries),
                    response_headers,
                    diag.body_snippet.replace("\n", " "),
                )
                if exc.code == 502 and attempt < len(retries):
                    continue
                raise
            except Exception as exc:
                if self._is_transient_connection_error(exc) and attempt < len(retries):
                    logger.warning(
                        "parcel.search.external.transient_retry url=%s query=%s attempt=%s/%s error=%s",
                        request_url,
                        params,
                        attempt,
                        len(retries),
                        exc,
                    )
                    continue
                raise
        diag.body_snippet = payload[:1000]
        logger.info(
            "parcel.search.external.response url=%s query=%s status=%s responseHeaders=%s contentType=%s bodySnippet=%s",
            request_url,
            params,
            diag.status_code,
            response_headers,
            diag.content_type,
            diag.body_snippet.replace("\n", " ")[:500],
        )
        try:
            parsed = parse_wfs_payload(response_headers={"Content-Type": diag.content_type}, response_body=payload, diagnostics=diag)
            return parsed, diag
        except WfsServiceError as exc:
            if exc.diagnostics:
                diag = exc.diagnostics
            diag.error_type = exc.error_type
            diag.error_message = exc.technical_message
            logger.warning(
                "parcel.search.external.parse_failed url=%s status=%s contentType=%s detected=%s parser=%s errorType=%s error=%s",
                diag.request_url,
                diag.status_code,
                diag.content_type,
                diag.detected_format,
                diag.parser_used,
                diag.error_type,
                exc.user_message,
            )
            raise RuntimeError(exc.user_message) from exc

    @staticmethod
    def _is_transient_connection_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "connection reset" in text or "connection aborted" in text or "broken pipe" in text

    def _discover_feature_type_name(self, *, url: str, requested_type_name: str, timeout: int | float) -> str | None:
        if ":" in requested_type_name:
            return None
        params = {
            "service": "WFS",
            "request": "GetCapabilities",
        }
        query = urllib.parse.urlencode(params)
        capabilities_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        request = urllib.request.Request(
            capabilities_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BuildParcelBot/1.0)",
                "Accept": "application/xml, text/xml;q=0.9, */*;q=0.8",
            },
        )
        try:
            with self._safe_urlopen(request, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                xml_payload = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None
        try:
            root = ET.fromstring(xml_payload)
        except Exception:
            return None
        for elem in root.findall(".//{*}FeatureType/{*}Name"):
            value = (elem.text or "").strip()
            if value.endswith(f":{requested_type_name}"):
                return value
        return None

    def _safe_urlopen(self, request: Any, *, timeout: int | float):
        proxies = urllib.request.getproxies()
        has_proxy = bool(proxies.get("http") or proxies.get("https"))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies if has_proxy else {}))
        try:
            return opener.open(request, timeout=timeout)
        except urllib.error.HTTPError:
            raise
        except Exception as exc:
            diag_code = classify_wfs_connection_error(exc)
            if diag_code == "PROXY_CONNECT_403":
                logger.error("parcel.search.external.infrastructure_error code=PROXY_CONNECT_403 detail=%s", exc)
            elif diag_code in {"NETWORK_UNREACHABLE", "TCP_BLOCKED"}:
                logger.error("parcel.search.external.infrastructure_error code=%s detail=%s", diag_code, exc)
            raise

    def diagnose_wfs_connectivity(self) -> dict[str, Any]:
        wfs = self.config.get("wfs", {}) if isinstance(self.config, dict) else {}
        url = str(wfs.get("url") or "").strip()
        if not url:
            return {"ok": False, "code": "NOT_CONFIGURED", "message": "Brak konfiguracji WFS (url)."}

        timeout = _wfs_timeout_seconds(wfs.get("timeout", 15))
        params = {"service": "WFS", "request": "GetCapabilities"}
        if wfs.get("version"):
            params["version"] = wfs.get("version")

        query = urllib.parse.urlencode(params, doseq=True)
        request_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        request = urllib.request.Request(
            request_url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; BuildParcelBot/1.0)",
                "Accept": "application/xml, text/xml;q=0.9, */*;q=0.8",
            },
        )
        diag = WfsDiagnostics(request_url=request_url, method="GET", query_params=params)
        try:
            with self._safe_urlopen(request, timeout=timeout) as resp:
                diag.status_code = resp.status
                diag.content_type = str(resp.headers.get("Content-Type", ""))
                body = resp.read().decode("utf-8", errors="replace")
            diag.body_snippet = body[:1000]
            if resp.status != 200:
                return {"ok": False, "code": "WFS_HTTP_ERROR", "status": resp.status, "url": request_url, "contentType": diag.content_type}
            parse_wfs_payload(response_headers={"Content-Type": diag.content_type}, response_body=body, diagnostics=diag)
            return {
                "ok": True,
                "code": "DNS_OK",
                "status": diag.status_code,
                "url": request_url,
                "contentType": diag.content_type,
                "detectedFormat": diag.detected_format,
                "parserUsed": diag.parser_used,
            }
        except urllib.error.HTTPError as exc:
            return {"ok": False, "code": "WFS_HTTP_ERROR", "status": exc.code, "url": request_url, "message": str(exc)}
        except Exception as exc:
            return {"ok": False, "code": classify_wfs_connection_error(exc), "url": request_url, "message": str(exc)}

    def _build_cql_filter(self, mapping_cfg: dict[str, Any], normalized: dict[str, Any]) -> str:
        filters = []
        parcel_cfg = mapping_cfg.get("parcelNumber", {})
        parcel_type = parcel_cfg.get("type", "singleField")
        if parcel_type == "singleField" and parcel_cfg.get("field"):
            parcel_value = str(normalized["nrCanonical"]).replace("'", "''")
            filters.append(f"{parcel_cfg['field']}='{parcel_value}'")
        elif parcel_type == "mainSubFields":
            main_field = parcel_cfg.get("mainField")
            sub_field = parcel_cfg.get("subField")
            if main_field:
                main_value = str(normalized["nrMain"]).replace("'", "''")
                filters.append(f"{main_field}='{main_value}'")
            if sub_field and normalized.get("nrSub") is not None:
                sub_value = str(normalized["nrSub"]).replace("'", "''")
                filters.append(f"{sub_field}='{sub_value}'")

        obreb_field = mapping_cfg.get("obreb", {}).get("field")
        obreb_variants = [str(value).strip() for value in normalized.get("obrebVariants", []) if str(value).strip()]
        if obreb_field:
            if len(obreb_variants) > 1:
                or_filters = " OR ".join(f"{obreb_field}='{value.replace(chr(39), chr(39) * 2)}'" for value in obreb_variants)
                filters.append(f"({or_filters})")
            elif obreb_variants:
                safe_obreb = obreb_variants[0].replace(chr(39), chr(39) * 2)
                filters.append(f"{obreb_field}='{safe_obreb}'")
            elif normalized.get("obrebCanonical"):
                fallback_obreb = str(normalized["obrebCanonical"]).replace("'", "''")
                filters.append(f"{obreb_field}='{fallback_obreb}'")

        miejsc_field = mapping_cfg.get("miejscowosc", {}).get("field")
        if miejsc_field and normalized.get("miejscowoscVariants"):
            miejsc = normalized["miejscowoscVariants"][0].replace("'", "''")
            filters.append(f"{miejsc_field} ILIKE '{miejsc}'")
        return " AND ".join(filters)

    def _map_feature(self, feature: dict[str, Any], mapping_cfg: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or props.get(mapping_cfg.get("geomField"))
        if geometry and isinstance(geometry, dict):
            geometry = self._ensure_4326(geometry, self.config.get("wfs", {}))

        parcel_number = self._resolve_parcel_number(props, mapping_cfg, normalized)
        obreb_value = props.get(mapping_cfg.get("obreb", {}).get("field"), normalized.get("obrebCanonical"))
        miejsc_value = props.get(mapping_cfg.get("miejscowosc", {}).get("field"), normalized.get("miejscowoscVariants", [""])[0])
        id_field = mapping_cfg.get("idField")
        return {
            "id": props.get(id_field) or feature.get("id") or f"parcel-{parcel_number}-{obreb_value}",
            "parcelNumber": parcel_number,
            "obreb": obreb_value,
            "miejscowosc": miejsc_value or "",
            "geometry": geometry,
        }

    def _resolve_parcel_number(self, props: dict[str, Any], mapping_cfg: dict[str, Any], normalized: dict[str, Any]) -> str:
        parcel_cfg = mapping_cfg.get("parcelNumber", {})
        parcel_type = parcel_cfg.get("type", "singleField")
        if parcel_type == "singleField":
            value = props.get(parcel_cfg.get("field"))
            return normalize_parcel_number(str(value or normalized["nrCanonical"]))
        if parcel_type == "mainSubFields":
            main_field = parcel_cfg.get("mainField")
            sub_field = parcel_cfg.get("subField")
            main_val = props.get(main_field) if main_field else normalized["nrMain"]
            sub_val = props.get(sub_field) if sub_field else normalized["nrSub"]
            if sub_val is None or str(sub_val) == "0":
                return normalize_parcel_number(str(main_val or ""))
            return normalize_parcel_number(f"{main_val}/{sub_val}")
        return normalized["nrCanonical"]

    def _ensure_4326(self, geometry: dict[str, Any], wfs_cfg: dict[str, Any]) -> dict[str, Any]:
        srs = wfs_cfg.get("srsName", "EPSG:4326")
        if srs == "EPSG:4326" or Transformer is None:
            return geometry
        try:
            transformer = Transformer.from_crs(srs, "EPSG:4326", always_xy=True).transform
            geom = shp_transform(transformer, shape(geometry))
            return mapping(geom)
        except Exception:
            return geometry


class ContextProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch_context(self, buffer_geom: Polygon) -> tuple[dict[str, list[dict[str, Any]]], ProviderMeta]:
        minx, miny, maxx, maxy = buffer_geom.bounds
        buildings = [
            {
                "type": "Feature",
                "geometry": mapping(Polygon([(minx + 0.1*(maxx-minx), miny + 0.1*(maxy-miny)), (minx + 0.2*(maxx-minx), miny + 0.1*(maxy-miny)), (minx + 0.2*(maxx-minx), miny + 0.2*(maxy-miny)), (minx + 0.1*(maxx-minx), miny + 0.2*(maxy-miny))])),
                "properties": {"kind": "building", "source": "context"},
            }
        ]
        roads = [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[minx, (miny+maxy)/2], [maxx, (miny+maxy)/2]]},
                "properties": {"kind": "road", "source": "context"},
            }
        ]
        return {"buildings": buildings, "roads": roads}, ProviderMeta(
            sourceName="BDOT/OSM fallback (stub)",
            dataType="vector",
            licenseNote="OSM ODbL dla fallback.",
            accuracyNote="Warstwa kontekstowa orientacyjna.",
            warnings=[],
        )


class UtilitiesProvider:
    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fetch_utilities(self, buffer_geom: Polygon) -> tuple[dict[str, Any], ProviderMeta]:
        minx, miny, maxx, maxy = buffer_geom.bounds
        utilities = [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[minx, miny], [maxx, maxy]]},
            "properties": {"kind": "power=line"},
        }]
        wms_overlays = []
        if self.config.get("provider") == "wms_overlay":
            wms = self.config.get("wms", {})
            wms_overlays.append({
                "id": "utilities-wms",
                "label": "Media (orientacyjne)",
                "url": wms.get("url", ""),
                "layers": wms.get("layers", ""),
            })
        return {"utilities": utilities, "wmsOverlays": wms_overlays}, ProviderMeta(
            sourceName="Utilities WFS/WMS",
            dataType="vector_or_raster_overlay",
            licenseNote="WMS wyłącznie poglądowo.",
            accuracyNote="Sieci mogą wymagać weryfikacji terenowej.",
            warnings=[] if utilities else ["Brak warstw mediów wektorowych."],
        )


class MapService:
    def __init__(self, db_conn, config: dict[str, Any]):
        self.db = db_conn
        self.config = config

    def _check_parcel_provider(self):
        parcels_cfg = self.config.get("parcels", {})
        if not parcels_cfg.get("provider"):
            raise RuntimeError("PARCEL_PROVIDER_NOT_CONFIGURED")

    def resolve(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._check_parcel_provider()
        normalized = normalizeParcelInput(payload.get("nrDzialki", ""), payload.get("obreb", ""), payload.get("miejscowosc", ""))
        parcel_provider = ParcelProvider(self.config.get("parcels", {}))
        candidates, parcel_meta = parcel_provider.resolve_candidates(normalized)

        scored = []
        for item in candidates:
            score = 0
            if normalize_parcel_number(item.get("parcelNumber", "")) == normalized["nrCanonical"]:
                score += 60
            item_obreb = str(item.get("obreb", "") or "").strip()
            if item_obreb and (item_obreb == normalized["obrebCanonical"] or item_obreb in normalized.get("obrebVariants", [])):
                score += 25
            miejsc = (item.get("miejscowosc") or "").lower()
            if miejsc and miejsc in [v.lower() for v in normalized["miejscowoscVariants"]]:
                score += 15
            if normalize_text_ascii(miejsc) in [normalize_text_ascii(v.lower()) for v in normalized["miejscowoscVariants"]]:
                score += 10
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            raise ValueError("Nie znaleziono działki dla podanych danych.")

        warnings = []
        winner_score, winner = scored[0]
        if len(scored) > 1 and winner_score - scored[1][0] <= 5:
            warnings.append("Niejednoznaczny wynik dopasowania działki.")

        winner_geometry = winner.get("geometry")
        if not isinstance(winner_geometry, dict):
            raise ValueError("MISSING_GEOMETRY")
        try:
            plot_geom_4326 = make_valid(shape(winner_geometry))
        except Exception as exc:
            raise ValueError("MISSING_GEOMETRY") from exc
        buffer_m = float(payload.get("bufferMeters", 30))
        site_boundary_geom = createSiteBoundaryFromPlot(mapping(plot_geom_4326), buffer_m)
        buffer_4326 = make_valid(shape(site_boundary_geom))
        buffer_geom_2180 = buffer_4326

        context_provider = ContextProvider(self.config.get("context", {}))
        util_provider = UtilitiesProvider(self.config.get("utilities", {}))

        context = {"buildings": [], "roads": []}
        context_meta = ProviderMeta(
            sourceName="BDOT/OSM fallback (stub)",
            dataType="vector",
            licenseNote="Źródło kontekstowe niedostępne.",
            accuracyNote="Brak danych kontekstowych.",
            warnings=["Brak danych kontekstowych."],
        )
        util_data = {"utilities": [], "wmsOverlays": []}
        util_meta = ProviderMeta(
            sourceName="Utilities WFS/WMS",
            dataType="vector_or_raster_overlay",
            licenseNote="Źródło mediów niedostępne.",
            accuracyNote="Brak danych mediów.",
            warnings=["Brak danych mediów."],
        )
        try:
            context, context_meta = context_provider.fetch_context(buffer_geom_2180)
        except Exception as exc:
            warnings.append(f"CONTEXT_SOURCE_ERROR: {exc}")
        try:
            util_data, util_meta = util_provider.fetch_utilities(buffer_geom_2180)
        except Exception as exc:
            warnings.append(f"UTILITIES_SOURCE_ERROR: {exc}")

        minx, miny, maxx, maxy = buffer_4326.bounds
        session_id = str(uuid.uuid4())
        now = int(time.time())
        metadata = {
            "createdAt": now,
            "expiresAt": now + 86400,
            "sources": {
                "parcel": parcel_meta.__dict__,
                "context": context_meta.__dict__,
                "utilities": util_meta.__dict__,
            },
        }
        self.db.execute(
            "INSERT INTO map_sessions (id, plot_geom, buffer_geom, bbox4326, metadata, createdAt) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, json.dumps(mapping(plot_geom_4326)), json.dumps(mapping(buffer_4326)), json.dumps([minx, miny, maxx, maxy]), json.dumps(metadata), now),
        )

        def save_features(layer: str, features: list[dict[str, Any]]):
            for ft in features:
                self.db.execute(
                    "INSERT INTO map_features (session_id, layer, geom, props) VALUES (?, ?, ?, ?)",
                    (session_id, layer, json.dumps(ft.get("geometry")), json.dumps(ft.get("properties", {}))),
                )

        save_features("plot", [{"geometry": mapping(plot_geom_4326), "properties": {"main": True}}])
        save_features("neighbors", [{"geometry": mapping(buffer_4326.difference(plot_geom_4326)), "properties": {"synthetic": True}}])
        save_features("buildings", context["buildings"])
        save_features("roads", context["roads"])
        save_features("utilities", util_data["utilities"])
        self.db.commit()

        return {
            "sessionId": session_id,
            "plot": {"type": "Feature", "geometry": mapping(plot_geom_4326), "properties": {"id": winner["id"]}},
            "buffer": {"type": "Feature", "geometry": mapping(buffer_4326), "properties": {"bufferMeters": buffer_m}},
            "bbox4326": [minx, miny, maxx, maxy],
            "sources": metadata["sources"],
            "warnings": warnings,
            "candidates": [i for _, i in scored[:3]] if warnings else [],
            "wmsOverlays": util_data["wmsOverlays"],
        }

    def search_parcels(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._check_parcel_provider()
        normalized = normalizeParcelInput(payload.get("nrDzialki", ""), payload.get("obreb", ""), payload.get("miejscowosc", ""))
        parcel_provider = ParcelProvider(self.config.get("parcels", {}))
        candidates, parcel_meta = parcel_provider.resolve_candidates(normalized)
        scored = []
        for item in candidates:
            score = 0
            if normalize_parcel_number(item.get("parcelNumber", "")) == normalized["nrCanonical"]:
                score += 60
            item_obreb = str(item.get("obreb", "") or "").strip()
            if item_obreb and (item_obreb == normalized["obrebCanonical"] or item_obreb in normalized.get("obrebVariants", [])):
                score += 25
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)

        response_items = []
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
            response_items.append({
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
            })

        return {
            "items": response_items,
            "sources": {"parcel": parcel_meta.__dict__},
            "empty": len(response_items) == 0,
        }

    def get_parcel_details(self, payload: dict[str, Any], parcel_id: str) -> dict[str, Any]:
        results = self.search_parcels(payload)
        matched = next((item for item in results.get("items", []) if str(item.get("id")) == str(parcel_id)), None)
        if not matched:
            raise ValueError("Nie znaleziono wskazanej działki.")
        return matched

    def import_parcel_to_project(self, project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        parcel = payload.get("parcel") or {}
        geometry = parcel.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError("Brak geometrii działki.")
        parcel_geom_4326 = make_valid(shape(geometry))
        centroid = parcel_geom_4326.centroid
        bbox = list(parcel_geom_4326.bounds)

        layer_payload = payload.get("layers") or ["plot", "neighbors", "buildings", "roads", "utilities"]
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.db.execute(
            """
            INSERT INTO planning_parcel_imports (
                projectId, source, parcelId, parcelNumber, cadastralUnit, precinct,
                geometryJson, centroidJson, bboxJson, area, layersJson, visible, locked, importedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(projectId, source, parcelId)
            DO UPDATE SET
                parcelNumber=excluded.parcelNumber,
                cadastralUnit=excluded.cadastralUnit,
                precinct=excluded.precinct,
                geometryJson=excluded.geometryJson,
                centroidJson=excluded.centroidJson,
                bboxJson=excluded.bboxJson,
                area=excluded.area,
                layersJson=excluded.layersJson,
                visible=excluded.visible,
                locked=excluded.locked,
                importedAt=excluded.importedAt
            """,
            (
                int(project_id),
                "geoportal",
                str(parcel.get("parcelId") or parcel.get("id") or ""),
                parcel.get("parcelNumber"),
                parcel.get("cadastralUnit"),
                parcel.get("precinct"),
                json.dumps(mapping(parcel_geom_4326)),
                json.dumps({"type": "Point", "coordinates": [centroid.x, centroid.y]}),
                json.dumps(bbox),
                float(parcel.get("area")) if parcel.get("area") is not None else float(parcel_geom_4326.area),
                json.dumps(layer_payload),
                1,
                1,
                now_iso,
            ),
        )
        self.db.commit()
        resolve_payload = {
            "nrDzialki": parcel.get("parcelNumber") or payload.get("nrDzialki") or "",
            "obreb": parcel.get("precinct") or payload.get("obreb") or "",
            "miejscowosc": parcel.get("cadastralUnit") or payload.get("miejscowosc") or "",
            "bufferMeters": payload.get("bufferMeters", 30),
        }
        resolved = self.resolve(resolve_payload)
        resolved["imported"] = {
            "projectId": int(project_id),
            "source": "geoportal",
            "parcelId": str(parcel.get("parcelId") or parcel.get("id") or ""),
            "parcelNumber": parcel.get("parcelNumber"),
            "cadastralUnit": parcel.get("cadastralUnit"),
            "precinct": parcel.get("precinct"),
            "geometry": mapping(parcel_geom_4326),
            "centroid": {"type": "Point", "coordinates": [centroid.x, centroid.y]},
            "bbox": bbox,
            "area": float(parcel.get("area")) if parcel.get("area") is not None else float(parcel_geom_4326.area),
            "layers": layer_payload,
            "importedAt": now_iso,
            "visible": True,
            "locked": True,
        }
        context = self._persist_site_context(
            project_id=int(project_id),
            parcel_id=str(parcel.get("parcelId") or parcel.get("id") or ""),
            site_boundary=mapping(parcel_geom_4326),
            analysis_buffer_m=float(payload.get("bufferMeters", 30) or 30),
            resolved_payload=resolved,
            warnings=resolved.get("warnings") or [],
            source_name="geoportal",
            layer_import_plan=payload.get("layerImportPlan"),
        )
        resolved["siteContext"] = dataclass_to_dict(context)
        return resolved

    def _persist_site_context(
        self,
        *,
        project_id: int,
        parcel_id: str,
        site_boundary: dict[str, Any],
        analysis_buffer_m: float,
        resolved_payload: dict[str, Any],
        warnings: list[str],
        source_name: str,
        layer_import_plan: dict[str, Any] | None = None,
    ) -> SiteContext:
        session_id = resolved_payload.get("sessionId")
        layers_payload = self.get_session_features(session_id) if session_id else {}
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        context_id = str(uuid.uuid4())

        analysis_boundary = createSiteBoundaryFromPlot(site_boundary, analysis_buffer_m)
        plot_geom = make_valid(shape(site_boundary))
        site_geom = make_valid(shape(analysis_boundary))

        source_layer_mapping = {
            "plot_boundary": "plot",
            "land_use_boundary": "neighbors",
            "road_edge": "roads",
            "road_centerline": "roads",
            "road_right_of_way": "roads",
            "elevation_point": "neighbors",
            "contour_line": "neighbors",
            "existing_building": "buildings",
            "adjacent_building": "buildings",
            "fence_line": "neighbors",
            "water_pipe": "utilities",
            "sanitary_sewer": "utilities",
            "storm_sewer": "utilities",
            "gas_pipe": "utilities",
            "power_line_underground": "utilities",
            "power_line_overhead": "utilities",
            "telecom_line": "utilities",
            "utility_node": "utilities",
            "transformer_station": "utilities",
            "watercourse": "neighbors",
            "drainage_ditch": "neighbors",
            "pond": "neighbors",
            "flood_zone": "neighbors",
            "tree": "neighbors",
            "shrub_area": "neighbors",
            "forest_boundary": "neighbors",
            "conservation_zone": "neighbors",
            "environmental_protection_zone": "neighbors",
            "noise_impact_zone": "neighbors",
            "height_limit_zone": "neighbors",
            "special_restriction_zone": "neighbors",
        }
        network_layer_keys = {
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
        }
        plan_layers = {item.get("layerKey"): item for item in (layer_import_plan or {}).get("layers", []) if isinstance(item, dict)}
        fetched_layers = []
        empty_layers = []
        unavailable_layers = []
        partial_errors = list(warnings or [])
        objects_per_layer: dict[str, int] = {}
        site_layers: list[SiteLayer] = []
        site_objects: list[SiteObject] = []

        def _spatial_flags(geometry_data: dict[str, Any]) -> tuple[bool | None, bool | None, bool | None, Any, Any, Any]:
            try:
                geom_obj = make_valid(shape(geometry_data))
                centroid = geom_obj.centroid
                bbox = list(geom_obj.bounds)
                within_plot = bool(geom_obj.within(plot_geom))
                within_site_boundary = bool(geom_obj.within(site_geom))
                intersects_plot = bool(geom_obj.intersects(plot_geom))
                return within_plot, within_site_boundary, intersects_plot, geom_obj, centroid, bbox
            except Exception:
                return None, None, None, None, None, None

        for idx, layer_key in enumerate(ALL_SITE_LAYER_KEYS):
            definition = SITE_LAYER_DEFINITIONS[layer_key]
            planned = plan_layers.get(layer_key, {})
            strategy = planned.get("strategy") or "source_unavailable"
            features: list[dict[str, Any]] = []
            status = planned.get("targetStatus") or "unavailable"

            if strategy == "core_geometry":
                if layer_key == "plot_boundary":
                    features = [{"type": "Feature", "geometry": site_boundary, "properties": {"main": True}}]
                else:
                    features = [{"type": "Feature", "geometry": analysis_boundary, "properties": {"analytical": True}}]
                status = "loaded"
                fetched_layers.append(layer_key)
            elif strategy == "try_direct_import" or layer_key == "adjacent_building":
                source_key = source_layer_mapping.get(layer_key)
                if not source_key:
                    status = "unavailable"
                    unavailable_layers.append(layer_key)
                else:
                    raw_features = layers_payload.get(source_key)
                    if raw_features is None:
                        status = "unavailable"
                        unavailable_layers.append(layer_key)
                    elif not raw_features:
                        status = "empty"
                        empty_layers.append(layer_key)
                    else:
                        normalized_features = []
                        invalid_count = 0
                        for ft in raw_features:
                            geometry = (ft or {}).get("geometry")
                            if not isinstance(geometry, dict):
                                invalid_count += 1
                                continue
                            properties = dict((ft or {}).get("properties") or {})
                            within_plot, within_site_boundary, intersects_plot, _, _, _ = _spatial_flags(geometry)

                            if layer_key == "existing_building" and not intersects_plot:
                                continue
                            if layer_key == "adjacent_building" and not (within_site_boundary and not intersects_plot):
                                continue

                            if layer_key in network_layer_keys:
                                properties["plotRelation"] = "collision" if intersects_plot else "context"
                                properties["isCollision"] = bool(intersects_plot)
                            if layer_key == "tree":
                                properties["treeContext"] = "plot" if within_plot else "neighborhood"

                            normalized_features.append({
                                "type": "Feature",
                                "geometry": geometry,
                                "properties": properties,
                            })

                        features = normalized_features
                        if invalid_count and not features:
                            status = "error"
                            partial_errors.append(f"{layer_key}: invalid features")
                        elif invalid_count:
                            status = "loaded"
                            partial_errors.append(f"{layer_key}: skipped {invalid_count} invalid features")
                            fetched_layers.append(layer_key)
                        elif features:
                            status = "loaded"
                            fetched_layers.append(layer_key)
                        else:
                            status = "empty"
                            empty_layers.append(layer_key)
            elif strategy == "manual_placeholder":
                status = "manual_placeholder"
            elif strategy == "derive_later":
                status = "derived"
            elif strategy == "create_empty":
                status = "empty"
                empty_layers.append(layer_key)
            else:
                status = "unavailable"
                unavailable_layers.append(layer_key)

            geometry_type = definition.geometryType
            if features:
                geometry_type = str(features[0].get("geometry", {}).get("type") or definition.geometryType)
            layer = SiteLayer(
                id=str(uuid.uuid4()),
                projectId=project_id,
                siteContextId=context_id,
                layerKey=layer_key,
                label=definition.label,
                status=status,
                sourceType=definition.sourcePreference,
                visible=definition.defaultVisibility,
                locked=definition.defaultLocked,
                geometryType=geometry_type,
                features=features,
                metadata={"sourceSessionId": session_id, "group": definition.group, "canBeDerived": definition.canBeDerived, "strategy": strategy},
                style={},
                sortOrder=definition.sortOrder,
            )
            site_layers.append(layer)
            objects_per_layer[layer_key] = len(features)


        # Derived layers computation (saved exactly like imported layers)
        derived_service = DerivedLayerComputationService(self.config.get("derivedLayers", {}))
        base_layers_map = {layer.layerKey: layer.features for layer in site_layers}
        derived_result = None
        try:
            derived_result = derived_service.compute(
                plot_boundary=site_boundary,
                site_boundary=analysis_boundary,
                layers=base_layers_map,
            )
            if derived_result.errors:
                partial_errors.extend(derived_result.errors)
        except Exception as exc:
            partial_errors.append(f"DERIVED_LAYER_ERROR: {exc}")

        for target_key in [
            "offset_from_boundary_zone",
            "utility_protection_zone",
            "tree_canopy",
            "root_protection_zone",
            "limited_build_zone",
        ]:
            layer = next((it for it in site_layers if it.layerKey == target_key), None)
            if layer is None:
                continue
            feats = (derived_result.layers.get(target_key, []) if derived_result else [])
            layer.features = feats
            layer.geometryType = str(feats[0].get("geometry", {}).get("type") or layer.geometryType) if feats else layer.geometryType
            layer.status = "loaded" if feats else "derived"
            objects_per_layer[target_key] = len(feats)
            if feats and target_key not in fetched_layers:
                fetched_layers.append(target_key)
            if not feats and target_key in fetched_layers:
                fetched_layers.remove(target_key)

        # Buildability analysis from all layers
        layers_for_analysis = {layer.layerKey: layer.features for layer in site_layers}
        buildability_service = SiteBuildabilityAnalysisService(self.config.get("buildability", {}))
        try:
            buildability = buildability_service.compute(
                plot_boundary=site_boundary,
                layers=layers_for_analysis,
            )
        except Exception as exc:
            partial_errors.append(f"SPATIAL_ANALYSIS_ERROR: {exc}")

            class _FallbackBuildability:
                buildable_area_geometry = None
                max_building_envelope_geometry = None
                preferred_building_zone_geometry = None
                building_candidates = []
                constraints = []
                observations = []
                warnings = ["Analiza przestrzenna nie powiodła się."]
                notes = []

            buildability = _FallbackBuildability()

        analysis_layer_features = {
            "buildable_area": [] if buildability.buildable_area_geometry is None else [{"type": "Feature", "geometry": buildability.buildable_area_geometry, "properties": {"analysis": True}}],
            "max_building_envelope": [] if buildability.max_building_envelope_geometry is None else [{"type": "Feature", "geometry": buildability.max_building_envelope_geometry, "properties": {"analysis": True}}],
            "preferred_building_zone": [] if buildability.preferred_building_zone_geometry is None else [{"type": "Feature", "geometry": buildability.preferred_building_zone_geometry, "properties": {"analysis": True}}],
            "building_candidate": [
                {"type": "Feature", "geometry": candidate.get("geometry"), "properties": {k: v for k, v in candidate.items() if k != "geometry"}}
                for candidate in buildability.building_candidates
                if isinstance(candidate.get("geometry"), dict)
            ],
        }
        for layer in site_layers:
            if layer.layerKey not in analysis_layer_features:
                continue
            feats = analysis_layer_features[layer.layerKey]
            layer.features = feats
            layer.status = "loaded" if feats else "derived"
            objects_per_layer[layer.layerKey] = len(feats)
            if feats and layer.layerKey not in fetched_layers:
                fetched_layers.append(layer.layerKey)

        # rebuild objects to include analysis-result layers
        site_objects = []
        for layer in site_layers:
            for ft_idx, feature in enumerate(layer.features or []):
                geom_data = feature.get("geometry") or {}
                within_plot, within_site_boundary, intersects_plot, _, centroid, bbox = _spatial_flags(geom_data)
                source_metadata = {
                    "layer": layer.layerKey,
                    "plotRelation": "on_plot" if within_plot else ("collision" if intersects_plot else "site_context"),
                }
                if layer.layerKey in network_layer_keys:
                    source_metadata["collision"] = bool(intersects_plot)
                if layer.layerKey == "tree":
                    source_metadata["treeContext"] = "plot" if within_plot else "neighborhood"
                site_objects.append(
                    SiteObject(
                        id=f"{context_id}:{layer.layerKey}:{ft_idx}",
                        projectId=project_id,
                        siteContextId=context_id,
                        layerKey=layer.layerKey,
                        objectType=str(geom_data.get("type") or "unknown"),
                        geometry=geom_data,
                        bbox=bbox,
                        centroid={"type": "Point", "coordinates": [centroid.x, centroid.y]} if centroid else None,
                        sourceType=layer.sourceType,
                        sourceName=source_name,
                        sourceMetadata=source_metadata,
                        confidence=1.0 if layer.layerKey == "plot_boundary" else 0.75,
                        withinPlot=within_plot,
                        withinSiteBoundary=within_site_boundary,
                        intersectsPlot=intersects_plot,
                        properties=feature.get("properties") or {},
                    )
                )

        analysis = SiteAnalysisResult(
            buildableArea=0.0 if buildability.buildable_area_geometry is None else float(shape(buildability.buildable_area_geometry).area),
            maxBuildingEnvelope=buildability.max_building_envelope_geometry,
            preferredBuildingZone=buildability.preferred_building_zone_geometry,
            buildingCandidates=buildability.building_candidates,
            constraints=buildability.constraints,
            observations=buildability.observations,
            warnings=[*warnings, *buildability.warnings],
            notes=[*buildability.notes, "Warstwa referencyjna jest zablokowana do edycji."],
        )
        summary_status = "loaded"
        if unavailable_layers or partial_errors:
            summary_status = "unavailable" if not fetched_layers else "error"
        if not fetched_layers and empty_layers:
            summary_status = "empty"
        if not fetched_layers and not empty_layers and not unavailable_layers:
            summary_status = "derived"
        import_summary = ImportSummary(
            status=summary_status,
            objectsPerLayer=objects_per_layer,
            fetchedLayers=fetched_layers,
            emptyLayers=empty_layers,
            unavailableLayers=unavailable_layers,
            partialErrors=partial_errors,
        )

        site_context = SiteContext(
            id=context_id,
            projectId=project_id,
            primaryParcelId=parcel_id,
            siteBoundary=analysis_boundary,
            analysisBufferMeters=analysis_buffer_m,
            layers=site_layers,
            objects=site_objects,
            analysisResult=analysis,
            importSummary=import_summary,
            createdAt=now_iso,
            updatedAt=now_iso,
        )

        self.db.execute(
            """
            INSERT INTO site_contexts (
                id, projectId, primaryParcelId, siteBoundaryJson, analysisBufferMeters,
                analysisResultJson, importSummaryJson, dataStatus, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site_context.id,
                site_context.projectId,
                site_context.primaryParcelId,
                json.dumps(site_context.siteBoundary),
                float(site_context.analysisBufferMeters),
                json.dumps(dataclass_to_dict(site_context.analysisResult)),
                json.dumps(dataclass_to_dict(site_context.importSummary)),
                summary_status,
                site_context.createdAt,
                site_context.updatedAt,
            ),
        )
        analysis_id = str(uuid.uuid4())
        self.db.execute(
            """
            INSERT INTO site_analysis_results (
                id, projectId, siteContextId, buildableArea, maxBuildingEnvelopeJson,
                preferredBuildingZoneJson, buildingCandidatesJson, constraintsJson,
                observationsJson, warningsJson, notesJson, createdAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                site_context.projectId,
                site_context.id,
                site_context.analysisResult.buildableArea if site_context.analysisResult else None,
                json.dumps(site_context.analysisResult.maxBuildingEnvelope) if site_context.analysisResult else None,
                json.dumps(site_context.analysisResult.preferredBuildingZone) if site_context.analysisResult else None,
                json.dumps(site_context.analysisResult.buildingCandidates if site_context.analysisResult else []),
                json.dumps(site_context.analysisResult.constraints if site_context.analysisResult else []),
                json.dumps(site_context.analysisResult.observations if site_context.analysisResult else []),
                json.dumps(site_context.analysisResult.warnings if site_context.analysisResult else []),
                json.dumps(site_context.analysisResult.notes if site_context.analysisResult else []),
                now_iso,
            ),
        )
        import_log_id = str(uuid.uuid4())
        self.db.execute(
            """
            INSERT INTO site_import_logs (
                id, projectId, siteContextId, status, objectsPerLayerJson, fetchedLayersJson,
                emptyLayersJson, unavailableLayersJson, partialErrorsJson, createdAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_log_id,
                site_context.projectId,
                site_context.id,
                site_context.importSummary.status if site_context.importSummary else "failed",
                json.dumps(site_context.importSummary.objectsPerLayer if site_context.importSummary else {}),
                json.dumps(site_context.importSummary.fetchedLayers if site_context.importSummary else []),
                json.dumps(site_context.importSummary.emptyLayers if site_context.importSummary else []),
                json.dumps(site_context.importSummary.unavailableLayers if site_context.importSummary else []),
                json.dumps(site_context.importSummary.partialErrors if site_context.importSummary else []),
                now_iso,
            ),
        )
        for layer in site_layers:
            self.db.execute(
                """
                INSERT INTO site_layers (
                    id, projectId, siteContextId, layerKey, label, status, sourceType,
                    visible, locked, geometryType, featuresJson, metadataJson, styleJson, sortOrder
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    layer.id,
                    layer.projectId,
                    layer.siteContextId,
                    layer.layerKey,
                    layer.label,
                    layer.status,
                    layer.sourceType,
                    1 if layer.visible else 0,
                    1 if layer.locked else 0,
                    layer.geometryType,
                    json.dumps(layer.features),
                    json.dumps(layer.metadata),
                    json.dumps(layer.style),
                    layer.sortOrder,
                ),
            )
        for obj in site_objects:
            self.db.execute(
                """
                INSERT INTO site_objects (
                    id, projectId, siteContextId, layerKey, objectType, geometryJson, bboxJson, centroidJson,
                    sourceType, sourceName, sourceMetadataJson, confidence, withinPlot, withinSiteBoundary,
                    intersectsPlot, propertiesJson
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obj.id,
                    obj.projectId,
                    obj.siteContextId,
                    obj.layerKey,
                    obj.objectType,
                    json.dumps(obj.geometry),
                    json.dumps(obj.bbox) if obj.bbox is not None else None,
                    json.dumps(obj.centroid) if obj.centroid is not None else None,
                    obj.sourceType,
                    obj.sourceName,
                    json.dumps(obj.sourceMetadata),
                    obj.confidence,
                    None if obj.withinPlot is None else (1 if obj.withinPlot else 0),
                    None if obj.withinSiteBoundary is None else (1 if obj.withinSiteBoundary else 0),
                    None if obj.intersectsPlot is None else (1 if obj.intersectsPlot else 0),
                    json.dumps(obj.properties),
                ),
            )
        self.db.commit()
        return site_context

    def get_latest_site_context(self, project_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM site_contexts WHERE projectId = ? ORDER BY createdAt DESC LIMIT 1",
            (int(project_id),),
        ).fetchone()
        if not row:
            return None
        layers_rows = self.db.execute(
            "SELECT * FROM site_layers WHERE siteContextId = ? ORDER BY sortOrder ASC",
            (row["id"],),
        ).fetchall()
        objects_rows = self.db.execute(
            "SELECT * FROM site_objects WHERE siteContextId = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()
        analysis_row = self.db.execute(
            "SELECT * FROM site_analysis_results WHERE siteContextId = ? ORDER BY createdAt DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        import_row = self.db.execute(
            "SELECT * FROM site_import_logs WHERE siteContextId = ? ORDER BY createdAt DESC LIMIT 1",
            (row["id"],),
        ).fetchone()
        analysis_payload = (
            {
                "buildableArea": analysis_row["buildableArea"],
                "maxBuildingEnvelope": json.loads(analysis_row["maxBuildingEnvelopeJson"] or "null"),
                "preferredBuildingZone": json.loads(analysis_row["preferredBuildingZoneJson"] or "null"),
                "buildingCandidates": json.loads(analysis_row["buildingCandidatesJson"] or "[]"),
                "constraints": json.loads(analysis_row["constraintsJson"] or "[]"),
                "observations": json.loads(analysis_row["observationsJson"] or "[]"),
                "warnings": json.loads(analysis_row["warningsJson"] or "[]"),
                "notes": json.loads(analysis_row["notesJson"] or "[]"),
            }
            if analysis_row
            else json.loads(row["analysisResultJson"] or "{}")
        )
        import_payload = (
            {
                "status": import_row["status"],
                "objectsPerLayer": json.loads(import_row["objectsPerLayerJson"] or "{}"),
                "fetchedLayers": json.loads(import_row["fetchedLayersJson"] or "[]"),
                "emptyLayers": json.loads(import_row["emptyLayersJson"] or "[]"),
                "unavailableLayers": json.loads(import_row["unavailableLayersJson"] or "[]"),
                "partialErrors": json.loads(import_row["partialErrorsJson"] or "[]"),
            }
            if import_row
            else json.loads(row["importSummaryJson"] or "{}")
        )
        return {
            "id": row["id"],
            "projectId": row["projectId"],
            "primaryParcelId": row["primaryParcelId"],
            "siteBoundary": json.loads(row["siteBoundaryJson"]),
            "analysisBufferMeters": row["analysisBufferMeters"],
            "analysisResult": analysis_payload,
            "importSummary": import_payload,
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
            "layers": [
                {
                    "id": item["id"],
                    "projectId": item["projectId"],
                    "siteContextId": item["siteContextId"],
                    "layerKey": item["layerKey"],
                    "label": item["label"],
                    "status": item["status"],
                    "sourceType": item["sourceType"],
                    "visible": bool(item["visible"]),
                    "locked": bool(item["locked"]),
                    "geometryType": item["geometryType"],
                    "features": json.loads(item["featuresJson"] or "[]"),
                    "metadata": json.loads(item["metadataJson"] or "{}"),
                    "style": json.loads(item["styleJson"] or "{}"),
                    "sortOrder": item["sortOrder"],
                }
                for item in layers_rows
            ],
            "objects": [
                {
                    "id": item["id"],
                    "projectId": item["projectId"],
                    "siteContextId": item["siteContextId"],
                    "layerKey": item["layerKey"],
                    "objectType": item["objectType"],
                    "geometry": json.loads(item["geometryJson"]),
                    "bbox": json.loads(item["bboxJson"]) if item["bboxJson"] else None,
                    "centroid": json.loads(item["centroidJson"]) if item["centroidJson"] else None,
                    "sourceType": item["sourceType"],
                    "sourceName": item["sourceName"],
                    "sourceMetadata": json.loads(item["sourceMetadataJson"] or "{}"),
                    "confidence": item["confidence"],
                    "withinPlot": None if item["withinPlot"] is None else bool(item["withinPlot"]),
                    "withinSiteBoundary": None if item["withinSiteBoundary"] is None else bool(item["withinSiteBoundary"]),
                    "intersectsPlot": None if item["intersectsPlot"] is None else bool(item["intersectsPlot"]),
                    "properties": json.loads(item["propertiesJson"] or "{}"),
                }
                for item in objects_rows
            ],
        }

    def get_session_features(self, session_id: str) -> dict[str, Any]:
        rows = self.db.execute("SELECT layer, geom, props FROM map_features WHERE session_id = ?", (session_id,)).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["layer"], []).append({
                "type": "Feature",
                "geometry": json.loads(row["geom"]),
                "properties": json.loads(row["props"] or "{}"),
            })
        return grouped
