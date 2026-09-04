"""
Read/write access to the `runs` table — one row per review-pipeline
invocation, so the dashboard has history to show without re-deriving it
from GitHub on every load.
"""
import json
from datetime import datetime, timezone
from typing import Any

from app.db import get_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict[str, Any]:
    d = dict(row)
    if d.get("findings"):
        d["findings"] = json.loads(d["findings"])
    return d


def create_run(*, repo: str, pr_number: int, pr_title: str, pr_url: str, action: str) -> int:
    now = _now()
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO runs (repo, pr_number, pr_title, pr_url, action, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)""",
            (repo, pr_number, pr_title, pr_url, action, now, now),
        )
        return cur.lastrowid


def update_run(
    run_id: int,
    *,
    status: str,
    findings: dict[str, Any] | None = None,
    fix_pr_url: str | None = None,
    error: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """UPDATE runs SET status = ?, findings = ?, fix_pr_url = ?, error = ?, updated_at = ?
               WHERE id = ?""",
            (status, json.dumps(findings) if findings is not None else None, fix_pr_url, error, _now(), run_id),
        )


def get_run(run_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_dict(row) if row else None


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]
