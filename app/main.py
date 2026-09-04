import logging

from fastapi import FastAPI

from app.api.runs import router as runs_api_router
from app.config import get_settings
from app.web.dashboard import router as dashboard_router
from app.webhooks.github_webhook import router as github_webhook_router

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="AI Code Review Agent",
    description="Reviews PRs for security/performance/test gaps and opens an auto-fix PR.",
    version="0.1.0",
)

app.include_router(github_webhook_router)
app.include_router(runs_api_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
