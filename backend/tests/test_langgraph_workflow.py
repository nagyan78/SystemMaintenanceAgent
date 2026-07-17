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


SAMPLE_PATH = Path("data/sample/产品标准体系.xlsx")


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
        deepseek_api_key="",
        llm_provider="deepseek",
        llm_model="deepseek-chat",
        dashscope_api_key="",
    )


def _create_sample_file_record(settings):
    metadata = UploadedFileMetadata(
        file_name=SAMPLE_PATH.name,
        file_path=SAMPLE_PATH,
        file_size=SAMPLE_PATH.stat().st_size,
        sheet_name="Sheet1",
        row_count=21090,
        column_count=6,
        columns=[
            "category_id",
            "category_name",
            "category_group_id",
            "category_pids",
            "category_group_name",
            "syn_list",
        ],
    )
    return FileRepository(settings).create_uploaded_file(metadata)


def test_graph_runs_m1_deterministic_workflow_to_report(tmp_path):
    settings = _settings(tmp_path)
    create_app(settings)
    file_id = _create_sample_file_record(settings)
    checkpointer = create_memory_checkpointer()
    graph = build_taxonomy_graph(
        checkpointer,
        settings=settings,
        enable_suggestion_review=False,
    )
    state = create_initial_state(
        file_id=file_id,
        task_id="task_demo",
        workflow_id="workflow_demo",
    )

    result = graph.invoke(state, config={"configurable": {"thread_id": state.thread_id}})

    assert result["status"] == "waiting_review"
    assert result["current_step"] == "review_pending"
    assert result["progress"] == 80
    assert result["version_no"] == "v1.0"
    assert result["node_count"] == 21090
    assert result["structure_issue_count"] >= 44
    assert Path(result["report_path"]).exists()


def test_graph_m2_runs_content_diagnosis_without_human_review(tmp_path):
    settings = _settings(tmp_path)
    create_app(settings)
    file_id = _create_sample_file_record(settings)
    graph = build_taxonomy_graph(
        create_memory_checkpointer(),
        settings=settings,
        enable_suggestion_review=False,
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
    assert "wait_human_review_node" not in result["completed_steps"]


def test_route_after_validate_ignores_stale_upstream_error_after_successful_validation():
    state = TaxonomyGraphState(
        workflow_id="workflow_demo",
        thread_id="thread_demo",
        task_id="task_demo",
        status="running",
        current_step="validate_action",
        progress=86,
        error_code="WORKFLOW_NODE_ERROR",
        error_message="content diagnosis failed earlier",
    )

    assert route_after_validate(state) == "execute_action_node"
