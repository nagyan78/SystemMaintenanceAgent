<template>
  <AppShell>
    <div v-if="isTaskAvailable" class="page-stack workflow-page">
      <section class="workflow-hero card">
        <div class="workflow-hero-head">
          <div><p class="eyebrow">自动维护任务</p><h2>{{ statusLabel }}</h2><p>{{ currentStepLabel }}</p></div>
          <span class="workflow-percent" :data-tone="badgeTone">{{ progress }}%</span>
        </div>
        <div class="workflow-progress" :data-tone="badgeTone"><span :style="{ width: `${progress}%` }"></span></div>
        <div class="workflow-meta"><span>任务 {{ taskId.slice(-8) }}</span><span>{{ activeStepCount }} / {{ stepOrder.length }} 个阶段</span></div>
        <button v-if="isWorkflowRunning && isProgressModalDismissed" class="workflow-reopen" type="button" @click="reopenProgressModal">查看实时执行详情</button>
      </section>

      <section v-if="status === 'waiting_continue' || ['completed', 'completed_degraded'].includes(status) || errorMessage" class="card workflow-result">
        <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
        <div class="action-row">
          <button v-if="status === 'waiting_continue'" class="button primary" @click="continueOptimization('continue')">继续优化</button>
          <button v-if="status === 'waiting_continue'" class="button secondary" @click="continueOptimization('finish')">结束并生成报告</button>
          <RouterLink v-if="['completed', 'completed_degraded'].includes(status) && currentVersionId" :to="`/versions?file_id=${fileId}`" class="button primary">查看版本</RouterLink>
          <RouterLink v-if="['completed', 'completed_degraded'].includes(status) && currentVersionId" :to="`/report/${currentVersionId}`" class="button secondary">查看报告</RouterLink>
        </div>
      </section>

      <QualityComparison v-if="evaluationBeforeId || evaluationAfterId || verification" :evaluation-before-id="evaluationBeforeId" :evaluation-after-id="evaluationAfterId" :evaluation-before="evaluationBefore" :evaluation-after="evaluationAfter" :verification="verification" />
      <details class="workflow-events"><summary>查看实时执行记录</summary><TaskStatusBar :task-id="taskId" @progress="onSseProgress" @interrupt="onSseInterrupt" @completed="onSseCompleted" @failed="onSseFailed" /></details>
    </div>

    <Teleport to="body">
      <Transition name="workflow-progress-modal">
        <div v-if="isProgressModalVisible" class="workflow-progress-backdrop">
          <section class="workflow-progress-modal" role="dialog" aria-modal="true" aria-labelledby="workflow-progress-title" aria-live="polite">
            <button class="workflow-modal-close" type="button" aria-label="关闭执行进度弹窗" title="关闭" @click="closeProgressModal">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
            <div class="workflow-modal-head">
              <div><p class="eyebrow">维护智能体正在执行</p><h2 id="workflow-progress-title">{{ currentStepLabel }}</h2><p>进度会随着每个阶段完成逐步更新。</p><p class="workflow-loading-state"><span class="workflow-spinner" aria-hidden="true"></span>智能体加载中</p></div>
              <div class="workflow-modal-percent"><strong>{{ progress }}%</strong><span>{{ activeStepCount }} / {{ stepOrder.length }}</span></div>
            </div>
            <div class="workflow-modal-progress"><span :style="{ width: `${progress}%` }"></span></div>
            <div class="stage-viewport" aria-label="执行阶段">
              <TransitionGroup name="stage-step" tag="div" class="stage-steps">
                <div v-for="step in visibleSteps" :key="step.key" class="stage-step" :data-state="step.state">
                  <span class="stage-marker"><svg v-if="step.state === 'completed'" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg><span v-else-if="step.state === 'running'"></span></span>
                  <div><strong>{{ step.label }}</strong><small>{{ step.phase }}<template v-if="step.key === currentStep"> · 当前阶段</template></small></div>
                </div>
              </TransitionGroup>
            </div>
            <p class="workflow-modal-note">请保持此页面打开，任务会自动保存阶段结果。</p>
          </section>
        </div>
      </Transition>
    </Teleport>
  </AppShell>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import QualityComparison from '../components/QualityComparison.vue'
