<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <p class="eyebrow">报告路径</p>
        <h2>Version {{ versionId }}</h2>
        <p class="lead">{{ reportPath || '暂无 report_path，后端生成后会自动展示。' }}</p>
        <div class="action-row" v-if="reportPath">
          <a :href="reportPath" class="button secondary" target="_blank" rel="noreferrer">打开文件</a>
        </div>
      </section>
      <MarkdownViewer v-if="markdown" title="报告预览" :markdown="markdown" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const { state } = useWorkspace()
const versionId = computed(() => String(route.params.versionId))
const reportPath = computed(() => state.reportPath)
const markdown = computed(() => reportPath.value ? `## 报告文件已生成\n\n路径：\`${reportPath.value}\`` : '')
</script>
