"""Upgrades: one profileset per (equipped slot, target rank strictly above current).

Track/rank detection and the crest ladder come from ``toonopt.data.season.upgrade_path``
(bonus ids, in turn, from ``toonopt.data.bonuses``). Slots whose current item carries no
recognised upgrade track (crafted gear, last season's leftovers, already max rank) are
skipped and counted in the job's progress message.

``UpgradeInfo.affordable`` compares ``cost`` against the profile's ``Currency`` whose
``crest`` matches this step's crest name (``toonopt.simc.profile`` parses those from the
addon export); ``None`` when the profile carries no currency info at all.
"""
from __future__ import annotations

from toonopt.models import (
    CharacterProfile,
    Item,
    ResultMeta,
    SimOptions,
    SimResult,
    UpgradeInfo,
    UpgradeStepInfo,
)
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names

MAX_PROFILESETS = 400


class DataUnavailable(RuntimeError):
    pass


class TooManyProfilesets(ValueError):
    pass


def available() -> bool:
    try:
        from toonopt.data.season import upgrade_path  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


def _current_track(item: Item) -> dict | None:
    try:
        from toonopt.data import bonuses
        from toonopt.data.season import UPGRADE_SEASON_ID
    except Exception as e:
        raise DataUnavailable(f"season data layer unavailable: {e}") from e
    return bonuses.upgrade_of(item.bonus_ids, season_id=UPGRADE_SEASON_ID)


def _upgrade_path(item: Item) -> list:
    try:
        from toonopt.data.season import upgrade_path
    except Exception as e:
        raise DataUnavailable(f"season data layer unavailable: {e}") from e
    return upgrade_path(item)


def _max_rank(track: str) -> int:
    from toonopt.data.season import load as season_load

    return int(season_load().get("upgrade_tracks", {}).get(track, {}).get("max") or 0)


def _slot_label(slot: str) -> str:
    return slot.replace("_", " ").title()


def _affordable(profile: CharacterProfile, crest: str, cost: int) -> bool | None:
    """``cost <= the profile's amount of `crest``; None when the profile carries no currency
    info at all (e.g. an armory import), vs. False when it does but has none of this crest."""
    if not profile.currencies:
        return None
    amount = next((c.amount for c in profile.currencies if c.crest == crest), 0)
    return amount >= cost


VOIDFORGE_TRACK = "Voidforged"
VOIDFORGE_CREST = "Ascendant Voidcore"


def _voidforge_variant(item: Item) -> Item | None:
    """``toonopt.data.season.voidforge_variant(item)`` (Raidbots parity, wave 2): the Myth-max
    twin with the season's Voidforge bonus id, or ``None`` when ``item`` isn't Voidforge-eligible
    (wrong slot, or not currently at Myth max rank) -- see season.py's own docstring for the
    full eligibility rule. Tolerant of the data layer being unavailable, like ``_current_track``/
    ``_upgrade_path``/``_max_rank`` above."""
    try:
        from toonopt.data.season import voidforge_variant
    except Exception:  # noqa: BLE001 - data layer optional
        return None
    try:
        return voidforge_variant(item)
    except Exception:  # noqa: BLE001 - an item season.py can't Voidforge just yields None
        return None


