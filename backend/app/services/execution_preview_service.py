from collections import Counter
from typing import Any

from backend.app.config import Settings
from backend.app.repositories.review_batch_repo import ReviewBatchRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.services.action_simulation_service import ActionSimulationService
from backend.app.services.suggestion_consistency_service import SuggestionConsistencyService


class ExecutionPreviewService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.batches = ReviewBatchRepository(settings)
        self.suggestions = SuggestionRepository(settings)
        self.versions = VersionRepository(settings)

    def create(self, review_batch_id: str) -> dict[str, Any]:
        batch = self.batches.get(review_batch_id)
        if not batch:
            raise ValueError("审核批次不存在。")
        records = self.suggestions.list_suggestions(review_batch_id=review_batch_id)
        pending_count = sum(item.status in {"pending", "edited"} for item in records)
        if pending_count:
            raise ValueError(f"还有 {pending_count} 条建议尚未审核")
        approved = [item for item in records if item.status == "approved"]
        if not approved:
            raise ValueError("没有审核通过的修改动作。")
        consistency = SuggestionConsistencyService(self.settings)
        consistency_errors: list[dict[str, Any]] = []
        executable_approved = []
        for item in approved:
            result = consistency.check(item)
            if not result.valid or not result.executable:
                consistency_errors.append({"code": "consistency_invalid", "suggestion_id": item.id, "reason": result.reason or "该建议不可执行。"})
            else:
                executable_approved.append(item)
        executable_approved, deduplication = _deduplicate_missing_parent(executable_approved)
        if not executable_approved:
            raise ValueError("当前没有可执行修改")
        version_id = int(batch["version_id"])
        version = self.versions.get_version(version_id)
        if not version:
            raise ValueError("审核基线版本不存在。")
        latest = self.versions.get_latest_for_file(int(version["file_id"]))
        baseline_changed = bool(latest and int(latest["id"]) != version_id)
        simulation = ActionSimulationService(self.settings).simulate(version_id, executable_approved)
        errors = [*consistency_errors, *simulation.errors]
        if baseline_changed:
            errors.append({"code": "baseline_changed", "reason": "审核基线版本已变化，请基于最新版本重新创建审核批次。"})
        diff = simulation.diff.model_dump(mode="json")
        action_counts = Counter(
            "create_missing_parent" if item.action_type == "add_node" and item.action_payload.get("missing_parent_id") else item.action_type
            for item in executable_approved
        )
        affected_children = sum(int(item.change_preview.get("impact", {}).get("受影响子节点数量") or
                                    item.change_preview.get("impact", {}).get("迁移子节点") or 0) for item in executable_approved)
        affected_references = sum(int(item.change_preview.get("impact", {}).get("影响引用数量") or 0) for item in executable_approved)
        affected_children += sum(item["affected_child_count"] for item in deduplication)
        introduced_risks = [
            {"risk_level": "high" if any(word in str(error) for word in ("环", "孤立", "父节点")) else "medium",
             "reason": error.get("reason") or error.get("code")}
            for error in simulation.errors
        ]
        payload = {
            "review_batch_id": review_batch_id, "base_version_id": version_id,
            "valid": not errors and simulation.valid, "review_hash": simulation.review_hash,
            "errors": errors, "warnings": [], "action_counts": dict(action_counts),
            "affected_child_count": affected_children, "affected_reference_count": affected_references,
            "path_changes": [item.change_preview for item in executable_approved if item.action_type == "move_node"],
            "deduplicated_actions": deduplication,
            "summary": [item["summary"] for item in deduplication],
            "diff": diff, "checks": {
                "cycle": not any(item.get("code") == "cycle" for item in errors),
                "duplicate_sibling": not any(item.get("code") == "duplicate_sibling" for item in errors),
                "orphan": not any(item.get("code") == "orphan" for item in errors),
                "parent_exists": not any(item.get("code") in {"orphan", "parent_missing"} for item in errors),
                "depth_limit": not any(item.get("code") == "depth_limit" for item in errors),
                "synonyms_valid": not any(item.get("code") == "synonyms_invalid" for item in errors),
                "multi_action_conflicts": not any(item.get("code") == "multi_action_conflict" for item in errors),
                "baseline_unchanged": not baseline_changed,
                "new_medium_high_risk_issues": introduced_risks,
            },
        }
        self.batches.save_preview(review_batch_id, review_hash=simulation.review_hash, payload=payload,
                                  base_version_id=version_id,
                                  base_generation=int(version.get("vector_index_generation") or 0), valid=payload["valid"])
        return payload

    def require_executable(self, review_batch_id: str) -> dict[str, Any]:
        batch = self.batches.get(review_batch_id)
        if not batch or batch.get("status") != "preview_ready" or batch.get("execution_status") != "ready":
            raise ValueError("必须先完成并通过最新执行预览。")
        if not batch.get("preview_hash") or not batch.get("preview_payload"):
            raise ValueError("执行预览已失效，请重新预览。")
        version = self.versions.get_version(int(batch["version_id"]))
        if not version or int(version.get("vector_index_generation") or 0) != int(batch.get("preview_base_generation") or 0):
            raise ValueError("基线版本已变化，执行预览失效。")
        latest = self.versions.get_latest_for_file(int(version["file_id"]))
        if latest and int(latest["id"]) != int(version["id"]):
            raise ValueError("当前文件已产生更新版本，原基线执行预览失效。")
        records = [item for item in self.suggestions.list_suggestions(review_batch_id=review_batch_id) if item.status == "approved"]
        records, _ = _deduplicate_missing_parent(records)
        current = ActionSimulationService(self.settings).simulate(int(batch["version_id"]), records)
        if current.review_hash != batch["preview_hash"] or not current.valid:
            raise ValueError("审核内容已变化或存在阻断错误，请重新执行预览。")
        return {"review_hash": current.review_hash, "batch": batch, "suggestions": records}


def _deduplicate_missing_parent(records):
    grouped: dict[tuple[int, int], list] = {}
    passthrough = []
    for item in records:
        missing_id = item.action_payload.get("missing_parent_id") or (
            item.action_payload.get("category_id") if item.action_type == "add_node" else None
        )
        if item.action_type == "add_node" and missing_id is not None:
            grouped.setdefault((item.version_id, int(missing_id)), []).append(item)
        else:
            passthrough.append(item)
    summaries = []
    canonical = list(passthrough)
    for (version_id, missing_id), items in sorted(grouped.items()):
        representative = min(items, key=lambda item: item.id)
        children = []
        for item in items:
            scope = item.change_preview.get("impact_scope") or item.change_preview.get("impact") or {}
            for child in scope.get("direct_affected_nodes") or []:
                if child not in children:
                    children.append(child)
        if not children:
            children = [{"id": item.action_payload.get("subject_node_id"), "name": item.issue_id} for item in items]
        preview = dict(representative.change_preview)
        scope = dict(preview.get("impact_scope") or preview.get("impact") or {})
        scope.update({"direct_affected_nodes": children, "shared_missing_parent": len(items) > 1,
                      "shared_child_count": len(children)})
        preview.update({"impact_scope": scope, "impact": scope})
        canonical.append(representative.model_copy(update={"change_preview": preview}))
        summaries.append({"version_id": version_id, "missing_parent_id": missing_id,
                          "source_suggestion_ids": [item.id for item in items],
                          "action_count": 1, "affected_child_count": len(children),
                          "summary": f"1 个父节点补建动作，影响 {len(children)} 个子节点"})
    return sorted(canonical, key=lambda item: item.id), summaries
