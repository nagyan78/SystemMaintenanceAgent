from fastapi import APIRouter, HTTPException, Query, Request, status

from backend.app.api._placeholder import not_implemented
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.services.version_service import VersionService

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/run")
def run_diagnosis() -> None:
    not_implemented("diagnosis", "run")


@router.get("/issues")
def list_diagnosis_issues(
    request: Request,
    version_id: int = Query(...),
    issue_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    if VersionService(request.app.state.settings).get_version(version_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found.")
    issues = DiagnosisRepository(request.app.state.settings).list_issues(
        version_id, status=issue_status, limit=limit
    )
    return {"version_id": version_id, "issues": issues}


@router.get("/issues/{issue_id}")
def get_diagnosis_issue(issue_id: int, request: Request, version_id: int = Query(...)) -> dict:
    issues = list_diagnosis_issues(version_id=version_id, request=request)["issues"]
    issue = next((item for item in issues if item["id"] == issue_id), None)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnosis issue not found.")
    return issue
