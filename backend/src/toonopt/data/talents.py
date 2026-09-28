"""Talent trees and Blizzard loadout-string decoding from the Trait* DB2 tables.

Tree lookup: ``TraitTreeLoadout`` maps a ``ChrSpecialization`` to its trees; the class
talent tree is the one whose ``TraitTree.TraitSystemID`` is 0 with the most nodes (the
other system-0 rows are small auxiliary trees). Nodes visible to a spec are those without a
spec condition (``TraitCond.CondType == 1`` through ``TraitNodeGroupXTraitCond`` or
``TraitNodeXTraitCond``) or whose condition's ``SpecSetMember`` includes the spec. Class vs
spec placement follows the trait currency the node's group spends (``CondType 0`` with a
``TraitCurrencyID``; the currency whose nodes sit further left is the class one); hero nodes
carry ``TraitNode.TraitSubTreeID``.

Loadout strings (``Blizzard_ClassTalentImportExport.lua`` version 2, mirrored by SimC's
``parse_traits_hash``): a base64 bit stream, LSB first per character. Header = 8-bit version,
16-bit spec id, 128-bit tree hash (ignored). Then for EVERY node of the class tree in
ascending node id: 1 bit selected; if selected 1 bit purchased; if purchased 1 bit partial
(+ 6-bit rank) and 1 bit choice (+ 2-bit entry index, in ``TraitNodeXTraitNodeEntry._Index``
order). A selected-but-not-purchased node is granted (rank 1).
"""
from __future__ import annotations

import re
from functools import lru_cache

import polars as pl

from toonopt.data import wago
from toonopt.data.loot import CLASS_IDS, CLASS_SLUG_BY_ID, normalize_class

B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
SERIALIZATION_VERSION = 2
NODE_TYPES = {0: "single", 1: "tiered", 2: "choice", 3: "subtree"}
ENTRY_SUBTREE = 13          # TraitNodeEntry.NodeEntryType for hero-tree choices
COND_CURRENCY = 0
COND_SPEC = 1
COND_GRANTED = 2


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


@lru_cache(maxsize=1)
def specs(build: str | None = None) -> list[dict]:
    df = wago.table("ChrSpecialization", build, ["ID", "Name_lang", "ClassID", "Role"])
    return [{"id": int(r["ID"]), "name": str(r["Name_lang"]), "slug": _slug(r["Name_lang"]), "class_id": int(r["ClassID"]),
             "role": int(r["Role"])} for r in df.iter_rows(named=True) if int(r["ClassID"]) > 0 and r["Name_lang"] != "Initial"]


def spec_id(klass: str, spec: str, build: str | None = None) -> int:
    cid = CLASS_IDS.get(normalize_class(klass))
    if not cid:
        raise KeyError(f"unknown class {klass!r}")
    want = _slug(spec)
    for s in specs(build):
        if s["class_id"] == cid and s["slug"] == want:
            return s["id"]
    raise KeyError(f"unknown spec {spec!r} for {klass}")


def spec_of_id(sid: int, build: str | None = None) -> dict | None:
    return next((s for s in specs(build) if s["id"] == sid), None)


@lru_cache(maxsize=64)
def class_tree_id(sid: int, build: str | None = None) -> int:
    tl = wago.table("TraitTreeLoadout", build)
    tt = wago.table("TraitTree", build, ["ID", "TraitSystemID"])
    tn = wago.table("TraitNode", build, ["ID", "TraitTreeID"])
    trees = tl.filter(pl.col("ChrSpecializationID") == sid).join(tt, left_on="TraitTreeID", right_on="ID") \
        .filter(pl.col("TraitSystemID") == 0)["TraitTreeID"].unique().to_list()
    if not trees:
        raise KeyError(f"no talent tree for spec {sid}")
    counts = tn.filter(pl.col("TraitTreeID").is_in(trees)).group_by("TraitTreeID").len()
    return int(counts.sort("len", descending=True)["TraitTreeID"][0])


def _icon_names(file_ids: list[int], build: str | None) -> dict[int, str]:
    if not file_ids:
        return {}
    mid = wago.table("ManifestInterfaceData", build, ["ID", "FileName"]).filter(pl.col("ID").is_in(file_ids))
    out = {}
    for i, n in zip(mid["ID"].to_list(), mid["FileName"].to_list(), strict=True):
        n = str(n or "")
        out[int(i)] = (n[:-4] if n.lower().endswith(".blp") else n).lower()
    return out


