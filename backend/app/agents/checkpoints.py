"""SQLite-backed LangGraph checkpointer (M4 requirement).

M1-M3 used an in-memory checkpointer (`InMemorySaver`), which is lost on
process restart and therefore cannot satisfy M4 §7.9 ("服务重启后同 thread_id
可恢复"). This module provides a file-persistent `SqliteSaver` so a workflow
paused at `human_review` can be resumed from the SAME thread_id after the
server restarts.
"""

from __future__ import annotations

import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver


def default_checkpoint_path() -> str:
    """Resolve the checkpoint database path.

    Honours ``WORKFLOW_CHECKPOINT_DB`` (useful for tests / isolated runs),
    otherwise falls back to ``data/workflow_checkpoints.sqlite`` relative to
    the current working directory (project root when running uvicorn).
    """
    env = os.environ.get("WORKFLOW_CHECKPOINT_DB")
    if env:
        return env
    return os.path.join("data", "workflow_checkpoints.sqlite")


_HOLDERS: dict[str, SqliteSaver] = {}


def create_sqlite_checkpointer(db_path: str | None = None) -> SqliteSaver:
    """Return a process-wide SQLite-backed LangGraph checkpointer.

    The underlying ``sqlite3`` connection is opened once and kept alive for the
    process lifetime, so the same ``thread_id`` can be resumed later (even
    across restarts, since the data lives in a file).
    """
    path = os.path.abspath(db_path or default_checkpoint_path())
    cached = _HOLDERS.get(path)
    if cached is not None:
        return cached

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    _HOLDERS[path] = saver
    return saver
