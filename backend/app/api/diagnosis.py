import json
import time
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from openai import APIConnectionError, APITimeoutError
from pydantic import BaseModel, Field

from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent, DiagnosisPlanningAgent
from backend.app.services.diagnosis_service import DiagnosisService
from backend.app.services.model_router import ModelBudgetExceededError, ModelUnavailableError
from backend.app.services.report_service import ReportService
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.taxonomy_service import TaxonomyService
from backend.app.services.version_service import VersionService
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.schemas.agent_run import AgentRunRecord
from backend.app.schemas.issue import DiagnosisCoverage

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

class RunDiagnosisRequest(BaseModel):
    file_id: int | None = None
    version_id: int | None = None
    enable_ai_analysis: bool = False
    model_provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    ai_candidate_limit: int | None = Field(default=None, ge=1, le=1000)
    ai_wall_seconds: int | None = Field(default=None, ge=60, le=86400)
    ai_max_model_calls: int | None = Field(default=None, ge=1, le=10000)
    ai_token_budget: int | None = Field(default=None, ge=1)
    priority_subtree_ids: list[int] = Field(default_factory=list)
    sample_strategy: Literal["focused", "full_scan", "sampling"] = "focused"
    focus_issues: list[str] = Field(default_factory=list)


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
    if payload.model_provider != "deepseek" or payload.model_name != "deepseek-chat":
        raise HTTPException(status_code=400, detail="Only deepseek/deepseek-chat is supported.")
    version = VersionRepository(settings).get_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    VersionRepository(settings).update_model_metadata(
        version_id,
        diagnosis_mode="ai_enhanced" if payload.enable_ai_analysis else "deterministic_rules",
        diagnosis_model=payload.model_name if payload.enable_ai_analysis else None,
    )
    task_repo = TaskRepository(settings)
    task_id = task_repo.create_diagnosis_task(
        file_id=int(version["file_id"]), version_id=version_id,
        enable_ai_analysis=payload.enable_ai_analysis,
        model_provider=payload.model_provider if payload.enable_ai_analysis else None,
        model_name=payload.model_name if payload.enable_ai_analysis else None,
    )
    workflow_id = task_id
    run_repo = AgentRunRepository(settings)
    run_id = run_repo.create_run(AgentRunRecord(
        id=f"run_{task_id}", workflow_id=workflow_id, agent_type="diagnosis",
        version_id=version_id, model_profile=payload.model_name if payload.enable_ai_analysis else "rules",
        budget={
            "candidate_limit": payload.ai_candidate_limit or settings.diagnosis_ai_candidate_limit,
            "max_model_calls": payload.ai_max_model_calls or settings.llm_max_calls,
            "max_tokens": payload.ai_token_budget or settings.llm_max_tokens,
            "max_wall_seconds": payload.ai_wall_seconds or settings.diagnosis_ai_wall_seconds,
            "sample_strategy": payload.sample_strategy,
            "focus_issues": payload.focus_issues,
            "priority_subtree_ids": payload.priority_subtree_ids,
        },
    ))
    task_repo.attach_primary_run(task_id, run_id)
    started = time.perf_counter()
    try:
        total_nodes = TaxonomyRepository(settings).count_nodes(version_id)
        structure = DiagnosisService(settings).run_structure_diagnosis(version_id)
        task_repo.update_task(task_id=task_id, current_step="content_rule_detection", progress=45)
        content_count = DiagnosisService(settings).run_content_rule_diagnosis(version_id)
        candidate_count = 0
        ai_processed_count = 0
        ai_issue_count = None if payload.enable_ai_analysis else 0
        ai_analysis_status = "not_requested"
        ai_warning = None
        model_calls_used = 0
        tokens_used = 0
        degraded_reason_code = None
        plan = DiagnosisPlan(
            priority_subtree_ids=payload.priority_subtree_ids,
            sample_strategy=payload.sample_strategy,
            focus_issues=payload.focus_issues,
            estimated_candidates=payload.ai_candidate_limit or settings.diagnosis_ai_candidate_limit,
        )
        if payload.enable_ai_analysis:
            run_settings = settings.model_copy(update={
                "diagnosis_ai_wall_seconds": payload.ai_wall_seconds or settings.diagnosis_ai_wall_seconds,
                "llm_max_calls": payload.ai_max_model_calls or settings.llm_max_calls,
                "llm_max_tokens": payload.ai_token_budget or settings.llm_max_tokens,
            })
            task_repo.update_task(task_id=task_id, current_step="ai_analysis", progress=60)
            try:
                overview = TaxonomyService(run_settings).get_planning_overview(version_id)
                planned = DiagnosisPlanningAgent(run_settings).run(structure.summary, overview)
                plan = DiagnosisPlan.model_validate(planned).model_copy(update={
                    "priority_subtree_ids": payload.priority_subtree_ids or planned.priority_subtree_ids,
                    "sample_strategy": payload.sample_strategy,
                    "focus_issues": payload.focus_issues or planned.focus_issues,
                })
                if payload.ai_candidate_limit is not None:
                    # 用户明确请求高覆盖分析时，以请求值覆盖规划器的抽样数量。
                    plan.estimated_candidates = payload.ai_candidate_limit
                elif payload.sample_strategy == "full_scan":
                    plan.estimated_candidates = min(total_nodes, 1000)
                else:
                    plan.estimated_candidates = min(
                        plan.estimated_candidates,
                        settings.diagnosis_ai_candidate_limit,
                    )
                progress_state = {"processed": 0, "total": 0}

                def record_ai_progress(processed: int, total: int) -> None:
                    progress_state.update(processed=processed, total=total)
                    task_repo.update_task(
                        task_id=task_id,
                        current_step="ai_analysis",
                        progress=min(74, 60 + round(14 * processed / max(total, 1))),
                        result_payload={
                            "candidate_count": total,
                            "ai_processed_count": processed,
                        },
                    )

                agent = ContentDiagnosisAgent(
                    run_settings,
                    max_iter=settings.diagnosis_ai_max_iter,
                    progress_sink=record_ai_progress,
                )
                candidates = agent.select_candidates(version_id, plan)
                candidate_count = len(candidates)
                progress_state["total"] = candidate_count
                task_repo.update_task(
                    task_id=task_id,
                    result_payload={
                        "candidate_count": candidate_count,
                        "ai_processed_count": 0,
                    },
                )
                agent.candidate_selector = lambda _version_id, _plan: candidates
                ai_issues = agent.run(version_id, plan)
                model_calls_used = int(getattr(agent, "model_calls_used", 0))
                tokens_used = int(getattr(agent, "tokens_used", 0))
                ai_issue_count = len(ai_issues)
                content_count += ai_issue_count
                ai_processed_count = progress_state["processed"]
                suggestions = SuggestionAgent(settings, enable_ai=False).run(version_id)
                ai_analysis_status = "completed"
            except (
                ModelBudgetExceededError,
                ModelUnavailableError,
                APIConnectionError,
                APITimeoutError,
                ConnectionError,
                TimeoutError,
            ) as exc:
                if "agent" in locals():
                    model_calls_used = int(getattr(agent, "model_calls_used", 0))
                    tokens_used = int(getattr(agent, "tokens_used", 0))
                if "progress_state" in locals():
                    candidate_count = int(progress_state["total"])
                    ai_processed_count = int(progress_state["processed"])
                ai_analysis_status = "partial"
                ai_warning = _ai_degraded_warning(exc)
                degraded_reason_code = type(exc).__name__
                task_repo.update_task(
                    task_id=task_id,
                    current_step="ai_degraded",
                    progress=75,
                    result_payload={"ai_analysis_status": ai_analysis_status, "ai_warning": ai_warning},
                )
                suggestions = SuggestionAgent(settings, enable_ai=False).run(version_id)
        else:
            suggestions = SuggestionAgent(settings, enable_ai=False).run(version_id)
        skipped_count = max(candidate_count - ai_processed_count, 0)
        unexamined_reasons: dict[str, int] = {}
        if ai_analysis_status == "partial":
            unexamined = skipped_count or max(total_nodes - ai_processed_count, 0)
            unexamined_reasons[degraded_reason_code or "AI_INCOMPLETE"] = unexamined
            skipped_count = unexamined
        rule_issue_count = sum(
            item.get("source") in {"structure_rule", "content_rule"}
            for item in DiagnosisRepository(settings).list_issues(version_id)
        )
        coverage = DiagnosisCoverage(
            total_nodes=total_nodes,
            rule_scanned_nodes=total_nodes,
            rule_issue_count=rule_issue_count,
            candidate_count=candidate_count,
            deep_diagnosed_count=ai_processed_count,
            ai_issue_count=int(ai_issue_count or 0),
            skipped_count=skipped_count,
            failed_count=0,
            unexamined_reasons=unexamined_reasons,
            model_calls=model_calls_used,
            tokens_used=tokens_used,
            wall_seconds=round(time.perf_counter() - started, 3),
            plan_revision=1,
            stop_reason=ai_warning,
            rules_complete=True,
            ai_complete=not payload.enable_ai_analysis or ai_analysis_status == "completed",
            coverage_complete=not payload.enable_ai_analysis or ai_analysis_status == "completed",
            completion_status="partial" if ai_analysis_status == "partial" else "completed",
            run_id=run_id,
            workflow_id=workflow_id,
            plan=plan.model_dump(),
        ).model_dump()
        run_repo.update_run(
            run_id,
            status="completed_degraded" if ai_analysis_status == "partial" else "completed",
            coverage=coverage,
        )
        DiagnosisRepository(settings).link_run_issues(run_id=run_id, version_id=version_id)
        result = {
            "task_id": task_id, "version_id": version_id,
            "status": "waiting_review" if suggestions.review_batch_id else ("partial" if ai_analysis_status == "partial" else "completed"),
            "workflow_id": workflow_id, "run_id": run_id,
            "structure_issue_count": structure.issue_count,
            "content_issue_count": content_count, "candidate_count": candidate_count,
            "ai_processed_count": ai_processed_count,
            "ai_issue_count": ai_issue_count,
            "ai_candidate_limit": payload.ai_candidate_limit or settings.diagnosis_ai_candidate_limit,
            "ai_wall_seconds": payload.ai_wall_seconds or settings.diagnosis_ai_wall_seconds,
            "suggestion_count": suggestions.generated_count,
            "review_batch_id": suggestions.review_batch_id,
            "enable_ai_analysis": payload.enable_ai_analysis,
            "model_provider": payload.model_provider if payload.enable_ai_analysis else None,
            "model_name": payload.model_name if payload.enable_ai_analysis else None,
            "ai_analysis_status": ai_analysis_status,
            "ai_warning": ai_warning,
            "coverage": coverage,
            "report_type": "partial" if ai_analysis_status == "partial" else ("draft" if suggestions.review_batch_id else "final"),
        }
        all_issues = DiagnosisRepository(settings).list_issues(version_id)
        structure_count = sum(1 for item in all_issues if item["issue_category"] == "structure")
        final_content_count = len(all_issues) - structure_count
        high_risk_count = sum(1 for item in all_issues if item["risk_level"] == "high")
        quality_score = max(0.0, round(100 - structure_count * 0.2 - final_content_count * 0.5 - high_risk_count * 0.8, 1))
        VersionRepository(settings).update_quality_score(version_id, quality_score)
        result["quality_score"] = quality_score
        if suggestions.review_batch_id:
            batch_repo = ReviewBatchRepository(settings)
            batch_repo.create(
                batch_id=suggestions.review_batch_id,
                file_id=int(version["file_id"]), version_id=version_id, task_id=task_id,
            )
            batch_repo.refresh_status(suggestions.review_batch_id)
        task_repo.update_task(
            task_id=task_id,
            status="waiting_review" if suggestions.review_batch_id else ("partial" if ai_analysis_status == "partial" else "completed"),
            current_step="review_pending" if suggestions.review_batch_id else "completed",
            progress=80 if suggestions.review_batch_id else 100,
            result_payload=result,
        )
        report = ReportService(settings).generate_diagnosis_report(
            version_id,
            report_type=result["report_type"],
            review_batch_id=suggestions.review_batch_id,
            workflow_id=workflow_id,
            run_id=run_id,
        )
        result["report_path"] = str(report.report_path)
        task_repo.update_task(task_id=task_id, result_payload={"report_path": str(report.report_path)})
        return result
    except Exception as exc:
        run_repo.update_run(run_id, status="failed", coverage={
            "run_id": run_id, "workflow_id": workflow_id,
            "completion_status": "failed", "coverage_complete": False,
            "stop_reason": str(exc), "wall_seconds": round(time.perf_counter() - started, 3),
        })
        task_repo.update_task(task_id=task_id, status="failed", current_step="failed", error_message=str(exc))
        raise HTTPException(status_code=502, detail=f"Diagnosis failed: {exc}") from exc


