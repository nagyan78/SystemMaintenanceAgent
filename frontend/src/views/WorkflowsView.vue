<template><AppShell><div class="page-stack"><section class="card">
  <div class="card-head"><div><p class="eyebrow">后端任务资源</p><h2>全部工作流</h2></div><button class="button secondary" @click="load">刷新</button></div>
  <div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>阶段</th><th>状态</th><th>进度</th><th>创建时间</th><th>操作</th></tr></thead><tbody>
  <tr v-for="item in items" :key="item.id"><td>{{ item.file_name || `#${item.file_id}` }}</td><td>{{ item.current_step || '-' }}</td><td><span class="badge">{{ statusLabel(item.status) }}</span></td><td>{{ item.progress }}%</td><td>{{ item.created_time || '-' }}</td><td><RouterLink class="button secondary" :to="continueTo(item)">继续处理</RouterLink></td></tr>
  <tr v-if="!items.length"><td colspan="6">暂无任务</td></tr></tbody></table></div><p v-if="error" class="error">{{ error }}</p>
</section></div></AppShell></template>
<script setup lang="ts">
import { onMounted,ref } from 'vue';import AppShell from '../components/AppShell.vue';import { listWorkflows } from '../api/workflows';import type { WorkflowListItem } from '../api/workflows'
const items=ref<WorkflowListItem[]>([]),error=ref('');const statusLabel=(v:string)=>({running:'运行中',waiting_review:'待审核',completed:'已完成',failed:'失败',pending:'待开始'} as Record<string,string>)[v]||v
function continueTo(item:WorkflowListItem){if(item.review_batch_id&&item.execution_status!=='executed')return `/review/${item.review_batch_id}`;if(item.status==='completed'&&item.version_id)return `/report/${item.version_id}?type=final`;return `/workflow/${item.id}`}
async function load(){try{items.value=await listWorkflows()}catch(e){error.value=e instanceof Error?e.message:'加载失败'}}onMounted(load)
</script>
