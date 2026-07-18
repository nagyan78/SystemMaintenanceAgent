<template>
  <AppShell>
    <div class="page-stack">
      <section class="card hero-card">
        <div>
          <p class="eyebrow">Version {{ versionId }} · read-only diagnosis</p>
          <h2>诊断问题</h2>
          <p class="lead">风险和置信度共同解释智能体为何执行、跳过或仅记录某项维护建议。</p>
        </div>
        <div class="segmented-control" aria-label="风险筛选">
          <button v-for="item in filters" :key="item.value" class="segment" :class="{ active: filter === item.value }" @click="filter = item.value">{{ item.label }}</button>
        </div>
      </section>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <section v-if="filteredIssues.length" class="issue-list">
        <article v-for="issue in filteredIssues" :key="issue.id" class="card issue-card" :data-risk="issue.risk_level">
          <div class="issue-head"><span class="risk" :data-tone="issue.risk_level">{{ riskLabel(issue.risk_level) }}</span><span class="badge">{{ issue.issue_type }}</span><span class="issue-confidence">置信度 {{ Math.round(issue.confidence * 100) }}%</span></div>
          <h3>{{ issue.node_name || '未定位节点' }}</h3>
          <p>{{ issue.description }}</p>
          <p class="muted">依据：{{ issue.reason }}</p>
          <div class="issue-foot"><span>状态：{{ issue.status }}</span><span v-if="issue.detector_version">{{ issue.detector_version }}</span></div>
        </article>
      </section>
      <section v-else-if="!loading" class="card empty-state">
        <p class="eyebrow">结构稳定</p><h2>没有匹配的诊断问题</h2><p class="lead">可以切换筛选条件，或回到工作流启动新的分析。</p>
      </section>
      <section v-else class="card loading-card">正在读取诊断结果…</section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { listIssues, type DiagnosisIssue } from '../api/diagnosis'

const route = useRoute()
const versionId = computed(() => Number(route.params.versionId))
const issues = ref<DiagnosisIssue[]>([])
const filter = ref('all')
const loading = ref(true)
const error = ref('')
const filters = [{ label: '全部', value: 'all' }, { label: '高风险', value: 'high' }, { label: '中风险', value: 'medium' }, { label: '低风险', value: 'low' }]
const filteredIssues = computed(() => filter.value === 'all' ? issues.value : issues.value.filter(issue => issue.risk_level === filter.value))
function riskLabel(value: string) { return ({ low: '低风险', medium: '中风险', high: '高风险' } as Record<string, string>)[value] || value }

onMounted(async () => {
  try {
    issues.value = (await listIssues(versionId.value)).issues
  } catch (err) {
    error.value = err instanceof Error ? err.message : '诊断问题加载失败'
  } finally {
    loading.value = false
  }
})
</script>
