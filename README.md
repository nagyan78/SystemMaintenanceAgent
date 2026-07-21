# 产品标准体系维护智能体

本项目是一套本地运行的产品分类体系检测、整改和版本维护平台。系统面向固定六列的分类树 Excel，通过确定性规则和有界 AI 分析检查两万级节点的结构与内容质量，并在独立 AI 复核、确定性校验和完整快照预演通过后，在副本上自动执行整改。

技术栈为 FastAPI、LangGraph、SQLite、Qdrant 和 Vue。本项目不是通用 Excel 上传器，也不是聊天机器人。

## 核心能力

- 导入、校验和保存产品分类体系 Excel；
- 将分类数据解析为可查询、可追溯的树形版本；
- 全量检测父节点缺失、同级重名、路径过深、节点过宽等结构问题；
- 全量检测同义词格式和确定性内容问题；
- 按根分类、层级、叶子属性和同义词状态进行联合分层随机抽样；
- 使用 AI 对抽样节点进行“合理 / 不合理”二分类；
- 不合理节点必须记录问题类型、证据、原因和影响范围；
- 按固定问题类型生成整改方案；
- 由独立 AI 二次复核方案，不设置人工审核环节；
- 通过确定性校验、快照预演、事务和幂等门禁后自动执行；
- 永不覆盖原始 Excel，整改结果生成新版本；
- 输出版本差异、质量评分、Markdown/PDF 报告和新版本 Excel；
- 通过 workflow、run、work item、issue、suggestion、review batch 和 execution 保存完整证据链。

## 输入数据格式

输入文件必须为 `.xlsx`，业务表只包含以下六列：

| 字段 | 含义 |
|---|---|
| `category_id` | 节点唯一 ID |
| `category_name` | 分类名称 |
| `category_group_id` | 根分类或分类组 ID |
| `category_pids` | 祖先 ID 路径 |
| `category_group_name` | 根分类或分类组名称 |
| `syn_list` | 同义词列表 |

父节点缺失不会阻止导入，而是在诊断阶段记录为高风险结构问题。导出的业务 Excel 仍保持这六列，不增加系统内部评分、状态或审计字段。

## 完整工作流

```text
上传 Excel
  ↓
字段校验与分类树解析
  ↓
保存不可变初始版本
  ↓
全量结构规则诊断
  ↓
全量内容规则诊断
  ↓
联合分层随机抽样
  ↓
AI 合理 / 不合理二分类
  ↓
不合理问题分类与整改方案生成
  ↓
独立 AI 二次复核
  ↓
确定性校验与完整快照预演
  ↓
副本自动执行
  ↓
新版本、复诊、差异和报告
```

模型调用失败或未在限定轮次内提交有效二分类结论时，样本标记为“未完成”，不进入评分，也不伪造问题或整改动作。预算耗尽时保留已完成结果，并进入部分完成状态。

## 诊断规则

### 结构规则

- 父节点缺失：允许导入，诊断为结构断链；
- 同级重名：只检查同一父节点下的完全重名；
- 层级过深：根节点计为第一层，固定上限为 7 层；
- 节点过宽：固定上限为 80 个直接子节点。

### 内容规则与 AI 判断

- 同义词为空、重复或包含节点主名称；
- 同义词在父子层级间造成语义范围重叠；
- 节点名称是否清晰并符合产品分类表达；
- 节点与父节点是否具有合理的上下位关系；
- 节点与同级分类是否采用一致的分类维度；
- 同义词是否与主名称等价。

业务代码不得针对具体产品名称写死诊断答案。具体案例只允许保存在 Golden 测试数据中。

## 质量评分

综合质量分由三个子项组成：

```text
综合质量分 = 结构规则分 × 40%
           + 内容规则分 × 10%
           + AI 内容抽样分 × 50%
```

结构和内容规则采用每千节点风险扣分制：

```text
规则分 = max(
  0,
  100 - 1000 / max(节点总数, 1000)
        × (高风险节点数 × 10 + 中风险节点数 × 5 + 低风险节点数)
)
```

- 同一节点命中多个规则时，只计算最严重问题；
- 高风险问题计 10 个扣分点；
- 中风险问题计 5 个扣分点；
- 低风险问题计 1 个扣分点；
- 小于 1000 个节点时按 1000 个节点归一化；
- 不设置目标分、封顶分或具体文件特例。

