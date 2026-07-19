<template>
  <AppShell>
    <div class="page-stack upload-page">
      <section class="upload-intro">
        <div>
          <p class="eyebrow">全自动维护闭环</p>
          <h2>导入产品标准体系</h2>
          <p>上传 Excel 后，可选择纯规则维护或接入 DeepSeek 增强分析；两种模式都会自动完成校验、执行与结果复诊。</p>
        </div>
        <ol class="flow-steps" aria-label="工作流步骤">
          <li class="current"><b>01</b>导入文件</li>
          <li><b>02</b>选择分析模式</li>
          <li><b>03</b>预览结果</li>
        </ol>
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
              <strong>{{ displayFileName }}</strong>
              <span>{{ file ? '待上传 · 尚未写入工作区' : `${rowCount} 行 · ${columnCount} 列 · 已就绪` }}</span>
              <button type="button" class="replace-file" @click.stop="fileInput?.click()">更换文件</button>
            </template>
          </label>

          <div class="upload-actions-panel">
            <div class="file-readiness"><span class="readiness-dot" :class="{ ready: !!uploadedFileId }"></span><div><small>当前状态</small><strong>{{ actionStatus }}</strong></div></div>
            <p>{{ actionHint }}</p>
            <button v-if="file && !uploadedFileId" class="button primary action-button" :disabled="loading" @click="submit">{{ loading ? '正在上传…' : '上传并识别字段' }}</button>
            <button v-else-if="uploadedFileId" class="button primary action-button" :disabled="loading" @click="startAnalysis">{{ loading ? '正在启动…' : enableAiAnalysis ? '开始 AI 增强维护' : '开始规则维护' }}</button>
            <button v-else class="button secondary action-button" @click="fileInput?.click()">选择 Excel 文件</button>
            <RouterLink v-if="currentVersionId" class="button secondary action-button" :to="`/tree/${currentVersionId}`">预览当前分类树</RouterLink>
            <button v-if="existingFiles.length" type="button" class="history-button" @click="showFileModal = true">从历史文件中选择 <span>{{ existingFiles.length }}</span></button>
          </div>
        </div>
        <p v-if="error" class="error-bar" role="alert">{{ error }}</p>
      </section>

      <section v-if="displayFileName" class="schema-card">
        <div><span class="section-kicker">导入检查</span><h2>字段识别</h2><p>确认文件列可用于构建产品分类树。</p></div>
        <div class="schema-content">
          <div class="schema-summary"><strong>{{ schemaMatch ? '字段完整' : '需要检查' }}</strong><span>已识别 {{ columns.length }} 个字段</span></div>
          <div class="chip-row"><span v-for="field in expectedFields" :key="field" class="chip" :data-found="columns.includes(field)">{{ field }}</span></div>
        </div>
      </section>

      <section v-if="uploadedFileId" class="card automation-card">
        <div class="card-head"><div><p class="eyebrow">执行配置</p><h2>选择分析模式</h2></div><span class="badge" data-tone="success">无需人工审批</span></div>
        <div class="automation-grid">
          <label class="model-option" :class="{ selected: !enableAiAnalysis }">
            <input v-model="enableAiAnalysis" class="mode-radio" type="radio" :value="false" @change="saveAiMode" />
            <span><strong>规则模式（不接入 AI）</strong><small>仅运行确定性规则诊断，不调用 DeepSeek，适合离线或未配置 API Key 时使用。</small></span>
          </label>
          <label class="model-option" :class="{ selected: enableAiAnalysis }">
            <input v-model="enableAiAnalysis" class="mode-radio" type="radio" :value="true" @change="saveAiMode" />
            <span><strong>AI 增强模式（DeepSeek）</strong><small>在规则诊断基础上，调用云端模型完成语义分析与自动审核。</small></span>
          </label>
        </div>
        <p class="automation-note">{{ enableAiAnalysis ? 'AI 生成的建议仍会经过确定性规则校验和内存快照预演；不安全或不完整的动作将自动跳过。' : '当前不会发起任何 DeepSeek 请求；系统只处理规则能够确定的问题和安全动作。' }}</p>
      </section>

      <section class="card task-center">
        <div class="card-head"><div><p class="eyebrow">执行记录</p><h2>维护任务</h2></div><button class="button secondary" :disabled="tasksLoading" @click="loadTasks">{{ tasksLoading ? '刷新中…' : '刷新' }}</button></div>
        <p v-if="tasksError" class="error">{{ tasksError }}</p>
        <div v-else-if="tasks.length" class="table-wrap">
          <table class="data-table task-table">
            <thead><tr><th>文件</th><th>阶段</th><th>状态</th><th>进度</th><th>问题</th><th>操作</th></tr></thead>
            <tbody><tr v-for="item in tasks" :key="item.id">
              <td><strong>{{ item.file_name || `文件 #${item.file_id}` }}</strong><small>{{ fmtTime(item.created_time) }}</small></td>
              <td>{{ stageLabel(item.current_step) }}</td>
              <td><span class="badge" :data-tone="taskTone(item.status)">{{ taskStatusLabel(item.status) }}</span></td>
              <td><div class="compact-progress"><span :style="{ width: `${item.progress || 0}%` }"></span></div><small>{{ item.progress || 0 }}%</small></td>
              <td>{{ item.issue_count ?? 0 }}</td>
              <td><div class="task-actions">
                <RouterLink v-if="isTaskRunning(item)" class="link-sm" :to="`/workflow/${item.id}`">查看进度</RouterLink>
                <RouterLink v-if="resultVersion(item)" class="link-sm" :to="`/tree/${resultVersion(item)}`">预览分类树</RouterLink>
                <RouterLink v-if="resultVersion(item)" class="link-sm" :to="`/diagnosis/${resultVersion(item)}`">诊断结果</RouterLink>
                <RouterLink v-if="item.final_report_available && resultVersion(item)" class="link-sm" :to="`/report/${resultVersion(item)}?type=final`">最终报告</RouterLink>
              </div></td>
            </tr></tbody>
          </table>
        </div>
        <p v-else-if="!tasksLoading" class="empty-hint">还没有维护任务。上传文件并启动后，执行进度会显示在这里。</p>
      </section>

      <Modal :show="showFileModal" title="选择历史文件" @close="showFileModal = false">
        <div v-if="existingFiles.length" class="table-wrap">
          <p class="modal-hint">选择已上传文件后，可按当前选择的分析模式启动新一轮自动维护。</p>
          <table class="data-table selectable file-table"><thead><tr><th>文件</th><th>数据规模</th><th>上传时间</th></tr></thead><tbody>
            <tr v-for="item in existingFiles" :key="item.id" :class="{ selected: item.id === uploadedFileId }" @click="selectExistingFile(item)"><td><strong>{{ item.file_name }}</strong><span class="muted">文件 #{{ item.id }}</span></td><td class="muted">{{ item.row_count }} 行 · {{ item.column_count }} 列</td><td class="muted">{{ fmtTime(item.upload_time) }}</td></tr>
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
import { listWorkflows, startWorkflow } from '../api/workflows'
import type { WorkflowListItem } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const router = useRouter()
const { state, patch } = useWorkspace()
const fileInput = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const loading = ref(false), error = ref(''), dragging = ref(false)
const uploadedFileId = ref<number | null>(state.fileId)
const fileName = ref(state.fileName || '')
const rowCount = ref(state.fileRowCount || 0), columnCount = ref(state.fileColumnCount || 0)
const columns = ref<string[]>(state.fileColumns || [])
const existingFiles = ref<FileRecord[]>([]), tasks = ref<WorkflowListItem[]>([])
const showFileModal = ref(false), tasksLoading = ref(false), tasksError = ref('')
const enableAiAnalysis = ref(state.enableAiAnalysis)
const expectedFields = ['category_id', 'category_name', 'category_group_id', 'category_pids', 'category_group_name', 'syn_list']
const displayFileName = computed(() => file.value?.name || fileName.value)
const schemaMatch = computed(() => expectedFields.every(field => columns.value.includes(field)))
const currentVersionId = computed(() => state.newVersionId || state.currentVersionId)
const actionStatus = computed(() => uploadedFileId.value ? '可以开始自动维护' : file.value ? '可以上传文件' : '等待选择文件')
const actionHint = computed(() => uploadedFileId.value
  ? enableAiAnalysis.value
    ? '将使用规则诊断与 DeepSeek 增强分析，并自动完成审核、执行和复诊。'
    : '将仅使用确定性规则完成诊断、执行和复诊，不调用任何 AI 模型。'
  : file.value ? '先上传并检查字段，再选择分析模式。' : '支持标准产品分类体系 .xlsx 文件。')

