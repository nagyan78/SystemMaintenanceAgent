from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent, DiagnosisPlanningAgent
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.version_service import VersionService

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

STRUCTURE_TYPES = {"missing_parent", "deep_level", "wide_node", "duplicate_name", "orphan"}


class RunDiagnosisRequest(BaseModel):
    file_id: int | None = None
    version_id: int | None = None
    enable_ai_analysis: bool = False
    model_provider: str = "ollama"
    model_name: str = "qwen3:8b"


def _resolve_version(payload: RunDiagnosisRequest, request: Request) -> int:
    if payload.version_id is not None:
        return payload.version_id
    if payload.file_id is None:
        raise HTTPException(status_code=400, detail="file_id or version_id is required.")
    latest = VersionRepository(request.app.state.settings).get_latest_for_file(payload.file_id)
    if latest:
        return int(latest["id"])
    return VersionService(request.app.state.settings).create_initial_version(payload.file_id).version_id


@router.post("/run")
def run_diagnosis(payload: RunDiagnosisRequest, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    version_id = _resolve_version(payload, request)
    if payload.model_provider not in {"ollama", "deepseek"}:
        raise HTTPException(status_code=400, detail="model_provider must be ollama or deepseek.")
    expected_model = "qwen3:8b" if payload.model_provider == "ollama" else "deepseek-chat"
    if payload.model_name != expected_model:
        raise HTTPException(status_code=400, detail=f"{payload.model_provider} must use {expected_model}.")
    version = VersionRepository(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    task_repo = TaskRepository(settings)
    task_id = task_repo.create_diagnosis_task(
        file_id=int(version["file_id"]), version_id=version_id,
        enable_ai_analysis=payload.enable_ai_analysis,
        model_provider=payload.model_provider if payload.enable_ai_analysis else None,
        model_name=payload.model_name if payload.enable_ai_analysis else None,
    )
    try:
        structure = DiagnosisService(settings).run_structure_diagnosis(version_id)
        task_repo.update_task(task_id=task_id, current_step="content_rule_detection", progress=45)
        content_count = DiagnosisService(settings).run_content_rule_diagnosis(version_id)
        candidate_count = 0
        if payload.enable_ai_analysis:
            run_settings = settings.model_copy(update={
                "llm_provider": payload.model_provider,
                "llm_model": payload.model_name,
            })
            task_repo.update_task(task_id=task_id, current_step="ai_analysis", progress=60)
            overview = TaxonomyService(run_settings).get_planning_overview(version_id)
            plan = DiagnosisPlanningAgent(run_settings).run(structure.summary, overview)
            plan = DiagnosisPlan.model_validate(plan)
            plan.estimated_candidates = min(plan.estimated_candidates, 50)
            agent = ContentDiagnosisAgent(run_settings)
            candidates = agent.select_candidates(version_id, plan)
            candidate_count = len(candidates)
            agent.candidate_selector = lambda _version_id, _plan: candidates
            content_count += len(agent.run(version_id, plan))
            suggestions = SuggestionAgent(run_settings, enable_ai=True).run(version_id)
        else:
            suggestions = SuggestionAgent(settings, enable_ai=False).run(version_id)
        result = {
            "task_id": task_id, "version_id": version_id, "status": "completed",
            "structure_issue_count": structure.issue_count,
            "content_issue_count": content_count, "candidate_count": candidate_count,
            "suggestion_count": suggestions.generated_count,
            "review_batch_id": suggestions.review_batch_id,
            "enable_ai_analysis": payload.enable_ai_analysis,
            "model_provider": payload.model_provider if payload.enable_ai_analysis else None,
            "model_name": payload.model_name if payload.enable_ai_analysis else None,
        }
        all_issues = DiagnosisRepository(settings).list_issues(version_id)
        structure_count = sum(1 for item in all_issues if item["issue_type"] in STRUCTURE_TYPES)
        final_content_count = len(all_issues) - structure_count
        high_risk_count = sum(1 for item in all_issues if item["risk_level"] == "high")
        quality_score = max(0.0, round(100 - structure_count * 0.2 - final_content_count * 0.5 - high_risk_count * 0.8, 1))
        VersionRepository(settings).update_quality_score(version_id, quality_score)
        result["quality_score"] = quality_score
        task_repo.update_task(task_id=task_id, status="completed", current_step="completed", progress=100, result_payload=result)
        return result
    except Exception as exc:
        task_repo.update_task(task_id=task_id, status="failed", current_step="failed", error_message=str(exc))
        raise HTTPException(status_code=502, detail=f"Diagnosis failed: {exc}") from exc


@router.get("/summary")
def get_diagnosis_summary(version_id: int, request: Request) -> dict[str, Any]:
    repo = DiagnosisRepository(request.app.state.settings)
    issues = repo.list_issues(version_id)
    overview = TaxonomyRepository(request.app.state.settings).get_overview_counts(version_id)
    structure_count = sum(1 for item in issues if item["issue_type"] in STRUCTURE_TYPES)
    content_count = len(issues) - structure_count
    high_risk = sum(1 for item in issues if item["risk_level"] == "high")
    score = max(0.0, round(100 - structure_count * 0.2 - content_count * 0.5 - high_risk * 0.8, 1))
    task = TaskRepository(request.app.state.settings).get_latest_diagnosis_for_version(version_id)
    return {"version_id": version_id, "total_nodes": overview["node_count"], "structure_issue_count": structure_count, "content_issue_count": content_count, "high_risk_count": high_risk, "quality_score": score,
            "task_id": task["id"] if task else None,
            "enable_ai_analysis": bool(task["enable_ai_analysis"]) if task else False,
            "model_provider": task.get("model_provider") if task else None,
            "model_name": task.get("model_name") if task else None}


@router.get("/issues")
def list_diagnosis_issues(version_id: int, request: Request, issue_type: str | None = None, risk_level: str | None = None) -> list[dict]:
    return DiagnosisRepository(request.app.state.settings).list_issues(version_id, issue_type=issue_type, risk_level=risk_level)


@router.get("/issues/{issue_id}")
def get_diagnosis_issue(issue_id: int, request: Request) -> dict:
    settings = request.app.state.settings
    issue = DiagnosisRepository(settings).get_issue_detail(issue_id)
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found.")
    taxonomy = TaxonomyRepository(settings)
    node = taxonomy.get_node_detail(issue["version_id"], issue["node_id"]) if issue.get("node_id") else None
    parent = taxonomy.get_node_detail(issue["version_id"], node["parent_id"]) if node and node.get("parent_id") else None
    children = taxonomy.get_children(issue["version_id"], issue["node_id"]) if issue.get("node_id") else []
    siblings = taxonomy.get_children(issue["version_id"], node["parent_id"]) if node and node.get("parent_id") else []
    suggestions = SuggestionRepository(settings).list_suggestions(version_id=issue["version_id"])
    related = [item.model_dump() for item in suggestions if item.issue_id == issue_id]
    return {**issue, "parent": parent, "children": children, "siblings": [item for item in siblings if item["category_id"] != issue.get("node_id")], "suggestions": related}
