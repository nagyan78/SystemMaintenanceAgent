# Backend Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable FastAPI backend skeleton for the standard taxonomy maintenance agent.

**Architecture:** The backend exposes a small app factory, modular routers, SQLite initialization, and a file upload service. Business modules for taxonomy, diagnosis, suggestions, versions, chat, LangGraph, and Qdrant are scaffolded as boundaries for later implementation.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, sqlite3, pandas/openpyxl, pytest.

---

### Task 1: Backend App Factory And Health Check

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/api/health.py`
- Test: `backend/tests/test_health_api.py`

- [ ] **Step 1: Write failing health API test**

```python
from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_health_check_returns_ok():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_health_api.py -q`

Expected: FAIL because `backend.app.main` does not exist.

- [ ] **Step 3: Implement minimal FastAPI app and health router**

Create `create_app()` in `backend/app/main.py`, register `/api/health`, and return app metadata from settings.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_health_api.py -q`

Expected: PASS.

### Task 2: SQLite Initialization

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/repositories/file_repo.py`
- Test: `backend/tests/test_db.py`

- [ ] **Step 1: Write failing database initialization test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_db.py -q`

Expected: FAIL because `backend.app.db` does not exist.

- [ ] **Step 3: Implement SQLite schema bootstrap**

Implement `init_db(settings)` using stdlib `sqlite3`; create `uploaded_file` and `task_record` tables.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_db.py -q`

Expected: PASS.

### Task 3: File Upload Skeleton

**Files:**
- Create: `backend/app/api/files.py`
- Create: `backend/app/services/excel_service.py`
- Create: `backend/app/schemas/file.py`
- Test: `backend/tests/test_file_upload_api.py`

- [ ] **Step 1: Write failing upload test**

```python
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.main import create_app


def test_upload_xlsx_saves_file_and_returns_metadata(tmp_path):
    workbook_path = tmp_path / "taxonomy.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([
        "category_id",
        "category_name",
        "category_group_id",
        "category_pids",
        "category_group_name",
        "syn_list",
    ])
    sheet.append([1, "根节点", "", "", "根节点", ""])
    workbook.save(workbook_path)

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
    )
    client = TestClient(create_app(settings))

    with workbook_path.open("rb") as file_obj:
        response = client.post(
            "/api/files/upload",
            files={
                "file": (
                    "taxonomy.xlsx",
                    file_obj,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["file_id"] == 1
    assert body["row_count"] == 1
    assert body["column_count"] == 6
    assert body["status"] == "uploaded"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_file_upload_api.py -q`

Expected: FAIL because file API modules do not exist.

- [ ] **Step 3: Implement upload route and service**

Validate `.xlsx`, save to `data/uploads`, inspect the first sheet with openpyxl, insert `uploaded_file`, create an `import_excel` task, and return upload metadata.

- [ ] **Step 4: Run all backend tests**

Run: `python -m pytest backend/tests -q`

Expected: PASS.
