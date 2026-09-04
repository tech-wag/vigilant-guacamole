from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents import graph as graph_module
from app.agents.models import Finding
from app.prompts.review_prompts import (
    PERFORMANCE_SYSTEM_PROMPT,
    SECURITY_SYSTEM_PROMPT,
    TEST_COVERAGE_SYSTEM_PROMPT,
)


class _FakeAsyncAnthropic:
    """Stands in for AsyncAnthropic so tests don't need a real API key —
    `review()` is mocked separately, so this client is never actually called."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return MagicMock(name="anthropic-client")

    async def __aexit__(self, *args):
        return False


async def _canned_review(client, model, system_prompt, diff_context):
    if system_prompt == SECURITY_SYSTEM_PROMPT:
        return [Finding(file="a.py", message="sec issue")]
    if system_prompt == PERFORMANCE_SYSTEM_PROMPT:
        return [Finding(file="a.py", message="perf issue")]
    if system_prompt == TEST_COVERAGE_SYSTEM_PROMPT:
        return [Finding(file="a.py", message="missing test")]
    raise AssertionError(f"unexpected system prompt: {system_prompt!r}")


@pytest.mark.asyncio
async def test_run_pipeline_routes_each_agents_findings_to_its_own_key():
    with patch.object(graph_module, "AsyncAnthropic", _FakeAsyncAnthropic), \
         patch.object(graph_module, "review", AsyncMock(side_effect=_canned_review)):
        result = await graph_module.run_pipeline(files=[], model="claude-sonnet-5")

    assert result["security"] == [
        {"file": "a.py", "line": None, "severity": "medium", "message": "sec issue", "suggestion": None}
    ]
    assert result["performance"][0]["message"] == "perf issue"
    assert result["test"][0]["message"] == "missing test"


@pytest.mark.asyncio
async def test_run_pipeline_invokes_all_three_agents():
    calls = []

    async def _tracking_review(client, model, system_prompt, diff_context):
        calls.append(system_prompt)
        return []

    with patch.object(graph_module, "AsyncAnthropic", _FakeAsyncAnthropic), \
         patch.object(graph_module, "review", AsyncMock(side_effect=_tracking_review)):
        result = await graph_module.run_pipeline(files=[], model="claude-sonnet-5")

    assert len(calls) == 3
    assert {SECURITY_SYSTEM_PROMPT, PERFORMANCE_SYSTEM_PROMPT, TEST_COVERAGE_SYSTEM_PROMPT} == set(calls)
    assert result == {"security": [], "performance": [], "test": []}
