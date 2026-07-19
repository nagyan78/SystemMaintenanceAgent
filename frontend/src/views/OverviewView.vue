<template>
  <AppShell>
    <div class="page-stack overview-page">
      <section class="card overview-hero">
        <div><p class="eyebrow">版本 {{ version?.version_no || `#${versionId}` }}</p><h2>体系概览</h2><p class="lead">查看当前版本结构、质量以及指定诊断轮次的维护结果。</p></div>
        <div class="action-row"><RouterLink class="button primary" :to="`/tree/${versionId}`">浏览分类结果</RouterLink><RouterLink class="button secondary" :to="`/diagnosis/${versionId}${selectedRunId ? `?run_id=${selectedRunId}` : ''}`">查看诊断问题</RouterLink></div>
      </section>

      <section v-if="runs.length" class="card run-picker">
        <label><span>诊断轮次</span><select v-model="selectedRunId" @change="loadSummary"><option v-for="run in runs" :key="run.id" :value="run.id">{{ run.id }} · {{ run.status }}</option></select></label>
        <span class="badge">版本 + 诊断轮次</span>
      </section>
      <p v-if="loading" class="card lead">正在读取本轮体系结果…</p>
      <p v-if="error" class="card error">{{ error }}</p>

      <template v-if="overview && quality">
        <section class="overview-grid">
          <article class="card score-card"><span>质量评分</span><strong>{{ formatScore(quality.quality_after) }}</strong><small>{{ summary?.quality_verdict || (quality.after_issue_count ? '需要整改' : '质量通过') }}</small></article>
          <article class="card"><span>节点总数</span><strong>{{ overview.node_count }}</strong><small>{{ overview.root_count }} 个根节点</small></article>
          <article class="card"><span>最大层级</span><strong>{{ overview.max_depth }}</strong><small>最大直接子节点 {{ overview.max_children_count }}</small></article>
          <article class="card"><span>未解决问题</span><strong>{{ quality.after_issue_count }}</strong><small>影响比例 {{ formatRate(summary?.weighted_error_rate) }}</small></article>
        </section>

        <section class="card">
          <div class="card-head"><div><p class="eyebrow">本轮维护结果</p><h2>{{ summary?.task_status || quality.verification_status || '已生成' }}</h2></div><span class="badge" :data-tone="quality.verification_status === 'passed' ? 'success' : 'warning'">{{ quality.verification_status || '-' }}</span></div>
          <div class="result-grid"><div><span>叶子节点</span><strong>{{ overview.leaf_count }}</strong></div><div><span>非叶子节点</span><strong>{{ overview.non_leaf_count }}</strong></div><div><span>结构问题</span><strong>{{ summary?.structure_issue_count ?? '-' }}</strong></div><div><span>内容问题</span><strong>{{ summary?.content_issue_count ?? '-' }}</strong></div><div><span>已解决</span><strong>{{ quality.resolved_issues.length }}</strong></div><div><span>新增问题</span><strong>{{ quality.new_issues.length }}</strong></div></div>
        </section>

        <section v-if="summary?.coverage" class="card">
          <div class="card-head"><div><p class="eyebrow">诊断覆盖率</p><h2>{{ summary.coverage.coverage_complete ? '覆盖完成' : '部分完成' }}</h2></div><span class="badge">Run {{ summary.run_id || '-' }}</span></div>
          <div class="result-grid"><div><span>规则扫描</span><strong>{{ summary.coverage.rule_scanned_nodes }}/{{ summary.coverage.total_nodes }}</strong></div><div><span>AI 候选</span><strong>{{ summary.coverage.candidate_count }}</strong></div><div><span>AI 已处理</span><strong>{{ summary.coverage.deep_diagnosed_count }}</strong></div><div><span>跳过</span><strong>{{ summary.coverage.skipped_count }}</strong></div><div><span>失败</span><strong>{{ summary.coverage.failed_count }}</strong></div><div><span>Token</span><strong>{{ summary.coverage.tokens_used }}</strong></div></div>
        </section>
      </template>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getTaxonomyOverview } from '../api/taxonomy'
import type { TaxonomyOverview } from '../api/taxonomy'
import { getDiagnosisSummary, listDiagnosisRuns } from '../api/diagnosis'
import type { DiagnosisRun, DiagnosisSummary } from '../api/diagnosis'
import { getVersion, getVersionQuality } from '../api/versions'
import type { VersionQuality, VersionRecord } from '../api/versions'
import { useWorkspace } from '../state/workspace'

const props = defineProps<{ versionId?: string }>()
const route = useRoute(), { patch } = useWorkspace()
const versionId = computed(() => Number(route.params.versionId || props.versionId || 0))
const overview = ref<TaxonomyOverview | null>(null), quality = ref<VersionQuality | null>(null), summary = ref<DiagnosisSummary | null>(null), version = ref<VersionRecord | null>(null)
const runs = ref<DiagnosisRun[]>([]), selectedRunId = ref(String(route.query.run_id || ''))
const loading = ref(false), error = ref('')
const formatScore = (value?: number | null) => value == null ? '-' : Number(value).toFixed(2)
const formatRate = (value?: number) => value == null ? '-' : `${(value * 100).toFixed(2)}%`

async function loadSummary() { summary.value = await getDiagnosisSummary(versionId.value, selectedRunId.value || undefined) }
async function load() {
  if (!versionId.value) return
  loading.value = true; error.value = ''
  try {
    ;[version.value, overview.value, quality.value, runs.value] = await Promise.all([getVersion(versionId.value), getTaxonomyOverview(versionId.value), getVersionQuality(versionId.value), listDiagnosisRuns(versionId.value)])
    if (!selectedRunId.value && runs.value.length) selectedRunId.value = runs.value[runs.value.length - 1].id
    await loadSummary()
    patch({ fileId: version.value.file_id, currentVersionId: versionId.value, versionNo: version.value.version_no, taskId: summary.value?.task_id || null, diagnosisRunId: selectedRunId.value || null })
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '体系概览加载失败' }
  finally { loading.value = false }
}
onMounted(load)
watch(() => route.params.versionId, load)
</script>

<style scoped>
.overview-hero{display:flex;align-items:end;justify-content:space-between;gap:24px}.overview-hero h2{margin:5px 0}.run-picker{display:flex;align-items:end;justify-content:space-between}.run-picker label{display:grid;gap:7px;min-width:min(520px,100%)}.run-picker span{color:var(--muted);font-size:12px}.overview-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.overview-grid article span,.overview-grid article strong,.overview-grid article small{display:block}.overview-grid article span,.overview-grid article small{color:var(--muted)}.overview-grid article strong{margin:8px 0;font-size:30px}.score-card{background:linear-gradient(135deg,#0969da,#5b5fef);color:#fff}.score-card span,.score-card small{color:rgba(255,255,255,.78)!important}.result-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.result-grid div{padding:13px;border-radius:12px;background:var(--surface-subtle)}.result-grid span,.result-grid strong{display:block}.result-grid span{color:var(--muted);font-size:12px}.result-grid strong{margin-top:6px;font-size:20px}@media(max-width:900px){.overview-grid{grid-template-columns:repeat(2,1fr)}.result-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:620px){.overview-hero{align-items:start;flex-direction:column}.overview-grid,.result-grid{grid-template-columns:1fr}}
</style>
