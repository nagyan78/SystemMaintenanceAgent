# 演示操作手册

> 适用：从零开始，克隆仓库 → 启动服务 → 上传文件 → 运行诊断 → 查看结果。
> 当前演示功能：M1 确定性闭环 + M2 内容诊断智能体（DeepSeek + 千问 + Qdrant）+ M3 建议生成智能体与人工审核闭环。

---

## 前置条件

| 依赖 | 要求 | 验证命令 |
|------|------|---------|
| Python | ≥ 3.10 | `python3 --version` |
| Git | 任意版本 | `git --version` |
| Docker | 已安装并运行 | `docker info \| grep "Server Version"` |
| DeepSeek API key | 已注册 | https://platform.deepseek.com/ |
| 千问 API key | 已注册 | https://dashscope.console.aliyun.com/ |

> 如果没有 API key：注册免费即可获取，DeepSeek 和千问都有免费额度。

---

## 第 1 步：克隆仓库 + 安装依赖

```bash
git clone <仓库地址> standard-taxonomy-agent
cd standard-taxonomy-agent

# 创建虚拟环境
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

---

## 第 2 步：启动 Qdrant（向量数据库）

```bash
mkdir -p data/qdrant

docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/data/qdrant:/qdrant/storage \
  qdrant/qdrant
```

验证 Qdrant 已启动：

```bash
curl http://localhost:6333/
# 应返回: {"title":"qdrant","version":"..."}
```

> 如果端口被占用，改 `-p 16333:6333`，同步修改下面第 3 步的 `.env`。

---

## 第 3 步：配置 API Key

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 API 密钥：

```bash
DEEPSEEK_API_KEY=sk-你的DeepSeek密钥
DEEPSEEK_MODEL=deepseek-chat

DASHSCOPE_API_KEY=sk-你的千问密钥
EMBEDDING_MODEL=text-embedding-v2

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
```

> `.env` 已在 `.gitignore` 中，不会被提交到 Git。

---

## 第 4 步：启动后端

```bash
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后看到：
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

验证健康检查：

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","app":"standard-taxonomy-agent"}
```

---

## 第 5 步：上传样例 Excel

```bash
curl -F "file=@data/sample/产品标准体系.xlsx" \
  http://127.0.0.1:8000/api/files/upload
```

成功返回示例：

```json
{
  "file_id": 1,
  "task_id": "import_excel_20260705_000001",
  "file_name": "产品标准体系.xlsx",
  "row_count": 21090,
  "column_count": 6,
  "columns": ["category_id","category_name","category_group_id","category_pids","category_group_name","syn_list"],
  "status": "uploaded"
}
```

**记住返回的 `file_id`**，下一步要用。

---

## 第 6 步：启动诊断工作流

```bash
# 用上一步返回的 file_id 替换 1
curl -X POST http://127.0.0.1:8000/api/workflows/taxonomy/start \
  -H "Content-Type: application/json" \
  -d '{"file_id": 1}'
```

成功返回：

```json
{
  "task_id": "import_20260705_000001",
  "workflow_id": "taxonomy_workflow_1_20260705_000001",
  "thread_id": "taxonomy_workflow:taxonomy_workflow_1_20260705_000001",
  "status": "running",
  "current_step": "parse_excel",
  "progress": 0
}
```

**记住返回的 `task_id`**，下一步查询状态用。

后台会自动执行以下流程（约 1-3 分钟，取决于 API 响应速度）：

```
parse_excel → build_tree → save_initial_version
  → index_vector（千问 embedding 写入 Qdrant，21090 个节点）
  → structure_diagnosis（规则检测：父节点缺失/层级过深/节点过宽/重复名称）
  → diagnosis_planning（DeepSeek 规划诊断范围）
  → content_diagnosis（ReAct Agent Loop：召回→LLM判断→补充查询→再判断）
  → generate_suggestion（规则建议 + LLM ReAct 建议生成 + validate_action 自校验）
  → wait_human_review（LangGraph interrupt，等待人工审核）
