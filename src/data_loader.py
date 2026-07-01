"""读取并轻量清洗标准产品体系 Excel 数据。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .common import ID_COLUMNS, REQUIRED_COLUMNS


def load_product_data(file_path: str) -> pd.DataFrame:
    """读取标准产品体系 Excel 数据。

    处理目标：
    1. 只接受 `.xlsx` 文件，避免旧版 Excel 或其他格式造成字段解析差异。
    2. 检查必需字段，缺字段时尽早报错。
    3. 保留原始数据中的所有列，只对单元格做基础清洗。
    4. 把 ID 类字段规范为字符串，避免 Excel 把 ID 当数字处理。

    注意：本函数只读取和返回 DataFrame，不会写回或修改原始 Excel 文件。
    """

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Only .xlsx files are supported in the first-round loader.")

    # 产品 ID 是标识符，不是可计算数字；用 object 读取可以尽量保留 Excel 中
    # 的原始值，再由后续清洗函数统一处理。
    df = pd.read_excel(path, dtype=object, keep_default_na=False)
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")

    result = df.copy()
    for column in result.columns:
        result[column] = result[column].map(_clean_cell)

    # Excel 常见问题：ID 列会被显示成 1.0、1001.0。这里统一去掉无意义的
    # `.0`，并处理逗号分隔的祖先路径。
    for column in ID_COLUMNS:
        result[column] = result[column].map(_normalize_id_path)

    return result


def _clean_cell(value: Any) -> str:
    """把单元格转为去除首尾空格的字符串，空值统一变成空字符串。"""

    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_id_path(value: Any) -> str:
    """规范单个 ID 或 ID 路径。

    `category_group_id`、`category_pids` 这类字段可能是多个 ID 组成的路径，
    所以先拆分，再逐个规范化，最后重新用英文逗号连接。
    """

    text = _clean_cell(value)
    if not text:
        return ""
    tokens = [token.strip() for token in text.replace("，", ",").split(",")]
    return ",".join(_normalize_id_token(token) for token in tokens if token)


def _normalize_id_token(value: Any) -> str:
    """把 Excel 数字样式 ID 还原为稳定字符串，例如 `1.0` 还原为 `1`。"""

    text = _clean_cell(value)
    if text.endswith(".0"):
        head = text[:-2]
        if head.isdigit() or (head.startswith("-") and head[1:].isdigit()):
            return head
    return text
