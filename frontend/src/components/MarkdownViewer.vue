<template>
  <section class="card markdown-card">
    <div class="card-head">
      <div>
        <p class="eyebrow">报告预览</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="badge">Markdown</span>
    </div>
    <article class="markdown-body" v-html="rendered"></article>
  </section>
</template>

<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const props = defineProps<{ title: string; markdown: string }>()
const md = new MarkdownIt({ linkify: true, breaks: true })
const rendered = computed(() => md.render(props.markdown || '暂无报告内容'))
</script>
