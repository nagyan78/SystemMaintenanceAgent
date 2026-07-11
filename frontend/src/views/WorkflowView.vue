<template>
  <AppShell><div class="page-stack">
    <section class="card">
      <div class="card-head"><div><p class="eyebrow">任务状态</p><h2>{{ statusLabel }}</h2></div><span class="badge" :data-tone="tone">{{ progress }}%</span></div>
      <div class="progress-track"><div class="progress-fill" :data-tone="tone" :style="{width:`${progress}%`}"><span class="progress-text">{{ progress }}%</span></div></div>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </section>
    <section class="card">
      <div class="card-head"><div><p class="eyebrow">简化工作流</p><h2>诊断进度</h2></div><span class="badge">{{ enableAi ? `AI · ${modelName}` : '快速模式' }}</span></div>
      <div class="simple-steps">
        <div v-for="step in steps" :key="step.key" class="simple-step" :data-state="step.state"><span class="step-mark">{{ step.state === 'completed' ? '✓' : step.state === 'running' ? '…' : '○' }}</span><div><strong>{{ step.label }}</strong><small>{{ step.description }}</small></div></div>
      </div>
      <div class="action-row">
        <RouterLink v-if="currentVersionId" class="button primary" :to="`/diagnosis/${currentVersionId}`">查看诊断结果</RouterLink>
        <RouterLink v-if="reviewBatchId" class="button secondary" :to="`/review/${reviewBatchId}?task_id=${taskId}`">建议审核</RouterLink>
        <RouterLink v-if="fileId" class="button secondary" :to="`/versions?file_id=${fileId}`">版本管理</RouterLink>
        <RouterLink v-if="currentVersionId" class="button secondary" :to="`/report/${currentVersionId}`">查看报告</RouterLink>
        <button v-if="status==='running'" class="button danger" @click="cancel">安全停止</button>
      </div>
    </section>
    <AgentRunProgress v-if="agentCounts.total" :counts="agentCounts" />
    <AgentEventLog v-if="enableAi || agentEvents.length" :events="agentEvents" />
  </div></AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import AgentRunProgress from '../components/AgentRunProgress.vue'
import AgentEventLog from '../components/AgentEventLog.vue'
import type { AgentEvent } from '../components/AgentEventLog.vue'
import { cancelWorkflow, getWorkflowStatus, workflowEvents } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const route=useRoute(), taskId=String(route.params.taskId), {state,patch}=useWorkspace()
const status=ref('pending'), progress=ref(0), currentStep=ref(''), currentVersionId=ref<number|null>(null), fileId=ref<number|null>(state.fileId), reviewBatchId=ref(''), errorMessage=ref(''), enableAi=ref(false), modelName=ref(''), timer=ref<number|null>(null)
const eventSource=ref<EventSource|null>(null), agentEvents=ref<AgentEvent[]>([]), seenEventIds=new Set<number>()
const rawCounts=ref<Record<string,number>>({})
const agentCounts=computed(()=>{const c=rawCounts.value,total=c.total||0,clean=c.clean||0,issues=c.succeeded||0,inconclusive=c.inconclusive||0,failed=c.permanent_failed||0,processed=clean+issues+inconclusive+failed;return{total,processed,issues,clean,inconclusive,failed,remaining:Math.max(total-processed,0)}})
const statusLabel=computed(()=>({pending:'等待',running:'运行中',waiting_review:'等待审核',completed:'完成',failed:'失败'}[status.value]||status.value))
const tone=computed(()=>status.value==='completed'?'success':status.value==='failed'?'danger':'warning')
const activeIndex=computed(()=> currentStep.value.includes('ai')?3:currentStep.value.includes('content')?2:currentStep.value.includes('rule')||currentStep.value.includes('structure')?1:0)
const steps=computed(()=>[
  {key:'excel',label:'Excel 解析',description:'读取字段并构建分类树'},
  {key:'structure',label:'结构检测',description:'全量执行确定性结构规则'},
  {key:'content',label:'内容检测',description:'执行低成本内容规则筛查'},
  ...(enableAi.value?[{key:'ai',label:'AI 分析',description:`仅分析候选问题 · ${modelName.value}`}]:[]),
].map((step,index)=>({...step,state:status.value==='completed'||index<activeIndex.value?'completed':index===activeIndex.value&&status.value==='running'?'running':'pending'})))

async function refresh(){try{const data=await getWorkflowStatus(taskId);status.value=data.status;progress.value=data.progress;currentStep.value=data.current_step;currentVersionId.value=data.current_version_id||null;fileId.value=data.file_id;reviewBatchId.value=data.review_batch_id||'';errorMessage.value=data.error_message||'';enableAi.value=Boolean(data.enable_ai_analysis);modelName.value=data.model_name||'';rawCounts.value=data.work_item_counts||{};patch({taskId,fileId:data.file_id,currentVersionId:data.current_version_id||null,reviewBatchId:data.review_batch_id||null,enableAiAnalysis:enableAi.value,modelName:modelName.value});if(['completed','failed','waiting_review','cancelled'].includes(data.status))stop()}catch(e){errorMessage.value=e instanceof Error?e.message:'状态查询失败';stop()}}
function consumeAgentEvent(type:string,event:MessageEvent){const data=JSON.parse(event.data||'{}'),id=Number(data.event_id||event.lastEventId||0);if(id&&seenEventIds.has(id))return;if(id)seenEventIds.add(id);agentEvents.value=[...agentEvents.value,{event_id:id,event_type:type,agent_name:data.agent_name,status:data.status,attempt:data.attempt,tool_name:data.tool_name,latency_ms:data.latency_ms,summary:data.summary,evidence_refs:data.evidence_refs}].slice(-200)}
function startEvents(){eventSource.value=workflowEvents(taskId);for(const type of ['agent_step','agent_tool_completed','candidate_completed','issue_completed'])eventSource.value.addEventListener(type,(event)=>consumeAgentEvent(type,event as MessageEvent))}
async function cancel(){try{status.value='running';currentStep.value='正在安全停止';await cancelWorkflow(taskId);await refresh()}catch(e){errorMessage.value=e instanceof Error?e.message:'取消失败'}}
function stop(){if(timer.value)window.clearInterval(timer.value);timer.value=null;eventSource.value?.close();eventSource.value=null}
onMounted(async()=>{await refresh();startEvents();if(['pending','running'].includes(status.value))timer.value=window.setInterval(refresh,1500)})
onBeforeUnmount(stop)
</script>

<style scoped>.simple-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.simple-step{display:flex;gap:12px;padding:16px;border:1px solid var(--line);border-radius:16px;opacity:.55}.simple-step[data-state='completed'],.simple-step[data-state='running']{opacity:1}.simple-step[data-state='completed'] .step-mark{background:var(--success)}.simple-step[data-state='running'] .step-mark{background:var(--primary)}.step-mark{width:28px;height:28px;display:grid;place-items:center;border-radius:50%;background:#9ca3af;color:white;flex:none}.simple-step div{display:grid;gap:5px}.simple-step small{color:var(--muted);line-height:1.4}@media(max-width:900px){.simple-steps{grid-template-columns:1fr 1fr}}@media(max-width:560px){.simple-steps{grid-template-columns:1fr}}</style>
