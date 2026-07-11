import time
import threading
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
    ) -> dict[str, Any]:
        resolved_plan = plan or DiagnosisPlan()
        run_id = self.repo.create_run(AgentRunRecord(
            workflow_id=workflow_id, agent_type="content_diagnosis", version_id=version_id,
            model_profile=self.settings.llm_model,
            budget={"candidate_limit": min(max(resolved_plan.estimated_candidates, 1), 1000)},
        ))
        candidates = TaxonomyRepository(self.settings).list_content_diagnosis_candidates(
            version_id, priority_subtrees=resolved_plan.priority_subtrees,
            limit=min(max(resolved_plan.estimated_candidates, 1), 1000),
        )
        ids = [self.repo.upsert_work_item(run_id, "candidate", str(item["category_id"]), item) for item in candidates]
        self.repo.update_run(run_id, status="running", coverage={"total": len(ids)})
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
        started = time.perf_counter()
        self.repo.record_event(workflow_id=run["workflow_id"], run_id=item.run_id,
                               work_item_id=item_id, agent_name="content_diagnosis",
                               event_type="agent_step", phase="candidate", status="running",
                               attempt=item.attempt, summary={"subject_id": item.subject_id})
        try:
            scope = ToolScope(run["workflow_id"], int(run["version_id"]), int(item.subject_id))
            tools = AgentToolFactory(self.settings, resource_limits=self.resource_limits).content_diagnosis_tools(scope)
            agent = ContentDiagnosisAgent(
                self.settings, llm=self.llm, tools=tools,
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
            return {"processed_count": 1, "issue_count": len(issues), "clean_count": int(not issues), "inconclusive_count": 0, "failed_count": 0}
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
            return {"processed_count": 1, "issue_count": 0, "clean_count": 0, "inconclusive_count": 0, "failed_count": 1}

    def finalize_run(self, run_id: str) -> dict[str, int]:
        counts = self.repo.counts(run_id)
        unfinished = counts.get("pending", 0) + counts.get("running", 0) + counts.get("retryable_failed", 0)
        failed = counts.get("permanent_failed", 0)
        status = "running" if unfinished else "completed_degraded" if failed else "completed"
        self.repo.update_run(run_id, status=status, coverage=counts)
        return counts

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
    return {"processed_count": 0, "issue_count": 0, "clean_count": 0, "inconclusive_count": 0, "failed_count": 0}
