from langchain_core.messages import AIMessage

from backend.app.config import Settings
from backend.app.db import init_db
from backend.app.schemas.issue import DiagnosisPlan
from backend.app.services.content_diagnosis_service import ContentDiagnosisAgent
from backend.app.services.tool_factory import AgentToolFactory, ToolScope


def _settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        upload_dir=tmp_path / "uploads",
        export_dir=tmp_path / "exports",
        report_dir=tmp_path / "reports",
    )


def _candidate():
    return {
        "category_id": 7,
        "category_name": "测试节点",
        "parent_id": 1,
        "level": 2,
        "path_names": "产品 > 测试节点",
        "path_ids": "1,7",
        "syn_list": None,
        "is_leaf": 1,
    }


class ReasonableLLM:
    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        return AIMessage(content="提交结论", tool_calls=[{
            "id": "assessment-1",
            "name": "submit_content_assessment",
            "args": {"assessment": {
                "version_id": 1,
                "node_id": 7,
                "node_name": "测试节点",
                "conclusion": "reasonable",
                "reason": "路径、名称和同义词未发现明确冲突",
            }},
        }])


class NoConclusionLLM:
    def bind_tools(self, _tools):
        return self

    def invoke(self, _messages):
        return AIMessage(content="仍然无法判断")


def test_reasonable_assessment_is_explicit_not_inferred_from_missing_issue(tmp_path):
    agent = ContentDiagnosisAgent(
        _settings(tmp_path),
        llm=ReasonableLLM(),
        candidate_selector=lambda _version_id, _plan: [_candidate()],
    )

    issues = agent.run(1, DiagnosisPlan(estimated_candidates=1))

    assert issues == []
    assert agent.last_assessments[0].conclusion == "reasonable"


def test_missing_model_conclusion_becomes_evidence_insufficient(tmp_path):
    agent = ContentDiagnosisAgent(
        _settings(tmp_path),
        llm=NoConclusionLLM(),
        candidate_selector=lambda _version_id, _plan: [_candidate()],
        max_iter=1,
    )

    issues = agent.run(1, DiagnosisPlan(estimated_candidates=1))

    assert issues == []
    assert agent.last_assessments[0].conclusion == "evidence_insufficient"


def test_scoped_content_assessment_uses_subject_id(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    tool = next(
        item for item in AgentToolFactory(settings).content_diagnosis_tools(
            ToolScope("workflow-test", 1, 42)
        )
        if item.name == "submit_content_assessment"
    )

    result = tool.invoke({
        "assessment": {
            # 模型遗漏 version_id、误填节点 ID 时，程序必须使用 work item 作用域。
            "node_id": 999,
            "node_name": "测试节点",
            "conclusion": "reasonable",
            "reason": "路径与名称一致",
        }
    })

    assert '"accepted": true' in result
    assert '"node_id": 42' in result
    assert '"node_name": "测试节点"' in result
