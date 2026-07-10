<template>
  <AppShell>
    <div class="page-stack">

      <!-- ===== 主操作区：dropzone + 文件信息 + 操作按钮 横排 ===== -->
      <section class="card main-card">
        <div class="main-layout">
          <!-- 左：拖拽上传区 -->
          <label class="dropzone" :class="{ 'is-dragging': dragging, 'has-file': !!fileName }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
            <input ref="fileInput" type="file" accept=".xlsx,.xls" class="visually-hidden" @change="onPick" />
            <template v-if="!fileName">
              <div class="dropzone-icon">📥</div>
              <div class="dropzone-text">
                <strong>点击或拖拽</strong> Excel 到此处上传
              </div>
            </template>
            <template v-else>
              <div class="dz-file-icon">📊</div>
              <div class="dz-file-info">
                <strong>{{ fileName }}</strong>
                <span class="muted">{{ rowCount }} 行 · {{ columnCount }} 列</span>
              </div>
              <button type="button" class="dz-replace" title="重新选择文件" @click.stop="fileInput?.click()">更换</button>
            </template>
          </label>

          <!-- 右：操作面板 -->
          <div class="action-panel">
            <p class="panel-label">当前状态</p>
            <div class="status-row">
              <span class="status-dot" :data-status="fileName ? 'ready' : 'empty'" />
              <span class="status-text">{{ fileName ? '已就绪' : '等待上传文件' }}</span>
            </div>

            <div class="btn-stack">
              <button v-if="!fileName || file" class="btn-primary" :disabled="!file || loading" @click="submit">
                {{ loading ? '⏳ 上传中…' : '📤 上传 Excel' }}
              </button>
              <button class="btn-primary btn-analyze" :disabled="!uploadedFileId || loading" @click="startAnalysis">
                {{ loading ? '⏳ 处理中…' : '🚀 开始智能体分析' }}
              </button>
            </div>

            <div class="panel-footer">
              <button
                v-if="existingFiles.length > 0"
                type="button"
                class="link-btn"
                @click="showFileModal = true"
              >
                📁 历史文件 ({{ existingFiles.length }}) →
              </button>
            </div>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="error" class="error-bar">{{ error }}</div>
      </section>

      <!-- ===== 字段检查（紧凑行，仅上传后显示） ===== -->
      <section v-if="fileName && columns.length" class="card field-card">
        <div class="field-header">
          <span>标准字段识别</span>
          <span class="badge tiny" :data-tone="schemaMatch ? 'success' : 'warning'">{{ schemaMatch ? '字段齐全' : `${columns.length}/${expectedFields.length}` }}</span>
        </div>
        <div class="chip-row">
          <span v-for="field in expectedFields" :key="field" class="chip" :data-found="columns.includes(field)">
            {{ field }}
          </span>
        </div>
      </section>

      <!-- ===== 历史文件弹窗 ===== -->
      <Modal :show="showFileModal" title="选择历史文件" @close="showFileModal = false">
        <div v-if="existingFiles.length" class="table-wrap">
          <p class="modal-hint">点击任意行即可选中并加载该文件的解析结果</p>
          <table class="data-table selectable file-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>大小</th>
                <th>时间</th>
                <th class="col-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in existingFiles"
                :key="item.id"
                :class="{ selected: item.id === uploadedFileId }"
                @click="selectExistingFile(item)"
              >
                <td>
                  <div class="file-name-cell">
                    <span class="file-icon">📄</span>
                    <div>
                      <strong>{{ item.file_name }}</strong>
                      <span class="muted">#{{ item.id }}</span>
                    </div>
                  </div>
                </td>
                <td class="muted">{{ item.row_count }} 行 · {{ item.column_count }} 列</td>
                <td class="muted">{{ fmtTime(item.upload_time) }}</td>
                <td class="col-actions">
                  <RouterLink class="link-sm" :to="`/versions?file_id=${item.id}`" @click.stop>查看版本 →</RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-hint">还没有历史上传记录</p>
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

const schemaMatch = computed(() => expectedFields.every((f) => columns.value.includes(f)))

function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] || null
}

function onDrop(event: DragEvent) {
  dragging.value = false
  file.value = event.dataTransfer?.files?.[0] || null
}

function applyFileContext(record: FileRecord) {
  fileName.value = record.file_name
  rowCount.value = record.row_count
  columnCount.value = record.column_count
  columns.value = record.columns || []
  uploadedFileId.value = record.id
  patch({
    fileId: record.id,
    fileName: record.file_name,
    fileRowCount: record.row_count,
    fileColumnCount: record.column_count,
    fileColumns: record.columns || [],
    taskId: null, workflowId: null, threadId: null,
    currentVersionId: null, newVersionId: null, versionNo: null,
    reviewBatchId: null, reportPath: null,
  })
}

async function loadExistingFiles() {
  try { existingFiles.value = await listFiles() }
  catch (e) { error.value = e instanceof Error ? e.message : '加载失败' }
}

function selectExistingFile(record: FileRecord) {
  applyFileContext(record)
  showFileModal.value = false
}

function fmtTime(t?: string): string {
  if (!t) return '-'
  // strip timezone suffix for brevity
  return t.replace(/\+08:00$/, '')
}

