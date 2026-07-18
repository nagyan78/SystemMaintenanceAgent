import pytest
from pydantic import ValidationError

from backend.app.agents.states import TaxonomyGraphState


def test_taxonomy_graph_state_defaults_to_pending():
    state = TaxonomyGraphState(
        workflow_id="workflow_1",
        thread_id="taxonomy_workflow:workflow_1",
        file_id=1,
    )

    assert state.file_id == 1
    assert state.status == "pending"
    assert state.progress == 0
    assert state.completed_steps == []
    assert state.structure_issue_count == 0


def test_taxonomy_graph_state_rejects_invalid_progress():
    with pytest.raises(ValidationError):
        TaxonomyGraphState(
            workflow_id="workflow_1",
            thread_id="taxonomy_workflow:workflow_1",
            file_id=1,
            progress=101,
        )


def test_taxonomy_graph_state_rejects_removed_waiting_review_status():
    with pytest.raises(ValidationError):
        TaxonomyGraphState(
            workflow_id="workflow_1",
            thread_id="taxonomy_workflow:workflow_1",
            file_id=1,
            status="waiting_review",
        )
