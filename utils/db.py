import sqlite3
from datetime import datetime
from pathlib import Path

from flask import g


def _utc_now():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def get_db(db_path):
    if "db" not in g:
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    db_path = Path(app.config["DB_PATH"])
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parcels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcelId TEXT NOT NULL,
                geometry TEXT,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                userId TEXT,
                type TEXT NOT NULL,
                filename TEXT NOT NULL,
                mimeType TEXT NOT NULL,
                size INTEGER NOT NULL,
                storageUrl TEXT NOT NULL,
                status TEXT NOT NULL,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extracted_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uploadId INTEGER NOT NULL,
                parcelId TEXT,
                fieldKey TEXT NOT NULL,
                value TEXT,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                fileUrl TEXT NOT NULL,
                fileName TEXT NOT NULL,
                mimeType TEXT NOT NULL,
                size INTEGER NOT NULL,
                uploadedAt TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                ocrStatus TEXT NOT NULL,
                isDeleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fileName TEXT NOT NULL,
                fileUrl TEXT NOT NULL,
                mimeType TEXT NOT NULL,
                size INTEGER NOT NULL,
                fileKind TEXT NOT NULL,
                uploadedAt TEXT NOT NULL,
                isDeleted INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_extracted_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                documentId INTEGER NOT NULL,
                parcelId TEXT NOT NULL,
                fieldsJson TEXT,
                source TEXT NOT NULL,
                updatedAt TEXT NOT NULL,
                ocrConfidenceJson TEXT,
                UNIQUE(documentId, parcelId)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS extracted_field_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                extractedFieldId INTEGER NOT NULL,
                prevValue TEXT,
                prevStatus TEXT NOT NULL,
                changedAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parcel_plan_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parcelId TEXT NOT NULL UNIQUE,
                rulesJson TEXT NOT NULL,
                provenanceJson TEXT NOT NULL,
                lastUpdatedAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_import_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                userId TEXT,
                filename TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                sourcePath TEXT NOT NULL,
                isDisabled INTEGER NOT NULL DEFAULT 0,
                units TEXT,
                unitScale REAL,
                unitsSource TEXT,
                transformJson TEXT,
                bboxJson TEXT,
                confidence REAL,
                layerSignature TEXT,
                layerSummaryJson TEXT,
                cadPayloadJson TEXT,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_boundaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                importJobId INTEGER NOT NULL,
                geometryJson TEXT NOT NULL,
                transformJson TEXT,
                metadataJson TEXT,
                confidence REAL NOT NULL,
                isSelected INTEGER NOT NULL DEFAULT 0,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_sessions (
                id TEXT PRIMARY KEY,
                plot_geom TEXT NOT NULL,
                buffer_geom TEXT NOT NULL,
                bbox4326 TEXT NOT NULL,
                metadata TEXT NOT NULL,
                createdAt INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS map_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                layer TEXT NOT NULL,
                geom TEXT NOT NULL,
                props TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_map_features_session_layer ON map_features(session_id, layer)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS planning_parcel_imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'geoportal',
                parcelId TEXT NOT NULL,
                parcelNumber TEXT,
                cadastralUnit TEXT,
                precinct TEXT,
                geometryJson TEXT NOT NULL,
                centroidJson TEXT,
                bboxJson TEXT,
                area REAL,
                layersJson TEXT,
                visible INTEGER NOT NULL DEFAULT 1,
                locked INTEGER NOT NULL DEFAULT 1,
                importedAt TEXT NOT NULL,
                UNIQUE(projectId, source, parcelId)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_planning_parcel_imports_project ON planning_parcel_imports(projectId)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_contexts (
                id TEXT PRIMARY KEY,
                projectId INTEGER NOT NULL,
                primaryParcelId TEXT NOT NULL,
                siteBoundaryJson TEXT NOT NULL,
                analysisBufferMeters REAL NOT NULL DEFAULT 30,
                analysisResultJson TEXT,
                importSummaryJson TEXT,
                dataStatus TEXT NOT NULL DEFAULT 'ready',
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_contexts_project ON site_contexts(projectId, createdAt DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_layers (
                id TEXT PRIMARY KEY,
                projectId INTEGER NOT NULL,
                siteContextId TEXT NOT NULL,
                layerKey TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL,
                sourceType TEXT NOT NULL,
                visible INTEGER NOT NULL DEFAULT 1,
                locked INTEGER NOT NULL DEFAULT 1,
                geometryType TEXT,
                featuresJson TEXT NOT NULL,
                metadataJson TEXT,
                styleJson TEXT,
                sortOrder INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(siteContextId) REFERENCES site_contexts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_layers_context ON site_layers(siteContextId, sortOrder)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_objects (
                id TEXT PRIMARY KEY,
                projectId INTEGER NOT NULL,
                siteContextId TEXT NOT NULL,
                layerKey TEXT NOT NULL,
                objectType TEXT NOT NULL,
                geometryJson TEXT NOT NULL,
                bboxJson TEXT,
                centroidJson TEXT,
                sourceType TEXT,
                sourceName TEXT,
                sourceMetadataJson TEXT,
                confidence REAL,
                withinPlot INTEGER,
                withinSiteBoundary INTEGER,
                intersectsPlot INTEGER,
                propertiesJson TEXT,
                FOREIGN KEY(siteContextId) REFERENCES site_contexts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_objects_context ON site_objects(siteContextId, layerKey)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_analysis_results (
                id TEXT PRIMARY KEY,
                projectId INTEGER NOT NULL,
                siteContextId TEXT NOT NULL,
                buildableArea REAL,
                maxBuildingEnvelopeJson TEXT,
                preferredBuildingZoneJson TEXT,
                buildingCandidatesJson TEXT,
                constraintsJson TEXT,
                observationsJson TEXT,
                warningsJson TEXT,
                notesJson TEXT,
                createdAt TEXT NOT NULL,
                FOREIGN KEY(siteContextId) REFERENCES site_contexts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_analysis_results_context ON site_analysis_results(siteContextId, createdAt DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_import_logs (
                id TEXT PRIMARY KEY,
                projectId INTEGER NOT NULL,
                siteContextId TEXT NOT NULL,
                status TEXT NOT NULL,
                objectsPerLayerJson TEXT,
                fetchedLayersJson TEXT,
                emptyLayersJson TEXT,
                unavailableLayersJson TEXT,
                partialErrorsJson TEXT,
                createdAt TEXT NOT NULL,
                FOREIGN KEY(siteContextId) REFERENCES site_contexts(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_site_import_logs_context ON site_import_logs(siteContextId, createdAt DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_import_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                layerSignature TEXT NOT NULL UNIQUE,
                preferredLayer TEXT NOT NULL,
                createdAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'DRAFT',
                investorName TEXT,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fullName TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                passwordHash TEXT NOT NULL,
                createdAt TEXT NOT NULL,
                lastLoginAt TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_plots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                parcelId TEXT,
                externalParcelRef TEXT,
                geometryJson TEXT,
                area REAL,
                ownershipStatus TEXT,
                notes TEXT,
                createdAt TEXT NOT NULL,
                UNIQUE(projectId, externalParcelRef),
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_plot_parameters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectPlotId INTEGER NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                valueType TEXT NOT NULL DEFAULT 'TEXT',
                unit TEXT,
                source TEXT,
                updatedAt TEXT NOT NULL,
                UNIQUE(projectPlotId, key),
                FOREIGN KEY(projectPlotId) REFERENCES project_plots(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                projectPlotId INTEGER,
                kind TEXT NOT NULL,
                fileName TEXT NOT NULL,
                fileUrl TEXT NOT NULL,
                mimeType TEXT NOT NULL,
                size INTEGER NOT NULL,
                uploadedAt TEXT NOT NULL,
                isDeleted INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(projectPlotId) REFERENCES project_plots(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                requirementValue TEXT,
                priority TEXT NOT NULL DEFAULT 'MEDIUM',
                status TEXT NOT NULL DEFAULT 'OPEN',
                source TEXT,
                dueDate TEXT,
                createdAt TEXT NOT NULL,
                updatedAt TEXT NOT NULL,
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_estimates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                version INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'PLN',
                grossTotal REAL NOT NULL DEFAULT 0,
                netTotal REAL NOT NULL DEFAULT 0,
                contingencyPct REAL,
                source TEXT,
                createdAt TEXT NOT NULL,
                UNIQUE(projectId, version),
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cost_estimate_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                estimateId INTEGER NOT NULL,
                category TEXT NOT NULL,
                itemCode TEXT,
                description TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                unit TEXT,
                unitPrice REAL NOT NULL DEFAULT 0,
                netValue REAL NOT NULL DEFAULT 0,
                vatRate REAL,
                grossValue REAL,
                FOREIGN KEY(estimateId) REFERENCES cost_estimates(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_designs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                projectId INTEGER NOT NULL,
                version INTEGER NOT NULL,
                title TEXT NOT NULL,
                stage TEXT NOT NULL,
                description TEXT,
                assumptionsJson TEXT,
                fileId INTEGER,
                createdAt TEXT NOT NULL,
                UNIQUE(projectId, version),
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(fileId) REFERENCES project_files(id) ON DELETE SET NULL
            )
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plots_projectId ON project_plots(projectId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plot_parameters_plotId ON project_plot_parameters(projectPlotId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_files_projectId ON project_files(projectId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_requirements_projectId ON project_requirements(projectId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_estimates_projectId ON cost_estimates(projectId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cost_estimate_items_estimateId ON cost_estimate_items(estimateId)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_designs_projectId ON project_designs(projectId)")

        _ensure_plot_import_columns(conn)
        _ensure_demo_project(conn)

    app.teardown_appcontext(close_db)


def create_timestamp():
    return _utc_now()


def _ensure_plot_import_columns(conn):
    existing = {row[1] for row in conn.execute("PRAGMA table_info(plot_import_jobs)")}
    required = {
        "unitsSource": "TEXT",
        "layerSummaryJson": "TEXT",
        "cadPayloadJson": "TEXT",
        "isDisabled": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, col_type in required.items():
        if column in existing:
            continue
        conn.execute(f"ALTER TABLE plot_import_jobs ADD COLUMN {column} {col_type}")


def _ensure_demo_project(conn):
    now = _utc_now()
    row = conn.execute("SELECT id FROM projects WHERE code = ?", ("DEMO",)).fetchone()
    if row:
        project_id = row[0]
    else:
        cursor = conn.execute(
            """
            INSERT INTO projects (code, name, description, status, investorName, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "DEMO",
                "Projekt demo",
                "Domyślny projekt demonstracyjny do edycji w aplikacji.",
                "ACTIVE",
                "Demo inwestor",
                now,
                now,
            ),
        )
        project_id = cursor.lastrowid

    existing_plot = conn.execute(
        """
        SELECT id FROM project_plots
        WHERE projectId = ? AND externalParcelRef = ?
        """,
        (project_id, "_global"),
    ).fetchone()
    if not existing_plot:
        conn.execute(
            """
            INSERT INTO project_plots (projectId, parcelId, externalParcelRef, notes, createdAt)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "_global",
                "_global",
                "Domyślna działka projektu demo.",
                now,
            ),
        )
