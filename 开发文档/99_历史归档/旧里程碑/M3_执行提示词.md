# M3 里程碑执行 Prompt

> **历史执行材料（ARCHIVED）**：不得直接作为当前开发 prompt 使用。当前事实和路线见 `CURRENT_IMPLEMENTATION.md`、`ROADMAP.md`。

> 用途：先把"环境准备"确认完毕，再把"复制以下内容作为 Prompt"代码块整体复制给 AI 编程助手，启动 M3 代码实现。
> 项目路径：/Users/flflfl/Documents/code/SystemMaintenanceAgent
> 技术方案：LLM 用 DeepSeek API（OpenAI 兼容），Embedding 用通义千问 DashScope（OpenAI 兼容），统一 langchain-openai

---

## 一、环境准备（开工前必做）

M3 不需要新的外部依赖，M2 的 Qdrant + DeepSeek API + 千问 Embedding 全部复用。

| 组件 | 状态 | 需要操作 |
|------|------|---------|
| Docker + Qdrant | M2 已配置 | 启动 Qdrant 容器 |
| DeepSeek API | M2 已配置 | 确认 .env 中 DEEPSEEK_API_KEY 有效 |
| 千问 Embedding API | M2 已配置 | 确认 .env 中 DASHSCOPE_API_KEY 有效 |
| langchain-openai | M2 已安装 | 无 |
| qdrant-client | M2 已安装 | 无 |

### 步骤 1：启动 Qdrant

```bash
docker start qdrant  # 如果之前 stop 了
curl http://localhost:6333/  # 验证
```

### 步骤 2：验证 .env 配置

确认 `.env` 文件中：
```
DEEPSEEK_API_KEY=sk-你的deepseek密钥
DASHSCOPE_API_KEY=sk-你的千问密钥
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
```

> ⚠️ 确认 `DEEPSEEK_MODEL=deepseek-chat`（不是 deepseek-v4-flash，那个模型不存在）

### 步骤 3：验证 M2 测试通过

```bash
cd /Users/flflfl/Documents/code/SystemMaintenanceAgent
.venv/bin/python -m pytest backend/tests/ -v
```

确保 M1 + M2 的全部测试通过后再开始 M3。

---

## 二、M3 核心概念图

```
M3 做什么：诊断问题 → LLM 生成建议 → 人工审核 → 校验动作（不执行、不生成新版本）

    diagnosis_issue               adjustment_suggestion              operation_log
    (M1/M2 产出)                  (M3 产出)                          (M3 产出)
         │                              │                                │
         ▼                              ▼                                ▼
  ┌─────────────┐   SuggestionAgent   ┌──────────────┐   interrupt   ┌────────────┐
  │ 结构诊断问题 │ ────ReAct Loop────→ │ 结构化建议    │ ──────────→  │ 人工审核    │
  │ 内容诊断问题 │   (LLM+tool+自校验)  │ action_type  │   /resume    │ approve    │
  └─────────────┘                     │ reason       │ ←──────────  │ reject     │
                                       │ risk_level   │              │ edit       │
                                       └──────────────┘              └────────────┘
                                              │                          │
                                              ▼                          ▼
                                       validate_action            validate_action_node
                                       (程序校验合法性)            (校验已审核动作)
```

### M3 涉及 3 个节点

| 节点 | 性质 | 做什么 |
|------|------|--------|
| `generate_suggestion_node` | 🤖智能体·ReAct loop | LLM 分析问题→查询上下文→生成建议→自校验→提交 |
| `wait_human_review_node` | 工作流·interrupt | LangGraph interrupt 暂停，等待 POST /resume |
| `validate_action_node` | 工作流·规则 | 校验已审核动作的合法性 |

> M3 的阶段边界：只产出并审核 `adjustment_suggestion`，只校验动作合法性；不执行节点移动/合并/改名/同义词清理，不生成 `v1.1`，不导出 Excel。这些属于 M4/F07/F08。

### 当前 graph 拓扑问题（必须修复）

当前 `content_diagnosis_node` 直接连到 `generate_report_node`，跳过了 M3 的三个节点。M3 需要改为：

```
content_diagnosis_node → generate_suggestion_node → wait_human_review_node
                                                        ↓ (conditional)
                                              ┌─ reject/no actions → generate_report_node
                                              └─ has approved → validate_action_node
                                                                    ↓ (conditional)
                                                              ┌─ error → wait_human_review_node (回退)
                                                              └─ ok → generate_report_node（M3 收口）
```

