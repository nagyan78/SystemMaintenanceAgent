<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div><p class="eyebrow">审核批次 {{ reviewBatchId }}</p><h2>建议审核</h2></div>
          <span class="badge">{{ batch?.status || '-' }} / {{ batch?.execution_status || '-' }}</span>
        </div>
        <div class="review-stats">
          <span class="badge">待审核 {{ counts.pending + counts.edited }}</span>
          <span class="badge" data-tone="success">通过 {{ counts.approved }}</span>
          <span class="badge" data-tone="danger">驳回 {{ counts.rejected }}</span>
          <span class="badge" data-tone="warning">暂不处理/误报 {{ counts.deferred }}</span>
          <span class="badge" data-tone="success">已执行 {{ counts.executed }}</span>
        </div>
        <div v-if="legacyWarning" class="legacy-warning">
          <span>该批次包含旧版或不完整建议，建议使用当前规则重新生成。</span>
          <button class="button secondary" :disabled="loading" @click="regenerate">重新生成不完整建议</button>
        </div>
        <div class="type-filter" aria-label="问题分类筛选">
          <article v-for="category in categories" :key="category.key" :class="{ active: selectedCategory === category.key }" @click="selectedCategory = category.key">
            <button class="type-title" type="button">{{ category.label }}</button>
            <div class="type-counts"><span>总数 {{ category.total }}</span><span>待审核 {{ category.pending }}</span><span>通过 {{ category.approved }}</span><span>驳回 {{ category.rejected }}</span><span>暂不处理 {{ category.deferred }}</span></div>
            <div v-if="category.key !== 'all'" class="type-actions" @click.stop>
              <button type="button" @click="selectPending(category.key)">选择该类型全部待审核项</button>
              <button type="button" @click="clearCategorySelection(category.key)">取消选择</button>
              <button type="button" @click="requestCategoryDecision(category.key, 'approve')">通过全部</button>
              <button type="button" @click="requestCategoryDecision(category.key, 'reject')">驳回全部</button>
              <button type="button" @click="requestCategoryDecision(category.key, 'confirm_no_action')">标记误报</button>
              <button type="button" @click="requestCategoryDecision(category.key, 'uncertain')">暂不处理</button>
            </div>
          </article>
        </div>
        <div class="action-row">
          <button class="button primary" :disabled="batch?.status === 'executed' || loading || !suggestions.length" @click="autoComplete">自动完成审核</button>
          <button class="button secondary" :disabled="!openIds.length || loading" @click="selectAllPending">选择全部待审核项</button>
          <button class="button primary" :disabled="!selectedIds.length || loading" @click="decideSelected('approve')">通过选中修改</button>
          <button class="button danger" :disabled="!selectedIds.length || loading" @click="requestDecision(selectedIds, 'reject', '选中项')">驳回选中</button>
          <button class="button secondary" :disabled="!openIds.length || loading" @click="requestDecision(openIds, 'approve', '全部问题')">批量通过全部待审核项</button>
          <button class="button secondary" :disabled="!openIds.length || loading" @click="requestDecision(openIds, 'reject', '全部问题')">批量驳回全部待审核项</button>
          <button class="button secondary" :disabled="!openIds.length || loading" @click="requestDecision(openIds, 'uncertain', '全部问题')">批量暂不处理全部待审核项</button>
          <button class="button secondary" :disabled="!openIds.length || loading" @click="requestDecision(openIds, 'confirm_no_action', '全部问题')">批量确认全部为误报</button>
          <button class="button secondary" :disabled="!selectedIds.length" @click="loadPreview">预览选中动作</button>
          <button class="button secondary" :disabled="loading" @click="showManual = !showManual">人工添加修改</button>
        </div>
        <p class="review-hint">{{ selectionHint }}</p>

        <form v-if="showManual" class="manual-form" @submit.prevent="addManual">
          <label>问题 ID（可选，不填则创建人工问题）<input v-model.number="manualForm.issue_id" type="number" /></label>
          <label>动作<select v-model="manualForm.action_type"><option value="rename_node">修改节点名称</option><option value="update_synonyms">编辑同义词</option><option value="move_node">移动节点</option><option value="merge_node">合并节点</option><option value="review_only">暂不处理/人工判断</option></select></label>
          <label>节点 ID<input v-model.number="manualForm.target_node_id" type="number" /></label>
          <template v-if="manualForm.action_type === 'rename_node'"><label>原名称<input v-model="manualForm.old_name" required /></label><label>新名称<input v-model="manualForm.new_name" required /></label></template>
          <template v-if="manualForm.action_type === 'update_synonyms'"><label>原同义词<input v-model="manualForm.current_synonyms" /></label><label>删除内容<input v-model="manualForm.remove_synonyms" /></label><label>新增内容<input v-model="manualForm.add_synonyms" /></label></template>
          <template v-if="manualForm.action_type === 'move_node'"><label>原父节点 ID<input v-model.number="manualForm.old_parent_id" type="number" required /></label><label>新父节点 ID<input v-model.number="manualForm.new_parent_id" type="number" required /></label><label>原父节点名称<input v-model="manualForm.old_parent_name" required /></label><label>新父节点名称<input v-model="manualForm.new_parent_name" required /></label><label>原路径<input v-model="manualForm.old_path" required /></label><label>新父节点完整路径<input v-model="manualForm.new_parent_path" required /></label><label>修改后完整路径<input v-model="manualForm.new_path" required /></label><label>选择依据<input v-model="manualForm.selection_basis" required /></label></template>
          <template v-if="manualForm.action_type === 'merge_node'"><label>源节点 ID<input v-model.number="manualForm.source_node_id" type="number" required /></label><label>保留节点 ID<input v-model.number="manualForm.target_node_id" type="number" required /></label><label>等价证据<input v-model="manualForm.equivalence_evidence" required /></label><label>迁移子节点数<input v-model.number="manualForm.affected_child_count" type="number" required /></label><label>影响引用数<input v-model.number="manualForm.reference_count" type="number" required /></label></template>
          <label>原因<input v-model="manualForm.reason" required /></label>
          <label>建议说明<input v-model="manualForm.suggestion" required /></label>
          <button class="button primary" type="submit">加入审核批次</button>
        </form>
      </section>

      <section class="suggestion-list" aria-label="本次诊断的全部建议">
        <SuggestionReviewCard
          v-for="item in filteredSuggestions" :key="item.id" :suggestion="item"
          :selected="selectedIds.includes(item.id)" :busy="loading"
          @toggle="toggle(item.id)" @approve="decideOne(item.id, 'approve')"
          @edit="beginEdit(item)" @reject="decideOne(item.id, 'reject')"
          @uncertain="decideOne(item.id, 'uncertain')"
          @false-positive="decideOne(item.id, 'confirm_no_action')"
        />
      </section>

      <ActionPreview v-if="preview" :preview="preview" />
      <section class="card">
        <h2>执行前预览</h2>
        <p class="lead">审核全部完成后必须生成组合执行预览。任何审核或编辑变化都会使旧预览失效。</p>
        <div class="action-row follow-up-actions">
          <button class="button secondary" :disabled="!batch?.can_generate_preview || loading" @click="loadExecutionPreview">生成执行预览</button>
          <button class="button primary" :disabled="!batch?.can_execute || !executionPreview?.valid || loading" @click="execute">执行修改</button>
          <RouterLink v-if="batch" class="button secondary" :to="`/report/${batch.version_id}?type=draft`">查看诊断草稿</RouterLink>
          <RouterLink v-if="batch?.new_version_id" class="button secondary" :to="`/report/${batch.new_version_id}?type=final`">查看最终报告</RouterLink>
          <RouterLink class="button secondary" to="/reviews">返回审核中心</RouterLink>
        </div>
        <p v-if="batch?.blocked_reason" class="review-hint">{{ batch.blocked_reason }}</p>
        <p v-if="message" class="lead">{{ message }}</p><p v-if="error" class="error">{{ error }}</p>
      </section>
    </div>
    <SuggestionEditDialog :show="Boolean(editingSuggestion)" :suggestion="editingSuggestion" @close="editingSuggestion = null" @save="approveEdit" />
    <Modal :show="Boolean(confirmRequest)" title="确认批量审核" @close="confirmRequest = null">
      <div v-if="confirmRequest" class="confirm-content">
        <p><strong>问题类型：</strong>{{ confirmRequest.label }}</p><p><strong>影响数量：</strong>{{ confirmRequest.ids.length }}</p>
        <p><strong>可执行建议数：</strong>{{ executableCount(confirmRequest.ids) }}</p><p><strong>无修改方案建议数：</strong>{{ confirmRequest.ids.length - executableCount(confirmRequest.ids) }}</p>
        <div class="action-row"><button class="button primary" @click="confirmDecision">确认</button><button class="button secondary" @click="confirmRequest = null">取消</button></div>
      </div>
    </Modal>
    <Modal :show="Boolean(incompleteApprovalIds.length)" title="部分建议缺少修改方案" @close="incompleteApprovalIds = []">
      <p>以下建议需要人工补充或重新生成修改方案：{{ incompleteApprovalIds.join('、') }}</p>
      <div class="action-row"><button class="button primary" @click="regenerateMissing">重新生成这些建议</button><button class="button secondary" :disabled="!selectedExecutableIds.length" @click="approveExecutableOnly">仅通过有完整动作的建议</button><button class="button secondary" @click="incompleteApprovalIds = []">取消</button></div>
    </Modal>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import ActionPreview from '../components/ActionPreview.vue'
