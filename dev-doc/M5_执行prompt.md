# M5 里程碑执行 Prompt

> 用途：复制以下 Prompt 给 AI 编程助手，启动 M5 前端工作台实现。
> 项目路径：/Users/flflfl/Documents/code/SystemMaintenanceAgent
> 前置条件：M1-M4 后端已完成，版本 API、workflow API、review API、export API 可用。

---

## 一、M5 目标

你是一个资深前端工程师，现在要在现有项目上实现 M5 里程碑：本地智能体工作台 + 端到端演示。

M5 不新增智能体后端能力，而是把 M1-M4 的后端能力通过前端完整串联起来：

```text
上传 Excel
  -> 启动 LangGraph workflow
  -> 展示 workflow 节点进度
  -> waiting_review 时审核 Agent 建议
  -> resume workflow
  -> 执行动作并保存新版本
  -> 查看版本 diff
  -> 导出 Excel
  -> 查看报告
```

---

## 二、技术栈

如果仓库没有可用 `frontend/`，新建：

```text
Vue 3 + Vite + TypeScript + Vue Router
```

M5 P0 不强制引入 UI 框架。可以用原生 CSS 做清晰、稳定、适合答辩演示的界面。

默认 API base URL：

```text
http://127.0.0.1:8000/api
```

---

## 三、必读文档

1. `dev-doc/09_前端工作台开发设计.md` — M5 前端设计，以此为准。
2. `dev-doc/00_开发里程碑索引.md` — M5 章节和 M1-M4 边界。
3. `dev-doc/10_LangGraph智能体工作流开发设计.md` — workflow 节点、状态、interrupt/resume。
4. `dev-doc/M4_执行prompt.md` — 当前后端已实现到 M4，理解版本/diff/export/report 能力。
5. `backend/app/api/workflows.py` — start/status/resume 接口。
6. `backend/app/api/reviews.py` — review batch 查询。
7. `backend/app/api/versions.py` — versions/diff/rollback/export。
8. `backend/app/api/files.py` — Excel 上传。

---

## 四、实现范围

### P0 页面

1. `/upload`
   - 上传 Excel。
   - 展示文件名、行数、列数、字段。
   - 点击“开始智能体分析”。
   - 调 `POST /api/workflows/taxonomy/start`。
   - 跳转 `/workflow/:taskId`。

2. `/workflow/:taskId`
   - 轮询 `GET /api/workflows/{task_id}`。
   - 展示 LangGraph 节点步骤条。
   - status=waiting_review 时展示“进入审核”按钮。
   - status=completed 时展示“查看版本”“查看报告”按钮。
   - status=failed 时展示错误。

3. `/review/:reviewBatchId`
   - 调 `GET /api/reviews/{review_batch_id}`。
   - 展示建议列表。
   - 支持勾选 approve/reject。
   - 支持编辑建议 payload（MVP 可用 JSON textarea）。
   - 点击提交后调 `POST /api/workflows/{task_id}/resume`。
   - 跳回 workflow 页面。

4. `/versions`
   - 调 `GET /api/versions?file_id=xxx`。
   - 展示版本列表。
   - 支持选择两个版本并调 diff。
   - 支持导出版本 Excel。
   - 支持回滚版本。

5. `/report/:versionId`
   - MVP 展示 workflow 返回的 `report_path`。
   - 如果后端提供 preview，则展示 Markdown。

### P1 页面

6. `/overview/:versionId`
   - 展示统计卡片。

7. `/diagnosis/:versionId`
   - 展示结构/内容问题列表。
   - 如果后端诊断查询 API 不完整，可先展示空状态和报告入口。

8. `/tree/:versionId`
   - 分类树浏览。
   - 如果后端 tree API 不完整，可作为 P1 延后。

---

## 五、推荐文件结构

```text
frontend/
├── package.json
├── index.html
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/index.ts
    ├── api/
    │   ├── client.ts
    │   ├── files.ts
    │   ├── workflows.ts
    │   ├── reviews.ts
    │   └── versions.ts
    ├── state/workspace.ts
    ├── views/
    │   ├── UploadView.vue
    │   ├── WorkflowView.vue
    │   ├── ReviewView.vue
    │   ├── VersionsView.vue
    │   └── ReportView.vue
    ├── components/
    │   ├── AppShell.vue
    │   ├── StepTimeline.vue
    │   ├── FileInfoCard.vue
    │   ├── SuggestionTable.vue
    │   ├── VersionDiff.vue
    │   ├── VersionTable.vue
    │   ├── MarkdownViewer.vue
    │   └── EmptyState.vue
    └── styles/app.css
```

---

## 六、API 封装要求

### client.ts

实现统一 fetch wrapper：

```ts
export const API_BASE_URL = localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api'

export async function apiGet<T>(path: string): Promise<T> { ... }
export async function apiPost<T>(path: string, body?: unknown): Promise<T> { ... }
export async function apiUpload<T>(path: string, file: File): Promise<T> { ... }
```

所有 API 错误都要在页面上显示，不要静默失败。

### workflows.ts

封装：

```ts
startWorkflow(fileId: number)
getWorkflowStatus(taskId: string)
resumeWorkflow(taskId: string, payload: ResumeRequest)
```

### reviews.ts

封装：

```ts
getReviewBatch(reviewBatchId: string)
```

### versions.ts

封装：

```ts
listVersions(fileId?: number)
getVersion(versionId: number)
getVersionDiff(fromId: number, toId: number)
rollbackVersion(versionId: number)
exportVersion(versionId: number)
```

