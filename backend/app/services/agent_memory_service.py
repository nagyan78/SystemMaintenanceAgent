from backend.app.config import Settings
from backend.app.db import connect
from backend.app.repositories.agent_memory_repo import AgentMemoryRepository

class AgentMemoryService:
    def __init__(self, settings: Settings): self.settings=settings; self.repo=AgentMemoryRepository(settings)
    def record_review_feedback(self, *, workflow_id, version_id, suggestion, decision, reason=None):
        with connect(self.settings) as c:
            row=c.execute("SELECT issue_type FROM diagnosis_issue WHERE id=?", (suggestion.issue_id,)).fetchone()
        issue_type=str(row[0]) if row else "unknown"
        content={"decision":decision,"reason":reason or "","issue_type":issue_type,"action_type":suggestion.action_type,"target_node_id":suggestion.target_node_id}
        return self.repo.create(memory_type="review_feedback",scope_type="issue_action",scope_key=f"{issue_type}:{suggestion.action_type}",content=content,source_workflow_id=workflow_id,source_version_id=version_id,valid_from_version_id=version_id,confidence=1.0)
    def get_suggestion_context(self, *, version_id, issue_type, action_type=None, target_node_id=None, limit=5):
        if action_type: return self.repo.list_for_scope(f"{issue_type}:{action_type}",version_id,limit)
        contexts=[]
        for action in ("merge_node","split_subtree","move_node","rename_node","clean_synonym","deprecate_node","delete_leaf_node"):
            contexts.extend(self.repo.list_for_scope(f"{issue_type}:{action}",version_id,limit))
        contexts.sort(key=lambda item:item["id"], reverse=True)
        return [item["content"]|{"memory_id":item["id"],"confidence":item["confidence"]} for item in contexts[:limit]]
