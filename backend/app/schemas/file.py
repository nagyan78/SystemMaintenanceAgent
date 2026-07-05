from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    file_id: int
    task_id: str
    file_name: str
    row_count: int
    column_count: int
    columns: list[str]
    status: str