@router.get("/summary")
def get_diagnosis_summary(version_id: int, request: Request) -> dict[str, Any]:
    if VersionRepository(request.app.state.settings).get_version(version_id) is None:
        raise HTTPException(status_code=404, detail="Version not found.")
    repo = DiagnosisRepository(request.app.state.settings)
    issues = repo.list_issues(version_id)
    overview = TaxonomyRepository(request.app.state.settings).get_overview_counts(version_id)
    structure_count = sum(1 for item in issues if item["issue_category"] == "structure")
    content_count = len(issues) - structure_count
    high_risk = sum(1 for item in issues if item["risk_level"] == "high")
    score = max(0.0, round(100 - structure_count * 0.2 - content_count * 0.5 - high_risk * 0.8, 1))
    task_repo = TaskRepository(request.app.state.settings)
    task = task_repo.get_latest_for_version(version_id)
    if task and task.get("status") in {"pending", "running"}:
        raise HTTPException(status_code=409, detail="Diagnosis is not completed yet.")
    batch = ReviewBatchRepository(request.app.state.settings).get_for_task(str(task["id"])) if task else None
    task_result = json.loads(task.get("result_payload") or "{}") if task else {}
    return {"version_id": version_id, "total_nodes": overview["node_count"], "structure_issue_count": structure_count, "content_issue_count": content_count, "high_risk_count": high_risk, "quality_score": score,
            "task_id": task["id"] if task else None,
            "task_status": task.get("status") if task else None,
            "review_batch_id": batch.get("id") if batch else None,
            "enable_ai_analysis": bool(task["enable_ai_analysis"]) if task else False,
            "model_provider": task.get("model_provider") if task else None,
            "model_name": task.get("model_name") if task else None,
            "ai_analysis_status": task_result.get("ai_analysis_status"),
            "ai_warning": task_result.get("ai_warning"),
            "coverage": task_result.get("coverage") or {},
            "run_id": task_result.get("run_id") or (task.get("primary_run_id") if task else None),
            "workflow_id": task_result.get("workflow_id"),
            "report_type": task_result.get("report_type"),
            "report_path": task_result.get("report_path")}


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


def _ai_degraded_warning(exc: Exception) -> str:
    if isinstance(exc, ModelBudgetExceededError):
        reason = f"模型预算或运行时间达到上限（{exc}）"
    elif isinstance(exc, ModelUnavailableError):
        reason = f"所选模型暂不可用（{exc}）"
    else:
        reason = f"无法连接所选模型（{exc}）"
    return f"AI 分析因{reason}提前停止；已保留规则诊断和已写入的 AI 结果，并继续生成降级报告。"
