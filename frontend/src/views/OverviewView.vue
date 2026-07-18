<template>
  <AppShell>
    <div class="page-stack">
      <section class="card hero-card">
        <div>
          <p class="eyebrow">Version {{ versionId }} · taxonomy snapshot</p>
          <h2>体系概览</h2>
          <p class="lead">用一眼能读完的指标确认体系规模与需要关注的结构信号。</p>
        </div>
        <RouterLink :to="`/tree/${versionId}`" class="button primary">浏览分类树</RouterLink>
      </section>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <section v-if="overview" class="metric-grid" aria-label="体系指标">
        <article v-for="item in metrics" :key="item.label" class="metric-card" :data-tone="item.tone">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.hint }}</small>
        </article>
      </section>
      <section v-else-if="loading" class="card loading-card">正在读取版本快照…</section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getOverview, type TaxonomyOverview } from '../api/taxonomy'

const route = useRoute()
const versionId = computed(() => Number(route.params.versionId))
const overview = ref<TaxonomyOverview | null>(null)
const loading = ref(true)
const error = ref('')
const metrics = computed(() => {
  if (!overview.value) return []
  return [
    { label: '节点总数', value: overview.value.node_count, hint: '当前版本的全部类目', tone: 'neutral' },
    { label: '一级类目', value: overview.value.root_count, hint: '体系入口数量', tone: 'neutral' },
    { label: '最大层级', value: overview.value.max_depth, hint: '路径复杂度', tone: overview.value.max_depth > 7 ? 'warning' : 'success' },
    { label: '最大直接子类', value: overview.value.max_children_count, hint: '最宽节点的子类数量', tone: overview.value.max_children_count > 80 ? 'warning' : 'success' },
    { label: '缺失父节点', value: overview.value.missing_parent_count, hint: '需要结构修复', tone: overview.value.missing_parent_count ? 'danger' : 'success' },
    { label: '重复名称', value: overview.value.duplicate_name_count, hint: '需结合路径确认', tone: overview.value.duplicate_name_count ? 'warning' : 'success' },
  ]
})

onMounted(async () => {
  try {
    overview.value = await getOverview(versionId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '体系概览加载失败'
  } finally {
    loading.value = false
  }
})
</script>
