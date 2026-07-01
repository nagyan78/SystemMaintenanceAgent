"""Load and lightly normalize standard product taxonomy data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import ID_COLUMNS, REQUIRED_COLUMNS


def load_product_data(file_path: str) -> pd.DataFrame:
    """读取标准产品体系 Excel 数据。

    The loader reads an ``.xlsx`` workbook, checks required columns, keeps all
    source columns, converts ID-like fields to strings, and normalizes empty
    values to blank strings. It never writes back to the source Excel file.
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Only .xlsx files are supported in the first-round loader.")

    df = pd.read_excel(path, dtype=object, keep_default_na=False)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    result = df.copy()
    for column in result.columns:
        result[column] = result[column].map(_clean_cell)

    for column in ID_COLUMNS:
        result[column] = result[column].map(_normalize_id_path)

    return result


def _clean_cell(value: Any) -> str:
    """Convert a cell value to a stripped string while preserving blanks."""

    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_id_path(value: Any) -> str:
    """Normalize a single ID or an ID path without treating blanks as ``nan``."""

    text = _clean_cell(value)
    if not text:
        return ""
    tokens = [token.strip() for token in text.replace("，", ",").split(",")]
    return ",".join(_normalize_id_token(token) for token in tokens if token)


def _normalize_id_token(value: Any) -> str:
    """Convert Excel-style numeric IDs such as ``1.0`` back to stable strings."""

    text = _clean_cell(value)
    if text.endswith(".0"):
        head = text[:-2]
        if head.isdigit() or (head.startswith("-") and head[1:].isdigit()):
            return head
    return text

