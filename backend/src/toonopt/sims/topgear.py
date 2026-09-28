"""Top Gear: every combination of equipped + selected bag/vault items.

Slot families: each armour slot on its own, ``finger`` (finger1+finger2 as an
unordered pair), ``trinket`` (same) and ``weapons`` (main_hand+off_hand with 2H /
1H+OH rules). The cross product of family options is simmed as profilesets. When it
exceeds ``max_combos`` a two-stage search is used by default: stage 1 sims every single
swap, keeps the top-N options per family (N chosen so the product fits), stage 2 sims
the pruned cross product.

``smart=True`` switches to the experimental GPU surrogate path (see
``toonopt.surrogate``) when a model has been trained for the profile's (klass, spec):
every valid combination is enumerated (bounded by ``_SMART_HARD_CAP``), scored with the
surrogate, and only the top ``max_combos`` of them -- plus every single-item swap, so no
obvious upgrade is missed -- are simmed exactly through SimC. Without a trained model it
falls back to the normal 2-stage search and reports that in the job's progress message.
"""
from __future__ import annotations

import itertools
import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from toonopt.models import CharacterProfile, Item, ResultMeta, SimOptions, SimResult
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import (
    Plan,
    apply_meta,
    apply_season,
    can_dual_wield,
    is_off_hand_only,
    is_two_hand,
    item_label,
    new_names,
    precision_stages,
    run_staged,
)
from toonopt.sims.talentcompare import Loadout

log = logging.getLogger(__name__)

WarnFn = Callable[[str], None]
_SMART_HARD_CAP = 2_000_000     # enumeration cap for the smart path; see _enumerate_idx_tuples

Assignment = dict[str, Item | None]
GENERIC = {"finger1": "finger", "finger2": "finger", "trinket1": "trinket", "trinket2": "trinket",
           "main_hand": "weapons", "off_hand": "weapons"}
FAMILY_SLOTS = {"finger": ("finger1", "finger2"), "trinket": ("trinket1", "trinket2"), "weapons": ("main_hand", "off_hand")}


# --------------------------------------------------------------------------------------
# Raidbots parity, wave 2: Catalyst / +socket / Voidforge / crafted-recraft variants.
# Variants are just extra candidate Items (same slot as their source, key prefixed
# catalyst:/socket:/voidforge:/crafted:) merged into the normal candidate pool -- families()
# groups them by slot exactly like any bag/vault/search candidate, no changes needed there.
# --------------------------------------------------------------------------------------


class CatalystRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)
    min_set_pieces: Literal[0, 2, 4] = 0


class SocketRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)
    gem_id: int | None = None


class VoidforgeRequest(BaseModel):
    keys: list[str] = Field(default_factory=list)


class CraftedRequest(BaseModel):
    key: str
    stats: tuple[str, str]
    embellishment_id: int | None = None
    quality_bonus: int | None = None


def _season_mod():
    try:
        from toonopt.data import season
        return season
    except Exception:  # noqa: BLE001 - data layer optional
        return None


def _pool_by_key(profile: CharacterProfile, extra_items: list[Item] | None = None) -> dict[str, Item]:
    pool: dict[str, Item] = {}
    for it in [*profile.equipped.values(), *profile.bags, *profile.vault, *(extra_items or [])]:
        pool[it.key] = it
    return pool


def _default_gem_id(profile: CharacterProfile, season) -> int | None:
    try:
        recs = season.recommendations(profile.klass, profile.spec)
        return int(recs["gems"]["default"]["id"])
    except Exception:  # noqa: BLE001 - best-effort default
        return None


