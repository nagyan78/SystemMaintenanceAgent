"""Compare two product category versions."""

from __future__ import annotations

from typing import Any

import pandas as pd


COMPARE_COLUMNS = ["category_name", "parent_id", "synonyms"]


def compare_versions(old_df: pd.DataFrame, new_df: pd.DataFrame) -> dict[str, Any]:
    """Compare old and new DataFrames by category_id."""

    old = old_df.set_index("category_id", drop=False)
    new = new_df.set_index("category_id", drop=False)
    old_ids = set(old.index)
    new_ids = set(new.index)

    added_ids = sorted(new_ids - old_ids)
    deleted_ids = sorted(old_ids - new_ids)
    common_ids = sorted(old_ids & new_ids)

    changed = {
        "name_changes": [],
        "parent_changes": [],
        "synonym_changes": [],
    }

    for category_id in common_ids:
        old_row = old.loc[category_id]
        new_row = new.loc[category_id]
        if _value(old_row, "category_name") != _value(new_row, "category_name"):
            changed["name_changes"].append(_change_record(category_id, old_row, new_row, "category_name"))
        if _value(old_row, "parent_id") != _value(new_row, "parent_id"):
            changed["parent_changes"].append(_change_record(category_id, old_row, new_row, "parent_id"))
        if _value(old_row, "synonyms") != _value(new_row, "synonyms"):
            changed["synonym_changes"].append(_change_record(category_id, old_row, new_row, "synonyms"))

    return {
        "summary": {
            "old_nodes": len(old_df),
            "new_nodes": len(new_df),
            "added_count": len(added_ids),
            "deleted_count": len(deleted_ids),
            "name_change_count": len(changed["name_changes"]),
            "parent_change_count": len(changed["parent_changes"]),
            "synonym_change_count": len(changed["synonym_changes"]),
        },
        "details": {
            "added_nodes": [_row_record(new.loc[node_id]) for node_id in added_ids],
            "deleted_nodes": [_row_record(old.loc[node_id]) for node_id in deleted_ids],
            **changed,
        },
    }


def _value(row: pd.Series, column: str) -> str:
    return str(row.get(column, "")).strip()


def _row_record(row: pd.Series) -> dict[str, Any]:
    return {column: _value(row, column) for column in ["category_id", "category_name", "parent_id", "synonyms", "path"] if column in row}


def _change_record(category_id: str, old_row: pd.Series, new_row: pd.Series, column: str) -> dict[str, Any]:
    return {
        "category_id": category_id,
        "category_name": _value(new_row, "category_name"),
        "field": column,
        "old_value": _value(old_row, column),
        "new_value": _value(new_row, column),
        "old_path": _value(old_row, "path"),
        "new_path": _value(new_row, "path"),
    }
