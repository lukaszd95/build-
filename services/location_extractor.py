import re
from dataclasses import dataclass
from typing import Any

STOPWORD_PATTERNS = [
    r"\burz[aą]d\b",
    r"\bwydzia[łl]\b",
    r"\btel\.?\b",
    r"\bfax\b",
    r"\be-?mail\b",
    r"\bwww\b",
    r"\bbip\b",
    r"\bkrs\b",
    r"\bnip\b",
    r"\bregon\b",
    r"\b\d{2}-\d{3}\b",
]

WINDOW_POSITIVE_HINTS = {
    "parcel": 5,
    "precinct": 4,
    "located": 3,
    "street": 2,
    "city_near_located": 2,
    "subject_phrase": 4,
}

WINDOW_NEGATIVE_HINTS = {
    "footer": -10,
}

PARCEL_NUMBER_TOKEN = r"\d+[A-Za-z]?(?:\s*[/-]\s*\d+[A-Za-z]?){0,2}(?=[^A-Za-z]|$)"

PARCEL_BLOCK_REGEX = re.compile(
    r"(?:dzia[łl]k(?:a|i|ę|ach|ami)?|dz\.?)"
    r"[^\n]{0,120}?"
    r"(?:(?:nr|numer)\s*(?:ewid(?:\. |\.|encyjn\w*)?|ew\.?)?|(?:ewid(?:\. |\.|encyjn\w*)?|ew\.?)\s*(?:nr|numer)?)?\s*[:\-]?\s*"
    r"(?P<numbers>" + PARCEL_NUMBER_TOKEN + r"(?:\s*(?:,|;|/|oraz|i)\s*" + PARCEL_NUMBER_TOKEN + r")*)",
    re.IGNORECASE,
)
PARCEL_NUMBER_REGEX = re.compile(PARCEL_NUMBER_TOKEN)

PARCEL_LABEL_ONLY_REGEX = re.compile(
    r"(?:nr|numer)\s+dzia[łl]k(?:i|a)?\s*[:\-]?\s*"
    r"(?P<numbers>" + PARCEL_NUMBER_TOKEN + r"(?:\s*(?:,|;|/|oraz|i)\s*" + PARCEL_NUMBER_TOKEN + r")*)",
    re.IGNORECASE,
)

PARCEL_EWID_LABEL_REGEX = re.compile(
    r"(?:nr|numer)\s+ewidencyjn\w*\s+dzia[łl]k(?:i|a)?\s*[:\-]?\s*"
    r"(?P<numbers>" + PARCEL_NUMBER_TOKEN + r"(?:\s*(?:,|;|/|oraz|i)\s*" + PARCEL_NUMBER_TOKEN + r")*)",
    re.IGNORECASE,
)

PARCEL_INLINE_NUMERIC_REGEX = re.compile(
    r"(?<!\d)(?P<number>\d{1,5}\s*[/-]\s*\d{1,5}(?:\s*[/-]\s*\d{1,5}[A-Za-z]?)?|\d{1,5})(?!\d)",
    re.IGNORECASE,
)

PARCEL_COMPACT_REGEX = re.compile(
    r"(?<!\d)(?P<first>\d{1,5})\s*(?:[\-\.]|\s)\s*(?P<second>\d{1,5}[A-Za-z]?)(?![\dA-Za-z])",
    re.IGNORECASE,
)

FULL_IDENTIFIER_PARCEL_REGEX = re.compile(
    r"\b\d{6,8}[_\.-]\d(?:[_\.-]\d{4})?[_\.-](?P<number>\d{1,5}\s*/\s*\d{1,5}[A-Za-z]?)\b",
    re.IGNORECASE,
)