> `execute_action_node → save_new_version_node` 从 M4 开始接入。M3 禁止把校验通过的建议直接执行。

---

## 三、复制以下内容作为 Prompt

```
你是一个资深 Python 后端工程师，现在要在现有项目上实现 M3 里程碑：建议生成智能体 + 人工审核闭环。这是项目体现"可解释、可确认、可校验"治理能力的关键里程碑。M3 只生成、审核并校验建议，不执行动作、不生成新版本。

## 项目背景
项目名：产品标准体系维护智能体（FastAPI + LangGraph + LangChain + SQLite + Qdrant）。
- M1 已完成：graph 的 5 个确定性节点已接真实 service，确定性闭环跑通
- M2 已完成：Qdrant 向量索引 + 内容诊断 ReAct Agent Loop，diagnosis_planning_node 集成到 graph
- M3 目标：实现建议生成的 Agent Loop（LLM 分析→查询→生成→自校验→重试）+ LangGraph interrupt/resume 人工审核闭环 + 已审核动作校验
- M3 非目标：不执行动作、不生成新版本、不导出 Excel；这些从 M4 开始实现

## LLM 与 Embedding 方案（沿用 M2）
- **Chat LLM**：DeepSeek API，用 langchain-openai 的 ChatOpenAI，base_url="https://api.deepseek.com"，model="deepseek-chat"
- **Embedding**：通义千问 DashScope，用 langchain-openai 的 OpenAIEmbeddings（M3 建议生成不需要 embedding，但 validate_action 中 search_similar_nodes 可能用到）
- ChatOpenAI 必须加 request_timeout=60 防止卡死
- API key 从环境变量读取：DEEPSEEK_API_KEY、DASHSCOPE_API_KEY（用 python-dotenv 加载 .env）

## 必读文档（开工前先读，不要跳过）
1. dev-doc/00_开发里程碑索引.md — 读 §6 M3 章节（节点清单/文件清单/数据结构/接口契约/实现顺序/验收标准/禁止行为）
2. dev-doc/05_智能建议生成开发设计.md — 完整阅读，特别是 §12 建议生成 Agent Loop 设计（ReAct 伪代码/Tool 列表/自校验规则/Prompt 模板）
3. dev-doc/06_人工审核开发设计.md — 完整阅读，特别是 §4 状态机/§5 API 设计/§6 审核校验/§7 操作日志
4. dev-doc/10_LangGraph智能体工作流开发设计.md — 读 §8.8 generate_suggestion_node、§8.8 wait_human_review_node、§8.9 validate_action_node、§9 条件路由、§10 Graph 构建示例
5. backend/app/agents/nodes.py — 现有节点实现（重点看 generate_suggestion_node/wait_human_review_node/validate_action_node 的占位代码，需要替换）
6. backend/app/agents/graph.py — 现有 graph 拓扑（重点看 content_diagnosis_node → generate_report_node 的边需要改为 → generate_suggestion_node）
7. backend/app/agents/states.py — State 定义（已有 review_batch_id/review_decision/review_payload 字段）
8. backend/app/services/content_diagnosis_service.py — M2 的 Agent Loop 实现（M3 的 SuggestionAgent 参考同样的模式）
9. backend/app/tools/tree_tools.py — M2 的 @tool 函数（M3 的 validate_action/submit_suggestion 参考）
10. backend/app/agents/prompts.py — 现有 prompt（M3 需追加建议生成 prompt）
11. backend/app/db.py — 数据库建表（adjustment_suggestion 表和 operation_log 表已存在，但 adjustment_suggestion 表缺 review_batch_id 列）
12. backend/app/repositories/diagnosis_repo.py — 诊断问题查询（当前缺少 list_open_issues/list_pending_issues，M3 需要补充，用于 SuggestionAgent 读取 status='pending' 的 diagnosis_issue）

## 当前代码状态（M3 需要改的地方）

### nodes.py 中 3 个占位节点（当前是硬编码，需要替换）：
```python
# 当前 generate_suggestion_node — 占位，返回 suggestion_count=0
def generate_suggestion_node(state):
    _require_current_version_id(state)
    return _complete_step(state, "generate_suggestion_node", ..., suggestion_count=0)

