import io
import sqlite3

from pathlib import Path

from app import create_app
from pypdf import PdfWriter


def build_test_client(tmp_path):
    upload_dir = tmp_path / "uploads"
    app = create_app(
        {
            "TESTING": True,
            "DB_PATH": str(tmp_path / "test.db"),
            "AT_UPLOAD_FOLDER": str(upload_dir / "at"),
            "AT_MAX_SIZE_MB": 1,
            "AT_MAX_FILES": 2,
        }
    )
    return app.test_client()


def build_pdf_bytes():
    stream = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(stream)
    stream.seek(0)
    return stream


def test_at_menu_button_visible_on_app_page(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    html = (project_root / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'data-menu-tab="at"' in html
    assert 'id="openAtBtn"' in html
    assert '<div class="fab-label">AT</div>' in html
    assert "AT" in html


def test_at_sidebar_button_handler_opens_at_view():
    project_root = Path(__file__).resolve().parents[1]
    js = (project_root / "static" / "js" / "menuPreview.js").read_text(encoding="utf-8")
    assert 'const openAtBtn = document.getElementById("openAtBtn");' in js
    assert 'openAtBtn?.addEventListener("click", () => {' in js
    assert 'setMenuPreviewView(true);' in js
    assert 'setMenuTab("at");' in js


def test_at_upload_rejects_non_pdf(tmp_path):
    client = build_test_client(tmp_path)
    response = client.post(
        "/api/at/documents",
        data={"file": (io.BytesIO(b"hello"), "foo.txt")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400


def test_at_upload_rejects_too_large_file(tmp_path):
    client = build_test_client(tmp_path)
    huge = b"%PDF-" + b"a" * (2 * 1024 * 1024)
    response = client.post(
        "/api/at/documents",
        data={"file": (io.BytesIO(huge), "large.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "limit" in response.get_json()["errors"][0]["error"].lower() or "limit" in response.get_json().get("error", "").lower()


def test_at_upload_and_process_happy_path(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt.pdf")},
        content_type="multipart/form-data",
    )
    assert upload_response.status_code == 201
    payload = upload_response.get_json()
    document_id = payload["documents"][0]["id"]

    process_response = client.post(f"/api/at/documents/{document_id}/process")
    assert process_response.status_code == 200
    process_payload = process_response.get_json()
    assert process_payload["document"]["processingStatus"] == "INDUSTRY_CLASSIFIED"
    assert "detectedIndustry" in process_payload["document"]
    assert "industryConfidence" in process_payload["document"]
    assert "detectedContentType" in process_payload["document"]
    assert "pageContentResults" in process_payload["document"]


def test_at_retry_industry_classification_endpoint(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt_architektura.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]
    client.post(f"/api/at/documents/{document_id}/process")

    response = client.post(f"/api/at/documents/{document_id}/classify-industry/retry")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["document"]["detectedIndustry"] in {
        "Architektura",
        "PZT",
        "Konstrukcja",
        "Elektryka",
        "Wod-kan",
        "Wentylacja",
        "Nieznana",
        "Wiele branż",
    }


def test_at_document_detail_contains_industry_fields(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]
    client.post(f"/api/at/documents/{document_id}/process")

    detail_response = client.get(f"/api/at/documents/{document_id}")
    assert detail_response.status_code == 200
    document = detail_response.get_json()["document"]
    assert "detectedIndustry" in document
    assert "detectedIndustries" in document
    assert "industryConfidence" in document
    assert "industryClassificationReason" in document
    assert "detectedContentType" in document
    assert "detectedContentTypes" in document
    assert "contentTypeConfidence" in document
    assert "contentTypePagesSummary" in document


def test_at_retry_content_type_classification_endpoint(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt_schemat.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]
    client.post(f"/api/at/documents/{document_id}/process")

    response = client.post(f"/api/at/documents/{document_id}/classify-content-type/retry")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["document"]["detectedContentType"] in {
        "Opis",
        "Rzut",
        "Przekrój",
        "Elewacja",
        "Schemat",
        "Zestawienie",
        "Detal",
        "Plan sytuacyjny / PZT",
        "Legenda",
        "Inna / Nieznana",
    }


def test_at_upload_limit_number_of_files(tmp_path):
    client = build_test_client(tmp_path)
    response = client.post(
        "/api/at/documents",
        data={
            "files": [
                (io.BytesIO(b"%PDF-1.4\n%%EOF"), "a.pdf"),
                (build_pdf_bytes(), "b.pdf"),
                (build_pdf_bytes(), "c.pdf"),
            ]
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "FILES_LIMIT_EXCEEDED"


def test_at_page_content_type_override_endpoint(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt_override.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]
    client.post(f"/api/at/documents/{document_id}/process")

    response = client.patch(
        f"/api/at/documents/{document_id}/pages/1/content-type-override",
        json={"contentTypeOverride": "Detal", "contentTypeOverrideReason": "manualna korekta"},
    )
    assert response.status_code == 200
    document = response.get_json()["document"]
    assert document["contentTypeOverride"] == "Detal"
    assert document["contentTypeConfirmedByUser"] in {"Detal", "Inna / Nieznana", "Rzut", "Przekrój", "Elewacja", "Schemat", "Zestawienie", "Plan sytuacyjny / PZT", "Legenda", "Opis"}
    assert any(page.get("isUserOverridden") for page in document.get("pageContentResults", []))


def test_at_retry_project_matching_and_project_creation(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt_match.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]

    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE at_documents
            SET projectTitleDetected = ?, projectTitleNormalized = ?, projectTitleConfidence = ?,
                investmentAddressDetected = ?, investmentAddressNormalized = ?, investmentAddressConfidence = ?,
                plotNumberDetected = ?, plotNumberNormalized = ?, projectIdentityConfidence = ?, projectAssignmentStatus = ?
            WHERE id = ?
            """,
            (
                "Budowa budynku mieszkalnego jednorodzinnego",
                "budowa budynku mieszkalnego jednorodzinnego",
                0.91,
                "ul. Lipowa 12, Kraków",
                "ul. lipowa 12, kraków",
                0.9,
                "145/7",
                "145/7",
                0.9,
                "matching_pending",
                document_id,
            ),
        )
        conn.commit()

    response = client.post(f"/api/at/documents/{document_id}/match-project/retry")
    assert response.status_code == 200
    payload = response.get_json()["document"]
    assert payload["projectAssignmentStatus"] in {"project_created", "project_matched", "review_required"}


def test_at_manual_project_identity_override(tmp_path):
    client = build_test_client(tmp_path)
    upload_response = client.post(
        "/api/at/documents",
        data={"file": (build_pdf_bytes(), "projekt_override_identity.pdf")},
        content_type="multipart/form-data",
    )
    document_id = upload_response.get_json()["documents"][0]["id"]

    response = client.patch(
        f"/api/at/documents/{document_id}/project-identity-override",
        json={
            "projectTitle": "Budowa budynku mieszkalnego jednorodzinnego",
            "investmentAddress": "ul. Lipowa 12, Kraków",
            "plotNumber": "145/7",
            "reason": "korekta ręczna",
        },
    )
    assert response.status_code == 200
    document = response.get_json()["document"]
    assert document["projectAssignmentStatus"] == "manually_reviewed"
    assert document["projectIdentityOverrideJson"]["plotNumber"] == "145/7"


def test_at_projects_endpoint_lists_detected_projects(tmp_path):
    client = build_test_client(tmp_path)
    response = client.get("/api/at/projects")
    assert response.status_code == 200
    payload = response.get_json()
    assert "projects" in payload
    assert isinstance(payload["projects"], list)
