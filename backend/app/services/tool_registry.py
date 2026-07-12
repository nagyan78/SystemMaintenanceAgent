from dataclasses import dataclass
from typing import Any, Callable, Literal
from pydantic import BaseModel, Field, model_validator
from backend.app.repositories.tool_cache_repo import ToolCacheRepository
from backend.app.services.tool_cache import DataRevisionResolver, normalized_args_hash

class ToolSpec(BaseModel):
    name: str; owner_agents: set[str]; read_only: bool; side_effect: bool; timeout_ms: int=Field(ge=1)
    cost_level: Literal["low","medium","high"]; cache_ttl_seconds: int=Field(default=0,ge=0)
    result_limit: int=Field(default=100,ge=1); scoped_arguments: set[str]=Field(default_factory=set); redacted_fields: set[str]=Field(default_factory=set)
    @model_validator(mode="after")
    def no_side_effect_cache(self):
        if self.side_effect and self.cache_ttl_seconds: raise ValueError("side-effect tools cannot be cached")
        return self

@dataclass
class ToolRegistryMetrics: cache_hits:int=0; invocations:int=0

class ToolRegistry:
    def __init__(self, settings, workflow_id, version_id, agent_name):
        self.settings,self.workflow_id,self.version_id,self.agent_name=settings,workflow_id,version_id,agent_name
        self.specs={}; self.functions={}; self.repo=ToolCacheRepository(settings); self.resolver=DataRevisionResolver(settings); self.metrics=ToolRegistryMetrics()
    def register(self, spec: ToolSpec, function: Callable[...,Any]): self.specs[spec.name]=spec; self.functions[spec.name]=function
    def invoke(self, name, args):
        spec=self.specs[name]
        if self.agent_name not in spec.owner_agents: raise PermissionError(f"{self.agent_name} cannot invoke {name}")
        values=dict(args)
        if "version_id" in spec.scoped_arguments:
            if "version_id" in values and int(values["version_id"]) != self.version_id: raise ValueError("tool scope violation")
            values["version_id"]=self.version_id
        self.metrics.invocations += 1
        revision=self.resolver.for_tool(name, values) if spec.cache_ttl_seconds else ""
        key=normalized_args_hash(values)
        if spec.cache_ttl_seconds:
            cached=self.repo.get(self.workflow_id,self.version_id,name,key,revision)
            if cached is not None: self.metrics.cache_hits+=1; return cached
        if spec.side_effect and not values.get("idempotency_key"): raise ValueError("side-effect tool requires idempotency_key")
        result=self.functions[name](**values)
        if isinstance(result,list): result=result[:spec.result_limit]
        if isinstance(result,dict): result={k:v for k,v in result.items() if k not in spec.redacted_fields}
        if spec.cache_ttl_seconds: self.repo.put(self.workflow_id,self.version_id,name,key,revision,result,spec.cache_ttl_seconds)
        return result
