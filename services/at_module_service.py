import hashlib
import json
import os
import re
import time
from pathlib import Path

from pypdf import PdfReader
from werkzeug.utils import secure_filename

from services.at_industry_classifier import ATIndustryClassifier
from utils.db import create_timestamp


class ATModuleError(Exception):
    def __init__(self, message, status_code=400, code="AT_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class ATModuleService:
    ALLOWED_MIME_TYPES = {"application/pdf", "application/octet-stream"}

    def __init__(self, app):
        self.app = app
        self.industry_classifier = ATIndustryClassifier()

    @staticmethod
    def _parse_json_column(value, fallback):
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    def _document_row_to_dict(self, row):
        return {
            "id": row["id"],
            "originalFileName": row["originalFileName"],
            "storedFileName": row["storedFileName"],
            "storageKey": row["storageKey"],
            "mimeType": row["mimeType"],
            "fileSize": row["fileSize"],
            "fileHash": row["fileHash"],
            "numberOfPages": row["numberOfPages"],
            "uploadStatus": row["uploadStatus"],
            "processingStatus": row["processingStatus"],
            "errorMessage": row["errorMessage"],
            "createdBy": row["createdBy"],
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
            "isDuplicate": bool(row["isDuplicate"]),
            "metadataJson": self._parse_json_column(row["metadataJson"], {}),
            "detectedIndustry": row["detectedIndustry"],
            "detectedIndustries": self._parse_json_column(row["detectedIndustries"], []),
            "industryConfidence": row["industryConfidence"],
            "industryClassificationReason": row["industryClassificationReason"],
            "industrySignals": self._parse_json_column(row["industrySignals"], []),
            "industryClassificationDetails": self._parse_json_column(row["industryClassificationDetails"], {}),
            "industryClassifiedAt": row["industryClassifiedAt"],
        }

    def validate_pdf(self, file_storage):
        filename = secure_filename(file_storage.filename or "")
        if not filename:
            raise ATModuleError("Nieprawidłowa nazwa pliku.")

        ext = Path(filename).suffix.lower()
        if ext != ".pdf":
            raise ATModuleError("Dozwolony jest wyłącznie format PDF (.pdf).", code="UNSUPPORTED_FILE_TYPE")

        normalized_mime = (file_storage.mimetype or "application/octet-stream").lower()
        if normalized_mime not in self.ALLOWED_MIME_TYPES:
            raise ATModuleError("Nieprawidłowy typ MIME. Wgraj poprawny plik PDF.", code="INVALID_MIME")

        max_bytes = self.app.config["AT_MAX_SIZE_MB"] * 1024 * 1024
        file_storage.stream.seek(0, os.SEEK_END)
        size = file_storage.stream.tell()
        file_storage.stream.seek(0)

        if size <= 0:
            raise ATModuleError("Plik jest pusty.", code="EMPTY_FILE")
        if size > max_bytes:
            raise ATModuleError(
                f"Plik przekracza limit {self.app.config['AT_MAX_SIZE_MB']} MB.",
                code="FILE_TOO_LARGE",
            )

        header = file_storage.stream.read(5)
        file_storage.stream.seek(0)
        if header != b"%PDF-":
            raise ATModuleError("Plik nie ma poprawnego nagłówka PDF.", code="INVALID_PDF_HEADER")

        return {"filename": filename, "size": size, "mimeType": normalized_mime}

    def extract_pdf_metadata(self, stored_path):
        try:
            reader = PdfReader(stored_path, strict=False)
            num_pages = len(reader.pages)
            metadata = reader.metadata or {}
            return {
                "numberOfPages": num_pages,
                "title": getattr(metadata, "title", None),
                "author": getattr(metadata, "author", None),
                "subject": getattr(metadata, "subject", None),
                "producer": getattr(metadata, "producer", None),
                "keywords": getattr(metadata, "keywords", None),
            }
        except Exception as error:
            raise ATModuleError(
                f"Nie udało się odczytać metadanych PDF: {error}",
                code="PDF_METADATA_READ_FAILED",
            )

    def _extract_page_headings(self, page_text):
        headings = []
        for raw_line in (page_text or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if len(line) > 140:
                continue
            normalized = line.lower()
            if re.search(r"\b(branża|branza|projekt|rysunek|pzt|instalacja|schemat|zestawienie|tabela)\b", normalized):
                headings.append(line)
            if len(headings) >= 6:
                break
        return headings

    def extract_pdf_text_preview(self, stored_path, max_pages=6):
        try:
            reader = PdfReader(stored_path, strict=False)
            chunks = []
            pages = []
            for page_idx, page in enumerate(reader.pages[:max_pages], start=1):
                raw_text = page.extract_text() or ""
                text = raw_text.strip()
                if text:
                    chunks.append(text[:3000])
                pages.append(
                    {
                        "pageNumber": page_idx,
                        "text": raw_text[:5000],
                        "headings": self._extract_page_headings(raw_text),
                    }
                )
            merged = re.sub(r"\s+", " ", "\n".join(chunks)).strip()
            return {"text": merged[:14000], "charCount": len(merged), "pages": pages}
        except Exception:  # noqa: BLE001
            return {"text": "", "charCount": 0, "pages": []}

    def _sha256_for_path(self, path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def upload_document(self, db, file_storage, created_by):
        validated = self.validate_pdf(file_storage)

        storage_dir = self.app.config["AT_UPLOAD_FOLDER"]
        os.makedirs(storage_dir, exist_ok=True)

        timestamp = int(time.time() * 1000)
        stem = Path(validated["filename"]).stem
        stored_name = f"{stem}_{timestamp}.pdf"
        stored_path = os.path.join(storage_dir, stored_name)
        file_storage.save(stored_path)

        file_hash = self._sha256_for_path(stored_path)
        duplicate = db.execute(
            """
            SELECT id FROM at_documents
            WHERE fileHash = ? AND isDeleted = 0
            LIMIT 1
            """,
            (file_hash,),
        ).fetchone()

        metadata = self.extract_pdf_metadata(stored_path)
        now = create_timestamp()
        cursor = db.execute(
            """
            INSERT INTO at_documents (
                originalFileName, storedFileName, storageKey, mimeType, fileSize, fileHash,
                numberOfPages, uploadStatus, processingStatus, errorMessage, createdBy,
                createdAt, updatedAt, isDuplicate, metadataJson,
                detectedIndustry, detectedIndustries, industryConfidence,
                industryClassificationReason, industrySignals, industryClassificationDetails,
                industryClassifiedAt, isDeleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                validated["filename"],
                stored_name,
                stored_path,
                validated["mimeType"],
                validated["size"],
                file_hash,
                metadata.get("numberOfPages"),
                "UPLOADED",
                "READY",
                None,
                str(created_by) if created_by is not None else "anonymous",
                now,
                now,
                1 if duplicate else 0,
                json.dumps(metadata, ensure_ascii=False),
                None,
                json.dumps([], ensure_ascii=False),
                None,
                None,
                json.dumps([], ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                None,
            ),
        )
        document_id = cursor.lastrowid
        self.create_processing_job(db, document_id, "PENDING")
        row = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(row)

    def create_processing_job(self, db, document_id, status="PENDING", error_message=None):
        now = create_timestamp()
        cursor = db.execute(
            """
            INSERT INTO at_processing_jobs (
                documentId, status, errorMessage, stage, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (document_id, status, error_message, "queued", now, now),
        )
        return cursor.lastrowid

    def get_document_status(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")
        return self._document_row_to_dict(row)

    def classify_document_industry(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        metadata = self._parse_json_column(row["metadataJson"], {})
        text_preview = self.extract_pdf_text_preview(row["storageKey"])
        result = self.industry_classifier.classify_document_industry(
            filename=row["originalFileName"],
            metadata=metadata,
            text=text_preview["text"],
            pages=text_preview.get("pages") or [],
        )

        details = result.get("industryClassificationDetails", {})
        details["textCharCount"] = text_preview["charCount"]
        details["industryScoreBreakdown"] = result.get("industryScoreBreakdown", {})
        details["pageIndustryResults"] = result.get("pageIndustryResults", [])

        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET detectedIndustry = ?,
                detectedIndustries = ?,
                industryConfidence = ?,
                industryClassificationReason = ?,
                industrySignals = ?,
                industryClassificationDetails = ?,
                industryClassifiedAt = ?,
                updatedAt = ?,
                processingStatus = ?,
                errorMessage = NULL
            WHERE id = ?
            """,
            (
                result["detectedIndustry"],
                json.dumps(result["detectedIndustries"], ensure_ascii=False),
                result["industryConfidence"],
                result["industryClassificationReason"],
                json.dumps(result["industrySignals"], ensure_ascii=False),
                json.dumps(details, ensure_ascii=False),
                now,
                now,
                "INDUSTRY_CLASSIFIED",
                document_id,
            ),
        )
        updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(updated)

    def start_processing(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")
        if row["processingStatus"] in {"ANALYZING", "UPLOADING", "CLASSIFYING_INDUSTRY"}:
            raise ATModuleError(
                "Dokument jest już przetwarzany.",
                status_code=409,
                code="PROCESSING_ALREADY_IN_PROGRESS",
            )

        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET processingStatus = ?, uploadStatus = ?, updatedAt = ?, errorMessage = NULL
            WHERE id = ?
            """,
            ("CLASSIFYING_INDUSTRY", "UPLOADED", now, document_id),
        )
        job_id = self.create_processing_job(db, document_id, "RUNNING")
        db.execute(
            "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
            ("RUNNING", "classifying_industry", create_timestamp(), job_id),
        )

        try:
            classified = self.classify_document_industry(db, document_id)
            db.execute(
                "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
                ("COMPLETED", "industry_classified", create_timestamp(), job_id),
            )
            return classified
        except Exception as error:  # noqa: BLE001
            db.execute(
                """
                UPDATE at_documents
                SET processingStatus = ?, errorMessage = ?, updatedAt = ?
                WHERE id = ?
                """,
                ("INDUSTRY_CLASSIFICATION_FAILED", str(error), create_timestamp(), document_id),
            )
            db.execute(
                "UPDATE at_processing_jobs SET status = ?, stage = ?, errorMessage = ?, updatedAt = ? WHERE id = ?",
                ("FAILED", "industry_classification_failed", str(error), create_timestamp(), job_id),
            )
            if isinstance(error, ATModuleError):
                raise
            raise ATModuleError("Nie udało się sklasyfikować branży dokumentu.", status_code=500, code="INDUSTRY_CLASSIFICATION_FAILED")

    def retry_processing(self, db, document_id):
        return self.start_processing(db, document_id)

    def retry_industry_classification(self, db, document_id):
        return self.classify_document_industry(db, document_id)

    def list_documents(self, db):
        rows = db.execute(
            "SELECT * FROM at_documents WHERE isDeleted = 0 ORDER BY createdAt DESC"
        ).fetchall()
        return [self._document_row_to_dict(row) for row in rows]
