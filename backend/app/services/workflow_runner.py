from typing import Any, Callable

from fastapi import BackgroundTasks

from backend.app.config import Settings
from backend.app.repositories.agent_run_repo import AgentRunRepository
from backend.app.repositories.task_repo import TaskRepository


class WorkflowRunner:
    """Small in-process command runner; durable work items hold recovery state."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def submit(self, background_tasks: BackgroundTasks, command: Callable[..., Any], *args: Any) -> None:
        background_tasks.add_task(command, *args)

    def cancel(self, task_id: str) -> dict[str, Any]:
        task_repo = TaskRepository(self.settings)
        task = task_repo.get_task(task_id)
        if task is None:
            raise ValueError("Task not found.")
        AgentRunRepository(self.settings).cancel_workflow(str(task.get("workflow_id") or task_id))
        task_repo.update_task(task_id=task_id, status="cancelled", current_step="cancelled")
        return {"task_id": task_id, "status": "cancelled"}

    def recover_expired(self) -> int:
        return AgentRunRepository(self.settings).recover_expired_work()
