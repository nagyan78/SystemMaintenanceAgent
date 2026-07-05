import { apiRequest } from "./client";

export type FileUploadResponse = {
  file_id: number;
  task_id: string;
  file_name: string;
  row_count: number;
  column_count: number;
  columns: string[];
  status: "uploaded";
};

export type UploadedFileRecord = {
  id: number;
  file_name: string;
  file_path: string;
  file_size: number;
  sheet_name: string;
  row_count: number;
  column_count: number;
  upload_time: string;
  status: string;
};

export async function uploadExcel(file: File): Promise<FileUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest<FileUploadResponse>("/api/files/upload", {
    method: "POST",
    body: formData
  });
}

export async function listFiles(): Promise<UploadedFileRecord[]> {
  return apiRequest<UploadedFileRecord[]>("/api/files");
}
