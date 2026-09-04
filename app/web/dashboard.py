"""Serves the read-only run-history dashboard (polls /runs client-side)."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])

_PAGE = (Path(__file__).parent / "templates" / "dashboard.html").read_text(encoding="utf-8")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return _PAGE
