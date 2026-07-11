from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.main import create_app
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.task_repo import TaskRepository


def _settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path/'app.db'}", upload_dir=tmp_path/"uploads", export_dir=tmp_path/"exports", report_dir=tmp_path/"reports")


def test_agent_event_is_resumable_and_redacted_over_sse(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    tasks = TaskRepository(settings)
    task_id = tasks.create_workflow_task(file_id=1, workflow_id="wf-events", thread_id="thread-events")
    agent_events = AgentRunRepository(settings)
    agent_events.record_event(
        workflow_id="wf-events", event_type="candidate_completed", agent_name="content_diagnosis",
        status="succeeded", summary={"api_key":"secret", "raw_prompt":"hidden", "decision":"issue"},
    )
    tasks.update_task(task_id=task_id, status="completed", current_step="completed", progress=100)
    client = TestClient(app)
    first = client.get(f"/api/workflows/{task_id}/events?after_id=0")
    assert "id: " in first.text
    assert "candidate_completed" in first.text
    assert "api_key" not in first.text
    assert "raw_prompt" not in first.text
    event_id = next(int(line.removeprefix("id: ")) for line in first.text.splitlines() if line.startswith("id: "))
    second = client.get(f"/api/workflows/{task_id}/events", headers={"Last-Event-ID": str(event_id)})
    assert f"id: {event_id}\n" not in second.text


def test_cancelled_workflow_stops_new_claims(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id,file_name,file_path) VALUES (1,'test.xlsx','test.xlsx')")
    task_id = TaskRepository(settings).create_workflow_task(file_id=1, workflow_id="wf-cancel", thread_id="thread")
    client = TestClient(app)
    response = client.post(f"/api/workflows/{task_id}/cancel")
    assert response.status_code == 200
    assert client.get(f"/api/workflows/{task_id}").json()["status"] == "cancelled"
