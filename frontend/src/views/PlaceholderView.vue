<template>
  <AppShell>
    <EmptyState eyebrow="P1 占位" title="待补充" description="该页面作为 P1 入口保留，当前聚焦 P0 端到端闭环。" action-label="返回上传" action-to="/upload" />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '../components/AppShell.vue'
import EmptyState from '../components/EmptyState.vue'
</script>
