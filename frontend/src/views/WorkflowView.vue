<template>
  <AppShell>
    <div class="page-stack">
      <TaskStatusBar
        :task-id="taskId"
        @progress="onSseProgress"
        @interrupt="onSseInterrupt"
        @completed="onSseCompleted"
        @failed="onSseFailed"
      />
      <StepTimeline :phase="phase" :label="label" :status="status" :tone="badgeTone" :steps="timelineSteps" />
      <QualityComparison
        v-if="evaluationBeforeId || evaluationAfterId || verification"
        :evaluation-before-id="evaluationBeforeId"
        :evaluation-after-id="evaluationAfterId"
        :evaluation-before="evaluationBefore"
        :evaluation-after="evaluationAfter"
        :verification="verification"
      />
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">工作流状态</p>
            <h2>{{ statusLabel }}</h2>
          </div>
          <span class="badge" :data-tone="badgeTone">{{ progress }}%</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :data-tone="badgeTone" :style="{ width: progress + '%' }">
            <span class="progress-text">{{ progress }}%</span>
          </div>
        </div>
        <p class="lead">{{ currentStepLabel }}</p>
        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <div class="action-row">
          <RouterLink v-if="reviewBatchId && status === 'waiting_review'" :to="`/review/${reviewBatchId}?task_id=${taskId}`" class="button primary">进入审核</RouterLink>
          <button v-if="status === 'waiting_continue'" class="button primary" @click="continueOptimization('continue')">继续优化</button>
          <button v-if="status === 'waiting_continue'" class="button secondary" @click="continueOptimization('finish')">结束并生成报告</button>
          <RouterLink v-if="['completed', 'completed_degraded'].includes(status) && currentVersionId" :to="`/versions?file_id=${fileId}`" class="button primary">查看版本</RouterLink>
          <RouterLink v-if="['completed', 'completed_degraded'].includes(status) && currentVersionId" :to="`/report/${currentVersionId}`" class="button secondary">查看报告</RouterLink>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import QualityComparison from '../components/QualityComparison.vue'
import StepTimeline from '../components/StepTimeline.vue'
import TaskStatusBar from '../components/TaskStatusBar.vue'
import { getWorkflowStatus, resumeWorkflow } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const router = useRouter()
const { state, patch } = useWorkspace()
const taskId = String(route.params.taskId)
const status = ref('running')
const progress = ref(0)
const currentStep = ref('')
const reviewBatchId = ref('')
const currentVersionId = ref<number | null>(null)
const fileId = ref<number | null>(state.fileId)
const errorMessage = ref('')
const interruptType = ref<'human_review' | 'continue_optimization' | ''>('')
const interruptId = ref('')
const evaluationBeforeId = ref<number | null>(state.evaluationBeforeId)
const evaluationAfterId = ref<number | null>(state.evaluationAfterId)
const evaluationBefore = ref<Record<string, unknown> | null>(state.evaluationBefore)
const evaluationAfter = ref<Record<string, unknown> | null>(state.evaluationAfter)
const verification = ref<Record<string, unknown> | null>(state.verification)
const timer = ref<number | null>(null)

const stepOrder = [
  'parse_excel',
  'build_tree',
  'save_initial_version',
  'index_vector',
  'structure_diagnosis',
  'diagnosis_planning',
  'content_diagnosis',
  'generate_suggestion',
  'human_review',
  'validate_action',
  'execute_action',
  'save_new_version',
  'index_result_version',
  'result_quality_evaluation',
  'verification',
  'continue_optimization',
  'completed',
] as const

const stepMeta: Record<string, { label: string; phase: string }> = {
  parse_excel: { label: '解析 Excel', phase: 'M1' },
  build_tree: { label: '构建分类树', phase: 'M1' },
  save_initial_version: { label: '保存 v1.0', phase: 'M1' },
  index_vector: { label: '向量索引', phase: 'M2' },
  structure_diagnosis: { label: '结构诊断', phase: 'M1/M2' },
  diagnosis_planning: { label: '诊断规划 Agent', phase: 'M2' },
  content_diagnosis: { label: '内容诊断 Agent', phase: 'M2' },
  generate_suggestion: { label: '建议生成 Agent', phase: 'M3' },
  human_review: { label: '人工审核', phase: 'M3' },
  validate_action: { label: '动作校验', phase: 'M3' },
  execute_action: { label: '执行动作', phase: 'M4' },
  save_new_version: { label: '保存新版本', phase: 'M4' },
  index_result_version: { label: '结果版本索引', phase: '阶段一' },
  result_quality_evaluation: { label: '结果质量评价', phase: '阶段一' },
  verification: { label: '修改验证', phase: '阶段一' },
  continue_optimization: { label: '是否继续优化', phase: '阶段一' },
  completed: { label: '生成报告', phase: 'M4' },
}