def build(
    profile: CharacterProfile, options: SimOptions, slots: list[str] | None = None,
    max_ranks: int | None = None, min_ilevel: int | None = None,
) -> tuple[Plan, int]:
    """Plan plus the count of requested slots skipped for lacking a recognised track."""
    names = new_names()
    plan = Plan(simc_text="")
    target_slots = slots if slots is not None else list(profile.equipped.keys())
    skipped_slots: list[str] = []
    n = 0
    for slot in target_slots:
        item = profile.equipped.get(slot)
        if item is None:
            continue
        if min_ilevel is not None and item.ilevel < min_ilevel:
            continue
        added_any = False
        up = _current_track(item)
        if up:
            steps = _upgrade_path(item)
            if max_ranks is not None:
                steps = steps[:max_ranks]
            if steps:
                added_any = True
                current_rank = up["level"]
                track = up["track"]
                max_rank = _max_rank(track) or (steps[-1].rank if steps else current_rank)
                for idx, step in enumerate(steps):
                    n += 1
                    path = steps[: idx + 1]
                    cost = sum(st.cost for st in path)
                    new_item = item.model_copy(update={"bonus_ids": list(step.bonus_ids), "ilevel": step.ilevel})
                    label = (
                        f"{_slot_label(slot)}: {track} {current_rank}/{max_rank} -> {step.rank}/{max_rank} "
                        f"(ilvl {item.ilevel} -> {step.ilevel}, {cost} {step.crest})"
                    )
                    name = names.make(label, hint=f"u{n}")
                    overrides = [simc_input.item_line(new_item, slot)]
                    plan.profilesets.append(Profileset(name=name, label=label, overrides=overrides))
                    plan.labels[name] = label
                    plan.meta[name] = ResultMeta(
                        changes={slot: new_item},
                        upgrade=UpgradeInfo(
                            slot=slot, item_id=item.id, track=track, from_rank=current_rank, to_rank=step.rank,
                            max_rank=max_rank, from_ilevel=item.ilevel, to_ilevel=step.ilevel, crest=step.crest,
                            cost=cost, steps=[UpgradeStepInfo(rank=st.rank, ilevel=st.ilevel, crest=st.crest, cost=st.cost)
                                              for st in path],
                            affordable=_affordable(profile, step.crest, cost),
                        ),
                    )
        # Voidforge step (Raidbots parity, wave 2): Myth-max weapons/trinkets (voidforged.slots)
        # gain one extra row regardless of whether the normal track above had anything left.
        vf = _voidforge_variant(item)
        if vf is not None:
            n += 1
            added_any = True
            cost = 1
            label = f"{_slot_label(slot)}: Voidforge (ilvl {item.ilevel} -> {vf.ilevel}, {cost} {VOIDFORGE_CREST})"
            name = names.make(label, hint=f"u{n}")
            overrides = [simc_input.item_line(vf, slot)]
            plan.profilesets.append(Profileset(name=name, label=label, overrides=overrides))
            plan.labels[name] = label
            plan.meta[name] = ResultMeta(
                changes={slot: vf},
                upgrade=UpgradeInfo(
                    slot=slot, item_id=item.id, track=VOIDFORGE_TRACK, from_rank=0, to_rank=1, max_rank=1,
                    from_ilevel=item.ilevel, to_ilevel=vf.ilevel, crest=VOIDFORGE_CREST, cost=cost,
                    steps=[UpgradeStepInfo(rank=1, ilevel=vf.ilevel, crest=VOIDFORGE_CREST, cost=cost)],
                    affordable=_affordable(profile, VOIDFORGE_CREST, cost),
                ),
            )
        if not added_any:
            skipped_slots.append(slot)
    if len(plan.profilesets) > MAX_PROFILESETS:
        raise TooManyProfilesets(
            f"upgrades would run {len(plan.profilesets)} profilesets (cap is {MAX_PROFILESETS}); "
            "narrow the selected slots or max_ranks"
        )
    if skipped_slots:
        plan.notes.append(
            f"Skipped {len(skipped_slots)} slot(s) with no remaining upgrade: "
            f"{', '.join(skipped_slots)} (already at max rank or no crest track)."
        )
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan, len(skipped_slots)


def execute(
    ctx, profile: CharacterProfile, options: SimOptions, slots: list[str] | None = None,
    max_ranks: int | None = None, min_ilevel: int | None = None,
) -> SimResult:
    ctx.progress("candidates", 0, 0, "Computing upgrade paths")
    plan, skipped = build(profile, options, slots, max_ranks, min_ilevel)
    if skipped:
        ctx.progress("candidates", 0, 0, f"Skipped {skipped} slot(s) without a recognised upgrade track")
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res = apply_meta(res, plan)
    res.notes = list(plan.notes)
    return res
