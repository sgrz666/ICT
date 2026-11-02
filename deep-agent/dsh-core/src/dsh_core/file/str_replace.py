"""String replacement editor module.

Implements the official str_replace_editor contract from DeepSeek Harness:
exact literal substring replacement with uniqueness validation. If the target
string appears more than once and replace_all is False, an ambiguous edit error
is raised to prevent unintended edits.
"""

from __future__ import annotations

from .containment import FsAmbiguousEditError, FsEditNotFoundError


class StrReplaceEditor:
    """Exact substring replacement editor."""

    @staticmethod
    def replace_exact(
        content: str,
        old_str: str,
        new_str: str,
        replace_all: bool = False,
    ) -> str:
        """Perform exact substring replacement on content.

        Args:
            content: The original document content.
            old_str: The exact literal substring to find and replace.
            new_str: The replacement string.
            replace_all: If True, replace all occurrences. If False, require
                exactly one occurrence or raise FsAmbiguousEditError.

        Returns:
            The modified content.

        Raises:
            FsEditNotFoundError: If old_str does not occur in content.
            FsAmbiguousEditError: If replace_all is False and old_str occurs > 1 times.
        """
        if not old_str:
            raise ValueError("old_str cannot be empty")

        count = content.count(old_str)
        if count == 0:
            raise FsEditNotFoundError(
                f"Target string not found in content: {old_str!r}"
            )

        if not replace_all and count > 1:
            raise FsAmbiguousEditError(
                f"Ambiguous edit: target string occurs {count} times in content. "
                "Provide a larger unique context chunk or set replace_all=True."
            )

        if replace_all:
            return content.replace(old_str, new_str)

        # Single exact replacement
        return content.replace(old_str, new_str, 1)

    @staticmethod
    def validate_unique(content: str, target: str) -> tuple[bool, int]:
        """Check if target substring occurs uniquely in content.

        Returns:
            (is_unique, count)
        """
        count = content.count(target)
        return (count == 1, count)
