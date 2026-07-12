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
}

export type ReviewBatch = {
  review_batch_id: string
  suggestion_count: number
  suggestions: SuggestionRecord[]
}

export type ReviewDecisionRequest = {
  decision: 'approve' | 'reject' | 'edit'
  approved_suggestion_ids: number[]
  rejected_suggestion_ids: number[]
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
  message?: string
}

export function getReviewBatch(reviewBatchId: string) {
  return apiGet<ReviewBatch>(`/reviews/${reviewBatchId}`)
}

export function applyReviewDecision(reviewBatchId: string, payload: ReviewDecisionRequest) {
  return apiPost<ReviewDecisionResult>(`/reviews/${reviewBatchId}/decision`, payload)
}

export function executeReviewBatch(reviewBatchId: string, operator = 'local_user') {
  return apiPost<ExecuteReviewResult>(`/reviews/${reviewBatchId}/execute`, { operator })
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
