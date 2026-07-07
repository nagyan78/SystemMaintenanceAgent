<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">文件范围</p>
            <h2>按文件管理版本</h2>
          </div>
          <span class="badge">{{ files.length }} 个文件</span>
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
      </section>
      <VersionTable title="版本列表" name="version-picker" :versions="versions" :selected-ids="selectedIds" @select="selectVersion" />
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">差异与操作</p>
            <h2>版本对比</h2>
          </div>
          <span class="badge">file {{ selectedFileId || '-' }}</span>
        </div>
        <div class="action-row">
          <button class="button primary" :disabled="selectedIds.length !== 2" @click="loadDiff">查看 diff</button>
          <button class="button secondary" :disabled="!selectedIds[0]" @click="doExport">导出版本</button>
          <button class="button danger" :disabled="!selectedIds[0]" @click="doRollback">回滚版本</button>
        </div>
        <p v-if="message" class="lead">{{ message }}</p>
        <p v-if="downloadUrl" class="lead">下载地址：{{ downloadUrl }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>
      <VersionDiff v-if="diff" title="版本差异" :diff-label="`${fromVersion} → ${toVersion}`" :groups="diffGroups" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import VersionTable from '../components/VersionTable.vue'
import VersionDiff from '../components/VersionDiff.vue'
import { listFiles } from '../api/files'
import type { FileRecord } from '../api/files'
import { exportVersion, getVersionDiff, listVersions, rollbackVersion } from '../api/versions'
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
const downloadUrl = ref('')
const selectedFileId = ref(Number(route.query.file_id || state.fileId) || 0)
const orderedSelectedIds = computed(() => [...selectedIds.value].sort((left, right) => left - right))
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
    return
  }
  selectedIds.value = selectedIds.value.length >= 2 ? [selectedIds.value[1], id] : [...selectedIds.value, id]
}

async function loadDiff() {
  if (selectedIds.value.length !== 2) return
  error.value = ''
  try {
    const [fromId, toId] = orderedSelectedIds.value
    selectedIds.value = [fromId, toId]
    diff.value = await getVersionDiff(fromId, toId)
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
    downloadUrl.value = result.download_url
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
  } catch (err) {
    error.value = err instanceof Error ? err.message : '版本列表加载失败'
  }
}

onMounted(async () => {
  try {
    await loadFiles()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '文件列表加载失败'
  }
  await loadVersions()
})
</script>
