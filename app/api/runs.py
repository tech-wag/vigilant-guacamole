"""Read-only API over the run history, for the dashboard (or any other client)."""
from fastapi import APIRouter, HTTPException

from app.services import runs as runs_service

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(limit: int = 50):
    return runs_service.list_runs(limit=limit)


@router.get("/{run_id}")
async def get_run(run_id: int):
    run = runs_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run
