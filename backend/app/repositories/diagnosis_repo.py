from collections.abc import Iterable

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.domain.issue_types import issue_type_metadata, legacy_values_for
from backend.app.schemas.issue import DiagnosisIssueRecord


class DiagnosisRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def replace_issues(
        self,
        *,
        version_id: int,
        issues: Iterable[DiagnosisIssueRecord],
        issue_types: Iterable[str] | None = None,
    ) -> None:
        issue_list = list(issues)
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
                issue.path,
                issue.evidence,
                issue.source,
                issue.subject_node_id or issue.node_id,
                issue.subject_node_name or issue.node_name,
                issue.subject_path or issue.path,
            )
            for issue in issue_list
        ]
        managed_types = sorted(set(issue_types or (issue.issue_type for issue in issue_list)))
        with connect(self.settings) as connection:
            if managed_types:
                placeholders = ",".join("?" for _ in managed_types)
                connection.execute(
                    f"""
                    DELETE FROM diagnosis_issue
                    WHERE version_id = ?
                      AND issue_type IN ({placeholders})
                      AND NOT EXISTS (
                          SELECT 1
                          FROM adjustment_suggestion
                          WHERE adjustment_suggestion.issue_id = diagnosis_issue.id
                      )
                    """,
                    (version_id, *managed_types),
                )
            connection.executemany(
                """
                INSERT OR IGNORE INTO diagnosis_issue (
                    version_id, issue_type, node_id, node_name, description,
                    reason, risk_level, confidence, status, path, evidence, source,
                    subject_node_id, subject_node_name, subject_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    reason, risk_level, confidence, status, path, evidence, source,
                    subject_node_id, subject_node_name, subject_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    issue.path,
                    issue.evidence,
                    issue.source,
                    issue.subject_node_id or issue.node_id,
                    issue.subject_node_name or issue.node_name,
                    issue.subject_path or issue.path,
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
                   reason, risk_level, confidence, status, path, evidence, source,
                   COALESCE(subject_node_id,node_id) subject_node_id,
                   COALESCE(subject_node_name,node_name) subject_node_name,
                   COALESCE(subject_path,path) subject_path
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

    def list_issues(
        self,
        version_id: int,
        *,
        issue_type: str | None = None,
        risk_level: str | None = None,
    ) -> list[dict]:
        clauses = ["issue.version_id = ?"]
        params: list[object] = [version_id]
        if issue_type:
            values = legacy_values_for(issue_type)
            clauses.append(f"issue.issue_type IN ({','.join('?' for _ in values)})")
            params.extend(values)
        if risk_level:
            clauses.append("issue.risk_level = ?")
            params.append(risk_level)
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT issue.id, issue.version_id, issue.issue_type, issue.node_id,
                       issue.node_name, COALESCE(issue.path, node.path_names) AS path,
                       issue.description, issue.reason,
                       COALESCE(issue.evidence, issue.description) AS evidence,
                       issue.risk_level, issue.confidence,
                       COALESCE(issue.source, 'structure_rule') AS source,
                       issue.status, COALESCE(issue.subject_node_id,issue.node_id) subject_node_id,
                       COALESCE(issue.subject_node_name,issue.node_name) subject_node_name,
                       COALESCE(issue.subject_path,issue.path,node.path_names) subject_path
                FROM diagnosis_issue issue
                LEFT JOIN category_node node
                  ON node.version_id = issue.version_id
                 AND node.category_id = issue.node_id
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE issue.risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                         issue.confidence DESC, issue.id
                """,
                params,
            ).fetchall()
        return [
            {**_with_issue_type_metadata(dict(row)), "run_ids": self.list_run_ids(int(row["id"]))}
            for row in rows
        ]

    def get_issue_detail(self, issue_id: int) -> dict | None:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT issue.id, issue.version_id, issue.issue_type, issue.node_id,
                       issue.node_name, COALESCE(issue.path, node.path_names) AS path,
                       issue.description, issue.reason,
                       COALESCE(issue.evidence, issue.description) AS evidence,
                       issue.risk_level, issue.confidence,
                       COALESCE(issue.source, 'structure_rule') AS source,
                       issue.status, node.parent_id,
                       COALESCE(issue.subject_node_id,issue.node_id) subject_node_id,
                       COALESCE(issue.subject_node_name,issue.node_name) subject_node_name,
                       COALESCE(issue.subject_path,issue.path,node.path_names) subject_path
                FROM diagnosis_issue issue
                LEFT JOIN category_node node
                  ON node.version_id = issue.version_id
                 AND node.category_id = issue.node_id
                WHERE issue.id = ?
                """,
                (issue_id,),
            ).fetchone()
        return (
            {**_with_issue_type_metadata(dict(row)), "run_ids": self.list_run_ids(int(row["id"]))}
            if row else None
        )

    def update_status(self, issue_id: int, status: str) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                "UPDATE diagnosis_issue SET status = ? WHERE id = ?",
                (status, issue_id),
            )

    def link_run_issues(self, *, run_id: str, version_id: int) -> int:
        """Associate this run with the stable issue records it observed.

        A junction table is used because an idempotent re-run may observe an issue
        originally created by an earlier run; overwriting a single run_id would lose
        that audit history.
        """
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO run_issue(run_id,issue_id)
                   SELECT ?,id FROM diagnosis_issue WHERE version_id=?""",
                (run_id, version_id),
            )
        return int(cursor.rowcount)

    def list_run_ids(self, issue_id: int) -> list[str]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                "SELECT run_id FROM run_issue WHERE issue_id=? ORDER BY created_time,run_id",
                (issue_id,),
            ).fetchall()
        return [str(row["run_id"]) for row in rows]

    _STRUCTURE_TYPES = {
        value
        for code in (
            "missing_parent",
            "excessive_depth",
            "excessive_width",
            "duplicate_sibling",
            "parent_child_redundancy",
        )
        for value in legacy_values_for(code)
    }

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
        return [_with_issue_type_metadata(dict(row)) for row in rows]


def _with_issue_type_metadata(row: dict) -> dict:
    """Add canonical display fields without rewriting historical storage."""
    return {**row, **issue_type_metadata(row.get("issue_type"))}
