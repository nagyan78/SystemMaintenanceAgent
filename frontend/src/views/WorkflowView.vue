<template>
  <AppShell>
    <div class="page-stack workflow-page">
      <section class="card workflow-hero">
        <div class="workflow-hero-head">
          <div><p class="eyebrow">任务 {{ taskId }}</p><h2>{{ statusLabel }}</h2><p>{{ currentStepLabel }}</p></div>
          <strong class="workflow-percent" :data-tone="tone">{{ progress }}%</strong>
        </div>
        <div class="workflow-progress" :data-tone="tone"><span :style="{ width: `${progress}%` }"></span></div>
        <div class="workflow-meta"><span>{{ enableAi ? `AI · ${modelName || '已启用'}` : '规则模式' }}</span><span>{{ completedStepCount }} / {{ steps.length }} 个阶段完成</span></div>
        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <button v-if="isWorkflowRunning && isProgressModalDismissed" class="workflow-reopen" type="button" @click="isProgressModalDismissed = false">查看实时执行详情</button>
      </section>

      <section class="card">
        <div class="card-head"><div><p class="eyebrow">自动执行链路</p><h2>AI 审核与维护进度</h2></div><span class="badge" data-tone="success">无需人工审批</span></div>
        <div class="stage-grid">
          <div v-for="step in steps" :key="step.key" class="stage-card" :data-state="step.state">
            <span class="stage-index">{{ step.state === 'completed' ? '✓' : String(step.index).padStart(2, '0') }}</span>
            <div><strong>{{ step.label }}</strong><small>{{ step.description }}</small></div>
          </div>
        </div>
        <div class="action-row workflow-actions">
          <RouterLink v-if="currentVersionId" class="button primary" :to="`/tree/${currentVersionId}`">预览分类树</RouterLink>
          <RouterLink v-if="currentVersionId" class="button secondary" :to="`/diagnosis/${currentVersionId}`">查看诊断结果</RouterLink>
          <RouterLink v-if="fileId" class="button secondary" :to="`/versions?file_id=${fileId}`">版本管理</RouterLink>
          <RouterLink v-if="currentVersionId && isTerminal" class="button secondary" :to="`/report/${currentVersionId}?type=final`">查看最终报告</RouterLink>
          <button v-if="status === 'running'" class="button danger" @click="cancel">安全停止</button>
        </div>
      </section>

      <AgentRunProgress v-if="agentCounts.total" :counts="agentCounts" />
      <section v-if="enableAi" class="card budget-card">
        <div class="card-head"><div><p class="eyebrow">执行资源</p><h2>AI 分析预算</h2></div><span class="badge">Plan {{ planRevision }}</span></div>
        <div class="budget-grid"><div><span>模型调用</span><strong>{{ modelCallsUsed }}</strong></div><div><span>Token</span><strong>{{ tokensUsed }}</strong></div><div><span>耗时</span><strong>{{ wallSecondsUsed.toFixed(1) }}s</strong></div><div><span>候选处理</span><strong>{{ aiProcessedCount }}/{{ candidateCount }}</strong></div></div>
        <p v-if="stopReason" class="muted">停止原因：{{ stopReason }}</p>
      </section>
      <AgentEventLog v-if="enableAi || agentEvents.length" :events="agentEvents" />
    </div>

    <Teleport to="body">
      <Transition name="workflow-modal">
        <div v-if="isProgressModalVisible" class="workflow-modal-backdrop">
          <section class="workflow-modal" role="dialog" aria-modal="true" aria-labelledby="workflow-modal-title" aria-live="polite">
            <button class="workflow-modal-close" type="button" aria-label="关闭执行进度" @click="isProgressModalDismissed = true">×</button>
            <div class="workflow-modal-head"><div><p class="eyebrow">产品标准体系维护智能体</p><h2 id="workflow-modal-title">{{ statusLabel }}</h2><p>当前阶段：{{ currentStepLabel }}</p><span class="loading-line"><i></i>智能体正在自动执行</span></div><div class="modal-percent"><strong>{{ progress }}%</strong><span>{{ completedStepCount }} / {{ steps.length }}</span></div></div>
            <div class="modal-progress"><span :style="{ width: `${progress}%` }"></span></div>
            <div class="modal-stages"><div v-for="step in steps" :key="step.key" class="modal-stage" :data-state="step.state"><span>{{ step.state === 'completed' ? '✓' : step.state === 'running' ? '…' : '·' }}</span><div><strong>{{ step.label }}</strong><small>{{ step.description }}</small></div></div></div>
            <p class="modal-note">可以关闭弹窗继续浏览页面，任务会在后台保持运行并记录每个阶段。</p>
          </section>
        </div>
      </Transition>
    </Teleport>
  </AppShell>
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

