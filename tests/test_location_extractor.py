from services.location_extractor import extract_location


def _pages(text):
    return [{"page": 1, "text": text}]


def test_wz_single_sentence_with_all_fields():
    text = """
    Dla inwestycji obejmującej działka nr ewid. 170 obręb 0032 – Dzierzków II położoną w Radomiu przy ul. Kwiatowej 33.
    """
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["170"]
    assert result["precinct"].startswith("0032")
    assert result["city"] == "Radomiu"
    assert result["street"] == "Kwiatowej 33"


def test_multiple_parcels_extraction():
    text = "Działki nr ewid. 5/1, 4/9 oraz 340/7 obręb 90 – Niechodzin-Bielin położone w Ciechanowie przy ul. Leśnej."
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["5/1", "4/9", "340/7"]
    assert result["precinct"] == "90 – Niechodzin-Bielin"


def test_mpzp_fragment_extraction():
    text = "teren obejmuje działka ewidencyjna nr 12 obręb 0013 Szczecinek położona w Szczecinku"
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["12"]
    assert result["precinct"] == "0013 – Szczecinek"
    assert result["city"] == "Szczecinku"


def test_footer_address_is_penalized_vs_subject_fragment():
    text = """
    URZĄD MIASTA, Wydział Geodezji, tel. 123-456-789, 00-120 Warszawa, www.miasto.pl
    Działka nr ewid. 340/7 obręb 0013 Szczecinek położona w Szczecinku przy ul. Klonowej 7.
    """
    result = extract_location(_pages(text))

    assert result["city"] == "Szczecinku"
    assert result["street"] == "Klonowej 7"
    assert result["primary_window"]["score"] > 0


def test_missing_street_returns_null():
    text = "Działka nr ewid. 27 obręb 0032 Dzierzków II położona w Radomiu."
    result = extract_location(_pages(text))

    assert result["street"] is None


def test_ocr_error_in_precinct_word_lowers_confidence_and_notes():
    text = "działka nr ewid. 77 0bręb 90 położona w Ciechanowie"
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["77"]
    assert result["precinct"] is not None
    assert result["confidence"] <= 0.98
    assert isinstance(result["notes"], list)


def test_evidence_quote_exists_for_non_null_fields():
    text = "Działka nr ewid. 170 obręb 0032 Dzierzków II położona w Radomiu przy ul. Kwiatowej 33."
    result = extract_location(_pages(text))

    for field, evidence_key in [
        ("parcel_numbers", "parcel_numbers"),
        ("precinct", "precinct"),
        ("city", "city"),
        ("street", "street"),
    ]:
        value = result[field]
        quote = result["evidence"][evidence_key]
        if value is not None and value != []:
            assert quote


