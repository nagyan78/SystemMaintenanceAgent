import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const packageJson = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
assert.equal(packageJson.scripts['test:contract'], 'node tests/navigation-contract.test.mjs')

const routerSource = readFileSync(new URL('../src/router/index.ts', import.meta.url), 'utf8')
for (const route of ['/upload', '/workflow/:taskId', '/versions', '/report/:versionId']) {
  assert.ok(routerSource.includes(route), `missing route ${route}`)
}

const workflowSource = readFileSync(new URL('../src/views/WorkflowView.vue', import.meta.url), 'utf8')
for (const step of ['parse_excel', 'build_tree', 'save_initial_version', 'index_vector', 'structure_diagnosis', 'diagnosis_planning', 'content_diagnosis', 'generate_suggestion', 'validate_action', 'execute_action', 'save_new_version', 'completed']) {
  assert.ok(workflowSource.includes(step), `missing workflow step ${step}`)
}
assert.ok(workflowSource.includes('QualityComparison'), 'workflow page must render quality comparison')
assert.ok(workflowSource.includes('continue_optimization'), 'workflow page must handle continue interrupts')
assert.ok(workflowSource.includes('继续优化'), 'workflow page must expose continue action')
assert.ok(workflowSource.includes('结束并生成报告'), 'workflow page must expose finish action')
assert.ok(workflowSource.includes('workflow-launch-backdrop'), 'workflow page must present an animated launch sheet')
assert.ok(workflowSource.includes('clearExpiredTask'), 'workflow page must clear an expired persisted task')
assert.ok(workflowSource.includes("router.replace('/upload')"), 'expired workflow must return to upload instead of polling forever')

const uploadViewSource = readFileSync(new URL('../src/views/UploadView.vue', import.meta.url), 'utf8')
assert.ok(uploadViewSource.includes('开始智能体分析'), 'upload page must let users inspect fields before starting workflow')
assert.ok(uploadViewSource.includes('listFiles'), 'upload page must load previously uploaded files')
assert.ok(uploadViewSource.includes('历史文件'), 'upload page must show a historical file section')
assert.ok(uploadViewSource.includes('selectExistingFile'), 'upload page must allow selecting an existing file without re-uploading')

const clientSource = readFileSync(new URL('../src/api/client.ts', import.meta.url), 'utf8')
assert.ok(clientSource.includes("localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api'"), 'missing api base url default')

const workspaceSource = readFileSync(new URL('../src/state/workspace.ts', import.meta.url), 'utf8')
assert.ok(workspaceSource.includes("import { reactive } from 'vue'"), 'workspace must import reactive for runtime mount')
for (const key of ['fileId', 'fileName', 'taskId', 'workflowId', 'threadId', 'workflowMode', 'baseVersionId', 'resultVersionId', 'currentVersionId', 'newVersionId', 'versionNo', 'evaluationBeforeId', 'evaluationAfterId', 'verification', 'round', 'maxRounds', 'reportPath']) {
  assert.ok(workspaceSource.includes(key), `missing workspace key ${key}`)
}

const appShellSource = readFileSync(new URL('../src/components/AppShell.vue', import.meta.url), 'utf8')
for (const label of ['上传与启动', '执行进度', '版本管理', '体系概览', '分类浏览', '诊断问题', '诊断报告']) {
  assert.ok(appShellSource.includes(label), `missing nav item ${label}`)
}
assert.ok(!appShellSource.includes("to: '/report/0'"), 'report nav must use current workspace version instead of /report/0')

for (const view of ['OverviewView', 'TreeView', 'DiagnosisView']) {
  assert.ok(routerSource.includes(`import ${view}`), `router must import ${view}`)
  assert.ok(routerSource.includes(`component: ${view}`), `router must mount ${view}`)
}

const overviewSource = readFileSync(new URL('../src/views/OverviewView.vue', import.meta.url), 'utf8')
assert.ok(overviewSource.includes('getOverview'), 'overview page must load live taxonomy metrics')
assert.ok(!overviewSource.includes('P1 占位'), 'overview page must not remain a placeholder')

const treeSource = readFileSync(new URL('../src/views/TreeView.vue', import.meta.url), 'utf8')
assert.ok(treeSource.includes('getTree'), 'tree page must load live taxonomy nodes')
assert.ok(treeSource.includes('搜索类目或路径'), 'tree page must expose a direct search field')

const diagnosisSource = readFileSync(new URL('../src/views/DiagnosisView.vue', import.meta.url), 'utf8')
assert.ok(diagnosisSource.includes('listIssues'), 'diagnosis page must load live issues')
assert.ok(diagnosisSource.includes('高风险'), 'diagnosis page must expose risk filtering')

const reportSource = readFileSync(new URL('../src/views/ReportView.vue', import.meta.url), 'utf8')
assert.ok(reportSource.includes('getReport'), 'report page must load a backend preview')
assert.ok(reportSource.includes('下载 Markdown'), 'report page must expose a download action')

const versionTableSource = readFileSync(new URL('../src/components/VersionTable.vue', import.meta.url), 'utf8')
assert.ok(versionTableSource.includes('type="checkbox"'), 'version table must allow selecting two versions for diff')

const versionsViewSource = readFileSync(new URL('../src/views/VersionsView.vue', import.meta.url), 'utf8')
assert.ok(versionsViewSource.includes('listFiles'), 'versions page must load files for file-scoped version management')
assert.ok(versionsViewSource.includes('selectedFileId'), 'versions page must maintain selected file context')
assert.ok(versionsViewSource.includes('orderedSelectedIds'), 'versions page must compare versions from older to newer')
assert.ok(versionsViewSource.includes('继续优化此版本'), 'versions page must start maintain mode from a selected version')
assert.ok(versionsViewSource.includes("mode: 'maintain'"), 'versions page must send maintain mode')
for (const fn of ['loadDiff', 'doExport', 'doRollback']) {
  const sourceFromFunction = versionsViewSource.slice(versionsViewSource.indexOf(`async function ${fn}`))
  assert.ok(sourceFromFunction.includes('try {'), `${fn} must display API errors instead of failing silently`)
}

assert.ok(!routerSource.includes('/review/'), 'review route must be removed')

const workflowApiSource = readFileSync(new URL('../src/api/workflows.ts', import.meta.url), 'utf8')
for (const token of ['base_version_id', 'result_version_id', 'interrupt_type', 'continue_optimization', 'affected_node_ids']) {
  assert.ok(workflowApiSource.includes(token), `workflow api missing ${token}`)
}

const qualityComparisonSource = readFileSync(new URL('../src/components/QualityComparison.vue', import.meta.url), 'utf8')
for (const token of ['available_dimensions', 'resolved_fingerprints', 'unresolved_fingerprints', 'introduced_fingerprints']) {
  assert.ok(qualityComparisonSource.includes(token), `quality comparison missing ${token}`)
}

console.log('navigation contract checks passed')
