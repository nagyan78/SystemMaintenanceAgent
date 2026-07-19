import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.schemas.suggestion import SuggestionRecord


@dataclass(frozen=True)
class AIReviewResult:
    completed: bool
    decisions: list[dict[str, Any]]
    warning: str | None = None


class AIReviewService:
    """Obtain an independent product-level judgment over generated actions.

    This reviewer never edits data. Deterministic validation and snapshot
    simulation remain the execution gate; review output is retained as a
    decision summary instead of chain-of-thought.
    """

    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def review(self, suggestions: list[SuggestionRecord]) -> AIReviewResult:
        decisions: list[dict[str, Any]] = []
        warnings: list[str] = []
        for index in range(0, len(suggestions), 10):
            result = self._review_batch(suggestions[index:index + 10])
            decisions.extend(result.decisions)
            if result.warning:
                warnings.append(result.warning)
        known = {item.id for item in suggestions}
        completed = len({item["suggestion_id"] for item in decisions}) == len(known)
        return AIReviewResult(completed, decisions, "；".join(warnings) or None)

    def _review_batch(self, suggestions: list[SuggestionRecord]) -> AIReviewResult:
        payload = [
            {
                "suggestion_id": item.id,
                "issue_id": item.issue_id,
                "action_type": item.action_type,
                "target_node_id": item.target_node_id,
                "new_parent_id": item.new_parent_id,
                "old_name": item.old_name,
                "new_name": item.new_name,
                "risk_level": item.risk_level,
                "reason": item.reason,
                "action_payload": item.action_payload,
            }
            for item in suggestions
        ]
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(
                        content=(
                            "你是独立的产品分类体系修改复核 AI。逐条判断方案是否与问题、目标节点和产品语义一致。"
                            "不得要求人工介入，也不得仅因风险高而拒绝删除、合并或整棵子树迁移。"
                            "只输出 JSON：{\"decisions\":[{\"suggestion_id\":1,\"verdict\":\"approve|concern\","
                            "\"decision_summary\":\"简短复核结论\"}]}。不要输出思维过程。"
                        )
                    ),
                    HumanMessage(content=json.dumps({"suggestions": payload}, ensure_ascii=False)),
                ]
            )
            parsed = _extract_json(str(response.content))
            known = {item.id for item in suggestions}
            decisions = [
                item for item in parsed.get("decisions", [])
                if isinstance(item, dict) and item.get("suggestion_id") in known
                and item.get("verdict") in {"approve", "concern"}
            ]
            if len({item["suggestion_id"] for item in decisions}) != len(known):
                return AIReviewResult(False, decisions, "独立 AI 复核返回不完整；已保留现有方案并继续确定性校验。")
            return AIReviewResult(True, decisions)
        except Exception as exc:
            return AIReviewResult(False, [], f"独立 AI 复核不可用：{type(exc).__name__}；已保留现有方案并继续确定性校验。")


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("AI review did not return a JSON object")
    result = json.loads(value[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("AI review JSON must be an object")
    return result
