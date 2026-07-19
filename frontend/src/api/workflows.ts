import { apiGet, apiPost, getApiBaseUrl } from './client'

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
  status: 'pending' | 'running' | 'waiting_review' | 'partial' | 'completed_degraded' | 'completed' | 'failed' | 'cancelled'
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
  export_path?: string
  verification_status?: string
  quality_before?: number
  quality_after?: number
  quality_delta?: number
  remaining_issue_count?: number
  error_message?: string
  enable_ai_analysis?: boolean
  model_provider?: string | null
  model_name?: string | null
  analysis_run_id?: string | null
  work_item_counts?: Record<string, number>
  candidate_count?: number
  ai_processed_count?: number
  coverage?: DiagnosisCoverage
  diagnosis_completion_status?: 'completed' | 'partial' | 'failed'
  report_type?: 'draft' | 'partial' | 'failed' | 'final'
}

export type DiagnosisCoverage = {
  total_nodes: number; rule_scanned_nodes: number; rule_issue_count: number
  candidate_count: number; deep_diagnosed_count: number; ai_issue_count: number
  skipped_count: number; failed_count: number; unexamined_reasons: Record<string, number>
  model_calls: number; tokens_used: number; wall_seconds: number; plan_revision: number
  stop_reason?: string | null; rules_complete: boolean; ai_complete: boolean
  coverage_complete: boolean; completion_status: 'completed' | 'partial' | 'failed'
  run_id?: string | null; workflow_id?: string | null
}

export type WorkflowListItem = {
  id: string; file_id: number; file_name?: string; task_type: string; status: string
  current_step?: string; progress: number; version_id?: number; workflow_id?: string
  review_batch_id?: string; review_status?: string; execution_status?: string
  new_version_id?: number; verification_status?: string
  issue_count?: number; suggestion_count?: number
  draft_report_available?: boolean; final_report_available?: boolean
  created_time?: string; updated_time?: string; error_message?: string
}

export function listWorkflows() {
  return apiGet<WorkflowListItem[]>('/workflows')
}

export type ResumeRequest = {
  decision: 'approve' | 'reject' | 'edit' | 'confirm_no_action' | 'uncertain'
  approved_suggestion_ids: number[]
  rejected_suggestion_ids: number[]
  confirmed_without_action_suggestion_ids?: number[]
  uncertain_suggestion_ids?: number[]
  edits: Array<Record<string, unknown>>
  operator: string
  reject_reason?: string | null
}

export type StartWorkflowOptions = {
  enable_ai_analysis?: boolean
  model_provider?: 'ollama' | 'deepseek'
  model_name?: string
  priority_subtree_ids?: number[]
  sample_strategy?: 'focused' | 'full_scan' | 'sampling'
  focus_issues?: string[]
  ai_candidate_limit?: number
  ai_max_model_calls?: number
  ai_token_budget?: number
  ai_wall_seconds?: number
}

export function startWorkflow(fileId: number, options: StartWorkflowOptions = {}) {
  return apiPost<StartWorkflowResponse>('/workflows/taxonomy/start', { file_id: fileId, ...options })
}

export function getWorkflowStatus(taskId: string) {
  return apiGet<WorkflowStatus>(`/workflows/${taskId}`)
}

export function workflowEvents(taskId: string, afterId = 0): EventSource {
  const baseUrl = getApiBaseUrl()
  return new EventSource(`${baseUrl}/workflows/${taskId}/events?after_id=${afterId}`)
}

export function cancelWorkflow(taskId: string) {
  return apiPost<{task_id:string;status:string}>(`/workflows/${taskId}/cancel`)
}

export function resumeWorkflow(taskId: string, payload: ResumeRequest) {
  return apiPost<Record<string, unknown>>(`/workflows/${taskId}/resume`, payload)
}
