import { API_BASE_URL, apiGet, apiPost } from './client'

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
  status: 'pending' | 'running' | 'waiting_review' | 'completed' | 'failed'
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
  report_preview_url?: string
  report_download_url?: string
  error_message?: string
  enable_ai_analysis?: boolean
  model_provider?: string | null
  model_name?: string | null
  analysis_run_id?: string | null
  work_item_counts?: Record<string, number>
}

export type ResumeRequest = {
  decision: 'approve' | 'reject' | 'edit'
  approved_suggestion_ids: number[]
  rejected_suggestion_ids: number[]
  edits: Array<Record<string, unknown>>
  operator: string
  reject_reason?: string | null
}

export function startWorkflow(fileId: number) {
  return apiPost<StartWorkflowResponse>('/workflows/taxonomy/start', { file_id: fileId })
}

export function getWorkflowStatus(taskId: string) {
  return apiGet<WorkflowStatus>(`/workflows/${taskId}`)
}

export function workflowEvents(taskId: string, afterId = 0): EventSource {
  const baseUrl = (localStorage.getItem('apiBaseUrl') || API_BASE_URL).replace(/\/$/, '')
  return new EventSource(`${baseUrl}/workflows/${taskId}/events?after_id=${afterId}`)
}

export function cancelWorkflow(taskId: string) {
  return apiPost<{task_id:string;status:string}>(`/workflows/${taskId}/cancel`)
}

export function resumeWorkflow(taskId: string, payload: ResumeRequest) {
  return apiPost<Record<string, unknown>>(`/workflows/${taskId}/resume`, payload)
}
