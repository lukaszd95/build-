from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any


@dataclass
class WfsDiagnostics:
    request_url: str = ""
    method: str = "GET"
    query_params: dict[str, Any] | None = None
    status_code: int | None = None
    content_type: str = ""
    detected_format: str = "unknown"
    parser_used: str = "none"
    body_snippet: str = ""
    error_type: str = ""
    error_message: str = ""


class WfsServiceError(RuntimeError):
    def __init__(self, *, error_type: str, user_message: str, technical_message: str = "", diagnostics: WfsDiagnostics | None = None):
        super().__init__(technical_message or user_message)
        self.error_type = error_type
        self.user_message = user_message
        self.technical_message = technical_message or user_message
        self.diagnostics = diagnostics


_GML_NS = "{http://www.opengis.net/gml}"
_GML32_NS = "{http://www.opengis.net/gml/3.2}"


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def detect_wfs_response_format(response_headers: Any, response_body: str) -> str:
    body = (response_body or "").strip()
    content_type = str(getattr(response_headers, "get", lambda _k, _d="": "")("Content-Type", "") or "").lower()

    if not body:
        return "empty"
    if body.startswith("{") or body.startswith("["):
        return "geojson" if "geojson" in content_type else "json"
    body_head = body[:300].lower()
    if "<html" in body_head or "<!doctype html" in body_head:
        return "html"
    if body.startswith("<"):
        if any(token in body_head for token in ["exceptionreport", "serviceexceptionreport", "ows:exceptionreport"]):
            return "xml_exception"
        if any(token in content_type for token in ["gml", "xml"]) or re.search(r"<\w+:featurecollection|<featurecollection", body_head):
            if "gml" in body_head or "featuremember" in body_head or "featurecollection" in body_head:
                return "gml_xml"
            return "xml"
        return "xml"
    if "json" in content_type:
        return "json"
    return "unknown"


def parse_wfs_payload(*, response_headers: Any, response_body: str, diagnostics: WfsDiagnostics | None = None) -> dict[str, Any]:
    fmt = detect_wfs_response_format(response_headers, response_body)
    if diagnostics is not None:
        diagnostics.detected_format = fmt

    body = (response_body or "").strip()
    if not body:
        raise WfsServiceError(error_type="empty_response", user_message="WFS zwrócił pusty wynik.", diagnostics=diagnostics)

    if fmt in {"json", "geojson"}:
        try:
            parsed = json.loads(body)
        except Exception as exc:
            raise WfsServiceError(
                error_type="invalid_json",
                user_message="Źródło danych zwróciło niepoprawny JSON.",
                technical_message=str(exc),
                diagnostics=diagnostics,
            ) from exc
        if diagnostics is not None:
            diagnostics.parser_used = "json"
        if isinstance(parsed, dict) and parsed.get("features") is not None:
            return parsed
        raise WfsServiceError(
            error_type="missing_features",
            user_message="WFS zwrócił odpowiedź bez kolekcji obiektów.",
            diagnostics=diagnostics,
        )

    if fmt == "html":
        raise WfsServiceError(
            error_type="html_response",
            user_message="WFS odpowiedział HTML zamiast danych przestrzennych.",
            diagnostics=diagnostics,
        )

    if fmt in {"xml", "gml_xml", "xml_exception"}:
        try:
            root = ET.fromstring(body)
        except Exception as exc:
            raise WfsServiceError(
                error_type="invalid_xml",
                user_message="Źródło danych zwróciło niepoprawny XML.",
                technical_message=str(exc),
                diagnostics=diagnostics,
            ) from exc
        root_name = _local_name(root.tag).lower()
        if "exceptionreport" in root_name or "serviceexceptionreport" in root_name:
            error_code, error_text = _parse_exception(root)
            message = f"WFS zwrócił błąd usługi: {error_text or error_code or 'nieznany błąd'}"
            raise WfsServiceError(
                error_type="service_exception",
                user_message=message,
                technical_message=f"code={error_code} message={error_text}",
                diagnostics=diagnostics,
            )

        if diagnostics is not None:
            diagnostics.parser_used = "xml_gml"
        return _parse_feature_collection_xml(root)

    raise WfsServiceError(
        error_type="unsupported_response_format",
        user_message="Źródło danych zwróciło nieoczekiwaną odpowiedź.",
        diagnostics=diagnostics,
    )


