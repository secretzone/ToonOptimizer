"""/api/data/* -- game-data routes (see API.md)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from toonopt.config import settings
from toonopt.data import items, loot, season, talents, wago
from toonopt.jobs import JobContext, manager
from toonopt.models import Item, Job

log = logging.getLogger(__name__)
router = APIRouter()


class RefreshBody(BaseModel):
    build: str | None = None


class DecodeBody(BaseModel):
    klass: str
    spec: str
    loadout: str


class EncodeBody(BaseModel):
    klass: str
    spec: str
    selections: dict | list[dict]
    hero_tree: int | str | None = None


class ModifyBody(BaseModel):
    klass: str
    spec: str
    base: str
    add: list[str] = []
    remove: list[str] = []


class NamesBody(BaseModel):
    klass: str
    spec: str
    loadout: str


def _run_refresh(build: str, progress: Any) -> dict:
    wago.refresh(build, lambda cur, tot, msg: progress("download", cur, tot, msg))
    progress("rebuild", 0, 0, "Rebuilding season and loot tables")
    season.load.cache_clear()
    loot.clear_db(build)
    if build == wago.build():
        season.write(build)
        loot.db(build)
    progress("done", 1, 1, "Data refreshed")
    return wago.status(build)


@router.post("/data/refresh", response_model=Job)
def refresh(body: RefreshBody | None = None) -> Job:
    build = (body.build if body and body.build else None) or settings.refresh_wow_build() or wago.build()

    def run(ctx: JobContext) -> dict:
        return _run_refresh(build, ctx.progress)

    return manager.submit("data_refresh", run)


@router.get("/data/season")
def get_season() -> dict:
    try:
        return season.load()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/data/loot/sources")
def loot_sources(klass: str = Query(...), spec: str = Query(...)) -> dict:
    _require_cache()
    return loot.sources(klass, spec)


@router.get("/data/recommendations")
def get_recommendations(klass: str = Query(...), spec: str = Query(...)) -> dict:
    _require_cache()
    return season.recommendations(klass, spec)


@router.get("/data/items/search")
def search_items(q: str = Query(""), klass: str | None = Query(None), spec: str | None = Query(None),
                  slot: str | None = Query(None), limit: int = Query(25)) -> dict:
    _require_cache()
    return {"items": items.search_items(q, klass, spec, slot, limit)}


@router.get("/data/items/{item_id}", response_model=Item)
def get_item(item_id: int, bonus_ids: str = Query(""), ilevel: str | None = Query(None),
             slot: str | None = Query(None), track: str | None = Query(None),
             rank: int | None = Query(None)) -> Item:
    _require_cache()
    ids = [int(b) for b in bonus_ids.replace(",", "/").split("/") if b.strip().isdigit()]
    ilvl = int(ilevel) if ilevel and ilevel.strip().isdigit() else None
    key = f"item:{item_id}"
    if track and rank is not None:
        track_ids, track_ilvl = items.resolve_track_rank(track, rank)
        if not track_ids:
            raise HTTPException(400, f"unknown track/rank: {track} {rank}")
        ids = ids + [b for b in track_ids if b not in ids]
        if track_ilvl is not None:
            ilvl = track_ilvl
        key = f"search:{item_id}:{'-'.join(str(b) for b in ids)}"
    try:
        return items.resolve_item(item_id, ids, ilvl, key=key, slot_hint=slot)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/data/talents/{klass}/{spec}")
def get_talents(klass: str, spec: str) -> dict:
    _require_cache()
    try:
        return talents.tree(klass, spec)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/data/talents/decode")
def decode_talents(body: DecodeBody) -> dict:
    _require_cache()
    try:
        return talents.decode(body.klass, body.spec, body.loadout)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/data/talents/encode")
def encode_talents(body: EncodeBody) -> dict:
    _require_cache()
    try:
        return {"string": talents.encode(body.klass, body.spec, body.selections, body.hero_tree)}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/data/talents/modify")
def modify_talents(body: ModifyBody) -> dict:
    _require_cache()
    try:
        return talents.modify(body.klass, body.spec, body.base, body.add, body.remove)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


@router.post("/data/talents/names")
def talent_names(body: NamesBody) -> dict:
    _require_cache()
    try:
        return talents.names(body.klass, body.spec, body.loadout)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e


def _require_cache() -> None:
    if not wago.is_ready():
        raise HTTPException(503, "game data not downloaded yet; POST /api/data/refresh first")
