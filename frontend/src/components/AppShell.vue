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
      <RouterLink
        v-for="item in navItems"
        :key="item.label"
        :to="item.to"
        class="shell-nav-item"
        :class="{ active: isActive(item) }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
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
        <label class="api-input" title="修改后端 API 服务地址（保存后立即生效，无需刷新）">
          API Base
          <span class="api-hint">后端服务地址</span>
          <input v-model="apiBaseUrl" @change="saveApiBaseUrl" type="text" placeholder="http://127.0.0.1:8000/api" />
          <small v-if="apiBaseError" class="error">{{ apiBaseError }}</small>
        </label>
        <div v-if="statusText" class="status-pill" :data-status="statusTone">{{ statusText }}</div>
      </div>
    </header>

    <main class="content-grid">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspace } from '../state/workspace'
import { normalizeApiBase } from '../api/client'

const route = useRoute()
const { state, patch } = useWorkspace()
const apiBaseUrl = ref(state.apiBaseUrl)
const apiBaseError = ref('')

type NavItem = { label: string; icon: string; to: string; match: string }

const navItems = computed<NavItem[]>(() => {
  const versionId = state.newVersionId || state.currentVersionId
  return [
    { label: '上传分析', icon: '⬆', to: '/upload', match: '/upload' },
    {
      label: '诊断结果', icon: '🩺',
      to: versionId ? `/diagnosis/${versionId}` : '/diagnosis',
      match: versionId ? `/diagnosis/${versionId}` : '/diagnosis',
    },
    {
      label: '建议审核',
      icon: '✅',
      to: '/reviews',
      match: '/reviews',
    },
    { label: '版本管理', icon: '🗂', to: '/versions', match: '/versions' },
    {
      label: '报告',
      icon: '📄',
      to: versionId ? `/report/${versionId}` : '/report',
      match: versionId ? `/report/${versionId}` : '/report',
    },
  ]
})

// 精确匹配当前路由，避免包含式匹配导致多个导航项同时高亮。
function isActive(item: NavItem): boolean {
  if (!item.match) return false
  return route.path === item.match
}

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

const statusText = computed(() => {
  if (route.params.taskId) return `任务 ${String(route.params.taskId)}`
  if (route.params.reviewBatchId) return `审核 ${String(route.params.reviewBatchId)}`
  if (route.params.versionId) return `版本 #${String(route.params.versionId)}`
  if (route.query.file_id) return `文件 #${String(route.query.file_id)}`
  if (route.path === '/upload' && state.fileId) return `文件 #${state.fileId}`
  return ''
})
const statusTone = computed(() => statusText.value ? 'active' : 'idle')

function saveApiBaseUrl() {
  try {
    const normalized = normalizeApiBase(apiBaseUrl.value)
    apiBaseUrl.value = normalized
    apiBaseError.value = ''
    patch({ apiBaseUrl: normalized })
  } catch (error) {
    apiBaseError.value = error instanceof Error ? error.message : 'API Base 无效'
  }
}
</script>
