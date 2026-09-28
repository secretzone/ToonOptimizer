"""Parse the in-game SimulationCraft addon ``/simc`` export into a :class:`CharacterProfile`.

Format (from Interface/AddOns/Simulationcraft/core.lua ``GetSimcProfile``)::

    # Name - Spec - 2026-09-21 13:00 - US/Realm
    # SimC Addon 12.1.0-01
    # WoW 12.1.0.69875, TOC 120100
    # Requires SimulationCraft 1000-01 or newer

    deathknight="Name"
    level=90
    race=human
    region=us
    server=realm
    role=attack
    professions=blacksmithing=100/mining=100
    spec=frost
    # loot_spec=frost

    talents=C...                      (active loadout)

    # Saved Loadout: Raid
    # talents=C...
    omnium_talents=1:1/2:1

    # Item Name (344)
    head=,id=271474,bonus_id=4786/12854,gem_id=240983,enchant_id=7987,crafted_stats=32/49,crafting_quality=5
    ...
    ### Gear from Bags
    #
    # Item Name (334)
    # finger1=,id=268252,bonus_id=...
    ### Weekly Reward Choices
    #
    # Item Name (344)
    # trinket1=,id=...
    #
    ### End of Weekly Reward Choices
    ### Additional Character Info
    #
    # catalyst_currencies=<currencyId>:<amount>[/<currencyId>:<amount>...]
    #
    # upgrade_currencies=c:<currencyId>:<amount>[,c:<currencyId>:<amount>...]   (i:<itemId>:<count> for item currencies)
    #
    # bonus_roll_currencies=<currencyId>:<amount>[/...]
    #
    # slot_high_watermarks=<Enum.ItemRedundancySlot>:<characterHW>:<accountHW>[/...]
    # ...
    # Checksum: abcd1234

``catalyst_currencies``/``upgrade_currencies``/``bonus_roll_currencies`` come from
``Simulationcraft:GetCatalystCurrencies``/``GetUpgradeCurrencies``/``GetBonusRollCurrencies``
(core.lua ~748-791); entries are ``/``-joined per the addon, ``,``-joined variants seen in the
wild are also accepted (see ``_CURRENCY_ENTRY_SPLIT_RE``). They resolve into
``CharacterProfile.currencies`` (``toonopt.data.currencies.resolve_currency``, lazily imported
like items) and ``catalyst_charges``/``catalyst_charges_max``.

``catalyst_currencies`` entries are ``id:amount`` (``GetCatalystCurrencies``, core.lua ~748-757,
``table.concat({ currencyId, currencyInfo.quantity }, ':')`` -- there is no third field despite
some fixtures/exports carrying a trailing ``:0``; see ``_split_currency_entries``).
``Simulationcraft.catalystCurrencies`` (extras.lua) is a static table of *every* catalyst
currency the addon has ever tracked across seasons (5 entries at the time of writing), and the
addon emits an entry for each one ``C_CurrencyInfo.GetCurrencyInfo`` returns data for -- usually
all of them, most reading 0 or a stale leftover amount from a past season. Only the currency
matching *this* season's catalyst (``toonopt.data.season.catalyst()["currency_id"]``, e.g. 3465
"Venomblight Manaflux") is real; ``catalyst_charges`` is that entry's amount (falling back to the
first entry's amount when the season id can't be resolved or isn't present), not the sum of
every entry.

Slot names in the export are SimC's (``shoulder``, ``wrist``); simc-repo profiles
use ``shoulders``/``wrists`` and are normalised. The data layer
(``toonopt.data.items.resolve_item``) enriches items when available.

``CharacterProfile.saved_loadouts`` is every loadout the export carries: the active one
(the un-commented ``talents=`` line, name from the header/character name, ``kind="active"``)
plus every ``# Saved Loadout: <name>`` / ``# Offspec Loadout: <name>`` block (``kind="saved"``,
via :func:`saved_loadouts`). ``loot_spec`` is the addon's ``# loot_spec=<spec>`` comment
(``Tokenize(playerLootSpec)``, core.lua ~1138-1164), verbatim. ``high_watermarks`` decodes
``# slot_high_watermarks=<Enum.ItemRedundancySlot>:<characterHW>:<accountHW>[/...]``
(``Simulationcraft:GetSlotHighWatermarks``, core.lua ~734-746) into our slot names -> ilvl
(see :data:`_HIGH_WATERMARK_SLOT_MAP`); for gold-only upgrades later.
"""
from __future__ import annotations

