"""Tests for Excel loader validation and ID normalization."""

from __future__ import annotations

import pandas as pd

from src.data_loader import load_product_data


def test_load_product_data_normalizes_id_fields(tmp_path) -> None:
    """Excel ID fields should be loaded as stable strings with blanks preserved."""

    input_path = tmp_path / "taxonomy.xlsx"
    pd.DataFrame(
        [
            {
                "category_id": 1,
                "category_name": "Root",
                "category_group_id": "",
                "category_pids": "",
                "category_group_name": "",
                "syn_list": "",
            },
            {
                "category_id": 2,
                "category_name": "Child",
                "category_group_id": "1",
                "category_pids": "1",
                "category_group_name": "Root",
                "syn_list": "alias",
            },
        ]
    ).to_excel(input_path, index=False)

    df = load_product_data(str(input_path))

    assert df.loc[0, "category_id"] == "1"
    assert df.loc[0, "category_group_id"] == ""
    assert df.loc[1, "category_pids"] == "1"

