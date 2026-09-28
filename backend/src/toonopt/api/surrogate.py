"""GET /surrogate/status, POST /surrogate/train.

Experimental GPU surrogate model (see toonopt.surrogate). Importing this module never
requires torch -- only the job's run function (executed on the worker thread) does, and
a missing/broken torch install surfaces as a normal failed Job, not a broken API.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from toonopt.jobs import JobContext, manager
from toonopt.models import Job
from toonopt.surrogate import model as surrogate_model

router = APIRouter(prefix="/surrogate", tags=["surrogate"])


class TrainRequest(BaseModel):
    klass: str
    spec: str
    min_samples: int = 200
    epochs: int = surrogate_model.DEFAULT_EPOCHS


@router.get("/status")
def status() -> dict:
    return surrogate_model.status()


@router.post("/train", response_model=Job)
def train(req: TrainRequest) -> Job:
    def run(ctx: JobContext) -> dict:
        def cb(epoch: int, total: int, val_mae: float) -> None:
            ctx.progress("training", epoch, total, f"epoch {epoch}/{total} val_mae={val_mae * 100:.2f}%")

        report = surrogate_model.train(
            req.klass, req.spec, min_samples=req.min_samples, epochs=req.epochs, progress_cb=cb,
        )
        return {
            "samples": report.samples, "val_mae_pct": report.val_mae_pct,
            "epochs": report.epochs, "device": report.device, "path": report.path,
        }

    return manager.submit("surrogate_train", run, character=req.klass, spec=req.spec)
