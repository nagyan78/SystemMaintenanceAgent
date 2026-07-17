<template>
  <section v-if="versionId" class="card optimization-panel">
    <div class="card-head">
      <div><p class="eyebrow">持续维护</p><h2>继续优化当前版本</h2></div>
      <span class="badge">{{ quality?.lifecycle_status || version?.lifecycle_status || '-' }}</span>
    </div>

    <div class="action-row">
      <button class="button secondary" :disabled="busy" @click="load">刷新复诊问题</button>
      <button class="button primary" :disabled="!selectedIssueIds.length || busy" @click="createBatch(selectedIssueIds)">按复诊问题创建审核批次</button>
      <button class="button secondary" :disabled="busy" @click="createBatch([])">创建人工修改批次</button>
      <button class="button secondary" :disabled="busy" @click="restore">基于本版本创建恢复版本</button>
      <select v-model.number="supersedesVersionId" :disabled="busy"><option :value="0">不指定被替代版本</option><option v-for="item in failedVersions" :key="item.id" :value="item.id">替代 {{ item.version_no }}（失败）</option></select>
      <button class="button secondary" :disabled="!quality?.release_allowed || busy" @click="release">发布版本</button>
      <button class="button secondary" :disabled="busy" @click="loadRecords">查看执行记录</button>
    </div>

    <div v-if="issues.length" class="issue-picker">
      <label v-for="issue in issues" :key="Number(issue.id)" class="issue-option">
        <input v-model="selectedIssueIds" type="checkbox" :value="Number(issue.id)" />
        <span><strong>{{ issue.issue_type_label || issue.issue_type }}</strong> · {{ issue.node_name || `问题 #${issue.id}` }}</span>
        <small>{{ issue.description }}</small>
      </label>
    </div>
    <p v-else-if="loaded" class="muted">当前版本没有可继续处理的复诊问题；仍可从新审核批次中人工添加修改。</p>

    <div v-if="createdBatchId" class="action-row result-row">
      <span class="badge">审核批次 {{ createdBatchId }}</span>
      <RouterLink class="button primary" :to="`/reviews/${createdBatchId}`">进入审核并人工添加修改</RouterLink>
    </div>

    <div v-if="records.length" class="record-list">
      <article v-for="record in records" :key="record.id">
        <strong>{{ record.review_batch_id }}</strong>
        <span>v#{{ record.source_version_id }} → v#{{ record.target_version_id }}</span>
        <span>{{ record.status }}</span>
      </article>
    </div>
    <p v-if="message" class="lead">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import {
  createVersionReviewBatch, getVersion, getVersionQuality, listExecutionRecords, listVersions,
  releaseVersion, restoreVersion,
} from '../api/versions'
import type { ExecutionRecord, VersionQuality, VersionRecord } from '../api/versions'

const props = defineProps<{ versionId: number }>()
const version = ref<VersionRecord | null>(null)
const quality = ref<VersionQuality | null>(null)
const issues = ref<Array<Record<string, unknown>>>([])
const selectedIssueIds = ref<number[]>([])
const createdBatchId = ref('')
const records = ref<ExecutionRecord[]>([])
const failedVersions = ref<VersionRecord[]>([])
const supersedesVersionId = ref(0)
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const message = ref('')

async function load() {
  if (!props.versionId) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const [versionResult, qualityResult] = await Promise.all([getVersion(props.versionId), getVersionQuality(props.versionId)])
    version.value = versionResult
    quality.value = qualityResult
    failedVersions.value = (await listVersions(versionResult.file_id)).filter(item => item.lifecycle_status === 'failed' && item.id !== props.versionId)
    issues.value = [...qualityResult.unresolved_issues, ...qualityResult.new_issues, ...qualityResult.deferred_issues]
      .filter((item, index, all) => all.findIndex(other => Number(other.id) === Number(item.id)) === index)
    selectedIssueIds.value = selectedIssueIds.value.filter(id => issues.value.some(item => Number(item.id) === id))
    loaded.value = true
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '持续优化数据加载失败' }
  finally { busy.value = false }
}

async function createBatch(issueIds: number[]) {
  busy.value = true; error.value = ''
  try {
    const result = await createVersionReviewBatch(props.versionId, issueIds)
    createdBatchId.value = result.review_batch_id
    message.value = `已创建审核批次，生成 ${result.suggestion_count} 条建议。可进入审核页继续人工添加修改。`
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '创建审核批次失败' }
  finally { busy.value = false }
}

async function restore() {
  busy.value = true; error.value = ''
  try {
    const result = await restoreVersion(props.versionId, supersedesVersionId.value || null)
    message.value = `已创建恢复版本 ${result.new_version_no}，历史版本未被覆盖。`
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '创建恢复版本失败' }
  finally { busy.value = false }
}

async function release() {
  busy.value = true; error.value = ''
  try { version.value = await releaseVersion(props.versionId); message.value = '版本已正式发布。'; await load() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '发布失败' }
  finally { busy.value = false }
}

async function loadRecords() {
  busy.value = true; error.value = ''
  try { records.value = await listExecutionRecords(props.versionId); if (!records.value.length) message.value = '本版本暂无执行记录。' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '执行记录加载失败' }
  finally { busy.value = false }
}

onMounted(load)
watch(() => props.versionId, () => { createdBatchId.value = ''; records.value = []; void load() })
</script>

<style scoped>
.optimization-panel { display:grid; gap:14px; }
.issue-picker { display:grid; gap:8px; max-height:360px; overflow:auto; }
.issue-option { display:grid; grid-template-columns:auto 1fr; gap:4px 10px; padding:10px; border:1px solid var(--line); border-radius:10px; }
.issue-option small { grid-column:2; color:var(--muted); }
.result-row { padding-top:8px; }
.record-list { display:grid; gap:7px; }
.record-list article { display:grid; grid-template-columns:1fr auto auto; gap:12px; padding:9px 12px; border:1px solid var(--line); border-radius:9px; }
</style>
