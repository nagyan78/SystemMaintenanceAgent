# 阶段二：Agent 执行单元化 Implementation Plan

> **历史实施计划（SUPERSEDED）**：保留用于追溯四阶段方案，不再决定当前开发顺序。当前路线见 `ROADMAP.md`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将内容诊断和建议生成从单个 LangGraph 节点内的串行黑盒循环，升级为候选/问题级可持久化、可并发、可重试、可观测的执行单元。

**Architecture:** 使用 `agent_run + agent_work_item + agent_event` 作为业务执行账本，LangGraph `Send` 负责 fan-out，reducer 汇总计数和路由。模型和只读工具可并发，SQLite 副作用通过幂等 work item 提交；Graph State 只保存 run ID 和计数。

**Tech Stack:** LangGraph Send API、LangChain tools、SQLite WAL、FastAPI SSE、Vue 3、pytest。

---

## 0. 前置条件与边界

前置：阶段一全部测试通过，workflow 已支持版本驱动、质量评价和验证闭环。

本阶段交付：

- 不再使用模块级 `_runtime_settings/_runtime_qdrant_store/_runtime_embeddings`。
- 内容诊断一候选一 work item，建议生成一问题一 work item。
- 已成功 work item 恢复时直接跳过，失败只重试对应对象。
- DeepSeek/Qdrant/Embedding 有独立并发和退避策略。
- 前端实时展示 candidate/issue 进度、工具和证据摘要。
- SSE 支持 event ID 和断线续传。

本阶段不实现新动作类型、滚动规划、模型路由和长期记忆。

## 1. 文件结构

### 新建

- `backend/app/schemas/agent_run.py`
- `backend/app/repositories/agent_run_repo.py`
- `backend/app/services/agent_run_service.py`
- `backend/app/services/tool_factory.py`
- `backend/app/services/retry_policy.py`
- `backend/app/agents/content_diagnosis_subgraph.py`
- `backend/app/agents/suggestion_subgraph.py`
- `backend/app/agents/reducers.py`
- `backend/app/api/agent_runs.py`
- `backend/app/services/workflow_runner.py`
- `backend/tests/test_phase2_agent_work_items.py`
- `backend/tests/test_phase2_send_subgraphs.py`
- `backend/tests/test_phase2_agent_events.py`
- `frontend/src/components/AgentRunProgress.vue`
- `frontend/src/components/AgentEventLog.vue`

### 修改

- `backend/app/db.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/agents/states.py`
- `backend/app/agents/graph.py`
- `backend/app/agents/nodes.py`
- `backend/app/agents/events.py`
- `backend/app/api/workflows.py`
- `backend/app/repositories/task_repo.py`
- `backend/app/services/content_diagnosis_service.py`
- `backend/app/services/suggestion_service.py`
- `backend/app/tools/tree_tools.py`
- `backend/app/tools/validation_tools.py`
- `frontend/src/api/workflows.ts`
- `frontend/src/views/WorkflowView.vue`
- `frontend/tests/navigation-contract.test.mjs`

---

### Task 1: 消除全局运行时并建立工具工厂

**Files:**
- Create: `backend/app/services/tool_factory.py`
- Modify: `backend/app/tools/tree_tools.py`
- Modify: `backend/app/tools/validation_tools.py`
- Modify: `backend/app/services/content_diagnosis_service.py`
- Modify: `backend/app/services/suggestion_service.py`
- Test: `backend/tests/test_phase2_agent_work_items.py`

- [ ] **Step 1: 编写并发隔离失败测试**

```python
def test_two_toolsets_do_not_share_runtime_settings(tmp_path):
    settings_a, version_a = _seed_database(tmp_path / "a", "A节点")
    settings_b, version_b = _seed_database(tmp_path / "b", "B节点")
    tools_a = AgentToolFactory(settings_a).content_diagnosis_tools()
    tools_b = AgentToolFactory(settings_b).content_diagnosis_tools()
    detail_a = _tool(tools_a, "get_node_detail").invoke(
        {"version_id": version_a, "category_id": 1}
    )
    detail_b = _tool(tools_b, "get_node_detail").invoke(
        {"version_id": version_b, "category_id": 1}
    )
    assert detail_a["category_name"] == "A节点"
    assert detail_b["category_name"] == "B节点"
```

