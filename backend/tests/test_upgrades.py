"""Unit tests for sims/upgrades.py -- season/bonus lookups are monkeypatched at the
module's own private hooks (``_current_track``/``_upgrade_path``/``_max_rank``) so these
run without the real DB2 cache, mirroring how test_droptimizer.py stubs ``fetch_candidates``.
"""
from __future__ import annotations

import re

import pytest

from toonopt.data.season import UpgradeStep
from toonopt.models import (
    Baseline,
    CharacterProfile,
    Currency,
    Item,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.sims import upgrades

HERO_STEPS = [
    UpgradeStep(rank=2, ilevel=308, bonus_ids=[12842], crest="Hero Mistcrest", cost=20),
    UpgradeStep(rank=3, ilevel=311, bonus_ids=[12843], crest="Hero Mistcrest", cost=20),
    UpgradeStep(rank=4, ilevel=315, bonus_ids=[12844], crest="Hero Mistcrest", cost=20),
    UpgradeStep(rank=5, ilevel=318, bonus_ids=[12845], crest="Hero Mistcrest", cost=20),
    UpgradeStep(rank=6, ilevel=321, bonus_ids=[12846], crest="Hero Mistcrest", cost=20),
]


def _item(**kw) -> Item:
    base = {"key": "equipped:head", "id": 500, "slot": "head", "ilevel": 305, "name": "Test Helm",
            "bonus_ids": [12841]}
    base.update(kw)
    return Item(**base)


@pytest.fixture(autouse=True)
def stub_upgrade_data(monkeypatch):
    def current_track(item: Item):
        return {"track": "Hero", "level": 1, "bonus_id": 12841} if item.bonus_ids == [12841] else None

    def upgrade_path(item: Item):
        return list(HERO_STEPS) if item.bonus_ids == [12841] else []

    monkeypatch.setattr(upgrades, "_current_track", current_track)
    monkeypatch.setattr(upgrades, "_upgrade_path", upgrade_path)
    monkeypatch.setattr(upgrades, "_max_rank", lambda track: 6)


def test_available_false_when_season_stubbed():
    # the autouse no_data_layer fixture (conftest) stubs toonopt.data.season to None
    assert upgrades.available() is False


def test_build_one_row_per_remaining_rank():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    plan, skipped = upgrades.build(profile, SimOptions())
    assert skipped == 0
    assert len(plan.profilesets) == 5
    labels = list(plan.labels.values())
    assert labels[0] == "Head: Hero 1/6 -> 2/6 (ilvl 305 -> 308, 20 Hero Mistcrest)"
    assert labels[-1] == "Head: Hero 1/6 -> 6/6 (ilvl 305 -> 321, 100 Hero Mistcrest)"
    last_name = plan.profilesets[-1].name
    up = plan.meta[last_name].upgrade
    assert up.slot == "head" and up.track == "Hero" and up.from_rank == 1 and up.to_rank == 6
    assert up.max_rank == 6 and up.from_ilevel == 305 and up.to_ilevel == 321
    assert up.cost == 100 and up.crest == "Hero Mistcrest" and len(up.steps) == 5
    assert up.steps[0].rank == 2 and up.steps[0].cost == 20
    changed = plan.meta[last_name].changes["head"]
    assert changed.ilevel == 321 and changed.bonus_ids == [12846]


def test_max_ranks_limits_steps():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    plan, _ = upgrades.build(profile, SimOptions(), max_ranks=2)
    assert len(plan.profilesets) == 2
    last_name = plan.profilesets[-1].name
    assert plan.meta[last_name].upgrade.to_rank == 3


def test_min_ilevel_filters_slot_before_track_lookup():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    plan, skipped = upgrades.build(profile, SimOptions(), min_ilevel=400)
    assert len(plan.profilesets) == 0 and skipped == 0


def test_skips_slots_without_track_and_counts():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={
        "head": _item(),
        "chest": _item(key="equipped:chest", id=501, slot="chest", bonus_ids=[999]),
    })
    plan, skipped = upgrades.build(profile, SimOptions())
    assert skipped == 1
    assert len(plan.profilesets) == 5
    assert plan.notes == [
        "Skipped 1 slot(s) with no remaining upgrade: chest (already at max rank or no crest track)."
    ]


