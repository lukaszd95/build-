import pytest

fpdf = pytest.importorskip("fpdf")
pil = pytest.importorskip("PIL")

from fpdf import FPDF
from PIL import Image

from utils.extraction_pipeline import build_extraction_result, extract_text_from_image, extract_text_from_pdf


def test_pdf_integration_extracts_fields(tmp_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(
        0,
        8,
        "Maksymalna wysokosc zabudowy: 9 m.\nPowierzchnia biologicznie czynna 25 %.",
    )
    pdf_path = tmp_path / "sample.pdf"
    pdf.output(str(pdf_path))

    pages = extract_text_from_pdf(str(pdf_path))
    extraction = build_extraction_result(pages)
    fields = {field["fieldKey"]: field for field in extraction["fields"]}

    assert fields["maxBuildingHeightM"]["value"] == 9.0
    assert fields["maxBuildingHeightM"]["status"] == "EXTRACTED"
    assert fields["minBiologicallyActivePct"]["value"] == 25.0
    assert fields["minBiologicallyActivePct"]["status"] == "EXTRACTED"


def test_scan_image_requires_review(tmp_path):
    img_path = tmp_path / "scan.jpg"
    img = Image.new("RGB", (200, 200), color="white")
    img.save(img_path)

    pages = extract_text_from_image(str(img_path))
    extraction = build_extraction_result(pages)
    fields = {field["fieldKey"]: field for field in extraction["fields"]}

    assert fields["maxBuildingHeightM"]["value"] is None
    assert fields["maxBuildingHeightM"]["status"] == "REQUIRES_REVIEW"
