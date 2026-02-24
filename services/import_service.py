import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from werkzeug.utils import secure_filename

from shapely.geometry import mapping as shapely_mapping

from services.cad_pipeline import (
    detect_units_from_doc,
    extract_parcel_boundaries,
    normalize_boundary_candidates,
    normalize_entities,
    parse_file,
    select_main_boundary,
    summarize_layers,
)
from services.dwg_converter import DwgConverterError, create_dwg_converter
from services.dxf_parser import list_layers
from utils.db import create_timestamp, get_db


ALLOWED_EXTENSIONS = {".dxf", ".dwg"}
ALLOWED_MIME = {
    "application/dxf",
    "image/vnd.dwg",
    "application/acad",
    "application/x-autocad",
    "application/octet-stream",
}

logger = logging.getLogger("plot-import")


def _validate_upload(file_storage, max_size_mb: int):
    filename = secure_filename(file_storage.filename or "")
    if not filename:
        raise ValueError("Nieprawidłowa nazwa pliku.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Nieobsługiwany format. Wgraj DXF lub DWG.")

    if file_storage.mimetype and file_storage.mimetype not in ALLOWED_MIME:
        raise ValueError("Nieobsługiwany MIME pliku CAD.")

    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        raise ValueError("Plik jest pusty.")
    if size > max_size_mb * 1024 * 1024:
        raise ValueError(f"Plik jest za duży. Maksymalny rozmiar to {max_size_mb} MB.")

    return filename, ext, size


def _layer_signature(layers: list[str]) -> str:
    normalized = sorted({layer.lower() for layer in layers if layer})
    return "|".join(normalized)


def _merge_bounds(bounds_list):
    filtered = [bounds for bounds in bounds_list if bounds]
    if not filtered:
        return None
    min_x = min(bounds[0] for bounds in filtered)
    min_y = min(bounds[1] for bounds in filtered)
    max_x = max(bounds[2] for bounds in filtered)
    max_y = max(bounds[3] for bounds in filtered)
    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


def _get_import_rule(db, signature: str):
    row = db.execute(
        "SELECT * FROM plot_import_rules WHERE layerSignature = ?",
        (signature,),
    ).fetchone()
    if not row:
        return None
    return row["preferredLayer"]


def _save_import_rule(db, signature: str, preferred_layer: str):
    db.execute(
        """
        INSERT INTO plot_import_rules (layerSignature, preferredLayer, createdAt)
        VALUES (?, ?, ?)
        ON CONFLICT(layerSignature)
        DO UPDATE SET preferredLayer = excluded.preferredLayer
        """,
        (signature, preferred_layer, create_timestamp()),
    )


