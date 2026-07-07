<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">上传 Excel</p>
            <h2>开始分析工作流</h2>
          </div>
          <span class="badge">{{ readinessLabel }}</span>
        </div>
        <div class="upload-box">
          <input type="file" accept=".xlsx,.xls" @change="onPick" />
          <button class="button secondary" :disabled="!file || loading" @click="submit">{{ loading ? '上传中...' : '上传 Excel' }}</button>
          <button class="button primary" :disabled="!uploadedFileId || loading" @click="startAnalysis">
            {{ loading ? '处理中...' : '开始智能体分析' }}
          </button>
        </div>
        <p class="lead">请上传包含分类体系的 Excel，系统会识别字段并启动 LangGraph workflow。</p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>

      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">历史文件</p>
            <h2>已上传文件</h2>
          </div>
          <span class="badge">{{ existingFiles.length }} 个文件</span>
        </div>
        <div v-if="existingFiles.length" class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>文件</th>
                <th>行列</th>
                <th>上传时间</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in existingFiles" :key="item.id" :data-selected="item.id === uploadedFileId">
                <td>
                  <strong>{{ item.file_name }}</strong>
                  <div class="muted">#{{ item.id }}</div>
                </td>
                <td>{{ item.row_count }} 行 / {{ item.column_count }} 列</td>
                <td>{{ item.upload_time || '-' }}</td>
                <td><span class="badge">{{ item.status || 'uploaded' }}</span></td>
                <td>
                  <div class="action-row">
                    <button class="button secondary" @click="selectExistingFile(item)">选择</button>
                    <RouterLink class="button secondary" :to="`/versions?file_id=${item.id}`">查看版本</RouterLink>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="lead">还没有历史文件，上传后会在这里保留记录。</p>
      </section>

      <FileInfoCard
        v-if="fileName"
        :file-name="fileName"
        :row-count="rowCount"
        :column-count="columnCount"
        :columns="columns"
      />

      <section v-if="fileName" class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">字段检查</p>
            <h2>标准字段识别</h2>
          </div>
          <span class="badge" :data-tone="schemaMatch ? 'success' : 'warning'">{{ schemaMatch ? '字段齐全' : '待确认' }}</span>
        </div>
        <div class="chip-row">
          <span v-for="field in expectedFields" :key="field" class="chip" :data-tone="columns.includes(field) ? 'success' : 'missing'">
            {{ field }}
          </span>
        </div>
        <p class="lead">高亮字段表示已识别，缺失字段会在演示前提醒确认。</p>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import FileInfoCard from '../components/FileInfoCard.vue'
import { getFile, listFiles, uploadFile } from '../api/files'
import type { FileRecord } from '../api/files'
import { startWorkflow } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const router = useRouter()
const { state, patch } = useWorkspace()
const file = ref<File | null>(null)
const loading = ref(false)
const error = ref('')
const uploadedFileId = ref<number | null>(state.fileId)
const fileName = ref(state.fileName || '')
const rowCount = ref(state.fileRowCount || 0)
const columnCount = ref(state.fileColumnCount || 0)
const columns = ref<string[]>(state.fileColumns || [])
const existingFiles = ref<FileRecord[]>([])
const expectedFields = ['一级类目', '二级类目', '三级类目', '节点名称', '父级名称', '同义词']

const schemaMatch = computed(() => expectedFields.every(field => columns.value.includes(field)))
const readinessLabel = computed(() => fileName.value ? `${rowCount.value} 行 / ${columnCount.value} 列` : '等待上传')

function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] || null
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
    taskId: null,
    workflowId: null,
    threadId: null,
    currentVersionId: null,
    newVersionId: null,
    versionNo: null,
    reviewBatchId: null,
    reportPath: null,
  })
}

async function loadExistingFiles() {
  try {
    existingFiles.value = await listFiles()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '历史文件加载失败'
  }
}

function selectExistingFile(record: FileRecord) {
  applyFileContext(record)
}

async function submit() {
  if (!file.value) return
  loading.value = true
  error.value = ''
  try {
    const uploaded = await uploadFile(file.value)
    fileName.value = uploaded.file_name
    rowCount.value = uploaded.row_count
    columnCount.value = uploaded.column_count
    columns.value = uploaded.columns
    uploadedFileId.value = uploaded.file_id
    patch({
      fileId: uploaded.file_id,
      fileName: uploaded.file_name,
      fileRowCount: uploaded.row_count,
      fileColumnCount: uploaded.column_count,
      fileColumns: uploaded.columns,
      taskId: null,
      workflowId: null,
      threadId: null,
      currentVersionId: null,
      newVersionId: null,
      versionNo: null,
      reviewBatchId: null,
      reportPath: null,
    })
    await loadExistingFiles()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    loading.value = false
  }
}

async function startAnalysis() {
  if (!uploadedFileId.value) return
  loading.value = true
  error.value = ''
  try {
    const workflow = await startWorkflow(uploadedFileId.value)
    patch({ taskId: workflow.task_id, workflowId: workflow.workflow_id, threadId: workflow.thread_id })
    await router.push(`/workflow/${workflow.task_id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动工作流失败'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadExistingFiles()
  if (state.fileId && (!state.fileColumns.length || state.fileRowCount === null)) {
    try {
      applyFileContext(await getFile(state.fileId))
    } catch {
      // Keep the lightweight localStorage state if the file was removed.
    }
  }
})
</script>
