from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.claude_client import review


def _mock_client(response_text: str):
    client = MagicMock()
    content_block = SimpleNamespace(text=response_text)
    client.messages.create = AsyncMock(return_value=SimpleNamespace(content=[content_block]))
    return client


@pytest.mark.asyncio
async def test_review_parses_well_formed_findings():
    findings_json = (
        '[{"file": "app/main.py", "line": 12, "severity": "high", '
        '"message": "SQL injection", "suggestion": "use parameterized queries"}]'
    )
    client = _mock_client(findings_json)
    findings = await review(client, "claude-sonnet-5", "system prompt", "diff context")
    assert len(findings) == 1
    assert findings[0].file == "app/main.py"
    assert findings[0].severity == "high"


@pytest.mark.asyncio
async def test_review_returns_empty_list_for_no_issues():
    client = _mock_client("[]")
    findings = await review(client, "claude-sonnet-5", "system prompt", "diff context")
    assert findings == []


@pytest.mark.asyncio
async def test_review_swallows_malformed_json_and_returns_empty():
    client = _mock_client("not valid json at all")
    findings = await review(client, "claude-sonnet-5", "system prompt", "diff context")
    assert findings == []


@pytest.mark.asyncio
async def test_review_swallows_json_that_fails_schema_validation():
    client = _mock_client('[{"file": "app/main.py", "severity": "not-a-real-severity", "message": "x"}]')
    findings = await review(client, "claude-sonnet-5", "system prompt", "diff context")
    assert findings == []


@pytest.mark.asyncio
async def test_review_passes_system_prompt_and_diff_context_through():
    client = _mock_client("[]")
    await review(client, "claude-sonnet-5", "SYSTEM", "DIFF")
    _, kwargs = client.messages.create.call_args
    assert kwargs["system"] == "SYSTEM"
    assert kwargs["messages"] == [{"role": "user", "content": "DIFF"}]
    assert kwargs["model"] == "claude-sonnet-5"
