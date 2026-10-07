"""Unit tests for sims/gems.py -- ``gems._data()`` (the module's one hook into
``toonopt.data.bonuses``/``toonopt.data.season``) is monkeypatched with fakes so these run
without the real DB2 cache. Socket counts are modelled the same way ``best_gems`` itself
falls back when bonus-id decoding yields 0: ``len(item.gem_ids)`` (a list of zeros = empty
sockets of that count).
"""
from __future__ import annotations

import re
import types

import pytest

from toonopt.models import (
    Baseline,
    CharacterProfile,
    Item,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.sims import gems
from toonopt.sims.gems import GemSet

RECS = {
    "season": "Test Season",
    "gems": {
        "default": {"id": 1, "name": "Mastery Gem", "icon": "i1", "stat": "mastery"},
        "by_stat": {
            "crit": {"id": 11, "name": "Crit Gem", "icon": "i2", "stat": "crit"},
            "haste": {"id": 12, "name": "Haste Gem", "icon": "i3", "stat": "haste"},
            "mastery": {"id": 1, "name": "Mastery Gem", "icon": "i1", "stat": "mastery"},
            "versatility": {"id": 13, "name": "Vers Gem", "icon": "i4", "stat": "versatility"},
        },
        "unique": [
            {"id": 99, "name": "Diamond", "icon": "i5", "stat": "primary", "limit": 1, "limit_category": "Diamond"},
            {"id": 98, "name": "Odd Diamond", "icon": "i6", "stat": "special", "limit": 1, "limit_category": "Diamond"},
        ],
    },
    "enchants": {
        "head": [
            {"id": 501, "name": "Head Ench A", "recommended": True},
            {"id": 502, "name": "Head Ench B", "recommended": False},
        ],
        "chest": [{"id": 601, "name": "Chest Ench A", "recommended": True, "stat": "all"}],
    },
    "consumables": {},
}


def _item(**kw) -> Item:
    base = {"key": "equipped:neck", "id": 100, "slot": "neck", "ilevel": 300, "gem_ids": []}
    base.update(kw)
    return Item(**base)


def _bonuses_mod():
    # socket_count is bonus-id driven in production; tests instead give items gem_ids of the
    # desired length ([0, 0] = two empty sockets) and rely on gems.socket_count()'s fallback.
    return types.SimpleNamespace(socket_count=lambda bonus_ids, build=None: 0)


def _season_mod():
    def best_gems(item: Item, profile: CharacterProfile) -> list[int]:
        n = len(item.gem_ids)
        return [1] * n if n else []

    def best_enchant(slot: str, profile: CharacterProfile):
        opts = RECS["enchants"].get(slot)
        return opts[0]["id"] if opts else None

    def recommendations(klass: str, spec: str) -> dict:
        return RECS

    return types.SimpleNamespace(best_gems=best_gems, best_enchant=best_enchant, recommendations=recommendations)


@pytest.fixture(autouse=True)
def stub_data(monkeypatch):
    monkeypatch.setattr(gems, "_data", lambda: (_bonuses_mod(), _season_mod()))


def test_available_false_when_season_stubbed():
    assert gems.available() is False


def test_uniform_rows_and_recommended():
    neck = _item(gem_ids=[0])                                      # 1 socket
    trinket = _item(key="equipped:trinket1", id=200, slot="trinket1", gem_ids=[])   # no sockets
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"neck": neck, "trinket1": trinket})
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[11, 12], include_enchants=False)
    assert len(plan.profilesets) == 3          # 2 pool gems + Recommended
    labels = list(plan.labels.values())
    assert "All sockets: Crit gem" in labels and "All sockets: Haste gem" in labels and "Recommended" in labels
    rec_name = next(n for n, label in plan.labels.items() if label == "Recommended")
    assert plan.meta[rec_name].changes["neck"].gem_ids == [1]
    assert "trinket1" not in plan.meta[rec_name].changes           # no sockets -> untouched


def test_uniform_skips_recommended_row_without_sockets():
    trinket = _item(key="equipped:trinket1", id=200, slot="trinket1", gem_ids=[])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"trinket1": trinket})
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[11, 12], include_enchants=False)
    assert len(plan.profilesets) == 0
    assert plan.notes == [
        "Skipped 1 item(s) with no sockets: trinket1 (item has no gem sockets)."
    ]


