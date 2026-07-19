import { apiGet, apiPost } from './client'

export type SuggestionRecord = {
  id: number
  review_batch_id?: string | null
  issue_id: number
  version_id: number
  action_type: string
  target_node_id?: number | null
  target_node_name?: string | null
  old_parent_id?: number | null
  new_parent_id?: number | null
  old_name?: string | null
  new_name?: string | null
  action_payload: Record<string, unknown>
  reason: string
  suggestion: string
  risk_level: 'low' | 'medium' | 'high'
  confidence: number
  need_confirm: boolean
  status: string
  change_preview: { action_type?: string; before?: Record<string, unknown>; after?: Record<string, unknown>; action?: Record<string, unknown>; impact?: Record<string, unknown>; impact_scope?: Record<string, unknown>; details?: Record<string, unknown> }
  before?: Record<string, unknown>
  after?: Record<string, unknown>
  action?: Record<string, unknown>
  impact_scope?: Record<string, unknown>
  is_executable?: boolean
  needs_manual_edit?: boolean
  is_complete?: boolean
  regenerated_at?: string | null
  generator_version?: string | null
  consistency_status?: string
  consistency_reason?: string | null
  is_manual?: boolean
  work_item_id?: string | null
  analysis_run_id?: string | null
  issue?: {
    id: number
    issue_type: string
    issue_type_code: string
    issue_type_label: string
    issue_category: 'structure' | 'content'
    node_name?: string | null
    path?: string | null
    subject_node_id?: number | null
    subject_node_name?: string | null
    subject_path?: string | null
    description: string
    reason: string
    evidence: string
    status: string
  } | null
}

export type ReviewBatch = {
  batch?: ReviewBatchSummary | null
  review_batch_id: string
  suggestion_count: number
  suggestions: SuggestionRecord[]
  legacy_warning?: boolean
  type_stats?: IssueTypeStat[]
  incomplete_suggestion_ids?: number[]
  invalid_suggestion_ids?: number[]
  execution_preview?: ExecutionPreviewResult | null
}

export type IssueTypeStat = {
  issue_type_code: string
  issue_type_label: string
  total: number
  pending: number
  approved: number
  rejected: number
  deferred: number
}

export type ReviewDecisionRequest = {
  decision: 'approve' | 'reject' | 'edit' | 'confirm_no_action' | 'uncertain'
  approved_suggestion_ids: number[]
  rejected_suggestion_ids: number[]
  confirmed_without_action_suggestion_ids?: number[]
  uncertain_suggestion_ids?: number[]
  edits: Array<Record<string, unknown>>
  operator: string
  reject_reason?: string | null
}

export type ReviewDecisionResult = {
  review_batch_id: string
  approved_count: number
  status: string
}

export type ExecuteReviewResult = {
  review_batch_id: string
  source_version_id: number
  new_version_id?: number | null
  new_version_no?: string | null
  node_count?: number
  executed_count: number
  failed_count: number
  quality_score?: number | null
  quality_before?: number | null
  quality_after?: number | null
  quality_delta?: number | null
  verification_status?: string
  export_path?: string
  report_path?: string
  report_preview_url?: string
  message?: string
}

export function getReviewBatch(reviewBatchId: string) {
  return apiGet<ReviewBatch>(`/reviews/${reviewBatchId}`)
}

export function applyReviewDecision(reviewBatchId: string, payload: ReviewDecisionRequest) {
  return apiPost<ReviewDecisionResult>(`/reviews/${reviewBatchId}/decision`, payload)
}

export function autoCompleteReview(reviewBatchId: string, operator = 'local_user') {
  return apiPost<{ review_batch_id: string; approved_ids: number[]; ignored_ids: number[]; unchanged_ids: number[]; batch: ReviewBatchSummary }>(`/reviews/${reviewBatchId}/auto-complete`, { operator })
}

export function executeReviewBatch(reviewBatchId: string, operator = 'local_user') {
  return apiPost<ExecuteReviewResult>(`/reviews/${reviewBatchId}/execute`, { operator })
}

export type ReviewBatchSummary = {
  id: string; file_id: number; file_name: string; version_id: number; version_no: string
  task_id?: string | null; status: 'in_review' | 'reviewed' | 'preview_ready' | 'executing' | 'executed' | 'failed' | string
  review_status?: string; preview_status?: string
  execution_status: 'blocked' | 'missing' | 'stale' | 'ready' | 'executed' | string; new_version_id?: number | null
  suggestion_count: number; pending_count: number; approved_count: number
  rejected_count: number; deferred_count: number; executed_count: number
  created_time?: string; updated_time?: string
  workflow_state?: 'reviewing'|'review_completed'|'preview_required'|'preview_passed'|'executable'|'executed'|string
  preview_hash?: string | null
  can_generate_preview?: boolean
  can_execute?: boolean
  blocked_reason?: string | null
}

export function listReviewBatches() {
  return apiGet<ReviewBatchSummary[]>('/reviews')
}

export type ActionPreviewResult = {
  valid: boolean
  errors: Array<Record<string, unknown>>
  diff: Record<string, Array<Record<string, unknown>>>
  review_hash: string
}

export function previewReviewBatch(reviewBatchId: string, suggestionIds: number[]) {
  return apiPost<ActionPreviewResult>(`/reviews/${reviewBatchId}/preview`, { suggestion_ids: suggestionIds })
}

export type ExecutionPreviewResult = ActionPreviewResult & {
  review_batch_id: string; base_version_id: number; warnings: Array<Record<string, unknown>>
  action_counts: Record<string, number>; affected_child_count: number; affected_reference_count: number
  path_changes: Array<Record<string, unknown>>; checks: Record<string, unknown>
  deduplicated_actions?: Array<Record<string, unknown>>
  summary?: string
}

export function createExecutionPreview(reviewBatchId: string) {
  return apiPost<ExecutionPreviewResult>(`/reviews/${reviewBatchId}/execution-preview`, {})
}

export function createManualSuggestions(reviewBatchId: string, suggestions: Array<Record<string, unknown>>) {
  return apiPost<{ review_batch_id: string; created_count: number; suggestion_ids: number[] }>(`/reviews/${reviewBatchId}/manual-suggestions`, { suggestions })
}

export function regenerateReviewBatch(reviewBatchId: string) {
  return apiPost<{ source_review_batch_id: string; review_batch_id: string; suggestion_count: number; regenerated_count: number; reset_to_pending_count: number }>(`/reviews/${reviewBatchId}/regenerate`, {})
}
