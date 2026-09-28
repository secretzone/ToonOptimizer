from __future__ import annotations

import re

from toonopt.models import CharacterProfile, Item, ItemSource, ResultMeta, ResultRow
from toonopt.sims import droptimizer


def _item(**kw) -> Item:
    base = {"key": "k", "id": 1, "slot": "head", "inventory_type": 0, "ilevel": 300}
    base.update(kw)
    return Item(**base)


def test_target_slots_expands_generic_only():
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    # generic slots (from loot.candidates()) expand to both concrete slots
    assert droptimizer.target_slots(_item(slot="finger"), profile) == ["finger1", "finger2"]
    assert droptimizer.target_slots(_item(slot="trinket"), profile) == ["trinket1", "trinket2"]
    # a concrete slot (already narrowed by candidates(), e.g. a unique-equipped ring that can
    # only legally replace the one copy already worn) is honoured as-is, not re-expanded
    assert droptimizer.target_slots(_item(slot="finger2"), profile) == ["finger2"]
    assert droptimizer.target_slots(_item(slot="trinket1"), profile) == ["trinket1"]
    # concrete weapon slots pass through untouched -- one candidate, one row, no duplicates
    assert droptimizer.target_slots(_item(slot="main_hand", inventory_type=13), profile) == ["main_hand"]
    assert droptimizer.target_slots(_item(slot="off_hand", inventory_type=13), profile) == ["off_hand"]
    # only the generic "weapon" slot is resolved by is_off_hand_only()
    assert droptimizer.target_slots(_item(slot="weapon", inventory_type=13), profile) == ["main_hand"]
    assert droptimizer.target_slots(_item(slot="weapon", inventory_type=23), profile) == ["off_hand"]
    # anything else (armor slots) passes through unchanged
    assert droptimizer.target_slots(_item(slot="head"), profile) == ["head"]


def test_build_one_row_per_concrete_weapon_slot():
    """A 1H weapon offered for both hands (loot.candidates() emits one main_hand-slotted and
    one off_hand-slotted candidate) must produce exactly one profileset per concrete slot --
    not four, and not two rows both landing on main_hand."""
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={
        "main_hand": _item(key="mh", id=10, slot="main_hand", inventory_type=13),
        "off_hand": _item(key="oh", id=11, slot="off_hand", inventory_type=13),
    })
    from toonopt.models import SimOptions
    dagger_mh = _item(key="d1", id=99, slot="main_hand", inventory_type=13, name="Dagger")
    dagger_oh = _item(key="d2", id=99, slot="off_hand", inventory_type=13, name="Dagger")
    plan = droptimizer.build(profile, SimOptions(), [dagger_mh, dagger_oh])
    slots_hit = sorted(next(iter(m.changes)) for m in plan.meta.values())
    assert slots_hit == ["main_hand", "off_hand"]
    assert len(plan.profilesets) == 2


class _FakeCtx:
    """Minimal ctx for exercising execute() without SimC."""

    def __init__(self):
        self.progress_messages: list[str] = []

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def sim(self, simc_text, options, *, klass="", spec=""):
        from toonopt.models import Baseline, SimResult

        return SimResult(job_id="j", type="droptimizer", baseline=Baseline(dps=1000.0))


def test_execute_drops_low_ilevel_candidates_before_build(monkeypatch):
    """min_ilevel must filter loot candidates before profilesets are built, so a low-ilevel
    drop is never simmed at all, and the number skipped is reported via ctx.progress."""
    from toonopt.models import SimOptions

    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    low = _item(key="drop:1:0", id=100, slot="head", ilevel=320, name="Low Helm")
    high = _item(key="drop:2:0", id=101, slot="head", ilevel=350, name="High Helm")
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [low, high])

    captured: dict = {}
    real_build = droptimizer.build

    def spy_build(profile, options, items, **kw):
        captured["items"] = items
        return real_build(profile, options, items, **kw)

    monkeypatch.setattr(droptimizer, "build", spy_build)
    ctx = _FakeCtx()
    droptimizer.execute(ctx, profile, SimOptions(), sources=[], upgrade="drop", min_ilevel=340)
    assert [i.key for i in captured["items"]] == ["drop:2:0"]
    assert any("Skipped 1 candidate(s) below min ilevel 340" in m for m in ctx.progress_messages)


