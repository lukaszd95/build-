import hashlib
import json
import os
import re
import time
from pathlib import Path
from collections import Counter

from pypdf import PdfReader
from werkzeug.utils import secure_filename

from services.at_content_type_classifier import ATContentTypeClassifier, CONTENT_TYPES
from services.at_industry_classifier import ATIndustryClassifier
from services.at_line_extraction_service import ATLineExtractionService
from services.at_scale_detection_service import ATScaleDetectionService
from services.at_project_identity_service import (
    build_match_score,
    explain_signals,
    extract_investment_address,
    extract_land_registry_unit,
    extract_plot_number,
    extract_project_title,
    to_json,
)
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
        self.content_type_classifier = ATContentTypeClassifier()
        self.line_extraction_service = ATLineExtractionService(app.config)
        self.scale_detection_service = ATScaleDetectionService()

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
            "detectedContentType": row["detectedContentType"],
            "detectedContentTypes": self._parse_json_column(row["detectedContentTypes"], []),
            "contentTypeConfidence": row["contentTypeConfidence"],
            "contentTypeScoreBreakdown": self._parse_json_column(row["contentTypeScoreBreakdown"], {}),
            "contentTypeReason": row["contentTypeReason"],
            "contentTypePagesSummary": self._parse_json_column(row["contentTypePagesSummary"], {}),
            "pageContentResults": self._parse_json_column(row["pageContentResults"], []),
            "contentTypeSignals": self._parse_json_column(row["contentTypeSignals"], []),
            "isMixedContent": bool(row["isMixedContent"]) if row["isMixedContent"] is not None else False,
            "contentTypeDetectedBySystem": row["contentTypeDetectedBySystem"] or row["detectedContentType"],
            "contentTypeConfirmedByUser": row["contentTypeConfirmedByUser"],
            "contentTypeOverride": row["contentTypeOverride"],
            "contentTypeOverrideReason": row["contentTypeOverrideReason"],
            "contentTypeClassifiedAt": row["contentTypeClassifiedAt"],
            "projectTitleDetected": row["projectTitleDetected"],
            "projectTitleNormalized": row["projectTitleNormalized"],
            "projectTitleConfidence": row["projectTitleConfidence"],
            "projectTitleSource": row["projectTitleSource"],
            "investmentAddressDetected": row["investmentAddressDetected"],
            "investmentAddressNormalized": row["investmentAddressNormalized"],
            "investmentAddressConfidence": row["investmentAddressConfidence"],
            "investmentAddressSource": row["investmentAddressSource"],
            "plotNumberDetected": row["plotNumberDetected"],
            "plotNumberNormalized": row["plotNumberNormalized"],
            "landRegistryUnitDetected": row["landRegistryUnitDetected"],
            "projectIdentityConfidence": row["projectIdentityConfidence"],
            "projectIdentitySignals": self._parse_json_column(row["projectIdentitySignals"], {}),
            "projectMatchScore": row["projectMatchScore"],
            "projectMatchReason": row["projectMatchReason"],
            "projectAssignmentStatus": row["projectAssignmentStatus"],
            "assignedAtProjectId": row["assignedAtProjectId"],
            "projectIdentityOverrideJson": self._parse_json_column(row["projectIdentityOverrideJson"], {}),
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
        insert_values = [
            validated["filename"], stored_name, stored_path, validated["mimeType"], validated["size"], file_hash,
            metadata.get("numberOfPages"), "UPLOADED", "READY", None, str(created_by) if created_by is not None else "anonymous",
            now, now, 1 if duplicate else 0, json.dumps(metadata, ensure_ascii=False),
            None, json.dumps([], ensure_ascii=False), None, None, json.dumps([], ensure_ascii=False), json.dumps({}, ensure_ascii=False), None,
            None, json.dumps([], ensure_ascii=False), None, json.dumps({}, ensure_ascii=False), None, json.dumps({}, ensure_ascii=False),
            json.dumps([], ensure_ascii=False), json.dumps([], ensure_ascii=False), 0, None, None, None, None, None,
            # project identity fields (18)
            None, None, None, None,
            None, None, None, None,
            None, None, None,
            None, json.dumps({}, ensure_ascii=False),
            None, None, "unassigned", None, json.dumps({}, ensure_ascii=False),
        ]
        placeholders = ", ".join(["?"] * len(insert_values))
        cursor = db.execute(
            f"""
            INSERT INTO at_documents (
                originalFileName, storedFileName, storageKey, mimeType, fileSize, fileHash,
                numberOfPages, uploadStatus, processingStatus, errorMessage, createdBy,
                createdAt, updatedAt, isDuplicate, metadataJson,
                detectedIndustry, detectedIndustries, industryConfidence,
                industryClassificationReason, industrySignals, industryClassificationDetails, industryClassifiedAt,
                detectedContentType, detectedContentTypes, contentTypeConfidence,
                contentTypeScoreBreakdown, contentTypeReason, contentTypePagesSummary,
                pageContentResults, contentTypeSignals, isMixedContent,
                contentTypeDetectedBySystem, contentTypeConfirmedByUser, contentTypeOverride, contentTypeOverrideReason, contentTypeClassifiedAt,
                projectTitleDetected, projectTitleNormalized, projectTitleConfidence, projectTitleSource,
                investmentAddressDetected, investmentAddressNormalized, investmentAddressConfidence, investmentAddressSource,
                plotNumberDetected, plotNumberNormalized, landRegistryUnitDetected,
                projectIdentityConfidence, projectIdentitySignals,
                projectMatchScore, projectMatchReason, projectAssignmentStatus, assignedAtProjectId, projectIdentityOverrideJson
            ) VALUES ({placeholders})
            """,
            insert_values,
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

    def classify_document_content_types(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        metadata = self._parse_json_column(row["metadataJson"], {})
        text_preview = self.extract_pdf_text_preview(row["storageKey"], max_pages=50)
        result = self.content_type_classifier.classify_document_content_types(
            filename=row["originalFileName"],
            metadata=metadata,
            text=text_preview["text"],
            pages=text_preview.get("pages") or [],
            detected_industry=row["detectedIndustry"],
        )
        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET detectedContentType = ?,
                detectedContentTypes = ?,
                contentTypeConfidence = ?,
                contentTypeScoreBreakdown = ?,
                contentTypeReason = ?,
                contentTypePagesSummary = ?,
                pageContentResults = ?,
                contentTypeSignals = ?,
                isMixedContent = ?,
                contentTypeDetectedBySystem = ?,
                contentTypeClassifiedAt = ?,
                updatedAt = ?,
                errorMessage = NULL
            WHERE id = ?
            """,
            (
                result["detectedContentType"],
                json.dumps(result["detectedContentTypes"], ensure_ascii=False),
                result["contentTypeConfidence"],
                json.dumps(result["contentTypeScoreBreakdown"], ensure_ascii=False),
                result["contentTypeReason"],
                json.dumps(result["contentTypePagesSummary"], ensure_ascii=False),
                json.dumps(result["pageContentResults"], ensure_ascii=False),
                json.dumps(result["contentTypeSignals"], ensure_ascii=False),
                1 if result["isMixedContent"] else 0,
                result["contentTypeDetectedBySystem"],
                now,
                now,
                document_id,
            ),
        )
        updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(updated)

    def extract_project_identity(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        text_preview = self.extract_pdf_text_preview(row["storageKey"], max_pages=30)
        pages = text_preview.get("pages") or []
        title_candidate, title_candidates, rejected_titles = extract_project_title(pages)
        address_candidate, address_candidates, rejected_office = extract_investment_address(pages)
        plot_candidate, plot_candidates, rejected_plots = extract_plot_number(pages)
        land_registry_candidate = extract_land_registry_unit(pages)

        document_identity_candidates = []
        for idx in range(0, max(len(title_candidates), len(address_candidates), len(plot_candidates), 1)):
            t = title_candidates[idx] if idx < len(title_candidates) else title_candidate
            a = address_candidates[idx] if idx < len(address_candidates) else address_candidate
            p = plot_candidates[idx] if idx < len(plot_candidates) else plot_candidate
            if not any([t, a, p]):
                continue
            score_parts = [c.confidence for c in [t, a, p] if c]
            support = len({(c.source.split(":")[1] if c and c.source else "") for c in [t, a, p] if c})
            candidate_score = round((sum(score_parts) / len(score_parts)) + (0.03 * max(0, support - 1)), 4) if score_parts else 0.0
            document_identity_candidates.append(
                {
                    "score": min(0.99, candidate_score),
                    "projectTitleDetected": t.value if t else None,
                    "investmentAddressDetected": a.value if a else None,
                    "plotNumberDetected": p.value if p else None,
                    "sources": [c.source for c in [t, a, p] if c],
                    "composedFromMultipleSources": support > 1,
                }
            )
        document_identity_candidates = sorted(document_identity_candidates, key=lambda x: x["score"], reverse=True)[:10]

        signals = explain_signals(
            title_candidate,
            address_candidate,
            plot_candidate,
            rejected_office,
            title_candidates=title_candidates,
            address_candidates=address_candidates,
            plot_candidates=plot_candidates,
            rejected_titles=rejected_titles,
            rejected_addresses=rejected_office,
            rejected_plots=rejected_plots,
        )
        signals["documentProjectIdentityCandidates"] = document_identity_candidates
        signals["projectTitleDetected"] = title_candidate.value if title_candidate else None
        signals["projectTitleNormalized"] = title_candidate.normalized if title_candidate else None
        signals["projectTitleConfidence"] = title_candidate.confidence if title_candidate else None
        signals["projectTitleSource"] = title_candidate.source if title_candidate else None
        signals["projectTitleReason"] = ", ".join(title_candidate.signals) if title_candidate else ""
        signals["plotNumberDetected"] = plot_candidate.value if plot_candidate else None
        signals["plotNumbersDetected"] = (plot_candidate.value.split(", ") if plot_candidate and plot_candidate.value else [])
        signals["plotNumberNormalized"] = plot_candidate.normalized if plot_candidate else None
        signals["plotNumbersNormalized"] = (plot_candidate.normalized.split(", ") if plot_candidate and plot_candidate.normalized else [])
        signals["plotNumberConfidence"] = plot_candidate.confidence if plot_candidate else None
        signals["plotNumberSource"] = plot_candidate.source if plot_candidate else None
        signals["plotNumberReason"] = ", ".join(plot_candidate.signals) if plot_candidate else ""

        component_confidence = {"title": 0.0, "address": 0.0, "plot": 0.0}
        if title_candidate:
            component_confidence["title"] = title_candidate.confidence
        if address_candidate:
            component_confidence["address"] = address_candidate.confidence
        if plot_candidate:
            component_confidence["plot"] = plot_candidate.confidence
        completeness_bonus = 0.08 if sum(1 for v in component_confidence.values() if v > 0) >= 2 else 0.0
        best_component = max(component_confidence.values()) if any(component_confidence.values()) else 0.0
        avg_component = sum(v for v in component_confidence.values() if v > 0) / max(1, sum(1 for v in component_confidence.values() if v > 0))
        project_identity_confidence = round(min(0.99, (avg_component * 0.75) + (best_component * 0.25) + completeness_bonus), 4) if best_component else 0.0
        assignment_status = "review_required" if project_identity_confidence < 0.35 else "matching_pending"

        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET projectTitleDetected = ?,
                projectTitleNormalized = ?,
                projectTitleConfidence = ?,
                projectTitleSource = ?,
                investmentAddressDetected = ?,
                investmentAddressNormalized = ?,
                investmentAddressConfidence = ?,
                investmentAddressSource = ?,
                plotNumberDetected = ?,
                plotNumberNormalized = ?,
                landRegistryUnitDetected = ?,
                projectIdentityConfidence = ?,
                projectIdentitySignals = ?,
                projectAssignmentStatus = ?,
                updatedAt = ?
            WHERE id = ?
            """,
            (
                title_candidate.value if title_candidate else None,
                title_candidate.normalized if title_candidate else None,
                title_candidate.confidence if title_candidate else None,
                title_candidate.source if title_candidate else None,
                address_candidate.value if address_candidate else None,
                address_candidate.normalized if address_candidate else None,
                address_candidate.confidence if address_candidate else None,
                address_candidate.source if address_candidate else None,
                plot_candidate.value if plot_candidate else None,
                plot_candidate.normalized if plot_candidate else None,
                land_registry_candidate.value if land_registry_candidate else None,
                project_identity_confidence,
                to_json(signals),
                assignment_status,
                now,
                document_id,
            ),
        )
        updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(updated)

    def match_document_by_title_and_address(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        identity = {
            "projectTitleNormalized": row["projectTitleNormalized"] or "",
            "investmentAddressNormalized": row["investmentAddressNormalized"] or "",
            "plotNumberNormalized": row["plotNumberNormalized"] or "",
        }
        if not any(identity.values()):
            db.execute(
                "UPDATE at_documents SET projectAssignmentStatus = ?, projectMatchReason = ?, updatedAt = ? WHERE id = ?",
                ("review_required", "missing_identity_fields", create_timestamp(), document_id),
            )
            updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
            return self._document_row_to_dict(updated)

        projects = db.execute("SELECT * FROM at_projects ORDER BY updatedAt DESC").fetchall()
        best = None
        for project in projects:
            score, reason = build_match_score(project, identity)
            if not best or score > best["score"]:
                best = {"project": project, "score": score, "reason": reason}

        if best and best["score"] >= 0.78:
            return self.assign_document_to_project(db, document_id, best["project"]["id"], best["score"], best["reason"], "project_matched")
        if best and best["score"] >= 0.5:
            db.execute(
                """
                UPDATE at_documents
                SET projectMatchScore = ?, projectMatchReason = ?, projectAssignmentStatus = ?, updatedAt = ?
                WHERE id = ?
                """,
                (best["score"], best["reason"], "review_required", create_timestamp(), document_id),
            )
            updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
            return self._document_row_to_dict(updated)

        return self._create_project_for_document(db, row)

    def _create_project_for_document(self, db, row):
        now = create_timestamp()
        cursor = db.execute(
            """
            INSERT INTO at_projects (
                projectTitle, projectTitleNormalized, investmentAddress, investmentAddressNormalized,
                plotNumber, plotNumberNormalized, landRegistryUnit, projectIdentityConfidence, projectIdentitySignals,
                assignmentStatus, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["projectTitleDetected"],
                row["projectTitleNormalized"],
                row["investmentAddressDetected"],
                row["investmentAddressNormalized"],
                row["plotNumberDetected"],
                row["plotNumberNormalized"],
                row["landRegistryUnitDetected"],
                row["projectIdentityConfidence"],
                row["projectIdentitySignals"] or to_json({}),
                "project_created",
                now,
                now,
            ),
        )
        return self.assign_document_to_project(db, row["id"], cursor.lastrowid, 0.0, "no_match_new_project_created", "project_created")

    def assign_document_to_project(self, db, document_id, project_id, score=None, reason=None, status="project_matched"):
        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET assignedAtProjectId = ?, projectMatchScore = ?, projectMatchReason = ?, projectAssignmentStatus = ?, updatedAt = ?
            WHERE id = ?
            """,
            (project_id, score, reason, status, now, document_id),
        )
        db.execute("UPDATE at_projects SET updatedAt = ? WHERE id = ?", (now, project_id))
        updated = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(updated)

    def retry_project_matching(self, db, document_id):
        extracted = self.extract_project_identity(db, document_id)
        return self.match_document_by_title_and_address(db, extracted["id"])

    def override_project_identity(self, db, document_id, payload):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        override_json = {
            "projectTitle": (payload.get("projectTitle") or "").strip(),
            "investmentAddress": (payload.get("investmentAddress") or "").strip(),
            "plotNumber": (payload.get("plotNumber") or "").strip(),
            "landRegistryUnit": (payload.get("landRegistryUnit") or "").strip(),
            "decision": payload.get("decision") or "manual_override",
            "reason": payload.get("reason") or "",
            "updatedAt": create_timestamp(),
        }
        db.execute(
            """
            UPDATE at_documents
            SET projectIdentityOverrideJson = ?, projectAssignmentStatus = ?, updatedAt = ?
            WHERE id = ?
            """,
            (to_json(override_json), "manually_reviewed", create_timestamp(), document_id),
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
            classified = self.classify_document_content_types(db, document_id)
            self.extract_lines_for_document(db, document_id)
            db.execute(
                "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
                ("RUNNING", "extracting_project_title", create_timestamp(), job_id),
            )
            classified = self.extract_project_identity(db, document_id)
            db.execute(
                "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
                ("RUNNING", "matching_project", create_timestamp(), job_id),
            )
            classified = self.match_document_by_title_and_address(db, document_id)
            db.execute(
                "UPDATE at_processing_jobs SET status = ?, stage = ?, updatedAt = ? WHERE id = ?",
                ("COMPLETED", classified.get("projectAssignmentStatus") or "project_matched", create_timestamp(), job_id),
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

    def retry_content_type_classification(self, db, document_id):
        return self.classify_document_content_types(db, document_id)

    def _serialize_line_extraction_row(self, row):
        if not row:
            return None
        lines = self._parse_json_column(row["linesJson"], [])
        factor = row["pdfUnitToRealFactor"]
        if factor:
            for line in lines:
                length = float(line.get("length") or 0.0)
                line["realLength"] = round(length * float(factor), 3)
                line["realUnit"] = row["realWorldUnit"] or "mm"
        return {
            "id": row["id"],
            "documentId": row["documentId"],
            "pageNumber": row["pageNumber"],
            "contentType": row["contentType"],
            "extractionSource": row["extractionSource"],
            "pageWidth": row["pageWidth"],
            "pageHeight": row["pageHeight"],
            "lineCount": row["lineCount"] or 0,
            "lines": lines,
            "extractionConfidence": row["extractionConfidence"],
            "extractionStatus": row["extractionStatus"],
            "errorMessage": row["errorMessage"],
            "diagnostics": self._parse_json_column(row["diagnosticsJson"], {}),
            "detectedScaleText": row["detectedScaleText"],
            "detectedScaleNormalized": row["detectedScaleNormalized"],
            "scaleSource": row["scaleSource"],
            "scaleConfidence": row["scaleConfidence"],
            "scaleReason": row["scaleReason"],
            "scaleCandidates": self._parse_json_column(row["scaleCandidatesJson"], []),
            "dimensionCandidates": self._parse_json_column(row["dimensionCandidatesJson"], []),
            "realWorldUnit": row["realWorldUnit"] or "mm",
            "pdfUnitToRealFactor": row["pdfUnitToRealFactor"],
            "viewportUnitToRealFactor": row["viewportUnitToRealFactor"],
            "scaleOverride": self._parse_json_column(row["scaleOverrideJson"], None),
            "scaleOverrideReason": row["scaleOverrideReason"],
            "scaleResolvedAt": row["scaleResolvedAt"],
            "scaleConsistencyCheck": row["scaleConsistencyCheck"],
            "scaleConflictDetected": bool(row["scaleConflictDetected"]),
            "scaleConflictReason": row["scaleConflictReason"],
            "scaleDetectedBySystem": self._parse_json_column(row["scaleDetectedBySystemJson"], None),
            "scaleConfirmedByUser": row["scaleConfirmedByUser"],
            "createdAt": row["createdAt"],
            "updatedAt": row["updatedAt"],
        }

    def _resolve_page_content_type(self, page):
        if page.get("isUserOverridden") and page.get("contentTypeOverride"):
            return page.get("contentTypeOverride")
        return page.get("detectedContentType") or "Inna / Nieznana"

    def _upsert_line_extraction(self, db, document_id, page_number, content_type, payload):
        now = create_timestamp()
        scale = payload.get("scale") or {}
        db.execute(
            """
            INSERT INTO at_page_line_extractions (
                documentId, pageNumber, contentType, extractionSource, pageWidth, pageHeight, lineCount, linesJson,
                extractionConfidence, extractionStatus, errorMessage, diagnosticsJson,
                detectedScaleText, detectedScaleNormalized, scaleSource, scaleConfidence, scaleReason, scaleCandidatesJson,
                dimensionCandidatesJson, realWorldUnit, pdfUnitToRealFactor, viewportUnitToRealFactor, scaleOverrideJson,
                scaleOverrideReason, scaleResolvedAt, scaleConsistencyCheck, scaleConflictDetected, scaleConflictReason,
                scaleDetectedBySystemJson, scaleConfirmedByUser, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(documentId, pageNumber) DO UPDATE SET
                contentType = excluded.contentType,
                extractionSource = excluded.extractionSource,
                pageWidth = excluded.pageWidth,
                pageHeight = excluded.pageHeight,
                lineCount = excluded.lineCount,
                linesJson = excluded.linesJson,
                extractionConfidence = excluded.extractionConfidence,
                extractionStatus = excluded.extractionStatus,
                errorMessage = excluded.errorMessage,
                diagnosticsJson = excluded.diagnosticsJson,
                detectedScaleText = excluded.detectedScaleText,
                detectedScaleNormalized = excluded.detectedScaleNormalized,
                scaleSource = excluded.scaleSource,
                scaleConfidence = excluded.scaleConfidence,
                scaleReason = excluded.scaleReason,
                scaleCandidatesJson = excluded.scaleCandidatesJson,
                dimensionCandidatesJson = excluded.dimensionCandidatesJson,
                realWorldUnit = excluded.realWorldUnit,
                pdfUnitToRealFactor = excluded.pdfUnitToRealFactor,
                viewportUnitToRealFactor = excluded.viewportUnitToRealFactor,
                scaleOverrideJson = excluded.scaleOverrideJson,
                scaleOverrideReason = excluded.scaleOverrideReason,
                scaleResolvedAt = excluded.scaleResolvedAt,
                scaleConsistencyCheck = excluded.scaleConsistencyCheck,
                scaleConflictDetected = excluded.scaleConflictDetected,
                scaleConflictReason = excluded.scaleConflictReason,
                scaleDetectedBySystemJson = excluded.scaleDetectedBySystemJson,
                scaleConfirmedByUser = excluded.scaleConfirmedByUser,
                updatedAt = excluded.updatedAt
            """,
            (
                document_id,
                page_number,
                content_type,
                payload.get("extractionSource"),
                payload.get("pageWidth"),
                payload.get("pageHeight"),
                payload.get("lineCount") or 0,
                json.dumps(payload.get("lines") or [], ensure_ascii=False),
                payload.get("extractionConfidence"),
                payload.get("extractionStatus") or "PENDING",
                payload.get("errorMessage"),
                json.dumps(payload.get("diagnostics") or {}, ensure_ascii=False),
                scale.get("detectedScaleText"),
                scale.get("detectedScaleNormalized"),
                scale.get("scaleSource"),
                scale.get("scaleConfidence"),
                scale.get("scaleReason"),
                json.dumps(scale.get("scaleCandidates") or [], ensure_ascii=False),
                json.dumps(scale.get("dimensionCandidates") or [], ensure_ascii=False),
                scale.get("realWorldUnit") or "mm",
                scale.get("pdfUnitToRealFactor"),
                scale.get("viewportUnitToRealFactor"),
                json.dumps(scale.get("scaleOverride"), ensure_ascii=False) if scale.get("scaleOverride") else None,
                scale.get("scaleOverrideReason"),
                scale.get("scaleResolvedAt"),
                scale.get("scaleConsistencyCheck"),
                1 if scale.get("scaleConflictDetected") else 0,
                scale.get("scaleConflictReason"),
                json.dumps(scale.get("scaleDetectedBySystem"), ensure_ascii=False) if scale.get("scaleDetectedBySystem") else None,
                scale.get("scaleConfirmedByUser"),
                now,
                now,
            ),
        )

    def _extract_page_text(self, storage_key, page_number):
        try:
            reader = PdfReader(storage_key, strict=False)
            if page_number < 1 or page_number > len(reader.pages):
                return ""
            return (reader.pages[page_number - 1].extract_text() or "")[:30000]
        except Exception:  # noqa: BLE001
            return ""

    def _load_scale_override(self, db, document_id, page_number):
        row = db.execute(
            "SELECT scaleOverrideJson FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
            (document_id, page_number),
        ).fetchone()
        return self._parse_json_column(row["scaleOverrideJson"], None) if row else None

    def _compute_scale_payload(self, db, document_row, page_number, lines, page_width):
        page_text = self._extract_page_text(document_row["storageKey"], page_number)
        text_candidates = self.scale_detection_service.detect_scale_from_text(page_text)
        dimension_candidates = self.scale_detection_service.extract_dimension_candidates(page_text)
        inferred = self.scale_detection_service.infer_scale_from_dimensions(dimension_candidates, lines)
        override = self._load_scale_override(db, document_row["id"], page_number)
        resolved = self.scale_detection_service.resolve_scale(text_candidates, inferred, override=override)
        factor = resolved.get("pdfUnitToRealFactor")
        viewport_factor = (factor / float(page_width)) if factor and page_width else None
        return {
            **resolved,
            "scaleCandidates": text_candidates,
            "dimensionCandidates": dimension_candidates,
            "realWorldUnit": "mm",
            "viewportUnitToRealFactor": round(viewport_factor, 9) if viewport_factor else None,
            "scaleResolvedAt": create_timestamp(),
            "scaleOverride": override,
            "scaleOverrideReason": (override or {}).get("reason") if isinstance(override, dict) else None,
        }

    def extract_lines_for_document(self, db, document_id):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        page_results = self._parse_json_column(row["pageContentResults"], [])
        if not page_results:
            raise ATModuleError("Brak klasyfikacji stron. Uruchom klasyfikację typu zawartości.", code="CONTENT_TYPE_REQUIRED")

        extracted_pages = []
        skipped_pages = []
        for page in page_results:
            page_number = int(page.get("pageNumber") or 0)
            if page_number <= 0:
                continue
            resolved_type = self._resolve_page_content_type(page)
            if resolved_type != "Rzut":
                skipped_pages.append({"pageNumber": page_number, "contentType": resolved_type, "reason": "not_target_content_type"})
                continue
            try:
                result = self.line_extraction_service.extract_page_lines(row["storageKey"], page_number)
                scale_payload = self._compute_scale_payload(db, row, page_number, result["lines"], result["pageWidth"])
                payload = {
                    "extractionSource": result["extractionSource"],
                    "pageWidth": result["pageWidth"],
                    "pageHeight": result["pageHeight"],
                    "lineCount": result["lineCount"],
                    "lines": result["lines"],
                    "extractionConfidence": result["extractionConfidence"],
                    "extractionStatus": result["status"],
                    "errorMessage": None,
                    "diagnostics": {
                        "fallbackUsed": result["fallbackUsed"],
                        "rasterFallbackUsed": result.get("rasterFallbackUsed"),
                        "fallbackReason": result["fallbackReason"],
                        "nativeVectorAvailable": result.get("nativeVectorAvailable"),
                        "nativeVectorUsed": result.get("nativeVectorUsed"),
                        "isNativeVector": result.get("isNativeVector"),
                        "vectorObjectCount": result.get("vectorObjectCount"),
                        "vectorExtractionReason": result.get("vectorExtractionReason"),
                        "vectorExtractionConfidence": result.get("vectorExtractionConfidence"),
                        "pageCoordinateSystem": (result.get("meta") or {}).get("pageCoordinateSystem"),
                        "viewportTransform": (result.get("meta") or {}).get("viewportTransform"),
                        "rejected": result["rejected"],
                        "bbox": result["bbox"],
                        "meta": result["meta"],
                        "filters": {
                            "minLength": self.line_extraction_service.config.min_length,
                            "dedupeEps": self.line_extraction_service.config.dedupe_eps,
                        },
                    },
                    "scale": scale_payload,
                }
                self._upsert_line_extraction(db, document_id, page_number, resolved_type, payload)
                extracted_pages.append({"pageNumber": page_number, "lineCount": result["lineCount"], "source": result["extractionSource"]})
            except Exception as exc:  # noqa: BLE001
                self._upsert_line_extraction(
                    db,
                    document_id,
                    page_number,
                    resolved_type,
                    {
                        "extractionSource": None,
                        "pageWidth": None,
                        "pageHeight": None,
                        "lineCount": 0,
                        "lines": [],
                        "extractionConfidence": 0.0,
                        "extractionStatus": "FAILED",
                        "errorMessage": str(exc),
                        "diagnostics": {"fallbackUsed": False, "errorStage": "extract_page_lines"},
                    },
                )
                extracted_pages.append({"pageNumber": page_number, "lineCount": 0, "source": None, "status": "FAILED"})

        rows = db.execute(
            "SELECT * FROM at_page_line_extractions WHERE documentId = ? ORDER BY pageNumber ASC",
            (document_id,),
        ).fetchall()
        return {
            "documentId": document_id,
            "extractedPages": extracted_pages,
            "skippedPages": skipped_pages,
            "pages": [self._serialize_line_extraction_row(item) for item in rows],
        }

    def extract_lines_for_page(self, db, document_id, page_number):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")
        page_results = self._parse_json_column(row["pageContentResults"], [])
        target = next((page for page in page_results if int(page.get("pageNumber") or 0) == int(page_number)), None)
        if not target:
            raise ATModuleError("Nie znaleziono wskazanej strony.", status_code=404, code="PAGE_NOT_FOUND")
        resolved_type = self._resolve_page_content_type(target)
        if resolved_type != "Rzut":
            raise ATModuleError("Ekstrakcja linii jest dostępna tylko dla stron typu Rzut.", status_code=409, code="PAGE_NOT_PLAN")
        self.extract_lines_for_document(db, document_id)
        row = db.execute(
            "SELECT * FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
            (document_id, page_number),
        ).fetchone()
        return self._serialize_line_extraction_row(row)

    def get_page_line_extraction(self, db, document_id, page_number):
        row = db.execute(
            "SELECT * FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
            (document_id, page_number),
        ).fetchone()
        if not row:
            raise ATModuleError("Brak wyniku ekstrakcji linii dla tej strony.", status_code=404, code="LINES_NOT_FOUND")
        return self._serialize_line_extraction_row(row)

    def detect_scale_for_page(self, db, document_id, page_number, force_retry=False):
        document = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not document:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")
        page = db.execute(
            "SELECT * FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
            (document_id, page_number),
        ).fetchone()
        if not page:
            self.extract_lines_for_page(db, document_id, page_number)
            page = db.execute(
                "SELECT * FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
                (document_id, page_number),
            ).fetchone()
        if not page:
            raise ATModuleError("Brak danych strony do wykrycia skali.", status_code=404, code="PAGE_NOT_FOUND")

        current = self._serialize_line_extraction_row(page)
        if current.get("scaleResolvedAt") and not force_retry:
            return current
        scale_payload = self._compute_scale_payload(db, document, page_number, current.get("lines") or [], current.get("pageWidth"))
        self._upsert_line_extraction(
            db,
            document_id,
            page_number,
            current.get("contentType") or "Rzut",
            {
                "extractionSource": current.get("extractionSource"),
                "pageWidth": current.get("pageWidth"),
                "pageHeight": current.get("pageHeight"),
                "lineCount": current.get("lineCount"),
                "lines": current.get("lines"),
                "extractionConfidence": current.get("extractionConfidence"),
                "extractionStatus": current.get("extractionStatus"),
                "errorMessage": current.get("errorMessage"),
                "diagnostics": current.get("diagnostics"),
                "scale": scale_payload,
            },
        )
        updated = db.execute(
            "SELECT * FROM at_page_line_extractions WHERE documentId = ? AND pageNumber = ?",
            (document_id, page_number),
        ).fetchone()
        return self._serialize_line_extraction_row(updated)

    def override_scale_for_page(self, db, document_id, page_number, payload):
        ratio = int(payload.get("ratio") or 0)
        if ratio <= 0:
            raise ATModuleError("ratio musi być dodatnią liczbą całkowitą.", status_code=400, code="INVALID_SCALE_OVERRIDE")
        factor = payload.get("pdfUnitToRealFactor")
        factor_value = float(factor) if factor is not None else float(ratio) * 10.0
        override = {
            "ratio": ratio,
            "pdfUnitToRealFactor": factor_value,
            "reason": payload.get("reason") or "manual_override",
            "source": payload.get("source") or "user_input",
            "updatedAt": create_timestamp(),
        }
        db.execute(
            """
            UPDATE at_page_line_extractions
            SET scaleOverrideJson = ?, scaleOverrideReason = ?, updatedAt = ?
            WHERE documentId = ? AND pageNumber = ?
            """,
            (json.dumps(override, ensure_ascii=False), override["reason"], create_timestamp(), document_id, page_number),
        )
        return self.detect_scale_for_page(db, document_id, page_number, force_retry=True)

    def get_geometry_with_real_units(self, db, document_id, page_number):
        page = self.get_page_line_extraction(db, document_id, page_number)
        return {
            "documentId": document_id,
            "pageNumber": page_number,
            "scale": {
                "detectedScaleNormalized": page.get("detectedScaleNormalized"),
                "scaleSource": page.get("scaleSource"),
                "scaleConfidence": page.get("scaleConfidence"),
                "pdfUnitToRealFactor": page.get("pdfUnitToRealFactor"),
                "realWorldUnit": page.get("realWorldUnit"),
            },
            "geometry": page.get("lines") or [],
        }


    def override_page_content_type(self, db, document_id, page_number, override_type, reason=None):
        row = db.execute("SELECT * FROM at_documents WHERE id = ? AND isDeleted = 0", (document_id,)).fetchone()
        if not row:
            raise ATModuleError("Dokument AT nie istnieje.", status_code=404, code="DOCUMENT_NOT_FOUND")

        allowed = set(CONTENT_TYPES)
        if override_type not in allowed:
            raise ATModuleError("Nieprawidłowy typ strony do nadpisania.", status_code=400, code="INVALID_CONTENT_TYPE")

        pages = self._parse_json_column(row["pageContentResults"], [])
        updated = False
        for entry in pages:
            if int(entry.get("pageNumber") or 0) != int(page_number):
                continue
            entry["contentTypeOverride"] = override_type
            entry["contentTypeConfirmedByUser"] = override_type
            entry["contentTypeOverrideReason"] = reason or ""
            entry["isUserOverridden"] = True
            entry["detectedContentType"] = override_type
            updated = True
            break

        if not updated:
            raise ATModuleError("Nie znaleziono wskazanej strony.", status_code=404, code="PAGE_NOT_FOUND")

        counts = Counter((entry.get("detectedContentType") or "Inna / Nieznana") for entry in pages)
        known = {k: v for k, v in counts.items() if k != "Inna / Nieznana"}
        dominant = "Inna / Nieznana"
        if known:
            dominant = sorted(known.items(), key=lambda item: item[1], reverse=True)[0][0]

        now = create_timestamp()
        db.execute(
            """
            UPDATE at_documents
            SET pageContentResults = ?,
                contentTypePagesSummary = ?,
                detectedContentType = ?,
                contentTypeConfirmedByUser = ?,
                contentTypeOverride = ?,
                contentTypeOverrideReason = ?,
                updatedAt = ?
            WHERE id = ?
            """,
            (
                json.dumps(pages, ensure_ascii=False),
                json.dumps(dict(counts), ensure_ascii=False),
                dominant,
                dominant,
                override_type,
                reason or "",
                now,
                document_id,
            ),
        )
        updated_row = db.execute("SELECT * FROM at_documents WHERE id = ?", (document_id,)).fetchone()
        return self._document_row_to_dict(updated_row)

    def list_documents(self, db):
        rows = db.execute(
            "SELECT * FROM at_documents WHERE isDeleted = 0 ORDER BY createdAt DESC"
        ).fetchall()
        return [self._document_row_to_dict(row) for row in rows]
