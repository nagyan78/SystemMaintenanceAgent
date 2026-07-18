<template>
  <aside class="shell-sidebar" aria-label="主导航">
    <RouterLink to="/upload" class="brand" aria-label="返回上传与启动">
      <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
      <span>
        <strong class="brand-name">Taxonomy</strong>
        <span class="brand-subtitle">Maintenance Studio</span>
      </span>
    </RouterLink>

    <nav class="shell-nav">
      <section v-for="group in navGroups" :key="group.label" class="nav-group">
        <p>{{ group.label }}</p>
        <RouterLink
          v-for="item in group.items"
          :key="item.label"
          :to="item.to"
          class="shell-nav-item"
          :class="{ active: isActive(item) }"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="item.icon" /></svg>
          <span>{{ item.label }}</span>
        </RouterLink>
      </section>
    </nav>

    <div class="sidebar-footer"><span class="footer-dot"></span>本地工作区</div>
  </aside>

  <div class="shell-main">
    <header class="topbar">
      <div>
        <p class="eyebrow">产品标准体系维护</p>
        <h1>{{ title }}</h1>
      </div>
      <div class="topbar-meta">
        <details class="connection-control">
          <summary><span class="status-dot" :data-status="statusTone"></span>{{ statusText }}</summary>
          <label>
            API 服务地址
            <input v-model="apiBaseUrl" @change="saveApiBaseUrl" type="text" placeholder="http://127.0.0.1:8000/api" />
          </label>
        </details>
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

const navGroups = computed(() => {
  const versionId = state.newVersionId || state.currentVersionId
  return [
    {
      label: '工作台',
      items: [
        { label: '上传与启动', icon: 'M12 3v12m0-12 4 4m-4-4L8 7M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5', to: '/upload', match: '/upload' },
        { label: '执行进度', icon: 'M4 12a8 8 0 1 0 2-5.3M4 5v5h5M12 8v5l3 2', to: state.taskId ? `/workflow/${state.taskId}` : '/upload', match: state.taskId ? `/workflow/${state.taskId}` : '' },
        { label: '版本管理', icon: 'M4 6.5 12 3l8 3.5v11L12 21l-8-3.5v-11ZM4 6.5 12 10l8-3.5M12 10v11', to: '/versions', match: '/versions' },
      ],
    },
    {
      label: '结果查看',
      items: [
        { label: '体系概览', icon: 'M5 19V9m7 10V5m7 14v-7', to: versionId ? `/overview/${versionId}` : '/versions', match: versionId ? `/overview/${versionId}` : '' },
        { label: '分类浏览', icon: 'M5 4v16m0-8h6m0 0v8m0-8h8m-8 0V4', to: versionId ? `/tree/${versionId}` : '/versions', match: versionId ? `/tree/${versionId}` : '' },
        { label: '诊断问题', icon: 'M12 9v4m0 4h.01M10 3h4l7 7-7 11h-4L3 10l7-7Z', to: versionId ? `/diagnosis/${versionId}` : '/versions', match: versionId ? `/diagnosis/${versionId}` : '' },
        { label: '诊断报告', icon: 'M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm6 0v5h5M8 13h8m-8 4h6', to: versionId ? `/report/${versionId}` : '/versions', match: versionId ? `/report/${versionId}` : '' },
      ],
    },
  ]
})

function isActive(item: NavItem): boolean {
  return Boolean(item.match) && route.path === item.match
}

const title = computed(() => {
  if (route.path.startsWith('/workflow')) return '执行进度'
  if (route.path.startsWith('/versions')) return '版本管理'
  if (route.path.startsWith('/report')) return '诊断报告'
  if (route.path.startsWith('/overview')) return '体系概览'
  if (route.path.startsWith('/tree')) return '分类浏览'
  if (route.path.startsWith('/diagnosis')) return '诊断问题'
  return '上传与启动'
})

const statusText = computed(() => state.taskId ? '任务进行中' : '服务已连接')
const statusTone = computed(() => state.taskId ? 'active' : 'ready')
function saveApiBaseUrl() { patch({ apiBaseUrl: apiBaseUrl.value }) }
watch(apiBaseUrl, value => patch({ apiBaseUrl: value }))
</script>
