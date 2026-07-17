from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.main import create_app
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisIssueRecord
from backend.app.schemas.suggestion import AdjustmentSuggestion
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.remediation_planning_service import RemediationPlanningService


def _settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "uploads",
                    export_dir=tmp_path / "exports", report_dir=tmp_path / "reports",
                    deepseek_api_key="", dashscope_api_key="")


def _seed_missing_parent_batch(tmp_path, count=3):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file(id,file_name,file_path) VALUES(1,'review.xlsx','review.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    nodes = [
        TaxonomyNodeRecord(category_id=1, category_name="Root", parent_id=None, level=1,
                           path_ids="1", path_names="Root", is_leaf=0),
        TaxonomyNodeRecord(category_id=10, category_name="Equipment", parent_id=1, level=2,
                           path_ids="1,10", path_names="Root > Equipment", is_leaf=0),
    ]
    for offset in range(count):
        node_id = 100 + offset
        nodes.append(TaxonomyNodeRecord(category_id=node_id, category_name=f"Child {offset}", parent_id=99,
                                        level=4, path_ids=f"1,10,99,{node_id}",
                                        path_names=f"Root > Equipment > Missing Parent > Child {offset}", is_leaf=1))
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=nodes)
    batch_id = "review_state_machine"
    ReviewBatchRepository(settings).create(batch_id=batch_id, file_id=1, version_id=version_id)
    suggestion_ids = []
    for offset in range(count):
        node_id = 100 + offset
        issue_id = DiagnosisRepository(settings).create_issue(version_id=version_id, issue=DiagnosisIssueRecord(
            issue_type="missing_parent", node_id=node_id, node_name=f"Child {offset}",
            path=f"Root > Equipment > Missing Parent > Child {offset}",
            description=f"node {node_id} misses parent 99", reason="parent missing",
            risk_level="high", confidence=1.0,
        ))
        issue = DiagnosisRepository(settings).get_issue_detail(issue_id)
        proposal = RemediationPlanningService(settings).plan(version_id, issue)
        suggestion_ids.append(SuggestionRepository(settings).create_suggestion(
            review_batch_id=batch_id, suggestion=proposal
        ))
    ReviewBatchRepository(settings).refresh_status(batch_id)
    return settings, TestClient(create_app(settings)), batch_id, suggestion_ids


def _decision(client, batch_id, decision, ids):
    fields = {
        "approved_suggestion_ids": [], "rejected_suggestion_ids": [],
        "confirmed_without_action_suggestion_ids": [], "uncertain_suggestion_ids": [],
    }
    fields[{"approve": "approved_suggestion_ids", "reject": "rejected_suggestion_ids",
            "confirm_no_action": "confirmed_without_action_suggestion_ids",
            "uncertain": "uncertain_suggestion_ids"}[decision]] = ids
    return client.post(f"/api/reviews/{batch_id}/decision",
                       json={"decision": decision, **fields, "operator": "tester"})


