"""GET /status, POST /simc/install."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from toonopt.config import settings
from toonopt.jobs import JobContext, manager
from toonopt.models import Job
from toonopt.simc import runtime

router = APIRouter(tags=["status"])


class InstallRequest(BaseModel):
    tag: str | None = None


def gpu_status() -> dict:
    try:
        import torch  # type: ignore[import-not-found]

        if torch.cuda.is_available():
            return {"available": True, "name": torch.cuda.get_device_name(0)}
        return {"available": False, "name": None}
    except Exception:  # noqa: BLE001 - torch missing or broken CUDA
        return {"available": False, "name": None}


def data_status(build: str) -> dict:
    try:
        from toonopt.data import wago  # type: ignore[attr-defined]

        st = wago.status(build)
        if isinstance(st, dict):
            return st
        return st.model_dump() if hasattr(st, "model_dump") else dict(st)
    except Exception:  # noqa: BLE001 - data layer optional
        return {"build": build, "cached_tables": [], "ready": False, "refreshed_at": None}


def simc_status(check_latest: bool = True) -> dict:
    inst = runtime.installed()
    latest = runtime.latest_tag() if check_latest else None
    return {
        "installed": inst is not None,
        "tag": inst.tag if inst else None,
        "path": str(inst.path) if inst else None,
        "version_string": inst.version_string if inst else None,
        "simc_version": inst.simc_version if inst else None,
        "wow_version": inst.wow_version if inst else None,
        "latest_tag": latest,
        "update_available": bool(inst and latest and inst.tag not in ("custom", latest)),
    }


def _version_patch(v: str) -> str:
    """``major.minor.patch`` of a WoW version string like ``12.1.0.69875`` (build number
    dropped: a SimC build lagging only the trailing build/hotfix number still works fine)."""
    parts = v.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else v


def _effective_data_build() -> str:
    """The build every data read currently uses (``toonopt.data.wago.effective_build()``).

    This can differ from ``data_status(game_build)["build"]``, which always echoes back
    whatever build it was asked about -- it never tells you what's *actually* being read.
    Used to warn when WoW patched but "Refresh data" hasn't been re-run for the new build.
    """
    try:
        from toonopt.data import wago  # type: ignore[attr-defined]

        return wago.effective_build()
    except Exception:  # noqa: BLE001 - data layer optional
        return ""


def mismatch_status(simc: dict, game_build: str, effective_build: str) -> dict:
    simc_wow_version = simc.get("wow_version") or ""
    simc_mismatch = bool(simc_wow_version) and bool(game_build) and (
        _version_patch(simc_wow_version) != _version_patch(game_build)
    )
    data_mismatch = bool(effective_build) and bool(game_build) and effective_build != game_build
    return {
        "simc": simc_mismatch,
        "data": data_mismatch,
        "simc_wow_version": simc_wow_version,
        "data_build": effective_build,
        "game_build": game_build,
    }


@router.get("/status")
def status() -> dict:
    game_build = settings.refresh_wow_build()
    simc = simc_status()
    return {
        "simc": simc,
        "data": data_status(game_build),
        "gpu": gpu_status(),
        "threads": settings.threads,
        "wow_build": game_build,
        "mismatch": mismatch_status(simc, game_build, _effective_data_build()),
    }


def _install_job(tag: str | None):
    def run(ctx: JobContext) -> dict:
        def cb(message: str, done: int, total: int) -> None:
            ctx.progress("download" if "Download" in message else "install", done, total, message)

        inst = runtime.install(tag, cb)
        return {"message": f"Installed {inst.tag}", **inst.to_dict()}

    return run


@router.post("/simc/install", response_model=Job)
def install(req: InstallRequest | None = None) -> Job:
    tag = req.tag if req else None
    return manager.submit("simc_install", _install_job(tag), character=tag or "latest")