def test_execute_without_min_ilevel_keeps_everything(monkeypatch):
    from toonopt.models import SimOptions

    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    low = _item(key="drop:1:0", id=100, slot="head", ilevel=320)
    high = _item(key="drop:2:0", id=101, slot="head", ilevel=350)
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [low, high])
    captured: dict = {}
    real_build = droptimizer.build

    def spy_build(profile, options, items, **kw):
        captured["items"] = items
        return real_build(profile, options, items, **kw)

    monkeypatch.setattr(droptimizer, "build", spy_build)
    ctx = _FakeCtx()
    droptimizer.execute(ctx, profile, SimOptions(), sources=[], upgrade="drop")
    assert {i.key for i in captured["items"]} == {"drop:1:0", "drop:2:0"}
    assert not any("Skipped" in m for m in ctx.progress_messages)


# ---------------------------------------------------------------------------
# staged precision (H5, sims.base.run_staged)

class _PrecisionFakeCtx:
    """Fake ctx for exercising ``options.precision`` through ``run_staged`` (see
    ``test_sims_base.py``'s ``StagedFakeCtx`` for the pattern) -- droptimizer hands
    ``run_staged`` a plain ``Plan``, so this only needs to return per-stage rows for
    whatever profileset names show up in the ``.simc`` text of each ``ctx.sim()`` call."""

    def __init__(self, dps_table: dict[str, list[tuple[float, float]]]):
        self.dps_table = dps_table
        self.sim_calls = 0
        self.progress_messages: list[str] = []

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def check_cancelled(self) -> None:
        pass

    def sim(self, simc_text, options, *, klass="", spec="", stage_label=""):
        from toonopt.models import Baseline, SimResult

        stage_idx = self.sim_calls
        self.sim_calls += 1
        names = sorted(set(re.findall(r'profileset\."([^"]+)"', simc_text)))
        rows = [ResultRow(name=n, label=n, dps=self.dps_table[n][stage_idx][0],
                           dps_error=self.dps_table[n][stage_idx][1]) for n in names]
        res = SimResult(job_id="j", type="droptimizer", baseline=Baseline(dps=1000.0))
        res.results = rows
        return res


def test_execute_runs_staged_precision_for_low(monkeypatch):
    from toonopt.models import SimOptions

    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    high = _item(key="drop:1:0", id=100, slot="head", ilevel=350, name="High Helm")
    low = _item(key="drop:2:0", id=101, slot="head", ilevel=340, name="Low Helm")
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [high, low])

    # same deterministic profileset names execute() will build internally
    plan = droptimizer.build(profile, SimOptions(), [high, low])
    strong_name, weak_name = list(plan.meta)
    dps_table = {
        strong_name: [(1100.0, 50.0), (1105.0, 10.0)],
        weak_name: [(900.0, 50.0)],            # eliminated after stage 1 ("low" has 2 stages)
    }
    ctx = _PrecisionFakeCtx(dps_table)

    res = droptimizer.execute(ctx, profile, SimOptions(precision="low"), sources=[], upgrade="drop")

    assert ctx.sim_calls == 2      # "low" -> precision_stages() == [1.0, 0.2]
    by_name = {r.name: r for r in res.results}
    assert by_name[strong_name].meta.stage == 2
    assert by_name[strong_name].dps == 1105.0
    assert by_name[weak_name].meta.stage == 1      # frozen at the stage it was dropped
    assert by_name[weak_name].dps == 900.0
    assert res.groups == droptimizer.build_groups(res.results, res.baseline.dps)  # post-processing still ran


def test_execute_without_precision_runs_single_pass(monkeypatch):
    from toonopt.models import SimOptions

    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    high = _item(key="drop:1:0", id=100, slot="head", ilevel=350, name="High Helm")
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [high])

    ctx = _FakeCtx()
    res = droptimizer.execute(ctx, profile, SimOptions(), sources=[], upgrade="drop")
    assert len(res.results) == 0   # _FakeCtx.sim() returns no rows; just confirms a single call
    # _FakeCtx.sim has no call counter, but a second ctx.sim signature (stage_label) would
    # raise TypeError if run_staged's path were taken instead -- reaching here proves it wasn't.


# ---------------------------------------------------------------------------
# upgrade_equipped (H3)

class _FakeStep:
    def __init__(self, rank: int, ilevel: int, bonus_ids: list[int]):
        self.rank = rank
        self.ilevel = ilevel
        self.bonus_ids = bonus_ids


