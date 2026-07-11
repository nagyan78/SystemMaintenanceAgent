<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <p class="eyebrow">报告路径</p>
        <h2>Version {{ versionId }}</h2>
        <p class="lead" v-if="loading">正在读取报告…</p>
        <p class="lead error" v-else-if="errorMessage">{{ errorMessage }}</p>
        <p class="lead" v-else>{{ reportPath }}</p>
        <div class="action-row" v-if="downloadUrl">
          <a :href="downloadUrl" class="button secondary">下载 Markdown</a>
        </div>
      </section>
      <MarkdownViewer v-if="markdown" title="报告预览" :markdown="markdown" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { API_BASE_URL } from '../api/client'
import { generateReport, getReportPreview } from '../api/reports'
import AppShell from '../components/AppShell.vue'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const { patch } = useWorkspace()
const versionId = computed(() => Number(route.params.versionId))
const reportPath = ref('')
const downloadUrl = ref('')
const markdown = ref('')
const loading = ref(true)
const errorMessage = ref('')

function absoluteApiUrl(path: string) {
  const base = (localStorage.getItem('apiBaseUrl') || API_BASE_URL).replace(/\/api\/?$/, '')
  return `${base}${path}`
}

async function loadReport() {
  loading.value = true
  errorMessage.value = ''
  try {
    let preview
    try {
      preview = await getReportPreview(versionId.value)
    } catch {
      await generateReport(versionId.value)
      preview = await getReportPreview(versionId.value)
    }
    reportPath.value = preview.report_path
    downloadUrl.value = absoluteApiUrl(preview.download_url)
    markdown.value = preview.markdown
    patch({
      reportPath: preview.report_path,
      currentVersionId: preview.version_id,
      versionNo: preview.version_no,
    })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '报告生成失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadReport)
</script>
