<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">文件范围</p>
            <h2>按文件管理版本</h2>
          </div>
          <span class="badge">{{ loadingFiles ? '正在读取文件…' : `${files.length} 个文件` }}</span>
        </div>
        <label class="api-input file-picker">
          当前文件
          <select v-model.number="selectedFileId" @change="onFileChange">
            <option :value="0">请选择文件</option>
            <option v-for="item in files" :key="item.id" :value="item.id">
              #{{ item.id }} {{ item.file_name }}（{{ item.row_count }} 行）
            </option>
          </select>
        </label>
        <p v-if="loadingFiles" class="muted">正在从后端读取文件列表…</p>
        <p v-else-if="!error && !files.length" class="muted">后端当前确实没有文件。</p>
      </section>

      <VersionTable title="版本列表" name="version-picker" :versions="versions" :selected-ids="selectedIds" @select="selectVersion" />

      <section class="card actions-card">
        <div class="card-head">
          <div>
            <p class="eyebrow">差异与操作</p>
            <h2>版本对比</h2>
          </div>
          <span class="badge">file {{ selectedFileId || '-' }}</span>
        </div>
        <div class="action-row">
          <button class="button primary" :disabled="selectedIds.length !== 2" @click="loadDiff">查看 Diff</button>
          <RouterLink v-if="selectedReportRoute" class="button secondary" :to="selectedReportRoute">查看报告</RouterLink>
          <button class="button secondary" :disabled="!selectedIds[0]" @click="doExport">导出版本</button>
          <button class="button danger" :disabled="!selectedIds[0]" @click="doRollback">回滚版本</button>
        </div>
        <p v-if="message" class="lead">{{ message }}</p>
        <p v-if="downloadUrl" class="lead">下载地址：<a :href="downloadUrl">下载导出文件</a></p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>

      <section v-if="quality" class="card quality-summary">
        <div class="card-head"><div><p class="eyebrow">复诊摘要</p><h2>版本质量摘要</h2></div><RouterLink class="button primary" :to="`/report/${quality.version_id}`">查看完整报告</RouterLink></div>
        <div class="metric-grid"><div><span>当前质量分</span><strong>{{ quality.quality_after ?? '-' }}</strong></div><div><span>问题数量</span><strong>{{ quality.before_issue_count }} → {{ quality.after_issue_count }}</strong></div><div><span>已解决</span><strong>{{ quality.resolved_issues.length }}</strong></div><div><span>新增</span><strong>{{ quality.new_issues.length }}</strong></div><div><span>改善率</span><strong>{{ quality.improvement_rate }}%</strong></div><div><span>复诊状态</span><strong>{{ quality.verification_status || '-' }}</strong></div></div>
      </section>

      <!-- ===== Diff 弹窗 ===== -->
      <Modal :show="showDiffModal" :title="`版本差异 ${fromVersion} → ${toVersion}`" @close="showDiffModal = false">
        <div v-if="diff" class="diff-in-modal">
          <div v-if="summaryText" class="diff-summary">{{ summaryText }}</div>

          <div v-for="group in diffGroups" :key="group.key" class="diff-section">
            <details open class="diff-details">
              <summary class="diff-summary-head">
                <span class="diff-kind" :data-kind="group.key">{{ kindLabel(group.key) }}</span>
                <span class="diff-count">{{ group.items.length }}</span>
                <span class="diff-kind-text">{{ group.label }}</span>
              </summary>
              <div class="hunks">
                <article v-for="(item, index) in group.items" :key="index" class="hunk" :data-kind="group.key">
                  <div class="hunk-head">{{ itemTitle(item) }}</div>
                  <div class="hunk-body">
                    <!-- synonym compare -->
                    <template v-if="group.key === 'synonym_changed' && hasCompare(item)">
                      <div class="diff-compare">
                        <div class="compare-col old">
                          <div class="compare-tag">修改前</div>
                          <div class="compare-val">{{ asText(item.old ?? item.old_synonyms ?? item.from) }}</div>
                        </div>
                        <div class="compare-arrow">→</div>
                        <div class="compare-col new">
                          <div class="compare-tag">修改后</div>
                          <div class="compare-val">{{ asText(item.new ?? item.new_synonyms ?? item.to) }}</div>
                        </div>
                      </div>
                    </template>
                    <!-- rename/move -->
                    <template v-else-if="(group.key === 'renamed' || group.key === 'moved') && hasCompare(item)">
                      <div class="diff-move">
                        <code>{{ asText(item.from ?? item.old) }}</code>
                        <span class="move-arrow">→</span>
                        <code>{{ asText(item.to ?? item.new) }}</code>
                      </div>
                    </template>
                    <!-- add/delete rows -->
                    <template v-else>
                      <div
                        v-for="(entry, i) in itemRows(item)"
                        :key="i"
                        class="diff-row"
                        :class="group.key === 'added' ? 'add' : group.key === 'deleted' ? 'del' : ''"
                      >
                        <span class="sign">{{ group.key === 'added' ? '+' : group.key === 'deleted' ? '−' : '' }}</span>
                        <span class="k">{{ entry[0] }}</span>
                        <span class="v">{{ entry[1] }}</span>
                      </div>
                    </template>
                  </div>
                </article>
              </div>
            </details>
          </div>
        </div>
      </Modal>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import VersionTable from '../components/VersionTable.vue'