def test_per_socket_rows_and_meta():
    neck = _item(gem_ids=[0, 0])                                    # 2 sockets
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"neck": neck})
    plan = gems.build(profile, SimOptions(), mode="per_socket", gem_pool=[11, 12], include_enchants=False)
    assert len(plan.profilesets) == 4                               # 2 sockets * 2 pool gems
    first = plan.profilesets[0].name
    assert plan.labels[first] == "Neck socket 1: Crit gem"
    gc = plan.meta[first].gem
    assert gc.slot == "neck" and gc.socket_index == 0 and gc.gem_id == 11 and gc.gem_name == "Crit Gem"
    assert plan.meta[first].changes["neck"].gem_ids == [11, 0]
    third = plan.profilesets[2].name                                # socket index 1, first pool gem
    assert plan.meta[third].gem.socket_index == 1
    assert plan.meta[third].changes["neck"].gem_ids == [0, 11]


def test_custom_rows_apply_gems_and_enchants():
    neck = _item(gem_ids=[0])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"neck": neck})
    sets = [GemSet(name="My Set", gems={"neck": [11]}, enchants={})]
    plan = gems.build(profile, SimOptions(), mode="custom", sets=sets, include_enchants=False)
    assert len(plan.profilesets) == 1
    name = plan.profilesets[0].name
    assert plan.labels[name] == "My Set"
    assert plan.meta[name].changes["neck"].gem_ids == [11]


def test_custom_skips_sets_touching_unequipped_slots():
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={})
    sets = [GemSet(name="Empty", gems={"neck": [11]}, enchants={})]
    plan = gems.build(profile, SimOptions(), mode="custom", sets=sets, include_enchants=False)
    assert len(plan.profilesets) == 0


def test_include_enchants_adds_rows_that_differ_from_current():
    head = _item(key="equipped:head", id=300, slot="head", enchant_id=501, gem_ids=[])
    chest = _item(key="equipped:chest", id=301, slot="chest", enchant_id=None, gem_ids=[])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"head": head, "chest": chest})
    plan = gems.build(profile, SimOptions(), mode="custom", sets=[], include_enchants=True)
    labels = list(plan.labels.values())
    assert "Head enchant: Head Ench B" in labels          # 501 already applied -> not offered again
    assert "Head enchant: Head Ench A" not in labels
    assert "Chest enchant: Chest Ench A" in labels
    name = next(n for n, label in plan.labels.items() if label == "Chest enchant: Chest Ench A")
    ec = plan.meta[name].enchant
    assert ec.slot == "chest" and ec.enchant_id == 601 and ec.name == "Chest Ench A" and ec.stat == "all"


def test_enchant_rows_note_slots_without_enchant_options():
    head = _item(key="equipped:head", id=300, slot="head", enchant_id=None, gem_ids=[])
    neck = _item(key="equipped:neck", id=301, slot="neck", enchant_id=None, gem_ids=[])   # no enchant options
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"head": head, "neck": neck})
    plan = gems.build(profile, SimOptions(), mode="custom", sets=[], include_enchants=True)
    assert plan.notes == [
        "Skipped 1 slot(s) with no enchant options: neck (no enchant available for this slot)."
    ]


def test_enchant_slots_filter_restricts_rows():
    head = _item(key="equipped:head", id=300, slot="head", enchant_id=None, gem_ids=[])
    chest = _item(key="equipped:chest", id=301, slot="chest", enchant_id=None, gem_ids=[])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"head": head, "chest": chest})
    plan = gems.build(profile, SimOptions(), mode="custom", sets=[], include_enchants=True, enchant_slots=["chest"])
    labels = list(plan.labels.values())
    assert all("Head enchant" not in label for label in labels)
    assert any("Chest enchant" in label for label in labels)


def test_invalid_mode_raises():
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={})
    with pytest.raises(ValueError, match="invalid gems mode"):
        gems.build(profile, SimOptions(), mode="bogus")


def test_row_cap(monkeypatch):
    monkeypatch.setattr(gems, "MAX_ROWS", 2)
    neck = _item(gem_ids=[0])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"neck": neck})
    with pytest.raises(gems.TooManyRows):
        gems.build(profile, SimOptions(), mode="uniform", gem_pool=[11, 12, 13], include_enchants=False)


def test_default_pool_is_by_stat_plus_unique():
    assert gems.default_pool(RECS) == [11, 12, 1, 13, 99, 98]


_PS_NAME_RE = re.compile(r'profileset\."([^"]+)"\+=')


