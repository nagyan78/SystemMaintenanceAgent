import asyncio
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic import Field

from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    create_thread_id,
    create_workflow_id,
)
from backend.app.repositories.file_repo import FileRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.db import connect
from backend.app.services.workflow_runner import WorkflowRunner


router = APIRouter(prefix="/workflows", tags=["workflows"])
_WORKFLOW_CHECKPOINTER = None


class StartWorkflowRequest(BaseModel):
    file_id: int
    enable_ai_analysis: bool = False
    model_provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    priority_subtree_ids: list[int] = Field(default_factory=list)
    sample_strategy: Literal["focused", "full_scan", "sampling"] = "sampling"
    focus_issues: list[str] = Field(default_factory=list)
    ai_candidate_limit: int | None = Field(default=None, ge=1, le=1000)
    ai_max_model_calls: int | None = Field(default=None, ge=1, le=10000)
    ai_token_budget: int | None = Field(default=None, ge=1)
    ai_wall_seconds: int | None = Field(default=None, ge=1, le=86400)


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


@router.get("")
def list_workflows(
    request: Request,
    file_id: int | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
) -> list[dict[str, Any]]:
    rows = TaskRepository(request.app.state.settings).list_tasks(file_id=file_id, status=task_status)
    for row in rows:
        row.pop("result_payload", None)
    return rows


