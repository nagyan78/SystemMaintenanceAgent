import json
from typing import Any

from langchain_core.tools import tool

from backend.app.config import Settings, get_settings
from backend.app.db import connect
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.suggestion import ActionValidationResult, AdjustmentSuggestion

_runtime_settings: Settings = get_settings()
REMOVE_SYNONYM_KEYS = (
    "synonyms_to_remove",
    "remove_synonyms",
    "removed_synonyms",
    "syn_to_remove",
    "synonyms_to_delete",
)
SINGLE_REMOVE_SYNONYM_KEYS = ("remove_synonym", "target_synonym", "synonym_to_remove")
FINAL_SYNONYM_KEYS = (
    "new_syn_list",
    "updated_synonyms",
    "final_syn_list",
    "remaining_synonyms",
    "keep_synonyms",
    "synonyms",
)
MOVE_PARENT_KEYS = ("new_parent_id", "to_parent_id", "destination_parent_id", "target_parent_id")

ALLOWED_ACTION_TYPES = {
    "add_node",
    "move_node",
    "rename_node",
    "merge_node",
    "clean_synonym",
    "split_subtree",
    "mark_as_valid",
}


def configure_validation_tool_runtime(settings: Settings) -> None:
    global _runtime_settings
    _runtime_settings = settings


@tool
def validate_action(action_json: str) -> dict:
    """预校验维护建议动作是否合法。"""
    try:
        payload = json.loads(action_json) if isinstance(action_json, str) else action_json
        suggestion = AdjustmentSuggestion.model_validate(payload)
    except Exception as exc:
        return ActionValidationResult(valid=False, reason=f"建议 JSON 结构非法：{exc}").model_dump()
    result = validate_suggestion_action(suggestion, _runtime_settings)
    return result.model_dump()


