"""Unit tests for toonopt.data.currencies: name/icon resolution (CurrencyTypes DB2 table)
and the currency-id -> UpgradeInfo.crest mapping (data/season.json's per-track
``crest.currency_id``, set by toonopt.data.bonuses.season_tracks from Raidbots' currency
field). Needs the real DB2 cache (skipped otherwise, see conftest.real_data_layer)."""
from __future__ import annotations


def test_resolve_currency_names_icons_and_max_quantity(real_data_layer):
    from toonopt.data import currencies

    myth = currencies.resolve_currency(3446, "currency", 40)
    assert myth.name == "Myth Mistcrest"
    assert myth.icon == "inv_121_crest_myth"
    assert myth.max_quantity == 100
    assert myth.amount == 40


def test_crest_currency_ids_match_upgrade_track_crest_strings(real_data_layer):
    """Every season.json upgrade track's crest.currency_id resolves (by id, not by string
    matching) to that exact track's crest name -- the string sims/upgrades.py puts on
    UpgradeInfo.crest."""
    from toonopt.data import currencies
    from toonopt.data.season import load as season_load

    tracks = season_load()["upgrade_tracks"]
    for track in tracks.values():
        crest = track["crest"]
        resolved = currencies.resolve_currency(crest["currency_id"], "currency", 0)
        assert resolved.name == crest["name"]
        assert currencies.crest_name_for_currency(crest["currency_id"]) == crest["name"]
        assert resolved.crest == crest["name"]


def test_crest_name_for_currency_none_for_non_crest_or_unknown(real_data_layer):
    from toonopt.data import currencies

    assert currencies.crest_name_for_currency(999999999) is None    # unknown id
    # Valorstones (3008): a real upgrade currency, but not a crest track
    assert currencies.crest_name_for_currency(3008) is None


def test_resolve_currency_unknown_id_is_bare(real_data_layer):
    from toonopt.data import currencies

    c = currencies.resolve_currency(999999999, "currency", 7)
    assert c.name == "" and c.icon == "" and c.crest is None and c.amount == 7


def test_resolve_item_based_currency(real_data_layer):
    from toonopt.data import currencies

    c = currencies.resolve_currency(173381, "item", 3)
    assert c.kind == "item" and c.amount == 3
    assert c.name == "Crafter's Mark I"
    assert c.icon
    assert c.crest is None
