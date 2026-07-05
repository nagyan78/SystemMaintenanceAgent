import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from openpyxl import load_workbook

from backend.app.config import Settings


REQUIRED_COLUMNS = {
    "category_id",
    "category_name",
    "category_group_id",
    "category_pids",
    "category_group_name",
    "syn_list",
}


class ExcelValidationError(ValueError):
    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass(frozen=True)
class UploadedFileMetadata:
    file_name: str
    file_path: Path
    file_size: int
    sheet_name: str
    row_count: int
    column_count: int
    columns: list[str]


@dataclass(frozen=True)
class ParseExcelResult:
    file_id: int
    file_name: str
    file_path: Path
    sheet_name: str
    row_count: int
    column_count: int
    columns: list[str]


class ExcelService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def save_and_inspect(self, upload_file: UploadFile) -> UploadedFileMetadata:
        original_name = upload_file.filename or "uploaded.xlsx"
        suffix = Path(original_name).suffix.lower()
        if suffix not in self.settings.allowed_upload_suffixes:
            raise ExcelValidationError("Only .xlsx files are supported.", "INVALID_FILE_TYPE")

        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        saved_path = self.settings.upload_dir / self._saved_file_name(original_name)

        with saved_path.open("wb") as output:
            shutil.copyfileobj(upload_file.file, output)

        file_size = saved_path.stat().st_size
        if file_size == 0:
            saved_path.unlink(missing_ok=True)
            raise ExcelValidationError("Excel file is empty.", "EMPTY_FILE")
        if file_size > self.settings.max_upload_size_bytes:
            saved_path.unlink(missing_ok=True)
            raise ExcelValidationError("Excel file is too large.", "FILE_TOO_LARGE")

        try:
            workbook = load_workbook(saved_path, read_only=True, data_only=True)
        except Exception as exc:
            saved_path.unlink(missing_ok=True)
            raise ExcelValidationError("Excel file could not be read.", "INVALID_EXCEL") from exc

        sheet = workbook.worksheets[0]
        columns = [
            "" if value is None else str(value).strip()
            for value in next(sheet.iter_rows(max_row=1, values_only=True))
        ]
        missing_columns = sorted(REQUIRED_COLUMNS.difference(columns))
        if missing_columns:
            saved_path.unlink(missing_ok=True)
            joined = ", ".join(missing_columns)
            raise ExcelValidationError(f"Excel missing required columns: {joined}", "INVALID_COLUMNS")

        return UploadedFileMetadata(
            file_name=original_name,
            file_path=saved_path,
            file_size=file_size,
            sheet_name=sheet.title,
            row_count=max(sheet.max_row - 1, 0),
            column_count=len(columns),
            columns=columns,
        )

    def parse_uploaded_file(self, file_id: int) -> ParseExcelResult:
        from backend.app.repositories.file_repo import FileRepository

        file_record = FileRepository(self.settings).get_file(file_id)
        if file_record is None:
            raise ExcelValidationError("Uploaded file was not found.", "FILE_NOT_FOUND")

        file_path = Path(file_record["file_path"])
        if not file_path.exists():
            raise ExcelValidationError("Uploaded file path does not exist.", "FILE_NOT_FOUND")

        try:
            workbook = load_workbook(file_path, read_only=True, data_only=True)
        except Exception as exc:
            raise ExcelValidationError("Excel file could not be read.", "INVALID_EXCEL") from exc

        sheet = workbook.worksheets[0]
        columns = [
            "" if value is None else str(value).strip()
            for value in next(sheet.iter_rows(max_row=1, values_only=True))
        ]
        missing_columns = sorted(REQUIRED_COLUMNS.difference(columns))
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ExcelValidationError(f"Excel missing required columns: {joined}", "INVALID_COLUMNS")

        return ParseExcelResult(
            file_id=file_id,
            file_name=file_record["file_name"],
            file_path=file_path,
            sheet_name=sheet.title,
            row_count=max(sheet.max_row - 1, 0),
            column_count=len(columns),
            columns=columns,
        )

    def _saved_file_name(self, original_name: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(original_name).name)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{timestamp}_{safe_name}"