- [ ] **Step 2: 运行测试并确认全局配置会串扰或工厂不存在**

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_agent_work_items.py::test_two_toolsets_do_not_share_runtime_settings -v`
Expected: FAIL。

- [ ] **Step 3: 实现实例化 Tool Factory**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ToolScope:
    workflow_id: str
    version_id: int
    subject_id: int | None = None

def _enforce_scope(
    scope: ToolScope | None,
    version_id: int,
) -> None:
    if scope is None:
        return
    if version_id != scope.version_id:
        raise ValueError("Tool version_id is outside workflow scope")

class AgentToolFactory:
    def __init__(self, settings, *, qdrant_store=None, embeddings=None):
        self.settings = settings
        self.taxonomy = TaxonomyRepository(settings)
        self.diagnosis = DiagnosisRepository(settings)
        self.suggestions = SuggestionRepository(settings)
        self.store = qdrant_store
        self.embeddings = embeddings

    def content_diagnosis_tools(self, scope: ToolScope | None = None):
        taxonomy = self.taxonomy
        store = self.store or QdrantStore(self.settings, embeddings=self.embeddings)

        @tool
        def get_node_detail(version_id: int, category_id: int) -> dict:
            """查询当前版本节点详情。"""
            _enforce_scope(scope, version_id)
            return taxonomy.get_node_detail(version_id, category_id) or {}

        @tool
        def search_similar_nodes(version_id: int, node_text: str, top_k: int = 10) -> list[dict]:
            """查询当前版本语义相似节点。"""
            _enforce_scope(scope, version_id)
            return store.search_similar(version_id, node_text, min(max(top_k, 1), 20))

        @tool
        def get_node_path(version_id: int, category_id: int) -> str:
            """查询当前版本节点路径。"""
            _enforce_scope(scope, version_id)
            return taxonomy.get_node_path(version_id, category_id)

        @tool
        def get_children(version_id: int, parent_id: int) -> list[dict]:
            """查询当前版本直接子节点。"""
            _enforce_scope(scope, version_id)
            return taxonomy.get_children(version_id, parent_id)[:100]

        return [get_node_detail, get_node_path, get_children, search_similar_nodes]
```

`ToolScope` 固定 workflow/version/subject，系统注入并校验作用域；模型不能通过参数访问其他版本或候选。内容诊断最终结论改为 worker 解析的结构化输出，由 worker 按 work item 幂等写库，不再把数据库提交工具暴露给模型。

- [ ] **Step 4: Agent 构造函数显式接收 tools**

删除 `configure_tree_tool_runtime/configure_validation_tool_runtime` 调用。默认 tools 由 `AgentToolFactory(settings)` 创建；测试仍可传 fake tools。

- [ ] **Step 5: 验证并提交**

Run: `.venv/bin/python -m pytest backend/tests/test_m2_vector_content_agent.py backend/tests/test_m3_suggestion_review.py backend/tests/test_phase2_agent_work_items.py -v`
Expected: PASS。

```bash
git add backend/app/services/tool_factory.py backend/app/tools/tree_tools.py backend/app/tools/validation_tools.py backend/app/services/content_diagnosis_service.py backend/app/services/suggestion_service.py backend/tests/test_phase2_agent_work_items.py
git commit -m "refactor: isolate agent tool runtimes"
```

---

### Task 2: 建立 Agent 执行账本和 SQLite 并发基础

**Files:**
- Create: `backend/app/schemas/agent_run.py`
- Create: `backend/app/repositories/agent_run_repo.py`
- Modify: `backend/app/db.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_phase2_agent_work_items.py`

- [ ] **Step 1: 编写表、唯一键和原子 claim 测试**

```python
def test_work_item_is_idempotent_and_claimed_once(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    repo = AgentRunRepository(settings)
    run_id = repo.create_run(_run(workflow_id="wf", agent_type="content_diagnosis"))
    first = repo.upsert_work_item(run_id, "candidate", "441", {"category_id": 441})
    second = repo.upsert_work_item(run_id, "candidate", "441", {"category_id": 441})
    assert first == second
    assert repo.claim_work_item(first, worker_id="worker-a") is True
    assert repo.claim_work_item(first, worker_id="worker-b") is False
```

- [ ] **Step 2: 创建 schema**

