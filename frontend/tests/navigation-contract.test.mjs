import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const packageJson = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
assert.equal(packageJson.scripts['test:contract'], 'node tests/navigation-contract.test.mjs')

const routerSource = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
for (const route of ['/upload', '/workflow/:taskId', '/review/:reviewBatchId', '/versions', '/report/:versionId', '/evaluation', '/triage']) {
  assert.ok(routerSource.includes(route), `missing route ${route}`)
}

const workflowSource = readFileSync(new URL('../src/views/WorkflowView.vue', import.meta.url), 'utf8')
for (const step of ['Excel 解析', '结构检测', '内容检测', 'AI 分析']) {
  assert.ok(workflowSource.includes(step), `missing workflow step ${step}`)
}

const uploadViewSource = readFileSync(new URL('../src/views/UploadView.vue', import.meta.url), 'utf8')
assert.ok(uploadViewSource.includes('开始诊断'), 'upload page must expose the diagnosis-first user action')
assert.ok(uploadViewSource.includes('分类层级'), 'upload page must show parsed taxonomy metrics')
assert.ok(uploadViewSource.includes('runDiagnosis'), 'upload page must start the simplified diagnosis flow')
assert.ok(uploadViewSource.includes('快速模式（关闭 AI）'), 'AI must be disabled by default for fast diagnosis')
assert.ok(uploadViewSource.includes('本地模型 qwen3:8b'), 'upload page must expose the local model choice')
assert.ok(uploadViewSource.includes('DeepSeek API'), 'upload page must expose the deployment model choice')
assert.ok(uploadViewSource.includes('listFiles'), 'upload page must load previously uploaded files')
assert.ok(uploadViewSource.includes('历史文件'), 'upload page must show a historical file section')
assert.ok(uploadViewSource.includes('selectExistingFile'), 'upload page must allow selecting an existing file without re-uploading')

const clientSource = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
assert.ok(clientSource.includes("localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api'"), 'missing api base url default')

const workspaceSource = readFileSync(new URL('../src/state/workspace.ts', import.meta.url), 'utf8')
assert.ok(workspaceSource.includes("import { reactive } from 'vue'"), 'workspace must import reactive for runtime mount')
for (const key of ['fileId', 'fileName', 'taskId', 'workflowId', 'threadId', 'currentVersionId', 'newVersionId', 'versionNo', 'reviewBatchId', 'reportPath', 'enableAiAnalysis', 'modelProvider', 'modelName']) {
  assert.ok(workspaceSource.includes(key), `missing workspace key ${key}`)
}

const appShellSource = readFileSync(new URL('../src/components/AppShell.vue', import.meta.url), 'utf8')
for (const label of ['上传分析', '工作流', '建议审核', '版本管理', '报告']) {
  assert.ok(appShellSource.includes(label), `missing nav item ${label}`)
}
assert.ok(!appShellSource.includes("to: '/report/0'"), 'report nav must use current workspace version instead of /report/0')

for (const view of ['OverviewView', 'TreeView', 'DiagnosisView']) {
  assert.ok(routerSource.includes(`import ${view}`), `router must import ${view}`)
  assert.ok(routerSource.includes(`component: ${view}`), `router must mount ${view}`)
}
const evaluationSource = readFileSync(new URL('../src/components/EvaluationDashboard.vue', import.meta.url), 'utf8')
for (const label of ['Precision', 'Recall', 'F1', '危险动作漏拦截率', 'Model calls', 'Token', 'Cache hit', 'P95 latency', 'Triage']) assert.ok(evaluationSource.includes(label), `evaluation dashboard missing ${label}`)
for (const component of ['AgentRunProgress', 'AgentEventLog']) {
  assert.ok(workflowSource.includes(component), `workflow must use ${component}`)
}
for (const eventName of ['agent_step', 'agent_tool_completed', 'candidate_completed']) {
  assert.ok(workflowSource.includes(eventName), `workflow must consume ${eventName}`)
}
assert.ok(workflowSource.includes('cancelWorkflow'), 'workflow must expose safe cancellation')
for (const label of ['Model calls', 'Token', 'Wall time', 'Batch decision', 'Triage']) assert.ok(workflowSource.includes(label), `workflow budget missing ${label}`)
const triageSource = readFileSync(new URL('../src/views/TriageView.vue', import.meta.url), 'utf8')
for (const label of ['确认问题', '确认正常', '仍不确定', '检测器分歧']) assert.ok(triageSource.includes(label), `triage view missing ${label}`)

