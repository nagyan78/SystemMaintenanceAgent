<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div>
            <p class="eyebrow">可追溯的自动维护结果</p>
            <h2>{{ reportName || `Version ${versionId} 报告` }}</h2>
            <p class="lead">报告展示诊断结果、智能体自动决策依据和版本变更记录。</p>
          </div>
          <span class="badge" :data-tone="error ? 'danger' : markdown ? 'success' : 'warning'">{{ error ? '加载失败' : markdown ? '已生成' : '准备中' }}</span>
        </div>
        <div class="action-row">
          <button class="button secondary" :disabled="loading" @click="loadReport">{{ loading ? '正在加载…' : '刷新预览' }}</button>
          <a v-if="downloadUrl" :href="apiUrl(downloadUrl)" class="button primary">下载 Markdown</a>
        </div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </section>
      <MarkdownViewer v-if="markdown" title="报告预览" :markdown="markdown" />
      <section v-else-if="!loading && !error" class="card empty-state">
        <p class="eyebrow">尚无报告</p>
        <h2>完成一次工作流后即可查看</h2>
        <p class="lead">也可直接刷新，系统会为当前版本生成结构诊断报告。</p>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import { apiUrl } from '../api/client'
import { getReport } from '../api/versions'

const route = useRoute()
const versionId = computed(() => String(route.params.versionId))
const markdown = ref('')
const reportName = ref('')
const downloadUrl = ref('')
const loading = ref(false)
const error = ref('')

async function loadReport() {
  loading.value = true
  error.value = ''
  try {
    const report = await getReport(Number(versionId.value))
    markdown.value = report.markdown
    reportName.value = report.report_name
    downloadUrl.value = report.download_url
  } catch (err) {
    error.value = err instanceof Error ? err.message : '报告加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadReport)
</script>
