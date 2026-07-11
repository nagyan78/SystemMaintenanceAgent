# 产品标准体系维护智能体

本项目是一套本地运行的产品分类体系持续维护平台。系统通过 FastAPI、LangGraph、SQLite、Qdrant 和 Vue 串联 Excel 导入、分类树解析、结构与内容诊断、建议生成、人工审核、动作执行、版本保存和报告导出。

它不是通用 Excel 上传器，也不是泛聊天机器人。核心目标是让分类体系维护过程可审核、可追溯、可生成新版本。

## 当前状态

当前已经具备一条可运行的主工作流：

```text
上传 Excel
→ 解析分类树
→ 保存初始版本
→ 建立向量索引
→ 结构诊断
→ 诊断规划与内容诊断
→ 生成建议
→ 人工审核
→ 校验并执行动作
→ 保存新版本
→ 生成报告
```

workflow、suggestions、reviews、versions 和 reports 已有实际 API。taxonomy、diagnosis 和 chat 仍存在未完成的查询边界；诊断覆盖率、run 级证据链、新版本复检和持续维护闭环仍需补齐。

完整事实基线见 [当前实现矩阵](dev-doc/CURRENT_IMPLEMENTATION.md)，近期路线见 [ROADMAP](dev-doc/ROADMAP.md)。

## 环境要求

- Windows PowerShell
- Python 3.11+
- Node.js 18+
- 可选：Docker/Qdrant（内容诊断需要）
- 可选：DeepSeek 与 DashScope API Key（LLM/Embedding 路径需要）

项目已包含 `.venv` 和 `frontend/node_modules` 时，无需重复全局安装依赖。

## 配置

复制 `.env.example` 为 `.env`，按需要填写：

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=
EMBEDDING_MODEL=text-embedding-v2
```

## 启动

后端：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`

完整演示步骤见 [RUNBOOK.md](RUNBOOK.md)。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
```

2026-07-11 实测基线：后端 56 passed；前端 contract 和 production build 通过。

## 项目结构

```text
backend/          FastAPI、LangGraph、service、repository 和测试
frontend/         Vue 工作台
dev-doc/          当前设计、功能文档、backlog、产品材料和历史归档
data/             SQLite、上传文件、导出物和报告（运行时生成）
requirements.txt Python 依赖
RUNBOOK.md        演示与故障排查手册
```

文档从 [dev-doc/README.md](dev-doc/README.md) 开始阅读。

## 当前开发重点

当前优先完成 R1“可信诊断与完整结果”：

1. 补齐 taxonomy 和 diagnosis 查询 API；
2. 建立全量轻筛查、候选召回和 Agent 深诊断的覆盖漏斗；
3. 让诊断规划真正约束执行；
4. 完善问题、节点、证据和报告之间的追溯关系。

