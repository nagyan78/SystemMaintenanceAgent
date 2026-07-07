<template>
  <AppShell>
    <div class="page-stack">
      <SuggestionTable :title="`Review batch ${reviewBatchId}`" :suggestions="suggestions" :selected-ids="selectedIds" @toggle="toggle" />
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
          <button class="button primary" :disabled="loading || selectedIds.length === 0" @click="applyDecision('approve')">批准选中</button>
          <button class="button secondary" :disabled="loading || selectedIds.length === 0" @click="applyDecision('reject')">拒绝选中</button>
          <button class="button primary" :disabled="loading || statusCounts.approved === 0" @click="executeApproved">执行已批准</button>
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
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import SuggestionTable from '../components/SuggestionTable.vue'
import { applyReviewDecision, executeReviewBatch, getReviewBatch } from '../api/reviews'
import type { SuggestionRecord } from '../api/reviews'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const { state, patch } = useWorkspace()
const reviewBatchId = String(route.params.reviewBatchId)
const taskId = String(route.query.task_id || state.taskId || '')
const suggestions = ref<SuggestionRecord[]>([])
const selectedIds = ref<number[]>([])
const loading = ref(false)
const error = ref('')
const message = ref('')
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

async function applyDecision(decision: 'approve' | 'reject') {
  if (!selectedIds.value.length) return
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const ids = [...selectedIds.value]
    await applyReviewDecision(reviewBatchId, {
      decision,
      approved_suggestion_ids: decision === 'approve' ? ids : [],
      rejected_suggestion_ids: decision === 'reject' ? ids : [],
      edits: [],
      operator: 'local_user',
      reject_reason: decision === 'reject' ? 'manual reject' : null,
    })
    message.value = decision === 'approve' ? `已批准 ${ids.length} 条建议，可继续执行生成新版本。` : `已拒绝 ${ids.length} 条建议。`
    await loadBatch()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '提交失败'
  } finally {
    loading.value = false
  }
}

async function executeApproved() {
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await executeReviewBatch(reviewBatchId)
    if (result.new_version_id) {
      patch({
        currentVersionId: result.new_version_id,
        newVersionId: result.new_version_id,
        versionNo: result.new_version_no || state.versionNo,
        reviewBatchId,
      })
      message.value = `执行完成，已生成版本 ${result.new_version_no || result.new_version_id}，执行 ${result.executed_count} 条。`
    } else {
      message.value = result.message || '当前没有已批准且待执行的建议。'
    }
    await loadBatch()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '执行失败'
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
