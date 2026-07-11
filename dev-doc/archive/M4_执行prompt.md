# M4 里程碑执行 Prompt

> **历史执行材料（ARCHIVED）**：不得直接作为当前开发 prompt 使用。当前事实和路线见 `CURRENT_IMPLEMENTATION.md`、`ROADMAP.md`。

> 用途：先确认 M3 校验结果，再把“复制以下内容作为 Prompt”代码块整体复制给 AI 编程助手，启动 M4 代码实现。
> 项目路径：/Users/flflfl/Documents/code/SystemMaintenanceAgent
> 技术方案：FastAPI + LangGraph + SQLite + Qdrant；LLM 用 DeepSeek API（OpenAI 兼容），Embedding 用通义千问 DashScope（OpenAI 兼容）。

---

## 一、M3 校验结论

当前 M3 已基本完成，可以进入 M4 开发。

已通过测试：

```bash
.venv/bin/python -m pytest backend/tests/test_m3_suggestion_review.py -q
# 8 passed

.venv/bin/python -m pytest backend/tests/test_langgraph_workflow.py backend/tests/test_m1_workflow.py backend/tests/test_m2_vector_content_agent.py -q
# 12 passed, 1 warning
```

M3 已具备：

1. `SuggestionAgent` 生成结构化维护建议。
2. 规则型建议直接生成，LLM 型建议支持 tool loop。
3. `adjustment_suggestion.review_batch_id` 已入库。
4. `ReviewService` 支持 approve/reject/edit/batch approve，并写 `operation_log`。
5. `ActionService.validate_approved_actions()` 已能校验 approved 建议。
6. `wait_human_review_node` 已使用 interrupt，并写入 waiting_review 状态。
7. `POST /api/workflows/{task_id}/resume` 已存在。
8. M3 graph 不会从 `validate_action_node` 进入 `execute_action_node`。

进入 M4 前必须注意的现状：

1. `execute_action_node` 和 `save_new_version_node` 仍是占位：不会真实修改节点，也不会保存新版本。
2. `ActionService` 目前只有 `validate_approved_actions()`，没有 `execute_actions()`。
3. `VersionService` 目前只有初始版本创建和查询，没有 `save_new_version()`、diff、rollback。
4. `api/versions.py` 仍是 501 placeholder。
5. `tools/export_tools.py` 仍是空占位。
6. `ReportService` 仍主要是模板报告，且报告中 M3 建议摘要还不完整。
7. `graph.py` 虽然注册了 M4 节点，但 M3 成功分支目前刻意不连过去；M4 需要接入真实执行链路。

---

## 二、M4 做什么

M4 目标：把 M3 已审核通过的结构化建议转换成真实节点变更，并生成新版本、版本差异、操作日志、导出文件和增强报告。

M4 主链路：

```text
validate_action_node
  -> execute_action_node
  -> save_new_version_node
  -> generate_report_node
```

M4 业务闭环：

```text
approved adjustment_suggestion
  -> validate again
  -> copy current version nodes in memory
  -> apply deterministic actions
  -> recompute parent/level/path/is_leaf
  -> create taxonomy_version v1.1/v1.2/...
  -> bulk insert new category_node snapshot
  -> mark suggestions executed/failed
  -> write operation_log
  -> expose versions/diff/export/report APIs
```

M4 不做：

1. 不执行 `pending`、`rejected`、`edited` 但未 approved 的建议。
2. 不覆盖原始版本节点。
3. 不直接修改上传 Excel。
4. `split_subtree` MVP 只记录方案，不自动拆分节点。
5. 不让 LLM 直接执行动作；动作执行是确定性 service。

---

## 三、复制以下内容作为 Prompt

