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

