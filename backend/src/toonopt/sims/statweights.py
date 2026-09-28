"""Stat Weights: ``calculate_scale_factors=1`` with ``scale_only=`` the requested stats."""
from __future__ import annotations

from toonopt.models import CharacterProfile, SimOptions, SimResult
from toonopt.simc import input as simc_input
from toonopt.sims.base import Plan, primary_stat

SECONDARY = ("crit", "haste", "mastery", "versatility")
# our names -> SimC scale_only names
SIMC_STAT = {
    "strength": "strength", "agility": "agility", "intellect": "intellect", "stamina": "stamina",
    "crit": "crit", "haste": "haste", "mastery": "mastery", "versatility": "versatility",
    "weapon_dps": "weapon_dps", "weapon_offhand_dps": "weapon_offhand_dps",
    "leech": "leech", "avoidance": "avoidance", "speed": "speed", "armor": "armor",
}


def default_stats(profile: CharacterProfile) -> list[str]:
    return [primary_stat(profile), *SECONDARY]


def build(profile: CharacterProfile, options: SimOptions, stats: list[str] | None = None) -> Plan:
    chosen = [s for s in (stats or default_stats(profile)) if s in SIMC_STAT] or default_stats(profile)
    extra = [
        "calculate_scale_factors=1",
        "scale_only=" + ",".join(SIMC_STAT[s] for s in chosen),
    ]
    return Plan(simc_text=simc_input.build(profile, options, extra_globals=extra))


def execute(ctx, profile: CharacterProfile, options: SimOptions, stats: list[str] | None = None) -> SimResult:
    plan = build(profile, options, stats)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res.results = []
    return res
