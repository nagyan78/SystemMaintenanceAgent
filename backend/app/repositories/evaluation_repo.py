import json
from backend.app.config import Settings
from backend.app.db import connect
from backend.app.schemas.evaluation import AgentEvaluationResult

class EvaluationRepository:
    def __init__(self, settings: Settings): self.settings=settings
    def create(self, result: AgentEvaluationResult, bundle_version="candidate"):
        with connect(self.settings) as c:
            cur=c.execute("INSERT INTO agent_evaluation(dataset_version,workflow_id,metrics,agent_bundle_version) VALUES(?,?,?,?)",(result.dataset_version,result.workflow_id,result.model_dump_json(),bundle_version)); return int(cur.lastrowid)
    def get(self, evaluation_id):
        with connect(self.settings) as c: row=c.execute("SELECT * FROM agent_evaluation WHERE id=?",(evaluation_id,)).fetchone()
        if not row:return None
        item=dict(row); item["metrics"]=json.loads(item["metrics"]); return item
    def list(self):
        with connect(self.settings) as c: rows=c.execute("SELECT * FROM agent_evaluation ORDER BY id DESC").fetchall()
        return [{**dict(row),"metrics":json.loads(row["metrics"])} for row in rows]
    def promote(self,evaluation_id,dataset_version,bundle,operator):
        baseline_id=f"{dataset_version}-{evaluation_id}"
        with connect(self.settings) as c:
            c.execute("DELETE FROM evaluation_baseline WHERE dataset_version=?",(dataset_version,)); c.execute("INSERT INTO evaluation_baseline(baseline_id,dataset_version,evaluation_id,agent_bundle_version,approved_by) VALUES(?,?,?,?,?)",(baseline_id,dataset_version,evaluation_id,bundle,operator))
        return baseline_id
    def baseline(self,dataset_version):
        with connect(self.settings) as c: row=c.execute("SELECT * FROM evaluation_baseline WHERE dataset_version=? AND pinned=1",(dataset_version,)).fetchone()
        return dict(row) if row else None
