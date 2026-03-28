import re
import unicodedata
from collections import Counter, defaultdict
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
    kind: str = "positive"


class ATContentTypeClassifier:
    SOURCE_WEIGHTS = {
        "filename": 4.2,
        "metadata": 3.2,
        "heading": 8.5,
        "text": 1.5,
        "layout": 5.2,
        "table": 3.5,
        "industry_hint": 2.0,
        "conflict": 1.0,
    }

    SIGNAL_STRENGTH_POINTS = {"weak": 1.0, "medium": 2.1, "strong": 3.4, "critical": 4.2}

    DRAWING_TYPES = ("Rzut", "Przekrój", "Elewacja", "Detal")

    KEYWORDS = {
        "Opis": {
            "strong": ("opis techniczny", "część opisowa", "opis architektoniczny", "założenia projektowe"),
            "medium": ("dane techniczne", "opis konstrukcyjny", "opis instalacji"),
            "weak": ("zakres opracowania", "informacje ogólne", "charakterystyka"),
        },
        "Rzut": {
            "strong": (
                "rzut parteru",
                "rzut piętra",
                "rzut kondygnacji",
                "rzut dachu",
                "rzut fundamentów",
                "rzut i piętra",
                "rzut poziomy",
            ),
            "medium": (
                "rzut",
                "pomieszczenie",
                "pomieszczeń",
                "osie konstrukcyjne",
                "osie",
                "drzwi",
                "okna",
                "powierzchnia",
                "korytarz",
            ),
            "weak": ("kondygnacja", "układ pomieszczeń", "ściany działowe"),
        },
        "Przekrój": {
            "strong": ("przekrój a-a", "przekrój b-b", "przekrój c-c", "przekrój pionowy", "sekcja"),
            "medium": ("przekrój", "rzędna", "poziom", "poziom ±0,00", "wysokość"),
            "weak": ("warstwa", "kondygnacji", "fundament", "dach"),
        },
        "Elewacja": {
            "strong": ("elewacja północna", "elewacja południowa", "elewacja wschodnia", "elewacja zachodnia"),
            "medium": ("elewacja", "widok zewnętrzny", "fasada", "materiał elewacyjny"),
            "weak": ("okładzina", "front", "strona budynku"),
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
            "strong": ("detal wykonawczy", "detal połączenia", "szczegół połączenia", "detal a"),
            "medium": ("detal", "powiększenie", "szczegół", "fragment"),
            "weak": ("skala 1:5", "skala 1:10", "skala 1:2", "mocowanie", "łącznik"),
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

    TITLE_PATTERNS = {
        "Rzut": [r"\brzut\s+(parteru|pietra|kondygnacji|dachu|fundamentow|poziomy)\b", r"\brzut\b"],
        "Przekrój": [r"\bprzekroj\s+[a-z]-[a-z]\b", r"\bprzekroj\s+pionowy\b", r"\bsekcja\b"],
        "Elewacja": [r"\belewacja\s+(polnocna|poludniowa|wschodnia|zachodnia)\b", r"\belewacja\b"],
        "Detal": [r"\bdetal\s+[a-z0-9]+\b", r"\bdetal\s+polaczenia\b", r"\bszczegol\b", r"\bpowiekszenie\b"],
    }

    INDUSTRY_HINTS = {
        "Elektryka": "Schemat",
        "PZT": "Plan sytuacyjny / PZT",
        "Architektura": "Rzut",
        "Konstrukcja": "Przekrój",
    }

    CONFLICT_RULES = (
        ("Przekrój", "Rzut", 0.32, "silne_sygnały_pionowe_osłabiają_rzut"),
        ("Elewacja", "Przekrój", 0.24, "widok_zewnętrzny_osłabia_przekrój"),
        ("Rzut", "Elewacja", 0.28, "układ_pomieszczeń_osłabia_elewację"),
        ("Detal", "Rzut", 0.26, "lokalny_detal_osłabia_rzut_całości"),
        ("Detal", "Elewacja", 0.22, "lokalny_detal_osłabia_elewację_całości"),
        ("Przekrój", "Elewacja", 0.16, "przecięcie_pionowe_osłabia_elewację"),
    )

    ROOM_TERMS = ("pokoj", "kuchnia", "lazienka", "wc", "korytarz", "sypialnia", "salon", "pow.", "pom.")

    def _normalize(self, value):
        cleaned = (value or "").lower()
        cleaned = cleaned.replace("–", "-").replace("—", "-")
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
        cleaned = cleaned.replace("/", " ")
        cleaned = re.sub(r"[^a-z0-9+\-:\s]", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _add_signal(self, source, content_type, phrase, source_weight, strength, signals, scores, page, kind="positive"):
        base_points = self.SIGNAL_STRENGTH_POINTS.get(strength, 1.0)
        phrase_factor = 1.0 + min(len(self._normalize(phrase)) / 80, 0.32)
        score = round(source_weight * base_points * phrase_factor, 3)
        if kind == "negative":
            score *= -1
        scores[content_type] += score
        signals.append(
            ContentTypeSignal(
                source=source,
                contentType=content_type,
                phrase=self._normalize(phrase),
                weight=score,
                page=page,
                strength=strength,
                kind=kind,
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

    def _boost_from_titles(self, heading, signals, scores, page):
        normalized = self._normalize(heading)
        if not normalized:
            return
        for content_type, patterns in self.TITLE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, normalized):
                    strength = "critical" if re.search(r"(parteru|a-a|b-b|c-c|polnocna|poludniowa|wschodnia|zachodnia|polaczenia)", normalized) else "strong"
                    self._add_signal("heading", content_type, f"title:{heading}", self.SOURCE_WEIGHTS["heading"], strength, signals, scores, page)
                    break

    def _extract_structural_features(self, text):
        normalized = self._normalize(text)
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        features = {
            "room_hits": sum(len(re.findall(rf"\b{term}\b", normalized)) for term in self.ROOM_TERMS),
            "axis_hits": len(re.findall(r"\b(o[sś]ie|axis|[a-h]-[a-h]|\d+-\d+)\b", normalized)),
            "vertical_markers": len(re.findall(r"\b(\+\d+[\.,]\d+|-\d+[\.,]\d+|poziom|rzedna|n p m|m n p m)\b", normalized)),
            "section_marks": len(re.findall(r"\b([a-z]-[a-z]|przekroj|sekcja)\b", normalized)),
            "elevation_dirs": len(re.findall(r"\b(polnocna|poludniowa|wschodnia|zachodnia|fasada|widok zewnetrzny)\b", normalized)),
            "detail_scale": len(re.findall(r"\b(1:1|1:2|1:5|1:10|1:20)\b", normalized)),
            "connection_terms": len(re.findall(r"\b(polaczenie|mocowanie|warstwa|izolacja|detal|szczegol)\b", normalized)),
            "table_like_lines": sum(1 for line in lines if line.count("|") >= 2 or line.count(";") >= 2 or line.count("\t") >= 2),
            "line_count": len(lines),
            "word_count": len(normalized.split()),
            "numeric_ratio": len(re.findall(r"\d", text or "")) / max(len(text or ""), 1),
        }
        return features

    def _apply_layout_heuristics(self, page_text, signals, scores, page):
        features = self._extract_structural_features(page_text)

        if features["table_like_lines"] >= 2:
            self._add_signal("layout", "Zestawienie", "uklad_tabelaryczny", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)

        if features["word_count"] > 150 and features["numeric_ratio"] < 0.08:
            self._add_signal("layout", "Opis", "duze_bloki_tekstu", self.SOURCE_WEIGHTS["layout"], "medium", signals, scores, page)

        if features["room_hits"] >= 4:
            self._add_signal("layout", "Rzut", "wiele_nazw_pomieszczen", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)
        if features["room_hits"] >= 2 and features["axis_hits"] >= 1:
            self._add_signal("layout", "Rzut", "siatka_osi_i_uklad_poziomy", self.SOURCE_WEIGHTS["layout"], "medium", signals, scores, page)

        if features["vertical_markers"] >= 3 or features["section_marks"] >= 2:
            self._add_signal("layout", "Przekrój", "relacje_pionowe_i_rzedne", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)

        if features["elevation_dirs"] >= 1 and features["room_hits"] == 0 and features["section_marks"] == 0:
            self._add_signal("layout", "Elewacja", "zewnetrzny_kontur_bez_wnetrza", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)

        if features["detail_scale"] >= 1 and features["connection_terms"] >= 2:
            self._add_signal("layout", "Detal", "lokalny_fragment_duza_skala", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)

        if features["word_count"] < 45 and re.search(r"\b(legenda|symbol|oznaczenia)\b", self._normalize(page_text)):
            self._add_signal("layout", "Legenda", "krotki_tekst_z_symbolami", self.SOURCE_WEIGHTS["layout"], "strong", signals, scores, page)

    def _apply_conflicts(self, signals, scores, page):
        positives = defaultdict(float)
        for signal in signals:
            if signal.kind == "positive":
                positives[signal.contentType] += max(0.0, signal.weight)

        for source_type, target_type, factor, reason in self.CONFLICT_RULES:
            source_score = positives.get(source_type, 0.0)
            target_score = positives.get(target_type, 0.0)
            if source_score < 6.0 or target_score <= 0:
                continue
            penalty = min(target_score * factor, source_score * 0.38)
            if penalty <= 0:
                continue
            scores[target_type] -= round(penalty, 3)
            signals.append(
                ContentTypeSignal(
                    source="conflict",
                    contentType=target_type,
                    phrase=reason,
                    weight=round(-penalty, 3),
                    page=page,
                    strength="medium",
                    kind="negative",
                )
            )

    def _build_page_diagnostics(self, signals, scores):
        positives = sorted([s for s in signals if s["weight"] > 0], key=lambda item: item["weight"], reverse=True)
        negatives = sorted([s for s in signals if s["weight"] < 0], key=lambda item: item["weight"])
        source_truth = Counter(signal["source"] for signal in signals)
        return {
            "topPositiveSignals": positives[:5],
            "topConflictSignals": negatives[:5],
            "sourceOfTruth": dict(source_truth),
            "scoreBreakdown": {k: round(v, 3) for k, v in scores.items()},
        }

    def _resolve_page(self, scores, signals, page_no):
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_type, top_score = ranked[0]
        second_type, second_score = ranked[1]
        spread = top_score - second_score

        diagnostics = self._build_page_diagnostics(signals, scores)
        low_signal = top_score < 7.4
        heavy_conflict = second_score > 0 and (spread <= 1.35 or second_score >= top_score * 0.88)

        if low_signal or heavy_conflict:
            confidence = 0.26 if low_signal else 0.34
            reason = "Niski poziom pewności lub silny konflikt sygnałów — oznaczono jako Inna / Nieznana."
            return {
                "pageNumber": page_no,
                "detectedContentType": "Inna / Nieznana",
                "contentTypeDetectedBySystem": "Inna / Nieznana",
                "contentTypeOverride": None,
                "contentTypeConfirmedByUser": None,
                "contentTypeOverrideReason": None,
                "isUserOverridden": False,
                "classificationStatus": "uncertain",
                "confidence": round(confidence, 3),
                "reason": reason,
                "textPreview": "",
                **diagnostics,
                "runnersUp": [
                    {"contentType": top_type, "score": round(top_score, 3)},
                    {"contentType": second_type, "score": round(second_score, 3)},
                ],
            }

        confidence = min(0.97, max(0.36, (top_score + max(spread, 0.0) * 0.35) / (top_score + second_score + 2.0)))
        if second_score >= top_score * 0.74:
            confidence = max(0.36, confidence - 0.12)

        return {
            "pageNumber": page_no,
            "detectedContentType": top_type,
            "contentTypeDetectedBySystem": top_type,
            "contentTypeOverride": None,
            "contentTypeConfirmedByUser": None,
            "contentTypeOverrideReason": None,
            "isUserOverridden": False,
            "classificationStatus": "ok" if confidence >= 0.55 else "low_confidence",
            "confidence": round(confidence, 3),
            "reason": f"Najsilniejsze sygnały strony wskazują na typ: {top_type}.",
            "textPreview": "",
            **diagnostics,
            "runnersUp": [
                {"contentType": second_type, "score": round(second_score, 3)},
            ],
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
                self._boost_from_titles(heading, page_signals, page_scores, page_no)

            table_lines = [line for line in page_text.splitlines() if line.count("|") >= 2 or line.count(";") >= 2 or line.count("\t") >= 2]
            for line in table_lines[:10]:
                self._add_signal("table", "Zestawienie", line, self.SOURCE_WEIGHTS["table"], "medium", page_signals, page_scores, page_no)

            self._apply_layout_heuristics(page_text, page_signals, page_scores, page_no)
            self._apply_conflicts(page_signals, page_scores, page_no)

            grouped = Counter([signal.contentType for signal in page_signals if signal.kind == "positive"])
            for content_type, count in grouped.items():
                if count >= 3:
                    bonus = min(6.2, 2.4 + (count - 3) * 0.9)
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
            sorted_counts = sorted(known_counts.items(), key=lambda item: item[1], reverse=True)
            dominant = sorted_counts[0][0]
            total_known = sum(known_counts.values())
            top_share = sorted_counts[0][1] / max(total_known, 1)
            is_mixed = len(known_counts) >= 2 and top_share < 0.62
            if is_mixed:
                dominant = "Inna / Nieznana"

        ranked_scores = sorted(document_scores.items(), key=lambda item: item[1], reverse=True)
        top_score = ranked_scores[0][1] if ranked_scores else 0.0
        second_score = ranked_scores[1][1] if len(ranked_scores) > 1 else 0.0
        spread = top_score - second_score
        confidence = 0.2 if top_score < 7.0 else min(0.96, max(0.32, (top_score - 0.2 * second_score) / (top_score + 2.0)))
        if spread < 3.5:
            confidence = max(0.28, confidence - 0.14)
        if is_mixed:
            confidence = max(0.32, confidence - 0.12)

        detected_types = [k for k, score in ranked_scores if score >= max(6.0, top_score * 0.48)] if top_score > 0 else []
        reason = "Wykryto dominujący typ zawartości dokumentu."
        if is_mixed:
            reason = "Dokument mieszany: udział typów stron jest porównywalny, brak wyraźnej dominacji."
        if dominant == "Inna / Nieznana" and not is_mixed:
            reason = "Brak wystarczających sygnałów dla klasyfikacji typu dokumentu."

        score_breakdown = {
            "totalScores": {k: round(v, 3) for k, v in document_scores.items()},
            "topScores": [{"contentType": k, "score": round(v, 3)} for k, v in ranked_scores],
            "documentSpread": round(spread, 3),
        }

        return {
            "detectedContentType": dominant,
            "contentTypeDetectedBySystem": dominant,
            "contentTypeOverride": None,
            "contentTypeConfirmedByUser": None,
            "contentTypeOverrideReason": None,
            "detectedContentTypes": detected_types,
            "contentTypeConfidence": round(confidence, 3),
            "contentTypeScoreBreakdown": score_breakdown,
            "contentTypeReason": reason,
            "contentTypePagesSummary": dict(counts),
            "pageContentResults": page_results,
            "contentTypeSignals": [signal.__dict__ for signal in all_signals],
            "isMixedContent": bool(is_mixed),
        }
