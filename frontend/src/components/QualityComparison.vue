<template>
  <section class="card quality-comparison">
    <div class="card-head">
      <div>
        <p class="eyebrow">Quality v1</p>
        <h2>版本质量与验证对比</h2>
      </div>
      <span class="badge">{{ qualityDelta }}</span>
    </div>
    <div class="quality-grid">
      <div>
        <span>修改前评价</span>
        <strong>#{{ evaluationBeforeId || '—' }}</strong>
      </div>
      <div>
        <span>修改后评价</span>
        <strong>#{{ evaluationAfterId || '—' }}</strong>
      </div>
      <div>
        <span>可用维度</span>
        <strong>{{ availabilityText }}</strong>
      </div>
    </div>
    <div class="finding-row">
      <span>已解决 {{ resolved_fingerprints.length }}</span>
      <span>未解决 {{ unresolved_fingerprints.length }}</span>
      <span>新引入 {{ introduced_fingerprints.length }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  evaluationBeforeId?: number | null
  evaluationAfterId?: number | null
  verification?: Record<string, unknown> | null
}>()

const resolved_fingerprints = computed(() =>
  Array.isArray(props.verification?.resolved_fingerprints)
    ? props.verification.resolved_fingerprints as string[]
    : [],
)
const unresolved_fingerprints = computed(() =>
  Array.isArray(props.verification?.unresolved_fingerprints)
    ? props.verification.unresolved_fingerprints as string[]
    : [],
)
const introduced_fingerprints = computed(() =>
  Array.isArray(props.verification?.introduced_fingerprints)
    ? props.verification.introduced_fingerprints as string[]
    : [],
)
const available_dimensions = computed<Record<string, boolean>>(() => {
  const value = props.verification?.available_dimensions
  return value && typeof value === 'object' ? value as Record<string, boolean> : {}
})
const availabilityText = computed(() => {
  const values = Object.values(available_dimensions.value)
  if (!values.length) return '见报告'
  return `${values.filter(Boolean).length}/${values.length}`
})
const qualityDelta = computed(() => {
  const value = props.verification?.quality_delta
  return typeof value === 'number' ? `${value >= 0 ? '+' : ''}${value}` : '待验证'
})
</script>

<style scoped>
.quality-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.quality-grid div { padding: 12px; border: 1px solid var(--line); border-radius: 12px; }
.quality-grid span, .quality-grid strong { display: block; }
.quality-grid span { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.finding-row { display: flex; gap: 12px; margin-top: 14px; color: var(--muted); }
@media (max-width: 720px) { .quality-grid { grid-template-columns: 1fr; } }
</style>
