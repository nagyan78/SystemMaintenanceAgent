import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from pydantic import BaseModel, ValidationError

from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    create_thread_id,
    create_workflow_id,
)
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.quality_repo import QualityRepository
from backend.app.schemas.workflow import StartWorkflowRequest, parse_resume_request
from backend.app.services.workflow_context_service import WorkflowContextService


router = APIRouter(prefix="/workflows", tags=["workflows"])
_WORKFLOW_CHECKPOINTER = None


class StartWorkflowResponse(BaseModel):
    task_id: str
    workflow_id: str
    thread_id: str
    status: str
    current_step: str
    progress: int


def _get_workflow_checkpointer():
    global _WORKFLOW_CHECKPOINTER
    if _WORKFLOW_CHECKPOINTER is None:
        from backend.app.agents.checkpoints import create_sqlite_checkpointer

        _WORKFLOW_CHECKPOINTER = create_sqlite_checkpointer()
    return _WORKFLOW_CHECKPOINTER


@router.post("/taxonomy/start", response_model=StartWorkflowResponse)
def start_taxonomy_workflow(
    payload: StartWorkflowRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> StartWorkflowResponse:
    settings = request.app.state.settings
    try:
        context = WorkflowContextService(settings).resolve(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    workflow_id = create_workflow_id(context.file_id)
    thread_id = create_thread_id(workflow_id)
    task_repo = TaskRepository(settings)
    task_id = task_repo.create_workflow_task(
        file_id=context.file_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
        workflow_mode=context.mode,
        base_version_id=context.base_version_id,
        result_version_id=context.result_version_id,
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
        payload=context.model_dump(),
    )
    background_tasks.add_task(
        _run_workflow,
        settings,
        context,
        task_id,
        workflow_id,
    )
    return StartWorkflowResponse(
        task_id=task_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
        status="running",
        current_step=(
            "parse_excel" if context.mode == "import" else "load_version_context"
        ),
        progress=0,
    )


@router.get("/{task_id}")
def get_workflow_status(task_id: str, request: Request) -> dict[str, Any]:
    task = TaskRepository(request.app.state.settings).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    payload = _loads(task.get("result_payload"))
    interrupt_payload = _loads(task.get("interrupt_payload"))
    quality_repo = QualityRepository(request.app.state.settings)
    evaluation_before = (
        quality_repo.get(int(payload["evaluation_before_id"]))
        if payload.get("evaluation_before_id")
        else None
    )
    evaluation_after = (
        quality_repo.get(int(payload["evaluation_after_id"]))
        if payload.get("evaluation_after_id")
        else None
    )
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
        "suggestion_count": payload.get("suggestion_count", 0),
        "review_batch_id": payload.get("review_batch_id"),
        "report_path": payload.get("report_path"),
        "error_message": task.get("error_message"),
        "workflow_mode": task.get("workflow_mode") or "import",
        "base_version_id": task.get("base_version_id") or payload.get("base_version_id"),
        "result_version_id": payload.get("result_version_id") or task.get("result_version_id"),
        "evaluation_before_id": payload.get("evaluation_before_id"),
        "evaluation_after_id": payload.get("evaluation_after_id"),
        "evaluation_before": evaluation_before.model_dump() if evaluation_before else None,
        "evaluation_after": evaluation_after.model_dump() if evaluation_after else None,
        "verification": payload.get("verification_payload"),
        "interrupt_type": interrupt_payload.get("interrupt_type"),
        "interrupt_id": interrupt_payload.get("interrupt_id") or task.get("interrupt_id"),
        "round": payload.get("round") or task.get("round") or 1,
        "max_rounds": payload.get("max_rounds") or 2,
    }


@router.get("/{task_id}/events")
def workflow_events(task_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events stream of real workflow progress (M5).

    Emits ``workflow_step`` frames as nodes complete, then a terminal
    ``workflow_interrupt`` / ``workflow_completed`` / ``workflow_failed`` frame
    and closes. The frontend consumes this instead of a static progress bar.
    """
    settings = request.app.state.settings
    task_repo = TaskRepository(settings)
    task = task_repo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    workflow_id = task["workflow_id"]

    async def _stream() -> Any:
        from backend.app.agents.events import (
            completed_event,
            format_sse,
            interrupt_event,
            map_workflow_event,
        )

        last_id = 0
        seen_terminal = False
        while not seen_terminal:
            if await request.is_disconnected():
                return
            rows = task_repo.list_events(workflow_id, after_id=last_id)
            for row in rows:
                last_id = row["id"]
                event = map_workflow_event(row)
                if event is not None:
                    yield format_sse(event)

            current = task_repo.get_task(task_id)
            if current is None:
                return
            task_status = current["status"]
            if task_status in {"waiting_review", "waiting_continue"}:
                yield format_sse(interrupt_event(current.get("interrupt_payload")))
                seen_terminal = True
            elif task_status == "waiting_manual_intervention":
                yield format_sse(
                    {
                        "event": "workflow_manual_intervention",
                        "data": {"task_id": task_id, "status": task_status},
                    }
                )
                seen_terminal = True
            elif task_status == "completed":
                yield format_sse(completed_event(task_id, current.get("result_payload")))
                seen_terminal = True
            elif task_status == "completed_degraded":
                event = completed_event(task_id, current.get("result_payload"))
                event["event"] = "workflow_completed_degraded"
                yield format_sse(event)
                seen_terminal = True
            elif task_status == "failed":
                yield format_sse(
                    {
                        "event": "workflow_failed",
                        "data": {"message": current.get("error_message") or "workflow failed"},
                    }
                )
                seen_terminal = True
            else:
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/{task_id}/resume")
def resume_workflow(
    task_id: str,
    payload: dict[str, Any],
    request: Request,
) -> dict[str, Any]:
    settings = request.app.state.settings
    task_repo = TaskRepository(settings)
    task = task_repo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    stored_interrupt = _loads(task.get("interrupt_payload"))
    normalized = dict(payload)
    normalized.setdefault(
        "interrupt_type",
        stored_interrupt.get("interrupt_type") or "human_review",
    )
    normalized.setdefault(
        "interrupt_id",
        task.get("interrupt_id")
        or stored_interrupt.get("interrupt_id")
        or f"legacy:{task_id}",
    )
    try:
        resume_request = parse_resume_request(normalized)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc
    expected_status = {
        "human_review": "waiting_review",
        "continue_optimization": "waiting_continue",
    }[resume_request.interrupt_type]
    stored_type = stored_interrupt.get("interrupt_type") or (
        "human_review" if task["status"] == "waiting_review" else None
    )
    if task.get("consumed_interrupt_id") == resume_request.interrupt_id and task.get(
        "resume_result_payload"
    ):
        return _loads(task.get("resume_result_payload"))
    if task["status"] != expected_status or (
        stored_type is not None and stored_type != resume_request.interrupt_type
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume request does not match the active workflow interrupt.",
        )
    claim_status, claimed_result = task_repo.claim_interrupt(
        task_id,
        resume_request.interrupt_id,
    )
    if claim_status == "consumed":
        return claimed_result or {}
    if claim_status != "claimed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Resume request interrupt_id does not match the active interrupt."
                if claim_status == "mismatch"
                else "The active interrupt is already being resumed."
            ),
        )
    try:
        graph = build_taxonomy_graph(
            _get_workflow_checkpointer(),
            settings=settings,
            enable_suggestion_review=True,
        )
        result = graph.invoke(
            Command(resume=resume_request.model_dump()),
            config={"configurable": {"thread_id": task["thread_id"]}},
        )
    except Exception as exc:
        task_repo.release_interrupt_claim(task_id, resume_request.interrupt_id)
        task_repo.update_task(
            task_id=task_id,
            status="failed",
            current_step="failed",
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    task_repo.save_resume_result(
        task_id=task_id,
        interrupt_id=resume_request.interrupt_id,
        result=result,
    )
    return result


def _run_workflow(settings, context, task_id: str, workflow_id: str) -> None:
    state = create_initial_state(
        file_id=context.file_id,
        task_id=task_id,
        workflow_id=workflow_id,
        workflow_mode=context.mode,
        base_version_id=context.base_version_id,
        result_version_id=context.result_version_id,
        affected_node_ids=context.affected_node_ids,
        max_rounds=context.max_rounds,
    )
    task_repo = TaskRepository(settings)
    try:
        graph = build_taxonomy_graph(
            _get_workflow_checkpointer(),
            settings=settings,
            enable_suggestion_review=True,
        )
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
