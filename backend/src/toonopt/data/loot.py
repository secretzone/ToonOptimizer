"""Droptimizer loot: what can drop for a spec, from which source, at which item level.

The loot database (per build, cached as ``CACHE_DIR/<build>/lootdb.derived.json``) joins the
journal tables for the live season's raids, keystone dungeons and world bosses, plus the
curated delve pool and the profession-crafted pool. :func:`candidates` turns a list of
``DropSource`` selections into fully resolved :class:`Item` objects, filtered to what the
class/spec can equip and would want (port of localbots' lootFilter.js):

* quality >= rare (curated delve entries are trusted regardless)
* ``AllowableClass`` mask, armour subclass per class, weapon subclasses per class
* an item with a primary stat must grant the spec's primary (secondary-only items pass)
* shields only for shield specs, held-in-off-hand only for intellect specs
* one-handers go in both hands for dual-wield specs; off-hand weapons need a dual-wielder;
  a two-hander in the main hand (Titan's Grip aside) closes the off-hand slot

Keys are ``drop:<itemid>:<slot>:<source>`` where ``<source>`` is
``raid:<instance>:<difficulty>:<encounter>``, ``dungeon:<instance>:<key>``, ``world_boss:<encounter>``,
``delve:<tier>`` or ``crafted``.
"""
from __future__ import annotations

import json
from functools import lru_cache

import polars as pl

from toonopt.data import droplevels, items, season, wago
from toonopt.models import CharacterProfile, DropSource, Item, ItemSource

LOOT_DB_VERSION = 3

# simc class name -> WoW class id (both slug spellings accepted)
CLASS_IDS: dict[str, int] = {
    "warrior": 1, "paladin": 2, "hunter": 3, "rogue": 4, "priest": 5, "death_knight": 6, "deathknight": 6,
    "shaman": 7, "mage": 8, "warlock": 9, "monk": 10, "druid": 11, "demon_hunter": 12, "demonhunter": 12,
    "evoker": 13,
}
CLASS_SLUG_BY_ID: dict[int, str] = {
    1: "warrior", 2: "paladin", 3: "hunter", 4: "rogue", 5: "priest", 6: "death_knight", 7: "shaman",
    8: "mage", 9: "warlock", 10: "monk", 11: "druid", 12: "demon_hunter", 13: "evoker",
}
# class id -> armour subclass (1 cloth, 2 leather, 3 mail, 4 plate)
ARMOR_TYPE: dict[int, int] = {1: 4, 2: 4, 6: 4, 3: 3, 7: 3, 13: 3, 4: 2, 10: 2, 11: 2, 12: 2, 5: 1, 8: 1, 9: 1}
# primary stat per "class_spec" (3 agi, 4 str, 5 int)
SPEC_PRIMARY: dict[str, int] = {
    "warrior_arms": 4, "warrior_fury": 4, "warrior_protection": 4,
    "paladin_holy": 5, "paladin_protection": 4, "paladin_retribution": 4,
    "hunter_beast_mastery": 3, "hunter_marksmanship": 3, "hunter_survival": 3,
    "rogue_assassination": 3, "rogue_outlaw": 3, "rogue_subtlety": 3,
    "priest_discipline": 5, "priest_holy": 5, "priest_shadow": 5,
    "death_knight_blood": 4, "death_knight_frost": 4, "death_knight_unholy": 4,
    "shaman_elemental": 5, "shaman_enhancement": 3, "shaman_restoration": 5,
    "mage_arcane": 5, "mage_fire": 5, "mage_frost": 5,
    "warlock_affliction": 5, "warlock_demonology": 5, "warlock_destruction": 5,
    "monk_brewmaster": 3, "monk_mistweaver": 5, "monk_windwalker": 3,
    "druid_balance": 5, "druid_feral": 3, "druid_guardian": 3, "druid_restoration": 5,
    "demon_hunter_havoc": 3, "demon_hunter_vengeance": 3, "demon_hunter_devourer": 3,
    "evoker_devastation": 5, "evoker_preservation": 5, "evoker_augmentation": 5,
}
PRIMARY_NAMES: dict[int, str] = {3: "agility", 4: "strength", 5: "intellect"}
STAT_GRANTS: dict[int, tuple[int, ...]] = {3: (3,), 4: (4,), 5: (5,), 71: (3, 4, 5), 72: (3, 4), 73: (3, 5), 74: (4, 5)}
# weapon subclasses per class id
# 0 axe1h 1 axe2h 2 bow 3 gun 4 mace1h 5 mace2h 6 polearm 7 sword1h 8 sword2h 9 warglaive
# 10 staff 13 fist 15 dagger 18 crossbow 19 wand
WEAPONS: dict[int, set[int]] = {
    1: {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 18}, 2: {0, 1, 4, 5, 6, 7, 8},
    3: {0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 18}, 4: {0, 4, 7, 13, 15}, 5: {4, 10, 15, 19},
    6: {0, 1, 4, 5, 6, 7, 8}, 7: {0, 1, 4, 5, 10, 13, 15}, 8: {7, 10, 15, 19}, 9: {7, 10, 15, 19},
    10: {0, 4, 6, 7, 10, 13}, 11: {4, 5, 6, 10, 13, 15}, 12: {0, 7, 9, 13, 15},
    13: {0, 1, 4, 5, 7, 8, 10, 13, 15},
}
SHIELD_SPECS = {"warrior_protection", "paladin_holy", "paladin_protection", "shaman_elemental", "shaman_restoration"}
DUAL_WIELD_1H = {
    "warrior_fury", "death_knight_frost", "shaman_enhancement", "rogue_assassination", "rogue_outlaw",
    "rogue_subtlety", "demon_hunter_havoc", "demon_hunter_vengeance", "demon_hunter_devourer", "monk_windwalker",
    "monk_brewmaster", "hunter_survival",
}
DUAL_WIELD_2H = {"warrior_fury"}       # Titan's Grip
TWO_HAND_INV = 17
ONE_HAND_INV = {13, 21, 15, 26}
OFF_HAND_ONLY = {22, 23}
DUNGEON_DIFFICULTY_BITS = (1 << 0) | (1 << 1) | (1 << 7) | (1 << 22)   # Normal, Heroic, M+, Mythic
CURRENT_ITEM_ID = 240000
MPLUS_TAG_BONUS = 13440
TRACK_MAX_RANK = 6
# The world-boss "instance" is really the ungated JournalInstance container (named after the
# expansion, e.g. "Midnight" -- see season.py's world-boss detection); show a real label instead.
WORLD_BOSS_LABEL = "World Bosses"


