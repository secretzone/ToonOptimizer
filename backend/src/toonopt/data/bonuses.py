"""Bonus-id decoding: item level, upgrade track, sockets, quality, crafted stats.

Primary source is Raidbots' ``bonuses.json`` (cached by :mod:`toonopt.data.wago`). Rules
learned from the live data for 12.1 (all confirmed against the MID2 SimC profiles):

* ``itemLevel.amount`` is an ABSOLUTE item level; when several bonus ids carry one the entry
  with the LOWEST ``priority`` number wins (crafted 244581: 12214 prio 100 -> 246, 13751 prio 70
  -> 292, 13836 prio 65 -> 318; the game shows 318 (+13 from 9627's ``levelOffset``) = 331).
* ``levelOffset.amount`` is added on top (crafting-quality offsets such as 9627 = +13).
* ``upgrade`` = {name, level, max, group, seasonId, itemLevel}. Season 37 (Midnight S2) owns
  groups 614-618 / bonus ids 12817-12856 plus 13848 (Myth 9 = Ascendant Voidforged 344).
* ``socket`` marks a bonus that adds a prismatic socket (13668, 1808, 13534, 13695, 13750...).
* ``quality`` overrides the item's quality (tracks carry 3 = rare on Adventurer, 4 elsewhere).
* ``craftedStats`` [a, b] are the SimC ``crafted_stats`` codes (32 crit 36 haste 40 vers 49 mastery).

When ``bonuses.json`` is missing the DB2 ``ItemBonus`` table is used for the classic types
(1 = +delta, 14 / 42 = set level, 6 = socket, 3 = quality); upgrade tracks then come from
``ItemBonusListGroupEntry`` + season.json's track ladders.
"""
from __future__ import annotations

import json
from functools import lru_cache

import polars as pl

from toonopt.data import wago

# SimC / DB2 ItemBonus.Type values we honour in the fallback path
ITEM_BONUS_ILEVEL = 1
ITEM_BONUS_MOD = 2
ITEM_BONUS_QUALITY = 3
ITEM_BONUS_SOCKET = 6
ITEM_BONUS_SET_ILEVEL = 14
ITEM_BONUS_UPGRADE_GROUP = 34      # Value_0 = ItemBonusListGroup id (upgrade track)
ITEM_BONUS_SET_ILEVEL_2 = 42

TRACK_ORDER = ["Adventurer", "Veteran", "Champion", "Hero", "Myth"]


@lru_cache(maxsize=4)
def bonus_map(build: str | None = None) -> dict[int, dict]:
    """Raidbots bonus map keyed by int bonus id ({} when the file is missing)."""
    path = wago.extra_path("bonuses.json", build)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001 - a corrupt bonus map just means fewer bonus ids decode
        return {}
    return {int(k): v for k, v in raw.items()}


def entry(bonus_id: int, build: str | None = None) -> dict:
    return bonus_map(build).get(int(bonus_id), {})


def upgrade_of(bonus_ids: list[int] | tuple[int, ...], build: str | None = None,
               season_id: int | None = None) -> dict | None:
    """The upgrade-track step encoded in ``bonus_ids``.

    Returns ``{track, level, max, ilevel, group, season_id, bonus_id}`` or None. With
    ``season_id`` only that season's tracks count (last season's gear keeps its level but
    loses its track, and its levels overlap this season's lower tracks, so never guess).
    """
    for b in bonus_ids:
        u = entry(b, build).get("upgrade")
        if not u or not u.get("name") or not u.get("level"):
            continue
        if season_id is not None and u.get("seasonId") != season_id:
            continue
        return {
            "track": u["name"], "level": int(u["level"]), "max": int(u.get("max") or 0),
            "ilevel": int(u["itemLevel"]) if u.get("itemLevel") else None,
            "group": u.get("group"), "season_id": u.get("seasonId"), "bonus_id": int(b),
        }
    return None


