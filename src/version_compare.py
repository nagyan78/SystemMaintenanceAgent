"""Placeholder interfaces for future version comparison features."""

from __future__ import annotations

import pandas as pd


def compare_versions(old_df: pd.DataFrame, new_df: pd.DataFrame) -> dict[str, object]:
    """Return an empty comparison result until version rules are implemented."""

    return {
        "added_nodes": [],
        "deleted_nodes": [],
        "renamed_nodes": [],
        "moved_nodes": [],
    }

