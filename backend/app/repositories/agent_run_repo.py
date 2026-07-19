import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.agent_run import AgentRunRecord, AgentWorkItemRecord


class AgentRunRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_run(self, record: AgentRunRecord) -> str:
        run_id = record.id or f"agent_run_{uuid4().hex[:12]}"
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO agent_run
                   (id, workflow_id, agent_type, version_id, plan_revision, status, model_profile, budget, coverage)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, record.workflow_id, record.agent_type, record.version_id,
                 record.plan_revision, record.status, record.model_profile,
                 _dump(record.budget), _dump(record.coverage)),
            )
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with connect(self.settings) as connection:
            row = connection.execute("SELECT * FROM agent_run WHERE id = ?", (run_id,)).fetchone()
        return _decode(dict(row), "budget", "coverage") if row else None

    def update_run(self, run_id: str, *, status: str | None = None, coverage: dict | None = None) -> None:
        current = self.get_run(run_id)
        if current is None:
            return
        requested = status or current["status"]
        if current["status"] in {"completed", "completed_degraded", "failed", "cancelled"} and requested != current["status"]:
            requested = current["status"]
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE agent_run SET status = ?, coverage = ?, updated_time = CURRENT_TIMESTAMP WHERE id = ?",
                (requested, _dump(coverage if coverage is not None else current["coverage"]), run_id),
            )

    def list_runs_for_workflow(self, workflow_id: str) -> list[dict[str, Any]]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_run WHERE workflow_id=? ORDER BY created_time,id",
                (workflow_id,),
            ).fetchall()
        return [_decode(dict(row), "budget", "coverage") for row in rows]

    def list_runs_for_version(self, version_id: int) -> list[dict[str, Any]]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_run WHERE version_id=? ORDER BY created_time,id",
                (version_id,),
            ).fetchall()
        return [_decode(dict(row), "budget", "coverage") for row in rows]

    def upsert_work_item(
        self, run_id: str, subject_type: str, subject_id: str, input_payload: dict,
        *, max_attempts: int | None = None,
    ) -> str:
        with connect(self.settings) as connection:
            row = connection.execute(
                "SELECT id FROM agent_work_item WHERE run_id=? AND subject_type=? AND subject_id=?",
                (run_id, subject_type, str(subject_id)),
            ).fetchone()
            if row:
                return str(row["id"])
            item_id = f"work_item_{uuid4().hex[:12]}"
            connection.execute(
                """INSERT INTO agent_work_item
                   (id, run_id, subject_type, subject_id, max_attempts, input_payload)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (item_id, run_id, subject_type, str(subject_id),
                 max_attempts or self.settings.agent_work_item_max_attempts, _dump(input_payload)),
            )
        return item_id

    def get_work_item(self, item_id: str) -> AgentWorkItemRecord | None:
        with connect(self.settings) as connection:
            row = connection.execute("SELECT * FROM agent_work_item WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return None
        data = _decode(dict(row), "input_payload", "result_payload")
        return AgentWorkItemRecord.model_validate(data)

    def list_work_items(self, run_id: str) -> list[AgentWorkItemRecord]:
        with connect(self.settings) as connection:
            rows = connection.execute("SELECT * FROM agent_work_item WHERE run_id = ? ORDER BY created_time, id", (run_id,)).fetchall()
        return [AgentWorkItemRecord.model_validate(_decode(dict(row), "input_payload", "result_payload")) for row in rows]

    def claim_work_item(self, item_id: str, *, worker_id: str) -> bool:
        lease = (datetime.now(timezone.utc) + timedelta(seconds=self.settings.agent_lease_seconds)).isoformat()
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """UPDATE agent_work_item
                   SET status='running', worker_id=?, lease_expires_at=?, attempt=attempt+1,
                       updated_time=CURRENT_TIMESTAMP
                   WHERE id=? AND status IN ('pending','retryable_failed')
                     AND attempt < max_attempts
                     AND NOT EXISTS (SELECT 1 FROM agent_run r WHERE r.id=run_id AND r.status='cancelled')""",
                (worker_id, lease, item_id),
            )
        return cursor.rowcount == 1

    def reclaim_expired_leases(self, run_id: str) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """UPDATE agent_work_item SET status='retryable_failed', worker_id=NULL,
                       error_code='LEASE_EXPIRED', error_message='worker lease expired'
                   WHERE run_id=? AND status='running' AND lease_expires_at < ?""",
                (run_id, now),
            )
        return cursor.rowcount

    def complete_work_item(self, item_id: str, *, status: str, result_payload: dict | None = None) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE agent_work_item SET status=?, result_payload=?, error_code=NULL,
                       error_message=NULL, lease_expires_at=NULL, updated_time=CURRENT_TIMESTAMP WHERE id=?""",
                (status, _dump(result_payload or {}), item_id),
            )

    def skip_work_item(self, item_id: str, *, reason: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE agent_work_item SET status='skipped',error_code='BUDGET_EXHAUSTED',
                       error_message=?,lease_expires_at=NULL,updated_time=CURRENT_TIMESTAMP WHERE id=?""",
                (reason, item_id),
            )

    def fail_work_item(self, item_id: str, *, retryable: bool, error_code: str, error_message: str) -> str:
        item = self.get_work_item(item_id)
        if item is None:
            raise ValueError("work item not found")
        status = "retryable_failed" if retryable and item.attempt < item.max_attempts else "permanent_failed"
        final_code = "MAX_ATTEMPTS_EXHAUSTED" if status == "permanent_failed" and retryable else error_code
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE agent_work_item SET status=?, error_code=?, error_message=?,
                       lease_expires_at=NULL, updated_time=CURRENT_TIMESTAMP WHERE id=?""",
                (status, final_code, error_message, item_id),
            )
        return status

    def is_runnable(self, item_id: str) -> bool:
        item = self.get_work_item(item_id)
        return bool(item and item.status in {"pending", "retryable_failed"} and item.attempt < item.max_attempts)

    def counts(self, run_id: str) -> dict[str, int]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) count FROM agent_work_item WHERE run_id=? GROUP BY status", (run_id,),
            ).fetchall()
        result = {str(row["status"]): int(row["count"]) for row in rows}
        result["total"] = sum(result.values())
        return result

    def usage_totals(self, run_id: str) -> dict[str, int]:
        calls = tokens = 0
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT token_usage,summary FROM agent_event WHERE run_id=?",
                (run_id,),
            ).fetchall()
        for row in rows:
            usage = _decode({"value": row["token_usage"]}, "value").get("value") or {}
            summary = _decode({"value": row["summary"]}, "value").get("value") or {}
            calls += int(summary.get("model_calls", 0) or 0)
            tokens += int(usage.get("total_tokens", 0) or 0)
        return {"model_calls": calls, "tokens_used": tokens}

    def record_event(self, *, workflow_id: str, event_type: str, run_id: str | None = None,
                     work_item_id: str | None = None, agent_name: str | None = None,
                     phase: str | None = None, tool_name: str | None = None,
                     status: str | None = None, attempt: int | None = None,
                     latency_ms: int | None = None, model: str | None = None,
                     token_usage: dict | None = None, summary: dict | None = None,
                     evidence_refs: list | None = None) -> int:
        safe_summary = _redact(summary or {})
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """INSERT INTO agent_event
                   (workflow_id, run_id, work_item_id, agent_name, event_type, phase,
                    tool_name, status, attempt, latency_ms, model, token_usage, summary, evidence_refs)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, run_id, work_item_id, agent_name, event_type, phase, tool_name,
                 status, attempt, latency_ms, model, _dump(token_usage or {}),
                 _dump(safe_summary), _dump(evidence_refs or [])),
            )
            connection.execute(
                """INSERT INTO workflow_event
                   (workflow_id, thread_id, node_name, event_type, status, message, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (workflow_id, workflow_id, agent_name, event_type, status,
                 str(safe_summary.get("decision") or safe_summary.get("error_code") or ""),
                 _dump({"run_id": run_id, "work_item_id": work_item_id,
                        "phase": phase, "tool_name": tool_name, "attempt": attempt,
                        "latency_ms": latency_ms, "model": model,
                        "summary": safe_summary, "evidence_refs": evidence_refs or []})),
            )
            return int(cursor.lastrowid)

    def list_events(self, workflow_id: str, *, after_id: int = 0, limit: int = 200) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT * FROM agent_event WHERE workflow_id=? AND id>? ORDER BY id LIMIT ?",
                (workflow_id, after_id, limit),
            ).fetchall()
        return [_decode(dict(row), "token_usage", "summary", "evidence_refs") for row in rows]

    def cancel_workflow(self, workflow_id: str) -> int:
        with connect(self.settings) as connection:
            runs = connection.execute("SELECT id FROM agent_run WHERE workflow_id=?", (workflow_id,)).fetchall()
            connection.execute("UPDATE agent_run SET status='cancelled', updated_time=CURRENT_TIMESTAMP WHERE workflow_id=? AND status NOT IN ('completed','failed','cancelled')", (workflow_id,))
            for row in runs:
                connection.execute("UPDATE agent_work_item SET status='cancelled', updated_time=CURRENT_TIMESTAMP WHERE run_id=? AND status IN ('pending','retryable_failed')", (row["id"],))
        return len(runs)

    def recover_expired_work(self) -> int:
        with connect(self.settings) as connection:
            rows = connection.execute("SELECT id FROM agent_run WHERE status='running'").fetchall()
        return sum(self.reclaim_expired_leases(str(row["id"])) for row in rows)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _decode(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str):
            try:
                row[key] = json.loads(value)
            except ValueError:
                row[key] = {} if key != "evidence_refs" else []
    return row


def _redact(value: Any) -> Any:
    blocked = {"api_key", "raw_prompt", "chain_of_thought", "thought"}
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items() if key.lower() not in blocked}
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:2000]
    return value
