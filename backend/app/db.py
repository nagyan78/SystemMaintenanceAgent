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
            },
        )
        _ensure_columns(
            connection,
            "adjustment_suggestion",
            {"review_batch_id": "TEXT", "old_value": "TEXT", "new_value": "TEXT",
             "work_item_id": "TEXT", "analysis_run_id": "TEXT", "workflow_id": "TEXT"},
        )
        _ensure_columns(
            connection,
            "diagnosis_issue",
            {"path": "TEXT", "evidence": "TEXT", "source": "TEXT"},
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestion_work_item ON adjustment_suggestion(work_item_id) WHERE work_item_id IS NOT NULL"
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
