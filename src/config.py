"""Project-level constants for rule thresholds and required fields."""

from __future__ import annotations

REQUIRED_COLUMNS: tuple[str, ...] = (
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
)

ID_COLUMNS: tuple[str, ...] = (
    "category_id",
    "category_group_id",
    "category_pids",
)

DEFAULT_DEPTH_THRESHOLD = 8
DEFAULT_WIDTH_THRESHOLD = 100

