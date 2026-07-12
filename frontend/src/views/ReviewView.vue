<template>
  <AppShell>
    <div class="page-stack">
      <SuggestionTable :title="`Review batch ${reviewBatchId}`" :suggestions="suggestions" :selected-ids="selectedIds" @toggle="toggle" />
      <ActionPreview v-if="preview" :preview="preview" />
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">人工审核</p>
            <h2>分批处理建议</h2>
          </div>
          <span class="badge">{{ selectedIds.length }} selected</span>
        </div>
        <div class="review-stats">
          <span class="badge" data-tone="warning">待审核 {{ statusCounts.pending + statusCounts.edited }}</span>
          <span class="badge" data-tone="success">已批准 {{ statusCounts.approved }}</span>
          <span class="badge" data-tone="success">已执行 {{ statusCounts.executed }}</span>
          <span class="badge" data-tone="danger">失败 {{ statusCounts.failed }}</span>
          <span class="badge">已拒绝 {{ statusCounts.rejected }}</span>
        </div>
        <div class="action-row">
          <button class="button primary" :disabled="loading || selectedIds.length === 0" @click="applyDecision('approve')">接受选中建议</button>
          <button class="button secondary" :disabled="loading || selectedIds.length === 0" @click="loadPreview">预览选中动作</button>
          <button class="button secondary" :disabled="loading || statusCounts.pending + statusCounts.edited === 0" @click="applyDecision('reject')">拒绝其余建议</button>
          <RouterLink v-if="taskId" class="button secondary" :to="`/workflow/${taskId}`">查看工作流</RouterLink>
          <RouterLink class="button secondary" :to="state.fileId ? `/versions?file_id=${state.fileId}` : '/versions'">查看版本</RouterLink>
          <RouterLink v-if="currentReportVersionId" class="button secondary" :to="`/report/${currentReportVersionId}`">查看报告</RouterLink>
        </div>
        <p v-if="message" class="lead">{{ message }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import SuggestionTable from '../components/SuggestionTable.vue'
import ActionPreview from '../components/ActionPreview.vue'
import { applyReviewDecision, getReviewBatch, previewReviewBatch } from '../api/reviews'
import type { ActionPreviewResult, SuggestionRecord } from '../api/reviews'
import { resumeWorkflow } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const router = useRouter()
const { state, patch } = useWorkspace()
const reviewBatchId = String(route.params.reviewBatchId)
const taskId = String(route.query.task_id || state.taskId || '')
const suggestions = ref<SuggestionRecord[]>([])
const selectedIds = ref<number[]>([])
const loading = ref(false)
const error = ref('')
const message = ref('')
const preview = ref<ActionPreviewResult | null>(null)
const currentReportVersionId = computed(() => state.newVersionId || state.currentVersionId)
const statusCounts = computed(() => suggestions.value.reduce(
  (counts, item) => {
    counts[item.status] = (counts[item.status] || 0) + 1
    return counts
  },
  { pending: 0, edited: 0, approved: 0, executed: 0, failed: 0, rejected: 0 } as Record<string, number>,
))

function isSelectable(item: SuggestionRecord) {
  return ['pending', 'edited'].includes(item.status)
}

function toggle(id: number) {
  const item = suggestions.value.find(value => value.id === id)
  if (!item || !isSelectable(item)) return
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter(value => value !== id)
    : [...selectedIds.value, id]
}

async function loadPreview() {
  loading.value = true
  error.value = ''
  try { preview.value = await previewReviewBatch(reviewBatchId, selectedIds.value) }
  catch (err) { error.value = err instanceof Error ? err.message : '动作预览失败' }
  finally { loading.value = false }
}

async function applyDecision(decision: 'approve' | 'reject') {
  if (!taskId) {
    error.value = '缺少 task_id，无法恢复工作流。请从工作流页面进入审核。'
    return
  }
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const pendingIds = suggestions.value.filter(isSelectable).map(item => item.id)
    const approvedIds = decision === 'approve' ? [...selectedIds.value] : []
    const rejectedIds = decision === 'approve'
      ? pendingIds.filter(id => !approvedIds.includes(id))
      : pendingIds
    const decisionPayload = {
      decision,
      approved_suggestion_ids: approvedIds,
      rejected_suggestion_ids: rejectedIds,
      edits: [],
      operator: 'local_user',
      reject_reason: rejectedIds.length ? 'manual reject' : null,
    }
    if (taskId.startsWith('diagnosis_') || !taskId) {
      await applyReviewDecision(reviewBatchId, decisionPayload)
      await loadBatch()
      message.value = decision === 'approve'
        ? `已接受 ${approvedIds.length} 条建议；系统不会自动执行修改。`
        : `已拒绝 ${rejectedIds.length} 条建议。`
      return
    }
    const result = await resumeWorkflow(taskId, decisionPayload)
    patch({
      currentVersionId: typeof result.current_version_id === 'number' ? result.current_version_id : state.currentVersionId,
      newVersionId: typeof result.new_version_id === 'number' ? result.new_version_id : state.newVersionId,
      versionNo: typeof result.version_no === 'string' ? result.version_no : state.versionNo,
      reportPath: typeof result.report_path === 'string' ? result.report_path : state.reportPath,
      reviewBatchId,
    })
    message.value = decision === 'approve'
      ? `已批准 ${approvedIds.length} 条建议，工作流已继续执行。`
      : `已拒绝 ${rejectedIds.length} 条建议，工作流已继续生成报告。`
    await router.push(`/workflow/${taskId}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败'
  } finally {
    loading.value = false
  }
}

async function loadBatch() {
  const batch = await getReviewBatch(reviewBatchId)
  suggestions.value = batch.suggestions
  selectedIds.value = batch.suggestions
    .filter(item => isSelectable(item) && item.risk_level === 'low' && !item.need_confirm)
    .map(item => item.id)
  patch({ reviewBatchId })
}

onMounted(async () => {
  try {
    await loadBatch()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '审核批次加载失败'
  }
})
</script>