# 当前 wait_human_review_node — 有 interrupt 但 review_batch_id 未设置
def wait_human_review_node(state):
    review_batch_id = _require_review_batch_id(state)  # 会报错，因为没人设置 review_batch_id
    decision = interrupt({...})
    ...

# 当前 validate_action_node — 占位，什么都没做
def validate_action_node(state):
    _require_review_batch_id(state)
    return _complete_step(state, "validate_action_node", ..., progress=86)
```

### graph.py 中缺少的边：
```python
# 当前（错误）：
builder.add_edge("content_diagnosis_node", "generate_report_node")

# 应改为：
builder.add_edge("content_diagnosis_node", "generate_suggestion_node")
builder.add_edge("generate_suggestion_node", "wait_human_review_node")
```

### checkpointer 与 task 状态问题：
当前 `_run_workflow` 没有传 checkpointer，interrupt 无法工作。需要在 app.state 中维护一个全局 InMemorySaver 实例。
同时需要处理 graph interrupt 后的 `task_record` 状态更新：到达 `wait_human_review_node` 时应写入 `status="waiting_review"`、`current_step="wait_human_review"`、`interrupt_payload`，并保证 `GET /api/workflows/{task_id}` 能返回 `review_batch_id`。
`task_record` 已有 `workflow_id` / `thread_id` / `interrupt_payload` / `result_payload` 字段，M3 应复用这些字段保存 interrupt payload 和 resume 后结果，不要另起一套 workflow 状态表。

## 文件清单（新建/修改）

### 新建文件：
1. `backend/app/services/suggestion_service.py` — 建议生成 Agent Loop 封装（SuggestionAgent）
2. `backend/app/services/review_service.py` — 审核请求创建 + 决策应用
3. `backend/app/services/action_service.py` — 动作校验逻辑（execute 留 M4）
4. `backend/app/repositories/suggestion_repo.py` — 建议 CRUD
5. `backend/app/repositories/operation_log_repo.py` — 操作日志 CRUD
6. `backend/app/api/reviews.py` — GET /api/reviews/{review_batch_id}
7. `backend/app/schemas/suggestion.py` — AdjustmentAction / ReviewRequest / ReviewDecisionResult 等 schema

### 修改文件：
1. `backend/app/tools/validation_tools.py` — 实现 validate_action + submit_suggestion 两个 @tool 函数
2. `backend/app/agents/prompts.py` — 追加建议生成 system prompt + few-shot
3. `backend/app/agents/nodes.py` — 替换 generate_suggestion/wait_review/validate 三个节点
4. `backend/app/agents/graph.py` — 修复 content_diagnosis → generate_suggestion 边 + 添加 generate_suggestion → wait_review 边
5. `backend/app/api/workflows.py` — 新增 POST /api/workflows/{task_id}/resume + 修复 checkpointer
6. `backend/app/db.py` — adjustment_suggestion 表加 review_batch_id 列（用 _ensure_columns 模式）；复用 task_record 的 workflow_id/thread_id/interrupt_payload/result_payload 字段
7. `backend/app/main.py` — 注册 reviews router + 初始化 checkpointer 到 app.state

## 数据结构

### AdjustmentAction（建议结构化输出）
```python
class AdjustmentAction(BaseModel):
    issue_id: int
    action_type: Literal["add_node", "move_node", "rename_node", "merge_node", "clean_synonym", "split_subtree", "mark_as_valid"]
    target_node_id: int
    target_node_name: str
    old_parent_id: int | None = None
    new_parent_id: int | None = None
    old_name: str | None = None
    new_name: str | None = None
    synonyms_to_remove: list[str] = Field(default_factory=list)
    reason: str
    suggestion: str
    risk_level: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)
    need_confirm: bool = True
```

### ReviewRequest
```python
class ReviewRequest(BaseModel):
    review_batch_id: str
    version_id: int
    suggestion_count: int
    suggestions: list[dict]  # 序列化的 AdjustmentAction 列表
```

### ResumeRequest（POST /resume 的请求体）
```python
class ResumeRequest(BaseModel):
    decision: Literal["approve", "reject", "edit"]
    approved_suggestion_ids: list[int] = Field(default_factory=list)
    rejected_suggestion_ids: list[int] = Field(default_factory=list)
    edited_suggestions: list[dict] = Field(default_factory=list)