import Modal from '../components/Modal.vue'
import { listFiles } from '../api/files'
import type { FileRecord } from '../api/files'
import { apiUrl } from '../api/client'
import { exportVersion, getVersionDiff, getVersionQuality, listVersions, rollbackVersion } from '../api/versions'
import type { VersionQuality } from '../api/versions'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const router = useRouter()
const { state, patch } = useWorkspace()
const files = ref<FileRecord[]>([])
const versions = ref<any[]>([])
const selectedIds = ref<number[]>([])
const diff = ref<any>(null)
const message = ref('')
const error = ref('')
const loadingFiles = ref(false)
const downloadUrl = ref('')
const quality = ref<VersionQuality | null>(null)
const selectedFileId = ref(Number(route.query.file_id || state.fileId) || 0)
const showDiffModal = ref(false)
const orderedSelectedIds = computed(() => [...selectedIds.value].sort((left, right) => left - right))
const optimizationVersionId = computed(() => orderedSelectedIds.value.at(-1) || 0)
const selectedReportRoute = computed(() => {
  const selectedVersionId = orderedSelectedIds.value[orderedSelectedIds.value.length - 1]
  const version = versions.value.find(item => item.id === selectedVersionId)
  if (!version) return ''
  const isFinal = Boolean(
    version.parent_version_id
      && version.action_batch_id
      && ['passed', 'partial'].includes(String(version.verification_status || '')),
  )
  return `/report/${version.id}?type=${isFinal ? 'final' : 'draft'}`
})
const fromVersion = computed(() => orderedSelectedIds.value[0] || '-')
const toVersion = computed(() => orderedSelectedIds.value[1] || '-')
const diffGroups = computed(() => diff.value ? [
  { key: 'added', label: '新增', items: diff.value.added || [] },
  { key: 'deleted', label: '删除', items: diff.value.deleted || [] },
  { key: 'renamed', label: '重命名', items: diff.value.renamed || [] },
  { key: 'moved', label: '移动', items: diff.value.moved || [] },
  { key: 'synonym_changed', label: '同义词变更', items: diff.value.synonym_changed || [] },
] : [])

function selectVersion(id: number) {
  if (selectedIds.value.includes(id)) {
    selectedIds.value = selectedIds.value.filter(value => value !== id)
    void loadQualitySummary()
    return
  }
  selectedIds.value = selectedIds.value.length >= 2 ? [selectedIds.value[1], id] : [...selectedIds.value, id]
  void loadQualitySummary()
}
async function loadQualitySummary(){quality.value=optimizationVersionId.value?await getVersionQuality(optimizationVersionId.value):null}

