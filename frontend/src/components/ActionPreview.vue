<template>
  <section class="card" data-testid="action-preview">
    <div class="card-head"><div><p class="eyebrow">执行前组合模拟</p><h2>动作影响预览</h2></div><span class="badge" :data-tone="preview.valid ? 'success' : 'danger'">{{ preview.valid ? '校验通过' : '存在阻断错误' }}</span></div>
    <div v-if="preview.errors.length" class="error-list"><p v-for="(item, index) in preview.errors" :key="index" class="error">{{ item.reason || item.code || '未知错误' }}</p></div>
    <div class="review-stats"><span v-for="item in groups" :key="item.key" class="badge">{{ item.label }} {{ item.count }}</span></div>
    <template v-if="execution">
      <p v-if="execution.summary" class="lead">{{ execution.summary }}</p>
      <div class="preview-summary"><strong>组合模拟结果</strong><span v-for="(count, action) in execution.action_counts" :key="action" class="badge">{{ action }} {{ count }}</span><span class="badge">影响子节点 {{ execution.affected_child_count }}</span><span class="badge">影响引用 {{ execution.affected_reference_count }}</span></div>
      <div class="checks-grid"><div v-for="(value, key) in execution.checks" :key="key"><strong>{{ checkLabel(String(key)) }}</strong><span :data-ok="value === true">{{ display(value) }}</span></div></div>
      <div v-if="execution.path_changes.length" class="path-list"><h3>修改前后路径</h3><article v-for="(change, index) in execution.path_changes" :key="index"><div v-for="(value, key) in flattenChange(change)" :key="key"><strong>{{ key }}</strong><span>{{ display(value) }}</span></div></article></div>
    </template>
    <small>审核指纹：{{ preview.review_hash.slice(0, 16) }}</small>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ActionPreviewResult, ExecutionPreviewResult } from '../api/reviews'
const props = defineProps<{ preview: ActionPreviewResult | ExecutionPreviewResult }>()
const labels: Record<string, string> = { added: '新增', deleted: '删除', moved: '移动', renamed: '重命名', synonym_changed: '同义词', split: '拆分', merged: '合并', deprecated: '停用' }
const groups = computed(() => Object.entries(labels).map(([key, label]) => ({ key, label, count: props.preview.diff[key]?.length || 0 })))
const execution = computed(() => 'action_counts' in props.preview ? props.preview as ExecutionPreviewResult : null)
const checkLabels: Record<string, string> = { cycle: '无环', duplicate_sibling: '无同级重名', orphan: '无孤立节点', parent_exists: '父节点存在', depth_limit: '层级合规', synonyms_valid: '同义词有效', multi_action_conflicts: '无多动作冲突', baseline_unchanged: '基线未变化', new_medium_high_risk_issues: '新增中高风险问题' }
function checkLabel(key: string) { return checkLabels[key] || key }
function display(value: unknown): string {
  if (Array.isArray(value)) return value.length ? value.map(item => display(item)).join('；') : '无'
  if (value === true) return '通过'
  if (value === false) return '未通过'
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${riskFieldLabels[key] || key}: ${display(item)}`)
      .join('，')
  }
  return String(value ?? '-')
}
const riskFieldLabels: Record<string, string> = { risk_level: '风险等级', reason: '原因', code: '代码', node_id: '节点ID', level: '层级' }
function flattenChange(change: Record<string, unknown>) { const result: Record<string, unknown> = {}; for (const section of ['before', 'after', 'impact']) { const value = change[section]; if (value && typeof value === 'object') Object.assign(result, value) } return result }
</script>

<style scoped>
.preview-summary { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }.checks-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; }.checks-grid div,.path-list article div { padding:10px; border:1px solid var(--line); border-radius:10px; display:flex; justify-content:space-between; gap:8px; }.checks-grid span[data-ok="true"] { color:var(--success); }.path-list { margin-top:14px; }.path-list article { display:grid; gap:6px; margin-top:8px; }.error-list { display:grid; gap:4px; }
</style>
