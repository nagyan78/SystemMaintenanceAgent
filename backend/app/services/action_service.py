from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.repositories.operation_log_repo import OperationLogRepository
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.suggestion import ActionValidationResult, AdjustmentSuggestion, SuggestionRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.version import ExecuteActionsResult
from backend.app.tools.validation_tools import (
    extract_move_new_parent_id,
    resolve_clean_synonym_update,
    validate_suggestion_action,
)
from backend.app.services.action_simulation_service import ActionSimulationService, SnapshotActionApplier


class ActionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.suggestion_repo = SuggestionRepository(settings)
        self.log_repo = OperationLogRepository(settings)
        self.taxonomy_repo = TaxonomyRepository(settings)

    def validate_approved_actions(self, review_batch_id: str) -> list[ActionValidationResult]:
        approved = [
            item
            for item in self.suggestion_repo.list_suggestions(review_batch_id=review_batch_id)
            if item.status == "approved"
        ]
        return self.validate_suggestion_records(approved)

    def validate_suggestion_records(self, suggestions: list[SuggestionRecord]) -> list[ActionValidationResult]:
        return [
            validate_suggestion_action(
                AdjustmentSuggestion.model_validate(item.model_dump(exclude={"id", "review_batch_id"})),
                self.settings,
            ).model_copy(update={"suggestion_id": item.id})
            for item in suggestions
        ]

    def execute_actions(
        self,
        version_id: int,
        review_batch_id: str,
        operator: str = "local_user",
    ) -> ExecuteActionsResult:
        approved = self.suggestion_repo.list_suggestions(
            version_id=version_id,
            review_batch_id=review_batch_id,
            status="approved",
        )
        return self.execute_suggestion_records(
            version_id=version_id,
            review_batch_id=review_batch_id,
            approved=approved,
            operator=operator,
        )

    def execute_suggestion_records(
        self,
        *,
        version_id: int,
        review_batch_id: str,
        approved: list[SuggestionRecord],
        operator: str = "local_user",
        persist_side_effects: bool = True,
    ) -> ExecuteActionsResult:
        validations = self.validate_suggestion_records(approved)
        failed_validations = [item for item in validations if not item.valid]
        if failed_validations:
            if persist_side_effects:
                for item in failed_validations:
                    if item.suggestion_id is not None:
                        self.suggestion_repo.update_status(item.suggestion_id, "failed")
            joined = "; ".join(item.reason for item in failed_validations)
            raise ValueError(f"动作校验失败：{joined}")
        if not approved:
            return ExecuteActionsResult(
                source_version_id=version_id,
                review_batch_id=review_batch_id,
                action_batch_id=str(uuid4()),
                executed_count=0,
                failed_count=0,
                nodes=self.taxonomy_repo.list_node_records(version_id),
            )

        action_batch_id = str(uuid4())
        preview = ActionSimulationService(self.settings).simulate(version_id, approved)
        failures: list[dict[str, Any]] = preview.errors

        if failures:
            if persist_side_effects:
                for failure in failures:
                    self.suggestion_repo.update_status(int(failure["suggestion_id"]), "failed")
                self.log_repo.create_log(
                version_id=version_id,
                operator=operator,
                operation_type="execute_actions_failed",
                operation_detail={
                    "review_batch_id": review_batch_id,
                    "action_batch_id": action_batch_id,
                    "failures": failures,
                },
                )
            raise ValueError(f"动作执行失败：{failures[0]['reason']}")

        if persist_side_effects:
            for suggestion in approved:
                self.suggestion_repo.update_status(suggestion.id, "executed")
            self.log_repo.create_log(
            version_id=version_id,
            operator=operator,
            operation_type="execute_actions",
            operation_detail={
                "review_batch_id": review_batch_id,
                "action_batch_id": action_batch_id,
                "executed_count": len(approved),
                "suggestion_ids": [item.id for item in approved],
            },
            )
        return ExecuteActionsResult(
            source_version_id=version_id,
            review_batch_id=review_batch_id,
            action_batch_id=action_batch_id,
            executed_count=len(approved),
            failed_count=0,
            nodes=preview.nodes,
        )

    def _apply_action(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        suggestion: SuggestionRecord,
    ) -> None:
        SnapshotActionApplier().apply(nodes, suggestion)

    def _clean_synonym(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        suggestion: SuggestionRecord,
    ) -> None:
        node = self._require_node(nodes, suggestion.target_node_id)
        updated_terms, _ = resolve_clean_synonym_update(node.syn_list or "", suggestion.action_payload)
        nodes[node.category_id] = node.model_copy(update={"syn_list": ", ".join(updated_terms) or None})

    def _rename_node(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        suggestion: SuggestionRecord,
    ) -> None:
        node = self._require_node(nodes, suggestion.target_node_id)
        new_name = (suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
        if not new_name:
            raise ValueError("rename_node 缺少 new_name。")
        for sibling in nodes.values():
            if (
                sibling.parent_id == node.parent_id
                and sibling.category_id != node.category_id
                and sibling.category_name == new_name
            ):
                raise ValueError("同级节点下已存在相同名称。")
        nodes[node.category_id] = node.model_copy(update={"category_name": new_name})

    def _move_node(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        suggestion: SuggestionRecord,
    ) -> None:
        node = self._require_node(nodes, suggestion.target_node_id)
        has_parent, new_parent_id = extract_move_new_parent_id(suggestion)
        if not has_parent:
            raise ValueError("move_node 缺少 new_parent_id。")
        if new_parent_id is None:
            nodes[node.category_id] = node.model_copy(update={"parent_id": None})
            return
        new_parent_id = int(new_parent_id)
        if new_parent_id == node.category_id:
            raise ValueError("move_node 不能移动到自身下。")
        if new_parent_id not in nodes:
            raise ValueError("new_parent_id 不存在。")
        if _is_descendant(nodes, node.category_id, new_parent_id):
            raise ValueError("move_node 不能移动到自身子树下。")
        nodes[node.category_id] = node.model_copy(update={"parent_id": new_parent_id})

    def _add_node(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        suggestion: SuggestionRecord,
    ) -> None:
        new_name = (suggestion.new_name or suggestion.action_payload.get("new_name") or "").strip()
        parent_id = suggestion.new_parent_id or suggestion.action_payload.get("parent_id")
        if not new_name or parent_id is None:
            raise ValueError("add_node 缺少 new_name 或 parent_id。")
        parent_id = int(parent_id)
        if parent_id not in nodes:
            raise ValueError("add_node 的 parent_id 不存在。")
        category_id = int(suggestion.action_payload.get("category_id") or max(nodes) + 1)
        if category_id in nodes:
            raise ValueError("add_node 的 category_id 已存在。")
        nodes[category_id] = TaxonomyNodeRecord(
            category_id=category_id,
            category_name=new_name,
            parent_id=parent_id,
            level=1,
            path_ids=str(category_id),
            path_names=new_name,
            syn_list=suggestion.action_payload.get("syn_list"),
            is_leaf=1,
        )

    def _require_node(
        self,
        nodes: dict[int, TaxonomyNodeRecord],
        category_id: int | None,
    ) -> TaxonomyNodeRecord:
        if category_id is None or category_id not in nodes:
            raise ValueError("target_node_id 不存在。")
        return nodes[category_id]


def _split_synonyms(syn_list: str) -> list[str]:
    return [item.strip() for item in syn_list.replace("，", ",").split(",") if item.strip()]


def _is_descendant(
    nodes: dict[int, TaxonomyNodeRecord],
    ancestor_id: int,
    descendant_id: int,
) -> bool:
    current = nodes.get(descendant_id)
    while current and current.parent_id is not None:
        if current.parent_id == ancestor_id:
            return True
        current = nodes.get(current.parent_id)
    return False