class _FakeCtx:
    def __init__(self):
        self.progress_messages: list[str] = []

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def sim(self, simc_text, options, *, klass="", spec=""):
        names = list(dict.fromkeys(_PS_NAME_RE.findall(simc_text)))
        rows = [ResultRow(name=n, label=n, dps=1000.0 + i) for i, n in enumerate(names)]
        return SimResult(job_id="j", type="gems", baseline=Baseline(dps=1000.0), results=rows)


def test_execute_populates_meta():
    ctx = _FakeCtx()
    neck = _item(gem_ids=[0])
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped={"neck": neck})
    res = gems.execute(ctx, profile, SimOptions(), mode="uniform", gem_pool=[11, 12], include_enchants=False)
    assert len(res.results) == 3
    assert all(r.meta.changes for r in res.results)
    assert res.notes == []


# --- unique-equipped gem limits ---------------------------------------------------------

DIAMONDS = {99, 98, 97}          # 97: a lower-rank diamond outside the pool, known via gem_limit


def _jewelry(neck=(1,), finger1=(1,), finger2=(1,)) -> CharacterProfile:
    eq = {
        slot: _item(key=f"equipped:{slot}", id=400 + i, slot=slot, gem_ids=list(g))
        for i, (slot, g) in enumerate((("neck", neck), ("finger1", finger1), ("finger2", finger2)))
    }
    return CharacterProfile(name="x", klass="hunter", spec="marksmanship", equipped=eq)


def _worn(profile: CharacterProfile, meta) -> dict[str, list[int]]:
    """Every socket's gem with this row applied (changed items + the untouched rest)."""
    return {slot: (meta.changes.get(slot) or item).gem_ids for slot, item in profile.equipped.items()}


def _diamond_count(worn: dict[str, list[int]]) -> int:
    return sum(g in DIAMONDS for gem_ids in worn.values() for g in gem_ids)


def _limited_season(monkeypatch, best_gems=None):
    mod = _season_mod()
    mod.gem_limit = lambda gem_id: ("Diamond", 1) if gem_id in DIAMONDS else None
    mod.gem_name = lambda gem_id: {97: "Old Diamond"}.get(gem_id, "")
    if best_gems:
        mod.best_gems = best_gems
    monkeypatch.setattr(gems, "_data", lambda: (_bonuses_mod(), mod))


def test_uniform_limited_gem_goes_in_the_neck_only(monkeypatch):
    _limited_season(monkeypatch)
    profile = _jewelry()
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[12, 99, 98], include_enchants=False)
    by_label = {plan.labels[n]: m for n, m in plan.meta.items()}
    row = by_label["Neck: Diamond, other sockets unchanged"]
    assert {s: it.gem_ids for s, it in row.changes.items()} == {"neck": [99]}
    assert "Neck: Odd Diamond, other sockets unchanged" in by_label
    assert by_label["All sockets: Haste gem"].changes["finger2"].gem_ids == [12]
    for meta in plan.meta.values():
        assert _diamond_count(_worn(profile, meta)) <= 1


def test_uniform_limited_gem_swaps_an_existing_diamond_in_place(monkeypatch):
    _limited_season(monkeypatch)
    profile = _jewelry(finger1=(97,))
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[12, 99], include_enchants=False)
    by_label = {plan.labels[n]: m for n, m in plan.meta.items()}
    row = by_label["Finger1: Diamond, other sockets unchanged"]
    assert {s: it.gem_ids for s, it in row.changes.items()} == {"finger1": [99]}
    stat_row = by_label["All sockets: Haste gem (kept Old Diamond in Finger1)"]
    assert "finger1" not in stat_row.changes
    assert _worn(profile, stat_row) == {"neck": [12], "finger1": [97], "finger2": [12]}


def test_uniform_skips_a_limited_gem_already_in_place(monkeypatch):
    _limited_season(monkeypatch)
    plan = gems.build(_jewelry(neck=(99,)), SimOptions(), mode="uniform", gem_pool=[99], include_enchants=False)
    assert list(plan.labels.values()) == ["Recommended"]


def test_uniform_limit_from_recs_without_season_lookup():
    # the default stub season has no gem_limit: RECS' unique entries alone carry the limit
    profile = _jewelry()
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[99], include_enchants=False)
    for meta in plan.meta.values():
        assert sum(g == 99 for gem_ids in _worn(profile, meta).values() for g in gem_ids) <= 1


