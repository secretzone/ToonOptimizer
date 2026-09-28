"""Item stats at an item level, computed the way the game (and SimC) computes them.

Formula (SimC ``item_database::scaled_stat``, ported from localbots' itemStats.js which was
verified against in-game tooltips for a chest, a two-hander and a trinket at two levels):

    value = StatPercentEditor_i * RandPropPoints[ilevel][budget_slot] * 0.0001
    combat ratings  *= combat_ratings_mult_by_ilvl[rating_type][ilevel]
    stamina         *= stamina_mult_by_ilvl[rating_type][ilevel]
    round()

Budget column: quality 4+ (epic) -> EpicF, 3 -> SuperiorF, else GoodF. The two multiplier
curves come from SimC's generated ``sc_scale_data.inc`` (cached next to the tables) because
wago does not publish them for the current build.

Output keys are SimC-ish short names: agility, strength, intellect, stamina, crit, haste,
mastery, versatility, leech, avoidance, speed, plus ``armor`` for armour and
``weapon_dps`` / ``weapon_speed`` / ``weapon_min`` / ``weapon_max`` for weapons. Combined
primary stats (DB2 71-74, "Agility/Strength/Intellect") are reported under ``primary``;
callers that know the spec rename it (see :func:`toonopt.data.loot.candidates`).
"""
from __future__ import annotations

import re
from functools import lru_cache

from toonopt.data import wago

STAT_KEYS: dict[int, str] = {
    3: "agility", 4: "strength", 5: "intellect", 6: "spirit", 7: "stamina",
    32: "crit", 36: "haste", 40: "versatility", 49: "mastery",
    61: "speed", 62: "leech", 63: "avoidance",
    71: "primary", 72: "primary", 73: "primary", 74: "primary",
}
# DB2 stat id -> primary stats it grants (71-74 are the multi-stat combos)
STAT_GRANTS: dict[int, tuple[int, ...]] = {
    3: (3,), 4: (4,), 5: (5,), 71: (3, 4, 5), 72: (3, 4), 73: (3, 5), 74: (4, 5),
}
RATINGS = {32, 36, 40, 49, 61, 62, 63}
PRIMARY_COMBINED = {71, 72, 73, 74}
# SimC crafted_stats codes (verified empirically by localbots)
CRAFTED_STAT_CODES = {32: "crit", 36: "haste", 40: "versatility", 49: "mastery"}
CRAFTED_STAT_BY_NAME = {v: k for k, v in CRAFTED_STAT_CODES.items()}
# ItemSparse placeholder stat ids on crafted gear with player-chosen secondaries
CRAFT_PLACEHOLDERS = (24, 25)

# combat_rating_multiplier_type, in SimC's order
CR_ARMOR, CR_WEAPON, CR_TRINKET, CR_JEWELRY = 0, 1, 2, 3

# InventoryType
INV = {
    "HEAD": 1, "NECK": 2, "SHOULDERS": 3, "CHEST": 5, "WAIST": 6, "LEGS": 7, "FEET": 8,
    "WRISTS": 9, "HANDS": 10, "FINGER": 11, "TRINKET": 12, "WEAPON": 13, "SHIELD": 14,
    "RANGED": 15, "CLOAK": 16, "TWOHAND": 17, "ROBE": 20, "MAINHAND": 21, "OFFHAND": 22,
    "HOLDABLE": 23, "RANGEDRIGHT": 26,
}
_TWO_HAND_SUBCLASSES = {1, 5, 6, 8, 10, 2, 3, 18, 16}
_WEAPON_INV = {13, 17, 21, 22, 15, 26, 23, 14}


def budget_slot(inv_type: int, item_class: int, subclass: int) -> int:
    if item_class == 2:
        return 0 if subclass in _TWO_HAND_SUBCLASSES else 3
    if inv_type in (INV["HEAD"], INV["CHEST"], INV["LEGS"], INV["ROBE"]):
        return 0
    if inv_type in (INV["SHOULDERS"], INV["WAIST"], INV["FEET"], INV["HANDS"], INV["TRINKET"]):
        return 1
    if inv_type in (INV["NECK"], INV["FINGER"], INV["CLOAK"], INV["WRISTS"]):
        return 2
    return 3


def rating_type(inv_type: int) -> int:
    if inv_type in (INV["NECK"], INV["FINGER"]):
        return CR_JEWELRY
    if inv_type == INV["TRINKET"]:
        return CR_TRINKET
    if inv_type in _WEAPON_INV:
        return CR_WEAPON
    return CR_ARMOR


# ---------------------------------------------------------------------------
# SimC scaling curves