import logging
import re

from toonopt.models import (
    SLOTS,
    CharacterProfile,
    Currency,
    Item,
    ItemSource,
    SavedLoadout,
)

log = logging.getLogger(__name__)

CLASS_TOKENS: dict[str, str] = {
    "deathknight": "death_knight", "death_knight": "death_knight",
    "demonhunter": "demon_hunter", "demon_hunter": "demon_hunter",
    "druid": "druid", "evoker": "evoker", "hunter": "hunter", "mage": "mage", "monk": "monk",
    "paladin": "paladin", "priest": "priest", "rogue": "rogue", "shaman": "shaman",
    "warlock": "warlock", "warrior": "warrior",
}
SLOT_ALIASES: dict[str, str] = {"shoulders": "shoulder", "wrists": "wrist"}
GEAR_SLOTS = set(SLOTS) | set(SLOT_ALIASES)
IGNORED_SLOTS = {"shirt", "tabard", "ammo"}
GENERIC_SLOT = {"finger1": "finger", "finger2": "finger", "trinket1": "trinket", "trinket2": "trinket"}
INT_LIST_KEYS = {"bonus_id", "gem_id", "crafted_stats", "gem_bonus_id"}

_CLASS_RE = re.compile(r'^(\w+)\s*=\s*"?([^"]*)"?\s*$')
_KV_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.*)$")
_NAME_COMMENT_RE = re.compile(r"^#\s*(.+?)\s*\((\d+)\)\s*$")
_HEADER_RE = re.compile(r"^#\s*(.+?) - (.+?) - (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) - (\w+)/(.+?)\s*$")
_SAVED_RE = re.compile(r"^#\s*(Saved Loadout|Offspec Loadout):\s*(.+?)\s*$")
_TALENTS_COMMENT_RE = re.compile(r"^#\s*(talents|offspec_talents)=(\S+)\s*$")
_CURRENCY_COMMENT_RE = re.compile(r"^(catalyst_currencies|upgrade_currencies|bonus_roll_currencies)=(.*)$")
_CURRENCY_ENTRY_SPLIT_RE = re.compile(r"[,/]")
_LOOT_SPEC_RE = re.compile(r"^loot_spec=(\S*)$")
_HIGH_WATERMARKS_RE = re.compile(r"^slot_high_watermarks=(.*)$")

# Enum.ItemRedundancySlot (core.lua's Simulationcraft:GetSlotHighWatermarks(), ~734-746) --
# NOT normal equipment slot ids. It groups the two ring/trinket slots and the weapon slots
# into single ids, since a high watermark tracks "the best ilvl ever seen for this *type* of
# slot", not a concrete paperdoll slot. Mapped to our SimC slot names: the ring/trinket pair
# collapses to the generic "finger"/"trinket" (same convention Item.slot uses for unplaced
# candidates), and the five weapon ids collapse to main_hand/off_hand -- the best available
# signal given our model only has those two weapon slots (see docstring below).
_HIGH_WATERMARK_SLOT_MAP: dict[int, str] = {
    0: "head", 1: "neck", 2: "shoulder", 3: "chest", 4: "waist", 5: "legs", 6: "feet",
    7: "wrist", 8: "hands", 9: "finger", 10: "trinket", 11: "back",
    12: "main_hand", 13: "main_hand", 14: "main_hand",   # Twohand, MainhandWeapon, OnehandWeapon
    15: "off_hand", 16: "off_hand",                       # OnehandWeaponSecond, Offhand
}


class ProfileError(ValueError):
    pass


def _slot_of(line: str) -> str | None:
    m = _KV_RE.match(line)
    if not m:
        return None
    key = m.group(1)
    if key in IGNORED_SLOTS:
        return "ignored"
    if key in GEAR_SLOTS:
        return SLOT_ALIASES.get(key, key)
    return None


def parse_item_line(line: str) -> tuple[str, dict[str, object]]:
    """``head=name,id=1,bonus_id=1/2`` -> ("head", {"name": ..., "id": 1, "bonus_id": [1, 2], ...})."""
    m = _KV_RE.match(line.strip())
    if not m:
        raise ProfileError(f"not an item line: {line!r}")
    slot = SLOT_ALIASES.get(m.group(1), m.group(1))
    fields: dict[str, object] = {}
    parts = m.group(2).split(",")
    fields["name"] = parts[0].strip()
    for part in parts[1:]:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if k in INT_LIST_KEYS:
            fields[k] = [int(x) for x in v.split("/") if x.strip().lstrip("-").isdigit()]
        elif v.lstrip("-").isdigit():
            fields[k] = int(v)
        else:
            fields[k] = v
    return slot, fields


