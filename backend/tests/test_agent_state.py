from backend.app.agents.states import TaxonomyGraphState


def test_taxonomy_graph_state_defaults_to_pending():
    state = TaxonomyGraphState(file_id=1)

    assert state.file_id == 1
    assert state.status == "pending"
    assert state.structure_issue_count == 0

