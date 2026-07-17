import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const router = read('../src/router/index.ts')
const shell = read('../src/components/AppShell.vue')
const client = read('../src/api/client.ts')
const upload = read('../src/views/UploadView.vue')
const diagnosis = read('../src/views/DiagnosisView.vue')
const reports = read('../src/views/ReportView.vue')
const reviews = read('../src/views/ReviewsView.vue')
const evaluation = read('../src/views/EvaluationView.vue')
const versions = read('../src/views/VersionsView.vue')
const review = read('../src/views/ReviewView.vue')
const reviewCard = read('../src/components/SuggestionReviewCard.vue')
const comparison = read('../src/components/ActionComparison.vue')
const details = read('../src/components/SuggestionDetails.vue')
const editDialog = read('../src/components/SuggestionEditDialog.vue')
const cleanupDialog = read('../src/components/DataManagementDialog.vue')

for (const route of [
  '/upload', '/workflow/:taskId', '/workflows', '/reviews', '/review/:reviewBatchId',
  '/versions', '/diagnosis', '/diagnosis/:versionId', '/report', '/report/:versionId', '/evaluation',
]) assert.ok(router.includes(route), `missing route ${route}`)
assert.ok(router.includes("{ path: '/workflows', redirect: '/upload' }"), 'legacy workflows route must redirect to upload')
assert.ok(!router.includes("path: '/triage'"), 'triage route must not be user-visible')

for (const label of ['上传分析', '诊断结果', '建议审核', '版本管理', '报告']) {
  assert.ok(shell.includes(label), `missing nav item ${label}`)
}
assert.ok(!shell.includes("label: '工作流'"), 'workflow must not remain a standalone menu')
assert.ok(!shell.includes("label: '人工分流'"), 'triage must not remain a standalone menu')
assert.ok(shell.includes('statusText'), 'topbar context must be derived from the active route')

for (const sample of ['http://127.0.0.1:8000', "url.pathname = '/api'", "toLowerCase() === 'api'"]) {
  assert.ok(client.includes(sample), `API base normalization missing ${sample}`)
}
for (const kind of ['invalid_base', 'network', 'not_found', 'http']) {
  assert.ok(client.includes(kind), `API error kind missing ${kind}`)
}

assert.ok(upload.includes('listWorkflows'), 'upload page must query backend workflows')
for (const label of ['诊断任务', '上传文件名', '创建时间', '当前阶段', '真实进度', '问题数量', '审核状态', '当前可执行操作']) {
  assert.ok(upload.includes(label), `upload task center missing ${label}`)
}
assert.ok(upload.includes('进入建议审核'), 'waiting workflow must enter review')
assert.ok(upload.includes('查看完整报告'), 'verified workflow must expose its final report')
assert.ok(upload.includes('删除文件') && upload.includes('requestHistoryDelete'), 'historical files must expose safe deletion')
assert.ok(!upload.includes("router.push(`/workflow/"), 'new upload must remain on upload page')

assert.ok(reviews.includes('listReviewBatches'), 'review center must query backend batches')
assert.ok(reviews.includes('loading') && reviews.includes('error'), 'review center must distinguish loading/error/empty')
for (const action of ['选择全部待审核项', '通过选中修改', '驳回选中', '批量通过全部待审核项', '批量驳回全部待审核项', '批量暂不处理全部待审核项', '批量确认全部为误报', '执行修改']) {
  assert.ok(review.includes(action), `review page missing ${action}`)
}
for (const code of ['missing_parent', 'depth_exceeded', 'width_exceeded', 'synonym_format', 'naming_nonstandard', 'synonym_conflict', 'parent_child_redundancy', 'semantic_misplacement', 'synonym_overlap']) {
  assert.ok(review.includes(code), `review page missing stable issue category ${code}`)
}
assert.ok(review.includes(':disabled="!selectedIds.length || loading"'), 'selected review actions must enable from the real pending selection count')
assert.ok(review.includes('batch?.can_generate_preview') && review.includes('batch?.can_execute'), 'preview and execution controls must use backend capabilities')
assert.ok(review.includes('incompleteApprovalIds') && review.includes('approveExecutableOnly'), 'incomplete selected proposals must offer a recovery choice')
assert.ok(review.includes('executeReviewBatch'), 'review page must execute approved suggestions')
for (const component of ['SuggestionReviewCard', 'SuggestionEditDialog']) assert.ok(review.includes(component), `review page missing ${component}`)
for (const label of ['通过修改', '编辑后通过', '驳回建议', '展开详情', '完整路径', '影响范围']) {
  assert.ok(reviewCard.includes(label), `review card missing ${label}`)
}
assert.ok(!reviewCard.includes('JSON.stringify'), 'review card must not render raw JSON')
for (const label of ['原名称', '新名称', '原同义词', '原父节点', '被合并节点', '历史建议未记录该信息']) {
  assert.ok(comparison.includes(label), `comparison missing ${label}`)
}
for (const label of ['完整证据', '判断理由', '格式化动作字段', 'work_item_id', 'analysis_run_id']) {
  assert.ok(details.includes(label), `details missing ${label}`)
}
assert.ok(!details.includes('JSON.stringify'), 'details must not render action payload as JSON')
assert.ok(editDialog.includes('保存并通过修改'), 'edit dialog missing save action')

assert.ok(diagnosis.includes('route.params.versionId'), 'diagnosis must be route-version driven')
assert.ok(diagnosis.includes('选择要查看的版本'), 'diagnosis without a version must offer a selector')
for (const message of ['诊断尚未完成', '该版本不存在']) assert.ok(diagnosis.includes(message), `diagnosis missing state ${message}`)
assert.ok(!diagnosis.includes('state.taskId'), 'diagnosis must not infer a version from taskId')
for (const field of ['可信诊断覆盖漏斗', 'rule_scanned_nodes', 'deep_diagnosed_count', 'tokens_used', '问题来源']) {
  assert.ok(diagnosis.includes(field), `diagnosis coverage UI missing ${field}`)
}

assert.ok(reports.includes('listReports'), 'report page must query report resources first')
assert.ok(!reports.includes('generateReport'), 'preview failure must not generate a report')
for (const type of ['诊断草稿', '部分完成报告', '失败报告', '最终报告', '历史诊断报告', '尚未生成']) {
  assert.ok(reports.includes(type), `report page missing ${type}`)
}

assert.ok(evaluation.includes('route.query.version_id'), 'evaluation must support direct URL version context')
assert.ok(evaluation.includes('getVersionQuality'), 'evaluation must query version quality')
assert.ok(versions.includes('listFiles') && versions.includes('listVersions'), 'version management must query backend resources')
for (const field of ['generatePreview', 'database_backup_path', 'filesystem_paths', 'expectedConfirmation', 'executeConfirmed']) {
  assert.ok(cleanupDialog.includes(field), `two-phase cleanup UI missing ${field}`)
}

console.log('navigation contract checks passed')