```

M3 会在人工审核节点暂停，不会执行动作、不会生成新版本、不会导出 Excel。

---

## 第 7 步：查询工作流状态

等待 1-3 分钟后，查询结果：

```bash
curl http://127.0.0.1:8000/api/workflows/<你的task_id>
```

当 `status` 变为 `"waiting_review"` 时表示 M3 建议已生成，正在等待人工审核：

```json
{
  "task_id": "workflow_xxxxxxxxxxxx",
  "status": "waiting_review",
  "current_step": "human_review",
  "progress": 80,
  "file_id": 1,
  "current_version_id": 1,
  "version_no": "v1.0",
  "node_count": 21090,
  "structure_issue_count": 195,
  "suggestion_count": 192,
  "review_batch_id": "review_xxxxxxxxxxxx",
  "report_path": null
}
```

**记住返回的 `review_batch_id`**，下一步查看待审核建议用。

> 如果 `status` 还是 `"running"`，等 30 秒再查一次。

---

## 第 8 步：查看待审核建议

```bash
curl http://127.0.0.1:8000/api/reviews/<你的review_batch_id>
```

返回示例：

```json
{
  "review_batch_id": "review_xxxxxxxxxxxx",
  "suggestion_count": 192,
  "suggestions": [
    {
      "id": 1,
      "issue_id": 1,
      "version_id": 1,
      "action_type": "add_node",
      "target_node_id": null,
      "target_node_name": "...",
      "action_payload": {"source": "missing_parent"},
      "reason": "...",
      "suggestion": "建议补齐缺失父节点或中间分类，新增前需人工确认名称与位置。",
      "risk_level": "medium",
      "confidence": 0.8,
      "need_confirm": true,
      "status": "pending"
    }
  ]
}
```

也可以按条件查询建议：

```bash
curl "http://127.0.0.1:8000/api/suggestions?review_batch_id=<你的review_batch_id>&status=pending"
```

---

## 第 9 步：审核并恢复工作流

M3 支持接受、拒绝、编辑建议。最简单的演示是选择一个建议 ID 并接受：

```bash
curl -X POST http://127.0.0.1:8000/api/workflows/<你的task_id>/resume \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve",
    "approved_suggestion_ids": [1],
    "operator": "local_user"
  }'
```

也可以整批拒绝本轮建议：

```bash
curl -X POST http://127.0.0.1:8000/api/workflows/<你的task_id>/resume \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "reject",
    "reject_reason": "本次演示不执行建议",
    "operator": "local_user"
  }'
```

恢复后工作流会执行：

```
wait_human_review → validate_action → generate_report
```

M3 的 `validate_action` 只校验已审核建议是否合法，不执行任何分类树修改。

---

## 第 10 步：查看诊断报告

```bash
cat data/reports/v1.0_diagnosis_report.md
```

---

## 当前输出效果

运行完成后，你得到一份 Markdown 诊断报告。以下是真实样例（来自实际运行）：

```markdown
# 产品标准体系诊断报告

## 1. 基本信息

- 报告生成时间：2026-07-05T22:59:17+08:00
- 文件名称：产品标准体系.xlsx
- 版本号：v1.0

## 2. 体系统计

- 节点总数：21090
- 一级类目数：12
- 最大层级：10
- 叶子节点数：17965
- 非叶子节点数：3125
- 最大直接子节点数：225
- 同义词非空节点数：15072

## 3. 结构诊断结果

- 父节点缺失：44
- 层级过深：139
- 节点过宽：9
- 重复名称：3
- 结构问题总数：195

## 4. 内容诊断结果

