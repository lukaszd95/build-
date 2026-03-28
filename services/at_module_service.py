import hashlib
import os
import time
from pathlib import Path

from pypdf import PdfReader
from werkzeug.utils import secure_filename

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
            "metadataJson": row["metadataJson"],
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
            }
        except Exception as error:
            raise ATModuleError(
                f"Nie udało się odczytać metadanych PDF: {error}",
                code="PDF_METADATA_READ_FAILED",
            )

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
                createdAt, updatedAt, isDuplicate, metadataJson, isDeleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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
                str(metadata),
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

    def start_processing(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")
        if row["processingStatus"] in {"ANALYZING", "UPLOADING"}:
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
            ("ANALYZING", "UPLOADED", now, document_id),
        )
        job_id = self.create_processing_job(db, document_id, "RUNNING")
        db.execute(
            "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
            ("COMPLETED", "ready_for_ocr", create_timestamp(), job_id),
        )
        db.execute(
            """
            UPDATE at_documents
            SET processingStatus = ?, updatedAt = ?
            WHERE id = ?
            """,
            ("COMPLETED", create_timestamp(), document_id),
        )
        row = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(row)

    def retry_processing(self, db, document_id):
        return self.start_processing(db, document_id)

    def list_documents(self, db):
        rows = db.execute(
            "SELECT * FROM at_documents WHERE isDeleted = 0 ORDER BY createdAt DESC"
        ).fetchall()
        return [self._document_row_to_dict(row) for row in rows]
