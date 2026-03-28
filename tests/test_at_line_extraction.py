import io

import fitz

from app import create_app


def build_test_client(tmp_path):
    upload_dir = tmp_path / "uploads"
    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": str(tmp_path / "test.db"),
            "AT_UPLOAD_FOLDER": str(upload_dir / "at"),
            "AT_MAX_SIZE_MB": 4,
            "AT_MAX_FILES": 4,
            "AT_LINES_VECTOR_MIN": 2,
            "AT_LINES_MIN_LENGTH": 2,
        }
    )
    return app.test_client()


def _upload(client, pdf_bytes, name="plan.pdf"):
    response = client.post(
        "/api/at/documents",
        data={"file": (io.BytesIO(pdf_bytes), name)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    return response.get_json()["documents"][0]["id"]


def build_vector_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page(width=300, height=220)
    shape = page.new_shape()
    shape.draw_line((20, 20), (180, 20))
    shape.draw_line((20, 20), (20, 160))
    shape.draw_line((20, 160), (180, 160))
    shape.draw_line((180, 20), (180, 160))
    shape.finish(width=1.2, color=(0, 0, 0))
    shape.commit()
    b = doc.tobytes()
    doc.close()
    return b


def build_raster_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page(width=300, height=220)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 440), False)
    pix.clear_with(255)
    # draw black horizontal + vertical bars into pix samples
    data = bytearray(pix.samples)
    width = pix.width
    for y in range(50, 390):
        idx = (y * width + 80) * 3
        data[idx:idx + 3] = b"\x00\x00\x00"
    for x in range(100, 520):
        idx = (120 * width + x) * 3
        data[idx:idx + 3] = b"\x00\x00\x00"
    pix2 = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, bytes(data), False)
    page.insert_image(page.rect, pixmap=pix2)
    b = doc.tobytes()
    doc.close()
    return b


def set_page_as_rzut(client, document_id, page=1):
    response = client.patch(
        f"/api/at/documents/{document_id}/pages/{page}/content-type-override",
        json={"contentTypeOverride": "Rzut", "contentTypeOverrideReason": "test"},
    )
    assert response.status_code == 200


def test_vector_line_extraction_for_rzut_page(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_vector_pdf_bytes(), "vector_plan.pdf")
    client.post(f"/api/at/documents/{document_id}/process")
    set_page_as_rzut(client, document_id)

    response = client.post(f"/api/at/documents/{document_id}/extract-lines")
    assert response.status_code == 200
    payload = response.get_json()
    page = payload["pages"][0]
    assert page["pageNumber"] == 1
    assert page["lineCount"] >= 4
    assert page["extractionSource"] == "pdf_vector"
    assert page["diagnostics"]["nativeVectorAvailable"] is True
    assert page["diagnostics"]["nativeVectorUsed"] is True
    assert page["diagnostics"]["fallbackUsed"] is False
    assert page["extractionStatus"] in {"COMPLETED", "EMPTY"}


def test_get_lines_returns_404_before_extraction(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_vector_pdf_bytes(), "before_extract.pdf")
    client.post(f"/api/at/documents/{document_id}/process")
    set_page_as_rzut(client, document_id)

    response = client.get(f"/api/at/documents/{document_id}/pages/1/lines")
    assert response.status_code == 404


def test_retry_endpoint_extracts_page(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_vector_pdf_bytes(), "retry_extract.pdf")
    client.post(f"/api/at/documents/{document_id}/process")
    set_page_as_rzut(client, document_id)

    response = client.post(f"/api/at/documents/{document_id}/pages/1/extract-lines/retry")
    assert response.status_code == 200
    page = response.get_json()["page"]
    assert page["pageNumber"] == 1
    assert page["lineCount"] >= 1
    assert page["extractionSource"] == "pdf_vector"


def test_non_rzut_page_is_rejected(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_vector_pdf_bytes(), "non_rzut.pdf")
    client.post(f"/api/at/documents/{document_id}/process")

    response = client.post(f"/api/at/documents/{document_id}/pages/1/extract-lines/retry")
    assert response.status_code in {409, 404}


def test_raster_fallback_signal_is_reported_when_vector_is_missing(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_raster_pdf_bytes(), "scan_plan.pdf")
    client.post(f"/api/at/documents/{document_id}/process")
    set_page_as_rzut(client, document_id)

    response = client.post(f"/api/at/documents/{document_id}/extract-lines")
    assert response.status_code == 200
    page = response.get_json()["pages"][0]
    assert page["diagnostics"].get("fallbackUsed") is True
    assert page["extractionSource"] in {"raster_detected", "pdf_vector"}
    if page["extractionSource"] == "pdf_vector":
        assert str(page["diagnostics"].get("fallbackReason", "")).startswith("raster_failed:")


def test_line_payload_contains_length_and_angle(tmp_path):
    client = build_test_client(tmp_path)
    document_id = _upload(client, build_vector_pdf_bytes(), "metrics_plan.pdf")
    client.post(f"/api/at/documents/{document_id}/process")
    set_page_as_rzut(client, document_id)
    client.post(f"/api/at/documents/{document_id}/extract-lines")

    response = client.get(f"/api/at/documents/{document_id}/pages/1/lines")
    assert response.status_code == 200
    line = response.get_json()["page"]["lines"][0]
    assert line["length"] > 0
    assert 0 <= line["angle"] <= 360
    assert line["sourceType"] in {"pdf_vector", "raster_detected"}
