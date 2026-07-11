"""Compatibility exports for tree tools.

Agent workers must create tools through ``AgentToolFactory`` so runtime
settings are instance-scoped. This module intentionally holds no mutable
runtime configuration.
"""

from backend.app.services.tool_factory import AgentToolFactory, ToolScope

__all__ = ["AgentToolFactory", "ToolScope"]