def build_variant_candidates(
    profile: CharacterProfile,
    catalyst: CatalystRequest | None = None,
    add_socket: SocketRequest | None = None,
    voidforge: VoidforgeRequest | None = None,
    crafted: list[CraftedRequest] | None = None,
    extra_items: list[Item] | None = None,
    warn: WarnFn | None = None,
) -> list[Item]:
    """Catalyst/+socket/Voidforge/crafted-recraft twins for the requested keys, as extra
    candidate ``Item``s (key prefixed accordingly, label suffix baked into ``Item.name``
    per API.md's "human label suffix" contract). ``[]`` (with a warning, if any variants
    were requested) when the season data layer isn't available."""
    if not (catalyst or add_socket or voidforge or crafted):
        return []
    season = _season_mod()
    if season is None:
        if warn:
            warn("season data layer unavailable; catalyst/socket/voidforge/crafted variants skipped")
        return []
    pool = _pool_by_key(profile, extra_items)
    out: list[Item] = []

    def _get(key: str) -> Item | None:
        src = pool.get(key)
        if src is None and warn:
            warn(f"Skipping variant of unknown item key {key!r}")
        return src

    if catalyst:
        for key in catalyst.keys:
            src = _get(key)
            if src is None:
                continue
            try:
                variant = season.catalyst_variant(src, profile.klass)
            except Exception as e:  # noqa: BLE001 - a bad source item shouldn't crash the run
                log.warning("catalyst_variant(%s) failed: %s", key, e)
                variant = None
            if variant is None:
                continue
            out.append(variant.model_copy(update={"name": f"{variant.name} (Catalyst)"}))

    if add_socket:
        gem_id = add_socket.gem_id or _default_gem_id(profile, season)
        if gem_id:
            for key in add_socket.keys:
                src = _get(key)
                if src is None:
                    continue
                try:
                    variant = season.socket_variant(src, gem_id)
                except Exception as e:  # noqa: BLE001
                    log.warning("socket_variant(%s) failed: %s", key, e)
                    continue
                out.append(variant.model_copy(update={"name": f"{variant.name} (+socket)"}))
        elif warn:
            warn("add_socket requested but no gem_id given and no recommended gem found")

    if voidforge:
        for key in voidforge.keys:
            src = _get(key)
            if src is None:
                continue
            try:
                variant = season.voidforge_variant(src)
            except Exception as e:  # noqa: BLE001
                log.warning("voidforge_variant(%s) failed: %s", key, e)
                variant = None
            if variant is None:
                continue
            out.append(variant.model_copy(update={"name": f"{variant.name} (Voidforged)"}))

    if crafted:
        for req in crafted:
            src = _get(req.key)
            if src is None:
                continue
            try:
                variant = season.crafted_variant(src, tuple(req.stats), req.embellishment_id, req.quality_bonus)
            except Exception as e:  # noqa: BLE001
                log.warning("crafted_variant(%s) failed: %s", req.key, e)
                continue
            suffix = "/".join(s.title() for s in req.stats)
            out.append(variant.model_copy(update={"name": f"{variant.name} (recraft {suffix})"}))

    return out


@dataclass
class VariantLimits:
    """Extra ``_valid()`` context derived from the profile/season + this request's
    ``min_set_pieces`` (the only knob that isn't derivable from the profile alone)."""
    catalyst_charges: int | None = None
    min_set_pieces: int = 0
    catalyst_set_id: int | None = None
    vault_slots: tuple[str, ...] = ()
    max_embellished: int | None = None
    embellishment_bonus_ids: frozenset[int] = frozenset()


def _variant_limits(profile: CharacterProfile, min_set_pieces: int = 0) -> VariantLimits:
    season = _season_mod()
    if season is None:
        return VariantLimits(min_set_pieces=min_set_pieces)
    try:
        crafted_cfg = season.load().get("crafted", {})
        embellishment_ids: set[int] = set()
        for e in crafted_cfg.get("embellishments", []):
            if e.get("bonus"):
                embellishment_ids.add(int(e["bonus"]))
            if e.get("second_bonus"):
                embellishment_ids.add(int(e["second_bonus"]))
        return VariantLimits(
            catalyst_charges=profile.catalyst_charges,
            min_set_pieces=min_set_pieces,
            catalyst_set_id=season.catalyst_set_id(profile.klass),
            vault_slots=tuple(season.socket_rules().get("vault_slots", ())),
            max_embellished=crafted_cfg.get("max_embellished"),
            embellishment_bonus_ids=frozenset(embellishment_ids),
        )
    except Exception as e:  # noqa: BLE001 - a season.json hiccup shouldn't block plain Top Gear
        log.warning("_variant_limits failed: %s", e)
        return VariantLimits(catalyst_charges=profile.catalyst_charges, min_set_pieces=min_set_pieces)


@dataclass
class Family:
    name: str
    slots: tuple[str, ...]
    options: list[Assignment] = field(default_factory=list)   # options[0] is the equipped state


@dataclass
class Combo:
    assignment: Assignment          # only the changed slots
    label: str
    items: list[Item]
    predicted_norm: float | None = None    # smart mode: predicted dps / predicted baseline dps


def _key(item: Item | None) -> str | None:
    return item.key if item else None


def _family_of(slot: str) -> str:
    return GENERIC.get(slot, slot)