def handle_plot_upload(app_config: dict, file_storage) -> dict[str, Any]:
    filename, ext, size = _validate_upload(file_storage, app_config["PLOT_MAX_SIZE_MB"])
    storage_dir = Path(app_config["PLOT_UPLOAD_FOLDER"])
    storage_dir.mkdir(parents=True, exist_ok=True)
    timestamp = int(time.time())
    stored_name = f"{Path(filename).stem}_{timestamp}{ext}"
    stored_path = storage_dir / stored_name
    db = get_db(app_config["DB_PATH"])
    existing = db.execute(
        "SELECT id FROM plot_import_jobs WHERE filename = ?",
        (filename,),
    ).fetchone()
    if existing:
        raise ValueError("Ten plik już istnieje w aplikacji.")
    file_storage.save(stored_path)
    cursor = db.execute(
        """
        INSERT INTO plot_import_jobs (userId, filename, status, error, sourcePath, createdAt)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (None, filename, "PROCESSING", None, str(stored_path), create_timestamp()),
    )
    import_job_id = cursor.lastrowid
    db.commit()

    try:
        if ext == ".dwg":
            logger.debug("Starting DWG conversion for %s", stored_path)
            converter = create_dwg_converter(
                app_config.get("ODA_FILE_CONVERTER"),
                app_config.get("DWG2DXF_PATH"),
            )
            try:
                dxf_path = converter.convert(str(stored_path), str(storage_dir))
            except DwgConverterError as exc:
                message = str(exc)
                if "Brak skonfigurowanego konwertera" in message:
                    raise ValueError(
                        "DWG wymaga konwersji do DXF. Skonfiguruj konwerter lub prześlij DXF."
                    ) from exc
                raise
            logger.debug("DWG converted to %s", dxf_path)
        else:
            dxf_path = str(stored_path)

        logger.debug("Parsing CAD file %s", dxf_path)
        parsed = parse_file(dxf_path)
        logger.debug("Parsed CAD file: entities=%s layers=%s", len(parsed.raw_entities), len(parsed.layer_summary))
        layers = list_layers(parsed.doc)
        signature = _layer_signature(layers)
        preferred_layer = _get_import_rule(db, signature)

        extraction = extract_parcel_boundaries(parsed.doc, preferred_layer=preferred_layer)
        if not extraction.candidates:
            raise ValueError("Nie znaleziono granic działek w pliku.")

        units_payload = detect_units_from_doc(parsed.doc, extraction.bounds or parsed.bounds)
        unit_name = units_payload["unitName"]
        unit_scale = units_payload["unitScaleToMeters"]
        units_source = units_payload["unitsSource"]

        logger.debug("Detected units=%s scale=%s source=%s", unit_name, unit_scale, units_source)
        normalized_entities = normalize_entities(parsed.raw_entities, unit_scale, parsed.bounds)
        normalized_boundaries = normalize_boundary_candidates(extraction.candidates, unit_scale, parsed.bounds)
        transform = normalized_entities.get("transform")
        normalized_bounds = _merge_bounds([candidate["bbox"] for candidate in normalized_boundaries])
        main_boundary = select_main_boundary(extraction.candidates)

        selected_id = None
        status = "NEEDS_REVIEW"
        if extraction.confidence >= 0.8 and normalized_boundaries:
            selected_id = normalized_boundaries[0]["uid"]
            status = "COMPLETED"
        if main_boundary:
            selected_id = main_boundary.uid

        for candidate in normalized_boundaries:
            metadata = {
                "layer": candidate["layer"],
                "area": candidate["area"],
                "bbox": {
                    "minX": candidate["bbox"][0],
                    "minY": candidate["bbox"][1],
                    "maxX": candidate["bbox"][2],
                    "maxY": candidate["bbox"][3],
                },
                "vertexCount": candidate["vertexCount"],
                "score": candidate["score"],
                "source": candidate["source"],
            }
            db.execute(
                """
                INSERT INTO plot_boundaries (importJobId, geometryJson, transformJson, metadataJson, confidence, isSelected, createdAt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    import_job_id,
                    json.dumps(shapely_mapping(candidate["geometry"])),
                    json.dumps(transform),
                    json.dumps(metadata),
                    extraction.confidence,
                    1 if candidate["uid"] == selected_id else 0,
                    create_timestamp(),
                ),
            )

        db.execute(
            """
            UPDATE plot_import_jobs
            SET status = ?,
                error = ?,
                units = ?,
                unitScale = ?,
                unitsSource = ?,
                transformJson = ?,
                bboxJson = ?,
                confidence = ?,
                layerSignature = ?
            WHERE id = ?
            """,
            (
                status,
                None,
                unit_name,
                unit_scale,
                units_source,
                json.dumps(transform),
                json.dumps(
                    {
                        "minX": normalized_bounds["minX"],
                        "minY": normalized_bounds["minY"],
                        "maxX": normalized_bounds["maxX"],
                        "maxY": normalized_bounds["maxY"],
                    }
                    if normalized_bounds
                    else None
                ),
                extraction.confidence,
                signature,
                import_job_id,
            ),
        )
        layer_summary = summarize_layers(parsed.layer_summary)
        cad_payload = {
            "unitsDetected": unit_name + (" (heurystyka)" if units_payload["heuristic"] else ""),
            "unitScaleToMeters": unit_scale,
            "bbox": normalized_entities.get("bbox"),
            "layers": normalized_entities.get("layers", []),
            "layerCount": len(normalized_entities.get("layers", [])),
            "entityCount": normalized_entities.get("entityCount", 0),
            "parcelBoundaryCount": len(normalized_boundaries),
            "parcelSourceLayers": list({candidate.layer for candidate in extraction.candidates}),
            "parcelDetection": {
                "status": "ok" if extraction.candidates else "empty",
                "selectedLayers": list({candidate.layer for candidate in extraction.candidates}),
                "reasons": [],
            },
        }
        db.execute(
            """
            UPDATE plot_import_jobs
            SET layerSummaryJson = ?,
                cadPayloadJson = ?
            WHERE id = ?
            """,
            (json.dumps(layer_summary), json.dumps(cad_payload), import_job_id),
        )
        db.commit()
    except (ValueError, DwgConverterError) as exc:
        db.execute(
            "UPDATE plot_import_jobs SET status = ?, error = ? WHERE id = ?",
            ("FAILED", str(exc), import_job_id),
        )
        db.commit()
        raise
    except Exception as exc:
        db.execute(
            "UPDATE plot_import_jobs SET status = ?, error = ? WHERE id = ?",
            ("FAILED", "Nie udało się przetworzyć pliku CAD.", import_job_id),
        )
        db.commit()
        raise exc

    bounds_payload = None
    if normalized_bounds:
        bounds_payload = {
            "minX": normalized_bounds["minX"],
            "minY": normalized_bounds["minY"],
            "maxX": normalized_bounds["maxX"],
            "maxY": normalized_bounds["maxY"],
        }

    return {
        "importJobId": import_job_id,
        "status": status,
        "confidence": extraction.confidence,
        "units": unit_name,
        "unitScale": unit_scale,
        "bounds": bounds_payload,
    }


