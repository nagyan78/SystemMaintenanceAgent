from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
import json
from backend.app.db import connect
from backend.app.repositories.evaluation_repo import EvaluationRepository
from backend.app.schemas.evaluation import AgentEvaluationResult
from backend.app.services.evaluation_service import EvaluationService

router=APIRouter(prefix="/evaluations",tags=["evaluations"])
class CreateEvaluationRequest(BaseModel): workflow_id:str; dataset_version:str; agent_bundle_version:str="candidate"
class PromoteRequest(BaseModel): operator:str; agent_bundle_version:str
@router.get("")
def list_evaluations(request:Request): return EvaluationRepository(request.app.state.settings).list()
@router.post("")
def create_evaluation(payload:CreateEvaluationRequest,request:Request):
    fixture=Path(__file__).parents[2]/"tests"/"fixtures"/"golden_taxonomy_issues.json"
    if not fixture.exists(): raise HTTPException(404,"golden dataset not found")
    raw=json.loads(fixture.read_text(encoding="utf-8"))
    if raw.get("dataset_version")!=payload.dataset_version: raise HTTPException(404,"golden dataset version not found")
    with connect(request.app.state.settings) as c:
        task=c.execute("SELECT version_id FROM task_record WHERE workflow_id=? ORDER BY id DESC LIMIT 1",(payload.workflow_id,)).fetchone()
        if not task or task[0] is None: raise HTTPException(404,"workflow result not found")
        version_id=int(task[0])
        predicted=[dict(row) for row in c.execute("SELECT node_id,issue_type,confidence FROM diagnosis_issue WHERE version_id=?",(version_id,)).fetchall()]
        suggestions=[{"schema_valid":True,"executable":row["status"] not in {"failed"}} for row in c.execute("SELECT status FROM adjustment_suggestion WHERE version_id=?",(version_id,)).fetchall()]
        events=[dict(row) for row in c.execute("SELECT latency_ms,token_usage FROM agent_event WHERE workflow_id=?",(payload.workflow_id,)).fetchall()]
    golden=raw.get("items",[]); latencies=[int(e["latency_ms"]) for e in events if e.get("latency_ms") is not None]
    result=EvaluationService().evaluate(golden=golden,predicted=predicted,suggestions=suggestions,workflow_id=payload.workflow_id,dataset_version=payload.dataset_version,latencies=latencies,model_calls=len(events))
    return {"evaluation_id":EvaluationRepository(request.app.state.settings).create(result,payload.agent_bundle_version),"result":result.model_dump()}
@router.post("/{evaluation_id}/promote-baseline")
def promote(evaluation_id:int,payload:PromoteRequest,request:Request):
    repo=EvaluationRepository(request.app.state.settings); item=repo.get(evaluation_id)
    if not item: raise HTTPException(404,"evaluation not found")
    result=AgentEvaluationResult.model_validate(item["metrics"])
    if result.unsafe_action_escape_rate!=0 or result.action_executable_rate<.95: raise HTTPException(400,"evaluation does not meet baseline safety requirements")
    baseline_id=repo.promote(evaluation_id,result.dataset_version,payload.agent_bundle_version,payload.operator)
    with connect(request.app.state.settings) as c:
        c.execute("INSERT INTO operation_log(version_id,operator,operation_type,operation_detail) VALUES(NULL,?,?,?)",(payload.operator,"promote_evaluation_baseline",json.dumps({"evaluation_id":evaluation_id,"baseline_id":baseline_id},ensure_ascii=False)))
    return {"baseline_id":baseline_id}
@router.get("/release-gate")
def release_gate(dataset_version:str,evaluation_id:int,request:Request):
    repo=EvaluationRepository(request.app.state.settings); item=repo.get(evaluation_id)
    if not item: raise HTTPException(404,"evaluation not found")
    baseline_row=repo.baseline(dataset_version); baseline=None
    if baseline_row:
        stored=repo.get(int(baseline_row["evaluation_id"])); baseline=AgentEvaluationResult.model_validate(stored["metrics"]) if stored else None
    return EvaluationService().release_gate(AgentEvaluationResult.model_validate(item["metrics"]),baseline)|{"baseline_id":baseline_row["baseline_id"] if baseline_row else None}
