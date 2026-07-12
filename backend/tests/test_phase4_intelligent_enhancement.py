from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient

from backend.app.db import init_db
from backend.app.main import create_app
from backend.app.repositories.suggestion_repo import SuggestionRepository
from backend.app.schemas.model_routing import ModelBudget, ModelEndpoint, ModelProfile
from backend.app.schemas.planning import DiagnosisBatchFeedback
from backend.app.services.adaptive_planning_service import AdaptivePlanningService
from backend.app.services.agent_memory_service import AgentMemoryService
from backend.app.services.evaluation_service import EvaluationService
from backend.app.services.model_router import ModelRouter
from backend.app.services.tool_registry import ToolRegistry, ToolSpec
from backend.tests.test_m4_action_execution import _create_issue, _seed_version, _settings, _create_approved_suggestion


def test_adaptive_planner_expands_then_stops_on_repeated_low_hit():
    service=AdaptivePlanningService(); plan=service.create(workflow_id="wf",version_id=1,candidate_budget=20)
    expanded=service.revise(plan,DiagnosisBatchFeedback(batch_id="b1",plan_revision=1,processed=20,issues=9,clean=11,inconclusive=0,failed=0,model_calls=20,tokens=100,wall_seconds=2))
    assert expanded.decision=="expand" and expanded.targets[0].candidate_budget==40
    stopped=service.revise(expanded,DiagnosisBatchFeedback(batch_id="b2",plan_revision=2,processed=20,issues=0,clean=20,inconclusive=0,failed=0,model_calls=20,tokens=100,wall_seconds=2,previous_hit_rate=.01))
    assert stopped.decision=="stop" and stopped.stop_reason=="consecutive_low_hit_rate"


class Failing:
    def invoke(self,messages,**kwargs):
        error=RuntimeError("unavailable"); error.status_code=503; raise error
class Success:
    def invoke(self,messages,**kwargs): return SimpleNamespace(content='{"ok":true}',usage_metadata={"total_tokens":5})

def test_model_router_fallback_and_budget():
    profile=ModelProfile(task_type="planning",primary=ModelEndpoint(model="primary",client=Failing()),fallback=ModelEndpoint(model="fallback",client=Success()))
    router=ModelRouter(profiles={"planning":profile},budget=ModelBudget(max_calls=3,max_tokens=100))
    assert router.invoke("planning",[]).content=='{"ok":true}'
    assert router.usage.calls==2 and router.usage.fallback_calls==1


def test_read_tool_cache_and_side_effect_guard(tmp_path):
    settings=_settings(tmp_path); init_db(settings); calls={"count":0}
    registry=ToolRegistry(settings,"wf",1,"diagnosis")
    registry.register(ToolSpec(name="get_node_detail",owner_agents={"diagnosis"},read_only=True,side_effect=False,timeout_ms=1000,cost_level="low",cache_ttl_seconds=60,scoped_arguments={"version_id"}),lambda version_id,category_id: calls.__setitem__("count",calls["count"]+1) or {"category_id":category_id})
    assert registry.invoke("get_node_detail",{"category_id":10})==registry.invoke("get_node_detail",{"category_id":10})
    assert calls["count"]==1 and registry.metrics.cache_hits==1
    with pytest.raises(ValueError,match="side-effect tools cannot be cached"):
        ToolSpec(name="write",owner_agents={"diagnosis"},read_only=False,side_effect=True,timeout_ms=1,cost_level="high",cache_ttl_seconds=1)


