"""EduForge LabKit physics & circuit experiment subsystem for dsh-core.

Exposes the 6 `experiment_*` capabilities (`experiment_recipes`, `experiment_validate`,
`experiment_simulate`, `experiment_render`, `experiment_verify`, `experiment_build`)
and the `eduforge:labkit` system prompt section.
"""

from .bridge import LABKIT_SYSTEM_PROMPT_SECTION, RECIPES_CATALOG, LabKitBridge

__all__ = [
    "LabKitBridge",
    "RECIPES_CATALOG",
    "LABKIT_SYSTEM_PROMPT_SECTION",
]