def _parse_exception(root: ET.Element) -> tuple[str, str]:
    code = ""
    text = ""
    for elem in root.iter():
        name = _local_name(elem.tag).lower()
        if name in {"exception", "serviceexception"}:
            code = code or elem.attrib.get("exceptionCode") or elem.attrib.get("code") or elem.attrib.get("locator") or ""
            if (elem.text or "").strip():
                text = text or (elem.text or "").strip()
        if name in {"exceptiontext", "serviceexception"} and (elem.text or "").strip():
            text = text or (elem.text or "").strip()
    return code, text


def _parse_feature_collection_xml(root: ET.Element) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for member in root.findall(".//{*}featureMember") + root.findall(".//{*}member"):
        for feature_elem in list(member):
            feature = _parse_xml_feature(feature_elem)
            if feature:
                features.append(feature)

    if not features:
        for feature_elem in root.findall(".//{*}featureMembers/{*}*"):
            feature = _parse_xml_feature(feature_elem)
            if feature:
                features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def _parse_xml_feature(feature_elem: ET.Element) -> dict[str, Any] | None:
    props: dict[str, Any] = {}
    geometry = None
    for child in list(feature_elem):
        lname = _local_name(child.tag).lower()
        if lname in {"boundedby", "geometryproperty", "shape"}:
            geom_candidate = _extract_geometry(child)
            geometry = geometry or geom_candidate
            continue
        geom_candidate = _extract_geometry(child)
        if geom_candidate is not None:
            geometry = geometry or geom_candidate
            continue
        value = _extract_text_value(child)
        if value is not None:
            props[_local_name(child.tag)] = value

    fid = feature_elem.attrib.get(f"{_GML32_NS}id") or feature_elem.attrib.get(f"{_GML_NS}id") or feature_elem.attrib.get("fid")
    return {"type": "Feature", "id": fid, "properties": props, "geometry": geometry} if geometry else None


def _extract_text_value(elem: ET.Element) -> str | None:
    if list(elem):
        return None
    text = (elem.text or "").strip()
    return text if text else None


def _extract_geometry(elem: ET.Element) -> dict[str, Any] | None:
    for geom in elem.iter():
        lname = _local_name(geom.tag)
        if lname in {"Polygon", "MultiSurface", "MultiPolygon"}:
            parsed = _parse_polygon_like(geom)
            if parsed:
                return parsed
    return None


def _parse_polygon_like(geom: ET.Element) -> dict[str, Any] | None:
    polygons: list[list[list[float]]] = []
    for poly in ([geom] if _local_name(geom.tag) == "Polygon" else [e for e in geom.iter() if _local_name(e.tag) == "Polygon"]):
        ring = _extract_ring(poly)
        if ring:
            polygons.append(ring)
    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": [polygons[0]]}
    return {"type": "MultiPolygon", "coordinates": [[[ring] for ring in polygons]][0]}


def _extract_ring(poly: ET.Element) -> list[list[float]] | None:
    pos_list = None
    for elem in poly.iter():
        if _local_name(elem.tag) == "posList" and (elem.text or "").strip():
            pos_list = (elem.text or "").strip()
            break
        if _local_name(elem.tag) == "coordinates" and (elem.text or "").strip():
            pairs = []
            for pair in (elem.text or "").strip().split():
                xy = pair.split(",")
                if len(xy) >= 2:
                    pairs.append([float(xy[0]), float(xy[1])])
            return pairs if len(pairs) >= 4 else None
    if not pos_list:
        return None
    nums = [float(n) for n in pos_list.split() if n]
    dims = 2
    srs_dim = next((el.attrib.get("srsDimension") for el in poly.iter() if el.attrib.get("srsDimension")), None)
    if srs_dim and srs_dim.isdigit():
        dims = max(2, int(srs_dim))
    coords: list[list[float]] = []
    for i in range(0, len(nums), dims):
        chunk = nums[i : i + dims]
        if len(chunk) >= 2:
            coords.append([chunk[0], chunk[1]])
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords
