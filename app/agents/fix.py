"""
Step 4: turns Step 3's findings into an actual patch and opens a second PR
with the fix applied — the auto-fix half of the pitch.

Only files that have at least one finding get rewritten; unrelated files
in the PR are left untouched. If there are no findings at all, this is a
no-op — there's nothing to fix.
"""
import logging

from anthropic import AsyncAnthropic
from github.File import File

from app.github_client.client import fetch_file_content, open_fix_pr
from app.prompts.fix_prompts import FIX_SYSTEM_PROMPT, build_fix_user_message

logger = logging.getLogger("agents.fix")


def _findings_by_file(review_results: dict) -> dict[str, list[dict]]:
    by_file: dict[str, list[dict]] = {}
    for findings in review_results.values():
        for finding in findings:
            by_file.setdefault(finding["file"], []).append(finding)
    return by_file


def _strip_code_fence(text: str) -> str:
    """Defensive cleanup in case Claude wraps the file in a ```fence despite
    being told not to — the instruction isn't always followed exactly."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def _build_pr_body(pr_number: int, pr_title: str, findings_by_file: dict[str, list[dict]]) -> str:
    lines = [f"Automated fix for issues found while reviewing #{pr_number} ({pr_title}).", ""]
    for path, findings in findings_by_file.items():
        lines.append(f"### {path}")
        lines.extend(f"- **{f['severity']}**: {f['message']}" for f in findings)
        lines.append("")
    return "\n".join(lines)


async def run_fix_agent(
    *,
    repo: str,
    pr_number: int,
    pr_title: str,
    head_sha: str,
    head_ref: str,
    files: list[File],
    review_results: dict,
    token: str,
    model: str,
) -> str | None:
    """Generate fixes for every file with findings and open a PR with them.
    Returns the fix PR's URL, or None if there was nothing to fix."""
    findings_by_file = _findings_by_file(review_results)
    if not findings_by_file:
        return None

    diffed_filenames = {f.filename for f in files}
    file_updates: list[tuple[str, str, str]] = []

    async with AsyncAnthropic() as client:
        for path, findings in findings_by_file.items():
            if path not in diffed_filenames:
                continue  # defensive: a hallucinated file path shouldn't blow up the run
            original_content, blob_sha = await fetch_file_content(repo, path, head_sha, token)
            response = await client.messages.create(
                model=model,
                max_tokens=8192,
                system=FIX_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": build_fix_user_message(path, original_content, findings)}],
            )
            new_content = _strip_code_fence(response.content[0].text)
            file_updates.append((path, new_content, blob_sha))

    if not file_updates:
        return None

    branch_name = f"bot/fix-pr-{pr_number}-{head_sha[:7]}"
    return await open_fix_pr(
        repo=repo,
        token=token,
        base_head_sha=head_sha,
        base_head_ref=head_ref,
        branch_name=branch_name,
        file_updates=file_updates,
        pr_title=f"Fix: {pr_title} (automated)",
        pr_body=_build_pr_body(pr_number, pr_title, findings_by_file),
    )
