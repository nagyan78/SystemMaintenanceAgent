from langgraph.types import Command

from backend.app.agents.graph import (
    build_taxonomy_graph,
    create_initial_state,
    create_memory_checkpointer,
)


def test_graph_runs_to_human_review_interrupt_with_memory_saver():
    checkpointer = create_memory_checkpointer()
    graph = build_taxonomy_graph(checkpointer)
    state = create_initial_state(
        file_id=1,
        task_id="task_demo",
        workflow_id="workflow_demo",
    )
    config = {"configurable": {"thread_id": state.thread_id}}

    result = graph.invoke(state, config=config)

    assert "__interrupt__" in result
    interrupt = result["__interrupt__"][0]
    assert interrupt.value["type"] == "human_review"
    assert interrupt.value["review_batch_id"] == "review_workflow_demo"
    assert interrupt.value["suggestion_count"] == 3


def test_graph_resumes_from_human_review_and_completes():
    checkpointer = create_memory_checkpointer()
    graph = build_taxonomy_graph(checkpointer)
    state = create_initial_state(
        file_id=1,
        task_id="task_demo",
        workflow_id="workflow_demo",
    )
    config = {"configurable": {"thread_id": state.thread_id}}
    graph.invoke(state, config=config)

    result = graph.invoke(
        Command(
            resume={
                "decision": "approve",
                "approved_suggestion_ids": [1, 2],
                "edited_suggestions": [],
            }
        ),
        config=config,
    )

    assert result["status"] == "completed"
    assert result["current_step"] == "completed"
    assert result["progress"] == 100
    assert result["approved_action_count"] == 2
    assert result["executed_action_count"] == 2
    assert result["report_path"].endswith("workflow_demo.md")
