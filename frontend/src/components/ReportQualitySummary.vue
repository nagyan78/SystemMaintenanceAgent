<template>
  <section class="card report-quality">
    <div class="card-head"><div><p class="eyebrow">完整质量评价</p><h2>复诊与发布结论</h2></div><span class="badge" :data-tone="quality?.release_allowed ? 'success':'warning'">{{ quality?.release_allowed ? '允许发布':'不允许发布' }}</span></div>
    <div v-if="quality" class="metric-grid"><div><span>结构质量</span><strong>{{ structureScore }}</strong></div><div><span>内容质量</span><strong>{{ contentScore }}</strong></div><div><span>同义词质量</span><strong>{{ synonymScore }}</strong></div><div><span>修改前后</span><strong>{{ quality.before_issue_count }} → {{ quality.after_issue_count }}</strong></div><div><span>已解决/未解决/新增</span><strong>{{ quality.resolved_issues.length }}/{{ quality.unresolved_issues.length }}/{{ quality.new_issues.length }}</strong></div><div><span>复诊结论</span><strong>{{ quality.verification_status || '-' }}</strong></div></div>
    <div v-if="batch" class="audit-grid"><span>审核统计：通过 {{ batch.approved_count + batch.executed_count }}，驳回 {{ batch.rejected_count }}，暂不处理 {{ batch.deferred_count }}</span><span>执行动作批次：{{ records.length }} 次</span><span>生命周期：{{ quality?.lifecycle_status || '-' }}</span></div>
    <div v-if="quality" class="issue-columns"><article><h3>已解决</h3><p v-for="item in quality.resolved_issues" :key="Number(item.id)">{{ item.issue_type_label || item.issue_type }} · {{ item.node_name }}</p><p v-if="!quality.resolved_issues.length">无</p></article><article><h3>未解决</h3><p v-for="item in quality.unresolved_issues" :key="Number(item.id)">{{ item.issue_type_label || item.issue_type }} · {{ item.node_name }}</p><p v-if="!quality.unresolved_issues.length">无</p></article><article><h3>新增问题</h3><p v-for="item in quality.new_issues" :key="Number(item.id)">{{ item.issue_type_label || item.issue_type }} · {{ item.node_name }}</p><p v-if="!quality.new_issues.length">无</p></article></div>
    <p v-if="error" class="error">{{ error }}</p>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getVersionQuality, listExecutionRecords } from '../api/versions'
import type { ExecutionRecord, VersionQuality } from '../api/versions'
import { listReviewBatches } from '../api/reviews'
import type { ReviewBatchSummary } from '../api/reviews'
const props=defineProps<{versionId:number}>();const quality=ref<VersionQuality|null>(null),records=ref<ExecutionRecord[]>([]),batch=ref<ReviewBatchSummary|null>(null),error=ref('')
const activeIssues=computed(()=>[...(quality.value?.unresolved_issues||[]),...(quality.value?.new_issues||[])])
const issueCount=(predicate:(item:Record<string,unknown>)=>boolean)=>activeIssues.value.filter(predicate).length
const score=(count:number)=>Math.max(0,Math.round(100-count*10))
const structureScore=computed(()=>score(issueCount(item=>item.issue_category==='structure'))),contentScore=computed(()=>score(issueCount(item=>item.issue_category==='content'))),synonymScore=computed(()=>score(issueCount(item=>String(item.issue_type_code||item.issue_type).startsWith('synonym_'))))
async function load(){error.value='';try{const [q,r,b]=await Promise.all([getVersionQuality(props.versionId),listExecutionRecords(props.versionId),listReviewBatches()]);quality.value=q;records.value=r;batch.value=b.find(item=>item.new_version_id===props.versionId||item.version_id===props.versionId)||null}catch(cause){error.value=cause instanceof Error?cause.message:'质量评价加载失败'}}
onMounted(load);watch(()=>props.versionId,load)
</script>
<style scoped>.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.metric-grid div,.audit-grid span,.issue-columns article{padding:12px;border:1px solid var(--line);border-radius:12px}.metric-grid span{display:block;color:var(--muted);font-size:12px}.metric-grid strong{display:block;margin-top:5px}.audit-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.issue-columns{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:12px}.issue-columns p{font-size:12px}@media(max-width:800px){.metric-grid,.audit-grid,.issue-columns{grid-template-columns:1fr}}</style>
