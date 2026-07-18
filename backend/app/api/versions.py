from typing import Any

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.version import ExportResult
from backend.app.services.version_service import VersionService
from backend.app.services.report_service import ReportService
from backend.app.tools.export_tools import export_excel

router = APIRouter(prefix="/versions", tags=["versions"])


@router.get("")
def list_versions(
    request: Request,
    file_id: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    return VersionService(request.app.state.settings).list_versions(file_id=file_id)


@router.get("/{version_id}")
def get_version(version_id: int, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    node_count = TaxonomyRepository(settings).count_nodes(version_id)
    return {**version, "node_count": node_count}


@router.get("/{version_id}/diff")
def get_version_diff(
    version_id: int,
    request: Request,
    target_version_id: int = Query(...),
) -> dict[str, Any]:
    service = VersionService(request.app.state.settings)
    if service.get_version(version_id) is None or service.get_version(target_version_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    return service.get_version_diff(version_id, target_version_id).model_dump()


@router.post("/{version_id}/rollback")
def rollback_version(version_id: int, request: Request) -> dict[str, Any]:
    try:
        return VersionService(request.app.state.settings).rollback_version(version_id).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{version_id}/export")
def export_version(version_id: int, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    try:
        export_path = export_excel(version_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ExportResult(
        version_id=version_id,
        version_no=str(version["version_no"]),
        file_name=export_path.name,
        export_path=str(export_path),
        download_url=f"/api/versions/{version_id}/export/download",
    ).model_dump()


@router.get("/{version_id}/export/download")
def download_export(version_id: int, request: Request) -> FileResponse:
    """Create (or refresh) a workbook and stream it directly to the browser."""
    settings = request.app.state.settings
    if VersionService(settings).get_version(version_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    try:
        export_path = export_excel(version_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return FileResponse(
        export_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=export_path.name,
    )


@router.get("/{version_id}/report")
def get_report(version_id: int, request: Request) -> dict[str, Any]:
    """Return a rendered report for in-app preview, generating one when absent."""
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")

    report_path = _find_report(settings.report_dir, str(version["version_no"]))
    if report_path is None:
        report_path = ReportService(settings).generate_diagnosis_report(version_id).report_path
    return {
        "version_id": version_id,
        "report_name": report_path.name,
        "markdown": report_path.read_text(encoding="utf-8"),
        "download_url": f"/api/versions/{version_id}/report/download",
    }


@router.get("/{version_id}/report/download")
def download_report(version_id: int, request: Request) -> FileResponse:
    settings = request.app.state.settings
    version = VersionService(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    report_path = _find_report(settings.report_dir, str(version["version_no"]))
    if report_path is None:
        report_path = ReportService(settings).generate_diagnosis_report(version_id).report_path
    return FileResponse(report_path, media_type="text/markdown; charset=utf-8", filename=report_path.name)


def _find_report(report_dir: Path, version_no: str) -> Path | None:
    candidates = list(report_dir.glob(f"{version_no}_*diagnosis_report.md"))
    if not candidates:
        candidates = list(report_dir.glob(f"{version_no}_diagnosis_report.md"))
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None
