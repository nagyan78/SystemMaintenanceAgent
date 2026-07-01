"""Tests for the local upload web front end."""

from __future__ import annotations

import zipfile

from src.web_app import _extract_filename, _is_xlsx_content, _render_upload_page


def test_upload_page_has_drag_and_drop_controls() -> None:
    """The upload page should expose a visible drag-and-drop drop zone."""

    html = _render_upload_page()

    assert "拖拽 .xlsx 文件到这里" in html
    assert "dropZone" in html
    assert "dragover" in html
    assert "DataTransfer" in html
    assert "开始诊断" in html


def test_extract_filename_supports_encoded_filename_star() -> None:
    """Multipart filename* headers should decode UTF-8 file names."""

    headers = (
        "Content-Disposition: form-data; "
        "name=\"file\"; "
        "filename*=UTF-8''%E4%BA%A7%E5%93%81.xlsx"
    )

    assert _extract_filename(headers) == "产品.xlsx"


def test_is_xlsx_content_checks_workbook_zip_members(tmp_path) -> None:
    """XLSX detection should use workbook contents instead of filename only."""

    workbook = tmp_path / "renamed.bin"
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("xl/workbook.xml", "<workbook></workbook>")

    assert _is_xlsx_content(workbook.read_bytes()) is True
    assert _is_xlsx_content(b"not an excel file") is False
