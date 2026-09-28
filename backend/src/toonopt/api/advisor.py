"""POST /advisor/obvious-upgrades (see API.md "Advisor")."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from toonopt import advisor, characters
from toonopt.models import AdvisorResult, CharacterProfile

router = APIRouter(prefix="/advisor", tags=["advisor"])


class AdvisorOptions(BaseModel):
    key_level: int | None = None
    delve_tier: int | None = None
    raid_difficulties: list[str] | None = None
    min_ilevel_gain: int | None = None
    include_downgrades: bool = False   # additive: API.md's verdict rules exclude downgrades unless set


class AdvisorRequest(BaseModel):
    slug: str | None = None
    profile: CharacterProfile | None = None
    options: AdvisorOptions | None = None


def _require_cache() -> None:
    from toonopt.data import wago
    if not wago.is_ready():
        raise HTTPException(503, "game data not downloaded yet; POST /api/data/refresh first")


@router.post("/obvious-upgrades", response_model=AdvisorResult)
def obvious_upgrades(req: AdvisorRequest) -> AdvisorResult:
    _require_cache()
    profile = req.profile
    slug = req.slug
    if profile is None:
        if not slug:
            raise HTTPException(400, "provide either 'slug' or 'profile'")
        profile = characters.get(slug)
        if profile is None:
            raise HTTPException(404, f"no saved character {slug!r}")
    if not slug:
        slug = characters.slugify(profile.name, profile.realm)

    opts = req.options or AdvisorOptions()
    kwargs: dict = {"include_downgrades": opts.include_downgrades}
    if opts.key_level is not None:
        kwargs["key_level"] = opts.key_level
    if opts.delve_tier is not None:
        kwargs["delve_tier"] = opts.delve_tier
    if opts.raid_difficulties is not None:
        kwargs["raid_difficulties"] = opts.raid_difficulties
    if opts.min_ilevel_gain is not None:
        kwargs["min_ilevel_gain"] = opts.min_ilevel_gain

    try:
        return advisor.evaluate(profile, slug, **kwargs)
    except advisor.DataUnavailable as e:
        raise HTTPException(503, str(e)) from e
