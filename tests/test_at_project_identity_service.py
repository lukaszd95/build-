from services.at_project_identity_service import (
    build_match_score,
    extract_investment_address,
    extract_land_registry_unit,
    extract_plot_number,
    extract_project_title,
    normalize_address,
    normalize_plot_number,
)


def _pages(*lines):
    return [{"pageNumber": 1, "text": "\n".join(lines), "headings": []}]


def test_extracts_project_title_from_title_page():
    candidate = extract_project_title(
        _pages(
            "TEMAT: Budowa budynku mieszkalnego jednorodzinnego",
            "Adres inwestycji: ul. Lipowa 12, Kraków",
        )
    )
    assert candidate is not None
    assert "budowa budynku mieszkalnego" in candidate.normalized
    assert candidate.confidence >= 0.45


def test_extracts_investment_address_from_dedicated_section():
    candidate, rejected = extract_investment_address(
        _pages(
            "Adres inwestycji: ul. Lipowa 12, Kraków",
            "Temat: Budowa budynku mieszkalnego",
        )
    )
    assert candidate is not None
    assert "lipowa" in candidate.normalized
    assert not rejected


def test_extracts_plot_number_from_dz_ew_section():
    candidate = extract_plot_number(_pages("dz. ew. nr 145/7, 145/8"))
    assert candidate is not None
    assert candidate.normalized == "145/7, 145/8"


def test_rejects_office_address_as_investment_address():
    candidate, rejected = extract_investment_address(
        _pages(
            "Biuro projektowe ABC Architekci, ul. Kwiatowa 5, Kraków, tel. 123-123-123",
        )
    )
    assert candidate is None
    assert rejected
    assert rejected[0].rejected_as_office is True


def test_prefers_investment_when_document_has_office_and_investment_addresses():
    candidate, rejected = extract_investment_address(
        _pages(
            "Biuro projektowe ABC, ul. Kwiatowa 5, Kraków, tel. 123",
            "Adres inwestycji: ul. Lipowa 12, Kraków",
        )
    )
    assert candidate is not None
    assert "lipowa" in candidate.normalized
    assert rejected


def test_handles_plot_only_without_street():
    plot = extract_plot_number(_pages("Inwestycja na działce nr 23/8"))
    assert plot is not None
    assert plot.normalized == "23/8"


def test_match_score_same_title_and_plot():
    project = {
        "projectTitleNormalized": "budowa budynku mieszkalnego jednorodzinnego",
        "investmentAddressNormalized": "",
        "plotNumberNormalized": "145/7",
    }
    identity = {
        "projectTitleNormalized": "budowa budynku mieszkalnego jednorodzinnego",
        "investmentAddressNormalized": "",
        "plotNumberNormalized": "145/7",
    }
    score, reason = build_match_score(project, identity)
    assert score > 0.5
    assert reason in {"same_plot_and_similar_title", "partial_match"}


def test_partial_title_similarity_returns_partial_match():
    project = {
        "projectTitleNormalized": "rozbudowa budynku hali magazynowej",
        "investmentAddressNormalized": "kraków ul. lipowa 12",
        "plotNumberNormalized": "",
    }
    identity = {
        "projectTitleNormalized": "rozbudowa hali magazynowej",
        "investmentAddressNormalized": "krakow ul. lipowa 12",
        "plotNumberNormalized": "",
    }
    score, reason = build_match_score(project, identity)
    assert score >= 0.5
    assert reason in {"partial_match", "same_address_and_supporting_signals"}


def test_normalization_of_address_and_plot_numbers():
    assert normalize_address("  ULICA Lipowa   12,   Gmina Kraków  ") == "ul. lipowa 12, gm. kraków"
    assert normalize_plot_number(" 12/4; 12/5 ;12/4") == "12/4, 12/5"


def test_extract_land_registry_unit_when_present():
    unit = extract_land_registry_unit(_pages("Obręb: Krowodrza, jednostka ewidencyjna: Kraków-Krowodrza"))
    assert unit is not None
    assert "krowodrza" in unit.normalized
