import sqlite3
from pathlib import Path

from backend.app.config import Settings


def sqlite_path_from_url(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only sqlite:/// database URLs are supported.")
    return Path(database_url.removeprefix(prefix))


def connect(settings: Settings) -> sqlite3.Connection:
    db_path = sqlite_path_from_url(settings.database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_db(settings: Settings) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS uploaded_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER,
                sheet_name TEXT,
                row_count INTEGER,
                column_count INTEGER,
                upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'uploaded'
            );

            CREATE TABLE IF NOT EXISTS task_record (
                id TEXT PRIMARY KEY,
                file_id INTEGER,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                current_step TEXT,
                progress INTEGER DEFAULT 0,
                error_message TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES uploaded_file(id)
            );

            CREATE TABLE IF NOT EXISTS taxonomy_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                version_no TEXT NOT NULL,
                description TEXT,
                quality_score REAL,
                snapshot_path TEXT,
                vector_index_generation INTEGER NOT NULL DEFAULT 0,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (file_id) REFERENCES uploaded_file(id)
            );

            CREATE TABLE IF NOT EXISTS category_node (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                category_name TEXT NOT NULL,
                parent_id INTEGER,
                level INTEGER,
                path_ids TEXT,
                path_names TEXT,
                category_group_id TEXT,
                category_pids TEXT,
                category_group_name TEXT,
                syn_list TEXT,
                is_leaf INTEGER DEFAULT 0,
                node_status TEXT NOT NULL DEFAULT 'active',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS diagnosis_issue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                issue_type TEXT NOT NULL,
                node_id INTEGER,
                node_name TEXT,
                description TEXT,
                reason TEXT,
                risk_level TEXT,
                confidence REAL,
                status TEXT DEFAULT 'pending',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS adjustment_suggestion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                review_batch_id TEXT,
                version_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                target_node_id INTEGER,
                target_node_name TEXT,
                old_parent_id INTEGER,
                new_parent_id INTEGER,
                old_name TEXT,
                new_name TEXT,
                action_payload TEXT,
                reason TEXT,
                suggestion TEXT,
                risk_level TEXT,
                confidence REAL,
                need_confirm INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (issue_id) REFERENCES diagnosis_issue(id),
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS operation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER,
                operator TEXT,
                operation_type TEXT,
                operation_detail TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS workflow_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                task_id TEXT,
                node_name TEXT,
                event_type TEXT NOT NULL,
                status TEXT,
                progress INTEGER,
                message TEXT,
                payload TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS review_batch (
                id TEXT PRIMARY KEY,
                file_id INTEGER NOT NULL,
                version_id INTEGER NOT NULL,
                task_id TEXT,
                workflow_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                execution_status TEXT NOT NULL DEFAULT 'not_ready',
                new_version_id INTEGER,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_time DATETIME,
                FOREIGN KEY (file_id) REFERENCES uploaded_file(id),
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id),
                FOREIGN KEY (new_version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS report_artifact (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                review_batch_id TEXT,
                report_type TEXT NOT NULL,
                report_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'generated',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(version_id, report_type),
                FOREIGN KEY (version_id) REFERENCES taxonomy_version(id)
            );

            CREATE TABLE IF NOT EXISTS agent_run (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                version_id INTEGER NOT NULL,
                plan_revision INTEGER DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending',
                model_profile TEXT DEFAULT 'default',
                budget TEXT DEFAULT '{}',
                coverage TEXT DEFAULT '{}',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_work_item (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                worker_id TEXT,
                lease_expires_at DATETIME,
                input_payload TEXT DEFAULT '{}',
                result_payload TEXT DEFAULT '{}',
                error_code TEXT,
                error_message TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES agent_run(id)
            );

            CREATE TABLE IF NOT EXISTS run_issue (
                run_id TEXT NOT NULL,
                issue_id INTEGER NOT NULL,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (run_id, issue_id),
                FOREIGN KEY (run_id) REFERENCES agent_run(id),
                FOREIGN KEY (issue_id) REFERENCES diagnosis_issue(id)
            );

            CREATE TABLE IF NOT EXISTS agent_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                run_id TEXT,
                work_item_id TEXT,
                agent_name TEXT,
                event_type TEXT NOT NULL,
                phase TEXT,
                tool_name TEXT,
                status TEXT,
                attempt INTEGER,
                latency_ms INTEGER,
                model TEXT,
                token_usage TEXT DEFAULT '{}',
                summary TEXT DEFAULT '{}',
                evidence_refs TEXT DEFAULT '[]',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tool_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL, version_id INTEGER, tool_name TEXT NOT NULL,
                args_hash TEXT NOT NULL, data_revision TEXT NOT NULL, result_json TEXT NOT NULL,
                expires_time DATETIME NOT NULL, hit_count INTEGER NOT NULL DEFAULT 0,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(workflow_id, version_id, tool_name, args_hash, data_revision)
            );

            CREATE TABLE IF NOT EXISTS agent_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT, memory_type TEXT NOT NULL,
                scope_type TEXT NOT NULL, scope_key TEXT NOT NULL, content TEXT NOT NULL,
                source_workflow_id TEXT, source_version_id INTEGER, valid_from_version_id INTEGER,
                valid_until_version_id INTEGER, confidence REAL NOT NULL, created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS agent_evaluation (
                id INTEGER PRIMARY KEY AUTOINCREMENT, dataset_version TEXT NOT NULL, workflow_id TEXT NOT NULL,
                metrics TEXT NOT NULL, agent_bundle_version TEXT, created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS evaluation_baseline (
                id INTEGER PRIMARY KEY AUTOINCREMENT, baseline_id TEXT NOT NULL UNIQUE,
                dataset_version TEXT NOT NULL UNIQUE, evaluation_id INTEGER NOT NULL,
                agent_bundle_version TEXT NOT NULL, approved_by TEXT NOT NULL,
                approved_time DATETIME DEFAULT CURRENT_TIMESTAMP, pinned INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(evaluation_id) REFERENCES agent_evaluation(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_node_version_category
            ON category_node(version_id, category_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_unique_rule
            ON diagnosis_issue(version_id, issue_type, node_id, description);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_work_item_unique
            ON agent_work_item(run_id, subject_type, subject_id);

            CREATE INDEX IF NOT EXISTS idx_agent_work_item_status
            ON agent_work_item(run_id, status);

            CREATE INDEX IF NOT EXISTS idx_agent_event_workflow_sequence
            ON agent_event(workflow_id, id);
            """
        )
        _ensure_columns(
            connection,
            "task_record",
            {
                "workflow_id": "TEXT",
                "thread_id": "TEXT",
                "version_id": "INTEGER",
                "interrupt_payload": "TEXT",
                "result_payload": "TEXT",
                "enable_ai_analysis": "INTEGER DEFAULT 0",
                "model_provider": "TEXT",
                "model_name": "TEXT",
                "start_time": "DATETIME",
                "end_time": "DATETIME",
                "primary_run_id": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "taxonomy_version",
            {
                "vector_index_generation": "INTEGER NOT NULL DEFAULT 0",
                "parent_version_id": "INTEGER",
                "source_workflow_id": "TEXT",
                "action_batch_id": "TEXT",
                "verification_status": "TEXT NOT NULL DEFAULT 'not_verified'",
                "export_path": "TEXT",
                "supersedes_version_id": "INTEGER",
                "lifecycle_status": "TEXT NOT NULL DEFAULT 'draft'",
                "diagnosis_mode": "TEXT",
                "diagnosis_model": "TEXT",
                "verification_mode": "TEXT",
                "verification_model": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "category_node",
            {"node_status": "TEXT NOT NULL DEFAULT 'active'"},
        )
        _ensure_columns(
            connection,
            "adjustment_suggestion",
            {"review_batch_id": "TEXT", "old_value": "TEXT", "new_value": "TEXT",
             "work_item_id": "TEXT", "analysis_run_id": "TEXT", "workflow_id": "TEXT",
             "change_preview": "TEXT DEFAULT '{}'", "consistency_status": "TEXT DEFAULT 'unchecked'",
             "consistency_reason": "TEXT", "is_manual": "INTEGER DEFAULT 0",
             "regenerated_at": "DATETIME", "generator_version": "TEXT"},
        )
        _ensure_columns(
            connection,
            "review_batch",
            {"workflow_state": "TEXT NOT NULL DEFAULT 'reviewing'", "preview_hash": "TEXT",
             "preview_payload": "TEXT", "preview_base_version_id": "INTEGER",
             "preview_base_generation": "INTEGER", "preview_created_time": "DATETIME"},
        )
        _ensure_columns(
            connection,
            "diagnosis_issue",
            {"path": "TEXT", "evidence": "TEXT", "source": "TEXT",
             "subject_node_id": "INTEGER", "subject_node_name": "TEXT", "subject_path": "TEXT",
             "detector_version": "TEXT NOT NULL DEFAULT 'rules-v1'"},
        )
        _ensure_columns(
            connection,
            "report_artifact",
            {"workflow_id": "TEXT", "run_id": "TEXT", "fact_payload": "TEXT DEFAULT '{}'"},
        )
        _ensure_columns(
            connection,
            "review_batch",
            {"source_review_batch_id": "TEXT", "batch_kind": "TEXT NOT NULL DEFAULT 'current'"},
        )
        connection.execute("""UPDATE diagnosis_issue SET subject_node_id=COALESCE(subject_node_id,node_id),
                              subject_node_name=COALESCE(subject_node_name,node_name),
                              subject_path=COALESCE(subject_path,path)""")
        # One batched work item may produce one suggestion per issue.  The
        # composite key keeps retries idempotent without collapsing a batch to
        # its first issue.
        connection.execute("DROP INDEX IF EXISTS idx_suggestion_work_item")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestion_work_item_issue ON adjustment_suggestion(work_item_id, issue_id) WHERE work_item_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_version_action_batch ON taxonomy_version(action_batch_id) WHERE action_batch_id IS NOT NULL"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS version_execution_record (
            id INTEGER PRIMARY KEY AUTOINCREMENT, review_batch_id TEXT NOT NULL,
            source_version_id INTEGER NOT NULL, target_version_id INTEGER,
            review_hash TEXT, action_summary TEXT DEFAULT '{}', status TEXT NOT NULL,
            created_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        _ensure_columns(
            connection,
            "version_execution_record",
            {"workflow_id": "TEXT", "run_id": "TEXT", "error_code": "TEXT", "error_message": "TEXT"},
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_run_issue_issue ON run_issue(issue_id, run_id)"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS maintenance_cleanup_preview (
            id TEXT PRIMARY KEY, request_payload TEXT NOT NULL, resolved_scope TEXT NOT NULL,
            result_payload TEXT NOT NULL, scope_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_time DATETIME DEFAULT CURRENT_TIMESTAMP, expires_time DATETIME NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS pending_file_cleanup (
            id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending', created_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS maintenance_cleanup_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cleanup_preview_id TEXT NOT NULL,
            request_payload TEXT NOT NULL, resolved_scope TEXT NOT NULL,
            deleted_payload TEXT NOT NULL, backup_path TEXT NOT NULL,
            pending_payload TEXT DEFAULT '[]', status TEXT NOT NULL,
            created_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute(
            """INSERT OR IGNORE INTO review_batch(id,file_id,version_id,task_id,workflow_id,status,execution_status)
               SELECT suggestion.review_batch_id, version.file_id, suggestion.version_id,
                      task.id, suggestion.workflow_id,
                      CASE WHEN SUM(suggestion.status='executed')>0 THEN 'executed'
                           WHEN SUM(suggestion.status IN ('pending','edited'))=0 THEN 'reviewed'
                           ELSE 'in_review' END,
                       CASE WHEN SUM(suggestion.status='executed')>0 THEN 'executed'
                            WHEN SUM(suggestion.status IN ('pending','edited'))=0 THEN 'missing'
                           ELSE 'blocked' END
               FROM adjustment_suggestion suggestion
               JOIN taxonomy_version version ON version.id=suggestion.version_id
               LEFT JOIN task_record task ON task.workflow_id=suggestion.workflow_id
               WHERE suggestion.review_batch_id IS NOT NULL
               GROUP BY suggestion.review_batch_id"""
        )
        # Compatibility is additive: historical decisions/actions remain untouched, while
        # completed batches must obtain a fresh preview before any future execution.
        connection.execute(
            """UPDATE review_batch SET
                   status=CASE WHEN status='executed' THEN 'executed'
                               WHEN status IN ('completed','reviewed','preview_ready') THEN 'reviewed' ELSE 'in_review' END,
                   execution_status=CASE WHEN execution_status='executed' THEN 'executed'
                                         WHEN status IN ('completed','reviewed','preview_ready') THEN 'missing' ELSE 'blocked' END,
                   workflow_state=CASE WHEN execution_status='executed' THEN 'executed'
                                       WHEN status IN ('completed','reviewed','preview_ready') THEN 'review_completed' ELSE 'reviewing' END
               WHERE preview_hash IS NULL"""
        )
        connection.execute(
            """UPDATE taxonomy_version SET lifecycle_status=
                   CASE verification_status WHEN 'passed' THEN 'passed' WHEN 'partial' THEN 'partial'
                                            WHEN 'failed' THEN 'failed' ELSE 'draft' END
               WHERE lifecycle_status IS NULL OR lifecycle_status='draft'"""
        )


def _ensure_columns(
    connection: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, column_type in columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            )