import TaskStatusBar from '../components/TaskStatusBar.vue'
import { getWorkflowStatus, resumeWorkflow } from '../api/workflows'
import { useWorkspace } from '../state/workspace'

const route = useRoute()
const router = useRouter()
const { state, patch } = useWorkspace()
const taskId = String(route.params.taskId)
const status = ref('running')
const progress = ref(0)
const currentStep = ref('')
const currentVersionId = ref<number | null>(null)
const fileId = ref<number | null>(state.fileId)
const errorMessage = ref('')
const interruptId = ref('')
const evaluationBeforeId = ref<number | null>(state.evaluationBeforeId)
const evaluationAfterId = ref<number | null>(state.evaluationAfterId)
const evaluationBefore = ref<Record<string, unknown> | null>(state.evaluationBefore)
const evaluationAfter = ref<Record<string, unknown> | null>(state.evaluationAfter)
const verification = ref<Record<string, unknown> | null>(state.verification)
const timer = ref<number | null>(null)
const isTaskAvailable = ref(false)
const isProgressModalDismissed = ref(false)

const stepOrder = ['parse_excel', 'build_tree', 'save_initial_version', 'index_vector', 'structure_diagnosis', 'diagnosis_planning', 'content_diagnosis', 'generate_suggestion', 'validate_action', 'execute_action', 'save_new_version', 'index_result_version', 'result_quality_evaluation', 'verification', 'continue_optimization', 'completed'] as const
const stepMeta: Record<string, { label: string; phase: string }> = {
  parse_excel: { label: '解析 Excel', phase: 'M1' }, build_tree: { label: '构建分类树', phase: 'M1' }, save_initial_version: { label: '保存初始版本', phase: 'M1' }, index_vector: { label: '构建向量索引', phase: 'M2' }, structure_diagnosis: { label: '结构诊断', phase: 'M1/M2' }, diagnosis_planning: { label: '规划诊断范围', phase: 'M2' }, content_diagnosis: { label: '内容诊断', phase: 'M2' }, generate_suggestion: { label: '生成维护建议', phase: 'M3' }, validate_action: { label: '验证自动动作', phase: 'M3' }, execute_action: { label: '执行维护动作', phase: 'M4' }, save_new_version: { label: '保存新版本', phase: 'M4' }, index_result_version: { label: '索引结果版本', phase: '阶段一' }, result_quality_evaluation: { label: '评价维护质量', phase: '阶段一' }, verification: { label: '验证维护结果', phase: '阶段一' }, continue_optimization: { label: '确认优化轮次', phase: '阶段一' }, completed: { label: '生成诊断报告', phase: 'M4' },
}
const badgeTone = computed(() => ['completed', 'completed_degraded'].includes(status.value) ? 'success' : status.value === 'failed' ? 'danger' : 'warning')
const statusLabel = computed(() => ({ running: '正在运行', pending: '正在准备', waiting_continue: '等待下一步', waiting_manual_intervention: '需要人工处理', completed: '维护完成', completed_degraded: '降级完成', failed: '执行失败' } as Record<string, string>)[status.value] || status.value)
const currentStepLabel = computed(() => stepMeta[currentStep.value]?.label || '正在连接执行任务')
const currentIndex = computed(() => Math.max(stepOrder.indexOf(currentStep.value as typeof stepOrder[number]), 0))
const activeStepCount = computed(() => Math.min(currentIndex.value + 1, stepOrder.length))
const visibleSteps = computed(() => stepOrder.slice(0, Math.min(currentIndex.value + 3, stepOrder.length)).map((key, index) => ({ key, ...stepMeta[key], state: index < currentIndex.value || ['completed', 'completed_degraded'].includes(status.value) ? 'completed' : key === currentStep.value ? 'running' : 'pending' })))
const isWorkflowRunning = computed(() => isTaskAvailable.value && ['running', 'pending'].includes(status.value))
const isProgressModalVisible = computed(() => isWorkflowRunning.value && !isProgressModalDismissed.value)