def _bare_item(key: str, slot: str, fields: dict, comment_name: str | None, comment_ilvl: int | None,
               source: ItemSource | None, simc_line: str) -> Item:
    name = comment_name or str(fields.get("name") or "").replace("_", " ").title()
    return Item(
        key=key, id=int(fields.get("id") or 0), name=name, slot=slot,
        ilevel=int(fields.get("ilevel") or comment_ilvl or 0),
        bonus_ids=list(fields.get("bonus_id") or []),
        gem_ids=list(fields.get("gem_id") or []),
        enchant_id=int(fields["enchant_id"]) if fields.get("enchant_id") else None,
        crafted_stats=list(fields.get("crafted_stats") or []),
        crafting_quality=int(fields["crafting_quality"]) if fields.get("crafting_quality") else None,
        source=source, simc_string=simc_line,
    )


DATA_UNAVAILABLE = "toonopt.data is not available"


def make_item(key: str, slot: str, line: str, *, comment_name: str | None = None, comment_ilvl: int | None = None,
              source: ItemSource | None = None, failures: list[tuple[str, str]] | None = None) -> Item:
    """Build an Item from an item line, enriched by the data layer when it is importable.

    ``failures`` is an optional shared list that callers (``parse()``) use to collect
    per-item resolve failures across a whole export, so the profile can carry a single
    aggregated warning rather than one per item. Each failure is also logged at WARNING
    with the item id so a real failure (e.g. cache missing for the current build) is
    diagnosable from the server log even though the UI only shows one summary line.
    """
    concrete_slot, fields = parse_item_line(line)
    simc_line = f"{concrete_slot}=" + line.split("=", 1)[1].strip()
    bare = _bare_item(key, slot, fields, comment_name, comment_ilvl, source, simc_line)
    try:
        from toonopt.data.items import resolve_item  # type: ignore[import-not-found]
    except Exception as e:  # noqa: BLE001 - data layer optional; degrade to a bare, unresolved item
        # ImportError covers both "not installed" and the test stub (sys.modules[...] = None,
        # which Python turns into an ImportError on import); anything else is still reported
        # as a per-item failure below rather than crashing the whole import.
        reason = DATA_UNAVAILABLE if isinstance(e, ImportError) else f"{type(e).__name__}: {e}"
        log.warning("toonopt.data is unavailable; cannot resolve item %s (key=%s): %s", bare.id, key, e)
        if failures is not None:
            failures.append((key, reason))
        return bare.model_copy(update={"resolved": False})
    try:
        item = resolve_item(
            bare.id, bare.bonus_ids, bare.ilevel or None, key=key, slot_hint=slot,
            gem_ids=tuple(bare.gem_ids), enchant_id=bare.enchant_id,
            crafted_stats=tuple(bare.crafted_stats), crafting_quality=bare.crafting_quality,
        )
    except Exception as e:  # noqa: BLE001 - any resolve failure degrades to a bare, unresolved item
        log.warning("failed to resolve item %s (key=%s, slot=%s): %s", bare.id, key, slot, e)
        if failures is not None:
            failures.append((key, f"{type(e).__name__}: {e}"))
        return bare.model_copy(update={"resolved": False})
    if not isinstance(item, Item):
        log.warning("resolve_item returned a non-Item for item %s (key=%s): %r", bare.id, key, item)
        if failures is not None:
            failures.append((key, "resolve_item returned an unexpected type"))
        return bare.model_copy(update={"resolved": False})
    # keep what we know for sure from the export
    update: dict[str, object] = {"key": key, "simc_string": simc_line}
    if not item.name and bare.name:
        update["name"] = bare.name
    if not item.ilevel and bare.ilevel:
        update["ilevel"] = bare.ilevel
    if source and not item.source:
        update["source"] = source
    if item.slot not in GENERIC_SLOT.values() and item.slot != slot and slot in SLOTS:
        update["slot"] = slot
    return item.model_copy(update=update)


