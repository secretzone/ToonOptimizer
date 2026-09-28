"""FastAPI app. Routers live in toonopt.api.* and register themselves in `ROUTERS`."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from toonopt import __version__
from toonopt.config import FRONTEND_DIST, settings

log = logging.getLogger(__name__)


def _maybe_start_data_refresh() -> None:
    """Kick off a background ``data_refresh`` job if the *live* WoW build's DB2 cache isn't
    ready yet -- e.g. right after a patch, before anyone has clicked "Refresh data".

    Never blocks startup: ``manager.submit`` only enqueues the job, a worker thread runs it.
    Deliberately does NOT touch SimC install status -- installing SimC is the user's own
    click, never automatic.
    """
    try:
        from toonopt.data import wago
        from toonopt.jobs import manager
    except ModuleNotFoundError:
        return  # data layer not installed; nothing to refresh
    build = settings.refresh_wow_build()
    if not build:
        return
    try:
        ready = wago.is_ready(build)
    except Exception:
        log.exception("could not check data cache readiness for build %s", build)
        return
    if ready:
        return
    log.info("wow build %s has no cached game data yet; submitting a background data_refresh job", build)

    def run(ctx):
        from toonopt.api.data import _run_refresh

        return _run_refresh(build, ctx.progress)

    manager.submit("data_refresh", run)


def _maybe_backfill_characters() -> None:
    """Seed ``characters/`` from ``history/*/profile.json`` on first startup (API.md
    "Characters" backfill); never blocks or fails startup."""
    try:
        from toonopt import characters
        characters.backfill()
    except Exception:
        log.exception("character backfill from history/*/profile.json failed")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _maybe_start_data_refresh()
    _maybe_backfill_characters()
    yield


app = FastAPI(title="ToonOptimizer", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


def _mount_routers() -> None:
    # Each module in toonopt.api exposes `router`. Import lazily so a broken
    # optional module (e.g. surrogate without torch) does not take the app down.
    import importlib

    for name in (
        "status", "importer", "data", "sims", "jobs", "history", "settings_api", "surrogate",
        "characters", "advisor", "reports",
    ):
        try:
            mod = importlib.import_module(f"toonopt.api.{name}")
        except ModuleNotFoundError as e:
            if e.name and e.name.startswith("toonopt.api"):
                continue          # router not written yet
            raise
        app.include_router(mod.router, prefix="/api")


_mount_routers()

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
