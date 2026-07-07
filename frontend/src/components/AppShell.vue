<template>
  <aside class="shell-sidebar">
    <div class="brand">
      <div class="brand-mark">T</div>
      <div>
        <div class="brand-name">Taxonomy Workbench</div>
        <div class="brand-subtitle">M5 前端工作台</div>
      </div>
    </div>
    <nav class="shell-nav">
      <RouterLink v-for="item in navItems" :key="item.label" :to="item.to" class="shell-nav-item">
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </aside>

  <div class="shell-main">
    <header class="topbar">
      <div>
        <div class="eyebrow">Local AI Workbench</div>
        <h1>{{ title }}</h1>
      </div>
      <div class="topbar-meta">
        <label class="api-input">
          API Base
          <input v-model="apiBaseUrl" @change="saveApiBaseUrl" type="text" />
        </label>
        <div class="status-pill" :data-status="statusTone">{{ statusText }}</div>
      </div>
    </header>

    <main class="content-grid">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const { state, patch } = useWorkspace()
const apiBaseUrl = ref(state.apiBaseUrl)
const navItems = computed(() => {
  const versionId = state.newVersionId || state.currentVersionId
  return [
    { to: '/upload', label: '上传分析' },
    { to: state.taskId ? `/workflow/${state.taskId}` : '/upload', label: '工作流' },
    {
      to: state.reviewBatchId
        ? `/review/${state.reviewBatchId}?task_id=${state.taskId || ''}`
        : state.taskId
          ? `/workflow/${state.taskId}`
          : '/upload',
      label: '建议审核',
    },
    { to: '/versions', label: '版本管理' },
    { to: versionId ? `/report/${versionId}` : '/versions', label: '报告' },
  ]
})

const title = computed(() => {
  if (route.path.startsWith('/workflow')) return '工作流进度'
  if (route.path.startsWith('/review')) return '建议审核'
  if (route.path.startsWith('/versions')) return '版本管理'
  if (route.path.startsWith('/report')) return '诊断报告'
  if (route.path.startsWith('/overview')) return '体系概览'
  if (route.path.startsWith('/tree')) return '分类树'
  if (route.path.startsWith('/diagnosis')) return '诊断问题'
  return '上传与启动'
})

const statusText = computed(() => state.taskId ? `Task ${state.taskId}` : 'Ready')
const statusTone = computed(() => state.taskId ? 'active' : 'idle')

function saveApiBaseUrl() {
  patch({ apiBaseUrl: apiBaseUrl.value })
}

watch(apiBaseUrl, value => patch({ apiBaseUrl: value }))
</script>
