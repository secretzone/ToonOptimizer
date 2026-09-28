"""Unit tests for the data layer that need no DB2 cache."""
from __future__ import annotations

import pytest

from toonopt.data import items, loot, season, stats
from toonopt.data.talents import _Bits

# --- slot mapping -----------------------------------------------------------

@pytest.mark.parametrize("inv,slot", [
    (1, "head"), (2, "neck"), (3, "shoulder"), (5, "chest"), (20, "chest"), (6, "waist"), (7, "legs"),
    (8, "feet"), (9, "wrist"), (10, "hands"), (11, "finger"), (12, "trinket"), (16, "back"),
    (13, "main_hand"), (21, "main_hand"), (17, "main_hand"), (15, "main_hand"), (26, "main_hand"),
    (22, "off_hand"), (23, "off_hand"), (14, "off_hand"),
])
def test_inventory_type_to_slot(inv: int, slot: str) -> None:
    assert items.canonical_slot(inv) == slot


def test_slot_hint_only_when_legal() -> None:
    assert items.pick_slot(11, "finger2") == "finger2"
    assert items.pick_slot(11, "trinket1") == "finger"
    assert items.pick_slot(13, "off_hand") == "off_hand"      # dual-wielded one-hander
    assert items.pick_slot(17, "off_hand") == "main_hand"     # never a two-hander
    assert items.pick_slot(12, None) == "trinket"


# --- stat budget slots (itemStats.js) ----------------------------------------

def test_budget_slot_and_rating_type() -> None:
    assert stats.budget_slot(1, 4, 3) == 0            # head
    assert stats.budget_slot(12, 4, 0) == 1           # trinket
    assert stats.budget_slot(11, 4, 0) == 2           # ring
    assert stats.budget_slot(13, 2, 15) == 3          # dagger (1h)
    assert stats.budget_slot(17, 2, 8) == 0           # 2h sword
    assert stats.rating_type(11) == stats.CR_JEWELRY
    assert stats.rating_type(12) == stats.CR_TRINKET
    assert stats.rating_type(13) == stats.CR_WEAPON
    assert stats.rating_type(5) == stats.CR_ARMOR


def test_scale_curve_parser() -> None:
    text = "static constexpr double __combat_ratings_mult_by_ilvl[][1300] = {\n  // Armor\n  {\n 1.5, 1.5, // 2\n },\n { 2.0, 2.0 },\n};\n"
    curves = stats._parse_curves(text.replace("// 2", "").replace("// Armor", ""), "combat_ratings_mult_by_ilvl")
    assert curves == [[1.5, 1.5], [2.0, 2.0]]


# --- loot filter (lootFilter.js) ---------------------------------------------

def _item(**kw) -> dict:
    base = {"id": 1, "name": "x", "inv_type": 5, "quality": 4, "allowable_class": -1, "class_id": 4, "subclass_id": 1,
            "stats": [5, 7, 32, 36], "sockets": 0, "set_id": None, "unique": False, "limit_category": 0, "expansion": 11}
    base.update(kw)
    return base


def test_armor_type_and_primary_stat_gate() -> None:
    cloth_int = _item()
    assert loot.usable_slots(cloth_int, 8, "mage_fire") == ["chest"]
    assert loot.usable_slots(cloth_int, 1, "warrior_fury") is None             # plate wearer, cloth
    plate_str = _item(subclass_id=4, stats=[4, 7, 32])
    assert loot.usable_slots(plate_str, 1, "warrior_fury") == ["chest"]
    assert loot.usable_slots(plate_str, 2, "paladin_holy") is None             # int spec, str item
    agi_str = _item(subclass_id=4, stats=[72, 7])
    assert loot.usable_slots(agi_str, 6, "death_knight_frost") == ["chest"]
    assert loot.usable_slots(agi_str, 2, "paladin_holy") is None
    assert loot.usable_slots(agi_str, 2, "paladin_holy", offspec=True) == ["chest"]


def test_rings_trinkets_and_quality() -> None:
    ring = _item(inv_type=11, subclass_id=0, stats=[7, 32, 49])
    assert loot.usable_slots(ring, 8, "mage_fire") == ["finger1", "finger2"]
    assert loot.usable_slots(_item(inv_type=12, subclass_id=0, stats=[5], quality=2), 8, "mage_fire") is None
    assert loot.usable_slots(_item(inv_type=12, subclass_id=0, stats=[5], quality=2, curated=True), 8, "mage_fire") == ["trinket1", "trinket2"]


def test_unique_equipped_already_worn_only_that_slot() -> None:
    from toonopt.models import CharacterProfile, Item
    p = CharacterProfile(name="x", klass="mage", spec="fire", equipped={
        "trinket2": Item(key="e", id=99, slot="trinket2", inventory_type=12, ilevel=300)})
    trinket = _item(id=99, inv_type=12, subclass_id=0, stats=[5], unique=True)
    assert loot.usable_slots(trinket, 8, "mage_fire", gear=loot.Gear(p)) == ["trinket2"]


def test_spec_secondary_matches_curated_flask() -> None:
    from toonopt.models import CharacterProfile
    # mage_fire -> flask_of_thalassian_resistance_2 -> versatility (not always mastery)
    assert season._spec_secondary(CharacterProfile(name="x", klass="mage", spec="fire")) == "versatility"
    # death_knight_frost -> flask_of_the_shattered_sun_2 -> crit
    assert season._spec_secondary(CharacterProfile(name="y", klass="death_knight", spec="frost")) == "crit"
    # death_knight_unholy -> flask_of_the_blood_knights_2 -> haste
    assert season._spec_secondary(CharacterProfile(name="z", klass="death_knight", spec="unholy")) == "haste"