const props = defineProps<{ taskId?: string }>()
const route = useRoute(), taskId = String(route.params.taskId || props.taskId), { state, patch } = useWorkspace()
const status = ref('pending'), progress = ref(0), currentStep = ref(''), currentVersionId = ref<number | null>(null), fileId = ref<number | null>(state.fileId)
const errorMessage = ref(''), enableAi = ref(false), modelName = ref(''), timer = ref<number | null>(null)
const eventSource = ref<EventSource | null>(null), agentEvents = ref<AgentEvent[]>([]), seenEventIds = new Set<number>()
const rawCounts = ref<Record<string, number>>({})
const planRevision = ref(1), stopReason = ref(''), modelCallsUsed = ref(0), tokensUsed = ref(0), wallSecondsUsed = ref(0), candidateCount = ref(0), aiProcessedCount = ref(0)
const isProgressModalDismissed = ref(false)

const statusLabel = computed(() => ({ pending: '正在准备', running: '正在自动维护', partial: '部分完成', completed_degraded: '降级完成', completed: '维护完成', failed: '执行失败', cancelled: '已停止', waiting_review: '旧任务已暂停' } as Record<string, string>)[status.value] || status.value)
const tone = computed(() => ['completed', 'completed_degraded', 'partial'].includes(status.value) ? 'success' : status.value === 'failed' ? 'danger' : 'warning')
const isWorkflowRunning = computed(() => ['pending', 'running'].includes(status.value))
const isTerminal = computed(() => ['partial', 'completed_degraded', 'completed'].includes(status.value))
const isProgressModalVisible = computed(() => isWorkflowRunning.value && !isProgressModalDismissed.value)
const currentStepLabel = computed(() => stepLabel(currentStep.value))
const agentCounts = computed(() => { const c = rawCounts.value, total = c.total || 0, clean = c.clean || 0, issues = c.succeeded || 0, inconclusive = c.inconclusive || 0, failed = c.permanent_failed || 0, processed = clean + issues + inconclusive + failed; return { total, processed, issues, clean, inconclusive, failed, remaining: Math.max(total - processed, 0) } })
const activeIndex = computed(() => {
  const value = currentStep.value
  if (value.includes('report') || value === 'completed') return 6
  if (value.includes('verify') || value.includes('new_version')) return 5
  if (value.includes('validate') || value.includes('execute') || value.includes('save_new')) return 4
  if (value.includes('review')) return 3
  if (value.includes('suggestion') || value.includes('ai')) return 2
  if (value.includes('diagnosis') || value.includes('content') || value.includes('structure')) return 1
  return 0
})
const steps = computed(() => [
  { key: 'import', label: '解析建树', description: '读取 Excel 并创建初始版本' },
  { key: 'diagnosis', label: '规则诊断', description: '全量筛查结构与内容问题' },
  { key: 'suggestion', label: 'AI 分析', description: '生成有证据的维护建议' },
  { key: 'review', label: 'AI 审核', description: '自动筛除不完整或不可靠建议' },
  { key: 'execute', label: '校验执行', description: '规则校验、快照预演并应用动作' },
  { key: 'verify', label: '保存复诊', description: '生成新版本并验证维护结果' },
  { key: 'report', label: '最终报告', description: '汇总覆盖、证据与版本变化' },
].map((step, index) => ({ ...step, index: index + 1, state: isTerminal.value || index < activeIndex.value ? 'completed' : index === activeIndex.value && isWorkflowRunning.value ? 'running' : 'pending' })))
const completedStepCount = computed(() => steps.value.filter(step => step.state === 'completed').length)

