from backend.app.config import Settings
from backend.app.db import connect, init_db
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.agent_run import AgentRunRecord
from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.services.retry_policy import RetryPolicy
from backend.app.services.tool_factory import AgentToolFactory, ToolScope
from concurrent.futures import ThreadPoolExecutor


def _settings(path) -> Settings:
    return Settings(database_url=f"sqlite:///{path / 'app.db'}", upload_dir=path / "uploads", export_dir=path / "exports", report_dir=path / "reports", dashscope_api_key="")


def _seed(path, name: str):
    settings = _settings(path)
    init_db(settings)
    with connect(settings) as connection:
        connection.execute("INSERT INTO uploaded_file (id, file_name, file_path) VALUES (1, 'test.xlsx', 'test.xlsx')")
    version_id = VersionRepository(settings).create_version(file_id=1, version_no="v1.0")
    TaxonomyRepository(settings).bulk_insert_nodes(version_id=version_id, nodes=[TaxonomyNodeRecord(category_id=1, category_name=name, parent_id=None, level=1, path_ids="1", path_names=name, is_leaf=1)])
    return settings, version_id


def _tool(tools, name):
    return next(item for item in tools if item.name == name)


def test_two_toolsets_do_not_share_runtime_settings(tmp_path):
    settings_a, version_a = _seed(tmp_path / "a", "A节点")
    settings_b, version_b = _seed(tmp_path / "b", "B节点")
    tools_a = AgentToolFactory(settings_a).content_diagnosis_tools(ToolScope("wf-a", version_a))
    tools_b = AgentToolFactory(settings_b).content_diagnosis_tools(ToolScope("wf-b", version_b))
    assert _tool(tools_a, "get_node_detail").invoke({"version_id": version_a, "category_id": 1})["category_name"] == "A节点"
    assert _tool(tools_b, "get_node_detail").invoke({"version_id": version_b, "category_id": 1})["category_name"] == "B节点"


def test_tool_scope_rejects_other_version(tmp_path):
    settings, version_id = _seed(tmp_path, "节点")
    tool = _tool(AgentToolFactory(settings).content_diagnosis_tools(ToolScope("wf", version_id)), "get_node_detail")
    try:
        tool.invoke({"version_id": version_id + 1, "category_id": 1})
    except ValueError as exc:
        assert "outside workflow scope" in str(exc)
    else:
        raise AssertionError("scope escape must fail")


def test_two_toolsets_remain_isolated_when_invoked_concurrently(tmp_path):
    settings_a, version_a = _seed(tmp_path / "a", "A节点")
    settings_b, version_b = _seed(tmp_path / "b", "B节点")
    tool_a = _tool(AgentToolFactory(settings_a).content_diagnosis_tools(ToolScope("wf-a", version_a)), "get_node_detail")
    tool_b = _tool(AgentToolFactory(settings_b).content_diagnosis_tools(ToolScope("wf-b", version_b)), "get_node_detail")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit((tool_a if index % 2 == 0 else tool_b).invoke, {"version_id": version_a if index % 2 == 0 else version_b, "category_id": 1}) for index in range(20)]
    names = [future.result()["category_name"] for future in futures]
    assert names[::2] == ["A节点"] * 10
    assert names[1::2] == ["B节点"] * 10


def test_work_item_is_idempotent_and_claimed_once(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    repo = AgentRunRepository(settings)
    run_id = repo.create_run(AgentRunRecord(workflow_id="wf", agent_type="content_diagnosis", version_id=1))
    first = repo.upsert_work_item(run_id, "candidate", "441", {"category_id": 441})
    second = repo.upsert_work_item(run_id, "candidate", "441", {"category_id": 441})
    assert first == second
    assert repo.claim_work_item(first, worker_id="worker-a") is True
    assert repo.claim_work_item(first, worker_id="worker-b") is False


def test_retryable_failure_becomes_permanent_at_max_attempts(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    repo = AgentRunRepository(settings)
    run_id = repo.create_run(AgentRunRecord(workflow_id="wf", agent_type="content_diagnosis", version_id=1))
    item_id = repo.upsert_work_item(run_id, "candidate", "1", {}, max_attempts=2)
    for attempt in range(2):
        assert repo.claim_work_item(item_id, worker_id=f"w{attempt}")
        status = repo.fail_work_item(item_id, retryable=True, error_code="TIMEOUT", error_message="timeout")
    assert status == "permanent_failed"
    assert repo.get_work_item(item_id).error_code == "MAX_ATTEMPTS_EXHAUSTED"
    assert repo.is_runnable(item_id) is False


def test_agent_event_is_redacted_and_resumable(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    repo = AgentRunRepository(settings)
    first = repo.record_event(workflow_id="wf", event_type="agent_step", summary={"api_key": "secret", "raw_prompt": "hidden", "decision": "candidate accepted"})
    second = repo.record_event(workflow_id="wf", event_type="candidate_completed", summary={"node": 1})
    events = repo.list_events("wf", after_id=first)
    assert [item["id"] for item in events] == [second]
    assert "api_key" not in repo.list_events("wf")[0]["summary"]


def test_sqlite_connection_enables_wal_and_foreign_keys(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    with connect(settings) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_retry_policy_classifies_timeout_and_caps_delay():
    policy = RetryPolicy(max_attempts=3, base_delay=1, max_delay=5)
    assert policy.classify(TimeoutError()) == "retryable_external"
    assert policy.classify(ValueError()) == "permanent_internal"
    assert policy.delay(10) == 5
    assert policy.delay(1, retry_after=20) == 5