```text
你是一个资深 Python 后端工程师，现在要在现有项目上实现 M4 里程碑：动作执行 + 版本管理 + 报告/导出增强。

## 项目背景

项目名：产品标准体系维护智能体（FastAPI + LangGraph + LangChain + SQLite + Qdrant）。

- M1 已完成：Excel 上传、解析、建树、v1.0 保存、结构诊断、模板报告。
- M2 已完成：Qdrant 向量索引、诊断规划、内容诊断 ReAct Agent。
- M3 已完成：SuggestionAgent 生成结构化建议、人工审核 interrupt/resume、approved 动作校验。
- M4 目标：只执行 approved 建议，基于当前版本生成新 taxonomy_version 和完整 category_node 快照，提供版本 diff/export/report 能力。

## 必读文档

1. dev-doc/00_开发里程碑索引.md — 读 §7 M4 章节。
2. dev-doc/07_动作执行与版本管理开发设计.md — 完整阅读。
3. dev-doc/08_导出与诊断报告开发设计.md — 完整阅读。
4. dev-doc/10_LangGraph智能体工作流开发设计.md — 重点读 execute_action_node、save_new_version_node、generate_report_node 和 Graph 构建。
5. backend/app/services/action_service.py — 当前只有 validate_approved_actions，需要补 execute_actions。
6. backend/app/services/version_service.py — 当前只有 create_initial_version/get_version，需要补 save_new_version/diff/rollback。
7. backend/app/repositories/taxonomy_repo.py — 当前有 list_nodes/bulk_insert_nodes/get_node_detail/is_descendant 等，可复用。
8. backend/app/repositories/suggestion_repo.py — 读取 approved 建议、更新 suggestion 状态。
9. backend/app/repositories/operation_log_repo.py — 写执行日志。
10. backend/app/agents/graph.py — 当前 M3 成功分支不进入 execute，需要在 M4 改路由。
11. backend/app/agents/nodes.py — execute_action_node/save_new_version_node 仍是占位，需要替换为真实 service 调用。
12. backend/app/api/versions.py — 当前是 501 placeholder，需要实现版本 API。
13. backend/app/tools/export_tools.py — 当前为空，需要实现 Excel 导出工具。

## 当前代码现状

### M3 已完成能力

- `SuggestionAgent(settings).run(version_id)` 可生成 `review_batch_id` 和 pending suggestions。
- `ReviewService` 可将建议状态改为 approved/rejected/edited。
- `ActionService.validate_approved_actions(review_batch_id)` 可校验 approved 建议。
- `validate_action_node` 校验通过后当前进入 `generate_report_node`，这是 M3 收口设计。

### M4 必须替换的占位

`backend/app/agents/nodes.py` 中：

```python
def execute_action_node(state):
    _require_current_version_id(state)
    _require_review_batch_id(state)
    return _complete_step(... executed_action_count=state.approved_action_count)


def save_new_version_node(state):
    current_version_id = _require_current_version_id(state)
    return _complete_step(... new_version_id=current_version_id + 1, version_no="v1.1")
```

这两个节点必须改成真实 service 调用，禁止继续用 `current_version_id + 1` 伪造新版本。

`backend/app/agents/graph.py` 中：

```python
def route_after_validate(state):
    if state.error_code:
        return "generate_report_node"
    return "generate_report_node"
```

M4 需要改成：

```python
def route_after_validate(state):
    if state.error_code:
        return "generate_report_node"  # 或回到 wait_human_review_node，看现有错误处理策略
    return "execute_action_node"
