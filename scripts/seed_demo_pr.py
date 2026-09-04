#!/usr/bin/env python
"""
Step 5: seeds a demo repo with a baseline "user lookup" endpoint on its
default branch, then opens a PR from a feature branch that introduces a
SQL-injection bug — the PR the recorded demo reviews.

Safe to re-run: it reuses an existing repo/branch/PR instead of failing
if one is already there, so you can re-record without cleaning up first.

Usage:
    python scripts/seed_demo_pr.py

Requires GITHUB_TOKEN (repo scope — creating a repo needs more than the
contents+pull-requests scope the running app needs) and GITHUB_REPO in
.env, same as the running app. If GITHUB_REPO doesn't exist yet, it's
created under the token's account.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github import Auth, Github
from github.GithubException import GithubException
from github.Repository import Repository

from app.config import get_settings

DEMO_FILE_PATH = "app/lookup.py"
FEATURE_BRANCH = "feature/user-lookup"
PR_TITLE = "Add user lookup endpoint"
PR_BODY = (
    "Adds a `/users/{user_id}` lookup endpoint.\n\n"
    "_(Seeded by `scripts/seed_demo_pr.py` for the recorded demo — this PR "
    "contains an intentional SQL-injection bug for the review agents to catch.)_"
)

SEED_DIR = Path(__file__).resolve().parent.parent / "demo" / "seed"


def _read(name: str) -> str:
    return (SEED_DIR / name).read_text(encoding="utf-8")


def _get_or_create_repo(gh: Github, full_name: str) -> Repository:
    try:
        repo = gh.get_repo(full_name)
        print(f"Using existing repo {full_name}")
        return repo
    except GithubException as exc:
        if exc.status != 404:
            raise
        print(f"Repo {full_name} not found, creating it...")
        _owner, name = full_name.split("/", 1)
        return gh.get_user().create_repo(
            name, description="AI Code Review Agent demo target", auto_init=True
        )


def _seed_baseline(repo: Repository, base_branch: str) -> None:
    baseline = _read("app_before.py")
    try:
        existing = repo.get_contents(DEMO_FILE_PATH, ref=base_branch)
        if existing.decoded_content.decode("utf-8") != baseline:
            repo.update_file(
                DEMO_FILE_PATH, "chore: seed baseline lookup endpoint",
                baseline, existing.sha, branch=base_branch,
            )
            print(f"Updated {DEMO_FILE_PATH} on {base_branch}")
        else:
            print(f"{DEMO_FILE_PATH} already up to date on {base_branch}")
    except GithubException as exc:
        if exc.status != 404:
            raise
        repo.create_file(
            DEMO_FILE_PATH, "chore: seed baseline lookup endpoint", baseline, branch=base_branch
        )
        print(f"Created {DEMO_FILE_PATH} on {base_branch}")


def _create_or_reuse_branch(repo: Repository, base_branch: str) -> None:
    base_sha = repo.get_branch(base_branch).commit.sha
    try:
        repo.create_git_ref(ref=f"refs/heads/{FEATURE_BRANCH}", sha=base_sha)
        print(f"Created branch {FEATURE_BRANCH}")
    except GithubException as exc:
        if exc.status != 422:  # "Reference already exists"
            raise
        print(f"Branch {FEATURE_BRANCH} already exists, reusing it")


def _push_vulnerable_version(repo: Repository) -> None:
    vulnerable = _read("app_after_vulnerable.py")
    file_on_branch = repo.get_contents(DEMO_FILE_PATH, ref=FEATURE_BRANCH)
    if file_on_branch.decoded_content.decode("utf-8") != vulnerable:
        repo.update_file(
            DEMO_FILE_PATH, "Add user lookup endpoint",
            vulnerable, file_on_branch.sha, branch=FEATURE_BRANCH,
        )
        print(f"Pushed vulnerable version of {DEMO_FILE_PATH} to {FEATURE_BRANCH}")
    else:
        print(f"{FEATURE_BRANCH} already has the vulnerable version")


def _open_or_reuse_pr(repo: Repository, base_branch: str) -> str:
    existing = list(repo.get_pulls(
        state="open", head=f"{repo.owner.login}:{FEATURE_BRANCH}", base=base_branch
    ))
    if existing:
        print(f"Reusing existing PR: {existing[0].html_url}")
        return existing[0].html_url
    pr = repo.create_pull(base=base_branch, head=FEATURE_BRANCH, title=PR_TITLE, body=PR_BODY)
    print(f"Opened PR: {pr.html_url}")
    return pr.html_url


def main() -> None:
    settings = get_settings()
    gh = Github(auth=Auth.Token(settings.github_token))

    repo = _get_or_create_repo(gh, settings.github_repo)
    base_branch = repo.default_branch

    _seed_baseline(repo, base_branch)
    _create_or_reuse_branch(repo, base_branch)
    _push_vulnerable_version(repo)
    pr_url = _open_or_reuse_pr(repo, base_branch)

    print(f"\nDemo ready: {pr_url}")
    print("With the app running and a webhook pointed at it (see README:")
    print("'Point a real GitHub webhook at it'), this PR should already have")
    print("triggered a review run — check GET /dashboard.")


if __name__ == "__main__":
    main()
