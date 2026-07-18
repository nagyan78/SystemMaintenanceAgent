<template>
  <AppShell>
    <div class="page-stack upload-page">
      <section class="upload-intro">
        <div>
          <p class="eyebrow">开始一次维护任务</p>
          <h2>导入产品标准体系</h2>
          <p>上传 Excel，系统将解析分类树、完成结构诊断，并由智能体自动生成可执行的维护版本。</p>
        </div>
        <ol class="flow-steps" aria-label="工作流步骤"><li class="current"><b>01</b>导入文件</li><li><b>02</b>自动分析</li><li><b>03</b>查看结果</li></ol>
      </section>

      <section class="upload-workspace">
        <div class="upload-workspace-head">
          <div><span class="section-kicker">文件导入</span><h2>选择待维护的 Excel 文件</h2></div>
          <span class="file-format">.xlsx</span>
        </div>
        <div class="upload-layout">
          <label class="dropzone" :class="{ 'is-dragging': dragging, 'has-file': !!displayFileName }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
            <input ref="fileInput" type="file" accept=".xlsx" class="visually-hidden" @change="onPick" />
            <template v-if="!displayFileName">
              <svg viewBox="0 0 48 48" class="upload-glyph" aria-hidden="true"><path d="M24 31V9m0 0-8 8m8-8 8 8M10 28v9a3 3 0 0 0 3 3h22a3 3 0 0 0 3-3v-9" /></svg>
              <strong>拖入 Excel 文件</strong><span>或点击此区域从本地选择</span>
            </template>
            <template v-else>
              <svg viewBox="0 0 48 48" class="upload-glyph success" aria-hidden="true"><path d="M14 6h15l8 8v27a1 1 0 0 1-1 1H14a3 3 0 0 1-3-3V9a3 3 0 0 1 3-3Zm14 0v9h9M17 28l5 5 10-11" /></svg>
              <strong>{{ displayFileName }}</strong><span>{{ file ? '待上传 · 尚未写入工作区' : `${rowCount} 行 · ${columnCount} 列 · 已就绪` }}</span>
              <button type="button" class="replace-file" @click.stop="fileInput?.click()">更换文件</button>
            </template>
          </label>

          <div class="upload-actions-panel">
            <div class="file-readiness"><span class="readiness-dot" :class="{ ready: !!uploadedFileId }"></span><div><small>当前状态</small><strong>{{ actionStatus }}</strong></div></div>
            <p>{{ actionHint }}</p>
            <button v-if="file && !uploadedFileId" class="button primary action-button" :disabled="loading" @click="submit">{{ loading ? '正在上传…' : '上传并识别字段' }}</button>
            <button v-else-if="uploadedFileId" class="button primary action-button" :disabled="loading" @click="startAnalysis">{{ loading ? '正在启动…' : '开始智能体分析' }}</button>
            <button v-else class="button secondary action-button" @click="fileInput?.click()">选择 Excel 文件</button>
            <button v-if="existingFiles.length" type="button" class="history-button" @click="showFileModal = true">从历史文件中选择 <span>{{ existingFiles.length }}</span></button>
          </div>
        </div>
        <p v-if="error" class="error-bar" role="alert">{{ error }}</p>
      </section>

      <section v-if="displayFileName" class="schema-card">
        <div><span class="section-kicker">导入检查</span><h2>字段识别</h2><p>确认文件列可用于构建标准分类树。</p></div>
        <div class="schema-content"><div class="schema-summary"><strong>{{ schemaMatch ? '字段完整' : '需要检查' }}</strong><span>{{ schemaMatch ? '已识别全部标准字段' : `已识别 ${columns.length} 个字段` }}</span></div><div class="chip-row"><span v-for="field in expectedFields" :key="field" class="chip" :data-found="columns.includes(field)">{{ field }}</span></div></div>
      </section>

      <Modal :show="showFileModal" title="选择历史文件" @close="showFileModal = false">
        <div v-if="existingFiles.length" class="table-wrap">
          <p class="modal-hint">选择一个已上传文件后，可直接开始新一轮维护。</p>
          <table class="data-table selectable file-table"><thead><tr><th>文件</th><th>数据规模</th><th>上传时间</th><th></th></tr></thead><tbody>
            <tr v-for="item in existingFiles" :key="item.id" :class="{ selected: item.id === uploadedFileId }" @click="selectExistingFile(item)">
              <td><strong>{{ item.file_name }}</strong><span class="muted">文件 #{{ item.id }}</span></td><td class="muted">{{ item.row_count }} 行 · {{ item.column_count }} 列</td><td class="muted">{{ fmtTime(item.upload_time) }}</td><td><RouterLink class="link-sm" :to="`/versions?file_id=${item.id}`" @click.stop>查看版本</RouterLink></td>
            </tr>
          </tbody></table>
        </div>
        <p v-else class="empty-hint">还没有历史上传记录。</p>
      </Modal>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import Modal from '../components/Modal.vue'
