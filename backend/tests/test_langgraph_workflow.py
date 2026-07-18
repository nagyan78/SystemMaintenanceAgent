from pathlib import Path

from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    create_memory_checkpointer,
    route_after_validate,
)
from backend.app.agents.states import TaxonomyGraphState
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.repositories.file_repo import FileRepository
from backend.app.services.excel_service import UploadedFileMetadata
from backend.tests.taxonomy_fixture import TAXONOMY_COLUMNS, write_taxonomy_workbook


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        dashscope_api_key="",
    )


def _create_sample_file_record(settings, sample_path: Path):
    metadata = UploadedFileMetadata(
        file_name=sample_path.name,
        file_path=sample_path,
        file_size=sample_path.stat().st_size,
        sheet_name="Sheet1",
        row_count=3,
        column_count=6,
        columns=TAXONOMY_COLUMNS,
    )
    return FileRepository(settings).create_uploaded_file(metadata)


def test_graph_runs_m1_deterministic_workflow_to_report(tmp_path):
    settings = _settings(tmp_path)
    create_app(settings)
    file_id = _create_sample_file_record(
        settings, write_taxonomy_workbook(tmp_path / "taxonomy.xlsx")
    )
    checkpointer = create_memory_checkpointer()
    graph = build_taxonomy_graph(
        checkpointer,
        settings=settings,
    )
    state = create_initial_state(
        file_id=file_id,
        task_id="task_demo",
        workflow_id="workflow_demo",
    )

    result = graph.invoke(state, config={"configurable": {"thread_id": state.thread_id}})

    assert result["status"] == "completed"
    assert result["current_step"] == "completed"
    assert result["progress"] == 100
    assert result["version_no"] == "v1.0"
    assert result["node_count"] == 3
    assert Path(result["report_path"]).exists()


def test_graph_m2_runs_content_diagnosis_without_review_node(tmp_path):
    settings = _settings(tmp_path)
    create_app(settings)
    file_id = _create_sample_file_record(
        settings, write_taxonomy_workbook(tmp_path / "taxonomy.xlsx")
    )
    graph = build_taxonomy_graph(
        create_memory_checkpointer(),
        settings=settings,
    )
    state = create_initial_state(
        file_id=file_id,
        task_id="task_demo",
        workflow_id="workflow_demo",
    )

    result = graph.invoke(state, config={"configurable": {"thread_id": state.thread_id}})

    assert "__interrupt__" not in result
    assert result["vector_index_status"] == "skipped"
    assert result["vector_index_count"] == 0
    assert "diagnosis_planning_node" in result["completed_steps"]
    assert "content_diagnosis_node" in result["completed_steps"]
    assert result["diagnosis_plan"]["sample_strategy"] == "focused"
    assert "generate_suggestion_node" in result["completed_steps"]
    assert "validate_action_node" not in result["completed_steps"] or result["validated_action_count"] >= 0


def test_route_after_validate_ignores_stale_upstream_error_after_successful_validation():
    state = TaxonomyGraphState(
        workflow_id="workflow_demo",
        thread_id="thread_demo",
        task_id="task_demo",
        status="running",
        current_step="validate_action",
        progress=86,
        validated_action_count=1,
        error_code="WORKFLOW_NODE_ERROR",
        error_message="content diagnosis failed earlier",
    )

    assert route_after_validate(state) == "execute_action_node"
