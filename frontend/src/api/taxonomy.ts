import { apiGet } from './client'

export type TaxonomyNode = {
  id: number
  version_id: number
  category_id: number
  category_name: string
  parent_id: number | null
  level: number
  path_ids: string
  path_names: string
  syn_list?: string | null
  is_leaf: number
}

export type TaxonomyOverview = {
  version_id: number
  node_count: number
  root_count: number
  max_depth: number
  max_children_count: number
  leaf_count: number
  non_leaf_count: number
  missing_parent_count: number
  duplicate_name_count: number
  synonym_non_empty_count: number
}

export function getOverview(versionId: number) {
  return apiGet<TaxonomyOverview>(`/taxonomy/overview?version_id=${versionId}`)
}

export function getTree(versionId: number) {
  return apiGet<{ version_id: number; nodes: TaxonomyNode[] }>(`/taxonomy/tree?version_id=${versionId}`)
}

export function searchNodes(versionId: number, query: string) {
  return apiGet<{ version_id: number; query: string; nodes: TaxonomyNode[] }>(`/taxonomy/search?version_id=${versionId}&q=${encodeURIComponent(query)}`)
}
