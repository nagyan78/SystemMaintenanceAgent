from fastapi import APIRouter

from backend.app.api._placeholder import not_implemented

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/run")
def run_diagnosis() -> None:
    not_implemented("diagnosis", "run")


@router.get("/issues")
def list_diagnosis_issues() -> None:
    not_implemented("diagnosis", "issues")


@router.get("/issues/{issue_id}")
def get_diagnosis_issue(issue_id: int) -> None:
    not_implemented("diagnosis", f"issue:{issue_id}")

