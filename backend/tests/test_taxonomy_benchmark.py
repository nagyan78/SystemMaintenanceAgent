from pathlib import Path
import subprocess
import sys

from backend.app.schemas.suggestion import ActionValidationResult
from scripts.run_taxonomy_benchmark import (
    build_measurement_scope,
    record_stream_chunk,
    load_golden_issues,
    preserve_artifact,
    score_issues,
    summarize_validation_results,
)


GOLDEN_PATH = Path("eval/golden_issues.json")


def test_load_golden_issues_pins_demo_dataset():
    golden = load_golden_issues(GOLDEN_PATH)

    assert golden.dataset_version == "demo-v1"
    assert golden.source_excel == "eval/golden_demo.xlsx"
    assert len(golden.issues) == 11
    assert {issue.issue_id for issue in golden.issues} == {
        "G-001",
        "G-002",
        "G-003",
        "G-004",
        "G-005",
        "G-006",
        "G-007",
        "G-008",
        "G-009",
        "G-010",
        "G-011",
    }


def test_score_issues_matches_by_issue_type_and_affected_nodes():
    golden = load_golden_issues(GOLDEN_PATH)
    predictions = [
        {
            "issue_type": "missing_parent",
            "node_id": 150,
            "node_name": "智能穿戴",
            "description": "节点 150 的父节点 998 不存在",
        },
        {
            "issue_type": "deep_level",
            "node_id": 111,
            "node_name": "Mate60",
            "description": "节点层级为 8，超过阈值 7",
        },
        {
            "issue_type": "duplicate_name",
            "node_id": None,
            "node_name": "外套",
            "description": "名称「外套」重复出现，节点 ID：304, 308, 323",
        },
        {
            "issue_type": "wide_node",
            "node_id": 100,
            "node_name": "电子产品",
            "description": "一个不在 golden set 中的假阳性",
        },
    ]

    metrics = score_issues(golden, predictions)

    assert metrics["overall"]["true_positive"] == 3
    assert metrics["overall"]["false_positive"] == 1
    assert metrics["overall"]["false_negative"] == 8
    assert metrics["overall"]["precision"] == 0.75
    assert metrics["overall"]["recall"] == 0.2727
    assert metrics["by_type"]["duplicate_name"]["recall"] == 1.0


def test_benchmark_script_can_run_directly_from_repo_root():
    result = subprocess.run(
        [sys.executable, "scripts/run_taxonomy_benchmark.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Run taxonomy agent benchmark" in result.stdout


def test_summarize_validation_results_reports_pass_rate_for_selected_actions():
    summary = summarize_validation_results(
        [
            ActionValidationResult(
                suggestion_id=1,
                valid=True,
                reason="passed",
            ),
            ActionValidationResult(
                suggestion_id=2,
                valid=False,
                reason="target_node_id 不存在",
            ),
        ]
    )

    assert summary == {
        "validated_count": 2,
        "validation_passed_count": 1,
        "validation_failed_count": 1,
        "validation_pass_rate": 0.5,
        "failed_reasons": ["target_node_id 不存在"],
    }


def test_preserve_artifact_copies_existing_file(tmp_path):
    source = tmp_path / "source_report.md"
    target = tmp_path / "results" / "baseline_report.md"
    source.write_text("# report\n", encoding="utf-8")

    preserved = preserve_artifact(source, target)

    assert preserved == target
    assert target.read_text(encoding="utf-8") == "# report\n"


def test_build_measurement_scope_documents_local_offline_timing():
    scope = build_measurement_scope(use_live_llm=False)

    assert scope["timing_field"] == "local_runner_elapsed_ms"
    assert scope["includes"] == ["in-process LangGraph node execution"]
    assert "HTTP request/response latency" in scope["excludes"]
    assert "LLM API latency" in scope["excludes"]
    assert scope["valid_for_resume_metrics"] is True
    assert scope["valid_for_user_wait_time"] is False


def test_record_stream_chunk_captures_failed_node_outcome():
    timings = {}
    outcomes = {}
    final_state = {}

    _, interrupted = record_stream_chunk(
        {
            "content_diagnosis_node": {
                "status": "failed",
                "current_step": "content_diagnosis_node",
                "error_code": "WORKFLOW_NODE_ERROR",
                "error_message": "LLM timeout",
                "progress": 62,
            }
        },
        timings,
        outcomes,
        final_state,
        previous=1.0,
        now=1.5,
    )

    assert interrupted is False
    assert timings["content_diagnosis_node"] == 0.5
    assert outcomes["content_diagnosis_node"] == {
        "status": "failed",
        "current_step": "content_diagnosis_node",
        "error_code": "WORKFLOW_NODE_ERROR",
        "error_message": "LLM timeout",
        "progress": 62,
    }
