"""Unit tests for toonopt.data.loot: pure helpers that don't need the DB2 cache
(``_dungeon_row``/``_dungeon_ilevel`` for the per-key-level vault option) and the
off-spec gate on ``usable_slots`` (uses ``real_data_layer`` because ``_placements``
resolves the item's inventory slot via ``toonopt.data.items.canonical_slot``, a pure
lookup, but the module import chain is stubbed to ``None`` by the autouse
``no_data_layer`` fixture otherwise).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def loot(real_data_layer):
    from toonopt.data import loot as loot_mod

    return loot_mod


def test_dungeon_row_level_minus_one_is_max_vault(loot):
    keys_by_level = {
        5: {"ilevel": 300, "vault_ilevel": 310, "track": "Champion", "rank": 2, "vault_track": "Hero", "vault_rank": 1},
        10: {"ilevel": 320, "vault_ilevel": 330, "track": "Hero", "rank": 3, "vault_track": "Myth", "vault_rank": 1},
    }
    row, use_vault, max_vault = loot._dungeon_row(-1, False, keys_by_level)
    assert row is keys_by_level[10]
    assert use_vault is True and max_vault is True
    ilevel, track, rank = loot._dungeon_ilevel(row, use_vault)
    assert (ilevel, track, rank) == (330, "Myth", 1)


def test_dungeon_row_vault_flag_uses_own_key_level_vault(loot):
    """DungeonSource.vault=True at a concrete key level uses THAT level's vault ilvl, not
    the end-of-dungeon ilvl and not the max key level's vault (which -1 means)."""
    keys_by_level = {
        5: {"ilevel": 300, "vault_ilevel": 310, "track": "Champion", "rank": 2, "vault_track": "Hero", "vault_rank": 1},
        10: {"ilevel": 320, "vault_ilevel": 330, "track": "Hero", "rank": 3, "vault_track": "Myth", "vault_rank": 1},
    }
    row, use_vault, max_vault = loot._dungeon_row(5, True, keys_by_level)
    assert row is keys_by_level[5]
    assert use_vault is True and max_vault is False
    ilevel, track, rank = loot._dungeon_ilevel(row, use_vault)
    assert (ilevel, track, rank) == (310, "Hero", 1)


def test_dungeon_row_no_vault_flag_uses_end_of_dungeon(loot):
    keys_by_level = {5: {"ilevel": 300, "vault_ilevel": 310, "track": "Champion", "rank": 2,
                         "vault_track": "Hero", "vault_rank": 1}}
    row, use_vault, max_vault = loot._dungeon_row(5, False, keys_by_level)
    assert use_vault is False and max_vault is False
    ilevel, track, rank = loot._dungeon_ilevel(row, use_vault)
    assert (ilevel, track, rank) == (300, "Champion", 2)


def test_usable_slots_offspec_gate(loot):
    """An item that only grants an off-spec primary stat is rejected by default and only
    offered when ``offspec=True`` (DroptimizerRequest.include_offspec)."""
    item = {
        "id": 999, "quality": 4, "allowable_class": -1, "class_id": 4, "subclass_id": 4,
        "inv_type": 5, "stats": [3], "unique": False, "limit_category": 0,
    }
    cid = loot.CLASS_IDS["warrior"]
    key = "warrior_arms"       # primary stat 4 (strength); item only grants 3 (agility)
    assert loot.usable_slots(item, cid, key, offspec=False) is None
    assert loot.usable_slots(item, cid, key, offspec=True) == ["chest"]
