"""File management subsystem for dsh-core.

Provides containment-safe file reads with line numbers, atomic writes, exact
string replacement editing, contextual diffs, and pure-Python grep/glob searches.
"""

from .containment import (
    FsAmbiguousEditError,
    FsEditNotFoundError,
    FsError,
    FsNotFoundError,
    FsSandboxDeniedError,
    assert_path_contained,
    is_path_contained,
)
from .diff import format_diff_card, generate_context_diff
from .manager import FileManager
from .observation import (
    FsNotObservedError,
    FsObservation,
    FsObservationPolicy,
    FsStaleFileError,
    FsVersion,
)
from .search import WorkspaceSearcher
from .str_replace import StrReplaceEditor

__all__ = [
    "FileManager",
    "FsObservationPolicy",
    "FsObservation",
    "FsVersion",
    "StrReplaceEditor",
    "WorkspaceSearcher",
    "assert_path_contained",
    "is_path_contained",
    "generate_context_diff",
    "format_diff_card",
    "FsError",
    "FsNotFoundError",
    "FsNotObservedError",
    "FsStaleFileError",
    "FsSandboxDeniedError",
    "FsAmbiguousEditError",
    "FsEditNotFoundError",
]
