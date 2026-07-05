from collections.abc import Iterable

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.issue import DiagnosisIssueRecord


class DiagnosisRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def replace_issues(
        self,
        *,
        version_id: int,
        issues: Iterable[DiagnosisIssueRecord],
    ) -> None:
        values = [
            (
                version_id,
                issue.issue_type,
                issue.node_id,
                issue.node_name,
                issue.description,
                issue.reason,
                issue.risk_level,
                issue.confidence,
                issue.status,
            )
            for issue in issues
        ]
        with connect(self.settings) as connection:
            connection.execute(
                "DELETE FROM diagnosis_issue WHERE version_id = ?",
                (version_id,),
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO diagnosis_issue (
                    version_id, issue_type, node_id, node_name, description,
                    reason, risk_level, confidence, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def create_issue(
        self,
        *,
        version_id: int,
        issue: DiagnosisIssueRecord,
    ) -> int:
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO diagnosis_issue (
                    version_id, issue_type, node_id, node_name, description,
                    reason, risk_level, confidence, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    issue.issue_type,
                    issue.node_id,
                    issue.node_name,
                    issue.description,
                    issue.reason,
                    issue.risk_level,
                    issue.confidence,
                    issue.status,
                ),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            row = connection.execute(
                """
                SELECT id
                FROM diagnosis_issue
                WHERE version_id = ?
                  AND issue_type = ?
                  AND IFNULL(node_id, -1) = IFNULL(?, -1)
                  AND description = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (version_id, issue.issue_type, issue.node_id, issue.description),
            ).fetchone()
            return int(row["id"]) if row else 0

    def count_by_type(self, version_id: int) -> dict[str, int]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT issue_type, COUNT(*) AS issue_count
                FROM diagnosis_issue
                WHERE version_id = ?
                GROUP BY issue_type
                ORDER BY issue_type
                """,
                (version_id,),
            ).fetchall()
        return {row["issue_type"]: int(row["issue_count"]) for row in rows}

    def list_examples(self, version_id: int, limit: int = 5) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT issue_type, node_id, node_name, description, reason,
                       risk_level, confidence
                FROM diagnosis_issue
                WHERE version_id = ?
                ORDER BY
                    CASE risk_level
                        WHEN 'high' THEN 0
                        WHEN 'medium' THEN 1
                        ELSE 2
                    END,
                    confidence DESC,
                    id ASC
                LIMIT ?
                """,
                (version_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