@lru_cache(maxsize=16)
def tree_data(tree_id: int, build: str | None = None) -> dict:
    """Everything about one class tree: nodes (sorted by id), entries, edges, sub-trees, gating."""
    tn = wago.table("TraitNode", build).filter(pl.col("TraitTreeID") == tree_id)
    node_ids = [int(x) for x in tn["ID"].to_list()]
    tnx = wago.table("TraitNodeXTraitNodeEntry", build).filter(pl.col("TraitNodeID").is_in(node_ids))
    tne = wago.table("TraitNodeEntry", build)
    td = wago.table("TraitDefinition", build, ["ID", "SpellID", "OverrideName_lang", "OverrideIcon", "VisibleSpellID"])
    entries = tnx.join(tne, left_on="TraitNodeEntryID", right_on="ID") \
        .join(td, left_on="TraitDefinitionID", right_on="ID", how="left").sort(["TraitNodeID", "_Index"])
    spell_ids = sorted({int(s) for s in entries["SpellID"].to_list() if s} | {int(s) for s in entries["VisibleSpellID"].to_list() if s})
    sn = wago.table("SpellName", build).filter(pl.col("ID").is_in(spell_ids))
    spell_names = {int(i): str(n) for i, n in zip(sn["ID"].to_list(), sn["Name_lang"].to_list(), strict=True)}
    sm = wago.table("SpellMisc", build, ["SpellID", "DifficultyID", "SpellIconFileDataID"]) \
        .filter(pl.col("SpellID").is_in(spell_ids)).sort("DifficultyID").group_by("SpellID").first()
    spell_icon_file = {int(s): int(f) for s, f in zip(sm["SpellID"].to_list(), sm["SpellIconFileDataID"].to_list(), strict=True) if f}
    file_ids = sorted(set(spell_icon_file.values()) | {int(x) for x in entries["OverrideIcon"].to_list() if x})
    icon_names = _icon_names(file_ids, build)

    ent_by_node: dict[int, list[dict]] = {}
    for r in entries.iter_rows(named=True):
        spell = int(r["SpellID"] or 0)
        name = r["OverrideName_lang"] or spell_names.get(spell) or spell_names.get(int(r["VisibleSpellID"] or 0)) or ""
        file_id = int(r["OverrideIcon"] or 0) or spell_icon_file.get(spell, 0)
        ent_by_node.setdefault(int(r["TraitNodeID"]), []).append({
            "id": int(r["TraitNodeEntryID"]), "index": int(r["_Index"]), "name": str(name), "spell_id": spell,
            "icon": icon_names.get(file_id, ""), "max_ranks": int(r["MaxRanks"] or 0), "type": int(r["NodeEntryType"] or 0),
            "subtree_id": int(r["TraitSubTreeID"] or 0) or None,
        })

    # gating: node -> spec sets, currency, and (CondType 0) a SpentAmountRequired row-unlock threshold
    tc = wago.table("TraitCond", build, ["ID", "CondType", "SpecSetID", "TraitCurrencyID", "TraitTreeID", "SpentAmountRequired"]) \
        .filter(pl.col("TraitTreeID") == tree_id)
    conds = {int(r["ID"]): r for r in tc.iter_rows(named=True)}
    ssm = wago.table("SpecSetMember", build)
    spec_sets: dict[int, set[int]] = {}
    for ss, sid in zip(ssm["SpecSet"].to_list(), ssm["ChrSpecializationID"].to_list(), strict=True):
        spec_sets.setdefault(int(ss), set()).add(int(sid))
    tng = wago.table("TraitNodeGroup", build).filter(pl.col("TraitTreeID") == tree_id)
    group_ids = [int(g) for g in tng["ID"].to_list()]
    gxc = wago.table("TraitNodeGroupXTraitCond", build).filter(pl.col("TraitNodeGroupID").is_in(group_ids))
    group_conds: dict[int, list[dict]] = {}
    for g, c in zip(gxc["TraitNodeGroupID"].to_list(), gxc["TraitCondID"].to_list(), strict=True):
        if int(c) in conds:
            group_conds.setdefault(int(g), []).append(conds[int(c)])
    gxn = wago.table("TraitNodeGroupXTraitNode", build).filter(pl.col("TraitNodeID").is_in(node_ids))
    node_conds: dict[int, list[dict]] = {}
    for g, n in zip(gxn["TraitNodeGroupID"].to_list(), gxn["TraitNodeID"].to_list(), strict=True):
        node_conds.setdefault(int(n), []).extend(group_conds.get(int(g), []))
    nxc = wago.table("TraitNodeXTraitCond", build).filter(pl.col("TraitNodeID").is_in(node_ids))
    for n, c in zip(nxc["TraitNodeID"].to_list(), nxc["TraitCondID"].to_list(), strict=True):
        if int(c) in conds:
            node_conds.setdefault(int(n), []).append(conds[int(c)])

    # class / spec currency split: the currency whose nodes are further left is the class one
    cur_x: dict[int, list[int]] = {}
    pos = {int(r["ID"]): (int(r["PosX"]), int(r["PosY"])) for r in tn.iter_rows(named=True)}
    for n, cs in node_conds.items():
        for c in cs:
            if int(c["CondType"]) == COND_CURRENCY and int(c["TraitCurrencyID"] or 0):
                cur_x.setdefault(int(c["TraitCurrencyID"]), []).append(pos[n][0])
    class_currency = min(cur_x, key=lambda c: sum(cur_x[c]) / len(cur_x[c])) if cur_x else None
    xs = sorted(x for x, _ in pos.values())
    mid_x = xs[len(xs) // 2] if xs else 0

    te = wago.table("TraitEdge", build, ["LeftTraitNodeID", "RightTraitNodeID", "Type"]).filter(pl.col("LeftTraitNodeID").is_in(node_ids))
    edges = [(int(a), int(b)) for a, b in zip(te["LeftTraitNodeID"].to_list(), te["RightTraitNodeID"].to_list(), strict=True)]
    tst = wago.table("TraitSubTree", build, ["ID", "Name_lang", "TraitTreeID"]).filter(pl.col("TraitTreeID") == tree_id)
    subtrees = {int(i): str(n) for i, n in zip(tst["ID"].to_list(), tst["Name_lang"].to_list(), strict=True)}

    nodes = []
    for r in tn.sort("ID").iter_rows(named=True):
        nid = int(r["ID"])
        ents = ent_by_node.get(nid, [])
        cs = node_conds.get(nid, [])
        spec_ok: set[int] | None = None
        for c in cs:
            if int(c["CondType"]) == COND_SPEC and int(c["SpecSetID"] or 0):
                spec_ok = (spec_ok or set()) | spec_sets.get(int(c["SpecSetID"]), set())
        currencies = {int(c["TraitCurrencyID"]) for c in cs if int(c["CondType"]) == COND_CURRENCY and int(c["TraitCurrencyID"] or 0)}
        granted = any(int(c["CondType"]) == COND_GRANTED for c in cs)          # auto-selected, costs no point
        points_required = max((int(c["SpentAmountRequired"] or 0) for c in cs if int(c["CondType"]) == COND_CURRENCY), default=0)
        sub = int(r["TraitSubTreeID"] or 0)
        if int(r["Type"] or 0) == 3:
            section = "selection"          # the hero-tree picker node
        elif sub:
            section = "hero"
        elif class_currency is not None and currencies:
            section = "class" if class_currency in currencies else "spec"
        else:
            section = "class" if pos[nid][0] < mid_x else "spec"
        ntype = int(r["Type"] or 0)
        max_ranks = sum(e["max_ranks"] for e in ents) if ntype == 1 else (ents[0]["max_ranks"] if ents else 0)
        nodes.append({
            "id": nid, "x": pos[nid][0], "y": pos[nid][1], "type": NODE_TYPES.get(ntype, str(ntype)), "node_type": ntype,
            "section": section, "subtree_id": sub or None, "max_ranks": max_ranks, "entries": ents,
            "name": ents[0]["name"] if ents else "", "spell_id": ents[0]["spell_id"] if ents else 0,
            "icon": ents[0]["icon"] if ents else "", "specs": sorted(spec_ok) if spec_ok is not None else None,
            "next": sorted({b for a, b in edges if a == nid}), "prev": sorted({a for a, b in edges if b == nid}),
            "flags": int(r["Flags"] or 0), "granted": granted, "points_required": points_required,
            "currencies": sorted(currencies),
        })
    return {"tree_id": tree_id, "nodes": nodes, "subtrees": subtrees, "edges": edges}


def _visible(node: dict, sid: int) -> bool:
    return node["specs"] is None or sid in node["specs"]


def tree(klass: str, spec: str) -> dict:
    """{class_tree, spec_tree, hero_trees, spec_id, tree_id} -- nodes visible to the spec."""
    sid = spec_id(klass, spec)
    data = tree_data(class_tree_id(sid))
    vis = [n for n in data["nodes"] if _visible(n, sid) and n["x"] > 0 and n["y"] > 0]
    heroes: dict[int, list[dict]] = {}
    for n in vis:
        if n["section"] == "hero" and n["subtree_id"]:
            heroes.setdefault(n["subtree_id"], []).append(n)
    return {
        "spec_id": sid, "tree_id": data["tree_id"],
        "class_tree": [n for n in vis if n["section"] == "class"],
        "spec_tree": [n for n in vis if n["section"] == "spec"],
        "hero_trees": [{"id": hid, "name": data["subtrees"].get(hid, ""), "nodes": ns} for hid, ns in sorted(heroes.items())],
    }


class _Bits:
    def __init__(self, s: str):
        self.s = s.strip()
        self.head = 0
        self.total = len(self.s) * 6

    def read(self, n: int) -> int:
        v = 0
        for i in range(n):
            if self.head >= self.total:
                raise ValueError("the talent string ends unexpectedly")
            c = B64.find(self.s[self.head // 6])
            if c < 0:
                raise ValueError("the talent string has invalid characters")
            v |= ((c >> (self.head % 6)) & 1) << i
            self.head += 1
        return v


def decode(klass: str, spec: str, loadout: str) -> dict:
    """Decode a Blizzard export string into {selected: [{node_id, rank, entry_id, ...}], hero_tree, ...}."""
    bits = _Bits(loadout)
    version = bits.read(8)
    if version != SERIALIZATION_VERSION:
        return {"selected": [], "hero_tree": None, "spec_id": None, "supported": False,
                "error": f"loadout format version {version} is not supported (expected {SERIALIZATION_VERSION})"}
    sid = bits.read(16)
    tree_hash = [bits.read(8) for _ in range(16)]   # ignored for gameplay purposes, like SimC does; kept for encode()
    info = spec_of_id(sid)
    if info is None:
        return {"selected": [], "hero_tree": None, "spec_id": sid, "supported": False, "error": f"unknown spec id {sid}",
                "tree_hash": tree_hash}
    want = None
    try:
        want = spec_id(klass, spec)
    except KeyError:
        pass
    data = tree_data(class_tree_id(sid))
    selected: list[dict] = []
    hero_ids: set[int] = set()
    for node in data["nodes"]:      # ascending id == export order
        if not bits.read(1):
            continue
        ents = node["entries"]
        entry = ents[0] if ents else None
        rank = node["max_ranks"] or 1
        purchased = bool(bits.read(1))
        if not purchased:
            rank = 1               # granted, not purchased -- some nodes are free only in some
        else:                       # hero-tree/spec contexts, so this bit (not static tree data) is authoritative
            if bits.read(1):
                rank = bits.read(6)
            if bits.read(1):
                idx = bits.read(2)
                if idx >= len(ents):
                    raise ValueError(f"choice index {idx} out of range on node {node['id']}")
                entry = ents[idx]
        if node["node_type"] == 1 and len(ents) > 1:      # tiered: spread ranks across entries
            left = rank
            for e in ents:
                take = min(left, e["max_ranks"])
                if take <= 0:
                    break
                selected.append({"node_id": node["id"], "rank": take, "entry_id": e["id"], "name": e["name"],
                                 "spell_id": e["spell_id"], "section": node["section"], "purchased": purchased})
                left -= take
            continue
        selected.append({"node_id": node["id"], "rank": rank, "entry_id": entry["id"] if entry else None,
                         "name": entry["name"] if entry else "", "spell_id": entry["spell_id"] if entry else 0,
                         "section": node["section"], "purchased": purchased})
        if entry and entry["type"] == ENTRY_SUBTREE and entry["subtree_id"]:
            hero_ids.add(entry["subtree_id"])
        elif node["subtree_id"]:
            hero_ids.add(node["subtree_id"])
    hero = min(hero_ids) if hero_ids else None
    out = {
        "spec_id": sid, "spec": info["slug"], "klass": CLASS_SLUG_BY_ID.get(info["class_id"]),
        "tree_id": data["tree_id"], "supported": True,
        "selected": selected, "tree_hash": tree_hash,
        "hero_tree": {"id": hero, "name": data["subtrees"].get(hero, "")} if hero else None,
        "counts": {s: sum(1 for x in selected if x["section"] == s) for s in ("class", "spec", "hero")},
    }
    if want is not None and want != sid:
        out["warning"] = f"loadout is for spec {sid} ({info['slug']}), not {klass} {spec}"
    return out


class _BitWriter:
    """Inverse of :class:`_Bits`: LSB-first per base64 character, zero-padded to a full character
    (real export strings pad their trailing partial character with zero bits, so this round-trips
    byte-for-byte with :func:`decode`)."""

    def __init__(self) -> None:
        self.bits: list[int] = []

    def write(self, value: int, n: int) -> None:
        for i in range(n):
            self.bits.append((value >> i) & 1)

    def to_string(self) -> str:
        bits = self.bits + [0] * (-len(self.bits) % 6)
        out = []
        for i in range(0, len(bits), 6):
            v = 0
            for j in range(6):
                v |= bits[i + j] << j
            out.append(B64[v])
        return "".join(out)


def _hero_subtree_id(data: dict, hero_tree: int | str) -> int:
    if isinstance(hero_tree, int):
        return hero_tree
    if isinstance(hero_tree, str) and hero_tree.strip().isdigit():
        return int(hero_tree)
    want = _slug(hero_tree)
    for hid, name in data["subtrees"].items():
        if _slug(name) == want:
            return hid
    raise KeyError(f"unknown hero tree {hero_tree!r}")


def _apply_hero_tree(data: dict, sid: int, by_node: dict[int, list[dict]], hero_tree: int | str) -> None:
    """Force the hero-tree picker node visible to ``sid`` to select ``hero_tree`` (id or name)."""
    target = _hero_subtree_id(data, hero_tree)
    for node in data["nodes"]:
        if node["node_type"] != 3 or not _visible(node, sid):
            continue
        for e in node["entries"]:
            if e.get("subtree_id") == target:
                by_node[node["id"]] = [{"node_id": node["id"], "entry_id": e["id"], "rank": 1}]
                return
    raise KeyError(f"hero tree {hero_tree!r} is not available for {sid}")


def encode(klass: str, spec: str, selections: dict | list[dict], hero_tree: int | str | None = None) -> str:
    """Encode a set of talent selections into a Blizzard-importable loadout string.

    Inverse of :func:`decode`: ``encode(klass, spec, decode(klass, spec, s)) == s`` bit-for-bit
    (the trailing base64 character is zero-padded either way). ``selections`` is either the
    ``selected`` list ``decode`` returns -- dicts shaped ``{node_id, entry_id, rank}`` -- or a
    full ``decode()`` result, in which case its ``tree_hash`` and ``hero_tree`` are reused unless
    ``hero_tree`` overrides them. Nodes with no matching selection are left unselected; a node
    flagged ``granted`` in the tree data (free, e.g. some baseline/hero-tree nodes) is always
    written as selected-but-not-purchased when present, matching the client's own export.
    """
    sid = spec_id(klass, spec)
    tree_hash = [0] * 16
    hero = hero_tree
    if isinstance(selections, dict):
        if selections.get("supported") is False:
            raise ValueError(selections.get("error") or "cannot encode an unsupported loadout")
        entries = selections.get("selected", [])
        if selections.get("tree_hash"):
            tree_hash = [int(b) for b in selections["tree_hash"]]
        if hero is None:
            ht = selections.get("hero_tree")
            hero = ht.get("id") if isinstance(ht, dict) else ht
    else:
        entries = list(selections or [])

    data = tree_data(class_tree_id(sid))
    by_node: dict[int, list[dict]] = {}
    for e in entries:
        by_node.setdefault(int(e["node_id"]), []).append(e)
    if hero is not None:
        _apply_hero_tree(data, sid, by_node, hero)

    w = _BitWriter()
    w.write(SERIALIZATION_VERSION, 8)
    w.write(sid, 16)
    for b in tree_hash:
        w.write(int(b), 8)
    for node in data["nodes"]:      # ascending id -- must match decode()'s iteration order exactly
        sels = by_node.get(node["id"])
        if not sels:
            w.write(0, 1)            # not selected
            continue
        w.write(1, 1)                # selected
        purchased = sels[0].get("purchased")
        if purchased is None:
            purchased = not node["granted"]         # no per-selection flag given: fall back to the static guess
        if not purchased:
            w.write(0, 1)            # not purchased: free node, no further bits (rank is implicitly 1)
            continue
        w.write(1, 1)                # purchased
        ents = node["entries"]
        if node["node_type"] == 1 and len(ents) > 1:        # tiered: one rank total, spread over entries
            by_entry = {int(s["entry_id"]): s for s in sels if s.get("entry_id") is not None}
            total = 0
            for e in ents:
                s = by_entry.get(e["id"])
                if s is None:
                    continue
                r = s.get("rank")
                total += int(r) if r is not None else e["max_ranks"]
            partial = total != node["max_ranks"]
            w.write(1 if partial else 0, 1)
            if partial:
                w.write(total, 6)
            w.write(0, 1)             # tiered nodes never carry a choice bit
            continue
        s = sels[0]
        idx = 0
        if s.get("entry_id") is not None:
            idx = next((i for i, e in enumerate(ents) if e["id"] == s["entry_id"]), 0)
        rank = int(s["rank"]) if s.get("rank") is not None else (node["max_ranks"] or 1)
        partial = rank != (node["max_ranks"] or 1)
        w.write(1 if partial else 0, 1)
        if partial:
            w.write(rank, 6)
        if node["node_type"] in (2, 3):                     # choice node or hero-tree picker
            w.write(1, 1)
            w.write(idx, 2)
        else:
            w.write(0, 1)
    return w.to_string()


def _name_index(nodes: list[dict]) -> dict[str, list[tuple[dict, dict]]]:
    idx: dict[str, list[tuple[dict, dict]]] = {}
    for n in nodes:
        for e in n["entries"]:
            if not e["name"]:
                continue
            idx.setdefault(e["name"].strip().lower(), []).append((n, e))
    return idx


def names(klass: str, spec: str, loadout: str) -> dict:
    """Selected talent names for a loadout, grouped by class/spec/hero section.

    ``{"class": [...], "spec": [...], "hero": [...], "hero_tree": {id, name} | None}``; a name is
    suffixed ``" (N)"`` when invested above rank 1. Unsupported loadouts return empty lists plus
    an ``"error"`` key.
    """
    d = decode(klass, spec, loadout)
    if not d.get("supported"):
        return {"class": [], "spec": [], "hero": [], "hero_tree": None, "error": d.get("error")}
    by_node: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    for x in d["selected"]:      # a tiered node spreads across several entries; fold them back into one rank
        if not x["name"] or x["section"] not in ("class", "spec", "hero"):
            continue
        key = (x["section"], x["node_id"])
        if key not in by_node:
            by_node[key] = {"name": x["name"], "rank": 0}
            order.append(key)
        by_node[key]["rank"] += x["rank"]
    out: dict[str, list[str]] = {"class": [], "spec": [], "hero": []}
    for section, node_id in order:
        info = by_node[(section, node_id)]
        out[section].append(info["name"] if info["rank"] <= 1 else f"{info['name']} ({info['rank']})")
    return {**out, "hero_tree": d["hero_tree"]}


def modify(klass: str, spec: str, base: str, add: list[str] | None = None, remove: list[str] | None = None) -> dict:
    """Remove then add named talents on top of ``base``, re-encoding the result.

    Talents are resolved case-insensitively by their spell/definition name (for a choice node,
    name the entry you want); ``remove`` is applied before ``add`` so a choice node can be
    re-picked in one call. Each requested name is validated independently against the point
    budget (the section's own current total in ``base`` -- i.e. you can reshuffle points but not
    manufacture new ones), row-unlock gates (``TraitCond`` ``SpentAmountRequired``) and
    ``TraitEdge`` parent prerequisites (satisfied if *any* listed parent is selected); a talent
    that would violate one of these, or that names an unknown/already-selected/not-selected
    talent, is skipped and reported in ``errors`` rather than silently applied.

    Returns ``{string, changes: [{action, name, node_id, section}], errors: [str], points}``
    where ``points`` is ``{section: {spent, budget}}`` for class/spec/hero after the edit.
    """
    add = list(add or [])
    remove = list(remove or [])
    d = decode(klass, spec, base)
    if not d.get("supported"):
        return {"string": base, "changes": [], "errors": [d.get("error") or "unsupported base loadout"], "points": {}}
    sid = d["spec_id"]
    data = tree_data(class_tree_id(sid))
    nodes_by_id = {n["id"]: n for n in data["nodes"]}
    visible = tree(klass, spec)
    name_idx = _name_index(visible["class_tree"] + visible["spec_tree"] + [n for h in visible["hero_trees"] for n in h["nodes"]])

    by_node: dict[int, list[dict]] = {}
    for x in d["selected"]:
        by_node.setdefault(x["node_id"], []).append({"node_id": x["node_id"], "entry_id": x["entry_id"], "rank": x["rank"]})

    budgets = {s: sum(x["rank"] for x in d["selected"] if x["section"] == s) for s in ("class", "spec", "hero")}

    def spent(section: str) -> int:
        return sum(sum(int(s.get("rank") or 0) for s in sels) for nid, sels in by_node.items()
                   if (n := nodes_by_id.get(nid)) and n["section"] == section)

    changes: list[dict] = []
    errors: list[str] = []

    for name in remove:
        hits = name_idx.get(name.strip().lower())
        if not hits:
            errors.append(f"unknown talent: {name}")
            continue
        node, entry = hits[0]
        if node["granted"]:
            errors.append(f"cannot remove {name}: it is automatically granted")
            continue
        sels = by_node.get(node["id"])
        if not sels or not any(s.get("entry_id") == entry["id"] for s in sels):
            errors.append(f"{name} is not currently selected")
            continue
        orphaned = []
        for c in node["next"]:
            child = nodes_by_id.get(c)
            if not child or c not in by_node:
                continue
            if not any(p in by_node for p in child["prev"] if p != node["id"]):
                orphaned.append(child["name"] or str(c))
        if orphaned:
            errors.append(f"cannot remove {name}: {', '.join(orphaned)} require(s) it as a prerequisite")
            continue
        del by_node[node["id"]]
        changes.append({"action": "remove", "name": entry["name"], "node_id": node["id"], "section": node["section"]})

    for name in add:
        hits = name_idx.get(name.strip().lower())
        if not hits:
            errors.append(f"unknown talent: {name}")
            continue
        node, entry = hits[0]
        if node["granted"]:
            errors.append(f"{name} is automatically granted; nothing to add")
            continue
        existing = by_node.get(node["id"])
        if existing and any(s.get("entry_id") == entry["id"] for s in existing):
            errors.append(f"{name} is already selected")
            continue
        if node["prev"] and not any(p in by_node for p in node["prev"]):
            prereq = ", ".join(nodes_by_id[p]["name"] or str(p) for p in node["prev"] if p in nodes_by_id)
            errors.append(f"cannot add {name}: requires {prereq} first")
            continue
        section = node["section"]
        already = sum(int(s.get("rank") or 0) for s in (existing or []))
        projected = spent(section) - already + node["max_ranks"] if section in budgets else None
        if projected is not None and projected > budgets[section]:
            errors.append(f"cannot add {name}: would exceed the {section} point budget ({projected}/{budgets[section]})")
            continue
        # gate: needs N points already committed to this section's currency. Compare against the
        # *post-add* total (this node's own points count too) -- the threshold is normally already
        # met by the time you reach it, and a same-cost swap through remove-then-add shouldn't dip
        # below it just because the old pick was removed first.
        if node["points_required"] and projected is not None and projected < node["points_required"]:
            errors.append(f"cannot add {name}: requires {node['points_required']} points spent in the "
                           f"{section} tree first (have {projected})")
            continue
        ents = node["entries"]
        if node["node_type"] == 1 and len(ents) > 1:
            by_node[node["id"]] = [{"node_id": node["id"], "entry_id": e["id"], "rank": e["max_ranks"]} for e in ents]
        else:
            by_node[node["id"]] = [{"node_id": node["id"], "entry_id": entry["id"], "rank": entry["max_ranks"] or 1}]
        changes.append({"action": "add", "name": entry["name"], "node_id": node["id"], "section": section})

    selections = [s for sels in by_node.values() for s in sels]
    string = encode(klass, spec, {"selected": selections, "tree_hash": d.get("tree_hash"), "hero_tree": d.get("hero_tree")})
    points = {s: {"spent": spent(s), "budget": budgets[s]} for s in ("class", "spec", "hero")}
    return {"string": string, "changes": changes, "errors": errors, "points": points}
