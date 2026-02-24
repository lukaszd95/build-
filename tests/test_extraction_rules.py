from utils.extraction_rules import (
    extract_fields_from_pages,
    extract_locality_refs,
    extract_street_refs,
    validate_unit_presence,
)


def test_validate_unit_presence():
    assert validate_unit_presence("wysokość 9 m", "m") is True
    assert validate_unit_presence("wysokość 9", "m") is False


def test_rule_extraction_basic():
    pages = [
        {
            "page": 1,
            "text": (
                "Przeznaczenie terenu: MN – zabudowa mieszkaniowa jednorodzinna.\n"
                "Maksymalna wysokość zabudowy: 9 m.\n"
                "Powierzchnia biologicznie czynna 30 %.\n"
                "Dach dwuspadowy, kąt nachylenia 35°."
            ),
        }
    ]

    fields = extract_fields_from_pages(pages)
    data = {field["fieldKey"]: field for field in fields}

    assert data["terrainSymbol"]["value"] == "MN"
    assert data["terrainSymbol"]["status"] == "EXTRACTED"
    assert data["maxBuildingHeightM"]["value"] == 9.0
    assert data["maxBuildingHeightM"]["status"] == "EXTRACTED"
    assert data["minBiologicallyActivePct"]["value"] == 30.0
    assert data["minBiologicallyActivePct"]["status"] == "EXTRACTED"
    assert data["roofType"]["value"] == "dach dwuspadowy"
    assert data["roofAngleDeg"]["value"] == 35.0


def test_rule_extraction_bio_active_with_min_share_phrase():
    pages = [
        {
            "page": 1,
            "text": "Minimalny udział powierzchni biologicznie czynnej: 25%.",
        }
    ]

    fields = extract_fields_from_pages(pages)
    data = {field["fieldKey"]: field for field in fields}

    assert data["minBiologicallyActivePct"]["value"] == 25.0
    assert data["minBiologicallyActivePct"]["status"] == "EXTRACTED"


def test_street_extraction_ignores_planowania_word():
    pages = [
        {
            "page": 1,
            "text": "Ulica: Planowania Przestrzennego\nStudium planowania przestrzennego",
        }
    ]

    streets = extract_street_refs(pages)

    assert len(streets) == 1
    assert streets[0]["street"] == "Planowania Przestrzennego"


def test_locality_extraction_ignores_miasta_stolecznego():
    pages = [
        {
            "page": 1,
            "text": "Planowania przestrzennego miasta stołecznego Warszawy",
        }
    ]

    localities = extract_locality_refs(pages)

    assert localities == []


def test_street_extraction_stops_before_postal_and_locality():
    pages = [
        {
            "page": 1,
            "text": "Adres: ul. Kwiatowa 12 00-001 Warszawa",
        }
    ]

    streets = extract_street_refs(pages)

    assert len(streets) == 1
    assert streets[0]["street"] == "Kwiatowa 12"


def test_locality_extraction_trims_after_comma():
    pages = [
        {
            "page": 1,
            "text": "Miejscowość: Kraków, obręb 0123",
        }
    ]

    localities = extract_locality_refs(pages)

    assert len(localities) == 1
    assert localities[0]["locality"] == "Kraków"


def test_street_extraction_stops_before_district_phrase():
    pages = [
        {
            "page": 1,
            "text": (
                "położona przy ul. Słonecki w dzielnicy Wawer w Warszawie."
            ),
        }
    ]

    streets = extract_street_refs(pages)

    assert len(streets) == 1
    assert streets[0]["street"] == "Słonecki"


def test_street_extraction_prioritizes_address_line():
    pages = [
        {
            "page": 1,
            "text": (
                "Kontakt: ul. Urzędowa 1\n"
                "Adres: ul. Kwiatowa 2 00-001 Warszawa"
            ),
        }
    ]

    streets = extract_street_refs(pages)

    assert len(streets) == 2
    assert streets[0]["street"] == "Kwiatowa 2"
