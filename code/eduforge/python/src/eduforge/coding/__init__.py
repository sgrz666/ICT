"""EduForge 代码定制模块（Coding Layer）。

对齐方案 §1.2 和 §4.6，提供深度智能体沙箱执行与预算管理能力。
"""
from eduforge.coding.budget import ExecutionBudget
from eduforge.coding.deep_agent import EXPORT_PATHS, customize
from eduforge.coding.sandbox_factory import SandboxFactory
from eduforge.coding.workspace import WorkspaceManager

__all__ = [
    "ExecutionBudget",
    "customize",
    "EXPORT_PATHS",
    "SandboxFactory",
    "WorkspaceManager",
]
