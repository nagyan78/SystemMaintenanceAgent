<template>
  <AppShell>
    <EmptyState eyebrow="P1 占位" title="体系概览" description="后端概览 API 仍在完善中，当前仅保留报告入口与工作流链路。" action-label="返回上传" action-to="/upload" />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '../components/AppShell.vue'
import EmptyState from '../components/EmptyState.vue'
</script>
