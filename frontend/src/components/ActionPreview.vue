<template>
  <section class="card" data-testid="action-preview">
    <div class="card-head">
      <div><p class="eyebrow">执行前模拟</p><h2>动作影响预览</h2></div>
      <span class="badge" :data-tone="preview.valid ? 'success' : 'danger'">{{ preview.valid ? '校验通过' : '存在冲突' }}</span>
    </div>
    <p v-if="preview.errors.length" class="error">{{ preview.errors.map(item => item.reason || '未知错误').join('；') }}</p>
    <div class="review-stats">
      <span v-for="item in groups" :key="item.key" class="badge">{{ item.label }} {{ item.count }}</span>
    </div>
    <div v-for="item in specialActions" :key="item.title" class="preview-action">
      <strong>{{ item.title }}</strong><pre>{{ JSON.stringify(item.value, null, 2) }}</pre>
    </div>
    <small>审核指纹：{{ preview.review_hash.slice(0, 16) }}</small>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ActionPreviewResult } from '../api/reviews'
const props = defineProps<{ preview: ActionPreviewResult }>()
const labels: Record<string, string> = { added: '新增', deleted: '删除', moved: '移动', renamed: '重命名', synonym_changed: '同义词', split: '拆分', merged: '合并', deprecated: '弃用' }
const groups = computed(() => Object.entries(labels).map(([key, label]) => ({ key, label, count: props.preview.diff[key]?.length || 0 })))
const specialActions = computed(() => ['split', 'merged', 'deprecated'].flatMap(key => (props.preview.diff[key] || []).map(value => ({ title: labels[key], value }))))
</script>

<style scoped>
.preview-action { margin-top: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; }
.preview-action pre { margin: 8px 0 0; white-space: pre-wrap; font-size: 12px; }
</style>
