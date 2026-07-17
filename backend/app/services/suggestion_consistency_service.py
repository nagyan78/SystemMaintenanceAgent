from dataclasses import dataclass
from typing import Any

from backend.app.config import Settings
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion


ACTION_ALIASES = {"clean_synonym": "update_synonyms", "mark_as_valid": "review_only"}
ALLOWED_BY_ISSUE = {
    "missing_parent": {"move_node", "add_node", "review_only"},
    "excessive_depth": {"move_node", "review_only"},
    "excessive_width": {"split_subtree", "move_node", "add_node", "review_only"},
    "duplicate_sibling": {"merge_node", "review_only"},
    "parent_child_redundancy": {"rename_node", "merge_node", "review_only"},
    "synonym_format": {"update_synonyms", "review_only"},
    "synonym_typo": {"update_synonyms", "review_only"},
    "synonym_conflict": {"update_synonyms", "review_only"},
    "synonym_overlap": {"update_synonyms", "review_only"},
    "naming_nonstandard": {"rename_node", "review_only"},
    "semantic_duplicate": {"merge_node", "review_only"},
    "semantic_misplacement": {"move_node", "review_only"},
    "inconsistent_dimension": {"review_only"},
    "unknown": {"review_only"},
}


@dataclass(frozen=True)
class ConsistencyResult:
    suggestion: AdjustmentSuggestion
    valid: bool
    executable: bool
    reason: str | None
    change_preview: dict[str, Any]
    downgraded: bool = False


