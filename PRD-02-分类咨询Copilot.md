# PRD-02 分类咨询 Copilot（C1）

- **文档编号**：PRD-02
- **名称**：分类咨询 Copilot（基于 Qdrant 召回 + LLM 解释）
- **状态**：待评审
- **作者**：调度达（AgentsOrchestrator）
- **日期**：2026-07-09
- **关联方案**：`功能增强脑暴与优先级.md`（C1）、`backend/app/vectorstores/qdrant_store.py`、`backend/app/services/vector_index_service.py`

---

## 1. 背景与问题

当前系统把 Qdrant 向量索引、LangGraph agent loop 只用在「诊断 + 建议」内部，用户**感知不到 AI 的存在**；`chat.py` 的 `POST /chat`、`GET /chat/history` 仍是 `not_implemented`（501 占位）。分类体系最大的日常痛点是**「这个新商品/新类目该归到哪」**，而这正是向量召回最擅长的场景。把已有的 Qdrant 索引产品化为一个面向用户的咨询助手，是让 AI 能力"可见、可交互、不单调"的最低成本高价值落点。

---

## 2. 目标与范围

### 目标
- G1：用户用自然语言问"XX 商品该分到哪个类目 / 跟哪些类目相近"，系统基于**当前版本向量索引**召回候选并给出可解释答案。
- G2：答案**带引用**（命中的 category_id、路径、相似度分数），可一键跳转分类树查看。
- G3：支持流式回答（SSE），体验接近真实助手。
- G4：复用现有 embedding（DashScope）与 LLM（DeepSeek ChatOpenAI）通道，不引入新模型。

### 成功指标
- 对 demo 数据（data/sample/产品标准体系_demo.xlsx，4 根类目）的归类咨询，Top-3 召回命中正确类目率 ≥ 90%。
- 回答中每条结论至少附 1 个可点击引用节点。
- P95 首字延迟 < 3s（取决于 LLM 流式）。

### 范围内 / 外
- **内**：`/chat` 流式接口、检索增强生成（RAG）、引用、历史。
- **外**：不替代诊断/建议主流程；不做多轮"自由 agent 互调"；不做规则录入（C2 另案）。

---

## 3. 用户角色与场景

- **业务录入员**：拿到一个新产品"无线降噪耳机"，不确定归「电子产品/音频设备」还是「电子产品/穿戴设备」→ 问 Copilot，得到路径建议 + 相似类目列表。
- **分类架构师**：想确认"智能音箱"是否已有近义类目，避免新建重复 → 问"有没有跟智能音箱相似的类目"，看 Top-K 相似节点。
- **新同事**：不熟悉体系，用对话式探索"母婴用品下面有哪些二级类目"。

---

## 4. 功能需求（FR）

| 编号 | 需求 | 优先级 |
|------|------|--------|
| FR-1 | `POST /api/chat` 由占位改为 RAG 实现：接收 `{version_id?, message, session_id?, history?}`，流式 SSE 返回 | P0 |
| FR-2 | 检索：调 `QdrantStore.search_similar(version_id, query, top_k=8)` 召回候选节点 | P0 |
| FR-3 | 生成：用 DeepSeek `ChatOpenAI` 基于召回上下文 + 用户问题生成解释，**必须输出结构化引用**（命中的 category_id 列表） | P0 |
| FR-4 | 引用回传：响应中携带 `citations: [{category_id, category_name, path_names, score}]`，前端可点击跳转树 | P0 |
| FR-5 | `GET /api/chat/history?session_id=` 返回会话历史（新增 `chat_session`/`chat_message` 表或复用 operation_log） | P1 |
| FR-6 | 若 `version_id` 未索引，自动触发 `VectorIndexService.index_version(version_id)`（或返回"该版本尚未建索引"提示） | P1 |
| FR-7 | 支持"相似类目"专项问法：检测意图后直接返回 Top-K 相似节点列表（不强制走 LLM 解释） | P2 |

---

## 5. 现有资产与改动点

