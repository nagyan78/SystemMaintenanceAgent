<template>
  <AppShell>
    <div class="page-stack">
      <section class="report-hero">
        <div>
          <div class="eyebrow">体系体检报告</div>
          <h2>诊断结果</h2>
          <p class="lead">集中查看系统发现的问题、判断依据和可执行修改建议。</p>
        </div>
        <div class="action-row">
          <button v-if="summary" class="button primary" :disabled="applying" @click="applyFixes">
            {{ applying ? '正在生成 v1.1…' : '执行修改并生成 v1.1' }}
          </button>
          <RouterLink v-if="summary" class="button primary" :to="`/report/${summary.version_id}?type=${summary.report_type || 'draft'}`">查看诊断报告</RouterLink>
          <button class="button secondary" :disabled="loading" @click="loadAll">刷新结果</button>
        </div>
      </section>

      <section v-if="!activeVersionId" class="card">
        <div class="card-head"><div><p class="eyebrow">后端版本资源</p><h2>选择要查看的版本</h2></div></div>
        <div class="action-row">
          <select v-model.number="selectedFileId" @change="loadSelectableVersions"><option :value="0">选择文件</option><option v-for="item in files" :key="item.id" :value="item.id">{{ item.file_name }}</option></select>
          <select v-model.number="selectedVersionId" :disabled="!selectedFileId"><option :value="0">选择版本</option><option v-for="item in selectableVersions" :key="item.id" :value="item.id">{{ item.version_no }}</option></select>
          <button class="button primary" :disabled="!selectedVersionId" @click="openSelectedVersion">打开诊断结果</button>
        </div>
        <p v-if="!loading && !files.length && !error" class="muted">确实没有可选择的上传文件。</p>
      </section>

      <p v-if="loading" class="card lead">正在读取诊断结果…</p>
      <p v-else-if="statusMessage" class="card lead">{{ statusMessage }}</p>
      <p v-if="error" class="card error">{{ error }}</p>
      <section v-if="summary?.ai_analysis_status === 'partial'" class="card partial-warning">
        <div><strong>AI 分析部分完成</strong><p>{{ summary.ai_warning || '模型预算耗尽，已保留规则诊断和部分 AI 结果。' }}</p></div>
        <RouterLink class="button secondary" :to="`/report/${summary.version_id}?type=draft`">打开降级报告</RouterLink>
      </section>
      <section v-if="summary" class="metric-grid">
        <div class="metric"><span>节点总数</span><strong>{{ summary.total_nodes }}</strong></div>
        <div class="metric"><span>结构问题</span><strong>{{ summary.structure_issue_count }}</strong></div>
        <div class="metric"><span>内容问题</span><strong>{{ summary.content_issue_count }}</strong></div>
        <div class="metric danger-metric"><span>高风险问题</span><strong>{{ summary.high_risk_count }}</strong></div>
        <div class="metric score"><span>综合评分</span><strong>{{ summary.quality_score }}</strong></div>
      </section>
      <section v-if="summary" class="card run-config-bar">
        <div><span>本次诊断模式</span><strong>{{ summary.enable_ai_analysis ? 'AI 增强模式' : '快速规则模式' }}</strong></div>
        <div><span>模型</span><strong>{{ summary.enable_ai_analysis ? summary.model_name : '未启用' }}</strong></div>
        <RouterLink class="button secondary" to="/upload">返回上传分析</RouterLink>
        <RouterLink v-if="summary.version_id" class="button primary" :to="`/tree/${summary.version_id}`">预览分类树</RouterLink>
      </section>
      <section v-if="summary?.coverage" class="card coverage-card">
        <div class="card-head"><div><p class="eyebrow">可信诊断覆盖漏斗</p><h2>{{ summary.coverage.coverage_complete ? '覆盖完成' : '部分完成' }}</h2></div><span class="badge" :data-tone="summary.coverage.coverage_complete ? 'success' : 'warning'">Run {{ summary.run_id || '-' }}</span></div>
        <div class="coverage-grid">
          <div><span>全部节点</span><strong>{{ summary.coverage.total_nodes }}</strong></div>
          <div><span>规则扫描</span><strong>{{ summary.coverage.rule_scanned_nodes }}</strong></div>
          <div><span>AI 候选</span><strong>{{ summary.coverage.candidate_count }}</strong></div>
          <div><span>深诊断完成</span><strong>{{ summary.coverage.deep_diagnosed_count }}</strong></div>
          <div><span>跳过/失败</span><strong>{{ summary.coverage.skipped_count + summary.coverage.failed_count }}</strong></div>
          <div><span>Token</span><strong>{{ summary.coverage.tokens_used }}</strong></div>
        </div>
        <p v-if="summary.coverage.stop_reason" class="muted">停止原因：{{ summary.coverage.stop_reason }}</p>
      </section>

      <section v-if="summary" class="diagnosis-layout">
        <div class="card issue-panel">
          <div class="card-head"><div><h2>问题列表</h2><p class="muted">显示 {{ filteredIssues.length }} / {{ issues.length }} 项真实诊断记录</p></div></div>
          <div class="filter-bar">
            <label class="filter-control"><span>问题分类</span><select v-model="categoryFilter"><option value="all">全部分类</option><option value="structure">结构问题</option><option value="content">内容问题</option></select></label>
            <label class="filter-control"><span>问题类型</span><select v-model="typeFilter"><option value="all">全部类型</option><option v-for="type in availableIssueTypes" :key="type.code" :value="type.code">{{ type.label }}</option></select></label>
            <label class="filter-control"><span>风险等级</span><select v-model="riskFilter"><option value="all">全部风险</option><option value="high">高风险</option><option value="medium">中风险</option><option value="low">低风险</option></select></label>
            <label class="filter-control"><span>问题来源</span><select v-model="sourceFilter"><option value="all">全部来源</option><option value="structure_rule">结构规则</option><option value="content_rule">内容规则</option><option value="model_analysis">模型分析</option></select></label>
            <button v-if="hasActiveFilters" class="button secondary clear-filter" @click="clearFilters">清除筛选</button>
          </div>
          <div class="table-wrap">
            <table class="data-table selectable">
              <thead><tr><th>分类</th><th>问题类型</th><th>节点名称</th><th>完整路径</th><th>风险</th><th>置信度</th><th>来源</th><th>操作</th></tr></thead>
              <tbody>
                <tr v-for="issue in filteredIssues" :key="issue.id" :data-selected="selected?.id === issue.id" @click="selectIssue(issue.id)">
                  <td><span class="category-badge" :data-category="issue.issue_category">{{ categoryLabel(issue) }}</span></td>
                  <td>{{ issue.issue_type_label }}</td><td>{{ issue.node_name || '-' }}</td>
                  <td class="path-cell">{{ issue.path || '-' }}</td>
                  <td><span class="risk" :data-tone="issue.risk_level">{{ riskLabel(issue.risk_level) }}</span></td>
                  <td>{{ Math.round(issue.confidence * 100) }}%</td><td>{{ sourceLabel(issue.source) }}</td>
                  <td><button class="link-btn" @click.stop="selectIssue(issue.id)">查看详情</button></td>
                </tr>
                <tr v-if="!loading && !filteredIssues.length"><td colspan="8" class="muted">当前筛选条件下没有问题。</td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <aside class="card detail-panel">
          <template v-if="selected">
            <div class="eyebrow">问题详情 #{{ selected.id }}</div><h2>{{ selected.node_name || selected.issue_type_label }}</h2>
            <dl class="detail-list">
              <div><dt>节点 ID</dt><dd>{{ selected.node_id || '-' }}</dd></div><div><dt>完整路径</dt><dd>{{ selected.path || '-' }}</dd></div>
              <div><dt>父节点</dt><dd>{{ nodeName(selected.parent) }}</dd></div><div><dt>子节点</dt><dd>{{ nodeNames(selected.children) }}</dd></div>
              <div><dt>兄弟节点</dt><dd>{{ nodeNames(selected.siblings) }}</dd></div>
            </dl>
            <div class="explanation"><h3>问题原因</h3><p>{{ selected.reason }}</p><h3>检测依据</h3><p>{{ selected.evidence }}</p><h3>模型分析</h3><p>{{ modelAnalysis(selected) }}</p></div>
            <div class="suggestion-box"><h3>建议动作</h3>
              <template v-if="selected.suggestions?.length"><div v-for="item in selected.suggestions" :key="String(item.id)"><strong>{{ actionLabel(item.action_type) }}</strong><p>{{ item.suggestion || item.reason }}</p><p v-if="item.new_name || item.new_parent_id" class="muted">建议值：{{ item.new_name || `父节点 ${item.new_parent_id}` }}</p></div></template>
              <p v-else class="muted">暂无可执行建议，可重新运行建议生成。</p>
            </div>
          </template>
          <div v-else class="empty-state"><h2>选择一个问题</h2><p class="muted">点击左侧问题查看原因、上下文和修改建议。</p></div>
        </aside>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getDiagnosisIssue, getDiagnosisSummary, listDiagnosisIssues } from '../api/diagnosis'