def _pair_options(equipped: tuple[Item | None, Item | None], pool: list[Item], slots: tuple[str, str]) -> list[Assignment]:
    """Unordered pairs of distinct items; ordered so that unchanged items stay in their slot."""
    e1, e2 = equipped
    seen: set[frozenset[str]] = set()
    opts: list[Assignment] = [{slots[0]: e1, slots[1]: e2}]
    seen.add(frozenset(k for k in (_key(e1), _key(e2)) if k))
    for a, b in itertools.combinations(pool, 2):
        if a.key == b.key or a.id == b.id:
            continue
        pair = frozenset((a.key, b.key))
        if pair in seen:
            continue
        seen.add(pair)
        # keep an item that is already equipped in its current slot
        if (e2 and a.key == e2.key) or (e1 and b.key == e1.key):
            a, b = b, a
        opts.append({slots[0]: a, slots[1]: b})
    if len(pool) == 1 and not (e1 and e2):     # only one ring available at all
        opts.append({slots[0]: pool[0], slots[1]: None})
    return opts


def _legal_slots(profile: CharacterProfile, item: Item) -> list[str] | None:
    """Legal SimC slots for a bag/vault candidate per the loot layer's class/spec rules
    (weapon/armour subclass, shields, held-in-off-hand, primary stat -- see
    ``toonopt.data.loot.usable_slots_for_profile``), or ``None`` when the data layer isn't
    importable at all -- callers then fall back to their old, unfiltered behaviour so Top
    Gear still works without it. The preflight import of ``toonopt.data.items`` (rather
    than just ``toonopt.data.loot``) matters: it's the module unit tests stub out to
    simulate "no data layer", and ``toonopt.data.loot`` itself may already be cached from
    an unrelated import elsewhere in the process.
    """
    try:
        import toonopt.data.items as _items_check  # noqa: F401 - see docstring: the real availability check
        from toonopt.data.loot import usable_slots_for_profile
    except Exception:  # noqa: BLE001 - data layer optional
        return None
    try:
        return usable_slots_for_profile(item, profile)
    except Exception as e:  # noqa: BLE001 - unresolved item data shouldn't crash the run
        log.warning("topgear: could not resolve %s (%s): %s", item.name or item.id, item.key, e)
        return []


def _legal(profile: CharacterProfile, item: Item, warn: WarnFn | None) -> bool:
    """Whether the class/spec can equip *item* at all. Always true when the data layer is
    unavailable (old, unfiltered behaviour); an item whose legality can't be determined
    (missing item data) is excluded with a warning instead of reaching SimC."""
    slots = _legal_slots(profile, item)
    if slots is None:
        return True
    if not slots and warn:
        warn(f"Skipping {item.name or item.id} ({item.key}): not usable by {profile.klass} {profile.spec}")
    return bool(slots)


def _weapon_options(profile: CharacterProfile, cands: list[Item]) -> list[Assignment]:
    emh, eoh = profile.equipped.get("main_hand"), profile.equipped.get("off_hand")
    equipped_keys = {_key(emh), _key(eoh)} - {None}
    dual = can_dual_wield(profile)
    weapon_cands = [c for c in cands if _family_of(c.slot) == "weapons"]

    def hand_ok(item: Item, hand: str) -> bool:
        if item.key in equipped_keys:
            return True                # already worn; trust it, no extra lookup needed
        slots = _legal_slots(profile, item)
        return slots is None or hand in slots

    mh_pool = ([emh] if emh else []) + [c for c in weapon_cands if not is_off_hand_only(c) and hand_ok(c, "main_hand")]
    oh_pool: list[Item] = ([eoh] if eoh else []) + [c for c in weapon_cands if is_off_hand_only(c) and hand_ok(c, "off_hand")]
    if dual:
        oh_pool += [c for c in mh_pool if not is_two_hand(c, profile) and hand_ok(c, "off_hand") and c.key not in {o.key for o in oh_pool}]
    opts: list[Assignment] = [{"main_hand": emh, "off_hand": eoh}]
    seen: set[tuple[str | None, str | None]] = {(_key(emh), _key(eoh))}

    def add(mh: Item | None, oh: Item | None) -> None:
        k = (_key(mh), _key(oh))
        if k in seen:
            return
        seen.add(k)
        opts.append({"main_hand": mh, "off_hand": oh})

    for mh in mh_pool:
        if is_two_hand(mh, profile):
            add(mh, None)
            continue
        ohs = [o for o in oh_pool if o.key != mh.key and o.id != mh.id and (dual or is_off_hand_only(o))]
        if not ohs:
            add(mh, eoh if (eoh and eoh.key != mh.key) else None)
        for oh in ohs:
            add(mh, oh)
    return opts


