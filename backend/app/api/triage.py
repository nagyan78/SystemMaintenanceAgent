from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.app.repositories.triage_repo import TriageRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.schemas.issue import DiagnosisIssueRecord

router=APIRouter(prefix="/triage",tags=["triage"])
class TriageDecision(BaseModel): decision:str; operator:str="local_user"
@router.get("")
def list_triage(request:Request,workflow_id:str|None=None): return TriageRepository(request.app.state.settings).list(workflow_id)
@router.post("/{triage_id}/decision")
def decide(triage_id:int,payload:TriageDecision,request:Request):
    if payload.decision not in {"issue","clean","inconclusive"}: raise HTTPException(400,"invalid triage decision")
    repo=TriageRepository(request.app.state.settings)
    try: item=repo.decide(triage_id,payload.decision,payload.operator)
    except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    issue_id=None
    if payload.decision=="issue":
        issue_id=DiagnosisRepository(request.app.state.settings).create_issue(version_id=int(item["version_id"]),issue=DiagnosisIssueRecord(issue_type=item["issue_type"],node_id=item["node_id"],node_name=item["node_name"],description=item["reason"] or "人工确认问题",reason=item["reason"] or "",evidence=item["evidence"],confidence=float(item["confidence"]),risk_level="medium",source="human_triage"))
    return {"triage_id":triage_id,"decision":payload.decision,"issue_id":issue_id}
