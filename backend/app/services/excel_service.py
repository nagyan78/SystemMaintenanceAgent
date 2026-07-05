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

        try:
            workbook = load_workbook(saved_path, read_only=True, data_only=True)
        except Exception as exc:
            raise ExcelValidationError("Excel file could not be read.", "INVALID_EXCEL") from exc

        sheet = workbook.worksheets[0]
        columns = [str(value).strip() for value in next(sheet.iter_rows(max_row=1, values_only=True))]
        missing_columns = sorted(REQUIRED_COLUMNS.difference(columns))
        if missing_columns:
            joined = ", ".join(missing_columns)
            raise ExcelValidationError(f"Excel missing required columns: {joined}", "INVALID_COLUMNS")

        return UploadedFileMetadata(
            file_name=original_name,
            file_path=saved_path,
            file_size=saved_path.stat().st_size,
            sheet_name=sheet.title,
            row_count=max(sheet.max_row - 1, 0),
            column_count=len(columns),
            columns=columns,
        )

    def _saved_file_name(self, original_name: str) -> str:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(original_name).name)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return f"{timestamp}_{safe_name}"

