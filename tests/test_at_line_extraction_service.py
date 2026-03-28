import fitz

from services.at_line_extraction_service import ATLineExtractionService


def _build_pdf_without_vectors(path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=150)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 150), False)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    doc.close()


def _build_pdf_with_vectors(path):
    doc = fitz.open()
    page = doc.new_page(width=200, height=150)
    shape = page.new_shape()
    shape.draw_line((10, 10), (180, 10))
    shape.draw_line((10, 10), (10, 140))
    shape.finish(width=1.0, color=(0, 0, 0))
    shape.commit()
    doc.save(path)
    doc.close()


def test_vector_source_preferred_and_not_mislabeled_as_raster(tmp_path):
    pdf_path = tmp_path / "vector.pdf"
    _build_pdf_with_vectors(str(pdf_path))
    service = ATLineExtractionService({"AT_LINES_MIN_LENGTH": 2})

    result = service.extract_page_lines(str(pdf_path), 1)

    assert result["extractionSource"] == "pdf_vector"
    assert result["fallbackUsed"] is False
    assert result["nativeVectorAvailable"] is True
    assert result["nativeVectorUsed"] is True
    assert all(line["sourceType"] == "pdf_vector" for line in result["lines"])


def test_raster_fallback_used_only_when_vector_geometry_missing(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _build_pdf_without_vectors(str(pdf_path))
    service = ATLineExtractionService({"AT_LINES_MIN_LENGTH": 2})

    result = service.extract_page_lines(str(pdf_path), 1)

    assert result["fallbackUsed"] is True
    assert result["fallbackReason"] == "no_usable_pdf_vector_geometry" or str(result["fallbackReason"]).startswith("raster_failed:")
    assert result["extractionSource"] in {"raster_detected", "pdf_vector"}
    if result["extractionSource"] == "raster_detected":
        assert all(line["sourceType"] == "raster_detected" for line in result["lines"])


def test_normalization_filters_zero_length_and_preserves_pdf_coordinates():
    service = ATLineExtractionService({"AT_LINES_VECTOR_MIN_LENGTH": 0.5, "AT_LINES_DEDUPE_EPS": 0.1})
    lines = [
        {"x1": 10.0, "y1": 10.0, "x2": 10.0, "y2": 10.0, "length": 0.0, "angle": 0.0},
        {"x1": 15.0, "y1": 20.0, "x2": 115.0, "y2": 20.0, "length": 100.0, "angle": 0.0},
    ]

    normalized, rejected = service.normalize_and_filter(lines, 200.0, 150.0, "pdf_vector")

    assert len(normalized) == 1
    assert normalized[0]["x1"] == 15.0
    assert normalized[0]["y1"] == 20.0
    assert rejected["rejectedShort"] == 1
