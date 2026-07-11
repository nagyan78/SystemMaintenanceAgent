import { apiGet, apiPost } from './client'

export type ReportPreview = {
  version_id: number
  version_no: string
  report_name: string
  report_path: string
  download_url: string
  markdown: string
}

export type GeneratedReport = {
  version_id: number
  report_name: string
  report_path: string
  preview_url: string
  download_url: string
  status: string
}

export function getReportPreview(versionId: number) {
  return apiGet<ReportPreview>(`/reports/${versionId}/preview`)
}

export function generateReport(versionId: number) {
  return apiPost<GeneratedReport>('/reports/generate', {
    version_id: versionId,
    format: 'markdown',
  })
}
