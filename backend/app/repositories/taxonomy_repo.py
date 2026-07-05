from collections.abc import Iterable

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
            )
            for node in nodes
        ]
        with connect(self.settings) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO category_node (
                    version_id, category_id, category_name, parent_id, level,
                    path_ids, path_names, category_group_id, category_pids,
                    category_group_name, syn_list, is_leaf
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )

    def list_nodes(self, version_id: int) -> list[dict]:
        with connect(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, version_id, category_id, category_name, parent_id,
                       level, path_ids, path_names, category_group_id,
                       category_pids, category_group_name, syn_list, is_leaf
                FROM category_node
                WHERE version_id = ?
                ORDER BY id
                """,
                (version_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_nodes(self, version_id: int) -> int:
        with connect(self.settings) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM category_node WHERE version_id = ?",
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