function isMissingTask(error: unknown): boolean { return error instanceof Error && /Task not found|404/i.test(error.message) }
async function clearExpiredTask() {
  stop()
  patch({ taskId: null, workflowId: null, threadId: null, currentVersionId: null, newVersionId: null, versionNo: null, reportPath: null })
  await router.replace('/upload')
}
async function refresh(): Promise<boolean> {
  try {
    const data = await getWorkflowStatus(taskId)
    isTaskAvailable.value = true; status.value = data.status; progress.value = data.progress; currentStep.value = data.current_step; currentVersionId.value = data.current_version_id || null; fileId.value = data.file_id; errorMessage.value = data.error_message || ''; interruptId.value = data.interrupt_id || ''; evaluationBeforeId.value = data.evaluation_before_id || null; evaluationAfterId.value = data.evaluation_after_id || null; evaluationBefore.value = data.evaluation_before || null; evaluationAfter.value = data.evaluation_after || null; verification.value = data.verification || null
    patch({ taskId, fileId: data.file_id, currentVersionId: data.current_version_id || null, workflowMode: data.workflow_mode || state.workflowMode, baseVersionId: data.base_version_id || null, resultVersionId: data.result_version_id || null, evaluationBeforeId: data.evaluation_before_id || null, evaluationAfterId: data.evaluation_after_id || null, evaluationBefore: data.evaluation_before || null, evaluationAfter: data.evaluation_after || null, verification: data.verification || null, round: data.round || state.round, maxRounds: data.max_rounds || state.maxRounds, reportPath: data.report_path || null, versionNo: data.version_no || null })
    if (['waiting_continue', 'waiting_manual_intervention', 'completed', 'completed_degraded', 'failed'].includes(data.status)) stop()
    return true
  } catch (error) {
    if (isMissingTask(error)) { await clearExpiredTask(); return false }
    errorMessage.value = error instanceof Error ? error.message : '状态查询失败'; stop(); return false
  }
}
function onSseProgress(data: Record<string, unknown>) { if (typeof data.status === 'string') status.value = data.status; if (typeof data.progress === 'number') progress.value = data.progress; if (typeof data.current_step === 'string') currentStep.value = data.current_step }
async function onSseInterrupt(payload: Record<string, unknown>) { await refresh(); interruptId.value = String(payload.interrupt_id || ''); status.value = 'waiting_continue'; stop() }
async function continueOptimization(decision: 'continue' | 'finish') { if (!interruptId.value) { errorMessage.value = '缺少中断标识，请刷新后重试'; return }; try { await resumeWorkflow(taskId, { interrupt_type: 'continue_optimization', interrupt_id: interruptId.value, decision, operator: 'local_user' }); status.value = 'running'; isProgressModalDismissed.value = false; if (await refresh()) start() } catch (error) { errorMessage.value = error instanceof Error ? error.message : '恢复工作流失败' } }
async function onSseCompleted() { await refresh(); stop() }
async function onSseFailed(message: string) { errorMessage.value = message; await refresh(); stop() }
function closeProgressModal() { isProgressModalDismissed.value = true }
function reopenProgressModal() { isProgressModalDismissed.value = false }
function start() { if (!timer.value) timer.value = window.setInterval(() => { void refresh() }, 1500) }
function stop() { if (timer.value) window.clearInterval(timer.value); timer.value = null }
onMounted(async () => { const found = await refresh(); if (!found) return; if (status.value === 'running' || status.value === 'pending') start() })
onBeforeUnmount(stop)
</script>

