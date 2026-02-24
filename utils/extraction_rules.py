import re


FIELD_DEFINITIONS = [
    {"fieldKey": "terrainSymbol"},
    {"fieldKey": "terrainDescription"},
    {"fieldKey": "primaryPurpose"},
    {"fieldKey": "allowedPurpose"},
    {"fieldKey": "forbiddenPurpose"},
    {"fieldKey": "maxBuildingHeightM", "unit": "m"},
    {"fieldKey": "maxAboveGroundStoreys"},
    {"fieldKey": "maxBelowGroundStoreys"},
    {"fieldKey": "maxRidgeHeightM", "unit": "m"},
    {"fieldKey": "maxEavesHeightM", "unit": "m"},
    {"fieldKey": "minBuildingIntensity"},
    {"fieldKey": "maxBuildingIntensity"},
    {"fieldKey": "maxStoreys"},
    {"fieldKey": "buildingIntensity"},
    {"fieldKey": "maxBuildingCoveragePctOrM2"},
    {"fieldKey": "minBiologicallyActivePct", "unit": "%"},
    {"fieldKey": "roofType"},
    {"fieldKey": "roofAngleDeg", "unit": "°"},
    {"fieldKey": "facadeMaterials"},
    {"fieldKey": "coloring"},
    {"fieldKey": "minParcelAreaM2", "unit": "m"},
    {"fieldKey": "minFrontWidthM", "unit": "m"},
    {"fieldKey": "minFacadeWidthM", "unit": "m"},
    {"fieldKey": "maxFacadeWidthM", "unit": "m"},
    {"fieldKey": "allowedDevelopmentType"},
    {"fieldKey": "protectionZones"},
    {"fieldKey": "noiseLandscapeRestrictions"},
    {"fieldKey": "prohibitions"},
]

FIELD_KEYS = [field["fieldKey"] for field in FIELD_DEFINITIONS]

PARCEL_REGEX = re.compile(
    r"(?:"
    r"(?:działk[ai]|dz\.?)\s*(?:nr|numer)?\s*"
    r"(?:ew\.?|ewid\.?|ewidencyjn(?:a|ej|y|ego))?\s*(?:nr|numer)?\s*"
    r"|(?:nr|numer)\s*(?:działk[ai]|dz\.?)\s*"
    r"(?:ew\.?|ewid\.?|ewidencyjn(?:a|ej|y|ego))?\s*"
    r")"
    r"([0-9A-Za-z./-]+)",
    re.IGNORECASE,
)
OBREB_REGEX = re.compile(
    r"(?:"
    r"(?:obr[eę]b(?:u|ie)?|obr\.)\s*"
    r"(?:(?:ewidencyjn|geodezyjn)(?:y|ego))?\s*(?:nr|numer)?\s*"
    r"|(?:nr|numer)\s*(?:obr[eę]b(?:u|ie)?|obr\.)\s*"
    r"(?:(?:ewidencyjn|geodezyjn)(?:y|ego))?\s*"
    r")"
    r"([0-9A-Za-z./-]+)",
    re.IGNORECASE,
)
STREET_REGEX = re.compile(
    r"(?:\b(?:ul|al|pl|os)\b\.?|\b(?:ulica|aleja|plac|osiedle)\b)"
    r"\s*[:\-]?\s*([A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]+?)"
    r"(?=\s*(?:,|\n|$|\b\d{2}-\d{3}\b|\bw\s+dzielnic\w*\b|\b(?:miejscowość|miejscowosc|miasto|gm\.|gmina|obr[eę]b)\b))",
    re.IGNORECASE,
)
LOCALITY_REGEX = re.compile(
    r"(?:\bmiejscowość\b|\bmiejscowosc\b|\bmiasto\b|\bm\.|\bgm\.|\bgmina\b)"
    r"\s*[:\-]?\s*([A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]+?)"
    r"(?=\s*(?:,|\n|$|\b\d{2}-\d{3}\b|\b(?:ul|al|pl|os|ulica|aleja|plac|osiedle|obr[eę]b)\b))",
    re.IGNORECASE,
)
ADDRESS_LOCALITY_REGEX = re.compile(
    r"(?:adres|siedziba)\s*[:\-]?\s*[^,\n]+,\s*([A-Za-zÀ-ÿ0-9 .'-]+)",
    re.IGNORECASE,
)
LOCALITY_DATE_REGEX = re.compile(
    r"([A-Za-zÀ-ÿ0-9 .'-]+)\s*,\s*(?:dn\.?|dnia)\s*\d{1,2}",
    re.IGNORECASE,
)
LOCALITY_POSTAL_REGEX = re.compile(
    r"\b\d{2}-\d{3}\s+([A-Za-zÀ-ÿ0-9 .'-]+)",
    re.IGNORECASE,
)
LOCALITY_IN_TEXT_REGEX = re.compile(
    r"(?:w\s+dzielnicy\s+[A-Za-zÀ-ÿ0-9 .'-]+\s+)?w\s+([A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿ0-9 .'-]+)",
    re.IGNORECASE,
)

