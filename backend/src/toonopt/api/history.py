"""GET /history, DELETE /history/{id}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from toonopt.jobs import manager

router = APIRouter(prefix="/history", tags=["history"])


@router.get("")
def list_history() -> list[dict]:
    return manager.history()


@router.delete("/{job_id}")
def delete_history(job_id: str) -> dict:
    if manager.get(job_id) is None and not manager.job_dir(job_id).exists():
        raise HTTPException(404, "job not found")
    manager.delete(job_id)
    return {"ok": True}
