"""Step 3: calls Claude for one review agent and parses its JSON findings.
Shared by every node in app/agents/graph.py — each node differs only by
its system prompt."""
import json
import logging

from anthropic import AsyncAnthropic
from pydantic import TypeAdapter, ValidationError

from app.agents.models import Finding

logger = logging.getLogger("agents")

_findings_adapter = TypeAdapter(list[Finding])


async def review(client: AsyncAnthropic, model: str, system_prompt: str, diff_context: str) -> list[Finding]:
    """
    Call Claude with `system_prompt` over `diff_context` and return parsed
    findings.

    Only malformed-response errors are swallowed here (returns [] and logs)
    — a single agent misformatting its JSON shouldn't take the whole run
    down. Actual API failures (bad auth, rate limit, network) are *not*
    caught: they propagate so the caller marks the run failed instead of
    silently reporting "no issues found", which would be actively
    misleading for a security reviewer.
    """
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": diff_context}],
    )
    text = response.content[0].text
    try:
        return _findings_adapter.validate_json(text)
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("Failed to parse review agent response as findings JSON: %s", exc)
        return []
