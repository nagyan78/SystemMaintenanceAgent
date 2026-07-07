import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const packageJson = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
assert.equal(packageJson.scripts['test:contract'], 'node tests/navigation-contract.test.mjs')

const routerSource = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
for (const route of ['/upload', '/workflow/:taskId', '/review/:reviewBatchId', '/versions', '/report/:versionId']) {
  assert.ok(routerSource.includes(route), `missing route ${route}`)
}

const workflowSource = readFileSync(new URL('../src/views/WorkflowView.vue', import.meta.url), 'utf8')
for (const step of ['parse_excel', 'build_tree', 'save_initial_version', 'index_vector', 'structure_diagnosis', 'diagnosis_planning', 'content_diagnosis', 'generate_suggestion', 'human_review', 'validate_action', 'execute_action', 'save_new_version', 'completed']) {
  assert.ok(workflowSource.includes(step), `missing workflow step ${step}`)
}

const uploadViewSource = readFileSync(new URL('../src/views/UploadView.vue', import.meta.url), 'utf8')
assert.ok(uploadViewSource.includes('开始智能体分析'), 'upload page must let users inspect fields before starting workflow')
assert.ok(uploadViewSource.includes('listFiles'), 'upload page must load previously uploaded files')
assert.ok(uploadViewSource.includes('历史文件'), 'upload page must show a historical file section')
assert.ok(uploadViewSource.includes('selectExistingFile'), 'upload page must allow selecting an existing file without re-uploading')

const clientSource = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
assert.ok(clientSource.includes("localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api'"), 'missing api base url default')

const workspaceSource = readFileSync(new URL('../src/state/workspace.ts', import.meta.url), 'utf8')
assert.ok(workspaceSource.includes("import { reactive } from 'vue'"), 'workspace must import reactive for runtime mount')
for (const key of ['fileId', 'fileName', 'taskId', 'workflowId', 'threadId', 'currentVersionId', 'newVersionId', 'versionNo', 'reviewBatchId', 'reportPath']) {
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
assert.ok(reviewViewSource.includes('applyReviewDecision'), 'review page must persist approve/reject decisions without resuming a completed workflow')
assert.ok(reviewViewSource.includes('executeReviewBatch'), 'review page must execute approved suggestions and generate a new version')
assert.ok(reviewViewSource.includes('执行已批准'), 'review page must expose an explicit execute-approved action')
assert.ok(!reviewViewSource.includes('editJson'), 'review page must not require users to type a JSON edits array')
assert.ok(!reviewViewSource.includes('resumeWorkflow'), 'review page must not depend on workflow resume for repeated review execution')

const reviewApiSource = readFileSync(new URL('../src/api/reviews.ts', import.meta.url), 'utf8')
assert.ok(reviewApiSource.includes('/decision'), 'review api must expose decision endpoint')
assert.ok(reviewApiSource.includes('/execute'), 'review api must expose execute endpoint')

console.log('navigation contract checks passed')
