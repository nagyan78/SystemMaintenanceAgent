from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.taxonomy import TaxonomyNodeRecord
from backend.app.schemas.version import VersionDiff


class SplitGroup(BaseModel):
    name: str = Field(min_length=1)
    child_ids: list[int] = Field(min_length=1)


class SplitSubtreePayload(BaseModel):
    groups: list[SplitGroup] = Field(min_length=2)

    @model_validator(mode="after")
    def unique_assignment(self) -> "SplitSubtreePayload":
        assigned = [child_id for group in self.groups for child_id in group.child_ids]
        if len(assigned) != len(set(assigned)):
            raise ValueError("split child_ids must be unique across groups")
        names = [group.name.strip() for group in self.groups]
        if len(names) != len(set(names)):
            raise ValueError("split group names must be unique")
        return self


class MergeNodePayload(BaseModel):
    source_node_id: int
    target_node_id: int
    child_strategy: Literal["move_to_target"] = "move_to_target"
    synonym_strategy: Literal["union"] = "union"


class DeprecateNodePayload(BaseModel):
    target_node_id: int
    reason: str = Field(min_length=1)
    child_strategy: Literal["require_empty", "cascade_subtree"] = "require_empty"


class DeleteLeafPayload(BaseModel):
    target_node_id: int


class ActionPreview(BaseModel):
    valid: bool
    errors: list[dict] = Field(default_factory=list)
    diff: VersionDiff
    nodes: list[TaxonomyNodeRecord] = Field(default_factory=list)
    review_hash: str

