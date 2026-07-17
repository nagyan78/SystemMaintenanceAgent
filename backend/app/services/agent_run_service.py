import time
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.agent_run import AgentRunRecord
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent
from backend.app.services.retry_policy import RetryPolicy
from backend.app.services.suggestion_service import SuggestionAgent
from backend.app.services.tool_factory import AgentResourceLimits, AgentToolFactory, ToolScope


class AgentRunService:
    def __init__(self, settings: Settings, *, llm: Any | None = None) -> None:
        self.settings = settings
        self.llm = llm
        self.repo = AgentRunRepository(settings)
        self.retry = RetryPolicy(max_attempts=settings.agent_work_item_max_attempts)
        self.llm_slots = threading.BoundedSemaphore(max(1, settings.agent_llm_max_concurrency))
        self.resource_limits = AgentResourceLimits.from_settings(settings)

    def prepare_content_candidates(
        self, *, workflow_id: str, version_id: int, plan: DiagnosisPlan | None = None,
        rule_scanned_nodes: int = 0, rule_issue_count: int = 0,
        budget: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_plan = plan or DiagnosisPlan()
        configured_budget = {
            "candidate_limit": min(max(resolved_plan.estimated_candidates, 0), 1000),
            "max_model_calls": self.settings.llm_max_calls,
            "max_tokens": self.settings.llm_max_tokens,
            "max_wall_seconds": self.settings.diagnosis_ai_wall_seconds,
            "rule_scanned_nodes": rule_scanned_nodes,
            "rule_issue_count": rule_issue_count,
            "plan": resolved_plan.model_dump(),
            **(budget or {}),
        }
        run_id = self.repo.create_run(AgentRunRecord(
            workflow_id=workflow_id, agent_type="content_diagnosis", version_id=version_id,
            model_profile=self.settings.llm_model,
            budget=configured_budget,
        ))
        candidates = TaxonomyRepository(self.settings).list_content_diagnosis_candidates(
            version_id, priority_subtrees=resolved_plan.priority_subtrees,
            priority_subtree_ids=resolved_plan.priority_subtree_ids,
            focus_issues=resolved_plan.focus_issues,
            sample_strategy=resolved_plan.sample_strategy,
            limit=min(max(resolved_plan.estimated_candidates, 1), 1000),
        )
        ids = [self.repo.upsert_work_item(run_id, "candidate", str(item["category_id"]), item) for item in candidates]
        self.repo.update_run(run_id, status="running", coverage={
            "total_nodes": rule_scanned_nodes, "rule_scanned_nodes": rule_scanned_nodes,
            "rule_issue_count": rule_issue_count, "candidate_count": len(ids),
        })
        return {"run_id": run_id, "work_item_ids": ids}

    def execute_content_work_item(self, item_id: str, *, worker_id: str = "local-worker") -> dict[str, int]:
        if not self.repo.claim_work_item(item_id, worker_id=worker_id):
            return _zero_delta()
        item = self.repo.get_work_item(item_id)
        if item is None:
            return _zero_delta()
        run = self.repo.get_run(item.run_id)
        if run is None:
            return _zero_delta()
        budget = run.get("budget") or {}
        usage = self.repo.usage_totals(item.run_id)
        max_calls = int(budget.get("max_model_calls") or self.settings.llm_max_calls)
        max_tokens = int(budget.get("max_tokens") or self.settings.llm_max_tokens)
        max_wall = int(budget.get("max_wall_seconds") or self.settings.diagnosis_ai_wall_seconds)
        elapsed = _elapsed_seconds(run.get("created_time"))
        if usage["model_calls"] >= max_calls or usage["tokens_used"] >= max_tokens or elapsed >= max_wall:
            reason = "model_calls" if usage["model_calls"] >= max_calls else "tokens" if usage["tokens_used"] >= max_tokens else "wall_time"
            self.repo.skip_work_item(item_id, reason=f"budget exhausted: {reason}")
            return {**_zero_delta(), "skipped_count": 1}
        started = time.perf_counter()
        self.repo.record_event(workflow_id=run["workflow_id"], run_id=item.run_id,
                               work_item_id=item_id, agent_name="content_diagnosis",
                               event_type="agent_step", phase="candidate", status="running",
                               attempt=item.attempt, summary={"subject_id": item.subject_id})
        try:
            remaining_calls = max(1, max_calls - usage["model_calls"])
            remaining_tokens = max(1, max_tokens - usage["tokens_used"])
            runtime_settings = self.settings.model_copy(update={
                "llm_max_calls": remaining_calls,
                "llm_max_tokens": remaining_tokens,
                "diagnosis_ai_max_iter": min(self.settings.diagnosis_ai_max_iter, remaining_calls),
                "diagnosis_ai_wall_seconds": min(
                    self.settings.diagnosis_ai_wall_seconds,
                    int(budget.get("max_wall_seconds") or self.settings.diagnosis_ai_wall_seconds),
                ),
            })
            scope = ToolScope(run["workflow_id"], int(run["version_id"]), int(item.subject_id))
            tools = AgentToolFactory(runtime_settings, resource_limits=self.resource_limits).content_diagnosis_tools(scope)
            agent = ContentDiagnosisAgent(
                runtime_settings, llm=self.llm, tools=tools,
                max_iter=runtime_settings.diagnosis_ai_max_iter,
                candidate_selector=lambda _version_id, _plan: [item.input_payload],
                event_sink=lambda event: self.repo.record_event(
                    workflow_id=run["workflow_id"], run_id=item.run_id, work_item_id=item_id,
                    agent_name="content_diagnosis", phase="candidate", attempt=item.attempt,
                    **event,
                ),
            )
            with self.llm_slots:
                issues = agent.run(int(run["version_id"]), DiagnosisPlan(estimated_candidates=1))
            status = "succeeded" if issues else "clean"
            payload = {"issues": [issue.model_dump() for issue in issues]}
            self.repo.complete_work_item(item_id, status=status, result_payload=payload)
            self.repo.record_event(
                workflow_id=run["workflow_id"], run_id=item.run_id, work_item_id=item_id,
                agent_name="content_diagnosis", event_type="candidate_completed",
                phase="candidate", status=status, attempt=item.attempt,
                latency_ms=int((time.perf_counter() - started) * 1000),
                model=self.settings.llm_model,
                summary={"subject_id": item.subject_id, "issue_count": len(issues)},
            )
            return {"processed_count": 1, "issue_count": len(issues), "clean_count": int(not issues), "inconclusive_count": 0, "failed_count": 0, "skipped_count": 0}
        except Exception as exc:
            retryable = self.retry.classify(exc) == "retryable_external"
            status = self.repo.fail_work_item(item_id, retryable=retryable, error_code=type(exc).__name__, error_message=str(exc))
            self.repo.record_event(
                workflow_id=run["workflow_id"], run_id=item.run_id, work_item_id=item_id,
                agent_name="content_diagnosis", event_type="agent_step", phase="candidate",
                status=status, attempt=item.attempt,
                latency_ms=int((time.perf_counter() - started) * 1000),
                summary={"subject_id": item.subject_id, "error_code": type(exc).__name__},
            )
            return {"processed_count": 1, "issue_count": 0, "clean_count": 0, "inconclusive_count": 0, "failed_count": 1, "skipped_count": 0}

    def finalize_run(self, run_id: str) -> dict[str, int]:
        counts = self.repo.counts(run_id)
        unfinished = counts.get("pending", 0) + counts.get("running", 0) + counts.get("retryable_failed", 0)
        failed = counts.get("permanent_failed", 0)
        status = "running" if unfinished else "completed_degraded" if failed or counts.get("skipped", 0) else "completed"
        run = self.repo.get_run(run_id) or {}
        budget = run.get("budget") or {}
        usage = self.repo.usage_totals(run_id)
        deep_count = sum(int(counts.get(key, 0)) for key in ("succeeded", "clean", "inconclusive"))
        failed_count = int(counts.get("permanent_failed", 0))
        skipped_count = int(counts.get("skipped", 0))
        reasons: dict[str, int] = {}
        for item in self.repo.list_work_items(run_id):
            if item.status in {"skipped", "permanent_failed", "retryable_failed"}:
                key = item.error_code or item.status
                reasons[key] = reasons.get(key, 0) + 1
        completion = "partial" if failed_count or skipped_count or unfinished else "completed"
        stop_reason = None
        if skipped_count:
            stop_reason = "模型调用、Token 或运行时间预算达到上限"
        elif failed_count:
            stop_reason = "部分候选深诊断失败"
        coverage = {
            "total_nodes": int(budget.get("rule_scanned_nodes", 0)),
            "rule_scanned_nodes": int(budget.get("rule_scanned_nodes", 0)),
            "rule_issue_count": int(budget.get("rule_issue_count", 0)),
            "candidate_count": int(counts.get("total", 0)),
            "deep_diagnosed_count": deep_count,
            "ai_issue_count": int(counts.get("succeeded", 0)),
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "unexamined_reasons": reasons,
            **usage,
            "wall_seconds": round(_elapsed_seconds(run.get("created_time")), 3),
            "plan_revision": int(run.get("plan_revision", 1)),
            "stop_reason": stop_reason,
            "rules_complete": int(budget.get("rule_scanned_nodes", 0)) > 0,
            "ai_complete": completion == "completed",
            "coverage_complete": completion == "completed" and int(budget.get("rule_scanned_nodes", 0)) > 0,
            "completion_status": completion,
            "run_id": run_id,
            "workflow_id": run.get("workflow_id"),
            "plan": budget.get("plan") or {},
            "work_item_counts": counts,
        }
        self.repo.update_run(run_id, status=status, coverage=coverage)
        return counts

    def coverage_for_run(self, run_id: str) -> dict[str, Any]:
        run = self.repo.get_run(run_id)
        return dict(run.get("coverage") or {}) if run else {}

    def prepare_suggestion_issues(
        self, *, workflow_id: str, version_id: int, analysis_run_id: str | None = None,
    ) -> dict[str, Any]:
        review_batch_id = f"review_{uuid4().hex[:12]}"
        run_id = self.repo.create_run(AgentRunRecord(
            workflow_id=workflow_id, agent_type="suggestion_generation", version_id=version_id,
            model_profile=self.settings.llm_model,
            budget={"review_batch_id": review_batch_id, "analysis_run_id": analysis_run_id},
        ))
        issue_ids: list[int] = []
        if analysis_run_id:
            for item in self.repo.list_work_items(analysis_run_id):
                for issue in item.result_payload.get("issues", []):
                    raw_id = issue.get("issue_id")
                    if isinstance(raw_id, str) and raw_id.startswith("issue_"):
                        issue_ids.append(int(raw_id.removeprefix("issue_")))
        if not issue_ids:
            issue_ids = [int(issue["id"]) for issue in DiagnosisRepository(self.settings).list_pending_issues(version_id)]
        ids = [self.repo.upsert_work_item(run_id, "issue", str(issue_id), {"issue_id": issue_id}) for issue_id in issue_ids]
        self.repo.update_run(run_id, status="running", coverage={"total": len(ids)})
        return {"run_id": run_id, "work_item_ids": ids, "review_batch_id": review_batch_id}

    def execute_suggestion_work_item(self, item_id: str, *, worker_id: str = "local-worker") -> dict[str, int]:
        if not self.repo.claim_work_item(item_id, worker_id=worker_id):
            return {"processed_count": 0, "suggestion_count": 0, "failed_count": 0}
        item = self.repo.get_work_item(item_id)
        run = self.repo.get_run(item.run_id) if item else None
        if item is None or run is None:
            return {"processed_count": 0, "suggestion_count": 0, "failed_count": 0}
        started = time.perf_counter()
        try:
            review_batch_id = str(run["budget"]["review_batch_id"])
            with self.llm_slots:
                result = SuggestionAgent(
                    self.settings, llm=self.llm, review_batch_id=review_batch_id,
                    work_item_id=item_id, analysis_run_id=run["budget"].get("analysis_run_id"),
                    workflow_id=run["workflow_id"], enable_ai=self.llm is not None,
                    resource_limits=self.resource_limits,
                    event_sink=lambda event: self.repo.record_event(
                        workflow_id=run["workflow_id"], run_id=item.run_id, work_item_id=item_id,
                        agent_name="suggestion_generation", phase="suggestion", attempt=item.attempt,
                        **event,
                    ),
                ).run(int(run["version_id"]), issue_ids=[int(item.subject_id)])
            status = "succeeded" if result.generated_count else "inconclusive"
            self.repo.complete_work_item(item_id, status=status, result_payload={"suggestion_ids": [record.id for record in result.suggestions]})
            self.repo.record_event(
                workflow_id=run["workflow_id"], run_id=item.run_id, work_item_id=item_id,
                agent_name="suggestion_generation", event_type="issue_completed", phase="suggestion",
                status=status, attempt=item.attempt, latency_ms=int((time.perf_counter()-started)*1000),
                model=self.settings.llm_model,
                summary={"issue_id": item.subject_id, "suggestion_count": result.generated_count},
            )
            return {"processed_count": 1, "suggestion_count": result.generated_count, "failed_count": 0}
        except Exception as exc:
            retryable = self.retry.classify(exc) == "retryable_external"
            self.repo.fail_work_item(item_id, retryable=retryable, error_code=type(exc).__name__, error_message=str(exc))
            return {"processed_count": 1, "suggestion_count": 0, "failed_count": 1}


def _zero_delta() -> dict[str, int]:
    return {"processed_count": 0, "issue_count": 0, "clean_count": 0, "inconclusive_count": 0, "failed_count": 0, "skipped_count": 0}


def _elapsed_seconds(created_time: Any) -> float:
    if not created_time:
        return 0.0
    try:
        created = datetime.fromisoformat(str(created_time))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())
    except (TypeError, ValueError):
        return 0.0
