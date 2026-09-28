"""Resolve currency ids (and item-based currencies) to :class:`toonopt.models.Currency`.

Name/icon come from the ``CurrencyTypes`` DB2 table (``toonopt.data.wago.TABLES``); the icon
file name is resolved the same way item icons are, through ``ManifestInterfaceData``
(``INV_Foo_Bar.blp`` -> ``inv_foo_bar``).

Crest currencies are matched to the exact string used in ``UpgradeInfo.crest`` via
``data/season.json``'s ``upgrade_tracks[*].crest.currency_id`` -- set by
``toonopt.data.bonuses.season_tracks`` from Raidbots' ``bonuses.json`` ``upgrade.currency.id``
field, so the mapping is explicit (matched by currency id, never guessed from the name) and
regenerated automatically whenever ``toonopt.data.season.write()`` runs for a new season.
"""
from __future__ import annotations

from functools import lru_cache

import polars as pl

from toonopt.data import wago
from toonopt.models import Currency

CURRENCY_COLUMNS = ["ID", "Name_lang", "InventoryIconFileID", "MaxQty"]


@lru_cache(maxsize=4)
def _currencies(build: str | None = None) -> pl.DataFrame:
    return wago.table("CurrencyTypes", build, CURRENCY_COLUMNS)


def row(currency_id: int, build: str | None = None) -> dict | None:
    df = _currencies(build).filter(pl.col("ID") == int(currency_id))
    if df.height == 0:
        return None
    return df.row(0, named=True)


def _icon_name(file_id: int, build: str | None = None) -> str:
    if not file_id:
        return ""
    mid = wago.table("ManifestInterfaceData", build, ["ID", "FileName"])
    df = mid.filter(pl.col("ID") == int(file_id))
    if df.height == 0:
        return ""
    name = str(df.row(0, named=True)["FileName"] or "")
    if name.lower().endswith(".blp"):
        name = name[:-4]
    return name.lower()


@lru_cache(maxsize=4)
def _crest_currency_ids(build: str | None = None) -> dict[int, str]:
    """currency_id -> the exact crest name used in ``UpgradeInfo.crest`` (``season.json``).

    Returns ``{}`` (never raises) when ``season.json`` is missing or the DB2 cache isn't
    ready yet -- a currency can still resolve its name/icon without a crest mapping.
    """
    try:
        from toonopt.data.season import load as season_load
        tracks = season_load().get("upgrade_tracks", {})
    except Exception:  # noqa: BLE001 - season data optional here; crest just stays unmapped
        return {}
    out: dict[int, str] = {}
    for track in tracks.values():
        crest = track.get("crest") or {}
        cid, name = crest.get("currency_id"), crest.get("name")
        if cid and name:
            out[int(cid)] = str(name)
    return out


def crest_name_for_currency(currency_id: int, build: str | None = None) -> str | None:
    """The ``UpgradeInfo.crest`` string this currency id pays for, or None if it isn't one
    of this live season's crests (an old season's crest, a non-crest currency, an item, ...)."""
    return _crest_currency_ids(build).get(int(currency_id))


def resolve_currency(currency_id: int, kind: str, amount: int, build: str | None = None) -> Currency:
    """Public entry point (see module docstring).

    Falls back to a bare ``Currency`` (``name=""``, ``icon=""``) when the id is unknown to
    ``CurrencyTypes`` (or, for ``kind="item"``, unknown to the item tables) rather than raising
    -- mirrors ``toonopt.data.items.resolve_item`` degrading callers (``toonopt.simc.profile``).
    """
    crest = crest_name_for_currency(currency_id, build) if kind == "currency" else None
    if kind == "item":
        from toonopt.data import items
        r = items.row(currency_id, build)
        if r is None:
            return Currency(id=currency_id, kind=kind, amount=amount)
        return Currency(
            id=currency_id, kind=kind, amount=amount, name=str(r.get("Display_lang") or ""),
            icon=items.icon(currency_id, build),
        )
    r = row(currency_id, build)
    if r is None:
        return Currency(id=currency_id, kind=kind, amount=amount, crest=crest)
    max_qty = int(r.get("MaxQty") or 0) or None
    return Currency(
        id=currency_id, kind=kind, amount=amount, name=str(r.get("Name_lang") or ""),
        icon=_icon_name(int(r.get("InventoryIconFileID") or 0), build), crest=crest,
        max_quantity=max_qty,
    )
