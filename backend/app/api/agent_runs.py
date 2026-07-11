from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.repositories.agent_run_repo import AgentRunRepository

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.get("/{run_id}")
def get_agent_run(run_id: str, request: Request) -> dict:
    repo = AgentRunRepository(request.app.state.settings)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found.")
    return {**run, "work_item_counts": repo.counts(run_id)}


@router.get("/{run_id}/events")
def list_agent_events(run_id: str, request: Request, after_id: int = Query(default=0, ge=0)) -> list[dict]:
    repo = AgentRunRepository(request.app.state.settings)
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found.")
    return [event for event in repo.list_events(run["workflow_id"], after_id=after_id) if event.get("run_id") == run_id]
