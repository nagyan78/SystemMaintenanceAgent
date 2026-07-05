from pydantic import BaseModel


class TaxonomyNodeRecord(BaseModel):
    category_id: int
    category_name: str
    parent_id: int | None
    level: int
    path_ids: str
    path_names: str
    category_group_id: str | None = None
    category_pids: str | None = None
    category_group_name: str | None = None
    syn_list: str | None = None
    is_leaf: int = 0


class BuildTreeResult(BaseModel):
    file_id: int
    node_count: int
    root_count: int
    max_depth: int
    max_children_count: int
    leaf_count: int
    non_leaf_count: int
    missing_parent_count: int
    duplicate_name_count: int
    synonym_non_empty_count: int


class OverviewResult(BuildTreeResult):
    version_id: int
