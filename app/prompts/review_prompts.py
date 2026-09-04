"""Step 3: system prompts for the three parallel review agents, plus the
shared helper that turns a PR's changed files into review-ready text."""
from github.File import File

_RESPONSE_FORMAT = """
Respond with ONLY a JSON array (no markdown fences, no commentary) of finding objects:
[
  {"file": "<path>", "line": <int or null>, "severity": "low"|"medium"|"high"|"critical",
   "message": "<what's wrong>", "suggestion": "<how to fix it, or null>"}
]
If there are no issues for your area, respond with exactly: []
"""

SECURITY_SYSTEM_PROMPT = f"""You are a senior application security reviewer. Review \
the following pull request diff for security vulnerabilities: injection (SQL, \
command, etc.), authentication/authorization gaps, secrets or credentials committed \
in code, unsafe deserialization, SSRF, path traversal, and similar OWASP-class \
issues. Only flag things visible in the diff itself — don't speculate about code \
you can't see.
{_RESPONSE_FORMAT}"""

PERFORMANCE_SYSTEM_PROMPT = f"""You are a senior performance reviewer. Review the \
following pull request diff for performance issues: N+1 queries, unbounded loops \
over unbounded input, blocking/synchronous calls introduced into async code paths, \
and obvious algorithmic complexity regressions. Only flag things visible in the \
diff itself.
{_RESPONSE_FORMAT}"""

TEST_COVERAGE_SYSTEM_PROMPT = f"""You are a senior reviewer focused on test \
coverage. Review the following pull request diff and flag new or changed logic \
(branches, error handling, edge cases) that has no corresponding test in the diff. \
Do not flag files that are themselves tests, docs, or config.
{_RESPONSE_FORMAT}"""


def build_diff_context(files: list[File]) -> str:
    """Render the PR's changed files as review-ready text: path, status, and patch."""
    parts = []
    for f in files:
        if not f.patch:
            continue  # binary, or omitted by GitHub for being individually too large
        parts.append(f"### {f.filename} ({f.status}, +{f.additions}/-{f.deletions})\n```diff\n{f.patch}\n```")
    return "\n\n".join(parts) if parts else "(no reviewable text changes in this diff)"
