from services.at_content_type_classifier import ATContentTypeClassifier


def _classify(text, filename="dokument.pdf", metadata=None, pages=None, industry=None):
    classifier = ATContentTypeClassifier()
    return classifier.classify_document_content_types(
        filename=filename,
        metadata=metadata or {},
        text=text,
        pages=pages or [],
        detected_industry=industry,
    )


def test_classifies_opis_from_text_block():
    result = _classify(
        "Opis techniczny inwestycji. Część opisowa obejmuje dane techniczne oraz założenia projektowe. " * 8,
        pages=[
            {
                "pageNumber": 1,
                "text": "Opis techniczny inwestycji. Część opisowa obejmuje dane techniczne oraz założenia projektowe. " * 8,
                "headings": ["Opis techniczny"],
            }
        ],
    )
    assert result["detectedContentType"] == "Opis"


def test_classifies_rzut_from_heading():
    result = _classify(
        "",
        pages=[{"pageNumber": 1, "text": "Pomieszczenia, ściany, drzwi i okna.", "headings": ["Rzut parteru"]}],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Rzut"


def test_classifies_przekroj_elewacja_schemat_and_detal():
    result = _classify(
        "",
        pages=[
            {"pageNumber": 1, "text": "Przekrój A-A poziom +0,00 warstwy.", "headings": ["Przekrój A-A"]},
            {"pageNumber": 2, "text": "Widok zewnętrzny i materiały elewacyjne.", "headings": ["Elewacja północna"]},
            {"pageNumber": 3, "text": "Połączenia i symbole instalacyjne.", "headings": ["Schemat ideowy"]},
            {"pageNumber": 4, "text": "Powiększenie połączenia.", "headings": ["Detal wykonawczy"]},
        ],
    )
    page_types = [page["detectedContentType"] for page in result["pageContentResults"]]
    assert page_types == ["Przekrój", "Elewacja", "Schemat", "Detal"]


def test_classifies_zestawienie_from_table_layout():
    table_text = "Pozycja|Ilość|Wymiary|Uwagi\nOkno O1|4|120x150|PCV\nDrzwi D1|2|90x210|EI30"
    result = _classify("", pages=[{"pageNumber": 1, "text": table_text, "headings": ["Zestawienie stolarki"]}])
    assert result["pageContentResults"][0]["detectedContentType"] == "Zestawienie"


def test_classifies_plan_sytuacyjny_and_legend():
    result = _classify(
        "",
        pages=[
            {"pageNumber": 1, "text": "Granica działki, dojścia i dojazdy.", "headings": ["Plan sytuacyjny / PZT"]},
            {"pageNumber": 2, "text": "Legenda oznaczenia symbole.", "headings": ["Legenda"]},
        ],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Plan sytuacyjny / PZT"
    assert result["pageContentResults"][1]["detectedContentType"] == "Legenda"


def test_unknown_for_ambiguous_low_signal_content():
    result = _classify("Załącznik 1. Tom II.")
    assert result["detectedContentType"] == "Inna / Nieznana"
    assert result["contentTypeConfidence"] <= 0.3


def test_conflicting_signals_reduce_confidence_and_mark_mixed():
    result = _classify(
        "",
        pages=[
            {"pageNumber": 1, "text": "Opis techniczny i dane techniczne." * 4, "headings": ["Opis techniczny"]},
            {"pageNumber": 2, "text": "Rzut parteru pomieszczenia drzwi okna", "headings": ["Rzut parteru"]},
            {"pageNumber": 3, "text": "Przekrój A-A +0,00", "headings": ["Przekrój A-A"]},
        ],
    )
    assert result["isMixedContent"] is True
    assert len(result["detectedContentTypes"]) >= 2


def test_uses_industry_hint_as_supporting_signal_only():
    result = _classify("Krótki dokument", industry="Elektryka")
    assert "Schemat" in result["contentTypeScoreBreakdown"]["totalScores"]


def test_page_payload_contains_required_fields():
    result = _classify("", pages=[{"pageNumber": 1, "text": "Opis techniczny" * 10, "headings": ["Opis techniczny"]}])
    page = result["pageContentResults"][0]
    assert {"pageNumber", "textPreview", "detectedContentType", "confidence", "scoreBreakdown", "signals", "reason"}.issubset(set(page.keys()))