import { getFile, listFiles, uploadFile } from '../api/files'
import type { FileRecord } from '../api/files'
import { startWorkflow } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const router = useRouter()
const { state, patch } = useWorkspace()
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const loading = ref(false)
const error = ref('')
const dragging = ref(false)
const uploadedFileId = ref<number | null>(state.fileId)
const fileName = ref(state.fileName || '')
const rowCount = ref(state.fileRowCount || 0)
const columnCount = ref(state.fileColumnCount || 0)
const columns = ref<string[]>(state.fileColumns || [])
const existingFiles = ref<FileRecord[]>([])
const showFileModal = ref(false)
const expectedFields = ['一级类目', '二级类目', '三级类目', '节点名称', '父级名称', '同义词']
const displayFileName = computed(() => file.value?.name || fileName.value)
const schemaMatch = computed(() => expectedFields.every(field => columns.value.includes(field)))
const actionStatus = computed(() => uploadedFileId.value ? '可以开始自动分析' : file.value ? '可以上传文件' : '等待选择文件')
const actionHint = computed(() => uploadedFileId.value ? '系统将基于已上传文件创建维护任务。' : file.value ? '先上传并检查字段，再启动维护智能体。' : '支持标准分类体系的 .xlsx 文件。')

function onPick(event: Event) { const target = event.target as HTMLInputElement; file.value = target.files?.[0] || null; uploadedFileId.value = null; error.value = '' }
function onDrop(event: DragEvent) { dragging.value = false; file.value = event.dataTransfer?.files?.[0] || null; uploadedFileId.value = null; error.value = '' }
function applyFileContext(record: FileRecord) {
  file.value = null; fileName.value = record.file_name; rowCount.value = record.row_count; columnCount.value = record.column_count; columns.value = record.columns || []; uploadedFileId.value = record.id
  patch({ fileId: record.id, fileName: record.file_name, fileRowCount: record.row_count, fileColumnCount: record.column_count, fileColumns: record.columns || [], taskId: null, workflowId: null, threadId: null, currentVersionId: null, newVersionId: null, versionNo: null, reportPath: null })
}
async function loadExistingFiles() { try { existingFiles.value = await listFiles() } catch (e) { error.value = e instanceof Error ? e.message : '加载历史文件失败' } }
function selectExistingFile(record: FileRecord) { applyFileContext(record); showFileModal.value = false }
function fmtTime(value?: string) { return value ? value.replace(/\+08:00$/, '') : '—' }
async function submit() {
  if (!file.value) return
  loading.value = true; error.value = ''
  try { const uploaded = await uploadFile(file.value); fileName.value = uploaded.file_name; rowCount.value = uploaded.row_count; columnCount.value = uploaded.column_count; columns.value = uploaded.columns; uploadedFileId.value = uploaded.file_id; patch({ fileId: uploaded.file_id, fileName: uploaded.file_name, fileRowCount: uploaded.row_count, fileColumnCount: uploaded.column_count, fileColumns: uploaded.columns, taskId: null, workflowId: null, threadId: null, currentVersionId: null, newVersionId: null, versionNo: null, reportPath: null }); file.value = null; await loadExistingFiles() } catch (e) { error.value = e instanceof Error ? e.message : '上传失败' } finally { loading.value = false }
}
async function startAnalysis() {
  if (!uploadedFileId.value) return
  loading.value = true; error.value = ''
  try { const workflow = await startWorkflow(uploadedFileId.value); patch({ taskId: workflow.task_id, workflowId: workflow.workflow_id, threadId: workflow.thread_id }); await router.push(`/workflow/${workflow.task_id}`) } catch (e) { error.value = e instanceof Error ? e.message : '启动失败' } finally { loading.value = false }
}
onMounted(async () => { await loadExistingFiles(); if (state.fileId && (!state.fileColumns.length || state.fileRowCount === null)) { try { applyFileContext(await getFile(state.fileId)) } catch { /* retain local workspace */ } } })
</script>

