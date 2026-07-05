import { reactive } from "vue";
import { listFiles } from "../api/files";
import type { FileUploadResponse, UploadedFileRecord } from "../api/files";

export type WorkspaceState = {
  fileId: number | null;
  taskId: string | null;
  currentFile: FileUploadResponse | null;
  files: UploadedFileRecord[];
  loadingFiles: boolean;
};

export const workspace = reactive<WorkspaceState>({
  fileId: null,
  taskId: null,
  currentFile: null,
  files: [],
  loadingFiles: false
});

export function applyUploadResult(result: FileUploadResponse) {
  workspace.fileId = result.file_id;
  workspace.taskId = result.task_id;
  workspace.currentFile = result;
}

export async function refreshFiles() {
  workspace.loadingFiles = true;
  try {
    workspace.files = await listFiles();
  } finally {
    workspace.loadingFiles = false;
  }
}

export function formatUploadTime(uploadTime: string) {
  if (!uploadTime) return "";

  const legacySqliteUtc = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(uploadTime);
  const normalized = legacySqliteUtc ? `${uploadTime.replace(" ", "T")}Z` : uploadTime;
  const parsed = new Date(normalized);

  if (Number.isNaN(parsed.getTime())) return uploadTime;

  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  })
    .format(parsed)
    .replace(/\//g, "-");
}
