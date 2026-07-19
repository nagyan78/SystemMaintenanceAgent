import sqlite3

from backend.app.config import Settings
from backend.app.db import init_db


def test_init_db_creates_uploaded_file_and_task_tables(tmp_path):
    db_path = tmp_path / "app.db"

    init_db(Settings(database_url=f"sqlite:///{db_path}"))

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "uploaded_file" in tables
    assert "task_record" in tables


def test_init_db_migrates_duplicate_analysis_issues_before_creating_index(tmp_path):
    db_path = tmp_path / "app.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    init_db(settings)

    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP INDEX idx_issue_unique_run_rule")
        values = (1, "workflow-1", "run-1", "structure-v1", "missing_parent", 5, "节点", "缺少父节点")
        connection.execute(
            """
            INSERT INTO diagnosis_issue (
                version_id, workflow_id, analysis_run_id, detector_version,
                issue_type, node_id, node_name, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        connection.execute(
            """
            INSERT INTO diagnosis_issue (
                version_id, workflow_id, analysis_run_id, detector_version,
                issue_type, node_id, node_name, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

    init_db(settings)

    with sqlite3.connect(db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM diagnosis_issue").fetchone()[0]
        index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_issue_unique_run_rule'"
        ).fetchone()

    assert count == 1
    assert index == ("idx_issue_unique_run_rule",)
