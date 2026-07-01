"""Load product category data from CSV or Excel files."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pandas as pd


REQUIRED_BASE_COLUMNS = ["category_id", "category_name"]
REQUIRED_COLUMNS = ["category_id", "category_name", "parent_id"]
OPTIONAL_COLUMNS = ["synonyms", "version"]
COLUMN_ALIASES = {
    "id": "category_id",
    "node_id": "category_id",
    "cat_id": "category_id",
    "name": "category_name",
    "node_name": "category_name",
    "cat_name": "category_name",
    "parent": "parent_id",
    "pid": "parent_id",
    "parent_category_id": "parent_id",
    "category_group_id": "category_group_id",
    "category_pids": "category_pids",
    "category_group_name": "category_group_name",
    "syn_list": "synonyms",
    "synonym": "synonyms",
    "alias": "synonyms",
    "aliases": "synonyms",
}


def load_product_data(file_path: str | Path) -> pd.DataFrame:
    """Read a CSV/XLSX file, normalize columns, and return a DataFrame."""

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = _read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str, keep_default_na=False)
    else:
        raise ValueError("Only .csv, .xlsx, and .xls files are supported.")

    df = _normalize_columns(df)
    if "parent_id" not in df.columns and "category_group_id" in df.columns:
        df["parent_id"] = df["category_group_id"].map(_parent_from_category_group_id)

    missing = [col for col in REQUIRED_BASE_COLUMNS if col not in df.columns]
    if "parent_id" not in df.columns:
        missing.append("parent_id or category_group_id")
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    for col in OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    for col in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["synonyms"] = df["synonyms"].map(_normalize_synonyms)

    return df


def _read_csv(path: Path) -> pd.DataFrame:
    """Read CSV with encodings commonly seen on Windows and Excel."""

    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize header names and apply a small set of common aliases."""

    normalized = {}
    for column in df.columns:
        clean = str(column).strip().lower().replace(" ", "_").replace("-", "_")
        normalized[column] = COLUMN_ALIASES.get(clean, clean)
    return df.rename(columns=normalized)


def _parent_from_category_group_id(value: str) -> str:
    """Infer direct parent_id from category_group_id ancestor path."""

    text = str(value).strip()
    if not text:
        return ""
    ids = [item for item in re.findall(r"-?\d+", text) if item != "-1"]
    return ids[-1] if ids else ""


def _normalize_synonyms(value: str) -> str:
    """Normalize syn_list/list-like values into a comma-separated string."""

    text = str(value).strip()
    if not text or text == "[]":
        return ""
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, list):
            return ",".join(str(item).strip() for item in parsed if str(item).strip())
    except (SyntaxError, ValueError):
        pass
    return text.strip("[]").replace("'", "").replace('"', "").strip()
