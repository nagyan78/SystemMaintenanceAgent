import { apiGet } from './client'

export type ReviewBatchSummary = {
  id: string
  file_id: number
  file_name: string
  version_id: number
  version_no: string
  task_id?: string | null
  status: string
  review_status?: string
  execution_status: string
  new_version_id?: number | null
  suggestion_count: number
  pending_count: number
  approved_count: number
  rejected_count: number
  deferred_count: number
  executed_count: number
  created_time?: string
  updated_time?: string
  workflow_state?: string
  preview_hash?: string | null
  can_generate_preview?: boolean
  can_execute?: boolean
  blocked_reason?: string | null
}

export function listReviewBatches() {
  return apiGet<ReviewBatchSummary[]>('/reviews')
}