def test_per_socket_limited_gem_replaces_the_other_diamond(monkeypatch):
    _limited_season(monkeypatch)
    profile = _jewelry(finger1=(97,))
    plan = gems.build(profile, SimOptions(), mode="per_socket", gem_pool=[99], include_enchants=False)
    by_label = {plan.labels[n]: m for n, m in plan.meta.items()}
    row = by_label["Neck socket 1: Diamond (Finger1 Old Diamond -> Mastery gem: unique-equipped)"]
    assert {s: it.gem_ids for s, it in row.changes.items()} == {"neck": [99], "finger1": [1]}
    assert row.gem.slot == "neck" and row.gem.gem_id == 99
    assert {s: it.gem_ids for s, it in by_label["Finger1 socket 1: Diamond"].changes.items()} == {"finger1": [99]}
    for meta in plan.meta.values():
        assert _diamond_count(_worn(profile, meta)) <= 1


def test_recommended_row_obeys_limits(monkeypatch):
    # best_gems keeps a diamond per item, so an (in-game impossible) import with two diamonds
    # would otherwise recommend both
    def best_gems(item: Item, profile: CharacterProfile) -> list[int]:
        kept = [g for g in item.gem_ids if g in DIAMONDS][:1]
        return kept + [1] * (len(item.gem_ids) - len(kept))

    _limited_season(monkeypatch, best_gems=best_gems)
    profile = _jewelry(neck=(99,), finger1=(98,))
    plan = gems.build(profile, SimOptions(), mode="uniform", gem_pool=[], include_enchants=False)
    rec = next(m for n, m in plan.meta.items() if plan.labels[n] == "Recommended")
    assert _worn(profile, rec) == {"neck": [99], "finger1": [1], "finger2": [1]}


def test_custom_set_over_the_limit_is_noted(monkeypatch):
    _limited_season(monkeypatch)
    sets = [GemSet(name="Greedy", gems={"neck": [99], "finger1": [98]}), GemSet(name="Fine", gems={"neck": [99]})]
    plan = gems.build(_jewelry(), SimOptions(), mode="custom", sets=sets, include_enchants=False)
    assert len(plan.profilesets) == 2
    assert plan.notes == [(
        'Set "Greedy" equips 2 Diamond gems but the game allows 1; it was simmed as given and cannot be '
        "equipped in game."
    )]


def test_season_gem_limit_reads_the_shared_diamond_category(real_data_layer):
    from toonopt.data import season

    # every Eversong Diamond shares ItemLimitCategory 698 "Thalassian Diamond", Quantity 1
    for gem_id in (240967, 240983, 240982):
        assert season.gem_limit(gem_id) == ("Thalassian Diamond", 1)
    assert season.gem_limit(240900) is None
    unique = season.recommendations("hunter", "marksmanship")["gems"]["unique"]
    assert unique and all(g["limit"] == 1 and g["limit_category"] == "Thalassian Diamond" for g in unique)


def test_season_gem_limit_falls_back_to_curated_diamonds(real_data_layer, monkeypatch):
    from toonopt.data import items, season

    def no_cache(*a, **k):
        raise FileNotFoundError("no DB2 cache")

    monkeypatch.setattr(items, "row", no_cache)
    assert season.gem_limit(240983) == ("Thalassian Diamond", 1)
    assert season.gem_limit(240900) is None


def test_enchant_notes_split_utility_only_slots(monkeypatch):
    mod = _season_mod()
    mod.utility_enchant_slots = lambda: ["head", "shoulder", "feet"]
    monkeypatch.setattr(gems, "_data", lambda: (_bonuses_mod(), mod))
    eq = {
        slot: _item(key=f"equipped:{slot}", id=500 + i, slot=slot, enchant_id=None, gem_ids=[])
        for i, slot in enumerate(("shoulder", "feet", "neck", "back"))
    }
    profile = CharacterProfile(name="x", klass="mage", spec="fire", equipped=eq)
    plan = gems.build(profile, SimOptions(), mode="custom", sets=[], include_enchants=True)
    assert plan.notes == [
        "Skipped 2 slot(s) with only utility enchants: shoulder, feet (speed / leech / avoidance; no DPS effect to sim).",
        "Skipped 2 slot(s) with no enchant options: neck, back (no enchant available for this slot).",
    ]


def test_season_has_midnight_shoulder_enchants(real_data_layer):
    from toonopt.data import season

    s = season.load()
    assert [o["id"] for o in s["enchant_options"]["shoulder"]] == [8001, 8031, 7973, 7971, 7999, 8029]
    assert s["enchants"]["shoulder"] == 8001
    assert season.utility_enchant_slots() == ["head", "shoulder", "feet"]
    profile = season.CharacterProfile(name="x", klass="hunter", spec="marksmanship")
    assert season.best_enchant("shoulder", profile) == 8001
