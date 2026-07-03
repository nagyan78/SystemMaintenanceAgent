"""Ollama-powered semantic analysis for taxonomy issues."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd

from .config import Settings, settings

try:
    from langchain_ollama import ChatOllama
except ImportError:  # pragma: no cover - AI analysis is optional.
    ChatOllama = None


logger = logging.getLogger(__name__)

AI_RELEVANT_TYPES = {
    "branch_explosion",
    "branch_wide",
    "deep_node",
    "duplicate_category_name",
    "leaf_ratio_abnormal",
    "redundant_single_child_chain",
    "same_name_parent_child",
    "suspicious_parent_child",
    "suspicious_name_redundancy",
    "suspicious_synonym",
}


def run_ai_analysis(
    df: pd.DataFrame,
    issues: list[dict[str, Any]],
    summary: dict[str, Any],
    app_settings: Settings = settings,
) -> list[dict[str, Any]]:
    """Analyze selected rule candidates with local Ollama and merge semantic results."""

    if not _should_run(app_settings):
        return issues

    candidates = _select_candidates(issues, app_settings.ai_max_items)
    if not candidates:
        return issues

    model = _build_model(app_settings)
    if model is None:
        return issues

    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for issue in candidates:
        prompt = _build_prompt(issue, df, summary)
        try:
            response = model.invoke(prompt)
            content = getattr(response, "content", str(response))
            judgement = _parse_json(content)
            _normalize_judgement(judgement)
            by_key[_issue_key(issue)] = judgement
        except Exception as exc:  # noqa: BLE001 - local AI must not break diagnosis.
            logger.warning("Ollama analysis failed for %s/%s: %s", issue.get("issue_type"), issue.get("node_id"), exc)
            by_key[_issue_key(issue)] = _failed_rule_fallback(issue, exc)

    merged: list[dict[str, Any]] = []
    for issue in issues:
        updated = dict(issue)
        judgement = by_key.get(_issue_key(issue))
        if judgement:
            updated["ai_judgement"] = judgement
            updated["ai_confirmed"] = bool(judgement.get("is_problem"))
            updated["ai_confidence"] = judgement.get("confidence", 0)
            updated["ai_reason"] = judgement.get("reason", "")
            updated["ai_suggestion"] = judgement.get("suggestion", "")
            updated["need_manual_check"] = True
            updated["need_manual_review"] = True
        merged.append(updated)
    return merged


def _failed_rule_fallback(issue: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "is_problem": False,
        "confidence": 0,
        "relevant_nodes": [],
        "semantic_relation": "",
        "reason": f"AI调用失败：{exc}",
        "suggestion": "本条未获得AI语义判断，请查看规则命中依据并人工复核。",
        "result_source": "rule_result",
        "analysis_failed": True,
        "rule_reason": str(issue.get("evidence") or issue.get("reason") or ""),
        "rule_suggestion": str(issue.get("suggestion") or ""),
    }


def _should_run(app_settings: Settings) -> bool:
    if not app_settings.enable_ai_analysis:
        logger.info("AI analysis is disabled. Set ENABLE_AI_ANALYSIS=true to enable it.")
        return False
    if app_settings.model_provider.lower() != "ollama":
        logger.info("AI analysis only uses Ollama in this flow. MODEL_PROVIDER=%s", app_settings.model_provider)
        return False
    if not app_settings.model_name:
        logger.info("MODEL_NAME is empty. Skipping Ollama analysis.")
        return False
    if ChatOllama is None:
        logger.info("langchain-ollama is not installed. Skipping Ollama analysis.")
        return False
    return True


def _build_model(app_settings: Settings) -> Any | None:
    try:
        return ChatOllama(
            model=app_settings.model_name,
            base_url=app_settings.ollama_base_url,
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001 - optional local model.
        logger.warning("Could not initialize Ollama model: %s", exc)
        return None


def _select_candidates(issues: list[dict[str, Any]], max_items: int) -> list[dict[str, Any]]:
    candidates = [
        issue
        for issue in issues
        if str(issue.get("issue_type", "")) in AI_RELEVANT_TYPES
    ]
    candidates.sort(key=_candidate_sort_key)
    limit_per_type = max(0, max_items)
    if limit_per_type == 0:
        return []

    selected: list[dict[str, Any]] = []
    counts_by_type: dict[str, int] = {}
    for issue in candidates:
        issue_type = str(issue.get("issue_type", ""))
        if counts_by_type.get(issue_type, 0) >= limit_per_type:
            continue
        selected.append(issue)
        counts_by_type[issue_type] = counts_by_type.get(issue_type, 0) + 1
    return selected


def _candidate_sort_key(issue: dict[str, Any]) -> tuple[int, int, str]:
    ai_rank = {"high": 0, "medium": 1, "low": 2}.get(str(issue.get("ai_dependency", "low")), 3)
    severity_rank = {"high": 0, "medium": 1, "low": 2}.get(str(issue.get("severity", "low")), 3)
    return (ai_rank, severity_rank, str(issue.get("path", "")))


def _build_prompt(issue: dict[str, Any], df: pd.DataFrame, summary: dict[str, Any]) -> str:
    del summary  # Summary metrics are intentionally not used as semantic evidence.
    issue_type = str(issue.get("issue_type", ""))
    payload = {
        "analysis_focus": _analysis_focus(issue_type),
        "node_context": _issue_context(issue, df),
    }
    return (
        "你是一个产品分类体系语义诊断助手。\n"
        "你的任务不是复述规则检测结果，而是从给定节点信息中提取真正需要语义分析的节点名称，"
        "并判断这些节点之间是否存在分类体系问题。\n\n"
        "请严格按照以下要求输出：\n\n"
        "1. 先提取“必要分析节点”\n"
        "只保留判断该问题所必需的节点名称。\n"
        "不要把规则名称、指标数值、规则建议当作分析依据。\n\n"
        "2. 再进行语义判断\n"
        "根据节点名称、父子关系、路径关系、兄弟关系判断是否真的存在问题。\n\n"
        "3. 禁止输出以下内容：\n"
        "- “分支爆炸比超标”\n"
        "- “节点数量远超平均宽度”\n"
        "- “叶子节点占比为100%”\n"
        "- “父节点名称包含子节点名称”\n"
        "- “建议按业务属性合并”\n"
        "- “建议增加中间分组”\n"
        "- 任何单纯复述规则检测结果的话\n\n"
        "4. 如果规则命中但从语义上看是合理结构，应输出“不确认问题”。\n"
        "例如：父节点“光模块”，子节点“单模光模块”，这通常是合理的上下位分类，"
        "不应仅因为名称包含就确认问题。\n\n"
        "5. 只输出 JSON，格式如下：\n"
        "{\n"
        '  "is_problem": true 或 false,\n'
        '  "confidence": 0到1之间的小数,\n'
        '  "relevant_nodes": ["节点1", "节点2", "节点3"],\n'
        '  "semantic_relation": "说明这些节点之间的语义关系",\n'
        '  "reason": "只写语义原因，不要写规则原因",\n'
        '  "suggestion": "只写基于语义的修改建议，如果不确认问题则写无需调整或建议人工复核"\n'
        "}\n\n"
        f"待分析节点信息：\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _analysis_focus(issue_type: str) -> str:
    if issue_type in {"branch_explosion", "branch_wide"}:
        return "分支偏宽：判断当前节点下的直接子节点是否可以按语义继续分组，必要时参考兄弟节点。"
    if issue_type == "leaf_ratio_abnormal":
        return "叶子占比异常：判断直接叶子子节点是否已经是终极类别，或是否还能按用途、规格、材料、产业环节等维度细分。"
    if issue_type == "duplicate_category_name":
        return "全局重名：判断重复名称在不同完整路径下是否语义相同，是否需要补充限定词。"
    if issue_type == "same_name_parent_child":
        return "父子同名：判断父节点和子节点是否无法体现上下位语义差异。"
    if issue_type == "suspicious_name_redundancy":
        return "疑似名称冗余：判断子节点是否只是父节点的合理细分，还是确实存在冗余命名。"
    if issue_type == "suspicious_synonym":
        return "异常同义词：判断同义词是否与标准名称重复，或是否属于别名、简称、英文名、无效冗余。"
    if issue_type == "suspicious_parent_child":
        return "可疑父子关系：判断父子节点是否存在业务上的上下位关系，必要时参考兄弟节点。"
    if issue_type in {"deep_node", "redundant_single_child_chain"}:
        return "路径层级：判断完整路径中是否存在语义重复、层级冗余或可合并节点。"
    return "判断节点名称之间是否存在分类体系语义问题。"


def _issue_context(issue: dict[str, Any], df: pd.DataFrame) -> dict[str, Any]:
    issue_type = str(issue.get("issue_type", ""))
    node_id = str(issue.get("node_id") or issue.get("category_id") or "")
    row = _row_by_id(df, node_id)
    context: dict[str, Any] = {}

    if row:
        context["current_node_name"] = str(row.get("category_name", ""))
        context["parent_name"] = str(row.get("parent_name", ""))
        context["path_nodes"] = _path_nodes(row.get("path", issue.get("path", "")))
    elif issue.get("path"):
        context["current_node_name"] = str(issue.get("node_name") or issue.get("category_name") or "")
        context["path_nodes"] = _path_nodes(issue.get("path", ""))
    else:
        context["current_node_name"] = str(issue.get("node_name") or issue.get("category_name") or "")

    if issue_type in {"branch_explosion", "branch_wide"}:
        context["direct_child_names"] = _children_sample(df, node_id, limit=40)
        context["sibling_node_names"] = _sibling_sample(df, row, limit=20)
    elif issue_type == "leaf_ratio_abnormal":
        context["direct_leaf_child_names"] = _direct_leaf_children_sample(df, node_id, limit=50)
        context["sample_leaf_descendant_names"] = _leaf_sample(df, node_id, limit=50)
    elif issue_type == "duplicate_category_name":
        duplicate_name = str(issue.get("node_name") or issue.get("category_name") or context.get("current_node_name", ""))
        context["duplicate_node_name"] = duplicate_name
        context["same_name_paths"] = _same_name_paths(df, duplicate_name, limit=30)
    elif issue_type in {"same_name_parent_child", "suspicious_name_redundancy", "suspicious_parent_child"}:
        context["parent_child_pair"] = {
            "parent_name": str(row.get("parent_name", "")) if row else "",
            "child_name": str(row.get("category_name", "")) if row else context.get("current_node_name", ""),
        }
        context["sibling_node_names"] = _sibling_sample(df, row, limit=30)
    elif issue_type == "suspicious_synonym" and row:
        context["standard_node_name"] = str(row.get("category_name", ""))
        context["synonym_names"] = _split_synonym_names(row.get("synonyms", ""))
    elif issue_type in {"deep_node", "redundant_single_child_chain"}:
        context["path_nodes"] = context.get("path_nodes") or _path_nodes(issue.get("path", ""))

    return _drop_empty(context)


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in ("", [], {}, None)
    }


def _row_by_id(df: pd.DataFrame, node_id: str) -> dict[str, Any]:
    if not node_id or node_id == "GLOBAL" or "category_id" not in df.columns:
        return {}
    matches = df[df["category_id"].astype(str) == node_id]
    if matches.empty:
        return {}
    return matches.iloc[0].to_dict()


def _path_nodes(path: Any) -> list[str]:
    return [part.strip() for part in str(path or "").split(">") if part.strip()]


def _children_sample(df: pd.DataFrame, node_id: str, limit: int) -> list[str]:
    if not node_id or "parent_id" not in df.columns:
        return []
    children = df[df["parent_id"].astype(str) == node_id].head(limit)
    return _name_list(children)


def _direct_leaf_children_sample(df: pd.DataFrame, node_id: str, limit: int) -> list[str]:
    if not node_id or "parent_id" not in df.columns or "is_leaf" not in df.columns:
        return []
    children = df[(df["parent_id"].astype(str) == node_id) & (df["is_leaf"].astype(bool))].head(limit)
    return _name_list(children)


def _leaf_sample(df: pd.DataFrame, node_id: str, limit: int) -> list[str]:
    if "is_leaf" not in df.columns:
        return []
    leaves = df[df["is_leaf"].astype(bool)]
    if node_id and node_id != "GLOBAL":
        row = _row_by_id(df, node_id)
        base_path = str(row.get("path", "")) if row else ""
        if base_path:
            leaves = leaves[leaves["path"].astype(str).str.startswith(base_path + " > ")]
    return _name_list(leaves.head(limit))


def _sibling_sample(df: pd.DataFrame, row: dict[str, Any], limit: int) -> list[str]:
    if not row or "parent_id" not in df.columns:
        return []
    parent_id = str(row.get("parent_id", ""))
    node_id = str(row.get("category_id", ""))
    siblings = df[(df["parent_id"].astype(str) == parent_id) & (df["category_id"].astype(str) != node_id)].head(limit)
    return _name_list(siblings)


def _name_list(rows: pd.DataFrame) -> list[str]:
    return [
        str(row.get("category_name", "")).strip()
        for _, row in rows.iterrows()
        if str(row.get("category_name", "")).strip()
    ]


def _same_name_paths(df: pd.DataFrame, node_name: str, limit: int) -> list[list[str]]:
    if not node_name or "category_name" not in df.columns:
        return []
    matches = df[df["category_name"].astype(str).str.strip() == node_name].head(limit)
    return [_path_nodes(row.get("path", "")) for _, row in matches.iterrows()]


def _split_synonym_names(value: Any) -> list[str]:
    parts = re.split(r"[,;；，、|/]+", str(value or ""))
    return [part.strip() for part in parts if part.strip()]


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = re.sub(r"<think>.*?</think>", "", str(content), flags=re.DOTALL | re.IGNORECASE).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama response JSON is not an object.")
    return parsed


def _normalize_judgement(judgement: dict[str, Any]) -> None:
    judgement["is_problem"] = bool(judgement.get("is_problem", judgement.get("has_problem", False)))
    try:
        confidence = float(judgement.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    judgement["confidence"] = max(0.0, min(1.0, confidence))
    judgement["relevant_nodes"] = _normalize_node_names(
        judgement.get("relevant_nodes", judgement.get("key_nodes", []))
    )
    judgement["semantic_relation"] = str(judgement.get("semantic_relation", "")).strip()
    judgement["reason"] = str(judgement.get("reason", "")).strip()
    judgement["suggestion"] = str(judgement.get("suggestion", "")).strip()
    judgement["result_source"] = "ai_semantic"


def _normalize_node_names(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;；，、|/]+", value) if item.strip()]
    return []


def _issue_key(issue: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(issue.get("issue_type", "")),
        str(issue.get("node_id") or issue.get("category_id", "")),
        str(issue.get("evidence") or issue.get("reason", "")),
    )
