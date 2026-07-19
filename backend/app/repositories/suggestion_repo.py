import json
from typing import Any

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.suggestion import AdjustmentSuggestion, SuggestionRecord


class SuggestionRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_suggestion(
        self,
        *,
        review_batch_id: str,
        suggestion: AdjustmentSuggestion,
        work_item_id: str | None = None,
        analysis_run_id: str | None = None,
        workflow_id: str | None = None,
    ) -> int:
        with connect(self.settings) as connection:
            if work_item_id:
                existing = connection.execute(
                    "SELECT id FROM adjustment_suggestion WHERE work_item_id = ? AND issue_id = ?",
                    (work_item_id, suggestion.issue_id),
                ).fetchone()
                if existing:
                    return int(existing["id"])
            action_payload = dict(suggestion.action_payload)
            if work_item_id:
                action_payload["work_item_id"] = work_item_id
            if analysis_run_id:
                action_payload["analysis_run_id"] = analysis_run_id
            cursor = connection.execute(
                """
                INSERT INTO adjustment_suggestion (
                    issue_id, review_batch_id, version_id, action_type, target_node_id,
                    target_node_name, old_parent_id, new_parent_id, old_name, new_name,
                    action_payload, reason, suggestion, risk_level, confidence,
                    need_confirm, status, work_item_id, analysis_run_id, workflow_id,
                    change_preview, consistency_status, consistency_reason, is_manual
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.issue_id,
                    review_batch_id,
                    suggestion.version_id,
                    suggestion.action_type,
                    suggestion.target_node_id,
                    suggestion.target_node_name,
                    suggestion.old_parent_id,
                    suggestion.new_parent_id,
                    suggestion.old_name,
                    suggestion.new_name,
                    json.dumps(action_payload, ensure_ascii=False),
                    suggestion.reason,
                    suggestion.suggestion,
                    suggestion.risk_level,
                    suggestion.confidence,
                    int(suggestion.need_confirm),
                    suggestion.status,
                    work_item_id,
                    analysis_run_id,
                    workflow_id,
                    json.dumps({}, ensure_ascii=False),
                    "unchecked",
                    None,
                    0,
                ),
            )
            return int(cursor.lastrowid)

    def list_suggestions(
        self,
        *,
        version_id: int | None = None,
        status: str | None = None,
        review_batch_id: str | None = None,
    ) -> list[SuggestionRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if version_id is not None:
            clauses.append("version_id = ?")
            params.append(version_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if review_batch_id is not None:
            clauses.append("review_batch_id = ?")
            params.append(review_batch_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, issue_id, review_batch_id, version_id, action_type,
                       target_node_id, target_node_name, old_parent_id, new_parent_id,
                       old_name, new_name, action_payload, reason, suggestion,
                       risk_level, confidence, need_confirm, status,
                       work_item_id, analysis_run_id, change_preview,
                       consistency_status, consistency_reason, is_manual,
                       regenerated_at, generator_version
                FROM adjustment_suggestion
                {where}
                ORDER BY id
                """,
                params,
            ).fetchall()
        return [_record_from_row(dict(row)) for row in rows]

    def get_suggestion(self, suggestion_id: int) -> SuggestionRecord | None:
        suggestions = self._query_by_ids([suggestion_id])
        return suggestions[0] if suggestions else None

    def list_by_ids(self, suggestion_ids: list[int]) -> list[SuggestionRecord]:
        if not suggestion_ids:
            return []
        return self._query_by_ids(suggestion_ids)

    def update_status(self, suggestion_id: int, status: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE adjustment_suggestion SET status = ? WHERE id = ?",
                (status, suggestion_id),
            )
            self._invalidate_preview(connection, suggestion_id)

    def update_consistency(self, suggestion_id: int, *, suggestion: AdjustmentSuggestion,
                           change_preview: dict[str, Any], status: str, reason: str | None) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE adjustment_suggestion SET action_type=?, target_node_id=?, target_node_name=?,
                   old_parent_id=?, new_parent_id=?, old_name=?, new_name=?, action_payload=?,
                   suggestion=?, change_preview=?, consistency_status=?, consistency_reason=? WHERE id=?""",
                (suggestion.action_type, suggestion.target_node_id, suggestion.target_node_name,
                 suggestion.old_parent_id, suggestion.new_parent_id, suggestion.old_name, suggestion.new_name,
                 json.dumps(suggestion.action_payload, ensure_ascii=False), suggestion.suggestion,
                 json.dumps(change_preview, ensure_ascii=False), status, reason, suggestion_id),
            )

    def regenerate(self, suggestion_id: int, *, suggestion: AdjustmentSuggestion,
                   change_preview: dict[str, Any], consistency_status: str,
                   consistency_reason: str | None, preserve_status: bool,
                   generator_version: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """UPDATE adjustment_suggestion SET action_type=?,target_node_id=?,target_node_name=?,
                   old_parent_id=?,new_parent_id=?,old_name=?,new_name=?,action_payload=?,reason=?,suggestion=?,
                   risk_level=?,confidence=?,need_confirm=?,change_preview=?,consistency_status=?,
                   consistency_reason=?,status=CASE WHEN ? THEN status ELSE 'pending' END,
                   regenerated_at=CURRENT_TIMESTAMP,generator_version=? WHERE id=?""",
                (suggestion.action_type, suggestion.target_node_id, suggestion.target_node_name,
                 suggestion.old_parent_id, suggestion.new_parent_id, suggestion.old_name, suggestion.new_name,
                 json.dumps(suggestion.action_payload, ensure_ascii=False), suggestion.reason, suggestion.suggestion,
                 suggestion.risk_level, suggestion.confidence, int(suggestion.need_confirm),
                 json.dumps(change_preview, ensure_ascii=False), consistency_status, consistency_reason,
                 int(preserve_status), generator_version, suggestion_id),
            )
            self._invalidate_preview(connection, suggestion_id)

    def mark_manual(self, suggestion_id: int) -> None:
        with connect(self.settings) as connection:
            connection.execute("UPDATE adjustment_suggestion SET is_manual=1 WHERE id=?", (suggestion_id,))

    def update_suggestion(self, suggestion_id: int, suggestion: AdjustmentSuggestion) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """
                UPDATE adjustment_suggestion
                SET action_type = ?, target_node_id = ?, target_node_name = ?,
                    old_parent_id = ?, new_parent_id = ?, old_name = ?, new_name = ?,
                    action_payload = ?, reason = ?, suggestion = ?, risk_level = ?,
                    confidence = ?, need_confirm = ?, status = 'edited'
                WHERE id = ?
                """,
                (
                    suggestion.action_type,
                    suggestion.target_node_id,
                    suggestion.target_node_name,
                    suggestion.old_parent_id,
                    suggestion.new_parent_id,
                    suggestion.old_name,
                    suggestion.new_name,
                    json.dumps(suggestion.action_payload, ensure_ascii=False),
                    suggestion.reason,
                    suggestion.suggestion,
                    suggestion.risk_level,
                    suggestion.confidence,
                    int(suggestion.need_confirm),
                    suggestion_id,
                ),
            )
            self._invalidate_preview(connection, suggestion_id)

    def _query_by_ids(self, suggestion_ids: list[int]) -> list[SuggestionRecord]:
        placeholders = ",".join("?" for _ in suggestion_ids)
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, issue_id, review_batch_id, version_id, action_type,
                       target_node_id, target_node_name, old_parent_id, new_parent_id,
                       old_name, new_name, action_payload, reason, suggestion,
                       risk_level, confidence, need_confirm, status,
                       work_item_id, analysis_run_id, change_preview,
                       consistency_status, consistency_reason, is_manual,
                       regenerated_at, generator_version
                FROM adjustment_suggestion
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                suggestion_ids,
            ).fetchall()
        return [_record_from_row(dict(row)) for row in rows]

    @staticmethod
    def _invalidate_preview(connection, suggestion_id: int) -> None:
        connection.execute(
            """UPDATE review_batch SET
               status=CASE WHEN status='preview_ready' THEN 'reviewed' ELSE status END,
               workflow_state=CASE WHEN status IN ('reviewed','preview_ready') THEN 'review_completed' ELSE 'reviewing' END,
               execution_status=CASE WHEN preview_hash IS NOT NULL THEN 'stale' ELSE 'blocked' END,
               updated_time=CURRENT_TIMESTAMP WHERE id=(SELECT review_batch_id FROM adjustment_suggestion WHERE id=?)""",
            (suggestion_id,),
        )


def _record_from_row(row: dict[str, Any]) -> SuggestionRecord:
    payload = row.get("action_payload")
    row["action_payload"] = json.loads(payload) if payload else {}
    preview = row.get("change_preview")
    row["change_preview"] = json.loads(preview) if preview else {}
    row["need_confirm"] = bool(row.get("need_confirm"))
    row["is_manual"] = bool(row.get("is_manual"))
    return SuggestionRecord.model_validate(row)
