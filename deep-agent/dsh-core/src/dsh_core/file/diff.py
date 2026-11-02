"""Contextual unified diff generator module.

Produces standard unified diffs with configurable context lines (default 3 lines),
matching the upstream diff presentation contract for model observation.
"""

from __future__ import annotations

import difflib


def generate_context_diff(
    before: str,
    after: str,
    filename: str = "file",
    context_lines: int = 3,
) -> str:
    """Generate a standard unified diff between before and after text.

    Args:
        before: Original file content.
        after: New file content.
        filename: Relative display filename.
        context_lines: Number of surrounding context lines to retain (default 3).

    Returns:
        Unified diff string. Empty string if no changes.
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)

    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context_lines,
        )
    )

    return "".join(diff_lines)


def format_diff_card(diff_text: str, filename: str = "file") -> str:
    """Format a unified diff as a Markdown code block card.

    Args:
        diff_text: Raw diff text.
        filename: Target filename.

    Returns:
        Markdown formatted string.
    """
    if not diff_text.strip():
        return f"No changes in {filename}."

    return f"```diff\n# {filename}\n{diff_text.strip()}\n```"
