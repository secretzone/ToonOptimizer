"""Gear Compare: named sets, each overriding some slots."""
from __future__ import annotations

from pydantic import BaseModel, Field

from toonopt.models import CharacterProfile, Item, ResultMeta, SimOptions, SimResult
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names


class GearSet(BaseModel):
    name: str
    changes: dict[str, Item] = Field(default_factory=dict)


def build(profile: CharacterProfile, options: SimOptions, sets: list[GearSet]) -> Plan:
    names = new_names()
    plan = Plan(simc_text="")
    for i, gs in enumerate(sets, 1):
        if not gs.changes:
            continue
        name = names.make(gs.name, hint=f"set{i}")
        overrides = [simc_input.item_line(item, slot) for slot, item in gs.changes.items()]
        plan.profilesets.append(Profileset(name=name, label=gs.name, overrides=overrides))
        plan.labels[name] = gs.name
        plan.meta[name] = ResultMeta(changes=dict(gs.changes), items=list(gs.changes.values()))
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(ctx, profile: CharacterProfile, options: SimOptions, sets: list[GearSet]) -> SimResult:
    plan = build(profile, options, sets)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    return apply_meta(res, plan)
