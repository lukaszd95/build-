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
        "filename": 5.0,
        "metadata": 4.0,
        "heading": 8.0,
        "text": 1.0,
        "table": 1.5,
        "abbr": 2.0,
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
                "uklad funkcjonalny",
            ),
            "medium": ("branza architektoniczna",),
            "weak": ("stolarka", "okna", "drzwi", "pomieszczenie", "elewacje", "przekroje"),
            "abbr": ("a", "arch"),
        },
        "PZT": {
            "strong": (
                "pzt",
                "projekt zagospodarowania terenu",
                "projekt zagospodarowania dzialki",
                "plan sytuacyjny",
                "usytuowanie obiektu",
                "zagospodarowanie terenu",
            ),
            "medium": ("plan zagospodarowania terenu",),
            "weak": ("granica dzialki", "dojscia i dojazdy", "miejsca postojowe", "przylacze na dzialce", "uklad terenu"),
            "abbr": ("zt",),
        },
        "Konstrukcja": {
            "strong": ("konstrukcja", "projekt konstrukcyjny", "rysunek konstrukcyjny", "zbrojenie", "fundament", "strop", "belka", "slup", "wiezba"),
            "medium": ("branza konstrukcyjna", "przekroj konstrukcyjny", "detale zbrojenia"),
            "weak": ("plyta", "lawa", "trzpien", "podciag"),
            "abbr": ("k", "konstr"),
        },
        "Elektryka": {
            "strong": ("instalacja elektryczna", "projekt elektryczny", "schemat elektryczny", "tablica rozdzielcza", "rozdzielnia", "wlz", "instalacje teletechniczne"),
            "medium": ("branza elektryczna",),
            "weak": ("gniazda", "oswietlenie", "obwody", "oprawy", "przewody", "punkt elektryczny"),
            "abbr": ("el", "teletechn"),
        },
        "Wod-kan": {
            "strong": (
                "instalacja wod kan",
                "instalacja wodociagowa",
                "instalacja kanalizacyjna",
                "projekt sanitarny",
                "kanalizacja",
                "pion kanalizacyjny",
                "instalacja cieplej wody",
                "instalacja zimnej wody",
            ),
            "medium": ("instalacja sanitarna", "branza sanitarna", "wod kan"),
            "weak": ("podejscia kanalizacyjne", "przybory sanitarne", "wodociag", "rury kanalizacyjne", "sanitarna", "cwu", "zw"),
            "abbr": ("san", "wk"),
        },
        "Wentylacja": {
            "strong": ("wentylacja", "projekt wentylacji", "wentylacja mechaniczna", "rekuperacja", "instalacja hvac", "centrala wentylacyjna", "kanaly wentylacyjne"),
            "medium": ("instalacja wentylacji", "klimatyzacja"),
            "weak": ("nawiew", "wywiew", "czerpnia", "wyrzutnia", "anemostat", "przewody wentylacyjne"),
            "abbr": ("went", "hvac"),
        },
    }

    SIGNAL_STRENGTH_POINTS = {
        "weak": 1.0,
        "medium": 2.0,
        "strong": 3.0,
        "abbr": 2.0,
    }

    HEADING_PATTERNS = (
        r"\bbranza\b.{0,50}",
        r"\bprojekt\b.{0,80}",
        r"\brysunek\b.{0,80}",
        r"\bopis techniczny\b.{0,120}",
    )

    def _normalize(self, value):
        cleaned = (value or "").lower()
        cleaned = cleaned.replace("–", "-").replace("—", "-")
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
        cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _add_signal(self, source, industry, phrase, source_weight, strength, signals, scores, page):
        normalized_phrase = self._normalize(phrase)
        base_points = self.SIGNAL_STRENGTH_POINTS.get(strength, 1.0)
        phrase_factor = 1.0 + min(len(normalized_phrase) / 60, 0.4)
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

    def extract_industry_signals(self, filename="", metadata=None, text="", pages=None):
        metadata = metadata or {}
        scores = {industry: 0.0 for industry in INDUSTRIES}
        signals = []
        pages = pages or []
        page_results = []

        self._collect_from_text("filename", filename, self.SOURCE_WEIGHTS["filename"], signals, scores)
        metadata_blob = " ".join(
            str(metadata.get(field, "") or "")
            for field in ("title", "subject", "author", "producer", "keywords")
        )
        self._collect_from_text("metadata", metadata_blob, self.SOURCE_WEIGHTS["metadata"], signals, scores)
        self._collect_from_text("text", text, self.SOURCE_WEIGHTS["text"], signals, scores)
        for chunk in self._extract_table_like_chunks(text):
            self._collect_from_text("table", chunk, self.SOURCE_WEIGHTS["table"], signals, scores)

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

                # bonus za spójny zestaw wielu sygnałów na stronie
                for industry in INDUSTRIES:
                    industry_signals = [s for s in page_signals if s.industry == industry]
                    if len(industry_signals) >= 3:
                        bonus = min(6.0, 3.0 + (len(industry_signals) - 3))
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

                top_industry = max(page_scores.items(), key=lambda item: item[1])[0]
                top_score = page_scores[top_industry]
                page_results.append(
                    {
                        "pageNumber": page_no,
                        "detectedIndustry": top_industry if top_score >= 6.0 else "Nieznana",
                        "scores": {k: round(v, 3) for k, v in page_scores.items()},
                        "signalCount": len(page_signals),
                    }
                )
                for industry, value in page_scores.items():
                    scores[industry] += value
                signals.extend(page_signals)
        else:
            normalized_text = self._normalize(text)
            for pattern in self.HEADING_PATTERNS:
                for match in re.finditer(pattern, normalized_text):
                    snippet = normalized_text[match.start() : min(len(normalized_text), match.end() + 160)]
                    self._collect_from_text("heading", snippet, self.SOURCE_WEIGHTS["heading"], signals, scores)

        return {
            "scores": scores,
            "signals": [signal.__dict__ for signal in signals],
            "pageResults": page_results,
        }

    def resolve_primary_industry(self, scores, signals, fallback_text_quality, page_results=None):
        page_results = page_results or []
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_industry, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        matched_industries = [industry for industry, score in ranked if score >= 8.0]
        page_winners = [item["detectedIndustry"] for item in page_results if item["detectedIndustry"] != "Nieznana"]
        unique_page_winners = sorted(set(page_winners))

        if top_score < 7.0:
            reason = "Brak wystarczających sygnałów branżowych."
            if fallback_text_quality == "poor":
                reason = "Bardzo mało tekstu do analizy — klasyfikacja niejednoznaczna."
            return {
                "detectedIndustry": "Nieznana",
                "detectedIndustries": [],
                "industryConfidence": 0.18 if fallback_text_quality == "poor" else 0.25,
                "industryClassificationReason": reason,
            }

        if (len(matched_industries) >= 2 and second_score >= top_score * 0.65) or len(unique_page_winners) >= 2:
            confidence = min(0.9, max(0.5, top_score / (top_score + second_score + 0.1)))
            return {
                "detectedIndustry": "Wiele branż",
                "detectedIndustries": matched_industries if matched_industries else unique_page_winners,
                "industryConfidence": round(confidence, 3),
                "industryClassificationReason": "Wykryto silne i porównywalne sygnały dla więcej niż jednej branży.",
            }

        confidence = min(0.97, max(0.4, (top_score - second_score * 0.25) / (top_score + 2.0)))
        return {
            "detectedIndustry": top_industry,
            "detectedIndustries": [top_industry] + [industry for industry, score in ranked[1:] if score >= top_score * 0.6],
            "industryConfidence": round(confidence, 3),
            "industryClassificationReason": f"Najsilniejsze dopasowania wskazują na branżę {top_industry}.",
        }

    def classify_document_industry(self, filename="", metadata=None, text="", pages=None):
        extracted = self.extract_industry_signals(filename=filename, metadata=metadata, text=text, pages=pages)
        text_quality = "good" if len(self._normalize(text)) >= 120 else "poor"
        resolved = self.resolve_primary_industry(
            extracted["scores"],
            extracted["signals"],
            text_quality,
            page_results=extracted.get("pageResults"),
        )
        score_breakdown = {
            "totalScores": {industry: round(score, 3) for industry, score in extracted["scores"].items()},
            "topScores": sorted(
                [{"industry": industry, "score": round(score, 3)} for industry, score in extracted["scores"].items()],
                key=lambda item: item["score"],
                reverse=True,
            ),
        }
        return {
            **resolved,
            "industrySignals": extracted["signals"],
            "industryScoreBreakdown": score_breakdown,
            "pageIndustryResults": extracted.get("pageResults", []),
            "industryClassificationDetails": {
                "scores": {industry: round(score, 3) for industry, score in extracted["scores"].items()},
                "textQuality": text_quality,
                "signalCount": len(extracted["signals"]),
                "pageCountAnalyzed": len(extracted.get("pageResults", [])),
            },
        }
