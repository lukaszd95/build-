import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher


TITLE_SECTION_PATTERNS = [
    re.compile(r"\b(temat|tytuł projektu|tytul projektu|nazwa inwestycji|inwestycja|obiekt|zamierzenie budowlane)\b", re.I),
]
TITLE_CANDIDATE_PATTERNS = [
    re.compile(r"\b(budowa|przebudowa|rozbudowa|nadbudowa|projekt zagospodarowania|remont|modernizacja)\b", re.I),
]
INVESTMENT_ADDRESS_HINTS = [
    "adres inwestycji", "lokalizacja inwestycji", "miejsce inwestycji", "adres obiektu", "inwestycja", "obiekt", "działka", "dz. ew", "nr działki", "obręb", "teren inwestycji", "lokalizacja",
]
OFFICE_HINTS = [
    "biuro projektowe", "pracownia projektowa", "studio projektowe", "architekt", "architekci", "projektant", "siedziba", "kontakt", "tel", "telefon", "e-mail", "email", "www", "nip", "regon", "biuro", "pracownia", "firma", "sp. z o.o",
]

STREET_PATTERN = re.compile(r"(ul\.?|al\.?|os\.?|pl\.?)\s*[A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż\- ]+\s+\d+[A-Za-z]?", re.I)
CITY_PATTERN = re.compile(r"\b([A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż\-]+(?:\s+[A-ZĄĆĘŁŃÓŚŹŻ][\wąćęłńóśźż\-]+)?)\b")
PLOT_PATTERN = re.compile(r"(?:dz\.?\s*ew\.?\s*nr|działk[aię]|nr działki|inwestycja na działce nr)\s*[:\-]?\s*([\d/ ,;]+)", re.I)
LAND_REGISTRY_PATTERN = re.compile(r"\b(jednostka ewidencyjna|obręb|obreb)\b\s*[:\-]?\s*([^,\n]+)", re.I)


@dataclass
class Candidate:
    value: str
    normalized: str
    confidence: float
    source: str
    signals: list[str]
    rejected_as_office: bool = False


def _normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    return text


def normalize_project_title(value: str) -> str:
    return _normalize_text(re.sub(r"[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ\-/]", " ", value or ""))


def normalize_address(value: str) -> str:
    text = _normalize_text(value)
    text = text.replace("ulica", "ul.")
    text = re.sub(r"\b(gmina)\b", "gm.", text)
    return text


def normalize_plot_number(value: str) -> str:
    if not value:
        return ""
    parts = [part.strip() for part in re.split(r"[,;]", value) if part.strip()]
    cleaned = sorted({_normalize_text(re.sub(r"[^\d/]", "", part)) for part in parts if re.search(r"\d", part)})
    return ", ".join(cleaned)


def _line_source(page_idx: int, line_idx: int) -> str:
    return f"page:{page_idx + 1}:line:{line_idx + 1}"


def extract_project_title(pages: list[dict]) -> Candidate | None:
    candidates: list[Candidate] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:120]):
            lowered = line.lower()
            line_clean = re.sub(r"\s+", " ", line).strip()
            if len(line_clean) < 12:
                continue
            base = 0.25
            signals = []
            if any(pattern.search(lowered) for pattern in TITLE_SECTION_PATTERNS):
                base += 0.35
                signals.append("section_title_hint")
            if any(pattern.search(lowered) for pattern in TITLE_CANDIDATE_PATTERNS):
                base += 0.25
                signals.append("construction_verb_hint")
            if page_idx == 0:
                base += 0.1
                signals.append("title_page")
            if len(line_clean) > 180:
                base -= 0.15
            if base >= 0.45:
                candidates.append(
                    Candidate(
                        value=line_clean,
                        normalized=normalize_project_title(line_clean),
                        confidence=min(0.99, base),
                        source=_line_source(page_idx, line_idx),
                        signals=signals,
                    )
                )
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)[0]


