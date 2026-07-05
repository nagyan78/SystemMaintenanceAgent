from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    create_thread_id,
    create_workflow_id,
)
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.task_repo import TaskRepository


router = APIRouter(prefix="/workflows", tags=["workflows"])


class StartWorkflowRequest(BaseModel):
    file_id: int


class StartWorkflowResponse(BaseModel):
    task_id: str
    workflow_id: str
    thread_id: str
    status: str
    current_step: str
    progress: int


@router.post("/taxonomy/start", response_model=StartWorkflowResponse)
def start_taxonomy_workflow(
    payload: StartWorkflowRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> StartWorkflowResponse:
    settings = request.app.state.settings
    if FileRepository(settings).get_file(payload.file_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    workflow_id = create_workflow_id(payload.file_id)
    thread_id = create_thread_id(workflow_id)
    task_repo = TaskRepository(settings)
    task_id = task_repo.create_workflow_task(
        file_id=payload.file_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
    )
    task_repo.record_event(
        workflow_id=workflow_id,
        thread_id=thread_id,
        task_id=task_id,
        node_name=None,
        event_type="workflow_started",
        status="running",
        progress=0,
        message="taxonomy workflow started",
        payload={"file_id": payload.file_id},
    )
    background_tasks.add_task(
        _run_workflow,
        settings,
        payload.file_id,
        task_id,
        workflow_id,
    )
    return StartWorkflowResponse(
        task_id=task_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
        status="running",
        current_step="parse_excel",
        progress=0,
    )


@router.get("/{task_id}")
def get_workflow_status(task_id: str, request: Request) -> dict[str, Any]:
    task = TaskRepository(request.app.state.settings).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    payload = _loads(task.get("result_payload"))
    return {
        "task_id": task["id"],
        "status": task["status"],
        "current_step": task["current_step"],
        "progress": task["progress"],
        "file_id": task["file_id"],
        "current_version_id": task["version_id"],
        "version_no": payload.get("version_no"),
        "node_count": payload.get("node_count", 0),
        "structure_issue_count": payload.get("structure_issue_count", 0),
        "report_path": payload.get("report_path"),
    }


def _run_workflow(settings, file_id: int, task_id: str, workflow_id: str) -> None:
    state = create_initial_state(
        file_id=file_id,
        task_id=task_id,
        workflow_id=workflow_id,
    )
    task_repo = TaskRepository(settings)
    try:
        graph = build_taxonomy_graph(settings=settings)
        result = graph.invoke(state, config={"configurable": {"thread_id": state.thread_id}})
        if result.get("status") == "failed":
            task_repo.update_task(
                task_id=task_id,
                status="failed",
                current_step=result.get("current_step"),
                progress=result.get("progress", 0),
                error_message=result.get("error_message"),
                result_payload=result,
            )
    except Exception as exc:
        task_repo.update_task(
            task_id=task_id,
            status="failed",
            current_step="failed",
            error_message=str(exc),
        )
        task_repo.record_event(
            workflow_id=workflow_id,
            thread_id=create_thread_id(workflow_id),
            task_id=task_id,
            node_name=None,
            event_type="workflow_failed",
            status="failed",
            message=str(exc),
        )


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    import json

    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}