def test_upgrade_equipped_items_max_and_match(monkeypatch):
    steps = [_FakeStep(2, 310, [201]), _FakeStep(3, 320, [202]), _FakeStep(4, 330, [203])]
    head = _item(key="equipped:head", id=50, slot="head", ilevel=300, bonus_ids=[200])
    other = _item(key="equipped:chest", id=51, slot="chest", ilevel=305, bonus_ids=[999])  # no recognised track
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost",
                                equipped={"head": head, "chest": other})

    def fake_upgrade_path(item):
        return list(steps) if item.bonus_ids == [200] else []

    monkeypatch.setattr(droptimizer, "_upgrade_path", fake_upgrade_path)

    # max: straight to the top step, regardless of reference_ilevel
    new_profile, upgraded = droptimizer.upgrade_equipped_items(profile, "max", reference_ilevel=1)
    assert upgraded == ["head"]
    assert new_profile.equipped["head"].ilevel == 330
    assert new_profile.equipped["head"].bonus_ids == [203]
    assert profile.equipped["head"].ilevel == 300     # original untouched (deep copy)
    assert new_profile.equipped["chest"].ilevel == 305  # no track -> untouched

    # match: highest step whose ilevel <= reference_ilevel
    new_profile, upgraded = droptimizer.upgrade_equipped_items(profile, "match", reference_ilevel=325)
    assert upgraded == ["head"]
    assert new_profile.equipped["head"].ilevel == 320
    assert new_profile.equipped["head"].bonus_ids == [202]

    # match: reference_ilevel below every step -> no upgrade applied
    new_profile, upgraded = droptimizer.upgrade_equipped_items(profile, "match", reference_ilevel=305)
    assert upgraded == []
    assert new_profile.equipped["head"].ilevel == 300

    # none: profile returned as-is (same object, no copy)
    same_profile, upgraded = droptimizer.upgrade_equipped_items(profile, "none", reference_ilevel=999)
    assert same_profile is profile
    assert upgraded == []


def test_execute_upgrade_equipped_max_sets_note_and_baseline_gear(monkeypatch):
    from toonopt.models import Baseline, SimOptions, SimResult

    steps = [_FakeStep(2, 310, [201])]
    head = _item(key="equipped:head", id=50, slot="head", ilevel=300, bonus_ids=[200], name="Old Helm")
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": head})
    drop = _item(key="drop:1:0", id=100, slot="chest", ilevel=350, name="New Chest")
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [drop])
    monkeypatch.setattr(droptimizer, "_upgrade_path", lambda item: list(steps) if item.bonus_ids == [200] else [])

    captured: dict = {}

    class Ctx(_FakeCtx):
        def sim(self, simc_text, options, *, klass="", spec=""):
            captured["simc_text"] = simc_text
            return SimResult(job_id="j", type="droptimizer", baseline=Baseline(dps=1000.0))

    res = droptimizer.execute(Ctx(), profile, SimOptions(), sources=[], upgrade="drop", upgrade_equipped="max")
    assert any("Upgraded equipped gear (max) in 1 slot(s): head" in n for n in res.notes)
    assert "bonus_id=201" in captured["simc_text"]
    assert "ilevel=310" in captured["simc_text"]


def test_execute_upgrade_equipped_none_leaves_notes_and_gear_untouched(monkeypatch):
    from toonopt.models import Baseline, SimOptions, SimResult

    head = _item(key="equipped:head", id=50, slot="head", ilevel=300, bonus_ids=[200], name="Old Helm")
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": head})
    drop = _item(key="drop:1:0", id=100, slot="chest", ilevel=350, name="New Chest")
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [drop])

    def boom(item):
        raise AssertionError("_upgrade_path must not be called when upgrade_equipped='none'")

    monkeypatch.setattr(droptimizer, "_upgrade_path", boom)

    captured: dict = {}

    class Ctx(_FakeCtx):
        def sim(self, simc_text, options, *, klass="", spec=""):
            captured["simc_text"] = simc_text
            return SimResult(job_id="j", type="droptimizer", baseline=Baseline(dps=1000.0))

    res = droptimizer.execute(Ctx(), profile, SimOptions(), sources=[], upgrade="drop")
    assert res.notes == []
    assert "ilevel=300" in captured["simc_text"]


# ---------------------------------------------------------------------------
# include_offspec (Low)

