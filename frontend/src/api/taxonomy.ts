import { apiGet } from './client'

export type TaxonomyNode = {
  id?: number
  version_id?: number
  category_id: number
  category_name: string
  parent_id?: number | null
  level?: number
  path_ids?: string
  path_names?: string
  syn_list?: string | null
  is_leaf?: number
  child_count?: number
  node_status?: string
}

export function getTreeLevel(versionId: number, parentId?: number) {
  const parent = parentId === undefined ? '' : `&parent_id=${parentId}`
  return apiGet<TaxonomyNode[]>(`/taxonomy/tree?version_id=${versionId}${parent}`)
}

export function searchTaxonomyNodes(versionId: number, query: string) {
  return apiGet<TaxonomyNode[]>(`/taxonomy/search?version_id=${versionId}&q=${encodeURIComponent(query)}`)
}