import type { DiagnosisIssue, DiagnosisSummary } from '../api/diagnosis'
import { listFiles } from '../api/files'
import type { FileRecord } from '../api/files'
import { applyVersionFixes, getVersion, listVersions } from '../api/versions'
import type { VersionRecord } from '../api/versions'
import { ApiError, apiUrl } from '../api/client'
import { useWorkspace } from '../state/workspace'

const props = defineProps<{ versionId?: string }>()
const route = useRoute(), router = useRouter()
const { patch } = useWorkspace()
const activeVersionId = computed(() => Number(route.params.versionId || props.versionId || 0))
const loading = ref(false), error = ref(''), statusMessage = ref('')
const applying = ref(false)
const summary = ref<DiagnosisSummary | null>(null), issues = ref<DiagnosisIssue[]>([]), selected = ref<DiagnosisIssue | null>(null)
const files = ref<FileRecord[]>([]), selectableVersions = ref<VersionRecord[]>([])
const selectedFileId = ref(0), selectedVersionId = ref(0)
const categoryFilter = ref<'all' | 'structure' | 'content'>('all'), typeFilter = ref('all'), riskFilter = ref('all'), sourceFilter = ref('all')
const sourceLabels: Record<string, string> = { structure_rule: '结构规则', content_rule: '内容规则', model_analysis: '模型分析', human_triage: '历史复核记录' }
const actionLabels: Record<string, string> = { add_node: '新增节点', move_node: '移动节点', rename_node: '重命名节点', merge_node: '合并节点', clean_synonym: '清理同义词', split_subtree: '拆分子树', deprecate_node: '停用节点', delete_leaf_node: '删除叶子节点', mark_as_valid: '标记为有效' }
const riskLabel = (value: string) => ({ high: '高', medium: '中', low: '低' }[value] || value)
const sourceLabel = (value: string) => sourceLabels[value] || value?.replaceAll('_', ' ') || '-'
const actionLabel = (value: unknown) => actionLabels[String(value)] || String(value || '-')
const categoryLabel = (issue: DiagnosisIssue) => issue.issue_category === 'structure' ? '结构问题' : '内容问题'
const nodeName = (node?: Record<string, unknown> | null) => String(node?.category_name || '-')
const nodeNames = (nodes?: Array<Record<string, unknown>>) => nodes?.slice(0, 8).map(nodeName).join('、') || '-'
const modelAnalysis = (issue: DiagnosisIssue) => String(issue.suggestions?.[0]?.reason || (issue.source?.includes('model') ? issue.description : 'AI 修改方案尚未生成；该问题仍计入未解决问题，不会被自动忽略。'))
const availableIssueTypes = computed(() => {
  const result = new Map<string, string>()
  issues.value.filter(issue => categoryFilter.value === 'all' || issue.issue_category === categoryFilter.value).forEach(issue => result.set(issue.issue_type_code, issue.issue_type_label))
  return [...result].map(([code, label]) => ({ code, label })).sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
})
const filteredIssues = computed(() => issues.value.filter(issue => (categoryFilter.value === 'all' || issue.issue_category === categoryFilter.value) && (typeFilter.value === 'all' || issue.issue_type_code === typeFilter.value) && (riskFilter.value === 'all' || issue.risk_level === riskFilter.value) && (sourceFilter.value === 'all' || issue.source === sourceFilter.value)))
const hasActiveFilters = computed(() => categoryFilter.value !== 'all' || typeFilter.value !== 'all' || riskFilter.value !== 'all' || sourceFilter.value !== 'all')
function clearFilters() { categoryFilter.value = 'all'; typeFilter.value = 'all'; riskFilter.value = 'all'; sourceFilter.value = 'all' }