LOCALITY_STOPWORDS = {
    "sprawie",
    "zakresie",
    "dniu",
    "dnia",
    "związku",
    "obszarze",
    "granicach",
    "mieście",
}

TERRAIN_REGEX = re.compile(
    r"(?:przeznaczenie terenu[:\s]+)?([A-Z]{1,3})\s*[–-]\s*([^\n]+)",
    re.IGNORECASE,
)
PRIMARY_PURPOSE_REGEX = re.compile(
    r"przeznaczenie podstawowe[^\n]*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
ALLOWED_PURPOSE_REGEX = re.compile(
    r"przeznaczenie dopuszczalne[^\n]*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
FORBIDDEN_PURPOSE_REGEX = re.compile(
    r"(?:przeznaczenie zakazane|funkcje zakazane)[^\n]*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)

HEIGHT_REGEX = re.compile(
    r"(?:maksymaln(?:a|ą)\s+wysoko(?:ść|sc)\s+zabudowy|wysoko(?:ść|sc)\s+zabudowy)"
    r"[^\d]{0,80}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

ABOVE_GROUND_STOREYS_REGEX = re.compile(
    r"(?:maksymalna liczba kondygnacji nadziemnych|"
    r"liczba kondygnacji nadziemnych)[^\d]{0,20}(\d+)",
    re.IGNORECASE,
)

BELOW_GROUND_STOREYS_REGEX = re.compile(
    r"(?:maksymalna liczba kondygnacji podziemnych|"
    r"liczba kondygnacji podziemnych)[^\d]{0,20}(\d+)",
    re.IGNORECASE,
)

RIDGE_HEIGHT_REGEX = re.compile(
    r"(?:maksymaln(?:a|ą)\s+wysoko(?:ść|sc)\s+kalenicy|wysoko(?:ść|sc)\s+kalenicy)"
    r"[^\d]{0,80}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

EAVES_HEIGHT_REGEX = re.compile(
    r"(?:maksymaln(?:a|ą)\s+wysoko(?:ść|sc)\s+okapu|wysoko(?:ść|sc)\s+okapu)"
    r"[^\d]{0,80}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

STOREYS_REGEX = re.compile(
    r"(?:maksymalna liczba kondygnacji|liczba kondygnacji)[^\d]{0,20}(\d+)",
    re.IGNORECASE,
)

INTENSITY_REGEX = re.compile(
    r"intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)

MIN_INTENSITY_REGEX = re.compile(
    r"(?:minimalna|min\.?)\s*intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)

MAX_INTENSITY_REGEX = re.compile(
    r"(?:maksymalna|max\.?)\s*intensywność zabudowy[^\d]{0,20}(\d+[,.]?\d*)",
    re.IGNORECASE,
)

COVERAGE_REGEX = re.compile(
    r"(?:maksymalna powierzchnia zabudowy|powierzchnia zabudowy)[^\d]{0,20}(\d+[,.]?\d*)\s*(%|m2|m²)",
    re.IGNORECASE,
)

BIO_REGEX = re.compile(
    r"(?:minimalny|min\.?)?\s*(?:udział\s+)?"
    r"powierzchni[a]?\s+biologicznie\s+czynn(?:a|ej)"
    r"[^\d]{0,20}(\d+[,.]?\d*)\s*(%)",
    re.IGNORECASE,
)

ROOF_TYPE_REGEX = re.compile(
    r"(dach\s+(?:dwuspadowy|wielospadowy|płaski|jednospadowy))",
    re.IGNORECASE,
)

ROOF_ANGLE_REGEX = re.compile(
    r"kąt nachylenia[^\d]{0,20}(\d+[,.]?\d*)\s*(°|stopni)",
    re.IGNORECASE,
)

MIN_PARCEL_AREA_REGEX = re.compile(
    r"minimalna powierzchnia działki[^\d]{0,20}(\d+[,.]?\d*)\s*(m2|m²)",
    re.IGNORECASE,
)

MIN_FRONT_WIDTH_REGEX = re.compile(
    r"minimalna szerokość frontu[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

MIN_FACADE_WIDTH_REGEX = re.compile(
    r"(?:minimalna|min\.?)\s*szerokość elewacji frontowej[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

MAX_FACADE_WIDTH_REGEX = re.compile(
    r"(?:maksymalna|max\.?)\s*szerokość elewacji frontowej[^\d]{0,20}(\d+[,.]?\d*)\s*(m)",
    re.IGNORECASE,
)

DEV_TYPE_REGEX = re.compile(
    r"zabudowa\s+(wolnostojąca|bliźniacza|szeregowa)",
    re.IGNORECASE,
)

PROHIBITIONS_REGEX = re.compile(
    r"(zakaz[^\n\.]+|nie dopuszcza się[^\n\.]+)",
    re.IGNORECASE,
)

PROTECTION_REGEX = re.compile(
    r"(strefa ochron[^\n\.]+|obszar ochron[^\n\.]+)",
    re.IGNORECASE,
)

NOISE_REGEX = re.compile(
    r"(hałas[^\n\.]+|krajobraz[^\n\.]+)",
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


def validate_unit_presence(raw_text, unit):
    if not unit:
        return True
    if not raw_text:
        return False
    return unit in raw_text


def _clean_value(value):
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = re.sub(r"[,:;.)]+$", "", cleaned).strip()
    return cleaned or None


def extract_parcel_refs(pages):
    results = []
    for page in pages:
        text = page["text"]
        for match in PARCEL_REGEX.finditer(text):
            parcel_id = _clean_value(match.group(1))
            if not parcel_id:
                continue
            raw_text = match.group(0)
            results.append(
                {"parcelId": parcel_id, "rawText": raw_text, "page": page["page"]}
            )
    return results


def extract_obreb_refs(pages):
    results = []
    for page in pages:
        text = page["text"]
        for match in OBREB_REGEX.finditer(text):
            obreb = _clean_value(match.group(1))
            if not obreb:
                continue
            raw_text = match.group(0)
            results.append(
                {"obreb": obreb, "rawText": raw_text, "page": page["page"]}
            )
    return results


def extract_street_refs(pages):
    results = []
    for page in pages:
        text = page["text"]
        matches = []
        for match in STREET_REGEX.finditer(text):
            street = _clean_value(match.group(1))
            if not street:
                continue
            raw_text = match.group(0)
            line_start = text.rfind("\n", 0, match.start())
            line_end = text.find("\n", match.end())
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            if line_end == -1:
                line_end = len(text)
            line = text[line_start:line_end]
            priority = 0
            if re.search(r"\badres\b", line, re.IGNORECASE):
                priority = 2
            elif re.search(r"\bpołożon\w*\b|\bpolozon\w*\b|\bprzy\b", line, re.IGNORECASE):
                priority = 1
            matches.append(
                {
                    "street": street,
                    "rawText": raw_text,
                    "page": page["page"],
                    "_priority": priority,
                    "_pos": match.start(),
                }
            )
        matches.sort(key=lambda item: (-item["_priority"], item["_pos"]))
        for match in matches:
            match.pop("_priority", None)
            match.pop("_pos", None)
            results.append(match)
    return results


def extract_locality_refs(pages):
    results = []
    for page in pages:
        text = page["text"]
        matches = []
        for match in LOCALITY_REGEX.finditer(text):
            locality = _clean_value(match.group(1))
            if not locality:
                continue
            raw_text = match.group(0)
            label_text = raw_text.lower()
            if "miejscow" in label_text or "miasto" in label_text:
                priority = 2
            elif re.search(r"\bm\.", label_text):
                priority = 1
            else:
                priority = 0
            matches.append(
                {
                    "locality": locality,
                    "rawText": raw_text,
                    "page": page["page"],
                    "_priority": priority,
                    "_pos": match.start(),
                }
            )
        matches.sort(key=lambda item: (-item["_priority"], item["_pos"]))
        for match in matches:
            match.pop("_priority", None)
            match.pop("_pos", None)
            results.append(match)
        if not results:
            match = ADDRESS_LOCALITY_REGEX.search(text)
            if match:
                locality = _clean_value(match.group(1))
                if locality:
                    results.append(
                        {
                            "locality": locality,
                            "rawText": match.group(0),
                            "page": page["page"],
                        }
                    )
                    continue
            match = LOCALITY_POSTAL_REGEX.search(text)
            if match:
                locality = _clean_value(match.group(1))
                if locality:
                    results.append(
                        {
                            "locality": locality,
                            "rawText": match.group(0),
                            "page": page["page"],
                        }
                    )
            else:
                match = LOCALITY_DATE_REGEX.search(text)
                if match:
                    locality = _clean_value(match.group(1))
                    if locality:
                        results.append(
                            {
                                "locality": locality,
                                "rawText": match.group(0),
                                "page": page["page"],
                            }
                        )
                else:
                    match = LOCALITY_IN_TEXT_REGEX.search(text)
                    if match:
                        locality = _clean_value(match.group(1))
                        if locality and locality.lower() not in LOCALITY_STOPWORDS:
                            results.append(
                                {
                                    "locality": locality,
                                    "rawText": match.group(0),
                                    "page": page["page"],
                                }
                            )
    return results


def _match_first(regex, pages):
    for page in pages:
        match = regex.search(page["text"])
        if match:
            return page["page"], match
    return None, None


def extract_fields_from_pages(pages):
    results = []

    page, match = _match_first(TERRAIN_REGEX, pages)
    if match:
        symbol = match.group(1).upper()
        desc = match.group(2).strip()
        raw = match.group(0)
        results.append(
            _build_field(
                "terrainSymbol",
                symbol,
                raw,
                page,
                confidence=0.9,
                unit=None,
            )
        )
        results.append(
            _build_field(
                "terrainDescription",
                desc,
                raw,
                page,
                confidence=0.88,
                unit=None,
            )
        )

    for regex, field_key, confidence in [
        (PRIMARY_PURPOSE_REGEX, "primaryPurpose", 0.86),
        (ALLOWED_PURPOSE_REGEX, "allowedPurpose", 0.84),
        (FORBIDDEN_PURPOSE_REGEX, "forbiddenPurpose", 0.8),
    ]:
        page, match = _match_first(regex, pages)
        if match:
            raw = match.group(0)
            value = _clean_value(match.group(1))
            results.append(
                _build_field(
                    field_key,
                    value,
                    raw,
                    page,
                    confidence=confidence,
                    unit=None,
                )
            )

    page, match = _match_first(HEIGHT_REGEX, pages)
    if match:
        value = _parse_number(match.group(1))
        raw = match.group(0)
        results.append(
            _build_field(
                "maxBuildingHeightM",
                value,
                raw,
                page,
                confidence=0.9,
                unit="m",
            )
        )

    page, match = _match_first(ABOVE_GROUND_STOREYS_REGEX, pages)
    if match:
        raw = match.group(0)
        value = int(match.group(1))
        results.append(
            _build_field(
                "maxAboveGroundStoreys",
                value,
                raw,
                page,
                confidence=0.86,
                unit=None,
            )
        )

    page, match = _match_first(BELOW_GROUND_STOREYS_REGEX, pages)
    if match:
        raw = match.group(0)
        value = int(match.group(1))
        results.append(
            _build_field(
                "maxBelowGroundStoreys",
                value,
                raw,
                page,
                confidence=0.84,
                unit=None,
            )
        )

    page, match = _match_first(RIDGE_HEIGHT_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "maxRidgeHeightM",
                value,
                raw,
                page,
                confidence=0.84,
                unit="m",
            )
        )

    page, match = _match_first(EAVES_HEIGHT_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "maxEavesHeightM",
                value,
                raw,
                page,
                confidence=0.84,
                unit="m",
            )
        )

    page, match = _match_first(STOREYS_REGEX, pages)
    if match:
        raw = match.group(0)
        value = int(match.group(1))
        results.append(
            _build_field(
                "maxStoreys",
                value,
                raw,
                page,
                confidence=0.88,
                unit=None,
            )
        )

    page, match = _match_first(MIN_INTENSITY_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "minBuildingIntensity",
                value,
                raw,
                page,
                confidence=0.82,
                unit=None,
            )
        )

    page, match = _match_first(MAX_INTENSITY_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "maxBuildingIntensity",
                value,
                raw,
                page,
                confidence=0.82,
                unit=None,
            )
        )
    else:
        page, match = _match_first(INTENSITY_REGEX, pages)
        if match:
            raw = match.group(0)
            value = _parse_number(match.group(1))
            results.append(
                _build_field(
                    "maxBuildingIntensity",
                    value,
                    raw,
                    page,
                    confidence=0.8,
                    unit=None,
                )
            )

    page, match = _match_first(INTENSITY_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "buildingIntensity",
                value,
                raw,
                page,
                confidence=0.84,
                unit=None,
            )
        )

    page, match = _match_first(COVERAGE_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        unit = match.group(2)
        results.append(
            _build_field(
                "maxBuildingCoveragePctOrM2",
                {"value": value, "unit": unit},
                raw,
                page,
                confidence=0.82,
                unit=unit,
            )
        )

    page, match = _match_first(BIO_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "minBiologicallyActivePct",
                value,
                raw,
                page,
                confidence=0.86,
                unit="%",
            )
        )

    page, match = _match_first(ROOF_TYPE_REGEX, pages)
    if match:
        raw = match.group(0)
        value = match.group(1).strip().lower()
        results.append(
            _build_field("roofType", value, raw, page, confidence=0.78, unit=None)
        )

    page, match = _match_first(ROOF_ANGLE_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        unit = match.group(2)
        results.append(
            _build_field(
                "roofAngleDeg",
                value,
                raw,
                page,
                confidence=0.8,
                unit=unit,
            )
        )

    page, match = _match_first(MIN_PARCEL_AREA_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        unit = match.group(2)
        results.append(
            _build_field(
                "minParcelAreaM2",
                value,
                raw,
                page,
                confidence=0.84,
                unit=unit,
            )
        )

    page, match = _match_first(MIN_FRONT_WIDTH_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "minFrontWidthM",
                value,
                raw,
                page,
                confidence=0.84,
                unit="m",
            )
        )

    page, match = _match_first(MIN_FACADE_WIDTH_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "minFacadeWidthM",
                value,
                raw,
                page,
                confidence=0.84,
                unit="m",
            )
        )

    page, match = _match_first(MAX_FACADE_WIDTH_REGEX, pages)
    if match:
        raw = match.group(0)
        value = _parse_number(match.group(1))
        results.append(
            _build_field(
                "maxFacadeWidthM",
                value,
                raw,
                page,
                confidence=0.82,
                unit="m",
            )
        )

    page, match = _match_first(DEV_TYPE_REGEX, pages)
    if match:
        raw = match.group(0)
        value = match.group(1).lower()
        results.append(
            _build_field(
                "allowedDevelopmentType",
                value,
                raw,
                page,
                confidence=0.76,
                unit=None,
            )
        )

    for regex, field_key in [
        (PROTECTION_REGEX, "protectionZones"),
        (NOISE_REGEX, "noiseLandscapeRestrictions"),
        (PROHIBITIONS_REGEX, "prohibitions"),
    ]:
        page, match = _match_first(regex, pages)
        if match:
            raw = match.group(0)
            value = [entry.strip() for entry in raw.split(",") if entry.strip()]
            results.append(
                _build_field(
                    field_key,
                    value,
                    raw,
                    page,
                    confidence=0.7,
                    unit=None,
                )
            )

    present_keys = {item["fieldKey"] for item in results}
    for field_key in FIELD_KEYS:
        if field_key not in present_keys:
            results.append(
                _build_field(
                    field_key,
                    None,
                    "",
                    None,
                    confidence=0.0,
                    unit=None,
                    status="REQUIRES_REVIEW",
                )
            )
    return results


def _build_field(field_key, value, raw_text, page, confidence, unit, status=None):
    resolved_status = status
    if resolved_status is None:
        if value is None or not validate_unit_presence(raw_text, unit):
            resolved_status = "REQUIRES_REVIEW"
        else:
            resolved_status = "EXTRACTED"

    final_value = value if resolved_status == "EXTRACTED" else None

    return {
        "fieldKey": field_key,
        "value": final_value,
        "unit": unit,
        "rawText": raw_text,
        "page": page,
        "bbox": None,
        "confidence": confidence if resolved_status == "EXTRACTED" else 0.0,
        "status": resolved_status,
    }