```python
AgentRunStatus = Literal["pending", "running", "completed", "completed_degraded", "failed", "cancelled"]
WorkItemStatus = Literal[
    "pending", "running", "succeeded", "clean", "inconclusive",
    "retryable_failed", "permanent_failed", "skipped", "cancelled",
]

class AgentRunRecord(BaseModel):
    id: str
    workflow_id: str
    agent_type: str
    version_id: int
    plan_revision: int = 1
    status: AgentRunStatus = "pending"
    model_profile: str = "default"
    budget: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)

class AgentWorkItemRecord(BaseModel):
    id: str
    run_id: str
    subject_type: str
    subject_id: str
    status: WorkItemStatus = "pending"
    attempt: int = 0
    max_attempts: int = 3
    input_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
```

- [ ] **Step 3: 创建三张表**

创建 `agent_run`、`agent_work_item`、`agent_event`。关键索引：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_work_item_unique
ON agent_work_item(run_id, subject_type, subject_id);

CREATE INDEX IF NOT EXISTS idx_agent_work_item_status
ON agent_work_item(run_id, status);

CREATE INDEX IF NOT EXISTS idx_agent_event_workflow_sequence
ON agent_event(workflow_id, id);
```

`agent_event` 不保存原始 prompt/chain-of-thought，只保存脱敏 summary JSON。

- [ ] **Step 4: 配置 SQLite WAL 和原子 claim**

`connect()` 执行：

```python
connection.execute("PRAGMA foreign_keys = ON")
connection.execute("PRAGMA journal_mode = WAL")
connection.execute("PRAGMA busy_timeout = 5000")
```

claim 使用单条条件更新：

```sql
UPDATE agent_work_item
SET status='running', worker_id=?, lease_expires_at=?, attempt=attempt+1
WHERE id=? AND status IN ('pending', 'retryable_failed')
```

以 `cursor.rowcount == 1` 判断领取成功。

- [ ] **Step 5: 验证并提交**

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_agent_work_items.py -v`
Expected: PASS。

```bash
git add backend/app/schemas/agent_run.py backend/app/repositories/agent_run_repo.py backend/app/db.py backend/app/config.py backend/tests/test_phase2_agent_work_items.py
git commit -m "feat: add durable agent work item ledger"
```

---

### Task 3: 将内容诊断改为 Send/map-reduce 子图

**Files:**
- Create: `backend/app/agents/content_diagnosis_subgraph.py`
- Create: `backend/app/agents/reducers.py`
- Create: `backend/app/services/agent_run_service.py`
- Modify: `backend/app/agents/states.py`
- Modify: `backend/app/agents/graph.py`
- Modify: `backend/app/agents/nodes.py`
- Test: `backend/tests/test_phase2_send_subgraphs.py`

- [ ] **Step 1: 编写部分失败和恢复测试**

```python
class AlwaysTimeoutLLM:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        raise TimeoutError("simulated permanent timeout")

def test_content_subgraph_retries_only_unfinished_candidates(tmp_path):
    settings, version_id = _seed_candidates(tmp_path, count=5)
    llm = FailOnceForCandidate(candidate_id=4)
    graph = build_content_diagnosis_subgraph(settings=settings, llm=llm)
    first = graph.invoke(_content_state(version_id), config={"configurable": {"thread_id": "wf"}})
    assert first["work_item_counts"]["succeeded"] == 4
    assert first["work_item_counts"]["retryable_failed"] == 1
    second = graph.invoke(Command(resume={"retry": True}), config={"configurable": {"thread_id": "wf"}})
    assert second["work_item_counts"]["succeeded"] == 5
    assert llm.calls_by_candidate[1] == 1
    assert llm.calls_by_candidate[4] == 2

def test_retryable_error_becomes_permanent_after_max_attempts(tmp_path):
    settings, version_id = _seed_candidates(tmp_path, count=1)
    service = AgentRunService(settings, llm=AlwaysTimeoutLLM())
    prepared = service.prepare_content_candidates(
        workflow_id="wf-permanent", version_id=version_id,
    )
    item_id = prepared.work_item_ids[0]
    for _attempt in range(3):
        service.execute_content_work_item(item_id, worker_id="test-worker")
    item = AgentRunRepository(settings).get_work_item(item_id)
    assert item.attempt == 3
    assert item.status == "permanent_failed"
    assert item.error_code == "MAX_ATTEMPTS_EXHAUSTED"
    calls_before = service.llm.calls
    service.execute_content_work_item(item_id, worker_id="test-worker")
    assert service.llm.calls == calls_before
```

