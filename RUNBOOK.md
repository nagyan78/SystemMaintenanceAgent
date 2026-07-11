# 演示与运行手册

> 更新日期：2026-07-11  
> 适用环境：Windows PowerShell

## 1. 前置条件

- Python 虚拟环境位于 `.venv`；
- 前端依赖位于 `frontend/node_modules`；
- 内容诊断需要 Qdrant、DeepSeek API 和 DashScope Embedding；
- 只验证确定性代码或运行测试时，不要求所有外部服务始终在线。

## 2. 配置环境变量

确认根目录 `.env` 至少包含所需配置：

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=
EMBEDDING_MODEL=text-embedding-v2
```

不要提交真实 API Key。

## 3. 启动 Qdrant

如果本机使用 Docker：

```powershell
docker run --name taxonomy-qdrant -p 6333:6333 -p 6334:6334 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

已有容器时使用：

```powershell
docker start taxonomy-qdrant
```

验证：访问 `http://127.0.0.1:6333/`。

## 4. 启动后端和前端

终端一：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

终端二：

```powershell
Set-Location frontend
npm.cmd run dev
```

验证：

- `GET http://127.0.0.1:8000/api/health`
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:5173`

## 5. 推荐演示流程

### 5.1 上传或选择文件

打开前端上传页，上传 `.xlsx` 文件，或者从历史文件列表选择已经上传的文件。确认字段预览正确后启动工作流。

也可以使用 API：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/files/upload -F "file=@sample.xlsx"
```

记录返回的 `file_id`。

### 5.2 启动工作流

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/workflows/taxonomy/start `
  -H "Content-Type: application/json" `
  -d '{"file_id":1}'
```

记录 `task_id`、`workflow_id` 和 `thread_id`。

### 5.3 查看进度

```powershell
curl.exe http://127.0.0.1:8000/api/workflows/{task_id}
curl.exe -N http://127.0.0.1:8000/api/workflows/{task_id}/events
```

正常情况下，工作流会执行诊断与建议生成，并在存在待审核建议时进入 `waiting_review`。

### 5.4 审核建议

从工作流状态取得 `review_batch_id`：

```powershell
curl.exe http://127.0.0.1:8000/api/reviews/{review_batch_id}
```

推荐直接在前端审核页选择建议并点击“批准选中并继续工作流”或“全部拒绝并生成报告”。前端会提交决策并调用 workflow resume。

如果使用 API，应先提交审核决策，再调用：

```text
POST /api/workflows/{task_id}/resume
```

请求字段以 Swagger 中的 `ResumeWorkflowRequest` 为准。

### 5.5 查看版本、Diff 和导出

```text
GET /api/versions?file_id={file_id}
GET /api/versions/{from_version_id}/diff?target_version_id={to_version_id}
GET /api/versions/{version_id}/export
POST /api/versions/{version_id}/rollback
```

前端版本页已经支持选择两个版本并请求 Diff，但更完整的过滤、树高亮和路径变化展示仍属于后续增强。

### 5.6 查看报告

```text
POST /api/reports/generate
GET /api/reports/{version_id}/preview
GET /api/reports/{version_id}/download
```

当前报告按版本生成 Markdown。按 workflow run 聚合输入版本、审核、动作和输出版本的完整证据链仍在路线图中。

## 6. 当前已知限制

- taxonomy 和 diagnosis 独立查询 API 尚未完整接入；
- chat/Copilot API 仍为 backlog；
- 内容诊断候选尚未形成可量化的全量覆盖漏斗；
- 新版本复检与从任意版本继续维护尚未形成完整产品闭环；
- 后台任务仍运行在应用进程内，不是独立 durable worker；
- SSE 还缺完整的 Last-Event-ID 续传语义。

## 7. 常见问题

### 工作流停在 waiting_review

这是正常人工审核点。进入审核页完成决策并恢复工作流。

### 工作流一直 running

检查后端日志、Qdrant、API Key 和模型服务；再查询 workflow events 是否记录了失败节点。不要通过修改 graph 跳过失败节点来伪造完成状态。

### Qdrant 无法连接

确认 `QDRANT_URL`、容器端口和 collection；执行 `docker ps -a` 查看容器状态。

### 没有生成建议

可能是没有诊断问题、模型服务不可用，或候选范围为空。检查 workflow 状态、事件和数据库中的 `diagnosis_issue`，不要把零建议自动解释为“体系没有问题”。

### 报告为空或缺少旧版本问题

这是已知的 run 级证据链问题。当前报告主要按版本查询，执行后切换版本可能导致上下游数据没有完整聚合。

## 8. 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
```

2026-07-11 基线：后端 56 passed、1 个第三方弃用警告；前端 contract 和 build 通过。

