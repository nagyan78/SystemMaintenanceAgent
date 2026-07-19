import { apiGet, apiPost } from './client'
export type TriageItem={id:number;workflow_id:string;node_id:number|null;node_name:string|null;issue_type:string;reason:string|null;evidence:string|null;confidence:number;detector_disagreement:number}
export const listTriage=(workflowId='')=>apiGet<TriageItem[]>(`/triage${workflowId?`?workflow_id=${encodeURIComponent(workflowId)}`:''}`)
export const decideTriage=(id:number,decision:'issue'|'clean'|'inconclusive')=>apiPost(`/triage/${id}/decision`,{decision,operator:'local_user'})