def make_currency(currency_id: int, kind: str, amount: int) -> Currency:
    """Build a Currency, enriched by the data layer when it is importable (mirrors
    :func:`make_item`'s lazy-import/bare-fallback pattern; failures just degrade to a bare,
    unnamed Currency rather than failing the whole import)."""
    try:
        from toonopt.data.currencies import resolve_currency
    except Exception as e:  # noqa: BLE001 - data layer optional; degrade to a bare currency
        log.warning("toonopt.data is unavailable; cannot resolve currency %s: %s", currency_id, e)
        return Currency(id=currency_id, kind=kind, amount=amount)
    try:
        return resolve_currency(currency_id, kind, amount)
    except Exception as e:  # noqa: BLE001 - any resolve failure degrades to a bare currency
        log.warning("failed to resolve currency %s (kind=%s): %s", currency_id, kind, e)
        return Currency(id=currency_id, kind=kind, amount=amount)


def _split_currency_entries(value: str) -> list[tuple[int, int]]:
    """``id:amount`` or ``id:amount:<extra>`` per entry (``catalyst_currencies``/
    ``bonus_roll_currencies``); the addon (``GetCatalystCurrencies``/``GetBonusRollCurrencies``,
    core.lua ~748-791) only ever emits ``id:amount``, joined by ``/`` -- the optional 3rd field
    and ``,`` separator are accepted for forward/export-variant compatibility and ignored."""
    out: list[tuple[int, int]] = []
    for part in _CURRENCY_ENTRY_SPLIT_RE.split(value or ""):
        fields = part.strip().split(":")
        if len(fields) < 2:
            continue
        try:
            out.append((int(fields[0]), int(fields[1])))
        except ValueError:
            continue
    return out


def _split_upgrade_currency_entries(value: str) -> list[tuple[str, int, int]]:
    """``c:<currencyId>:<amount>`` or ``i:<itemId>:<count>`` per entry (``upgrade_currencies``,
    ``GetUpgradeCurrencies``, core.lua ~760-779): (kind, id, amount)."""
    out: list[tuple[str, int, int]] = []
    for part in _CURRENCY_ENTRY_SPLIT_RE.split(value or ""):
        fields = part.strip().split(":")
        if len(fields) < 3:
            continue
        kind = "item" if fields[0] == "i" else "currency"
        try:
            out.append((kind, int(fields[1]), int(fields[2])))
        except ValueError:
            continue
    return out


def _season_catalyst_currency_id() -> int | None:
    """This season's catalyst-charge currency id (``toonopt.data.season.catalyst()
    ["currency_id"]``, e.g. 3465 "Venomblight Manaflux"). Best-effort like
    :func:`make_currency`/:func:`make_item`: degrades to None (never raises) when the data
    layer isn't importable or season data isn't ready yet, so callers fall back to the first
    catalyst entry instead."""
    try:
        from toonopt.data import season  # type: ignore[import-not-found]
    except Exception as e:  # noqa: BLE001 - data layer optional; caller falls back
        log.warning("toonopt.data is unavailable; cannot resolve this season's catalyst currency id: %s", e)
        return None
    try:
        cid = season.catalyst().get("currency_id")
    except Exception as e:  # noqa: BLE001 - season data optional; caller falls back
        log.warning("failed to read this season's catalyst currency id: %s", e)
        return None
    return int(cid) if cid else None


def _parse_currencies(raw: dict[str, str]) -> tuple[list[Currency], int | None, int | None]:
    """The three ``### Additional Character Info`` currency comment lines -> (currencies,
    catalyst_charges, catalyst_charges_max).

    ``catalyst_currencies`` carries one ``id:amount`` entry per catalyst currency the addon has
    *ever* tracked (``Simulationcraft.catalystCurrencies``, extras.lua) -- typically several,
    with only the current season's actually meaningful and the rest reading 0 or a stale amount
    left over from a past season. Summing them (the old behaviour) overcounts. Instead,
    ``catalyst_charges``/``catalyst_charges_max`` are the amount/``max_quantity`` of the entry
    matching this season's catalyst currency id (:func:`_season_catalyst_currency_id`, i.e.
    ``season.catalyst.currency_id``), falling back to the first catalyst entry when that id
    can't be resolved or isn't present in this export. Both are None when the export carried no
    ``catalyst_currencies`` line at all; catalyst_charges is 0 (max stays None) for an empty
    line."""
    currencies: list[Currency] = []
    catalyst_charges: int | None = None
    catalyst_charges_max: int | None = None
    if "catalyst_currencies" in raw:
        entries = _split_currency_entries(raw["catalyst_currencies"])
        catalyst_objs = [make_currency(cid, "currency", amount) for cid, amount in entries]
        currencies.extend(catalyst_objs)
        if entries:
            season_cid = _season_catalyst_currency_id()
            chosen_idx = 0
            if season_cid is not None:
                for i, (cid, _amount) in enumerate(entries):
                    if cid == season_cid:
                        chosen_idx = i
                        break
            catalyst_charges = entries[chosen_idx][1]
            catalyst_charges_max = catalyst_objs[chosen_idx].max_quantity
        else:
            catalyst_charges = 0
    for cid, amount in _split_currency_entries(raw.get("bonus_roll_currencies", "")):
        currencies.append(make_currency(cid, "currency", amount))
    for kind, cid, amount in _split_upgrade_currency_entries(raw.get("upgrade_currencies", "")):
        currencies.append(make_currency(cid, kind, amount))
    return currencies, catalyst_charges, catalyst_charges_max


