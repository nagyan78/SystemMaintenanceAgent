from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.domain.issue_types import ISSUE_TYPES, issue_type_metadata, normalize_issue_type_code
from backend.app.repositories.diagnosis_repo import DiagnosisRepository
from backend.app.repositories.version_repo import VersionRepository


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
        export_dir=tmp_path / "exports",
    )


def test_issue_type_registry_has_only_supported_categories():
    assert set(ISSUE_TYPES) == {
        "missing_parent", "excessive_depth", "excessive_width", "duplicate_sibling",
        "parent_child_redundancy", "semantic_misplacement", "inconsistent_dimension",
        "synonym_format", "synonym_typo", "synonym_conflict", "synonym_overlap",
        "naming_nonstandard", "semantic_duplicate", "unknown",
    }
    assert {item.category for item in ISSUE_TYPES.values()} == {"structure", "content"}
    assert all(item.label and item.description for item in ISSUE_TYPES.values())


def test_legacy_mapping_is_explicit_and_unknown_is_not_guessed():
    assert normalize_issue_type_code("wide_node") == "excessive_width"
    assert normalize_issue_type_code("synonym_format_issue") == "synonym_format"
    assert normalize_issue_type_code("synonym_pollution") == "synonym_conflict"
    assert normalize_issue_type_code("duplicate_name") == "unknown"
    assert normalize_issue_type_code("some_new_model_phrase") == "unknown"


def test_historical_issue_keeps_raw_type_and_gains_canonical_fields(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id, file_name, file_path) VALUES (1, 'old.xlsx', 'old.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0", description="history")
    with connect(settings) as connection:
        issue_id = connection.execute(
            """INSERT INTO diagnosis_issue
               (version_id, issue_type, node_name, description, reason, risk_level, confidence, status)
               VALUES (?, 'synonym_format_issue', '苹果', '旧问题', '旧依据', 'low', 1, 'pending')""",
            (version_id,),
        ).lastrowid

    issue = DiagnosisRepository(settings).get_issue_detail(int(issue_id))

    assert issue is not None
    assert issue["issue_type"] == "synonym_format_issue"
    assert issue_type_metadata(issue["issue_type"]) == {
        "issue_type_code": "synonym_format",
        "issue_type_label": "同义词格式错误",
        "issue_category": "content",
    }
    assert issue["issue_type_code"] == "synonym_format"
