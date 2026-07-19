<template>
  <section class="card">
    <div class="card-head">
      <div>
        <p class="eyebrow">{{ phase }}</p>
        <h2>{{ label }}</h2>
      </div>
      <span class="badge" :data-tone="tone">{{ statusLabel }}</span>
    </div>
    <div class="timeline">
      <div v-for="step in steps" :key="step.key" class="timeline-step" :data-state="step.state">
        <div class="timeline-dot">
          <span v-if="step.state === 'completed'" class="timeline-check">✓</span>
          <span v-else-if="step.state === 'waiting_review'" class="timeline-pulse">●</span>
        </div>
        <div class="timeline-body">
          <div class="timeline-label">
            <span class="step-icon">{{ iconFor(step.key) }}</span>
            {{ step.label }}
          </div>
          <div class="timeline-meta">{{ step.phase }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const props = defineProps<{
  phase: string
  label: string
  status: string
  tone?: string
  steps: Array<{ key: string; label: string; phase: string; state: string }>
}>()

const statusLabelMap: Record<string, string> = {
  running: '运行中',
  pending: '等待中',
  waiting_review: '待审核',
  completed: '已完成',
  failed: '失败',
}
const statusLabel = props.status ? (statusLabelMap[props.status] ?? props.status) : '运行中'

const icons: Record<string, string> = {
  parse_excel: '📊',
  build_tree: '🌲',
  save_initial_version: '💾',
  index_vector: '🔍',
  structure_diagnosis: '🔧',
  diagnosis_planning: '🧭',
  content_diagnosis: '🤖',
  generate_suggestion: '💡',
  human_review: '👀',
  validate_action: '✅',
  execute_action: '⚡',
  save_new_version: '📦',
  completed: '📄',
}
function iconFor(key: string): string {
  return icons[key] ?? '•'
}
</script>

<style scoped>
.timeline-step { display: grid; grid-template-columns: 28px 1fr; gap: 12px; align-items: start; padding: 8px 0; }
.timeline-dot {
  position: relative;
  width: 22px;
  height: 22px;
  margin-top: 2px;
  border-radius: 50%;
  background: rgba(17, 24, 39, 0.08);
  display: grid;
  place-items: center;
  font-size: 12px;
  color: var(--muted);
}
.timeline-step[data-state='completed'] .timeline-dot { background: var(--success); color: #fff; }
.timeline-step[data-state='waiting_review'] .timeline-dot { background: #f59e0b; }
.timeline-check { font-size: 13px; font-weight: 700; }
.timeline-pulse { color: #fff; font-size: 10px; animation: pulse 1.2s infinite; }
.timeline-body { border-left: 1px solid var(--line); padding-left: 4px; }
.timeline-step[data-state='pending'] .timeline-body { opacity: 0.5; }
.timeline-label { font-weight: 600; display: flex; align-items: center; gap: 8px; }
.step-icon { font-size: 15px; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
</style>
