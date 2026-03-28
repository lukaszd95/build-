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
    candidate, candidates, rejected = extract_project_title(
        _pages(
            "TEMAT: Budowa budynku mieszkalnego jednorodzinnego",
            "Adres inwestycji: ul. Lipowa 12, Kraków",
        )
    )
    assert candidate is not None
    assert "budowa budynku mieszkalnego" in candidate.normalized
    assert candidate.confidence >= 0.45
    assert candidates
    assert isinstance(rejected, list)


def test_extracts_investment_address_from_dedicated_section():
    candidate, candidates, rejected = extract_investment_address(
        _pages(
            "Adres inwestycji: ul. Lipowa 12, Kraków",
            "Temat: Budowa budynku mieszkalnego",
        )
    )
    assert candidate is not None
    assert "lipowa" in candidate.normalized
    assert candidates
    assert not rejected


def test_extracts_plot_number_from_dz_ew_section():
    candidate, candidates, rejected = extract_plot_number(_pages("dz. ew. nr 145/7, 145/8"))
    assert candidate is not None
    assert candidate.normalized == "145/7, 145/8"
    assert candidates
    assert rejected == []


def test_rejects_office_address_as_investment_address():
    candidate, _, rejected = extract_investment_address(
        _pages(
            "Biuro projektowe ABC Architekci, ul. Kwiatowa 5, Kraków, tel. 123-123-123",
        )
    )
    assert candidate is None
    assert rejected
    assert rejected[0].rejected_as_office is True


def test_prefers_investment_when_document_has_office_and_investment_addresses():
    candidate, _, rejected = extract_investment_address(
        _pages(
            "Biuro projektowe ABC, ul. Kwiatowa 5, Kraków, tel. 123",
            "Adres inwestycji: ul. Lipowa 12, Kraków",
        )
    )
    assert candidate is not None
    assert "lipowa" in candidate.normalized
    assert rejected


def test_handles_plot_only_without_street():
    plot, _, _ = extract_plot_number(_pages("Inwestycja na działce nr 23/8"))
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


def test_multiline_title_is_merged_from_topic_block():
    candidate, _, _ = extract_project_title(
        _pages(
            "Temat:",
            "Budowa budynku mieszkalnego jednorodzinnego",
            "z infrastrukturą techniczną na działce nr 145/7",
        )
    )
    assert candidate is not None
    assert "działce nr 145/7" in candidate.value


def test_object_label_is_supported_for_project_title():
    candidate, _, _ = extract_project_title(_pages("OBIEKT: Rozbudowa hali magazynowej z zapleczem socjalnym"))
    assert candidate is not None
    assert "rozbudowa hali magazynowej" in candidate.normalized


def test_generic_project_header_does_not_beat_specific_title():
    candidate, _, rejected = extract_project_title(
        _pages(
            "Projekt budowlany",
            "Temat projektu: Budowa budynku usługowego na działce nr 12/4",
        )
    )
    assert candidate is not None
    assert "budowa budynku usługowego" in candidate.normalized
    assert any("generic_title_penalty" in entry.get("reason", "") for entry in rejected)


def test_plot_number_supports_many_separators_and_spacing():
    candidate, _, _ = extract_plot_number(_pages("dz. ew. nr 145 / 7 oraz 145/8; 145/9 i 145/10"))
    assert candidate is not None
    assert candidate.normalized == "145/10, 145/7, 145/8, 145/9"


def test_plot_with_obreb_without_street_is_detected():
    candidate, _, _ = extract_plot_number(_pages("na działkach 12/4 i 12/5, obręb Krowodrza"))
    assert candidate is not None
    assert candidate.normalized == "12/4, 12/5"


def test_multiline_address_block_is_supported():
    candidate, _, _ = extract_investment_address(
        _pages(
            "Lokalizacja inwestycji:",
            "ul. Lipowa 12",
            "Kraków",
            "dz. ew. nr 145/7",
        )
    )
    assert candidate is not None
    assert "lipowa" in candidate.normalized


def test_match_score_for_plot_only_document_is_high_enough_for_candidate():
    project = {
        "projectTitleNormalized": "",
        "investmentAddressNormalized": "",
        "plotNumberNormalized": "12/4, 12/5",
    }
    identity = {
        "projectTitleNormalized": "",
        "investmentAddressNormalized": "",
        "plotNumberNormalized": "12/4",
    }
    score, reason = build_match_score(project, identity)
    assert score >= 0.5
    assert reason in {"same_plot_partial_data", "partial_match"}
