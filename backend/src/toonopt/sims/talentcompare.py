"""Talent Compare: one profileset per loadout string."""
from __future__ import annotations

from pydantic import BaseModel

from toonopt.models import CharacterProfile, ResultMeta, SimOptions, SimResult
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names


class Loadout(BaseModel):
    name: str
    string: str


def build(profile: CharacterProfile, options: SimOptions, loadouts: list[Loadout]) -> Plan:
    names = new_names()
    plan = Plan(simc_text="")
    for i, lo in enumerate(loadouts, 1):
        if not lo.string.strip():
            continue
        name = names.make(lo.name, hint=f"loadout{i}")
        plan.profilesets.append(Profileset(name=name, label=lo.name, overrides=[f"talents={lo.string.strip()}"]))
        plan.labels[name] = lo.name
        plan.meta[name] = ResultMeta(loadout=lo.string.strip())
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(ctx, profile: CharacterProfile, options: SimOptions, loadouts: list[Loadout]) -> SimResult:
    plan = build(profile, options, loadouts)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    return apply_meta(res, plan)
