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
        workflow_id: str | None = None,
        analysis_run_id: str | None = None,
        suggestion: AdjustmentSuggestion,
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT INTO adjustment_suggestion (
                    issue_id, workflow_id, analysis_run_id,
                    version_id, action_type, target_node_id,
                    target_node_name, old_parent_id, new_parent_id, old_name, new_name,
                    action_payload, reason, suggestion, risk_level, confidence,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    suggestion.issue_id,
                    workflow_id,
                    analysis_run_id,
                    suggestion.version_id,
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
                    suggestion.status,
                ),
            )
            return int(cursor.lastrowid)

    def list_suggestions(
        self,
        *,
        version_id: int | None = None,
        status: str | None = None,
    ) -> list[SuggestionRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if version_id is not None:
            clauses.append("version_id = ?")
            params.append(version_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, issue_id, version_id, action_type,
                       target_node_id, target_node_name, old_parent_id, new_parent_id,
                       old_name, new_name, action_payload, reason, suggestion,
                       risk_level, confidence, status
                FROM adjustment_suggestion
                {where}
                ORDER BY id
                """,
                params,
            ).fetchall()
        return [_record_from_row(dict(row)) for row in rows]

    def list_for_run(self, analysis_run_id: str) -> list[SuggestionRecord]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, issue_id, version_id, action_type,
                       target_node_id, target_node_name, old_parent_id, new_parent_id,
                       old_name, new_name, action_payload, reason, suggestion,
                       risk_level, confidence, status
                FROM adjustment_suggestion
                WHERE analysis_run_id = ?
                ORDER BY id
                """,
                (analysis_run_id,),
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

    def record_decision_reason(self, suggestion_id: int, reason: str) -> None:
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion is None:
            return
        payload = {
            **suggestion.action_payload,
            "automatic_decision_reason": reason,
        }
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE adjustment_suggestion SET action_payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), suggestion_id),
            )

    def update_suggestion(self, suggestion_id: int, suggestion: AdjustmentSuggestion) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """
                UPDATE adjustment_suggestion
                SET action_type = ?, target_node_id = ?, target_node_name = ?,
                    old_parent_id = ?, new_parent_id = ?, old_name = ?, new_name = ?,
                    action_payload = ?, reason = ?, suggestion = ?, risk_level = ?,
                    confidence = ?, status = 'pending'
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
                    suggestion_id,
                ),
            )

    def _query_by_ids(self, suggestion_ids: list[int]) -> list[SuggestionRecord]:
        placeholders = ",".join("?" for _ in suggestion_ids)
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, issue_id, version_id, action_type,
                       target_node_id, target_node_name, old_parent_id, new_parent_id,
                       old_name, new_name, action_payload, reason, suggestion,
                       risk_level, confidence, status
                FROM adjustment_suggestion
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                suggestion_ids,
            ).fetchall()
        return [_record_from_row(dict(row)) for row in rows]


def _record_from_row(row: dict[str, Any]) -> SuggestionRecord:
    payload = row.get("action_payload")
    row["action_payload"] = json.loads(payload) if payload else {}
    return SuggestionRecord.model_validate(row)
