from backend.app.config import Settings
from backend.app.db import connect

class TriageRepository:
    def __init__(self, settings: Settings): self.settings=settings
    def create(self, *, workflow_id, version_id, issue):
        with connect(self.settings) as c:
            cur=c.execute("""INSERT INTO diagnosis_triage(workflow_id,version_id,node_id,node_name,issue_type,reason,evidence,confidence,detector_disagreement)
                VALUES(?,?,?,?,?,?,?,?,?)""",(workflow_id,version_id,issue.get("node_id"),issue.get("node_name"),issue["issue_type"],issue.get("reason"),issue.get("evidence"),float(issue.get("confidence",0)),int(bool(issue.get("detector_disagreement"))))); return int(cur.lastrowid)
    def list(self, workflow_id=None, status="needs_triage"):
        clauses=["status=?"]; params=[status]
        if workflow_id: clauses.append("workflow_id=?"); params.append(workflow_id)
        with connect(self.settings) as c: rows=c.execute(f"SELECT * FROM diagnosis_triage WHERE {' AND '.join(clauses)} ORDER BY id",params).fetchall()
        return [dict(row) for row in rows]
    def decide(self, triage_id, decision, operator):
        with connect(self.settings) as c:
            row=c.execute("SELECT * FROM diagnosis_triage WHERE id=? AND status='needs_triage'",(triage_id,)).fetchone()
            if not row: raise ValueError("triage item not found or already decided")
            c.execute("UPDATE diagnosis_triage SET status='decided',decision=?,operator=?,decided_time=CURRENT_TIMESTAMP WHERE id=?",(decision,operator,triage_id))
            return dict(row)