async function selectIssue(id: number) { try { selected.value = await getDiagnosisIssue(id) } catch (e) { error.value = e instanceof Error ? e.message : '详情加载失败' } }
async function applyFixes() {
  if (!summary.value || applying.value) return
  applying.value = true
  error.value = ''
  statusMessage.value = '正在执行修改并生成新版本…'
  try {
    const result = await applyVersionFixes(summary.value.version_id)
    const anchor = document.createElement('a')
    anchor.href = apiUrl(result.download_url)
    anchor.download = result.file_name
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    await router.push(`/diagnosis/${result.new_version_id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '执行修改失败'
  } finally {
    applying.value = false
  }
}

async function loadSelectableVersions() {
  selectableVersions.value = selectedFileId.value ? await listVersions(selectedFileId.value) : []
  selectedVersionId.value = 0
}
async function openSelectedVersion() {
  if (selectedVersionId.value) await router.push(`/diagnosis/${selectedVersionId.value}`)
}
async function loadAll() {
  loading.value = true; error.value = ''; statusMessage.value = ''; summary.value = null; issues.value = []; selected.value = null
  try {
    if (!files.value.length) files.value = await listFiles()
    if (!activeVersionId.value) return
    const version = await getVersion(activeVersionId.value)
    selectedFileId.value = version.file_id
    selectableVersions.value = await listVersions(version.file_id)
    selectedVersionId.value = version.id
    const runId = String(route.query.run_id || '') || undefined
    ;[summary.value, issues.value] = await Promise.all([getDiagnosisSummary(version.id, runId), listDiagnosisIssues(version.id, runId)])
    patch({ fileId: version.file_id, currentVersionId: version.id, versionNo: version.version_no,
      taskId: summary.value.task_id || null, diagnosisRunId: summary.value.run_id || null, reviewBatchId: null })
    if (issues.value.length) await selectIssue(issues.value[0].id)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) statusMessage.value = '该版本不存在'
    else if (e instanceof ApiError && e.status === 409) statusMessage.value = '诊断尚未完成'
    else error.value = e instanceof Error ? e.message : '诊断结果接口请求失败'
  } finally { loading.value = false }
}
onMounted(loadAll)
watch(() => route.params.versionId, loadAll)
watch(categoryFilter, () => { if (typeFilter.value !== 'all' && !availableIssueTypes.value.includes(typeFilter.value)) typeFilter.value = 'all' })
</script>

<style scoped>
.report-hero { display:flex; justify-content:space-between; align-items:end; padding:8px 4px; } .report-hero h2 { font-size:30px; margin:5px 0; }
.metric-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:14px; }.metric { padding:20px; border:1px solid var(--line); border-radius:18px; background:var(--surface-solid); }.metric span { display:block; color:var(--muted); font-size:13px; }.metric strong { display:block; margin-top:8px; font-size:30px; }.danger-metric strong { color:var(--danger); }.score { background:linear-gradient(135deg,#0969da,#5b5fef); color:white; }.score span { color:rgba(255,255,255,.75); }
.diagnosis-layout { display:grid; grid-template-columns:minmax(0,1.8fr) minmax(320px,.8fr); gap:16px; align-items:start; }.issue-panel { min-width:0; }.detail-panel { position:sticky; top:24px; }.path-cell { max-width:300px; color:var(--muted); }.link-btn { border:0; background:none; color:var(--primary); cursor:pointer; }.detail-list { display:grid; gap:0; margin:18px 0; }.detail-list div { padding:10px 0; border-bottom:1px solid var(--line); }.detail-list dt { color:var(--muted); font-size:12px; }.detail-list dd { margin:5px 0 0; overflow-wrap:anywhere; }.explanation h3,.suggestion-box h3 { margin:18px 0 6px; font-size:14px; }.explanation p,.suggestion-box p { line-height:1.6; margin:0; }.suggestion-box { margin-top:18px; padding:16px; border-radius:14px; background:rgba(10,132,255,.07); }
.filter-bar { display:flex; flex-wrap:wrap; gap:12px; align-items:end; margin:-2px 0 16px; padding:14px; border-radius:16px; background:rgba(17,24,39,.035); }.filter-control { display:grid; gap:6px; min-width:150px; }.filter-control span { color:var(--muted); font-size:12px; }.filter-control select { padding:10px 34px 10px 12px; border:1px solid var(--line); border-radius:12px; background:var(--surface-solid); color:var(--text); }.clear-filter { padding:10px 14px; }.category-badge { display:inline-flex; padding:4px 8px; border-radius:999px; white-space:nowrap; font-size:12px; }.category-badge[data-category='structure'] { color:#7c3aed; background:rgba(124,58,237,.1); }.category-badge[data-category='content'] { color:#0369a1; background:rgba(3,105,161,.1); }
.run-config-bar { display:flex; align-items:center; gap:28px; }.run-config-bar div { display:grid; gap:4px; margin-right:auto; }.run-config-bar div+div { margin-right:auto; }.run-config-bar span { color:var(--muted); font-size:12px; }
.partial-warning { display:flex; align-items:center; justify-content:space-between; gap:18px; border-color:rgba(217,119,6,.25); background:rgba(251,191,36,.1); }.partial-warning strong { color:#92400e; }.partial-warning p { margin:5px 0 0; color:#78350f; line-height:1.5; }
.coverage-grid { display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.coverage-grid div{padding:12px;border-radius:12px;background:rgba(10,132,255,.06)}.coverage-grid span{display:block;color:var(--muted);font-size:12px}.coverage-grid strong{display:block;margin-top:6px;font-size:22px}
@media(max-width:1100px){.metric-grid{grid-template-columns:repeat(2,1fr)}.diagnosis-layout{grid-template-columns:1fr}.detail-panel{position:static}} @media(max-width:620px){.metric-grid{grid-template-columns:1fr}}
</style>
