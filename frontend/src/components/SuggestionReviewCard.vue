<template>
  <article class="suggestion-card" :data-status="suggestion.status" data-testid="suggestion-review-card">
    <header class="suggestion-card-head">
      <div class="tag-row">
        <span class="badge" :data-tone="statusTone">{{ statusLabel }}</span>
        <span class="badge">{{ categoryLabel }}</span>
        <span class="risk" :data-tone="suggestion.risk_level">{{ riskLabel }}</span>
      </div>
      <label v-if="canReview" class="select-suggestion">
        <input type="checkbox" :checked="selected" @change="$emit('toggle')" /> 批量选择
      </label>
    </header>

    <div class="issue-heading">
      <div>
        <p class="issue-type">{{ suggestion.issue?.issue_type_label || '待确认问题' }}</p>
        <h3>{{ nodeName }}</h3>
      </div>
      <code>{{ suggestion.issue?.issue_type_code || 'unknown' }}</code>
    </div>
    <p class="issue-path"><span>完整路径</span>{{ suggestion.issue?.subject_path || suggestion.issue?.path || '历史建议未记录该信息' }}</p>
    <p class="issue-summary">{{ suggestion.issue?.description || suggestion.suggestion || '历史建议未记录该信息' }}</p>
    <p v-if="suggestion.needs_manual_edit" class="manual-warning">无法可靠生成修改动作，自动流程将忽略此建议</p>

    <ActionComparison :suggestion="suggestion" />

    <div class="impact"><strong>影响范围</strong><span>{{ impact }}</span></div>
    <div class="card-actions">
      <button v-if="isExecutableProposal" class="button primary" type="button" :disabled="!canReview || busy" @click="$emit('approve')">通过修改</button>
      <button v-if="isExecutableProposal" class="button secondary" type="button" :disabled="!canReview || busy" @click="$emit('edit')">编辑后通过</button>
      <button class="button danger" type="button" :disabled="!canReview || busy" @click="$emit('reject')">驳回建议</button>
      <button v-if="!isExecutableProposal" class="button secondary" type="button" :disabled="!canReview || busy" @click="$emit('uncertain')">证据不足，暂不处理</button>
      <button v-if="!isExecutableProposal" class="button secondary" type="button" :disabled="!canReview || busy" @click="$emit('falsePositive')">确认为误报</button>
      <button class="button secondary" type="button" @click="expanded = !expanded">{{ expanded ? '收起详情' : '展开详情' }}</button>
    </div>
    <SuggestionDetails
      v-if="expanded"
      :suggestion="suggestion"
      :can-review="canReview"
      @uncertain="$emit('uncertain')"
      @false-positive="$emit('falsePositive')"
    />
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { SuggestionRecord } from '../api/reviews'
import ActionComparison from './ActionComparison.vue'
import SuggestionDetails from './SuggestionDetails.vue'

const props = defineProps<{ suggestion: SuggestionRecord; selected: boolean; busy: boolean }>()
defineEmits<{ toggle: []; approve: []; edit: []; reject: []; uncertain: []; falsePositive: [] }>()
const expanded = ref(false)
const canReview = computed(() => ['pending', 'edited'].includes(props.suggestion.status))
const isExecutableProposal = computed(() => Boolean(props.suggestion.is_executable))
const categoryLabel = computed(() => props.suggestion.issue?.issue_category === 'structure' ? '结构类' : '内容类')
const nodeName = computed(() => props.suggestion.issue?.subject_node_name || props.suggestion.issue?.node_name || props.suggestion.target_node_name || (props.suggestion.target_node_id ? `节点 ID ${props.suggestion.target_node_id}` : '未记录节点'))
const riskLabel = computed(() => ({ low: '低风险', medium: '中风险', high: '高风险' }[props.suggestion.risk_level] || props.suggestion.risk_level))
const statusLabel = computed(() => ({ pending: '待审核', edited: '已编辑', approved: '已通过', rejected: '已驳回', deferred: '证据不足，暂不处理', executed: '已执行', failed: '失败' }[props.suggestion.status] || props.suggestion.status))
const statusTone = computed(() => ({ pending: 'warning', edited: 'warning', approved: 'success', executed: 'success', rejected: 'danger', deferred: 'warning', failed: 'danger' }[props.suggestion.status] || 'neutral'))
const impact = computed(() => {
  const payload = props.suggestion.action_payload || {}
  const previewImpact = props.suggestion.impact_scope || props.suggestion.change_preview?.impact_scope || props.suggestion.change_preview?.impact || {}
  if (Object.keys(previewImpact).length) {
    return Object.entries(previewImpact).map(([key, value]) => `${key}：${Array.isArray(value) ? value.join('、') : String(value ?? '-')}`).join('；')
  }
  const parts: string[] = []
  const fields: Array<[string, string]> = [
    ['affected_child_count', '个子节点'], ['affected_children_count', '个子节点'],
    ['reference_count', '处引用'], ['affected_reference_count', '处引用'],
  ]
  for (const [key, suffix] of fields) if (payload[key] !== null && payload[key] !== undefined) parts.push(`${payload[key]}${suffix}`)
  if (Array.isArray(payload.child_ids)) parts.push(`${payload.child_ids.length} 个子节点`)
  return parts.length ? [...new Set(parts)].join('，') : '历史建议未记录该信息'
})
</script>

<style scoped>
.suggestion-card { padding:20px; border:1px solid var(--line); border-radius:18px; background:var(--surface-solid); box-shadow:0 8px 24px rgba(15,23,42,.045); }
.suggestion-card[data-status='approved'],.suggestion-card[data-status='executed'] { border-color:rgba(26,127,55,.22); }
.suggestion-card-head,.tag-row,.issue-heading,.card-actions,.impact { display:flex; align-items:center; gap:10px; }
.suggestion-card-head,.issue-heading { justify-content:space-between; }
.tag-row,.card-actions { flex-wrap:wrap; }
.select-suggestion { color:var(--muted); font-size:12px; }
.issue-heading { margin:18px 0 6px; align-items:start; }
.issue-heading h3 { margin:4px 0 0; font-size:20px; }
.issue-type { margin:0; color:var(--primary-strong); font-size:13px; font-weight:700; }
.issue-heading code { color:var(--muted); font-size:11px; }
.issue-path { display:flex; gap:10px; margin:0 0 12px; color:var(--muted); font-size:13px; line-height:1.5; }
.issue-path span { flex:none; color:var(--text); font-weight:600; }
.issue-summary { margin:0 0 16px; line-height:1.65; }
.impact { margin:14px 0; padding:11px 13px; border-radius:12px; background:rgba(17,24,39,.035); align-items:start; }
.impact strong { flex:none; font-size:13px; }.impact span { color:var(--muted); font-size:13px; }
.manual-warning { padding:10px 12px; color:#9a3412; background:#fff7ed; border:1px solid #fdba74; border-radius:10px; font-weight:700; }
@media (max-width:640px) { .suggestion-card-head,.issue-heading { align-items:flex-start; flex-direction:column; } }
</style>