def families(profile: CharacterProfile, candidates: list[Item]) -> list[Family]:
    by_family: dict[str, list[Item]] = {}
    for c in candidates:
        by_family.setdefault(_family_of(c.slot), []).append(c)
    fams: list[Family] = []
    for slot in ("head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet"):
        eq = profile.equipped.get(slot)
        cands = by_family.get(slot, [])
        if not cands:
            continue
        opts: list[Assignment] = [{slot: eq}]
        for c in cands:
            if eq and c.key == eq.key:
                continue
            opts.append({slot: c})
        fams.append(Family(slot, (slot,), opts))
    for fam in ("finger", "trinket"):
        s1, s2 = FAMILY_SLOTS[fam]
        e1, e2 = profile.equipped.get(s1), profile.equipped.get(s2)
        cands = by_family.get(fam, [])
        if not cands:
            continue
        pool = [i for i in (e1, e2) if i] + [c for c in cands if c.key not in {_key(e1), _key(e2)}]
        fams.append(Family(fam, (s1, s2), _pair_options((e1, e2), pool, (s1, s2))))
    if by_family.get("weapons"):
        fams.append(Family("weapons", ("main_hand", "off_hand"), _weapon_options(profile, by_family["weapons"])))
    return [f for f in fams if len(f.options) > 1]


def _unique_limit(category: str) -> int:
    """Max items sharing a limit category. Embellished gear allows 2; anything else 1."""
    return 2 if "embellish" in category.lower() else 1


def _is_shared_category(category: str | None) -> bool:
    # The data layer reports the plain Unique-Equipped item flag as "Unique-Equipped";
    # that only forbids the same item twice (already enforced by id), not different items.
    return bool(category) and category.strip().lower().replace("_", "-") != "unique-equipped"


def _valid(full: Assignment, limits: VariantLimits | None = None) -> bool:
    limits = limits or VariantLimits()
    ids: list[int] = []
    cats: dict[str, int] = {}
    vault_count = 0
    catalyzed_count = 0
    socket_vault_count = 0
    set_piece_count = 0
    embellished_count = 0
    for slot, item in full.items():
        if item is None:
            continue
        ids.append(item.id)
        if item.key.startswith("vault:"):
            vault_count += 1
        if _is_shared_category(item.unique_equipped):
            cats[item.unique_equipped] = cats.get(item.unique_equipped, 0) + 1
        if item.key.startswith("catalyst:"):
            catalyzed_count += 1
        if item.key.startswith("socket:") and slot in limits.vault_slots:
            socket_vault_count += 1
        if limits.catalyst_set_id is not None and item.set_id == limits.catalyst_set_id:
            set_piece_count += 1
        if limits.embellishment_bonus_ids and (set(item.bonus_ids) & limits.embellishment_bonus_ids):
            embellished_count += 1
    if len(ids) != len(set(ids)):
        return False
    if vault_count > 1:          # at most one Great Vault item per combination (H2)
        return False
    if socket_vault_count > 1:   # at most one +socket item among the vault-reward slots (wave 2)
        return False
    if limits.catalyst_charges is not None and catalyzed_count > limits.catalyst_charges:
        return False
    if limits.min_set_pieces and set_piece_count < limits.min_set_pieces:
        return False
    if limits.max_embellished is not None and embellished_count > limits.max_embellished:
        return False
    return all(n <= _unique_limit(c) for c, n in cats.items())


def _full_and_changed(profile: CharacterProfile, fams: list[Family], idxs: tuple[int, ...]) -> tuple[Assignment, Assignment]:
    full: Assignment = {s: it for s, it in profile.equipped.items()}
    changed: Assignment = {}
    for fam, i in zip(fams, idxs, strict=True):
        for slot in fam.slots:
            new = fam.options[i].get(slot)
            full[slot] = new
            if _key(new) != _key(profile.equipped.get(slot)):
                changed[slot] = new
    return full, changed


def _combo_for_idxs(profile: CharacterProfile, fams: list[Family], idxs: tuple[int, ...],
                     min_set_pieces: int = 0) -> Combo | None:
    full, changed = _full_and_changed(profile, fams, idxs)
    if not changed or not _valid(full, _variant_limits(profile, min_set_pieces)):
        return None
    items = [it for it in changed.values() if it]
    label = ", ".join(f"{item_label(it)} [{slot}]" if it else f"empty [{slot}]" for slot, it in changed.items())
    return Combo(changed, label, items)


