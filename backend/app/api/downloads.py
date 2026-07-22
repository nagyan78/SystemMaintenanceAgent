from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.get("/exports/{file_name}")
def download_export(file_name: str, request: Request) -> FileResponse:
    if Path(file_name).name != file_name:
        raise HTTPException(status_code=400, detail="Invalid export file name.")
    export_dir = request.app.state.settings.export_dir.resolve()
    export_path = (export_dir / file_name).resolve()
    if export_path.parent != export_dir or not export_path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found.")
    return FileResponse(
        export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=export_path.name,
    )