import SuggestionReviewCard from '../components/SuggestionReviewCard.vue'
import SuggestionEditDialog from '../components/SuggestionEditDialog.vue'
import Modal from '../components/Modal.vue'
import { applyReviewDecision, autoCompleteReview, createExecutionPreview, createManualSuggestions, executeReviewBatch, getReviewBatch, previewReviewBatch, regenerateReviewBatch } from '../api/reviews'
import type { ActionPreviewResult, ExecutionPreviewResult, ReviewBatchSummary, ReviewDecisionRequest, SuggestionRecord } from '../api/reviews'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const reviewBatchId = String(route.params.reviewBatchId)
const { patch } = useWorkspace()
const suggestions = ref<SuggestionRecord[]>([])
const batch = ref<ReviewBatchSummary | null>(null)
const selectedIds = ref<number[]>([])
const loading = ref(false), error = ref(''), message = ref('')
const preview = ref<ActionPreviewResult | ExecutionPreviewResult | null>(null)
const executionPreview = ref<ExecutionPreviewResult | null>(null)
const editingSuggestion = ref<SuggestionRecord | null>(null)
const showManual = ref(false)
const legacyWarning = ref(false)
const selectedCategory = ref('all')
const incompleteApprovalIds = ref<number[]>([])
const confirmRequest = ref<{ ids: number[]; decision: ReviewDecisionRequest['decision']; label: string } | null>(null)
const manualForm = ref<Record<string, any>>({ action_type: 'rename_node', risk_level: 'medium', reason: '', suggestion: '' })
const counts = computed(() => suggestions.value.reduce((result, item) => {
  result[item.status] = (result[item.status] || 0) + 1
  return result
}, { pending: 0, edited: 0, approved: 0, rejected: 0, deferred: 0, executed: 0, failed: 0 } as Record<string, number>))
const openIds = computed(() => suggestions.value.filter(item => ['pending', 'edited'].includes(item.status)).map(item => item.id))
const executableOpenIds = computed(() => suggestions.value.filter(item => ['pending', 'edited'].includes(item.status) && item.is_executable).map(item => item.id))
const selectedExecutableIds = computed(() => selectedIds.value.filter(id => executableOpenIds.value.includes(id)))