def combos_from(profile: CharacterProfile, fams: list[Family], picks: list[list[int]],
                 min_set_pieces: int = 0) -> list[Combo]:
    """Cross product of the chosen option indices per family, minus the all-equipped combo."""
    out: list[Combo] = []
    for idxs in itertools.product(*picks):
        if all(i == 0 for i in idxs):
            continue
        combo = _combo_for_idxs(profile, fams, idxs, min_set_pieces)
        if combo is not None:
            out.append(combo)
    return out


def combos_from_idxs(
    profile: CharacterProfile, fams: list[Family], idxs_list: list[tuple[int, ...]],
    predicted: dict[tuple[int, ...], float] | None = None, min_set_pieces: int = 0,
) -> list[Combo]:
    """Like ``combos_from`` but for an explicit list of index tuples (not a cross product) --
    used by the smart path, whose top-K picks are not one family's options held fixed."""
    out: list[Combo] = []
    for idxs in idxs_list:
        if all(i == 0 for i in idxs):
            continue
        combo = _combo_for_idxs(profile, fams, idxs, min_set_pieces)
        if combo is None:
            continue
        if predicted is not None:
            combo.predicted_norm = predicted.get(idxs)
        out.append(combo)
    return out


def combo_count(fams: list[Family]) -> int:
    return math.prod(len(f.options) for f in fams) - 1 if fams else 0


def _single_swap_idxs(fams: list[Family]) -> set[tuple[int, ...]]:
    """Index tuples for every single-item swap (one family away from all-equipped)."""
    n = len(fams)
    out: set[tuple[int, ...]] = set()
    for fi, fam in enumerate(fams):
        for oi in range(1, len(fam.options)):
            idxs = [0] * n
            idxs[fi] = oi
            out.add(tuple(idxs))
    return out


def _enumerate_idx_tuples(fams: list[Family], cap: int = _SMART_HARD_CAP) -> list[tuple[int, ...]]:
    """Every index tuple across all families (minus all-equipped), bounded by ``cap``.

    Combo spaces that fit under the cap are enumerated exactly. Larger ones (rare -- it
    takes several large families to exceed a couple million combos) are approximated by
    a uniform random sample of ``cap`` distinct tuples instead of the first ``cap`` in
    ``itertools.product`` order, so the sample isn't systematically biased toward options
    early in any one family's candidate list.
    """
    sizes = [len(f.options) for f in fams]
    total = math.prod(sizes) if sizes else 0
    if total <= cap + 1:
        return [idxs for idxs in itertools.product(*(range(s) for s in sizes)) if any(idxs)]
    rnd = random.Random(0)
    seen: set[tuple[int, ...]] = set()
    out: list[tuple[int, ...]] = []
    max_attempts = cap * 4
    attempts = 0
    while len(out) < cap and attempts < max_attempts:
        attempts += 1
        r = rnd.randrange(total)
        idxs = []
        rem = r
        for s in reversed(sizes):
            idxs.append(rem % s)
            rem //= s
        tup = tuple(reversed(idxs))
        if not any(tup) or tup in seen:
            continue
        seen.add(tup)
        out.append(tup)
    return out


