from backend.app.agents.graph import build_taxonomy_graph
from backend.app.agents.nodes import configure_workflow_runtime, verification_node
from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.quality_evaluation_service import QualityEvaluationService
from backend.app.services.verification_service import (
    VerificationIssueComparator,
    VerificationProbeService,
    VerificationService,
)


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def _node(
    node_id: int,
    name: str,
    parent_id: int | None,
    path: str,
    level: int,
) -> TaxonomyNodeRecord:
    return TaxonomyNodeRecord(
        category_id=node_id,
        category_name=name,
        parent_id=parent_id,
        level=level,
        path_ids="",
        path_names=path,
        is_leaf=1,
    )


def _seed_versions(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    versions = VersionRepository(settings)
    base_id = versions.create_version(file_id=1, version_no="v1.0")
    result_id = versions.create_version(
        file_id=1,
        version_no="v1.1",
        parent_version_id=base_id,
        action_batch_id="batch",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=base_id,
        nodes=[
            _node(1, "根", None, "根", 1),
            _node(2, "苹果", 99, "缺失 > 苹果", 2),
            _node(3, "叶", 2, "缺失 > 苹果 > 叶", 3),
        ],
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=result_id,
        nodes=[
            _node(1, "根", None, "根", 1),
            _node(2, "苹果", 1, "根 > 苹果", 2),
            _node(3, "叶", 2, "根 > 苹果 > 叶", 3),
            _node(4, "新孤儿", 404, "缺失 > 新孤儿", 2),
        ],
    )
    return base_id, result_id


def test_symmetric_scope_contains_changed_nodes_parents_children_and_descendants(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _seed_versions(settings)

    scope = VerificationProbeService(settings).build_symmetric_scope(
        base_version_id=base_id,
        result_version_id=result_id,
        affected_node_ids=[2, 4],
    )

    assert {1, 2, 3, 4, 99, 404}.issubset(scope)


def test_verification_finds_resolved_and_high_risk_introduced_issues(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _seed_versions(settings)
    evaluator = QualityEvaluationService(settings)
    before = evaluator.evaluate(
        workflow_id="wf",
        analysis_run_id="run",
        version_id=base_id,
        evaluation_role="verify_base",
    )
    after = evaluator.evaluate(
        workflow_id="wf",
        analysis_run_id="run",
        version_id=result_id,
        evaluation_role="verify_result",
    )

    result = VerificationService(settings).verify(
        base_version_id=base_id,
        result_version_id=result_id,
        affected_node_ids=[2, 4],
        evaluation_before_id=before.id,
        evaluation_after_id=after.id,
        current_round=1,
        max_rounds=2,
    )

    assert result.resolved_fingerprints
    assert result.introduced_fingerprints
    assert result.status == "failed"
    assert result.next_decision == "manual_intervention"


def test_comparator_uses_fingerprint_not_ephemeral_row_identity(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _seed_versions(settings)
    comparison = VerificationIssueComparator(
        VerificationProbeService(settings)
    ).compare(base_id, result_id, [2])

    assert all("verify-structure-v1" in item for item in comparison.resolved)
    assert comparison.unresolved == []


def test_graph_runs_verification_after_result_evaluation() -> None:
    edges = {
        (edge.source, edge.target)
        for edge in build_taxonomy_graph().get_graph().edges
    }

    assert ("result_quality_evaluation_node", "verification_node") in edges
    assert ("verify_result_quality_evaluation_node", "verification_node") in edges


def test_verification_node_returns_structured_state_update(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _seed_versions(settings)
    evaluator = QualityEvaluationService(settings)
    before = evaluator.evaluate(
        workflow_id="wf-node",
        analysis_run_id="run-node",
        version_id=base_id,
        evaluation_role="verify_base",
    )
    after = evaluator.evaluate(
        workflow_id="wf-node",
        analysis_run_id="run-node",
        version_id=result_id,
        evaluation_role="verify_result",
    )
    configure_workflow_runtime(settings)

    update = verification_node(
        TaxonomyGraphState(
            workflow_id="wf-node",
            thread_id="thread-node",
            workflow_mode="verify",
            base_version_id=base_id,
            current_version_id=result_id,
            result_version_id=result_id,
            analysis_run_id="run-node",
            evaluation_before_id=before.id,
            evaluation_after_id=after.id,
            affected_node_ids=[2, 4],
        )
    )

    assert update["current_step"] == "verification"
    assert update["verification_payload"]["next_decision"] == "manual_intervention"
