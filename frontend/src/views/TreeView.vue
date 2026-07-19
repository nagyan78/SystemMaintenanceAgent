<template>
  <AppShell>
    <div class="page-stack tree-page">
      <section class="card tree-toolbar">
        <div>
          <p class="eyebrow">Version {{ versionId }} · 分类树预览</p>
          <h2>浏览自动维护结果</h2>
          <p class="lead">逐层展开节点，或搜索类目名称快速定位修改后的分类路径。</p>
        </div>
        <label class="search-field">
          <span class="visually-hidden">搜索分类节点</span>
          <input v-model.trim="query" type="search" placeholder="搜索类目名称" @input="scheduleSearch" />
        </label>
      </section>

      <section class="tree-summary">
        <div><span>根节点</span><strong>{{ roots.length }}</strong></div>
        <div><span>已加载节点</span><strong>{{ loadedCount }}</strong></div>
        <div><span>当前视图</span><strong>{{ query ? '搜索结果' : '层级树' }}</strong></div>
      </section>

      <p v-if="error" class="card error" role="alert">{{ error }}</p>
      <section v-else class="card tree-browser">
        <div v-if="loading" class="loading-card">正在读取分类树…</div>
        <template v-else-if="rows.length">
          <div class="tree-list-head"><span>分类节点</span><span>层级</span><span>同义词</span><span>类型</span></div>
          <div v-for="row in rows" :key="`${row.node.category_id}-${row.depth}`" class="tree-row">
            <div class="tree-node" :style="{ paddingInlineStart: `${row.depth * 22}px` }">
              <button v-if="canExpand(row.node) && !query" class="tree-toggle" type="button" :aria-expanded="expanded.has(row.node.category_id)" @click="toggle(row.node)">
                <svg viewBox="0 0 20 20" :class="{ open: expanded.has(row.node.category_id) }" aria-hidden="true"><path d="m7 5 5 5-5 5" /></svg>
              </button>
              <span v-else class="tree-leaf-dot"></span>
              <div><strong>{{ row.node.category_name }}</strong><small>{{ row.node.path_names || '根分类' }}</small></div>
              <span v-if="loadingNodes.has(row.node.category_id)" class="node-spinner" aria-label="正在加载子节点"></span>
            </div>
            <span><span class="badge">L{{ row.node.level || row.depth + 1 }}</span></span>
            <span class="synonyms">{{ row.node.syn_list || '—' }}</span>
            <span><span class="risk" :data-tone="canExpand(row.node) ? 'medium' : 'low'">{{ canExpand(row.node) ? '目录节点' : '叶子节点' }}</span></span>
          </div>
        </template>
        <div v-else class="empty-state"><h2>没有匹配节点</h2><p class="lead">尝试更换搜索关键词，或清空搜索返回分类树。</p></div>
      </section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getTreeLevel, searchTaxonomyNodes } from '../api/taxonomy'
import type { TaxonomyNode } from '../api/taxonomy'

type TreeRow = { node: TaxonomyNode; depth: number }
const route = useRoute()
const props = defineProps<{ versionId?: string }>()
const versionId = computed(() => Number(route.params.versionId || props.versionId))
const roots = ref<TaxonomyNode[]>([])
const children = ref<Record<number, TaxonomyNode[]>>({})
const searchResults = ref<TaxonomyNode[]>([])
const expanded = ref(new Set<number>())
const loadingNodes = ref(new Set<number>())
const query = ref(''), loading = ref(true), error = ref('')
let searchTimer: number | null = null

const canExpand = (node: TaxonomyNode) => Number(node.child_count || 0) > 0 || node.is_leaf === 0
const loadedCount = computed(() => roots.value.length + Object.values(children.value).reduce((sum, items) => sum + items.length, 0))
const rows = computed<TreeRow[]>(() => {
  if (query.value) return searchResults.value.map(node => ({ node, depth: Math.max(0, Number(node.level || 1) - 1) }))
  const result: TreeRow[] = []
  const visit = (nodes: TaxonomyNode[], depth: number) => {
    for (const node of nodes) {
      result.push({ node, depth })
      if (expanded.value.has(node.category_id)) visit(children.value[node.category_id] || [], depth + 1)
    }
  }
  visit(roots.value, 0)
  return result
})

