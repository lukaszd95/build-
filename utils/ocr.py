import json
import re
import sqlite3
import time

from utils.db import create_timestamp
from utils.extraction_pipeline import detect_format, extract_text_from_image, extract_text_from_pdf
from services.location_extractor import extract_location
from utils.extraction_rules import (
    LOCALITY_DATE_REGEX,
    LOCALITY_IN_TEXT_REGEX,
    LOCALITY_POSTAL_REGEX,
    LOCALITY_REGEX,
    LOCALITY_STOPWORDS,
    STREET_REGEX,
)

STATUS_PATTERN = re.compile(r"\b(obowiązuje|zmiana|brak)\b", re.IGNORECASE)
ISSUE_SIGN_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:znak sprawy|sygn\.?|sygnatura)\s*[:\-]?\s*([A-Z0-9./-]{4,})",
    re.IGNORECASE,
)
ISSUE_SIGN_LINE_PATTERN = re.compile(
    r"(?m)^\s*([A-Z0-9]{1,8}(?:[-./][A-Z0-9]{1,12}){2,})\s*$",
    re.IGNORECASE,
)
ISSUE_DATE_PATTERN = re.compile(
    r"\b\d{1,2}\s+(?:stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|wrze\u015bnia|pa\u017adziernika|listopada|grudnia)\s+\d{4}\s*r?\.?",
    re.IGNORECASE,
)
ISSUED_FOR_PATTERN = re.compile(
    r"(?:wydany dla|dla)\s*[:\-]?\s*([^\n]{3,120})",
    re.IGNORECASE,
)
LEGAL_BASIS_PATTERN = re.compile(
    r"(uchwała[^,\n]+(?:nr|numer)?\s*[A-Za-z0-9./-]+[^,\n]*\d{4})",
    re.IGNORECASE,
)
TERRAIN_SYMBOL_PATTERN = re.compile(
    r"(?:symbol\s+terenu|przeznaczenie\s+terenu)\s*[:\-]?\s*([A-Z0-9/.-]{1,8})",
    re.IGNORECASE,
)
TERRAIN_LINE_PATTERN = re.compile(
    r"\b([A-Z]{1,3}(?:/[A-Z0-9]{1,3})?)\s*[–-]\s*([^\n]+)",
    re.IGNORECASE,
)
HEIGHT_PATTERN = re.compile(
    r"(?:maksymalna wysoko(?:ść|sc)|wysoko(?:ść|sc) zabudowy)[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)
ABOVE_GROUND_STOREYS_PATTERN = re.compile(
    r"(?:maksymalna liczba kondygnacji nadziemnych|"
    r"liczba kondygnacji nadziemnych)[^\d]{0,20}(\d+)",
    re.IGNORECASE,
)
BELOW_GROUND_STOREYS_PATTERN = re.compile(
    r"(?:maksymalna liczba kondygnacji podziemnych|"
    r"liczba kondygnacji podziemnych)[^\d]{0,20}(\d+)",
    re.IGNORECASE,
)
RIDGE_HEIGHT_PATTERN = re.compile(
    r"(?:maksymalna wysoko(?:ść|sc) kalenicy|wysoko(?:ść|sc) kalenicy)"
    r"[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)
EAVES_HEIGHT_PATTERN = re.compile(
    r"(?:maksymalna wysoko(?:ść|sc) okapu|wysoko(?:ść|sc) okapu)"
    r"[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)
INTENSITY_PATTERN = re.compile(
    r"intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)
MIN_INTENSITY_PATTERN = re.compile(
    r"(?:minimalna|min\.?)\s*intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)
MAX_INTENSITY_PATTERN = re.compile(
    r"(?:maksymalna|max\.?)\s*intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)
COVERAGE_PATTERN = re.compile(
    r"(?:maksymalna powierzchnia zabudowy|powierzchnia zabudowy)[^\d]{0,20}(\d+[,.]?\d*)\s*(%|m2|m²)",
    re.IGNORECASE,
)
BIO_PATTERN = re.compile(
    r"(?:minimalny|min\.?)?\s*(?:udział\s+)?"
    r"powierzchni[a]?\s+biologicznie\s+czynn(?:a|ej)"
    r"[^\d]{0,20}(\d+[,.]?\d*)\s*(%|m2|m²)",
    re.IGNORECASE,
)
MIN_FACADE_WIDTH_PATTERN = re.compile(
    r"(?:minimalna|min\.?)\s*szerokość elewacji frontowej[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)
MAX_FACADE_WIDTH_PATTERN = re.compile(
    r"(?:maksymalna|max\.?)\s*szerokość elewacji frontowej[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)
ROOF_PATTERN = re.compile(
    r"(dach\s+(?:dwuspadowy|wielospadowy|płaski|jednospadowy))",
    re.IGNORECASE,
)
LINE_PATTERN = re.compile(
    r"(linie zabudowy[^\n]+)",
    re.IGNORECASE,
)
PARKING_PATTERN = re.compile(
    r"(miejsc[ae]\s+postojow[ey]ch[^\n]+|parking[^\n]+)",
    re.IGNORECASE,
)
PROHIBITIONS_PATTERN = re.compile(
    r"(zakaz[^\n\.]+|nie dopuszcza się[^\n\.]+)",
    re.IGNORECASE,
)
PROTECTION_PATTERN = re.compile(
    r"(strefa ochron[^\n\.]+|obszar ochron[^\n\.]+)",
    re.IGNORECASE,
)
PRIMARY_USE_PATTERN = re.compile(
    r"przeznaczenie podstawowe[^\n]*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
SECONDARY_USE_PATTERN = re.compile(
    r"przeznaczenie dopuszczalne[^\n]*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
COMBINE_PATTERN = re.compile(
    r"(?:możliwość|mozliwosc)\s+łączenia\s+funkcji[^\n]*[:\-]?\s*(tak|nie)",
    re.IGNORECASE,
)
OBREB_PATTERN = re.compile(
    r"obr[eę]b(?:u|ie)?(?:\s+ewidencyjn(?:y|ego))?\s*(?:nr|numer)?\s*([0-9A-Za-z./-]+)",
    re.IGNORECASE,
)
GMINA_PATTERN = re.compile(
    r"(?:gmina|gm\.?)\s*[:\-]?\s*([A-Za-zÀ-ÿ0-9 .'-]+)",
    re.IGNORECASE,
)


def _parse_number(raw_value):
    if raw_value is None:
        return None
    value = raw_value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _match_first(pattern, text):
    if not text:
        return None
    match = pattern.search(text)
    return match


def _extract_first_group(pattern, text):
    match = _match_first(pattern, text)
    if not match:
        return None
    return match.group(1).strip()


def _combine_obreb_gmina(text):
    obreb = _clean_value(_extract_first_group(OBREB_PATTERN, text))
    gmina = _clean_value(_extract_first_group(GMINA_PATTERN, text))
    if obreb and gmina:
        return f"Obręb {obreb}, Gmina {gmina}"
    if obreb:
        return f"Obręb {obreb}"
    if gmina:
        return f"Gmina {gmina}"
    return None


def _clean_value(value):
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = re.sub(r"[,:;.)]+$", "", cleaned).strip()
    return cleaned or None


def _extract_street(text):
    match = _match_first(STREET_REGEX, text)
    if match:
        return _clean_value(match.group(1))
    return None


def _extract_locality(text):
    match = _match_first(LOCALITY_REGEX, text)
    if match:
        return _clean_value(match.group(1))
    match = _match_first(LOCALITY_POSTAL_REGEX, text)
    if match:
        return _clean_value(match.group(1))
    match = _match_first(LOCALITY_DATE_REGEX, text)
    if match:
        return _clean_value(match.group(1))
    match = _match_first(LOCALITY_IN_TEXT_REGEX, text)
    if match:
        candidate = _clean_value(match.group(1))
        if candidate and candidate.lower() not in LOCALITY_STOPWORDS:
            return candidate
    return None




def _extract_issue_date(text):
    match = _match_first(ISSUE_DATE_PATTERN, text)
    if not match:
        return None
    return _clean_value(match.group(0))


def _extract_issue_sign(text):
    labeled = _extract_first_group(ISSUE_SIGN_PATTERN, text)
    if labeled:
        return _clean_value(labeled)

    head = (text or "")[:1600]
    candidates = []
    for match in ISSUE_SIGN_LINE_PATTERN.finditer(head):
        token = _clean_value(match.group(1))
        if not token:
            continue
        has_digit = any(ch.isdigit() for ch in token)
        has_letter = any(ch.isalpha() for ch in token)
        if has_digit and has_letter:
            candidates.append(token)
    if candidates:
        return candidates[0]
    return None



def _extract_symbol(text):
    match = _match_first(TERRAIN_SYMBOL_PATTERN, text)
    if match:
        return match.group(1).upper()
    match = _match_first(TERRAIN_LINE_PATTERN, text)
    if match:
        return match.group(1).upper()
    return None


def _extract_terrain_description(text):
    match = _match_first(TERRAIN_LINE_PATTERN, text)
    if match:
        return match.group(2).strip()
    return None


def _extract_status(text):
    match = _match_first(STATUS_PATTERN, text)
    if match:
        return match.group(1).lower()
    return None


def run_document_ocr(document, db_path, parcel_id="_global"):
    time.sleep(0.8)
    format_type = detect_format(document["fileName"], document["mimeType"])
    if format_type == "pdf":
        pages = extract_text_from_pdf(document["fileUrl"])
    elif format_type == "image":
        pages = extract_text_from_image(document["fileUrl"])
    else:
        pages = [{"page": 1, "text": ""}]

    full_text = " ".join(page["text"] for page in pages if page.get("text"))
    location = extract_location(pages)
    parcel_numbers = location.get("parcel_numbers") or []
    parcel_id_value = parcel_numbers[0] if parcel_numbers else None
    obreb_gmina = location.get("precinct")
    street_value = location.get("street")
    locality_value = location.get("city")
    issue_sign = _extract_issue_sign(full_text)
    issue_date = _extract_issue_date(full_text)
    issued_for = _extract_first_group(ISSUED_FOR_PATTERN, full_text)
    symbol_mpzp = _extract_symbol(full_text)
    status = _extract_status(full_text)
    legal_basis = _extract_first_group(LEGAL_BASIS_PATTERN, full_text)
    primary_use = _extract_first_group(PRIMARY_USE_PATTERN, full_text)
    secondary_use = _extract_first_group(SECONDARY_USE_PATTERN, full_text)
    prohibitions = _extract_first_group(PROHIBITIONS_PATTERN, full_text)
    combine = _extract_first_group(COMBINE_PATTERN, full_text)
    symbol_terrain = symbol_mpzp
    height_match = _match_first(HEIGHT_PATTERN, full_text)
    height_value = _parse_number(height_match.group(1)) if height_match else None
    above_storeys_match = _match_first(ABOVE_GROUND_STOREYS_PATTERN, full_text)
    above_storeys_value = int(above_storeys_match.group(1)) if above_storeys_match else None
    below_storeys_match = _match_first(BELOW_GROUND_STOREYS_PATTERN, full_text)
    below_storeys_value = int(below_storeys_match.group(1)) if below_storeys_match else None
    ridge_height_match = _match_first(RIDGE_HEIGHT_PATTERN, full_text)
    ridge_height_value = _parse_number(ridge_height_match.group(1)) if ridge_height_match else None
    eaves_height_match = _match_first(EAVES_HEIGHT_PATTERN, full_text)
    eaves_height_value = _parse_number(eaves_height_match.group(1)) if eaves_height_match else None
    min_intensity_value = _parse_number(
        _extract_first_group(MIN_INTENSITY_PATTERN, full_text)
    )
    max_intensity_value = _parse_number(
        _extract_first_group(MAX_INTENSITY_PATTERN, full_text)
    )
    intensity_value = _parse_number(
        _extract_first_group(INTENSITY_PATTERN, full_text)
    )
    if max_intensity_value is None:
        max_intensity_value = intensity_value
    coverage_match = _match_first(COVERAGE_PATTERN, full_text)
    coverage_value = _parse_number(coverage_match.group(1)) if coverage_match else None
    bio_match = _match_first(BIO_PATTERN, full_text)
    bio_value = _parse_number(bio_match.group(1)) if bio_match else None
    min_facade_width_match = _match_first(MIN_FACADE_WIDTH_PATTERN, full_text)
    min_facade_width_value = (
        _parse_number(min_facade_width_match.group(1)) if min_facade_width_match else None
    )
    max_facade_width_match = _match_first(MAX_FACADE_WIDTH_PATTERN, full_text)
    max_facade_width_value = (
        _parse_number(max_facade_width_match.group(1)) if max_facade_width_match else None
    )
    line_value = _extract_first_group(LINE_PATTERN, full_text)
    roof_value = _extract_first_group(ROOF_PATTERN, full_text)
    parking_value = _extract_first_group(PARKING_PATTERN, full_text)
    protection_value = _extract_first_group(PROTECTION_PATTERN, full_text)
    terrain_desc = _extract_terrain_description(full_text)

    fields = {
        "znak_sprawy": _clean_value(issue_sign),
        "data_wydania": issue_date,
        "wydany_dla": _clean_value(issued_for),
        "numer_dzialki": parcel_id_value,
        "numery_dzialek": parcel_numbers,
        "obreb_gmina": obreb_gmina,
        "ulica": street_value,
        "miejscowosc": locality_value,
        "symbol_terenu_mpzp": symbol_mpzp,
        "status_planu": status,
        "podstawa_prawna": legal_basis,
        "przeznaczenie_podstawowe": primary_use or terrain_desc,
        "przeznaczenie_dopuszczalne": secondary_use,
        "funkcje_zakazane": prohibitions,
        "mozliwosc_laczenia_funkcji": combine,
        "symbol_terenu": symbol_terrain,
        "max_wysokosc": {"value": height_value, "unit": "m"} if height_value else None,
        "max_liczba_kondygnacji_nadziemnych": above_storeys_value,
        "max_liczba_kondygnacji_podziemnych": below_storeys_value,
        "max_wysokosc_kalenicy": ridge_height_value,
        "max_wysokosc_okapu": eaves_height_value,
        "min_intensywnosc": min_intensity_value,
        "max_intensywnosc": max_intensity_value,
        "max_pow_zabudowy": coverage_value,
        "min_pow_biol_czynna": bio_value,
        "min_szerokosc_elewacji_frontowej": min_facade_width_value,
        "max_szerokosc_elewacji_frontowej": max_facade_width_value,
        "linie_zabudowy": line_value,
        "dach_typ": roof_value,
        "parking_wymagania": parking_value,
        "strefy_ograniczenia": protection_value,
        "notatki": "; ".join(location.get("notes") or []) or None,
        "evidence": location.get("evidence") or {},
        "location_confidence": location.get("confidence"),
    }

    confidence = {
        key: 0.7 if value else 0.0 for key, value in fields.items()
    }

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute(
        """
        INSERT INTO document_extracted_data (documentId, parcelId, fieldsJson, source, updatedAt, ocrConfidenceJson)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(documentId, parcelId)
        DO UPDATE SET fieldsJson = excluded.fieldsJson,
                      source = excluded.source,
                      updatedAt = excluded.updatedAt,
                      ocrConfidenceJson = excluded.ocrConfidenceJson
        """,
        (
            document["id"],
            parcel_id,
            json.dumps(fields),
            json.dumps({"source": "ocr"}),
            create_timestamp(),
            json.dumps(confidence),
        ),
    )
    db.execute(
        "UPDATE documents SET ocrStatus = ?, status = ? WHERE id = ?",
        ("DONE", "READY", document["id"]),
    )
    db.commit()
