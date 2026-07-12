import json
from datetime import datetime, timedelta, timezone
from backend.app.config import Settings
from backend.app.db import connect

class ToolCacheRepository:
    def __init__(self, settings: Settings): self.settings = settings
    def get(self, workflow_id, version_id, tool_name, args_hash, data_revision):
        with connect(self.settings) as c:
            row = c.execute("SELECT id,result_json,expires_time FROM tool_cache WHERE workflow_id=? AND version_id IS ? AND tool_name=? AND args_hash=? AND data_revision=?", (workflow_id,version_id,tool_name,args_hash,data_revision)).fetchone()
            if not row or datetime.fromisoformat(row["expires_time"]) <= datetime.now(timezone.utc): return None
            c.execute("UPDATE tool_cache SET hit_count=hit_count+1 WHERE id=?", (row["id"],))
            return json.loads(row["result_json"])
    def put(self, workflow_id, version_id, tool_name, args_hash, data_revision, result, ttl):
        expires=(datetime.now(timezone.utc)+timedelta(seconds=ttl)).isoformat()
        with connect(self.settings) as c:
            c.execute("INSERT OR REPLACE INTO tool_cache(workflow_id,version_id,tool_name,args_hash,data_revision,result_json,expires_time) VALUES(?,?,?,?,?,?,?)", (workflow_id,version_id,tool_name,args_hash,data_revision,json.dumps(result,ensure_ascii=False,default=str),expires))
