"""
Step 3: a LangGraph StateGraph that fans a PR's diff out to three parallel
Claude review agents (Security / Performance / Test-coverage) and fans
their findings back in. Step 4 will add a Fix agent downstream of this.

The three review nodes share no state between each other (each only
writes its own key), so LangGraph runs them concurrently in one superstep
once compiled — no extra fan-out/fan-in bookkeeping needed here.
"""
from typing import TypedDict

from anthropic import AsyncAnthropic
from github.File import File
from langgraph.graph import END, START, StateGraph

from app.agents.claude_client import review
from app.agents.models import Finding
from app.prompts.review_prompts import (
    PERFORMANCE_SYSTEM_PROMPT,
    SECURITY_SYSTEM_PROMPT,
    TEST_COVERAGE_SYSTEM_PROMPT,
    build_diff_context,
)


class ReviewState(TypedDict):
    diff_context: str
    model: str
    client: AsyncAnthropic
    security_findings: list[Finding]
    performance_findings: list[Finding]
    test_findings: list[Finding]


def _make_node(system_prompt: str, output_key: str):
    async def node(state: ReviewState) -> dict:
        findings = await review(state["client"], state["model"], system_prompt, state["diff_context"])
        return {output_key: findings}

    return node


def _build_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("security", _make_node(SECURITY_SYSTEM_PROMPT, "security_findings"))
    graph.add_node("performance", _make_node(PERFORMANCE_SYSTEM_PROMPT, "performance_findings"))
    graph.add_node("test_coverage", _make_node(TEST_COVERAGE_SYSTEM_PROMPT, "test_findings"))
    for name in ("security", "performance", "test_coverage"):
        graph.add_edge(START, name)
        graph.add_edge(name, END)
    return graph.compile()


_graph = _build_graph()


async def run_pipeline(files: list[File], model: str) -> dict[str, list[dict]]:
    """Fan the PR's diff out to the three review agents and return their findings,
    keyed by agent name, as plain JSON-serializable dicts."""
    diff_context = build_diff_context(files)
    async with AsyncAnthropic() as client:
        result = await _graph.ainvoke({
            "diff_context": diff_context,
            "model": model,
            "client": client,
            "security_findings": [],
            "performance_findings": [],
            "test_findings": [],
        })
    return {
        "security": [f.model_dump() for f in result["security_findings"]],
        "performance": [f.model_dump() for f in result["performance_findings"]],
        "test": [f.model_dump() for f in result["test_findings"]],
    }