```

并接入：

```python
execute_action_node -> save_new_version_node -> generate_report_node
```

## 文件清单

### 修改文件

1. `backend/app/services/action_service.py`
   - 新增 `execute_actions(version_id: int, review_batch_id: str, operator: str = "local_user") -> ExecuteActionsResult`
   - 只执行 approved 建议。
   - 执行前重新调用 validate。
   - 在内存节点集合上应用动作。
   - 返回执行后的节点集合、executed_count、failed_count、action_batch_id 或 execution summary。

2. `backend/app/services/version_service.py`
   - 新增 `save_new_version(base_version_id: int, review_batch_id: str, nodes: list[TaxonomyNodeRecord] | None = None) -> SaveVersionResult`
   - 新增 `get_version_diff(from_id: int, to_id: int) -> VersionDiff`
   - 新增 `rollback_version(version_id: int, operator: str = "local_user") -> SaveVersionResult`
   - 新版本号按同 file_id 下最大版本递增：v1.0 -> v1.1 -> v1.2。

3. `backend/app/repositories/version_repo.py`
   - 新增 `list_versions(file_id: int | None = None)`。
   - 新增查询同 file_id 最大 version_no 的方法。
   - 复用 `create_version()`。

4. `backend/app/repositories/taxonomy_repo.py`
   - 如需要，新增 `copy_nodes_as_records(version_id)` 或 `list_node_records(version_id)`。
   - 如需要，新增同级重名检查、category_id 存在检查、批量写入快照复用方法。

5. `backend/app/repositories/suggestion_repo.py`
   - 如当前没有，新增批量更新 suggestion 状态为 `executed` / `failed`。
   - 确保可以按 review_batch_id + status='approved' 查询。

6. `backend/app/schemas/version.py`
   - 新增 `SaveVersionResult`
   - 新增 `ExecuteActionsResult`
   - 新增 `VersionDiff`
   - 新增 `ExportResult`
   - 如更合适，也可把 execute 相关 schema 放到 `schemas/suggestion.py`。

7. `backend/app/tools/export_tools.py`
   - 实现 `export_excel(version_id: int) -> str`。
   - 导出字段：category_id, category_name, category_group_id, category_pids, category_group_name, syn_list。
   - 输出到 `data/exports/{version_no}_taxonomy.xlsx`。

8. `backend/app/api/versions.py`
   - 实现 `GET /api/versions?file_id=1`
   - 实现 `GET /api/versions/{version_id}`
   - 实现 `GET /api/versions/{version_id}/diff?target_version_id=2`
   - 实现 `POST /api/versions/{version_id}/rollback`
   - 实现 `GET /api/versions/{version_id}/export`

9. `backend/app/services/report_service.py`
   - 增强报告：加入 M3 suggestions、审核结果、M4 执行结果、版本变更、质量评分变化。
   - 可选：有 DeepSeek key 时使用 LLM 组织报告摘要；无 key 时保留模板报告。
   - LLM 报告只组织语言，不参与动作执行。

10. `backend/app/agents/nodes.py`
    - `execute_action_node` 调 `ActionService.execute_actions()`。
    - `save_new_version_node` 调 `VersionService.save_new_version()`。
    - `generate_report_node` 对新版本生成报告。
    - node 继续保持 thin，不写动作执行细节。

11. `backend/app/agents/graph.py`
    - `route_after_validate` 成功分支改到 `execute_action_node`。
    - 保留 M3 跳过逻辑只用于 `enable_suggestion_review=False` 或无 approved actions 场景。
    - 确保完整 M4 链路为：validate -> execute -> save_new_version -> report。

12. `backend/app/agents/checkpoints.py`（可选但推荐）
    - 如果 LangGraph 当前版本支持 SQLite checkpointer，封装 SQLite checkpointer factory。
    - 如果当前环境难以接官方 SQLite checkpointer，至少保留 `InMemorySaver` 并在文档/测试中标注 SQLite checkpointer 延后；不要伪装成已持久化恢复。

## 动作执行规则

### 通用规则

1. 只读取 `status='approved'` 的建议。
2. 执行前重新校验所有 approved 建议。
3. 任一必需校验失败时，不生成新版本。
4. 所有节点变更先在内存集合上完成，最后一次性保存新版本快照。
5. 原版本 `category_node` 永远不修改。
6. 执行完成后更新建议状态为 `executed`；失败建议标记为 `failed` 并保留原因。
7. 每次执行写 `operation_log`。

### 支持的 action_type

1. `clean_synonym`
   - 从目标节点 `syn_list` 删除 `action_payload.synonyms_to_remove`。
   - 删除词必须存在于原 syn_list。

2. `rename_node`
   - 将目标节点名称改为 `new_name` 或 `action_payload.new_name`。
   - 新名称不能为空。
   - 同级下不能重名。
   - 需要重算该节点及子孙节点 path_names。

3. `move_node`
   - 将目标节点 parent_id 改为 `new_parent_id` 或 `action_payload.new_parent_id`。
   - 目标父节点必须存在或为根。
   - 不能移动到自身或自身子树下。
   - 需要重算该节点及子孙节点 level/path_ids/path_names。

4. `mark_as_valid`
   - 不修改节点。
   - 将关联 `diagnosis_issue.status` 或 suggestion 状态标记为已处理/已确认即可。

5. `add_node`
   - MVP 可支持：新增一个中间节点。
   - 如果信息不足，可以只记录 failed reason，不生成半成品版本。
   - 若实现，必须生成不冲突的 category_id，并重算受影响子树。

6. `merge_node`
   - MVP 可先不自动合并复杂子树。
   - 如果 action_payload 缺源/目标信息，标记 failed。
   - 如实现，只允许明确 source_node_id/target_node_id 的同级或同路径兼容合并。

7. `split_subtree`
   - M4 MVP 不自动拆分，只记录方案，不修改节点。

## 版本保存规则

1. 从 `base_version_id` 读取完整节点快照。
2. 应用执行后的节点集合。
3. 重新计算所有节点：
   - `parent_id`
   - `level`
   - `path_ids`
   - `path_names`
   - `is_leaf`
4. 创建新 `taxonomy_version`，version_no 递增。
5. 批量写入新版本 `category_node`。
6. 计算并写入 `quality_score`。
7. 返回 `new_version_id`、`new_version_no`、`executed_count`、`failed_count`。

## 版本 diff 规则

`get_version_diff(from_id, to_id)` 应比较两个完整版本快照，输出：

```python
class VersionDiff(BaseModel):
    from_version_id: int
    to_version_id: int
    added: list[dict]
    deleted: list[dict]
    renamed: list[dict]
    moved: list[dict]
    synonym_changed: list[dict]
