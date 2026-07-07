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

    def list_pending_issues(self, version_id: int, limit: int | None = None) -> list[dict]:
        query = """
            SELECT id, version_id, issue_type, node_id, node_name, description,
                   reason, risk_level, confidence, status
            FROM diagnosis_issue
            WHERE version_id = ? AND status = 'pending'
            ORDER BY
                CASE risk_level
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    ELSE 2
                END,
                confidence DESC,
                id ASC
        """
        params: tuple[object, ...] = (version_id,)
        if limit is not None:
            query += " LIMIT ?"
            params = (version_id, limit)
        with connect(self.settings) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_open_issues(self, version_id: int, limit: int | None = None) -> list[dict]:
        return self.list_pending_issues(version_id, limit=limit)

    _STRUCTURE_TYPES = {"missing_parent", "deep_level", "wide_node", "duplicate_name", "orphan"}

    def count_content_issues(self, version_id: int) -> int:
        with connect(self.settings) as connection:
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS cnt FROM diagnosis_issue
                WHERE version_id = ?
                  AND issue_type NOT IN ({','.join('?' * len(self._STRUCTURE_TYPES))})
                """,
                (version_id, *self._STRUCTURE_TYPES),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def list_content_examples(self, version_id: int, limit: int = 3) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT issue_type, node_id, node_name, description, reason,
                       risk_level, confidence
                FROM diagnosis_issue
                WHERE version_id = ?
                  AND issue_type NOT IN ({','.join('?' * len(self._STRUCTURE_TYPES))})
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
                (version_id, *self._STRUCTURE_TYPES, limit),
            ).fetchall()
        return [dict(row) for row in rows]
