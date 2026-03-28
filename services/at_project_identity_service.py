import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher


TITLE_SECTION_PATTERNS = [
    re.compile(
        r"\b(temat|temat opracowania|temat projektu|tytuł projektu|tytul projektu|nazwa inwestycji|nazwa zadania|inwestycja|obiekt|zamierzenie budowlane|przedsięwzięcie|przedsiewziecie|projekt|projekt budowlany|projekt wykonawczy|budowa|przebudowa|rozbudowa|remont)\b",
        re.I,
    ),
]
TITLE_CANDIDATE_PATTERNS = [
    re.compile(r"\b(budowa|przebudowa|rozbudowa|nadbudowa|projekt zagospodarowania|remont|modernizacja)\b", re.I),
]
GENERIC_TITLE_PATTERNS = [
    re.compile(r"^\s*(projekt budowlany|projekt wykonawczy|projekt techniczny|opracowanie)\s*$", re.I),
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
LABEL_LINE_PATTERN = re.compile(r"^\s*([A-ZĄĆĘŁŃÓŚŹŻa-ząćęłńóśźż .\-]{3,45})\s*[:\-]\s*(.+)$")
PLOT_TOKEN_PATTERN = re.compile(r"\b\d+\s*/\s*\d+\b|\b\d+\b")


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
    normalized = re.sub(r"\s*/\s*", "/", value)
    normalized = re.sub(r"\s+", " ", normalized)
    parts = [part.strip() for part in re.split(r"(?:,|;|\boraz\b|\bi\b)", normalized, flags=re.I) if part.strip()]
    cleaned = sorted({_normalize_text(re.sub(r"[^\d/]", "", part)) for part in parts if re.search(r"\d", part)})
    return ", ".join(cleaned)


def parse_plot_numbers(value: str) -> list[str]:
    if not value:
        return []
    text = re.sub(r"\s*/\s*", "/", value)
    tokens = []
    for match in PLOT_TOKEN_PATTERN.findall(text):
        token = re.sub(r"\s+", "", match)
        token = re.sub(r"[^\d/]", "", token)
        if token and any(ch.isdigit() for ch in token):
            tokens.append(token)
    unique = sorted(set(tokens))
    return unique


def _line_source(page_idx: int, line_idx: int) -> str:
    return f"page:{page_idx + 1}:line:{line_idx + 1}"


def _is_label_like(line: str) -> bool:
    if len(line) > 48:
        return False
    return bool(TITLE_SECTION_PATTERNS[0].search(line.lower()))


def _looks_like_new_section(line: str) -> bool:
    lowered = line.lower()
    return bool(LABEL_LINE_PATTERN.match(line) or any(h in lowered for h in INVESTMENT_ADDRESS_HINTS + OFFICE_HINTS))


def extract_project_title(pages: list[dict]) -> tuple[Candidate | None, list[Candidate], list[dict]]:
    candidates: list[Candidate] = []
    rejected: list[dict] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:120]):
            lowered = line.lower()
            line_clean = re.sub(r"\s+", " ", line).strip()
            if re.match(r"^\s*(temat|temat projektu|temat opracowania|nazwa inwestycji|obiekt|inwestycja)\s*[:\-]?\s*$", line_clean, re.I):
                merged_parts = []
                for extra_idx in range(line_idx + 1, min(len(lines), line_idx + 5)):
                    extra = re.sub(r"\s+", " ", lines[extra_idx]).strip()
                    if len(extra) < 6 or _looks_like_new_section(extra):
                        break
                    merged_parts.append(extra)
                if merged_parts:
                    candidate_value = " ".join(merged_parts)
                    candidates.append(
                        Candidate(
                            value=candidate_value,
                            normalized=normalize_project_title(candidate_value),
                            confidence=min(0.99, 0.8 + (0.08 if page_idx == 0 else 0)),
                            source=_line_source(page_idx, line_idx),
                            signals=["standalone_title_label", "multiline_merged"] + (["title_page"] if page_idx == 0 else []),
                        )
                    )
                continue
            if len(line_clean) < 10:
                continue
            base = 0.2
            signals: list[str] = []
            label_match = LABEL_LINE_PATTERN.match(line_clean)
            candidate_value = line_clean
            if label_match:
                label = label_match.group(1).strip()
                value = label_match.group(2).strip()
                if any(pattern.search(label.lower()) for pattern in TITLE_SECTION_PATTERNS):
                    candidate_value = value
                    base += 0.3
                    signals.append("title_label_match")
                    merged_parts = [candidate_value]
                    for extra_idx in range(line_idx + 1, min(len(lines), line_idx + 4)):
                        extra = re.sub(r"\s+", " ", lines[extra_idx]).strip()
                        if len(extra) < 6 or _looks_like_new_section(extra):
                            break
                        merged_parts.append(extra)
                    if len(merged_parts) > 1:
                        candidate_value = " ".join(merged_parts)
                        base += 0.1
                        signals.append("multiline_merged")

            if any(pattern.search(lowered) for pattern in TITLE_SECTION_PATTERNS):
                base += 0.35
                signals.append("section_title_hint")
            if any(pattern.search(candidate_value.lower()) for pattern in TITLE_CANDIDATE_PATTERNS):
                base += 0.25
                signals.append("construction_verb_hint")
            if page_idx == 0:
                base += 0.1
                signals.append("title_page")
            if len(candidate_value) > 180:
                base -= 0.15
            if _is_label_like(candidate_value):
                base -= 0.25
                signals.append("label_like_penalty")
            if any(pattern.match(candidate_value) for pattern in GENERIC_TITLE_PATTERNS):
                base -= 0.35
                signals.append("generic_title_penalty")
            if len(candidate_value) >= 45:
                base += 0.1
                signals.append("descriptive_length_bonus")
            normalized = normalize_project_title(candidate_value)
            if base >= 0.44:
                candidates.append(
                    Candidate(value=candidate_value, normalized=normalized, confidence=min(0.99, base), source=_line_source(page_idx, line_idx), signals=signals)
                )
            else:
                rejected.append({"value": candidate_value, "source": _line_source(page_idx, line_idx), "score": round(base, 3), "reason": ",".join(signals) or "low_score"})
        for line_idx in range(0, min(len(lines) - 1, 80)):
            joined = f"{lines[line_idx]} {lines[line_idx + 1]}".strip()
            if len(joined) < 20:
                continue
            if not any(pattern.search(joined.lower()) for pattern in TITLE_CANDIDATE_PATTERNS):
                continue
            score = 0.42 + (0.1 if page_idx == 0 else 0)
            candidates.append(
                Candidate(
                    value=re.sub(r"\s+", " ", joined),
                    normalized=normalize_project_title(joined),
                    confidence=min(0.96, score),
                    source=_line_source(page_idx, line_idx),
                    signals=["adjacent_lines_joined", "construction_verb_hint"] + (["title_page"] if page_idx == 0 else []),
                )
            )
    if not candidates:
        return None, [], rejected
    ranked = sorted(candidates, key=lambda c: (c.confidence, len(c.value)), reverse=True)
    return ranked[0], ranked[:10], rejected[:20]


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


