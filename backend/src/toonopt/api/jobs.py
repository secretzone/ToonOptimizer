"""GET /jobs, /jobs/{id}, /jobs/{id}/events (SSE), POST /jobs/{id}/cancel, result/input/report."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sse_starlette.sse import EventSourceResponse

from toonopt.jobs import manager
from toonopt.models import Job, SimResult
from toonopt.report import render

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _job(job_id: str) -> Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("", response_model=list[Job])
def list_jobs() -> list[Job]:
    return manager.list_jobs()


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    return _job(job_id)


@router.post("/{job_id}/cancel", response_model=Job)
def cancel_job(job_id: str) -> Job:
    job = manager.cancel(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request):
    job = _job(job_id)
    q = manager.subscribe(job_id)

    async def gen():
        try:
            # initial snapshot so late subscribers see the current state
            current = manager.get(job_id) or job
            if current.status in ("done", "failed", "cancelled"):
                yield {"event": "done" if current.status == "done" else "failed", "data": current.model_dump_json()}
                return
            yield {"event": "progress", "data": current.model_dump_json()}
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event, payload = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    yield {"comment": "keepalive"}
                    continue
                yield {"event": event, "data": json.dumps(payload)}
                if event in ("done", "failed"):
                    return
        finally:
            manager.unsubscribe(job_id, q)

    return EventSourceResponse(gen())


@router.get("/{job_id}/result", response_model=SimResult)
def job_result(job_id: str) -> SimResult:
    job = _job(job_id)
    res = manager.result(job_id)
    if res is None:
        if job.status in ("queued", "running"):
            raise HTTPException(409, f"job is {job.status}")
        raise HTTPException(404, job.error or "no result")
    if not isinstance(res, SimResult):
        raise HTTPException(404, "job has no sim result")
    return res


@router.get("/{job_id}/input", response_class=PlainTextResponse)
def job_input(job_id: str) -> str:
    _job(job_id)
    text = manager.input_text(job_id)
    if text is None:
        raise HTTPException(404, "no input for this job")
    return text


@router.get("/{job_id}/report.html", response_class=HTMLResponse)
def job_report(job_id: str) -> str:
    _job(job_id)
    p = manager.job_dir(job_id) / "report.html"
    if p.exists():
        return p.read_text("utf-8")
    res = manager.sim_result(job_id)
    if res is None:
        raise HTTPException(404, "no report for this job")
    return render(res)


@router.get("/{job_id}/simc.html", response_class=HTMLResponse)
def job_simc_html(job_id: str) -> str:
    """SimC's own native HTML report (job runs always pass html=True + report_details=1)."""
    _job(job_id)
    p = manager.job_dir(job_id) / "simc.html"
    if not p.exists():
        raise HTTPException(404, "no SimC report for this job")
    return p.read_text("utf-8")