async function loadDiff() {
  if (selectedIds.value.length !== 2) return
  error.value = ''
  try {
    const [fromId, toId] = orderedSelectedIds.value
    selectedIds.value = [fromId, toId]
    diff.value = await getVersionDiff(fromId, toId)
    showDiffModal.value = true
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载 diff 失败'
  }
}

async function doExport() {
  error.value = ''
  downloadUrl.value = ''
  try {
    const result = await exportVersion(selectedIds.value[0])
    message.value = `导出成功：${result.export_path}`
    downloadUrl.value = apiUrl(result.download_url)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '导出失败'
  }
}

async function doRollback() {
  if (!confirm('确认回滚该版本？')) return
  error.value = ''
  try {
    const result = await rollbackVersion(selectedIds.value[0])
    message.value = `回滚完成：${JSON.stringify(result)}`
    await loadVersions()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '回滚失败'
  }
}

async function loadFiles() {
  files.value = await listFiles()
  if (!selectedFileId.value && state.fileId) selectedFileId.value = state.fileId
  if (!selectedFileId.value && files.value.length) selectedFileId.value = files.value[0].id
  syncSelectedFileToWorkspace()
}

function syncSelectedFileToWorkspace() {
  const selected = files.value.find(item => item.id === selectedFileId.value)
  patch({
    fileId: selected?.id || null,
    fileName: selected?.file_name || null,
    fileRowCount: selected?.row_count || null,
    fileColumnCount: selected?.column_count || null,
    fileColumns: selected?.columns || [],
    currentVersionId: null,
    newVersionId: null,
    versionNo: null,
    reportPath: null,
  })
}

async function onFileChange() {
  syncSelectedFileToWorkspace()
  await router.replace(selectedFileId.value ? `/versions?file_id=${selectedFileId.value}` : '/versions')
  await loadVersions()
}

async function loadVersions() {
  error.value = ''
  try {
    if (!selectedFileId.value) {
      versions.value = []
      selectedIds.value = []
      diff.value = null
      return
    }
    versions.value = await listVersions(selectedFileId.value || undefined)
    const newest = versions.value[versions.value.length - 1]
    const prev = versions.value[versions.value.length - 2]
    selectedIds.value = prev ? [prev.id, newest.id] : newest ? [newest.id] : []
    await loadQualitySummary()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '版本列表加载失败'
  }
}

/* ---- diff helpers ---- */
const META_KEYS = new Set(['id', 'category_id', 'from', 'to', 'old', 'new', 'old_synonyms', 'new_synonyms'])
const TITLE_KEYS = ['category_path', 'node_name', 'name', 'path', 'label', 'title']

function asText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function hasCompare(item: Record<string, unknown>): boolean {
  return 'old' in item || 'new' in item || 'old_synonyms' in item || 'new_synonyms' in item || ('from' in item && 'to' in item)
}

function itemTitle(item: Record<string, unknown>): string {
  for (const key of TITLE_KEYS) {
    if (item[key] != null && typeof item[key] !== 'object') return String(item[key])
  }
  if (item.category_id != null) return `节点 #${item.category_id}`
  const firstKey = Object.keys(item).find((k) => !META_KEYS.has(k) && item[k] != null)
  return firstKey ? String(item[firstKey]) : '未命名节点'
}

function itemRows(item: Record<string, unknown>): Array<[string, string]> {
  const rows: Array<[string, string]> = []
  for (const [key, value] of Object.entries(item)) {
    if (key === 'category_path' || key === 'node_name' || key === 'name') continue
    if (META_KEYS.has(key)) continue
    rows.push([key, asText(value)])
  }
  if (rows.length === 0) rows.push(['值', asText(item)])
  return rows
}

function kindLabel(key: string): string {
  const map: Record<string, string> = { added: 'A', deleted: 'D', renamed: 'R', moved: 'M', synonym_changed: 'S' }
  return map[key] ?? '·'
}