def test_explicit_slots_restrict_selection():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={
        "head": _item(),
        "chest": _item(key="equipped:chest", id=502, slot="chest"),
    })
    plan, skipped = upgrades.build(profile, SimOptions(), slots=["chest"])
    assert skipped == 0
    assert len(plan.profilesets) == 5
    assert all("chest" in m.changes for m in plan.meta.values())


def test_affordable_none_without_currency_info():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    plan, _ = upgrades.build(profile, SimOptions())
    assert all(m.upgrade.affordable is None for m in plan.meta.values())


def test_affordable_true_when_enough_crests():
    profile = CharacterProfile(
        name="x", klass="death_knight", spec="frost", equipped={"head": _item()},
        currencies=[Currency(id=3445, kind="currency", amount=100, name="Hero Mistcrest", crest="Hero Mistcrest")],
    )
    plan, _ = upgrades.build(profile, SimOptions())
    by_to_rank = {m.upgrade.to_rank: m.upgrade for m in plan.meta.values()}
    assert by_to_rank[2].cost == 20 and by_to_rank[2].affordable is True     # 20 <= 100
    assert by_to_rank[6].cost == 100 and by_to_rank[6].affordable is True    # 100 <= 100


def test_affordable_false_when_not_enough_crests():
    profile = CharacterProfile(
        name="x", klass="death_knight", spec="frost", equipped={"head": _item()},
        currencies=[Currency(id=3445, kind="currency", amount=30, name="Hero Mistcrest", crest="Hero Mistcrest")],
    )
    plan, _ = upgrades.build(profile, SimOptions())
    by_to_rank = {m.upgrade.to_rank: m.upgrade for m in plan.meta.values()}
    assert by_to_rank[2].cost == 20 and by_to_rank[2].affordable is True     # 20 <= 30
    assert by_to_rank[6].cost == 100 and by_to_rank[6].affordable is False   # 100 > 30


def test_affordable_false_when_currencies_present_but_not_this_crest():
    profile = CharacterProfile(
        name="x", klass="death_knight", spec="frost", equipped={"head": _item()},
        currencies=[Currency(id=3444, kind="currency", amount=999, name="Champion Mistcrest", crest="Champion Mistcrest")],
    )
    plan, _ = upgrades.build(profile, SimOptions())
    assert all(m.upgrade.affordable is False for m in plan.meta.values())


def test_too_many_profilesets(monkeypatch):
    monkeypatch.setattr(upgrades, "MAX_PROFILESETS", 2)
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    with pytest.raises(upgrades.TooManyProfilesets):
        upgrades.build(profile, SimOptions())


_PS_NAME_RE = re.compile(r'profileset\."([^"]+)"\+=')


class _FakeCtx:
    def __init__(self):
        self.progress_messages: list[str] = []

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def sim(self, simc_text, options, *, klass="", spec=""):
        names = list(dict.fromkeys(_PS_NAME_RE.findall(simc_text)))
        rows = [ResultRow(name=n, label=n, dps=1000.0 + i) for i, n in enumerate(names)]
        return SimResult(job_id="j", type="upgrades", baseline=Baseline(dps=1000.0), results=rows)


def test_execute_populates_meta_and_reports_skips():
    ctx = _FakeCtx()
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={
        "head": _item(),
        "chest": _item(key="equipped:chest", id=503, slot="chest", bonus_ids=[999]),
    })
    res = upgrades.execute(ctx, profile, SimOptions())
    assert len(res.results) == 5
    assert any("Skipped 1 slot(s) without a recognised upgrade track" in m for m in ctx.progress_messages)
    assert any("chest" in note for note in res.notes)
    top = max(res.results, key=lambda r: r.dps)
    assert top.meta.upgrade is not None
    assert top.meta.changes["head"].ilevel in (308, 311, 315, 318, 321)


def test_execute_notes_empty_when_nothing_skipped():
    ctx = _FakeCtx()
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _item()})
    res = upgrades.execute(ctx, profile, SimOptions())
    assert res.notes == []