PRECINCT_NUMBERED_REGEX = re.compile(
    r"(?:w\s+obr[eę]bie|[o0]br[eę]b(?:u|ie)?|obr\.?)\s*[:\-]?\s*(?:ewidencyjn\w*)?\s*(?:nr|numer)?\s*"
    r"(?P<number>\d{1,4}(?:[-./]\d{1,4})*)"
    r"(?:\s*(?:[-–—:]|\))\s*|\s+)?"
    r"(?P<name>(?!(?:w\s+[A-ZĄĆĘŁŃÓŚŹŻ]|na\s+terenie))[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,60}?)?"
    r"(?=(?:\s+po[łl]o[zż]on|\s+przy\s+(?:ul\.?|al\.?|alej\w*|pl\.?|os\.?|rondo)|\s+w\s+[A-ZĄĆĘŁŃÓŚŹŻ]|\s+(?:miejscowo[śs][ćc]|miasto|gmina|ulica)\s*[:\-]|\s+na\s+terenie|\s*[,.;)]|$))",
    re.IGNORECASE,
)

PRECINCT_NAME_ONLY_REGEX = re.compile(
    r"(?:w\s+obr[eę]bie|[o0]br[eę]b(?:u|ie)?|obr\.?)\s*[:\-]?\s*(?:ewidencyjn\w*)?\s*(?:nr|numer)?\s*"
    r"(?P<name>(?!na\s+terenie)[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,60}?)"
    r"(?=(?:\s+po[łl]o[zż]on|\s+przy\s+(?:ul\.?|al\.?|alej\w*|pl\.?|os\.?|rondo)|\s+w\s+[A-ZĄĆĘŁŃÓŚŹŻ]|\s+(?:miejscowo[śs][ćc]|miasto|gmina|ulica)\s*[:\-]|\s+na\s+terenie|\s*[,.;)]|$))",
    re.IGNORECASE,
)

PRECINCT_PAREN_REGEX = re.compile(
    r"\((?P<number>\d{1,4}(?:[-./]\d{1,4})*)\)",
    re.IGNORECASE,
)

STREET_REGEX = re.compile(
    r"(?:przy\s+|rejonie\s+)?(?:ul\.?|ulica|al\.?|alej\w*|pl\.?|plac|os\.?|osiedle|rondo)\s*[:\-]?\s+"
    r"(?P<street>[A-ZĄĆĘŁŃÓŚŹŻ0-9][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'/\-]{1,90}?)"
    r"(?=(?:\s+w\s+[A-ZĄĆĘŁŃÓŚŹŻ]|\s*[-,]\s*dz\.?|\s+dz\.?|\s+dzia[łl]k|\s+z\s+obr|\s+obr\.?|\s*[,]|\.|$))",
    re.IGNORECASE,
)

CITY_LOCATED_REGEX = re.compile(
    r"po[łl]o[zż]on\w*[^\n]{0,100}?\bw\s+"
    r"(?P<city>[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,80}?)"
    r"(?=(?:\s+przy\s+(?:ul\.?|al\.?|alej\w*|pl\.?|os\.?|rondo)|\s*(?:,|\.|;)|\s+dla\b|$))",
    re.IGNORECASE,
)

CITY_POSITION_REGEX = re.compile(
    r"po[łl]o[zż]enie\s+nieruchomo[śs]ci\s+(?P<city>[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,80}?)"
    r"(?=(?:\s*,|\s+(?:ul\.?|al\.?|pl\.?|os\.?|rondo)|\s+dz\.?|\.|$))",
    re.IGNORECASE,
)

CITY_LABEL_REGEX = re.compile(
    r"(?:miejscowo[śs][ćc]|w\s+miejscowo[śs][ćc]i|miasto|gmina|m\.)\s*[:\-]?\s*(?P<city>[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,80}?)"
    r"(?=(?:\s*(?:,|\.|;)|\s+(?:ul\.?|al\.?|pl\.?|os\.?|rondo)|$))",
    re.IGNORECASE,
)

CITY_POSTAL_REGEX = re.compile(
    r"\b\d{2}-\d{3}\s+(?P<city>[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,80}?)"
    r"(?=(?:\s*(?:,|\.|;)|\s+(?:ul\.?|al\.?|pl\.?|os\.?|rondo)|$))",
    re.IGNORECASE,
)

CITY_GENERIC_REGEX = re.compile(
    r"\bw\s+(?P<city>[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zÀ-ÿĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9 .'-]{1,80}?)(?=(?:\s*(?:,|\.|;)|\s+dla\b|$))",
    re.IGNORECASE,
)



