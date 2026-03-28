from services.at_industry_classifier import ATIndustryClassifier


def _classify(text, filename="projekt.pdf", metadata=None, pages=None):
    classifier = ATIndustryClassifier()
    return classifier.classify_document_industry(
        filename=filename,
        metadata=metadata or {},
        text=text,
        pages=pages or [],
    )


def test_classify_from_filename_signal():
    result = _classify("", filename="Projekt_Elektryczny_WLZ.pdf")
    assert result["detectedIndustry"] == "Elektryka"
    assert result["industryScoreBreakdown"]["totalScores"]["Elektryka"] >= 20


def test_classify_from_page_heading_signal():
    result = _classify(
        "Dokument zbiorczy",
        pages=[
            {
                "pageNumber": 1,
                "text": "Opis ogólny.",
                "headings": ["Rysunek konstrukcyjny - fundament i zbrojenie"],
            }
        ],
    )
    assert result["detectedIndustry"] == "Konstrukcja"
    assert result["pageIndustryResults"][0]["detectedIndustry"] == "Konstrukcja"


def test_classify_from_text_signal():
    result = _classify("Projekt zagospodarowania terenu. Granica działki, dojścia i dojazdy, plan sytuacyjny.")
    assert result["detectedIndustry"] == "PZT"


def test_table_content_can_increase_wod_kan_score():
    result = _classify("Instalacja wod-kan i kanalizacja sanitarna. Pion kanalizacyjny oraz wodociąg.")
    assert result["detectedIndustry"] == "Wod-kan"


def test_detect_from_diacritics_free_text():
    result = _classify("Branza sanitarna. Instalacja wodociagowa i kanalizacja deszczowa.")
    assert result["detectedIndustry"] == "Wod-kan"


def test_conflict_signals_return_multiple_industries():
    text = """
    Instalacja elektryczna: tablica rozdzielcza i obwody.
    Instalacja wod-kan: kanalizacja, pion kanalizacyjny, woda zimna.
    """
    result = _classify(text)
    assert result["detectedIndustry"] == "Wiele branż"
    assert "Elektryka" in result["detectedIndustries"]
    assert "Wod-kan" in result["detectedIndustries"]


def test_document_with_different_page_industries_returns_multiple():
    result = _classify(
        "Dokument wielobranżowy",
        pages=[
            {"pageNumber": 1, "text": "Projekt elektryczny. WLZ, tablica rozdzielcza, obwody.", "headings": ["Instalacja elektryczna"]},
            {"pageNumber": 2, "text": "Wentylacja mechaniczna. Rekuperacja, kanały wentylacyjne.", "headings": ["Projekt wentylacji"]},
        ],
    )
    assert result["detectedIndustry"] == "Wiele branż"
    assert set(result["detectedIndustries"]) >= {"Elektryka", "Wentylacja"}


def test_unknown_for_low_signal_and_low_confidence():
    result = _classify("Dokumentacja budowlana tom 1. Załącznik.")
    assert result["detectedIndustry"] == "Nieznana"
    assert result["industryConfidence"] <= 0.25


def test_boundary_case_keeps_low_confidence():
    result = _classify("", filename="scan_001.pdf")
    assert result["detectedIndustry"] == "Nieznana"
    assert result["industryConfidence"] <= 0.25


def test_result_exposes_breakdown_and_reasons():
    result = _classify("Projekt architektoniczny. Rzut kondygnacji i elewacja frontowa.")
    assert result["detectedIndustry"] == "Architektura"
    assert "industryScoreBreakdown" in result
    assert "industryClassificationReason" in result


def test_normalizes_shortcuts_variants_for_industries():
    result = _classify("Instalacja elektryczna oraz wod.kan. oraz went. mechaniczna z HVAC.")
    scores = result["industryScoreBreakdown"]["totalScores"]
    assert scores["Elektryka"] > 0
    assert scores["Wod-kan"] > 0
    assert scores["Wentylacja"] > 0


def test_page_results_include_signals_and_confidence():
    result = _classify(
        "Test",
        pages=[
            {"pageNumber": 1, "text": "Projekt wentylacji. Rekuperacja i kanały.", "headings": ["Instalacja wentylacji"]},
            {"pageNumber": 2, "text": "Opis techniczny bez sygnałów.", "headings": []},
        ],
    )
    page1 = result["pageIndustryResults"][0]
    assert page1["detectedIndustry"] == "Wentylacja"
    assert page1["industryConfidence"] > 0.4
    assert page1["industrySignals"]


def test_conflict_penalty_is_reported_in_breakdown():
    result = _classify(
        "Instalacja elektryczna i tablica rozdzielcza. Instalacja wod kan i kanalizacja. Projekt instalacja rysunek."
    )
    penalties = result["industryScoreBreakdown"]["negativeSignals"]
    assert penalties