```

比较键优先使用 `category_id`。

## Graph 接入要求

M4 完成后主路径应为：

```text
content_diagnosis_node
  -> generate_suggestion_node
  -> wait_human_review_node
  -> validate_action_node
  -> execute_action_node
  -> save_new_version_node
  -> generate_report_node
```

拒绝或无 approved actions 时仍可直接进入 report：

```text
wait_human_review_node -> generate_report_node
```

## 测试要求

新增测试文件建议：

1. `backend/tests/test_m4_action_execution.py`
2. `backend/tests/test_m4_version_service.py`
3. `backend/tests/test_m4_versions_api.py`
4. `backend/tests/test_m4_export_report.py`

必须覆盖：

1. `clean_synonym` 生成新版本，原版本不变。
2. `rename_node` 后 path_names 重算。
3. `move_node` 到自身子树被拒绝。
4. 未 approved 建议不会执行。
5. 任一动作校验失败不生成新版本。
6. `GET /api/versions?file_id=1` 返回版本列表。
7. `GET /api/versions/{id}/diff?target_version_id={new_id}` 返回 synonym_changed/renamed/moved。
8. `GET /api/versions/{id}/export` 生成 Excel。
9. M4 graph 中 `validate_action_node -> execute_action_node -> save_new_version_node -> generate_report_node` 链路存在。
10. M1/M2/M3 回归测试继续通过。

回归命令：

```bash
.venv/bin/python -m pytest backend/tests/test_m1_workflow.py backend/tests/test_langgraph_workflow.py backend/tests/test_m2_vector_content_agent.py backend/tests/test_m3_suggestion_review.py -q
```

M4 测试命令：

```bash
.venv/bin/python -m pytest backend/tests/test_m4_action_execution.py backend/tests/test_m4_version_service.py backend/tests/test_m4_versions_api.py backend/tests/test_m4_export_report.py -q
```

## 禁止行为

- 禁止执行非 approved 建议。
- 禁止直接 UPDATE 原版本 category_node 来完成变更。
- 禁止用 `current_version_id + 1` 伪造新版本 ID。
- 禁止只改 suggestion 状态但不保存新 category_node 快照。
- 禁止动作执行过程中调用 LLM 决定怎么改节点。
- 禁止 action 失败后生成半成品版本。
- 禁止跳过 operation_log。
- 禁止 node 函数写复杂动作执行逻辑。
- 禁止把 `split_subtree` 复杂拆分硬做成不可靠自动执行；MVP 只记录方案。

## 完成后

1. 运行 M1-M3 回归测试。
2. 运行新增 M4 测试。
3. 用至少一条 `clean_synonym` approved 建议跑完整 workflow，确认生成 `v1.1`。
4. 验证 `v1.0` 节点未变，`v1.1` 节点已变。
5. 验证 diff、export、report API 可用。
6. 输出代码摘要：列出新建/修改文件和核心函数。
```
