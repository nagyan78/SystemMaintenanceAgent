<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head"><div><p class="eyebrow">产品体系版本质量</p><h2>版本质量对比</h2></div></div>
        <div class="action-row">
          <select v-model.number="fileId" :disabled="loadingFiles" @change="loadVersions"><option :value="0">选择文件</option><option v-for="file in files" :key="file.id" :value="file.id">{{ file.file_name }}</option></select>
          <select v-model.number="versionId" :disabled="loadingVersions || !fileId" @change="loadQuality"><option :value="0">选择版本</option><option v-for="version in versions" :key="version.id" :value="version.id">{{ version.version_no }} · {{ version.lifecycle_status || 'draft' }}</option></select>
        </div>
        <p v-if="loadingFiles || loadingVersions" class="muted">正在读取文件和版本…</p><p v-else-if="error" class="error">{{ error }}</p><p v-else-if="!versionId" class="muted">请选择需要评价的版本。</p>
      </section>

      <p v-if="loadingQuality" class="muted">正在计算版本质量…</p>
      <section v-if="quality" class="metric-grid">
        <div class="metric"><span>修改前问题</span><strong>{{ quality.before_issue_count }}</strong></div><div class="metric"><span>修改后问题</span><strong>{{ quality.after_issue_count }}</strong></div>
        <div class="metric"><span>已解决</span><strong>{{ quality.resolved_issues.length }}</strong></div><div class="metric"><span>未解决</span><strong>{{ quality.unresolved_issues.length }}</strong></div>
        <div class="metric danger"><span>新增</span><strong>{{ quality.new_issues.length }}</strong></div><div class="metric"><span>待确认</span><strong>{{ quality.deferred_issues.length }}</strong></div>
        <div class="metric"><span>误报</span><strong>{{ quality.false_positive_issues.length }}</strong></div><div class="metric"><span>质量分</span><strong>{{ quality.quality_before ?? '-' }} → {{ quality.quality_after ?? '-' }}</strong></div>
        <div class="metric"><span>改善率</span><strong>{{ quality.improvement_rate }}%</strong></div><div class="metric"><span>生命周期</span><strong class="status-text">{{ quality.lifecycle_status || '-' }}</strong></div>
      </section>

      <section v-if="quality" class="quality-groups">
        <article v-for="group in issueGroups" :key="group.label" class="card">
          <h2>{{ group.label }}（{{ group.items.length }}）</h2>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>问题类型</th><th>节点</th><th>风险</th><th>说明</th></tr></thead><tbody>
            <tr v-for="issue in group.items" :key="Number(issue.id)"><td>{{ issue.issue_type_label || issue.issue_type }}</td><td>{{ issue.node_name || '-' }}</td><td>{{ issue.risk_level || '-' }}</td><td>{{ issue.description || '-' }}</td></tr>
            <tr v-if="!group.items.length"><td colspan="4">无</td></tr>
          </tbody></table></div>
        </article>
      </section>
      <VersionOptimizationPanel v-if="versionId" :version-id="versionId" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import VersionOptimizationPanel from '../components/VersionOptimizationPanel.vue'
import { describeApiError } from '../api/client'
import { listFiles } from '../api/files'
import type { FileRecord } from '../api/files'
import { getVersionQuality, listVersions } from '../api/versions'
import type { VersionQuality, VersionRecord } from '../api/versions'
import { useWorkspace } from '../state/workspace'

const route = useRoute(), router = useRouter(), { patch } = useWorkspace()
const files = ref<FileRecord[]>([]), versions = ref<VersionRecord[]>([])
const fileId = ref(Number(route.query.file_id) || 0), versionId = ref(Number(route.query.version_id) || 0)
const quality = ref<VersionQuality | null>(null), error = ref('')
const loadingFiles = ref(false), loadingVersions = ref(false), loadingQuality = ref(false)
const issueGroups = computed(() => quality.value ? [
  { label: '已解决', items: quality.value.resolved_issues }, { label: '未解决', items: quality.value.unresolved_issues },
  { label: '新增问题', items: quality.value.new_issues }, { label: '待确认', items: quality.value.deferred_issues },
  { label: '误报', items: quality.value.false_positive_issues },
] : [])

async function syncRoute() { const query: Record<string, string> = {}; if (fileId.value) query.file_id = String(fileId.value); if (versionId.value) query.version_id = String(versionId.value); await router.replace({ path: '/evaluation', query }) }
async function loadVersions() {
  error.value = ''; quality.value = null; versions.value = []
  if (!fileId.value) { versionId.value = 0; await syncRoute(); return }
  loadingVersions.value = true
  try {
    versions.value = await listVersions(fileId.value)
    if (!versions.value.some(item => item.id === versionId.value)) versionId.value = versions.value.at(-1)?.id || 0
    const file = files.value.find(item => item.id === fileId.value); patch({ fileId: file?.id || null, fileName: file?.file_name || null })
    await syncRoute(); await loadQuality()
  } catch (cause) { error.value = describeApiError(cause, '版本列表加载失败') }
  finally { loadingVersions.value = false }
}
async function loadQuality() {
  error.value = ''; quality.value = null; await syncRoute(); if (!versionId.value) return; loadingQuality.value = true
  try { quality.value = await getVersionQuality(versionId.value); const version = versions.value.find(item => item.id === versionId.value); patch({ fileId: version?.file_id || fileId.value || null, currentVersionId: versionId.value, newVersionId: version?.parent_version_id ? versionId.value : null, versionNo: version?.version_no || null }) }
  catch (cause) { error.value = describeApiError(cause, '版本质量加载失败') }
  finally { loadingQuality.value = false }
}
onMounted(async () => { loadingFiles.value = true; try { files.value = await listFiles(); if (!fileId.value && versionId.value) fileId.value = (await listVersions()).find(item => item.id === versionId.value)?.file_id || 0; if (!fileId.value && files.value.length) fileId.value = files.value[0].id; await loadVersions() } catch (cause) { error.value = describeApiError(cause, '文件列表加载失败') } finally { loadingFiles.value = false } })
watch(() => route.query.version_id, value => { const next = Number(value) || 0; if (next && next !== versionId.value) { versionId.value = next; void loadQuality() } })
</script>

<style scoped>
.metric-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; }.metric { padding:16px; border:1px solid var(--line); border-radius:14px; background:var(--surface-solid); }.metric span { display:block; color:var(--muted); }.metric strong { display:block; font-size:25px; margin-top:7px; }.metric.danger strong { color:var(--danger); }.metric .status-text { font-size:18px; }.quality-groups { display:grid; gap:14px; }@media (max-width:900px){.metric-grid{grid-template-columns:repeat(2,1fr)}}
</style>
