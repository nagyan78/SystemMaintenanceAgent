<template>
  <Modal :show="show" title="编辑建议并通过" @close="$emit('close')">
    <form v-if="draft" class="edit-form" @submit.prevent="save">
      <label>动作类型<select v-model="draft.action_type"><option v-for="type in actionTypes" :key="type" :value="type">{{ type }}</option></select></label>
      <label v-if="draft.action_type === 'rename_node'">新名称<input v-model="draft.new_name" /></label>
      <label v-if="draft.action_type === 'move_node'">新父节点 ID<input v-model.number="draft.new_parent_id" type="number" /></label>
      <label>建议说明<textarea v-model="draft.suggestion" rows="4" /></label>
      <p class="muted">原动作字段会被保留；此处不直接展示或编辑原始 JSON。</p>
      <div class="action-row"><button class="button primary" type="submit">保存并通过修改</button><button class="button secondary" type="button" @click="$emit('close')">取消</button></div>
    </form>
  </Modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { SuggestionRecord } from '../api/reviews'
import Modal from './Modal.vue'
const props = defineProps<{ show: boolean; suggestion: SuggestionRecord | null }>()
const emit = defineEmits<{ close: []; save: [suggestion: SuggestionRecord] }>()
const draft = ref<SuggestionRecord | null>(null)
const actionTypes = ['rename_node', 'update_synonyms', 'move_node', 'merge_node', 'review_only']
watch(() => props.suggestion, value => { draft.value = value ? { ...value, action_payload: { ...value.action_payload }, issue: value.issue ? { ...value.issue } : null } : null }, { immediate: true })
function save() {
  if (!draft.value) return
  if (draft.value.action_type === 'rename_node') draft.value.action_payload.new_name = draft.value.new_name
  if (draft.value.action_type === 'move_node') draft.value.action_payload.new_parent_id = draft.value.new_parent_id
  emit('save', draft.value)
}
</script>

<style scoped>
.edit-form { display:grid; gap:14px; }
.edit-form label { display:grid; gap:6px; font-weight:600; font-size:13px; }
.edit-form input,.edit-form select,.edit-form textarea { padding:11px 12px; border:1px solid var(--line); border-radius:10px; background:var(--surface-solid); font-weight:400; }
</style>
