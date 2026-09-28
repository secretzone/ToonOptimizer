"""GET /settings, PUT /settings (partial update)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from toonopt.config import Settings, settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=Settings)
def get_settings() -> Settings:
    return settings


@router.put("", response_model=Settings)
def update_settings(patch: dict) -> Settings:
    unknown = set(patch) - set(Settings.model_fields)
    if unknown:
        raise HTTPException(400, f"unknown settings: {', '.join(sorted(unknown))}")
    if "wow_build" in patch:
        raise HTTPException(400, "wow_build is computed automatically; set wow_build_override instead")
    try:
        merged = Settings.model_validate({**settings.model_dump(), **patch})
    except ValidationError as e:
        raise HTTPException(400, str(e)) from e
    for name in Settings.model_fields:
        setattr(settings, name, getattr(merged, name))
    if "wow_dir" in patch or "wow_build_override" in patch:
        settings.refresh_wow_build()
    settings.save()
    return settings
