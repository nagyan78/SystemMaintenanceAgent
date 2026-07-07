<template>
  <AppShell>
    <div class="page-stack">
      <StepTimeline :phase="phase" :label="label" :status="status" :tone="tone" :steps="timelineSteps" />
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">工作流状态</p>
            <h2>{{ status }}</h2>
          </div>
          <span class="badge">{{ progress }}%</span>
        </div>
        <p class="lead">{{ currentStep }}</p>
        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <div class="action-row">
          <RouterLink v-if="reviewBatchId && status === 'waiting_review'" :to="`/review/${reviewBatchId}?task_id=${taskId}`" class="button primary">进入审核</RouterLink>
          <RouterLink v-if="status === 'completed' && currentVersionId" :to="`/versions?file_id=${fileId}`" class="button primary">查看版本</RouterLink>
          <RouterLink v-if="status === 'completed' && currentVersionId" :to="`/report/${currentVersionId}`" class="button secondary">查看报告</RouterLink>
        </div>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import StepTimeline from '../components/StepTimeline.vue'
import { getWorkflowStatus } from '../api/workflows'
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
  completed: { label: '生成报告', phase: 'M4' },
}

const phase = computed(() => status.value === 'waiting_review' ? 'M3' : status.value === 'completed' ? 'M4' : 'M1-M4')
const label = computed(() => currentStep.value || '工作流运行中')
const tone = computed(() => status.value)

const timelineSteps = computed(() => {
  const currentIndex = Math.max(stepOrder.indexOf(currentStep.value as (typeof stepOrder)[number]), 0)
  return stepOrder.map((key, index) => {
    const meta = stepMeta[key]
    return {
      key,
      label: meta.label,
      phase: meta.phase,
      state: index < currentIndex || status.value === 'completed' ? 'completed' : key === currentStep.value ? 'waiting_review' : 'pending',
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
    patch({
      taskId,
      fileId: data.file_id,
      currentVersionId: data.current_version_id || null,
      reviewBatchId: data.review_batch_id || null,
      reportPath: data.report_path || null,
      versionNo: data.version_no || null,
    })
    if (data.status === 'waiting_review' || data.status === 'completed' || data.status === 'failed') {
      stop()
    }
  } catch (err) {
    errorMessage.value = err instanceof Error ? err.message : '状态查询失败'
    stop()
  }
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
  if (status.value === 'waiting_review' && reviewBatchId.value) await router.push(`/review/${reviewBatchId.value}?task_id=${taskId}`)
})

onBeforeUnmount(stop)
</script>
