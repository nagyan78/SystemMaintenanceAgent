import { apiGet } from './client'
export type EvaluationItem = { id:number; dataset_version:string; workflow_id:string; metrics:Record<string, number | string | null> }
export const listEvaluations = () => apiGet<EvaluationItem[]>('/evaluations')
export const getReleaseGate = (dataset:string,id:number) => apiGet<Record<string,unknown>>(`/evaluations/release-gate?dataset_version=${encodeURIComponent(dataset)}&evaluation_id=${id}`)
