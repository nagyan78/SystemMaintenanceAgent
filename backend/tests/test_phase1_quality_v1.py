from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.quality_repo import QualityRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.quality_evaluation_service import QualityEvaluationService


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def _seed(settings: Settings) -> int:
    init_db(settings)
    version_id = VersionRepository(settings).create_version(
        file_id=1,
        version_no="v1.0",
        vector_index_status="skipped",
    )
    TaxonomyRepository(settings).bulk_insert_nodes(
        version_id=version_id,
        nodes=[
            TaxonomyNodeRecord(
                category_id=1,
                category_name="根",
                parent_id=None,
                level=1,
                path_ids="1",
                path_names="根",
                is_leaf=0,
            ),
            TaxonomyNodeRecord(
                category_id=2,
                category_name="苹果",
                parent_id=1,
                level=2,
                path_ids="1,2",
                path_names="根 > 苹果",
                is_leaf=1,
            ),
            TaxonomyNodeRecord(
                category_id=3,
                category_name="苹果",
                parent_id=1,
                level=2,
                path_ids="1,3",
                path_names="根 > 苹果",
                is_leaf=1,
            ),
            TaxonomyNodeRecord(
                category_id=4,
                category_name="孤儿",
                parent_id=99,
                level=8,
                path_ids="99,4",
                path_names="缺失 > 孤儿",
                is_leaf=1,
            ),
        ],
    )
    return version_id


def test_quality_v1_has_exact_deterministic_scores_and_availability(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id = _seed(settings)

    result = QualityEvaluationService(settings).evaluate(
        workflow_id="wf",
        analysis_run_id="run",
        version_id=version_id,
        evaluation_role="baseline",
    )

    assert result.score_version == "quality-v1"
    assert result.dimensions.structural_integrity == 18.75
    assert result.dimensions.hierarchy_balance == 15.0
    assert result.dimensions.semantic_consistency == 0.0
    assert result.dimensions.redundancy == 11.25
    assert result.dimensions.naming_quality == 10.0
    assert result.dimensions.coverage_confidence == 8.0
    assert result.total_score == 63.0
    assert result.available_points == 80.0
    assert result.coverage_ratio == 0.8
    assert result.available_dimensions["semantic_consistency"] is False


def test_quality_evaluation_upsert_is_idempotent_for_role(tmp_path) -> None:
    settings = _settings(tmp_path)
    version_id = _seed(settings)
    service = QualityEvaluationService(settings)

    first = service.evaluate(
        workflow_id="wf",
        analysis_run_id="run",
        version_id=version_id,
        evaluation_role="baseline",
    )
    second = service.evaluate(
        workflow_id="wf",
        analysis_run_id="run",
        version_id=version_id,
        evaluation_role="baseline",
    )

    assert first.id == second.id
    stored = QualityRepository(settings).get(first.id)
    assert stored.total_score == 63.0