def extract_investment_address(pages: list[dict]) -> tuple[Candidate | None, list[Candidate], list[Candidate]]:
    candidates: list[Candidate] = []
    rejected: list[Candidate] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:160]):
            context_lines = lines[max(0, line_idx - 1):min(len(lines), line_idx + 3)]
            context = " ".join(context_lines)
            candidate = _classify_address_line(line, " ".join(lines[max(0, line_idx - 1):line_idx + 1]), page_idx, line_idx)
            if not candidate:
                if any(h in line.lower() for h in INVESTMENT_ADDRESS_HINTS):
                    merged = " ".join(context_lines)
                    if STREET_PATTERN.search(merged) or PLOT_PATTERN.search(merged) or re.search(r"\bobr[ęe]b\b", merged.lower()):
                        boosted = _classify_address_line(merged, merged, page_idx, line_idx)
                        if boosted:
                            boosted.confidence = min(0.99, boosted.confidence + 0.12)
                            boosted.signals.append("multiline_address_merge")
                            candidates.append(boosted)
                continue
            if candidate.rejected_as_office:
                rejected.append(candidate)
                continue
            if page_idx == 0:
                candidate.confidence = min(0.99, candidate.confidence + 0.07)
                candidate.signals.append("title_page")
            candidates.append(candidate)

    if not candidates:
        return None, [], rejected
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    return ranked[0], ranked[:10], rejected