```

### 数据库变更
adjustment_suggestion 表需要增加 review_batch_id 列：
```python
# 在 db.py 的 _ensure_columns 中添加
_ensure_columns(connection, "adjustment_suggestion", {"review_batch_id": "TEXT"})
```

## 接口契约

### API：恢复工作流
```
POST /api/workflows/{task_id}/resume
```
请求：
```json
{
  "decision": "approve",
  "approved_suggestion_ids": [1, 2, 3],
  "rejected_suggestion_ids": [4],
  "edited_suggestions": []
}
```
响应：
```json
{
  "task_id": "import_1_20260705",
  "status": "running",
  "current_step": "validate_action",
  "message": "workflow resumed"
}
```

### API：获取审核建议列表
```
GET /api/reviews/{review_batch_id}
```
响应：
```json
{
  "review_batch_id": "review_import_1_20260705_001",
  "version_id": 1,
  "suggestion_count": 5,
  "suggestions": [
    {
      "id": 1,
      "issue_id": 101,
      "action_type": "clean_synonym",
      "target_node_id": 237,
      "target_node_name": "苹果",
      "reason": "...",
      "suggestion": "...",
      "risk_level": "medium",
      "confidence": 0.92,
      "need_confirm": true,
      "status": "pending"
    }
  ]
}
```

### Tool 函数签名
```python
@tool
def validate_action(action_json: str) -> dict:
    """预校验建议动作合法性，返回 {valid: bool, reason: str}"""

@tool
def submit_suggestion(suggestion: dict) -> str:
    """提交一条维护建议，返回 suggestion_id"""
```

### Service 函数签名
```python
# suggestion_service
class SuggestionAgent:
    def run(self, version_id: int, issues: list[dict]) -> list[AdjustmentAction]: ...

# review_service
def create_review_request(version_id: int, review_batch_id: str, suggestions: list) -> ReviewRequest: ...
def apply_review_decision(review_batch_id: str, decision: dict) -> ReviewDecisionResult: ...

