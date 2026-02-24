import io
import json
import logging
import os
import sqlite3
from datetime import datetime

from utils.extraction_rules import (
    extract_fields_from_pages,
    extract_locality_refs,
    extract_obreb_refs,
    extract_parcel_refs,
    extract_street_refs,
)
from utils.llm_extraction import build_extraction_from_llm, is_llm_enabled, is_llm_strict

_DOCTR_PREDICTOR = None


def _utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def detect_format(filename, mime_type):
    extension = os.path.splitext(filename)[1].lower()
    if extension == ".pdf" or mime_type == "application/pdf":
        return "pdf"
    if mime_type.startswith("image/") or extension in {".png", ".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff"}:
        return "image"
    return "unknown"


def _load_pytesseract():
    try:
        import pytesseract
    except ModuleNotFoundError:
        return None
    return pytesseract


def _load_doctr_predictor():
    global _DOCTR_PREDICTOR
    if _DOCTR_PREDICTOR is not None:
        return _DOCTR_PREDICTOR
    try:
        from doctr.models import ocr_predictor
    except Exception:
        return None
    try:
        _DOCTR_PREDICTOR = ocr_predictor(pretrained=True)
    except Exception:
        return None
    return _DOCTR_PREDICTOR


def _doctr_result_to_pages(result):
    exported = result.export()
    pages_text = []
    for page in exported.get("pages", []):
        lines = []
        for block in page.get("blocks", []):
            for line in block.get("lines", []):
                words = [
                    word.get("value")
                    for word in line.get("words", [])
                    if word.get("value")
                ]
                if words:
                    lines.append(" ".join(words))
        pages_text.append("\n".join(lines))
    return pages_text


def _doctr_ocr_file(file_path, file_type):
    predictor = _load_doctr_predictor()
    if predictor is None:
        return None
    try:
        from doctr.io import DocumentFile
    except ModuleNotFoundError:
        return None
    try:
        if file_type == "pdf":
            document = DocumentFile.from_pdf(file_path)
        else:
            document = DocumentFile.from_images(file_path)
        result = predictor(document)
        return _doctr_result_to_pages(result)
    except Exception:
        return None


def _ocr_pil_image(image, ocr_lang):
    pytesseract = _load_pytesseract()
    if pytesseract is None:
        return ""
    try:
        return pytesseract.image_to_string(image, lang=ocr_lang)
    except Exception:
        if ocr_lang != "eng":
            try:
                return pytesseract.image_to_string(image, lang="eng")
            except Exception:
                return ""
        return ""


def _ocr_images_from_pdf_page(page, ocr_lang):
    text_chunks = []
    images = getattr(page, "images", None)
    if not images:
        return ""

    from PIL import Image

    for image in images:
        data = getattr(image, "data", None)
        if data is None and hasattr(image, "get_data"):
            try:
                data = image.get_data()
            except Exception:
                data = None
        if not data:
            continue
        try:
            with Image.open(io.BytesIO(data)) as pil_image:
                text = _ocr_pil_image(pil_image, ocr_lang)
                if text:
                    text_chunks.append(text)
        except Exception:
            continue
    return " ".join(text_chunks)


def extract_text_from_pdf(file_path):
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = []
    ocr_lang = os.getenv("OCR_LANG", "pol+eng")
    empty_pages = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            text = _ocr_images_from_pdf_page(page, ocr_lang)
        if not text.strip():
            empty_pages.append(idx - 1)
        pages.append({"page": idx, "text": text})
    if empty_pages:
        doctr_pages = _doctr_ocr_file(file_path, "pdf")
        if doctr_pages:
            for page_index in empty_pages:
                if page_index < len(doctr_pages):
                    doctr_text = doctr_pages[page_index]
                    if doctr_text and doctr_text.strip():
                        pages[page_index]["text"] = doctr_text
    return pages


def extract_text_from_image(file_path):
    from PIL import Image

    try:
        import pillow_heif  # type: ignore

        pillow_heif.register_heif_opener()
    except Exception:
        pass

    ocr_lang = os.getenv("OCR_LANG", "pol+eng")
    text = ""
    try:
        with Image.open(file_path) as image:
            text = _ocr_pil_image(image, ocr_lang)
    except Exception:
        text = ""
    doctr_text = None
    doctr_pages = _doctr_ocr_file(file_path, "image")
    if doctr_pages:
        doctr_text = doctr_pages[0] if doctr_pages else None
    if doctr_text and len(doctr_text.strip()) > len(text.strip()):
        text = doctr_text
    return [{"page": 1, "text": text or ""}]


def build_extraction_result(pages, use_llm=True):
    if use_llm and is_llm_enabled():
        try:
            return build_extraction_from_llm(pages)
        except Exception:
            if is_llm_strict():
                raise
    parcel_refs = extract_parcel_refs(pages)
    obreb_refs = extract_obreb_refs(pages)
    street_refs = extract_street_refs(pages)
    locality_refs = extract_locality_refs(pages)
    fields = extract_fields_from_pages(pages)
    return {
        "parcelRefs": parcel_refs,
        "obrebRefs": obreb_refs,
        "streetRefs": street_refs,
        "localityRefs": locality_refs,
        "fields": fields,
    }