@dataclass
class WindowCandidate:
    page: int
    start_line: int
    end_line: int
    text: str
    score: int
    notes: list[str]
    has_parcel: bool
    has_precinct: bool
    has_location: bool
    has_street: bool
    has_city: bool


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ,;.-")
    return cleaned or None


def _normalize_street(street: str | None) -> str | None:
    return _clean(re.sub(r"^(?:ul\.?|ulica)\s+", "", street or "", flags=re.IGNORECASE))


def _normalize_city(city: str | None) -> str | None:
    cleaned = _clean(city)
    if not cleaned:
        return None
    cleaned = re.sub(r"^m\.\s*", "", cleaned, flags=re.IGNORECASE)
    if cleaned.lower() in {"st", "st.", "m", "m.", "m st", "m. st"}:
        return None
    if len(cleaned) <= 2:
        return None
    return cleaned or None


def _normalize_parcel_number(parcel: str | None) -> str | None:
    cleaned = _clean(parcel)
    if not cleaned:
        return None
    cleaned = cleaned.replace("／", "/").replace("\\", "/")
    cleaned = re.sub(r"\s*[/-]\s*", "/", cleaned)
    segments = [segment for segment in cleaned.split("/") if segment != ""]
    if len(segments) >= 2:
        normalized_segments = []
        for segment in segments:
            match = re.match(r"(?P<num>\d+)(?P<suf>[A-Za-z]?)$", segment)
            if match:
                num = match.group("num").lstrip("0") or "0"
                suf = match.group("suf")
                normalized_segments.append(f"{num}{suf}")
            else:
                normalized_segments.append(segment)
        return "/".join(normalized_segments)
    match = re.match(r"(?P<num>\d+)(?P<suf>[A-Za-z]?)$", cleaned)
    if match:
        return f"{match.group('num').lstrip('0') or '0'}{match.group('suf')}"
    return cleaned