const categoryDefinitions = [
  ['missing_parent', '父节点缺失', ['missing_parent']],
  ['depth_exceeded', '层级过深', ['depth_exceeded', 'excessive_depth']],
  ['width_exceeded', '节点过宽', ['width_exceeded', 'excessive_width']],
  ['synonym_format', '同义词格式错误', ['synonym_format']],
  ['naming_nonstandard', '节点命名不规范', ['naming_nonstandard']],
  ['synonym_conflict', '同义词语义冲突', ['synonym_conflict']],
  ['parent_child_redundancy', '父子命名重复', ['parent_child_redundancy']],
  ['semantic_misplacement', '父子语义不匹配', ['semantic_misplacement']],
  ['synonym_overlap', '父子同义词重叠', ['synonym_overlap']],
] as const
const knownCodes = new Set<string>(categoryDefinitions.flatMap(item => [...item[2]]))
function issueCode(item: SuggestionRecord) { return item.issue?.issue_type_code || 'unknown' }
function categoryMatches(item: SuggestionRecord, key: string) {
  if (key === 'all') return true
  if (key === 'other') return !knownCodes.has(issueCode(item))
  const definition = categoryDefinitions.find(item => item[0] === key)
  return Boolean(definition && (definition[2] as readonly string[]).includes(issueCode(item)))
}
function categoryStats(key: string, label: string) {
  const items = suggestions.value.filter(item => categoryMatches(item, key))
  const count = (statuses: string[]) => items.filter(item => statuses.includes(item.status)).length
  return { key, label, total: items.length, pending: count(['pending', 'edited']), approved: count(['approved']), rejected: count(['rejected']), deferred: count(['deferred']) }
}
const categories = computed(() => [
  categoryStats('all', '全部'),
  ...categoryDefinitions.map(item => categoryStats(item[0], item[1])),
  categoryStats('other', '其他'),
])
const filteredSuggestions = computed(() => suggestions.value.filter(item => categoryMatches(item, selectedCategory.value)))
const selectionHint = computed(() => {
  if (!selectedIds.value.length) return '尚未选择待审核建议。'
  const missing = selectedIds.value.length - selectedExecutableIds.value.length
  return missing ? `已选择 ${selectedIds.value.length} 条，其中 ${missing} 条缺少可执行修改方案；点击通过后可选择重新生成或仅通过完整建议。` : `已选择 ${selectedIds.value.length} 条，均具有完整修改动作。`
})

