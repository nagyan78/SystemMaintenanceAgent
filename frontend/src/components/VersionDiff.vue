<template>
  <section class="card">
    <div class="card-head">
      <div>
        <p class="eyebrow">版本对比</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="badge">{{ diffLabel }}</span>
    </div>
    <div class="diff-grid">
      <div v-for="group in groups" :key="group.key" class="diff-panel">
        <h3>{{ group.label }}</h3>
        <div v-if="group.items.length" class="diff-list">
          <article v-for="(item, index) in group.items" :key="index" class="diff-item">
            <pre>{{ pretty(item) }}</pre>
          </article>
        </div>
        <p v-else class="empty-hint">暂无变更</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
const props = defineProps<{ title: string; diffLabel: string; groups: Array<{ key: string; label: string; items: Array<Record<string, unknown>> }> }>()

function pretty(value: Record<string, unknown>) {
  return JSON.stringify(value, null, 2)
}
</script>