def ilevel_from_bonuses(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int | None:
    """Absolute item level from the Raidbots map (lowest priority number wins, ties broken by
    the highest item level -- e.g. ``[12854, 13848]`` both carry priority 0; SimC/the client
    show 344, the Voidforged level, regardless of which bonus id comes first) plus offsets."""
    best: tuple[int, int] | None = None   # (priority, level)
    offset = 0
    for b in bonus_ids:
        e = entry(b, build)
        lvl = e.get("itemLevel")
        if isinstance(lvl, dict) and lvl.get("amount"):
            prio = int(lvl.get("priority", 0))
            amount = int(lvl["amount"])
            if best is None or prio < best[0] or (prio == best[0] and amount > best[1]):
                best = (prio, amount)
        off = e.get("levelOffset")
        if isinstance(off, dict) and off.get("amount"):
            offset += int(off["amount"])
    if best is None:
        return None
    return best[1] + offset


def quality_from_bonuses(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int | None:
    q = [int(entry(b, build)["quality"]) for b in bonus_ids if entry(b, build).get("quality")]
    return max(q) if q else None


def socket_count(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int:
    return sum(int(entry(b, build).get("socket") or 0) for b in bonus_ids)


def socket_bonus_ids(build: str | None = None) -> set[int]:
    return {k for k, v in bonus_map(build).items() if v.get("socket")}


def crafted_stats_of(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> list[int]:
    for b in bonus_ids:
        cs = entry(b, build).get("craftedStats")
        if cs:
            return [int(x) for x in cs]
    return []


def limit_category_of(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> int | None:
    for b in bonus_ids:
        lc = entry(b, build).get("item_limit_category")
        if lc:
            return int(lc)
    return None


def tags_of(bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> list[str]:
    out = []
    for b in bonus_ids:
        t = entry(b, build).get("tag")
        if t and t not in out:
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# Upgrade-track ladders (bonus id per step) from DB2 groups + Raidbots levels

@lru_cache(maxsize=4)
def _group_entries(build: str | None = None) -> pl.DataFrame:
    return wago.table("ItemBonusListGroupEntry", build,
                      ["ItemBonusListGroupID", "ItemBonusListID", "SequenceValue"])


def group_ladder(group_id: int, build: str | None = None) -> list[dict]:
    """[{step, bonus_id, ilevel}] for one ItemBonusListGroup (sequence order)."""
    df = _group_entries(build).filter(pl.col("ItemBonusListGroupID") == group_id).sort("SequenceValue")
    out = []
    for step, b in zip(df["SequenceValue"].to_list(), df["ItemBonusListID"].to_list(), strict=True):
        out.append({"step": int(step), "bonus_id": int(b), "ilevel": ilevel_from_bonuses([b], build)})
    return out


def season_tracks(season_id: int, build: str | None = None) -> dict[str, dict]:
    """All upgrade tracks of ``season_id`` from the Raidbots map: name -> {group, max, steps:[...]}."""
    groups: dict[str, dict] = {}
    for b, e in bonus_map(build).items():
        u = e.get("upgrade")
        if not u or u.get("seasonId") != season_id or not u.get("name"):
            continue
        g = groups.setdefault(u["name"], {"name": u["name"], "group": u.get("group"),
                                          "max": int(u.get("max") or 0), "steps": {}})
        lvl = int(u["level"])
        g["steps"][lvl] = {"rank": lvl, "bonus_id": int(b), "ilevel": int(u["itemLevel"]) if u.get("itemLevel") else None}
        cur = u.get("currency")
        if cur:
            g.setdefault("crest", {"name": cur.get("name"), "currency_id": cur.get("id"),
                                   "cost": cur.get("amount"), "icon": cur.get("icon")})
    out = {}
    for name, g in groups.items():
        steps = [g["steps"][k] for k in sorted(g["steps"])]
        g["steps"] = steps
        g["ilevels"] = [s["ilevel"] for s in steps]
        g["bonus_ids"] = [s["bonus_id"] for s in steps]
        out[name] = g
    return dict(sorted(out.items(), key=lambda kv: TRACK_ORDER.index(kv[0]) if kv[0] in TRACK_ORDER else 99))


# ---------------------------------------------------------------------------
# DB2 fallback (no bonuses.json)

@lru_cache(maxsize=4)
def _item_bonus(build: str | None = None) -> pl.DataFrame:
    return wago.table("ItemBonus", build, ["ParentItemBonusListID", "Type", "Value_0", "Value_1"])


def db2_apply(base_ilevel: int, bonus_ids: list[int] | tuple[int, ...], build: str | None = None) -> dict:
    """{ilevel, quality, sockets, upgrade_group} from the DB2 ItemBonus rows of ``bonus_ids``."""
    if not bonus_ids:
        return {"ilevel": base_ilevel, "quality": None, "sockets": 0, "upgrade_group": None}
    df = _item_bonus(build).filter(pl.col("ParentItemBonusListID").is_in(list(bonus_ids)))
    ilevel = base_ilevel
    quality = None
    sockets = 0
    group = None
    for t, v0, v1 in zip(df["Type"].to_list(), df["Value_0"].to_list(), df["Value_1"].to_list(), strict=True):
        if t == ITEM_BONUS_ILEVEL:
            ilevel += int(v0)
        elif t in (ITEM_BONUS_SET_ILEVEL, ITEM_BONUS_SET_ILEVEL_2):
            ilevel = int(v0)
        elif t == ITEM_BONUS_QUALITY:
            quality = max(quality or 0, int(v0))
        elif t == ITEM_BONUS_SOCKET:
            sockets += int(v0)
        elif t == ITEM_BONUS_UPGRADE_GROUP:
            group = int(v0)
    return {"ilevel": ilevel, "quality": quality, "sockets": sockets, "upgrade_group": group}
