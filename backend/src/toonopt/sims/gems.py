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
    if ref.get("limit"):                # unique gems: "Primary gem" would not say which one
        return ref["name"]
    return f"{ref['stat'].capitalize()} gem" if ref.get("stat") else ref["name"]


def _pad_gems(item: Item, n: int) -> list[int]:
    cur = list(item.gem_ids)[:n]
    return cur + [0] * (n - len(cur))


# ---------------------------------------------------------------------------
# unique-equipped gem limits
#
# Some gems are limited per character by an ItemLimitCategory shared across gem ids: every
# Eversong Diamond (any variant, any rank) counts against "Thalassian Diamond", max 1. A row
# that puts a limited gem in more sockets than its category allows is a setup the game
# refuses to equip, so every generated row is fitted to the limits before it is simmed.

Sockets = dict[str, list[int]]          # slot -> gem id per socket (0 = empty)
Pos = tuple[str, int]                   # (slot, socket index)


class _Limits:
    """gem id -> (category, max equipped), from ``recommendations.gems.unique`` (``limit`` /
    ``limit_category``) and, for gems outside the pool such as a lower-rank diamond the
    character already wears, ``season.gem_limit``."""

    def __init__(self, recs: dict, season_mod):
        self._lookup = getattr(season_mod, "gem_limit", None)
        self._name_lookup = getattr(season_mod, "gem_name", None)
        self._recs = recs
        self._known: dict[int, tuple[str, int] | None] = {}
        for g in recs["gems"]["unique"]:
            if g.get("limit"):
                self._known[int(g["id"])] = (g.get("limit_category") or f"gem {g['id']}", int(g["limit"]))

    def of(self, gem_id: int) -> tuple[str, int] | None:
        if not gem_id:
            return None
        if gem_id not in self._known:
            try:
                self._known[gem_id] = self._lookup(gem_id) if self._lookup else None
            except Exception:  # noqa: BLE001 - data layer optional
                self._known[gem_id] = None
        return self._known[gem_id]

    def name(self, gem_id: int) -> str:
        ref = _gem_ref(gem_id, self._recs)
        if ref["name"] != str(gem_id) or not self._name_lookup:
            return ref["name"]
        try:
            return self._name_lookup(gem_id) or str(gem_id)
        except Exception:  # noqa: BLE001 - data layer optional
            return str(gem_id)


def _positions(assign: Sockets) -> list[Pos]:
    return [(slot, i) for slot, gem_ids in assign.items() for i in range(len(gem_ids))]


def _fit_limits(assign: Sockets, limits: _Limits, filler: int, pinned: list[Pos] | None = None) -> list[tuple[Pos, int]]:
    """Replace limited gems over their category's cap with ``filler`` (in place).

    ``pinned`` sockets claim their category's allowance first (the gem a row is testing);
    the rest keep the first ones in slot order. Returns ``[(pos, removed gem id)]``.
    """
    pinned = pinned or []
    used: dict[str, int] = {}
    removed: list[tuple[Pos, int]] = []
    for slot, i in [*pinned, *(p for p in _positions(assign) if p not in pinned)]:
        gem_id = assign[slot][i]
        lim = limits.of(gem_id)
        if lim is None:
            continue
        category, cap = lim
        if used.get(category, 0) < cap:
            used[category] = used.get(category, 0) + 1
            continue
        assign[slot][i] = filler
        removed.append(((slot, i), gem_id))
    return removed


def _current_sockets(profile: CharacterProfile, bonuses_mod) -> Sockets:
    out: Sockets = {}
    for slot, item in profile.equipped.items():
        n = socket_count(item, bonuses_mod)
        if n > 0:
            out[slot] = _pad_gems(item, n)
    return out


def _changed(profile: CharacterProfile, current: Sockets, assign: Sockets, always: tuple[str, ...] = ()) -> dict:
    return {
        slot: profile.equipped[slot].model_copy(update={"gem_ids": gem_ids})
        for slot, gem_ids in assign.items()
        if gem_ids != current[slot] or slot in always
    }


def _socket_label(slot: str, i: int, assign: Sockets) -> str:
    return _slot_label(slot) if len(assign[slot]) == 1 else f"{_slot_label(slot)} socket {i + 1}"


def _removed_suffix(removed: list[tuple[Pos, int]], assign: Sockets, recs: dict, limits: _Limits, filler: int) -> str:
    if not removed:
        return ""
    parts = [
        f"{_socket_label(slot, i, assign)} {limits.name(old)} -> {_short_gem_label(filler, recs)}"
        for (slot, i), old in removed
    ]
    return f" ({'; '.join(parts)}: unique-equipped)"


def _limited_targets(current: Sockets, gem_id: int, limits: _Limits) -> list[Pos]:
    """Where a limited gem goes: sockets already holding its category (swap in place), then
    the neck, then the first sockets in equipped-slot order -- at most ``limit`` of them."""
    category, cap = limits.of(gem_id)
    positions = _positions(current)
    same = [p for p in positions if (lim := limits.of(current[p[0]][p[1]])) and lim[0] == category]
    neck = [p for p in positions if p[0] == "neck"]
    return list(dict.fromkeys([*same, *neck, *positions]))[:cap]


