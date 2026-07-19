from pydantic import BaseModel, Field

class AgentEvaluationResult(BaseModel):
    dataset_version: str; workflow_id: str
    detection_precision: float|None=None; detection_recall: float|None=None; detection_f1: float|None=None
    issue_type_accuracy: float|None=None; action_schema_valid_rate: float=0; action_executable_rate: float=0
    unsafe_action_escape_rate: float=0; human_accept_rate: float=0; human_edit_rate: float=0
    avg_cost_per_valid_issue: float=0; p95_candidate_latency_ms: float=0; model_calls: int=0
    tokens: int=0; cache_hit_rate: float=0; triage_count: int=0; calibration_bins: list[dict]=Field(default_factory=list)

class EvaluationBaseline(BaseModel):
    baseline_id: str; dataset_version: str; evaluation_id: int; agent_bundle_version: str
    approved_by: str; approved_time: str; pinned: bool=True
