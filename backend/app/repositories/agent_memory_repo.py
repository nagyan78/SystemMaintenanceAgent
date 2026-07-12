import json
from backend.app.config import Settings
from backend.app.db import connect

class AgentMemoryRepository:
    def __init__(self, settings: Settings): self.settings=settings
    def create(self, *, memory_type, scope_type, scope_key, content, source_workflow_id=None, source_version_id=None, valid_from_version_id=None, valid_until_version_id=None, confidence=1.0):
        with connect(self.settings) as c:
            cur=c.execute("INSERT INTO agent_memory(memory_type,scope_type,scope_key,content,source_workflow_id,source_version_id,valid_from_version_id,valid_until_version_id,confidence) VALUES(?,?,?,?,?,?,?,?,?)", (memory_type,scope_type,scope_key,json.dumps(content,ensure_ascii=False),source_workflow_id,source_version_id,valid_from_version_id,valid_until_version_id,confidence))
            return int(cur.lastrowid)
    def list_for_scope(self, scope_key, version_id, limit=10):
        with connect(self.settings) as c:
            rows=c.execute("SELECT * FROM agent_memory WHERE scope_key=? AND (valid_from_version_id IS NULL OR valid_from_version_id<=?) AND (valid_until_version_id IS NULL OR valid_until_version_id>=?) ORDER BY id DESC LIMIT ?", (scope_key,version_id,version_id,limit)).fetchall()
        result=[]
        for row in rows:
            item=dict(row); item["content"]=json.loads(item["content"]); result.append(item)
        return result
