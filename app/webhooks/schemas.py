"""
We deliberately model only the fields we use, not the full GitHub payload
(which is enormous). Pydantic's default `extra="ignore"` behavior means
unknown fields are silently dropped rather than raising, so this stays
forward-compatible with GitHub adding fields.
"""
from typing import Literal

from pydantic import BaseModel


class Repository(BaseModel):
    full_name: str  # "owner/repo"
    name: str
    owner_login: str = ""

    @classmethod
    def from_payload(cls, data: dict) -> "Repository":
        return cls(
            full_name=data["full_name"],
            name=data["name"],
            owner_login=data.get("owner", {}).get("login", ""),
        )


class PullRequestRef(BaseModel):
    ref: str  # branch name
    sha: str


class PullRequest(BaseModel):
    number: int
    title: str
    html_url: str
    head: PullRequestRef
    base: PullRequestRef
    draft: bool = False


class PullRequestEvent(BaseModel):
    """
    Payload shape for the GitHub `pull_request` webhook event.
    Docs: https://docs.github.com/en/webhooks/webhook-events-and-payloads#pull_request
    """
    action: Literal[
        "opened", "reopened", "synchronize", "edited",
        "closed", "labeled", "unlabeled", "ready_for_review",
    ]
    number: int
    pull_request: PullRequest
    repository: Repository

    @classmethod
    def from_payload(cls, data: dict) -> "PullRequestEvent":
        return cls(
            action=data["action"],
            number=data["number"],
            pull_request=PullRequest(
                number=data["pull_request"]["number"],
                title=data["pull_request"]["title"],
                html_url=data["pull_request"]["html_url"],
                head=PullRequestRef(
                    ref=data["pull_request"]["head"]["ref"],
                    sha=data["pull_request"]["head"]["sha"],
                ),
                base=PullRequestRef(
                    ref=data["pull_request"]["base"]["ref"],
                    sha=data["pull_request"]["base"]["sha"],
                ),
                draft=data["pull_request"].get("draft", False),
            ),
            repository=Repository.from_payload(data["repository"]),
        )


# Actions that should actually trigger a review run.
REVIEW_TRIGGER_ACTIONS = {"opened", "reopened", "synchronize", "ready_for_review"}
