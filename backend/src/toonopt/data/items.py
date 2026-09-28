"""Resolve an item id (+ bonus ids) to a fully described :class:`toonopt.models.Item`.

Item level: an explicit ``ilevel`` wins (that is what SimC does with ``ilevel=``). Otherwise
``ItemSparse.ItemLevel`` is the base and bonus ids adjust it -- absolute levels from the
Raidbots map (upgrade-track steps, crafted tiers, Voidforged), then the DB2 ``ItemBonus``
deltas when the map is unavailable. See :mod:`toonopt.data.bonuses`.

Slot: DB2 InventoryType -> SimC slot. Rings -> ``finger``, trinkets -> ``trinket`` (placed as
finger1/trinket1 at combination time); one-handers / two-handers -> ``main_hand``; shields,
off-hand weapons and held-in-off-hand -> ``off_hand``. A ``slot_hint`` (e.g. ``finger2`` or
``off_hand`` for a dual-wielded one-hander) is honoured when it is legal for the item.

Icon: ``Item.IconFileDataID`` covers non-transmoggable items (rings, necks, trinkets); modern
gear leaves it at 0 and keeps the icon on its appearance, so
``ItemModifiedAppearance -> ItemAppearance.DefaultIconFileDataID`` fills the rest. The file
data id maps to a name through ``ManifestInterfaceData`` (``INV_Foo_Bar.blp`` -> ``inv_foo_bar``),
which is what Wowhead's CDN serves.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import polars as pl

from toonopt.data import bonuses, stats, wago
from toonopt.models import Item

log = logging.getLogger(__name__)

ICON_URL = "https://wow.zamimg.com/images/wow/icons/large/{icon}.jpg"
FLAG_UNIQUE_EQUIPPED = 0x80000

# InventoryType -> canonical SimC slot
INV_SLOT: dict[int, str] = {
    1: "head", 2: "neck", 3: "shoulder", 5: "chest", 20: "chest", 6: "waist", 7: "legs",
    8: "feet", 9: "wrist", 10: "hands", 11: "finger", 12: "trinket", 16: "back",
    13: "main_hand", 21: "main_hand", 17: "main_hand", 15: "main_hand", 26: "main_hand",
    22: "off_hand", 23: "off_hand", 14: "off_hand",
}
# alternative placements a slot hint may pick
_SLOT_ALIASES: dict[str, set[str]] = {
    "finger": {"finger1", "finger2"}, "trinket": {"trinket1", "trinket2"},
    "main_hand": {"off_hand"},        # one-handers may be dual-wielded
}
TWO_HAND_INV = 17
ONE_HAND_INV = {13, 21}
OFF_HAND_ONLY_INV = {22, 23, 14}

SPARSE_COLUMNS = [
    "ID", "Display_lang", "ItemLevel", "InventoryType", "OverallQualityID", "AllowableClass",
    "Flags_0", "ItemSet", "LimitCategory", "ExpansionID", "ItemDelay", "DmgVariance",
    *[f"StatPercentEditor_{i}" for i in range(10)],
    *[f"StatModifier_bonusStat_{i}" for i in range(10)],
    "SocketType_0", "SocketType_1", "SocketType_2",
]
ITEM_COLUMNS = ["ID", "ClassID", "SubclassID", "InventoryType", "IconFileDataID"]


def item_icon_url(icon: str) -> str:
    return ICON_URL.format(icon=icon or "inv_misc_questionmark")


# ---------------------------------------------------------------------------
# tables

@lru_cache(maxsize=4)
def _items(build: str | None = None) -> pl.DataFrame:
    sparse = wago.table("ItemSparse", build, SPARSE_COLUMNS)
    base = wago.table("Item", build, ITEM_COLUMNS).rename({"InventoryType": "InventoryType_item"})
    return sparse.join(base, on="ID", how="left")


def rows(item_ids: list[int] | tuple[int, ...] | set[int], build: str | None = None) -> dict[int, dict]:
    """Raw joined ItemSparse+Item rows keyed by id (missing ids are absent)."""
    ids = list({int(i) for i in item_ids})
    if not ids:
        return {}
    df = _items(build).filter(pl.col("ID").is_in(ids))
    return {int(r["ID"]): r for r in df.iter_rows(named=True)}


def row(item_id: int, build: str | None = None) -> dict | None:
    return rows([item_id], build).get(int(item_id))


@lru_cache(maxsize=4)
def _limit_categories(build: str | None = None) -> dict[int, str]:
    df = wago.table("ItemLimitCategory", build, ["ID", "Name_lang"])
    return {int(i): str(n) for i, n in zip(df["ID"].to_list(), df["Name_lang"].to_list(), strict=True)}


@lru_cache(maxsize=4)
def _appearance_icons(build: str | None = None) -> pl.DataFrame:
    """ItemID -> DefaultIconFileDataID via the item's lowest-OrderIndex appearance."""
    ima = wago.table("ItemModifiedAppearance", build, ["ItemID", "ItemAppearanceID", "OrderIndex"])
    ia = wago.table("ItemAppearance", build, ["ID", "DefaultIconFileDataID"])
    best = ima.sort("OrderIndex").group_by("ItemID").first()
    return best.join(ia, left_on="ItemAppearanceID", right_on="ID", how="left") \
               .select("ItemID", "DefaultIconFileDataID")


