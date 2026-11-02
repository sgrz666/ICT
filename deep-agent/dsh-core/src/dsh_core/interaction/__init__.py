"""User interaction, approval, and deliverable subsystem for dsh-core.

Provides permission presets and user approval gates (`@deepseek-ai/dsh-user-approval`,
`@deepseek-ai/dsh-permission-presets`), structured user questions
(`@deepseek-ai/dsh-user-questions`, `@deepseek-ai/dsh-tool-ask-user`),
and workspace deliverable presentation & turn change tracking
(`@deepseek-ai/dsh-tool-present`, `@deepseek-ai/dsh-workspace-changes`).
"""

from .approval import (
    DEFAULT_PERMISSION_PRESETS,
    ApprovalDeniedError,
    ApprovalManager,
    ApprovalPolicy,
    PermissionPreset,
    PresetName,
)
from .deliverables import (
    DeliverableItem,
    DeliverableManager,
    TurnWorkspaceChanges,
    WorkspaceChangeTracker,
)
from .questions import UserQuestion, UserQuestionManager, UserQuestionResponse

__all__ = [
    "ApprovalPolicy",
    "PresetName",
    "PermissionPreset",
    "DEFAULT_PERMISSION_PRESETS",
    "ApprovalDeniedError",
    "ApprovalManager",
    "UserQuestion",
    "UserQuestionResponse",
    "UserQuestionManager",
    "DeliverableItem",
    "DeliverableManager",
    "TurnWorkspaceChanges",
    "WorkspaceChangeTracker",
]