---

## 七、工作流步骤条

使用固定配置：

```ts
const workflowSteps = [
  { key: 'parse_excel', label: '解析 Excel', phase: 'M1' },
  { key: 'build_tree', label: '构建分类树', phase: 'M1' },
  { key: 'save_initial_version', label: '保存 v1.0', phase: 'M1' },
  { key: 'index_vector', label: '向量索引', phase: 'M2' },
  { key: 'structure_diagnosis', label: '结构诊断', phase: 'M1/M2' },
  { key: 'diagnosis_planning', label: '诊断规划 Agent', phase: 'M2' },
  { key: 'content_diagnosis', label: '内容诊断 Agent', phase: 'M2' },
  { key: 'generate_suggestion', label: '建议生成 Agent', phase: 'M3' },
  { key: 'human_review', label: '人工审核', phase: 'M3' },
  { key: 'validate_action', label: '动作校验', phase: 'M3' },
  { key: 'execute_action', label: '执行动作', phase: 'M4' },
  { key: 'save_new_version', label: '保存新版本', phase: 'M4' },
  { key: 'completed', label: '生成报告', phase: 'M4' },
]
```

根据 `current_step` 和 `status` 映射 pending/running/completed/waiting/failed。

---

## 八、工作区状态

实现 `state/workspace.ts`，保存并持久化：

```ts
type WorkspaceState = {
  fileId: number | null
  fileName: string | null
  taskId: string | null
  workflowId: string | null
  threadId: string | null
  currentVersionId: number | null
  newVersionId: number | null
  versionNo: string | null
  reviewBatchId: string | null
  reportPath: string | null
}
```

用 localStorage 持久化，刷新页面后恢复。

---

## 九、页面交互细节

### UploadView

1. 用户选择 Excel。
2. 调 `POST /api/files/upload`。
3. 展示 `columns`，检查是否包含标准字段。
4. 点击“开始智能体分析”。
5. 调 `POST /api/workflows/taxonomy/start`。
6. 保存 taskId，跳转 workflow。

### WorkflowView

1. 每 1.5 秒轮询一次状态。
2. 如果 `waiting_review` 且有 `review_batch_id`，显示审核按钮。
3. 如果 `completed`，停止轮询。
4. 如果 `failed`，停止轮询并展示错误。
5. 离开页面时清理 timer。

### ReviewView

1. 读取 route param `reviewBatchId` 和 query `task_id`。
2. 拉取建议列表。
3. 默认中高风险建议不自动 approve。
4. 用户选择 approve/reject 后提交：

```ts
{
  decision: 'approve',
  approved_suggestion_ids: [...],
  rejected_suggestion_ids: [...],
  edits: [],
  operator: 'local_user'
}
```

5. 提交成功后跳回 workflow 页面继续轮询。

### VersionsView

1. 从 workspace.fileId 拉版本列表。
2. 默认选最新版本和前一个版本做 diff。
3. diff 分组展示 added/deleted/renamed/moved/synonym_changed。
4. export 成功后展示导出路径。
5. rollback 前必须弹确认。

### ReportView

1. 优先展示 workspace.reportPath。
2. 如能拿到 report preview，展示 Markdown。
3. 否则展示“报告已生成在本地路径”。

---

## 十、样式要求

目标：清晰、可信、适合演示，不追求复杂动效。

布局：

```text
左侧导航 + 顶部状态栏 + 主内容区
```

导航项：

```text
上传分析
工作流
建议审核
版本管理
报告
```

视觉重点：

1. M1/M2/M3/M4 阶段标签。
2. Agent 节点用不同颜色标记。
3. waiting_review 用醒目提示。
4. 风险等级用 low/medium/high badge。
5. diff 用分组卡片展示。

---

## 十一、测试要求

至少实现一个 contract test：

```text
frontend/tests/navigation-contract.test.mjs
```

覆盖：

1. 关键路由存在。
2. workflowSteps 包含 M1-M4 节点。
3. API wrapper path 正确。
4. workspace localStorage 能保存/恢复。

命令：

```bash
cd frontend
npm run test:contract
npm run build
```

---

## 十二、Electron 设计（M5+，不阻塞 P0）

M5 P0 先做 Web 工作台。Electron 作为 M5+ 增强。

阶段 A：轻量桌面壳

```text
用户手动启动 FastAPI
Electron 打开前端 dist
前端请求 http://127.0.0.1:8000/api
```

阶段 B：完整桌面应用

```text
Electron main 启动 Python FastAPI 子进程
检查 /api/health
打开窗口
退出时关闭后端
```

M5 当前不要把 Electron 打包作为验收阻塞项。

---

## 十三、禁止行为

- 禁止前端硬编码诊断结果、建议结果、版本 diff。
- 禁止前端直接读写 SQLite。
- 禁止前端直接调用 LLM 或 Qdrant。
- 禁止绕过 workflow 直接执行建议。
- 禁止把 Electron 作为 P0 必选项。
- 禁止假进度；如果没有 SSE，就用真实 status 轮询。

---

## 十四、完成后

1. 运行 `npm run build`。
2. 运行 `npm run test:contract`。
3. 手动启动后端。
4. 前端上传 demo Excel。
5. 点击开始分析，看到 workflow 节点流转。
6. 到 waiting_review 后进入审核页。
7. approve 至少一条建议并 resume。
8. 完成后进入版本页查看 v1.1 和 diff。
9. 导出 Excel。
10. 查看报告页。
```
