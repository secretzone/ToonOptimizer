"""Per-item raid drop levels (port of localbots' dropLevels.js, confirmed on live data).

The level a boss drops is not a property of the difficulty: it is the item's step on that
difficulty's upgrade track, and the step climbs through the instance. Three tables carry it:

    DungeonEncounter.ItemSequenceLevel   how far into the instance a boss sits (0-based)
    ItemBonusTreeNode                    per ItemContext (= difficulty) which upgrade-track
                                         GROUP a drop uses (keystone-gated nodes are M+)
    ItemBonusListGroupEntry              (group, sequence) -> track bonus id

A drop sits at step ItemSequenceLevel + 1. Live 12.1 check (The Venomous Abyss): bosses 1 /
2-3 / 4-6 / 7-8 have sequence levels 1 / 2 / 3 / 4, so Heroic drops read Hero 2/6 (308) on
Nek'zali and Hero 5/6 (318) on Ula'tek; the MID2 SimC profiles carry exactly those levels.
Item level of the resulting bonus id comes from the Raidbots map.
"""
from __future__ import annotations

from functools import lru_cache

from toonopt.data import bonuses, wago

# ItemContext, the game's own "where did this drop from" enum
DIFFICULTY_CONTEXT: dict[str, int] = {"lfr": 4, "normal": 3, "heroic": 5, "mythic": 6}
# difficulty tag bonus ids (Raidbots tags: Raid Finder / (Normal) / Heroic / Mythic)
DIFFICULTY_TAG_BONUS: dict[str, int] = {"lfr": 13332, "normal": 13333, "heroic": 13334, "mythic": 13335}
# M+ contexts seen on the 12.1 dungeon trees: end-of-dungeon (16) and vault (35)
MPLUS_CONTEXT_END = 16
MPLUS_CONTEXT_VAULT = 35
MPLUS_CONTEXT_M0 = 23


@lru_cache(maxsize=4)
def _tables(build: str | None = None) -> dict:
    ixb = wago.table("ItemXBonusTree", build, ["ItemBonusTreeID", "ItemID"])
    trees_by_item: dict[int, list[int]] = {}
    for tree, item in zip(ixb["ItemBonusTreeID"].to_list(), ixb["ItemID"].to_list(), strict=True):
        trees_by_item.setdefault(int(item), []).append(int(tree))
    btn = wago.table("ItemBonusTreeNode", build, [
        "ItemContext", "ChildItemBonusTreeID", "ChildItemBonusListID", "ChildItemBonusListGroupID",
        "MinMythicPlusLevel", "MaxMythicPlusLevel", "ParentItemBonusTreeID",
    ])
    nodes_by_tree: dict[int, list[dict]] = {}
    for r in btn.iter_rows(named=True):
        nodes_by_tree.setdefault(int(r["ParentItemBonusTreeID"]), []).append(r)
    ge = wago.table("ItemBonusListGroupEntry", build, ["ItemBonusListGroupID", "ItemBonusListID", "SequenceValue"])
    by_step: dict[tuple[int, int], int] = {}
    for g, b, s in zip(ge["ItemBonusListGroupID"].to_list(), ge["ItemBonusListID"].to_list(), ge["SequenceValue"].to_list(), strict=True):
        by_step[(int(g), int(s))] = int(b)
    de = wago.table("DungeonEncounter", build, ["ID", "ItemSequenceLevel"])
    seq = {int(i): int(s) for i, s in zip(de["ID"].to_list(), de["ItemSequenceLevel"].to_list(), strict=True)}
    return {"trees_by_item": trees_by_item, "nodes_by_tree": nodes_by_tree, "by_step": by_step, "sequence": seq}


def sequence_level(dungeon_encounter_id: int, build: str | None = None) -> int | None:
    return _tables(build)["sequence"].get(int(dungeon_encounter_id))


def walk(item_id: int, build: str | None = None) -> list[dict]:
    """Every ItemBonusTreeNode reachable from the item's bonus trees."""
    t = _tables(build)
    seen: set[int] = set()
    out: list[dict] = []

    def rec(tree: int) -> None:
        if tree in seen:
            return
        seen.add(tree)
        for n in t["nodes_by_tree"].get(tree, []):
            out.append(n)
            child = int(n["ChildItemBonusTreeID"] or 0)
            if child:
                rec(child)

    for tree in t["trees_by_item"].get(int(item_id), []):
        rec(tree)
    return out


@lru_cache(maxsize=4096)
def groups_for(item_id: int, build: str | None = None) -> dict[int, int]:
    """ItemContext -> upgrade group for non-keystone nodes of this item."""
    found: dict[int, int] = {}
    for n in walk(item_id, build):
        group = int(n["ChildItemBonusListGroupID"] or 0)
        if group and not int(n["MinMythicPlusLevel"] or 0) and not int(n["MaxMythicPlusLevel"] or 0):
            found.setdefault(int(n["ItemContext"]), group)
    return found


@lru_cache(maxsize=4096)
def keystone_groups_for(item_id: int, build: str | None = None) -> dict[int, list[tuple[int, int, int]]]:
    """ItemContext -> [(min_key, max_key, group)] for keystone-gated nodes (max 0 = open-ended)."""
    found: dict[int, list[tuple[int, int, int]]] = {}
    for n in walk(item_id, build):
        group = int(n["ChildItemBonusListGroupID"] or 0)
        lo, hi = int(n["MinMythicPlusLevel"] or 0), int(n["MaxMythicPlusLevel"] or 0)
        if group and (lo or hi):
            found.setdefault(int(n["ItemContext"]), []).append((lo, hi, group))
    return found


def step_bonus(group: int, step: int, build: str | None = None) -> int | None:
    return _tables(build)["by_step"].get((int(group), int(step)))


def drop_for(item_id: int, sequence: int, difficulty: str, build: str | None = None) -> dict | None:
    """{ilevel, track, step, max, bonus_id} for one difficulty, or None when the item has no
    track there (last season's leftovers sit on retired groups)."""
    group = groups_for(item_id, build).get(DIFFICULTY_CONTEXT[difficulty])
    if not group:
        return None
    b = step_bonus(group, int(sequence) + 1, build)
    if not b:
        return None
    up = bonuses.upgrade_of([b], build)
    if not up or not up["ilevel"]:
        lvl = bonuses.ilevel_from_bonuses([b], build)
        if not lvl:
            return None
        return {"ilevel": lvl, "track": None, "step": None, "max": None, "bonus_id": b}
    return {"ilevel": up["ilevel"], "track": up["track"], "step": up["level"], "max": up["max"], "bonus_id": b}


def drops_for(item_id: int, sequence: int, build: str | None = None) -> dict[str, dict]:
    out = {}
    for diff in DIFFICULTY_CONTEXT:
        d = drop_for(item_id, sequence, diff, build)
        if d:
            out[diff] = d
    return out


def mplus_track_group(item_id: int, key_level: int, vault: bool, build: str | None = None) -> int | None:
    """Upgrade group an M+ drop of ``item_id`` uses at ``key_level`` (0 = M0)."""
    if key_level <= 0:
        return groups_for(item_id, build).get(MPLUS_CONTEXT_M0)
    ctx = MPLUS_CONTEXT_VAULT if vault else MPLUS_CONTEXT_END
    for lo, hi, group in keystone_groups_for(item_id, build).get(ctx, []):
        if key_level >= lo and (hi == 0 or key_level <= hi):
            return group
    return None
