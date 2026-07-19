<template>
  <section class="suggestion-details" data-testid="suggestion-details">
    <div class="detail-block"><h4>完整证据</h4><p>{{ suggestion.issue?.evidence || missing }}</p></div>
    <div class="detail-block"><h4>判断理由</h4><p>{{ suggestion.reason || suggestion.issue?.reason || missing }}</p></div>
    <div class="detail-block"><h4>动作类型</h4><p><code>{{ suggestion.action_type }}</code></p></div>
    <div class="detail-block">
      <h4>格式化动作字段</h4>
      <dl class="field-table" data-testid="formatted-action-fields">
        <template v-if="actionFields.length">
          <template v-for="field in actionFields" :key="field.key"><dt>{{ field.key }}</dt><dd>{{ field.value }}</dd></template>
        </template>
        <template v-else><dt>动作字段</dt><dd>{{ missing }}</dd></template>
      </dl>
    </div>
    <div class="detail-block debug-fields">
      <h4>追踪信息</h4>
      <dl class="field-table">
        <dt>work_item_id</dt><dd>{{ suggestion.work_item_id || valueFromPayload('work_item_id') || missing }}</dd>
        <dt>analysis_run_id</dt><dd>{{ suggestion.analysis_run_id || valueFromPayload('analysis_run_id') || missing }}</dd>
      </dl>
    </div>
    <div v-if="canReview" class="secondary-decisions">
      <p class="muted">以下结论与“驳回建议”含义不同：</p>
      <button class="button secondary" type="button" @click="$emit('uncertain')">证据不足、暂不处理</button>
      <button class="button secondary" type="button" @click="$emit('falsePositive')">确认为误报</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SuggestionRecord } from '../api/reviews'
const props = defineProps<{ suggestion: SuggestionRecord; canReview: boolean }>()
defineEmits<{ uncertain: []; falsePositive: [] }>()
const missing = '历史建议未记录该信息'

function format(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.map(format).join('、') : '（空）'
  if (value && typeof value === 'object') return Object.entries(value).map(([key, child]) => `${key}: ${format(child)}`).join('；')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value ?? missing)
}
function flatten(value: unknown, prefix = ''): Array<{ key: string; value: string }> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return prefix ? [{ key: prefix, value: format(value) }] : []
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    if (child && typeof child === 'object' && !Array.isArray(child)) return flatten(child, path)
    return [{ key: path, value: format(child) }]
  })
}
const actionFields = computed(() => flatten(props.suggestion.action_payload).filter(field => !['work_item_id', 'analysis_run_id'].includes(field.key)))
function valueFromPayload(key: string) { const value = props.suggestion.action_payload?.[key]; return value == null ? '' : format(value) }
</script>

<style scoped>
.suggestion-details { margin-top:16px; padding-top:16px; border-top:1px solid var(--line); display:grid; gap:14px; }
.detail-block h4 { margin:0 0 6px; font-size:13px; }
.detail-block p { margin:0; line-height:1.6; white-space:pre-wrap; }
.field-table { display:grid; grid-template-columns:minmax(120px,220px) 1fr; margin:0; border:1px solid var(--line); border-radius:12px; overflow:hidden; }
.field-table dt,.field-table dd { margin:0; padding:9px 11px; border-bottom:1px solid var(--line); word-break:break-word; }
.field-table dt { color:var(--muted); background:rgba(17,24,39,.035); font-size:12px; }
.field-table dt:last-of-type,.field-table dd:last-of-type { border-bottom:0; }
.secondary-decisions { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
.secondary-decisions p { width:100%; margin:0; }
@media (max-width:640px) { .field-table { grid-template-columns:1fr; } .field-table dd { border-bottom:1px solid var(--line); } }
</style>