def _file_names(file_ids: list[int], build: str | None = None) -> dict[int, str]:
    if not file_ids:
        return {}
    mid = wago.table("ManifestInterfaceData", build, ["ID", "FileName"])
    df = mid.filter(pl.col("ID").is_in(file_ids))
    out = {}
    for i, n in zip(df["ID"].to_list(), df["FileName"].to_list(), strict=True):
        name = str(n or "")
        if name.lower().endswith(".blp"):
            name = name[:-4]
        out[int(i)] = name.lower()
    return out


def icons(item_ids: list[int] | tuple[int, ...] | set[int], build: str | None = None) -> dict[int, str]:
    """Icon file names (without extension, lower-case) for many items at once."""
    ids = list({int(i) for i in item_ids})
    if not ids:
        return {}
    direct = wago.table("Item", build, ITEM_COLUMNS).filter(pl.col("ID").is_in(ids)) \
        .select("ID", "IconFileDataID")
    file_of: dict[int, int] = {int(i): int(f) for i, f in zip(direct["ID"].to_list(), direct["IconFileDataID"].to_list(), strict=True) if f}
    missing = [i for i in ids if i not in file_of]
    if missing:
        app = _appearance_icons(build).filter(pl.col("ItemID").is_in(missing))
        for i, f in zip(app["ItemID"].to_list(), app["DefaultIconFileDataID"].to_list(), strict=True):
            if f:
                file_of[int(i)] = int(f)
    names = _file_names(sorted(set(file_of.values())), build)
    return {i: names.get(f, "") for i, f in file_of.items()}


def icon(item_id: int, build: str | None = None) -> str:
    return icons([item_id], build).get(int(item_id), "")


# ---------------------------------------------------------------------------
# helpers on raw rows

def allocs_of(r: dict) -> list[tuple[int, int]]:
    out = []
    for i in range(10):
        stat = int(r.get(f"StatModifier_bonusStat_{i}", -1) or -1)
        alloc = int(r.get(f"StatPercentEditor_{i}", 0) or 0)
        if stat >= 0 and alloc:
            out.append((stat, alloc))
    return out


def stat_ids_of(r: dict) -> list[int]:
    return [int(r[f"StatModifier_bonusStat_{i}"]) for i in range(10)
            if int(r.get(f"StatModifier_bonusStat_{i}", -1) or -1) > 0]


def born_sockets(r: dict) -> int:
    return sum(1 for i in range(3) if int(r.get(f"SocketType_{i}", 0) or 0) > 0)


def inv_type_of(r: dict) -> int:
    return int(r.get("InventoryType") or r.get("InventoryType_item") or 0)


def canonical_slot(inv_type: int) -> str | None:
    return INV_SLOT.get(int(inv_type))


def pick_slot(inv_type: int, slot_hint: str | None) -> str:
    base = canonical_slot(inv_type) or "unknown"
    if not slot_hint:
        return base
    if slot_hint == base:
        return slot_hint
    if slot_hint in _SLOT_ALIASES.get(base, set()):
        # a two-hander is never legal in the off-hand slot, even as a hint
        if slot_hint == "off_hand" and int(inv_type) == TWO_HAND_INV:
            return base
        return slot_hint
    return base