# action_service（M3 只做 validate，execute 留 M4）
def validate_approved_actions(review_batch_id: str) -> ValidationResult: ...
```

## 实现顺序（严格按此顺序）

### 阶段 1：Schema + DB + Repo（基础设施）
1. 新建 `schemas/suggestion.py`（AdjustmentAction / ReviewRequest / ReviewDecisionResult / ValidationResult）
2. 修改 `db.py`：adjustment_suggestion 表加 review_batch_id 列；task_record 已有 workflow_id/thread_id/interrupt_payload/result_payload，复用这些字段
3. 新建 `repositories/suggestion_repo.py`（create_suggestion / list_suggestions / update_suggestion_status / list_by_review_batch）
4. 新建 `repositories/operation_log_repo.py`（create_log / list_logs）
5. 修改 `repositories/diagnosis_repo.py`：补充 list_open_issues/list_pending_issues，用于按 version_id 读取 status='pending' 的 diagnosis_issue

### 阶段 2：Tools + Prompts（工具和提示词）
5. 实现 `tools/validation_tools.py`：
   - `validate_action` @tool：接收 action_json，校验 action_type/target_node_id/risk_level/confidence/synonyms_to_remove 等，返回 {valid, reason}
   - `submit_suggestion` @tool：接收 suggestion dict，写入 adjustment_suggestion 表，返回 suggestion_id
6. 追加 `agents/prompts.py`：建议生成 system prompt + few-shot example

### 阶段 3：SuggestionAgent（核心智能体）
7. 实现 `services/suggestion_service.py`：
   - SuggestionAgent 类，封装 ReAct loop
   - 对每条 diagnosis_issue 执行：分析→查询上下文→生成建议→validate_action 自校验→submit_suggestion 提交
   - 规则型建议（missing_parent/wide_node/duplicate_name）直接生成，不走 LLM
   - LLM 型建议（synonym_pollution/semantic_duplicate/bad_parent_child_relation/naming_irregular）走 Agent Loop
   - max_iter=8（内层 ReAct 循环），max_retry=3（自校验失败重试）
   - ChatOpenAI 加 request_timeout=60

### 阶段 4：Review + Action Service（审核和校验）
8. 实现 `services/review_service.py`：
   - create_review_request：生成 review_batch_id，查询 pending 建议列表
   - apply_review_decision：根据 decision 更新建议状态（approved/rejected/edited），写 operation_log
9. 实现 `services/action_service.py`：
   - validate_approved_actions：校验所有 approved 状态的建议动作合法性
   - 校验规则：move_node 不能移到自身子树下、merge_node 必须有源和目标、clean_synonym 的待删除词必须在原 syn_list 中等
   - execute 逻辑留空（M4 实现）

### 阶段 5：Node + Graph（接入工作流）
10. 修改 `agents/nodes.py`：
    - `generate_suggestion_node`：调 SuggestionAgent.run()，设置 review_batch_id 到 state
    - `wait_human_review_node`：设置 status="waiting_review"，调 review_service.create_review_request()，写 task_record.interrupt_payload，调 interrupt()
    - `validate_action_node`：调 action_service.validate_approved_actions()
11. 修改 `agents/graph.py`：
    - 改 `content_diagnosis_node → generate_report_node` 为 `content_diagnosis_node → generate_suggestion_node`
    - 加 `generate_suggestion_node → wait_human_review_node`
    - 审核通过后只进入 `validate_action_node → generate_report_node`
    - 不接入 `execute_action_node → save_new_version_node`，该链路留到 M4

### 阶段 6：API（接口层）
12. 新建 `api/reviews.py`：GET /api/reviews/{review_batch_id}
13. 修改 `api/workflows.py`：
    - 新增 POST /api/workflows/{task_id}/resume
    - 修复 _run_workflow：传入 InMemorySaver checkpointer
    - checkpointer 需要在 app.state 中共享（resume 时用同一个 checkpointer）
    - GET /api/workflows/{task_id} 需要返回 waiting_review 状态、interrupt_payload/review_batch_id、suggestion_count
    - workflow 完成或失败时必须更新 task_record.status/current_step/progress/result_payload
14. 修改 `main.py`：注册 reviews router + 初始化 checkpointer

### 阶段 7：测试
15. 编写 M3 集成测试

> 依赖关系：1-4（基础设施）→ 5-6（Tool+Prompt）→ 7（SuggestionAgent）→ 8-9（Review+Action）→ 10-11（Node+Graph）→ 12-14（API）→ 15

## Agent Loop 设计要点

### SuggestionAgent（ReAct loop）

对每条 diagnosis_issue：
1. 判断是规则型还是 LLM 型
   - 规则型（missing_parent → add_node, wide_node → split_subtree, duplicate_name → mark_as_valid）：直接生成，不走 LLM
   - LLM 型（synonym_pollution/semantic_duplicate/bad_parent_child_relation/naming_irregular）：走 Agent Loop
2. LLM 型的 ReAct 循环：
   - [Thought] 分析 issue 类型和目标节点
   - [Action] 调用 get_node_detail 获取节点上下文
   - [Action] 调用 get_node_path 获取路径上下文
   - [Action] 调用 search_similar_nodes 获取相似节点（判断是否重复时）
   - [Thought] 生成建议 JSON
   - [Action] 调用 validate_action 预校验
   - [Observation] 校验通过/失败
   - [Thought] 如果校验失败，调整建议内容
   - [Action] 调用 submit_suggestion 提交建议
3. 超过 max_retry 次仍失败则跳过该 issue

### 参考M2的ContentDiagnosisAgent实现模式
M2 的 ContentDiagnosisAgent 已经实现了完整的 ReAct loop，M3 的 SuggestionAgent 应参考同样的模式：
- 用 `llm.bind_tools(tools)` 绑定工具
- 手写 while 循环处理 tool_calls
- 用 ToolMessage 返回工具执行结果
- submit_suggestion 类似 M2 的 submit_diagnosis

### interrupt/resume 机制
1. `wait_human_review_node` 中调用 `interrupt(payload)` 暂停 graph
2. graph 的 checkpointer 自动保存当前 state
3. `POST /resume` 收到用户决策后，调 `graph.invoke(Command(resume=decision), config=...)`
4. graph 从 interrupt 处恢复，`interrupt()` 的返回值就是用户传入的 decision
5. node 根据 decision 更新 state（approved_ids/rejected_ids/edited_suggestions）
6. M3 恢复后只校验 approved 建议，校验通过后生成报告；执行和新版本保存留到 M4

### checkpointer 配置
```python
# main.py 中初始化
app.state.checkpointer = InMemorySaver()

