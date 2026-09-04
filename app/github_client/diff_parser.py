"""
Step 2: turns a single file's unified-diff patch (as returned by GitHub's
`files` API — just the hunk bodies, no `diff --git`/`---`/`+++` headers)
into structured, line-addressable hunks for the Step 3 review agents.
"""
import re
from dataclasses import dataclass, field

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@"
)


@dataclass
class DiffLine:
    type: str  # "add" | "remove" | "context"
    content: str
    old_lineno: int | None
    new_lineno: int | None


@dataclass
class Hunk:
    header: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[DiffLine] = field(default_factory=list)


def parse_patch(patch: str) -> list[Hunk]:
    """Parse one file's `.patch` text (from PyGithub's File object) into hunks."""
    hunks: list[Hunk] = []
    current: Hunk | None = None
    old_lineno = new_lineno = 0

    for line in patch.splitlines():
        match = _HUNK_HEADER_RE.match(line)
        if match:
            old_start = int(match.group("old_start"))
            new_start = int(match.group("new_start"))
            current = Hunk(
                header=line,
                old_start=old_start,
                old_lines=int(match.group("old_lines") or "1"),
                new_start=new_start,
                new_lines=int(match.group("new_lines") or "1"),
            )
            hunks.append(current)
            old_lineno, new_lineno = old_start, new_start
            continue

        if current is None or not line:
            continue

        marker, content = line[0], line[1:]
        if marker == "+":
            current.lines.append(DiffLine("add", content, None, new_lineno))
            new_lineno += 1
        elif marker == "-":
            current.lines.append(DiffLine("remove", content, old_lineno, None))
            old_lineno += 1
        elif marker == " ":
            current.lines.append(DiffLine("context", content, old_lineno, new_lineno))
            old_lineno += 1
            new_lineno += 1
        # else: "\ No newline at end of file" or similar — not a code line, skip.

    return hunks