<style scoped>
.upload-page { max-width: 1080px; gap: 28px; }
.upload-intro { display: flex; align-items: end; justify-content: space-between; gap: 32px; padding: 10px 0 4px; }
.upload-intro h2 { margin: 5px 0 9px; font-size: clamp(1.55rem, 3vw, 2.15rem); letter-spacing: -.035em; }
.upload-intro p { max-width: 640px; margin: 0; color: var(--muted); }
.flow-steps { display: flex; gap: 20px; padding: 0; margin: 0; list-style: none; color: var(--muted); font-size: 12px; white-space: nowrap; }
.flow-steps li { display: grid; gap: 4px; }
.flow-steps b { font-size: 11px; font-weight: 700; color: #9ca3af; }
.flow-steps .current, .flow-steps .current b { color: var(--primary); }
.upload-workspace { overflow: hidden; border: 1px solid var(--line); border-radius: 18px; background: var(--surface-solid); box-shadow: var(--shadow); }
.upload-workspace-head { display: flex; justify-content: space-between; align-items: start; padding: 22px 26px; border-bottom: 1px solid var(--line); }
.upload-workspace-head h2, .schema-card h2 { margin: 3px 0 0; font-size: 1.05rem; letter-spacing: -.015em; }
.section-kicker { color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.file-format { padding: 5px 8px; border: 1px solid var(--line); border-radius: 6px; color: var(--muted); font-size: 11px; font-weight: 700; }
.upload-layout { display: grid; grid-template-columns: minmax(0, 1fr) 290px; }
.dropzone { min-height: 290px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; padding: 32px; border-right: 1px solid var(--line); background: #fbfcfe; color: var(--muted); cursor: pointer; transition: background .22s ease, color .22s ease; }
.dropzone:hover, .dropzone.is-dragging { background: #f2f7ff; color: var(--primary); }
.dropzone.has-file { background: #f7fbf8; color: var(--text); }
.upload-glyph { width: 42px; height: 42px; fill: none; stroke: var(--primary); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; margin-bottom: 4px; }
.upload-glyph.success { stroke: var(--success); }
.dropzone strong { color: var(--text); font-size: 15px; }
.dropzone span { font-size: 13px; }
.replace-file { border: 0; padding: 0; background: transparent; color: var(--primary); font-size: 13px; cursor: pointer; }
.upload-actions-panel { display: flex; flex-direction: column; align-items: stretch; justify-content: center; gap: 16px; padding: 26px; }
.file-readiness { display: flex; align-items: center; gap: 10px; }
.readiness-dot { width: 9px; height: 9px; flex: none; border-radius: 50%; background: #aeb7c3; }
.readiness-dot.ready { background: var(--success); box-shadow: 0 0 0 4px rgba(34,122,75,.12); }
.file-readiness small { display: block; color: var(--muted); font-size: 11px; }
.file-readiness strong { font-size: 14px; }
.upload-actions-panel > p { min-height: 40px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.action-button { width: 100%; justify-content: center; }
.history-button { border: 0; padding: 8px 0 0; border-top: 1px solid var(--line); background: none; color: var(--muted); cursor: pointer; font-size: 12px; text-align: left; }
.history-button:hover { color: var(--primary); }
.history-button span { display: inline-grid; place-items: center; min-width: 18px; height: 18px; margin-left: 4px; border-radius: 50%; background: #edf1f7; color: var(--text); font-size: 11px; }
.error-bar { margin: 0; padding: 11px 26px; border-top: 1px solid rgba(217,45,32,.15); background: #fff5f4; color: var(--danger); font-size: 13px; }
.schema-card { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 28px; padding: 22px 26px; border: 1px solid var(--line); border-radius: 16px; background: var(--surface-solid); }
.schema-card p { margin: 7px 0 0; color: var(--muted); font-size: 13px; }
.schema-content { display: grid; gap: 14px; }
.schema-summary { display: flex; align-items: baseline; gap: 8px; }
.schema-summary strong { font-size: 14px; }.schema-summary span { color: var(--muted); font-size: 12px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 7px; }.chip { border: 1px solid var(--line); border-radius: 7px; padding: 5px 8px; color: var(--muted); background: #fbfcfe; font-size: 12px; }.chip[data-found='true'] { border-color: rgba(34,122,75,.28); background: #f3faf5; color: #176638; }
.modal-hint { color: var(--muted); font-size: 13px; }.file-table td strong, .file-table td .muted { display: block; }.file-table tbody tr.selected { background: #f0f6ff; }.link-sm { color: var(--primary); font-size: 12px; }
@media (max-width: 760px) { .upload-intro { align-items: start; flex-direction: column; }.upload-layout, .schema-card { grid-template-columns: 1fr; }.dropzone { min-height: 230px; border-right: 0; border-bottom: 1px solid var(--line); }.schema-card { gap: 16px; }.flow-steps { width: 100%; justify-content: space-between; gap: 8px; } }
</style>