async function submit() {
  if (!file.value) return
  loading.value = true; error.value = ''
  try {
    const u = await uploadFile(file.value)
    fileName.value = u.file_name; rowCount.value = u.row_count; columnCount.value = u.column_count
    columns.value = u.columns; uploadedFileId.value = u.file_id
    patch({
      fileId: u.file_id, fileName: u.file_name, fileRowCount: u.row_count,
      fileColumnCount: u.column_count, fileColumns: u.columns,
      taskId: null, workflowId: null, threadId: null,
      currentVersionId: null, newVersionId: null, versionNo: null,
      reviewBatchId: null, reportPath: null,
    })
    await loadExistingFiles()
  } catch (e) { error.value = e instanceof Error ? e.message : '上传失败' }
  finally { loading.value = false }
}

async function startAnalysis() {
  if (!uploadedFileId.value) return
  loading.value = true; error.value = ''
  try {
    const w = await startWorkflow(uploadedFileId.value)
    patch({ taskId: w.task_id, workflowId: w.workflow_id, threadId: w.thread_id })
    await router.push(`/workflow/${w.task_id}`)
  } catch (e) { error.value = e instanceof Error ? e.message : '启动失败' }
  finally { loading.value = false }
}

onMounted(async () => {
  await loadExistingFiles()
  if (state.fileId && (!state.fileColumns.length || state.fileRowCount === null)) {
    try { applyFileContext(await getFile(state.fileId)) }
    catch { /* keep localStorage state */ }
  }
})
</script>

<style scoped>
/* ---- main card: left-right layout ---- */
.main-card { max-width: 800px; }
.main-layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 28px;
  align-items: start;
}
@media (max-width: 680px) {
  .main-layout { grid-template-columns: 1fr; gap: 16px; }
}

/* ---- dropzone ---- */
.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 36px 24px;
  border-radius: 16px;
  border: 2px dashed var(--line);
  background: rgba(17, 24, 39, 0.02);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
  min-height: 160px;
}
.dropzone:hover { border-color: var(--primary); background: rgba(10, 132, 255, 0.04); }
.dropzone.is-dragging { border-color: var(--primary); background: rgba(10, 132, 255, 0.08); }
.dropzone.has-file {
  border-style: solid;
  border-color: var(--success);
  background: rgba(26, 127, 55, 0.05);
}
.dropzone-icon { font-size: 32px; line-height: 1; }
.dropzone-text { font-size: 14px; color: var(--muted); }

.dz-file-icon { font-size: 40px; }
.dz-file-info { text-align: center; }
.dz-file-info strong { font-size: 15px; }
.dz-replace {
  margin-top: 8px;
  padding: 4px 14px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}
.dz-replace:hover { border-color: var(--primary); color: var(--primary); }

/* ---- action panel ---- */
.action-panel { display: grid; gap: 14px; }
.panel-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 2px; }

.status-row { display: flex; align-items: center; gap: 8px; }
.status-dot {
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--muted);
  transition: background 0.25s ease;
}
.status-dot[data-status='ready'] { background: #22c55e; box-shadow: 0 0 0 3px rgba(34,197,94,0.18); }
.status-text { font-weight: 600; font-size: 14px; }

.btn-stack { display: grid; gap: 10px; }
.btn-primary {
  width: 100%;
  padding: 12px 20px;
  border-radius: 13px;
  border: none;
  background: var(--primary-strong);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.15s ease, transform 0.1s ease;
}
.btn-primary:disabled { opacity: 0.42; cursor: not-allowed; }
.btn-primary:not(:disabled):hover { opacity: 0.9; transform: translateY(-1px); }
.btn-primary:not(:disabled):active { transform: translateY(0); }
.btn-analyze { background: linear-gradient(135deg, #0a84ff, #5b5fef); }

.panel-footer { border-top: 1px solid var(--line); padding-top: 10px; }
.link-btn {
  background: none; border: none; color: var(--primary);
  font-size: 13px; cursor: pointer; text-align: left;
  padding: 4px 0;
}
.link-btn:hover { text-decoration: underline; }

/* ---- error bar ---- */
.error-bar {
  margin-top: 16px;
  padding: 10px 16px;
  border-radius: 10px;
  background: rgba(217, 45, 32, 0.07);
  color: var(--danger);
  font-size: 13px;
}

/* ---- field check card ---- */
.field-card { max-width: 800px; }
.field-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
}
.badge.tiny {
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--line);
  color: var(--muted);
  background: rgba(17,24,39,0.03);
}
.chip[data-found='true'] {
  border-color: rgba(26,127,55,0.35);
  color: #166534;
  background: rgba(26,127,55,0.07);
}
.chip:not([data-found='true']) {
  border-color: rgba(217,153,6,0.30);
  color: #854d0e;
  background: rgba(217,153,6,0.06);
}

/* ---- modal table ---- */
.modal-hint { font-size: 13px; color: var(--muted); margin-bottom: 12px; }
.file-table tbody tr.selected {
  background: rgba(10, 132, 255, 0.09) !important;
  box-shadow: inset 3px 0 0 var(--primary);
}
.file-table tbody tr.selected td:first-child strong { color: var(--primary-strong); }
.file-table tbody tr { cursor: pointer; transition: background 0.15s ease; }
.file-table tbody tr:hover:not(.selected) { background: rgba(17, 24, 39, 0.03); }

.file-name-cell {
  display: flex; align-items: center; gap: 8px;
}
.file-icon { font-size: 16px; flex-shrink: 0; }
.link-sm {
  font-size: 12px;
  color: var(--primary);
  text-decoration: none;
  white-space: nowrap;
}
.link-sm:hover { text-decoration: underline; }

.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
</style>
