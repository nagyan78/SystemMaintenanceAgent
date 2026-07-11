"""Streaming-event mapping for the M5 SSE endpoint.

M5 requires the frontend to consume *real* workflow events over SSE
(``GET /api/workflows/{task_id}/events``) instead of polling a static
progress value. The nodes already record every step into the
``workflow_event`` table via :class:`TaskRepository`; this module turns those
rows into the SSE event shapes described in ``dev-doc/00_开发里程碑索引.md`` §8.5.
"""

from __future__ import annotations

import json
from typing import Any

# SSE event names (must match the M5 contract in dev-doc §8.5).
EVENT_STEP = "workflow_step"
EVENT_INTERRUPT = "workflow_interrupt"
EVENT_THOUGHT = "agent_thought"
EVENT_COMPLETED = "workflow_completed"
EVENT_FAILED = "workflow_failed"


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def map_workflow_event(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map a ``workflow_event`` row to an SSE event dict (or ``None``)."""
    event_type = row.get("event_type")
    payload = _loads(row.get("payload"))

    if event_type in {"agent_step", "agent_tool_completed", "candidate_completed", "issue_completed"}:
        return {
            "id": row.get("id"),
            "event": event_type,
            "data": {
                "event_id": row.get("id"), "agent_name": row.get("node_name"),
                "status": row.get("status"), **payload,
            },
        }

    if event_type == "node_completed":
        current_step = payload.get("current_step") or row.get("node_name")
        return {
            "id": row.get("id"),
            "event": EVENT_STEP,
            "data": {
                "node": row.get("node_name"),
                "current_step": current_step,
                "status": row.get("status"),
                "progress": row.get("progress"),
                "message": row.get("message"),
            },
        }

    if event_type == "node_failed":
        return {
            "id": row.get("id"),
            "event": EVENT_STEP,
            "data": {
                "node": row.get("node_name"),
                "current_step": payload.get("current_step") or row.get("node_name"),
                "status": "failed",
                "progress": row.get("progress"),
                "message": row.get("message") or "node failed",
            },
        }

    if event_type == "workflow_failed":
        return {
            "id": row.get("id"),
            "event": EVENT_FAILED,
            "data": {
                "message": row.get("message") or "workflow failed",
            },
        }

    # workflow_started and any other informational rows -> a step heartbeat.
    return {
        "id": row.get("id"),
        "event": EVENT_STEP,
        "data": {
            "node": row.get("node_name"),
            "current_step": payload.get("current_step"),
            "status": row.get("status"),
            "progress": row.get("progress"),
            "message": row.get("message"),
        },
    }


def interrupt_event(interrupt_payload: str | None) -> dict[str, Any]:
    """Build the ``workflow_interrupt`` SSE event from a task's payload."""
    payload = _loads(interrupt_payload)
    return {
        "event": EVENT_INTERRUPT,
        "data": {
            "type": payload.get("type", "human_review"),
            "review_batch_id": payload.get("review_batch_id"),
            "suggestion_count": payload.get("suggestion_count"),
            "required_actions": payload.get("required_actions", ["approve", "reject", "edit"]),
        },
    }


def completed_event(task_id: str, result_payload: str | None) -> dict[str, Any]:
    payload = _loads(result_payload)
    return {
        "event": EVENT_COMPLETED,
        "data": {
            "task_id": task_id,
            "current_version_id": payload.get("current_version_id"),
            "new_version_id": payload.get("new_version_id"),
            "report_path": payload.get("report_path"),
        },
    }


def format_sse(event: dict[str, Any]) -> str:
    """Serialize an event dict into an SSE frame."""
    name = event.get("event", EVENT_STEP)
    data = json.dumps(event.get("data", {}), ensure_ascii=False)
    event_id = event.get("id")
    id_line = f"id: {event_id}\n" if event_id is not None else ""
    return f"{id_line}event: {name}\ndata: {data}\n\n"