class SuggestionConsistencyService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.issues = DiagnosisRepository(settings)
        self.taxonomy = TaxonomyRepository(settings)

    def check(self, suggestion: AdjustmentSuggestion, *, normalize_new: bool = False) -> ConsistencyResult:
        issue = self.issues.get_issue_detail(suggestion.issue_id)
        if not issue:
            return self._invalid(suggestion, "诊断问题不存在。", normalize_new)
        code = str(issue.get("issue_type_code") or "unknown")
        canonical_action = ACTION_ALIASES.get(suggestion.action_type, suggestion.action_type)
        candidate = suggestion.model_copy(update={"action_type": canonical_action}) if normalize_new else suggestion
        effective_action = canonical_action
        allowed = ALLOWED_BY_ISSUE.get(code)
        if allowed and effective_action not in allowed:
            return self._invalid(candidate, f"问题类型“{issue['issue_type_label']}”不能使用动作“{effective_action}”。", normalize_new)
        subject_node_id = issue.get("subject_node_id") or issue.get("node_id")
        if effective_action not in {"review_only", "add_node"} and subject_node_id is not None:
            if candidate.target_node_id != int(subject_node_id):
                return self._invalid(candidate, f"动作目标节点必须是问题主体节点 {subject_node_id}，不能修改其父节点或其他节点。", normalize_new)
        if effective_action == "review_only":
            reason = str(candidate.action_payload.get("no_change_reason") or candidate.reason or "需要人工确认")
            payload = candidate.action_payload
            preview = {"action_type": "review_only",
                       "before": {"当前节点 ID": payload.get("subject_node_id") or subject_node_id,
                                  "当前节点名称": issue.get("subject_node_name") or issue.get("node_name"),
                                  "缺失父节点 ID": payload.get("missing_parent_id"),
                                  "当前完整路径": payload.get("current_path") or issue.get("subject_path") or issue.get("path"),
                                  "最近有效祖先": payload.get("nearest_valid_ancestor_name")},
                       "after": {"处理状态": "需要人工补充修改方案" if payload.get("needs_manual_edit") else "不自动修改"},
                       "action": payload.get("action") or {"type": "needs_manual_edit" if payload.get("needs_manual_edit") else "review_only"},
                       "impact_scope": payload.get("impact_scope") or {},
                       "impact": payload.get("impact_scope") or {},
                       "details": {"不修改原因": reason, "需要人工确认的内容": candidate.suggestion,
                                   "needs_manual_edit": bool(payload.get("needs_manual_edit"))}}
            return ConsistencyResult(candidate, True, False, None, preview)
        if effective_action == "rename_node":
            old_name = str(candidate.old_name or issue.get("node_name") or "").strip()
            new_name = str(candidate.new_name or candidate.action_payload.get("new_name") or "").strip()
            if not old_name or not new_name:
                return self._invalid(candidate, "重命名缺少原名称或新名称。", normalize_new)
            if new_name == old_name or (new_name.endswith("分类") and new_name.removesuffix("分类") == old_name):
                return self._invalid(candidate, "禁止使用“原名称+分类”作为重命名兜底。", normalize_new)
            preview = {"action_type": effective_action, "before": {"原名称": old_name}, "after": {"新名称": new_name}, "impact": {}}
        elif effective_action == "update_synonyms":
            payload = candidate.action_payload
            current = self._list(payload.get("current_synonyms"))
            if not current and candidate.target_node_id:
                node = self.taxonomy.get_node_detail(candidate.version_id, candidate.target_node_id)
                current = self._list(node.get("syn_list") if node else None)
            removed = self._list(payload.get("synonyms_to_remove") or payload.get("remove_synonyms"))
            added = self._list(payload.get("synonyms_to_add") or payload.get("add_synonyms"))
            final = self._list(payload.get("final_syn_list") or payload.get("updated_synonyms"))
            if not final:
                final = [item for item in current if item not in removed] + [item for item in added if item not in current]
            if not (removed or added) or any(not item.strip() for item in final) or len(final) != len(set(final)):
                return self._invalid(candidate, "同义词动作缺少有效增删内容，或最终同义词存在空值/重复。", normalize_new)
            normalized_payload = {**payload, "current_synonyms": current, "synonyms_to_remove": removed,
                                  "synonyms_to_add": added, "final_syn_list": final}
            candidate = candidate.model_copy(update={"action_payload": normalized_payload})
            preview = {"action_type": effective_action, "before": {"原同义词": current, "删除内容": removed},
                       "after": {"新增内容": added, "最终同义词": final}, "impact": {}}
        elif effective_action == "move_node":
            payload = candidate.action_payload
            required = (candidate.old_parent_id, candidate.new_parent_id, payload.get("old_parent_name"),
                        payload.get("new_parent_name"), payload.get("old_path"), payload.get("new_parent_path"), payload.get("new_path"),
                        payload.get("selection_basis"), payload.get("new_level"))
            if any(value is None or value == "" for value in required):
                return self._invalid(candidate, "移动节点必须包含原/新父节点、原/新路径、修改后层级和可核验的目标选择依据。", normalize_new)
            if str(payload.get("selection_basis")).strip() == "层级规则与名称语义候选共同命中":
                return self._invalid(candidate, "名称相似度和笼统的层级规则不能证明父子语义关系，该移动建议必须重新人工确认。", normalize_new)
            node = self.taxonomy.get_node_detail(candidate.version_id, int(candidate.target_node_id)) if candidate.target_node_id is not None else None
            old_parent = self.taxonomy.get_node_detail(candidate.version_id, int(candidate.old_parent_id)) if candidate.old_parent_id is not None else None
            new_parent = self.taxonomy.get_node_detail(candidate.version_id, int(candidate.new_parent_id)) if candidate.new_parent_id is not None else None
            if not node or not old_parent or not new_parent:
                return self._invalid(candidate, "移动节点引用的目标节点、原父节点或新父节点不存在。", normalize_new)
            expected_parent_path = str(new_parent.get("path_names") or new_parent.get("category_name") or "")
            expected_new_path = f"{expected_parent_path} > {node['category_name']}"
            expected_level = int(new_parent.get("level") or 0) + 1
            if int(node.get("parent_id") or -1) != int(candidate.old_parent_id):
                return self._invalid(candidate, "移动建议记录的原父节点与当前基线版本不一致。", normalize_new)
            if (str(payload.get("old_parent_name")) != str(old_parent.get("category_name"))
                    or str(payload.get("new_parent_name")) != str(new_parent.get("category_name"))
                    or str(payload.get("new_parent_path")) != expected_parent_path
                    or str(payload.get("new_path")) != expected_new_path
                    or int(payload.get("new_level")) != expected_level):
                return self._invalid(candidate, "移动建议中的父节点名称、路径或修改后层级与基线版本不一致。", normalize_new)
            preview = {"action_type": effective_action,
                       "before": {"原父节点": payload["old_parent_name"], "原路径": payload["old_path"]},
                       "after": {"新父节点": payload["new_parent_name"], "新路径": payload["new_path"]},
                       "impact": {"受影响子节点数量": int(payload.get("affected_child_count") or 0),
                                  "修改后层级": payload.get("new_level"), "选择依据": payload["selection_basis"]}}
        elif effective_action == "merge_node":
            payload = candidate.action_payload
            required_keys = ("source_node_id", "target_node_id", "equivalence_evidence",
                             "affected_child_count", "reference_count")
            if any(payload.get(key) in (None, "") for key in required_keys):
                return self._invalid(candidate, "合并节点必须包含语义等价证据、迁移子节点和引用影响范围。", normalize_new)
            preview = {"action_type": effective_action,
                       "before": {"源节点": payload.get("source_node_name") or f"ID {payload['source_node_id']}"},
                       "after": {"保留节点": payload.get("target_node_name") or f"ID {payload['target_node_id']}",
                                 "合并后同义词": payload.get("merged_synonyms") or []},
                       "impact": {"迁移子节点": payload["affected_child_count"], "影响引用数量": payload["reference_count"],
                                  "等价证据": payload["equivalence_evidence"]}}
        elif effective_action == "add_node" and code == "missing_parent":
            payload = candidate.action_payload
            required = (payload.get("missing_parent_id") or payload.get("category_id"), payload.get("parent_id"),
                        payload.get("new_name"), payload.get("subject_node_id"), payload.get("new_parent_path"),
                        payload.get("new_path"), payload.get("nearest_valid_ancestor_id"))
            if any(value in (None, "") for value in required):
                return self._invalid(candidate, "补建父节点缺少名称、挂载位置、路径或最近有效祖先。", normalize_new)
            impact_scope = payload.get("impact_scope") or {}
            preview = {"action_type": effective_action,
                       "before": {"当前节点 ID": payload["subject_node_id"],
                                  "当前节点名称": issue.get("subject_node_name") or issue.get("node_name"),
                                  "缺失父节点 ID": payload.get("missing_parent_id") or payload.get("category_id"),
                                  "当前完整路径": payload.get("current_path") or issue.get("subject_path") or issue.get("path"),
                                  "最近有效祖先节点 ID": payload.get("nearest_valid_ancestor_id"),
                                  "最近有效祖先节点名称": payload.get("nearest_valid_ancestor_name")},
                       "after": {"需要创建或恢复的父节点名称": payload["new_name"],
                                 "新父节点挂载位置": payload["new_parent_path"],
                                 "当前节点修改后的父节点": payload.get("missing_parent_id") or payload.get("category_id"),
                                 "修改后的完整路径": payload["new_path"]},
                       "action": payload.get("action") or {"type": "create_missing_parent", "label": "补建缺失父节点"},
                       "impact_scope": impact_scope, "impact": impact_scope}
        elif effective_action in {"add_node", "split_subtree", "deprecate_node", "delete_leaf_node"}:
            preview = {
                "action_type": effective_action,
                "before": {"目标节点": candidate.target_node_name or candidate.target_node_id or "-"},
                "after": {"动作结果": candidate.suggestion},
                "impact": candidate.action_payload.get("impact") or {},
            }
        else:
            return self._invalid(candidate, f"动作“{effective_action}”不能证明可直接解决当前诊断问题。", normalize_new)
        preview.setdefault("action", {"type": effective_action})
        impact_scope = preview.get("impact_scope") or preview.get("impact") or {}
        preview["impact_scope"] = impact_scope
        preview["impact"] = impact_scope
        if candidate.risk_level == "high" and (
            not preview.get("before") or not preview.get("after") or not preview.get("impact")
        ):
            return self._invalid(candidate, "高风险动作缺少修改前后或影响范围，不能进入正式审核。", normalize_new)
        return ConsistencyResult(candidate, True, True, None, preview)

    def require_executable(self, suggestion: AdjustmentSuggestion) -> ConsistencyResult:
        result = self.check(suggestion)
        if not result.valid:
            raise ValueError(result.reason or "建议一致性校验失败。")
        return result

    def _invalid(self, suggestion: AdjustmentSuggestion, reason: str, downgrade: bool) -> ConsistencyResult:
        if not downgrade:
            return ConsistencyResult(suggestion, False, False, reason, {})
        payload = {"no_change_reason": reason, "confirmation_required": suggestion.suggestion}
        downgraded = suggestion.model_copy(update={"action_type": "review_only", "action_payload": payload,
                                                    "suggestion": f"暂不执行修改：{reason}"})
        preview = {"action_type": "review_only", "before": {}, "after": {},
                   "details": {"不修改原因": reason, "需要人工确认的内容": suggestion.suggestion}}
        preview.update({"action": {"type": "needs_manual_edit"}, "impact_scope": {}, "impact": {}})
        preview["details"]["needs_manual_edit"] = True
        return ConsistencyResult(downgraded, True, False, reason, preview, True)

    @staticmethod
    def _list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []
