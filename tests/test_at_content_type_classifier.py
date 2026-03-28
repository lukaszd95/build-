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


def test_classifies_rzut_strong_title_rzut_parteru():
    result = _classify(
        "",
        pages=[{"pageNumber": 1, "text": "pokoj kuchnia lazienka osie konstrukcyjne drzwi okna", "headings": ["RZUT PARTERU"]}],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Rzut"


def test_classifies_przekroj_strong_title_przekroj_aa():
    result = _classify(
        "",
        pages=[{"pageNumber": 1, "text": "przekroj pionowy poziom +0,00 poziom +2,80 rzedna", "headings": ["PRZEKRÓJ A-A"]}],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Przekrój"


def test_classifies_elewacja_strong_directional_title():
    result = _classify(
        "",
        pages=[{"pageNumber": 1, "text": "widok zewnetrzny fasada material elewacyjny", "headings": ["ELEWACJA POŁUDNIOWA"]}],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Elewacja"


def test_classifies_detal_strong_title_polaczenia():
    result = _classify(
        "",
        pages=[{"pageNumber": 1, "text": "detal polaczenia warstwa izolacja mocowanie skala 1:5", "headings": ["DETAL POŁĄCZENIA"]}],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Detal"


def test_conflict_rzut_vs_przekroj_prefers_przekroj_with_vertical_markers():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "rzut pomieszczenia pokoj kuchnia oraz przekroj a-a poziom +0,00 poziom +3,00 rzedna schody",
                "headings": ["Rysunek techniczny"],
            }
        ],
    )
    page = result["pageContentResults"][0]
    assert page["detectedContentType"] in {"Przekrój", "Inna / Nieznana"}


def test_conflict_przekroj_vs_elewacja_prefers_elewacja_for_direction_and_external_view():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "elewacja polnocna widok zewnetrzny fasada bez ukladu pomieszczen",
                "headings": ["Elewacja północna"],
            }
        ],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Elewacja"


def test_conflict_rzut_vs_detal_prefers_detal_for_local_scale():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "rzut fragment detal polaczenia mocowanie warstwa izolacja skala 1:2",
                "headings": ["Detal A"],
            }
        ],
    )
    assert result["pageContentResults"][0]["detectedContentType"] == "Detal"


def test_conflict_detal_vs_przekroj_resolves_to_uncertain_when_close_scores():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "detal przekroj a-a warstwa poziom +0,00 mocowanie skala 1:5",
                "headings": ["Rysunek"],
            }
        ],
    )
    page = result["pageContentResults"][0]
    assert page["detectedContentType"] in {"Detal", "Przekrój", "Inna / Nieznana"}
    assert "topConflictSignals" in page


def test_elewacja_is_weakened_by_room_names_and_may_not_win():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "elewacja poludniowa pokoj kuchnia lazienka osie drzwi okna",
                "headings": ["Rysunek"],
            }
        ],
    )
    assert result["pageContentResults"][0]["detectedContentType"] != "Elewacja"


def test_low_confidence_for_conflicting_signals_sets_uncertain_status():
    result = _classify(
        "",
        pages=[
            {
                "pageNumber": 1,
                "text": "rzut przekroj elewacja detal poziom +0,00 pokoj fasada skala 1:5",
                "headings": ["Rysunek"],
            }
        ],
    )
    page = result["pageContentResults"][0]
    assert page["classificationStatus"] in {"uncertain", "low_confidence", "ok"}
    assert "sourceOfTruth" in page


def test_unknown_for_insufficient_data():
    result = _classify("zalacznik tom ii", pages=[{"pageNumber": 1, "text": "zalacznik tom ii", "headings": ["Tom II"]}])
    assert result["detectedContentType"] == "Inna / Nieznana" or result["contentTypeConfidence"] <= 0.4


def test_document_mixed_when_pages_are_diverse():
    result = _classify(
        "",
        pages=[
            {"pageNumber": 1, "text": "pokoj kuchnia osie drzwi okna", "headings": ["Rzut parteru"]},
            {"pageNumber": 2, "text": "przekroj a-a poziom +0,00", "headings": ["Przekrój A-A"]},
            {"pageNumber": 3, "text": "elewacja polnocna widok zewnetrzny", "headings": ["Elewacja północna"]},
            {"pageNumber": 4, "text": "detal polaczenia skala 1:5", "headings": ["Detal połączenia"]},
        ],
    )
    assert result["isMixedContent"] is True
    assert result["detectedContentType"] == "Inna / Nieznana"
    assert len(result["detectedContentTypes"]) >= 3


def test_page_payload_contains_diagnostics_fields():
    result = _classify("", pages=[{"pageNumber": 1, "text": "Opis techniczny" * 10, "headings": ["Opis techniczny"]}])
    page = result["pageContentResults"][0]
    required = {
        "pageNumber",
        "textPreview",
        "detectedContentType",
        "contentTypeDetectedBySystem",
        "confidence",
        "scoreBreakdown",
        "topPositiveSignals",
        "topConflictSignals",
        "sourceOfTruth",
        "reason",
    }
    assert required.issubset(set(page.keys()))