def process_upload(upload, db_path):
    upload_id = upload["id"]
    logger = logging.getLogger("upload-pipeline")
    logger.info("Processing upload %s", upload_id)

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    format_type = detect_format(upload["filename"], upload["mimeType"])
    if format_type == "pdf":
        pages = extract_text_from_pdf(upload["storageUrl"])
    elif format_type == "image":
        pages = extract_text_from_image(upload["storageUrl"])
    else:
        pages = [{"page": 1, "text": ""}]

    extraction = build_extraction_result(pages)
    parcel_refs = extraction["parcelRefs"]
    obreb_refs = extraction["obrebRefs"]
    street_refs = extraction["streetRefs"]
    locality_refs = extraction["localityRefs"]
    fields = extraction["fields"]

    parcel_id = None
    unique_parcels = {ref["parcelId"] for ref in parcel_refs}
    if len(unique_parcels) == 1:
        parcel_id = next(iter(unique_parcels))

    for ref in parcel_refs:
        db.execute(
            """
            INSERT INTO extracted_fields
            (uploadId, parcelId, fieldKey, value, confidence, status, source, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                ref["parcelId"],
                "parcelReference",
                json.dumps({"parcelId": ref["parcelId"]}),
                0.9,
                "EXTRACTED",
                json.dumps(
                    {
                        "page": ref["page"],
                        "bbox": None,
                        "rawText": ref["rawText"],
                    }
                ),
                _utc_now(),
            ),
        )

    for ref in obreb_refs:
        db.execute(
            """
            INSERT INTO extracted_fields
            (uploadId, parcelId, fieldKey, value, confidence, status, source, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                None,
                "obrebReference",
                json.dumps({"obreb": ref["obreb"]}),
                0.85,
                "EXTRACTED",
                json.dumps(
                    {
                        "page": ref["page"],
                        "bbox": None,
                        "rawText": ref["rawText"],
                    }
                ),
                _utc_now(),
            ),
        )

    for ref in street_refs:
        db.execute(
            """
            INSERT INTO extracted_fields
            (uploadId, parcelId, fieldKey, value, confidence, status, source, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                None,
                "streetReference",
                json.dumps({"street": ref["street"]}),
                0.8,
                "EXTRACTED",
                json.dumps(
                    {
                        "page": ref["page"],
                        "bbox": None,
                        "rawText": ref["rawText"],
                    }
                ),
                _utc_now(),
            ),
        )

    for ref in locality_refs:
        db.execute(
            """
            INSERT INTO extracted_fields
            (uploadId, parcelId, fieldKey, value, confidence, status, source, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                None,
                "localityReference",
                json.dumps({"locality": ref["locality"]}),
                0.8,
                "EXTRACTED",
                json.dumps(
                    {
                        "page": ref["page"],
                        "bbox": None,
                        "rawText": ref["rawText"],
                    }
                ),
                _utc_now(),
            ),
        )

    for field in fields:
        assigned_parcel = parcel_id
        value = json.dumps(field["value"]) if field["value"] is not None else None
        source = {
            "page": field["page"],
            "bbox": field["bbox"],
            "rawText": field["rawText"],
        }
        db.execute(
            """
            INSERT INTO extracted_fields
            (uploadId, parcelId, fieldKey, value, confidence, status, source, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id,
                assigned_parcel,
                field["fieldKey"],
                value,
                field["confidence"],
                field["status"],
                json.dumps(source),
                _utc_now(),
            ),
        )

    db.execute("UPDATE uploads SET status = ? WHERE id = ?", ("DONE", upload_id))
    db.commit()

    if parcel_id:
        refresh_parcel_plan_rules(db, parcel_id)

    db.close()
    logger.info("Processing upload %s done", upload_id)
    return extraction


def refresh_parcel_plan_rules(db, parcel_id):
    rows = db.execute(
        """
        SELECT id, fieldKey, value, status
        FROM extracted_fields
        WHERE parcelId = ?
        AND status IN ('EXTRACTED', 'CONFIRMED', 'USER_EDITED')
        """,
        (parcel_id,),
    ).fetchall()

    rules = {}
    provenance = {}
    for row in rows:
        if row["fieldKey"] == "parcelReference":
            continue
        raw_value = row["value"]
        parsed_value = None
        if raw_value is not None:
            try:
                parsed_value = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed_value = raw_value
        rules[row["fieldKey"]] = parsed_value
        provenance[row["fieldKey"]] = row["id"]

    payload = json.dumps(rules)
    provenance_json = json.dumps(provenance)
    now = _utc_now()
    existing = db.execute(
        "SELECT id FROM parcel_plan_rules WHERE parcelId = ?",
        (parcel_id,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE parcel_plan_rules
            SET rulesJson = ?, provenanceJson = ?, lastUpdatedAt = ?
            WHERE parcelId = ?
            """,
            (payload, provenance_json, now, parcel_id),
        )
    else:
        db.execute(
            """
            INSERT INTO parcel_plan_rules (parcelId, rulesJson, provenanceJson, lastUpdatedAt)
            VALUES (?, ?, ?, ?)
            """,
            (parcel_id, payload, provenance_json, now),
        )
    db.commit()
