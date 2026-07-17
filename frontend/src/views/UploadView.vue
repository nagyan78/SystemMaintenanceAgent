<template>
  <AppShell>
    <div class="page-stack">

      <!-- ===== 主操作区：dropzone + 文件信息 + 操作按钮 横排 ===== -->
      <section class="card main-card">
        <div class="main-layout">
          <!-- 左：拖拽上传区 -->
          <label class="dropzone" :class="{ 'is-dragging': dragging, 'has-file': !!fileName }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
            <input ref="fileInput" type="file" accept=".xlsx" class="visually-hidden" @change="onPick" />
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
                <span class="muted">{{ file ? '等待上传解析' : `${rowCount} 行 · ${columnCount} 列` }}</span>
              </div>
              <button type="button" class="dz-replace" title="重新选择文件" @click.stop="fileInput?.click()">更换</button>
            </template>
          </label>

          <!-- 右：操作面板 -->
          <div class="action-panel">
            <p class="panel-label">当前状态</p>
            <div class="status-row">
              <span class="status-dot" :data-status="uploadedFileId ? 'ready' : 'empty'" />
              <span class="status-text">{{ file ? '文件已选择，请上传' : uploadedFileId ? '可以开始诊断' : '等待上传文件' }}</span>
            </div>

            <div class="btn-stack">
              <button v-if="file" class="btn-primary" :disabled="uploading || analysisRunning" @click="submit">
                {{ uploading ? '⏳ 上传中…' : '📤 上传 Excel' }}
              </button>
              <button class="btn-primary btn-analyze" :disabled="!uploadedFileId || uploading || analysisRunning" @click="startAnalysis">
                {{ analysisRunning ? '诊断进行中…' : '开始诊断' }}
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

      <section class="card task-center">
        <div class="card-head">
          <div><p class="eyebrow">后端持久化任务</p><h2>诊断任务</h2></div>
          <div class="action-row"><button class="button secondary" :disabled="!selectedTaskIds.length || cleanupBusy" @click="openCleanup('selected')">批量删除</button><button class="button secondary" :disabled="cleanupBusy" @click="openCleanup('failed')">清理失败任务</button><button class="button secondary" :disabled="cleanupBusy" @click="openCleanup('incomplete')">清理未开始任务</button><button class="button secondary" @click="openCleanup('files')">数据管理</button><button class="button secondary" :disabled="tasksLoading" @click="loadTasks">{{ tasksLoading ? '刷新中…' : '刷新' }}</button></div>
        </div>
        <p v-if="tasksError" class="error">{{ tasksError }}</p>
        <div v-else-if="tasksLoading && !tasks.length" class="empty-hint">正在读取诊断任务…</div>
        <div v-else-if="tasks.length" class="table-wrap">
          <table class="data-table">
            <thead><tr><th><input type="checkbox" :checked="selectedTaskIds.length === tasks.length" @change="toggleAllTasks" /></th><th>上传文件名</th><th>创建时间</th><th>当前阶段</th><th>运行状态</th><th>真实进度</th><th>问题数量</th><th>审核状态</th><th>当前可执行操作</th></tr></thead>
            <tbody>
              <tr v-for="item in tasks" :key="item.id">
                <td><input v-model="selectedTaskIds" type="checkbox" :value="item.id" /></td>
                <td><strong>{{ item.file_name || `文件 #${item.file_id}` }}</strong><small class="task-id">{{ item.id }}</small></td>
                <td>{{ fmtTime(item.created_time) }}</td>
                <td>{{ stageLabel(item.current_step) }}</td>
                <td><span class="badge" :data-tone="taskTone(item.status)">{{ taskStatusLabel(item.status) }}</span></td>
                <td><div class="task-progress"><progress :value="item.progress || 0" max="100"/><span>{{ item.progress || 0 }}%</span></div></td>
                <td>{{ item.issue_count ?? 0 }}</td>
                <td>{{ reviewStatusLabel(item) }}</td>
                <td><div class="task-actions">
                  <button v-if="isTaskRunning(item)" class="link-btn" @click="focusTask(item)">查看进度</button>
                  <button v-if="isTaskRunning(item)" class="link-btn" @click="cancelTask(item)">取消任务</button>
                  <RouterLink v-if="item.review_batch_id && item.execution_status !== 'executed'" class="link-sm" :to="`/review/${item.review_batch_id}`">进入建议审核</RouterLink>
                  <RouterLink v-if="item.version_id" class="link-sm" :to="`/diagnosis/${item.version_id}`">查看诊断结果</RouterLink>
                  <RouterLink v-if="item.new_version_id" class="link-sm" :to="`/versions?file_id=${item.file_id}`">查看新版本</RouterLink>
                  <RouterLink v-if="item.new_version_id && ['passed','partial'].includes(String(item.verification_status || ''))" class="link-sm" :to="`/report/${item.new_version_id}?type=final`">查看完整报告</RouterLink>
                  <RouterLink v-if="item.final_report_available && item.new_version_id" class="link-sm" :to="`/report/${item.new_version_id}?type=final`">查看报告</RouterLink>
                  <RouterLink v-else-if="item.draft_report_available && item.version_id" class="link-sm" :to="`/report/${item.version_id}?type=draft`">查看报告</RouterLink>
                  <button v-if="item.status === 'failed'" class="link-btn" @click="retryTask(item)">重试</button>
                  <button class="link-btn" :disabled="cleanupBusy" @click="deleteOneTask(item)">删除</button>
                  <span v-if="item.status === 'failed'" class="error task-error">{{ item.error_message || '任务失败' }}</span>
                </div></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="empty-hint">确实没有诊断任务。上传文件并开始诊断后，任务会显示在这里。</p>
      </section>
      <DataManagementDialog :show="showCleanup" :workflow-ids="selectedTaskIds" :file-ids="selectedTaskFileIds" :initial-mode="cleanupMode" @close="showCleanup=false" @completed="cleanupCompleted" />
      <DataManagementDialog
        :show="Boolean(historyDeleteTarget)"
        :file-ids="historyDeleteTarget ? [historyDeleteTarget.id] : []"
        :reset-workspace-on-complete="false"
        file-only
        :title="historyDeleteTarget ? `删除历史文件：${historyDeleteTarget.file_name}` : '删除历史文件'"
        @close="closeHistoryDelete"
        @completed="historyDeleteCompleted"
      />

      <section v-if="uploadedFileId" class="card overview-strip">
        <div><span>文件名称</span><strong>{{ fileName }}</strong></div>
        <div><span>节点数量</span><strong>{{ nodeCount || rowCount }}</strong></div>
        <div><span>分类层级</span><strong>{{ maxDepth || '待解析' }}</strong></div>
        <div><span>叶子节点</span><strong>{{ leafCount || '待解析' }}</strong></div>
      </section>

      <section v-if="uploadedFileId" class="card diagnosis-config">
        <div class="card-head"><div><p class="eyebrow">诊断配置</p><h2>选择本次分析方式</h2></div><span class="badge" :data-tone="enableAiAnalysis ? 'warning' : 'success'">{{ enableAiAnalysis ? '智能模式' : '快速模式' }}</span></div>
        <div class="option-grid">
          <label class="option-card" :class="{ selected: !enableAiAnalysis }"><input v-model="enableAiAnalysis" type="radio" :value="false" /><span><strong>快速模式（关闭 AI）</strong><small>只运行 Excel 解析、结构规则和内容规则，适合日常开发测试。</small></span></label>
          <label class="option-card" :class="{ selected: enableAiAnalysis }"><input v-model="enableAiAnalysis" type="radio" :value="true" /><span><strong>智能模式（开启 AI）</strong><small>规则筛选候选节点后，再进行语义分析。</small></span></label>
        </div>
        <div v-if="enableAiAnalysis" class="model-config">
          <p class="panel-label">选择模型</p>
          <label class="option-card" :class="{ selected: modelProvider === 'ollama' }"><input v-model="modelProvider" type="radio" value="ollama" /><span><strong>本地模型 qwen3:8b</strong><small>通过 Ollama 本地调用，用于开发测试。</small></span></label>
          <label class="option-card" :class="{ selected: modelProvider === 'deepseek' }"><input v-model="modelProvider" type="radio" value="deepseek" /><span><strong>DeepSeek API</strong><small>使用 deepseek-chat，需要配置 API Key。</small></span></label>
          <div class="advanced-grid">
            <label><span>候选策略</span><select v-model="sampleStrategy"><option value="focused">重点召回</option><option value="sampling">确定性抽样</option><option value="full_scan">全范围候选</option></select></label>
            <label><span>候选上限</span><input v-model.number="aiCandidateLimit" type="number" min="1" max="1000" /></label>
            <label><span>模型调用上限</span><input v-model.number="aiMaxModelCalls" type="number" min="1" /></label>
            <label><span>Token 总预算</span><input v-model.number="aiTokenBudget" type="number" min="1" /></label>
            <label><span>最长秒数</span><input v-model.number="aiWallSeconds" type="number" min="1" /></label>
            <label><span>关注问题 code（逗号分隔）</span><input v-model="focusIssuesText" placeholder="synonym_conflict,naming_nonstandard" /></label>
          </div>
        </div>
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

      <section v-if="activeTaskId" class="card workflow-card">
        <div class="card-head">
          <div><p class="eyebrow">实时分析</p><h2>诊断工作流</h2></div>
          <span class="badge" :data-tone="analysisStatus === 'completed' ? 'success' : analysisStatus === 'failed' ? 'danger' : 'warning'">{{ analysisStatusLabel }}</span>
        </div>
        <TaskStatusBar
          :task-id="activeTaskId"
          @progress="onWorkflowProgress"
          @completed="onWorkflowCompleted"
          @failed="onWorkflowFailed"
          @interrupt="onWorkflowInterrupt"
        />
        <p v-if="analysisStatus === 'completed' && qualityAfter !== null" class="lead">
          质量评价：{{ qualityBefore ?? '-' }} → {{ qualityAfter }}
          <span v-if="qualityDelta !== null">（{{ qualityDelta >= 0 ? '+' : '' }}{{ qualityDelta }}）</span>
        </p>
        <div class="result-actions">
          <RouterLink v-if="activeReviewBatchId" class="button primary" :to="`/review/${activeReviewBatchId}`">审核问题并修改</RouterLink>
          <RouterLink v-if="resultVersionId" class="button primary" :to="`/diagnosis/${resultVersionId}`">查看诊断结果</RouterLink>
          <RouterLink v-if="resultVersionId" class="button secondary" :to="`/report/${resultVersionId}?type=draft`">查看诊断草稿</RouterLink>
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
                  <div class="history-file-actions">
                    <RouterLink class="link-sm" :to="`/versions?file_id=${item.id}`" @click.stop>查看版本 →</RouterLink>
                    <button class="link-btn danger-link" type="button" @click.stop="requestHistoryDelete(item)">删除文件</button>
                  </div>
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import Modal from '../components/Modal.vue'
import TaskStatusBar from '../components/TaskStatusBar.vue'
import DataManagementDialog from '../components/DataManagementDialog.vue'
import { getFile, listFiles, uploadFile } from '../api/files'
import type { FileRecord } from '../api/files'
import { importTaxonomy } from '../api/diagnosis'
import type { CleanupRequest } from '../api/maintenance'
import { cancelWorkflow, getWorkflowStatus, listWorkflows, startWorkflow } from '../api/workflows'
import type { WorkflowListItem } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const { state, patch, reset } = useWorkspace()
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const uploading = ref(false)
const error = ref('')
const dragging = ref(false)
const uploadedFileId = ref<number | null>(state.fileId)
const fileName = ref(state.fileName || '')
const rowCount = ref(state.fileRowCount || 0)
const columnCount = ref(state.fileColumnCount || 0)
const columns = ref<string[]>(state.fileColumns || [])
const existingFiles = ref<FileRecord[]>([])
const showFileModal = ref(false)
const historyDeleteTarget = ref<FileRecord | null>(null)
const nodeCount = ref(0)
const maxDepth = ref(0)
const leafCount = ref(0)
const enableAiAnalysis = ref(state.enableAiAnalysis)
const modelProvider = ref<'ollama' | 'deepseek'>(state.modelProvider)
const sampleStrategy = ref<'focused'|'sampling'|'full_scan'>('focused')
const aiCandidateLimit = ref(20), aiMaxModelCalls = ref(100), aiTokenBudget = ref(100000), aiWallSeconds = ref(900)
const focusIssuesText = ref('synonym_conflict,naming_nonstandard,semantic_misplacement')
const activeTaskId = ref<string | null>(state.taskId?.startsWith('workflow_') ? state.taskId : null)
const activeReviewBatchId = ref<string | null>(state.reviewBatchId)
const analysisStatus = ref<'idle' | 'running' | 'waiting_review' | 'partial' | 'completed' | 'failed'>('idle')
const resultVersionId = ref<number | null>(state.currentVersionId)
const qualityBefore = ref<number | null>(null)
const qualityAfter = ref<number | null>(null)
const qualityDelta = ref<number | null>(null)
const tasks = ref<WorkflowListItem[]>([])
const tasksLoading = ref(false)
const tasksError = ref('')
const selectedTaskIds = ref<string[]>([])
const showCleanup = ref(false)
const cleanupBusy = ref(false)
const cleanupMode = ref<'selected'|'files'|'failed'|'incomplete'|'all'>('selected')
const selectedTaskFileIds = computed(() => [...new Set([
  ...tasks.value.filter(item => selectedTaskIds.value.includes(item.id)).map(item => item.file_id),
  ...(uploadedFileId.value ? [uploadedFileId.value] : []),
])])
let taskRefreshTimer: number | null = null
const expectedFields = [
  'category_id',
  'category_name',
  'category_group_id',
  'category_pids',
  'category_group_name',
  'syn_list',
]

