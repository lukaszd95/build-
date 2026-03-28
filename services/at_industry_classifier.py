import re
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


class ATIndustryClassifier:
    SOURCE_WEIGHTS = {
        "filename": 2.2,
        "metadata": 1.6,
        "heading": 2.0,
        "text": 1.2,
    }

    KEYWORDS = {
        "Architektura": (
            "architektura",
            "rzut kondygnacji",
            "elewacja",
            "przekrój",
            "zestawienie stolarki",
            "układ funkcjonalny",
            "projekt architektoniczny",
        ),
        "PZT": (
            "projekt zagospodarowania terenu",
            "pzt",
            "zagospodarowanie działki",
            "plan sytuacyjny",
            "usytuowanie obiektu",
            "granica działki",
            "dojścia i dojazdy",
        ),
        "Konstrukcja": (
            "konstrukcja",
            "zbrojenie",
            "fundament",
            "strop",
            "belka",
            "słup",
            "więźba",
            "rysunek konstrukcyjny",
            "projekt konstrukcyjny",
        ),
        "Elektryka": (
            "instalacja elektryczna",
            "tablica rozdzielcza",
            "obwody",
            "gniazda",
            "oświetlenie",
            "schemat elektryczny",
            "instalacje teletechniczne",
            "wlz",
        ),
        "Wod-kan": (
            "instalacja wod-kan",
            "kanalizacja",
            "wodociąg",
            "podejścia kanalizacyjne",
            "pion kanalizacyjny",
            "instalacja wody zimnej",
            "instalacja ciepłej wody",
            "sanitarna",
        ),
        "Wentylacja": (
            "wentylacja",
            "rekuperacja",
            "kanały wentylacyjne",
            "czerpnia",
            "wyrzutnia",
            "centrala wentylacyjna",
            "instalacja hvac",
            "nawiew",
            "wywiew",
        ),
    }

    HEADING_PATTERNS = (
        r"\bbranża\b.{0,40}",
        r"\bprojekt\b.{0,60}",
        r"\brysunek\b.{0,60}",
        r"\bopis techniczny\b.{0,80}",
    )

    def _normalize(self, value):
        cleaned = (value or "").lower()
        cleaned = cleaned.replace("–", "-").replace("—", "-")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _collect_from_text(self, source, text, source_weight, signals, scores):
        normalized_text = self._normalize(text)
        if not normalized_text:
            return
        for industry, phrases in self.KEYWORDS.items():
            for phrase in phrases:
                if phrase in normalized_text:
                    weight = source_weight * (1.0 + min(len(phrase) / 40, 0.65))
                    scores[industry] += weight
                    signals.append(
                        IndustrySignal(source=source, industry=industry, phrase=phrase, weight=round(weight, 3))
                    )

    def extract_industry_signals(self, filename="", metadata=None, text=""):
        metadata = metadata or {}
        scores = {industry: 0.0 for industry in INDUSTRIES}
        signals = []

        self._collect_from_text("filename", filename, self.SOURCE_WEIGHTS["filename"], signals, scores)
        metadata_blob = " ".join(
            str(metadata.get(field, "") or "")
            for field in ("title", "subject", "author", "producer", "keywords")
        )
        self._collect_from_text("metadata", metadata_blob, self.SOURCE_WEIGHTS["metadata"], signals, scores)
        self._collect_from_text("text", text, self.SOURCE_WEIGHTS["text"], signals, scores)

        normalized_text = self._normalize(text)
        for pattern in self.HEADING_PATTERNS:
            for match in re.finditer(pattern, normalized_text):
                snippet = normalized_text[match.start() : min(len(normalized_text), match.end() + 120)]
                self._collect_from_text("heading", snippet, self.SOURCE_WEIGHTS["heading"], signals, scores)

        return {"scores": scores, "signals": [signal.__dict__ for signal in signals]}

    def resolve_primary_industry(self, scores, signals, fallback_text_quality):
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_industry, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        matched_industries = [industry for industry, score in ranked if score >= 3.0]

        if top_score < 2.6:
            reason = "Brak wystarczających sygnałów branżowych."
            if fallback_text_quality == "poor":
                reason = "Bardzo mało tekstu do analizy — klasyfikacja niejednoznaczna."
            return {
                "detectedIndustry": "Nieznana",
                "detectedIndustries": [],
                "industryConfidence": 0.18 if fallback_text_quality == "poor" else 0.25,
                "industryClassificationReason": reason,
            }

        if len(matched_industries) >= 2 and (second_score >= top_score * 0.78):
            confidence = min(0.84, max(0.45, top_score / (top_score + second_score + 0.1)))
            return {
                "detectedIndustry": "Wiele branż",
                "detectedIndustries": matched_industries,
                "industryConfidence": round(confidence, 3),
                "industryClassificationReason": "Wykryto silne sygnały dla więcej niż jednej branży.",
            }

        confidence = min(0.96, max(0.42, (top_score - second_score * 0.28) / (top_score + 1.5)))
        return {
            "detectedIndustry": top_industry,
            "detectedIndustries": [top_industry] + [industry for industry, score in ranked[1:] if score >= top_score * 0.55],
            "industryConfidence": round(confidence, 3),
            "industryClassificationReason": f"Najsilniejsze dopasowania wskazują na branżę {top_industry}.",
        }

    def classify_document_industry(self, filename="", metadata=None, text=""):
        extracted = self.extract_industry_signals(filename=filename, metadata=metadata, text=text)
        text_quality = "good" if len(self._normalize(text)) >= 120 else "poor"
        resolved = self.resolve_primary_industry(extracted["scores"], extracted["signals"], text_quality)
        return {
            **resolved,
            "industrySignals": extracted["signals"],
            "industryClassificationDetails": {
                "scores": extracted["scores"],
                "textQuality": text_quality,
                "signalCount": len(extracted["signals"]),
            },
        }
