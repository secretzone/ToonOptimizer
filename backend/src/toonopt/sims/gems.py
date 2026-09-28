"""Gems & Enchants: uniform/per-socket/custom gem sets, plus enchant-option rows.

Socket counts come from ``toonopt.data.bonuses.socket_count`` (bonus ids), matching
``toonopt.data.season.best_gems``. Gem/enchant names, icons and the default pool come
from ``toonopt.data.season.recommendations`` -- the same source ``GET
/api/data/recommendations`` serves, so a "Recommended" row and the OptionsPanel tooltips
never disagree with what this engine actually simmed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from toonopt.models import (
    CharacterProfile,
    EnchantChange,
    GemChange,
    Item,
    ResultMeta,
    SimOptions,
    SimResult,
)
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names

MAX_ROWS = 400


class DataUnavailable(RuntimeError):
    pass


class TooManyRows(ValueError):
    pass


class GemSet(BaseModel):
    name: str
    gems: dict[str, list[int]] = Field(default_factory=dict)     # slot -> gem ids, one per socket
    enchants: dict[str, int] = Field(default_factory=dict)       # slot -> enchant id


def available() -> bool:
    try:
        from toonopt.data.season import recommendations  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


def _data():
    try:
        from toonopt.data import bonuses, season
    except Exception as e:
        raise DataUnavailable(f"season data layer unavailable: {e}") from e
    return bonuses, season


def socket_count(item: Item, bonuses_mod=None) -> int:
    bonuses_mod = bonuses_mod or _data()[0]
    n = bonuses_mod.socket_count(item.bonus_ids)
    if n == 0 and item.gem_ids:
        n = len(item.gem_ids)
    return max(0, n)


def _all_gem_refs(recs: dict) -> list[dict]:
    return [recs["gems"]["default"], *recs["gems"]["by_stat"].values(), *recs["gems"]["unique"]]


def default_pool(recs: dict) -> list[int]:
    """``recommendations.gems.by_stat`` values + unique, de-duplicated, id order preserved."""
    ids: list[int] = []
    seen: set[int] = set()
    for g in [*recs["gems"]["by_stat"].values(), *recs["gems"]["unique"]]:
        if g["id"] not in seen:
            seen.add(g["id"])
            ids.append(g["id"])
    return ids


def _gem_ref(gem_id: int, recs: dict) -> dict:
    for g in _all_gem_refs(recs):
        if g["id"] == gem_id:
            return g
    return {"id": gem_id, "name": str(gem_id), "icon": "", "stat": ""}


def _slot_label(slot: str) -> str:
    return slot.replace("_", " ").title()


def _short_gem_label(gem_id: int, recs: dict) -> str:
    ref = _gem_ref(gem_id, recs)
    return f"{ref['stat'].capitalize()} gem" if ref.get("stat") else ref["name"]


def _pad_gems(item: Item, n: int) -> list[int]:
    cur = list(item.gem_ids)[:n]
    return cur + [0] * (n - len(cur))


def _uniform_rows(profile: CharacterProfile, pool: list[int], recs: dict, bonuses_mod, season_mod) -> list[dict]:
    rows = []
    sockets = {slot: socket_count(it, bonuses_mod) for slot, it in profile.equipped.items()}
    slots_with_sockets = [s for s, n in sockets.items() if n > 0]
    if not slots_with_sockets:
        return rows
    for gem_id in pool:
        changes = {}
        for slot in slots_with_sockets:
            item = profile.equipped[slot]
            changes[slot] = item.model_copy(update={"gem_ids": [gem_id] * sockets[slot]})
        rows.append({"label": f"All sockets: {_short_gem_label(gem_id, recs)}", "changes": changes})
    rec_changes = {}
    for slot in slots_with_sockets:
        item = profile.equipped[slot]
        gem_ids = season_mod.best_gems(item, profile)
        if gem_ids:
            rec_changes[slot] = item.model_copy(update={"gem_ids": gem_ids})
    if rec_changes:
        rows.append({"label": "Recommended", "changes": rec_changes})
    return rows


def _per_socket_rows(profile: CharacterProfile, pool: list[int], recs: dict, bonuses_mod) -> list[dict]:
    rows = []
    for slot, item in profile.equipped.items():
        n = socket_count(item, bonuses_mod)
        for socket_index in range(n):
            for gem_id in pool:
                gem_ids = _pad_gems(item, n)
                gem_ids[socket_index] = gem_id
                new_item = item.model_copy(update={"gem_ids": gem_ids})
                ref = _gem_ref(gem_id, recs)
                label = f"{_slot_label(slot)} socket {socket_index + 1}: {_short_gem_label(gem_id, recs)}"
                rows.append({
                    "label": label,
                    "changes": {slot: new_item},
                    "gem": GemChange(slot=slot, socket_index=socket_index, gem_id=gem_id,
                                     gem_name=ref["name"], stat=ref.get("stat", "")),
                })
    return rows


def _custom_rows(profile: CharacterProfile, sets: list[GemSet]) -> list[dict]:
    rows = []
    for gs in sets:
        changes = {}
        for slot, gem_ids in gs.gems.items():
            item = profile.equipped.get(slot)
            if item is None:
                continue
            changes[slot] = item.model_copy(update={"gem_ids": list(gem_ids)})
        for slot, enchant_id in gs.enchants.items():
            item = changes.get(slot) or profile.equipped.get(slot)
            if item is None:
                continue
            changes[slot] = item.model_copy(update={"enchant_id": enchant_id})
        if changes:
            rows.append({"label": gs.name, "changes": changes})
    return rows


def _enchant_rows(
    profile: CharacterProfile, recs: dict, season_mod, enchant_slots: list[str] | None,
) -> tuple[list[dict], list[str]]:
    rows = []
    skipped: list[str] = []
    wanted = set(enchant_slots) if enchant_slots else None
    candidate_slots = [s for s in profile.equipped if wanted is None or s in wanted]
    for slot in candidate_slots:
        item = profile.equipped.get(slot)
        if item is None:
            continue
        options = recs.get("enchants", {}).get(slot)
        if not options:
            skipped.append(slot)      # slot has no enchant options this season
            continue
        if season_mod.best_enchant(slot, profile) is None:
            skipped.append(slot)      # e.g. an off-hand that isn't a weapon this run
            continue
        for opt in options:
            if item.enchant_id == opt["id"]:
                continue
            new_item = item.model_copy(update={"enchant_id": opt["id"]})
            rows.append({
                "label": f"{_slot_label(slot)} enchant: {opt['name']}",
                "changes": {slot: new_item},
                "enchant": EnchantChange(slot=slot, enchant_id=opt["id"], name=opt["name"], stat=opt.get("stat")),
            })
    return rows, skipped


def build(
    profile: CharacterProfile, options: SimOptions, mode: str, gem_pool: list[int] | None = None,
    include_enchants: bool = True, enchant_slots: list[str] | None = None, sets: list[GemSet] | None = None,
) -> Plan:
    bonuses_mod, season_mod = _data()
    recs = season_mod.recommendations(profile.klass, profile.spec)
    pool = gem_pool if gem_pool is not None else default_pool(recs)

    if mode == "uniform":
        rows = _uniform_rows(profile, pool, recs, bonuses_mod, season_mod)
    elif mode == "per_socket":
        rows = _per_socket_rows(profile, pool, recs, bonuses_mod)
    elif mode == "custom":
        rows = _custom_rows(profile, sets or [])
    else:
        raise ValueError(f"invalid gems mode: {mode!r}")

    notes: list[str] = []
    if mode in ("uniform", "per_socket"):
        no_socket_slots = [
            slot for slot, item in profile.equipped.items() if socket_count(item, bonuses_mod) == 0
        ]
        if no_socket_slots:
            notes.append(
                f"Skipped {len(no_socket_slots)} item(s) with no sockets: "
                f"{', '.join(no_socket_slots)} (item has no gem sockets)."
            )

    if include_enchants:
        enchant_rows, no_enchant_slots = _enchant_rows(profile, recs, season_mod, enchant_slots)
        rows.extend(enchant_rows)
        if no_enchant_slots:
            notes.append(
                f"Skipped {len(no_enchant_slots)} slot(s) with no enchant options: "
                f"{', '.join(no_enchant_slots)} (no enchant available for this slot)."
            )

    if len(rows) > MAX_ROWS:
        raise TooManyRows(
            f"gems/enchants would run {len(rows)} rows (cap is {MAX_ROWS}); narrow the gem pool, "
            "mode or enchant slots"
        )

    names = new_names()
    plan = Plan(simc_text="")
    plan.notes = notes
    for i, row in enumerate(rows, 1):
        name = names.make(row["label"], hint=f"g{i}")
        overrides = [simc_input.item_line(it, slot) for slot, it in row["changes"].items()]
        plan.profilesets.append(Profileset(name=name, label=row["label"], overrides=overrides))
        plan.labels[name] = row["label"]
        plan.meta[name] = ResultMeta(
            changes=dict(row["changes"]), items=list(row["changes"].values()),
            gem=row.get("gem"), enchant=row.get("enchant"),
        )
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(
    ctx, profile: CharacterProfile, options: SimOptions, mode: str, gem_pool: list[int] | None = None,
    include_enchants: bool = True, enchant_slots: list[str] | None = None, sets: list[GemSet] | None = None,
) -> SimResult:
    ctx.progress("candidates", 0, 0, f"Building {mode} gem/enchant rows")
    plan = build(profile, options, mode, gem_pool, include_enchants, enchant_slots, sets)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res = apply_meta(res, plan)
    res.notes = list(plan.notes)
    return res
