<template>
  <div class="comparison-grid" data-testid="action-comparison">
    <section class="comparison-side before"><h4>修改前</h4><dl><template v-for="row in comparison.before" :key="row.label"><dt>{{ row.label }}</dt><dd :data-missing="row.missing">{{ row.value }}</dd></template></dl></section>
    <section class="comparison-side after"><h4>修改后</h4><dl><template v-for="row in comparison.after" :key="row.label"><dt>{{ row.label }}</dt><dd :data-missing="row.missing">{{ row.value }}</dd></template></dl></section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { SuggestionRecord } from '../api/reviews'
const props = defineProps<{ suggestion: SuggestionRecord }>()
const missing = '历史建议未记录该信息'
type Row = { label: string; value: string; missing: boolean }
function display(value: unknown): string { if (Array.isArray(value)) return value.length ? value.map(display).join('、') : '（空）'; if (typeof value === 'boolean') return value ? '是' : '否'; if (value && typeof value === 'object') return Object.entries(value as Record<string, unknown>).map(([key, item]) => `${key}: ${display(item)}`).join('；'); return String(value) }
function row(label: string, ...values: unknown[]): Row { const value = values.find(item => item !== null && item !== undefined && item !== ''); return { label, value: value === undefined ? missing : display(value), missing: value === undefined } }
const comparison = computed<{ before: Row[]; after: Row[] }>(() => {
  const item = props.suggestion, preview = item.change_preview || {}
  if (preview.before || preview.after) {
    const rows = (value?: Record<string, unknown>) => Object.entries(value || {}).map(([label, content]) => row(label, content))
    return { before: rows(preview.before).length ? rows(preview.before) : [row('修改前')], after: rows(preview.after).length ? rows(preview.after) : [row('修改后')] }
  }
  const payload = item.action_payload || {}, value = (...keys: string[]) => keys.map(key => payload[key]).find(entry => entry !== null && entry !== undefined && entry !== '')
  if (item.action_type === 'rename_node') return { before: [row('原名称', item.old_name, value('old_name'))], after: [row('新名称', item.new_name, value('new_name'))] }
  if (['clean_synonym', 'update_synonyms'].includes(item.action_type)) return { before: [row('原同义词', value('current_synonyms', 'old_syn_list')), row('删除内容', value('synonyms_to_remove', 'remove_synonyms'))], after: [row('新增内容', value('synonyms_to_add', 'add_synonyms')), row('最终同义词', value('final_syn_list', 'updated_synonyms'))] }
  if (item.action_type === 'move_node') return { before: [row('原父节点', value('old_parent_name'), item.old_parent_id && `ID ${item.old_parent_id}`), row('原路径', value('old_path'), item.issue?.path)], after: [row('新父节点', value('new_parent_name'), item.new_parent_id && `ID ${item.new_parent_id}`), row('新路径', value('new_path'))] }
  if (item.action_type === 'merge_node') return { before: [row('被合并节点', value('source_node_name'), value('source_node_id'))], after: [row('保留节点', value('target_node_name'), value('target_node_id'))] }
  if (item.action_type === 'review_only') return { before: [row('当前问题', item.issue?.description)], after: [row('不修改原因', value('no_change_reason'), item.reason)] }
  return { before: [row('当前状态', item.old_name, item.target_node_name, item.issue?.node_name)], after: [row('建议结果', item.new_name, item.suggestion)] }
})
</script>

<style scoped>
.comparison-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }.comparison-side { padding:14px; border:1px solid var(--line); border-radius:14px; background:rgba(17,24,39,.025); }.comparison-side.after { background:rgba(10,132,255,.045); }h4 { margin:0 0 10px; font-size:13px; }dl { margin:0; display:grid; gap:5px; }dt { color:var(--muted); font-size:12px; }dd { margin:0 0 7px; line-height:1.5; word-break:break-word; }dd[data-missing='true'] { color:var(--muted); font-style:italic; }@media(max-width:760px){.comparison-grid{grid-template-columns:1fr}}
</style>