async function toggle(node: TaxonomyNode) {
  const next = new Set(expanded.value)
  if (next.has(node.category_id)) { next.delete(node.category_id); expanded.value = next; return }
  if (!children.value[node.category_id]) {
    const busy = new Set(loadingNodes.value); busy.add(node.category_id); loadingNodes.value = busy
    try {
      const items = await getTreeLevel(versionId.value, node.category_id)
      children.value = { ...children.value, [node.category_id]: items.map(item => ({ ...item, parent_id: node.category_id })) }
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '子节点加载失败' }
    finally { const done = new Set(loadingNodes.value); done.delete(node.category_id); loadingNodes.value = done }
  }
  next.add(node.category_id); expanded.value = next
}

function scheduleSearch() {
  if (searchTimer) window.clearTimeout(searchTimer)
  if (!query.value) { searchResults.value = []; return }
  searchTimer = window.setTimeout(async () => {
    try { searchResults.value = await searchTaxonomyNodes(versionId.value, query.value) }
    catch (cause) { error.value = cause instanceof Error ? cause.message : '分类搜索失败' }
  }, 220)
}

onMounted(async () => {
  try { roots.value = await getTreeLevel(versionId.value) }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '分类树加载失败' }
  finally { loading.value = false }
})
onBeforeUnmount(() => { if (searchTimer) window.clearTimeout(searchTimer) })
</script>

<style scoped>
.tree-page{gap:16px}.tree-toolbar h2{margin:4px 0 5px}.tree-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.tree-summary div{padding:14px 16px;border:1px solid var(--line);border-radius:11px;background:#fff}.tree-summary span,.tree-summary strong{display:block}.tree-summary span{color:var(--muted);font-size:11px}.tree-summary strong{margin-top:3px;font-size:18px}.tree-browser{padding:0;overflow:hidden}.tree-list-head,.tree-row{display:grid;grid-template-columns:minmax(320px,1fr) 80px minmax(150px,.45fr) 100px;align-items:center;gap:12px}.tree-list-head{padding:11px 18px;border-bottom:1px solid var(--line);background:var(--surface-subtle);color:var(--muted);font-size:10px;font-weight:750;letter-spacing:.06em;text-transform:uppercase}.tree-row{min-height:62px;padding:8px 18px;border-bottom:1px solid var(--line)}.tree-row:last-child{border-bottom:0}.tree-row:hover{background:#fafbfd}.tree-node{display:flex;align-items:center;gap:9px;min-width:0}.tree-node strong,.tree-node small{display:block}.tree-node strong{font-size:13px}.tree-node small{overflow:hidden;margin-top:2px;color:var(--muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.tree-toggle{display:grid;place-items:center;width:24px;height:24px;flex:none;padding:0;border:0;border-radius:6px;background:transparent;color:var(--muted);cursor:pointer}.tree-toggle:hover{background:#edf3ff;color:var(--primary)}.tree-toggle svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;transition:transform .18s}.tree-toggle svg.open{transform:rotate(90deg)}.tree-leaf-dot{width:5px;height:5px;margin:0 10px;flex:none;border-radius:50%;background:#bec7d4}.synonyms{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.node-spinner{width:12px;height:12px;margin-left:auto;border:2px solid #dce6f8;border-top-color:var(--primary);border-radius:50%;animation:spin .7s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.tree-summary{grid-template-columns:1fr}.tree-list-head{display:none}.tree-row{grid-template-columns:1fr auto}.tree-row>span:nth-child(3),.tree-row>span:nth-child(4){display:none}}
</style>
