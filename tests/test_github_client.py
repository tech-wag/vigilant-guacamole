from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from github.GithubException import GithubException

from app.github_client.client import (
    DiffTooLargeError,
    GitHubAPIError,
    fetch_file_content,
    fetch_pr_files,
    open_fix_pr,
)


def _fake_file(filename: str, patch: str, additions: int = 1, deletions: int = 0):
    return SimpleNamespace(filename=filename, patch=patch, additions=additions, deletions=deletions)


def _mock_github_returning(files):
    gh = MagicMock()
    gh.get_repo.return_value.get_pull.return_value.get_files.return_value = files
    return gh


@pytest.mark.asyncio
async def test_fetch_pr_files_returns_files_under_limit():
    files = [_fake_file("app/main.py", "@@ -1,1 +1,1 @@\n-a\n+b\n")]
    with patch("app.github_client.client.Github", return_value=_mock_github_returning(files)):
        result = await fetch_pr_files(repo="owner/repo", pr_number=1, token="t", max_bytes=1000)
    assert result == files


@pytest.mark.asyncio
async def test_fetch_pr_files_raises_when_over_limit():
    big_patch = "@@ -1,1 +1,1 @@\n" + ("+line\n" * 100)
    files = [_fake_file("big.py", big_patch)]
    with patch("app.github_client.client.Github", return_value=_mock_github_returning(files)):
        with pytest.raises(DiffTooLargeError) as exc_info:
            await fetch_pr_files(repo="owner/repo", pr_number=1, token="t", max_bytes=10)
    assert exc_info.value.max_bytes == 10
    assert exc_info.value.size_bytes == len(big_patch)


@pytest.mark.asyncio
async def test_fetch_pr_files_ignores_binary_files_with_no_patch():
    files = [_fake_file("image.png", None, additions=0, deletions=0)]
    with patch("app.github_client.client.Github", return_value=_mock_github_returning(files)):
        result = await fetch_pr_files(repo="owner/repo", pr_number=1, token="t", max_bytes=10)
    assert result == files


@pytest.mark.asyncio
async def test_fetch_pr_files_wraps_github_exception():
    gh = MagicMock()
    gh.get_repo.return_value.get_pull.side_effect = GithubException(404, {"message": "Not Found"}, None)
    with patch("app.github_client.client.Github", return_value=gh):
        with pytest.raises(GitHubAPIError) as exc_info:
            await fetch_pr_files(repo="owner/repo", pr_number=999, token="t", max_bytes=1000)
    assert exc_info.value.status == 404


@pytest.mark.asyncio
async def test_fetch_file_content_returns_decoded_text_and_sha():
    content_file = SimpleNamespace(decoded_content=b"print('hi')", sha="abc123")
    gh = MagicMock()
    gh.get_repo.return_value.get_contents.return_value = content_file
    with patch("app.github_client.client.Github", return_value=gh):
        content, sha = await fetch_file_content(repo="owner/repo", path="a.py", ref="deadbeef", token="t")
    assert content == "print('hi')"
    assert sha == "abc123"


@pytest.mark.asyncio
async def test_fetch_file_content_wraps_github_exception():
    gh = MagicMock()
    gh.get_repo.return_value.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, None)
    with patch("app.github_client.client.Github", return_value=gh):
        with pytest.raises(GitHubAPIError):
            await fetch_file_content(repo="owner/repo", path="missing.py", ref="deadbeef", token="t")


@pytest.mark.asyncio
async def test_open_fix_pr_creates_branch_commits_files_and_opens_pr():
    gh_repo = MagicMock()
    gh_repo.create_pull.return_value = SimpleNamespace(html_url="https://github.com/owner/repo/pull/99")
    gh = MagicMock()
    gh.get_repo.return_value = gh_repo

    with patch("app.github_client.client.Github", return_value=gh):
        url = await open_fix_pr(
            repo="owner/repo",
            token="t",
            base_head_sha="deadbeef",
            base_head_ref="feature/x",
            branch_name="bot/fix-pr-1-deadbee",
            file_updates=[("a.py", "fixed content", "sha1")],
            pr_title="Fix: something",
            pr_body="body",
        )

    assert url == "https://github.com/owner/repo/pull/99"
    gh_repo.create_git_ref.assert_called_once_with(ref="refs/heads/bot/fix-pr-1-deadbee", sha="deadbeef")
    gh_repo.update_file.assert_called_once_with(
        path="a.py", message="fix: automated review fix for a.py",
        content="fixed content", sha="sha1", branch="bot/fix-pr-1-deadbee",
    )
    gh_repo.create_pull.assert_called_once_with(
        base="feature/x", head="bot/fix-pr-1-deadbee", title="Fix: something", body="body",
    )


@pytest.mark.asyncio
async def test_open_fix_pr_wraps_github_exception():
    gh_repo = MagicMock()
    gh_repo.create_git_ref.side_effect = GithubException(422, {"message": "Reference already exists"}, None)
    gh = MagicMock()
    gh.get_repo.return_value = gh_repo

    with patch("app.github_client.client.Github", return_value=gh):
        with pytest.raises(GitHubAPIError) as exc_info:
            await open_fix_pr(
                repo="owner/repo", token="t", base_head_sha="deadbeef", base_head_ref="feature/x",
                branch_name="bot/fix-pr-1-deadbee", file_updates=[], pr_title="t", pr_body="b",
            )
    assert exc_info.value.status == 422