<style scoped>
.workflow-page { max-width: 860px; gap: 14px; }
.workflow-hero { padding: 24px; }.workflow-hero-head { display: flex; justify-content: space-between; gap: 18px; }.workflow-hero-head h2 { margin: 5px 0 5px; font-size: 1.45rem; letter-spacing: -.03em; }.workflow-hero-head p:not(.eyebrow) { margin: 0; color: var(--muted); font-size: 13px; }.workflow-percent { font-size: 2rem; font-weight: 720; letter-spacing: -.05em; font-variant-numeric: tabular-nums; }.workflow-percent[data-tone='success'] { color: var(--success); }.workflow-percent[data-tone='danger'] { color: var(--danger); }.workflow-percent[data-tone='warning'] { color: var(--primary); }.workflow-progress { height: 8px; overflow: hidden; margin: 22px 0 10px; border-radius: 999px; background: #edf0f5; }.workflow-progress span { display: block; height: 100%; min-width: 4px; border-radius: inherit; background: var(--primary); transition: width .45s cubic-bezier(.2,.8,.2,1); }.workflow-progress[data-tone='success'] span { background: var(--success); }.workflow-progress[data-tone='danger'] span { background: var(--danger); }.workflow-meta { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px; }.workflow-reopen { margin-top: 14px; padding: 0; border: 0; background: transparent; color: var(--primary-strong); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; }.workflow-reopen:hover { color: var(--primary); }.workflow-reopen:focus-visible, .workflow-modal-close:focus-visible { outline: 3px solid rgba(47,111,237,.3); outline-offset: 3px; }
.workflow-progress-backdrop { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 24px; background: rgba(17,26,43,.34); backdrop-filter: blur(9px) saturate(125%); }.workflow-progress-modal { position: relative; width: min(1050px, calc(100vw - 48px)); padding: 30px 32px 22px; border: 1px solid rgba(255,255,255,.75); border-radius: 22px; background: rgba(255,255,255,.92); box-shadow: 0 30px 90px rgba(12,20,35,.28); }.workflow-modal-close { position: absolute; top: 16px; right: 16px; display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 0; border-radius: 50%; background: rgba(234,238,245,.9); color: #566174; cursor: pointer; }.workflow-modal-close:hover { background: #dfe7f6; color: var(--primary-strong); }.workflow-modal-close svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-linecap: round; stroke-width: 2; }.workflow-modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding-right: 36px; }.workflow-modal-head h2 { margin: 5px 0 5px; font-size: clamp(1.3rem, 2vw, 1.7rem); letter-spacing: -.035em; }.workflow-modal-head p:not(.eyebrow), .workflow-modal-note { margin: 0; color: var(--muted); font-size: 13px; }.workflow-loading-state { display: inline-flex; align-items: center; gap: 7px; margin-top: 12px !important; color: var(--primary-strong) !important; font-size: 12px !important; font-weight: 650; }.workflow-spinner { width: 14px; height: 14px; border: 2px solid rgba(47,111,237,.2); border-top-color: var(--primary); border-radius: 50%; animation: workflow-spin .8s linear infinite; }.workflow-modal-percent { display: grid; justify-items: end; gap: 2px; color: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }.workflow-modal-percent strong { color: var(--primary-strong); font-size: 2rem; letter-spacing: -.06em; line-height: 1; }.workflow-modal-progress { height: 7px; overflow: hidden; margin: 22px 0 24px; border-radius: 999px; background: #e9eef7; }.workflow-modal-progress span { display: block; min-width: 5px; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--primary), #79a8ff); transition: width .48s cubic-bezier(.2,.8,.2,1); }.stage-viewport { overflow-x: auto; padding: 7px 2px 14px; scrollbar-color: #c8d4e9 transparent; }.stage-steps { display: flex; align-items: flex-start; min-width: max-content; }.stage-step { position: relative; display: grid; grid-template-columns: 26px minmax(110px, 1fr); gap: 9px; align-items: center; width: 168px; min-height: 52px; padding-right: 20px; }.stage-step:not(:last-child)::after { position: absolute; top: 18px; right: 0; width: 20px; height: 1px; background: #dce4f0; content: ''; }.stage-marker { display: grid; place-items: center; width: 20px; height: 20px; border: 1px solid #d7dde7; border-radius: 50%; background: #fff; }.stage-step[data-state='completed'] .stage-marker { border-color: var(--success); background: var(--success); color: #fff; }.stage-step[data-state='completed']::after { background: color-mix(in srgb, var(--success) 58%, #dce4f0); }.stage-step[data-state='running'] .stage-marker { border-color: var(--primary); box-shadow: 0 0 0 5px rgba(47,111,237,.12); }.stage-step[data-state='running'] .stage-marker span { width: 7px; height: 7px; border-radius: 50%; background: var(--primary); }.stage-marker svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }.stage-step strong { display: block; font-size: 13px; line-height: 1.3; }.stage-step[data-state='pending'] strong, .stage-step[data-state='pending'] small { color: #9aa4b3; }.stage-step small { display: block; margin-top: 3px; color: var(--muted); font-size: 11px; }.stage-step[data-state='running'] strong { color: var(--primary-strong); }.stage-step-enter-active { transition: opacity .32s ease, transform .38s cubic-bezier(.2,.8,.2,1); }.stage-step-enter-from { opacity: 0; transform: translateX(14px); }.workflow-modal-note { padding-top: 4px; border-top: 1px solid rgba(216,223,234,.8); font-size: 11px; }@keyframes workflow-spin { to { transform: rotate(360deg); } }
.workflow-result { padding: 18px 24px; }.workflow-result .error { margin: 0 0 12px; }.workflow-events { border: 1px solid var(--line); border-radius: 10px; background: #fff; }.workflow-events summary { padding: 11px 14px; color: var(--muted); cursor: pointer; font-size: 12px; }.workflow-events :deep(.sse-panel) { border: 0; border-top: 1px solid var(--line); border-radius: 0; }
.workflow-progress-modal { transform-origin: center; }.workflow-progress-modal-enter-active, .workflow-progress-modal-leave-active { transition: opacity .24s ease; }.workflow-progress-modal-enter-active .workflow-progress-modal, .workflow-progress-modal-leave-active .workflow-progress-modal { transition: opacity .28s ease, transform .38s cubic-bezier(.2,.8,.2,1), filter .28s ease; }.workflow-progress-modal-enter-from, .workflow-progress-modal-leave-to { opacity: 0; }.workflow-progress-modal-enter-from .workflow-progress-modal, .workflow-progress-modal-leave-to .workflow-progress-modal { opacity: 0; transform: translateY(18px) scale(.98); filter: blur(3px); }
@media (max-width: 620px) { .workflow-hero-head { align-items: start; }.workflow-percent { font-size: 1.6rem; }.workflow-meta { gap: 8px; flex-direction: column; }.workflow-progress-backdrop { align-items: end; padding: 12px; }.workflow-progress-modal { width: 100%; padding: 24px 20px 18px; border-radius: 18px; }.workflow-modal-head { gap: 14px; }.workflow-modal-percent strong { font-size: 1.55rem; }.stage-step { width: 154px; } }
@media (prefers-reduced-motion: reduce) { .workflow-progress-backdrop { backdrop-filter: none; }.workflow-spinner { animation: none; }.workflow-progress-modal-enter-active .workflow-progress-modal, .workflow-progress-modal-leave-active .workflow-progress-modal, .stage-step-enter-active { transition: opacity .16s ease; }.workflow-progress-modal-enter-from .workflow-progress-modal, .workflow-progress-modal-leave-to .workflow-progress-modal, .stage-step-enter-from { transform: none; filter: none; } }
</style>
