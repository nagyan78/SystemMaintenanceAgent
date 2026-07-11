import json

import pytest
from pydantic import ValidationError

from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.task_repo import TaskRepository
from backend.app.schemas.workflow import (
    ContinueResume,
    HumanReviewResume,
    StartWorkflowRequest,
    parse_resume_request,
)


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def test_start_request_validates_each_workflow_mode() -> None:
    assert StartWorkflowRequest(mode="import", file_id=1).file_id == 1
    assert StartWorkflowRequest(mode="maintain", base_version_id=2).base_version_id == 2
    assert StartWorkflowRequest(
        mode="verify", base_version_id=2, result_version_id=3, affected_node_ids=[11]
    ).result_version_id == 3

    with pytest.raises(ValidationError):
        StartWorkflowRequest(mode="import")
    with pytest.raises(ValidationError):
        StartWorkflowRequest(mode="maintain")
    with pytest.raises(ValidationError):
        StartWorkflowRequest(mode="verify", base_version_id=2)


def test_resume_request_is_discriminated_by_interrupt_type() -> None:
    review = parse_resume_request(
        {
            "interrupt_type": "human_review",
            "interrupt_id": "int-1",
            "decision": "approve",
        }
    )
    continuation = parse_resume_request(
        {
            "interrupt_type": "continue_optimization",
            "interrupt_id": "int-2",
            "decision": "continue",
        }
    )

    assert isinstance(review, HumanReviewResume)
    assert isinstance(continuation, ContinueResume)
    with pytest.raises(ValidationError):
        parse_resume_request(
            {
                "interrupt_type": "continue_optimization",
                "interrupt_id": "int-3",
                "decision": "approve",
            }
        )


def test_state_supports_continue_and_degraded_statuses() -> None:
    state = TaxonomyGraphState(
        workflow_id="wf",
        thread_id="thread",
        workflow_mode="maintain",
        status="waiting_continue",
        interrupt_type="continue_optimization",
        interrupt_id="int-1",
        base_version_id=1,
        result_version_id=2,
    )

    assert state.status == "waiting_continue"
    assert state.round == 1
    assert state.max_rounds == 2


def test_task_repository_persists_and_replays_consumed_interrupt(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    repo = TaskRepository(settings)
    task_id = repo.create_workflow_task(
        file_id=1,
        workflow_id="wf",
        thread_id="thread",
        workflow_mode="maintain",
        base_version_id=1,
    )
    repo.update_task(
        task_id=task_id,
        status="waiting_continue",
        interrupt_payload={
            "interrupt_type": "continue_optimization",
            "interrupt_id": "int-1",
        },
        interrupt_id="int-1",
    )
    assert repo.claim_interrupt(task_id, "int-1")[0] == "claimed"
    repo.save_resume_result(
        task_id=task_id,
        interrupt_id="int-1",
        result={"status": "running", "round": 2},
    )

    task = repo.get_task(task_id)
    assert task["workflow_mode"] == "maintain"
    assert task["base_version_id"] == 1
    assert task["consumed_interrupt_id"] == "int-1"
    assert json.loads(task["resume_result_payload"])["round"] == 2


def test_task_repository_atomically_claims_exact_active_interrupt(tmp_path) -> None:
    settings = _settings(tmp_path)
    init_db(settings)
    repo = TaskRepository(settings)
    task_id = repo.create_workflow_task(
        file_id=1,
        workflow_id="wf-claim",
        thread_id="thread-claim",
    )
    repo.update_task(
        task_id=task_id,
        status="waiting_continue",
        interrupt_payload={
            "interrupt_type": "continue_optimization",
            "interrupt_id": "active-int",
        },
        interrupt_id="active-int",
    )

    assert repo.claim_interrupt(task_id, "wrong-int")[0] == "mismatch"
    assert repo.claim_interrupt(task_id, "active-int")[0] == "claimed"
    assert repo.claim_interrupt(task_id, "active-int")[0] == "in_progress"
    repo.save_resume_result(
        task_id=task_id,
        interrupt_id="active-int",
        result={"status": "running"},
    )
    status, result = repo.claim_interrupt(task_id, "active-int")
    assert status == "consumed"
    assert result == {"status": "running"}
