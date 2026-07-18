import { apiGet } from './client'

export type DiagnosisIssue = {
  id: number
  issue_type: string
  node_id?: number | null
  node_name?: string | null
  description: string
  reason: string
  risk_level: 'low' | 'medium' | 'high'
  confidence: number
  status: string
  detector_version?: string
}

export function listIssues(versionId: number, status?: string) {
  const query = new URLSearchParams({ version_id: String(versionId) })
  if (status) query.set('status', status)
  return apiGet<{ version_id: number; issues: DiagnosisIssue[] }>(`/diagnosis/issues?${query}`)
}
