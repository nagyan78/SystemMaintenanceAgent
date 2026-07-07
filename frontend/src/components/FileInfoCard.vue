<template>
  <section class="card compact">
    <p class="eyebrow">文件信息</p>
    <h2>{{ fileName }}</h2>
    <div class="meta-grid">
      <div>
        <span>行数</span>
        <strong>{{ rowCount }}</strong>
      </div>
      <div>
        <span>列数</span>
        <strong>{{ columnCount }}</strong>
      </div>
    </div>
    <div class="chip-row">
      <span v-for="column in columns" :key="column" class="chip">{{ column }}</span>
    </div>
    <p class="lead">字段列表用于演示上传结果与 schema 识别情况。</p>
  </section>
</template>

<script setup lang="ts">
defineProps<{ fileName: string; rowCount: number; columnCount: number; columns: string[] }>()
</script>