@router.post("/taxonomy/start", response_model=StartWorkflowResponse)
def start_taxonomy_workflow(
    payload: StartWorkflowRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> StartWorkflowResponse:
    settings = request.app.state.settings
    if payload.model_provider != "deepseek" or payload.model_name != "deepseek-chat":
        raise HTTPException(status_code=400, detail="Only deepseek/deepseek-chat is supported.")
    if FileRepository(settings).get_file(payload.file_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    workflow_id = create_workflow_id(payload.file_id)
    thread_id = create_thread_id(workflow_id)
    task_repo = TaskRepository(settings)
    task_id = task_repo.create_workflow_task(
        file_id=payload.file_id,
        workflow_id=workflow_id,
        thread_id=thread_id,
        enable_ai_analysis=payload.enable_ai_analysis,
        model_provider=payload.model_provider if payload.enable_ai_analysis else None,
        model_name=payload.model_name if payload.enable_ai_analysis else None,
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
    WorkflowRunner(settings).submit(
        background_tasks,
        _run_workflow,
        settings,
        payload.file_id,
        task_id,
        workflow_id,
        payload.model_dump(),
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
    progress = 100 if task["status"] in {"completed", "partial", "completed_degraded"} else task["progress"]
    return {
        "task_id": task["id"],
        "status": task["status"],
        "current_step": task["current_step"],
        "progress": progress,
        "file_id": task["file_id"],
        "current_version_id": task["version_id"],
        "version_no": payload.get("version_no"),
        "node_count": payload.get("node_count", 0),
        "structure_issue_count": payload.get("structure_issue_count", 0),
        "suggestion_count": payload.get("suggestion_count", 0),
        "review_batch_id": payload.get("review_batch_id"),
        "report_path": payload.get("report_path"),
        "export_path": payload.get("export_path"),
        "verification_status": payload.get("verification_status"),
        "quality_before": payload.get("quality_before"),
        "quality_after": payload.get("quality_after"),
        "quality_delta": payload.get("quality_delta"),
        "remaining_issue_count": payload.get("remaining_issue_count", 0),
        "report_preview_url": (
            f"/api/reports/{task['version_id']}/preview?report_type={'draft' if task['status'] == 'waiting_review' else 'final'}"
            if task.get("version_id") and payload.get("report_path")
            else None
        ),
        "report_download_url": (
            f"/api/reports/{task['version_id']}/download?report_type={'draft' if task['status'] == 'waiting_review' else 'final'}"
            if task.get("version_id") and payload.get("report_path")
            else None
        ),
        "error_message": task.get("error_message") or payload.get("error_message"),
        "enable_ai_analysis": bool(task.get("enable_ai_analysis")),
        "model_provider": task.get("model_provider"),
        "model_name": task.get("model_name"),
        "start_time": task.get("start_time") or task.get("created_time"),
        "end_time": task.get("end_time"),
        "analysis_run_id": payload.get("analysis_run_id"),
        "work_item_counts": payload.get("work_item_counts", {}),
        "plan_revision": payload.get("plan_revision", 1),
        "plan_decision": payload.get("plan_decision", "initial"),
        "stop_reason": payload.get("stop_reason"),
        "model_calls_used": payload.get("model_calls_used", 0),
        "tokens_used": payload.get("tokens_used", 0),
        "wall_seconds_used": payload.get("wall_seconds_used", 0),
        "triage_count": payload.get("triage_count", 0),
        "candidate_count": payload.get("candidate_count", 0),
        "ai_processed_count": payload.get("ai_processed_count", 0),
        "coverage": payload.get("coverage", {}),
        "diagnosis_completion_status": payload.get("diagnosis_completion_status", "completed"),
        "report_type": payload.get("report_type"),
    }


@router.get("/{task_id}/evidence")
def get_workflow_evidence(task_id: str, request: Request) -> dict[str, Any]:
    """Return the complete persisted evidence graph for one business run."""
    settings = request.app.state.settings
    task = TaskRepository(settings).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")
    workflow_id = str(task.get("workflow_id") or task_id)
    runs = AgentRunRepository(settings).list_runs_for_workflow(workflow_id)
    run_ids = [str(item["id"]) for item in runs]
    with connect(settings) as connection:
        if run_ids:
            marks = ",".join("?" for _ in run_ids)
            issue_rows = connection.execute(
                f"""SELECT DISTINCT issue.* FROM diagnosis_issue issue
                    JOIN run_issue link ON link.issue_id=issue.id
                    WHERE link.run_id IN ({marks}) ORDER BY issue.id""",
                run_ids,
            ).fetchall()
        else:
            issue_rows = []
        batch_rows = connection.execute(
            "SELECT * FROM review_batch WHERE task_id=? OR workflow_id=? ORDER BY created_time,id",
            (task_id, workflow_id),
        ).fetchall()
        batch_ids = [str(row["id"]) for row in batch_rows]
        if batch_ids:
            marks = ",".join("?" for _ in batch_ids)
            suggestion_rows = connection.execute(
                f"SELECT * FROM adjustment_suggestion WHERE review_batch_id IN ({marks}) ORDER BY id",
                batch_ids,
            ).fetchall()
            execution_rows = connection.execute(
                f"SELECT * FROM version_execution_record WHERE review_batch_id IN ({marks}) ORDER BY id",
                batch_ids,
            ).fetchall()
        else:
            suggestion_rows = []
            execution_rows = []
        version_rows = connection.execute(
            """SELECT * FROM taxonomy_version
               WHERE id=? OR source_workflow_id=? OR parent_version_id=? ORDER BY id""",
            (task.get("version_id"), workflow_id, task.get("version_id")),
        ).fetchall()
        version_ids = [int(row["id"]) for row in version_rows]
        if version_ids:
            marks = ",".join("?" for _ in version_ids)
            report_rows = connection.execute(
                f"SELECT * FROM report_artifact WHERE version_id IN ({marks}) OR workflow_id=? ORDER BY id",
                [*version_ids, workflow_id],
            ).fetchall()
        else:
            report_rows = connection.execute(
                "SELECT * FROM report_artifact WHERE workflow_id=? ORDER BY id", (workflow_id,)
            ).fetchall()
    return {
        "task": task,
        "workflow_id": workflow_id,
        "input_version_id": min(version_ids) if version_ids else task.get("version_id"),
        "output_version_id": max(version_ids) if len(version_ids) > 1 else None,
        "runs": runs,
        "issues": [dict(row) for row in issue_rows],
        "suggestions": [dict(row) for row in suggestion_rows],
        "review_batches": [dict(row) for row in batch_rows],
        "executions": [dict(row) for row in execution_rows],
        "versions": [dict(row) for row in version_rows],
        "reports": [dict(row) for row in report_rows],
    }


@router.get("/{task_id}/events")
def workflow_events(
    task_id: str, request: Request,
    after_id: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
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

        try:
            header_cursor = int(last_event_id) if last_event_id else 0
        except ValueError:
            header_cursor = 0
        last_id = max(after_id, header_cursor)
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
            if task_status == "waiting_review":
                yield format_sse(interrupt_event(current.get("interrupt_payload") or current.get("result_payload")))
                seen_terminal = True
            elif task_status in {"completed", "partial", "completed_degraded"}:
                yield format_sse(completed_event(task_id, current.get("result_payload")))
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
    request: Request,
) -> dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="人工审核恢复接口已停用；新任务由独立 AI 复核并自动执行。",
    )


@router.post("/{task_id}/cancel")
def cancel_workflow(task_id: str, request: Request) -> dict[str, Any]:
    try:
        return WorkflowRunner(request.app.state.settings).cancel(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def _run_workflow(
    settings,
    file_id: int,
    task_id: str,
    workflow_id: str,
    options: dict[str, Any] | None = None,
) -> None:
    options = options or {}
    runtime_settings = settings
    if options.get("enable_ai_analysis"):
        runtime_settings = settings.model_copy(
            update={
                "llm_max_calls": options.get("ai_max_model_calls") or settings.llm_max_calls,
                "llm_max_tokens": options.get("ai_token_budget") or settings.llm_max_tokens,
                "diagnosis_ai_wall_seconds": options.get("ai_wall_seconds") or settings.diagnosis_ai_wall_seconds,
            }
        )
    state = create_initial_state(
        file_id=file_id,
        task_id=task_id,
        workflow_id=workflow_id,
        enable_ai_analysis=bool(options.get("enable_ai_analysis")),
        model_provider=(options.get("model_provider") if options.get("enable_ai_analysis") else None),
        model_name=(options.get("model_name") if options.get("enable_ai_analysis") else None),
        priority_subtree_ids=options.get("priority_subtree_ids") or [],
        sample_strategy=options.get("sample_strategy") or "sampling",
        focus_issues=options.get("focus_issues") or [],
        ai_candidate_limit=options.get("ai_candidate_limit"),
        ai_max_model_calls=options.get("ai_max_model_calls"),
        ai_token_budget=options.get("ai_token_budget"),
        ai_wall_seconds=options.get("ai_wall_seconds"),
    )
    task_repo = TaskRepository(settings)
    try:
        graph = build_taxonomy_graph(_get_workflow_checkpointer(), settings=runtime_settings)
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
