"""Raidbots parity, wave 2: Catalyst, sockets, Voidforge, crafted recraft, Omnium Folio,
consumable options (data/season.py accessors + data/season.json additions).

All of these need the real DB2/Raidbots-backed data layer (item names/ilevels/stats), so every
test takes the ``real_data_layer`` fixture (skips when the DB2 cache isn't downloaded).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def season_mod(real_data_layer):
    from toonopt.data import season
    return season


@pytest.fixture
def Item(real_data_layer):
    from toonopt.models import Item
    return Item


# ---------------------------------------------------------------------------
# season.json shape

def test_season_json_has_wave2_keys(season_mod) -> None:
    s = season_mod.load()
    for key in ("catalyst", "sockets", "omnium"):
        assert key in s
    # every previously-existing top-level key must still be there
    for key in ("season", "season_id", "raids", "dungeons", "upgrade_tracks", "crafted",
                "voidforged", "consumables", "enchants", "gems", "diamonds"):
        assert key in s


def test_voidforged_dropped_hero_and_crafted_ilevel(season_mod) -> None:
    vf = season_mod.load()["voidforged"]
    assert vf == {"slots": ["main_hand", "off_hand", "trinket1", "trinket2"], "myth_ilevel": 344, "bonus_id": 13848}
    assert "hero_ilevel" not in vf and "crafted_ilevel" not in vf


def test_crafted_wave2_additions(season_mod) -> None:
    c = season_mod.load()["crafted"]
    assert c["stat_ids"] == {"crit": 32, "haste": 36, "versatility": 40, "mastery": 49}
    assert c["stat_bonus_ids"] == [8790, 8791, 8792, 8793, 8794, 8795]
    assert c["quality_bonus_max"] == 12497
    assert c["embellish_marker"] == 8960
    assert c["max_embellished"] == 2
    # existing embellishments kept
    assert any(e["key"] == "arcanoweave" for e in c["embellishments"])


def test_sockets_block(season_mod) -> None:
    s = season_mod.load()["sockets"]
    assert s["add_bonus_id"] == 1808 and s["two"] == 8781 and s["three"] == 8782
    assert s["vault_slots"] == ["head", "wrist", "waist"]
    assert s["jewelbinder_slots"] == ["neck", "finger1", "finger2"]
    assert s["jewelbinder_item"] == 263897


def test_omnium_block(season_mod) -> None:
    o = season_mod.load()["omnium"]
    assert o["tree_id"] == 1186
    assert len(o["rows"]) == 5
    row1 = o["rows"][0]
    assert row1["row"] == 1 and "node_id" in row1
    choice = row1["choices"][0]
    assert {"entry_id", "token", "name", "icon"} <= choice.keys()


def test_consumable_options_cover_accepted_names(season_mod) -> None:
    opts = season_mod.load()["consumables"]["options"]
    for cat in ("flask", "food", "potion", "augmentation", "temporary_enchant"):
        assert opts[cat], f"{cat} options must not be empty"
        for o in opts[cat]:
            assert o["value"] and o["label"]
    values = {o["value"] for o in opts["flask"]}
    assert values == {"flask_of_the_shattered_sun_2", "flask_of_the_blood_knights_2",
                       "flask_of_the_magisters_2", "flask_of_thalassian_resistance_2"}
    assert "alluring_nostrum_2" in {o["value"] for o in opts["potion"]}


# ---------------------------------------------------------------------------
# catalyst()

def test_catalyst_item_for_maps_inventory_type_20_to_chest(season_mod) -> None:
    assert season_mod.catalyst_item_for("death_knight", 1) == 271474    # head
    assert season_mod.catalyst_item_for("death_knight", 5) == 271477    # chest (plate)
    assert season_mod.catalyst_item_for("priest", 20) == 271558         # chest (robe)
    assert season_mod.catalyst_item_for("death_knight", 20) == 271477   # 20 -> chest for every class
    assert season_mod.catalyst_item_for("death_knight", 999) is None


def test_catalyst_set_id(season_mod) -> None:
    assert season_mod.catalyst_set_id("death_knight") == 2055
    assert season_mod.catalyst_set_id("not_a_class") is None


def test_catalyst_variant_frost_dk_head(season_mod, Item) -> None:
    # source: a non-tier frost DK head (id 251126) at Myth 6/6 (bonus_id 4786/12854/13692/
    # 13698/13750, gem 240983) -- scratchpad w2/v_q5_vf_replace.simc / v_q1h_chest_cat.simc
    src = Item(key="equipped:head", id=251126, slot="head", inventory_type=1,
               bonus_ids=[4786, 12854, 13692, 13698, 13750], gem_ids=[240983])
    cat = season_mod.catalyst_variant(src, "death_knight")
    assert cat is not None
    assert cat.id == 271474
    assert cat.key == "catalyst:equipped:head"
    assert cat.ilevel == 334
    assert cat.set_id == 2055
    # models.py carries no dedicated field for redirected_base_stats this wave -- it's on
    # simc_string, which engines must render verbatim for this item.
    assert f"redirected_base_stats={src.id}" in cat.simc_string
    assert f"id={cat.id}" in cat.simc_string


def test_catalyst_variant_chest_inventory_type_20_source(season_mod, Item) -> None:
    # a non-tier chest (Reckless Spirit Breastplate, id 268222) catalyzed to the DK tier chest
    src = Item(key="equipped:chest", id=268222, slot="chest", inventory_type=5,
               bonus_ids=[13335, 13848], enchant_id=7987)
    cat = season_mod.catalyst_variant(src, "death_knight")
    assert cat.id == 271477 and cat.ilevel == 344
    assert "redirected_base_stats=268222" in cat.simc_string


def test_catalyst_variant_none_for_non_catalyst_slot(season_mod, Item) -> None:
    ring = Item(key="equipped:finger1", id=252258, slot="finger1", inventory_type=11, bonus_ids=[12854, 13335])
    assert season_mod.catalyst_variant(ring, "death_knight") is None


# ---------------------------------------------------------------------------
# voidforge_variant()

def test_voidforge_variant_myth_max_main_hand(season_mod, Item) -> None:
    # the checked-in dk_export fixture's main_hand (id 268209) at Myth 6/6, before Voidforge
    # (scratchpad w2/v_q5_myth6.simc); the export fixture itself already shows the
    # post-Voidforge state (bonus_id=13335/13848) for this same item id.
    mh = Item(key="equipped:main_hand", id=268209, slot="main_hand", inventory_type=13,
              bonus_ids=[13335, 12854], enchant_id=3368)
    vf = season_mod.voidforge_variant(mh)
    assert vf is not None
    assert vf.ilevel == 344
    assert 13848 in vf.bonus_ids
    assert 12854 not in vf.bonus_ids
    assert vf.key == "voidforge:equipped:main_hand"
    assert vf.enchant_id == 3368


def test_voidforge_variant_trinket(season_mod, Item) -> None:
    trinket = Item(key="equipped:trinket1", id=270175, slot="trinket1", inventory_type=12, bonus_ids=[13335, 12854])
    vf = season_mod.voidforge_variant(trinket)
    assert vf.ilevel == 344 and 13848 in vf.bonus_ids


def test_voidforge_variant_none_when_not_myth_max(season_mod, Item) -> None:
    # Hero 6/6 (bonus 12846) -- not Myth, so no Voidforge this season
    mh = Item(key="k", id=268209, slot="main_hand", inventory_type=13, bonus_ids=[13335, 12846])
    assert season_mod.voidforge_variant(mh) is None


def test_voidforge_variant_none_for_ineligible_slot(season_mod, Item) -> None:
    head = Item(key="k", id=271474, slot="head", inventory_type=1, bonus_ids=[4786, 12854])
    assert season_mod.voidforge_variant(head) is None


def test_voidforge_variant_already_voidforged_is_idempotent(season_mod, Item) -> None:
    # already at 13848 (no Myth-track bonus id at all) -- upgrade_of() won't match a
    # season-37 Myth track, so this correctly returns None rather than erroring.
    mh = Item(key="k", id=268209, slot="main_hand", inventory_type=13, bonus_ids=[13335, 13848])
    assert season_mod.voidforge_variant(mh) is None


# ---------------------------------------------------------------------------
# crafted_variant()

@pytest.fixture
def crafted_wrist(Item):
    # scratchpad w2/q8_fixture.simc: wrist=,id=237834,bonus_id=8793/8960/12384/13750/13751/
    # 13836/12497,gem_id=240908,crafted_stats=32/49,crafting_quality=5
    return Item(key="equipped:wrist", id=237834, slot="wrist", inventory_type=9,
                bonus_ids=[8793, 8960, 12384, 13750, 13751, 13836, 12497], gem_ids=[240908],
                crafted_stats=[49, 36], crafting_quality=5)


def test_crafted_variant_strips_stat_bonus_ids(season_mod, crafted_wrist) -> None:
    cr = season_mod.crafted_variant(crafted_wrist, ("haste", "versatility"))
    assert not (set(cr.bonus_ids) & {8790, 8791, 8792, 8793, 8794, 8795})
    assert cr.crafted_stats == [36, 40]
    assert "haste" in cr.stats and "versatility" in cr.stats
    assert "crit" not in cr.stats and "mastery" not in cr.stats
    # embellishment/quality bonuses untouched when not asked to change
    assert 8960 in cr.bonus_ids and 12384 in cr.bonus_ids and 12497 in cr.bonus_ids
    assert cr.key == "crafted:equipped:wrist"


def test_crafted_variant_swaps_embellishment(season_mod, crafted_wrist) -> None:
    cr = season_mod.crafted_variant(crafted_wrist, ("crit", "mastery"), embellishment_id=12693)
    assert 12384 not in cr.bonus_ids       # old embellishment (arcanoweave) gone
    assert 12693 in cr.bonus_ids            # new one (darkmoon hunt) present
    assert 8960 in cr.bonus_ids             # marker kept
    assert cr.crafted_stats == [32, 49]


def test_crafted_variant_swaps_quality(season_mod, crafted_wrist) -> None:
    cr = season_mod.crafted_variant(crafted_wrist, ("crit", "haste"), quality_bonus=12493)
    assert 12497 not in cr.bonus_ids
    assert 12493 in cr.bonus_ids


# ---------------------------------------------------------------------------
# socket_variant()

def test_socket_variant_adds_bonus_and_gem(season_mod, Item) -> None:
    # a bare Item() doesn't run resolve_row's socket-counting -- .sockets on a hand-built
    # fixture is just whatever was passed in (0 here), not derived from bonus_ids; only the
    # *output* of socket_variant (built via items.resolve_item) has a real computed value.
    # bonus_ids below carry no socket bonus of their own (verified: bonuses.socket_count == 0).
    head = Item(key="equipped:head", id=271474, slot="head", inventory_type=1, bonus_ids=[13335, 12854])
    sv = season_mod.socket_variant(head, 240908)
    assert 1808 in sv.bonus_ids
    assert sv.gem_ids == [240908]
    assert sv.sockets == 1
    assert sv.key == "socket:equipped:head"


def test_socket_variant_respects_existing_socket_cap(season_mod, Item) -> None:
    # a neck already carrying one real socket (bonus 13668, scratchpad w2/q4.py) plus its gem;
    # +1808 should cap the result at 2 filled gems, never 3.
    neck = Item(key="equipped:neck", id=268265, slot="neck", inventory_type=2,
                bonus_ids=[13335, 13708, 13848, 13668], gem_ids=[240908])
    sv = season_mod.socket_variant(neck, 240894)
    assert sv.sockets == 2
    assert sv.gem_ids == [240908, 240894]


# ---------------------------------------------------------------------------
# omnium_rows() / consumable_options()

def test_omnium_rows_accessor(season_mod) -> None:
    rows = season_mod.omnium_rows()
    assert len(rows) == 5
    assert rows[0]["choices"][0]["token"] == "rune_of_voidtouched_orbs"


def test_consumable_options_accessor(season_mod) -> None:
    opts = season_mod.consumable_options()
    assert "flask" in opts and "temporary_enchant" in opts


def test_socket_rules_accessor(season_mod) -> None:
    r = season_mod.socket_rules()
    assert r["add_bonus_id"] == 1808


def test_catalyst_accessor(season_mod) -> None:
    c = season_mod.catalyst()
    assert c["currency_id"] == 3465
    assert c["conversion_id"] == 13


# ---------------------------------------------------------------------------
# recommendations() gains catalyst/omnium

def test_recommendations_gains_catalyst_and_omnium(season_mod) -> None:
    r = season_mod.recommendations("death_knight", "frost")
    assert r["catalyst"]["charges_currency_id"] == 3465
    assert "head" in r["catalyst"]["slots"]
    assert len(r["omnium"]["rows"]) == 5
