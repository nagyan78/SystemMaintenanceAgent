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

type NavItem = { label: string; icon: string; to: string; match: string }

const navItems = computed<NavItem[]>(() => {
  const versionId = state.newVersionId || state.currentVersionId
  return [
    { label: '上传分析', icon: '⬆', to: '/upload', match: '/upload' },
    {
      label: '诊断结果', icon: '🩺',
      to: versionId ? `/diagnosis/${versionId}` : '/upload',
      match: versionId ? `/diagnosis/${versionId}` : '',
    },
    {
      label: '工作流',
      icon: '🔄',
      to: state.taskId ? `/workflow/${state.taskId}` : '/upload',
      match: state.taskId ? `/workflow/${state.taskId}` : '',
    },
    {
      label: '建议审核',
      icon: '✅',
      to: state.reviewBatchId
        ? `/review/${state.reviewBatchId}?task_id=${state.taskId || ''}`
        : state.taskId
          ? `/workflow/${state.taskId}`
          : '/upload',
      match: state.reviewBatchId ? `/review/${state.reviewBatchId}` : state.taskId ? `/workflow/${state.taskId}` : '',
    },
    { label: '版本管理', icon: '🗂', to: '/versions', match: '/versions' },
    { label: '质量评价', icon: '📊', to: '/evaluation', match: '/evaluation' },
    {
      label: '报告',
      icon: '📄',
      to: versionId ? `/report/${versionId}` : '/versions',
      match: versionId ? `/report/${versionId}` : '',
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
  if (route.path.startsWith('/evaluation')) return '质量评价'
  return '上传与启动'
})

const statusText = computed(() => (state.taskId ? `Task ${state.taskId}` : 'Ready'))
const statusTone = computed(() => (state.taskId ? 'active' : 'idle'))

function saveApiBaseUrl() {
  patch({ apiBaseUrl: apiBaseUrl.value })
}

watch(apiBaseUrl, (value) => patch({ apiBaseUrl: value }))
</script>