# workflows.py 的 _run_workflow 中使用
graph = build_taxonomy_graph(
    checkpointer=request.app.state.checkpointer,
    settings=settings,
)

# resume API 中使用同一个 checkpointer
graph = build_taxonomy_graph(
    checkpointer=request.app.state.checkpointer,
    settings=settings,
)
from langgraph.types import Command
graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": thread_id}})
```

## validate_action 校验规则（完整列表）

| 校验项 | 规则 | 失败原因示例 |
|--------|------|-------------|
| action_type | 必须在枚举中 | "delete_node 不在允许列表" |
| issue_id | 必须存在于 diagnosis_issue 表 | "issue_id 999 不存在" |
| target_node_id | 必须存在于 category_node 表（add_node 除外） | "节点 888 不存在" |
| risk_level | 必须是 low/medium/high | "risk_level 必须是枚举值" |
| confidence | 必须在 0-1 之间 | "confidence 1.5 超出范围" |
| clean_synonym | 待删除同义词必须存在于原 syn_list | "AirPods 不在节点 syn_list 中" |
| merge_node | 必须有源节点和目标节点 | "merge_node 缺少 target_node_id" |
| move_node | 不能移动到自身子树下 | "不能将节点移到自身子树下" |

## 规则型建议生成规则

| 问题类型 | 建议动作 | 生成规则 |
|---------|---------|---------|
| missing_parent | add_node | 从 category_group_name 提取缺失父节点名称，建议补齐 |
| deep_level | mark_as_valid | 标记需人工判断，不自动移动 |
| wide_node | split_subtree | 只生成拆分建议，不自动拆分 |
| duplicate_name | mark_as_valid | 默认先标记待判断，避免误合并 |

## 验收标准（全部要满足）
1. 建议由 LLM 生成（非硬编码），包含 action_type/reason/risk_level/confidence
2. LLM 在生成过程中调用了 get_node_detail / validate_action 等 tool（日志可见）
3. 自校验失败的建议被 LLM 自动调整后重新生成（日志可见 ReAct 重试）
4. interrupt 后 GET /api/reviews/{review_batch_id} 返回待审核建议列表
5. POST /api/workflows/{task_id}/resume 能恢复执行
6. validate_action 能拒绝非法动作（如 move 到自身子树下）
7. 规则型建议（missing_parent/deep_level/duplicate_name）不经过 LLM 直接生成
8. operation_log 表记录审核操作
9. M3 完成后不生成新版本，`new_version_id` 为空，报告中标记“待 M4 执行”

## 禁止行为（硬约束，违反即返工）
- 禁止在 generate_suggestion_node 中直接调 LLM 做单次生成——必须走 Agent Loop（分析→查询→生成→自校验→重试）
- 禁止让 LLM 生成建议后直接写库——必须先经过 validate_action tool 自校验
- 禁止跳过 interrupt 直接执行动作——必须等待人工审核
- 禁止在 validate_action_node 中写复杂业务逻辑——校验规则在 action_service 中
- 禁止在 node 函数中拼 prompt——prompt 在 agents/prompts.py 中管理
- 禁止 node 函数超过 30 行
- 禁止在 M3 阶段实现 execute 逻辑——execute 留 M4
- 禁止在 M3 graph 主路径中接入 execute_action_node/save_new_version_node
- 禁止忘记给 ChatOpenAI 加 request_timeout=60
- 禁止使用 langchain-ollama 或 Ollama——用 DeepSeek API + langchain-openai
- 禁止忘记修复 graph 拓扑：content_diagnosis_node 必须连到 generate_suggestion_node，不能直接连 generate_report_node

## 完成后
1. 运行 pytest 确保全部测试通过（含 M1 的 19 个 + M2 的 27 个回归测试）
2. 用 demo Excel（data/sample/产品标准体系_demo.xlsx，188 行）实际跑一遍 workflow
3. 验证 workflow 到达 waiting_review 状态时能 GET /api/reviews/{review_batch_id} 看到建议列表
4. 验证 POST /api/workflows/{task_id}/resume 能恢复执行
5. 验证 resume 后进入 validate_action_node，校验完成后进入 generate_report_node，不生成新版本
6. 检查日志中有 SuggestionAgent 的 Thought-Action-Observation 链
7. 输出代码摘要：列出新建/修改的文件和每个文件的核心函数
```
