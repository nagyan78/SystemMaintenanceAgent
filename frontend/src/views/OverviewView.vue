<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  AlertTriangle,
  Folder,
  GitBranch,
  Layers3,
  Network,
  Search,
  ShieldCheck,
  Sparkles
} from "@lucide/vue";
import MetricCard from "../components/MetricCard.vue";
import { formatUploadTime, refreshFiles, workspace } from "../stores/workspace";

const errorMessage = ref("");
const latestRecord = computed(() => workspace.files[0] ?? null);
const activeRowCount = computed(() => workspace.currentFile?.row_count ?? latestRecord.value?.row_count ?? null);
const activeColumnCount = computed(
  () => workspace.currentFile?.column_count ?? latestRecord.value?.column_count ?? null
);
const totalNodes = computed(() => activeRowCount.value?.toLocaleString() ?? "—");
const recentFiles = computed(() => workspace.files.slice(0, 4));

onMounted(async () => {
  try {
    await refreshFiles();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "文件列表加载失败";
  }
});
</script>

<template>
  <p v-if="errorMessage" class="error-banner">
    <AlertTriangle :size="18" />
    {{ errorMessage }}
  </p>

  <section class="metrics-grid">
    <MetricCard label="总节点数" :value="totalNodes" :icon="Network" />
    <MetricCard label="最大层级" value="待解析" :icon="Layers3" tone="muted" />
    <MetricCard label="最大子节点数" value="待解析" :icon="GitBranch" tone="muted" />
    <MetricCard label="缺失父节点" value="待诊断" :icon="AlertTriangle" tone="red" />
    <MetricCard label="体系质量分" value="待诊断" :icon="ShieldCheck" tone="green" />
  </section>

  <section class="content-grid">
    <section class="panel tree-panel">
      <div class="panel__title-row">
        <div>
          <p class="eyebrow">体系树</p>
          <h2>产品体系树</h2>
        </div>
        <span class="mini-pill">{{ activeRowCount ? "已接收文件" : "等待上传" }}</span>
      </div>
      <div class="toolbar-row">
        <label class="search-box">
          <Search :size="18" />
          <input placeholder="搜索节点名称或 ID" disabled />
        </label>
        <button class="ghost-button" type="button" disabled>全部节点</button>
      </div>
      <div class="empty-tree">
        <Folder :size="34" />
        <h3>{{ activeRowCount ? "等待分类树接口" : "等待上传" }}</h3>
      </div>
      <div class="tree-footer">
        <span>共 {{ activeRowCount?.toLocaleString() ?? "—" }} 个节点</span>
        <span>{{ activeColumnCount ?? "—" }} 个字段</span>
      </div>
    </section>

    <section class="panel issue-panel">
      <div class="panel__title-row">
        <div>
          <p class="eyebrow">诊断结果</p>
          <h2>问题检测结果</h2>
        </div>
        <span class="mini-pill">等待诊断接口</span>
      </div>
      <div class="tabbar">
        <button class="tabbar__item tabbar__item--active" type="button">结构问题</button>
        <button class="tabbar__item" type="button">内容问题</button>
      </div>
      <div class="empty-table">
        <Sparkles :size="32" />
        <h3>暂无诊断结果</h3>
      </div>
    </section>

    <aside class="right-rail">
      <section class="panel score-panel">
        <div class="panel__title-row">
          <div>
            <p class="eyebrow">质量评价</p>
            <h2>体系质量分</h2>
          </div>
        </div>
        <div class="score-ring">
          <span>{{ activeRowCount ? "待评估" : "—" }}</span>
        </div>
      </section>

      <section class="panel version-panel">
        <div class="panel__title-row">
          <div>
            <p class="eyebrow">版本管理</p>
            <h2>上传记录</h2>
          </div>
        </div>
        <div v-if="recentFiles.length" class="version-list">
          <article v-for="file in recentFiles" :key="file.id">
            <span></span>
            <div>
              <strong>#{{ file.id }} {{ file.file_name }}</strong>
              <p>{{ formatUploadTime(file.upload_time) }} · {{ file.row_count?.toLocaleString() }} 行</p>
            </div>
          </article>
        </div>
        <div v-else class="compact-empty">暂无上传记录</div>
      </section>
    </aside>
  </section>
</template>