def _normalize_text_for_parcel_extraction(text: str) -> str:
    if not text:
        return ""
    normalized = text.replace("／", "/").replace("\\", "/")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _extract_parcel_tokens(block: str) -> list[str]:
    if not block:
        return []
    normalized = _normalize_text_for_parcel_extraction(block)
    normalized = re.sub(r"\b(?:oraz|i|and|&)\b", ",", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace(";", ",").replace("|", ",")
    numbers: list[str] = []
    for parcel in PARCEL_NUMBER_REGEX.findall(normalized):
        cleaned = _normalize_parcel_number(parcel)
        if cleaned and cleaned not in numbers:
            numbers.append(cleaned)

    if numbers and all("/" not in token for token in numbers):
        compact = PARCEL_COMPACT_REGEX.search(normalized)
        if compact:
            compact_token = _normalize_parcel_number(f"{compact.group('first')}/{compact.group('second')}")
            if compact_token:
                return [compact_token]

    return numbers


def _is_likely_date_fragment(text: str, start: int, end: int) -> bool:
    left = max(0, start - 6)
    right = min(len(text), end + 6)
    fragment = text[left:right]
    return bool(re.search(r"\d{1,2}[\./-]\d{1,2}[\./-]\d{2,4}", fragment))


def _window_score(text: str) -> tuple[int, list[str], bool, bool, bool, bool, bool]:
    lowered = text.lower()
    score = 0
    notes: list[str] = []

    has_parcel = bool(re.search(r"dzia[łl]k|\bdz\.\b", lowered)) and bool(re.search(r"(?:nr\s*ewid|ewid|ew\.|nr\s+dzia[łl]k)", lowered))
    has_precinct = bool(re.search(r"[o0]br[eę]b|\bobr\.\b", lowered))
    has_street = bool(re.search(r"(?:\bprzy\s+ul\.?|\brejonie\s+ul\.?|\bul\.\s+[a-ząćęłńóśźż])", lowered))
    has_city = bool(re.search(r"\bw\s+[A-ZĄĆĘŁŃÓŚŹŻ]", text)) or bool(re.search(r"\b(?:warszawa|radom|szczecinek|ciechan[óo]w)\b", lowered))
    has_location = bool(re.search(r"po[łl]o[zż]on|po[łl]o[zż]enie\s+nieruchomo", lowered)) or has_street

    if has_parcel:
        score += WINDOW_POSITIVE_HINTS["parcel"]
        notes.append("+parcel")
    if has_precinct:
        score += WINDOW_POSITIVE_HINTS["precinct"]
        notes.append("+precinct")
    if re.search(r"po[łl]o[zż]on", lowered):
        score += WINDOW_POSITIVE_HINTS["located"]
        notes.append("+located")
    if has_street:
        score += WINDOW_POSITIVE_HINTS["street"]
        notes.append("+street")
    if re.search(r"po[łl]o[zż]on\w*[^\n]{0,40}\bw\s+[A-ZĄĆĘŁŃÓŚŹŻ]", text):
        score += WINDOW_POSITIVE_HINTS["city_near_located"]
        notes.append("+city-near-located")

    if has_parcel and has_precinct and (has_city or has_location):
        score += WINDOW_POSITIVE_HINTS["subject_phrase"]
        notes.append("+subject-phrase")

    for pattern in STOPWORD_PATTERNS:
        if re.search(pattern, lowered):
            score += WINDOW_NEGATIVE_HINTS["footer"]
            notes.append("-footer")
            break

    return score, notes, has_parcel, has_precinct, has_location, has_street, has_city


def _build_windows(pages: list[dict[str, Any]]) -> list[WindowCandidate]:
    windows: list[WindowCandidate] = []
    for page in pages:
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        if not lines:
            continue
        for idx in range(len(lines)):
            for radius in (1, 2):
                start = max(0, idx - radius)
                end = min(len(lines), idx + radius + 1)
                window_text = "\n".join(lines[start:end])
                score, notes, has_parcel, has_precinct, has_location, has_street, has_city = _window_score(window_text)
                windows.append(
                    WindowCandidate(
                        page=int(page.get("page", 1)),
                        start_line=start,
                        end_line=end - 1,
                        text=window_text,
                        score=score,
                        notes=notes,
                        has_parcel=has_parcel,
                        has_precinct=has_precinct,
                        has_location=has_location,
                        has_street=has_street,
                        has_city=has_city,
                    )
                )
    if not windows:
        windows.append(
            WindowCandidate(
                page=1,
                start_line=0,
                end_line=0,
                text="",
                score=0,
                notes=["empty"],
                has_parcel=False,
                has_precinct=False,
                has_location=False,
                has_street=False,
                has_city=False,
            )
        )
    return windows


def _is_footer_like(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in STOPWORD_PATTERNS)


def _window_extraction_presence(window: WindowCandidate) -> int:
    parcels, _ = _extract_parcels(window.text)
    precinct, _, _ = _extract_precinct(window.text)
    street, _ = _extract_street(window.text)
    city, _ = _extract_city(window.text)
    return int(bool(parcels)) + int(bool(precinct)) + int(bool(street)) + int(bool(city))


def _extract_parcels(text: str) -> tuple[list[str], str | None]:
    normalized_text = _normalize_text_for_parcel_extraction(text)
    numbers: list[str] = []
    evidence = None

    full_id_match = FULL_IDENTIFIER_PARCEL_REGEX.search(normalized_text)
    if full_id_match:
        token = _normalize_parcel_number(full_id_match.group("number"))
        if token:
            numbers = [token]
            evidence = _clean(full_id_match.group(0))

    if not numbers:
        match = (
            PARCEL_BLOCK_REGEX.search(normalized_text)
            or PARCEL_LABEL_ONLY_REGEX.search(normalized_text)
            or PARCEL_EWID_LABEL_REGEX.search(normalized_text)
        )
        if match:
            block = match.group("numbers")
            evidence = _clean(match.group(0))
            numbers = _extract_parcel_tokens(block)
            if numbers and len(numbers) == 1 and "/" not in numbers[0]:
                local_span = normalized_text[match.start(): min(len(normalized_text), match.end() + 24)]
                compact_local = PARCEL_COMPACT_REGEX.search(local_span)
                if compact_local and not _is_likely_date_fragment(local_span, compact_local.start(), compact_local.end()):
                    compact_token = _normalize_parcel_number(
                        f"{compact_local.group('first')}/{compact_local.group('second')}"
                    )
                    if compact_token:
                        numbers = [compact_token]
                        evidence = _clean(compact_local.group(0))

    if not numbers and re.search(r"(?:\bdzia[łl]k|\bdz\.?|\bobr\.?|obr[eę]b)", normalized_text, re.IGNORECASE):
        inline_candidates = []
        for parcel_match in PARCEL_INLINE_NUMERIC_REGEX.finditer(normalized_text):
            token = _normalize_parcel_number(parcel_match.group("number"))
            if not token:
                continue
            if len(token) <= 1:
                continue
            if token in {"00", "000", "0000"}:
                continue
            if _is_likely_date_fragment(normalized_text, parcel_match.start(), parcel_match.end()):
                continue
            inline_candidates.append((parcel_match.start(), token, parcel_match.group(0)))

        if inline_candidates:
            first = inline_candidates[0]
            numbers = [first[1]]
            evidence = _clean(first[2])

    if not numbers and re.search(r"(?:\bdzia[łl]k|\bdz\.?|\bobr\.?|obr[eę]b)", normalized_text, re.IGNORECASE):
        compact_candidates = []
        for compact_match in PARCEL_COMPACT_REGEX.finditer(normalized_text):
            if _is_likely_date_fragment(normalized_text, compact_match.start(), compact_match.end()):
                continue
            token = _normalize_parcel_number(f"{compact_match.group('first')}/{compact_match.group('second')}")
            if token:
                compact_candidates.append((compact_match.start(), token, compact_match.group(0)))
        if compact_candidates:
            first = compact_candidates[0]
            numbers = [first[1]]
            evidence = _clean(first[2])

    return numbers, evidence


def _extract_precinct(text: str) -> tuple[str | None, str | None, str | None]:
    match = PRECINCT_NUMBERED_REGEX.search(text)
    if match:
        number = _clean(match.group("number"))
        name = _clean(match.group("name"))
        precinct = f"{number} – {name}" if number and name else (number or name)
        return precinct, number, _clean(match.group(0))

    name_only = PRECINCT_NAME_ONLY_REGEX.search(text)
    if name_only:
        name = _clean(name_only.group("name"))
        return name, None, _clean(name_only.group(0))

    paren_match = PRECINCT_PAREN_REGEX.search(text)
    if paren_match:
        number = _clean(paren_match.group("number"))
        return number, number, _clean(paren_match.group(0))

    return None, None, None
def _extract_city(text: str) -> tuple[str | None, str | None]:
    label_match = CITY_LABEL_REGEX.search(text)
    if label_match:
        normalized = _normalize_city(label_match.group("city"))
        if normalized:
            return normalized, _clean(label_match.group(0))

    position_match = CITY_POSITION_REGEX.search(text)
    if position_match:
        normalized = _normalize_city(position_match.group("city"))
        if normalized:
            return normalized, _clean(position_match.group(0))

    located_match = CITY_LOCATED_REGEX.search(text)
    if located_match:
        normalized = _normalize_city(located_match.group("city"))
        if normalized:
            return normalized, _clean(located_match.group(0))

    postal_match = CITY_POSTAL_REGEX.search(text)
    if postal_match:
        normalized = _normalize_city(postal_match.group("city"))
        if normalized:
            return normalized, _clean(postal_match.group(0))

    generic_match = CITY_GENERIC_REGEX.search(text)
    if generic_match:
        normalized = _normalize_city(generic_match.group("city"))
        if normalized:
            return normalized, _clean(generic_match.group(0))
    return None, None
def _extract_street(text: str) -> tuple[str | None, str | None]:
    candidates: list[tuple[int, int, str, str]] = []
    for match in STREET_REGEX.finditer(text):
        raw = _clean(match.group(0))
        street = _normalize_street(match.group("street"))
        if not raw or not street:
            continue

        line_start = text.rfind("\n", 0, match.start())
        line_end = text.find("\n", match.end())
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]

        score = 0
        lowered_line = line.lower()
        if re.search(r"po[łl]o[zż]on|dotyczy|inwestycj", lowered_line):
            score += 3
        if re.search(r"dzia[łl]k|\bdz\.\b|\bobr", lowered_line):
            score += 2
        if re.search(r"\b(?:ul\.?|ulica|al\.?|alej\w*|pl\.?|plac|os\.?|osiedle|rondo)\b", lowered_line):
            score += 1
        if re.search(r"\bw\s+[A-ZĄĆĘŁŃÓŚŹŻ]", line):
            score += 1
        if any(re.search(pattern, lowered_line) for pattern in STOPWORD_PATTERNS):
            score -= 4

        candidates.append((score, match.start(), street, raw))

    if not candidates:
        return None, None

    score, _pos, street, raw = max(candidates, key=lambda item: (item[0], item[1]))
    if score < -2:
        return None, None
    return street, raw


