from backend.app.schemas.evaluation import AgentEvaluationResult

class EvaluationService:
    def evaluate(self, *, golden, predicted, suggestions=None, workflow_id="evaluation", dataset_version=None, unsafe_escaped=0, latencies=None, model_calls=0, tokens=0, cache_hits=0, cache_invocations=0):
        dataset_version=dataset_version or (golden[0].get("dataset_version") if golden else "runtime")
        truth={(int(i["node_id"]),i["issue_type"]) for i in golden}; guesses={(int(i["node_id"]),i["issue_type"]) for i in predicted}; tp=len(truth&guesses)
        precision=tp/max(len(guesses),1); recall=tp/max(len(truth),1); f1=2*precision*recall/max(precision+recall,1e-12)
        suggestions=suggestions or []; valid=sum(bool(i.get("schema_valid",True)) for i in suggestions); executable=sum(bool(i.get("executable",True)) for i in suggestions)
        latencies=sorted(latencies or []); p95=latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else 0
        return AgentEvaluationResult(dataset_version=dataset_version,workflow_id=workflow_id,detection_precision=round(precision,4),detection_recall=round(recall,4),detection_f1=round(f1,4),issue_type_accuracy=round(precision,4),action_schema_valid_rate=valid/max(len(suggestions),1),action_executable_rate=executable/max(len(suggestions),1),unsafe_action_escape_rate=unsafe_escaped/max(len(suggestions),1),p95_candidate_latency_ms=p95,model_calls=model_calls,tokens=tokens,cache_hit_rate=cache_hits/max(cache_invocations,1),triage_count=sum(1 for i in predicted if i.get("confidence",1)<.6 or i.get("inconclusive")),calibration_bins=_calibrate(truth,predicted))
    def release_gate(self,candidate,baseline=None):
        if baseline is None:return {"status":"baseline_missing","passed":False,"failures":["baseline_missing"]}
        failures=[]
        if candidate.unsafe_action_escape_rate!=0:failures.append("unsafe_action_escape_rate")
        if candidate.action_executable_rate<.95:failures.append("action_executable_rate")
        if (candidate.detection_f1 or 0)<(baseline.detection_f1 or 0):failures.append("detection_f1")
        return {"status":"pass" if not failures else "fail","passed":not failures,"failures":failures}

def _calibrate(truth,predicted):
    result=[]
    for low in (0,.2,.4,.6,.8):
        values=[i for i in predicted if low<=float(i.get("confidence",0))<=(1 if low==.8 else low+.2)]; correct=sum((int(i["node_id"]),i["issue_type"]) in truth for i in values)
        result.append({"lower":low,"upper":1 if low==.8 else low+.2,"count":len(values),"accuracy":correct/len(values) if values else None,"status":"ok" if len(values)>=5 else "insufficient_data"})
    return result