function toggle(id: number) { if (openIds.value.includes(id)) selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id] }
async function load() {
  const data = await getReviewBatch(reviewBatchId)
  suggestions.value = data.suggestions; batch.value = data.batch || null; selectedIds.value = []
  legacyWarning.value = Boolean(data.legacy_warning)
  executionPreview.value = data.execution_preview || null
  if (executionPreview.value) preview.value = executionPreview.value
  patch({ reviewBatchId })
}
async function submit(payload: ReviewDecisionRequest) {
  loading.value = true; error.value = ''; message.value = ''
  try { await applyReviewDecision(reviewBatchId, payload); await load(); message.value = '审核结论已保存，旧执行预览已失效。' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '提交失败' }
  finally { loading.value = false }
}
async function autoComplete() {
  const executable = suggestions.value.filter(item => item.is_executable && ['pending', 'edited', 'deferred'].includes(item.status)).length
  const ignored = suggestions.value.filter(item => !item.is_executable && ['pending', 'edited', 'deferred'].includes(item.status)).length
  if (!window.confirm(`将通过 ${executable} 条完整修改，并忽略 ${ignored} 条无法可靠修改的建议。是否继续？`)) return
  loading.value = true; error.value = ''; message.value = ''
  try {
    const result = await autoCompleteReview(reviewBatchId)
    await load()
    message.value = `审核完成：通过 ${result.approved_ids.length} 条，忽略 ${result.ignored_ids.length} 条。`
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '自动完成审核失败' }
  finally { loading.value = false }
}
function payloadFor(ids: number[], decision: ReviewDecisionRequest['decision']): ReviewDecisionRequest {
  return { decision, approved_suggestion_ids: decision === 'approve' ? ids : [], rejected_suggestion_ids: decision === 'reject' ? ids : [], confirmed_without_action_suggestion_ids: decision === 'confirm_no_action' ? ids : [], uncertain_suggestion_ids: decision === 'uncertain' ? ids : [], edits: [], operator: 'local_user', reject_reason: decision === 'reject' ? '人工驳回建议' : null }
}
function decideOne(id: number, decision: ReviewDecisionRequest['decision']) { return submit(payloadFor([id], decision)) }
function executableCount(ids: number[]) { return ids.filter(id => suggestions.value.find(item => item.id === id)?.is_executable).length }
function selectAllPending() { selectedIds.value = [...openIds.value] }
function pendingIdsForCategory(key: string) { return suggestions.value.filter(item => categoryMatches(item, key) && ['pending', 'edited'].includes(item.status)).map(item => item.id) }
function selectPending(key: string) { selectedIds.value = Array.from(new Set([...selectedIds.value, ...pendingIdsForCategory(key)])) }
function clearCategorySelection(key: string) { const ids = new Set(pendingIdsForCategory(key)); selectedIds.value = selectedIds.value.filter(id => !ids.has(id)) }
function requestCategoryDecision(key: string, decision: ReviewDecisionRequest['decision']) {
  const category = categories.value.find(item => item.key === key)
  requestDecision(pendingIdsForCategory(key), decision, category?.label || key)
}
function requestDecision(ids: number[], decision: ReviewDecisionRequest['decision'], label: string) {
  const pending = ids.filter(id => openIds.value.includes(id))
  if (!pending.length) return
  confirmRequest.value = { ids: pending, decision, label }
}
function decideSelected(decision: 'approve' | 'reject') {
  if (decision === 'approve') {
    const missing = selectedIds.value.filter(id => !selectedExecutableIds.value.includes(id))
    if (missing.length) { incompleteApprovalIds.value = missing; return }
  }
  requestDecision(selectedIds.value, decision, '选中项')
}
async function confirmDecision() {
  const request = confirmRequest.value
  if (!request) return
  confirmRequest.value = null
  await submit(payloadFor(request.ids, request.decision))
}
async function approveExecutableOnly() {
  const ids = [...selectedExecutableIds.value]
  incompleteApprovalIds.value = []
  if (ids.length) requestDecision(ids, 'approve', '选中项中的完整建议')
}
async function regenerateMissing() { incompleteApprovalIds.value = []; await regenerate() }
function beginEdit(item: SuggestionRecord) { editingSuggestion.value = item }
async function approveEdit(item: SuggestionRecord) {
  const suggestion: Record<string, unknown> = { ...item, action_payload: { ...item.action_payload } }
  for (const key of ['id', 'review_batch_id', 'issue', 'work_item_id', 'analysis_run_id', 'change_preview', 'consistency_status', 'consistency_reason', 'is_manual']) delete suggestion[key]
  editingSuggestion.value = null
  await submit({ ...payloadFor([item.id], 'edit'), approved_suggestion_ids: [item.id], edits: [{ suggestion_id: item.id, suggestion }] })
}
async function loadPreview() { preview.value = await previewReviewBatch(reviewBatchId, selectedIds.value) }
async function loadExecutionPreview() {
  loading.value = true; error.value = ''
  try { executionPreview.value = await createExecutionPreview(reviewBatchId); preview.value = executionPreview.value; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '执行预览失败' }
  finally { loading.value = false }
}
function terms(value: unknown) { return String(value || '').replaceAll('，', ',').split(',').map(item => item.trim()).filter(Boolean) }
async function addManual() {
  loading.value = true; error.value = ''
  try {
    const form = manualForm.value, actionPayload: Record<string, unknown> = {}
    for (const key of ['old_parent_name', 'new_parent_name', 'old_path', 'new_parent_path', 'new_path', 'selection_basis', 'source_node_id', 'target_node_id', 'equivalence_evidence', 'affected_child_count', 'reference_count']) if (form[key] !== undefined && form[key] !== '') actionPayload[key] = form[key]
    if (form.action_type === 'rename_node') actionPayload.new_name = form.new_name
    if (form.action_type === 'update_synonyms') { actionPayload.current_synonyms = terms(form.current_synonyms); actionPayload.synonyms_to_remove = terms(form.remove_synonyms); actionPayload.synonyms_to_add = terms(form.add_synonyms) }
    if (form.action_type === 'review_only') actionPayload.no_change_reason = form.reason
    await createManualSuggestions(reviewBatchId, [{ issue_id: form.issue_id, action_type: form.action_type, target_node_id: form.target_node_id || null, old_parent_id: form.old_parent_id || null, new_parent_id: form.new_parent_id || null, old_name: form.old_name || null, new_name: form.new_name || null, action_payload: actionPayload, reason: form.reason, suggestion: form.suggestion, risk_level: form.risk_level || 'medium', confidence: 1 }])
    showManual.value = false; manualForm.value = { action_type: 'rename_node', risk_level: 'medium', reason: '', suggestion: '' }; await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '人工建议创建失败' }
  finally { loading.value = false }
}
async function execute() {
  loading.value = true; error.value = ''
  try {
    const result = await executeReviewBatch(reviewBatchId); message.value = `已生成 ${result.new_version_no}`
    if (result.new_version_id) patch({ newVersionId: result.new_version_id, currentVersionId: result.new_version_id, reportPath: result.report_path || null })
    await load()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '执行失败' }
  finally { loading.value = false }
}
async function regenerate() {
  loading.value = true; error.value = ''
  try { const result = await regenerateReviewBatch(reviewBatchId); window.location.assign(`/review/${result.review_batch_id}`) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '重新生成失败' }
  finally { loading.value = false }
}
onMounted(() => load().catch(cause => { error.value = cause instanceof Error ? cause.message : '加载失败' }))
</script>

