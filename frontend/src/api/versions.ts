import { apiGet, apiPost } from './client'

export type VersionRecord = {
  id: number
  file_id: number
  version_no: string
  description?: string | null
  quality_score?: number | null
  snapshot_path?: string | null
  parent_version_id?: number | null
  source_workflow_id?: string | null
  action_batch_id?: string | null
  verification_status?: 'not_verified' | 'passed' | 'partial' | 'failed' | string
  lifecycle_status?: 'draft' | 'verifying' | 'passed' | 'partial' | 'failed' | 'released' | 'superseded' | string
  supersedes_version_id?: number | null
  diagnosis_mode?: string | null
  diagnosis_model?: string | null
  verification_mode?: string | null
  verification_model?: string | null
  export_path?: string | null
  created_time?: string | null
  node_count?: number
}

export type VersionDiff = {
  from_version_id: number
  to_version_id: number
  added: Array<Record<string, unknown>>
  deleted: Array<Record<string, unknown>>
  renamed: Array<Record<string, unknown>>
  moved: Array<Record<string, unknown>>
  synonym_changed: Array<Record<string, unknown>>
}

export type ExportResult = {
  version_id: number
  version_no: string
  file_name: string
  export_path: string
  download_url: string
}

export function listVersions(fileId?: number) {
  const query = fileId ? `?file_id=${fileId}` : ''
  return apiGet<VersionRecord[]>(`/versions${query}`)
}

export function getVersion(versionId: number) {
  return apiGet<VersionRecord>(`/versions/${versionId}`)
}

export function getVersionDiff(fromId: number, toId: number) {
  return apiGet<VersionDiff>(`/versions/${fromId}/diff?target_version_id=${toId}`)
}

export function rollbackVersion(versionId: number) {
  return apiPost<Record<string, unknown>>(`/versions/${versionId}/rollback`)
}

export function exportVersion(versionId: number) {
  return apiGet<ExportResult>(`/versions/${versionId}/export`)
}

export type VersionQuality = {
  version_id: number; version_no: string; parent_version_id?: number | null
  before_issue_count: number; after_issue_count: number
  quality_before?: number | null; quality_after?: number | null
  improvement_rate: number; verification_status?: string; lifecycle_status?: string; release_allowed?: boolean
  remaining_issues: Array<Record<string, unknown>>
  resolved_issues: Array<Record<string, unknown>>
  unresolved_issues: Array<Record<string, unknown>>
  new_issues: Array<Record<string, unknown>>
  deferred_issues: Array<Record<string, unknown>>
  false_positive_issues: Array<Record<string, unknown>>
}

export function getVersionQuality(versionId: number) {
  return apiGet<VersionQuality>(`/versions/${versionId}/quality`)
}

export type ExecutionRecord = {
  id: number
  review_batch_id: string
  source_version_id: number
  target_version_id: number
  review_hash: string
  action_summary: string
  status: string
  created_time?: string
}

export type RestoredVersionResult = {
  source_version_id: number
  new_version_id: number
  new_version_no: string
  node_count: number
  quality_score?: number | null
}

export function createVersionReviewBatch(versionId: number, issueIds: number[]) {
  return apiPost<{ review_batch_id: string; suggestion_count: number }>(`/versions/${versionId}/review-batches`, { issue_ids: issueIds })
}

export function restoreVersion(versionId: number, supersedesVersionId?: number | null) {
  return apiPost<RestoredVersionResult>(`/versions/${versionId}/restore`, { supersedes_version_id: supersedesVersionId || null, operator: 'local_user' })
}

export function releaseVersion(versionId: number) {
  return apiPost<VersionRecord>(`/versions/${versionId}/release`)
}

export function listExecutionRecords(versionId: number) {
  return apiGet<ExecutionRecord[]>(`/versions/${versionId}/execution-records`)
}