def extract_plot_number(pages: list[dict]) -> tuple[Candidate | None, list[Candidate], list[dict]]:
    candidates: list[Candidate] = []
    rejected: list[dict] = []
    for page_idx, page in enumerate(pages or []):
        lines = [line.strip() for line in (page.get("text") or "").splitlines() if line.strip()]
        for line_idx, line in enumerate(lines[:160]):
            lowered = line.lower()
            match = PLOT_PATTERN.search(line) or (re.search(r"(dz\.?|działk|nr ewid|na działk)", lowered) and PLOT_TOKEN_PATTERN.search(line))
            if not match:
                continue
            plot_raw = line
            plots = parse_plot_numbers(plot_raw)
            if not plots:
                rejected.append({"value": plot_raw, "source": _line_source(page_idx, line_idx), "score": 0.2, "reason": "no_plot_tokens"})
                continue
            confidence = 0.52 + (0.22 if "dz. ew" in lowered or "ewid" in lowered else 0)
            if page_idx == 0:
                confidence += 0.08
            if len(plots) > 1:
                confidence += 0.08
            candidates.append(
                Candidate(
                    value=", ".join(plots),
                    normalized=normalize_plot_number(", ".join(plots)),
                    confidence=min(0.98, confidence),
                    source=_line_source(page_idx, line_idx),
                    signals=["plot_number_hint"] + (["multiple_plots"] if len(plots) > 1 else []),
                )
            )
    if not candidates:
        return None, [], rejected
    ranked = sorted(candidates, key=lambda c: c.confidence, reverse=True)
    return ranked[0], ranked[:10], rejected


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
    project_plots = set((project_row.get("plotNumberNormalized") or "").split(", ")) if project_row.get("plotNumberNormalized") else set()
    identity_plots = set((identity.get("plotNumberNormalized") or "").split(", ")) if identity.get("plotNumberNormalized") else set()
    if project_plots and identity_plots:
        overlap = len(project_plots & identity_plots)
        plot_score = overlap / max(len(project_plots), len(identity_plots))
    else:
        plot_score = 0.0

    weighted_sum = 0.0
    total_weight = 0.0
    for score, weight, present in [
        (title_score, 0.35, bool(identity.get("projectTitleNormalized"))),
        (address_score, 0.4, bool(identity.get("investmentAddressNormalized"))),
        (plot_score, 0.45, bool(identity.get("plotNumberNormalized"))),
    ]:
        if present:
            weighted_sum += score * weight
            total_weight += weight
    final = (weighted_sum / total_weight) if total_weight else 0.0
    if identity.get("projectTitleNormalized") and identity.get("plotNumberNormalized"):
        final = min(1.0, final + 0.08 * min(title_score, plot_score))
    if address_score > 0.92 and (plot_score > 0 or title_score > 0.7):
        reason = "same_address_and_supporting_signals"
    elif plot_score >= 0.99 and title_score >= 0.4:
        reason = "same_plot_and_similar_title"
    elif plot_score >= 0.99 and not identity.get("investmentAddressNormalized"):
        reason = "same_plot_partial_data"
    elif final >= 0.5:
        reason = "partial_match"
    else:
        reason = "weak_match"
    return final, reason


def explain_signals(
    title: Candidate | None,
    address: Candidate | None,
    plot: Candidate | None,
    rejected_office: list[Candidate],
    title_candidates: list[Candidate] | None = None,
    address_candidates: list[Candidate] | None = None,
    plot_candidates: list[Candidate] | None = None,
    rejected_titles: list[dict] | None = None,
    rejected_addresses: list[Candidate] | None = None,
    rejected_plots: list[dict] | None = None,
) -> dict:
    return {
        "titleSignals": title.signals if title else [],
        "addressSignals": address.signals if address else [],
        "plotSignals": plot.signals if plot else [],
        "projectTitleCandidates": [
            {"value": c.value, "normalized": c.normalized, "confidence": c.confidence, "source": c.source, "reason": ", ".join(c.signals)}
            for c in (title_candidates or [])[:8]
        ],
        "investmentAddressCandidates": [
            {"value": c.value, "normalized": c.normalized, "confidence": c.confidence, "source": c.source, "reason": ", ".join(c.signals)}
            for c in (address_candidates or [])[:8]
        ],
        "plotNumberCandidates": [
            {"value": c.value, "normalized": c.normalized, "confidence": c.confidence, "source": c.source, "reason": ", ".join(c.signals)}
            for c in (plot_candidates or [])[:8]
        ],
        "rejectedProjectTitleCandidates": (rejected_titles or [])[:10],
        "rejectedInvestmentAddressCandidates": [
            {"value": c.value, "source": c.source, "score": c.confidence, "reason": ", ".join(c.signals)}
            for c in (rejected_addresses or [])[:10]
        ],
        "rejectedPlotNumberCandidates": (rejected_plots or [])[:10],
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