<style scoped>
.suggestion-list { display:grid; gap:14px; min-width:0; }
.follow-up-actions { margin-top:16px; }
.manual-form { margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; padding:16px; border:1px solid var(--line); border-radius:14px; }
.manual-form label { display:grid; gap:5px; font-size:12px; }
.manual-form input,.manual-form select { padding:10px; border:1px solid var(--line); border-radius:9px; }
.legacy-warning { display:flex; justify-content:space-between; gap:12px; align-items:center; margin:14px 0; padding:12px; border:1px solid #d97706; border-radius:12px; background:rgba(217,119,6,.08); }
.review-hint { margin:12px 0 0; color:#8a5b00; font-size:13px; }
.type-filter { display:grid; gap:8px; margin:14px 0; }
.type-filter article { padding:10px 12px; border:1px solid var(--line); border-radius:12px; cursor:pointer; }
.type-filter article.active { border-color:var(--primary); background:rgba(37,99,235,.05); }
.type-title { border:0; background:transparent; font-weight:700; cursor:pointer; }
.type-counts,.type-actions { display:flex; gap:10px; flex-wrap:wrap; margin-top:6px; font-size:12px; }
.type-actions button { border:0; background:transparent; color:var(--primary); cursor:pointer; padding:2px 0; }
.confirm-content { display:grid; gap:8px; }
.confirm-content p { margin:0; }
</style>