def _classify_address_line(line: str, context: str, page_idx: int, line_idx: int) -> Candidate | None:
    lowered = line.lower()
    street_match = STREET_PATTERN.search(line)
    plot_match = PLOT_PATTERN.search(line)
    if not street_match and not plot_match:
        return None

    base = 0.35
    signals = []
    if any(h in line.lower() for h in INVESTMENT_ADDRESS_HINTS):
        base += 0.5
        signals.append("investment_hint_line")
    elif any(h in context.lower() for h in INVESTMENT_ADDRESS_HINTS):
        base += 0.4
        signals.append("investment_hint")
    if any(h in line.lower() for h in OFFICE_HINTS):
        base -= 0.55
        signals.append("office_hint_line")
    elif any(h in context.lower() for h in OFFICE_HINTS):
        base -= 0.45
        signals.append("office_hint")

    candidate_text = street_match.group(0) if street_match else line
    if plot_match:
        candidate_text = f"{candidate_text}; działka {plot_match.group(1).strip()}"

    rejected = any(sig.startswith("office_hint") for sig in signals) and not any(sig.startswith("investment_hint") for sig in signals)
    if rejected:
        base = min(base, 0.25)

    return Candidate(
        value=candidate_text,
        normalized=normalize_address(candidate_text),
        confidence=max(0.05, min(0.99, base)),
        source=_line_source(page_idx, line_idx),
        signals=signals,
        rejected_as_office=rejected,
    )


def extract_investment_address(pages: list[dict]) -> tuple[Candidate | None, list[Candidate]]:
    candidates: list[Candidate] = []
    rejected: list[Candidate] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:160]):
            context = " ".join(lines[max(0, line_idx - 1):line_idx + 1])
            candidate = _classify_address_line(line, context, page_idx, line_idx)
            if not candidate:
                continue
            if candidate.rejected_as_office:
                rejected.append(candidate)
                continue
            candidates.append(candidate)

    if not candidates:
        return None, rejected
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)[0], rejected


def extract_plot_number(pages: list[dict]) -> Candidate | None:
    candidates: list[Candidate] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:160]):
            match = PLOT_PATTERN.search(line)
            if not match:
                continue
            plot_raw = match.group(1).strip()
            confidence = 0.55 + (0.25 if "dz. ew" in line.lower() else 0)
            candidates.append(
                Candidate(
                    value=plot_raw,
                    normalized=normalize_plot_number(plot_raw),
                    confidence=min(0.98, confidence),
                    source=_line_source(page_idx, line_idx),
                    signals=["plot_number_hint"],
                )
            )
    if not candidates:
        return None
    return sorted(candidates, key=lambda c: c.confidence, reverse=True)[0]


def extract_land_registry_unit(pages: list[dict]) -> Candidate | None:
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:160]):
            match = LAND_REGISTRY_PATTERN.search(line)
            if not match:
                continue
            value = match.group(2).strip()
            return Candidate(value=value, normalized=_normalize_text(value), confidence=0.6, source=_line_source(page_idx, line_idx), signals=["land_registry_hint"])
    return None


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def build_match_score(project_row: dict, identity: dict) -> tuple[float, str]:
    title_score = similarity(project_row.get("projectTitleNormalized") or "", identity.get("projectTitleNormalized") or "")
    address_score = similarity(project_row.get("investmentAddressNormalized") or "", identity.get("investmentAddressNormalized") or "")
    plot_score = 1.0 if (project_row.get("plotNumberNormalized") and project_row.get("plotNumberNormalized") == (identity.get("plotNumberNormalized") or "")) else 0.0

    final = (title_score * 0.35) + (address_score * 0.45) + (plot_score * 0.2)
    if address_score > 0.92 and (plot_score > 0 or title_score > 0.7):
        reason = "same_address_and_supporting_signals"
    elif plot_score > 0 and title_score > 0.5:
        reason = "same_plot_and_similar_title"
    elif final >= 0.5:
        reason = "partial_match"
    else:
        reason = "weak_match"
    return final, reason


def explain_signals(title: Candidate | None, address: Candidate | None, plot: Candidate | None, rejected_office: list[Candidate]) -> dict:
    return {
        "titleSignals": title.signals if title else [],
        "addressSignals": address.signals if address else [],
        "plotSignals": plot.signals if plot else [],
        "rejectedOfficeAddressSignals": [
            {
                "value": c.value,
                "source": c.source,
                "signals": c.signals,
            }
            for c in rejected_office[:5]
        ],
    }


def to_json(value):
    return json.dumps(value, ensure_ascii=False)