def _parse_high_watermarks(value: str) -> dict[str, int]:
    """``# slot_high_watermarks=<Enum.ItemRedundancySlot>:<characterHW>:<accountHW>[/...]``
    (``Simulationcraft:GetSlotHighWatermarks``, core.lua ~734-746) -> our slot names -> ilvl.
    The higher of the character/account watermark wins; two source ids that map to the same
    output slot (e.g. Twohand and MainhandWeapon both -> main_hand) also just keep the max."""
    out: dict[str, int] = {}
    for part in (value or "").split("/"):
        fields = [f.strip() for f in part.strip().split(":")]
        if not fields or not fields[0].lstrip("-").isdigit():
            continue
        slot = _HIGH_WATERMARK_SLOT_MAP.get(int(fields[0]))
        if slot is None:
            continue
        ilvls = [int(f) for f in fields[1:] if f.lstrip("-").isdigit()]
        if not ilvls:
            continue
        out[slot] = max([out.get(slot, 0), *ilvls])
    return out


def saved_loadouts(raw: str) -> list[dict[str, str]]:
    """``[{name, string, kind}]`` for ``# Saved Loadout:`` / ``# Offspec Loadout:`` blocks."""
    out: list[dict[str, str]] = []
    pending: str | None = None
    kind = "talents"
    for line in raw.splitlines():
        m = _SAVED_RE.match(line)
        if m:
            pending = m.group(2)
            kind = "talents" if m.group(1) == "Saved Loadout" else "offspec_talents"
            continue
        m = _TALENTS_COMMENT_RE.match(line)
        if m and pending is not None:
            out.append({"name": pending, "string": m.group(2), "kind": kind})
            pending = None
    return out


