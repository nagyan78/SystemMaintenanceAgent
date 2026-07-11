<template>
  <section class="sse-panel">
    <div class="sse-head">
      <span class="dot" :class="tone"></span>
      <span class="sse-title">实时事件流 (SSE)</span>
      <span class="sse-progress">{{ progress }}%</span>
    </div>
    <div class="sse-bar">
      <div class="sse-bar-fill" :class="tone" :style="{ width: progress + '%' }"></div>
    </div>
    <div class="sse-log" ref="logEl">
      <div v-if="log.length === 0" class="sse-empty">等待工作流事件…</div>
      <div v-for="(item, idx) in log" :key="idx" class="sse-row" :class="item.tone">
        <span class="sse-node">{{ item.label || item.node }}</span>
        <span class="sse-msg">{{ item.message || item.status }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { workflowEvents } from '../api/workflows'

const props = defineProps<{ taskId: string }>()
const emit = defineEmits<{
  (e: 'progress', payload: Record<string, unknown>): void
  (e: 'interrupt', payload: Record<string, unknown>): void
  (e: 'completed'): void
  (e: 'failed', message: string): void
}>()

const progress = ref(0)
const log = ref<
  Array<{ node?: string; label?: string; message?: string; status?: string; tone: string }>
>([])
const logEl = ref<HTMLElement | null>(null)
let source: EventSource | null = null

const tone = computed(() => {
  const last = log.value[log.value.length - 1]
  if (last?.tone === 'error') return 'error'
  if (progress.value >= 100) return 'ok'
  return 'running'
})

const stepLabels: Record<string, string> = {
  parse_excel: '解析 Excel',
  build_tree: '构建分类树',
  save_initial_version: '保存 v1.0',
  index_vector: '向量索引',
  structure_diagnosis: '结构诊断',
  diagnosis_planning: '诊断规划 Agent',
  content_diagnosis: '内容诊断 Agent',
  generate_suggestion: '建议生成 Agent',
  human_review: '人工审核',
  validate_action: '动作校验',
  execute_action: '执行动作',
  save_new_version: '保存新版本',
  generate_report: '生成报告',
}

function labelFor(node?: string, step?: string): string | undefined {
  const key = (step || node || '').replace(/_node$/, '')
  return stepLabels[key] || (node ? node.replace(/_node$/, '') : undefined)
}

function push(node: string | undefined, step: string | undefined, message: string | undefined, status?: string) {
  const label = labelFor(node, step)
  log.value.push({
    node,
    label,
    message,
    status,
    tone: status === 'failed' ? 'error' : 'ok',
  })
  if (log.value.length > 60) log.value.shift()
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function onStep(data: Record<string, unknown>) {
  if (typeof data.progress === 'number') progress.value = data.progress
  const step = data.current_step as string | undefined
  const node = data.node as string | undefined
  const status = data.status as string | undefined
  const message = data.message as string | undefined
  if (step || node) push(node, step, message, status)
  emit('progress', data)
}

function onInterrupt(data: Record<string, unknown>) {
  emit('interrupt', data)
}

function onCompleted() {
  emit('completed')
}

function onFailed(data: Record<string, unknown>) {
  emit('failed', (data.message as string) || 'workflow failed')
}

onMounted(() => {
  if (typeof EventSource === 'undefined') {
    push(undefined, undefined, '当前环境不支持 SSE，请刷新页面重试', 'failed')
    return
  }
  source = workflowEvents(props.taskId)
  source.addEventListener('workflow_step', (ev) => onStep(JSON.parse((ev as MessageEvent).data)))
  source.addEventListener('workflow_interrupt', (ev) => onInterrupt(JSON.parse((ev as MessageEvent).data)))
  source.addEventListener('workflow_waiting_continue', (ev) => onInterrupt(JSON.parse((ev as MessageEvent).data)))
  source.addEventListener('workflow_manual_intervention', (ev) => onInterrupt(JSON.parse((ev as MessageEvent).data)))
  source.addEventListener('workflow_completed', () => onCompleted())
  source.addEventListener('workflow_completed_degraded', () => onCompleted())
  source.addEventListener('workflow_failed', (ev) => onFailed(JSON.parse((ev as MessageEvent).data)))
  source.onerror = () => {
    // Browser auto-reconnects; ignore transient errors.
  }
})

onBeforeUnmount(() => {
  source?.close()
  source = null
})

watch(
  () => props.taskId,
  () => {
    log.value = []
    progress.value = 0
  },
)
</script>

<style scoped>
.sse-panel {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--surface-solid);
}
.sse-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #94a3b8;
}
.dot.running {
  background: #2563eb;
  animation: pulse 1.2s infinite;
}
.dot.ok {
  background: #16a34a;
}
.dot.error {
  background: #dc2626;
}
.sse-title {
  flex: 1;
}
.sse-progress {
  font-variant-numeric: tabular-nums;
  color: #475569;
}
.sse-bar {
  height: 6px;
  border-radius: 999px;
  background: #eef2f7;
  margin: 10px 0;
  overflow: hidden;
}
.sse-bar-fill {
  height: 100%;
  background: #2563eb;
  transition: width 0.4s ease;
}
.sse-bar-fill.ok {
  background: #16a34a;
}
.sse-bar-fill.error {
  background: #dc2626;
}
.sse-log {
  max-height: 220px;
  overflow-y: auto;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sse-empty {
  color: #94a3b8;
  padding: 8px 0;
}
.sse-row {
  display: flex;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  background: #f8fafc;
}
.sse-row.error {
  background: #fef2f2;
  color: #b91c1c;
}
.sse-node {
  font-weight: 600;
  min-width: 96px;
  color: #334155;
}
.sse-row.error .sse-node {
  color: #b91c1c;
}
.sse-msg {
  color: #64748b;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
</style>
