"""Step 3: the shared finding shape every review agent must return."""
from typing import Literal

from pydantic import BaseModel


class Finding(BaseModel):
    file: str
    line: int | None = None
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    message: str
    suggestion: str | None = None