def normalize_class(klass: str) -> str:
    k = klass.lower().replace(" ", "_").replace("-", "_")
    return {"deathknight": "death_knight", "demonhunter": "demon_hunter"}.get(k, k)


def spec_key(klass: str, spec: str) -> str:
    return f"{normalize_class(klass)}_{spec.lower().replace(' ', '_').replace('-', '_')}"


def primary_stat(klass: str, spec: str) -> str | None:
    p = SPEC_PRIMARY.get(spec_key(klass, spec))
    return PRIMARY_NAMES.get(p) if p else None


def is_dual_wield(key: str) -> bool:
    return key in DUAL_WIELD_1H or key in DUAL_WIELD_2H


# ---------------------------------------------------------------------------
# loot database

def _shape(r: dict, curated: bool = False) -> dict | None:
    inv = items.inv_type_of(r)
    if not inv or inv in (18, 24, 27, 28):
        return None
    cls = int(r.get("ClassID") or 0)
    if cls not in (2, 4):
        return None
    return {
        "id": int(r["ID"]), "name": str(r.get("Display_lang") or ""), "inv_type": inv,
        "quality": int(r.get("OverallQualityID") or 0), "allowable_class": int(r.get("AllowableClass") if r.get("AllowableClass") is not None else -1),
        "class_id": cls, "subclass_id": int(r.get("SubclassID") or 0), "stats": items.stat_ids_of(r),
        "sockets": items.born_sockets(r), "set_id": int(r["ItemSet"]) if int(r.get("ItemSet") or 0) > 0 else None,
        "unique": bool(int(r.get("Flags_0") or 0) & items.FLAG_UNIQUE_EQUIPPED), "limit_category": int(r.get("LimitCategory") or 0),
        "expansion": int(r.get("ExpansionID") if r.get("ExpansionID") is not None else -1), **({"curated": True} if curated else {}),
    }


