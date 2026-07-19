"""Deterministic Phase-5 Golden Excel fixture and its expected diagnosis set."""

from io import BytesIO

from openpyxl import Workbook


DATASET_VERSION = "phase5-golden-v1"
EXPECTED_ISSUES = {
    (4, "missing_parent"),
    (2, "naming_nonstandard"),
    (3, "synonym_format"),
    (26, "excessive_depth"),
}


def workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "taxonomy"
    sheet.append([
        "category_id", "category_name", "category_group_id", "category_pids",
        "category_group_name", "syn_list",
    ])
    sheet.append([1, "产品", "", "", "", ""])
    sheet.append([2, "其他", "1", "1", "产品", ""])
    sheet.append([3, "设备", "1", "1", "产品", "设备,设备"])
    sheet.append([4, "断裂节点", "999", "999", "缺失父节点", ""])
    ancestors = [1]
    names = ["产品"]
    for category_id in range(20, 27):
        sheet.append([
            category_id, f"层级{category_id}", ",".join(map(str, ancestors)),
            ",".join(map(str, ancestors)), ",".join(names), "",
        ])
        ancestors.append(category_id)
        names.append(f"层级{category_id}")
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
