"""GET /characters, GET /characters/{slug}, DELETE /characters/{slug} (see API.md).

Backfill (seeding ``characters/`` from ``history/*/profile.json`` when empty) runs from
``toonopt.main``'s lifespan startup hook, not at import time here -- see
``toonopt.characters.backfill``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from toonopt import characters
from toonopt.models import CharacterProfile, CharacterSummary

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=list[CharacterSummary])
def list_characters() -> list[CharacterSummary]:
    return characters.list_characters()


@router.get("/{slug}", response_model=CharacterProfile)
def get_character(slug: str) -> CharacterProfile:
    profile = characters.get(slug)
    if profile is None:
        raise HTTPException(404, f"no saved character {slug!r}")
    return profile


@router.delete("/{slug}")
def delete_character(slug: str) -> dict:
    if not characters.delete(slug):
        raise HTTPException(404, f"no saved character {slug!r}")
    return {"ok": True}