def validate_suggestion_action(
    suggestion: AdjustmentSuggestion,
    settings: Settings | None = None,
) -> ActionValidationResult:
    runtime_settings = settings or _runtime_settings
    if suggestion.action_type not in ALLOWED_ACTION_TYPES:
        return _invalid("action_type 不在允许枚举中。")
    if suggestion.risk_level not in {"low", "medium", "high"}:
        return _invalid("risk_level 必须是 low、medium 或 high。")
    if not 0 <= suggestion.confidence <= 1:
        return _invalid("confidence 必须在 0 到 1 之间。")
    if suggestion.need_confirm is False and suggestion.risk_level in {"medium", "high"}:
        return _invalid("中高风险建议必须 need_confirm=true。")
    if not _issue_exists(runtime_settings, suggestion.version_id, suggestion.issue_id):
        return _invalid("issue_id 不存在。")
    if suggestion.action_type != "add_node" and suggestion.target_node_id is None:
        return _invalid("非 add_node 建议必须包含 target_node_id。")
    if suggestion.target_node_id is not None:
        taxonomy_repo = TaxonomyRepository(runtime_settings)
        node = taxonomy_repo.get_node_detail(
            suggestion.version_id,
            suggestion.target_node_id,
        )
        if node is None:
            return _invalid("target_node_id 不存在。")
        if suggestion.action_type == "clean_synonym":
            try:
                resolve_clean_synonym_update(node.get("syn_list") or "", suggestion.action_payload)
            except ValueError as exc:
                return _invalid(str(exc))
        if suggestion.action_type == "rename_node":
            new_name = (suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
            if not new_name:
                return _invalid("rename_node 必须包含非空 new_name。")
            siblings = [
                item
                for item in taxonomy_repo.list_nodes(suggestion.version_id)
                if item["parent_id"] == node["parent_id"]
                and item["category_id"] != suggestion.target_node_id
            ]
            if any(item["category_name"] == new_name for item in siblings):
                return _invalid("同级节点下已存在相同名称。")
    if suggestion.action_type == "add_node":
        new_name = (suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
        parent_id = suggestion.new_parent_id or suggestion.action_payload.get("parent_id")
        if not new_name or parent_id is None:
            return _invalid("add_node 必须包含非空 new_name 和 parent_id。")
        if TaxonomyRepository(runtime_settings).get_node_detail(
            suggestion.version_id,
            int(parent_id),
        ) is None:
            return _invalid("add_node 的 parent_id 不存在。")
    if suggestion.action_type == "move_node":
        has_parent, new_parent_id = extract_move_new_parent_id(suggestion)
        if not has_parent:
            return _invalid("move_node 必须包含 new_parent_id。")
        if new_parent_id is None:
            return ActionValidationResult(valid=True)
        if suggestion.target_node_id == new_parent_id:
            return _invalid("move_node 不能移动到自身下。")
        if TaxonomyRepository(runtime_settings).get_node_detail(
            suggestion.version_id,
            int(new_parent_id),
        ) is None:
            return _invalid("new_parent_id 不存在。")
        if TaxonomyRepository(runtime_settings).is_descendant(
            suggestion.version_id,
            suggestion.target_node_id,
            int(new_parent_id),
        ):
            return _invalid("move_node 不能移动到自身子树下。")
    if suggestion.action_type == "merge_node":
        if not suggestion.action_payload.get("source_node_id") or not suggestion.action_payload.get("target_node_id"):
            return _invalid("merge_node 必须包含 source_node_id 和 target_node_id。")
    return ActionValidationResult(valid=True)


def validate_suggestion_records(
    suggestions: list[AdjustmentSuggestion],
    settings: Settings | None = None,
) -> list[ActionValidationResult]:
    return [validate_suggestion_action(item, settings) for item in suggestions]


def _issue_exists(settings: Settings, version_id: int, issue_id: int) -> bool:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT 1 FROM diagnosis_issue WHERE id = ? AND version_id = ? LIMIT 1",
            (issue_id, version_id),
        ).fetchone()
    return row is not None


def _missing_synonyms(syn_list: str, synonyms_to_remove: list[Any]) -> list[str]:
    existing = {item.strip() for item in syn_list.replace("，", ",").split(",") if item.strip()}
    return [str(item) for item in synonyms_to_remove if str(item) not in existing]


def _invalid(reason: str) -> ActionValidationResult:
    return ActionValidationResult(valid=False, reason=reason)


def extract_move_new_parent_id(suggestion: AdjustmentSuggestion) -> tuple[bool, Any]:
    if suggestion.new_parent_id is not None:
        return True, suggestion.new_parent_id
    for key in MOVE_PARENT_KEYS:
        if key in suggestion.action_payload:
            return True, suggestion.action_payload.get(key)
    return False, None


def resolve_clean_synonym_update(syn_list: str, payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    current_terms = _split_synonyms(syn_list)
    final_terms = _extract_final_synonyms(payload)
    if final_terms is not None:
        added_terms = [item for item in final_terms if item not in current_terms]
        if added_terms:
            raise ValueError(f"clean_synonym 不能新增当前不存在的同义词：{', '.join(added_terms)}")
        removed_terms = [item for item in current_terms if item not in final_terms]
        if not removed_terms:
            raise ValueError("clean_synonym 缺少待移除同义词或目标同义词列表。")
        return final_terms, removed_terms

    remove_terms = _extract_remove_synonyms(payload)
    if not remove_terms:
        raise ValueError("clean_synonym 缺少待移除同义词或目标同义词列表。")
    missing = [item for item in remove_terms if item not in current_terms]
    if missing:
        raise ValueError(f"待删除同义词不存在：{', '.join(missing)}")
    return [item for item in current_terms if item not in remove_terms], remove_terms


def _extract_remove_synonyms(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in REMOVE_SYNONYM_KEYS:
        values.extend(_normalize_synonym_values(payload.get(key)))
    for key in SINGLE_REMOVE_SYNONYM_KEYS:
        values.extend(_normalize_synonym_values(payload.get(key)))
    return _unique_non_empty(values)


def _extract_final_synonyms(payload: dict[str, Any]) -> list[str] | None:
    for key in FINAL_SYNONYM_KEYS:
        if key in payload:
            return _unique_non_empty(_normalize_synonym_values(payload.get(key)))
    return None


def _normalize_synonym_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return _split_synonyms(text)
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(_normalize_synonym_values(item))
        return values
    return [str(value).strip()] if str(value).strip() else []


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _split_synonyms(syn_list: str) -> list[str]:
    return [item.strip() for item in syn_list.replace("，", ",").split(",") if item.strip()]