const phase = computed(() => status.value === 'waiting_review' ? 'M3' : status.value === 'waiting_continue' ? '阶段一' : ['completed', 'completed_degraded'].includes(status.value) ? 'M4' : 'M1-M4')
const label = computed(() => currentStep.value || '工作流运行中')
const badgeTone = computed(() => {
  if (['completed', 'completed_degraded'].includes(status.value)) return 'success'
  if (status.value === 'failed') return 'danger'
  if (['waiting_review', 'waiting_continue', 'waiting_manual_intervention'].includes(status.value)) return 'warning'
  return 'warning'
})
const statusLabel = computed(() => {
  const map: Record<string, string> = { running: '运行中', pending: '等待启动', waiting_review: '等待人工审核', waiting_continue: '等待决定是否继续优化', waiting_manual_intervention: '等待人工处理回归', completed: '已完成', completed_degraded: '已降级完成', failed: '失败' }
  return map[status.value] || status.value
})
const currentStepLabel = computed(() => {
  const meta = stepMeta[currentStep.value as keyof typeof stepMeta]
  return meta ? `${meta.label}（${meta.phase}）` : '工作流运行中'
})

const timelineSteps = computed(() => {
  const currentIndex = Math.max(stepOrder.indexOf(currentStep.value as (typeof stepOrder)[number]), 0)
  return stepOrder.map((key, index) => {
    const meta = stepMeta[key]
    return {
      key,
      label: meta.label,
      phase: meta.phase,
      state: index < currentIndex || ['completed', 'completed_degraded'].includes(status.value) ? 'completed' : key === currentStep.value ? 'waiting_review' : 'pending',
    }
  })
})

async function refresh() {
  try {
    const data = await getWorkflowStatus(taskId)
    status.value = data.status
    progress.value = data.progress
    currentStep.value = data.current_step
    reviewBatchId.value = data.review_batch_id || ''
    currentVersionId.value = data.current_version_id || null
    fileId.value = data.file_id
    errorMessage.value = data.error_message || ''
    interruptType.value = data.interrupt_type || ''
    interruptId.value = data.interrupt_id || ''
    evaluationBeforeId.value = data.evaluation_before_id || null
    evaluationAfterId.value = data.evaluation_after_id || null
    evaluationBefore.value = data.evaluation_before || null
    evaluationAfter.value = data.evaluation_after || null
    verification.value = data.verification || null
    patch({
      taskId,
      fileId: data.file_id,
      currentVersionId: data.current_version_id || null,
      reviewBatchId: data.review_batch_id || null,
      workflowMode: data.workflow_mode || state.workflowMode,
      baseVersionId: data.base_version_id || null,
      resultVersionId: data.result_version_id || null,
      evaluationBeforeId: data.evaluation_before_id || null,
      evaluationAfterId: data.evaluation_after_id || null,
      evaluationBefore: data.evaluation_before || null,
      evaluationAfter: data.evaluation_after || null,
      verification: data.verification || null,
      round: data.round || state.round,
      maxRounds: data.max_rounds || state.maxRounds,
      reportPath: data.report_path || null,
      versionNo: data.version_no || null,
    })
    if (['waiting_review', 'waiting_continue', 'waiting_manual_intervention', 'completed', 'completed_degraded', 'failed'].includes(data.status)) {
      stop()
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : '状态查询失败'
    stop()
  }
}

// --- Real-time SSE handlers (M5: consume real workflow events) ---
function onSseProgress(data: Record<string, unknown>) {
  if (typeof data.status === 'string') status.value = data.status
  if (typeof data.progress === 'number') progress.value = data.progress
  if (typeof data.current_step === 'string') currentStep.value = data.current_step
}

async function onSseInterrupt(payload: Record<string, unknown>) {
  await refresh()
  const type = String(payload.interrupt_type || payload.type || 'human_review')
  interruptType.value = type === 'continue_optimization' ? 'continue_optimization' : 'human_review'
  interruptId.value = String(payload.interrupt_id || '')
  const batchId = String(payload.review_batch_id || '')
  status.value = type === 'continue_optimization' ? 'waiting_continue' : 'waiting_review'
  reviewBatchId.value = batchId
  stop()
  if (batchId) {
    router.push(`/review/${batchId}?task_id=${taskId}`).catch(() => {})
  }
}

async function continueOptimization(decision: 'continue' | 'finish') {
  if (!interruptId.value) {
    errorMessage.value = '缺少 interrupt_id，请刷新状态后重试'
    return
  }
  try {
    await resumeWorkflow(taskId, {
      interrupt_type: 'continue_optimization',
      interrupt_id: interruptId.value,
      decision,
      operator: 'local_user',
    })
    status.value = 'running'
    await refresh()
    if (status.value === 'running') start()
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : '恢复工作流失败'
  }
}

async function onSseCompleted() {
  await refresh()
  stop()
}

async function onSseFailed(message: string) {
  errorMessage.value = message
  await refresh()
  stop()
}

function start() {
  timer.value = window.setInterval(refresh, 1500)
}

function stop() {
  if (timer.value) window.clearInterval(timer.value)
  timer.value = null
}

onMounted(async () => {
  await refresh()
  if (status.value === 'running' || status.value === 'pending') start()
  if (status.value === 'waiting_review' && reviewBatchId.value) {
    router.push(`/review/${reviewBatchId.value}?task_id=${taskId}`).catch(() => {})
  }
})

onBeforeUnmount(stop)
</script>