function onPick(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; uploadedFileId.value = null; error.value = '' }
function onDrop(event: DragEvent) { dragging.value = false; file.value = event.dataTransfer?.files?.[0] || null; uploadedFileId.value = null; error.value = '' }
function saveAiMode() { patch({ enableAiAnalysis: enableAiAnalysis.value }) }
function applyFileContext(record: FileRecord) {
  file.value = null; fileName.value = record.file_name; rowCount.value = record.row_count; columnCount.value = record.column_count; columns.value = record.columns || []; uploadedFileId.value = record.id
  patch({ fileId: record.id, fileName: record.file_name, fileRowCount: record.row_count, fileColumnCount: record.column_count, fileColumns: record.columns || [], taskId: null, workflowId: null, threadId: null, currentVersionId: null, newVersionId: null, versionNo: null, reviewBatchId: null, reportPath: null })
}
async function loadExistingFiles() { try { existingFiles.value = await listFiles() } catch (cause) { error.value = cause instanceof Error ? cause.message : '历史文件加载失败' } }
async function loadTasks() { tasksLoading.value = true; tasksError.value = ''; try { tasks.value = await listWorkflows() } catch (cause) { tasksError.value = cause instanceof Error ? cause.message : '任务加载失败' } finally { tasksLoading.value = false } }
function selectExistingFile(record: FileRecord) { applyFileContext(record); showFileModal.value = false }
function fmtTime(value?: string) { return value ? value.replace('T', ' ').replace(/\+08:00$/, '').slice(0, 19) : '—' }
function resultVersion(item: WorkflowListItem) { return item.new_version_id || item.version_id || 0 }
function isTaskRunning(item: WorkflowListItem) { return ['pending', 'running'].includes(item.status) }
function taskTone(status: string) { return status === 'failed' ? 'danger' : ['completed', 'completed_degraded', 'partial'].includes(status) ? 'success' : 'warning' }
function taskStatusLabel(status: string) { return ({ pending: '等待启动', running: '自动执行中', waiting_review: '旧任务已暂停', partial: '部分完成', completed_degraded: '降级完成', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status }
function stageLabel(step?: string) { return ({ uploaded: '已上传', parse_excel: '解析 Excel', build_tree: '构建分类树', structure_diagnosis: '结构诊断', content_rule_diagnosis: '内容筛查', content_diagnosis: '内容诊断', ai_analysis: 'AI 深诊断', generate_suggestion: '生成建议', ai_review: 'AI 自动审核', validate_action: '规则校验', execute_action: '执行修改', save_new_version: '保存版本', verify_new_version: '结果复诊', completed: '生成报告', failed: '执行失败' } as Record<string, string>)[step || ''] || step || '—' }

async function submit() {
  if (!file.value) return
  loading.value = true; error.value = ''
  try { const uploaded = await uploadFile(file.value); applyFileContext({ id: uploaded.file_id, ...uploaded }); await loadExistingFiles() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '上传失败' }
  finally { loading.value = false }
}
async function startAnalysis() {
  if (!uploadedFileId.value) return
  loading.value = true; error.value = ''
  const useAi = enableAiAnalysis.value
  const modelProvider = 'deepseek' as const
  const modelName = useAi ? 'deepseek-chat' : ''
  try {
    const workflow = await startWorkflow(uploadedFileId.value, {
      enable_ai_analysis: useAi,
      ...(useAi ? { model_provider: modelProvider, model_name: modelName } : {})
    })
    patch({ taskId: workflow.task_id, workflowId: workflow.workflow_id, threadId: workflow.thread_id, enableAiAnalysis: useAi, modelProvider, modelName })
    await router.push(`/workflow/${workflow.task_id}`)
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '自动维护启动失败' }
  finally { loading.value = false }
}

onMounted(async () => { await Promise.all([loadExistingFiles(), loadTasks()]); if (state.fileId && !state.fileColumns.length) { try { applyFileContext(await getFile(state.fileId)) } catch { /* retain local context */ } } })
</script>

<style scoped>
.upload-page{gap:26px}.upload-intro{display:flex;align-items:end;justify-content:space-between;gap:32px;padding:6px 0 2px}.upload-intro h2{margin:5px 0 9px;font-size:clamp(1.55rem,3vw,2.15rem);letter-spacing:-.035em}.upload-intro p{max-width:660px;margin:0;color:var(--muted)}.flow-steps{display:flex;gap:20px;padding:0;margin:0;list-style:none;color:var(--muted);font-size:12px;white-space:nowrap}.flow-steps li{display:grid;gap:4px}.flow-steps b{color:#9ca3af;font-size:11px}.flow-steps .current,.flow-steps .current b{color:var(--primary)}
.upload-workspace{overflow:hidden;border:1px solid var(--line);border-radius:18px;background:var(--surface);box-shadow:var(--shadow)}.upload-workspace-head{display:flex;justify-content:space-between;align-items:start;padding:22px 26px;border-bottom:1px solid var(--line)}.upload-workspace-head h2,.schema-card h2{margin:3px 0 0;font-size:1.05rem}.section-kicker{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase}.file-format{padding:5px 8px;border:1px solid var(--line);border-radius:6px;color:var(--muted);font-size:11px;font-weight:700}.upload-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px}.dropzone{min-height:286px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:32px;border-right:1px solid var(--line);background:#fbfcfe;color:var(--muted);cursor:pointer;transition:.2s}.dropzone:hover,.dropzone.is-dragging{background:#f2f7ff;color:var(--primary)}.dropzone.has-file{background:#f7fbf8;color:var(--text)}.upload-glyph{width:42px;height:42px;fill:none;stroke:var(--primary);stroke-width:2;stroke-linecap:round;stroke-linejoin:round}.upload-glyph.success{stroke:var(--success)}.dropzone strong{color:var(--text);font-size:15px}.dropzone span{font-size:13px}.replace-file{border:0;padding:0;background:transparent;color:var(--primary);cursor:pointer}.upload-actions-panel{display:flex;flex-direction:column;justify-content:center;gap:15px;padding:26px}.file-readiness{display:flex;align-items:center;gap:10px}.readiness-dot{width:9px;height:9px;border-radius:50%;background:#aeb7c3}.readiness-dot.ready{background:var(--success);box-shadow:0 0 0 4px rgba(39,122,75,.12)}.file-readiness small,.file-readiness strong{display:block}.file-readiness small{color:var(--muted);font-size:11px}.upload-actions-panel>p{margin:0;color:var(--muted);font-size:13px}.action-button{width:100%}.history-button{border:0;padding:10px 0 0;border-top:1px solid var(--line);background:none;color:var(--muted);cursor:pointer;text-align:left;font-size:12px}.history-button span{display:inline-grid;place-items:center;min-width:18px;height:18px;margin-left:4px;border-radius:50%;background:#edf1f7}.error-bar{margin:0;padding:11px 26px;border-top:1px solid rgba(200,62,58,.15);background:#fff5f4;color:var(--danger);font-size:13px}
.schema-card{display:grid;grid-template-columns:220px 1fr;gap:28px;padding:22px 26px;border:1px solid var(--line);border-radius:16px;background:var(--surface)}.schema-card p{margin:7px 0 0;color:var(--muted);font-size:13px}.schema-content{display:grid;gap:14px}.schema-summary{display:flex;align-items:baseline;gap:8px}.schema-summary span{color:var(--muted);font-size:12px}.chip{border:1px solid var(--line);border-radius:7px;background:#fbfcfe}.chip[data-found='true']{border-color:rgba(39,122,75,.28);background:#f3faf5;color:#176638}.automation-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.model-option{display:flex;align-items:flex-start;gap:12px;padding:16px;border:1px solid var(--line);border-radius:12px;cursor:pointer}.model-option.selected{border-color:#9bb8f1;background:#f5f8ff}.mode-radio{margin:3px 0 0;accent-color:var(--primary)}.model-option span,.model-option small{display:block}.model-option small{margin-top:4px;color:var(--muted);line-height:1.45}.automation-note{margin:14px 0 0;color:var(--muted);font-size:12px}.task-table td strong,.task-table td small{display:block}.compact-progress{width:100px;height:5px;overflow:hidden;border-radius:999px;background:#edf0f5}.compact-progress span{display:block;height:100%;border-radius:inherit;background:var(--primary)}.task-actions{display:flex;flex-wrap:wrap;gap:8px}.link-sm{color:var(--primary);font-size:12px;font-weight:650}.file-table td strong,.file-table td .muted{display:block}.modal-hint{color:var(--muted);font-size:13px}
@media(max-width:760px){.upload-intro{align-items:start;flex-direction:column}.upload-layout,.schema-card,.automation-grid{grid-template-columns:1fr}.dropzone{min-height:220px;border-right:0;border-bottom:1px solid var(--line)}.flow-steps{width:100%;justify-content:space-between;gap:8px}}
</style>