def _bundle_from_text(text: str) -> dict[str, Any]:
    parcel_numbers, parcel_evidence = _extract_parcels(text)
    precinct, precinct_number, precinct_evidence = _extract_precinct(text)
    street, street_evidence = _extract_street(text)
    city, city_evidence = _extract_city(text)
    return {
        "parcel_numbers": parcel_numbers,
        "precinct": precinct,
        "precinct_number": precinct_number,
        "street": street,
        "city": city,
        "evidence": {
            "parcel_numbers": parcel_evidence,
            "precinct": precinct_evidence,
            "street": street_evidence,
            "city": city_evidence,
        },
    }


def _bundle_presence(bundle: dict[str, Any]) -> int:
    return (
        int(bool(bundle.get("parcel_numbers")))
        + int(bool(bundle.get("precinct")))
        + int(bool(bundle.get("street")))
        + int(bool(bundle.get("city")))
    )


def _merge_missing_fields(base: dict[str, Any], candidate: dict[str, Any], notes: list[str], source_note: str) -> None:
    for field in ("parcel_numbers", "precinct", "street", "city"):
        if base.get(field):
            continue
        value = candidate.get(field)
        if not value:
            continue
        base[field] = value
        if field == "precinct":
            base["precinct_number"] = candidate.get("precinct_number")
        base["evidence"][field] = candidate.get("evidence", {}).get(field)
        notes.append(f"{field}_{source_note}")


