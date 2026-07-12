import hashlib
import json

from backend.app.config import Settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.action import ActionPreview, DeprecateNodePayload, DeleteLeafPayload, MergeNodePayload, SplitSubtreePayload
from backend.app.schemas.suggestion import SuggestionRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.version import VersionDiff
from backend.app.services.version_service import recalculate_tree
from backend.app.tools.validation_tools import extract_move_new_parent_id, resolve_clean_synonym_update


class SnapshotActionApplier:
    def __init__(self, reference_checker=None):
        self.reference_checker = reference_checker
    def apply(self, nodes: dict[int, TaxonomyNodeRecord], suggestion: SuggestionRecord) -> None:
        handler = getattr(self, f"_{suggestion.action_type}", None)
        if handler is None:
            raise ValueError(f"Unsupported action: {suggestion.action_type}")
        handler(nodes, suggestion)

    def _mark_as_valid(self, nodes, suggestion):
        return

    def _clean_synonym(self, nodes, suggestion):
        node = self._node(nodes, suggestion.target_node_id)
        terms, _ = resolve_clean_synonym_update(node.syn_list or "", suggestion.action_payload)
        nodes[node.category_id] = node.model_copy(update={"syn_list": ", ".join(terms) or None})

    def _rename_node(self, nodes, suggestion):
        node = self._node(nodes, suggestion.target_node_id)
        name = str(suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
        if not name:
            raise ValueError("rename_node 缺少 new_name")
        if any(item.parent_id == node.parent_id and item.category_id != node.category_id and item.category_name == name for item in nodes.values()):
            raise ValueError("同级节点下已存在相同名称")
        nodes[node.category_id] = node.model_copy(update={"category_name": name})

    def _move_node(self, nodes, suggestion):
        node = self._node(nodes, suggestion.target_node_id)
        has_parent, parent_id = extract_move_new_parent_id(suggestion)
        if not has_parent:
            raise ValueError("move_node 缺少 new_parent_id")
        if parent_id is not None:
            parent_id = int(parent_id)
            self._node(nodes, parent_id)
            if parent_id == node.category_id or _descendant(nodes, node.category_id, parent_id):
                raise ValueError("move_node 不能移动到自身或自身子树下")
        nodes[node.category_id] = node.model_copy(update={"parent_id": parent_id})

    def _add_node(self, nodes, suggestion):
        name = str(suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
        parent_id = suggestion.new_parent_id or suggestion.action_payload.get("parent_id")
        if not name or parent_id is None:
            raise ValueError("add_node 缺少 new_name 或 parent_id")
        self._node(nodes, int(parent_id))
        node_id = int(suggestion.action_payload.get("category_id") or max(nodes, default=0) + 1)
        if node_id in nodes:
            raise ValueError("add_node 的 category_id 已存在")
        nodes[node_id] = TaxonomyNodeRecord(category_id=node_id, category_name=name, parent_id=int(parent_id), level=1, path_ids=str(node_id), path_names=name, syn_list=suggestion.action_payload.get("syn_list"), is_leaf=1)

    def _split_subtree(self, nodes, suggestion):
        target = self._node(nodes, suggestion.target_node_id)
        payload = SplitSubtreePayload.model_validate(suggestion.action_payload)
        actual = {item.category_id for item in nodes.values() if item.parent_id == target.category_id and item.node_status == "active"}
        assigned = {child_id for group in payload.groups for child_id in group.child_ids}
        if assigned != actual:
            raise ValueError("split child_ids 必须完整覆盖当前直接子节点")
        next_id = max(nodes, default=0) + 1
        for group in payload.groups:
            group_id, next_id = next_id, next_id + 1
            nodes[group_id] = TaxonomyNodeRecord(category_id=group_id, category_name=group.name.strip(), parent_id=target.category_id, level=target.level + 1, path_ids=str(group_id), path_names=group.name.strip())
            for child_id in group.child_ids:
                child = self._node(nodes, child_id)
                nodes[child_id] = child.model_copy(update={"parent_id": group_id})

    def _merge_node(self, nodes, suggestion):
        payload = MergeNodePayload.model_validate(suggestion.action_payload)
        source, target = self._node(nodes, payload.source_node_id), self._node(nodes, payload.target_node_id)
        if source.category_id == target.category_id or _descendant(nodes, source.category_id, target.category_id):
            raise ValueError("merge source/target 关系无效")
        for node_id, node in list(nodes.items()):
            if node.parent_id == source.category_id:
                nodes[node_id] = node.model_copy(update={"parent_id": target.category_id})
        terms = list(dict.fromkeys([*_synonyms(target.syn_list), *_synonyms(source.syn_list)]))
        nodes[target.category_id] = target.model_copy(update={"syn_list": ", ".join(terms) or None})
        del nodes[source.category_id]

    def _deprecate_node(self, nodes, suggestion):
        data = {**suggestion.action_payload, "target_node_id": suggestion.action_payload.get("target_node_id", suggestion.target_node_id)}
        payload = DeprecateNodePayload.model_validate(data)
        self._node(nodes, payload.target_node_id)
        affected = {payload.target_node_id}
        if payload.child_strategy == "cascade_subtree":
            affected |= {node_id for node_id in nodes if _descendant(nodes, payload.target_node_id, node_id)}
        elif any(item.parent_id == payload.target_node_id and item.node_status == "active" for item in nodes.values()):
            raise ValueError("deprecate_node 目标仍有 active children")
        for node_id in affected:
            nodes[node_id] = nodes[node_id].model_copy(update={"node_status": "deprecated"})

    def _delete_leaf_node(self, nodes, suggestion):
        data = {**suggestion.action_payload, "target_node_id": suggestion.action_payload.get("target_node_id", suggestion.target_node_id)}
        payload = DeleteLeafPayload.model_validate(data)
        self._node(nodes, payload.target_node_id)
        if any(item.parent_id == payload.target_node_id for item in nodes.values()):
            raise ValueError("delete_leaf_node 只允许删除叶子节点")
        if self.reference_checker and self.reference_checker(suggestion.version_id, payload.target_node_id):
            raise ValueError("delete_leaf_node 目标存在外部引用")
        del nodes[payload.target_node_id]

    @staticmethod
    def _node(nodes, node_id):
        if node_id is None or node_id not in nodes:
            raise ValueError("target node 不存在")
        return nodes[node_id]


class ActionSimulationService:
    def __init__(self, settings: Settings) -> None:
        repo = TaxonomyRepository(settings)
        self.settings, self.applier = settings, SnapshotActionApplier(repo.count_external_references)

    def simulate(self, version_id: int, suggestions: list[SuggestionRecord]) -> ActionPreview:
        source = TaxonomyRepository(self.settings).list_node_records(version_id, include_deprecated=True)
        nodes = {item.category_id: item.model_copy(deep=True) for item in source}
        errors = _conflicts(suggestions)
        for suggestion in _ordered(suggestions):
            try:
                self.applier.apply(nodes, suggestion)
            except (ValueError, TypeError) as exc:
                errors.append({"suggestion_id": suggestion.id, "reason": str(exc)})
        result = recalculate_tree(list(nodes.values())) if not errors else list(nodes.values())
        if not errors:
            errors.extend(_validate(result))
        diff = _compare(source, result, suggestions)
        raw = {"version_id": version_id, "suggestions": [item.model_dump(mode="json") for item in suggestions], "diff": diff.model_dump(mode="json")}
        return ActionPreview(valid=not errors, errors=errors, diff=diff, nodes=result, review_hash=hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest())


def _ordered(items):
    rank = {"add_node": 0, "split_subtree": 1, "merge_node": 2, "move_node": 3, "rename_node": 4, "clean_synonym": 5, "deprecate_node": 6, "delete_leaf_node": 7}
    return sorted(items, key=lambda item: (rank.get(item.action_type, 5), item.id))


def _conflicts(items):
    split, terminal, errors = set(), set(), []
    for item in items:
        if item.action_type == "split_subtree" and item.target_node_id in split:
            errors.append({"suggestion_id": item.id, "reason": "同一节点不能重复 split"})
        if item.action_type == "split_subtree": split.add(item.target_node_id)
        if item.target_node_id in terminal:
            errors.append({"suggestion_id": item.id, "reason": "节点已被删除或弃用"})
        if item.action_type in {"delete_leaf_node", "deprecate_node"}: terminal.add(item.target_node_id)
    return errors


def _validate(nodes):
    by_id, names, errors = {item.category_id: item for item in nodes}, set(), []
    for node in nodes:
        key = (node.parent_id, node.category_name)
        if key in names: errors.append({"reason": f"同级重名：{node.category_name}"})
        names.add(key)
        parent = by_id.get(node.parent_id) if node.parent_id is not None else None
        if node.parent_id is not None and parent is None: errors.append({"reason": f"悬空父节点：{node.category_id}"})
        if node.node_status == "active" and parent and parent.node_status != "active": errors.append({"reason": f"active 节点存在 deprecated 祖先：{node.category_id}"})
    return errors


def _compare(before, after, suggestions):
    old, new = ({item.category_id: item for item in values} for values in (before, after)); common = set(old) & set(new)
    return VersionDiff(from_version_id=0, to_version_id=0,
        added=[new[i].model_dump() for i in sorted(set(new)-set(old))], deleted=[old[i].model_dump() for i in sorted(set(old)-set(new))],
        renamed=[{"category_id":i,"old_name":old[i].category_name,"new_name":new[i].category_name} for i in sorted(common) if old[i].category_name != new[i].category_name],
        moved=[{"category_id":i,"old_parent_id":old[i].parent_id,"new_parent_id":new[i].parent_id} for i in sorted(common) if old[i].parent_id != new[i].parent_id],
        synonym_changed=[{"category_id":i,"old":old[i].syn_list,"new":new[i].syn_list} for i in sorted(common) if old[i].syn_list != new[i].syn_list],
        merged=[item.action_payload for item in suggestions if item.action_type=="merge_node"], split=[{"target_node_id":item.target_node_id,**item.action_payload} for item in suggestions if item.action_type=="split_subtree"], deprecated=[{"target_node_id":item.target_node_id,**item.action_payload} for item in suggestions if item.action_type=="deprecate_node"])


def _synonyms(value): return [item.strip() for item in (value or "").replace("，", ",").split(",") if item.strip()]


def _descendant(nodes, ancestor_id, descendant_id):
    current, visited = nodes.get(descendant_id), set()
    while current and current.parent_id is not None and current.category_id not in visited:
        visited.add(current.category_id)
        if current.parent_id == ancestor_id: return True
        current = nodes.get(current.parent_id)
    return False
