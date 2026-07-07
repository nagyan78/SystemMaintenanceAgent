import { apiGet, apiUpload } from './client'

export type FileUploadResponse = {
  file_id: number
  task_id: string
  file_name: string
  row_count: number
  column_count: number
  columns: string[]
  status: string
}

export type FileRecord = {
  id: number
  file_id?: number
  file_name: string
  file_path?: string
  file_size?: number
  sheet_name?: string
  row_count: number
  column_count: number
  columns: string[]
  upload_time?: string
  status?: string
}

export function uploadFile(file: File) {
  return apiUpload<FileUploadResponse>('/files/upload', file)
}

export function listFiles() {
  return apiGet<FileRecord[]>('/files')
}

export function getFile(fileId: number) {
  return apiGet<FileRecord>(`/files/${fileId}`)
}
