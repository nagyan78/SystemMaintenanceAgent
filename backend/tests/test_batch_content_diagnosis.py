import json
import time

from langchain_core.messages import AIMessage

from backend.app.services.batch_content_diagnosis_service import BatchContentDiagnosisService


def _candidates(count: int) -> list[dict]:
    return [
        {
            "category_id": index,
            "category_name": f"节点{index}",
            "parent_id": 1,
            "level": 2,
            "path_names": f"产品 > 节点{index}",
            "syn_list": None,
            "is_leaf": 1,
        }
        for index in range(1, count + 1)
    ]


class BatchLLM:
    def __init__(self, *, invalid: bool = False):
        self.invalid = invalid
        self.batch_sizes: list[int] = []

    def invoke(self, messages):
        candidates = json.loads(messages[1].content)["candidates"]
        self.batch_sizes.append(len(candidates))
        if self.invalid:
            return AIMessage(content="not-json")
        assessments = [
            {
                "node_id": item["node_id"],
                "conclusion": "reasonable",
                "issue_type": None,
                "reason": "路径与名称一致",
                "evidence": item["path"],
                "risk_level": "low",
                "confidence": 0.9,
            }
            for item in candidates
        ]
        message = AIMessage(content=json.dumps({"assessments": assessments}, ensure_ascii=False))
        message.usage_metadata = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        return message


def test_batch_analysis_processes_fifty_candidates_in_five_calls():
    llm = BatchLLM()

    result = BatchContentDiagnosisService(llm).analyze(
        _candidates(50),
        deadline=time.monotonic() + 300,
        max_calls=10,
    )

    assert llm.batch_sizes == [10, 10, 10, 10, 10]
    assert result.model_calls == 5
    assert result.tokens_used == 750
    assert len(result.assessments) == 50
    assert {item.conclusion for item in result.assessments} == {"reasonable"}


def test_invalid_batch_retries_once_then_returns_uncertain():
    llm = BatchLLM(invalid=True)

    result = BatchContentDiagnosisService(llm).analyze(
        _candidates(10),
        deadline=time.monotonic() + 300,
        max_calls=10,
    )

    assert result.model_calls == 2
    assert llm.batch_sizes == [10, 10]
    assert {item.conclusion for item in result.assessments} == {"uncertain"}
    assert result.warning
