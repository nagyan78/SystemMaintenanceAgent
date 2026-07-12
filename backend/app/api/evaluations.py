from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from backend.app.repositories.evaluation_repo import EvaluationRepository
from backend.app.schemas.evaluation import AgentEvaluationResult
from backend.app.services.evaluation_service import EvaluationService

router=APIRouter(prefix="/evaluations",tags=["evaluations"])
class CreateEvaluationRequest(BaseModel): result: AgentEvaluationResult; agent_bundle_version:str="candidate"
class PromoteRequest(BaseModel): operator:str; agent_bundle_version:str
@router.get("")
def list_evaluations(request:Request): return EvaluationRepository(request.app.state.settings).list()
@router.post("")
def create_evaluation(payload:CreateEvaluationRequest,request:Request): return {"evaluation_id":EvaluationRepository(request.app.state.settings).create(payload.result,payload.agent_bundle_version)}
@router.post("/{evaluation_id}/promote-baseline")
def promote(evaluation_id:int,payload:PromoteRequest,request:Request):
    repo=EvaluationRepository(request.app.state.settings); item=repo.get(evaluation_id)
    if not item: raise HTTPException(404,"evaluation not found")
    result=AgentEvaluationResult.model_validate(item["metrics"])
    if result.unsafe_action_escape_rate!=0 or result.action_executable_rate<.95: raise HTTPException(400,"evaluation does not meet baseline safety requirements")
    return {"baseline_id":repo.promote(evaluation_id,result.dataset_version,payload.agent_bundle_version,payload.operator)}
@router.get("/release-gate")
def release_gate(dataset_version:str,evaluation_id:int,request:Request):
    repo=EvaluationRepository(request.app.state.settings); item=repo.get(evaluation_id)
    if not item: raise HTTPException(404,"evaluation not found")
    baseline_row=repo.baseline(dataset_version); baseline=None
    if baseline_row:
        stored=repo.get(int(baseline_row["evaluation_id"])); baseline=AgentEvaluationResult.model_validate(stored["metrics"]) if stored else None
    return EvaluationService().release_gate(AgentEvaluationResult.model_validate(item["metrics"]),baseline)|{"baseline_id":baseline_row["baseline_id"] if baseline_row else None}
