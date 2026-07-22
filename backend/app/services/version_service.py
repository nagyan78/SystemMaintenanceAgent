from backend.app.config import Settings
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.version import CreateVersionResult, SaveVersionResult, VersionDiff
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.db import connect
from hashlib import sha256
import json
import re


class VersionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_initial_version(self, file_id: int) -> CreateVersionResult:
        version_repo = VersionRepository(self.settings)
        taxonomy_repo = TaxonomyRepository(self.settings)
        existing = version_repo.get_by_file_and_no(file_id, "v1.0")
        if existing and taxonomy_repo.count_nodes(int(existing["id"])) > 0:
            overview = TaxonomyService(self.settings).get_overview(int(existing["id"]))
            return CreateVersionResult(
                version_id=int(existing["id"]),
                file_id=file_id,
                version_no="v1.0",
                node_count=overview.node_count,
                root_count=overview.root_count,
                max_depth=overview.max_depth,
                max_children_count=overview.max_children_count,
            )

        taxonomy_service = TaxonomyService(self.settings)
        nodes = taxonomy_service.parse_tree_nodes(file_id)
        build_result = taxonomy_service._summarize(file_id, nodes)
        version_id = version_repo.create_version(
            file_id=file_id,
            version_no="v1.0",
            description="初始导入版本",
        )
        taxonomy_repo.bulk_insert_nodes(version_id=version_id, nodes=nodes)
        return CreateVersionResult(
            version_id=version_id,
            file_id=file_id,
            version_no="v1.0",
            node_count=build_result.node_count,
            root_count=build_result.root_count,
            max_depth=build_result.max_depth,
            max_children_count=build_result.max_children_count,
        )

    def get_version(self, version_id: int) -> dict | None:
        return VersionRepository(self.settings).get_version(version_id)

    def list_versions(self, file_id: int | None = None) -> list[dict]:
        return VersionRepository(self.settings).list_versions(file_id=file_id)

    def save_new_version(
        self,
        base_version_id: int,
        review_batch_id: str,
        nodes: list[TaxonomyNodeRecord] | None = None,
        action_batch_id: str | None = None,
        source_workflow_id: str | None = None,
    ) -> SaveVersionResult:
        version_repo = VersionRepository(self.settings)
        taxonomy_repo = TaxonomyRepository(self.settings)
        if action_batch_id:
            existing = version_repo.get_by_action_batch(action_batch_id)
            if existing is not None:
                return self._existing_save_result(
                    existing,
                    base_version_id=base_version_id,
                    review_batch_id=review_batch_id,
                )
        base_version = version_repo.get_version(base_version_id)
        if base_version is None:
            raise ValueError(f"Taxonomy version {base_version_id} was not found.")
        snapshot_nodes = nodes or taxonomy_repo.list_node_records(base_version_id, include_deprecated=True)
        recalculated = _recalculate_tree(snapshot_nodes)
        new_version_no = self._next_version_no(int(base_version["file_id"]))
        quality_score = _calc_quality_score(recalculated)
        new_version_id = version_repo.create_version(
            file_id=int(base_version["file_id"]),
            version_no=new_version_no,
            description=f"基于 {base_version['version_no']} 执行审核批次 {review_batch_id}",
            quality_score=quality_score,
            parent_version_id=base_version_id,
            source_workflow_id=source_workflow_id,
            action_batch_id=action_batch_id,
        )
        taxonomy_repo.bulk_insert_nodes(version_id=new_version_id, nodes=recalculated)
        suggestions = SuggestionRepository(self.settings).list_suggestions(
            review_batch_id=review_batch_id
        )
        executed_count = sum(1 for item in suggestions if item.status == "executed")
        failed_count = sum(1 for item in suggestions if item.status == "failed")
        OperationLogRepository(self.settings).create_log(
            version_id=new_version_id,
            operator="local_user",
            operation_type="save_new_version",
            operation_detail={
                "base_version_id": base_version_id,
                "review_batch_id": review_batch_id,
                "node_count": len(recalculated),
                "action_batch_id": action_batch_id,
                "source_workflow_id": source_workflow_id,
            },
        )
        return SaveVersionResult(
            source_version_id=base_version_id,
            new_version_id=new_version_id,
            new_version_no=new_version_no,
            node_count=len(recalculated),
            executed_count=executed_count,
            failed_count=failed_count,
            quality_score=quality_score,
            action_batch_id=action_batch_id,
        )

    def create_deterministic_optimized_version(
        self,
        *,
        base_version_id: int,
        source_workflow_id: str,
        operator: str = "deterministic_optimizer",
    ) -> SaveVersionResult:
        """Create an idempotent v1.1 snapshot using safe synonym cleanup.

        This is the delivery fallback when semantic suggestions do not pass the
        execution gate.  It still creates a real, changed workbook instead of
        ending the workflow at the v1.0 diagnosis report.
        """
        version_repo = VersionRepository(self.settings)
        taxonomy_repo = TaxonomyRepository(self.settings)
        base = version_repo.get_version(base_version_id)
        if base is None:
            raise ValueError(f"Taxonomy version {base_version_id} was not found.")
        digest = sha256(f"{source_workflow_id}:{base_version_id}:synonym-cleanup-v1".encode()).hexdigest()[:16]
        action_batch_id = f"deterministic_{digest}"
        existing = version_repo.get_by_action_batch(action_batch_id)
        if existing is not None:
            return SaveVersionResult(
                source_version_id=base_version_id,
                new_version_id=int(existing["id"]),
                new_version_no=str(existing["version_no"]),
                node_count=taxonomy_repo.count_nodes(int(existing["id"])),
                executed_count=_deterministic_change_count(self.settings, int(existing["id"])),
                quality_score=existing.get("quality_score"),
                action_batch_id=action_batch_id,
                reused=True,
            )

        nodes = taxonomy_repo.list_node_records(base_version_id, include_deprecated=True)
        optimized: list[TaxonomyNodeRecord] = []
        changes: list[dict[str, object]] = []
        for node in nodes:
            cleaned, changed = _clean_synonym_payload(node.category_name, node.syn_list)
            optimized.append(node.model_copy(update={"syn_list": cleaned}) if changed else node)
            if changed:
                changes.append({
                    "category_id": node.category_id,
                    "category_name": node.category_name,
                    "before": node.syn_list,
                    "after": cleaned,
                })

        new_version_no = self._next_version_no(int(base["file_id"]))
        quality_score = _calc_quality_score(optimized)
        new_version_id = version_repo.create_version(
            file_id=int(base["file_id"]),
            version_no=new_version_no,
            description=f"基于 {base['version_no']} 的确定性同义词规范化优化版本",
            quality_score=quality_score,
            parent_version_id=base_version_id,
            source_workflow_id=source_workflow_id,
            action_batch_id=action_batch_id,
        )
        taxonomy_repo.bulk_insert_nodes(version_id=new_version_id, nodes=optimized)
        OperationLogRepository(self.settings).create_log(
            version_id=new_version_id,
            operator=operator,
            operation_type="deterministic_synonym_cleanup",
            operation_detail={
                "base_version_id": base_version_id,
                "base_version_no": base["version_no"],
                "source_workflow_id": source_workflow_id,
                "changed_node_count": len(changes),
                "examples": changes[:8],
                "action_batch_id": action_batch_id,
            },
        )
        return SaveVersionResult(
            source_version_id=base_version_id,
            new_version_id=new_version_id,
            new_version_no=new_version_no,
            node_count=len(optimized),
            executed_count=len(changes),
            failed_count=0,
            quality_score=quality_score,
            action_batch_id=action_batch_id,
        )

    def _existing_save_result(
        self,
        existing: dict,
        *,
        base_version_id: int,
        review_batch_id: str,
    ) -> SaveVersionResult:
        suggestions = SuggestionRepository(self.settings).list_suggestions(
            review_batch_id=review_batch_id
        )
        return SaveVersionResult(
            source_version_id=base_version_id,
            new_version_id=int(existing["id"]),
            new_version_no=str(existing["version_no"]),
            node_count=TaxonomyRepository(self.settings).count_nodes(int(existing["id"])),
            executed_count=sum(item.status == "executed" for item in suggestions),
            failed_count=sum(item.status == "failed" for item in suggestions),
            quality_score=existing.get("quality_score"),
            action_batch_id=existing.get("action_batch_id"),
            reused=True,
        )

    def save_executed_action_batch(
        self, *, base_version_id: int, review_batch_id: str,
        nodes: list[TaxonomyNodeRecord], suggestion_ids: list[int], operator: str,
        action_batch_id: str, source_workflow_id: str | None = None,
    ) -> SaveVersionResult:
        version_repo = VersionRepository(self.settings)
        existing = version_repo.get_by_action_batch(action_batch_id)
        if existing is not None:
            return self._existing_save_result(
                existing,
                base_version_id=base_version_id,
                review_batch_id=review_batch_id,
            )
        base = version_repo.get_version(base_version_id)
        if base is None:
            raise ValueError(f"Taxonomy version {base_version_id} was not found.")
        recalculated = recalculate_tree(nodes)
        new_version_no = self._next_version_no(int(base["file_id"]))
        quality_score = _calc_quality_score(recalculated)
        with connect(self.settings) as connection:
            cursor = connection.execute(
                """INSERT INTO taxonomy_version(
                       file_id,version_no,description,quality_score,parent_version_id,
                       source_workflow_id,action_batch_id,verification_status,lifecycle_status,
                       diagnosis_mode,diagnosis_model
                   ) VALUES(?,?,?,?,?,?,?,'not_verified','draft',?,?)""",
                (int(base["file_id"]), new_version_no,
                 f"基于 {base['version_no']} 执行审核批次 {review_batch_id}", quality_score,
                 base_version_id, source_workflow_id, action_batch_id,
                 base.get("diagnosis_mode"), base.get("diagnosis_model")),
            )
            new_version_id = int(cursor.lastrowid)
            connection.executemany(
                """INSERT INTO category_node(version_id,category_id,category_name,parent_id,level,path_ids,path_names,category_group_id,category_pids,category_group_name,syn_list,is_leaf,node_status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(new_version_id, n.category_id, n.category_name, n.parent_id, n.level, n.path_ids, n.path_names,
                  n.category_group_id, n.category_pids, n.category_group_name, n.syn_list, n.is_leaf, n.node_status) for n in recalculated],
            )
            if suggestion_ids:
                placeholders = ",".join("?" for _ in suggestion_ids)
                connection.execute(f"UPDATE adjustment_suggestion SET status='executed' WHERE id IN ({placeholders})", suggestion_ids)
            connection.execute(
                "INSERT INTO operation_log(version_id,operator,operation_type,operation_detail) VALUES(?,?,?,?)",
                (new_version_id, operator, "execute_and_save_actions", json.dumps({"base_version_id": base_version_id, "review_batch_id": review_batch_id, "suggestion_ids": suggestion_ids, "action_batch_id": action_batch_id}, ensure_ascii=False)),
            )
        return SaveVersionResult(source_version_id=base_version_id, new_version_id=new_version_id,
            new_version_no=new_version_no, node_count=len(recalculated), executed_count=len(suggestion_ids),
            failed_count=0, quality_score=quality_score, action_batch_id=action_batch_id)

    def get_version_diff(self, from_id: int, to_id: int) -> VersionDiff:
        taxonomy_repo = TaxonomyRepository(self.settings)
        from_nodes = {
            int(item["category_id"]): item
            for item in taxonomy_repo.list_nodes(from_id, include_deprecated=True)
        }
        to_nodes = {
            int(item["category_id"]): item
            for item in taxonomy_repo.list_nodes(to_id, include_deprecated=True)
        }
        added_ids = sorted(set(to_nodes).difference(from_nodes))
        deleted_ids = sorted(set(from_nodes).difference(to_nodes))
        common_ids = sorted(set(from_nodes).intersection(to_nodes))
        renamed = []
        moved = []
        synonym_changed = []
        deprecated = []
        for category_id in common_ids:
            before = from_nodes[category_id]
            after = to_nodes[category_id]
            if before["category_name"] != after["category_name"]:
                renamed.append(
                    {
                        "category_id": category_id,
                        "old_name": before["category_name"],
                        "new_name": after["category_name"],
                    }
                )
            if before["parent_id"] != after["parent_id"]:
                moved.append(
                    {
                        "category_id": category_id,
                        "category_name": after["category_name"],
                        "old_parent_id": before["parent_id"],
                        "new_parent_id": after["parent_id"],
                        "old_path_names": before["path_names"],
                        "new_path_names": after["path_names"],
                    }
                )
            before_synonyms = _split_synonyms(before.get("syn_list") or "")
            after_synonyms = _split_synonyms(after.get("syn_list") or "")
            if before_synonyms != after_synonyms:
                synonym_changed.append(
                    {
                        "category_id": category_id,
                        "category_name": after["category_name"],
                        "removed_synonyms": [
                            item for item in before_synonyms if item not in after_synonyms
                        ],
                        "added_synonyms": [
                            item for item in after_synonyms if item not in before_synonyms
                        ],
                    }
                )
            if before.get("node_status", "active") != after.get("node_status", "active"):
                deprecated.append({
                    "category_id": category_id,
                    "category_name": after["category_name"],
                    "old_status": before.get("node_status", "active"),
                    "new_status": after.get("node_status", "active"),
                })
        return VersionDiff(
            from_version_id=from_id,
            to_version_id=to_id,
            added=[to_nodes[item] for item in added_ids],
            deleted=[from_nodes[item] for item in deleted_ids],
            renamed=renamed,
            moved=moved,
            synonym_changed=synonym_changed,
            deprecated=deprecated,
        )

    def rollback_version(
        self,
        version_id: int,
        operator: str = "local_user",
        supersedes_version_id: int | None = None,
    ) -> SaveVersionResult:
        version_repo = VersionRepository(self.settings)
        target = version_repo.get_version(version_id)
        if target is None:
            raise ValueError(f"Taxonomy version {version_id} was not found.")
        nodes = TaxonomyRepository(self.settings).list_node_records(version_id, include_deprecated=True)
        new_version_no = self._next_version_no(int(target["file_id"]))
        quality_score = _calc_quality_score(nodes)
        new_version_id = version_repo.create_version(
            file_id=int(target["file_id"]),
            version_no=new_version_no,
            description=f"回滚到 {target['version_no']} 的快照",
            quality_score=quality_score,
            parent_version_id=version_id,
            supersedes_version_id=supersedes_version_id,
            lifecycle_status="draft",
        )
        TaxonomyRepository(self.settings).bulk_insert_nodes(
            version_id=new_version_id,
            nodes=_recalculate_tree(nodes),
        )
        OperationLogRepository(self.settings).create_log(
            version_id=new_version_id,
            operator=operator,
            operation_type="rollback_version",
            operation_detail={
                "rollback_from_version_id": version_id,
                "rollback_from_version_no": target["version_no"],
            },
        )
        return SaveVersionResult(
            source_version_id=version_id,
            new_version_id=new_version_id,
            new_version_no=new_version_no,
            node_count=len(nodes),
            quality_score=quality_score,
        )

    def _next_version_no(self, file_id: int) -> str:
        versions = VersionRepository(self.settings).list_versions(file_id=file_id)
        max_minor = -1
        for version in versions:
            version_no = str(version["version_no"])
            if not version_no.startswith("v1."):
                continue
            try:
                max_minor = max(max_minor, int(version_no.split(".", 1)[1]))
            except ValueError:
                continue
        return f"v1.{max_minor + 1 if max_minor >= 0 else 0}"


def recalculate_tree(nodes: list[TaxonomyNodeRecord]) -> list[TaxonomyNodeRecord]:
    node_map = {node.category_id: node for node in nodes}
    children: dict[int | None, list[TaxonomyNodeRecord]] = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node)
    for sibling_nodes in children.values():
        sibling_nodes.sort(key=lambda item: item.category_id)

    recalculated: dict[int, TaxonomyNodeRecord] = {}

    def visit(node: TaxonomyNodeRecord, ancestor_ids: list[int], ancestor_names: list[str],
              *, preserve_missing_parent: bool = False) -> None:
        if preserve_missing_parent:
            original_ids = [int(item.strip()) for item in str(node.path_ids or "").split(",") if item.strip().isdigit()]
            original_names = [item.strip() for item in str(node.path_names or "").split(">") if item.strip()]
            path_ids = original_ids if original_ids and original_ids[-1] == node.category_id else [node.category_id]
            path_names = original_names if original_names and original_names[-1] == node.category_name else [node.category_name]
        else:
            path_ids = [*ancestor_ids, node.category_id]
            path_names = [*ancestor_names, node.category_name]
        direct_children = children.get(node.category_id, [])
        recalculated[node.category_id] = node.model_copy(
            update={
                "parent_id": node.parent_id if preserve_missing_parent else (ancestor_ids[-1] if ancestor_ids else None),
                "level": len(path_ids),
                "path_ids": ",".join(str(item) for item in path_ids),
                "path_names": " > ".join(path_names),
                "category_group_id": node.category_group_id if preserve_missing_parent else (",".join(str(item) for item in ancestor_ids) or None),
                "category_pids": node.category_pids if preserve_missing_parent else (",".join(str(item) for item in ancestor_ids) or None),
                "category_group_name": node.category_group_name if preserve_missing_parent else (",".join(ancestor_names) or None),
                "is_leaf": 0 if direct_children else 1,
            }
        )
        for child in direct_children:
            visit(child, path_ids, path_names)

    for root in children.get(None, []):
        visit(root, [], [])
    for node in nodes:
        if node.category_id not in recalculated:
            visit(node, [], [], preserve_missing_parent=node.parent_id is not None and node.parent_id not in node_map)
    return [recalculated[node.category_id] for node in sorted(nodes, key=lambda item: item.category_id)]


_recalculate_tree = recalculate_tree


def _split_synonyms(syn_list: str) -> list[str]:
    return [item.strip() for item in syn_list.replace("，", ",").split(",") if item.strip()]


def _clean_synonym_payload(node_name: str, raw: str | None) -> tuple[str, bool]:
    text = str(raw or "").strip()
    values: list[object]
    encoded_as_list = text.startswith("[") and text.endswith("]")
    try:
        parsed = json.loads(text) if text else []
        values = parsed if isinstance(parsed, list) else [parsed]
    except (TypeError, json.JSONDecodeError):
        quoted = [left or right for left, right in re.findall(r"'([^']*)'|\"([^\"]*)\"", text)]
        values = quoted if quoted else re.split(r"[，,、;；|\r\n]+", text)

    original = [str(item or "").strip() for item in values]
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in original:
        if not value or value == node_name or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    changed = cleaned != original
    if not changed:
        return text or "[]", False
    if encoded_as_list:
        return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")), True
    return "、".join(cleaned), True


def _deterministic_change_count(settings: Settings, version_id: int) -> int:
    with connect(settings) as connection:
        row = connection.execute(
            """SELECT operation_detail FROM operation_log
               WHERE version_id=? AND operation_type='deterministic_synonym_cleanup'
               ORDER BY id DESC LIMIT 1""",
            (version_id,),
        ).fetchone()
    if row is None:
        return 0
    try:
        return int(json.loads(row[0]).get("changed_node_count", 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0


def _calc_quality_score(nodes: list[TaxonomyNodeRecord]) -> float:
    missing_parent_count = sum(
        1
        for node in nodes
        if node.parent_id is not None and node.parent_id not in {item.category_id for item in nodes}
    )
    duplicate_names = len(nodes) - len({(node.parent_id, node.category_name) for node in nodes})
    max_depth_penalty = sum(max(node.level - 7, 0) for node in nodes) * 0.2
    score = 100.0 - missing_parent_count - duplicate_names * 0.5 - max_depth_penalty
    return max(round(score, 1), 0.0)