由 DeepSeek AI 通过 ReAct Agent Loop 诊断，包含同义词污染、语义重复、
父子关系异常等问题。日志中可见 Thought-Action-Observation 推理链。
```

### 诊断过程中体现的智能体能力

| 能力 | 体现方式 |
|------|---------|
| **LLM 决策** | `diagnosis_planning`：DeepSeek 看结构统计后决定重点诊断哪些子树，避免无差别扫描 21090 个节点 |
| **工具调用** | `content_diagnosis`：LLM 通过 `@tool` 自主调用 `get_node_detail`、`search_similar_nodes`、`get_node_path` 等查询节点上下文 |
| **ReAct 循环** | 内容诊断和建议生成均按"思考→行动→观察→再思考"迭代推理，不确定时补充查询再判断 |
| **向量语义召回** | 千问 embedding 将 21090 个节点向量化存入 Qdrant，`search_similar_nodes` 实现语义相似召回 |
| **建议生成** | `generate_suggestion` 将 `diagnosis_issue` 转换为 `adjustment_suggestion`，包含动作类型、原因、风险、置信度和结构化 `action_payload` |
| **人工审核** | `wait_human_review` 通过 LangGraph interrupt 暂停，`/api/workflows/{task_id}/resume` 恢复后处理接受/拒绝/编辑决策 |
| **动作校验** | `validate_action` 校验已审核建议，包含非法动作、缺失节点、同义词不存在、move 到自身子树等规则 |
| **确定性规则** | `structure_diagnosis`：纯算法检测父节点缺失/层级过深/节点过宽/重复名称，不浪费 API 额度 |

---

## Swagger UI（可选）

打开浏览器访问 http://127.0.0.1:8000/docs ，可在交互式界面中直接调用所有 API，无需 curl。

演示步骤：
1. `POST /api/files/upload` → 上传 Excel
2. `POST /api/workflows/taxonomy/start` → 启动诊断和建议生成
3. `GET /api/workflows/{task_id}` → 查询进度，等待 `waiting_review`
4. `GET /api/reviews/{review_batch_id}` → 查看建议批次
5. `POST /api/workflows/{task_id}/resume` → 提交人工审核决策并恢复工作流
6. `GET /api/files/{file_id}` → 查看文件信息

---

## 查看数据库（可选）

用 sqlite3 直接查看诊断结果：

```bash
# macOS 安装 sqlite3
brew install sqlite

# 查看诊断问题
sqlite3 data/app.db "SELECT issue_type, node_name, description, risk_level FROM diagnosis_issue ORDER BY id DESC LIMIT 10;"

# 查看建议批次
sqlite3 data/app.db "SELECT review_batch_id, action_type, risk_level, status, COUNT(*) FROM adjustment_suggestion GROUP BY review_batch_id, action_type, risk_level, status;"

# 查看审核日志
sqlite3 data/app.db "SELECT operator, operation_type, operation_detail, created_time FROM operation_log ORDER BY id DESC LIMIT 10;"

# 查看节点统计
sqlite3 data/app.db "SELECT level, COUNT(*) FROM category_node WHERE version_id=1 GROUP BY level ORDER BY level;"

# 查看工作流事件
sqlite3 data/app.db "SELECT node_name, event_type, created_time FROM workflow_event ORDER BY id;"
```

---

## 常见问题

### Q: 工作流一直 waiting_review？
这是 M3 的正常暂停点。先调用 `GET /api/reviews/{review_batch_id}` 查看建议，再调用 `POST /api/workflows/{task_id}/resume` 提交审核决策。

### Q: 审核通过后为什么没有新版本？
M3 只生成、审核并校验建议，不执行动作、不生成新版本。动作执行、版本保存和导出属于 M4。

### Q: 工作流一直 running 不进入 waiting_review？
- 检查后端日志，看是否有 API 调用报错（DeepSeek/千问 网络不通或额度耗尽）
- 可能是内容诊断或建议生成 Agent Loop 卡在某个 API 调用，60 秒超时后会失败并记录错误

### Q: Qdrant 启动不了？
```bash
# 查看之前是否已有同名容器
docker rm -f qdrant
# 重新启动
docker run -d --name qdrant -p 6333:6333 -v $(pwd)/data/qdrant:/qdrant/storage qdrant/qdrant
```

### Q: 不想用 Docker？
Qdrant 有 Python 本地模式：`pip install qdrant-client[fastembed]`，在 `config.py` 中将 `qdrant_url` 设为 `None` 或本地路径即可。但推荐用 Docker（数据持久化、性能更好）。

### Q: API 调用报 "401 Unauthorized"？
检查 `.env` 中的 API key 是否正确，DeepSeek key 以 `sk-` 开头，千问 key 以 `sk-ws` 或 `sk-` 开头。

### Q: 想跳过内容诊断只看结构诊断？
修改 `config.py` 或 graph 拓扑，将 `content_diagnosis_node` 替换为占位节点（返回空结果）。这是 M1 级别的演示——纯确定性工作流，不需要 API key。

---

## 测试

```bash
# 运行全部测试（需要 Qdrant 运行）
.venv/bin/python -m pytest backend/tests/ -v
```

当前 35 个测试全部通过，覆盖 M1（确定性闭环）+ M2（内容诊断智能体）+ M3（建议生成、人工审核、动作校验）。
