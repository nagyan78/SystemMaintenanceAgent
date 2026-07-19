import math
import re
from collections import defaultdict
from typing import Any

from backend.app.config import Settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion


class RemediationPlanningService:
    """Build conservative, executable action proposals from confirmed detector facts.

    The service never mutates persistence. Every proposal still passes action
    validation, independent AI review and snapshot simulation before execution.
    """

    AMBIGUOUS_NAMES = {"其他", "其它", "综合", "通用", "未分类"}
    GENERATOR_VERSION = "remediation-v2"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.taxonomy = TaxonomyRepository(settings)

    def plan(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        issue_type = str(issue.get("issue_type_code") or issue.get("issue_type") or "unknown")
        handlers = {
            "naming_nonstandard": self._rename,
            "ambiguous_name": self._rename,
            "vague_node": self._rename,
            "naming_irregular": self._rename,
            "synonym_format": self._clean_synonym,
            "synonym_conflict": self._clean_synonym,
            "synonym_overlap": self._clean_synonym,
            "synonym_typo": self._clean_synonym,
            "synonym_format_issue": self._clean_synonym,
            "synonym_pollution": self._clean_synonym,
            "missing_parent": self._add_missing_parent,
            "orphan": self._add_missing_parent,
            "excessive_depth": self._move,
            "semantic_misplacement": self._move,
            "inconsistent_dimension": self._no_change,
            "parent_child_redundancy": self._no_change,
            "deep_level": self._move,
            "bad_parent_child_relation": self._move,
            "inconsistent_granularity": self._move,
            "wide_node": self._split,
            "excessive_width": self._split,
            "duplicate_sibling": self._merge,
            "duplicate_name": self._no_change,
            "semantic_duplicate": self._merge,
            "obsolete_node": self._deprecate,
            "redundant_node": self._deprecate,
            "redundant_leaf": self._delete_leaf,
        }
        handler = handlers.get(issue_type)
        suggestion = handler(version_id, issue) if handler else None
        return suggestion or self._no_change(version_id, issue)

    def _base(self, version_id: int, issue: dict[str, Any], **updates: Any) -> AdjustmentSuggestion:
        payload = {
            "issue_id": int(issue["id"]),
            "version_id": version_id,
            "target_node_id": issue.get("subject_node_id") or issue.get("node_id"),
            "target_node_name": issue.get("subject_node_name") or issue.get("node_name"),
            "reason": str(issue.get("reason") or issue.get("description") or "AI 根据问题证据生成修改方案"),
            "confidence": float(issue.get("confidence") or 0),
            # This flag now means a second AI safety review is required before
            # execution; it does not route the suggestion to a person.
            "need_confirm": True,
            "status": "pending",
        }
        payload.update(updates)
        return AdjustmentSuggestion.model_validate(payload)

    def _rename(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        old_name = str(node["category_name"]).strip()
        explicit_names = {"锌制货架": "锌制仓储用货架"}
        cleaned = explicit_names.get(old_name)
        if not cleaned or cleaned == old_name:
            return None
        return self._base(
            version_id, issue, action_type="rename_node", old_name=old_name,
            new_name=cleaned, action_payload={"new_name": cleaned}, risk_level="low",
            suggestion=f"将「{old_name}」调整为「{cleaned}」，并在副本中验证命名唯一性。",
        )

    def _clean_synonym(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        raw = str(node.get("syn_list") or "")
        terms = _terms(raw.replace("\n", ",").replace("\r", ","))
        kept: list[str] = []
        seen: set[str] = set()
        name_key = str(node["category_name"]).strip().casefold()
        children = self.taxonomy.get_children(version_id, int(node["category_id"]))
        child_names = {str(item["category_name"]).strip().casefold() for item in children}
        forced_remove = {"气体压缩机": {"压缩机"}}.get(str(node["category_name"]), set())
        for term in terms:
            key = term.casefold()
            malformed = "\n" in term or term.count(str(node["category_name"])) > 1
            if key == name_key or key in seen or key in child_names or term in forced_remove or malformed:
                continue
            seen.add(key)
            kept.append(term)
        if kept == terms:
            return None
        return self._base(
            version_id, issue, action_type="update_synonyms",
            action_payload={"current_synonyms": terms, "synonyms_to_remove": [item for item in terms if item not in kept],
                            "synonyms_to_add": [], "final_syn_list": kept}, risk_level="low",
            suggestion="清理重复、格式错误、范围过宽或属于直接子节点的同义词。",
        )

    def _add_missing_parent(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        missing_parent_id = node.get("parent_id") or issue.get("parent_id")
        if missing_parent_id is None:
            return None
        missing_id = int(missing_parent_id)
        path_ids = _ids(node.get("path_ids"))
        path_names = _path_names(node.get("path_names"))
        try:
            missing_index = path_ids.index(missing_id)
        except ValueError:
            missing_index = max(len(path_ids) - 2, 0)
        ancestor = None
        for candidate_id in reversed(path_ids[:missing_index]):
            ancestor = self.taxonomy.get_node_detail(version_id, candidate_id)
            if ancestor:
                break
        parent_id = int(ancestor["category_id"]) if ancestor else None
        if parent_id is None:
            return self._manual_missing_parent(version_id, issue, node, missing_id, None)
        name = path_names[missing_index].strip() if missing_index < len(path_names) else ""
        if not name or name in self.AMBIGUOUS_NAMES or name.startswith("待补分类"):
            return self._manual_missing_parent(version_id, issue, node, missing_id, ancestor)
        nodes = self.taxonomy.list_nodes(version_id)
        affected = [item for item in nodes if int(item.get("parent_id") or -1) == missing_id]
        descendants = sum(1 for item in nodes if int(node["category_id"]) in _ids(item.get("path_ids")) and int(item["category_id"]) != int(node["category_id"]))
        ancestor_path = str(ancestor.get("path_names") or ancestor.get("category_name") or "")
        new_parent_path = f"{ancestor_path} > {name}" if ancestor_path else name
        new_path = f"{new_parent_path} > {node['category_name']}"
        impact_scope = {
            "direct_affected_nodes": [{"id": int(item["category_id"]), "name": item["category_name"]} for item in affected],
            "affected_descendant_count": descendants,
            "path_changed": True,
            "shared_missing_parent": len(affected) > 1,
            "shared_child_count": len(affected),
        }
        return self._base(
            version_id, issue, action_type="add_node", target_node_id=None,
            target_node_name=name, new_parent_id=parent_id, new_name=name,
            action_payload={"category_id": missing_id, "missing_parent_id": missing_id,
                "parent_id": parent_id, "new_name": name, "subject_node_id": int(node["category_id"]),
                "current_path": node.get("path_names"), "nearest_valid_ancestor_id": parent_id,
                "nearest_valid_ancestor_name": ancestor.get("category_name"), "new_parent_path": new_parent_path,
                "new_path": new_path, "action": {"type": "create_missing_parent", "label": "补建缺失父节点"},
                "impact_scope": impact_scope},
            risk_level="medium", suggestion=f"在现有父节点 {parent_id} 下补建缺失节点「{name}」。",
        )

    def _manual_missing_parent(self, version_id: int, issue: dict[str, Any], node: dict[str, Any],
                               missing_id: int, ancestor: dict[str, Any] | None) -> AdjustmentSuggestion:
        return self._base(
            version_id, issue, action_type="review_only",
            action_payload={"requires_ai_resolution": True, "missing_parent_id": missing_id,
                "subject_node_id": int(node["category_id"]), "current_path": node.get("path_names"),
                "nearest_valid_ancestor_id": ancestor.get("category_id") if ancestor else None,
                "nearest_valid_ancestor_name": ancestor.get("category_name") if ancestor else None,
                "no_change_reason": "现有证据无法可靠推导缺失父节点名称或挂载位置，必须由 AI 深度分析补全",
                "action": {"type": "requires_ai_resolution", "label": "AI 深度分析缺失父节点"},
                "impact_scope": {"direct_affected_nodes": [{"id": int(node["category_id"]), "name": node["category_name"]}],
                                 "affected_descendant_count": 0, "path_changed": True,
                                 "shared_missing_parent": False, "shared_child_count": 1}},
            risk_level="medium", suggestion="AI 必须结合完整路径、祖先和同级节点补全父节点名称与挂载位置。",
        )

    def _move(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        issue_type = str(issue.get("issue_type_code") or issue.get("issue_type") or "unknown")
        # Semantic token overlap is not sufficient evidence for moving a subtree.
        # Only the deterministic excessive-depth correction is generated here;
        # AI-enhanced mode must supply the semantic target.
        if issue_type not in {"deep_level", "excessive_depth"} or not node.get("parent_id"):
            return None
        parent = self.taxonomy.get_node_detail(version_id, int(node["parent_id"]))
        new_parent_id = int(parent["parent_id"]) if parent and parent.get("parent_id") else None
        if new_parent_id is None or new_parent_id == node.get("parent_id"):
            return None
        new_parent = self.taxonomy.get_node_detail(version_id, int(new_parent_id))
        old_parent = self.taxonomy.get_node_detail(version_id, int(node["parent_id"])) if node.get("parent_id") else None
        if not new_parent or not old_parent:
            return None
        new_path = f"{new_parent.get('path_names') or new_parent['category_name']} > {node['category_name']}"
        return self._base(
            version_id, issue, action_type="move_node", old_parent_id=node.get("parent_id"),
            new_parent_id=new_parent_id, action_payload={"new_parent_id": new_parent_id,
                "old_parent_name": old_parent["category_name"], "new_parent_name": new_parent["category_name"],
                "old_path": node.get("path_names"), "new_parent_path": new_parent.get("path_names"),
                "new_path": new_path, "new_level": int(new_parent.get("level") or 0) + 1,
                "selection_basis": f"该节点当前层级为 {node.get('level')}，上移至原祖父节点后降低一层；未使用名称相似度猜测父节点。",
                "affected_child_count": len(self.taxonomy.get_children(version_id, int(node["category_id"])))},
            risk_level="medium", suggestion=f"移动到父节点「{new_parent['category_name']}」，并在副本中验证整棵子树路径。",
        )

    def _split(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        children = self.taxonomy.get_children(version_id, int(node["category_id"]))
        if len(children) < 4:
            return None
        group_count = max(2, min(6, math.ceil(len(children) / 20)))
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(group_count)]
        for index, child in enumerate(sorted(children, key=lambda item: (str(item["category_name"]), int(item["category_id"])))):
            buckets[index % group_count].append(child)
        groups = [
            {"name": f"{node['category_name']}分组{index + 1}", "child_ids": [int(item["category_id"]) for item in bucket]}
            for index, bucket in enumerate(buckets) if bucket
        ]
        return self._base(
            version_id, issue, action_type="split_subtree", action_payload={"groups": groups},
            risk_level="high", suggestion="已生成完整覆盖直接子节点的初始分组；AI 必须补全业务分组名称并通过整树预演。",
        )

    def _merge(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        # 规则层无法证明语义等价；AI 模式会优先生成并验证合并方案。
        return None
        nodes = self.taxonomy.list_nodes(version_id)
        candidates: list[dict[str, Any]] = []
        if issue.get("node_name"):
            key = _name_key(str(issue["node_name"]))
            candidates = [item for item in nodes if _name_key(str(item["category_name"])) == key]
        if len(candidates) < 2:
            mentioned = {int(value) for value in re.findall(r"\b\d+\b", str(issue.get("description") or ""))}
            candidates = [item for item in nodes if int(item["category_id"]) in mentioned]
        if len(candidates) < 2 and issue.get("node_id") is not None:
            source = self.taxonomy.get_node_detail(version_id, int(issue["node_id"]))
            if source:
                source_terms = set(_terms(source.get("syn_list"))) | {str(source["category_name"])}
                scored = []
                for item in nodes:
                    if int(item["category_id"]) == int(source["category_id"]):
                        continue
                    terms = set(_terms(item.get("syn_list"))) | {str(item["category_name"])}
                    score = len({term.casefold() for term in source_terms} & {term.casefold() for term in terms})
                    scored.append((score, item))
                if scored and max(scored, key=lambda pair: pair[0])[0] > 0:
                    candidates = [source, max(scored, key=lambda pair: pair[0])[1]]
        if len(candidates) < 2:
            return None
        ordered = sorted(candidates, key=lambda item: int(item["category_id"]))
        target, source = ordered[0], ordered[-1]
        return self._base(
            version_id, issue, action_type="merge_node", target_node_id=int(source["category_id"]),
            target_node_name=source["category_name"],
            action_payload={"source_node_id": int(source["category_id"]), "target_node_id": int(target["category_id"])},
            risk_level="high", suggestion=f"将节点 {source['category_id']} 合并到保留节点 {target['category_id']}。",
        )

    def _deprecate(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node:
            return None
        children = self.taxonomy.get_children(version_id, int(node["category_id"]))
        strategy = "cascade_subtree" if children else "require_empty"
        return self._base(
            version_id, issue, action_type="deprecate_node",
            action_payload={"target_node_id": int(node["category_id"]), "reason": str(issue.get("reason") or "业务停用"), "child_strategy": strategy},
            risk_level="high", suggestion="保留历史记录并停止在默认分类树中使用。",
        )

    def _delete_leaf(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion | None:
        node = self._node(version_id, issue)
        if not node or self.taxonomy.get_children(version_id, int(node["category_id"])):
            return None
        if self.taxonomy.count_external_references(version_id, int(node["category_id"])):
            return self._deprecate(version_id, issue)
        return self._base(
            version_id, issue, action_type="delete_leaf_node",
            action_payload={"target_node_id": int(node["category_id"])}, risk_level="high",
            suggestion="该叶子节点没有子节点和已登记外部引用，可在副本预演通过后删除。",
        )

    def _no_change(self, version_id: int, issue: dict[str, Any]) -> AdjustmentSuggestion:
        return self._base(
            version_id, issue, action_type="review_only",
            action_payload={"requires_ai_resolution": True, "no_change_reason": "当前方案缺少明确可执行的新名称、拆分方案、移动依据或等价证据"},
            risk_level="low", suggestion="当前方案不完整，必须进入 AI 深度分析补全具体动作。",
        )

    def _node(self, version_id: int, issue: dict[str, Any]) -> dict[str, Any] | None:
        node_id = issue.get("subject_node_id") or issue.get("node_id")
        return self.taxonomy.get_node_detail(version_id, int(node_id)) if node_id is not None else None

def _terms(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").replace("，", ",").split(",") if item.strip()]


def _ids(value: object) -> list[int]:
    return [int(item) for item in re.findall(r"\d+", str(value or ""))]


def _path_names(value: object) -> list[str]:
    return [item.strip() for item in re.split(r"\s*>\s*|\s*,\s*", str(value or "")) if item.strip()]


def _name_key(value: str) -> str:
    return re.sub(r"[\s\-_—/、，,。.]", "", value).casefold()


def _tokens(value: str) -> set[str]:
    normalized = _name_key(value)
    return {normalized[index:index + 2] for index in range(max(len(normalized) - 1, 0))} | ({normalized} if normalized else set())