AI 内容抽样采用二分类评分：

```text
AI 内容抽样分 = 合理数量 / (合理数量 + 不合理数量) × 100
```

未完成样本单独统计，不进入分母。没有有效二分类结果时不计算 AI 抽样分，也不计算综合质量分。

## 自动整改与安全边界

AI 不直接修改 Excel、SQLite 或 Qdrant。修改方案必须依次经过：

1. 问题类型与固定整改动作匹配；
2. 独立 AI 二次复核明确通过；
3. 必填参数、节点存在性和影响范围校验；
4. 重复 ID、循环、断链和同级重名检查；
5. 整个动作批次在内存副本中预演；
6. 执行前数据库备份；
7. 事务和幂等键执行；
8. 新版本生成与重新诊断。

复核缺失、复核存在疑虑、参数不完整或预演失败都会阻止执行。原始 Excel 和历史版本始终保留。

## 技术架构

```text
Vue 工作台
  ↓ HTTP / SSE
FastAPI API 层
  ↓
LangGraph 工作流编排
  ↓
Service 业务层
  ├─ Excel 解析与版本服务
  ├─ 规则诊断与分层抽样
  ├─ AI 内容诊断与独立复核
  ├─ 整改规划、校验和快照预演
  └─ 报告、导出和质量评分
  ↓
Repository 数据访问层
  ├─ SQLite：版本、任务、问题和审计证据
  └─ Qdrant：可选的相似节点检索
```

LangGraph 节点保持轻量，只负责 service 调用、state 更新和路由。Excel 解析、SQL、向量检索、prompt 和动作执行逻辑均位于独立服务中。

## 项目目录

```text
standard_product_system/
├─ backend/
│  ├─ app/
│  │  ├─ agents/          LangGraph 图、节点、状态和提示词
│  │  ├─ api/             FastAPI 路由
│  │  ├─ domain/          领域定义
│  │  ├─ repositories/    SQLite 数据访问
│  │  ├─ schemas/         API 与业务模型
│  │  ├─ services/        诊断、抽样、复核、执行和报告
│  │  └─ tools/           Agent 受限工具
│  └─ tests/              后端测试与 Golden 数据
├─ frontend/
│  ├─ src/api/            前端 API 客户端
│  ├─ src/components/     可复用组件
│  ├─ src/views/          上传、工作流、版本、树和报告页面
│  └─ src/router/         页面路由
├─ data/                  本地数据库与运行时数据
├─ docs/                  解决方案和验收材料
├─ 开发文档/              当前状态、架构、路线图和历史资料
├─ tools/windows-launcher Windows 启停程序源码
├─ RUNBOOK.md             演示步骤与故障排查
├─ requirements.txt       Python 依赖
└─ README.md              项目入口
```

开发事实以当前代码和自动化测试为最高优先级。文档入口见[开发文档/README.md](开发文档/README.md)。

## 环境要求

- Windows 10/11；
- PowerShell；
- Python 3.11+；
- Node.js 18+；
- 可选 Qdrant，用于相似节点检索；
- DeepSeek API Key，用于 AI 判断和复核；
- 可选 DashScope API Key，用于 Embedding。

应优先使用项目的 `.venv` 和 `frontend/node_modules`，不要用全局 Python 修改项目环境。

## 配置

复制 `.env.example` 为 `.env`：

```dotenv
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=taxonomy_nodes

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

DASHSCOPE_API_KEY=
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v2

AGENT_LLM_MAX_CONCURRENCY=4
AGENT_QDRANT_MAX_CONCURRENCY=8
LLM_MAX_CALLS=1000
LLM_MAX_TOKENS=1200000
DIAGNOSIS_SAMPLE_SIZE=200
DIAGNOSIS_SAMPLE_SEED=20260721
DIAGNOSIS_AI_WALL_SECONDS=900
```

密钥只保存在本地 `.env`，不要提交到 Git。

## 安装与启动

安装后端依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

安装前端依赖：

```powershell
Set-Location frontend
npm.cmd install
```

Windows 下可直接双击根目录的 `启动系统.exe`。需要完整停止时双击 `停止系统.exe`。

手动启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 窗口启动前端：

