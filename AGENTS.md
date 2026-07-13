# Project Agent Notes

本文件供后续开发代理使用。修改代码前必须阅读，但不要用记忆替代仓库中的当前事实。

## Project Identity

- 项目路径：`D:\Code of my\Course\Professional Design\standard_product_system`
- 项目名称：产品标准体系维护智能体
- 产品定位：本地运行、由 LangGraph 编排、支持人工审核和版本持续维护的产品分类体系维护平台；不是通用 Excel 上传器，也不是泛聊天机器人。
- 技术栈：FastAPI、LangGraph、LangChain、SQLite、Qdrant、Vue。

## Source of Truth

先读 `开发文档/README.md`。它定义文档优先级、当前有效文档和历史文档的使用方式。

开工最小阅读顺序：

1. `开发文档/README.md`
2. `开发文档/00_当前状态/当前实现情况.md`
3. `开发文档/00_当前状态/当前开发路线图.md`
4. 与任务直接相关的功能需求或 R1～R3 执行计划
5. 涉及长期架构变更时读取 `开发文档/01_产品与架构/多智能体目标架构.md`

代码和自动化测试高于描述性文档。`开发文档/99_历史归档/` 中的旧索引、评审、阶段计划和执行提示词是历史资料，不是当前开发路线。

## Current Direction

当前优先完成 `开发文档/03_开发执行计划/R1_可信诊断与完整结果_执行计划.md`：

- 补齐 taxonomy/diagnosis 查询能力；
- 建立全量轻筛查、候选召回、重点 Agent 深诊断的覆盖漏斗；
- 让规划真实控制执行范围和 Token 预算；
- Token 不足时保留已有结果并生成部分完成报告；
- 完善节点、问题、证据和报告之间的可追溯关系。

不要在 R1～R3 用户闭环完成前扩张为分布式多 Agent 平台。

## Engineering Rules

- LangGraph 节点必须保持薄，只负责 service 调用、state 更新和路由；
- Excel 解析、树构建、SQL、Qdrant、prompt 和动作执行逻辑不得直接堆在 node 中；
- 规则诊断不使用 LLM；
- LLM 不直接修改 Excel、SQLite 或 Qdrant；
- 高风险动作必须先人工审核；
- 原始 Excel 不覆盖，新版本和导出物单独保存；
- 副作用必须具备 workflow/run、版本、审核和幂等证据；
- 前端不展示原始 chain-of-thought，只展示决策摘要、工具和证据；
- 节点失败不得被后续节点覆盖为 completed；
- 不硬编码诊断数量、评分或演示结果。

## Local Environment

当前环境是 Windows PowerShell。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
npm.cmd run dev
```

不要使用全局 Python 安装依赖。前端依赖位于 `frontend/node_modules/`。

## Verification Baseline

2026-07-13 实测后端基线：87 passed，1 个第三方 Starlette TestClient 弃用警告；前端 contract test 和 production build 通过。

声明后端完成前运行全部后端测试；声明前端完成前运行 contract test 和 build。文档修改至少检查链接、文件名和状态声明。

## Git and Workspace

- 工作树可能包含用户正在进行的修改；不要回退无关变更；
- 未提交改动不等于已发布能力，在文档中应注明事实范围；
- 保留历史设计文件，除非用户明确授权归档或删除；
- 修改与用户现有改动重叠时应先检查 diff，并尽量做最小修改。
