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
  workflowMode: 'import' | 'maintain' | 'verify'
  baseVersionId: number | null
  resultVersionId: number | null
  currentVersionId: number | null
  newVersionId: number | null
  versionNo: string | null
  reviewBatchId: string | null
  evaluationBeforeId: number | null
  evaluationAfterId: number | null
  verification: Record<string, unknown> | null
  round: number
  maxRounds: number
  reportPath: string | null
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
  workflowMode: 'import',
  baseVersionId: null,
  resultVersionId: null,
  currentVersionId: null,
  newVersionId: null,
  versionNo: null,
  reviewBatchId: null,
  evaluationBeforeId: null,
  evaluationAfterId: null,
  verification: null,
  round: 1,
  maxRounds: 2,
  reportPath: null,
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