const summaryText = computed(() => {
  const parts = diffGroups.value.filter((g) => g.items.length > 0).map((g) => `${g.items.length} ${g.label}`)
  if (parts.length === 0) return '无变更'
  const total = diffGroups.value.reduce((sum, g) => sum + g.items.length, 0)
  return `共 ${total} 项变更：${parts.join('，')}`
})

onMounted(async () => {
  loadingFiles.value = true
  try {
    await loadFiles()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '文件列表加载失败'
  } finally {
    loadingFiles.value = false
  }
  await loadVersions()
})
</script>

<style scoped>
.actions-card { max-width: 720px; }
.quality-summary .metric-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.quality-summary .metric-grid div{padding:12px;border:1px solid var(--line);border-radius:12px}.quality-summary span{display:block;color:var(--muted);font-size:12px}.quality-summary strong{display:block;margin-top:5px;font-size:18px}@media(max-width:900px){.quality-summary .metric-grid{grid-template-columns:repeat(2,1fr)}}

/* ---- diff-in-modal overrides ---- */
.diff-in-modal { max-height: 60vh; overflow-y: auto; padding-right: 4px; }
.diff-in-modal::-webkit-scrollbar { width: 6px; }
.diff-in-modal::-webkit-scrollbar-thumb { background: rgba(17,24,39,.18); border-radius: 6px; }

.diff-summary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(17,24,39,0.05);
  font-size: 13px;
  color: var(--muted);
}
.diff-details {
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 0;
  margin-bottom: 12px;
  overflow: hidden;
  background: var(--surface-solid);
}
.diff-summary-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.diff-summary-head::-webkit-details-marker { display: none; }
.diff-kind {
  width: 22px; height: 22px; border-radius: 6px;
  display: grid; place-items: center;
  font-weight: 700; font-size: 12px; color: #fff; flex: none;
}
.diff-kind[data-kind='added'] { background: var(--success); }
.diff-kind[data-kind='deleted'] { background: var(--danger); }
.diff-kind[data-kind='renamed'] { background: #d97706; }
.diff-kind[data-kind='moved'] { background: #d97706; }
.diff-kind[data-kind='synonym_changed'] { background: #0a84ff; }
.diff-count { font-weight: 700; }
.diff-kind-text { color: var(--muted); font-size: 13px; }

.hunks { display: grid; gap: 1px; background: var(--line); border-top: 1px solid var(--line); }
.hunk { background: var(--surface-solid); }
.hunk-head { padding: 8px 16px; font-weight: 600; font-size: 13px; background: rgba(17,24,39,0.03); border-bottom: 1px solid var(--line); }
.hunk-body { padding: 6px 0; }

.diff-row {
  display: grid;
  grid-template-columns: 22px 160px 1fr;
  gap: 10px;
  padding: 4px 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
}
.diff-row .sign { color: var(--muted); text-align: center; }
.diff-row .k { color: var(--muted); }
.diff-row .v { color: var(--text); word-break: break-word; }
.diff-row.add { background: rgba(26,127,55,0.08); }
.diff-row.add .sign, .diff-row.add .k { color: var(--success); }
.diff-row.del { background: rgba(217,45,32,0.07); }
.diff-row.del .sign, .diff-row.del .k { color: var(--danger); }

.diff-compare { display: grid; grid-template-columns: 1fr 28px 1fr; gap: 0; padding: 8px 16px; }
.compare-col { padding: 8px 10px; border-radius: 8px; }
.compare-col.old { background: rgba(217,45,32,0.07); }
.compare-col.new { background: rgba(26,127,55,0.08); }
.compare-tag { font-size: 11px; color: var(--muted); margin-bottom: 4px; }
.compare-val { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12.5px; word-break: break-word; }
.compare-arrow { display: grid; place-items: center; color: var(--muted); }

.diff-move { display: flex; align-items: center; gap: 10px; padding: 10px 16px; font-family: ui-monospace, monospace; font-size: 12.5px; }
.diff-move code { background: rgba(217,153,6,0.12); color: #8a5b00; padding: 2px 8px; border-radius: 6px; }
.move-arrow { color: var(--muted); }
</style>
