import asyncio
from pathlib import Path

import pytest
from fastapi import UploadFile
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.services.excel_service import ExcelService, ExcelValidationError
from backend.tests.taxonomy_fixture import write_taxonomy_workbook


EXPECTED_COLUMNS = [
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
]


def _service(tmp_path):
    return ExcelService(Settings(upload_dir=tmp_path / "uploads"))


def _upload_file(path, filename=None):
    path = Path(path)
    return UploadFile(path.open("rb"), filename=filename or path.name)


def _write_workbook(path, headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    sheet.append([1, "根节点", "", "", "根节点", ""])
    workbook.save(path)
    return path


def _inspect(service, path, filename=None):
    upload = _upload_file(path, filename)
    try:
        return asyncio.run(service.save_and_inspect(upload))
    finally:
        upload.file.close()


def test_service_reads_generated_excel_metadata(tmp_path):
    sample_path = write_taxonomy_workbook(tmp_path / "taxonomy.xlsx")
    metadata = _inspect(_service(tmp_path), sample_path, "taxonomy.xlsx")

    assert metadata.file_name == "taxonomy.xlsx"
    assert metadata.row_count == 3
    assert metadata.column_count == 6
    assert metadata.columns == EXPECTED_COLUMNS
    assert metadata.file_path.exists()


def test_service_rejects_missing_required_columns(tmp_path):
    workbook_path = _write_workbook(
        tmp_path / "missing.xlsx",
        [
            "category_id",
            "category_group_id",
            "category_pids",
            "category_group_name",
            "syn_list",
        ],
    )

    with pytest.raises(ExcelValidationError) as exc_info:
        _inspect(_service(tmp_path), workbook_path)

    assert exc_info.value.error_code == "INVALID_COLUMNS"
    assert str(exc_info.value) == "Excel missing required columns: category_name"


def test_service_rejects_non_xlsx_file(tmp_path):
    csv_path = tmp_path / "taxonomy.csv"
    csv_path.write_text(",".join(EXPECTED_COLUMNS), encoding="utf-8")

    with pytest.raises(ExcelValidationError) as exc_info:
        _inspect(_service(tmp_path), csv_path)

    assert exc_info.value.error_code == "INVALID_FILE_TYPE"


def test_service_rejects_empty_file(tmp_path):
    empty_path = tmp_path / "empty.xlsx"
    empty_path.write_bytes(b"")

    with pytest.raises(ExcelValidationError) as exc_info:
        _inspect(_service(tmp_path), empty_path)

    assert exc_info.value.error_code == "EMPTY_FILE"
