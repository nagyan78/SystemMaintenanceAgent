<template>
  <AppShell>
    <EmptyState eyebrow="P1 占位" title="诊断问题" description="结构/内容诊断查询接口完善后，这里会展示问题列表与筛选。" action-label="返回上传" action-to="/upload" />
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from '../components/AppShell.vue'
import EmptyState from '../components/EmptyState.vue'
</script>
