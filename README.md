# 产品标准体系维护智能体

本项目是一套本地运行的产品分类体系持续维护平台。系统使用 FastAPI、LangGraph、SQLite、Qdrant 和 Vue 串联 Excel 导入、分类树解析、结构与内容诊断、建议生成、人工审核、动作执行、版本保存和报告导出。

它不是通用 Excel 上传器，也不是泛聊天机器人。核心目标是让产品分类体系维护过程可审核、可追溯、可生成新版本。

## 当前状态

当前已具备一条可运行的主要工作流：

```text
上传 Excel
→ 解析分类树并保存初始版本
→ 建立向量索引
→ 结构诊断
→ 诊断规划与内容诊断
→ 生成建议并人工审核
→ 校验和执行动作
→ 保存新版本并生成报告
```

workflow、suggestions、reviews、versions 和 reports 已有实际 API。taxonomy、diagnosis 的查询边界，以及诊断覆盖率、Token 不足时的降级报告、run 级证据链和新版本复检仍是当前重点。

完整事实基线见[当前实现情况](开发文档/00_当前状态/当前实现情况.md)，近期路线见[当前开发路线图](开发文档/00_当前状态/当前开发路线图.md)。

## 环境要求

- Windows PowerShell
- Python 3.11+
- Node.js 18+
- 可选：Docker/Qdrant，用于向量检索与内容诊断
- 可选：DeepSeek 和 DashScope API Key，用于 LLM 与 Embedding

项目已包含 `.venv` 和 `frontend/node_modules` 时，无需重复使用全局环境安装依赖。

## 配置

复制 `.env.example` 为 `.env`，按需填写：

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=
EMBEDDING_MODEL=text-embedding-v2
```

## 本地启动

### 双击启动（推荐）

Windows 下可以直接双击项目根目录的 `启动系统.exe`，它会同时启动后端和前端，并自动打开浏览器。需要完整重启时，先双击 `停止系统.exe`，再双击 `启动系统.exe`。

启动器固定使用项目自己的 `.venv` 和 `frontend/node_modules`。如果启动失败，再使用下面的 PowerShell 命令查看详细错误。

### PowerShell 启动

在项目根目录打开 PowerShell，启动后端：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

再打开一个 PowerShell 窗口启动前端：

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`

如果平时使用 CMD，可在资源管理器打开项目目录，在地址栏输入 `powershell` 后回车；也可在 CMD 中直接输入 `powershell` 切换。

完整演示步骤见 [RUNBOOK.md](RUNBOOK.md)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests

Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
```

2026-07-13 本地验证基线：后端 87 passed，另有 1 个第三方 Starlette TestClient 弃用警告；前端 contract test 和 production build 通过。

## 项目结构

```text
backend/          FastAPI、LangGraph、service、repository 和测试
frontend/         Vue 工作台
开发文档/         当前状态、产品架构、功能需求、执行计划和历史归档
data/             SQLite、上传文件、导出物和报告（运行时生成）
requirements.txt Python 依赖
RUNBOOK.md        演示与故障排查手册
```

开发前从[开发文档总入口](开发文档/README.md)开始阅读。

## 当前开发重点

当前优先完成 [R1 可信诊断与完整结果](开发文档/03_开发执行计划/R1_可信诊断与完整结果_执行计划.md)：

1. 补齐 taxonomy 和 diagnosis 查询 API；
2. 建立全量轻筛查、候选召回和 Agent 深诊断的覆盖漏斗；
3. 让规划范围和 Token 预算真正约束执行；
4. Token 不足时保留已有结果并生成部分完成报告；
5. 完善问题、节点、证据和报告之间的追溯关系。
