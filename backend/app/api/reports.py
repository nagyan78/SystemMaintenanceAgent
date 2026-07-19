import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.app.repositories.version_repo import VersionRepository
from backend.app.services.report_service import ReportService, report_file_name
from backend.app.services.pdf_report_service import PdfReportService
from backend.app.repositories.report_repo import ReportRepository
from backend.app.repositories.task_repo import TaskRepository


router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    version_id: int
    format: str = "markdown"
    report_type: str = "final"


def _report_metadata(request: Request, version_id: int, report_type: str) -> tuple[dict, Path]:
    settings = request.app.state.settings
    version = VersionRepository(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    if report_type == "historical":
        report_path = _historical_report_path(request, version)
        if report_path is None:
            raise HTTPException(status_code=404, detail="Historical report not found.")
        return version, report_path
    artifact = ReportRepository(settings).get(version_id, report_type)
    report_path = Path(artifact["report_path"]) if artifact else settings.report_dir / report_file_name(version, report_type)
    return version, report_path


def _historical_report_path(request: Request, version: dict) -> Path | None:
    settings = request.app.state.settings
    task = TaskRepository(settings).get_latest_for_version(int(version["id"]))
    if task and task.get("result_payload"):
        try:
            payload = json.loads(task["result_payload"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        raw_path = payload.get("report_path") if isinstance(payload, dict) else None
        if raw_path and Path(raw_path).is_file():
            return Path(raw_path)
    exact = settings.report_dir / f"{version['version_no']}_version-{version['id']}_diagnosis_report.md"
    return exact if exact.is_file() else None


def _can_generate_final(version: dict) -> bool:
    return bool(
        version.get("parent_version_id")
        and version.get("action_batch_id")
        and version.get("verification_status") in {"passed", "partial"}
        and version.get("lifecycle_status") in {"passed", "partial", "released"}
    )


@router.get("")
def list_reports(request: Request, file_id: int | None = None, version_id: int | None = None) -> list[dict]:
    reports = []
    versions = VersionRepository(request.app.state.settings).list_versions(file_id=file_id)
    if version_id is not None:
        versions = [version for version in versions if int(version["id"]) == version_id]
        if not versions and VersionRepository(request.app.state.settings).get_version(version_id) is None:
            raise HTTPException(status_code=404, detail="Version not found.")
    for version in versions:
        for report_type in ("draft", "partial", "failed", "final"):
            artifact = ReportRepository(request.app.state.settings).get(int(version["id"]), report_type)
            if artifact:
                reports.append({"version_id": version["id"], "version_no": version["version_no"],
                    "quality_score": version.get("quality_score"), "report_name": Path(artifact["report_path"]).name,
                    "report_path": artifact["report_path"], "report_type": report_type, "status": artifact["status"],
                    "preview_url": f"/api/reports/{version['id']}/preview?report_type={report_type}",
                    "download_url": f"/api/reports/{version['id']}/download?report_type={report_type}",
                    "pdf_download_url": f"/api/reports/{version['id']}/download-pdf?report_type={report_type}"})
        historical = _historical_report_path(request, version)
        if historical and not any(item["version_id"] == version["id"] and Path(item["report_path"]) == historical for item in reports):
            reports.append({"version_id": version["id"], "version_no": version["version_no"],
                "quality_score": version.get("quality_score"), "report_name": historical.name,
                "report_path": str(historical), "report_type": "historical", "status": "generated",
                "preview_url": f"/api/reports/{version['id']}/preview?report_type=historical",
                "download_url": f"/api/reports/{version['id']}/download?report_type=historical",
                "pdf_download_url": f"/api/reports/{version['id']}/download-pdf?report_type=historical"})
    return reports


@router.post("/generate")
def generate_report(payload: GenerateReportRequest, request: Request) -> dict:
    if payload.format != "markdown":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only markdown reports are supported.",
        )
    try:
        version = VersionRepository(request.app.state.settings).get_version(payload.version_id)
        if version is None:
            raise ValueError("Version not found")
        if payload.report_type == "final" and not _can_generate_final(version):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Final report requires completed review, execution and re-diagnosis.")
        result = ReportService(request.app.state.settings).generate_diagnosis_report(
            payload.version_id, report_type=payload.report_type
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {
        "version_id": result.version_id,
        "report_name": result.report_name,
        "report_path": str(result.report_path),
        "preview_url": f"/api/reports/{result.version_id}/preview?report_type={payload.report_type}",
        "download_url": f"/api/reports/{result.version_id}/download?report_type={payload.report_type}",
        "pdf_download_url": f"/api/reports/{result.version_id}/download-pdf?report_type={payload.report_type}",
        "status": result.status,
        "report_type": payload.report_type,
    }


@router.get("/{version_id}/preview")
def preview_report(version_id: int, request: Request, report_type: str = "final") -> dict:
    version, report_path = _report_metadata(request, version_id, report_type)
    if not report_path.is_file():
        if report_type == "historical":
            raise HTTPException(status_code=404, detail="Historical report not found.")
        if report_type == "final" and not _can_generate_final(version):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Final report is not available before review execution and re-diagnosis.")
        ReportService(request.app.state.settings).generate_diagnosis_report(version_id, report_type=report_type)
    return {
        "version_id": version_id,
        "version_no": version["version_no"],
        "report_name": report_path.name,
        "report_path": str(report_path),
        "report_type": report_type,
        "download_url": f"/api/reports/{version_id}/download?report_type={report_type}",
        "pdf_download_url": f"/api/reports/{version_id}/download-pdf?report_type={report_type}",
        "markdown": report_path.read_text(encoding="utf-8"),
    }


@router.get("/{version_id}/download")
def download_report(version_id: int, request: Request, report_type: str = "final") -> FileResponse:
    version, report_path = _report_metadata(request, version_id, report_type)
    if not report_path.is_file():
        if report_type == "historical":
            raise HTTPException(status_code=404, detail="Historical report not found.")
        if report_type == "final" and not _can_generate_final(version):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Final report is not available.")
        ReportService(request.app.state.settings).generate_diagnosis_report(version_id, report_type=report_type)
    return FileResponse(
        report_path,
        media_type="text/markdown; charset=utf-8",
        filename=report_path.name,
    )


@router.get("/{version_id}/download-pdf")
def download_pdf_report(version_id: int, request: Request, report_type: str = "final") -> FileResponse:
    version, report_path = _report_metadata(request, version_id, report_type)
    if not report_path.is_file():
        if report_type == "historical":
            raise HTTPException(status_code=404, detail="Historical report not found.")
        if report_type == "final" and not _can_generate_final(version):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Final report is not available.")
        ReportService(request.app.state.settings).generate_diagnosis_report(version_id, report_type=report_type)
    pdf_path = report_path.with_suffix(".pdf")
    PdfReportService().render(
        report_path.read_text(encoding="utf-8"),
        pdf_path,
        title=f"{version['version_no']} 产品标准体系{report_type}报告",
    )
    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)
