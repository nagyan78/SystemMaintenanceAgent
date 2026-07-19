import { reactive } from 'vue'

export type WorkspaceState = {
  apiBaseUrl: string
  fileId: number | null
  fileName: string | null
  fileRowCount: number | null
  fileColumnCount: number | null
  fileColumns: string[]
  taskId: string | null
  workflowId: string | null
  threadId: string | null
  currentVersionId: number | null
  newVersionId: number | null
  versionNo: string | null
  reviewBatchId: string | null
  reportPath: string | null
  enableAiAnalysis: boolean
  modelProvider: 'ollama' | 'deepseek'
  modelName: string
}

const STORAGE_KEY = 'taxonomy-workbench-state'

const defaultState = (): WorkspaceState => ({
  apiBaseUrl: localStorage.getItem('apiBaseUrl') || 'http://127.0.0.1:8000/api',
  fileId: null,
  fileName: null,
  fileRowCount: null,
  fileColumnCount: null,
  fileColumns: [],
  taskId: null,
  workflowId: null,
  threadId: null,
  currentVersionId: null,
  newVersionId: null,
  versionNo: null,
  reviewBatchId: null,
  reportPath: null,
  enableAiAnalysis: false,
  modelProvider: 'ollama',
  modelName: 'qwen3:8b',
})

const state = reactive(defaultState())

function hydrate() {
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return
  Object.assign(state, defaultState(), JSON.parse(raw))
}

function persist() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  localStorage.setItem('apiBaseUrl', state.apiBaseUrl)
}

function patch(partial: Partial<WorkspaceState>) {
  Object.assign(state, partial)
  persist()
}

function reset() {
  Object.assign(state, defaultState())
  persist()
}

hydrate()

export function useWorkspace() {
  return { state, patch, reset }
}
