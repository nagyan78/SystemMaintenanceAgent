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
          <span v-else-if="step.state === 'running'" class="timeline-pulse">●</span>
        </div>
        <div class="timeline-body">
          <div class="timeline-label">
            <svg class="step-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="iconFor(step.key)" /></svg>
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
  completed: '已完成',
  failed: '失败',
}
const statusLabel = props.status ? (statusLabelMap[props.status] ?? props.status) : '运行中'

const icons: Record<string, string> = {
  parse_excel: 'M5 3h10l4 4v14H5V3Zm10 0v5h5M8 13h8m-8 4h6',
  build_tree: 'M5 4v16m0-8h6m0 0v8m0-8h8m-8 0V4',
  save_initial_version: 'M5 4h12l2 2v14H5V4Zm3 0v6h7V4m-6 12h6',
  index_vector: 'm20 20-4.5-4.5M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z',
  structure_diagnosis: 'M12 3v3m0 12v3M4.2 4.2l2.1 2.1m11.4 11.4 2.1 2.1M3 12h3m12 0h3M4.2 19.8l2.1-2.1m11.4-11.4 2.1-2.1M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z',
  diagnosis_planning: 'M12 21s7-3.5 7-10V5l-7-2-7 2v6c0 6.5 7 10 7 10Zm-3-9 2 2 4-4',
  content_diagnosis: 'M7 3h10a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H9l-5 3v-6a3 3 0 0 1 3-3Zm1 7h.01M12 10h.01M16 10h.01',
  generate_suggestion: 'M9 18h6m-5 3h4m3-10a5 5 0 1 0-10 0c0 2 1 3 2 4v1h6v-1c1-1 2-2 2-4Z',
  validate_action: 'm5 12 4 4L19 6',
  execute_action: 'M13 2 4 14h7l-1 8 9-12h-7l1-8Z',
  save_new_version: 'M5 4h12l2 2v14H5V4Zm3 0v6h7V4m-6 12h6',
  completed: 'M5 12l4 4L19 6',
}
function iconFor(key: string): string {
  return icons[key] ?? 'M12 6v6l4 2'
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
.timeline-step[data-state='running'] .timeline-dot { background: #f59e0b; }
.timeline-check { font-size: 13px; font-weight: 700; }
.timeline-pulse { color: #fff; font-size: 10px; animation: pulse 1.2s infinite; }
.timeline-body { border-left: 1px solid var(--line); padding-left: 4px; }
.timeline-step[data-state='pending'] .timeline-body { opacity: 0.5; }
.timeline-label { font-weight: 600; display: flex; align-items: center; gap: 8px; }
.step-icon { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
</style>
