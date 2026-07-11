# 开发文档入口

> 状态：CURRENT  
> 更新日期：2026-07-11  
> 本文件是 `dev-doc/` 的唯一入口。发生冲突时，按本文规定的优先级处理。

## 1. 当前产品目标

产品标准体系维护智能体是一套本地运行的分类体系持续维护工具。核心用户闭环是：

1. 上传或选择 Excel 体系文件；
2. 解析分类树并创建不可变的初始版本；
3. 运行全量规则筛查和重点语义诊断；
4. 展示问题、定位节点、证据和置信度；
5. 生成可执行建议，经过人工审核后执行；
6. 保存新版本，重新验证质量变化；
7. 导出新 Excel、完整报告，并允许基于新版本继续维护。

LangGraph 是确定性编排主干。LLM 只用于规划、语义诊断、建议组织和报告表述，不直接修改 Excel、SQLite 或 Qdrant。高风险动作必须经过人工审核。

## 2. 文档优先级

从高到低：

1. **当前事实**：代码、数据库迁移和自动化测试；
2. **当前文档**：本文件、`CURRENT_IMPLEMENTATION.md`、`ROADMAP.md`；
3. **产品与目标架构**：PRD、`12_标准产品体系维护多智能体最终设计.md`；
4. **功能设计参考**：01～10；
5. **历史分析和计划**：`archive/` 中的旧路线、评审、阶段计划和执行 prompt。

低优先级文档不能覆盖高优先级事实。历史文档中的“当前状态”“当前目标”和测试数量均只代表其编写时的快照。

## 3. 开工必读

任何实现任务先读：

1. 本文件；
2. `CURRENT_IMPLEMENTATION.md`；
3. `ROADMAP.md`；
4. 与任务直接相关的一份功能设计文档；
5. 涉及目标架构变化时，再读 `12_标准产品体系维护多智能体最终设计.md`。

不再要求每次开发同时阅读 00、10、11、12 和全部阶段计划。

## 4. 当前有效文件

| 文件 | 作用 | 状态 |
|---|---|---|
| `README.md` | 唯一入口、优先级和阅读路径 | CURRENT |
| `CURRENT_IMPLEMENTATION.md` | 代码和测试事实基线 | CURRENT |
| `ROADMAP.md` | 唯一当前开发路线 | CURRENT |
| `DOCUMENT_CONFLICTS.md` | 已裁决的冲突和过期声明 | CURRENT |
| `产品标准体系维护智能体_PRD.md` | 产品需求背景 | REFERENCE，需逐步精简 |
| `产品标准体系维护智能体_技术架构设计.md` | 基础技术分层和部署参考 | REFERENCE，以当前代码为准 |
| `12_标准产品体系维护多智能体最终设计.md` | 长期目标架构 | TARGET，不等于当前实现 |
| `01_...`～`09_...` | 按业务功能查阅的设计契约 | REFERENCE |
| `10_LangGraph智能体工作流开发设计.md` | 节点、State 和工作流契约参考 | REFERENCE，旧路线已失效 |
| `features/` | 已进入 R1～R3 的功能 PRD | PLANNED/PARTIAL |
| `backlog/` | 暂缓的候选需求 | DEFERRED |
| `product/` | 产品价值和答辩材料 | MATERIAL |
| `archive/` | 历史路线、评审、方案和 prompt | ARCHIVED |

## 5. 历史文件

历史文件已集中移动到 `archive/`，目录说明见 `archive/README.md`。它们保留用于追溯，不作为当前执行入口：

- `archive/00_开发里程碑索引.md`：旧 M1～M5 路线；
- `archive/架构评审报告.md`：早期代码审计快照；
- `archive/11_智能体架构迭代优化设计.md`：架构问题分析和演进建议；
- `archive/13_...`～`archive/16_...`：四阶段方案的详细历史实施计划；
- `archive/M1_执行prompt.md`～`archive/M5_执行prompt.md`、`archive/M3_最终执行计划.md`：一次性执行材料。

这些文件可以提供设计背景，但其中与当前代码冲突的描述视为过期。

## 6. 工程不变量

- LangGraph 节点保持薄：调用 service、更新 state、决定路由；
- 规则诊断不调用 LLM；
- LLM 不直接写业务数据库、Excel 或向量库；
- 原始 Excel 永不覆盖，新版本和导出物单独保存；
- 所有副作用操作必须有 workflow/run、版本和审核证据；
- 前端展示决策摘要、工具调用和证据，不展示原始 chain-of-thought；
- 失败不得被后续节点覆盖成 completed；
- “完成”必须同时有实现、测试和用户可见验收证据。

## 7. 验证命令

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests
Set-Location frontend
npm.cmd run test:contract
npm.cmd run build
```
