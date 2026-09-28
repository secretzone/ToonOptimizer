"""POST /sims/* - each submits a job to the manager and returns the Job."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toonopt.jobs import manager
from toonopt.models import CharacterProfile, DropSource, Item, Job, SimOptions
from toonopt.simc import runtime
from toonopt.simc.input import validate_options
from toonopt.sims import (
    advanced,
    consumables,
    droptimizer,
    gearcompare,
    gems,
    omnium,
    quick,
    statweights,
    talentcompare,
    topgear,
    upgrades,
)
from toonopt.sims.consumables import CustomConsumableSet
from toonopt.sims.gearcompare import GearSet
from toonopt.sims.gems import GemSet
from toonopt.sims.omnium import OmniumSet
from toonopt.sims.talentcompare import Loadout
from toonopt.sims.topgear import (
    CatalystRequest,
    CraftedRequest,
    SocketRequest,
    VoidforgeRequest,
)

router = APIRouter(prefix="/sims", tags=["sims"])


class SimRequest(BaseModel):
    profile: CharacterProfile
    options: SimOptions = Field(default_factory=SimOptions)


class TopGearRequest(SimRequest):
    candidate_keys: list[str] = Field(default_factory=list)
    max_combos: int = 500
    smart: bool = False
    min_ilevel: int | None = None
    loadouts: list[Loadout] | None = None       # each combo x each loadout; combo cap applies to the product (H6b)
    extra_items: list[Item] | None = None       # items from search, merged like bag candidates (key "search:...") (H7)
    catalyst: CatalystRequest | None = None     # Raidbots parity, wave 2
    add_socket: SocketRequest | None = None
    voidforge: VoidforgeRequest | None = None
    crafted: list[CraftedRequest] = Field(default_factory=list)


class DroptimizerRequest(SimRequest):
    sources: list[DropSource] = Field(default_factory=list)
    upgrade: str | int = "drop"
    min_ilevel: int | None = None
    upgrade_equipped: Literal["none", "match", "max"] = "none"
    include_offspec: bool = False
    include_catalyst: bool = False      # Raidbots parity, wave 2
    add_socket: bool = False
    preferred_gem: int | None = None


class StatWeightsRequest(SimRequest):
    stats: list[str] = Field(default_factory=list)


class GearCompareRequest(SimRequest):
    sets: list[GearSet] = Field(default_factory=list)


class TalentCompareRequest(SimRequest):
    loadouts: list[Loadout] = Field(default_factory=list)


class UpgradesRequest(SimRequest):
    slots: list[str] | None = None
    max_ranks: int | None = None
    min_ilevel: int | None = None


class GemsRequest(SimRequest):
    mode: str = "uniform"
    gem_pool: list[int] | None = None
    include_enchants: bool = True
    enchant_slots: list[str] | None = None
    sets: list[GemSet] = Field(default_factory=list)


class ConsumablesRequest(SimRequest):
    categories: list[str] | None = None
    custom: list[CustomConsumableSet] = Field(default_factory=list)


class OmniumRequest(SimRequest):
    mode: str = "per_row"
    sets: list[OmniumSet] = Field(default_factory=list)


class AdvancedRequest(BaseModel):
    simc_text: str
    options: SimOptions | None = None


def _require_simc() -> None:
    if runtime.installed() is None:
        raise HTTPException(503, "SimulationCraft is not installed; POST /api/simc/install first")


def _submit(job_type, fn, profile: CharacterProfile, options: SimOptions | None = None) -> Job:
    _require_simc()
    if options is not None:
        # fight_style/profile combinations rejected outright (e.g. DungeonSlice for the DH
        # specs it doesn't support) -- see simc/input.py::validate_options.
        try:
            validate_options(profile, options)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
    # `profile` is persisted alongside the job so toonopt.surrogate.dataset can later
    # reconstruct exact gear sets for every result row (see jobs.py JobManager._persist).
    return manager.submit(job_type, fn, character=profile.name, spec=profile.spec, profile=profile)


@router.post("/quick", response_model=Job)
def sim_quick(req: SimRequest) -> Job:
    return _submit("quick", lambda ctx: quick.execute(ctx, req.profile, req.options), req.profile, req.options)


@router.post("/topgear", response_model=Job)
def sim_topgear(req: TopGearRequest) -> Job:
    if req.max_combos < 1:
        raise HTTPException(400, "max_combos must be >= 1")
    return _submit(
        "topgear",
        lambda ctx: topgear.execute(
            ctx, req.profile, req.options, req.candidate_keys, req.max_combos, req.smart, req.min_ilevel,
            req.loadouts, req.extra_items, req.catalyst, req.add_socket, req.voidforge, req.crafted,
        ),
        req.profile, req.options,
    )


@router.post("/droptimizer", response_model=Job)
def sim_droptimizer(req: DroptimizerRequest) -> Job:
    if not droptimizer.available():
        raise HTTPException(503, "loot data layer (toonopt.data.loot) is not available yet")
    if not req.sources:
        raise HTTPException(400, "no drop sources selected")
    try:
        from toonopt.data.loot import validate_upgrade
        validate_upgrade(req.upgrade)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _submit(
        "droptimizer",
        lambda ctx: droptimizer.execute(
            ctx, req.profile, req.options, req.sources, req.upgrade, req.min_ilevel,
            req.upgrade_equipped, req.include_offspec, req.include_catalyst, req.add_socket,
            req.preferred_gem,
        ),
        req.profile, req.options,
    )


@router.post("/statweights", response_model=Job)
def sim_statweights(req: StatWeightsRequest) -> Job:
    return _submit(
        "statweights", lambda ctx: statweights.execute(ctx, req.profile, req.options, req.stats),
        req.profile, req.options,
    )


@router.post("/gearcompare", response_model=Job)
def sim_gearcompare(req: GearCompareRequest) -> Job:
    if not any(s.changes for s in req.sets):
        raise HTTPException(400, "no gear sets with changes")
    return _submit(
        "gearcompare", lambda ctx: gearcompare.execute(ctx, req.profile, req.options, req.sets),
        req.profile, req.options,
    )


@router.post("/talentcompare", response_model=Job)
def sim_talentcompare(req: TalentCompareRequest) -> Job:
    if not any(lo.string.strip() for lo in req.loadouts):
        raise HTTPException(400, "no loadouts")
    return _submit(
        "talentcompare", lambda ctx: talentcompare.execute(ctx, req.profile, req.options, req.loadouts),
        req.profile, req.options,
    )


@router.post("/upgrades", response_model=Job)
def sim_upgrades(req: UpgradesRequest) -> Job:
    if not upgrades.available():
        raise HTTPException(503, "season data layer (toonopt.data.season) is not available yet")
    return _submit(
        "upgrades",
        lambda ctx: upgrades.execute(ctx, req.profile, req.options, req.slots, req.max_ranks, req.min_ilevel),
        req.profile, req.options,
    )


@router.post("/gems", response_model=Job)
def sim_gems(req: GemsRequest) -> Job:
    if not gems.available():
        raise HTTPException(503, "season data layer (toonopt.data.season) is not available yet")
    if req.mode not in ("uniform", "per_socket", "custom"):
        raise HTTPException(400, f"invalid gems mode: {req.mode!r}")
    if req.mode == "custom" and not any(s.gems or s.enchants for s in req.sets):
        raise HTTPException(400, "custom mode needs at least one set with gems or enchants")
    # TooManyRows (like droptimizer's TooManyProfilesets) is only knowable once the plan is
    # built, which happens inside the job -- it surfaces as a failed job, not a 400 here.
    return _submit(
        "gems",
        lambda ctx: gems.execute(
            ctx, req.profile, req.options, req.mode, req.gem_pool, req.include_enchants,
            req.enchant_slots, req.sets,
        ),
        req.profile, req.options,
    )


@router.post("/consumables", response_model=Job)
def sim_consumables(req: ConsumablesRequest) -> Job:
    if not consumables.available():
        raise HTTPException(503, "season data layer (toonopt.data.season) is not available yet")
    bad = [c for c in (req.categories or []) if c not in consumables.CATEGORIES]
    if bad:
        raise HTTPException(400, f"invalid categories {bad}; valid: {list(consumables.CATEGORIES)}")
    # TooManyRows (like gems') is only knowable once the plan is built -- surfaces as a failed
    # job, not a 400 here.
    return _submit(
        "consumables",
        lambda ctx: consumables.execute(ctx, req.profile, req.options, req.categories, req.custom),
        req.profile, req.options,
    )


@router.post("/omnium", response_model=Job)
def sim_omnium(req: OmniumRequest) -> Job:
    if not omnium.available():
        raise HTTPException(503, "season data layer (toonopt.data.season) is not available yet")
    if req.mode not in omnium.MODES:
        raise HTTPException(400, f"invalid omnium mode: {req.mode!r}; valid: {list(omnium.MODES)}")
    if req.mode == "custom" and not req.sets:
        raise HTTPException(400, "custom mode needs at least one set")
    return _submit(
        "omnium",
        lambda ctx: omnium.execute(ctx, req.profile, req.options, req.mode, req.sets),
        req.profile, req.options,
    )


@router.post("/advanced", response_model=Job)
def sim_advanced(req: AdvancedRequest) -> Job:
    if not req.simc_text.strip():
        raise HTTPException(400, "empty simc_text")
    _require_simc()
    character, spec = advanced.describe(req.simc_text)
    return manager.submit("advanced", lambda ctx: advanced.execute(ctx, req.simc_text, req.options),
                          character=character, spec=spec)
