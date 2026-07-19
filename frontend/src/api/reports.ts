import { apiGet, apiPost } from './client'

export type ReportType = 'draft' | 'partial' | 'failed' | 'final' | 'historical'

export type ReportResource = {
  version_id: number
  version_no: string
  report_name: string
  report_path: string
  report_type: ReportType
  status: string
  preview_url: string
  download_url: string
  pdf_download_url: string
}

export type ReportPreview = ReportResource & { markdown: string }

export type GeneratedReport = {
  version_id: number
  report_name: string
  report_path: string
  preview_url: string
  download_url: string
  pdf_download_url: string
  status: string
}

export function listReports(versionId?: number) {
  return apiGet<ReportResource[]>(`/reports${versionId ? `?version_id=${versionId}` : ''}`)
}

export function getReportPreview(versionId: number, reportType: ReportType) {
  return apiGet<ReportPreview>(`/reports/${versionId}/preview?report_type=${reportType}`)
}

export function generateReport(versionId: number, reportType: Exclude<ReportType, 'historical'> = 'final') {
  return apiPost<GeneratedReport>('/reports/generate', {
    version_id: versionId,
    format: 'markdown',
    report_type: reportType,
  })
}
