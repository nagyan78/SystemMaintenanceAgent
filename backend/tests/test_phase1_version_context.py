import sqlite3

from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.repositories.version_repo import VersionRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.schemas.workflow import StartWorkflowRequest
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.version_service import VersionService
from backend.app.services.workflow_context_service import WorkflowContextService


def _settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}")


def _versions(settings: Settings) -> tuple[int, int]:
    init_db(settings)
    repo = VersionRepository(settings)
    base_id = repo.create_version(file_id=1, version_no="v1.0")
    result_id = repo.create_version(
        file_id=1,
        version_no="v1.1",
        parent_version_id=base_id,
        source_workflow_id="wf-1",
        analysis_run_id="run-1",
        action_batch_id="batch-1",
    )
    return base_id, result_id


def test_maintain_context_uses_requested_or_latest_version(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _versions(settings)
    service = WorkflowContextService(settings)

    requested = service.resolve(
        StartWorkflowRequest(mode="maintain", base_version_id=base_id)
    )
    latest = service.resolve(StartWorkflowRequest(mode="maintain", file_id=1))

    assert requested.base_version_id == base_id
    assert latest.base_version_id == result_id
    assert latest.file_id == 1


def test_verify_context_requires_result_to_descend_from_base(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, result_id = _versions(settings)
    repo = VersionRepository(settings)
    unrelated_id = repo.create_version(file_id=1, version_no="v1.2")
    service = WorkflowContextService(settings)

    resolved = service.resolve(
        StartWorkflowRequest(
            mode="verify",
            base_version_id=base_id,
            result_version_id=result_id,
            affected_node_ids=[11],
        )
    )
    assert resolved.result_version_id == result_id

    try:
        service.resolve(
            StartWorkflowRequest(
                mode="verify",
                base_version_id=base_id,
                result_version_id=unrelated_id,
                affected_node_ids=[11],
            )
        )
    except ValueError as exc:
        assert "descendant" in str(exc)
    else:
        raise AssertionError("unrelated result version was accepted")


def test_save_new_version_is_idempotent_by_action_batch(tmp_path) -> None:
    settings = _settings(tmp_path)
    base_id, _ = _versions(settings)
    service = VersionService(settings)

    first = service.save_new_version(
        base_version_id=base_id,
        action_batch_id="batch-idempotent",
        workflow_id="wf-2",
        analysis_run_id="run-2",
        nodes=[],
    )
    second = service.save_new_version(
        base_version_id=base_id,
        action_batch_id="batch-idempotent",
        workflow_id="wf-2",
        analysis_run_id="run-2",
        nodes=[],
    )

    assert first.new_version_id == second.new_version_id
    assert VersionRepository(settings).get_version(first.new_version_id)[
        "parent_version_id"
    ] == base_id


def test_action_batch_race_does_not_reinsert_existing_snapshot(
    tmp_path, monkeypatch
) -> None:
    settings = _settings(tmp_path)
    base_id, _ = _versions(settings)
    service = VersionService(settings)
    nodes = [
        TaxonomyNodeRecord(
            category_id=1,
            category_name="根",
            parent_id=None,
            level=1,
            path_ids="1",
            path_names="根",
            is_leaf=1,
        )
    ]
    first = service.save_new_version(
        base_version_id=base_id,
        action_batch_id="batch-race",
        nodes=nodes,
    )
    monkeypatch.setattr(
        VersionRepository,
        "get_by_action_batch",
        lambda self, action_batch_id: None,
    )

    raced = service.save_new_version(
        base_version_id=base_id,
        action_batch_id="batch-race",
        nodes=[nodes[0].model_copy(update={"category_name": "竞争写入"})],
    )

    assert raced.new_version_id == first.new_version_id
    assert TaxonomyRepository(settings).get_node_detail(
        first.new_version_id, 1
    )["category_name"] == "根"


def test_init_db_rejects_duplicate_versions_instead_of_skipping_constraint(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    with sqlite3.connect(tmp_path / "app.db") as connection:
        connection.executescript(
            """
            CREATE TABLE taxonomy_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                version_no TEXT NOT NULL,
                description TEXT,
                quality_score REAL,
                snapshot_path TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO taxonomy_version(file_id, version_no) VALUES (1, 'v1.0');
            INSERT INTO taxonomy_version(file_id, version_no) VALUES (1, 'v1.0');
            """
        )

    try:
        init_db(settings)
    except RuntimeError as exc:
        assert "idx_version_file_version_no" in str(exc)
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate legacy versions were silently accepted")
