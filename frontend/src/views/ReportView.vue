<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head"><div><p class="eyebrow">后端报告资源</p><h2>{{ activeVersionId ? `版本 #${activeVersionId}` : '选择报告版本' }}</h2></div><button v-if="activeVersionId" class="button secondary" :disabled="loading" @click="loadReport">刷新</button></div>
        <div v-if="!activeVersionId" class="action-row">
          <select v-model.number="selectedFileId" @change="loadSelectableVersions"><option :value="0">选择文件</option><option v-for="item in files" :key="item.id" :value="item.id">{{ item.file_name }}</option></select>
          <select v-model.number="selectedVersionId" :disabled="!selectedFileId"><option :value="0">选择版本</option><option v-for="item in versions" :key="item.id" :value="item.id">{{ item.version_no }}</option></select>
          <button class="button primary" :disabled="!selectedVersionId" @click="openSelectedVersion">查询报告</button>
        </div>
        <p v-if="loading" class="lead">正在查询报告资源…</p>
        <p v-else-if="pageState === 'not_found'" class="lead">报告不存在：该版本不存在。</p>
        <div v-else-if="pageState === 'not_generated'" class="empty-state"><h3>报告尚未生成</h3><p>{{ missingReason }}</p></div>
        <p v-else-if="pageState === 'error'" class="error">接口请求失败：{{ errorMessage }}</p>
        <template v-else-if="preview">
          <p class="lead"><span class="badge">{{ reportTypeLabel(preview.report_type) }}</span> {{ preview.report_path }}</p>
          <div class="action-row"><a :href="downloadUrl" class="button secondary">下载 Markdown</a><a :href="pdfDownloadUrl" class="button primary">下载 PDF 报告</a></div>
        </template>
      </section>
      <section v-if="resources.length > 1" class="card"><h3>该版本的报告资源</h3><div class="action-row"><button v-for="item in resources" :key="item.report_type" class="button secondary" @click="selectResource(item)">{{ reportTypeLabel(item.report_type) }}</button></div></section>
      <MarkdownViewer v-if="preview?.markdown" :title="reportTypeLabel(preview.report_type)" :markdown="preview.markdown" />
      <ReportQualitySummary v-if="activeVersionId" :version-id="activeVersionId" />
      <VersionOptimizationPanel v-if="activeVersionId" :version-id="activeVersionId" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import VersionOptimizationPanel from '../components/VersionOptimizationPanel.vue'
import ReportQualitySummary from '../components/ReportQualitySummary.vue'
import { ApiError, getApiOrigin } from '../api/client'
import { listFiles } from '../api/files'
import type { FileRecord } from '../api/files'
import { getVersion, listVersions } from '../api/versions'
import type { VersionRecord } from '../api/versions'
import { getReportPreview, listReports } from '../api/reports'
import type { ReportPreview, ReportResource, ReportType } from '../api/reports'
import { useWorkspace } from '../state/workspace'

const route = useRoute(), router = useRouter(), { patch } = useWorkspace()
const activeVersionId = computed(() => Number(route.params.versionId || 0))
const files = ref<FileRecord[]>([]), versions = ref<VersionRecord[]>([])
const selectedFileId = ref(0), selectedVersionId = ref(0)
const resources = ref<ReportResource[]>([]), preview = ref<ReportPreview | null>(null)
const loading = ref(false), errorMessage = ref(''), missingReason = ref('')
const pageState = ref<'idle' | 'ready' | 'not_generated' | 'not_found' | 'error'>('idle')
const downloadUrl = computed(() => preview.value ? `${getApiOrigin()}${preview.value.download_url}` : '')
const pdfDownloadUrl = computed(() => preview.value ? `${getApiOrigin()}${preview.value.pdf_download_url}` : '')
const reportTypeLabel = (type: ReportType) => ({ draft: '诊断草稿', partial: '部分完成报告', failed: '失败报告', final: '最终报告', historical: '历史诊断报告' }[type])

async function loadSelectableVersions() {
  versions.value = selectedFileId.value ? await listVersions(selectedFileId.value) : []
  selectedVersionId.value = 0
}
async function openSelectedVersion() {
  if (selectedVersionId.value) await router.push(`/report/${selectedVersionId.value}`)
}
async function selectResource(resource: ReportResource) {
  errorMessage.value = ''
  try {
    preview.value = await getReportPreview(resource.version_id, resource.report_type)
    pageState.value = 'ready'
  } catch (error) {
    preview.value = null
    if (error instanceof ApiError && error.status === 404) pageState.value = 'not_found'
    else {
      pageState.value = 'error'
      errorMessage.value = error instanceof Error ? error.message : '报告接口请求失败'
    }
  }
}
function requestedType(): ReportType | null {
  return ['draft', 'partial', 'failed', 'final', 'historical'].includes(String(route.query.type)) ? route.query.type as ReportType : null
}
async function loadReport() {
  loading.value = true; errorMessage.value = ''; missingReason.value = ''; preview.value = null; resources.value = []; pageState.value = 'idle'
  try {
    if (!files.value.length) files.value = await listFiles()
    if (!activeVersionId.value) return
    const version = await getVersion(activeVersionId.value)
    selectedFileId.value = version.file_id
    versions.value = await listVersions(version.file_id)
    selectedVersionId.value = version.id
    resources.value = await listReports(version.id)
    const requested = requestedType()
    const selected = requested
      ? resources.value.find(item => item.report_type === requested)
      : resources.value.find(item => item.report_type === 'final') || resources.value.find(item => item.report_type === 'partial') || resources.value.find(item => item.report_type === 'draft') || resources.value.find(item => item.report_type === 'failed') || resources.value.find(item => item.report_type === 'historical')
    if (!selected) {
      pageState.value = 'not_generated'
      if (requested === 'final' || (!requested && !version.parent_version_id)) missingReason.value = '最终报告需要先完成建议审核、执行修改、创建新版本并完成复诊。'
      else if (requested === 'draft') missingReason.value = '该版本尚未生成诊断草稿，请先完成诊断。'
      else missingReason.value = '后端没有找到该版本对应的报告资源。'
      return
    }
    await selectResource(selected)
    patch({ fileId: version.file_id, currentVersionId: version.id, versionNo: version.version_no, reportPath: selected.report_path })
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) pageState.value = 'not_found'
    else { pageState.value = 'error'; errorMessage.value = error instanceof Error ? error.message : '报告接口请求失败' }
  } finally { loading.value = false }
}

onMounted(loadReport)
watch(() => [route.params.versionId, route.query.type], loadReport)
</script>
