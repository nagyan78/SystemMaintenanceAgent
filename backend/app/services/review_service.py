from typing import Any

from backend.app.config import Settings
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.schemas.suggestion import AdjustmentSuggestion, SuggestionRecord
from backend.app.services.action_service import ActionService
from backend.app.services.version_service import VersionService
from backend.app.services.version_verification_service import VersionVerificationService
from backend.app.services.report_service import ReportService
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.task_repo import TaskRepository
from backend.app.tools.export_tools import export_excel
import shutil
from backend.app.tools.validation_tools import validate_suggestion_action
from backend.app.services.agent_memory_service import AgentMemoryService
from backend.app.services.suggestion_consistency_service import SuggestionConsistencyService
from backend.app.services.execution_preview_service import ExecutionPreviewService
from backend.app.db import connect


class ReviewService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.suggestion_repo = SuggestionRepository(settings)
        self.log_repo = OperationLogRepository(settings)

    def list_review_batch(self, review_batch_id: str) -> list[SuggestionRecord]:
        return self.suggestion_repo.list_suggestions(review_batch_id=review_batch_id)

    def approve_suggestion(self, suggestion_id: int, operator: str = "local_user") -> SuggestionRecord:
        suggestion = self._require_mutable_suggestion(suggestion_id)
        checked = SuggestionConsistencyService(self.settings).require_executable(suggestion)
        if not checked.executable:
            raise ValueError("review_only 需要人工选择暂不处理或确认为误报，不能作为修改动作通过。")
        validation = validate_suggestion_action(checked.suggestion, self.settings)
        if not validation.valid:
            raise ValueError(f"建议动作不可通过：{validation.reason}")
        self.suggestion_repo.update_consistency(suggestion.id, suggestion=checked.suggestion,
            change_preview=checked.change_preview, status="valid", reason=None)
        self.suggestion_repo.update_status(suggestion_id, "approved")
        DiagnosisRepository(self.settings).update_status(suggestion.issue_id, "confirmed")
        self._log(suggestion, operator, "approve_suggestion")
        AgentMemoryService(self.settings).record_review_feedback(workflow_id=str(suggestion.action_payload.get("workflow_id") or "manual"), version_id=suggestion.version_id, suggestion=suggestion, decision="approve")
        return self.suggestion_repo.get_suggestion(suggestion_id) or suggestion

    def reject_suggestion(
        self,
        suggestion_id: int,
        operator: str = "local_user",
        reject_reason: str | None = None,
    ) -> SuggestionRecord:
        suggestion = self._require_mutable_suggestion(suggestion_id)
        self.suggestion_repo.update_status(suggestion_id, "rejected")
        DiagnosisRepository(self.settings).update_status(suggestion.issue_id, "confirmed")
        self._log(
            suggestion,
            operator,
            "reject_suggestion",
            {"reject_reason": reject_reason or ""},
        )
        if reject_reason:
            AgentMemoryService(self.settings).record_review_feedback(workflow_id=str(suggestion.action_payload.get("workflow_id") or "manual"), version_id=suggestion.version_id, suggestion=suggestion, decision="reject", reason=reject_reason)
        return self.suggestion_repo.get_suggestion(suggestion_id) or suggestion

    def defer_suggestion(
        self,
        suggestion_id: int,
        *,
        issue_status: str,
        operator: str = "local_user",
        reason: str | None = None,
    ) -> SuggestionRecord:
        suggestion = self._require_mutable_suggestion(suggestion_id)
        self.suggestion_repo.update_status(suggestion_id, "deferred")
        DiagnosisRepository(self.settings).update_status(suggestion.issue_id, issue_status)
        self._log(suggestion, operator, "defer_suggestion", {"issue_status": issue_status, "reason": reason or ""})
        return self.suggestion_repo.get_suggestion(suggestion_id) or suggestion

    def edit_suggestion(
        self,
        suggestion_id: int,
        edited: AdjustmentSuggestion,
        operator: str = "local_user",
    ) -> SuggestionRecord:
        current = self._require_mutable_suggestion(suggestion_id)
        checked = SuggestionConsistencyService(self.settings).check(edited, normalize_new=True)
        edited = checked.suggestion
        validation = validate_suggestion_action(edited, self.settings)
        if not validation.valid:
            raise ValueError(validation.reason)
        self.suggestion_repo.update_suggestion(suggestion_id, edited)
        self.suggestion_repo.update_consistency(suggestion_id, suggestion=edited,
            change_preview=checked.change_preview, status="invalid" if checked.downgraded else "valid", reason=checked.reason)
        updated = self.suggestion_repo.get_suggestion(suggestion_id)
        self._log(updated or current, operator, "edit_suggestion")
        return updated or current

    def batch_approve(
        self,
        suggestion_ids: list[int],
        operator: str = "local_user",
    ) -> list[SuggestionRecord]:
        suggestions = self.suggestion_repo.list_by_ids(suggestion_ids)
        if len(suggestions) != len(set(suggestion_ids)):
            raise ValueError("部分 suggestion_id 不存在。")
        for suggestion in suggestions:
            checked = SuggestionConsistencyService(self.settings).check(suggestion)
            if not checked.valid or not checked.executable:
                raise ValueError(f"建议 {suggestion.id} 不是可执行修改，不能批量通过；请选择暂不处理或确认为误报。")
            if suggestion.status != "pending":
                raise ValueError("批量接受只允许 pending 建议。")
            if suggestion.risk_level != "low":
                raise ValueError("批量接受只允许 low 风险建议。")
        for suggestion in suggestions:
            self.approve_suggestion(suggestion.id, operator)
        return self.suggestion_repo.list_by_ids(suggestion_ids)

    def apply_workflow_decision(self, review_batch_id: str, decision: dict[str, Any]) -> int:
        operator = decision.get("operator") or "local_user"
        approved_ids = [int(item) for item in decision.get("approved_suggestion_ids", [])]
        rejected_ids = [int(item) for item in decision.get("rejected_suggestion_ids", [])]
        confirmed_without_action_ids = [int(item) for item in decision.get("confirmed_without_action_suggestion_ids", [])]
        uncertain_ids = [int(item) for item in decision.get("uncertain_suggestion_ids", [])]
        edits = decision.get("edits", []) or []
        review_decision = decision.get("decision")

        batch_ids = {item.id for item in self.list_review_batch(review_batch_id)}
        if approved_ids or rejected_ids or confirmed_without_action_ids or uncertain_ids or edits:
            requested_ids = set(approved_ids) | set(rejected_ids) | set(confirmed_without_action_ids) | set(uncertain_ids) | {int(item["suggestion_id"]) for item in edits}
            if not requested_ids.issubset(batch_ids):
                raise ValueError("审核决策包含不属于当前批次的 suggestion_id。")
            groups = [set(approved_ids), set(rejected_ids), set(confirmed_without_action_ids), set(uncertain_ids)]
            if sum(len(group) for group in groups) != len(set().union(*groups)):
                raise ValueError("同一建议不能提交多个审核结论。")

        for edit in edits:
            current = self.suggestion_repo.get_suggestion(int(edit["suggestion_id"]))
            if current is None:
                raise ValueError("编辑的 suggestion_id 不存在。")
            payload = {**current.model_dump(), **edit.get("suggestion", {})}
            payload.pop("id", None)
            payload.pop("review_batch_id", None)
            self.edit_suggestion(
                int(edit["suggestion_id"]),
                AdjustmentSuggestion.model_validate(payload),
                operator,
            )
        for suggestion_id in approved_ids:
            self.approve_suggestion(suggestion_id, operator)
        for suggestion_id in rejected_ids:
            self.reject_suggestion(suggestion_id, operator, decision.get("reject_reason"))
        for suggestion_id in confirmed_without_action_ids:
            self.defer_suggestion(suggestion_id, issue_status="false_positive", operator=operator, reason="confirmed false positive")
        for suggestion_id in uncertain_ids:
            self.defer_suggestion(suggestion_id, issue_status="deferred", operator=operator, reason="insufficient evidence")
        if review_decision == "reject" and not rejected_ids:
            for suggestion in self.list_review_batch(review_batch_id):
                if suggestion.status in {"pending", "edited"}:
                    self.reject_suggestion(suggestion.id, operator, decision.get("reject_reason"))
        return len(approved_ids)

    def auto_complete_review(self, review_batch_id: str, operator: str = "local_user") -> dict[str, Any]:
        """Approve complete executable proposals and ignore every non-executable proposal."""
        suggestions = self.list_review_batch(review_batch_id)
        if not suggestions:
            raise ValueError("审核批次没有建议。")
        approved_ids: list[int] = []
        ignored_ids: list[int] = []
        unchanged_ids: list[int] = []
        consistency = SuggestionConsistencyService(self.settings)
        for suggestion in suggestions:
            if suggestion.status in {"approved", "rejected", "executed"}:
                unchanged_ids.append(suggestion.id)
                continue
            result = consistency.check(suggestion)
            if result.valid and result.executable:
                if suggestion.status == "deferred":
                    self.suggestion_repo.update_status(suggestion.id, "pending")
                self.approve_suggestion(suggestion.id, operator)
                approved_ids.append(suggestion.id)
                continue
            if suggestion.status in {"pending", "edited"}:
                self.defer_suggestion(
                    suggestion.id, issue_status="deferred", operator=operator,
                    reason=result.reason or "无法生成可靠的可执行修改，已自动忽略",
                )
            ignored_ids.append(suggestion.id)
        batch = ReviewBatchRepository(self.settings).refresh_status(review_batch_id)
        completion = self.complete_without_execution(review_batch_id, operator=operator) if not approved_ids and not any(
            item.status == "approved" for item in self.list_review_batch(review_batch_id)
        ) else None
        return {"review_batch_id": review_batch_id, "approved_ids": approved_ids,
                "ignored_ids": ignored_ids, "unchanged_ids": unchanged_ids, "batch": batch,
                "completion": completion}

    def complete_without_execution(self, review_batch_id: str, *, operator: str = "local_user") -> dict[str, Any]:
        suggestions = self.list_review_batch(review_batch_id)
        if any(item.status in {"pending", "edited", "approved"} for item in suggestions):
            raise ValueError("仍有待审核或已通过动作，不能按无执行动作结束。")
        batch_repo = ReviewBatchRepository(self.settings)
        batch = self.ensure_batch_task_link(review_batch_id) or batch_repo.get(review_batch_id)
        if batch is None:
            raise ValueError("Review batch not found.")
        version_id = int(batch["version_id"])
        task = TaskRepository(self.settings).get_task(str(batch["task_id"])) if batch.get("task_id") else None
        workflow_id = batch.get("workflow_id") or (task or {}).get("workflow_id")
        run_id = (task or {}).get("primary_run_id")
        if task:
            TaskRepository(self.settings).update_task(
                task_id=str(task["id"]), status="completed", current_step="completed",
                progress=100, version_id=version_id,
                result_payload={
                    "status": "completed", "completion_reason": "no_executable_actions",
                    "review_batch_id": review_batch_id, "report_type": "final",
                },
            )
        report = ReportService(self.settings).generate_diagnosis_report(
            version_id, report_type="final", review_batch_id=review_batch_id,
            workflow_id=workflow_id, run_id=run_id,
        )
        if task:
            TaskRepository(self.settings).update_task(
                task_id=str(task["id"]), result_payload={"report_path": str(report.report_path)},
            )
        OperationLogRepository(self.settings).create_log(
            version_id=version_id, operator=operator,
            operation_type="complete_review_without_execution",
            operation_detail={"review_batch_id": review_batch_id,
                              "suggestion_count": len(suggestions)},
        )
        return {"status": "completed", "reason": "no_executable_actions",
                "version_id": version_id, "report_path": str(report.report_path)}

    def ensure_batch_task_link(self, review_batch_id: str) -> dict[str, Any] | None:
        batches = ReviewBatchRepository(self.settings)
        batch = batches.get(review_batch_id)
        if not batch or batch.get("task_id"):
            return batch
        candidate = TaskRepository(self.settings).get_latest_for_version(int(batch["version_id"]))
        if not candidate or candidate.get("status") not in {"waiting_review", "running"}:
            return batch
        task = TaskRepository(self.settings).get_task(str(candidate["id"])) or candidate
        batches.attach_task(review_batch_id, task_id=str(task["id"]), workflow_id=task.get("workflow_id"))
        TaskRepository(self.settings).update_task(
            task_id=str(task["id"]), result_payload={"review_batch_id": review_batch_id}
        )
        return batches.get(review_batch_id)

    def execute_approved_actions(self, review_batch_id: str, operator: str = "local_user") -> dict[str, Any]:
        batch_repo = ReviewBatchRepository(self.settings)
        suggestions = self.list_review_batch(review_batch_id)
        batch = self.ensure_batch_task_link(review_batch_id) or batch_repo.get(review_batch_id)
        if batch is None and suggestions:
            legacy_version = VersionRepository(self.settings).get_version(suggestions[0].version_id)
            if legacy_version is not None:
                batch_repo.create(
                    batch_id=review_batch_id,
                    file_id=int(legacy_version["file_id"]),
                    version_id=int(legacy_version["id"]),
                )
                batch = batch_repo.refresh_status(review_batch_id)
        if batch is None:
            raise ValueError("Review batch not found.")
        preview_guard = ExecutionPreviewService(self.settings).require_executable(review_batch_id)
        open_suggestions = [item for item in suggestions if item.status in {"pending", "edited"}]
        if open_suggestions:
            raise ValueError("审核尚未完成，所有建议必须先通过、驳回或明确延后。")
        approved = list(preview_guard.get("suggestions") or [])
        approved_source = [item for item in suggestions if item.status == "approved"]
        for item in approved:
            checked = SuggestionConsistencyService(self.settings).require_executable(item)
            if not checked.executable:
                raise ValueError(f"建议 {item.id} 不可执行：{checked.reason or '仅供人工审核'}")
        base_version_id = suggestions[0].version_id if suggestions else int(batch["version_id"])
        base_version = VersionRepository(self.settings).get_version(base_version_id)
        if base_version is None:
            raise ValueError("Review batch base version not found.")
        latest_version = VersionRepository(self.settings).get_latest_for_file(int(base_version["file_id"]))
        if latest_version is None:
            raise ValueError("No version found for review batch file.")
        source_version_id = int(base_version["id"])
        workflow_id = batch.get("workflow_id")
        linked_task = TaskRepository(self.settings).get_task(str(batch["task_id"])) if batch.get("task_id") else None
        run_id = (linked_task or {}).get("primary_run_id")
        batch_repo.mark_executing(review_batch_id)
        try:
            action_result = ActionService(self.settings).execute_suggestion_records(
                version_id=source_version_id,
                review_batch_id=review_batch_id,
                approved=approved,
                operator=operator,
                persist_side_effects=False,
            )
        except Exception as exc:
            batch_repo.mark_failed(review_batch_id)
            self._record_execution_failure(
                review_batch_id=review_batch_id, source_version_id=source_version_id,
                review_hash=preview_guard.get("review_hash"), workflow_id=workflow_id,
                run_id=run_id, exc=exc,
            )
            raise
        if not base_version.get("snapshot_path"):
            exported = export_excel(source_version_id, self.settings)
            snapshot_dir = self.settings.export_dir / "snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = snapshot_dir / f"{base_version['version_no']}_{review_batch_id}_before.xlsx"
            shutil.copy2(exported, snapshot_path)
            VersionRepository(self.settings).update_snapshot_path(source_version_id, str(snapshot_path))
        existing_result = VersionRepository(self.settings).get_by_action_batch(
            action_result.action_batch_id
        )
        latest_is_compatible_batch_descendant = (
            latest_version.get("parent_version_id") == source_version_id
            and latest_version.get("action_batch_id") is not None
        )
        if (
            int(latest_version["id"]) != source_version_id
            and existing_result is None
            and not latest_is_compatible_batch_descendant
        ):
            raise ValueError("审核基线已过期：当前文件已产生更新版本，请基于最新版本重新诊断。")
        try:
            save_result = VersionService(self.settings).save_executed_action_batch(
                base_version_id=source_version_id, review_batch_id=review_batch_id,
                nodes=action_result.nodes, suggestion_ids=[item.id for item in approved_source], operator=operator,
                action_batch_id=action_result.action_batch_id,
                source_workflow_id=workflow_id,
            )
            verification = VersionVerificationService(self.settings).verify(
                base_version_id=source_version_id,
                new_version_id=save_result.new_version_id,
            )
        except Exception as exc:
            batch_repo.mark_failed(review_batch_id)
            self._record_execution_failure(
                review_batch_id=review_batch_id, source_version_id=source_version_id,
                target_version_id=(save_result.new_version_id if "save_result" in locals() else None),
                review_hash=preview_guard.get("review_hash"), workflow_id=workflow_id,
                run_id=run_id, exc=exc,
            )
            raise
        diagnosis_repo = DiagnosisRepository(self.settings)
        new_issues = diagnosis_repo.list_issues(save_result.new_version_id)
        new_by_key = {(item.get("issue_type_code"), item.get("node_id")): item for item in new_issues}
        for item in suggestions:
            source_issue = diagnosis_repo.get_issue_detail(item.issue_id)
            if not source_issue or source_issue.get("status") not in {"false_positive", "deferred"}:
                continue
            matched = new_by_key.get((source_issue.get("issue_type_code"), source_issue.get("node_id")))
            if matched:
                diagnosis_repo.update_status(int(matched["id"]), str(source_issue["status"]))
        report = None
        if verification.status != "failed":
            report = ReportService(self.settings).generate_diagnosis_report(
                save_result.new_version_id, report_type="final", review_batch_id=review_batch_id,
                workflow_id=workflow_id, run_id=run_id,
            )
        batch_repo.mark_executed(review_batch_id, save_result.new_version_id)
        for item in approved_source:
            diagnosis_repo.update_status(item.issue_id, "resolved")
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT INTO version_execution_record(review_batch_id,source_version_id,target_version_id,review_hash,action_summary,status,workflow_id,run_id)
                   VALUES(?,?,?,?,?,'executed',?,?)""",
                (review_batch_id, source_version_id, save_result.new_version_id, preview_guard["review_hash"],
                 str({"suggestion_ids": [item.id for item in approved_source],
                      "executed_action_suggestion_ids": [item.id for item in approved]}), workflow_id, run_id),
            )
        batch = batch_repo.get(review_batch_id)
        if batch and batch.get("task_id"):
            TaskRepository(self.settings).update_task(
                task_id=str(batch["task_id"]), status="completed", current_step="completed",
                progress=100, version_id=save_result.new_version_id,
                result_payload={"status": "completed", "current_step": "completed", "progress": 100,
                    "current_version_id": save_result.new_version_id,
                    "new_version_id": save_result.new_version_id,
                    "version_no": save_result.new_version_no, "report_path": str(report.report_path) if report else None,
                    "node_count": save_result.node_count, "suggestion_count": len(suggestions),
                    "verification_status": verification.status,
                    "quality_before": verification.quality_before, "quality_after": verification.quality_after,
                    "quality_delta": verification.quality_delta},
            )
        return {
            "review_batch_id": review_batch_id,
            "source_version_id": source_version_id,
            "new_version_id": save_result.new_version_id,
            "new_version_no": save_result.new_version_no,
            "node_count": save_result.node_count,
            "executed_count": action_result.executed_count,
            "failed_count": action_result.failed_count,
            "quality_score": save_result.quality_score,
            "quality_before": verification.quality_before,
            "quality_after": verification.quality_after,
            "quality_delta": verification.quality_delta,
            "verification_status": verification.status,
            "export_path": verification.export_path,
            "report_path": str(report.report_path) if report else None,
            "report_preview_url": f"/api/reports/{save_result.new_version_id}/preview" if report else None,
        }

    def _record_execution_failure(
        self, *, review_batch_id: str, source_version_id: int,
        review_hash: str | None, workflow_id: str | None, run_id: str | None,
        exc: Exception, target_version_id: int | None = None,
    ) -> None:
        with connect(self.settings) as connection:
            connection.execute(
                """INSERT INTO version_execution_record(
                       review_batch_id,source_version_id,target_version_id,review_hash,
                       action_summary,status,workflow_id,run_id,error_code,error_message
                   ) VALUES(?,?,?,?,?,'failed',?,?,?,?)""",
                (review_batch_id, source_version_id, target_version_id, review_hash, "{}",
                 workflow_id, run_id, type(exc).__name__, str(exc)),
            )

    def _require_mutable_suggestion(self, suggestion_id: int) -> SuggestionRecord:
        suggestion = self.suggestion_repo.get_suggestion(suggestion_id)
        if suggestion is None:
            raise ValueError("suggestion_id 不存在。")
        if suggestion.status not in {"pending", "edited"}:
            raise ValueError("当前建议状态不允许审核操作。")
        return suggestion

    def _log(
        self,
        suggestion: SuggestionRecord,
        operator: str,
        operation_type: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        detail = {
            "suggestion_id": suggestion.id,
            "action_type": suggestion.action_type,
            "target_node_id": suggestion.target_node_id,
            **(extra or {}),
        }
        self.log_repo.create_log(
            version_id=suggestion.version_id,
            operator=operator,
            operation_type=operation_type,
            operation_detail=detail,
        )
