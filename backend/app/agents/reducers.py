import operator
from typing import Annotated, TypedDict


class ContentDiagnosisSubgraphState(TypedDict, total=False):
    workflow_id: str
    run_id: str
    version_id: int
    plan: dict
    work_item_ids: list[str]
    processed_count: Annotated[int, operator.add]
    issue_count: Annotated[int, operator.add]
    clean_count: Annotated[int, operator.add]
    inconclusive_count: Annotated[int, operator.add]
    failed_count: Annotated[int, operator.add]
    work_item_counts: dict[str, int]
    work_item_id: str