- **复用（已验证存在）**：
  - `backend/app/vectorstores/qdrant_store.py::search_similar(version_id, node_text, top_k)` —— 返回含 `category_id/category_name/parent_id/level/path_names/syn_list/is_leaf/score` 的 payload。
  - `backend/app/services/vector_index_service.py` —— `index_version(version_id)` 已建索引；节点文本 = 名称+路径+同义词。
  - embedding（`OpenAIEmbeddings` + DashScope）、LLM（`ChatOpenAI` + DeepSeek，`DEEPSEEK_MODEL=deepseek-chat`，`request_timeout=60`）。
  - 流式事件封装可参考 `backend/app/agents/events.py` 的 SSE 格式（`format_sse`）。
- **新增**：
  - `backend/app/services/copilot_service.py`：`retrieve(query, version_id, top_k)` + `answer(message, context, history)`（LangChain `RunnableLambda`/直接 `ChatOpenAI.invoke`，`stream()` 输出）。
  - `backend/app/api/chat.py`：替换占位，实现流式端点。
  - 前端 `frontend/src/api/chat.ts` 新封装 + `frontend/src/views/CopilotView.vue`（对话窗 + 引用卡片 + 跳树）。

---

## 6. 接口设计（草案）

```http
POST /api/chat
Content-Type: application/json
Accept: text/event-stream

{
  "version_id": 37,
  "message": "无线降噪耳机应该归到哪个类目？",
  "session_id": "sess_abc",
  "history": [{"role":"user","content":"..."}]   // 可选
}
```

SSE 事件（复用 events.py 风格）：
```
event: token
data: {"delta": "建议归到"}

event: citation
data: {"category_id": 1042, "category_name": "音频设备", "path_names": "电子产品/音频设备", "score": 0.91}

event: done
data: {"session_id": "sess_abc", "finish_reason": "stop"}
```

```http
GET /api/chat/history?session_id=sess_abc
→ [{"role":"user","content":"..."},{"role":"assistant","content":"...","citations":[...]}]
```

---

## 7. 前端交互

- 新增「分类咨询」导航入口 → `CopilotView`：左侧对话流，右侧"引用类目"卡片（点击跳转 `TaxonomyTreeView` 并高亮节点）。
- 输入框支持选择"基于哪个版本"（默认最新版）。
- 顶部提示当前所用版本是否已建索引；未建则显示"正在建索引…"进度（复用 TaskStatusBar 风格）。

---

## 8. 验收标准

- AC-1：`POST /chat` 返回 200 流式事件，包含 `token`/`citation`/`done`。
- AC-2：对 demo 数据归类问题，Top-3 召回正确率 ≥ 90%；每条结论附 ≥1 引用。
- AC-3：未索引版本自动建索引或明确提示，不 500。
- AC-4：`GET /chat/history` 返回对应会话历史。
- AC-5：前端可点击引用跳转树并高亮。

---

## 9. 依赖与里程碑

- **依赖**：Qdrant 已建索引（M2 已完成）；LLM/Embedding 通道已通。与 PRD-01 无强耦合，可**并行**开发。
- **里程碑**：
  - PR1：FR-1/2/3/4 基础 RAG + 引用（替换占位）。
  - PR2：FR-5 历史 + FR-6 自动建索引 + 前端 CopilotView。
  - PR3：FR-7 相似类目专项意图。

---

## 10. 风险与对策

| 风险 | 对策 |
|------|------|
| 召回版本与用户"当前查看版本"不一致 | 前端显式传 `version_id`，默认最新版；响应回显所用版本 |
| LLM 编造类目（幻觉） | 强约束 prompt："只能基于下方召回节点回答，不得发明类目"；引用强制来自检索结果 |
| 未索引版本 500 | FR-6 兜底：自动建索引或返回友好提示 |
| token 成本 | 仅对最终 query 做 1 次 embed + 单次 LLM 调用，不跑 ReAct 循环 |

---

## 11. 非功能性要求

- 流式首字延迟 < 3s（P95）。
- 引用必须可溯源（category_id 来自 Qdrant payload，非 LLM 生成）。
- 不修改原 Excel / 不触发诊断主流程；纯只读咨询。
