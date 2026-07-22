from uuid import uuid4
from backend.app.schemas.planning import DiagnosisBatchFeedback, DiagnosisTarget, MaintenancePlan

class AdaptivePlanningService:
    def __init__(self, llm=None) -> None:
        self.llm = llm

    def create(self, *, workflow_id: str, version_id: int, candidate_budget: int = 20) -> MaintenancePlan:
        return MaintenancePlan(id=f"plan_{uuid4().hex[:12]}", workflow_id=workflow_id,
            base_version_id=version_id, revision=1, strategy="sampling",
            targets=[DiagnosisTarget(issue_type="synonym_pollution", candidate_budget=candidate_budget)],
            max_model_calls=15, max_tokens=10000000, max_wall_seconds=300, max_rounds=1,
            target_quality_score=90)

    def revise(self, plan: MaintenancePlan, feedback: DiagnosisBatchFeedback) -> MaintenancePlan:
        calls = feedback.model_calls
        if plan.revision >= plan.max_rounds:
            return plan.model_copy(update={"revision": plan.revision + 1, "decision": "stop", "stop_reason": "max_rounds"})
        if calls >= plan.max_model_calls or feedback.tokens >= plan.max_tokens or feedback.wall_seconds >= plan.max_wall_seconds:
            return plan.model_copy(update={"revision": plan.revision + 1, "decision": "stop", "stop_reason": "budget_exhausted"})
        if feedback.failed / max(feedback.processed, 1) >= 0.3:
            decision = "shrink"
        elif feedback.hit_rate >= 0.3:
            decision = "expand"
        elif feedback.hit_rate < 0.03 and (feedback.previous_hit_rate or 0) < 0.03:
            return plan.model_copy(update={"revision": plan.revision + 1, "decision": "stop", "stop_reason": "consecutive_low_hit_rate"})
        else:
            decision = "continue"
        factor = 2 if decision == "expand" else 0.5 if decision == "shrink" else 1
        targets = [item.model_copy(update={"candidate_budget": max(1, min(1000, int(item.candidate_budget * factor)))}) for item in plan.targets]
        return plan.model_copy(update={"revision": plan.revision + 1, "decision": decision, "targets": targets})
