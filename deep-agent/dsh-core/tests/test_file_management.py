"""Tier 1 and Tier 2 tests for dsh_core.file subsystem.

Covers FileManager, StrReplaceEditor, Diff generator, WorkspaceSearcher,
path containment security, and edge/boundary conditions.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
import pytest

from dsh_core.file import (
    FileManager,
    FsAmbiguousEditError,
    FsEditNotFoundError,
    FsNotFoundError,
    FsSandboxDeniedError,
    StrReplaceEditor,
    WorkspaceSearcher,
    assert_path_contained,
    format_diff_card,
    generate_context_diff,
    is_path_contained,
)


# ==============================================================================
# Tier 1: Core Feature Tests (FileManager)
# ==============================================================================


def test_read_file_full_and_windowed(file_manager: FileManager):
    """Test reading text files with full content and line-windowing options."""
    # Read full file
    content, total_lines = file_manager.read_text("hello.txt", offset=1, limit=None, with_line_numbers=True)
    assert total_lines == 5
    assert "1: Line 1: Alpha" in content
    assert "5: Line 5: Epsilon" in content

    # Read window: offset=2, limit=2
    window, total = file_manager.read_text("hello.txt", offset=2, limit=2, with_line_numbers=True)
    assert total == 5
    assert "2: Line 2: Beta" in window
    assert "3: Line 3: Gamma" in window
    assert "1: Line 1: Alpha" not in window
    assert "4: Line 4: Delta" not in window

    # Read without line numbers
    raw_window, total = file_manager.read_text("hello.txt", offset=2, limit=2, with_line_numbers=False)
    assert total == 5
    assert raw_window.startswith("Line 2: Beta")
    assert not raw_window.startswith("2: ")


def test_read_file_offset_beyond_total(file_manager: FileManager):
    """Test reading with offset past the total line count returns empty content."""
    content, total = file_manager.read_text("hello.txt", offset=100, limit=10)
    assert total == 5
    assert content == ""


def test_write_text_atomic_and_direct(file_manager: FileManager, temp_workspace: Path):
    """Test atomic writing and direct writing, including nested directory creation."""
    target_rel = "nested/deep/created.txt"
    payload = "Automated generated content: line A\nline B\n"

    # Write atomic
    bytes_written = file_manager.write_text(target_rel, payload, atomic=True)
    assert bytes_written == len(payload.encode("utf-8"))

    # Verify physical file existence
    physical_path = temp_workspace / "nested" / "deep" / "created.txt"
    assert physical_path.is_file()
    assert physical_path.read_text(encoding="utf-8") == payload

    # Overwrite non-atomic
    new_payload = "Overwritten line C\n"
    file_manager.write_text(target_rel, new_payload, atomic=False)
    assert physical_path.read_text(encoding="utf-8") == new_payload


def test_list_dir_flat_and_recursive(file_manager: FileManager):
    """Test directory listing in both flat and recursive modes."""
    # Flat listing
    flat_items = file_manager.list_dir(".", recursive=False)
    item_names = {item["name"] for item in flat_items}
    assert "hello.txt" in item_names
    assert "sample_code.py" in item_names
    assert "src_sub" in item_names

    # Recursive listing
    rec_items = file_manager.list_dir(".", recursive=True)
    rec_paths = {item["path"] for item in rec_items}
    assert "hello.txt" in rec_paths
    assert "src_sub/nested.txt" in rec_paths


def test_delete_file(file_manager: FileManager, temp_workspace: Path):
    """Test deleting an existing file and attempting to delete non-existent file."""
    del_target = temp_workspace / "to_delete.txt"
    del_target.write_text("temporary", encoding="utf-8")
    assert del_target.exists()

    # Delete existing
    res = file_manager.delete_file("to_delete.txt")
    assert res is True
    assert not del_target.exists()

    # Delete non-existent
    res_fake = file_manager.delete_file("does_not_exist_xyz.txt")
    assert res_fake is False


# ==============================================================================
# Tier 1: Core Feature Tests (StrReplaceEditor & Diff)
# ==============================================================================


def test_str_replace_exact_single():
    """Test single exact occurrence replacement."""
    original = "a = 10\nb = 20\nc = a + b\n"
    modified = StrReplaceEditor.replace_exact(original, old_str="b = 20", new_str="b = 50", replace_all=False)
    assert modified == "a = 10\nb = 50\nc = a + b\n"


def test_str_replace_all_occurrences():
    """Test replacing all occurrences when replace_all is enabled."""
    original = "foo bar foo baz foo\n"
    modified = StrReplaceEditor.replace_exact(original, old_str="foo", new_str="qux", replace_all=True)
    assert modified == "qux bar qux baz qux\n"


def test_contextual_diff_generation():
    """Test generation of 3-line unified diff cards."""
    before = "line 1\nline 2\nline 3\nline 4\nline 5\n"
    after = "line 1\nline 2\nline 3 MODIFIED\nline 4\nline 5\n"

    diff_str = generate_context_diff(before, after, filename="test.txt", context_lines=3)
    assert "--- a/test.txt" in diff_str
    assert "+++ b/test.txt" in diff_str
    assert "+line 3 MODIFIED" in diff_str
    assert "-line 3" in diff_str

    # Formatted card
    card = format_diff_card(diff_str, filename="test.txt")
    assert card.startswith("```diff\n# test.txt")
    assert card.endswith("```")

    # Identical content yields empty diff
    empty_diff = generate_context_diff(before, before, filename="test.txt")
    assert empty_diff == ""
    assert "No changes in test.txt" in format_diff_card(empty_diff, "test.txt")


def test_file_manager_edit_text_with_diff(file_manager: FileManager, temp_workspace: Path):
    """Test high-level edit_text method on FileManager returning diff and updating disk."""
    new_content, diff = file_manager.edit_text(
        "hello.txt",
        old_str="Line 3: Gamma",
        new_str="Line 3: Gamma (Updated)",
    )
    assert "Line 3: Gamma (Updated)" in new_content
    assert "+Line 3: Gamma (Updated)" in diff

    # Verify disk reflects update
    disk_content = (temp_workspace / "hello.txt").read_text(encoding="utf-8")
    assert "Line 3: Gamma (Updated)" in disk_content


# ==============================================================================
# Tier 1: Core Feature Tests (WorkspaceSearcher)
# ==============================================================================


def test_workspace_searcher_grep(temp_workspace: Path):
    """Test grep literal and regex searching across workspace files."""
    searcher = WorkspaceSearcher(temp_workspace)

    # Literal search
    hits = searcher.grep("Beta", path=".")
    assert len(hits) == 1
    assert hits[0]["file"] == "hello.txt"
    assert hits[0]["line_number"] == 2
    assert "Beta" in str(hits[0]["line"])

    # Regex search
    hits_regex = searcher.grep(r"calculate_\w+", path=".", is_regex=True)
    assert len(hits_regex) >= 1
    assert hits_regex[0]["file"] == "sample_code.py"

    # Case-insensitive
    hits_ci = searcher.grep("beta", path=".", case_insensitive=True)
    assert len(hits_ci) == 1


def test_workspace_searcher_glob(temp_workspace: Path):
    """Test glob pattern matching within workspace."""
    searcher = WorkspaceSearcher(temp_workspace)

    py_files = searcher.glob("*.py")
    assert "sample_code.py" in py_files

    all_txt = searcher.glob("**/*.txt")
    assert "hello.txt" in all_txt
    assert "src_sub/nested.txt" in all_txt


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Path Containment & Robustness)
# ==============================================================================


def test_path_containment_parent_escape(temp_workspace: Path):
    """Test that relative traversal attempting to escape workspace root is blocked."""
    escape_path = temp_workspace / ".." / "unauthorized.txt"
    assert not is_path_contained(escape_path, temp_workspace)

    with pytest.raises(FsSandboxDeniedError) as exc_info:
        assert_path_contained(escape_path, temp_workspace)
    assert "Path escape denied" in str(exc_info.value)


def test_path_containment_absolute_escape(temp_workspace: Path):
    """Test that absolute paths outside workspace root are blocked."""
    abs_escape = Path("C:/Windows/System32/drivers/etc/hosts") if Path("C:/Windows").exists() else Path("/etc/passwd")
    assert not is_path_contained(abs_escape, temp_workspace)

    with pytest.raises(FsSandboxDeniedError):
        assert_path_contained(abs_escape, temp_workspace)


def test_read_nonexistent_file_raises(file_manager: FileManager):
    """Test reading a non-existent file raises FsNotFoundError."""
    with pytest.raises(FsNotFoundError):
        file_manager.read_text("non_existent_file_12345.txt")


def test_edit_nonexistent_file_raises(file_manager: FileManager):
    """Test editing a non-existent file raises FsNotFoundError."""
    with pytest.raises(FsNotFoundError):
        file_manager.edit_text("ghost.txt", old_str="a", new_str="b")


def test_str_replace_ambiguous_error():
    """Test that attempting to replace a non-unique string with replace_all=False raises FsAmbiguousEditError."""
    content = "item = 1\nitem = 2\nitem = 3\n"
    with pytest.raises(FsAmbiguousEditError) as exc_info:
        StrReplaceEditor.replace_exact(content, old_str="item = ", new_str="val = ", replace_all=False)
    assert "occurs 3 times" in str(exc_info.value)


def test_str_replace_not_found_error():
    """Test that searching for a string that does not exist raises FsEditNotFoundError."""
    content = "first line\nsecond line\n"
    with pytest.raises(FsEditNotFoundError):
        StrReplaceEditor.replace_exact(content, old_str="third line", new_str="replacement")


def test_str_replace_empty_target_raises():
    """Test that passing an empty string as old_str raises ValueError."""
    with pytest.raises(ValueError, match="old_str cannot be empty"):
        StrReplaceEditor.replace_exact("content", old_str="", new_str="anything")


def test_empty_file_handling(file_manager: FileManager, temp_workspace: Path):
    """Test reading and writing empty (0-byte) files."""
    empty_file = "empty.txt"
    file_manager.write_text(empty_file, "", atomic=True)

    phys = temp_workspace / empty_file
    assert phys.exists()
    assert phys.stat().st_size == 0

    content, lines = file_manager.read_text(empty_file)
    assert content == ""
    assert lines == 0


def test_unicode_and_crlf_preservation(file_manager: FileManager, temp_workspace: Path):
    """Test handling of multi-byte UTF-8 Unicode and CRLF line terminators."""
    unicode_content = "一二三四五\n光学仿真凸透镜实验\n🔬💡⚡\r\nCRLF_Line\r\n"
    file_manager.write_text("unicode_test.txt", unicode_content, atomic=True)

    read_back, total = file_manager.read_text("unicode_test.txt", with_line_numbers=False)
    assert read_back == unicode_content
    assert total == 4


def test_concurrent_writes_file_lock(file_manager: FileManager, temp_workspace: Path):
    """Test that concurrent writes to the same file are properly serialized without corrupting data."""
    target_file = "concurrent.txt"
    file_manager.write_text(target_file, "0\n", atomic=True)

    def write_worker(idx: int):
        payload = f"worker_{idx}_content\n"
        file_manager.write_text(target_file, payload, atomic=True)
        return idx

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(write_worker, i) for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(results) == 10
    final_content, _ = file_manager.read_text(target_file, with_line_numbers=False)
    assert final_content.startswith("worker_")
