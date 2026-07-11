import { API_BASE_URL, apiGet, apiPost } from './client'

export type StartWorkflowRequest = {
  mode: 'import' | 'maintain' | 'verify'
  file_id?: number
  base_version_id?: number
  result_version_id?: number
  affected_node_ids?: number[]
  max_rounds?: number
}

export type StartWorkflowResponse = {
  task_id: string
  workflow_id: string
  thread_id: string
  status: string
  current_step: string
  progress: number
}

export type WorkflowStatus = {
  task_id: string
  status: 'pending' | 'running' | 'waiting_review' | 'waiting_continue' | 'waiting_manual_intervention' | 'completed' | 'completed_degraded' | 'failed'
  current_step: string
  progress: number
  file_id: number
  current_version_id?: number
  version_no?: string
  node_count?: number
  structure_issue_count?: number
  content_issue_count?: number
  suggestion_count?: number
  approved_action_count?: number
  executed_action_count?: number
  review_batch_id?: string
  report_path?: string
  error_message?: string
  workflow_mode?: 'import' | 'maintain' | 'verify'
  base_version_id?: number
  result_version_id?: number
  evaluation_before_id?: number
  evaluation_after_id?: number
  evaluation_before?: QualityEvaluationSummary | null
  evaluation_after?: QualityEvaluationSummary | null
  verification?: Record<string, unknown>
  interrupt_type?: 'human_review' | 'continue_optimization'
  interrupt_id?: string
  round?: number
  max_rounds?: number
}

export type QualityEvaluationSummary = {
  id?: number
  total_score: number
  available_points: number
  coverage_ratio: number
  available_dimensions: Record<string, boolean>
  dimensions: Record<string, number>
  score_version: string
}

export type HumanReviewResumeRequest = {
  interrupt_type: 'human_review'
  interrupt_id: string
  decision: 'approve' | 'reject' | 'edit'
  approved_suggestion_ids: number[]
  rejected_suggestion_ids: number[]
  edits: Array<Record<string, unknown>>
  operator: string
  reject_reason?: string | null
}

export type ContinueResumeRequest = {
  interrupt_type: 'continue_optimization'
  interrupt_id: string
  decision: 'continue' | 'finish'
  operator: string
}

export type ResumeRequest = HumanReviewResumeRequest | ContinueResumeRequest

export function startWorkflow(payload: number | StartWorkflowRequest) {
  const request: StartWorkflowRequest = typeof payload === 'number'
    ? { mode: 'import', file_id: payload }
    : payload
  return apiPost<StartWorkflowResponse>('/workflows/taxonomy/start', request)
}

export function getWorkflowStatus(taskId: string) {
  return apiGet<WorkflowStatus>(`/workflows/${taskId}`)
}

export function workflowEvents(taskId: string): EventSource {
  const baseUrl = (localStorage.getItem('apiBaseUrl') || API_BASE_URL).replace(/\/$/, '')
  return new EventSource(`${baseUrl}/workflows/${taskId}/events`)
}

export function resumeWorkflow(taskId: string, payload: ResumeRequest) {
  return apiPost<Record<string, unknown>>(`/workflows/${taskId}/resume`, payload)
}
