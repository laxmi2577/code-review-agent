import re
from pathlib import Path
from typing import Optional

from git import Repo

from src.models.enums import ChangeType, Language
from src.models.schemas import DiffHunk, FunctionNode

EXTENSION_LANGUAGE_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".go": Language.GO,
    ".java": Language.JAVA,
    ".rs": Language.RUST,
}

HUNK_HEADER_REGEX = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: ?(.*))?$"
)


def detect_language(file_path: str) -> Optional[Language]:
    """Detect Language enum from file extension."""
    suffix = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(suffix)


def parse_unified_diff(diff_text: str) -> list[DiffHunk]:
    """Parse git unified diff string into a list of DiffHunk objects."""
    hunks: list[DiffHunk] = []
    lines = diff_text.splitlines()

    current_file_path: Optional[str] = None
    file_change_type: Optional[ChangeType] = None
    current_hunk_header = None
    current_hunk_lines: list[str] = []

    def flush_hunk():
        nonlocal current_hunk_header, current_hunk_lines
        if not current_hunk_header or not current_file_path:
            return

        lang = detect_language(current_file_path)
        if not lang:
            current_hunk_header = None
            current_hunk_lines = []
            return

        old_start, old_count, new_start, new_count = current_hunk_header
        new_end = new_start + max(new_count - 1, 0)
        hunk_content = "\n".join(current_hunk_lines)

        # Classify change type
        if file_change_type:
            c_type = file_change_type
        elif old_start == 0 and old_count == 0:
            c_type = ChangeType.ADDED
        elif new_start == 0 and new_count == 0:
            c_type = ChangeType.DELETED
        else:
            c_type = ChangeType.MODIFIED

        hunks.append(
            DiffHunk(
                file_path=current_file_path,
                language=lang,
                change_type=c_type,
                old_start=old_start,
                new_start=new_start,
                new_end=new_end,
                diff_content=hunk_content,
                affected_functions=[],
            )
        )
        current_hunk_header = None
        current_hunk_lines = []

    for line in lines:
        if line.startswith("diff --git "):
            flush_hunk()
            file_change_type = None
            # Extract path from 'diff --git a/path b/path'
            parts = line.split(" ")
            if len(parts) >= 4:
                b_path = parts[3]
                current_file_path = b_path[2:] if b_path.startswith("b/") else b_path
        elif line.startswith("new file mode "):
            file_change_type = ChangeType.ADDED
        elif line.startswith("deleted file mode "):
            file_change_type = ChangeType.DELETED
        elif line.startswith("--- "):
            if line.startswith("--- /dev/null"):
                file_change_type = ChangeType.ADDED
        elif line.startswith("+++ "):
            if line.startswith("+++ /dev/null"):
                file_change_type = ChangeType.DELETED
            elif not current_file_path:
                target = line[4:].strip()
                current_file_path = target[2:] if target.startswith("b/") else target
        elif line.startswith("@@ "):
            flush_hunk()
            match = HUNK_HEADER_REGEX.match(line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) is not None else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) is not None else 1
                current_hunk_header = (old_start, old_count, new_start, new_count)
                current_hunk_lines = [line]
        elif current_hunk_header is not None:
            current_hunk_lines.append(line)

    flush_hunk()
    return hunks


def extract_diff_from_repo(repo_path: str, base_sha: str, head_sha: str) -> list[DiffHunk]:
    """Extract and parse git diff between two SHAs using GitPython."""
    repo = Repo(repo_path)
    diff_text = repo.git.diff(f"{base_sha}..{head_sha}", unified=3)
    return parse_unified_diff(diff_text)


def map_diff_to_functions(
    hunks: list[DiffHunk],
    functions_by_file: dict[str, list[FunctionNode]],
) -> list[DiffHunk]:
    """Correlate diff hunk line ranges with AST FunctionNode boundaries.

    Populates hunk.affected_functions when line spans overlap.
    """
    for hunk in hunks:
        funcs = functions_by_file.get(hunk.file_path, [])
        affected: list[FunctionNode] = []
        for func in funcs:
            # Check overlap between [new_start, new_end] and [func.start_line, func.end_line]
            hunk_start = hunk.new_start
            hunk_end = max(hunk.new_end, hunk.new_start)

            if max(hunk_start, func.start_line) <= min(hunk_end, func.end_line):
                affected.append(func)

        hunk.affected_functions = affected

    return hunks