def parse(text: str) -> CharacterProfile:
    raw = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")
    klass = spec = name = ""
    realm, region, race, role = "", "us", "", "attack"
    level = 80
    talents = ""
    professions: dict[str, int] = {}
    header_lines: list[str] = []
    equipped: dict[str, Item] = {}
    bags: list[Item] = []
    vault: list[Item] = []
    section = "actor"           # actor | bags | vault | merchant | other
    comment_name: str | None = None
    comment_ilvl: int | None = None
    seen_gear = False
    failures: list[tuple[str, str]] = []
    currency_raw: dict[str, str] = {}
    loot_spec: str | None = None
    high_watermarks: dict[str, int] = {}
    omnium: dict[int, int] = {}

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("###"):
            title = s.lstrip("#").strip().lower()
            if title.startswith(("gear from bags", "linked gear")):
                section = "bags"
            elif title.startswith("weekly reward"):
                section = "vault"
            elif title.startswith("end of weekly"):
                section = "other"
            elif title.startswith("merchant"):
                section = "merchant"
            elif title.startswith("offspec loadouts"):
                section = "actor"
            else:
                section = "other"
            comment_name = comment_ilvl = None
            continue
        if s.startswith("#"):
            body = s[1:].strip()
            if not name:
                hm = _HEADER_RE.match(s)
                if hm:
                    name, region, realm = hm.group(1), hm.group(4).lower(), hm.group(5)
                    continue
            nm = _NAME_COMMENT_RE.match(s)
            if nm and not body.startswith(("gear_", "set_bonus", "Checksum")):
                comment_name, comment_ilvl = nm.group(1), int(nm.group(2))
                continue
            cur_m = _CURRENCY_COMMENT_RE.match(body)
            if cur_m:
                currency_raw[cur_m.group(1)] = cur_m.group(2)
                continue
            ls_m = _LOOT_SPEC_RE.match(body)
            if ls_m:
                loot_spec = ls_m.group(1) or None
                continue
            hwm_m = _HIGH_WATERMARKS_RE.match(body)
            if hwm_m:
                high_watermarks = _parse_high_watermarks(hwm_m.group(1))
                continue
            if section in ("bags", "vault") and _slot_of(body) not in (None, "ignored"):
                slot = _slot_of(body) or ""
                key = f"bag:{len(bags) + 1}" if section == "bags" else f"vault:{len(vault) + 1}"
                src = ItemSource(type="bag" if section == "bags" else "vault", name="Bags" if section == "bags" else "Great Vault")
                item = make_item(key, GENERIC_SLOT.get(slot, slot), body, comment_name=comment_name,
                                 comment_ilvl=comment_ilvl, source=src, failures=failures)
                (bags if section == "bags" else vault).append(item)
                comment_name = comment_ilvl = None
            continue
        # non-comment line
        if section != "actor":
            continue
        slot = _slot_of(s)
        if slot == "ignored":
            continue
        if slot:
            seen_gear = True
            src = ItemSource(type="equipped", name="Equipped")
            equipped[slot] = make_item(f"equipped:{slot}", slot, s, comment_name=comment_name,
                                       comment_ilvl=comment_ilvl, source=src, failures=failures)
            comment_name = comment_ilvl = None
            continue
        comment_name = comment_ilvl = None
        cm = _CLASS_RE.match(s)
        if cm and cm.group(1).lower() in CLASS_TOKENS and not klass:
            klass = CLASS_TOKENS[cm.group(1).lower()]
            name = cm.group(2) or name
            header_lines.append(s)
            continue
        if not seen_gear:
            header_lines.append(s)          # every actor line incl. actions+=, consumables, etc.
        kv = _KV_RE.match(s)
        if not kv:
            continue
        key, val = kv.group(1), kv.group(2).strip()
        if key == "level":
            level = int(val) if val.isdigit() else level
        elif key == "race":
            race = val
        elif key == "region":
            region = val.lower()
        elif key == "server":
            realm = val
        elif key == "role":
            role = val if val in ("attack", "tank", "heal") else role
        elif key == "spec":
            spec = val
        elif key == "talents":
            talents = val
        elif key == "professions":
            for part in val.split("/"):
                if "=" in part:
                    p, r = part.split("=", 1)
                    professions[p.strip()] = int(r) if r.strip().isdigit() else 0
        elif key == "omnium_talents":
            for part in val.split("/"):
                if ":" not in part:
                    continue
                eid_s, rank_s = part.split(":", 1)
                eid_s, rank_s = eid_s.strip(), rank_s.strip()
                if eid_s.lstrip("-").isdigit() and rank_s.lstrip("-").isdigit():
                    omnium[int(eid_s)] = int(rank_s)

    if not klass:
        raise ProfileError("no class line found (expected e.g. deathknight=\"Name\")")
    if not spec:
        raise ProfileError("no spec= line found")
    currencies, catalyst_charges, catalyst_charges_max = _parse_currencies(currency_raw)
    loadouts: list[SavedLoadout] = []
    if talents:
        loadouts.append(SavedLoadout(name=name or "Active", string=talents, kind="active"))
    loadouts.extend(SavedLoadout(name=lo["name"], string=lo["string"], kind="saved") for lo in saved_loadouts(raw))
    return CharacterProfile(
        name=name or "Unknown", realm=realm, region=region or "us", level=level, race=race,
        klass=klass, spec=spec, role=role, talents=talents, professions=professions,
        equipped=equipped, bags=bags, vault=vault, currencies=currencies,
        catalyst_charges=catalyst_charges, catalyst_charges_max=catalyst_charges_max,
        simc_header="\n".join(header_lines), raw=raw,
        warnings=_resolve_warnings(failures), saved_loadouts=loadouts, loot_spec=loot_spec,
        high_watermarks=high_watermarks, omnium=omnium,
    )


def _resolve_warnings(failures: list[tuple[str, str]]) -> list[str]:
    """One aggregated warning for every item that failed to resolve during ``parse()``
    (never one line per item -- an export can have a couple dozen items)."""
    if not failures:
        return []
    reasons = {reason for _, reason in failures}
    if reasons == {DATA_UNAVAILABLE}:
        return [f"{DATA_UNAVAILABLE}; items could not be resolved"]
    reason = failures[0][1]
    return [f"{len(failures)} item(s) could not be resolved (reason: {reason}) — refresh data in Settings"]
