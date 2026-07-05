<script setup lang="ts">
import { CheckCircle2, FileSpreadsheet, LoaderCircle } from "@lucide/vue";
import type { FileUploadResponse, UploadedFileRecord } from "../api/files";

defineProps<{
  file: FileUploadResponse | null;
  record: UploadedFileRecord | null;
  uploading: boolean;
}>();
</script>

<template>
  <section class="panel file-info-panel">
    <div class="panel__title-row">
      <div>
        <p class="eyebrow">Excel 导入</p>
        <h2>{{ file?.file_name ?? record?.file_name ?? "等待上传标准产品体系 Excel" }}</h2>
      </div>
      <div class="soft-icon">
        <LoaderCircle v-if="uploading" class="spin" :size="22" />
        <CheckCircle2 v-else-if="file || record" :size="22" />
        <FileSpreadsheet v-else :size="22" />
      </div>
    </div>

    <div v-if="file || record" class="file-info-grid">
      <div>
        <span>文件 ID</span>
        <strong>#{{ file?.file_id ?? record?.id }}</strong>
      </div>
      <div>
        <span>导入任务</span>
        <strong>{{ file?.task_id ?? "—" }}</strong>
      </div>
      <div>
        <span>数据行数</span>
        <strong>{{ (file?.row_count ?? record?.row_count ?? 0).toLocaleString() }}</strong>
      </div>
      <div>
        <span>字段数量</span>
        <strong>{{ file?.column_count ?? record?.column_count ?? "—" }}</strong>
      </div>
    </div>

    <div v-if="file" class="field-list">
      <span v-for="column in file.columns" :key="column">{{ column }}</span>
    </div>

    <p v-else class="muted-line">上传成功后，文件元数据、字段识别结果和任务 ID 会从后端返回。</p>
  </section>
</template>
