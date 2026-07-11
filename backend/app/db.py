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

            CREATE TABLE IF NOT EXISTS analysis_run (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                round INTEGER NOT NULL,
                analyzed_version_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_time DATETIME,
                UNIQUE(workflow_id, round)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_node_version_category
            ON category_node(version_id, category_id);

            CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_unique_rule
            ON diagnosis_issue(version_id, issue_type, node_id, description);
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
            },
        )
        _ensure_columns(
            connection,
            "adjustment_suggestion",
            {
                "review_batch_id": "TEXT",
                "workflow_id": "TEXT",
                "analysis_run_id": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "diagnosis_issue",
            {
                "workflow_id": "TEXT",
                "analysis_run_id": "TEXT",
                "detector_version": "TEXT DEFAULT 'legacy-v1'",
            },
        )
        _ensure_columns(
            connection,
            "operation_log",
            {"workflow_id": "TEXT", "analysis_run_id": "TEXT"},
        )
        connection.execute("DROP INDEX IF EXISTS idx_issue_unique_rule")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_issue_unique_run_rule
            ON diagnosis_issue(
                analysis_run_id, detector_version, issue_type, node_id, description
            )
            """
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