def test_tool_timeout_and_low_confidence_triage(tmp_path):
    import time
    settings=_settings(tmp_path); version_id=_seed_version(settings)
    registry=ToolRegistry(settings,"wf",version_id,"diagnosis")
    registry.register(ToolSpec(name="slow",owner_agents={"diagnosis"},read_only=True,side_effect=False,timeout_ms=10,cost_level="low"),lambda:time.sleep(.1))
    with pytest.raises(TimeoutError,match="timed out"): registry.invoke("slow",{})
    from backend.app.services.tool_factory import AgentToolFactory, ToolScope
    submit=next(tool for tool in AgentToolFactory(settings).content_diagnosis_tools(ToolScope("wf",version_id,20)) if tool.name=="submit_diagnosis")
    result=submit.invoke({"issue":{"version_id":version_id,"node_id":20,"node_name":"水果","issue_type":"semantic_duplicate","reason":"不确定","confidence":.4}})
    assert result.startswith("triage_")
    client=TestClient(create_app(settings)); items=client.get("/api/triage?workflow_id=wf").json(); assert len(items)==1
    decision=client.post(f"/api/triage/{items[0]['id']}/decision",json={"decision":"issue","operator":"tester"})
    assert decision.status_code==200 and decision.json()["issue_id"] is not None


def test_review_feedback_becomes_scoped_memory(tmp_path):
    settings=_settings(tmp_path); version_id=_seed_version(settings); issue_id=_create_issue(settings,version_id,20,"semantic_duplicate")
    sid=_create_approved_suggestion(settings,review_batch_id="memory",version_id=version_id,issue_id=issue_id,action_type="mark_as_valid",target_node_id=20,payload={})
    suggestion=SuggestionRepository(settings).get_suggestion(sid)
    AgentMemoryService(settings).record_review_feedback(workflow_id="wf",version_id=version_id,suggestion=suggestion,decision="reject",reason="不同路径同名属于合理复用")
    context=AgentMemoryService(settings).get_suggestion_context(version_id=version_id,issue_type="semantic_duplicate",action_type="mark_as_valid",target_node_id=20)
    assert context[0]["content"]["decision"]=="reject" and "合理复用" in context[0]["content"]["reason"]


def test_golden_metrics_release_gate_and_api(tmp_path):
    service=EvaluationService(); result=service.evaluate(golden=[{"dataset_version":"demo-v1","node_id":1,"issue_type":"wide_node"},{"dataset_version":"demo-v1","node_id":2,"issue_type":"deep_level"}],predicted=[{"node_id":1,"issue_type":"wide_node","confidence":.9},{"node_id":3,"issue_type":"deep_level","confidence":.4}],suggestions=[{"schema_valid":True,"executable":True}],workflow_id="wf")
    assert result.detection_precision==.5 and result.detection_recall==.5 and result.detection_f1==.5
    assert service.release_gate(result,None)["status"]=="baseline_missing"
    settings=_settings(tmp_path); version_id=_seed_version(settings)
    from backend.app.db import connect
    from backend.app.repositories.diagnosis_repo import DiagnosisRepository
    from backend.app.schemas.issue import DiagnosisIssueRecord
    _create_issue(settings,version_id,20,"wide_node"); _create_issue(settings,version_id,30,"semantic_duplicate")
    with connect(settings) as c:
        c.execute("INSERT INTO task_record(id,file_id,task_type,status,current_step,progress,workflow_id,thread_id,version_id) VALUES('task-eval',1,'taxonomy_workflow','completed','completed',100,'wf','thread',?)",(version_id,))
        c.execute("INSERT INTO adjustment_suggestion(issue_id,review_batch_id,version_id,action_type,target_node_id,reason,suggestion,risk_level,confidence,need_confirm,status) VALUES(1,'eval',?,'mark_as_valid',20,'ok','ok','low',1,0,'approved')",(version_id,))
    client=TestClient(create_app(settings)); created=client.post("/api/evaluations",json={"workflow_id":"wf","dataset_version":"demo-v1","agent_bundle_version":"bundle-1"})
    evaluation_id=created.json()["evaluation_id"]
    assert client.get(f"/api/evaluations/release-gate?dataset_version=demo-v1&evaluation_id={evaluation_id}").json()["status"]=="baseline_missing"
    assert client.post(f"/api/evaluations/{evaluation_id}/promote-baseline",json={"operator":"tester","agent_bundle_version":"bundle-1"}).status_code==200
    assert client.get(f"/api/evaluations/release-gate?dataset_version=demo-v1&evaluation_id={evaluation_id}").json()["passed"] is True