def _plan(profile: CharacterProfile, options: SimOptions, combos: list[Combo],
          loadouts: list[Loadout] | None = None) -> Plan:
    """One profileset per combo, or per (combo, loadout) when *loadouts* is given -- each
    such profileset adds a ``talents=<string>`` override on top of the combo's gear
    changes (H6b). ``ResultMeta.loadout`` carries the loadout name and the label gets a
    "· <loadout>" suffix so multi-loadout results stay distinguishable.
    """
    names = new_names()
    plan = Plan(simc_text="")
    lo_list: list[Loadout | None] = list(loadouts) if loadouts else [None]
    i = 0
    for combo in combos:
        overrides_base = [simc_input.item_line(it, slot) if it else simc_input.empty_slot(slot)
                           for slot, it in combo.assignment.items()]
        for lo in lo_list:
            i += 1
            label = combo.label if lo is None else f"{combo.label} · {lo.name}"
            name = names.make(label, hint=f"c{i}")
            overrides = overrides_base if lo is None else [*overrides_base, f"talents={lo.string.strip()}"]
            plan.profilesets.append(Profileset(name=name, label=label, overrides=overrides))
            plan.labels[name] = label
            plan.meta[name] = ResultMeta(
                changes={s: it for s, it in combo.assignment.items() if it}, items=combo.items,
                loadout=None if lo is None else lo.name,
            )
            if combo.predicted_norm is not None:
                plan.predicted_norm[name] = combo.predicted_norm
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def select_candidates(
    profile: CharacterProfile, candidate_keys: list[str], warn: WarnFn | None = None,
    min_ilevel: int | None = None, extra_items: list[Item] | None = None,
) -> list[Item]:
    """Bag/vault/searched candidates matching *candidate_keys*, legal for the profile's
    class/spec.

    ``extra_items`` are items found via item search (key ``search:...``, H7) -- they don't
    live on the profile like bag/vault items do, so the caller sends them alongside the
    request and they're merged into the same pool, subject to the same ``min_ilevel`` and
    legality filtering. ``min_ilevel`` drops candidates below the threshold (equipped items
    are never part of this pool in the first place, so they can never be dropped by it).
    """
    wanted = set(candidate_keys)
    pool = [i for i in [*profile.bags, *profile.vault, *(extra_items or [])] if i.key in wanted]
    if min_ilevel is not None:
        pool = [i for i in pool if i.ilevel >= min_ilevel]
    return [i for i in pool if _legal(profile, i, warn)]


def prepare(
    profile: CharacterProfile, options: SimOptions, candidate_keys: list[str], warn: WarnFn | None = None,
    min_ilevel: int | None = None, extra_items: list[Item] | None = None,
    catalyst: CatalystRequest | None = None, add_socket: SocketRequest | None = None,
    voidforge: VoidforgeRequest | None = None, crafted: list[CraftedRequest] | None = None,
) -> tuple[CharacterProfile, list[Family]]:
    variants = build_variant_candidates(profile, catalyst, add_socket, voidforge, crafted, extra_items, warn)
    all_extra = [*(extra_items or []), *variants]
    cands = select_candidates(profile, [*candidate_keys, *(v.key for v in variants)], warn, min_ilevel, all_extra)
    if options.enchant_all or options.socket_all:
        profile = profile.model_copy(deep=True)
        for slot, it in list(profile.equipped.items()):
            profile.equipped[slot] = apply_season(it, slot, options, profile)
        cands = [apply_season(c, c.slot, options, profile) for c in cands]
    return profile, families(profile, cands)


def build(
    profile: CharacterProfile, options: SimOptions, candidate_keys: list[str], max_combos: int = 500,
    min_ilevel: int | None = None, extra_items: list[Item] | None = None,
    loadouts: list[Loadout] | None = None,
    catalyst: CatalystRequest | None = None, add_socket: SocketRequest | None = None,
    voidforge: VoidforgeRequest | None = None, crafted: list[CraftedRequest] | None = None,
) -> Plan:
    """Single-stage plan (full cross product, or stage-1 singles when it would exceed max_combos)."""
    profile, fams = prepare(profile, options, candidate_keys, min_ilevel=min_ilevel, extra_items=extra_items,
                             catalyst=catalyst, add_socket=add_socket, voidforge=voidforge, crafted=crafted)
    min_set_pieces = catalyst.min_set_pieces if catalyst else 0
    if combo_count(fams) <= max_combos:
        picks = [list(range(len(f.options))) for f in fams]
        return _plan(profile, options, combos_from(profile, fams, picks, min_set_pieces), loadouts=loadouts)
    return _plan(profile, options, _stage1_combos(profile, fams, min_set_pieces), loadouts=loadouts)


def _stage1_combos(profile: CharacterProfile, fams: list[Family], min_set_pieces: int = 0) -> list[Combo]:
    combos: list[Combo] = []
    for fi, fam in enumerate(fams):
        picks = [[0] for _ in fams]
        picks[fi] = list(range(len(fam.options)))
        combos.extend(combos_from(profile, fams, picks, min_set_pieces))
    return combos


