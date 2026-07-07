import { apiGet, apiPost } from './client'

export type VersionRecord = {
  id: number
  file_id: number
  version_no: string
  description?: string | null
  quality_score?: number | null
  snapshot_path?: string | null
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
