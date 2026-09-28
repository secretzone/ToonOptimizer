"""Quick Sim: the actor as-is, no profilesets."""
from __future__ import annotations

from toonopt.models import CharacterProfile, SimOptions, SimResult
from toonopt.simc import input as simc_input
from toonopt.sims.base import Plan


def build(profile: CharacterProfile, options: SimOptions) -> Plan:
    return Plan(simc_text=simc_input.build(profile, options))


def execute(ctx, profile: CharacterProfile, options: SimOptions) -> SimResult:
    plan = build(profile, options)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res.results = []
    return res