const schemaMatch = computed(() => expectedFields.every((f) => columns.value.includes(f)))
const analysisRunning = computed(() => analysisStatus.value === 'running')
const analysisStatusLabel = computed(() => ({ idle: '等待开始', running: '分析中', waiting_review: '等待审核', partial: '部分完成', completed: '分析完成', failed: '分析失败' }[analysisStatus.value]))

const taskStatusLabel = (value: string) => ({ pending: '等待开始', running: '运行中', waiting_review: '等待审核', partial: '部分完成', completed_degraded: '降级完成', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[value] || value
const taskTone = (value: string) => value === 'failed' ? 'danger' : value === 'completed' ? 'success' : 'warning'
const stageLabel = (value?: string) => ({ uploaded: '已上传', parse_excel: '解析 Excel', structure_diagnosis: '结构诊断', content_rule_diagnosis: '内容规则诊断', ai_analysis: 'AI 深诊断', generate_suggestion: '生成建议', review_pending: '等待审核', human_review: '等待审核', completed: '诊断完成', failed: '失败' } as Record<string, string>)[value || ''] || value || '-'
const isTaskRunning = (item: WorkflowListItem) => ['pending', 'running'].includes(item.status)

function reviewStatusLabel(item: WorkflowListItem) {
  if (!item.review_batch_id) return '未创建审核批次'
  if (item.execution_status === 'executed') return '已执行'
  return ({ pending: '待审核', in_review: '审核中', completed: '审核完成' } as Record<string, string>)[item.review_status || ''] || item.review_status || '-'
}

async function loadTasks() {
  tasksLoading.value = true
  tasksError.value = ''
  try { tasks.value = await listWorkflows() }
  catch (e) { tasksError.value = e instanceof Error ? e.message : '诊断任务加载失败' }
  finally { tasksLoading.value = false }
}
function toggleAllTasks() { selectedTaskIds.value = selectedTaskIds.value.length === tasks.value.length ? [] : tasks.value.map(item => item.id) }
function openCleanup(mode: typeof cleanupMode.value) { cleanupMode.value = mode; showCleanup.value = true }
function deleteOneTask(item: WorkflowListItem) { selectedTaskIds.value=[item.id]; openCleanup('selected') }
async function cleanupCompleted() { showCleanup.value = false; selectedTaskIds.value = []; await Promise.all([loadTasks(), loadExistingFiles()]) }
function requestHistoryDelete(record: FileRecord) { historyDeleteTarget.value = record; showFileModal.value = false }
function closeHistoryDelete() { historyDeleteTarget.value = null; showFileModal.value = true }
async function historyDeleteCompleted() {
  const deletedActiveFile = historyDeleteTarget.value?.id === uploadedFileId.value
  historyDeleteTarget.value = null
  if (deletedActiveFile) {
    reset()
    file.value = null; fileName.value = ''; uploadedFileId.value = null
    rowCount.value = 0; columnCount.value = 0; columns.value = []
    nodeCount.value = 0; maxDepth.value = 0; leafCount.value = 0
    activeTaskId.value = null; activeReviewBatchId.value = null; resultVersionId.value = null
    analysisStatus.value = 'idle'
  }
  await Promise.all([loadTasks(), loadExistingFiles()])
  showFileModal.value = true
}

function focusTask(item: WorkflowListItem) {
  activeTaskId.value = item.id
  analysisStatus.value = item.status === 'failed' ? 'failed' : item.status === 'waiting_review' ? 'waiting_review' : ['partial','completed_degraded'].includes(item.status) ? 'partial' : item.status === 'completed' ? 'completed' : 'running'
  resultVersionId.value = item.version_id || null
  activeReviewBatchId.value = item.review_batch_id || null
  patch({ taskId: item.id, fileId: item.file_id, currentVersionId: item.version_id || null, reviewBatchId: item.review_batch_id || null })
}

async function retryTask(item: WorkflowListItem) {
  try {
    const record = await getFile(item.file_id)
    applyFileContext(record)
    await prepareTaxonomy(record.id)
    await startAnalysis()
  } catch (e) { error.value = e instanceof Error ? e.message : '重试失败' }
}
async function cancelTask(item: WorkflowListItem){try{await cancelWorkflow(item.id);await loadTasks()}catch(cause){tasksError.value=cause instanceof Error?cause.message:'取消失败'}}

function selectLocalFile(selected: File | null) {
  if (selected && !selected.name.toLowerCase().endsWith('.xlsx')) {
    error.value = '仅支持 .xlsx 格式的 Excel 文件。'
    file.value = null
    return
  }
  error.value = ''
  file.value = selected
  if (!selected) return
  fileName.value = selected.name
  rowCount.value = 0
  columnCount.value = 0
  columns.value = []
  uploadedFileId.value = null
  nodeCount.value = 0
  maxDepth.value = 0
  leafCount.value = 0
  activeTaskId.value = null
  activeReviewBatchId.value = null
  analysisStatus.value = 'idle'
  resultVersionId.value = null
  patch({ fileId: null, fileName: selected.name, fileRowCount: null, fileColumnCount: null,
    fileColumns: [], taskId: null, workflowId: null, threadId: null,
    currentVersionId: null, newVersionId: null, versionNo: null,
    reviewBatchId: null, reportPath: null })
}

function onPick(event: Event) {
  const target = event.target as HTMLInputElement
  selectLocalFile(target.files?.[0] || null)
}

function onDrop(event: DragEvent) {
  dragging.value = false
  selectLocalFile(event.dataTransfer?.files?.[0] || null)
}

function applyFileContext(record: FileRecord) {
  file.value = null
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

async function selectExistingFile(record: FileRecord) {
  applyFileContext(record)
  showFileModal.value = false
  await prepareTaxonomy(record.id)
}

async function prepareTaxonomy(fileId: number) {
  const overview = await importTaxonomy(fileId)
  nodeCount.value = overview.node_count
  maxDepth.value = overview.max_depth
  leafCount.value = overview.leaf_count
  patch({ currentVersionId: overview.version_id, versionNo: 'v1.0' })
}

function fmtTime(t?: string): string {
  if (!t) return '-'
  // strip timezone suffix for brevity
  return t.replace(/\+08:00$/, '')
}

async function submit() {
  if (!file.value) return
  uploading.value = true; error.value = ''
  try {
    const u = await uploadFile(file.value)
    fileName.value = u.file_name; rowCount.value = u.row_count; columnCount.value = u.column_count
    columns.value = u.columns; uploadedFileId.value = u.file_id
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
    patch({
      fileId: u.file_id, fileName: u.file_name, fileRowCount: u.row_count,
      fileColumnCount: u.column_count, fileColumns: u.columns,
      taskId: null, workflowId: null, threadId: null,
      currentVersionId: null, newVersionId: null, versionNo: null,
      reviewBatchId: null, reportPath: null,
    })
    await prepareTaxonomy(u.file_id)
    await loadExistingFiles()
  } catch (e) { error.value = e instanceof Error ? e.message : '上传失败' }
  finally { uploading.value = false }
}

async function startAnalysis() {
  if (!uploadedFileId.value) return
  analysisStatus.value = 'running'; error.value = ''
  try {
    const modelName = modelProvider.value === 'ollama' ? 'qwen3:8b' : 'deepseek-chat'
    const result = await startWorkflow(uploadedFileId.value, {
      enable_ai_analysis: enableAiAnalysis.value,
      model_provider: modelProvider.value,
      model_name: modelName,
      sample_strategy: sampleStrategy.value,
      focus_issues: focusIssuesText.value.split(',').map(item => item.trim()).filter(Boolean),
      ai_candidate_limit: aiCandidateLimit.value,
      ai_max_model_calls: aiMaxModelCalls.value,
      ai_token_budget: aiTokenBudget.value,
      ai_wall_seconds: aiWallSeconds.value,
    })
    activeTaskId.value = result.task_id
    activeReviewBatchId.value = null
    patch({ taskId: result.task_id, workflowId: result.workflow_id, threadId: result.thread_id,
      reviewBatchId: null, enableAiAnalysis: enableAiAnalysis.value,
      modelProvider: modelProvider.value, modelName, reportPath: null })
    await loadTasks()
  } catch (e) {
    analysisStatus.value = 'failed'
    error.value = e instanceof Error ? e.message : '启动失败'
  }
}

function onWorkflowProgress(payload: Record<string, unknown>) {
  const versionId = Number(payload.current_version_id || 0)
  if (versionId) {
    resultVersionId.value = versionId
    patch({ currentVersionId: versionId })
  }
}

async function onWorkflowCompleted() {
  if (!activeTaskId.value) return
  try {
    const result = await getWorkflowStatus(activeTaskId.value)
    analysisStatus.value = ['partial','completed_degraded'].includes(result.status) ? 'partial' : 'completed'
    resultVersionId.value = result.current_version_id || null
    activeReviewBatchId.value = result.review_batch_id || ''
    qualityBefore.value = result.quality_before ?? null
    qualityAfter.value = result.quality_after ?? null
    qualityDelta.value = result.quality_delta ?? null
    patch({ currentVersionId: result.current_version_id || null, versionNo: result.version_no || null,
      reportPath: result.report_path || null, reviewBatchId: result.review_batch_id || null })
    await loadTasks()
  } catch (e) { error.value = e instanceof Error ? e.message : '结果刷新失败' }
}

function onWorkflowFailed(message: string) {
  analysisStatus.value = 'failed'
  error.value = message || '诊断失败'
}

async function onWorkflowInterrupt(reviewBatchId: string) {
  analysisStatus.value = 'waiting_review'
  activeReviewBatchId.value = reviewBatchId
  if (activeTaskId.value) {
    try {
      const result = await getWorkflowStatus(activeTaskId.value)
      resultVersionId.value = result.current_version_id || null
      patch({
        currentVersionId: result.current_version_id || null,
        versionNo: result.version_no || null,
        reviewBatchId: result.review_batch_id || reviewBatchId,
        reportPath: result.report_path || null,
      })
    } catch (e) {
      error.value = e instanceof Error ? e.message : '审核上下文加载失败'
      patch({ reviewBatchId })
    }
  } else patch({ reviewBatchId })
  await loadTasks()
}

onMounted(async () => {
  await loadExistingFiles()
  await loadTasks()
  if (state.fileId && (!state.fileColumns.length || state.fileRowCount === null)) {
    try { applyFileContext(await getFile(state.fileId)) }
    catch { /* keep localStorage state */ }
  }
  if (state.fileId) {
    try { await prepareTaxonomy(state.fileId) }
    catch { /* diagnosis action will display a concrete error if preparation is invalid */ }
  }
  if (activeTaskId.value) {
    try {
      const task = await getWorkflowStatus(activeTaskId.value)
      analysisStatus.value = task.status === 'completed' ? 'completed' : ['partial','completed_degraded'].includes(task.status) ? 'partial' : task.status === 'failed' ? 'failed' : task.status === 'waiting_review' ? 'waiting_review' : 'running'
      resultVersionId.value = task.current_version_id || resultVersionId.value
      activeReviewBatchId.value = task.review_batch_id || activeReviewBatchId.value
    } catch { activeTaskId.value = null }
  }
  taskRefreshTimer = window.setInterval(loadTasks, 5000)
})
onBeforeUnmount(() => { if (taskRefreshTimer !== null) window.clearInterval(taskRefreshTimer) })
</script>

<style scoped>
.advanced-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;grid-column:1/-1}.advanced-grid label{display:grid;gap:6px}.advanced-grid span{font-size:12px;color:var(--muted)}.advanced-grid input,.advanced-grid select{padding:9px;border:1px solid var(--line);border-radius:10px;background:var(--surface-solid);color:var(--text)}
/* ---- main card: left-right layout ---- */
.main-card { max-width: 800px; }
.overview-strip { max-width: 1000px; display: grid; grid-template-columns: 2fr repeat(3, 1fr); gap: 16px; }
.overview-strip div { display: grid; gap: 6px; }
.overview-strip span { color: var(--muted); font-size: 12px; }
.overview-strip strong { font-size: 20px; overflow-wrap: anywhere; }
.diagnosis-config { max-width:1000px; }.option-grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; }.option-card { display:flex; gap:12px; align-items:flex-start; padding:16px; border:1px solid var(--line); border-radius:16px; cursor:pointer; background:rgba(255,255,255,.55); }.option-card.selected { border-color:var(--primary); background:rgba(10,132,255,.07); }.option-card span { display:grid; gap:5px; }.option-card small { color:var(--muted); line-height:1.5; }.model-config { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin-top:16px; }.model-config .panel-label { grid-column:1/-1; margin:0; }
.workflow-card { max-width:1000px; }.result-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; }
@media(max-width:680px){.option-grid,.model-config{grid-template-columns:1fr}}
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
.history-file-actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; min-width:150px; }
.danger-link { color:var(--danger); white-space:nowrap; }

.task-center { max-width: 100%; }
.task-id { display:block; margin-top:4px; color:var(--muted); font-size:11px; }
.task-progress { display:flex; align-items:center; gap:8px; min-width:110px; }
.task-progress progress { width:72px; }
.task-actions { display:flex; flex-wrap:wrap; gap:8px; align-items:center; min-width:220px; }
.task-error { flex-basis:100%; font-size:12px; }

.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
</style>
