import { apiGet, apiPost } from './client'
import type { DiagnosisCoverage } from './workflows'

export type DiagnosisSummary = {
  version_id: number
  total_nodes: number
  structure_issue_count: number
  content_issue_count: number
  high_risk_count: number
  quality_score: number
  task_id?: string | null
  task_status?: string | null
  review_batch_id?: string | null
  enable_ai_analysis: boolean
  model_provider?: string | null
  model_name?: string | null
  ai_analysis_status?: 'completed' | 'partial' | 'not_requested' | null
  ai_warning?: string | null
  report_path?: string | null
  report_type?: 'draft' | 'partial' | 'failed' | 'final' | null
  run_id?: string | null
  workflow_id?: string | null
  coverage?: DiagnosisCoverage
}

export type DiagnosisIssue = {
  id: number
  version_id: number
  issue_type: string
  issue_type_code: string
  issue_type_label: string
  issue_category: 'structure' | 'content'
  node_id?: number | null
  node_name?: string | null
  path?: string | null
  description: string
  reason: string
  evidence: string
  confidence: number
  risk_level: string
  source: string
  run_ids?: string[]
  parent?: Record<string, unknown> | null
  children?: Array<Record<string, unknown>>
  siblings?: Array<Record<string, unknown>>
  suggestions?: Array<Record<string, unknown>>
}

export function importTaxonomy(fileId: number) {
  return apiPost<Record<string, unknown> & { version_id: number; node_count: number; max_depth: number; leaf_count: number }>('/taxonomy/import', { file_id: fileId })
}

export type DiagnosisRunConfig = {
  enable_ai_analysis: boolean
  model_provider: 'deepseek'
  model_name: string
  ai_candidate_limit?: number
  ai_wall_seconds?: number
  ai_max_model_calls?: number
  ai_token_budget?: number
  priority_subtree_ids?: number[]
  sample_strategy?: 'focused' | 'full_scan' | 'sampling'
  focus_issues?: string[]
}

export function runDiagnosis(fileId: number, config: DiagnosisRunConfig) {
  return apiPost<{ task_id: string; version_id: number; status: string; review_batch_id?: string | null; ai_analysis_status?: string; ai_warning?: string | null; report_path?: string | null }>('/diagnosis/run', { file_id: fileId, ...config })
}

export function getDiagnosisSummary(versionId: number) {
  return apiGet<DiagnosisSummary>(`/diagnosis/summary?version_id=${versionId}`)
}

export function listDiagnosisIssues(versionId: number) {
  return apiGet<DiagnosisIssue[]>(`/diagnosis/issues?version_id=${versionId}`)
}

export function getDiagnosisIssue(issueId: number) {
  return apiGet<DiagnosisIssue>(`/diagnosis/issues/${issueId}`)
}