const reviewSource = readFileSync(new URL('../src/views/ReviewView.vue', import.meta.url), 'utf8')
const actionPreviewSource = readFileSync(new URL('../src/components/ActionPreview.vue', import.meta.url), 'utf8')
assert.ok(reviewSource.includes('ActionPreview'), 'review must render action preview')
assert.ok(reviewSource.includes('previewReviewBatch'), 'review must request server-side simulation')
assert.ok(actionPreviewSource.includes('执行前模拟'), 'action preview must explain simulation')

const progressSource = readFileSync(new URL('../src/components/AgentRunProgress.vue', import.meta.url), 'utf8')
for (const label of ['候选总数', '已处理', '发现问题', '正常', '不确定', '失败', '剩余']) {
  assert.ok(progressSource.includes(label), `agent progress must show ${label}`)
}

const diagnosisViewSource = readFileSync(new URL('../src/views/DiagnosisView.vue', import.meta.url), 'utf8')
for (const value of ['体系体检报告', '结构问题', '内容问题', '高风险问题', '综合评分', '问题原因', '检测依据', '建议动作']) {
  assert.ok(diagnosisViewSource.includes(value), `diagnosis report must display ${value}`)
}

const versionTableSource = readFileSync(new URL('../src/components/VersionTable.vue', import.meta.url), 'utf8')
assert.ok(versionTableSource.includes('type="checkbox"'), 'version table must allow selecting two versions for diff')

const versionsViewSource = readFileSync(new URL('../src/views/VersionsView.vue', import.meta.url), 'utf8')
assert.ok(versionsViewSource.includes('listFiles'), 'versions page must load files for file-scoped version management')
assert.ok(versionsViewSource.includes('selectedFileId'), 'versions page must maintain selected file context')
assert.ok(versionsViewSource.includes('orderedSelectedIds'), 'versions page must compare versions from older to newer')
for (const fn of ['loadDiff', 'doExport', 'doRollback']) {
  const sourceFromFunction = versionsViewSource.slice(versionsViewSource.indexOf(`async function ${fn}`))
  assert.ok(sourceFromFunction.includes('try {'), `${fn} must display API errors instead of failing silently`)
}

const reviewViewSource = readFileSync(new URL('../src/views/ReviewView.vue', import.meta.url), 'utf8')
assert.ok(reviewViewSource.slice(reviewViewSource.indexOf('onMounted')).includes('catch'), 'review batch loading must display API errors')
assert.ok(reviewViewSource.includes('resumeWorkflow'), 'review page must resume the interrupted LangGraph workflow')
assert.ok(reviewViewSource.includes('接受选中建议'), 'review page must expose an accept action')
assert.ok(reviewViewSource.includes('拒绝其余建议'), 'review page must expose a reject action')
assert.ok(reviewViewSource.includes('applyReviewDecision'), 'simplified diagnosis review must not require workflow resume')
assert.ok(!reviewViewSource.includes('editJson'), 'review page must not require users to type a JSON edits array')

const reviewApiSource = readFileSync(new URL('../src/api/reviews.ts', import.meta.url), 'utf8')
assert.ok(reviewApiSource.includes('/decision'), 'review api must expose decision endpoint')
assert.ok(reviewApiSource.includes('/execute'), 'review api must expose execute endpoint')

console.log('navigation contract checks passed')
