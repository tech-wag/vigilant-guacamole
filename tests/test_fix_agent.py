from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import fix as fix_module
from app.agents.fix import _findings_by_file, _strip_code_fence, run_fix_agent


def _fake_file(filename: str):
    return SimpleNamespace(filename=filename)


class _FakeAsyncAnthropic:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        client = MagicMock()
        content_block = SimpleNamespace(text="fixed file content")
        client.messages.create = AsyncMock(return_value=SimpleNamespace(content=[content_block]))
        return client

    async def __aexit__(self, *a):
        return False


def test_findings_by_file_groups_across_categories():
    review_results = {
        "security": [{"file": "a.py", "message": "sec"}],
        "performance": [{"file": "a.py", "message": "perf"}, {"file": "b.py", "message": "perf2"}],
        "test": [],
    }
    grouped = _findings_by_file(review_results)
    assert {f["message"] for f in grouped["a.py"]} == {"sec", "perf"}
    assert {f["message"] for f in grouped["b.py"]} == {"perf2"}


def test_strip_code_fence_removes_fence_when_present():
    assert _strip_code_fence("```python\nprint(1)\n```") == "print(1)"


def test_strip_code_fence_leaves_plain_content_untouched():
    assert _strip_code_fence("print(1)") == "print(1)"


@pytest.mark.asyncio
async def test_run_fix_agent_returns_none_when_no_findings():
    result = await run_fix_agent(
        repo="owner/repo", pr_number=1, pr_title="t", head_sha="sha", head_ref="feat",
        files=[_fake_file("a.py")], review_results={"security": [], "performance": [], "test": []},
        token="tok", model="claude-sonnet-5",
    )
    assert result is None


@pytest.mark.asyncio
async def test_run_fix_agent_skips_findings_for_files_outside_the_diff():
    with patch.object(fix_module, "AsyncAnthropic", _FakeAsyncAnthropic), \
         patch.object(fix_module, "fetch_file_content", AsyncMock()) as mock_fetch, \
         patch.object(fix_module, "open_fix_pr", AsyncMock(return_value=None)) as mock_open_pr:
        result = await run_fix_agent(
            repo="owner/repo", pr_number=1, pr_title="t", head_sha="sha", head_ref="feat",
            files=[_fake_file("a.py")],
            review_results={"security": [{"file": "not-in-diff.py", "message": "x", "severity": "high"}],
                             "performance": [], "test": []},
            token="tok", model="claude-sonnet-5",
        )
    mock_fetch.assert_not_called()
    mock_open_pr.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_run_fix_agent_generates_fix_and_opens_pr():
    with patch.object(fix_module, "AsyncAnthropic", _FakeAsyncAnthropic), \
         patch.object(fix_module, "fetch_file_content", AsyncMock(return_value=("original content", "blobsha"))), \
         patch.object(fix_module, "open_fix_pr", AsyncMock(return_value="https://github.com/owner/repo/pull/2")) as mock_open_pr:
        result = await run_fix_agent(
            repo="owner/repo", pr_number=1, pr_title="Add feature", head_sha="deadbeef", head_ref="feat",
            files=[_fake_file("a.py")],
            review_results={"security": [{"file": "a.py", "message": "sql injection", "severity": "high"}],
                             "performance": [], "test": []},
            token="tok", model="claude-sonnet-5",
        )

    assert result == "https://github.com/owner/repo/pull/2"
    _, kwargs = mock_open_pr.call_args
    assert kwargs["file_updates"] == [("a.py", "fixed file content", "blobsha")]
    assert kwargs["base_head_ref"] == "feat"
    assert kwargs["base_head_sha"] == "deadbeef"
    assert "bot/fix-pr-1-deadbee" == kwargs["branch_name"]
    assert kwargs["pr_title"] == "Fix: Add feature (automated)"