- [ ] **Step 2: 定义 reducer 状态**

```python
from typing import Annotated, Any
import operator
from pydantic import BaseModel, Field

class ContentDiagnosisSubgraphState(BaseModel):
    workflow_id: str
    run_id: str
    version_id: int
    work_item_ids: list[str] = Field(default_factory=list)
    processed_count: Annotated[int, operator.add] = 0
    issue_count: Annotated[int, operator.add] = 0
    clean_count: Annotated[int, operator.add] = 0
    inconclusive_count: Annotated[int, operator.add] = 0
    failed_count: Annotated[int, operator.add] = 0
    work_item_counts: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 3: 创建 work items 并 fan-out**

```python
from langgraph.types import Send

def prepare_candidates(state: ContentDiagnosisSubgraphState) -> dict:
    ids = AgentRunService(settings).prepare_content_candidates(
        workflow_id=state.workflow_id, version_id=state.version_id,
    )
    return {"run_id": ids.run_id, "work_item_ids": ids.work_item_ids}

def fan_out_candidates(state: ContentDiagnosisSubgraphState) -> list[Send]:
    repo = AgentRunRepository(settings)
    return [
        Send("diagnose_candidate", {"run_id": state.run_id, "work_item_id": item_id})
        for item_id in state.work_item_ids
        if repo.is_runnable(item_id)
    ]
```

- [ ] **Step 4: 实现幂等 worker 和 reducer**

worker 先原子 claim；已 succeeded/clean 的 item 直接返回零增量。模型/tool 错误按 RetryPolicy 分类；结果和 issue 使用 work item ID 作为幂等键提交。reduce 从数据库重新统计，不依赖内存列表。

状态转换必须明确：retryable error 且 `attempt < max_attempts` → `retryable_failed`；retryable error 且 `attempt >= max_attempts` → `permanent_failed` + `MAX_ATTEMPTS_EXHAUSTED`；`permanent_failed` 不再被 `is_runnable()` 选中。永久失败计入 coverage，是否使整个 run failed 或 completed_degraded 由 required/optional policy 决定。

- [ ] **Step 5: 接入主图并提交**

将 `content_diagnosis_node` 替换为已编译 subgraph；主 State 只接收 `analysis_run_id/content_issue_count/work_item_counts`。

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_send_subgraphs.py backend/tests/test_m2_vector_content_agent.py -v`
Expected: PASS。

```bash
git add backend/app/agents/content_diagnosis_subgraph.py backend/app/agents/reducers.py backend/app/services/agent_run_service.py backend/app/agents/states.py backend/app/agents/graph.py backend/app/agents/nodes.py backend/tests/test_phase2_send_subgraphs.py
git commit -m "feat: map content diagnosis over durable work items"
```

---

### Task 4: 将建议生成改为问题级子图

**Files:**
- Create: `backend/app/agents/suggestion_subgraph.py`
- Modify: `backend/app/services/agent_run_service.py`
- Modify: `backend/app/services/suggestion_service.py`
- Modify: `backend/app/agents/graph.py`
- Test: `backend/tests/test_phase2_send_subgraphs.py`

- [ ] **Step 1: 编写建议幂等和部分恢复测试**

```python
def test_suggestion_subgraph_does_not_duplicate_saved_suggestions(tmp_path):
    settings, version_id, issue_ids = _seed_pending_issues(tmp_path, count=3)
    graph = build_suggestion_subgraph(settings=settings, llm=FakeSuggestionLLM())
    state = graph.invoke(_suggestion_state(version_id, issue_ids))
    state = graph.invoke(state)
    suggestions = SuggestionRepository(settings).list_suggestions(version_id=version_id)
    assert len(suggestions) == 3
    assert len({item.action_payload["work_item_id"] for item in suggestions}) == 3
```

- [ ] **Step 2: 准备当前 run 的 issue work items**

只读取当前 `analysis_run_id` 产生且 status=pending 的 issue，禁止读取版本下全部历史 pending issue。work item 唯一键为 `(suggestion_run_id, 'issue', issue_id)`。

- [ ] **Step 3: fan-out SuggestionAgent**