```powershell
Set-Location frontend
npm.cmd run dev
```

默认地址：

- 前端：<http://127.0.0.1:5173>
- 后端：<http://127.0.0.1:8000>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 使用步骤

1. 打开“上传与启动”；
2. 上传包含六个约定字段的 `.xlsx`；
3. 选择是否启用 AI 分析并启动任务；
4. 在工作流页面查看规则、抽样、复核和执行进度；
5. 在诊断页面查看问题类型、节点路径、风险和证据；
6. 在版本页面比较原版本和新版本；
7. 在报告页面下载 Markdown、PDF 或新版本 Excel。

完整演示流程见[RUNBOOK.md](RUNBOOK.md)。

## 主要 API

| 模块 | 典型路径 | 用途 |
|---|---|---|
| 健康检查 | `GET /api/health` | 后端状态 |
| 文件 | `/api/files` | 上传和查询 Excel |
| 分类树 | `/api/taxonomy` | 树概览、节点和路径 |
| 诊断 | `/api/diagnosis` | 启动诊断和查询问题 |
| 工作流 | `/api/workflows` | 状态、事件和证据链 |
| Agent 运行 | `/api/agent-runs` | run、work item 和预算 |
| 建议 | `/api/suggestions` | 整改建议 |
| 自动复核 | `/api/reviews` | AI 复核与执行状态 |
| 版本 | `/api/versions` | 版本、差异、导出和回滚 |
| 报告 | `/api/reports` | Markdown/PDF 报告 |
| 维护 | `/api/maintenance` | 本地运行数据清理 |
| 评估 | `/api/evaluations` | Golden 评估和发布门禁 |

旧人工审核写接口默认关闭，前端不提供人工批准、拒绝或编辑入口。

## 运行时数据

- `data/app.db`：主 SQLite 数据库；
- `data/workflow_checkpoints.sqlite`：工作流 checkpoint；
- `data/uploads/`：原始上传文件；
- `data/exports/`：新版本 Excel；
- `data/reports/`：Markdown/PDF 报告；
- `data/qdrant/`：本地向量数据。

这些运行时文件由 `.gitignore` 排除，不应提交。清理数据前应先使用维护接口预览范围，并保留数据库备份。

## 常用开发命令

```powershell
# 后端
.\.venv\Scripts\python.exe -m pytest backend/tests

# 前端
Set-Location frontend
npm.cmd run typecheck
npm.cmd run test:contract
npm.cmd run build
```

README 只提供命令，不代表每次小改动都必须执行全部检查。完成状态以最近一次实际执行结果为准。

## 常见问题

### 后端无法启动

- 确认使用 `.venv\Scripts\python.exe`；
- 检查 8000 端口；
- 检查 `.env` 格式；
- 查看 PowerShell 中的 FastAPI 错误。

### 前端无法连接后端

- 检查 `/api/health`；
- 确认前端地址为 `127.0.0.1:5173`；
- 确认后端地址为 `127.0.0.1:8000`。

### AI 分析部分完成

- 检查 DeepSeek Key、网络和模型额度；
- 检查 Token、调用次数和 wall-time 预算；
- 已完成结果会保留，失败样本不进入二分类评分；
- 预算恢复后可以续跑未完成 work item。

### Qdrant 不可用

相似节点检索会降级，但确定性规则扫描仍可完成。系统不会用伪造结果替代外部依赖。

## 当前边界

当前项目定位为单机课程项目和本地维护工具，暂不包含：

- 泛化聊天机器人；
- 分布式多 Agent 平台；
- 多实例共享 worker 和 checkpoint；
- 人工审核工作台；
- 对全部节点逐个调用 LLM；
- 覆盖原始 Excel；
- 展示模型原始 chain-of-thought。

可靠性与规模化后续工作见[当前开发路线图](开发文档/00_当前状态/当前开发路线图.md)中的 R4。

## 相关文档

- [当前实现情况](开发文档/00_当前状态/当前实现情况.md)
- [当前开发路线图](开发文档/00_当前状态/当前开发路线图.md)
- [解决方案](docs/解决方案.md)
- [真实文件验收结果](docs/真实文件验收报告_20260721.md)
- [演示与故障排查](RUNBOOK.md)
- [Agent 开发约束](AGENTS.md)
