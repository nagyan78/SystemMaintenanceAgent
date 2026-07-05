from backend.app.agents.states import TaxonomyGraphState


def create_initial_state(file_id: int, task_id: str | None = None) -> TaxonomyGraphState:
    return TaxonomyGraphState(file_id=file_id, task_id=task_id, status="pending")

