<template>
  <AppShell>
    <div class="page-stack">
      <section class="card tree-toolbar">
        <div>
          <p class="eyebrow">Version {{ versionId }} · {{ nodes.length }} nodes</p>
          <h2>分类浏览</h2>
          <p class="lead">按层级浏览当前版本；搜索同时匹配类目名称和完整路径。</p>
        </div>
        <label class="search-field">
          <span class="visually-hidden">搜索分类</span>
          <input v-model.trim="query" type="search" placeholder="搜索类目或路径" @input="applyFilter" />
        </label>
      </section>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <section v-if="nodes.length" class="card table-wrap">
        <table class="data-table tree-table">
          <thead><tr><th>分类路径</th><th>层级</th><th>同义词</th><th>类型</th></tr></thead>
          <tbody>
            <tr v-for="node in visibleNodes" :key="node.id">
              <td>
                <div class="tree-name" :style="{ paddingInlineStart: `${Math.max(0, node.level - 1) * 1.25}rem` }">
                  <span class="tree-branch">{{ node.is_leaf ? '·' : '⌄' }}</span>
                  <div><strong>{{ node.category_name }}</strong><small>{{ node.path_names }}</small></div>
                </div>
              </td>
              <td><span class="badge">L{{ node.level }}</span></td>
              <td class="muted">{{ node.syn_list || '—' }}</td>
              <td><span class="risk" :data-tone="node.is_leaf ? 'low' : 'medium'">{{ node.is_leaf ? '叶子节点' : '目录节点' }}</span></td>
            </tr>
          </tbody>
        </table>
        <p v-if="visibleNodes.length === 0" class="empty-hint">没有匹配的分类节点。</p>
      </section>
      <section v-else-if="loading" class="card loading-card">正在读取分类树…</section>
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getTree, type TaxonomyNode } from '../api/taxonomy'

const route = useRoute()
const versionId = computed(() => Number(route.params.versionId))
const nodes = ref<TaxonomyNode[]>([])
const visibleNodes = ref<TaxonomyNode[]>([])
const query = ref('')
const loading = ref(true)
const error = ref('')

function applyFilter() {
  const normalized = query.value.toLocaleLowerCase()
  visibleNodes.value = !normalized
    ? nodes.value
    : nodes.value.filter(node => `${node.category_name} ${node.path_names}`.toLocaleLowerCase().includes(normalized))
}

onMounted(async () => {
  try {
    nodes.value = (await getTree(versionId.value)).nodes
    applyFilter()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '分类树加载失败'
  } finally {
    loading.value = false
  }
})
</script>