def test_radom_decision_pattern_with_precinct_and_street():
    text = (
        "budowa dwóch budynków mieszkalnych jednorodzinnych na działce nr ewid. 65 "
        "(obręb 0320 - Rajec Poduchowny, arkusz 231) położonej przy ul. Edmunda Bakalarza 18 w Radomiu"
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["65"]
    assert result["precinct"] == "0320 – Rajec Poduchowny"
    assert result["street"] == "Edmunda Bakalarza 18"
    assert result["city"] == "Radomiu"


def test_warsaw_mpzp_pattern_with_dz_abbreviation_and_two_parcels():
    text = "dotyczy: terenu przy ul. Wysowej - dz. nr ew. 46 i 47 z obr. 4-09-10 w Warszawie"
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["46", "47"]
    assert result["precinct"] == "4-09-10"
    assert result["street"] == "Wysowej"
    assert result["city"] == "Warszawie"


def test_large_parcel_list_without_street():
    text = (
        "działki: 200/12, 200/14, 200/16, 200/18, 200/20, 200/22 obręb ewidencyjny Sękowa "
        "położone w Sękowej"
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["200/12", "200/14", "200/16", "200/18", "200/20", "200/22"]
    assert "Sękowa" in (result["precinct"] or "")
    assert result["city"] == "Sękowej"
    assert result["street"] is None


def test_bialoleka_mpzp_position_pattern_without_polozona_phrase():
    text = (
        "Położenie nieruchomości Warszawa, ul. Operowa, dz. ew. nr 3/42 z obrębu 4-05-11 "
        "na terenie Dzielnicy Białołęka m. st. Warszawy."
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["3/42"]
    assert result["precinct"] == "4-05-11"
    assert result["street"] == "Operowa"
    assert result["city"] == "Warszawa"


def test_llm_path_prefers_references_when_complete(monkeypatch):
    from utils import llm_extraction as le

    pages = _pages("Działka nr ewid. 340/7 obręb 90 – Niechodzin-Bielin położona w Ciechanowie przy ul. Bielińskiej.")

    monkeypatch.setattr(le, "is_llm_enabled", lambda: True)

    called = {"llm": False}

    def _boom(_text):
        called["llm"] = True
        raise AssertionError("LLM should not be called when refs are complete")

    monkeypatch.setattr(le, "extract_parcel_inference", _boom)

    result = le.build_parcel_inference_from_pages(pages)

    assert result["parcelNumbers"] == ["340/7"]
    assert result["obreb"] == "90 – Niechodzin-Bielin"
    assert result["locality"] == "Ciechanowie"
    assert result["street"] == "Bielińskiej"
    assert called["llm"] is False



def test_llm_path_does_not_short_circuit_for_fallback_reference(monkeypatch):
    from utils import llm_extraction as le

    pages = _pages("Dowolny tekst")

    monkeypatch.setattr(le, "is_llm_enabled", lambda: True)

    monkeypatch.setattr(
        le,
        "_build_parcel_inference_from_refs",
        lambda _pages: {
            "parcelId": "12/3",
            "parcelNumbers": ["12/3"],
            "obreb": "0001",
            "street": None,
            "locality": "Warszawa",
            "details": {
                "overall_confidence": 0.9,
                "notes": ["fallback_best_window_no_full_subject"],
                "evidence": {},
            },
        },
    )

    called = {"llm": False}

    def _llm(_text):
        called["llm"] = True
        return {
            "parcel_id": {"value": "99/1", "confidence": 0.8, "justification": "..."},
            "obreb": {"value": "0002", "confidence": 0.8, "justification": "..."},
            "ulica": {"value": "Leśna", "confidence": 0.7, "justification": "..."},
            "miejscowosc": {"value": "Radom", "confidence": 0.8, "justification": "..."},
            "overall_confidence": 0.8,
        }

    monkeypatch.setattr(le, "extract_parcel_inference", _llm)

    result = le.build_parcel_inference_from_pages(pages)

    assert called["llm"] is True
    assert result["parcelNumbers"] == ["99/1"]
    assert result["obreb"] == "0002"
    assert result["locality"] == "Radom"


def test_wypis_label_style_fields_are_extracted():
    text = (
        "Numer działki: 125/7\n"
        "Obręb: 0003\n"
        "Miejscowość: Wólka Radzymińska\n"
        "Ulica: Leśna 12"
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["125/7"]
    assert result["precinct"] == "0003"
    assert result["city"] == "Wólka Radzymińska"


def test_backfill_from_secondary_windows_when_primary_is_fragmented():
    text = (
        "Projekt dotyczy inwestycji na terenie miasta.\n"
        "Działka nr ewid. 125/7 obręb 0003.\n"
        "\n"
        "\n"
        "\n"
        "Położona w Wólce Radzymińskiej.\n"
        "Ulica Leśna 12."
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["125/7"]
    assert result["precinct"] == "0003"
    assert result["city"] == "Wólce Radzymińskiej"
    assert result["street"] == "Leśna 12"


def test_position_line_without_commas_still_extracts_street_parcel_and_precinct():
    text = "Położenie nieruchomości Warszawa ul Operowa dz ew nr 3/42 z obrębu 4-05-11"
    result = extract_location(_pages(text))

    assert result["city"] == "Warszawa"
    assert result["street"] == "Operowa"
    assert result["parcel_numbers"] == ["3/42"]
    assert result["precinct"] == "4-05-11"


def test_full_text_fallback_extracts_street_when_window_split_is_too_wide():
    text = (
        "Położenie nieruchomości Warszawa,\n"
        "\n"
        "\n"
        "\n"
        "ul. Operowa\n"
        "dz. ew. nr 3/42\n"
        "z obrębu 4-05-11"
    )
    result = extract_location(_pages(text))

    assert result["city"] == "Warszawa"
    assert result["street"] == "Operowa"
    assert result["parcel_numbers"] == ["3/42"]
    assert result["precinct"] == "4-05-11"


def test_parcel_number_from_numer_ewidencyjny_dzialki_label():
    text = "Numer ewidencyjny działki: 88/14, obręb: 0007, miejscowość: Warszawa"
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["88/14"]
    assert result["precinct"] == "0007"
    assert result["city"] == "Warszawa"


def test_first_page_is_preferred_for_parcel_number():
    pages = [
        {"page": 1, "text": "Położenie nieruchomości Warszawa, ul. Operowa, dz. ew. nr 3/42 z obrębu 4-05-11"},
        {"page": 2, "text": "Dane przykładowe: działka nr ewid. 999/1 obręb 0001"},
    ]
    result = extract_location(pages)

    assert result["parcel_numbers"] == ["3/42"]
    assert result["precinct"] == "4-05-11"
    assert result["street"] == "Operowa"
    assert result["city"] == "Warszawa"


def test_fallback_window_prefers_non_footer_candidate():
    text = (
        "URZĄD MIASTA WARSZAWA ul. Modlińska 197, tel. 22 443 82 00\n"
        "Dotyczy inwestycji na działce nr ewid. 65 położonej przy ul. Edmunda Bakalarza 18 w Radomiu."
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["65"]
    assert result["street"] == "Edmunda Bakalarza 18"
    assert result["city"] == "Radomiu"


def test_single_window_mode_avoids_mixing_fields_from_distant_windows():
    text = (
        "Działka nr ewid. 125/7 obręb 0003.\n"
        "Informacja techniczna 1.\n"
        "Informacja techniczna 2.\n"
        "Informacja techniczna 3.\n"
        "Informacja techniczna 4.\n"
        "Położona w Wólce Radzymińskiej.\n"
        "Ulica Leśna 12."
    )
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["125/7"]
    assert result["precinct"] == "0003"
    assert result["city"] is None
    assert result["street"] is None


def test_mixed_backfill_mode_can_merge_missing_fields_from_other_windows():
    text = (
        "Działka nr ewid. 125/7 obręb 0003.\n"
        "Informacja techniczna 1.\n"
        "Informacja techniczna 2.\n"
        "Informacja techniczna 3.\n"
        "Informacja techniczna 4.\n"
        "Położona w Wólce Radzymińskiej.\n"
        "Ulica Leśna 12."
    )
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["125/7"]
    assert result["precinct"] == "0003"
    assert result["city"] == "Wólce Radzymińskiej"
    assert result["street"] == "Leśna 12"


def test_extracts_spacing_and_leading_zero_parcel_variants():
    text = "działka ewid. 00123 / 0004 w obrębie 0001, przy ul. Leśnej 12 w miejscowości Kobyłka"
    result = extract_location(_pages(text))

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "0001"
    assert result["street"] == "Leśnej 12"
    assert result["city"] == "Kobyłka"


def test_extracts_obreb_in_parentheses_next_to_parcel():
    text = "działka nr 123/4 (0001), ul. Leśna 12, 05-200 Kobyłka"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "0001"
    assert result["city"] == "Kobyłka"


def test_extracts_al_pl_os_street_prefixes():
    text = "działki nr 123/4, obręb Stare Miasto, al. Jana Pawła II 15, 00-001 Warszawa"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "Stare Miasto"
    assert result["street"] == "Jana Pawła II 15"
    assert result["city"] == "Warszawa"


def test_extracts_city_from_postal_code_with_district_suffix():
    text = "ul. Leśna 12, 00-001 Warszawa, Wola, działka nr 123/4 obręb 0001"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "0001"
    assert result["city"] == "Warszawa"


def test_extracts_compact_parcel_without_slash_as_number_and_part():
    text = "działka 123 4 obręb 0001, ul. Leśna 12, 05-200 Kobyłka"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "0001"


def test_extracts_parcel_with_backslash_and_fullwidth_slash():
    text = "działki nr 123\\4 oraz 125／2, obręb 0001, ul. Leśna 12, Kobyłka"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4", "125/2"]
    assert result["precinct"] == "0001"


def test_extracts_parcel_from_full_identifier_suffix():
    text = "Id działki: 146501_1.0001.00123/0004, obręb 0001, miejscowość: Kobyłka"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4"]
    assert result["precinct"] == "0001"
    assert result["city"] == "Kobyłka"


def test_extracts_multi_parcel_list_with_text_separators():
    text = "działki nr 123/4 i 123/5 oraz 124/1, obręb 0001, ul. Leśna 12, Warszawa"
    result = extract_location(_pages(text), allow_mixed_backfill=True)

    assert result["parcel_numbers"] == ["123/4", "123/5", "124/1"]
