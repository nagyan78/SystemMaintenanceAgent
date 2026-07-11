# 当前实现矩阵

> 状态：CURRENT  
> 核对日期：2026-07-11  
> 事实基线：当前工作树代码与自动化测试。未提交改动也属于本次核对范围，但不代表已经发布。

## 1. 验证基线

- 后端：`56 passed`，1 个第三方 Starlette TestClient 弃用警告；
- 前端：`npm.cmd run test:contract` 通过，`npm.cmd run build` 通过；
- Python 环境：Windows `.venv\Scripts\python.exe`，不是旧文档中的 `.venv/bin/python`。

## 2. 能力矩阵

| 用户能力 | 后端 | 前端 | 判断 | 主要缺口 |
|---|---|---|---|---|
| Excel 上传、字段识别、历史文件 | 已实现 | 已接入 | 可用 | 缺真实大文件和异常模板的系统验收 |
| 分类树解析与初始版本 | service/repository/node 已实现 | 有概览/树页面 | 部分可用 | taxonomy 查询 API 仍有 501 边界，页面能力不完整 |
| 结构诊断 | 规则 service 和 workflow 已实现 | 有诊断页面 | 部分可用 | diagnosis 查询 API 仍是占位，问题详情/筛选不足 |
| Qdrant 向量索引 | service/store/node 已存在 | 通过 workflow 展示 | 条件可用 | 依赖外部 Qdrant/embedding；缺稳定性和增量索引闭环 |
| 内容诊断 Agent | planning、tools、service、node 和测试已存在 | 可见步骤 | 部分可用 | 候选覆盖面有限；规划字段没有全部控制执行 |
| 建议生成 | service/repository/API/node 已实现 | 审核页已接入 | 部分可用 | 动作类型、证据完整性和质量评价仍需加强 |
| 人工审核与 resume | interrupt、审核 API、resume 已实现 | 审核交互已接入 | 可用主路径 | 编辑预览、风险分级和批量操作仍不完整 |
| 动作执行 | rename/move/add 等确定性动作和测试已存在 | 审核后可继续 | 部分可用 | split/merge/deprecate/delete 等产品动作未补齐 |
| 新版本、diff、回滚、导出 | service/API/工具和测试已存在 | 版本页已接入 | 部分可用 | 新版本重新索引、重诊断和持续维护入口不足 |
| 报告 | service、预览/下载 API 和测试已存在 | 报告页已接入 | 部分可用 | 应改为按 workflow run 聚合，补齐前后版本和证据链 |
| 工作流 API | start/status/events/resume 已实现 | workflow 页面已接入 | 部分可用 | 后台执行仍是进程内任务；恢复、取消和失败语义需加强 |
| SSE | 事件表、事件映射和输出已实现 | 时间线已接入 | 基础可用 | 缺标准 `id:`/Last-Event-ID 续传和细粒度 Agent 事件 |
| Chat | 501 占位 | 非核心 | 未实现 | 当前路线不优先，避免做成泛聊天机器人 |

## 3. 当前已确认的结构性风险

### P0：失败终态可能不可靠

图的大部分边是固定边。节点 guard 将异常转换为 state 后，后续节点仍可能继续运行；报告节点可能覆盖失败状态。所有节点需要统一失败路由和终态不变量。

### P0：运行时隔离不足

workflow checkpointer 和部分运行时对象使用进程级全局变量。并发任务、测试隔离和多应用实例存在互相污染风险。

### P0：报告证据链不完整

问题、建议、审核、动作和新版本不能只靠 `current_version_id` 聚合。执行后切换到新版本，可能查不到基于旧版本产生的问题和建议。报告需要以 `workflow_id/run_id` 为主键串联输入版本与输出版本。

### P1：诊断覆盖面不足

当前内容诊断候选并不等于全量节点。应先对所有节点执行低成本规则筛查，再对异常候选做向量召回和 Agent 深诊断，并记录覆盖率。

### P1：API 与内部 service 不对称

部分业务 service 已实现，但 taxonomy、diagnosis 和 chat API 仍有 501 占位。用户无法完整浏览树、搜索节点、筛选问题和追溯证据。

### P1：持续维护闭环尚未完成

生成新版本不等于闭环完成。还需要对新版本重新索引、重新诊断、使用同一评分公式比较，并允许用户选择新版本继续维护。

## 4. “完成”的统一定义

一个能力只有同时满足以下条件才能标记为完成：

1. 真实 service/repository 实现，不是硬编码或 501；
2. workflow/API 已接入；
3. 前端存在用户可完成的交互；
4. 自动化测试覆盖成功、失败和幂等主路径；
5. 固定样例 Excel 的端到端验收通过；
6. 结果可通过 workflow/run 追溯。