def _parse_curves(text: str, name: str) -> list[list[float]] | None:
    marker = f"__{name}[][1300] = {{"
    start = text.find(marker)
    if start < 0:
        return None
    open_ = text.find("{", start)
    depth = 0
    end = -1
    for i in range(open_, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return None
    body = text[open_ + 1:end]
    return [[float(x) for x in re.findall(r"-?\d+\.?\d*(?:e[-+]?\d+)?", m)]
            for m in re.findall(r"\{([^{}]*)\}", body)]


@lru_cache(maxsize=4)
def scaling(build: str | None = None) -> dict | None:
    path = wago.extra_path("sc_scale_data.inc", build)
    if not path.exists():
        return None
    text = re.sub(r"//[^\n]*", "", path.read_text("utf-8"))
    cr = _parse_curves(text, "combat_ratings_mult_by_ilvl")
    stam = _parse_curves(text, "stamina_mult_by_ilvl")
    if not cr or not stam:
        return None
    return {"cr": cr, "stam": stam}


# ---------------------------------------------------------------------------
# DB2 tables

@lru_cache(maxsize=4)
def _rpp(build: str | None = None) -> dict[int, dict]:
    df = wago.table("RandPropPoints", build)
    out = {}
    for row in df.iter_rows(named=True):
        out[int(row["ID"])] = {
            "epic": [row[f"EpicF_{i}"] for i in range(5)],
            "superior": [row[f"SuperiorF_{i}"] for i in range(5)],
            "good": [row[f"GoodF_{i}"] for i in range(5)],
            "damage_secondary": row["DamageSecondaryF"],
            "damage_replace": row["DamageReplaceStatF"],
        }
    return out


@lru_cache(maxsize=4)
def _dmg(build: str | None, two_hand: bool) -> dict[int, list[float]]:
    df = wago.table("ItemDamageTwoHand" if two_hand else "ItemDamageOneHand", build)
    return {int(r["ItemLevel"]): [r[f"Quality_{q}"] for q in range(7)] for r in df.iter_rows(named=True)}


@lru_cache(maxsize=4)
def _armor(build: str | None = None) -> tuple[dict[int, dict[int, float]], dict[int, dict[int, float]]]:
    tot = wago.table("ItemArmorTotal", build)
    loc = wago.table("ArmorLocation", build)
    totals = {int(r["ItemLevel"]): {1: r["Cloth"], 2: r["Leather"], 3: r["Mail"], 4: r["Plate"]}
              for r in tot.iter_rows(named=True)}
    # the generic Modifier column disagrees with the class-specific ones, so it is unused
    mods = {int(r["ID"]): {1: r["Clothmodifier"], 2: r["Leathermodifier"], 3: r["Chainmodifier"], 4: r["Platemodifier"]}
            for r in loc.iter_rows(named=True)}
    return totals, mods


def budget_for(ilevel: int, quality: int, build: str | None = None) -> list[float] | None:
    row = _rpp(build).get(int(ilevel))
    if not row:
        return None
    if quality >= 4:
        return row["epic"]
    if quality == 3:
        return row["superior"]
    return row["good"]


# ---------------------------------------------------------------------------

def compute(
    *,
    ilevel: int,
    quality: int,
    inv_type: int,
    item_class: int,
    subclass: int,
    allocs: list[tuple[int, int]],
    delay_ms: int = 0,
    dmg_variance: float = 0.0,
    crafted_stats: tuple[int, ...] | list[int] = (),
    build: str | None = None,
) -> dict[str, float]:
    """Stats for one item at ``ilevel``. ``allocs`` = [(stat_id, StatPercentEditor), ...]."""
    out: dict[str, float] = {}
    if not ilevel:
        return out
    budget = budget_for(ilevel, quality, build)
    curves = scaling(build)
    if budget is None:
        return out
    slot = budget_slot(inv_type, item_class, subclass)
    ctype = rating_type(inv_type)
    cr_mult = curves["cr"][ctype][ilevel - 1] if curves and ilevel - 1 < len(curves["cr"][ctype]) else 1.0
    st_mult = curves["stam"][ctype][ilevel - 1] if curves and ilevel - 1 < len(curves["stam"][ctype]) else 1.0

    crafted = list(crafted_stats)
    for stat, alloc in allocs:
        if stat in CRAFT_PLACEHOLDERS:
            if not crafted:
                continue
            stat = crafted[0] if stat == CRAFT_PLACEHOLDERS[0] else crafted[-1]
        if stat < 0 or not alloc:
            continue
        v = alloc * budget[slot] * 0.0001
        if stat in RATINGS:
            v *= cr_mult
        elif stat == 7:
            v *= st_mult
        value = round(v)
        if not value:
            continue
        key = STAT_KEYS.get(stat, f"stat_{stat}")
        out[key] = out.get(key, 0) + value

    if item_class == 2 and delay_ms:
        table = _dmg(build, slot == 0)
        row = table.get(int(ilevel))
        if row:
            dps = row[min(max(quality, 0), 6)]
            speed = delay_ms / 1000
            avg = dps * speed
            v = dmg_variance or 0.0
            lo = int(avg * (1 - v / 2))
            hi = int(avg * (1 + v / 2))
            out["weapon_min"] = lo
            out["weapon_max"] = hi
            out["weapon_speed"] = speed
            out["weapon_dps"] = int(((lo + hi) / 2) / speed * 10) / 10

    if item_class == 4 and 1 <= subclass <= 4:
        totals, mods = _armor(build)
        t = totals.get(int(ilevel))
        m = mods.get(inv_type)
        if t and m and m.get(subclass):
            out["armor"] = round(t[subclass] * m[subclass])
    return out
