import hashlib
import hmac
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Settings are read from env at import time, so tests set them before importing the app.
import os

os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("GITHUB_REPO", "your-username/ai-code-review-agent-demo")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
# Isolated DB file so test runs don't write into the repo's runs.db.
os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "test_runs.db"))

from app.main import app  # noqa: E402

client = TestClient(app)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_vulnerable_pr.json"
SECRET = "test-secret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def payload_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture(autouse=True)
def _stub_github_diff_fetch(monkeypatch):
    """
    These tests exercise the webhook receiver (auth, dedup, filtering),
    not the Step 2 GitHub client or Step 3 review agents — stub both out
    so they stay fast and offline instead of hitting real GitHub/Anthropic
    APIs from a background task.
    """
    async def _fake_fetch_pr_files(*args, **kwargs):
        return []

    async def _fake_run_pipeline(*args, **kwargs):
        return {"security": [], "performance": [], "test": []}

    monkeypatch.setattr("app.webhooks.github_webhook.fetch_pr_files", _fake_fetch_pr_files)
    monkeypatch.setattr("app.webhooks.github_webhook.run_pipeline", _fake_run_pipeline)


def test_rejects_missing_signature(payload_bytes):
    resp = client.post(
        "/webhooks/github",
        content=payload_bytes,
        headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "d1"},
    )
    assert resp.status_code == 401


def test_rejects_bad_signature(payload_bytes):
    resp = client.post(
        "/webhooks/github",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d2",
            "X-Hub-Signature-256": "sha256=deadbeef",
        },
    )
    assert resp.status_code == 401


def test_accepts_valid_pull_request_event(payload_bytes):
    resp = client.post(
        "/webhooks/github",
        content=payload_bytes,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d3",
            "X-Hub-Signature-256": _sign(payload_bytes),
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["pr_number"] == 42


def test_ignores_duplicate_delivery(payload_bytes):
    headers = {
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "d4",
        "X-Hub-Signature-256": _sign(payload_bytes),
    }
    first = client.post("/webhooks/github", content=payload_bytes, headers=headers)
    second = client.post("/webhooks/github", content=payload_bytes, headers=headers)
    assert first.status_code == 202
    assert second.json()["reason"] == "duplicate delivery"


def test_ignores_draft_pr(payload_bytes):
    data = json.loads(payload_bytes)
    data["pull_request"]["draft"] = True
    body = json.dumps(data).encode()
    resp = client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": "d5",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.json()["reason"] == "draft PR"


def test_ping_event_returns_pong():
    resp = client.post(
        "/webhooks/github",
        content=b"{}",
        headers={"X-GitHub-Event": "ping", "X-Hub-Signature-256": _sign(b"{}")},
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "pong"}