def extract_location(pages: list[dict[str, Any]], allow_mixed_backfill: bool = False) -> dict[str, Any]:
    first_page = next((page for page in pages if int(page.get("page", 1)) == 1), pages[0] if pages else {"page": 1, "text": ""})
    first_page_list = [first_page]
    windows = _build_windows(first_page_list)

    qualified_windows = [
        w
        for w in windows
        if w.has_parcel and w.has_precinct and (w.has_city or w.has_location or w.has_street)
    ]

    if qualified_windows:
        primary_window = max(
            qualified_windows,
            key=lambda window: (window.score, _window_extraction_presence(window), -window.start_line),
        )
        qualification_note = "qualified_subject_window"
    else:
        non_footer_windows = [window for window in windows if not _is_footer_like(window.text)]
        candidate_windows = non_footer_windows or windows
        primary_window = max(
            candidate_windows,
            key=lambda window: (window.score, _window_extraction_presence(window), -window.start_line),
        )
        qualification_note = "fallback_best_window_no_full_subject"

    notes: list[str] = [
        f"primary_window_score={primary_window.score}",
        qualification_note,
        "search_scope=first_page",
        f"bundle_mode={'mixed_backfill' if allow_mixed_backfill else 'single_window'}",
    ]
    notes.extend(primary_window.notes)

    primary_bundle = _bundle_from_text(primary_window.text)
    bundle = {
        "parcel_numbers": list(primary_bundle.get("parcel_numbers") or []),
        "precinct": primary_bundle.get("precinct"),
        "precinct_number": primary_bundle.get("precinct_number"),
        "street": primary_bundle.get("street"),
        "city": primary_bundle.get("city"),
        "evidence": dict(primary_bundle.get("evidence") or {}),
    }

    other_windows = [window for window in windows if window is not primary_window]
    other_windows = sorted(other_windows, key=lambda window: window.score, reverse=True)

    if not allow_mixed_backfill:
        complete_windows = []
        for candidate in windows:
            candidate_bundle = _bundle_from_text(candidate.text)
            is_complete = (
                bool(candidate_bundle.get("parcel_numbers"))
                and bool(candidate_bundle.get("precinct"))
                and bool(candidate_bundle.get("street"))
                and bool(candidate_bundle.get("city"))
            )
            if is_complete:
                complete_windows.append((candidate, candidate_bundle))

        if complete_windows and _bundle_presence(bundle) < 4:
            best_window, best_bundle = max(
                complete_windows,
                key=lambda item: (item[0].score, _bundle_presence(item[1]), -item[0].start_line),
            )
            bundle = {
                "parcel_numbers": list(best_bundle.get("parcel_numbers") or []),
                "precinct": best_bundle.get("precinct"),
                "precinct_number": best_bundle.get("precinct_number"),
                "street": best_bundle.get("street"),
                "city": best_bundle.get("city"),
                "evidence": dict(best_bundle.get("evidence") or {}),
            }
            if best_window is not primary_window:
                notes.append("selected_complete_bundle_window")
                notes.append(f"bundle_window_score={best_window.score}")
    else:
        for candidate in other_windows:
            candidate_bundle = _bundle_from_text(candidate.text)
            _merge_missing_fields(bundle, candidate_bundle, notes, "from_secondary_window")
            if _bundle_presence(bundle) == 4:
                break

    first_page_text = first_page.get("text") or ""
    if allow_mixed_backfill and _bundle_presence(bundle) < 4:
        first_page_bundle = _bundle_from_text(first_page_text)
        _merge_missing_fields(bundle, first_page_bundle, notes, "from_first_page_full_text")

    if allow_mixed_backfill and _bundle_presence(bundle) < 4 and len(pages) > 1:
        full_text = "\n".join((page.get("text") or "") for page in pages)
        full_bundle = _bundle_from_text(full_text)
        _merge_missing_fields(bundle, full_bundle, notes, "from_all_pages_full_text")

    parcel_numbers = bundle.get("parcel_numbers") or []
    precinct = bundle.get("precinct")
    precinct_number = bundle.get("precinct_number")
    street = bundle.get("street")
    city = bundle.get("city")

    missing_required = 0
    if not parcel_numbers:
        missing_required += 1
        notes.append("missing_parcel_numbers")
    if not precinct:
        missing_required += 1
        notes.append("missing_precinct")
    if not city:
        missing_required += 1
        notes.append("missing_city")

    base_confidence = 0.35 + min(max(primary_window.score, 0), 18) / 22
    if qualification_note.startswith("fallback"):
        base_confidence -= 0.15
    confidence = max(0.0, min(0.98, base_confidence - 0.2 * missing_required))

    evidence = {
        "parcel_numbers": bundle.get("evidence", {}).get("parcel_numbers") if parcel_numbers else None,
        "precinct": bundle.get("evidence", {}).get("precinct") if precinct else None,
        "street": bundle.get("evidence", {}).get("street") if street else None,
        "city": bundle.get("evidence", {}).get("city") if city else None,
        "primary_window": primary_window.text or None,
    }

    if parcel_numbers and not evidence["parcel_numbers"]:
        parcel_numbers = []
    if precinct and not evidence["precinct"]:
        precinct = None
        precinct_number = None
    if city and not evidence["city"]:
        city = None

    return {
        "parcel_numbers": parcel_numbers,
        "precinct": precinct,
        "precinct_number": precinct_number,
        "street": street,
        "city": city,
        "primary_window": {
            "page": primary_window.page,
            "line_start": primary_window.start_line,
            "line_end": primary_window.end_line,
            "score": primary_window.score,
            "text": primary_window.text,
        },
        "evidence": evidence,
        "notes": notes,
        "confidence": round(confidence, 3),
    }