def get_boundaries(db_path: str, import_job_id: int):
    db = get_db(db_path)
    job = db.execute("SELECT * FROM plot_import_jobs WHERE id = ?", (import_job_id,)).fetchone()
    if not job:
        return None

    boundaries = db.execute(
        "SELECT * FROM plot_boundaries WHERE importJobId = ? ORDER BY id",
        (import_job_id,),
    ).fetchall()

    candidates = []
    selected = None
    for row in boundaries:
        candidate = {
            "id": row["id"],
            "geometry": json.loads(row["geometryJson"]),
            "metadata": json.loads(row["metadataJson"]) if row["metadataJson"] else {},
            "confidence": row["confidence"],
            "isSelected": bool(row["isSelected"]),
        }
        candidates.append(candidate)
        if row["isSelected"]:
            selected = candidate

    return {
        "importJob": {
            "id": job["id"],
            "filename": job["filename"],
            "status": job["status"],
            "error": job["error"],
            "isDisabled": bool(job["isDisabled"]),
            "units": job["units"],
            "unitScale": job["unitScale"],
            "confidence": job["confidence"],
            "unitsSource": job["unitsSource"],
        },
        "selectedBoundary": selected,
        "candidates": candidates,
        "transform": json.loads(job["transformJson"]) if job["transformJson"] else None,
        "bbox": json.loads(job["bboxJson"]) if job["bboxJson"] else None,
        "layerSummary": json.loads(job["layerSummaryJson"]) if job["layerSummaryJson"] else [],
        "cadMap": json.loads(job["cadPayloadJson"]) if job["cadPayloadJson"] else None,
    }


def select_boundary(db_path: str, import_job_id: int, candidate_id: int):
    db = get_db(db_path)
    job = db.execute("SELECT * FROM plot_import_jobs WHERE id = ?", (import_job_id,)).fetchone()
    if not job:
        return None

    candidate = db.execute(
        "SELECT * FROM plot_boundaries WHERE id = ? AND importJobId = ?",
        (candidate_id, import_job_id),
    ).fetchone()
    if not candidate:
        raise ValueError("Wybrany kandydat nie istnieje.")

    db.execute("UPDATE plot_boundaries SET isSelected = 0 WHERE importJobId = ?", (import_job_id,))
    db.execute("UPDATE plot_boundaries SET isSelected = 1 WHERE id = ?", (candidate_id,))
    db.execute(
        "UPDATE plot_import_jobs SET status = ? WHERE id = ?",
        ("COMPLETED", import_job_id),
    )

    layer_signature = job["layerSignature"]
    metadata = json.loads(candidate["metadataJson"]) if candidate["metadataJson"] else {}
    if layer_signature and metadata.get("layer"):
        _save_import_rule(db, layer_signature, metadata["layer"])

    db.commit()

    return {
        "id": candidate["id"],
        "geometry": json.loads(candidate["geometryJson"]),
        "metadata": metadata,
        "confidence": candidate["confidence"],
        "isSelected": True,
    }