function stepLabel(value: string) { return ({ uploaded: '文件已上传', parse_excel: '正在解析 Excel', build_tree: '正在构建分类树', save_initial_version: '正在保存初始版本', index_vector: '正在建立向量索引', structure_diagnosis: '正在执行结构诊断', diagnosis_planning: '正在规划诊断范围', content_diagnosis: '正在执行内容诊断', generate_suggestion: '正在生成维护建议', ai_review: 'AI 正在自动审核建议', validate_action: '正在校验维护动作', execute_action: '正在执行维护动作', save_new_version: '正在保存新版本', verify_new_version: '正在复诊新版本', completed: '最终报告已生成', failed: '工作流执行失败' } as Record<string, string>)[value] || value || '正在建立执行上下文' }

async function refresh() {
  try {
    const data = await getWorkflowStatus(taskId)
    status.value = data.status; progress.value = data.progress; currentStep.value = data.current_step; currentVersionId.value = data.current_version_id || null; fileId.value = data.file_id; errorMessage.value = data.error_message || ''; enableAi.value = Boolean(data.enable_ai_analysis); modelName.value = data.model_name || ''; rawCounts.value = data.work_item_counts || {}; planRevision.value = Number(data.coverage?.plan_revision || 1); stopReason.value = String(data.coverage?.stop_reason || ''); modelCallsUsed.value = Number(data.coverage?.model_calls || 0); tokensUsed.value = Number(data.coverage?.tokens_used || 0); wallSecondsUsed.value = Number(data.coverage?.wall_seconds || 0); candidateCount.value = Number(data.coverage?.candidate_count || data.candidate_count || 0); aiProcessedCount.value = Number(data.coverage?.deep_diagnosed_count || data.ai_processed_count || 0)
    patch({ taskId, fileId: data.file_id, currentVersionId: data.current_version_id || null, newVersionId: data.executed_action_count ? data.current_version_id || null : state.newVersionId, enableAiAnalysis: enableAi.value, modelName: modelName.value })
    if (['completed', 'completed_degraded', 'partial', 'failed', 'cancelled'].includes(data.status)) stop()
  } catch (cause) { errorMessage.value = cause instanceof Error ? cause.message : '状态查询失败'; stop() }
}
function consumeAgentEvent(type: string, event: MessageEvent) { const data = JSON.parse(event.data || '{}'), id = Number(data.event_id || event.lastEventId || 0); if (id && seenEventIds.has(id)) return; if (id) seenEventIds.add(id); agentEvents.value = [...agentEvents.value, { event_id: id, event_type: type, agent_name: data.agent_name, status: data.status, attempt: data.attempt, tool_name: data.tool_name, latency_ms: data.latency_ms, summary: data.summary, evidence_refs: data.evidence_refs }].slice(-200) }
function startEvents() { eventSource.value = workflowEvents(taskId); for (const type of ['agent_step', 'agent_tool_completed', 'candidate_completed', 'issue_completed']) eventSource.value.addEventListener(type, event => consumeAgentEvent(type, event as MessageEvent)) }
async function cancel() { try { await cancelWorkflow(taskId); await refresh() } catch (cause) { errorMessage.value = cause instanceof Error ? cause.message : '取消失败' } }
function stop() { if (timer.value) window.clearInterval(timer.value); timer.value = null; eventSource.value?.close(); eventSource.value = null }
onMounted(async () => { await refresh(); if (isWorkflowRunning.value) { startEvents(); timer.value = window.setInterval(refresh, 1500) } })
onBeforeUnmount(stop)
</script>