规则建议也通过 work item 执行并持久化，以便统一 coverage；LLM 建议使用实例化 Tool Factory。`submit_suggestion` 写入 `work_item_id/analysis_run_id/workflow_id` 并具有唯一索引。

- [ ] **Step 4: reduce review batch**

所有成功建议使用同一 `review_batch_id`；永久失败和 inconclusive 保留在 run coverage 中。若成功数为 0，路由报告；否则进入人工审核。

- [ ] **Step 5: 验证并提交**

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_send_subgraphs.py backend/tests/test_m3_suggestion_review.py -v`
Expected: PASS。

```bash
git add backend/app/agents/suggestion_subgraph.py backend/app/services/agent_run_service.py backend/app/services/suggestion_service.py backend/app/agents/graph.py backend/tests/test_phase2_send_subgraphs.py
git commit -m "feat: map suggestions over diagnosis issues"
```

---

### Task 5: 统一重试、并发、取消和重启恢复

**Files:**
- Create: `backend/app/services/retry_policy.py`
- Create: `backend/app/services/workflow_runner.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/workflows.py`
- Modify: `backend/app/repositories/agent_run_repo.py`
- Test: `backend/tests/test_phase2_agent_work_items.py`

- [ ] **Step 1: 编写 429、lease 和 cancel 测试**

测试必须断言：429 读取 Retry-After；lease 过期可被新 worker 领取；cancelled run 不再领取新 item；已完成 item 不重复执行。

- [ ] **Step 2: 实现 RetryPolicy**

```python
class RetryPolicy:
    def __init__(self, max_attempts=3, base_delay=1.0, max_delay=30.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    def classify(self, exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        if status == 429 or status is not None and status >= 500:
            return "retryable_external"
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return "retryable_external"
        return "permanent_internal"

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        return min(self.base_delay * (2 ** max(attempt - 1, 0)), self.max_delay)
```

- [ ] **Step 3: 增加并发配置**

Settings 增加 `agent_llm_max_concurrency=4`、`agent_qdrant_max_concurrency=8`、`agent_embedding_max_concurrency=4`、`agent_work_item_max_attempts=3`、`agent_lease_seconds=120`。调用图时通过 `max_concurrency` 和资源 semaphore 双重限制。

- [ ] **Step 4: start/resume 只提交 runner 命令**

`WorkflowRunner.submit_start/submit_resume` 负责后台运行；API 快速返回。应用启动时扫描 running + lease expired 工作单元并恢复。增加 `POST /api/workflows/{task_id}/cancel`，取消只停止领取新 item，当前副作用安全完成后终止。

- [ ] **Step 5: 验证并提交**

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_agent_work_items.py -v`
Expected: PASS。

```bash
git add backend/app/services/retry_policy.py backend/app/services/workflow_runner.py backend/app/config.py backend/app/api/workflows.py backend/app/repositories/agent_run_repo.py backend/tests/test_phase2_agent_work_items.py
git commit -m "feat: recover retry and cancel agent work items"
```

---

### Task 6: Agent 事件和 SSE 断点续传

**Files:**
- Modify: `backend/app/agents/events.py`
- Modify: `backend/app/repositories/task_repo.py`
- Create: `backend/app/api/agent_runs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/workflows.py`
- Test: `backend/tests/test_phase2_agent_events.py`

- [ ] **Step 1: 编写事件脱敏和续传测试**

```python
def test_agent_event_is_resumable_and_redacted(client, seeded_task):
    first = client.get(f"/api/workflows/{seeded_task}/events?after_id=0")
    event_id = _last_event_id(first.text)
    second = client.get(
        f"/api/workflows/{seeded_task}/events",
        headers={"Last-Event-ID": str(event_id)},
    )
    assert f"id: {event_id}" not in second.text
    assert "api_key" not in first.text
    assert "raw_prompt" not in first.text
    assert "chain_of_thought" not in first.text
```

- [ ] **Step 2: 定义事件 payload**

统一字段：`event_id/workflow_id/run_id/work_item_id/agent_name/event_type/phase/tool_name/status/attempt/latency_ms/model/token_usage/summary/evidence_refs/created_time`。

- [ ] **Step 3: 在模型和工具边界记录事件**

记录 started/completed/failed；summary 只保留业务摘要。observation 通过 Tool 注册表的 redaction policy 截断和脱敏。

- [ ] **Step 4: SSE 输出 id 并消费 cursor**

`format_sse` 输出 `id: <event_id>`；API 优先读取 `Last-Event-ID`，其次 query `after_id`。前端按 event ID 去重。

- [ ] **Step 5: 验证并提交**

Run: `.venv/bin/python -m pytest backend/tests/test_phase2_agent_events.py backend/tests/test_m1_workflow.py -v`
Expected: PASS。

```bash
git add backend/app/agents/events.py backend/app/repositories/task_repo.py backend/app/api/agent_runs.py backend/app/main.py backend/app/api/workflows.py backend/tests/test_phase2_agent_events.py
git commit -m "feat: stream resumable structured agent events"
```

---

### Task 7: 前端 Agent 运行进度

**Files:**
- Create: `frontend/src/components/AgentRunProgress.vue`
- Create: `frontend/src/components/AgentEventLog.vue`
- Modify: `frontend/src/api/workflows.ts`
- Modify: `frontend/src/views/WorkflowView.vue`
- Modify: `frontend/tests/navigation-contract.test.mjs`

- [ ] **Step 1: 扩展 contract test**

断言 WorkflowView 使用两个新组件，SSE 监听 `agent_step/agent_tool_completed/candidate_completed`，API 支持 event ID，UI 包含“候选总数/已处理/发现问题/正常/不确定/失败/剩余”。

- [ ] **Step 2: 实现 AgentRunProgress**

props 使用结构化计数，不从日志文本猜测状态：

```ts
type AgentRunCounts = {
  total: number
  processed: number
  issues: number
  clean: number
  inconclusive: number
  failed: number
  remaining: number
}
```

- [ ] **Step 3: 实现 AgentEventLog**

展示对象、决策摘要、工具、证据、置信度、耗时、attempt；禁止渲染 raw prompt/Thought。事件按 ID 去重，最多保留最近 200 条可见记录。

- [ ] **Step 4: 接入 WorkflowView 和取消按钮**

节点进度与 candidate progress 分开展示；取消时调用 cancel API 并显示“正在安全停止”。

- [ ] **Step 5: 验证并提交**

Run: `cd frontend && npm run test:contract && npm run build`
Expected: PASS。

```bash
git add frontend/src/components/AgentRunProgress.vue frontend/src/components/AgentEventLog.vue frontend/src/api/workflows.ts frontend/src/views/WorkflowView.vue frontend/tests/navigation-contract.test.mjs
git commit -m "feat: show candidate-level agent progress"
```

---

### Task 8: 阶段二故障注入验收

**Files:**
- Modify: `backend/tests/test_phase2_agent_work_items.py`
- Modify: `backend/tests/test_phase2_send_subgraphs.py`
- Modify: `backend/tests/test_phase2_agent_events.py`

- [ ] **Step 1: 增加第 48 个候选故障场景**

准备 50 个 candidate：场景 A 的第 48 个第一次 timeout，断言前 47 个和后 2 个成功结果保留，恢复只执行第 48 个；场景 B 的第 48 个始终 timeout，断言第三次后进入 permanent_failed，第四次恢复不再调用模型且 workflow 不无限重试。

- [ ] **Step 2: 增加进程崩溃窗口场景**

分别在“业务结果提交前”和“业务结果提交后、checkpoint 前”注入异常，断言没有重复 issue/suggestion。

- [ ] **Step 3: 增加两个 workflow 并发隔离场景**

两个不同临时数据库、不同 Qdrant fake，同时运行候选 worker；断言不串版本、工具、事件和结果。

- [ ] **Step 4: 执行完整验证**

Run: `.venv/bin/python -m pytest backend/tests`
Expected: 全部 PASS。

Run: `cd frontend && npm run test:contract && npm run build`
Expected: 全部 PASS。

- [ ] **Step 5: 提交阶段二**

```bash
git add backend/tests/test_phase2_agent_work_items.py backend/tests/test_phase2_send_subgraphs.py backend/tests/test_phase2_agent_events.py
git commit -m "feat: complete durable concurrent agent execution"
```

阶段二完成标准：50 个候选中的任意一个失败不会导致其他成果丢失，用户能实时看到候选级进度，SSE 重连不重复事件，服务恢复后只继续未完成 work item。
