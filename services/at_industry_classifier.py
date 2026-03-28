import re
import unicodedata
from dataclasses import dataclass


INDUSTRIES = (
    "Architektura",
    "PZT",
    "Konstrukcja",
    "Elektryka",
    "Wod-kan",
    "Wentylacja",
)


@dataclass
class IndustrySignal:
    source: str
    industry: str
    phrase: str
    weight: float
    page: int | None = None
    strength: str = "medium"


class ATIndustryClassifier:
    SOURCE_WEIGHTS = {
        "heading": 7.0,
        "filename": 4.0,
        "metadata": 3.5,
        "text": 1.2,
        "table": 1.7,
        "abbr": 2.0,
        "penalty": 1.0,
    }

    KEYWORDS = {
        "Architektura": {
            "strong": (
                "architektura",
                "projekt architektoniczny",
                "projekt architektoniczno budowlany",
                "rzut kondygnacji",
                "elewacja",
                "przekroj",
                "zestawienie stolarki",
            ),
            "medium": ("architektoniczny", "branza architektoniczna"),
            "weak": ("stolarka", "okna", "drzwi", "pomieszczenie"),
            "abbr": ("arch", "arch."),
        },
        "PZT": {
            "strong": (
                "pzt",
                "projekt zagospodarowania terenu",
                "projekt zagospodarowania dzialki",
                "zagospodarowanie dzialki",
                "plan sytuacyjny",
                "usytuowanie obiektu",
            ),
            "medium": ("plan zagospodarowania terenu",),
            "weak": ("granica dzialki", "dojscia i dojazdy", "miejsca postojowe"),
            "abbr": ("zt",),
        },
        "Konstrukcja": {
            "strong": ("konstrukcja", "projekt konstrukcyjny", "rysunek konstrukcyjny", "zbrojenie", "fundament", "strop"),
            "medium": ("konstrukcyjny", "branza konstrukcyjna", "detale zbrojenia"),
            "weak": ("belka", "slup", "lawa", "podciag"),
            "abbr": ("konstr", "rys konstr"),
        },
        "Elektryka": {
            "strong": ("instalacja elektryczna", "projekt elektryczny", "schemat elektryczny", "tablica rozdzielcza", "rozdzielnia", "wlz"),
            "medium": ("branza elektryczna", "elektryczny", "instalacje teletechniczne"),
            "weak": ("gniazda", "oswietlenie", "obwody", "oprawy", "przewody"),
            "abbr": ("el", "inst elektr"),
        },
        "Wod-kan": {
            "strong": (
                "instalacja wod kan",
                "instalacja wodociagowa",
                "instalacja kanalizacyjna",
                "kanalizacja",
                "pion kanalizacyjny",
            ),
            "medium": ("instalacja sanitarna", "branza sanitarna", "wod kan"),
            "weak": ("przybory sanitarne", "wodociag", "rury kanalizacyjne", "cwu"),
            "abbr": ("san", "wk"),
        },
        "Wentylacja": {
            "strong": ("wentylacja", "projekt wentylacji", "wentylacja mechaniczna", "rekuperacja", "instalacja hvac", "centrala wentylacyjna"),
            "medium": ("instalacja wentylacji", "klimatyzacja"),
            "weak": ("nawiew", "wywiew", "czerpnia", "wyrzutnia", "anemostat"),
            "abbr": ("went", "hvac"),
        },
    }

    SIGNAL_STRENGTH_POINTS = {"weak": 1.0, "medium": 2.0, "strong": 3.0, "abbr": 1.5}

    AMBIGUOUS_PHRASES = ("instalacja", "projekt", "rysunek", "opis techniczny", "branza")

    NORMALIZATION_VARIANTS = (
        (r"\bwod[\s\.\-]*kan\b", "wod kan"),
        (r"\binst[\.\s]*elektr[\.\s]*\b", "instalacja elektryczna"),
        (r"\belektryczny\b", "elektryka"),
        (r"\bwent[\.\s]*\b", "wentylacja"),
        (r"\bhvac\b", "wentylacja"),
        (r"\brekuperacja\b", "wentylacja"),
        (r"\brys[\.\s]*konstr[\.\s]*\b", "rysunek konstrukcyjny"),
        (r"\barch[\.\s]*\b", "architektura"),
        (r"\bprojekt zagospodarowania terenu\b", "pzt"),
        (r"\bzagospodarowanie dzialki\b", "pzt"),
    )

    CONFLICT_PAIRS = (
        ("Elektryka", "Wod-kan"),
        ("Elektryka", "Wentylacja"),
        ("Konstrukcja", "Architektura"),
        ("PZT", "Architektura"),
    )

    def _normalize(self, value):
        cleaned = (value or "").lower()
        cleaned = cleaned.replace("–", "-").replace("—", "-").replace("’", "'")
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
        cleaned = re.sub(r"[^a-z0-9\.\-]+", " ", cleaned)
        for pattern, replacement in self.NORMALIZATION_VARIANTS:
            cleaned = re.sub(pattern, replacement, cleaned)
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _add_signal(self, source, industry, phrase, source_weight, strength, signals, scores, page):
        normalized_phrase = self._normalize(phrase)
        if not normalized_phrase:
            return
        base_points = self.SIGNAL_STRENGTH_POINTS.get(strength, 1.0)
        phrase_factor = 1.0 + min(len(normalized_phrase) / 80, 0.35)
        score = source_weight * base_points * phrase_factor
        scores[industry] += score
        signals.append(
            IndustrySignal(
                source=source,
                industry=industry,
                phrase=normalized_phrase,
                weight=round(score, 3),
                page=page,
                strength=strength,
            )
        )

    def _collect_from_text(self, source, text, source_weight, signals, scores, page=None):
        normalized_text = self._normalize(text)
        if not normalized_text:
            return
        for industry, groups in self.KEYWORDS.items():
            for strength, phrases in groups.items():
                for phrase in phrases:
                    normalized_phrase = self._normalize(phrase)
                    if not normalized_phrase:
                        continue
                    pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
                    if re.search(pattern, normalized_text):
                        signal_source = "abbr" if strength == "abbr" and source in {"text", "heading"} else source
                        source_mult = self.SOURCE_WEIGHTS.get(signal_source, source_weight)
                        self._add_signal(signal_source, industry, phrase, source_mult, strength, signals, scores, page)

    def _extract_table_like_chunks(self, text):
        table_chunks = []
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            separators = line.count(";") + line.count("|") + line.count("\t")
            if separators >= 2:
                table_chunks.append(line)
                continue
            if re.search(r"\b(zestawienie|tabela|specyfikacja)\b", self._normalize(line)):
                table_chunks.append(line)
        return table_chunks

    def _apply_conflict_penalties(self, scores, signals, page=None):
        applied = []
        for left, right in self.CONFLICT_PAIRS:
            left_score = scores.get(left, 0.0)
            right_score = scores.get(right, 0.0)
            if min(left_score, right_score) < 7.5:
                continue
            if max(left_score, right_score) == 0:
                continue
            closeness = min(left_score, right_score) / max(left_score, right_score)
            if closeness < 0.55:
                continue
            penalty = round(min(4.0, 1.2 + closeness * 2.4), 3)
            scores[left] = max(0.0, left_score - penalty)
            scores[right] = max(0.0, right_score - penalty)
            applied.append({"pair": [left, right], "penalty": penalty, "page": page})
            signals.append(
                IndustrySignal(
                    source="penalty-conflict",
                    industry=left,
                    phrase=f"conflict-with-{right}",
                    weight=round(-penalty, 3),
                    page=page,
                    strength="weak",
                )
            )
            signals.append(
                IndustrySignal(
                    source="penalty-conflict",
                    industry=right,
                    phrase=f"conflict-with-{left}",
                    weight=round(-penalty, 3),
                    page=page,
                    strength="weak",
                )
            )
        return applied

    def _apply_ambiguous_penalty(self, normalized_text, scores, signals, page=None):
        hits = [phrase for phrase in self.AMBIGUOUS_PHRASES if re.search(rf"\b{re.escape(phrase)}\b", normalized_text)]
        if len(hits) < 2:
            return 0.0
        penalty = min(3.0, 0.8 + (len(hits) - 2) * 0.5)
        for industry in INDUSTRIES:
            if scores[industry] > 0:
                scores[industry] = max(0.0, scores[industry] - penalty)
        signals.append(
            IndustrySignal(
                source="penalty-ambiguous",
                industry="Nieznana",
                phrase=f"ambiguous:{','.join(hits[:3])}",
                weight=round(-penalty, 3),
                page=page,
                strength="weak",
            )
        )
        return penalty

    def _build_page_result(self, page_no, page_text, page_scores, page_signals):
        ranked = sorted(page_scores.items(), key=lambda item: item[1], reverse=True)
        top_industry, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = 0.15 if top_score <= 0 else min(0.95, max(0.18, (top_score - second_score * 0.45) / (top_score + 1.8)))
        detected = top_industry if top_score >= 6.5 else "Nieznana"
        signal_list = sorted([signal.__dict__ for signal in page_signals], key=lambda entry: abs(entry["weight"]), reverse=True)
        return {
            "pageNumber": page_no,
            "pageTextPreview": (page_text or "").strip()[:240],
            "detectedIndustry": detected,
            "industryConfidence": round(confidence, 3),
            "industrySignals": signal_list[:12],
            "industryScoreBreakdown": {
                "scores": {k: round(v, 3) for k, v in page_scores.items()},
                "topScores": [{"industry": i, "score": round(s, 3)} for i, s in ranked[:3]],
            },
        }

    def extract_industry_signals(self, filename="", metadata=None, text="", pages=None):
        metadata = metadata or {}
        scores = {industry: 0.0 for industry in INDUSTRIES}
        signals = []
        pages = pages or []
        page_results = []
        page_summary = {industry: 0 for industry in INDUSTRIES}

        self._collect_from_text("filename", filename, self.SOURCE_WEIGHTS["filename"], signals, scores)
        metadata_blob = " ".join(str(metadata.get(field, "") or "") for field in ("title", "subject", "author", "producer", "keywords"))
        self._collect_from_text("metadata", metadata_blob, self.SOURCE_WEIGHTS["metadata"], signals, scores)
        self._collect_from_text("text", text, self.SOURCE_WEIGHTS["text"], signals, scores)
        for chunk in self._extract_table_like_chunks(text):
            self._collect_from_text("table", chunk, self.SOURCE_WEIGHTS["table"], signals, scores)

        conflict_details = []
        if pages:
            for page in pages:
                page_no = page.get("pageNumber")
                page_scores = {industry: 0.0 for industry in INDUSTRIES}
                page_signals = []
                page_text = page.get("text", "")
                headings = page.get("headings", [])

                self._collect_from_text("text", page_text, self.SOURCE_WEIGHTS["text"], page_signals, page_scores, page=page_no)
                for heading in headings:
                    self._collect_from_text("heading", heading, self.SOURCE_WEIGHTS["heading"], page_signals, page_scores, page=page_no)
                for chunk in self._extract_table_like_chunks(page_text):
                    self._collect_from_text("table", chunk, self.SOURCE_WEIGHTS["table"], page_signals, page_scores, page=page_no)

                for industry in INDUSTRIES:
                    industry_signals = [s for s in page_signals if s.industry == industry and s.weight > 0]
                    if len(industry_signals) >= 3:
                        bonus = min(5.0, 2.2 + (len(industry_signals) - 3) * 0.8)
                        page_scores[industry] += bonus
                        page_signals.append(
                            IndustrySignal(
                                source="page-bonus",
                                industry=industry,
                                phrase=f"bonus-{len(industry_signals)}-signals",
                                weight=round(bonus, 3),
                                page=page_no,
                                strength="medium",
                            )
                        )

                normalized_page = self._normalize(page_text)
                self._apply_ambiguous_penalty(normalized_page, page_scores, page_signals, page=page_no)
                conflict_details.extend(self._apply_conflict_penalties(page_scores, page_signals, page=page_no))

                page_result = self._build_page_result(page_no, page_text, page_scores, page_signals)
                page_results.append(page_result)
                if page_result["detectedIndustry"] in page_summary:
                    page_summary[page_result["detectedIndustry"]] += 1
                for industry, value in page_scores.items():
                    scores[industry] += value
                signals.extend(page_signals)
        else:
            self._apply_ambiguous_penalty(self._normalize(text), scores, signals)
            conflict_details.extend(self._apply_conflict_penalties(scores, signals, page=None))

        return {
            "scores": scores,
            "signals": [signal.__dict__ for signal in signals],
            "pageResults": page_results,
            "pageSummary": page_summary,
            "conflicts": conflict_details,
        }

    def resolve_primary_industry(self, scores, fallback_text_quality, page_results=None, page_summary=None):
        page_results = page_results or []
        page_summary = page_summary or {}
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_industry, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        active = [industry for industry, score in ranked if score >= 8.0]
        pages_known = [item for item in page_results if item["detectedIndustry"] != "Nieznana"]
        known_count = len(pages_known)
        total_pages = len(page_results)

        if top_score < 7.5:
            reason = "Brak wystarczających sygnałów branżowych."
            if fallback_text_quality == "poor":
                reason = "Bardzo mało tekstu do analizy — klasyfikacja niejednoznaczna."
            return {
                "detectedIndustry": "Nieznana",
                "detectedIndustries": [],
                "industryConfidence": 0.16 if fallback_text_quality == "poor" else 0.24,
                "industryClassificationReason": reason,
                "dominantIndustry": None,
            }

        representation = []
        if known_count:
            for industry in INDUSTRIES:
                pages = page_summary.get(industry, 0)
                if pages > 0:
                    representation.append({"industry": industry, "pages": pages, "share": round(pages / known_count, 3)})
        representation.sort(key=lambda item: item["pages"], reverse=True)
        dominant = representation[0]["industry"] if representation else top_industry
        second_repr = representation[1]["share"] if len(representation) > 1 else 0.0
        dominant_share = representation[0]["share"] if representation else 1.0

        multiple_due_to_scores = second_score >= top_score * 0.78 and second_score >= 9.0
        multiple_due_to_pages = second_repr >= 0.35 or len([r for r in representation if r["share"] >= 0.25]) >= 2
        multiple_due_to_active = len(active) >= 3 and second_score >= 8.0
        if multiple_due_to_scores or multiple_due_to_pages or multiple_due_to_active:
            confidence = min(0.88, max(0.45, top_score / (top_score + second_score + 0.8)))
            industries = sorted(set(active + [entry["industry"] for entry in representation if entry["share"] >= 0.2]))
            return {
                "detectedIndustry": "Wiele branż",
                "detectedIndustries": industries,
                "industryConfidence": round(confidence, 3),
                "industryClassificationReason": "Kilka branż ma porównywalnie silne sygnały i/lub istotny udział stron.",
                "dominantIndustry": dominant,
            }

        confidence = min(0.97, max(0.4, (top_score - second_score * 0.35) / (top_score + 2.0)))
        if total_pages >= 2 and known_count > 0 and dominant_share < 0.5:
            confidence = max(0.34, confidence - 0.12)
        return {
            "detectedIndustry": top_industry,
            "detectedIndustries": [top_industry] + [industry for industry, score in ranked[1:] if score >= top_score * 0.62],
            "industryConfidence": round(confidence, 3),
            "industryClassificationReason": f"Najsilniejsze dopasowania wskazują na branżę {top_industry}.",
            "dominantIndustry": dominant,
        }

    def classify_document_industry(self, filename="", metadata=None, text="", pages=None):
        extracted = self.extract_industry_signals(filename=filename, metadata=metadata, text=text, pages=pages)
        text_quality = "good" if len(self._normalize(text)) >= 120 else "poor"
        resolved = self.resolve_primary_industry(
            extracted["scores"],
            text_quality,
            page_results=extracted.get("pageResults"),
            page_summary=extracted.get("pageSummary"),
        )
        ranked_scores = sorted(
            [{"industry": industry, "score": round(score, 3)} for industry, score in extracted["scores"].items()],
            key=lambda item: item["score"],
            reverse=True,
        )
        page_summary = [
            {"industry": industry, "pages": count}
            for industry, count in extracted.get("pageSummary", {}).items()
            if count > 0
        ]
        page_summary.sort(key=lambda entry: entry["pages"], reverse=True)
        top_signals = sorted(extracted["signals"], key=lambda entry: abs(entry["weight"]), reverse=True)[:14]
        if resolved["detectedIndustry"] == "Wiele branż":
            strongest_pages = [page for page in extracted.get("pageResults", []) if page["detectedIndustry"] in resolved["detectedIndustries"]][:4]
        else:
            strongest_pages = [page for page in extracted.get("pageResults", []) if page["detectedIndustry"] == resolved["detectedIndustry"]][:4]
        score_breakdown = {
            "totalScores": {industry: round(score, 3) for industry, score in extracted["scores"].items()},
            "topScores": ranked_scores,
            "negativeSignals": extracted.get("conflicts", []),
        }
        return {
            **resolved,
            "industrySignals": extracted["signals"],
            "industryScoreBreakdown": score_breakdown,
            "industryPagesSummary": page_summary,
            "pageIndustryResults": extracted.get("pageResults", []),
            "industryClassificationDetails": {
                "scores": {industry: round(score, 3) for industry, score in extracted["scores"].items()},
                "textQuality": text_quality,
                "signalCount": len(extracted["signals"]),
                "topSignals": top_signals,
                "strongestPages": strongest_pages,
                "pageCountAnalyzed": len(extracted.get("pageResults", [])),
                "pageKnownCount": sum(1 for page in extracted.get("pageResults", []) if page["detectedIndustry"] != "Nieznana"),
                "dominantIndustry": resolved.get("dominantIndustry"),
            },
        }