def _prune(fams: list[Family], scores: dict[tuple[int, int], float], max_combos: int) -> list[list[int]]:
    """Per family: the equipped option plus its top-k single-swap alternatives.

    Alternatives that scored below the baseline are dropped outright; k is then
    shrunk on the family with the weakest k-th alternative until
    ``prod(k_f + 1) - 1 <= max_combos``.
    """
    ranked: list[list[int]] = []
    for fi, fam in enumerate(fams):
        base = scores.get((fi, 0), float("-inf"))
        idxs = [i for i in range(1, len(fam.options)) if scores.get((fi, i), float("-inf")) >= base]
        idxs.sort(key=lambda i: scores[(fi, i)], reverse=True)
        ranked.append(idxs)
    keep = [len(r) for r in ranked]
    while math.prod(k + 1 for k in keep) - 1 > max_combos and max(keep) > 0:
        def weakest(fi: int) -> float:
            k = keep[fi]
            return scores[(fi, ranked[fi][k - 1])] if k > 0 else float("inf")
        victim = min((fi for fi in range(len(keep)) if keep[fi] > 0), key=weakest)
        keep[victim] -= 1
    return [[0, *sorted(r[:k])] for r, k in zip(ranked, keep, strict=True)]


def _smart_available(klass: str, spec: str) -> bool:
    try:
        from toonopt.surrogate import model as surrogate_model
    except Exception:  # noqa: BLE001 - surrogate package itself missing is not fatal here
        return False
    return surrogate_model.has_model(klass, spec)


def _smart_select(ctx, profile: CharacterProfile, options: SimOptions, fams: list[Family], max_combos: int,
                   min_set_pieces: int = 0) -> list[Combo]:
    """Score every valid combo with the surrogate; return the top ``max_combos`` plus every
    single-item swap, as ``Combo`` objects carrying their predicted (dps / baseline dps)."""
    from toonopt.surrogate import model as surrogate_model
    from toonopt.surrogate.features import gear_vector

    limits = _variant_limits(profile, min_set_pieces)
    idx_tuples = _enumerate_idx_tuples(fams)
    scored_idxs: list[tuple[int, ...]] = []
    vectors: list[np.ndarray] = []
    for idxs in idx_tuples:
        full, changed = _full_and_changed(profile, fams, idxs)
        if not changed or not _valid(full, limits):
            continue
        scored_idxs.append(idxs)
        vectors.append(gear_vector(profile, full, options))
    ctx.check_cancelled()

    predicted: dict[tuple[int, ...], float] = {}
    if vectors:
        x = np.stack(vectors)
        chunks = []
        batch = 8192
        for s in range(0, len(x), batch):
            chunks.append(surrogate_model.predict(profile.klass, profile.spec, x[s:s + batch]))
            ctx.check_cancelled()
        preds = np.concatenate(chunks)
        predicted = dict(zip(scored_idxs, (float(v) for v in preds), strict=True))

    ranked = sorted(predicted, key=predicted.get, reverse=True)
    keep = max(0, max_combos - 1)          # leave room for the baseline profileset itself
    chosen = set(ranked[:keep]) | _single_swap_idxs(fams)
    return combos_from_idxs(profile, fams, sorted(chosen), predicted=predicted, min_set_pieces=min_set_pieces)