def test_validate_upgrade_accepts_drop_max_and_rank() -> None:
    loot.validate_upgrade("drop")
    loot.validate_upgrade("max")
    loot.validate_upgrade(3)
    loot.validate_upgrade("3")
    for bad in ("bogus", "", None, 0, -1, "-2"):
        with pytest.raises(ValueError, match="invalid upgrade value"):
            loot.validate_upgrade(bad)


def test_nearest_key_level_fills_gaps() -> None:
    table = {0: "m0", 2: "two", 3: "three", 12: "twelve"}
    assert loot._nearest_key_level(0, table) == "m0"
    assert loot._nearest_key_level(1, table) == "two"      # no level 1 -> next one up
    assert loot._nearest_key_level(2, table) == "two"
    assert loot._nearest_key_level(20, table) == "twelve"  # clamps to the top of the table
    assert loot._nearest_key_level(-5, table) == "m0"      # clamps to the bottom
    assert loot._nearest_key_level(5, {}) is None


def test_collapse_slot_pairs_rings_and_trinkets_once() -> None:
    # candidates() must emit a ring/trinket once under the generic slot, not once per
    # concrete slot -- sims/droptimizer.target_slots() re-expands "finger"/"trinket" to
    # both concrete slots at combo time, so emitting both here would double every row.
    assert loot._collapse_slot_pairs(["finger1", "finger2"]) == ["finger"]
    assert loot._collapse_slot_pairs(["trinket1", "trinket2"]) == ["trinket"]
    assert loot._collapse_slot_pairs(["chest"]) == ["chest"]
    assert loot._collapse_slot_pairs(["main_hand", "off_hand"]) == ["main_hand", "off_hand"]
    assert loot._collapse_slot_pairs(["trinket2"]) == ["trinket2"]        # already-worn-only case


def test_weapons() -> None:
    dagger = _item(inv_type=13, class_id=2, subclass_id=15, stats=[5, 7])
    assert loot.usable_slots(dagger, 8, "mage_fire") == ["main_hand"]
    agi_dagger = _item(inv_type=13, class_id=2, subclass_id=15, stats=[3, 7])
    assert loot.usable_slots(agi_dagger, 4, "rogue_assassination") == ["main_hand", "off_hand"]
    assert loot.usable_slots(agi_dagger, 3, "hunter_beast_mastery") == ["main_hand"]
    assert loot.usable_slots(_item(inv_type=17, class_id=2, subclass_id=8, stats=[4]), 4, "rogue_outlaw") is None   # rogues: no 2h swords
    two_h = _item(inv_type=17, class_id=2, subclass_id=8, stats=[4, 7])
    assert loot.usable_slots(two_h, 1, "warrior_fury") == ["main_hand", "off_hand"]    # Titan's Grip
    assert loot.usable_slots(two_h, 1, "warrior_arms") == ["main_hand"]
    shield = _item(inv_type=14, class_id=4, subclass_id=6, stats=[4, 7])
    assert loot.usable_slots(shield, 1, "warrior_protection") == ["off_hand"]
    assert loot.usable_slots(shield, 1, "warrior_fury") is None
    held = _item(inv_type=23, class_id=4, subclass_id=0, stats=[5, 7])
    assert loot.usable_slots(held, 8, "mage_fire") == ["off_hand"]
    assert loot.usable_slots(_item(inv_type=22, class_id=2, subclass_id=15, stats=[3]), 3, "hunter_survival") == ["off_hand"]
    assert loot.usable_slots(_item(inv_type=22, class_id=2, subclass_id=15, stats=[3]), 3, "hunter_marksmanship") is None


def test_two_hander_closes_off_hand() -> None:
    from toonopt.models import CharacterProfile, Item
    p = CharacterProfile(name="x", klass="paladin", spec="retribution", equipped={
        "main_hand": Item(key="e", id=5, slot="main_hand", inventory_type=17, ilevel=300)})
    shield = _item(inv_type=14, class_id=4, subclass_id=6, stats=[4, 7])
    assert loot.usable_slots(shield, 2, "paladin_protection", gear=loot.Gear(p)) is None


def test_spec_helpers() -> None:
    assert loot.spec_key("death_knight", "frost") == "death_knight_frost"
    assert loot.spec_key("deathknight", "frost") == "death_knight_frost"
    assert loot.primary_stat("demonhunter", "havoc") == "agility"
    assert loot.primary_stat("evoker", "augmentation") == "intellect"
    assert loot.CLASS_IDS["demon_hunter"] == 12


# --- upgrade math ------------------------------------------------------------

def test_upgrade_within_track() -> None:
    tracks = {"Hero": {"ilevels": [305, 308, 311, 315, 318, 321]}}
    assert loot._upgraded(308, "Hero", 2, "drop", tracks) == (308, 2)
    assert loot._upgraded(308, "Hero", 2, "max", tracks) == (321, 6)
    assert loot._upgraded(308, "Hero", 2, 4, tracks) == (315, 4)
    assert loot._upgraded(318, "Hero", 5, 2, tracks) == (318, 5)        # never downgrade
    assert loot._upgraded(302, None, None, "max", tracks) == (302, None)


# --- bit reader used by the loadout decoder ----------------------------------

def test_bit_reader_lsb_first() -> None:
    # "C" = 2 -> bits 0,1,0,0,0,0 ; "8" = 60 -> 0,0,1,1,1,1  => version byte = 2 | (0b00 << 6) -> 2
    b = _Bits("C8DA")
    assert b.read(8) == 2
