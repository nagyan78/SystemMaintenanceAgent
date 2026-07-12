from collections.abc import Iterable
from typing import Any

from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.taxonomy import TaxonomyNodeRecord


class TaxonomyRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def bulk_insert_nodes(
        self,
        *,
        version_id: int,
        nodes: Iterable[TaxonomyNodeRecord],
    ) -> None:
        values = [
            (
                version_id,
                node.category_id,
                node.category_name,
                node.parent_id,
                node.level,
                node.path_ids,
                node.path_names,
                node.category_group_id,
                node.category_pids,
                node.category_group_name,
                node.syn_list,
                node.is_leaf,
                node.node_status,
            )
            for node in nodes
        ]
        with connect(self.settings) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO category_node (
                    version_id, category_id, category_name, parent_id, level,
                    path_ids, path_names, category_group_id, category_pids,
                    category_group_name, syn_list, is_leaf, node_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def list_nodes(self, version_id: int, *, include_deprecated: bool = False) -> list[dict]:
        status_clause = "" if include_deprecated else "AND node_status = 'active'"
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, version_id, category_id, category_name, parent_id,
                       level, path_ids, path_names, category_group_id,
                       category_pids, category_group_name, syn_list, is_leaf, node_status
                FROM category_node
                WHERE version_id = ? {status_clause}
                ORDER BY id
                """.format(status_clause=status_clause),
                (version_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_node_records(self, version_id: int, *, include_deprecated: bool = False) -> list[TaxonomyNodeRecord]:
        return [
            TaxonomyNodeRecord.model_validate(
                {
                    key: value
                    for key, value in row.items()
                    if key
                    in {
                        "category_id",
                        "category_name",
                        "parent_id",
                        "level",
                        "path_ids",
                        "path_names",
                        "category_group_id",
                        "category_pids",
                        "category_group_name",
                        "syn_list",
                        "is_leaf",
                        "node_status",
                    }
                }
            )
            for row in self.list_nodes(version_id, include_deprecated=include_deprecated)
        ]

    def get_node_detail(self, version_id: int, category_id: int, *, include_deprecated: bool = False) -> dict | None:
        status_clause = "" if include_deprecated else "AND node_status = 'active'"
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, version_id, category_id, category_name, parent_id,
                       level, path_ids, path_names, category_group_id,
                       category_pids, category_group_name, syn_list, is_leaf, node_status
                FROM category_node
                WHERE version_id = ? AND category_id = ? {status_clause}
                """.format(status_clause=status_clause),
                (version_id, category_id),
            ).fetchone()
        return dict(row) if row else None

    def get_node_path(self, version_id: int, category_id: int) -> str:
        node = self.get_node_detail(version_id, category_id)
        return str(node["path_names"]) if node else ""

    def get_children(self, version_id: int, parent_id: int) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT category_id, category_name, path_names, syn_list, level, is_leaf
                FROM category_node
                WHERE version_id = ? AND parent_id = ? AND node_status = 'active'
                ORDER BY category_id
                """,
                (version_id, parent_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def is_descendant(self, version_id: int, ancestor_id: int, descendant_id: int) -> bool:
        with connect(self.settings) as connection:
            current = connection.execute(
                """
                SELECT parent_id
                FROM category_node
                WHERE version_id = ? AND category_id = ?
                """,
                (version_id, descendant_id),
            ).fetchone()
            while current and current[0] is not None:
                if int(current[0]) == ancestor_id:
                    return True
                current = connection.execute(
                    """
                    SELECT parent_id
                    FROM category_node
                    WHERE version_id = ? AND category_id = ?
                    """,
                    (version_id, int(current[0])),
                ).fetchone()
        return False

    def list_root_overview(self, version_id: int, limit: int = 20) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT parent.category_id,
                       parent.category_name,
                       parent.path_names,
                       COUNT(child.category_id) AS child_count
                FROM category_node parent
                LEFT JOIN category_node child
                  ON child.version_id = parent.version_id
                 AND child.parent_id = parent.category_id
                WHERE parent.version_id = ? AND parent.parent_id IS NULL
                  AND parent.node_status = 'active'
                  AND (child.category_id IS NULL OR child.node_status = 'active')
                GROUP BY parent.category_id, parent.category_name, parent.path_names
                ORDER BY parent.category_id
                LIMIT ?
                """,
                (version_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_content_diagnosis_candidates(
        self,
        version_id: int,
        *,
        priority_subtrees: list[str] | None = None,
        limit: int = 200,
    ) -> list[dict]:
        subtree_filter = ""
        params: list[object] = [version_id]
        if priority_subtrees:
            clauses = []
            for subtree in priority_subtrees:
                clauses.append("path_names LIKE ?")
                params.append(f"%{subtree}%")
            subtree_filter = f" AND ({' OR '.join(clauses)})"
        params.append(limit)
        with connect(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT category_id, category_name, parent_id, level, path_names,
                       syn_list, is_leaf
                FROM category_node
                WHERE version_id = ?
                  AND node_status = 'active'
                  AND syn_list IS NOT NULL
                  AND TRIM(syn_list) NOT IN ('', '[]')
                  {subtree_filter}
                ORDER BY
                  LENGTH(syn_list) DESC,
                  level DESC,
                  category_id
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def count_nodes(self, version_id: int) -> int:
        with connect(self.settings) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM category_node WHERE version_id = ? AND node_status = 'active'",
                    (version_id,),
                ).fetchone()[0]
            )

    def get_overview_counts(self, version_id: int) -> dict:
        with connect(self.settings) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS node_count,
                       SUM(CASE WHEN parent_id IS NULL THEN 1 ELSE 0 END) AS root_count,
                       MAX(level) AS max_depth,
                       SUM(CASE WHEN is_leaf = 1 THEN 1 ELSE 0 END) AS leaf_count,
                       SUM(CASE WHEN is_leaf = 0 THEN 1 ELSE 0 END) AS non_leaf_count,
                       SUM(CASE WHEN syn_list IS NOT NULL
                                  AND TRIM(syn_list) NOT IN ('', '[]')
                                THEN 1 ELSE 0 END) AS synonym_non_empty_count
                FROM category_node
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
            duplicate_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT category_name
                    FROM category_node
                    WHERE version_id = ?
                    GROUP BY category_name
                    HAVING COUNT(*) > 1
                )
                """,
                (version_id,),
            ).fetchone()[0]
            missing_parent_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM category_node child
                WHERE child.version_id = ?
                  AND child.parent_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM category_node parent
                      WHERE parent.version_id = child.version_id
                        AND parent.category_id = child.parent_id
                  )
                """,
                (version_id,),
            ).fetchone()[0]
            max_children_count = connection.execute(
                """
                SELECT COALESCE(MAX(child_count), 0)
                FROM (
                    SELECT parent_id, COUNT(*) AS child_count
                    FROM category_node
                    WHERE version_id = ? AND parent_id IS NOT NULL
                    GROUP BY parent_id
                )
                """,
                (version_id,),
            ).fetchone()[0]
        counts = dict(row)
        counts["duplicate_name_count"] = int(duplicate_count)
        counts["missing_parent_count"] = int(missing_parent_count)
        counts["max_children_count"] = int(max_children_count)
        return {key: int(value or 0) for key, value in counts.items()}
