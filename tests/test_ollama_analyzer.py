"""Tests for semantic AI prompt construction."""

from __future__ import annotations

import json
import re

import pandas as pd

from src.advanced.ollama_analyzer import _build_prompt, _normalize_judgement
from src.advanced.tree_builder import enrich_tree_fields


def _prompt_payload(prompt: str) -> dict:
    marker = "待分析节点信息："
    assert marker in prompt
    return json.loads(prompt.split(marker, 1)[1])


def test_wide_node_prompt_uses_node_names_without_rule_text() -> None:
    df = enrich_tree_fields(pd.DataFrame([
        {"category_id": "root", "category_name": "Components", "parent_id": ""},
        {"category_id": "p", "category_name": "Optical Module", "parent_id": "root"},
        {"category_id": "sibling", "category_name": "Optical Cable", "parent_id": "root"},
        {"category_id": "c1", "category_name": "Single Mode Optical Module", "parent_id": "p"},
        {"category_id": "c2", "category_name": "400G Optical Module", "parent_id": "p"},
        {"category_id": "c3", "category_name": "QSFP Optical Module", "parent_id": "p"},
    ]))
    issue = {
        "issue_type": "branch_wide",
        "node_id": "p",
        "node_name": "Optical Module",
        "evidence": "RULE_EVIDENCE_BRANCH_RATIO_TOO_HIGH",
        "suggestion": "RULE_SUGGESTION_ADD_MIDDLE_GROUP",
    }

    prompt = _build_prompt(issue, df, {"total_nodes": 6, "leaf_ratio": 0.5})
    payload = _prompt_payload(prompt)

    assert "RULE_EVIDENCE_BRANCH_RATIO_TOO_HIGH" not in prompt
    assert "RULE_SUGGESTION_ADD_MIDDLE_GROUP" not in prompt
    assert "metric_value" not in prompt
    assert "rule_reason" not in prompt
    assert payload["node_context"]["current_node_name"] == "Optical Module"
    assert payload["node_context"]["direct_child_names"] == [
        "Single Mode Optical Module",
        "400G Optical Module",
        "QSFP Optical Module",
    ]
    assert payload["node_context"]["sibling_node_names"] == ["Optical Cable"]


def test_duplicate_name_prompt_uses_same_name_paths() -> None:
    df = enrich_tree_fields(pd.DataFrame([
        {"category_id": "r1", "category_name": "Industrial Products", "parent_id": ""},
        {"category_id": "a", "category_name": "Battery", "parent_id": "r1"},
        {"category_id": "r2", "category_name": "Consumer Products", "parent_id": ""},
        {"category_id": "b", "category_name": "Battery", "parent_id": "r2"},
    ]))
    issue = {"issue_type": "duplicate_category_name", "node_id": "a", "node_name": "Battery"}

    prompt = _build_prompt(issue, df, {"total_nodes": 4, "leaf_ratio": 0.5})
    payload = _prompt_payload(prompt)

    assert payload["node_context"]["duplicate_node_name"] == "Battery"
    assert payload["node_context"]["same_name_paths"] == [
        ["Industrial Products", "Battery"],
        ["Consumer Products", "Battery"],
    ]


def test_name_redundancy_prompt_includes_parent_child_and_siblings() -> None:
    df = enrich_tree_fields(pd.DataFrame([
        {"category_id": "p", "category_name": "Optical Module", "parent_id": ""},
        {"category_id": "c1", "category_name": "Single Mode Optical Module", "parent_id": "p"},
        {"category_id": "c2", "category_name": "Multi Mode Optical Module", "parent_id": "p"},
    ]))
    issue = {"issue_type": "suspicious_name_redundancy", "node_id": "c1", "node_name": "Single Mode Optical Module"}

    prompt = _build_prompt(issue, df, {"total_nodes": 3, "leaf_ratio": 0.67})
    payload = _prompt_payload(prompt)

    assert payload["node_context"]["parent_child_pair"] == {
        "parent_name": "Optical Module",
        "child_name": "Single Mode Optical Module",
    }
    assert payload["node_context"]["sibling_node_names"] == ["Multi Mode Optical Module"]


def test_normalize_judgement_uses_relevant_nodes_and_legacy_key_nodes() -> None:
    judgement = {
        "is_problem": True,
        "confidence": "0.78",
        "key_nodes": "Single Mode Optical Module,400G Optical Module",
        "semantic_relation": "The children mix mode and speed dimensions.",
        "reason": "The node names show multiple classification dimensions.",
        "suggestion": "Group children by semantic dimension.",
    }

    _normalize_judgement(judgement)

    assert judgement["is_problem"] is True
    assert judgement["confidence"] == 0.78
    assert judgement["relevant_nodes"] == ["Single Mode Optical Module", "400G Optical Module"]
    assert judgement["semantic_relation"] == "The children mix mode and speed dimensions."
    assert judgement["result_source"] == "ai_semantic"