def test_selecting_one_pending_suggestion_exposes_real_executable_capability(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    item = client.get(f"/api/reviews/{batch_id}").json()["suggestions"][0]
    assert item["id"] == ids[0] and item["status"] == "pending" and item["is_executable"] is True


def test_missing_parent_type_can_be_selected_and_approved_together(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path)
    body = client.get(f"/api/reviews/{batch_id}").json()
    assert next(item for item in body["type_stats"] if item["issue_type_code"] == "missing_parent")["pending"] == 3
    assert _decision(client, batch_id, "approve", ids).status_code == 200
    assert client.get(f"/api/reviews/{batch_id}").json()["batch"]["review_status"] == "reviewed"


def test_batch_operation_does_not_change_completed_decisions(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path)
    assert _decision(client, batch_id, "approve", [ids[0]]).status_code == 200
    assert _decision(client, batch_id, "reject", [ids[1]]).status_code == 200
    assert _decision(client, batch_id, "uncertain", [ids[2]]).status_code == 200
    statuses = {item["id"]: item["status"] for item in client.get(f"/api/reviews/{batch_id}").json()["suggestions"]}
    assert statuses == {ids[0]: "approved", ids[1]: "rejected", ids[2]: "deferred"}


def test_incomplete_suggestion_regenerates_in_place(tmp_path):
    settings, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    before_issue_id = SuggestionRepository(settings).get_suggestion(ids[0]).issue_id
    result = client.post(f"/api/reviews/{batch_id}/regenerate", json={})
    item = SuggestionRepository(settings).get_suggestion(ids[0])
    assert result.status_code == 200 and result.json()["review_batch_id"] == batch_id
    assert item.id == ids[0] and item.issue_id == before_issue_id and item.status == "pending"
    assert item.regenerated_at and item.generator_version and item.change_preview.get("impact_scope") is not None


def test_three_shared_missing_parents_create_one_preview_action(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path)
    _decision(client, batch_id, "approve", ids)
    preview = client.post(f"/api/reviews/{batch_id}/execution-preview", json={}).json()
    assert preview["valid"] is True and preview["action_counts"]["create_missing_parent"] == 1
    assert preview["deduplicated_actions"][0]["affected_child_count"] == 3


def test_pending_suggestions_block_execution_preview(tmp_path):
    _, client, batch_id, _ = _seed_missing_parent_batch(tmp_path, 1)
    response = client.post(f"/api/reviews/{batch_id}/execution-preview", json={})
    assert response.status_code == 400 and "1" in response.json()["detail"]


def test_zero_pending_allows_execution_preview(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    _decision(client, batch_id, "approve", ids)
    response = client.post(f"/api/reviews/{batch_id}/execution-preview", json={})
    assert response.status_code == 200 and response.json()["valid"] is True


def test_review_change_marks_old_preview_stale_and_blocks_execute(tmp_path):
    _, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    _decision(client, batch_id, "approve", ids)
    assert client.post(f"/api/reviews/{batch_id}/execution-preview", json={}).status_code == 200
    manual = {"issue_id": None, "action_type": "review_only", "target_node_id": 100,
              "action_payload": {"no_change_reason": "manual check"}, "reason": "manual",
              "suggestion": "manual check", "risk_level": "low", "confidence": 1.0}
    assert client.post(f"/api/reviews/{batch_id}/manual-suggestions", json={"suggestions": [manual]}).status_code == 200
    batch = client.get(f"/api/reviews/{batch_id}").json()["batch"]
    assert batch["preview_status"] == "stale" and batch["can_execute"] is False
    assert client.post(f"/api/reviews/{batch_id}/execute", json={"operator": "tester"}).status_code == 400


def test_no_executable_action_refuses_empty_preview(tmp_path):
    settings, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    SuggestionRepository(settings).update_status(ids[0], "deferred")
    ReviewBatchRepository(settings).refresh_status(batch_id)
    response = client.post(f"/api/reviews/{batch_id}/execution-preview", json={})
    assert response.status_code == 400


def test_execute_rejects_stale_preview_even_if_database_status_is_forged_ready(tmp_path):
    settings, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    _decision(client, batch_id, "approve", ids)
    client.post(f"/api/reviews/{batch_id}/execution-preview", json={})
    with connect(settings) as connection:
        connection.execute("UPDATE adjustment_suggestion SET new_name='Changed after preview' WHERE id=?", (ids[0],))
    response = client.post(f"/api/reviews/{batch_id}/execute", json={"operator": "tester"})
    assert response.status_code == 400


def test_auto_complete_reopens_executable_deferred_and_ignores_non_executable(tmp_path):
    settings, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 2)
    SuggestionRepository(settings).update_status(ids[0], "deferred")
    SuggestionRepository(settings).update_status(ids[1], "deferred")
    with connect(settings) as connection:
        connection.execute(
            "UPDATE adjustment_suggestion SET action_type='review_only',action_payload=? WHERE id=?",
            ('{"no_change_reason":"no reliable action"}', ids[1]),
        )
    response = client.post(f"/api/reviews/{batch_id}/auto-complete", json={"operator": "tester"})
    assert response.status_code == 200
    assert response.json()["approved_ids"] == [ids[0]]
    assert response.json()["ignored_ids"] == [ids[1]]


def test_execution_attaches_detached_batch_and_completes_workflow(tmp_path):
    settings, client, batch_id, ids = _seed_missing_parent_batch(tmp_path, 1)
    task_id = TaskRepository(settings).create_workflow_task(
        file_id=1, workflow_id="workflow-test", thread_id="thread-test"
    )
    TaskRepository(settings).update_task(
        task_id=task_id, status="waiting_review", current_step="review_pending",
        progress=80, version_id=1,
    )
    _decision(client, batch_id, "approve", ids)
    assert client.post(f"/api/reviews/{batch_id}/execution-preview", json={}).status_code == 200
    assert client.post(f"/api/reviews/{batch_id}/execute", json={"operator": "tester"}).status_code == 200
    task = TaskRepository(settings).get_task(task_id)
    assert task["status"] == "completed" and task["progress"] == 100
