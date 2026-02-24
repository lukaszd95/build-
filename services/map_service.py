import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform as shp_transform
from shapely.validation import make_valid
try:
    from pyproj import Transformer
except Exception:
    Transformer = None


SEP_RE = re.compile(r"[.\-\\/]+")


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
    nr_main = str(int(main_raw or "0"))
    nr_sub = str(int(sub_raw or "0"))
    nr_canonical = f"{nr_main}/{nr_sub}" if nr_sub != "0" else nr_main
    obreb_canonical = f"{int((obreb or '0').strip() or '0'):04d}"
    miejsc = (miejscowosc or "").strip()
    miejsc_lower = miejsc.lower()
    miejsc_ascii = normalize_text_ascii(miejsc_lower)
    variants = [v for v in [miejsc, miejsc_lower, miejsc_ascii] if v]
    return {
        "nrMain": nr_main,
        "nrSub": nr_sub,
        "nrCanonical": nr_canonical,
        "obrebCanonical": obreb_canonical,
        "miejscowoscVariants": list(dict.fromkeys(variants)),
    }


def normalize_parcel_number(candidate: str) -> str:
    text = SEP_RE.sub("/", (candidate or "").strip().replace(" ", ""))
    if not text:
        return ""
    if "/" in text:
        a, b = text.split("/", 1)
        return f"{int(a or '0')}/{int(b or '0')}"
    return str(int(text or "0"))


@dataclass
class ProviderMeta:
    sourceName: str
    dataType: str
    licenseNote: str
    accuracyNote: str
    warnings: list[str]


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
        features = self._fetch_wfs_features(wfs, normalized)
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

    def _fetch_wfs_features(self, wfs: dict[str, Any], normalized: dict[str, Any]) -> list[dict[str, Any]]:
        url = wfs.get("url")
        if not url:
            raise RuntimeError("Brak konfiguracji WFS (url).")
        type_name = wfs.get("typeName")
        if not type_name:
            raise RuntimeError("Brak konfiguracji WFS (typeName).")
        params = {
            "service": "WFS",
            "request": "GetFeature",
            "outputFormat": "application/json",
            "typeName": type_name,
        }
        if wfs.get("version"):
            params["version"] = wfs["version"]
        if wfs.get("srsName"):
            params["srsName"] = wfs["srsName"]

        cql_filter = self._build_cql_filter(wfs.get("mapping", {}), normalized)
        if cql_filter:
            params["CQL_FILTER"] = cql_filter
        if wfs.get("maxFeatures"):
            params["maxFeatures"] = str(wfs["maxFeatures"])
        query = urllib.parse.urlencode(params, doseq=True)
        request_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
        try:
            with urllib.request.urlopen(request_url, timeout=wfs.get("timeout", 15)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"WFS zwrócił status {resp.status}.")
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Nie udało się pobrać danych WFS: {exc}") from exc
        return data.get("features", []) if isinstance(data, dict) else []

    def _build_cql_filter(self, mapping_cfg: dict[str, Any], normalized: dict[str, Any]) -> str:
        filters = []
        parcel_cfg = mapping_cfg.get("parcelNumber", {})
        parcel_type = parcel_cfg.get("type", "singleField")
        if parcel_type == "singleField" and parcel_cfg.get("field"):
            filters.append(f"{parcel_cfg['field']}='{normalized['nrCanonical']}'")
        elif parcel_type == "mainSubFields":
            main_field = parcel_cfg.get("mainField")
            sub_field = parcel_cfg.get("subField")
            if main_field:
                filters.append(f"{main_field}='{normalized['nrMain']}'")
            if sub_field and normalized.get("nrSub") is not None:
                filters.append(f"{sub_field}='{normalized['nrSub']}'")

        obreb_field = mapping_cfg.get("obreb", {}).get("field")
        if obreb_field:
            filters.append(f"{obreb_field}='{normalized['obrebCanonical']}'")

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
            if str(item.get("obreb", "")).zfill(4) == normalized["obrebCanonical"]:
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

        plot_geom_4326 = make_valid(shape(winner["geometry"]))
        buffer_m = float(payload.get("bufferMeters", 30))
        if Transformer is not None:
            to_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True).transform
            to_4326 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True).transform
            plot_2180 = shp_transform(to_2180, plot_geom_4326)
            buffer_geom_2180 = plot_2180.buffer(buffer_m)
            buffer_4326 = shp_transform(to_4326, buffer_geom_2180)
        else:
            # fallback approximation in degrees when pyproj is unavailable
            deg_buffer = buffer_m / 111_320.0
            buffer_4326 = plot_geom_4326.buffer(deg_buffer)
            buffer_geom_2180 = buffer_4326

        context_provider = ContextProvider(self.config.get("context", {}))
        context, context_meta = context_provider.fetch_context(buffer_geom_2180)
        util_provider = UtilitiesProvider(self.config.get("utilities", {}))
        util_data, util_meta = util_provider.fetch_utilities(buffer_geom_2180)

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