def unique_equipped_name(r: dict, bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> str | None:
    lc = int(r.get("LimitCategory") or 0) or bonuses.limit_category_of(bonus_ids, build)
    if lc:
        return _limit_categories(build).get(lc, f"limit category {lc}")
    if int(r.get("Flags_0") or 0) & FLAG_UNIQUE_EQUIPPED:
        return "Unique-Equipped"
    return None


def effective_ilevel(r: dict, bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int:
    base = int(r.get("ItemLevel") or 0)
    from_map = bonuses.ilevel_from_bonuses(bonus_ids, build)
    if from_map:
        return from_map
    if bonuses.bonus_map(build):
        return base
    return bonuses.db2_apply(base, bonus_ids, build)["ilevel"]


def effective_quality(r: dict, bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int:
    q = int(r.get("OverallQualityID") or 0)
    bq = bonuses.quality_from_bonuses(bonus_ids, build)
    if bq is None and not bonuses.bonus_map(build):
        bq = bonuses.db2_apply(0, bonus_ids, build)["quality"]
    return max(q, bq or 0)


# ---------------------------------------------------------------------------

def resolve_row(
    r: dict,
    bonus_ids: list[int] | tuple[int, ...],
    ilevel: int | None,
    *,
    key: str,
    slot_hint: str | None = None,
    gem_ids: tuple[int, ...] | list[int] = (),
    enchant_id: int | None = None,
    crafted_stats: tuple[int, ...] | list[int] = (),
    crafting_quality: int | None = None,
    icon_name: str | None = None,
    build: str | None = None,
) -> Item:
    bonus_ids = [int(b) for b in bonus_ids if int(b) > 0]
    crafted = [int(c) for c in crafted_stats] or bonuses.crafted_stats_of(bonus_ids, build)
    lvl = int(ilevel) if ilevel else effective_ilevel(r, bonus_ids, build)
    quality = effective_quality(r, bonus_ids, build)
    inv = inv_type_of(r)
    item_class = int(r.get("ClassID") or 0)
    subclass = int(r.get("SubclassID") or 0)
    st = stats.compute(
        ilevel=lvl, quality=quality, inv_type=inv, item_class=item_class, subclass=subclass,
        allocs=allocs_of(r), delay_ms=int(r.get("ItemDelay") or 0),
        dmg_variance=float(r.get("DmgVariance") or 0.0), crafted_stats=crafted, build=build,
    )
    filtered_gem_ids = [int(g) for g in gem_ids if int(g) > 0]
    # same logic as toonopt.data.season.best_gems: sockets come from the bonus ids on this
    # concrete item, not ItemSparse.SocketType (a static per-item-id placeholder); the
    # gem_ids-length fallback only helps when bonus-id decoding fails and the item already
    # carries a gem (bonuses.json missing, or a gem in a socket this decode can't see).
    n_sockets = bonuses.socket_count(bonus_ids, build)
    if n_sockets == 0 and filtered_gem_ids:
        n_sockets = len(filtered_gem_ids)
    item = Item(
        key=key,
        id=int(r["ID"]),
        name=str(r.get("Display_lang") or ""),
        slot=pick_slot(inv, slot_hint),
        inventory_type=inv,
        ilevel=lvl,
        quality=quality,
        icon=icon_name if icon_name is not None else icon(int(r["ID"]), build),
        bonus_ids=bonus_ids,
        sockets=max(0, n_sockets),
        gem_ids=filtered_gem_ids,
        enchant_id=int(enchant_id) if enchant_id else None,
        crafted_stats=crafted,
        crafting_quality=int(crafting_quality) if crafting_quality else None,
        unique_equipped=unique_equipped_name(r, bonus_ids, build),
        set_id=int(r["ItemSet"]) if int(r.get("ItemSet") or 0) > 0 else None,
        stats=st,
    )
    item.simc_string = item.to_simc()
    return item


def resolve_item(
    item_id: int,
    bonus_ids: list[int],
    ilevel: int | None,
    *,
    key: str,
    slot_hint: str | None = None,
    gem_ids=(),
    enchant_id=None,
    crafted_stats=(),
    crafting_quality=None,
) -> Item:
    """Public entry point (see module docstring). Raises KeyError for an unknown item id."""
    r = row(item_id)
    if r is None:
        raise KeyError(f"unknown item id {item_id}")
    return resolve_row(
        r, bonus_ids or [], ilevel, key=key, slot_hint=slot_hint, gem_ids=tuple(gem_ids or ()),
        enchant_id=enchant_id, crafted_stats=tuple(crafted_stats or ()), crafting_quality=crafting_quality,
    )


# ---------------------------------------------------------------------------
# item search (API.md "Raidbots parity, wave 1" -> GET /api/data/items/search)

def resolve_track_rank(track: str, rank: int, build: str | None = None) -> tuple[list[int], int | None]:
    """``(bonus_ids, ilevel)`` for an upgrade track name + rank (e.g. ``"Myth"``, 3), from
    ``season.json``'s ``upgrade_tracks`` (see :mod:`toonopt.data.season`). Reuses
    ``toonopt.data.loot._track_bonus`` for the bonus id lookup rather than duplicating it;
    the item level comes from the same track's parallel ``ilevels`` list. ``([], None)`` for
    an unknown track or an out-of-range rank."""
    from toonopt.data import season
    from toonopt.data.loot import _track_bonus

    tracks: dict = season.load().get("upgrade_tracks", {})
    bonus_ids = _track_bonus(tracks, track, rank)
    if not bonus_ids:
        return [], None
    ilevels = tracks.get(track, {}).get("ilevels") or []
    ilevel = int(ilevels[rank - 1]) if 0 < rank <= len(ilevels) and ilevels[rank - 1] is not None else None
    return bonus_ids, ilevel


def search_items(
    q: str,
    klass: str | None = None,
    spec: str | None = None,
    slot: str | None = None,
    limit: int = 25,
    build: str | None = None,
) -> list[dict]:
    """Item name search for the "Add item" box (API.md ``GET /api/data/items/search``).

    Case-insensitive substring match on ``ItemSparse.Display_lang``, restricted to equippable
    armour/weapons/jewelry -- ``toonopt.data.loot``'s own ``_shape()`` already drops everything
    else (quest items, cosmetics, cosmetic-only subclasses, ...) -- and to quality >= uncommon
    (drops gray/white junk). When ``klass``/``spec`` are given, further filtered to what that
    spec can actually equip via ``toonopt.data.loot.usable_slots`` (the same rule
    ``candidates()`` applies to fresh loot-db drops), with the quality floor turned off there
    since we already applied our own above. ``slot`` matches the item's canonical/generic slot
    (``toonopt.data.items.canonical_slot``, e.g. ``"finger"``/``"trinket"`` for rings/trinkets).

    Sorted current-expansion first, then by expansion id (or, when an item carries no
    ``ExpansionID`` at all, by item id) descending, then by name.
    """
    needle = (q or "").strip().lower()
    if not needle:
        return []
    from toonopt.data import loot, season

    df = _items(build).filter(pl.col("Display_lang").str.to_lowercase().str.contains(needle, literal=True))
    if df.is_empty():
        return []

    wanted_slot = {"finger1": "finger", "finger2": "finger", "trinket1": "trinket", "trinket2": "trinket"}.get(slot, slot) if slot else None
    cid = loot.CLASS_IDS.get(loot.normalize_class(klass), 0) if klass else 0
    key = loot.spec_key(klass, spec) if klass and spec else None
    current_exp = season.CURRENT_EXPANSION

    found: list[dict] = []
    for r in df.iter_rows(named=True):
        shaped = loot._shape(r)
        if shaped is None or shaped["quality"] < 2:
            continue
        canon = canonical_slot(shaped["inv_type"])
        if canon is None or (wanted_slot and canon != wanted_slot):
            continue
        if key and not loot.usable_slots(shaped, cid, key, check_quality=False, check_allowable_class=True):
            continue
        exp = shaped.get("expansion")
        found.append({
            "id": shaped["id"], "name": shaped["name"], "quality": shaped["quality"],
            "inventory_type": shaped["inv_type"], "slot": canon,
            "base_ilevel": int(r.get("ItemLevel") or 0), "_expansion": exp,
        })

    def sort_key(it: dict) -> tuple:
        exp = it["_expansion"]
        if exp is not None and exp >= 0:
            return (0 if exp == current_exp else 1, -exp, it["name"].lower())
        return (1, -it["id"], it["name"].lower())

    found.sort(key=sort_key)
    found = found[:limit]
    icon_of = icons([it["id"] for it in found], build)
    out = []
    for it in found:
        exp = it.pop("_expansion")
        it["icon"] = icon_of.get(it["id"], "")
        if exp == current_exp:
            try:
                it["expansion_hint"] = season.load().get("season")
            except Exception as e:  # noqa: BLE001 - purely cosmetic hint, never fail the search over it
                log.debug("could not resolve expansion_hint for item %s: %s", it["id"], e)
        out.append(it)
    return out
