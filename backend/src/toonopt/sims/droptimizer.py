"""Droptimizer: one profileset per (candidate drop, concrete slot).

Candidates come from ``toonopt.data.loot.candidates(profile, sources, upgrade)``;
rings/trinkets are simmed in both slots and both rows are kept.
"""
from __future__ import annotations

from toonopt.models import (
    CatalystSource,
    CharacterProfile,
    DropSource,
    Group,
    Item,
    ItemSource,
    ResultMeta,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import (
    Plan,
    apply_meta,
    apply_season,
    is_off_hand_only,
    is_two_hand,
    item_label,
    new_names,
    precision_stages,
    run_staged,
)

MAX_PROFILESETS = 2000

# ItemSource.type -> Group.kind (droptimizer candidates are one of these five drop kinds --
# see data/loot.py candidates() -- plus "catalyst" for Raidbots parity wave 2 twins, which
# never come from data/loot.py itself: see include_catalyst/CatalystSource below).
_SOURCE_KIND: dict[str, str] = {
    "raid": "boss", "dungeon": "dungeon", "world_boss": "world_boss", "delve": "delve", "crafted": "crafted",
    "catalyst": "catalyst",
}


class DataUnavailable(RuntimeError):
    pass


class TooManyProfilesets(ValueError):
    pass


def available() -> bool:
    try:
        from toonopt.data.loot import candidates  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


def fetch_candidates(profile: CharacterProfile, sources: list[DropSource], upgrade: str | int,
                      include_offspec: bool = False) -> list[Item]:
    try:
        from toonopt.data.loot import candidates
    except Exception as e:
        raise DataUnavailable(f"loot data layer unavailable: {e}") from e
    return list(candidates(profile, sources, upgrade, offspec=include_offspec))


def _upgrade_path(item: Item) -> list:
    """``toonopt.data.season.upgrade_path(item)``, tolerant of the data layer being
    unavailable (mirrors ``sims/upgrades.py``'s own private hook of the same name --
    kept separate so each engine's tests can stub it independently)."""
    try:
        from toonopt.data.season import upgrade_path
    except Exception:  # noqa: BLE001 - data layer optional
        return []
    try:
        return list(upgrade_path(item))
    except Exception:  # noqa: BLE001 - an item with no recognised track just yields []
        return []


# --------------------------------------------------------------------------------------
# Raidbots parity, wave 2: Catalyst twins (include_catalyst, CatalystSource) and vault
# +socket drops (add_socket). Catalyzed twins always carry ``source.type="catalyst"``
# regardless of where they came from, and are grouped together (kind "catalyst") by
# build_groups() via _group_info() above.
# --------------------------------------------------------------------------------------

def _season_mod():
    try:
        from toonopt.data import season
        return season
    except Exception:  # noqa: BLE001 - data layer optional
        return None


def _default_gem_id(profile: CharacterProfile, season) -> int | None:
    try:
        recs = season.recommendations(profile.klass, profile.spec)
        return int(recs["gems"]["default"]["id"])
    except Exception:  # noqa: BLE001 - best-effort default
        return None


def _catalyst_twin(item: Item, profile: CharacterProfile, season) -> Item | None:
    """``item``'s catalyzed twin (Raidbots parity wave 2's ``include_catalyst``), tagged
    ``source.type="catalyst"`` regardless of the drop's own original source."""
    try:
        variant = season.catalyst_variant(item, profile.klass)
    except Exception:  # noqa: BLE001 - a source item season.py can't catalyze just yields None
        return None
    if variant is None:
        return None
    origin = item.source.name if item.source else item.name
    return variant.model_copy(update={
        "name": f"{variant.name} (Catalyst)",
        "source": ItemSource(type="catalyst", name=f"Catalyst ({origin})"),
    })


def _bump_to_track(item: Item, track: str, rank: int | None, season) -> Item | None:
    """``item`` with its current upgrade-track bonus id replaced by ``track``/``rank``
    (default: that track's max rank), so a :class:`CatalystSource` can catalyze the
    character's own gear "as if" it were upgraded to a track/rank it isn't at yet.
    ``None`` when ``item`` carries no recognised upgrade-track bonus id at all."""
    from toonopt.data import bonuses

    up = bonuses.upgrade_of(item.bonus_ids, season_id=season.UPGRADE_SEASON_ID)
    tracks = season.load().get("upgrade_tracks", {})
    t = tracks.get(track)
    if not up or not t or not t.get("bonus_ids"):
        return None
    idx = (rank or len(t["bonus_ids"])) - 1
    idx = max(0, min(idx, len(t["bonus_ids"]) - 1))
    new_bonus_ids = [t["bonus_ids"][idx] if b == up["bonus_id"] else b for b in item.bonus_ids]
    return item.model_copy(update={"bonus_ids": new_bonus_ids, "ilevel": int(t["ilevels"][idx])})


def _catalyst_source_items(profile: CharacterProfile, src: CatalystSource, season) -> tuple[list[Item], int]:
    """One catalyzed twin per equipped/bag item in a Catalyst slot, first bumped to
    ``src.track``/``src.rank`` (see :func:`_bump_to_track`). Returns ``(items, charges_used)``."""
    cat = season.catalyst()
    slots = set(cat.get("slots", []))
    out: list[Item] = []
    seen_keys: set[str] = set()
    for item in [*profile.equipped.values(), *profile.bags]:
        if item.slot not in slots or item.key in seen_keys:
            continue
        bumped = _bump_to_track(item, src.track, src.rank, season)
        if bumped is None:
            continue
        try:
            variant = season.catalyst_variant(bumped, profile.klass)
        except Exception:  # noqa: BLE001
            variant = None
        if variant is None:
            continue
        seen_keys.add(item.key)
        rank_label = f" {src.rank}" if src.rank else ""
        out.append(variant.model_copy(update={
            "key": f"catalyst:{src.track}{rank_label}:{item.key}",
            "name": f"{variant.name} (Catalyst)",
            "source": ItemSource(type="catalyst", name=f"Catalyst ({src.track}{rank_label})"),
        }))
    return out, len(out)


def _apply_vault_socket(item: Item, profile: CharacterProfile, preferred_gem: int | None, season) -> Item:
    """``item`` with an extra socket (bonus 1808 + gem) when its slot is one of the season's
    vault-reward socket slots (``sockets.vault_slots``); unchanged otherwise."""
    try:
        rules = season.socket_rules()
    except Exception:  # noqa: BLE001
        return item
    if item.slot not in rules.get("vault_slots", []):
        return item
    gem_id = preferred_gem or _default_gem_id(profile, season)
    if not gem_id:
        return item
    try:
        variant = season.socket_variant(item, gem_id)
    except Exception:  # noqa: BLE001
        return item
    return variant.model_copy(update={"name": f"{variant.name} (+socket)"})


def upgrade_equipped_items(
    profile: CharacterProfile, mode: str, reference_ilevel: int | None,
) -> tuple[CharacterProfile, list[str]]:
    """Deep-copy ``profile`` and bump every equipped item that carries a recognised upgrade
    track (``season.upgrade_path``) along that track, for a fairer baseline-vs-drop
    comparison. ``mode="max"`` goes to the item's own top rank; ``mode="match"`` goes to the
    highest rank whose ilevel does not exceed ``reference_ilevel`` (the droptimizer's own
    ``upgrade`` selection already resolved this run's fetched drop candidates to a concrete
    ilevel -- the highest of those is what "the drop upgrade level chosen" means here).
    ``mode="none"`` (or no items on a recognised track) returns ``profile`` unchanged.

    Returns the (possibly new) profile and the list of slots that were actually upgraded,
    for the droptimizer's result note.
    """
    if mode == "none":
        return profile, []
    new_profile = profile.model_copy(deep=True)
    upgraded: list[str] = []
    for slot, item in list(new_profile.equipped.items()):
        steps = _upgrade_path(item)
        if not steps:
            continue
        if mode == "max":
            target = steps[-1]
        else:  # "match"
            eligible = [s for s in steps if reference_ilevel is not None and s.ilevel <= reference_ilevel]
            if not eligible:
                continue
            target = eligible[-1]
        new_profile.equipped[slot] = item.model_copy(
            update={"bonus_ids": list(target.bonus_ids), "ilevel": target.ilevel}
        )
        upgraded.append(slot)
    return new_profile, upgraded


def _group_info(source: ItemSource | None) -> tuple[str, str, str] | None:
    """(key, label, kind) grouping bucket for a drop's source (see API.md's droptimizer
    ``groups`` contract), or None for a source type that isn't one of the five drop kinds
    (droptimizer candidates never carry equipped/bag/vault sources, but stay defensive)."""
    if source is None or source.type not in _SOURCE_KIND:
        return None
    kind = _SOURCE_KIND[source.type]
    if source.type == "raid":
        diff = (source.difficulty or "").title()
        return (f"raid:{source.name}:{source.difficulty}:{source.boss}", f"{source.name} ({diff}): {source.boss}", kind)
    if source.type == "dungeon":
        level = source.key_level
        label = f"{source.name} (Vault)" if level == -1 else (f"{source.name} (+{level})" if level else source.name)
        return (f"dungeon:{source.name}:{level}", label, kind)
    if source.type == "world_boss":
        return (f"world_boss:{source.boss}", source.boss or source.name, kind)
    if source.type == "delve":
        return (f"delve:{source.key_level}", f"Delve Tier {source.key_level}", kind)
    if source.type == "catalyst":
        return ("catalyst", "Catalyst", kind)
    return ("crafted", "Crafted gear", kind)


def build_groups(rows: list[ResultRow], baseline_dps: float) -> list[Group]:
    """Per-source summary: per item take the best (max dps) of its slot rows -- a ring or
    trinket still has 2 rows in ``rows`` itself, one per slot, but counts once here -- then
    aggregate those per-item bests by drop source (boss/dungeon/delve/world_boss/crafted)."""
    best_by_item: dict[str, ResultRow] = {}
    info_by_item: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        item = row.meta.item
        if item is None:
            continue
        info = _group_info(item.source)
        if info is None:
            continue
        info_by_item[item.key] = info
        cur = best_by_item.get(item.key)
        if cur is None or row.dps > cur.dps:
            best_by_item[item.key] = row

    buckets: dict[str, dict] = {}
    for item_key, row in best_by_item.items():
        gkey, label, kind = info_by_item[item_key]
        buckets.setdefault(gkey, {"label": label, "kind": kind, "rows": []})["rows"].append(row)

    groups: list[Group] = []
    for gkey, b in buckets.items():
        item_rows: list[ResultRow] = b["rows"]
        n = len(item_rows)
        best_row = max(item_rows, key=lambda r: r.delta)
        ev = sum(max(0.0, r.delta) for r in item_rows) / n
        upgrade_share = sum(1 for r in item_rows if r.delta > 0) / n
        groups.append(Group(
            key=gkey, label=b["label"], kind=b["kind"], n=n,
            best=best_row.delta, best_pct=best_row.delta_pct, best_label=best_row.label,
            ev=ev, ev_pct=(ev / baseline_dps * 100.0) if baseline_dps else 0.0,
            upgrade_share=upgrade_share,
        ))
    groups.sort(key=lambda g: g.best, reverse=True)
    return groups


def target_slots(item: Item, profile: CharacterProfile) -> list[str]:
    """Concrete slots (``finger1``, ``off_hand``, ...) are honoured as-is -- candidates()
    already narrowed them (e.g. a unique-equipped ring restricted to the one ring slot it
    can legally replace, or a dual-wielded 1H weapon split into one main_hand candidate and
    one off_hand candidate). Only the generic slots get expanded here, once, at combo time.
    """
    slot = item.slot
    if slot == "finger":
        return ["finger1", "finger2"]
    if slot == "trinket":
        return ["trinket1", "trinket2"]
    if slot == "weapon":
        return ["off_hand"] if is_off_hand_only(item) else ["main_hand"]
    return [slot]


def build(profile: CharacterProfile, options: SimOptions, items: list[Item],
          add_socket: bool = False, preferred_gem: int | None = None) -> Plan:
    names = new_names()
    plan = Plan(simc_text="")
    n = 0
    socket_season = _season_mod() if add_socket else None
    for item in items:
        if options.socket_all or options.enchant_all:
            item = apply_season(item, item.slot, options, profile)
        if socket_season is not None and (item.source is None or item.source.type != "catalyst"):
            item = _apply_vault_socket(item, profile, preferred_gem, socket_season)
        for slot in target_slots(item, profile):
            n += 1
            replaced = profile.equipped.get(slot)
            overrides = [simc_input.item_line(item, slot)]
            if slot == "main_hand" and is_two_hand(item, profile) and profile.equipped.get("off_hand"):
                overrides.append(simc_input.empty_slot("off_hand"))
            label = f"{item_label(item)} -> {slot}"
            if replaced:
                label += f" (replaces {item_label(replaced)})"
            name = names.make(label, hint=f"d{n}")
            plan.profilesets.append(Profileset(name=name, label=label, overrides=overrides))
            plan.labels[name] = label
            plan.meta[name] = ResultMeta(item=item, source=item.source, changes={slot: item})
    if len(plan.profilesets) > MAX_PROFILESETS:
        raise TooManyProfilesets(
            f"droptimizer would run {len(plan.profilesets)} profilesets (cap is {MAX_PROFILESETS}); "
            "narrow your sources (fewer bosses/difficulties or a lower key level range)"
        )
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(ctx, profile: CharacterProfile, options: SimOptions, sources: list[DropSource],
            upgrade: str | int = "drop", min_ilevel: int | None = None,
            upgrade_equipped: str = "none", include_offspec: bool = False,
            include_catalyst: bool = False, add_socket: bool = False,
            preferred_gem: int | None = None) -> SimResult:
    ctx.progress("candidates", 0, 0, "Collecting drop candidates")
    items = fetch_candidates(profile, sources, upgrade, include_offspec)

    catalyst_notes: list[str] = []
    catalyst_sources = [s for s in sources if isinstance(s, CatalystSource)]
    season = _season_mod() if (catalyst_sources or include_catalyst) else None
    if season is not None:
        for cs in catalyst_sources:
            twins, n_twins = _catalyst_source_items(profile, cs, season)
            items.extend(twins)
            rank_txt = f" {cs.rank}" if cs.rank else ""
            if n_twins:
                if profile.catalyst_charges is not None:
                    charge_txt = f"; uses {n_twins} of your {profile.catalyst_charges} catalyst charge(s)"
                else:
                    charge_txt = "; catalyst charge count unknown (no catalyst_currencies in this export)"
                catalyst_notes.append(f"Catalyst ({cs.track}{rank_txt}): {n_twins} of your gear item(s){charge_txt}.")
        if include_catalyst:
            twins = []
            for it in list(items):
                if it.source is not None and it.source.type == "catalyst":
                    continue    # never re-catalyze an already-catalyzed twin
                twin = _catalyst_twin(it, profile, season)
                if twin is not None:
                    twins.append(twin)
            items.extend(twins)
            if twins:
                catalyst_notes.append(f"Catalyst: added {len(twins)} catalyzed twin(s) of drop candidate(s).")
    elif catalyst_sources or include_catalyst:
        catalyst_notes.append("Catalyst: season data layer unavailable; catalyst variants skipped.")

    if min_ilevel is not None:
        before = len(items)
        items = [i for i in items if i.ilevel >= min_ilevel]
        skipped = before - len(items)
        if skipped:
            ctx.progress("candidates", 0, 0, f"Skipped {skipped} candidate(s) below min ilevel {min_ilevel}")
    upgraded_slots: list[str] = []
    if upgrade_equipped != "none":
        reference_ilevel = max((i.ilevel for i in items), default=None)
        profile, upgraded_slots = upgrade_equipped_items(profile, upgrade_equipped, reference_ilevel)
    plan = build(profile, options, items, add_socket=add_socket, preferred_gem=preferred_gem)
    plan.notes.extend(catalyst_notes)
    if upgraded_slots:
        plan.notes.append(
            f"Upgraded equipped gear ({upgrade_equipped}) in {len(upgraded_slots)} slot(s): "
            f"{', '.join(upgraded_slots)}."
        )
    if options.precision:
        res = run_staged(
            ctx, plan, options, precision_stages(options.precision),
            klass=profile.klass, spec=profile.spec,
        )
    else:
        res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
        res = apply_meta(res, plan)
    res.notes = list(plan.notes)
    res.groups = build_groups(res.results, res.baseline.dps)
    return res
