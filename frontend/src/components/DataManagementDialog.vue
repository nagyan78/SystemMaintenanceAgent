<template>
  <Modal :show="show" :title="title || '数据管理'" @close="$emit('close')">
    <div class="cleanup-stack">
      <p v-if="fileOnly" class="muted">将删除该历史文件及其全部派生数据，包括任务、版本、诊断、审核和报告。运行中的任务会先安全取消。</p>
      <template v-else>
        <p class="muted">普通记录点击后直接删除。运行中任务、已执行审核批次和 released 版本仍受保护。</p>
        <label><input v-model="mode" type="radio" value="selected" /> 删除选中记录</label>
        <label><input v-model="mode" type="radio" value="files" /> 删除选中文件及全部派生数据</label>
        <label><input v-model="mode" type="radio" value="failed" /> 清理失败任务</label>
        <label><input v-model="mode" type="radio" value="incomplete" /> 清理未开始任务</label>
        <label class="danger-option"><input v-model="mode" type="radio" value="all" /> 清空全部业务数据（默认不选择）</label>
      </template>
      <button v-if="!preview" class="button secondary" :disabled="busy" @click="generatePreview">{{ busy ? '生成中…' : '生成清理预览' }}</button>
      <section v-else class="cleanup-preview">
        <strong>清理范围确认</strong>
        <div class="counts"><span>任务 {{ preview.task_count }}</span><span>版本 {{ preview.version_count }}</span><span>问题 {{ preview.diagnosis_issue_count }}</span><span>建议 {{ preview.suggestion_count }}</span><span>报告 {{ preview.report_count }}</span><span>文件 {{ preview.filesystem_paths.length }}</span></div>
        <p class="muted">执行前数据库备份：{{ preview.database_backup_path }}</p>
        <details v-if="preview.filesystem_paths.length"><summary>查看将删除的文件</summary><ul><li v-for="path in preview.filesystem_paths" :key="path">{{ path }}</li></ul></details>
        <p v-if="preview.blocking_reasons.length" class="error">{{ preview.blocking_reasons.join('；') }}</p>
        <label><span>输入 {{ expectedConfirmation }} 确认</span><input v-model="confirmation" :placeholder="expectedConfirmation" /></label>
        <div class="action-row"><button class="button secondary" :disabled="busy" @click="preview=null">重新选择</button><button class="button danger" :disabled="busy || confirmation !== expectedConfirmation || preview.blocking_reasons.length>0" @click="executeConfirmed">{{ busy ? '删除中…' : '执行清理' }}</button></div>
      </section>
      <p v-if="message" class="lead">{{ message }}</p><p v-if="error" class="error">{{ error }}</p>
    </div>
  </Modal>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Modal from './Modal.vue'
import { executeCleanup, previewCleanup } from '../api/maintenance'
import type { CleanupPreview, CleanupRequest } from '../api/maintenance'
import { useWorkspace } from '../state/workspace'
const props = withDefaults(defineProps<{ show: boolean; workflowIds?: string[]; reviewBatchIds?: string[]; fileIds?: number[]; initialMode?: 'selected'|'files'|'failed'|'incomplete'|'all'; title?: string; fileOnly?: boolean; resetWorkspaceOnComplete?: boolean }>(), {
  resetWorkspaceOnComplete: true,
})
const emit = defineEmits<{ close: []; completed: [result: Record<string, unknown>] }>()
const { reset } = useWorkspace()
const mode = ref<'selected'|'files'|'failed'|'incomplete'|'all'>('selected')
const busy = ref(false), error = ref(''), message = ref('')
const preview = ref<CleanupPreview|null>(null), confirmation = ref('')
const expectedConfirmation = computed(() => mode.value === 'all' ? 'DELETE ALL' : 'CONFIRM')
watch(() => props.show, value => { if (value) { mode.value = props.fileOnly ? 'files' : props.initialMode || 'selected'; error.value = ''; message.value = ''; preview.value=null; confirmation.value='' } })
watch(mode, () => { preview.value=null; confirmation.value='' })
function payload(): CleanupRequest { if(props.fileOnly || mode.value==='files') return {file_ids:props.fileIds||[]}; if(mode.value==='all') return {all_business_data:true,force_cancel_running:true}; if(mode.value==='failed') return {failed_workflows:true}; if(mode.value==='incomplete') return {incomplete_workflows:true}; return {workflow_ids:props.workflowIds||[],review_batch_ids:props.reviewBatchIds||[]} }
async function generatePreview(){busy.value=true;error.value='';try{preview.value=await previewCleanup({...payload(),force_cancel_running:true})}catch(cause){error.value=cause instanceof Error?cause.message:'预览失败'}finally{busy.value=false}}
async function executeConfirmed(){if(!preview.value)return;busy.value=true;error.value='';try{const result=await executeCleanup(preview.value.cleanup_preview_id,confirmation.value);if(props.resetWorkspaceOnComplete)reset();message.value=`删除完成：数据库 ${Object.values(result.deleted).reduce((a,b)=>a+b,0)} 条，文件 ${result.filesystem_deleted} 个；备份 ${result.database_backup_path}`;emit('completed',result)}catch(cause){error.value=cause instanceof Error?cause.message:'删除失败'}finally{busy.value=false}}
</script>
<style scoped>.cleanup-stack{display:grid;gap:12px}.cleanup-preview{display:grid;gap:10px;padding:14px;border:1px solid var(--line);border-radius:12px}.counts{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}.cleanup-preview label{display:grid;gap:6px}.cleanup-preview input{padding:9px}.danger-option{color:var(--danger)}</style>
