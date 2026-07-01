"""LLM semantic judgement using LangChain structured output."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from config import Settings, settings
from prompts import PARENT_CHILD_JUDGE_PROMPT, SYNONYM_JUDGE_PROMPT

try:
    from langchain.chat_models import init_chat_model
except ImportError:  # pragma: no cover - lets rule-only mode run before LangChain is installed.
    init_chat_model = None


logger = logging.getLogger(__name__)


class LLMJudgement(BaseModel):
    """Structured output schema expected from the model."""

    is_problem: bool = Field(description="Whether the checked item is a real problem.")
    problem_type: str = Field(description="Problem category, such as wrong_parent or wrong_synonym.")
    reason: str = Field(description="Short reason for the judgement.")
    suggestion: str = Field(description="Concrete maintenance suggestion.")
    confidence: float = Field(ge=0, le=1, description="Confidence between 0 and 1.")


def judge_parent_child_issues(
    issues: list[dict[str, Any]],
    df: pd.DataFrame,
    app_settings: Settings = settings,
) -> list[dict[str, Any]]:
    """Use LLM to judge candidate parent-child relationship issues."""

    return _judge_issues(issues, df, PARENT_CHILD_JUDGE_PROMPT, app_settings)


def judge_synonym_issues(
    issues: list[dict[str, Any]],
    df: pd.DataFrame,
    app_settings: Settings = settings,
) -> list[dict[str, Any]]:
    """Use LLM to judge candidate synonym issues."""

    return _judge_issues(issues, df, SYNONYM_JUDGE_PROMPT, app_settings)


def _judge_issues(
    issues: list[dict[str, Any]],
    df: pd.DataFrame,
    prompt_template: str,
    app_settings: Settings,
) -> list[dict[str, Any]]:
    if not issues:
        return []
    if init_chat_model is None:
        logger.info("LangChain is not installed. Skipping LLM semantic judgement.")
        return []
    if not app_settings.has_llm_config:
        logger.info("LLM config or API key not found. Skipping LLM semantic judgement.")
        return []

    try:
        model = init_chat_model(
            model=app_settings.model_name,
            model_provider=app_settings.model_provider,
            temperature=0,
        ).with_structured_output(LLMJudgement)
    except Exception as exc:
        logger.warning("Could not initialize LLM. Skipping LLM judgement: %s", exc)
        return []

    rows = df.set_index("category_id", drop=False)
    results: list[dict[str, Any]] = []
    for issue in issues:
        category_id = str(issue.get("category_id", ""))
        row = rows.loc[category_id].to_dict() if category_id in rows.index else {}
        prompt = prompt_template.format(
            parent_name=row.get("parent_name", ""),
            category_name=issue.get("category_name", ""),
            synonyms=row.get("synonyms", ""),
            path=issue.get("path", ""),
            evidence=issue.get("evidence", ""),
        )
        try:
            judgement = model.invoke(prompt)
            payload = judgement.model_dump() if isinstance(judgement, BaseModel) else dict(judgement)
            results.append({**issue, "llm_judgement": payload})
        except Exception as exc:
            logger.warning("LLM judgement failed for category_id=%s: %s", category_id, exc)
    return results
