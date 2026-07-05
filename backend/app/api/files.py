from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from backend.app.repositories.file_repo import FileRepository, TaskRepository
from backend.app.schemas.file import FileUploadResponse
from backend.app.services.excel_service import ExcelService, ExcelValidationError

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "/upload",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(request: Request, file: UploadFile = File(...)) -> FileUploadResponse:
    settings = request.app.state.settings
    service = ExcelService(settings)
    file_repo = FileRepository(settings)
    task_repo = TaskRepository(settings)

    try:
        metadata = await service.save_and_inspect(file)
    except ExcelValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": exc.error_code, "message": str(exc)},
        ) from exc

    file_id = file_repo.create_uploaded_file(metadata)
    task_id = task_repo.create_task(file_id=file_id, task_type="import_excel")

    return FileUploadResponse(
        file_id=file_id,
        task_id=task_id,
        file_name=metadata.file_name,
        row_count=metadata.row_count,
        column_count=metadata.column_count,
        columns=metadata.columns,
        status="uploaded",
    )


@router.get("")
def list_files(request: Request) -> list[dict]:
    return FileRepository(request.app.state.settings).list_files()


@router.get("/{file_id}")
def get_file(file_id: int, request: Request) -> dict:
    file_record = FileRepository(request.app.state.settings).get_file(file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    return file_record