def _dedupe_by_name(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for it in rows:
        prev = best.get(it["name"])
        if prev is None or it["id"] > prev["id"]:
            best[it["name"]] = it
    return list(best.values())


def _dungeon_keep(jei: pl.DataFrame) -> set[int]:
    """Journal rows of a (possibly returning) dungeon that are on its CURRENT loot table."""
    wse = [int(w) for w in jei["WorldStateExpressionID"].to_list()]
    groups = {w for w in wse if w}
    current = None
    if len(groups) > 1:
        with_new = [w for w in groups if any(int(i) >= CURRENT_ITEM_ID and int(x) == w
                                             for i, x in zip(jei["ItemID"].to_list(), wse, strict=True))]
        current = max(with_new or groups)
    keep = set()
    for rid, mask, w in zip(jei["ID"].to_list(), jei["DifficultyMask"].to_list(), wse, strict=True):
        mask = int(mask)
        if mask not in (-1, 0) and not (mask & DUNGEON_DIFFICULTY_BITS):
            continue
        if current is not None and w and w != current:
            continue
        keep.add(int(rid))
    return keep


def build_db(build: str | None = None) -> dict:
    build = build or wago.effective_build()
    s = season.load()
    jei = wago.table("JournalEncounterItem", build, ["ID", "JournalEncounterID", "ItemID", "DifficultyMask", "WorldStateExpressionID"])
    sources: list[dict] = []
    wanted: set[int] = set()
    plan: list[tuple[dict, str]] = [(r, "raid") for r in s["raids"]] + [(d, "dungeon") for d in s["dungeons"]] + [(w, "world_boss") for w in s["world_bosses"]]
    for inst, kind in plan:
        bosses = []
        for b in inst["bosses"]:
            rows = jei.filter(pl.col("JournalEncounterID") == b["encounter_id"])
            keep = _dungeon_keep(rows) if kind == "dungeon" else None
            ids = []
            for rid, item in zip(rows["ID"].to_list(), rows["ItemID"].to_list(), strict=True):
                if keep is not None and int(rid) not in keep:
                    continue
                if int(item) not in ids:
                    ids.append(int(item))
            wanted.update(ids)
            bosses.append({"encounter_id": b["encounter_id"], "name": b["name"], "order": b["order"],
                           "sequence": b.get("sequence"), "item_ids": ids, "drops": b.get("drops", {})})
        sources.append({"kind": kind, "instance_id": inst["instance_id"], "name": inst["name"], "bosses": bosses})

    # delves: curated pool, names resolve to the best (quality, newest) version
    pool = season.delve_pool()
    delve_ids = {int(e["id"]) for e in pool if e.get("id")}
    names = {e["name"] for e in pool if e.get("name") and not e.get("id")}
    if names:
        df = items._items(build).filter(pl.col("Display_lang").is_in(list(names))) \
            .sort(["OverallQualityID", "ID"], descending=[True, True]).group_by("Display_lang").first()
        delve_ids.update(int(i) for i in df["ID"].to_list())
    wanted.update(delve_ids)

    # crafted: CraftingData recipes for current-expansion gear with selectable secondaries
    cd = wago.table("CraftingData", build, ["CraftedItemID"])
    crafted_candidates = {int(i) for i in cd["CraftedItemID"].to_list() if i}
    sparse = items._items(build).filter(pl.col("ID").is_in(list(crafted_candidates)) & (pl.col("ExpansionID") == season.CURRENT_EXPANSION))
    crafted_ids = []
    for r in sparse.iter_rows(named=True):
        st = items.stat_ids_of(r)
        if 24 in st and 25 in st:
            crafted_ids.append(int(r["ID"]))
    wanted.update(crafted_ids)

    rows = items.rows(wanted, build)
    shaped: dict[int, dict] = {}
    for iid, r in rows.items():
        sh = _shape(r, curated=iid in delve_ids)
        if sh:
            shaped[iid] = sh
    for src in sources:
        for b in src["bosses"]:
            b["items"] = _dedupe_by_name([shaped[i] for i in b.pop("item_ids") if i in shaped])
        src["bosses"] = [b for b in src["bosses"] if b["items"]]
    sources = [src for src in sources if src["bosses"]]
    if delve_ids:
        sources.append({"kind": "delve", "instance_id": 0, "name": "Delves",
                        "bosses": [{"encounter_id": 0, "name": "Bountiful coffer", "order": 0, "sequence": None,
                                    "items": _dedupe_by_name([shaped[i] for i in sorted(delve_ids) if i in shaped]), "drops": {}}]})
    if crafted_ids:
        sources.append({"kind": "crafted", "instance_id": 0, "name": "Crafted gear",
                        "bosses": [{"encounter_id": 0, "name": "Profession crafts", "order": 0, "sequence": None,
                                    "items": [shaped[i] for i in sorted(crafted_ids) if i in shaped], "drops": {}}]})
    return {"version": LOOT_DB_VERSION, "build": build, "sources": sources}


@lru_cache(maxsize=2)
def db(build: str | None = None) -> dict:
    build = build or wago.effective_build()
    path = wago.cache_dir(build) / "lootdb.derived.json"
    if path.exists():
        try:
            d = json.loads(path.read_text("utf-8"))
            if d.get("version") == LOOT_DB_VERSION and d.get("build") == build:
                return d
        except Exception:  # noqa: BLE001, S110 - a corrupt/stale cache just gets rebuilt below
            pass
    d = build_db(build)
    path.write_text(json.dumps(d), "utf-8")
    return d


def clear_db(build: str | None = None) -> None:
    db.cache_clear()
    p = wago.cache_dir(build) / "lootdb.derived.json"
    p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# usability filter (lootFilter.js)

class Gear:
    """What the character is holding, as far as weapon slots are concerned."""

    def __init__(self, profile: CharacterProfile | None):
        self.two_hander = False
        self.has_off_hand = False
        self.slot_of_id: dict[int, str] = {}
        if profile is None:
            return
        mh = profile.equipped.get("main_hand")
        self.two_hander = bool(mh and mh.inventory_type == TWO_HAND_INV)
        self.has_off_hand = "off_hand" in profile.equipped
        for slot, it in profile.equipped.items():
            self.slot_of_id.setdefault(it.id, slot)


def usable_slots(item: dict, class_id: int, key: str, offspec: bool = False, gear: Gear | None = None,
                  *, check_quality: bool = True, check_allowable_class: bool = True) -> list[str] | None:
    """SimC slots this loot-db item may be placed in for the spec, or None when unusable.

    ``check_quality``/``check_allowable_class`` gate the two rules that only make sense for
    *fresh loot* (a drop must be rare+ to be worth simming; ``AllowableClass`` is Blizzard's
    client-side equip restriction) -- :func:`usable_slots_for_profile` turns both off for
    gear the character already owns, where the thing that actually crashes SimC is a
    weapon/armour *type* mismatch, not those two flags.
    """
    slots = _placements(item, class_id, key, offspec, gear, check_quality=check_quality, check_allowable_class=check_allowable_class)
    if not slots or len(slots) < 2 or not item.get("unique"):
        return slots
    worn = gear.slot_of_id.get(item["id"]) if gear else None
    return [worn] if worn and worn in slots else slots


def _placements(item: dict, class_id: int, key: str, offspec: bool, gear: Gear | None,
                 *, check_quality: bool = True, check_allowable_class: bool = True) -> list[str] | None:
    if check_quality and item["quality"] < 3 and not item.get("curated"):
        return None
    if check_allowable_class:
        ac = item["allowable_class"]
        if ac not in (-1, 0) and not (ac & (1 << (class_id - 1))):
            return None
    primary = SPEC_PRIMARY.get(key)
    primaries = {p for s in item["stats"] for p in STAT_GRANTS.get(s, ())}
    if not offspec and primaries and primary and primary not in primaries:
        return None
    inv = item["inv_type"]
    base = items.canonical_slot(inv)
    if not base:
        return None
    slots = {"finger": ["finger1", "finger2"], "trinket": ["trinket1", "trinket2"]}.get(base, [base])
    no_off_hand = bool(gear and gear.two_hander and key not in DUAL_WIELD_2H)
    if no_off_hand and (inv in OFF_HAND_ONLY or (item["class_id"] == 4 and item["subclass_id"] == 6)):
        return None
    if item["class_id"] == 2:
        if item["subclass_id"] not in WEAPONS.get(class_id, set()):
            return None
        is_2h = inv == TWO_HAND_INV
        is_1h = inv in ONE_HAND_INV
        if inv == 22:
            return ["off_hand"] if key in DUAL_WIELD_1H else None
        if (is_1h and key in DUAL_WIELD_1H) or (is_2h and key in DUAL_WIELD_2H):
            if no_off_hand:
                return ["main_hand"]
            return ["main_hand", "off_hand"]
        return slots
    if item["subclass_id"] == 5:
        return None                                   # cosmetic
    if item["class_id"] == 4 and item["subclass_id"] != 0 and not item["stats"]:
        return None                                   # statless
    if item["subclass_id"] == 6:
        return slots if key in SHIELD_SPECS else None
    if inv == 23:
        return slots if primary == 5 else None
    if 1 <= item["subclass_id"] <= 4 and inv != 16 and item["subclass_id"] != ARMOR_TYPE.get(class_id):
        return None
    return slots


class UnresolvedItem(ValueError):
    """Raised by :func:`usable_slots_for_profile` when the data layer has no usable row for
    the item's id (a test/deleted item, or the cached tables just don't cover it). Callers
    (Top Gear) should skip the item with a warning rather than pass its unknown legality
    on to SimC."""


def usable_slots_for_profile(item: Item, profile: CharacterProfile) -> list[str]:
    """Concrete SimC slots ``item`` -- gear the character already has, in bags or the vault
    -- may occupy for ``profile``'s class/spec. Reuses the same weapon/armour-subclass,
    shield, held-in-off-hand and primary-stat rules :func:`candidates` applies to fresh
    loot-db drops (see :func:`_placements`), but skips the quality-floor and
    ``AllowableClass`` checks: those describe whether a *drop* is worth offering or whether
    the WoW client would let you equip it, not whether SimC can simulate the item in that
    slot at all -- which is the actual crash this guards against (e.g. a dagger paired into
    a Death Knight's main hand aborts the whole SimC run).

    Empty list = the class/spec cannot equip this item in any slot. Raises
    :class:`UnresolvedItem` when the item's own row can't be found.
    """
    r = items.row(item.id)
    if r is None:
        raise UnresolvedItem(f"no item data for id {item.id} ({item.name or 'unnamed'})")
    shaped = _shape(r)
    if shaped is None:
        return []
    cid = CLASS_IDS.get(normalize_class(profile.klass), 0)
    key = spec_key(profile.klass, profile.spec)
    slots = usable_slots(shaped, cid, key, False, Gear(profile), check_quality=False, check_allowable_class=False)
    return list(slots) if slots else []


# ---------------------------------------------------------------------------
# public API

def sources(klass: str, spec: str) -> dict:
    """Loot sources for the UI (see API.md ``/api/data/loot/sources``) with usable counts."""
    s = season.load()
    d = db()
    cid = CLASS_IDS.get(normalize_class(klass), 0)
    key = spec_key(klass, spec)
    by_inst = {(src["kind"], src["instance_id"]): src for src in d["sources"]}

    def usable_count(bosses: list[dict]) -> int:
        return sum(1 for b in bosses for it in b["items"] if usable_slots(it, cid, key))

    raids = []
    for r in s["raids"]:
        src = by_inst.get(("raid", r["instance_id"]))
        bosses = []
        for b in r["bosses"]:
            sb = next((x for x in (src["bosses"] if src else []) if x["encounter_id"] == b["encounter_id"]), None)
            bosses.append({"encounter_id": b["encounter_id"], "name": b["name"], "order": b["order"],
                           "usable": usable_count([sb]) if sb else 0,
                           "drops": {k: {"ilevel": v["ilevel"], "track": v["track"], "rank": v["step"]} for k, v in b.get("drops", {}).items()}})
        raids.append({"instance_id": r["instance_id"], "name": r["name"],
                      "difficulties": [{"name": k, "ilevel": v["ilevel"], "max_ilevel": v.get("max_ilevel", v["ilevel"]), "track": v["track"]}
                                       for k, v in r["difficulties"].items()],
                      "bosses": bosses, "usable": sum(b["usable"] for b in bosses)})
    dungeons = []
    for dg in s["dungeons"]:
        src = by_inst.get(("dungeon", dg["instance_id"]))
        dungeons.append({"instance_id": dg["instance_id"], "name": dg["name"], "usable": usable_count(src["bosses"]) if src else 0,
                         "bosses": [{"encounter_id": b["encounter_id"], "name": b["name"], "order": b["order"]} for b in dg["bosses"]]})
    world = []
    for w in s["world_bosses"]:
        src = by_inst.get(("world_boss", w["instance_id"]))
        world.append({"instance_id": w["instance_id"], "name": WORLD_BOSS_LABEL, "ilevel": w["ilevel"],
                      "usable": usable_count(src["bosses"]) if src else 0,
                      "bosses": [{"encounter_id": b["encounter_id"], "name": b["name"], "order": b["order"]} for b in w["bosses"]]})
    delve_src = by_inst.get(("delve", 0))
    craft_src = by_inst.get(("crafted", 0))
    return {
        "raids": raids,
        "dungeons": dungeons,
        "key_levels": [{"level": k["level"], "ilevel": k["ilevel"], "vault_ilevel": k["vault_ilevel"], "track": k["track"], "vault_track": k["vault_track"]}
                       for k in s["key_levels"]],
        "world_bosses": world,
        "delves": [{"tier": x["tier"], "ilevel": x["ilevel"], "vault_ilevel": x["vault_ilevel"], "verified": x["verified"]} for x in s["delves"]],
        "delves_usable": usable_count(delve_src["bosses"]) if delve_src else 0,
        "crafted": {"ilevel": s["crafted"]["max_ilevel"], "voidforged_ilevel": s["crafted"]["voidforged_ilevel"],
                    "stats": list(s["crafted"]["stats"].values()), "usable": usable_count(craft_src["bosses"]) if craft_src else 0},
        "upgrade_tracks": {k: v["ilevels"] for k, v in s["upgrade_tracks"].items()},
    }


def validate_upgrade(upgrade: str | int) -> None:
    """Raise ``ValueError`` (400-able) for an ``upgrade`` selection that isn't 'drop', 'max',
    or a positive rank number."""
    if upgrade in ("drop", "max"):
        return
    try:
        rank = int(upgrade)
    except (TypeError, ValueError):
        raise ValueError(f"invalid upgrade value {upgrade!r}; expected 'drop', 'max', or a rank number") from None
    if rank < 1:
        raise ValueError(f"invalid upgrade value {upgrade!r}; rank must be >= 1")


def _upgraded(ilevel: int, track: str | None, rank: int | None, upgrade: str | int, tracks: dict) -> tuple[int, int | None]:
    """Apply the droptimizer's upgrade selection within the drop's own track."""
    validate_upgrade(upgrade)
    if upgrade == "drop" or not track or not rank or track not in tracks:
        return ilevel, rank
    ladder = tracks[track]["ilevels"]
    target = len(ladder) if upgrade == "max" else int(upgrade)
    target = max(rank, min(target, len(ladder)))
    return ladder[target - 1], target


def _nearest_key_level(level: int, keys_by_level: dict[int, dict]) -> dict | None:
    """The key-level table has gaps (e.g. no level 1 -- dungeons start tracking at 2), so a
    plain clamp to (min, max) can land on a level that isn't a key at all and silently drop
    every dungeon candidate. Clamp to the table's range, then snap to the nearest defined
    level at or above it (falling back to the highest one below)."""
    if not keys_by_level:
        return None
    avail = sorted(keys_by_level)
    lvl = max(min(level, avail[-1]), avail[0])
    if lvl not in keys_by_level:
        lvl = next((x for x in avail if x >= lvl), avail[-1])
    return keys_by_level[lvl]


def _dungeon_row(level: int, vault: bool, keys_by_level: dict[int, dict]) -> tuple[dict | None, bool, bool]:
    """(key-level row, use_vault, max_vault) for a ``DungeonSource`` selection.

    ``level == -1`` keeps meaning "max vault" (the highest defined key level's vault
    values); ``DungeonSource.vault=True`` at any other level means "this key level's own
    vault ilvl/bonus ids", not the end-of-dungeon ones."""
    max_vault = level == -1
    use_vault = max_vault or vault
    row = keys_by_level.get(max(keys_by_level)) if max_vault else _nearest_key_level(level, keys_by_level)
    return row, use_vault, max_vault


def _dungeon_ilevel(row: dict, use_vault: bool) -> tuple[int, str | None, int | None]:
    """(ilevel, track, rank) from a key-level row, vault or end-of-dungeon values."""
    if use_vault:
        return row["vault_ilevel"], row["vault_track"], row["vault_rank"]
    return row["ilevel"], row["track"], row["rank"]


def _track_bonus(tracks: dict, track: str | None, rank: int | None) -> list[int]:
    if track and rank and track in tracks and 0 < rank <= len(tracks[track]["bonus_ids"]):
        return [tracks[track]["bonus_ids"][rank - 1]]
    return []


_PAIRED_SLOTS: dict[frozenset[str], str] = {
    frozenset({"finger1", "finger2"}): "finger",
    frozenset({"trinket1", "trinket2"}): "trinket",
}


def _collapse_slot_pairs(slots: list[str]) -> list[str]:
    """A ring/trinket is usable in both concrete slots; emit it once under the generic
    slot name and let the sim engine (``target_slots``) expand it back to both slots at
    combo time, instead of producing one candidate per concrete slot (which the engine
    would then *also* expand, doubling every ring/trinket into duplicate rows)."""
    generic = _PAIRED_SLOTS.get(frozenset(slots))
    return [generic] if generic else slots


def candidates(profile: CharacterProfile, sources: list[DropSource], upgrade: str | int,
                offspec: bool = False) -> list[Item]:
    """Every usable item the selected sources can drop, resolved at the right item level.

    ``offspec`` (droptimizer's ``include_offspec``) passes through to :func:`usable_slots`:
    an item whose only granted primary stat isn't this spec's own is still offered when set.
    """
    s = season.load()
    d = db()
    tracks = s["upgrade_tracks"]
    cid = CLASS_IDS.get(normalize_class(profile.klass), 0)
    key = spec_key(profile.klass, profile.spec)
    prim = primary_stat(profile.klass, profile.spec)
    gear = Gear(profile)
    by_inst = {(src["kind"], src["instance_id"]): src for src in d["sources"]}
    keys_by_level = {k["level"]: k for k in s["key_levels"]}
    delves_by_tier = {x["tier"]: x for x in s["delves"]}

    plan: list[dict] = []       # {item, ilevel, track, rank, bonus_ids, source, tag, crafted}

    def add(item: dict, ilevel: int, track: str | None, rank: int | None, extra_bonus: list[int], src: ItemSource, tag: str,
            crafted: tuple[int, ...] = (), crafting_quality: int | None = None) -> None:
        if not ilevel:
            return
        lvl, rk = _upgraded(ilevel, track, rank, upgrade, tracks)
        plan.append({"item": item, "ilevel": lvl, "track": track, "rank": rk,
                     "bonus_ids": extra_bonus + _track_bonus(tracks, track, rk), "source": src, "tag": tag,
                     "crafted": crafted, "crafting_quality": crafting_quality})

    for sel in sources:
        if sel.type == "raid":
            src = by_inst.get(("raid", sel.instance_id))
            raid = next((r for r in s["raids"] if r["instance_id"] == sel.instance_id), None)
            if not src or not raid:
                continue
            fallback = raid["difficulties"].get(sel.difficulty, {})
            for b in src["bosses"]:
                if sel.bosses and b["encounter_id"] not in sel.bosses:
                    continue
                for it in b["items"]:
                    drop = (b.get("drops") or {}).get(sel.difficulty)
                    if drop is None and b.get("sequence") is not None:
                        drop = droplevels.drop_for(it["id"], b["sequence"], sel.difficulty)
                    lvl = drop["ilevel"] if drop else fallback.get("ilevel")
                    track = drop["track"] if drop else fallback.get("track")
                    rank = drop["step"] if drop else fallback.get("rank")
                    add(it, lvl, track, rank, [droplevels.DIFFICULTY_TAG_BONUS[sel.difficulty]],
                        ItemSource(type="raid", name=src["name"], boss=b["name"], difficulty=sel.difficulty),
                        f"raid:{src['instance_id']}:{sel.difficulty}:{b['encounter_id']}")
        elif sel.type == "dungeon":
            level = sel.key_level
            row, use_vault, max_vault = _dungeon_row(level, sel.vault, keys_by_level)
            if row is None:
                continue
            lvl, track, rank = _dungeon_ilevel(row, use_vault)
            tag_suffix = ":vault" if (use_vault and not max_vault) else ""
            for dg in s["dungeons"]:
                if sel.instance_ids and dg["instance_id"] not in sel.instance_ids:
                    continue
                src = by_inst.get(("dungeon", dg["instance_id"]))
                if not src:
                    continue
                for b in src["bosses"]:
                    for it in b["items"]:
                        add(it, lvl, track, rank, [MPLUS_TAG_BONUS] if level > 0 else [],
                            ItemSource(type="dungeon", name=src["name"], boss=b["name"], key_level=level),
                            f"dungeon:{src['instance_id']}:{level}{tag_suffix}")
        elif sel.type == "world_boss":
            for w in s["world_bosses"]:
                src = by_inst.get(("world_boss", w["instance_id"]))
                if not src:
                    continue
                for b in src["bosses"]:
                    for it in b["items"]:
                        add(it, w["ilevel"], w.get("track"), w.get("rank"), [],
                            ItemSource(type="world_boss", name=WORLD_BOSS_LABEL, boss=b["name"]), f"world_boss:{b['encounter_id']}")
        elif sel.type == "delve":
            src = by_inst.get(("delve", 0))
            row = delves_by_tier.get(min(max(sel.tier, 1), max(delves_by_tier)))
            if not src or not row:
                continue
            for b in src["bosses"]:
                for it in b["items"]:
                    add(it, row["ilevel"], row["track"], row["rank"], [],
                        ItemSource(type="delve", name="Delves", boss=b["name"], key_level=sel.tier), f"delve:{sel.tier}")
        elif sel.type == "crafted":
            src = by_inst.get(("crafted", 0))
            if not src:
                continue
            from toonopt.data.stats import CRAFTED_STAT_BY_NAME
            codes = tuple(CRAFTED_STAT_BY_NAME.get(x, 0) for x in sel.stats)
            if 0 in codes:
                raise ValueError(f"unknown crafted stats {sel.stats}; use {sorted(CRAFTED_STAT_BY_NAME)}")
            best: dict[tuple, dict] = {}
            for b in src["bosses"]:
                for it in b["items"]:
                    if not usable_slots(it, cid, key, offspec, gear):
                        continue
                    emb = it["limit_category"] in (512, 697)
                    k = (it["class_id"], it["subclass_id"], it["inv_type"], emb)
                    prev = best.get(k)
                    if prev is None or it["quality"] > prev["quality"] or (it["quality"] == prev["quality"] and it["id"] > prev["id"]):
                        best[k] = it
            for it in best.values():
                add(it, sel.ilevel or s["crafted"]["max_ilevel"], None, None, list(s["crafted"]["bonus_ids"]),
                    ItemSource(type="crafted", name="Crafted gear"), "crafted",
                    crafted=codes, crafting_quality=s["crafted"]["crafting_quality"])

    rows = items.rows({p["item"]["id"] for p in plan})
    icons = items.icons(list(rows))
    out: list[Item] = []
    seen: set[str] = set()
    for p in plan:
        it = p["item"]
        r = rows.get(it["id"])
        if r is None:
            continue
        slots = usable_slots(it, cid, key, offspec, gear)
        if not slots:
            continue
        for slot in _collapse_slot_pairs(slots):
            k = f"drop:{it['id']}:{slot}:{p['tag']}"
            if k in seen:
                continue
            seen.add(k)
            item = items.resolve_row(r, p["bonus_ids"], p["ilevel"], key=k, slot_hint=slot, icon_name=icons.get(it["id"], ""),
                                     crafted_stats=p["crafted"], crafting_quality=p["crafting_quality"])
            item.source = p["source"]
            if "primary" in item.stats and prim:
                item.stats[prim] = item.stats.pop("primary") + item.stats.get(prim, 0)
            out.append(item)
    return out
