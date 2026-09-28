"""Advisor engine: synchronous (no SimC) "obvious upgrades" heuristics (see API.md "Advisor").

Unlike the sim engines under ``toonopt.sims``, this module never runs SimC -- it scores
candidate items against the character's stat priority and item level, using the same data
layer (``toonopt.data.loot``/``season``/``bonuses``) the sim engines use to build profilesets.
Everything here is heuristic and explicitly says so (in ``AdvisorResult.notes`` and each
candidate's ``reasons``); the ``sim_plan`` it returns is meant to be handed straight to
``POST /api/sims/droptimizer`` / ``/api/sims/upgrades`` / Top Gear to actually confirm a pick.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from toonopt.config import HISTORY_DIR
from toonopt.models import (
    AdvisorCandidate,
    AdvisorEquipped,
    AdvisorPathStep,
    AdvisorResult,
    AdvisorSimPlan,
    AdvisorSlot,
    AdvisorSource,
    AdvisorTier,
    AdvisorVerdict,
    CatalystSource,
    CharacterProfile,
    CraftedSource,
    DelveSource,
    DropSource,
    DungeonSource,
    EffortLevel,
    Item,
    ItemSource,
    RaidSource,
    StatPriority,
    WorldBossSource,
)

log = logging.getLogger(__name__)

DEFAULT_MIN_ILEVEL_GAIN = 6
DEFAULT_KEY_LEVEL = 10
DEFAULT_DELVE_TIER = 8
STAT_KEYS: tuple[str, ...] = ("crit", "haste", "mastery", "versatility")
_WEIGHT_STEPS: tuple[float, ...] = (1.0, 0.8, 0.6, 0.4)
_PRIMARY_WEIGHT = 1.2
MAX_CANDIDATES_PER_SLOT = 8
EFFORT_ORDER: tuple[EffortLevel, ...] = ("trivial", "easy", "medium", "hard", "very_hard")
_VERDICT_RANK: dict[AdvisorVerdict, int] = {
    "obvious": 0, "likely": 1, "sim_to_confirm": 2, "sidegrade": 3, "downgrade": 4,
}


class DataUnavailable(RuntimeError):
    pass


def available() -> bool:
    try:
        from toonopt.data import loot, season  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


# ---------------------------------------------------------------------------
# per-spec heuristic secondary-stat order (used only when no statweights job exists for this
# character -- see API.md "Advisor specifics": "order the rest by a per-spec default table ...
# cite it as heuristic". This is NOT derived from any sim; it is a rough categorisation by
# which secondary a spec's community consensus usually favours, purely to break ties between
# secondaries `recommendations()` doesn't rank (it only names the single "default" one).

_CRIT_FIRST = {
    "hunter_beast_mastery", "rogue_subtlety", "warlock_affliction",
    "mage_arcane", "priest_shadow", "druid_balance", "shaman_elemental", "evoker_devastation",
}
_MASTERY_FIRST = {
    "warrior_arms", "warrior_protection", "paladin_retribution", "paladin_protection", "paladin_holy",
    "death_knight_blood", "monk_brewmaster", "monk_mistweaver", "druid_guardian", "druid_restoration",
    "priest_discipline", "priest_holy", "shaman_restoration", "evoker_preservation", "evoker_augmentation",
}
# specs whose current-guide order isn't just "one stat first, generic order after" -- explicit
# full orders that override the three generic buckets below. Marksmanship: crit > mastery >
# versatility > haste (Wowhead/Icy Veins, checked 2026-09); haste is its worst secondary, not
# its second-best, so the generic crit-first bucket (crit/haste/mastery/versatility) was wrong
# for it. A Stat Weights sim run for this character overrides this table entirely regardless
# (see stat_priority_for) -- this heuristic only fires with no finished statweights job.
_SPEC_ORDER_OVERRIDE: dict[str, list[str]] = {
    "hunter_marksmanship": ["crit", "mastery", "versatility", "haste"],
}
# everything else (hunter_survival, rogue_assassination/outlaw, warrior_fury, death_knight_frost/unholy,
# shaman_enhancement, monk_windwalker, demon_hunter_*, mage_fire/frost, warlock_destruction/demonology,
# druid_feral) defaults to haste-first, the single most common secondary across current specs.


def _default_secondary_order(spec_key: str) -> list[str]:
    if spec_key in _SPEC_ORDER_OVERRIDE:
        return list(_SPEC_ORDER_OVERRIDE[spec_key])
    if spec_key in _CRIT_FIRST:
        return ["crit", "haste", "mastery", "versatility"]
    if spec_key in _MASTERY_FIRST:
        return ["mastery", "crit", "versatility", "haste"]
    return ["haste", "crit", "mastery", "versatility"]


# ---------------------------------------------------------------------------
# stat priority

def _find_statweights_job(character_name: str) -> tuple[str, dict] | None:
    """(job_id, result dict) of the newest finished ``statweights`` job for this character in
    ``history/``, or ``None``."""
    if not HISTORY_DIR.exists():
        return None
    best: tuple[str, str, dict] | None = None
    for jd in HISTORY_DIR.iterdir():
        jf = jd / "job.json"
        if not jf.is_file():
            continue
        try:
            job = json.loads(jf.read_text("utf-8"))
        except (ValueError, OSError):
            continue
        if job.get("type") != "statweights" or job.get("status") != "done":
            continue
        if (job.get("character") or "").strip().lower() != character_name.strip().lower():
            continue
        rf = jd / "result.json"
        if not rf.is_file():
            continue
        sort_key = job.get("finished") or job.get("created") or ""
        if best is not None and sort_key <= best[0]:
            continue
        try:
            result = json.loads(rf.read_text("utf-8"))
        except (ValueError, OSError):
            continue
        best = (sort_key, jd.name, result)
    return (best[1], best[2]) if best else None


def _stat_priority_from_recommendation(profile: CharacterProfile, season, loot) -> StatPriority:
    rec = season.recommendations(profile.klass, profile.spec)
    top_secondary = ((rec.get("gems") or {}).get("default") or {}).get("stat")
    prim = loot.primary_stat(profile.klass, profile.spec)
    key = loot.spec_key(profile.klass, profile.spec)
    secondaries: list[str] = []
    if top_secondary in STAT_KEYS:
        secondaries.append(top_secondary)
    for s in _default_secondary_order(key):
        if s not in secondaries:
            secondaries.append(s)
    order = ([prim] if prim else []) + secondaries
    weights: dict[str, float] = {}
    if prim:
        weights[prim] = _PRIMARY_WEIGHT
    for i, s in enumerate(secondaries):
        weights[s] = _WEIGHT_STEPS[i] if i < len(_WEIGHT_STEPS) else 0.2
    return StatPriority(source="recommendation", order=order, weights=weights)


def stat_priority_for(profile: CharacterProfile, season, loot, notes: list[str]) -> StatPriority:
    found = _find_statweights_job(profile.name)
    if found:
        job_id, result = found
        weights = ((result.get("stat_weights") or {}).get("normalized")) or {}
        if weights:
            order = sorted(weights, key=lambda k: weights[k], reverse=True)
            return StatPriority(source="statweights_job", order=order, weights=weights, job_id=job_id)
    notes.append(
        "Stat priority: no finished statweights sim found in history for this character; used the "
        "season's recommended flask/gem secondary for the top slot and a per-spec heuristic order "
        "for the rest (toonopt.advisor._default_secondary_order) -- this table is a rough community "
        "default, not a sim result; run Stat Weights for this character and its ranking overrides it."
    )
    return _stat_priority_from_recommendation(profile, season, loot)


def _stat_score(item: Item, primary_name: str, weights: dict[str, float]) -> float:
    total = 0.0
    for stat, amount in item.stats.items():
        key = primary_name if stat == "primary" else stat
        w = weights.get(key)
        if w:
            total += w * amount
    return round(total, 2)


# ---------------------------------------------------------------------------
# candidate pool (cached per (klass, spec, sources) -- API.md: "cache loot candidates per
# (spec, sources) in memory" for the <10s /obvious-upgrades budget)

_CANDIDATES_CACHE: dict[tuple, list[Item]] = {}


def _sources_key(sources: list[DropSource]) -> tuple:
    return tuple(tuple(sorted(s.model_dump().items())) for s in sources)


def clear_candidate_cache() -> None:
    _CANDIDATES_CACHE.clear()


def _candidates_cached(profile: CharacterProfile, sources: list[DropSource], loot) -> list[Item]:
    key = (loot.normalize_class(profile.klass), profile.spec, _sources_key(sources))
    cached = _CANDIDATES_CACHE.get(key)
    if cached is not None:
        return cached
    items = list(loot.candidates(profile, sources, "drop"))
    _CANDIDATES_CACHE[key] = items
    return items


def _default_sources(season, key_level: int, delve_tier: int, raid_difficulties: list[str] | None) -> list[DropSource]:
    s = season.load()
    diffs = raid_difficulties or ["lfr", "normal", "heroic", "mythic"]
    sources: list[DropSource] = []
    for r in s.get("raids", []):
        for diff in diffs:
            if diff in (r.get("difficulties") or {}):
                sources.append(RaidSource(instance_id=r["instance_id"], difficulty=diff))
    sources.append(DungeonSource(key_level=key_level, vault=False))
    sources.append(DungeonSource(key_level=key_level, vault=True))
    sources.append(WorldBossSource())
    for tier in {delve_tier, 11}:
        sources.append(DelveSource(tier=tier))
    return sources


def _currency_amount(profile: CharacterProfile, *, currency_id: int | None, name: str | None) -> int:
    """Owned amount of a currency (crest or item-backed, e.g. Spark of Tides), matched by id
    first and by exact (case-insensitive) name as a fallback."""
    if currency_id is not None:
        for c in profile.currencies:
            if c.id == currency_id:
                return c.amount
    if name:
        low = name.strip().lower()
        for c in profile.currencies:
            if (c.name or "").strip().lower() == low:
                return c.amount
    return 0


def _crest_amount(profile: CharacterProfile, crest: str) -> int:
    return next((c.amount for c in profile.currencies if c.crest == crest), 0)


def _worse_effort(a: EffortLevel, b: EffortLevel) -> EffortLevel:
    return a if EFFORT_ORDER.index(a) >= EFFORT_ORDER.index(b) else b


def _crafted_step_effort(crest: str | None) -> EffortLevel:
    if crest is None:
        return "medium"   # missing Spark of Tides: gated behind a weekly quest/crafting order
    return _crest_tier_effort(crest)


def _crafted_tier_candidates(
    profile: CharacterProfile, season, loot, stat_priority: StatPriority,
) -> tuple[dict[str, list[RawCandidate]], list[CraftedSource]]:
    """One candidate per ``season.json`` ``crafted.tiers`` entry (this season: 305 Spark-only,
    318 with 80 Hero-tier crests, 331 with 80 Myth-tier crests -- see ``data/season.py``'s
    ``CRAFTED`` docstring) instead of a single flat "Crafted gear <max ilvl>" candidate, each
    with its own cumulative path from scratch and an effort/reasons pair driven by the Spark and
    crests this character actually owns. Capped to the best-affordable tier plus the max tier
    per slot -- a full 3-tier ladder would otherwise eat most of the 8-per-slot cap on what is,
    functionally, one item."""
    secondaries = [s for s in stat_priority.order if s in STAT_KEYS]
    if len(secondaries) < 2:
        return {}, []
    crafted_cfg = season.load().get("crafted", {})
    tiers = sorted(crafted_cfg.get("tiers") or [], key=lambda t: t["ilevel"])
    if not tiers:
        return {}, []
    stats = (secondaries[0], secondaries[1])
    spark_name = crafted_cfg.get("spark_name") or "Spark"
    spark_owned = _currency_amount(profile, currency_id=crafted_cfg.get("spark_id"), name=spark_name)

    resolved: list[dict] = []
    for tier in tiers:
        path: list[AdvisorPathStep] = []
        extra_reasons: list[str] = []
        affordable = True
        worst: EffortLevel = "trivial"
        for step in tiers:
            if step["ilevel"] > tier["ilevel"]:
                break
            crest = step.get("crest")
            cost = int(step.get("cost") or 0)
            if crest is None:
                path.append(AdvisorPathStep(step=f"Craft with 1 {spark_name} ({step['ilevel']})"))
                if spark_owned < 1:
                    extra_reasons.append(f"needs 1 {spark_name}")
                    affordable = False
                    worst = _worse_effort(worst, _crafted_step_effort(None))
            else:
                owned = _crest_amount(profile, crest)
                path.append(AdvisorPathStep(step=f"+{cost} {crest} → {step['ilevel']}", crest=crest, cost=cost))
                if owned < cost:
                    extra_reasons.append(f"needs {cost - owned} more {crest}")
                    affordable = False
                    worst = _worse_effort(worst, _crafted_step_effort(crest))
        resolved.append({
            "ilevel": tier["ilevel"], "affordable": affordable,
            "effort": "trivial" if affordable else worst,
            "path": path, "reasons": extra_reasons,
        })

    affordable_tiers = [t for t in resolved if t["affordable"]]
    best = affordable_tiers[-1] if affordable_tiers else resolved[0]
    kept = {best["ilevel"]: best, resolved[-1]["ilevel"]: resolved[-1]}
    kept_tiers = sorted(kept.values(), key=lambda t: t["ilevel"])

    out: dict[str, list[RawCandidate]] = {}
    craft_sources: list[CraftedSource] = []
    for t in kept_tiers:
        src = CraftedSource(ilevel=t["ilevel"], stats=stats)
        craft_sources.append(src)
        try:
            resolved_items = list(loot.candidates(profile, [src], "drop"))
        except Exception:  # noqa: BLE001 - a class/spec season.py can't craft for just yields none
            resolved_items = []
        for item in resolved_items:
            new_item = item.model_copy(update={"key": f"{item.key}:{t['ilevel']}"})
            rc = RawCandidate(item=new_item, effort=t["effort"], weekly=False,
                               path=list(t["path"]), extra_reasons=list(t["reasons"]))
            for slot in _expand_slot(new_item):
                if slot in profile.equipped:
                    out.setdefault(slot, []).append(rc)
    return out, craft_sources


def _last_two_bosses(season_data: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in season_data.get("raids", []):
        bosses = sorted(r.get("bosses", []), key=lambda b: b.get("order", 0))
        out[r["name"]] = {b["name"] for b in bosses[-2:]}
    return out


def _vault_ilevels(season_data: dict) -> dict[int, int]:
    return {row["level"]: row["vault_ilevel"] for row in season_data.get("key_levels", [])
            if row.get("vault_ilevel") is not None}


def _effort_for_drop(source: ItemSource | None, item: Item, last_two: dict[str, set[str]],
                      vault_ilevels: dict[int, int]) -> tuple[EffortLevel, bool]:
    if source is None:
        return "medium", False
    t = source.type
    if t == "raid":
        diff = source.difficulty
        if diff in ("lfr", "normal"):
            return "easy", False
        if diff == "heroic":
            return "medium", False
        if diff == "mythic":
            if source.boss in last_two.get(source.name, set()):
                return "very_hard", False
            return "hard", False
        return "medium", False
    if t == "dungeon":
        level = source.key_level or 0
        weekly = vault_ilevels.get(level) == item.ilevel and item.ilevel != 0
        if level <= 8:
            return "easy", weekly
        if level <= 10:
            return "medium", weekly
        return "hard", weekly
    if t == "world_boss":
        return "easy", True
    if t == "delve":
        tier = source.key_level or 0
        return ("easy", False) if tier <= 8 else ("medium", False)
    if t == "crafted":
        return "easy", False
    return "medium", False


def _affordable(profile: CharacterProfile, crest: str | None, cost: int) -> bool:
    if not crest:
        return False
    amount = next((c.amount for c in profile.currencies if c.crest == crest), 0)
    return amount >= cost


def _crest_tier_effort(crest_name: str | None) -> EffortLevel:
    low = (crest_name or "").lower()
    if "myth" in low or "voidcore" in low:
        return "hard"
    if "hero" in low or "champion" in low:
        return "medium"
    return "easy"


def _current_track_info(item: Item) -> dict | None:
    try:
        from toonopt.data import bonuses
        from toonopt.data.season import UPGRADE_SEASON_ID
    except Exception:  # noqa: BLE001 - data layer optional
        return None
    return bonuses.upgrade_of(item.bonus_ids, season_id=UPGRADE_SEASON_ID)


def _upgrade_path(item: Item) -> list:
    try:
        from toonopt.data.season import upgrade_path
    except Exception:  # noqa: BLE001 - data layer optional
        return []
    try:
        return list(upgrade_path(item))
    except Exception:  # noqa: BLE001 - an item with no recognised track just yields []
        return []


def _max_item(item: Item) -> Item | None:
    steps = _upgrade_path(item)
    if not steps:
        return None
    target = steps[-1]
    return item.model_copy(update={
        "bonus_ids": list(target.bonus_ids), "ilevel": target.ilevel, "key": f"{item.key}:max",
    })


def _upgrade_cost_to_max(item: Item) -> tuple[int, str] | None:
    steps = _upgrade_path(item)
    if not steps:
        return None
    return sum(st.cost for st in steps), steps[-1].crest


def _drop_path(item: Item, source: ItemSource | None) -> list[AdvisorPathStep]:
    label = source.name if source else "Drop"
    if source and source.difficulty:
        label += f" ({source.difficulty.title()})"
    elif source and source.key_level:
        label += f" (+{source.key_level})"
    label += f" {item.ilevel}"
    steps = [AdvisorPathStep(step=label)]
    cost_info = _upgrade_cost_to_max(item)
    if cost_info:
        cost, crest = cost_info
        up = _current_track_info(item)
        if up:
            steps.append(AdvisorPathStep(
                step=f"Upgrade {up['track']} {up['level']}/{up['max']}→max ({cost} {crest})",
                crest=crest, cost=cost,
            ))
    return steps


@dataclass
class RawCandidate:
    item: Item
    effort: EffortLevel
    weekly: bool
    path: list[AdvisorPathStep] = field(default_factory=list)
    extra_reasons: list[str] = field(default_factory=list)   # e.g. "needs 72 more Myth Mistcrest"


def _catalyst_candidates(profile: CharacterProfile, season, loot) -> list[RawCandidate]:
    cat = season.catalyst()
    slots = set(cat.get("slots", []))
    out: list[RawCandidate] = []
    seen: set[int] = set()
    charges = profile.catalyst_charges or 0
    for item in [*profile.equipped.values(), *profile.bags]:
        if item.slot not in slots or item.id in seen:
            continue
        try:
            variant = season.catalyst_variant(item, loot.normalize_class(profile.klass))
        except Exception:  # noqa: BLE001 - a source item season.py can't catalyze just yields None
            variant = None
        if variant is None:
            continue
        seen.add(item.id)
        origin = item.source.name if item.source else item.name
        new_item = variant.model_copy(update={
            "name": f"{variant.name} (Catalyst)",
            "source": ItemSource(type="catalyst", name=f"Catalyst ({origin})"),
        })
        effort: EffortLevel = "trivial" if charges > 0 else "easy"
        path = [AdvisorPathStep(step=f"Catalyze your {item.name}", cost=1, crest=cat.get("currency_name"))]
        out.append(RawCandidate(item=new_item, effort=effort, weekly=False, path=path))
    return out


def _upgrade_candidate(item: Item, profile: CharacterProfile) -> RawCandidate | None:
    steps = _upgrade_path(item)
    if not steps:
        return None
    target = steps[-1]
    total_cost = sum(st.cost for st in steps)
    up = _current_track_info(item)
    cur_level = up["level"] if up else 0
    max_rank = (up.get("max") if up else 0) or target.rank
    new_item = item.model_copy(update={
        "bonus_ids": list(target.bonus_ids), "ilevel": target.ilevel,
        "key": f"upgrade:{item.key}:{target.rank}",
        "source": ItemSource(type="upgrade", name="Upgrade current gear"),
    })
    affordable = _affordable(profile, target.crest, total_cost)
    effort: EffortLevel = "trivial" if affordable else _crest_tier_effort(target.crest)
    track_name = up["track"] if up else target.crest
    label = f"Upgrade {track_name} {cur_level}/{max_rank}→{target.rank}/{max_rank} ({total_cost} {target.crest})"
    return RawCandidate(item=new_item, effort=effort, weekly=False,
                         path=[AdvisorPathStep(step=label, crest=target.crest, cost=total_cost)])


VOIDFORGE_CREST = "Ascendant Voidcore"


def _voidforge_candidate(item: Item, profile: CharacterProfile, season) -> RawCandidate | None:
    try:
        vf = season.voidforge_variant(item)
    except Exception:  # noqa: BLE001 - an item season.py can't Voidforge just yields None
        vf = None
    if vf is None:
        return None
    cost = 1
    affordable = _affordable(profile, VOIDFORGE_CREST, cost)
    effort: EffortLevel = "trivial" if affordable else "hard"
    new_item = vf.model_copy(update={"source": ItemSource(type="upgrade", name="Voidforge")})
    label = f"Voidforge (ilvl {item.ilevel} → {vf.ilevel}, {cost} {VOIDFORGE_CREST})"
    return RawCandidate(item=new_item, effort=effort, weekly=False,
                         path=[AdvisorPathStep(step=label, crest=VOIDFORGE_CREST, cost=cost)])


def _is_embellished(item: Item, season) -> bool:
    try:
        markers = set(season.load().get("crafted", {}).get("embellishment_marker_bonus_ids", []))
    except Exception:  # noqa: BLE001
        return False
    return bool(markers & set(item.bonus_ids))


def _expand_slot(item: Item) -> list[str]:
    if item.slot == "finger":
        return ["finger1", "finger2"]
    if item.slot == "trinket":
        return ["trinket1", "trinket2"]
    return [item.slot]


# ---------------------------------------------------------------------------
# verdict + candidate assembly

def _verdict(ilevel_gain: int, score_delta: float, eq_score: float, is_trinket: bool, is_weapon: bool,
             tier_changed: bool, embellished: bool, min_gain: int) -> AdvisorVerdict:
    if is_trinket or is_weapon or tier_changed or embellished:
        return "sim_to_confirm"
    if ilevel_gain >= min_gain and score_delta >= 0:
        return "obvious"
    if ilevel_gain >= min_gain and score_delta < 0:
        return "likely" if ilevel_gain >= 13 else "downgrade"
    if abs(ilevel_gain) < min_gain and score_delta > 0:
        return "sim_to_confirm"
    if ilevel_gain == 0 and abs(score_delta) <= 0.02 * max(abs(eq_score), 1.0):
        return "sidegrade"
    return "downgrade"


def _build_candidate(
    rc: RawCandidate, slot: str, equipped_item: Item, eq_score: float, weights: dict[str, float],
    primary_name: str, tier_set_id: int | None, tier_slots: set[str], equipped_tier_count: int,
    min_ilevel_gain: int, season,
) -> AdvisorCandidate:
    item = rc.item
    max_item = _max_item(item)
    score = _stat_score(item, primary_name, weights)
    score_delta = round(score - eq_score, 2)
    ilevel_gain = item.ilevel - equipped_item.ilevel
    ilevel_gain_max = (max_item.ilevel if max_item else item.ilevel) - equipped_item.ilevel

    reasons: list[str] = []
    if ilevel_gain > 0:
        reasons.append(f"+{ilevel_gain} ilvl")
    elif ilevel_gain < 0:
        reasons.append(f"{ilevel_gain} ilvl")
    if score_delta > 0:
        reasons.append("stats favor your priority")
    elif score_delta < 0:
        reasons.append("stats work against your priority")
    reasons.extend(rc.extra_reasons)

    is_trinket = slot.startswith("trinket")
    is_weapon = slot in ("main_hand", "off_hand")
    tier_changed = False
    if slot in tier_slots and tier_set_id is not None:
        was_tier = equipped_item.set_id == tier_set_id
        is_tier = item.set_id == tier_set_id
        if was_tier and not is_tier:
            if equipped_tier_count >= 4:
                reasons.append("loses 4pc")
                tier_changed = True
            elif equipped_tier_count == 2:
                reasons.append("loses 2pc")
                tier_changed = True
        elif not was_tier and is_tier:
            if equipped_tier_count == 3:
                reasons.append("completes 4pc")
                tier_changed = True
            elif equipped_tier_count == 1:
                reasons.append("completes 2pc")
                tier_changed = True
    if is_trinket:
        reasons.append("trinket: effect needs sim")
    embellished = _is_embellished(item, season)
    if embellished:
        reasons.append("embellishment: effect needs sim")

    verdict = _verdict(ilevel_gain, score_delta, eq_score, is_trinket, is_weapon, tier_changed,
                        embellished, min_ilevel_gain)

    path = list(rc.path)
    if max_item is not None and max_item.ilevel > item.ilevel and not path:
        cost_info = _upgrade_cost_to_max(item)
        if cost_info:
            cost, crest = cost_info
            path.append(AdvisorPathStep(step=f"Upgrade to max ({cost} {crest})", crest=crest, cost=cost))

    src = rc.item.source or ItemSource(type="equipped", name="Unknown")
    source = AdvisorSource(**src.model_dump(), effort=rc.effort, weekly=rc.weekly)

    return AdvisorCandidate(
        item=item, max_item=max_item if max_item is not None and max_item.ilevel != item.ilevel else None,
        source=source, ilevel_gain=ilevel_gain, ilevel_gain_max=ilevel_gain_max,
        stat_score=score, stat_score_delta=score_delta, verdict=verdict, reasons=reasons,
        path=path, alternatives=[],
    )


def _cap_candidates(candidates: list[AdvisorCandidate], limit: int = MAX_CANDIDATES_PER_SLOT) -> list[AdvisorCandidate]:
    if len(candidates) <= limit:
        return candidates
    order_index = {id(c): i for i, c in enumerate(candidates)}
    chosen: list[AdvisorCandidate] = []
    chosen_ids: set[int] = set()
    for tier in EFFORT_ORDER:
        if len(chosen) >= limit:
            break
        for c in candidates:
            if id(c) in chosen_ids:
                continue
            if c.source.effort == tier:
                chosen.append(c)
                chosen_ids.add(id(c))
                break
    for c in candidates:
        if len(chosen) >= limit:
            break
        if id(c) not in chosen_ids:
            chosen.append(c)
            chosen_ids.add(id(c))
    chosen.sort(key=lambda c: order_index[id(c)])
    return chosen[:limit]


def _bis_heuristic(candidates: list[AdvisorCandidate]) -> AdvisorCandidate | None:
    if not candidates:
        return None
    return max(candidates, key=lambda c: ((c.max_item or c.item).ilevel, c.stat_score))


def _build_slot(
    slot: str, equipped_item: Item, raw_items: list[RawCandidate], stat_priority: StatPriority,
    primary_name: str, tier_set_id: int | None, tier_slots: set[str], equipped_tier_count: int,
    min_ilevel_gain: int, include_downgrades: bool, season,
) -> AdvisorSlot:
    weights = stat_priority.weights or {}
    eq_score = _stat_score(equipped_item, primary_name, weights)
    up = _current_track_info(equipped_item)
    equipped = AdvisorEquipped(
        item=equipped_item, ilevel=equipped_item.ilevel, stat_score=eq_score,
        track=up["track"] if up else None,
        rank=f"{up['level']}/{up['max']}" if up and up.get("max") else None,
    )

    # group by item id so the same drop from multiple sources collapses to one candidate with
    # ``alternatives`` -- except crafted tiers, which deliberately stay separate top-level
    # candidates (one per ilvl tier: 305/318/331 this season) even though they share the
    # underlying crafted item id, per API.md's crafted-ladder carve-out; each tier already
    # carries its own distinct ``item.key`` (see ``_crafted_tier_candidates``).
    by_group: dict[object, list[RawCandidate]] = {}
    for rc in raw_items:
        src = rc.item.source
        group_key: object = rc.item.key if (src and src.type == "crafted") else rc.item.id
        by_group.setdefault(group_key, []).append(rc)

    candidates: list[AdvisorCandidate] = []
    for group in by_group.values():
        group.sort(key=lambda rc: (-rc.item.ilevel, EFFORT_ORDER.index(rc.effort)))
        primary_rc, *rest = group
        candidate = _build_candidate(primary_rc, slot, equipped_item, eq_score, weights, primary_name,
                                      tier_set_id, tier_slots, equipped_tier_count, min_ilevel_gain, season)
        alt_names: list[str] = []
        for rc in rest:
            src = rc.item.source
            name = src.name if src else ""
            if src and src.boss:
                name = f"{name}: {src.boss}"
            if name and name not in alt_names:
                alt_names.append(name)
        candidate.alternatives = alt_names
        candidates.append(candidate)

    if not include_downgrades:
        candidates = [c for c in candidates if c.verdict != "downgrade"]

    candidates.sort(key=lambda c: (_VERDICT_RANK[c.verdict], -max(0.0, c.stat_score_delta), -c.ilevel_gain))
    bis = _bis_heuristic(candidates)
    capped = _cap_candidates(candidates)
    return AdvisorSlot(slot=slot, equipped=equipped, candidates=capped, bis_heuristic=bis)


def _build_sim_plan(sources: list[DropSource], slots: list[AdvisorSlot], upgrade_slots: list[str],
                     have_catalyst: bool) -> AdvisorSimPlan:
    droptimizer = list(sources)
    if have_catalyst:
        droptimizer.append(CatalystSource(track="Myth"))
    topgear_keys: list[str] = []
    seen: set[str] = set()
    for slot in slots:
        for c in slot.candidates:
            if c.verdict == "downgrade":
                continue
            if c.source.type in ("bag", "vault", "catalyst") and c.item.key not in seen:
                topgear_keys.append(c.item.key)
                seen.add(c.item.key)
    note = (
        "Droptimizer: sim these sources (plus Catalyst, if listed) to confirm drop upgrades with real dps. "
        "Top Gear: add the listed candidate keys (bag/vault/catalyst items) as extra candidates. "
        "Upgrades: run on the listed slots to see gain-per-crest for in-place upgrades."
    )
    return AdvisorSimPlan(droptimizer=droptimizer, topgear_candidate_keys=topgear_keys,
                           upgrades_slots=upgrade_slots, note=note)


# ---------------------------------------------------------------------------
# entry point

def evaluate(
    profile: CharacterProfile, slug: str, *, key_level: int = DEFAULT_KEY_LEVEL,
    delve_tier: int = DEFAULT_DELVE_TIER, raid_difficulties: list[str] | None = None,
    min_ilevel_gain: int = DEFAULT_MIN_ILEVEL_GAIN, include_downgrades: bool = False,
) -> AdvisorResult:
    try:
        from toonopt.data import loot, season
    except Exception as e:
        raise DataUnavailable(f"game data layer unavailable: {e}") from e

    notes: list[str] = []
    stat_priority = stat_priority_for(profile, season, loot, notes)
    primary_name = loot.primary_stat(profile.klass, profile.spec) or "agility"

    sources = _default_sources(season, key_level, delve_tier, raid_difficulties)

    season_data = season.load()
    last_two = _last_two_bosses(season_data)
    vault_ilevels = _vault_ilevels(season_data)

    drop_items = _candidates_cached(profile, sources, loot)

    raw: dict[str, list[RawCandidate]] = {}
    for item in drop_items:
        effort, weekly = _effort_for_drop(item.source, item, last_two, vault_ilevels)
        rc = RawCandidate(item=item, effort=effort, weekly=weekly, path=_drop_path(item, item.source))
        for slot in _expand_slot(item):
            if slot in profile.equipped:
                raw.setdefault(slot, []).append(rc)

    # crafted gear is its own ladder (one candidate per tier, not a single drop source) -- see
    # _crafted_tier_candidates; kept out of `sources`/`drop_items` above so its per-tier
    # candidates don't get merged into one by the generic item-id/tag dedup `loot.candidates`
    # applies to every other source sharing a `sources` list.
    crafted_raw, crafted_sources = _crafted_tier_candidates(profile, season, loot, stat_priority)
    for slot, rcs in crafted_raw.items():
        raw.setdefault(slot, []).extend(rcs)

    catalyst_candidates = _catalyst_candidates(profile, season, loot)
    for rc in catalyst_candidates:
        raw.setdefault(rc.item.slot, []).append(rc)

    upgrade_slots: list[str] = []
    for slot, equipped_item in profile.equipped.items():
        uc = _upgrade_candidate(equipped_item, profile)
        if uc:
            raw.setdefault(slot, []).append(uc)
            upgrade_slots.append(slot)
        vf = _voidforge_candidate(equipped_item, profile, season)
        if vf:
            raw.setdefault(slot, []).append(vf)

    tier_set_id = season.catalyst_set_id(loot.normalize_class(profile.klass))
    tier_slots = set(season.catalyst().get("tier_slots", []))
    slots_with_tier = [s for s, it in profile.equipped.items() if tier_set_id is not None and it.set_id == tier_set_id]

    slots_out: list[AdvisorSlot] = []
    for slot, equipped_item in profile.equipped.items():
        slots_out.append(_build_slot(
            slot, equipped_item, raw.get(slot, []), stat_priority, primary_name, tier_set_id, tier_slots,
            len(slots_with_tier), min_ilevel_gain, include_downgrades, season,
        ))

    ilevel_equipped = round(sum(it.ilevel for it in profile.equipped.values()) / max(1, len(profile.equipped)), 2)
    sim_plan = _build_sim_plan(sources + crafted_sources, slots_out, upgrade_slots, bool(catalyst_candidates))

    return AdvisorResult(
        slug=slug, character=profile.name, klass=profile.klass, spec=profile.spec,
        stat_priority=stat_priority, ilevel_equipped=ilevel_equipped, slots=slots_out,
        tier=AdvisorTier(set_id=tier_set_id, equipped_pieces=len(slots_with_tier), slots_with_tier=slots_with_tier,
                          catalyst_charges=profile.catalyst_charges),
        sim_plan=sim_plan, notes=notes,
    )
