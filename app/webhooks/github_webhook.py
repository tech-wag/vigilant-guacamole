"""
Step 1: the webhook receiver.

Responsibilities (and ONLY these — the graph/agents live elsewhere):
  1. Verify the request really came from GitHub (HMAC-SHA256 signature).
  2. Parse just enough of the payload to decide whether to act.
  3. Hand off to a background task immediately and return 202.

GitHub gives you ~10s before it considers a webhook delivery failed and
retries, so this handler must not block on anything slow (diff fetch,
Claude calls, PR creation all happen after we've already responded).
"""
import hashlib
import hmac
import logging

from anthropic import AnthropicError
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.agents.fix import run_fix_agent
from app.agents.graph import run_pipeline
from app.config import get_settings
from app.github_client.client import DiffTooLargeError, GitHubAPIError, fetch_pr_files
from app.github_client.diff_parser import parse_patch
from app.services import runs as runs_service
from app.webhooks.schemas import REVIEW_TRIGGER_ACTIONS, PullRequestEvent

logger = logging.getLogger("webhook")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# In-memory dedup for the demo. GitHub can redeliver the same event id on
# retry/timeout; without this a slow run could get kicked off twice.
# NOTE: process-local only — fine for a single-container demo, but swap for
# Redis (SETNX with a TTL) before running multiple workers or replicas.
_seen_delivery_ids: set[str] = set()
_SEEN_CAP = 5_000


def verify_signature(payload_body: bytes, signature_header: str | None, secret: str) -> None:
    """Raise HTTPException if the payload doesn't match GitHub's HMAC signature."""
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # compare_digest to avoid timing attacks
    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


def _remember_delivery(delivery_id: str) -> bool:
    """Returns True if this is a new delivery, False if we've seen it before."""
    if delivery_id in _seen_delivery_ids:
        return False
    if len(_seen_delivery_ids) >= _SEEN_CAP:
        _seen_delivery_ids.clear()  # crude cap; good enough for a demo
    _seen_delivery_ids.add(delivery_id)
    return True


async def run_review_pipeline(event: PullRequestEvent, run_id: int) -> None:
    """
    Step 2: fetch the PR's diff. Step 3: run it through the parallel review
    agents. Step 4: fan any findings into the fix agent and open the fix PR.
    Kept as a separate function so it's trivially swappable for a queue-based
    worker later without touching the webhook handler.
    """
    runs_service.update_run(run_id, status="running")
    settings = get_settings()
    logger.info(
        "Fetching diff for %s PR #%d (%s)",
        event.repository.full_name, event.pull_request.number, event.action,
    )

    try:
        files = await fetch_pr_files(
            repo=event.repository.full_name,
            pr_number=event.pull_request.number,
            token=settings.github_token,
            max_bytes=settings.max_diff_bytes,
        )
    except DiffTooLargeError as exc:
        logger.info("PR #%d diff too large (%d bytes), skipping review", event.pull_request.number, exc.size_bytes)
        runs_service.update_run(
            run_id,
            status="failed",
            error=f"diff too large ({exc.size_bytes} bytes > {exc.max_bytes}-byte limit) — skipped review",
        )
        return
    except GitHubAPIError as exc:
        logger.warning("GitHub API error fetching PR #%d: %s", event.pull_request.number, exc)
        runs_service.update_run(run_id, status="failed", error=str(exc))
        return

    hunks_by_file = {f.filename: parse_patch(f.patch) for f in files if f.patch}
    diff_summary = {
        "files_changed": len(files),
        "additions": sum(f.additions for f in files),
        "deletions": sum(f.deletions for f in files),
        "hunks": sum(len(h) for h in hunks_by_file.values()),
        "files": [f.filename for f in files],
    }

    try:
        review_results = await run_pipeline(files, settings.claude_model)
    except AnthropicError as exc:
        # Don't report "no issues found" on an API failure — that would be
        # actively misleading for a security review. Surface it as failed.
        logger.warning("Review agents failed for PR #%d: %s", event.pull_request.number, exc)
        runs_service.update_run(
            run_id,
            status="failed",
            error=f"review agents failed: {exc}",
            findings={"diff_summary": diff_summary},
        )
        return

    fix_pr_url = None
    fix_error = None
    try:
        fix_pr_url = await run_fix_agent(
            repo=event.repository.full_name,
            pr_number=event.pull_request.number,
            pr_title=event.pull_request.title,
            head_sha=event.pull_request.head.sha,
            head_ref=event.pull_request.head.ref,
            files=files,
            review_results=review_results,
            token=settings.github_token,
            model=settings.claude_model,
        )
    except (GitHubAPIError, AnthropicError) as exc:
        # The review itself already succeeded — don't throw those findings
        # away just because the bonus auto-fix step failed.
        logger.warning("Fix agent failed for PR #%d: %s", event.pull_request.number, exc)
        fix_error = str(exc)

    findings = {
        "diff_summary": diff_summary,
        "review": review_results,
        "total_findings": sum(len(v) for v in review_results.values()),
    }
    if fix_error:
        findings["fix_error"] = fix_error

    runs_service.update_run(run_id, status="completed", fix_pr_url=fix_pr_url, findings=findings)


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
):
    settings = get_settings()
    raw_body = await request.body()

    verify_signature(raw_body, x_hub_signature_256, settings.github_webhook_secret)

    # We only care about pull_request events; GitHub also sends ping,
    # issue_comment, etc. if those event types are enabled on the webhook.
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"unsupported event '{x_github_event}'"}

    if x_github_delivery and not _remember_delivery(x_github_delivery):
        return {"status": "ignored", "reason": "duplicate delivery"}

    payload = await request.json()
    event = PullRequestEvent.from_payload(payload)

    if event.action not in REVIEW_TRIGGER_ACTIONS:
        return {"status": "ignored", "reason": f"action '{event.action}' not review-triggering"}

    if event.pull_request.draft:
        return {"status": "ignored", "reason": "draft PR"}

    run_id = runs_service.create_run(
        repo=event.repository.full_name,
        pr_number=event.pull_request.number,
        pr_title=event.pull_request.title,
        pr_url=event.pull_request.html_url,
        action=event.action,
    )
    background_tasks.add_task(run_review_pipeline, event, run_id)

    return {
        "status": "accepted",
        "repo": event.repository.full_name,
        "pr_number": event.pull_request.number,
        "action": event.action,
        "run_id": run_id,
    }
