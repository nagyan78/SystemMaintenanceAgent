import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const router = read('../src/router/index.ts')
const shell = read('../src/components/AppShell.vue')
const client = read('../src/api/client.ts')
const upload = read('../src/views/UploadView.vue')
const workflow = read('../src/views/WorkflowView.vue')
const tree = read('../src/views/TreeView.vue')
const taxonomyApi = read('../src/api/taxonomy.ts')
const diagnosis = read('../src/views/DiagnosisView.vue')
const reports = read('../src/views/ReportView.vue')
const versions = read('../src/views/VersionsView.vue')

for (const route of ['/upload', '/workflow/:taskId', '/versions', '/diagnosis', '/diagnosis/:versionId', '/report', '/report/:versionId', '/tree/:versionId']) {
  assert.ok(router.includes(route), `missing route ${route}`)
}
assert.ok(router.includes("{ path: '/reviews', redirect: '/versions' }"), 'legacy review center must redirect away from manual review')
assert.ok(router.includes("{ path: '/review/:reviewBatchId', redirect: '/versions' }"), 'legacy review detail must redirect away from manual review')

for (const label of ['上传与启动', '执行进度', '版本管理', '体系概览', '分类浏览', '诊断问题', '诊断报告']) {
  assert.ok(shell.includes(label), `missing navigation item ${label}`)
}
assert.ok(!shell.includes("label: '建议审核'"), 'manual review must not remain in primary navigation')
assert.ok(shell.includes('AI 自动审核'), 'workflow description must expose automatic AI review')

for (const sample of ['http://127.0.0.1:8000', "url.pathname = '/api'", "toLowerCase() === 'api'"]) {
  assert.ok(client.includes(sample), `API base normalization missing ${sample}`)
}
for (const kind of ['invalid_base', 'network', 'not_found', 'http']) assert.ok(client.includes(kind), `API error kind missing ${kind}`)
assert.ok(client.includes('normalizedPath.slice(basePath.length)'), 'API URL builder must avoid duplicate /api prefixes')
assert.ok(reports.includes('apiUrl(preview.value.download_url)'), 'report downloads must use normalized API URLs')
assert.ok(versions.includes('apiUrl(result.download_url)'), 'version exports must use normalized API URLs')

for (const token of ['AI 自动审核', '无需人工审批', '开始 AI 自动维护', 'enable_ai_analysis: true', '预览分类树', 'listWorkflows']) {
  assert.ok(upload.includes(token), `automatic upload workflow missing ${token}`)
}
assert.ok(!upload.includes('进入建议审核'), 'upload page must not route users into manual review')
assert.ok(upload.includes('router.push(`/workflow/${workflow.task_id}`)'), 'new automatic task must open live workflow progress')

for (const stage of ['规则诊断', 'AI 分析', 'AI 审核', '校验执行', '保存复诊', '最终报告']) {
  assert.ok(workflow.includes(stage), `automatic workflow stage missing ${stage}`)
}
for (const token of ['workflow-modal-backdrop', 'isProgressModalDismissed', '预览分类树', "value.includes('review')"]) {
  assert.ok(workflow.includes(token), `workflow progress experience missing ${token}`)
}
assert.ok(!workflow.includes("status === 'waiting_review' ? 'draft'"), 'workflow must not treat review as the normal report path')

assert.ok(taxonomyApi.includes('/taxonomy/tree?version_id='), 'tree preview must query taxonomy tree API')
assert.ok(taxonomyApi.includes('/taxonomy/search?version_id='), 'tree preview must query taxonomy search API')
for (const token of ['分类树预览', 'getTreeLevel', 'searchTaxonomyNodes', 'expanded', '浏览自动维护结果']) {
  assert.ok(tree.includes(token), `classification tree preview missing ${token}`)
}

assert.ok(diagnosis.includes('route.params.versionId'), 'diagnosis must be route-version driven')
assert.ok(diagnosis.includes('预览分类树'), 'diagnosis must link to the maintained tree preview')
assert.ok(!diagnosis.includes('审核问题并修改'), 'diagnosis must not expose manual review')
assert.ok(reports.includes('listReports'), 'report page must query persisted report resources')
assert.ok(!reports.includes('generateReport'), 'report preview failure must not generate a report')
assert.ok(versions.includes('listFiles') && versions.includes('listVersions'), 'version management must query backend resources')

console.log('navigation contract checks passed')
