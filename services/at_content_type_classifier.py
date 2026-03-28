import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

CONTENT_TYPES = (
    "Opis",
    "Rzut",
    "Przekrój",
    "Elewacja",
    "Schemat",
    "Zestawienie",
    "Detal",
    "Plan sytuacyjny / PZT",
    "Legenda",
    "Inna / Nieznana",
)


@dataclass
class ContentTypeSignal:
    source: str
    contentType: str
    phrase: str
    weight: float
    page: int | None = None
    strength: str = "medium"


class ATContentTypeClassifier:
    SOURCE_WEIGHTS = {
        "filename": 4.0,
        "metadata": 3.0,
        "heading": 8.0,
        "text": 1.4,
        "layout": 5.0,
        "table": 3.5,
        "industry_hint": 2.0,
    }

    SIGNAL_STRENGTH_POINTS = {"weak": 1.0, "medium": 2.0, "strong": 3.2}

    KEYWORDS = {
        "Opis": {
            "strong": ("opis techniczny", "część opisowa", "opis architektoniczny", "założenia projektowe"),
            "medium": ("dane techniczne", "opis konstrukcyjny", "opis instalacji"),
            "weak": ("zakres opracowania", "informacje ogólne", "charakterystyka"),
        },
        "Rzut": {
            "strong": ("rzut parteru", "rzut piętra", "rzut kondygnacji", "rzut dachu", "rzut fundamentów"),
            "medium": ("rzut", "pomieszczeń", "osie", "drzwi", "okna"),
            "weak": ("kondygnacja", "układ pomieszczeń"),
        },
        "Przekrój": {
            "strong": ("przekrój a-a", "przekrój b-b", "przekrój pionowy"),
            "medium": ("przekrój", "poziom ±0,00", "rzędna"),
            "weak": ("wysokość", "warstwa", "kondygnacji"),
        },
        "Elewacja": {
            "strong": ("elewacja północna", "elewacja południowa", "elewacja wschodnia", "elewacja zachodnia"),
            "medium": ("elewacja", "widok zewnętrzny", "materiał elewacyjny"),
            "weak": ("fasada", "okładzina"),
        },
        "Schemat": {
            "strong": ("schemat ideowy", "schemat instalacji", "schemat elektryczny", "schemat technologiczny"),
            "medium": ("schemat", "układ blokowy", "połączenia"),
            "weak": ("symbol", "linia sygnałowa", "węzeł"),
        },
        "Zestawienie": {
            "strong": ("zestawienie stolarki", "zestawienie materiałów", "zestawienie elementów"),
            "medium": ("zestawienie", "tabela", "specyfikacja"),
            "weak": ("ilość", "wymiary", "uwagi", "pozycja"),
        },
        "Detal": {
            "strong": ("detal wykonawczy", "detal połączenia"),
            "medium": ("detal", "powiększenie", "fragment"),
            "weak": ("skala 1:5", "skala 1:10", "skala 1:2"),
        },
        "Plan sytuacyjny / PZT": {
            "strong": ("plan sytuacyjny", "projekt zagospodarowania terenu", "projekt zagospodarowania działki", "pzt"),
            "medium": ("granica działki", "dojścia i dojazdy", "usytuowanie obiektu"),
            "weak": ("przyłącza", "otoczenie", "układ działki"),
        },
        "Legenda": {
            "strong": ("legenda", "opis symboli"),
            "medium": ("oznaczenia", "symbole"),
            "weak": ("skrót", "objaśnienia"),
        },
    }

    INDUSTRY_HINTS = {
        "Elektryka": "Schemat",
        "PZT": "Plan sytuacyjny / PZT",
        "Architektura": "Rzut",
        "Konstrukcja": "Przekrój",
    }

    def _normalize(self, value):
        cleaned = (value or "").lower()
        cleaned = cleaned.replace("–", "-").replace("—", "-")
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
        cleaned = cleaned.replace("/", " ")
        cleaned = re.sub(r"[^a-z0-9+\-:\s]", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _add_signal(self, source, content_type, phrase, source_weight, strength, signals, scores, page):
        base_points = self.SIGNAL_STRENGTH_POINTS.get(strength, 1.0)
        phrase_factor = 1.0 + min(len(self._normalize(phrase)) / 70, 0.35)
        score = round(source_weight * base_points * phrase_factor, 3)
        scores[content_type] += score
        signals.append(
            ContentTypeSignal(
                source=source,
                contentType=content_type,
                phrase=self._normalize(phrase),
                weight=score,
                page=page,
                strength=strength,
            )
        )

    def _collect_from_text(self, source, text, signals, scores, page=None):
        normalized_text = self._normalize(text)
        if not normalized_text:
            return
        for content_type, groups in self.KEYWORDS.items():
            for strength, phrases in groups.items():
                for phrase in phrases:
                    normalized_phrase = self._normalize(phrase)
                    if not normalized_phrase:
                        continue
                    pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
                    if re.search(pattern, normalized_text):
                        self._add_signal(source, content_type, phrase, self.SOURCE_WEIGHTS[source], strength, signals, scores, page)

    def _layout_hints(self, text):
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        if not lines:
            return []
        normalized = self._normalize(text)
        words = normalized.split()
        avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
        punctuation_ratio = len(re.findall(r"[,:;]", text or "")) / max(len(text or ""), 1)
        numeric_ratio = len(re.findall(r"\d", text or "")) / max(len(text or ""), 1)
        table_like_lines = sum(1 for line in lines if line.count("|") >= 2 or line.count(";") >= 2 or line.count("\t") >= 2)

        hints = []
        if table_like_lines >= 2 or (table_like_lines >= 1 and numeric_ratio > 0.09):
            hints.append(("Zestawienie", "uklad_tabelaryczny", "strong"))
        if avg_line_len > 85 and punctuation_ratio > 0.015 and len(words) > 140:
            hints.append(("Opis", "duze_bloki_tekstu", "strong"))
        if len(words) < 45 and re.search(r"\b(legenda|symbol|oznaczenia)\b", normalized):
            hints.append(("Legenda", "krotki_tekst_z_symbolami", "strong"))
        if numeric_ratio > 0.12 and re.search(r"\b(skala|1:\d+|a-a|b-b|\+/-?0,?00)\b", normalized):
            hints.append(("Przekrój", "cechy_rysunku_technicznego", "medium"))
        return hints

    def _resolve_page(self, scores, signals, page_no):
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_type, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        spread = top_score - second_score

        if top_score < 7.2:
            return {
                "pageNumber": page_no,
                "detectedContentType": "Inna / Nieznana",
                "confidence": 0.24,
                "scoreBreakdown": {k: round(v, 3) for k, v in scores.items()},
                "signals": signals,
                "reason": "Brak wystarczających sygnałów dla jednoznacznej klasyfikacji strony.",
                "textPreview": "",
            }

        confidence = min(0.97, max(0.34, (top_score + max(spread, 0.0) * 0.35) / (top_score + second_score + 2.0)))
        if second_score >= top_score * 0.78:
            confidence = max(0.35, confidence - 0.18)
        return {
            "pageNumber": page_no,
            "detectedContentType": top_type,
            "confidence": round(confidence, 3),
            "scoreBreakdown": {k: round(v, 3) for k, v in scores.items()},
            "signals": signals,
            "reason": f"Najsilniejsze sygnały strony wskazują na typ: {top_type}.",
            "textPreview": "",
        }

    def classify_document_content_types(self, filename="", metadata=None, text="", pages=None, detected_industry=None):
        metadata = metadata or {}
        pages = pages or []
        document_scores = {content_type: 0.0 for content_type in CONTENT_TYPES if content_type != "Inna / Nieznana"}
        all_signals = []
        page_results = []

        self._collect_from_text("filename", filename, all_signals, document_scores)
        metadata_blob = " ".join(str(metadata.get(field, "") or "") for field in ("title", "subject", "keywords", "author"))
        self._collect_from_text("metadata", metadata_blob, all_signals, document_scores)
        self._collect_from_text("text", text, all_signals, document_scores)

        if detected_industry in self.INDUSTRY_HINTS:
            hinted = self.INDUSTRY_HINTS[detected_industry]
            self._add_signal("industry_hint", hinted, f"industry:{detected_industry}", self.SOURCE_WEIGHTS["industry_hint"], "weak", all_signals, document_scores, None)

        for page in pages:
            page_no = page.get("pageNumber")
            page_text = page.get("text") or ""
            headings = page.get("headings") or []
            page_scores = {content_type: 0.0 for content_type in document_scores.keys()}
            page_signals = []

            self._collect_from_text("text", page_text, page_signals, page_scores, page_no)
            for heading in headings:
                self._collect_from_text("heading", heading, page_signals, page_scores, page_no)

            table_lines = [line for line in (page_text or "").splitlines() if line.count("|") >= 2 or line.count(";") >= 2 or line.count("\t") >= 2]
            for line in table_lines[:10]:
                self._add_signal("table", "Zestawienie", line, self.SOURCE_WEIGHTS["table"], "medium", page_signals, page_scores, page_no)

            for content_type, hint_name, strength in self._layout_hints(page_text):
                self._add_signal("layout", content_type, hint_name, self.SOURCE_WEIGHTS["layout"], strength, page_signals, page_scores, page_no)

            grouped = Counter([signal.contentType for signal in page_signals])
            for content_type, count in grouped.items():
                if count >= 3:
                    bonus = min(6.0, 2.4 + (count - 3) * 0.8)
                    page_scores[content_type] += bonus
                    page_signals.append(
                        ContentTypeSignal(
                            source="page-bonus",
                            contentType=content_type,
                            phrase=f"spojne_sygnaly:{count}",
                            weight=round(bonus, 3),
                            page=page_no,
                            strength="medium",
                        )
                    )

            resolved_page = self._resolve_page(page_scores, [signal.__dict__ for signal in page_signals], page_no)
            resolved_page["textPreview"] = (self._normalize(page_text)[:260] + "...") if page_text else ""
            page_results.append(resolved_page)
            for key, value in page_scores.items():
                document_scores[key] += value
            all_signals.extend(page_signals)

        counts = Counter(item["detectedContentType"] for item in page_results)
        known_counts = {k: v for k, v in counts.items() if k != "Inna / Nieznana"}
        dominant = "Inna / Nieznana"
        is_mixed = False

        if known_counts:
            dominant = sorted(known_counts.items(), key=lambda item: item[1], reverse=True)[0][0]
            is_mixed = len(known_counts) >= 2

        ranked_scores = sorted(document_scores.items(), key=lambda item: item[1], reverse=True)
        top_score = ranked_scores[0][1] if ranked_scores else 0.0
        second_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0.0
        confidence = 0.2 if top_score < 7.0 else min(0.96, max(0.35, (top_score - 0.25 * second_score) / (top_score + 2.0)))
        if is_mixed:
            confidence = max(0.38, confidence - 0.1)

        detected_types = [k for k, _ in ranked_scores if _ >= max(6.0, top_score * 0.45)] if top_score > 0 else []
        reason = "Wykryto dominujący typ zawartości dokumentu."
        if is_mixed:
            reason = "Dokument zawiera wiele istotnych typów stron (dokument mieszany)."
        if dominant == "Inna / Nieznana":
            reason = "Brak wystarczających sygnałów dla klasyfikacji typu dokumentu."

        score_breakdown = {
            "totalScores": {k: round(v, 3) for k, v in document_scores.items()},
            "topScores": [{"contentType": k, "score": round(v, 3)} for k, v in ranked_scores],
        }

        return {
            "detectedContentType": dominant,
            "detectedContentTypes": detected_types,
            "contentTypeConfidence": round(confidence, 3),
            "contentTypeScoreBreakdown": score_breakdown,
            "contentTypeReason": reason,
            "contentTypePagesSummary": dict(counts),
            "pageContentResults": page_results,
            "contentTypeSignals": [signal.__dict__ for signal in all_signals],
            "isMixedContent": bool(is_mixed),
        }
