from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.repositories.version_repo import VersionRepository
from backend.app.services.report_service import ReportService, report_file_name


router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    version_id: int
    format: str = "markdown"


def _report_metadata(request: Request, version_id: int) -> tuple[dict, Path]:
    settings = request.app.state.settings
    version = VersionRepository(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    report_name = report_file_name(version)
    return version, settings.report_dir / report_name


@router.get("")
def list_reports(request: Request, file_id: int | None = None) -> list[dict]:
    reports = []
    for version in VersionRepository(request.app.state.settings).list_versions(file_id=file_id):
        report_name = report_file_name(version)
        report_path = request.app.state.settings.report_dir / report_name
        reports.append({
            "version_id": version["id"], "version_no": version["version_no"],
            "quality_score": version.get("quality_score"), "report_name": report_name,
            "status": "generated" if report_path.is_file() else "not_generated",
            "preview_url": f"/api/reports/{version['id']}/preview",
        })
    return reports


@router.post("/generate")
def generate_report(payload: GenerateReportRequest, request: Request) -> dict:
    if payload.format != "markdown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only markdown reports are supported.",
        )
    try:
        result = ReportService(request.app.state.settings).generate_diagnosis_report(
            payload.version_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "version_id": result.version_id,
        "report_name": result.report_name,
        "report_path": str(result.report_path),
        "preview_url": f"/api/reports/{result.version_id}/preview",
        "download_url": f"/api/reports/{result.version_id}/download",
        "status": result.status,
    }


@router.get("/{version_id}/preview")
def preview_report(version_id: int, request: Request) -> dict:
    version, report_path = _report_metadata(request, version_id)
    if not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report has not been generated yet.",
        )
    return {
        "version_id": version_id,
        "version_no": version["version_no"],
        "report_name": report_path.name,
        "report_path": str(report_path),
        "download_url": f"/api/reports/{version_id}/download",
        "markdown": report_path.read_text(encoding="utf-8"),
    }


@router.get("/{version_id}/download")
def download_report(version_id: int, request: Request) -> FileResponse:
    _, report_path = _report_metadata(request, version_id)
    if not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report has not been generated yet.",
        )
    return FileResponse(
        report_path,
        media_type="text/markdown; charset=utf-8",
        filename=report_path.name,
    )