def _uniform_rows(profile: CharacterProfile, pool: list[int], recs: dict, bonuses_mod, season_mod) -> list[dict]:
    rows = []
    current = _current_sockets(profile, bonuses_mod)
    if not current:
        return rows
    limits = _Limits(recs, season_mod)
    filler = int(recs["gems"]["default"]["id"])
    for gem_id in pool:
        if limits.of(gem_id) is None:
            # every socket gets the gem, except a unique-equipped gem the character already
            # wears stays where it is (that is the limited-gem rows' question, not this one's)
            assign = {slot: [g if limits.of(g) else gem_id for g in gem_ids] for slot, gem_ids in current.items()}
            _fit_limits(assign, limits, filler)
            kept = [(s, i) for s, i in _positions(assign) if assign[s][i] != gem_id]
            label = f"All sockets: {_short_gem_label(gem_id, recs)}"
            if kept:
                label += " (kept " + ", ".join(
                    f"{limits.name(assign[s][i])} in {_socket_label(s, i, assign)}" for s, i in kept
                ) + ")"
        else:
            # a limited gem goes in at most `limit` sockets; every other socket keeps its gem
            targets = _limited_targets(current, gem_id, limits)
            assign = {slot: list(gem_ids) for slot, gem_ids in current.items()}
            for slot, i in targets:
                assign[slot][i] = gem_id
            removed = _fit_limits(assign, limits, filler, pinned=targets)
            where = ", ".join(_socket_label(s, i, assign) for s, i in targets)
            label = f"{where}: {limits.name(gem_id)}, other sockets unchanged"
            label += _removed_suffix(removed, assign, recs, limits, filler)
        changes = _changed(profile, current, assign)
        if changes:                     # e.g. the limited gem is already in its socket
            rows.append({"label": label, "changes": changes})

    rec_assign: Sockets = {}
    for slot in current:
        gem_ids = season_mod.best_gems(profile.equipped[slot], profile)
        if gem_ids:
            rec_assign[slot] = list(gem_ids)
    _fit_limits(rec_assign, limits, filler)
    if rec_assign:
        rows.append({
            "label": "Recommended",
            "changes": {s: profile.equipped[s].model_copy(update={"gem_ids": g}) for s, g in rec_assign.items()},
        })
    return rows


def _per_socket_rows(profile: CharacterProfile, pool: list[int], recs: dict, bonuses_mod, season_mod) -> list[dict]:
    rows = []
    current = _current_sockets(profile, bonuses_mod)
    limits = _Limits(recs, season_mod)
    filler = int(recs["gems"]["default"]["id"])
    for slot, gem_ids_now in current.items():
        for socket_index in range(len(gem_ids_now)):
            for gem_id in pool:
                assign = {s: list(g) for s, g in current.items()}
                assign[slot][socket_index] = gem_id
                # a second copy of a unique-equipped gem elsewhere would be unequippable:
                # that one becomes the stat gem, and the label says so
                removed = _fit_limits(assign, limits, filler, pinned=[(slot, socket_index)])
                ref = _gem_ref(gem_id, recs)
                label = f"{_slot_label(slot)} socket {socket_index + 1}: {_short_gem_label(gem_id, recs)}"
                label += _removed_suffix(removed, assign, recs, limits, filler)
                rows.append({
                    "label": label,
                    "changes": _changed(profile, current, assign, always=(slot,)),
                    "gem": GemChange(slot=slot, socket_index=socket_index, gem_id=gem_id,
                                     gem_name=ref["name"], stat=ref.get("stat", "")),
                })
    return rows


def _limit_violations(profile: CharacterProfile, sets: list[GemSet], recs: dict, season_mod) -> list[str]:
    """Custom sets are simmed as given; warn when one could not be equipped in game."""
    limits = _Limits(recs, season_mod)
    notes = []
    for gs in sets:
        counts: dict[str, list[int]] = {}
        for slot, item in profile.equipped.items():
            for g in gs.gems.get(slot, item.gem_ids):
                if (lim := limits.of(g)) is not None:
                    counts.setdefault(lim[0], [0, lim[1]])[0] += 1
        for category, (n, cap) in counts.items():
            if n > cap:
                notes.append(
                    f'Set "{gs.name}" equips {n} {category} gems but the game allows {cap}; '
                    "it was simmed as given and cannot be equipped in game."
                )
    return notes


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
        rows = _per_socket_rows(profile, pool, recs, bonuses_mod, season_mod)
    elif mode == "custom":
        rows = _custom_rows(profile, sets or [])
    else:
        raise ValueError(f"invalid gems mode: {mode!r}")

    notes: list[str] = []
    if mode == "custom":
        notes.extend(_limit_violations(profile, sets or [], recs, season_mod))
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
        enchant_rows, skipped = _enchant_rows(profile, recs, season_mod, enchant_slots)
        rows.extend(enchant_rows)
        utility_only = set(getattr(season_mod, "utility_enchant_slots", list)())
        utility = [s for s in skipped if s in utility_only]
        no_enchant_slots = [s for s in skipped if s not in utility_only]
        if utility:
            notes.append(
                f"Skipped {len(utility)} slot(s) with only utility enchants: {', '.join(utility)} "
                "(speed / leech / avoidance; no DPS effect to sim)."
            )
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
