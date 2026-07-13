# PRD-01 审核多轮与版本续跑（循环节点方案）

> 状态：PLANNED  
> 路线归属：R2 安全变更与版本闭环  
> 注意：本文描述目标需求，不代表双循环和版本续跑已经实现。

- **文档编号**：PRD-01
- **名称**：审核多轮与版本续跑（双循环节点）
- **状态**：待评审
- **作者**：调度达（AgentsOrchestrator）
- **日期**：2026-07-09
- **历史关联方案**：[审核多轮与版本续跑修复方案](../99_历史归档/历史方案/审核多轮与版本续跑修复方案.md)、[功能增强脑暴与优先级](../99_历史归档/历史方案/功能增强脑暴与优先级.md)

---

## 1. 背景与问题

当前工作流是「导入 → 诊断 → **一次**审核 → 出版本 → 报告 → 结束」的单向、一次性原子管道。经代码核对，存在三处硬限制：

1. **审核只能一次**：`graph.py` 整条链路仅 `wait_human_review_node` 一个 `interrupt()`（nodes.py ~250），恢复后一路 `validate → execute → save_new_version → report → END`，无回路；`resume_workflow` 仅在 `task.status == "waiting_review"` 可用（workflows.py:161/193），跑完即终态，无法二次 resume。
2. **重跑从原始版本重来**：`POST /api/workflows/taxonomy/start` 只收 `file_id`（workflows.py:23-24）；`create_initial_version` 复用已存在的 `v1.0`（version_service.py:18-29），新一轮 `current_version_id` 永远是原始 v1.0；`save_new_version_node` 也以 v1.0 为 base（nodes.py:301-325）。**后果**：第二轮全量重诊断（含内容诊断再烧 50 候选 token），把已修问题重新发现；v2 不被复用，首轮修复若未再批准则丢失。
3. **不会自动重复检测**：`save_new_version → report → END`，无循环/定时/事件钩子。

根因：版本被建模为*终态产物*而非*可迭代状态*。

---

## 2. 目标与范围

### 目标
- G1：支持**单 run 内多次审核**（一次审不完，批准一部分→执行→再审核剩余），封顶防失控。
- G2：支持**跨轮 from_version 续跑**（几天后从某版本继续，不复用原始 v1.0，不重复全量诊断）。
- G3：修正版本链 base bug，使版本真正连续（v1.0 → v1.1 → v1.2 …）。
- G4：支持**跨轮 deferred 待办**（暂缓的建议带入下一轮，标注"此前您暂缓"）。

### 成功指标
- 同一 run 内可连续审核 ≥2 次且每次均需人工 resume。
- `start` 带 `version_id` 时，新一轮 `current_version_id` = 指定版本，内容诊断候选集降为增量/deferred（token 消耗较全量下降 ≥70%）。
- 版本链连续：v1.1.base_version_id = v1.0，v1.2.base_version_id = v1.1。

### 范围内 / 外
- **内**：循环 A（单 run 多轮）、循环 B（from_version 续跑）、base bug 修正、deferred 状态、State/节点/API/前端最小改动。
- **外（本 PRD 不做）**：自动定时巡检（A1，见 PRD 后续）、多角色审核（B1）、语义去重（A3）。

---

## 3. 用户角色与场景

- **维护员（单人）**：
  - 场景 1：本轮诊断出 20 条建议，先批准 8 条执行，剩余 12 条想"下一轮再决定" → 循环 A 实现"先执行一部分、留待继续审核"。
  - 场景 2：上周修完 v1.1，这周发现新类目问题 → 从 v1.1「续跑」，只诊断变更/deferred，不重跑原始 v1.0。
- **审计/主管**：要求看到完整版本链与每版来源（base_version_id）。

---

## 4. 功能需求（FR）

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-1 | `start` 请求新增可选 `version_id` 与 `mode`（`from_file`/`from_version`）；`from_version` 跳过 parse+save_initial，直接 `load_version` 作 `current_version_id` | P0 |
| FR-2 | 新增可重入 `bootstrap_node`：按 `mode` 分支决定入口（parse vs load） | P0 |
| FR-3 | 新增 `route_after_round` 判定：若 `pending_remaining and review_iteration < MAX_ROUNDS(3)` → 回环 `wait_human_review_node`（每次回环重设 `task.status=waiting_review`） | P0 |
| FR-4 | `save_new_version_node` 以 `get_latest_for_file(file_id)` 为 base（修正 nodes.py:310 的 base bug，与 review_service.py:120 一致） | P0 |
| FR-5 | 建议状态机新增 `deferred`（区别于 `rejected`）；`generate_suggestion_node` 合并上一轮 deferred 候选并标注"此前您暂缓的建议" | P1 |
| FR-6 | `start`/`resume` 在 `task.status != waiting_review` 时，若 `version_id` 合法仍可发起新一轮（解除"跑完即终态"限制） | P0 |
| FR-7 | 新增 `GET /api/versions?file_id=` 列出版本链（含 version_no、base_version_id、created_time）供前端「从此版本续跑」下拉 | P1 |

