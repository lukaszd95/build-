from services.at_industry_classifier import ATIndustryClassifier


def _classify(text, filename="projekt.pdf", metadata=None):
    classifier = ATIndustryClassifier()
    return classifier.classify_document_industry(filename=filename, metadata=metadata or {}, text=text)


def test_detect_architektura():
    result = _classify("Projekt architektoniczny. Rzut kondygnacji i elewacja frontowa.")
    assert result["detectedIndustry"] == "Architektura"


def test_detect_pzt():
    result = _classify("Projekt zagospodarowania terenu. Granica działki, dojścia i dojazdy, plan sytuacyjny.")
    assert result["detectedIndustry"] == "PZT"


def test_detect_konstrukcja():
    result = _classify("Rysunek konstrukcyjny. Fundament, strop i belka żelbetowa ze zbrojeniem.")
    assert result["detectedIndustry"] == "Konstrukcja"


def test_detect_elektryka():
    result = _classify("Instalacja elektryczna: tablica rozdzielcza, obwody, gniazda oraz oświetlenie.")
    assert result["detectedIndustry"] == "Elektryka"


def test_detect_wod_kan():
    result = _classify("Instalacja wod-kan i kanalizacja sanitarna. Pion kanalizacyjny oraz wodociąg.")
    assert result["detectedIndustry"] == "Wod-kan"


def test_detect_wentylacja():
    result = _classify("Wentylacja mechaniczna, rekuperacja, kanały wentylacyjne, nawiew i wywiew.")
    assert result["detectedIndustry"] == "Wentylacja"


def test_unknown_for_low_signal_text():
    result = _classify("Dokumentacja budowlana tom 1.")
    assert result["detectedIndustry"] == "Nieznana"


def test_multiple_industries_when_scores_close():
    text = """
    Instalacja elektryczna: tablica rozdzielcza i obwody.
    Instalacja wod-kan: kanalizacja, pion kanalizacyjny, woda zimna.
    """
    result = _classify(text)
    assert result["detectedIndustry"] == "Wiele branż"
    assert "Elektryka" in result["detectedIndustries"]
    assert "Wod-kan" in result["detectedIndustries"]


def test_conflict_filename_vs_content_prefers_content():
    result = _classify(
        "Rysunek konstrukcyjny. Fundament oraz strop.",
        filename="instalacja-elektryczna.pdf",
    )
    assert result["detectedIndustry"] in {"Konstrukcja", "Wiele branż"}
    assert result["industryConfidence"] >= 0.4


def test_empty_text_returns_unknown_with_low_confidence():
    result = _classify("", filename="scan_001.pdf")
    assert result["detectedIndustry"] == "Nieznana"
    assert result["industryConfidence"] <= 0.25
