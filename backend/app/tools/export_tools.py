from pathlib import Path

from openpyxl import Workbook

from backend.app.config import Settings, get_settings
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository


EXPORT_COLUMNS = [
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
]


def export_excel(version_id: int, settings: Settings | None = None) -> Path:
    runtime_settings = settings or get_settings()
    version = VersionRepository(runtime_settings).get_version(version_id)
    if version is None:
        raise ValueError(f"Taxonomy version {version_id} was not found.")
    nodes = TaxonomyRepository(runtime_settings).list_nodes(version_id)
    if not nodes:
        raise ValueError("VERSION_HAS_NO_NODES")

    runtime_settings.export_dir.mkdir(parents=True, exist_ok=True)
    export_path = runtime_settings.export_dir / f"{version['version_no']}_taxonomy.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "taxonomy"
    sheet.append(EXPORT_COLUMNS)
    for node in sorted(nodes, key=_sort_key):
        sheet.append([node.get(column) for column in EXPORT_COLUMNS])
    workbook.save(export_path)
    return export_path


def _sort_key(node: dict) -> tuple[list[int], int]:
    path_ids = [
        int(part)
        for part in str(node.get("path_ids") or "").split(",")
        if part.strip().isdigit()
    ]
    return (path_ids, int(node["category_id"]))