---

## 5. 现有资产与改动点

- **复用**：checkpointer（checkpoints.py，SQLite 常驻连接，支持 interrupt/resume）、`get_latest_for_file`（version_service.py）、`resume_workflow` 机制（workflows.py:161）、建议状态机（suggestion schema）。
- **改动**：
  - `backend/app/agents/states.py`：`TaxonomyGraphState` 新增 `session_id`、`round_index`、`mode`、`review_iteration`、`pending`、`deferred`、`base_version_id`。
  - `backend/app/agents/graph.py`：新增 `bootstrap_node`、`route_after_round`；`wait_human_review_node` 回边接 `route_after_round`；`start` 入口接 `bootstrap_node`。
  - `backend/app/agents/nodes.py`：`save_new_version_node` 修正 base；`generate_suggestion_node` 合并 deferred。
  - `backend/app/api/workflows.py`：`StartWorkflowRequest` 加 `version_id?`、`mode?`；新增 `GET /api/versions`。
  - 数据表：`taxonomy_version` 加 `base_version_id` 列；`adjustment_suggestion` 状态枚举加 `deferred`。

---

## 6. 接口设计（草案）

```http
POST /api/workflows/taxonomy/start
Content-Type: application/json

{
  "file_id": 12,
  "version_id": 37,        // 可选；省略则 mode=from_file
  "mode": "from_version"   // from_file | from_version
}
```

```http
GET /api/versions?file_id=12
→ [
  {"id":35,"version_no":"v1.0","base_version_id":null,"created_time":"..."},
  {"id":37,"version_no":"v1.1","base_version_id":35,"created_time":"..."}
]
```

---

## 7. 前端交互（最小可用）

- 版本列表页新增「从此版本续跑」按钮（携带 `version_id` 调 `start`，`mode=from_version`）。
- 审核页在「执行已批准」后，若仍有 pending，出现「继续审核（剩余 N 条）」入口，点击即 `resume` 再次进入中断。
- 版本选择器展示版本链与来源箭头（v1.0 → v1.1）。

---

## 8. 验收标准

- AC-1：单 run 内连续审核 2 次均成功，且每次均需人工 resume（checkpointer 产生新 checkpoint）。
- AC-2：`start(mode=from_version, version_id=v1.1)` 后，新一轮 `current_version_id == 37`，内容诊断候选集为增量/deferred，不重复全量。
- AC-3：v1.2.base_version_id == v1.1.id（base bug 修正生效）。
- AC-4：deferred 建议在下一轮 `generate_suggestion_node` 输出中出现，且标注"此前您暂缓"。
- AC-5：回归测试 `backend/tests` 全绿，且不得低于开工时记录的测试基线（2026-07-11 为 56 passed）。

---

## 9. 依赖与里程碑

- **依赖**：无外部 blocker；为 PRD-03（版本 Diff）的前置基础。
- **里程碑（建议 PR 拆分）**：
  - PR1-止血：FR-1/2/4/6 + base bug 修正 + State 字段 + `GET /api/versions`。
  - PR2：FR-3 循环 A + 前端「继续审核」。
  - PR3：FR-5 deferred 跨轮 + 增量诊断。

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| 循环 A 失控（用户无限回环） | `review_iteration < 3` 硬封顶；每次回环需人工 resume，无无人自转 |
| from_version 跳过 parse 致 state 缺字段 | bootstrap_node 显式 `load_version` 填充 nodes/overview 到 state |
| 版本链断（base 仍指向 v1.0） | FR-4 统一以 `get_latest_for_file` 为 base，并加 AC-3 校验 |

---

## 11. 非功能性要求

- 续跑新一轮不应触发全量内容诊断重跑（控制 DeepSeek/DashScope token 成本）。
- 所有版本写操作保持原 Excel 不变，新版本为独立快照（既有约束）。
- 回归：每次 PR 合并前跑 `pytest backend/tests` 与 `npm run test:contract`。
