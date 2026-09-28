"""Consumables: one profileset per (category, accepted-name) option, held against the
character's current gear/talents, plus any custom named sets.

Options come from ``toonopt.data.season.consumable_options()`` (Raidbots parity, wave 2):
the exact SimC names ``SimulationCraft 1210-01`` accepts this season, already limited to the
explicit ``_2``-quality variant where the category has one (see data/README.md). Each row
overrides just its own ``<category>=`` actor line; everything else -- gear, talents, the
other consumable slots -- stays at whatever the baseline options/profile already carry.
"""
from __future__ import annotations

from pydantic import BaseModel

from toonopt.models import (
    CharacterProfile,
    ConsumableChange,
    ResultMeta,
    SimOptions,
    SimResult,
)
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names

MAX_ROWS = 300
CATEGORIES: tuple[str, ...] = ("flask", "food", "potion", "augmentation", "temporary_enchant")


class CustomConsumableSet(BaseModel):
    name: str
    flask: str = ""
    food: str = ""
    potion: str = ""
    augmentation: str = ""
    temporary_enchant: str = ""


class DataUnavailable(RuntimeError):
    pass


class TooManyRows(ValueError):
    pass


def available() -> bool:
    try:
        from toonopt.data.season import consumable_options  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


def _options() -> dict[str, list[dict]]:
    try:
        from toonopt.data.season import consumable_options
    except Exception as e:
        raise DataUnavailable(f"season data layer unavailable: {e}") from e
    return consumable_options()


def _category_label(cat: str) -> str:
    return cat.replace("_", " ").title()


def build(
    profile: CharacterProfile, options: SimOptions,
    categories: list[str] | None = None, custom: list[CustomConsumableSet] | None = None,
) -> Plan:
    opts = _options()
    cats = [c for c in (categories if categories is not None else list(CATEGORIES)) if c in CATEGORIES]
    current = {k: (getattr(options.consumables, k, "") or "") for k in CATEGORIES}
    names = new_names()
    plan = Plan(simc_text="")
    i = 0
    for cat in cats:
        for o in opts.get(cat, []):
            value = o["value"]
            if value == current.get(cat):
                continue    # already the baseline's own choice -- not a swap worth a row
            i += 1
            label = f"{_category_label(cat)}: {o['label']}"
            name = names.make(label, hint=f"c{i}")
            plan.profilesets.append(Profileset(name=name, label=label, overrides=[f"{cat}={value}"]))
            plan.labels[name] = label
            plan.meta[name] = ResultMeta(consumable=ConsumableChange(category=cat, name=o["label"]))
    for cs in custom or []:
        i += 1
        label = cs.name
        name = names.make(label, hint=f"c{i}")
        overrides = [f"{cat}={val}" for cat in CATEGORIES if (val := getattr(cs, cat, "") or "")]
        plan.profilesets.append(Profileset(name=name, label=label, overrides=overrides))
        plan.labels[name] = label
        plan.meta[name] = ResultMeta(loadout=cs.name)
    if len(plan.profilesets) > MAX_ROWS:
        raise TooManyRows(
            f"consumables would run {len(plan.profilesets)} rows (cap is {MAX_ROWS}); "
            "narrow the categories or custom sets"
        )
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(
    ctx, profile: CharacterProfile, options: SimOptions,
    categories: list[str] | None = None, custom: list[CustomConsumableSet] | None = None,
) -> SimResult:
    ctx.progress("candidates", 0, 0, "Building consumable rows")
    plan = build(profile, options, categories, custom)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res = apply_meta(res, plan)
    return res