<style scoped>
.workflow-page{max-width:920px}.workflow-hero{padding:24px}.workflow-hero-head{display:flex;justify-content:space-between;gap:18px}.workflow-hero-head h2{margin:5px 0}.workflow-hero-head p:not(.eyebrow){margin:0;color:var(--muted);font-size:13px}.workflow-percent{font-size:2rem;letter-spacing:-.05em}.workflow-percent[data-tone='success']{color:var(--success)}.workflow-percent[data-tone='danger']{color:var(--danger)}.workflow-percent[data-tone='warning']{color:var(--primary)}.workflow-progress{height:8px;overflow:hidden;margin:22px 0 10px;border-radius:999px;background:#edf0f5}.workflow-progress span{display:block;height:100%;min-width:4px;border-radius:inherit;background:var(--primary);transition:width .4s}.workflow-progress[data-tone='success'] span{background:var(--success)}.workflow-progress[data-tone='danger'] span{background:var(--danger)}.workflow-meta{display:flex;justify-content:space-between;color:var(--muted);font-size:11px}.workflow-reopen{margin-top:14px;padding:0;border:0;background:transparent;color:var(--primary);cursor:pointer;font-weight:650}.stage-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.stage-card{display:flex;gap:11px;padding:14px;border:1px solid var(--line);border-radius:11px;opacity:.48}.stage-card[data-state='completed'],.stage-card[data-state='running']{opacity:1}.stage-card[data-state='running']{border-color:#a9c2f3;background:#f6f9ff}.stage-index{display:grid;place-items:center;width:27px;height:27px;flex:none;border-radius:50%;background:#edf0f4;color:var(--muted);font-size:10px;font-weight:750}.stage-card[data-state='completed'] .stage-index{background:var(--success);color:#fff}.stage-card[data-state='running'] .stage-index{background:var(--primary);color:#fff}.stage-card strong,.stage-card small{display:block}.stage-card small{margin-top:3px;color:var(--muted);font-size:11px}.workflow-actions{margin-top:18px}.budget-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.budget-grid div{padding:13px;border-radius:10px;background:var(--surface-subtle)}.budget-grid span,.budget-grid strong{display:block}.budget-grid span{color:var(--muted);font-size:11px}.budget-grid strong{margin-top:3px}
.workflow-modal-backdrop{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:24px;background:rgba(17,26,43,.34);backdrop-filter:blur(9px)}.workflow-modal{position:relative;width:min(1020px,calc(100vw - 48px));padding:30px 32px 24px;border:1px solid rgba(255,255,255,.75);border-radius:22px;background:rgba(255,255,255,.94);box-shadow:0 30px 90px rgba(12,20,35,.28)}.workflow-modal-close{position:absolute;top:16px;right:16px;width:34px;height:34px;padding:0;border:0;border-radius:50%;background:#eaf0f8;color:#526176;cursor:pointer;font-size:22px}.workflow-modal-head{display:flex;justify-content:space-between;gap:24px;padding-right:38px}.workflow-modal-head h2{margin:5px 0}.workflow-modal-head p{margin:0;color:var(--muted);font-size:13px}.loading-line{display:flex;align-items:center;gap:7px;margin-top:12px;color:var(--primary);font-size:12px;font-weight:650}.loading-line i{width:14px;height:14px;border:2px solid rgba(47,111,237,.2);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite}.modal-percent{display:grid;justify-items:end;color:var(--muted);font-size:11px}.modal-percent strong{color:var(--primary);font-size:2rem}.modal-progress{height:7px;overflow:hidden;margin:22px 0;border-radius:999px;background:#e9eef7}.modal-progress span{display:block;height:100%;min-width:5px;border-radius:inherit;background:linear-gradient(90deg,var(--primary),#79a8ff)}.modal-stages{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.modal-stage{display:flex;gap:9px;padding:12px;border:1px solid var(--line);border-radius:12px;opacity:.48}.modal-stage[data-state='completed'],.modal-stage[data-state='running']{opacity:1}.modal-stage>span{display:grid;place-items:center;width:24px;height:24px;flex:none;border-radius:50%;background:#edf0f4}.modal-stage[data-state='completed']>span{background:var(--success);color:#fff}.modal-stage[data-state='running']>span{background:var(--primary);color:#fff}.modal-stage strong,.modal-stage small{display:block}.modal-stage strong{font-size:12px}.modal-stage small{margin-top:3px;color:var(--muted);font-size:10px;line-height:1.35}.modal-note{margin:18px 0 0;padding-top:13px;border-top:1px solid var(--line);color:var(--muted);font-size:11px}.workflow-modal-enter-active,.workflow-modal-leave-active{transition:opacity .22s}.workflow-modal-enter-from,.workflow-modal-leave-to{opacity:0}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.stage-grid,.budget-grid,.modal-stages{grid-template-columns:1fr 1fr}.workflow-modal-backdrop{align-items:end;padding:12px}.workflow-modal{width:100%;padding:24px 20px 18px;border-radius:18px}}@media(max-width:480px){.stage-grid,.budget-grid,.modal-stages{grid-template-columns:1fr}.workflow-meta{gap:8px;flex-direction:column}}
</style>
