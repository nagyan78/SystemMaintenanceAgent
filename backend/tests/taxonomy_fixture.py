from pathlib import Path

from openpyxl import Workbook


TAXONOMY_COLUMNS = [
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
]


def write_taxonomy_workbook(path: Path) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(TAXONOMY_COLUMNS)
    sheet.append([1, "根", "", "", "根", ""])
    sheet.append([2, "水果", "1", "1", "根", "红富士, AirPods"])
    sheet.append([3, "苹果", "1,2", "1,2", "根,水果", ""])
    workbook.save(path)
    return path
