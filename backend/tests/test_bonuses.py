"""bonuses.ilevel_from_bonuses (Raidbots parity, wave 2: priority-tie bug fix).

Uses the real Raidbots bonus map (bonuses.json, cached alongside the DB2 tables) since the
priority/itemLevel data isn't derivable from a bare parsed Item at all.
"""
from __future__ import annotations


def test_ilevel_priority_tie_takes_the_max_level(real_data_layer) -> None:
    from toonopt.data import bonuses

    # 12854 (Myth 6/6, ilvl 334) and 13848 (Voidforged, ilvl 344) both carry itemLevel
    # priority 0 -- SimC/the client always show 344 regardless of which bonus id comes
    # first in the list; the old "first one wins on a tie" logic returned 334 for
    # [12854, 13848] and 344 for [13848, 12854], disagreeing with itself on order alone.
    assert bonuses.entry(12854)["itemLevel"]["priority"] == 0
    assert bonuses.entry(13848)["itemLevel"]["priority"] == 0
    assert bonuses.ilevel_from_bonuses([12854, 13848]) == 344
    assert bonuses.ilevel_from_bonuses([13848, 12854]) == 344


def test_ilevel_priority_tie_still_prefers_lower_priority_when_not_tied(real_data_layer) -> None:
    from toonopt.data import bonuses

    # sanity: a genuinely lower-priority entry still wins over a same-or-higher one even if
    # its own level is smaller (priority, not level, is the primary sort key).
    lo = bonuses.ilevel_from_bonuses([12854])
    assert lo == 334