def test_fetch_candidates_forwards_include_offspec(monkeypatch):
    import sys
    import types

    captured: dict = {}

    def fake_candidates(profile, sources, upgrade, offspec=False):
        captured["offspec"] = offspec
        return []

    fake_mod = types.ModuleType("toonopt.data.loot")
    fake_mod.candidates = fake_candidates
    monkeypatch.setitem(sys.modules, "toonopt.data.loot", fake_mod)

    profile = CharacterProfile(name="x", klass="death_knight", spec="frost")
    droptimizer.fetch_candidates(profile, [], "drop", include_offspec=True)
    assert captured["offspec"] is True
    droptimizer.fetch_candidates(profile, [], "drop")
    assert captured["offspec"] is False


# ---------------------------------------------------------------------------
# per-source summary (H4)

def test_build_groups_collapses_ring_rows_to_one_item(monkeypatch):
    ring = _item(key="drop:200:finger", id=200, slot="finger1", ilevel=320, name="Ring",
                 source=ItemSource(type="raid", name="Test Raid", boss="Boss A", difficulty="heroic"))
    rows = [
        ResultRow(name="r1", label="Ring -> finger1", dps=1100.0, delta=100.0, delta_pct=10.0,
                  meta=ResultMeta(item=ring, source=ring.source, changes={"finger1": ring})),
        ResultRow(name="r2", label="Ring -> finger2", dps=1150.0, delta=150.0, delta_pct=15.0,
                  meta=ResultMeta(item=ring, source=ring.source, changes={"finger2": ring})),
    ]
    groups = droptimizer.build_groups(rows, baseline_dps=1000.0)
    assert len(groups) == 1
    g = groups[0]
    assert g.kind == "boss"
    assert g.n == 1                        # one item, even though it produced 2 rows
    assert g.best == 150.0
    assert g.best_label == "Ring -> finger2"
    assert g.ev == 150.0                   # mean(max(0, delta)) over 1 item
    assert g.upgrade_share == 1.0


def test_build_groups_ev_and_upgrade_share_across_items(monkeypatch):
    good = _item(key="drop:201:0", id=201, slot="head", ilevel=320, name="Good Helm",
                 source=ItemSource(type="dungeon", name="Test Dungeon", boss="Boss", key_level=10))
    bad = _item(key="drop:202:0", id=202, slot="head", ilevel=280, name="Bad Helm",
                source=ItemSource(type="dungeon", name="Test Dungeon", boss="Boss", key_level=10))
    rows = [
        ResultRow(name="r1", label="Good Helm -> head", dps=1200.0, delta=200.0, delta_pct=20.0,
                  meta=ResultMeta(item=good, source=good.source, changes={"head": good})),
        ResultRow(name="r2", label="Bad Helm -> head", dps=900.0, delta=-100.0, delta_pct=-10.0,
                  meta=ResultMeta(item=bad, source=bad.source, changes={"head": bad})),
    ]
    groups = droptimizer.build_groups(rows, baseline_dps=1000.0)
    assert len(groups) == 1
    g = groups[0]
    assert g.kind == "dungeon"
    assert g.n == 2
    assert g.best == 200.0
    assert g.ev == 100.0                   # (200 + max(0, -100)) / 2
    assert g.upgrade_share == 0.5


def test_build_groups_splits_by_source(monkeypatch):
    a = _item(key="drop:300:0", id=300, slot="head", ilevel=320, name="Raid Helm",
              source=ItemSource(type="raid", name="Test Raid", boss="Boss A", difficulty="heroic"))
    b = _item(key="drop:301:0", id=301, slot="chest", ilevel=320, name="World Boss Chest",
              source=ItemSource(type="world_boss", name="World Bosses", boss="Big Boss"))
    rows = [
        ResultRow(name="r1", label="Raid Helm -> head", dps=1050.0, delta=50.0, delta_pct=5.0,
                  meta=ResultMeta(item=a, source=a.source, changes={"head": a})),
        ResultRow(name="r2", label="World Boss Chest -> chest", dps=1075.0, delta=75.0, delta_pct=7.5,
                  meta=ResultMeta(item=b, source=b.source, changes={"chest": b})),
    ]
    groups = droptimizer.build_groups(rows, baseline_dps=1000.0)
    kinds = {g.kind for g in groups}
    assert kinds == {"boss", "world_boss"}
    assert len(groups) == 2
    assert groups[0].best >= groups[1].best   # sorted best-first
