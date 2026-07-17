<template>
  <AppShell>
    <div class="page-stack">
      <section class="card">
        <div class="card-head">
          <div><p class="eyebrow">审核中心</p><h2>建议审核批次</h2></div>
          <div class="action-row"><select v-model="filter"><option value="all">全部状态</option><option value="pending">待审核</option><option value="in_review">审核中</option><option value="completed">已完成</option></select><select v-model.number="fileFilter"><option :value="0">全部文件</option><option v-for="file in fileOptions" :key="file.id" :value="file.id">{{ file.name }}</option></select><button class="button danger" :disabled="!selectedIds.length || cleanupBusy" @click="showCleanup=true">删除选中批次</button></div>
        </div>
        <p v-if="loading" class="muted">正在读取审核批次…</p>
        <p v-else-if="error" class="error">{{ error }}</p>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead><tr><th><input type="checkbox" :checked="selectedIds.length === filtered.length" @change="toggleAll" /></th><th>文件</th><th>基线</th><th>建议</th><th>待审核</th><th>已通过</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in filtered" :key="item.id">
                <td><input v-model="selectedIds" type="checkbox" :value="item.id" /></td>
                <td>{{ item.file_name }}</td><td>{{ item.version_no }}</td><td>{{ item.suggestion_count }}</td><td>{{ item.pending_count }}</td><td>{{ item.approved_count + item.executed_count }}</td><td>{{ label(item) }}</td>
                <td><RouterLink class="button primary" :to="`/review/${item.id}`">{{ item.execution_status === 'executed' ? '查看' : '继续审核' }}</RouterLink></td>
              </tr>
              <tr v-if="!filtered.length"><td colspan="7">后端当前确实没有符合条件的审核批次</td></tr>
            </tbody>
          </table>
        </div>
      </section>
      <DataManagementDialog :show="showCleanup" :review-batch-ids="selectedIds" :file-ids="selectedFileIds" :reset-workspace-on-complete="false" @close="showCleanup=false" @completed="cleanupCompleted" />
    </div>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import DataManagementDialog from '../components/DataManagementDialog.vue'
import { describeApiError } from '../api/client'
import { listReviewBatches } from '../api/reviews'
import type { ReviewBatchSummary } from '../api/reviews'

const items = ref<ReviewBatchSummary[]>([])
const filter = ref('all')
const fileFilter = ref(0)
const selectedIds = ref<string[]>([])
const cleanupBusy = ref(false)
const showCleanup = ref(false)
const error = ref('')
const loading = ref(false)
const filtered = computed(() => items.value.filter(item => (filter.value === 'all' || item.status === filter.value) && (!fileFilter.value || item.file_id === fileFilter.value)))
const fileOptions = computed(() => [...new Map(items.value.map(item => [item.file_id, { id:item.file_id, name:item.file_name }])).values()])
const selectedFileIds = computed(() => [...new Set(items.value.filter(item => selectedIds.value.includes(item.id)).map(item => item.file_id))])
const label = (item: ReviewBatchSummary) => item.execution_status === 'executed' ? '已执行' : ({ pending: '待审核', in_review: '审核中', completed: '审核完成' } as Record<string, string>)[item.status] || item.status

async function load() {
  loading.value = true
  error.value = ''
  try { items.value = await listReviewBatches() }
  catch (cause) { error.value = describeApiError(cause, '审核批次加载失败') }
  finally { loading.value = false }
}
function toggleAll(){const allowed=filtered.value.map(item=>item.id);selectedIds.value=selectedIds.value.length===allowed.length?[]:allowed}
async function cleanupCompleted(){showCleanup.value=false;selectedIds.value=[];await load()}

onMounted(load)
</script>