def _execute_precision(
    ctx, profile: CharacterProfile, options: SimOptions, fams: list[Family], max_combos: int,
    loadouts: list[Loadout] | None, min_set_pieces: int = 0,
) -> SimResult:
    """``options.precision`` path (H5): skip the family top-k prune entirely and instead
    hand a (bounded) candidate combo list to :func:`toonopt.sims.base.run_staged`, which
    narrows it down across increasingly tight target_errors. The candidate list is the
    full cross product when it fits under ``max_combos`` (adjusted for the loadout
    multiplier), else the single-swap set (same fallback ``execute`` uses for scoring in
    the non-precision 2-stage search) -- both are cheap enough to run once at
    ``target_error=1.0``, the first stage's precision.
    """
    n_loadouts = len(loadouts) if loadouts else 1
    max_combos_eff = max(1, max_combos // n_loadouts)
    if combo_count(fams) <= max_combos_eff:
        picks = [list(range(len(f.options))) for f in fams]
        combos = combos_from(profile, fams, picks, min_set_pieces)
    else:
        combos = _stage1_combos(profile, fams, min_set_pieces)
    full_plan = _plan(profile, options, combos, loadouts=loadouts)
    if not full_plan.profilesets:
        res = ctx.sim(full_plan.simc_text, options, klass=profile.klass, spec=profile.spec)
        return apply_meta(res, full_plan)

    def build_stage(stage_options: SimOptions, keep: set[str] | None) -> Plan:
        psets = full_plan.profilesets if keep is None else [
            ps for ps in full_plan.profilesets if ps.name in keep
        ]
        text = simc_input.build(profile, stage_options, psets)
        return Plan(text, full_plan.labels, full_plan.meta, psets, full_plan.predicted_norm, full_plan.notes)

    stages = precision_stages(options.precision)
    return run_staged(ctx, build_stage, options, stages, klass=profile.klass, spec=profile.spec)


def execute(ctx, profile: CharacterProfile, options: SimOptions, candidate_keys: list[str],
            max_combos: int = 500, smart: bool = False, min_ilevel: int | None = None,
            loadouts: list[Loadout] | None = None, extra_items: list[Item] | None = None,
            catalyst: CatalystRequest | None = None, add_socket: SocketRequest | None = None,
            voidforge: VoidforgeRequest | None = None, crafted: list[CraftedRequest] | None = None) -> SimResult:
    def warn(msg: str) -> None:
        log.warning("topgear: %s", msg)
        ctx.progress("candidates", 0, 0, msg)

    if min_ilevel is not None:
        skipped = sum(
            1 for i in [*profile.bags, *profile.vault, *(extra_items or [])]
            if i.key in set(candidate_keys) and i.ilevel < min_ilevel
        )
        if skipped:
            ctx.progress("candidates", 0, 0, f"Skipped {skipped} candidate(s) below min ilevel {min_ilevel}")
    profile, fams = prepare(profile, options, candidate_keys, warn, min_ilevel=min_ilevel, extra_items=extra_items,
                             catalyst=catalyst, add_socket=add_socket, voidforge=voidforge, crafted=crafted)
    min_set_pieces = catalyst.min_set_pieces if catalyst else 0
    n_loadouts = len(loadouts) if loadouts else 1
    if not fams:
        plan = _plan(profile, options, [], loadouts=loadouts)
        res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
        return apply_meta(res, plan)
    if options.precision:
        return _execute_precision(ctx, profile, options, fams, max_combos, loadouts, min_set_pieces)
    total = combo_count(fams) * n_loadouts
    if total <= max_combos:
        picks = [list(range(len(f.options))) for f in fams]
        plan = _plan(profile, options, combos_from(profile, fams, picks, min_set_pieces), loadouts=loadouts)
        res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
        return apply_meta(res, plan)

    max_combos_eff = max(1, max_combos // n_loadouts)

    if smart:
        if _smart_available(profile.klass, profile.spec):
            ctx.progress("smart", 0, 0, "Scoring gear combinations with the GPU surrogate model")
            combos = _smart_select(ctx, profile, options, fams, max_combos_eff, min_set_pieces)
            ctx.check_cancelled()
            plan = _plan(profile, options, combos, loadouts=loadouts)
            res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec,
                          stage_label=f"Smart ({len(combos)} combos)")
            res = apply_meta(res, plan)
            for row in res.results:
                norm = plan.predicted_norm.get(row.name)
                if norm is not None:
                    row.meta.predicted_dps = norm * res.baseline.dps
            return res
        ctx.progress(
            "smart", 0, 0,
            f"No surrogate model trained for {profile.klass}/{profile.spec} "
            "(POST /api/surrogate/train); falling back to the 2-stage search",
        )

    # stage 1: single swaps (loadout-agnostic scoring pass; loadouts are only crossed in
    # at stage 2, once the family top-k has been narrowed down)
    stage1 = _stage1_combos(profile, fams, min_set_pieces)
    plan1 = _plan(profile, options, stage1)
    res1 = apply_meta(ctx.sim(plan1.simc_text, options, klass=profile.klass, spec=profile.spec,
                              stage_label=f"Stage 1/2 ({len(stage1)} single swaps)"), plan1)
    ctx.check_cancelled()
    scores: dict[tuple[int, int], float] = {}
    by_label = {r.label: r.dps for r in res1.results}
    for fi, fam in enumerate(fams):
        scores[(fi, 0)] = res1.baseline.dps
        for oi in range(1, len(fam.options)):
            picks = [[0] for _ in fams]
            picks[fi] = [oi]
            c = combos_from(profile, fams, picks, min_set_pieces)
            if c:
                scores[(fi, oi)] = by_label.get(c[0].label, float("-inf"))
    picks = _prune(fams, scores, max_combos_eff)
    stage2 = combos_from(profile, fams, picks, min_set_pieces)
    singles = {c.label for c in stage1}
    if n_loadouts == 1 and all(c.label in singles for c in stage2):
        return res1
    plan2 = _plan(profile, options, stage2, loadouts=loadouts)
    res2 = ctx.sim(plan2.simc_text, options, klass=profile.klass, spec=profile.spec,
                   stage_label=f"Stage 2/2 ({len(stage2)} combos)")
    return apply_meta(res2, plan2)
