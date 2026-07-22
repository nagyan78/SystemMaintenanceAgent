import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.schemas.issue import ContentIssue, ContentSampleAssessment


@dataclass(frozen=True)
class BatchDiagnosisResult:
    assessments: list[ContentSampleAssessment]
    model_calls: int
    tokens_used: int
    warning: str | None = None


class BatchContentDiagnosisService:
    """Analyze compact candidate batches without tools or ReAct loops."""

    def __init__(self, llm: Any, *, batch_size: int = 10, max_attempts: int = 2) -> None:
        self.llm = llm
        self.batch_size = max(1, batch_size)
        self.max_attempts = max(1, max_attempts)

    def analyze(
        self,
        candidates: list[dict[str, Any]],
        *,
        deadline: float,
        max_calls: int,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> BatchDiagnosisResult:
        assessments: list[ContentSampleAssessment] = []
        warnings: list[str] = []
        calls = tokens = 0
        for offset in range(0, len(candidates), self.batch_size):
            batch = candidates[offset:offset + self.batch_size]
            if time.monotonic() >= deadline or calls >= max_calls:
                assessments.extend(_uncertain(item, "AI 分析达到运行预算，未继续处理。") for item in batch)
                assessments.extend(
                    _uncertain(item, "AI 分析达到运行预算，未继续处理。")
                    for item in candidates[offset + self.batch_size:]
                )
                warnings.append("AI 分析达到运行预算。")
                break
            parsed: dict[int, ContentSampleAssessment] | None = None
            last_error: Exception | None = None
            for _attempt in range(self.max_attempts):
                if time.monotonic() >= deadline or calls >= max_calls:
                    break
                try:
                    response = self.llm.invoke(_messages(batch))
                except Exception as exc:
                    calls += 1
                    last_error = exc
                    if event_sink:
                        event_sink({"model_calls": 1, "total_tokens": 0})
                    continue
                calls += 1
                usage = getattr(response, "usage_metadata", None) or {}
                call_tokens = int(usage.get("total_tokens", 0) or 0)
                tokens += call_tokens
                if event_sink:
                    event_sink({"model_calls": 1, "total_tokens": call_tokens})
                try:
                    parsed = _parse_assessments(str(response.content), batch)
                    break
                except Exception as exc:
                    last_error = exc
            if parsed is None:
                reason = f"批量 AI 分析失败：{type(last_error).__name__ if last_error else 'budget_exhausted'}。"
                warnings.append(reason)
                assessments.extend(_uncertain(item, reason) for item in batch)
                continue
            for candidate in batch:
                node_id = int(candidate["category_id"])
                assessments.append(parsed.get(node_id) or _uncertain(candidate, "AI 未返回该候选的有效结论。"))
        return BatchDiagnosisResult(assessments, calls, tokens, "；".join(warnings) or None)


def _messages(candidates: list[dict[str, Any]]) -> list[Any]:
    compact = [
        {
            "node_id": int(item["category_id"]),
            "node_name": item.get("category_name"),
            "parent_id": item.get("parent_id"),
            "level": item.get("level"),
            "path": item.get("path_names"),
            "synonyms": item.get("syn_list"),
            "is_leaf": item.get("is_leaf"),
        }
        for item in candidates
    ]
    return [
        SystemMessage(content=(
            "你是产品分类体系内容审核 AI。一次判断输入中的全部候选，不调用工具，不输出思维过程。"
            "只输出 JSON 对象：{\"assessments\":[{\"node_id\":1,"
            "\"conclusion\":\"reasonable|problem|uncertain\",\"issue_type\":null,"
            "\"reason\":\"简短结论\",\"evidence\":\"名称或路径证据\","
            "\"risk_level\":\"low|medium|high\",\"confidence\":0.8}]}。"
            "problem 必须给出 issue_type；证据不足时使用 uncertain。"
        )),
        HumanMessage(content=json.dumps({"candidates": compact}, ensure_ascii=False)),
    ]


def _parse_assessments(text: str, candidates: list[dict[str, Any]]) -> dict[int, ContentSampleAssessment]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("batch diagnosis did not return JSON")
    payload = json.loads(text[start:end + 1])
    known = {int(item["category_id"]): item for item in candidates}
    result: dict[int, ContentSampleAssessment] = {}
    for value in payload.get("assessments", []):
        if not isinstance(value, dict):
            continue
        node_id = int(value.get("node_id", 0) or 0)
        candidate = known.get(node_id)
        conclusion = str(value.get("conclusion") or "uncertain")
        if candidate is None or conclusion not in {"reasonable", "problem", "uncertain"}:
            continue
        issue = None
        if conclusion == "problem":
            issue_type = str(value.get("issue_type") or "naming_irregular")
            reason = str(value.get("reason") or "AI 判断内容存在问题")
            path = candidate.get("path_names")
            issue = ContentIssue(
                issue_type=issue_type,
                node_id=node_id,
                node_name=candidate.get("category_name"),
                description=reason,
                reason=reason,
                risk_level=str(value.get("risk_level") or "low"),
                confidence=max(0.0, min(float(value.get("confidence", 0.0) or 0.0), 1.0)),
                path=path,
                evidence=str(value.get("evidence") or path or reason),
                source="model_analysis",
            )
        result[node_id] = ContentSampleAssessment(
            conclusion=conclusion,
            node_id=node_id,
            node_name=candidate.get("category_name"),
            reason=str(value.get("reason") or "AI 未提供判断摘要"),
            issue=issue,
        )
    if not result:
        raise ValueError("batch diagnosis returned no valid assessments")
    return result


def _uncertain(candidate: dict[str, Any], reason: str) -> ContentSampleAssessment:
    return ContentSampleAssessment(
        conclusion="uncertain",
        node_id=int(candidate["category_id"]),
        node_name=candidate.get("category_name"),
        reason=reason,
    )
