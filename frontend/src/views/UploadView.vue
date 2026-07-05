<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { AlertTriangle, LoaderCircle, UploadCloud } from "@lucide/vue";
import FileInfoCard from "../components/FileInfoCard.vue";
import { ApiError } from "../api/client";
import { uploadExcel } from "../api/files";
import { applyUploadResult, formatUploadTime, refreshFiles, workspace } from "../stores/workspace";

const router = useRouter();
const uploadInput = ref<HTMLInputElement | null>(null);
const selectedFileName = ref("");
const uploading = ref(false);
const errorMessage = ref("");

const latestRecord = computed(() => workspace.files[0] ?? null);
const recentFiles = computed(() => workspace.files.slice(0, 5));

function openPicker() {
  uploadInput.value?.click();
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  selectedFileName.value = file.name;
  errorMessage.value = "";

  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    errorMessage.value = "请上传 .xlsx 文件";
    input.value = "";
    return;
  }

  uploading.value = true;
  try {
    const result = await uploadExcel(file);
    applyUploadResult(result);
    await refreshFiles();
    await router.push("/overview");
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError || error instanceof Error ? error.message : "上传失败";
  } finally {
    uploading.value = false;
    input.value = "";
  }
}
</script>

<template>
  <section class="upload-hero">
    <div class="upload-card panel" :class="{ 'upload-card--active': uploading }">
      <input
        ref="uploadInput"
        type="file"
        accept=".xlsx"
        class="sr-only"
        @change="handleFileChange"
      />
      <div class="upload-card__icon">
        <LoaderCircle v-if="uploading" class="spin" :size="32" />
        <UploadCloud v-else :size="34" />
      </div>
      <div>
        <p class="eyebrow">文件上传</p>
        <h2>{{ selectedFileName || "选择产品标准体系 Excel" }}</h2>
        <p v-if="uploading">上传中</p>
      </div>
      <button class="primary-button" type="button" :disabled="uploading" @click="openPicker">
        <UploadCloud :size="19" />
        {{ uploading ? "上传中" : "上传 Excel" }}
      </button>
    </div>

    <FileInfoCard :file="workspace.currentFile" :record="latestRecord" :uploading="uploading" />
  </section>

  <p v-if="errorMessage" class="error-banner">
    <AlertTriangle :size="18" />
    {{ errorMessage }}
  </p>

  <section class="panel page-panel">
    <div class="panel__title-row">
      <div>
        <p class="eyebrow">上传记录</p>
        <h2>最近文件</h2>
      </div>
    </div>
    <div v-if="recentFiles.length" class="version-list version-list--wide">
      <article v-for="file in recentFiles" :key="file.id">
        <span></span>
        <div>
          <strong>#{{ file.id }} {{ file.file_name }}</strong>
          <p>{{ formatUploadTime(file.upload_time) }} · {{ file.row_count?.toLocaleString() }} 行 · {{ file.column_count }} 字段</p>
        </div>
      </article>
    </div>
    <div v-else class="compact-empty">暂无上传记录</div>
  </section>
</template>
