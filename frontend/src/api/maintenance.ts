import { apiPost } from './client'

export type CleanupRequest = {
  workflow_ids?: string[]; review_batch_ids?: string[]; file_ids?: number[]
  failed_workflows?: boolean; incomplete_workflows?: boolean; all_business_data?: boolean; force_cancel_running?: boolean
}
export type CleanupPreview = {
  cleanup_preview_id: string; blocking_reasons: string[]; expires_time: string
  task_count: number; diagnosis_issue_count: number; suggestion_count: number; review_batch_count: number
  review_decision_count: number; execution_preview_count: number; execution_record_count: number
  version_count: number; node_snapshot_count: number; report_count: number; uploaded_file_count: number; vector_index_count: number
  filesystem_paths: string[]; database_backup_path: string
}
export function previewCleanup(payload: CleanupRequest) { return apiPost<CleanupPreview>('/maintenance/cleanup/preview', payload) }
export function executeCleanup(cleanupPreviewId: string, confirmation: string) { return apiPost<{ deleted: Record<string, number>; filesystem_deleted: number; pending_file_cleanup: string[]; database_backup_path: string }>('/maintenance/cleanup/execute', { cleanup_preview_id: cleanupPreviewId, confirmation }) }
export async function cleanupNow(payload: CleanupRequest, fallbackFileIds: number[] = []) {
  payload = { ...payload, force_cancel_running: true }
  let preview = await previewCleanup(payload)
  if (preview.blocking_reasons.length && fallbackFileIds.length && preview.blocking_reasons.some(requiresWholeFileDelete)) {
    payload = { file_ids: [...new Set(fallbackFileIds)], force_cancel_running: true }
    preview = await previewCleanup(payload)
  }
  if (preview.blocking_reasons.length) throw new Error(preview.blocking_reasons.join('；'))
  return executeCleanup(preview.cleanup_preview_id, payload.all_business_data ? 'DELETE ALL' : 'CONFIRM')
}

function requiresWholeFileDelete(reason: string) {
  return reason.includes('删除整个文件') || reason.includes('全部派生数据') || reason.includes('仍被其他任务或审核批次引用')
}
