"""
Step 2: fetches a PR's changed files from the GitHub API.
Step 4: fetches a file's current content and opens the fix PR.

Uses PyGithub (already a dependency) rather than hand-rolling HTTP calls —
`PullRequest.get_files()` already gives per-file unified-diff patches,
rename tracking, and add/delete counts, so there's no need to parse a raw
diff blob ourselves.

PyGithub is synchronous, so the actual network calls run in a worker
thread (via asyncio.to_thread) to avoid blocking the event loop that also
serves /health and /dashboard while a review run is in flight.
"""
import asyncio

from github import Auth, Github
from github.File import File
from github.GithubException import GithubException


class GitHubClientError(Exception):
    """Base class for GitHub client failures."""


class GitHubAPIError(GitHubClientError):
    """The GitHub API rejected the request (bad auth, missing PR, rate limit, ...)."""

    def __init__(self, status: int | None, message: str):
        self.status = status
        super().__init__(f"GitHub API error{f' {status}' if status else ''}: {message}")


class DiffTooLargeError(GitHubClientError):
    """The PR's combined diff exceeds the configured size limit."""

    def __init__(self, size_bytes: int, max_bytes: int):
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(f"diff is {size_bytes} bytes, over the {max_bytes}-byte limit")


def _fetch_files_sync(repo: str, pr_number: int, token: str) -> list[File]:
    try:
        gh = Github(auth=Auth.Token(token))
        pr = gh.get_repo(repo).get_pull(pr_number)
        return list(pr.get_files())
    except GithubException as exc:
        raise GitHubAPIError(exc.status, str(exc.data)) from exc


async def fetch_pr_files(repo: str, pr_number: int, token: str, max_bytes: int) -> list[File]:
    """
    Fetch the PR's changed files, each carrying a `.patch` unified-diff
    snippet for that file (None for binary files or ones GitHub omits for
    being too large on its own).

    Raises DiffTooLargeError if the combined patch size exceeds max_bytes
    — cheaper to bail here than to hand a huge diff to Claude later.
    """
    files = await asyncio.to_thread(_fetch_files_sync, repo, pr_number, token)
    total_bytes = sum(len(f.patch or "") for f in files)
    if total_bytes > max_bytes:
        raise DiffTooLargeError(total_bytes, max_bytes)
    return files


def _fetch_file_content_sync(repo: str, token: str, path: str, ref: str) -> tuple[str, str]:
    try:
        gh = Github(auth=Auth.Token(token))
        content_file = gh.get_repo(repo).get_contents(path, ref=ref)
        return content_file.decoded_content.decode("utf-8"), content_file.sha
    except GithubException as exc:
        raise GitHubAPIError(exc.status, str(exc.data)) from exc


async def fetch_file_content(repo: str, path: str, ref: str, token: str) -> tuple[str, str]:
    """Fetch a file's current text content and blob sha at `ref` — the sha is
    required by `update_file` to prove we're editing the version we read."""
    return await asyncio.to_thread(_fetch_file_content_sync, repo, token, path, ref)


def _open_fix_pr_sync(
    repo: str,
    token: str,
    base_head_sha: str,
    base_head_ref: str,
    branch_name: str,
    file_updates: list[tuple[str, str, str]],
    pr_title: str,
    pr_body: str,
) -> str:
    try:
        gh_repo = Github(auth=Auth.Token(token)).get_repo(repo)
        gh_repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base_head_sha)
        for path, new_content, blob_sha in file_updates:
            gh_repo.update_file(
                path=path,
                message=f"fix: automated review fix for {path}",
                content=new_content,
                sha=blob_sha,
                branch=branch_name,
            )
        pr = gh_repo.create_pull(base=base_head_ref, head=branch_name, title=pr_title, body=pr_body)
        return pr.html_url
    except GithubException as exc:
        raise GitHubAPIError(exc.status, str(exc.data)) from exc


async def open_fix_pr(
    repo: str,
    token: str,
    base_head_sha: str,
    base_head_ref: str,
    branch_name: str,
    file_updates: list[tuple[str, str, str]],
    pr_title: str,
    pr_body: str,
) -> str:
    """
    Create `branch_name` off `base_head_sha`, commit each (path, new_content,
    blob_sha) in `file_updates` to it, and open a PR from that branch back
    into `base_head_ref` — the original PR's own branch, so its author can
    review and merge the fix into their own work.

    Returns the fix PR's URL.
    """
    return await asyncio.to_thread(
        _open_fix_pr_sync, repo, token, base_head_sha, base_head_ref,
        branch_name, file_updates, pr_title, pr_body,
    )
