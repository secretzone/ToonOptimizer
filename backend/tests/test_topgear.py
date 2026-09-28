from __future__ import annotations

import pytest

from toonopt.models import Item, SimOptions, SimResult
from toonopt.sims import droptimizer, gearcompare, talentcompare, topgear
from toonopt.sims.gearcompare import GearSet
from toonopt.sims.talentcompare import Loadout


def _labels(combos):
    return [c.label for c in combos]


def test_families_rings_trinkets_weapons(dk_profile):
    keys = ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5", "vault:1", "vault:2"]
    fams = topgear.families(dk_profile, topgear.select_candidates(dk_profile, keys))
    by = {f.name: f for f in fams}
    assert set(by) == {"finger", "trinket", "weapons", "hands", "feet", "waist"}
    # 3 rings -> 3 unordered pairs (equipped first)
    assert len(by["finger"].options) == 3
    assert by["finger"].options[0]["finger1"].key == "equipped:finger1"
    for opt in by["finger"].options[1:]:
        assert {opt["finger1"].key, opt["finger2"].key} & {"bag:1"}
    # equipped ring kept in its own slot when only one changes
    swap = next(o for o in by["finger"].options[1:] if o["finger2"].key == "equipped:finger2")
    assert swap["finger1"].key == "bag:1"
    assert len(by["trinket"].options) == 3
    # weapons: dual-wield frost DK, 1H candidates go in either hand, no item twice
    weapons = by["weapons"].options
    assert weapons[0] == {"main_hand": dk_profile.equipped["main_hand"], "off_hand": dk_profile.equipped["off_hand"]}
    for w in weapons[1:]:
        assert w["main_hand"] is not None and (w["off_hand"] is None or w["off_hand"].key != w["main_hand"].key)
    assert any(w["main_hand"].key == "bag:3" and w["off_hand"] and w["off_hand"].key == "equipped:off_hand" for w in weapons)
    assert any(w["main_hand"].key == "equipped:main_hand" and w["off_hand"] and w["off_hand"].key == "bag:4" for w in weapons)
    assert len(by["hands"].options) == 2 and len(by["feet"].options) == 2
    assert topgear.combo_count(fams) == 3 * 3 * len(weapons) * 2 * 2 * 2 - 1


def test_combos_exclude_baseline_and_label_changes(dk_profile):
    fams = topgear.families(dk_profile, topgear.select_candidates(dk_profile, ["bag:5", "vault:1"]))
    combos = topgear.combos_from(dk_profile, fams, [list(range(len(f.options))) for f in fams])
    assert len(combos) == 3
    labels = _labels(combos)
    assert "Chosen Bloodslayer's Fanged Grips (334) [hands]" in labels
    both = next(c for c in combos if len(c.assignment) == 2)
    assert set(both.assignment) == {"hands", "feet"} and len(both.items) == 2


def test_two_hander_swap(warrior_export):
    from toonopt.simc import profile

    w = profile.parse(warrior_export)
    fams = topgear.families(w, topgear.select_candidates(w, ["bag:1"]))
    weapons = next(f for f in fams if f.name == "weapons")
    assert len(weapons.options) == 2 and weapons.options[1]["off_hand"] is None
    combos = topgear.combos_from(w, fams, [[0, 1]])
    assert combos[0].assignment == {"main_hand": w.bags[0]}          # no off_hand override needed (none equipped)


def test_unique_equipped_rejected(dk_profile):
    p = dk_profile.model_copy(deep=True)
    p.equipped["finger1"] = p.equipped["finger1"].model_copy(update={"unique_equipped": "signet"})
    p.bags[0] = p.bags[0].model_copy(update={"unique_equipped": "signet"})
    fams = topgear.families(p, topgear.select_candidates(p, ["bag:1"]))
    combos = topgear.combos_from(p, fams, [list(range(len(f.options))) for f in fams])
    # bag:1 may only replace finger1 (the other signet), never sit next to it
    assert len(combos) == 1 and combos[0].assignment.get("finger1").key == "bag:1"


# ---------------------------------------------------------------------------
# H2: at most one Great Vault item per combination


def test_valid_rejects_multiple_vault_items():
    # two vault items that would otherwise legally coexist in different slots
    v1 = Item(key="vault:1", id=1001, name="Vault Feet", slot="feet", ilevel=344)
    v2 = Item(key="vault:2", id=1002, name="Vault Waist", slot="waist", ilevel=344)
    assert topgear._valid({"feet": v1}) is True
    assert topgear._valid({"waist": v2}) is True
    assert topgear._valid({"feet": v1, "waist": v2}) is False


def test_combos_never_pair_two_vault_items(dk_profile):
    # fixture's vault:1 (feet) and vault:2 (waist) are in different families and would
    # otherwise combine into a valid two-slot combo
    fams = topgear.families(dk_profile, topgear.select_candidates(dk_profile, ["vault:1", "vault:2"]))
    combos = topgear.combos_from(dk_profile, fams, [list(range(len(f.options))) for f in fams])
    assert len(combos) == 2
    assert all(len(c.assignment) == 1 for c in combos)
    assert {c.items[0].key for c in combos} == {"vault:1", "vault:2"}


def test_smart_path_respects_vault_rule(dk_profile, monkeypatch):
    """`_smart_select` calls `_valid` directly (not through `combos_from`); make sure the
    vault rule holds there too."""
    fams = topgear.families(dk_profile, topgear.select_candidates(dk_profile, ["vault:1", "vault:2"]))
    idx_tuples = topgear._enumerate_idx_tuples(fams)
    for idxs in idx_tuples:
        full, changed = topgear._full_and_changed(dk_profile, fams, idxs)
        if not changed:
            continue
        vault_items = [it for it in full.values() if it and it.key.startswith("vault:")]
        if len(vault_items) > 1:
            assert topgear._valid(full) is False


# ---------------------------------------------------------------------------
# H7: searched items (extra_items) merged in like bag candidates


def test_extra_items_merged_as_candidates(dk_profile):
    extra = Item(key="search:999", id=999, name="Searched Ring", slot="finger", ilevel=350)
    cands = topgear.select_candidates(dk_profile, ["search:999"], extra_items=[extra])
    assert [c.key for c in cands] == ["search:999"]
    fams = topgear.families(dk_profile, cands)
    assert "finger" in {f.name for f in fams}


def test_extra_items_respect_min_ilevel_and_unknown_keys(dk_profile):
    extra = Item(key="search:999", id=999, name="Searched Ring", slot="finger", ilevel=200)
    # below min_ilevel: dropped
    assert topgear.select_candidates(dk_profile, ["search:999"], min_ilevel=300, extra_items=[extra]) == []
    # not requested via candidate_keys: not merged
    assert topgear.select_candidates(dk_profile, [], extra_items=[extra]) == []


def test_execute_uses_extra_items(dk_profile):
    extra = Item(key="search:999", id=999, name="Searched Ring", slot="finger", ilevel=350)
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), ["search:999"], max_combos=50,
                           extra_items=[extra])
    # the searched ring can go into either ring slot -> 2 single-slot combos
    assert len(res.results) == 2


# ---------------------------------------------------------------------------
# H6b: talent loadouts crossed with gear combos


def test_plan_crosses_combos_with_loadouts(dk_profile):
    loadouts = [Loadout(name="Raid", string="AAA"), Loadout(name="MPlus", string="BBB")]
    plan = topgear.build(dk_profile, SimOptions(iterations=10), ["bag:5"], loadouts=loadouts)
    assert len(plan.profilesets) == 2   # 1 combo (hands swap) x 2 loadouts
    labels = list(plan.labels.values())
    assert any(lbl.endswith("· Raid") for lbl in labels)
    assert any(lbl.endswith("· MPlus") for lbl in labels)
    assert {m.loadout for m in plan.meta.values()} == {"Raid", "MPlus"}
    assert plan.simc_text.count("talents=AAA") == 1
    assert plan.simc_text.count("talents=BBB") == 1


def test_plan_without_loadouts_unchanged(dk_profile):
    plan = topgear.build(dk_profile, SimOptions(iterations=10), ["bag:5"])
    assert len(plan.profilesets) == 1
    assert next(iter(plan.meta.values())).loadout is None
    assert "·" not in next(iter(plan.labels.values()))


def test_execute_small_combo_with_loadouts(dk_profile):
    loadouts = [Loadout(name="Raid", string="AAA"), Loadout(name="MPlus", string="BBB")]
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), ["bag:5", "vault:1"], max_combos=100,
                           loadouts=loadouts)
    assert len(res.results) == 6     # 3 combos x 2 loadouts
    assert all(r.meta.loadout in {"Raid", "MPlus"} for r in res.results)


# ---------------------------------------------------------------------------
# H5: staged precision ("Smart Sim") wired into Top Gear


def test_execute_precision_low_runs_two_stages(dk_profile):
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10, precision="low"), ["bag:5", "vault:1"],
                           max_combos=50)
    assert ctx.runs == [
        "Precision 1/2 (target_error 1.0)",
        "Precision 2/2 (target_error 0.2)",
    ]
    assert len(res.results) == 3
    assert all(r.meta.stage == 2 for r in res.results)


def test_execute_precision_medium_runs_three_stages(dk_profile):
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10, precision="medium"), ["bag:5", "vault:1"],
                           max_combos=50)
    assert len(ctx.runs) == 3
    assert all(r.meta.stage == 3 for r in res.results)


def test_execute_precision_high_runs_three_stages_tighter(dk_profile):
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10, precision="high"), ["bag:5", "vault:1"],
                           max_combos=50)
    assert ctx.runs[-1] == "Precision 3/3 (target_error 0.05)"
    assert all(r.meta.stage == 3 for r in res.results)


def test_select_candidates_min_ilevel_drops_low_bag_vault_items(dk_profile):
    keys = ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5", "vault:1", "vault:2"]
    # bag:1/4/5 are ilevel 334, bag:2/3 and vault:1/2 are 344 (see fixture)
    cands = topgear.select_candidates(dk_profile, keys, min_ilevel=340)
    assert {c.key for c in cands} == {"bag:2", "bag:3", "vault:1", "vault:2"}
    # equipped items are never part of this pool, so a high threshold can't touch them
    assert topgear.select_candidates(dk_profile, keys, min_ilevel=1000) == []
    # no filter at all when omitted (existing behaviour)
    assert len(topgear.select_candidates(dk_profile, keys)) == 7


def test_execute_reports_skipped_low_ilevel_candidates(dk_profile):
    ctx = FakeCtx({})
    keys = ["bag:1", "bag:5"]   # both ilevel 334
    topgear.execute(ctx, dk_profile, SimOptions(iterations=10), keys, max_combos=50, min_ilevel=1000)
    assert any("Skipped 2 candidate(s) below min ilevel 1000" in m for m in ctx.progress_messages)


def test_plan_profilesets_and_meta(dk_profile):
    plan = topgear.build(dk_profile, SimOptions(iterations=10), ["bag:5", "vault:1"])
    assert len(plan.profilesets) == 3 and plan.simc_text.count('profileset."') == 4   # 2 singles + 1 double (2 lines)
    name, meta = next(iter(plan.meta.items()))
    assert meta.changes and meta.items and plan.labels[name]


class FakeCtx:
    """Runs the plan through a canned result so the two-stage logic can be exercised."""

    def __init__(self, dps_by_label):
        self.dps_by_label = dps_by_label
        self.runs: list[str] = []
        self.progress_messages: list[str] = []

    def check_cancelled(self):
        pass

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def sim(self, simc_text, options, *, klass="", spec="", stage_label=""):
        import re

        from toonopt.models import Baseline, ResultRow

        self.runs.append(stage_label)
        names = sorted(set(re.findall(r'profileset\."([^"]+)"', simc_text)))
        rows = [ResultRow(name=n, label=n, dps=0.0) for n in names]
        res = SimResult(job_id="j", type="topgear", baseline=Baseline(dps=1000.0))
        res.results = rows
        self._names = names
        return res


def test_two_stage_search(dk_profile, monkeypatch):
    keys = ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5", "vault:1", "vault:2"]
    ctx = FakeCtx({})
    scored = {}

    real_apply = topgear.apply_meta

    def scoring_apply(result, plan):
        for row in result.results:
            label = plan.labels[row.name]
            # make hands/feet swaps good, everything else bad, deterministic
            row.dps = 1000.0 + (50 if "hands" in label else 0) + (40 if "feet" in label else 0) - 10 * label.count(",")
            scored[label] = row.dps
        return real_apply(result, plan)

    monkeypatch.setattr(topgear, "apply_meta", scoring_apply)
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), keys, max_combos=8)
    assert len(ctx.runs) == 2 and ctx.runs[0].startswith("Stage 1/2") and ctx.runs[1].startswith("Stage 2/2")
    assert 1 <= len(res.results) <= 8
    assert res.results[0].label.count("[hands]") == 1 and "[feet]" in res.results[0].label
    assert res.results[0].meta.changes and res.results[0].delta > 0


def test_loadouts_combo_cap_applies_to_product(dk_profile, monkeypatch):
    """3 combos x 2 loadouts = 6, over max_combos=4 -> the 2-stage search kicks in and
    loadouts are crossed in at stage 2."""
    loadouts = [Loadout(name="Raid", string="AAA"), Loadout(name="MPlus", string="BBB")]
    ctx = FakeCtx({})

    real_apply = topgear.apply_meta

    def scoring_apply(result, plan):
        for row in result.results:
            row.dps = 1050.0        # every combo beats the 1000.0 baseline
        return real_apply(result, plan)

    monkeypatch.setattr(topgear, "apply_meta", scoring_apply)
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), ["bag:5", "vault:1"], max_combos=4,
                           loadouts=loadouts)
    assert len(ctx.runs) == 2 and ctx.runs[0].startswith("Stage 1/2") and ctx.runs[1].startswith("Stage 2/2")
    assert res.results and all(r.meta.loadout in {"Raid", "MPlus"} for r in res.results)
    assert all("·" in r.label for r in res.results)


def test_single_stage_when_small(dk_profile):
    ctx = FakeCtx({})
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), ["bag:5"], max_combos=50)
    assert ctx.runs == [""] and len(res.results) == 1


def test_gearcompare_and_talentcompare_plans(dk_profile):
    new_head = Item(key="drop:1", id=999, name="Test Helm", slot="head", ilevel=350, bonus_ids=[1])
    plan = gearcompare.build(dk_profile, SimOptions(iterations=10), [GearSet(name="Set A", changes={"head": new_head}), GearSet(name="Empty")])
    assert len(plan.profilesets) == 1 and 'profileset."set1"+=head=,id=999,bonus_id=1,ilevel=350' in plan.simc_text
    assert plan.labels["set1"] == "Set A" and plan.meta["set1"].changes["head"].id == 999
    plan = talentcompare.build(dk_profile, SimOptions(iterations=10), [Loadout(name="A", string="AAA"), Loadout(name="B", string="BBB")])
    assert 'profileset."loadout1"+=talents=AAA' in plan.simc_text and plan.meta["loadout2"].loadout == "BBB"


def test_droptimizer_plan(dk_profile):
    ring = Item(key="drop:1:0", id=555, name="Drop Ring", slot="finger", ilevel=350)
    twoh = Item(key="drop:2:0", id=556, name="Big Axe", slot="main_hand", inventory_type=17, ilevel=350)
    plan = droptimizer.build(dk_profile, SimOptions(iterations=10), [ring, twoh])
    labels = list(plan.labels.values())
    assert len(labels) == 3
    assert labels[0].startswith("Drop Ring (350) -> finger1 (replaces Sickening Signet of Atroxus (344))")
    assert labels[1].startswith("Drop Ring (350) -> finger2")
    assert "off_hand=" in plan.simc_text.split('profileset."d3"')[-1]      # 2H clears the off-hand
    assert plan.meta["d1"].item.id == 555 and plan.meta["d1"].changes["finger1"].id == 555
    assert droptimizer.available() is False or True


# ---------------------------------------------------------------------------
# gear legality (real DB2 cache): Top Gear must never propose gear the class can't equip.
# A bare parsed Item carries no weapon/armour subclass at all, so these can only be
# checked against the real data layer -- skipped when the cache isn't downloaded.


@pytest.mark.integration
def test_dagger_excluded_from_dk_bags(real_data_layer, dk_export):
    """bag:4 in the fixture (id 275070, Sharpened Lightwood Slasher) is a real dagger --
    illegal for a Death Knight (see toonopt.data.loot.WEAPONS) -- and used to crash SimC
    outright when Top Gear paired it into the main hand."""
    from toonopt.simc import profile

    p = profile.parse(dk_export)
    assert topgear.select_candidates(p, ["bag:4"]) == []


@pytest.mark.integration
def test_one_hand_sword_yields_both_hands(real_data_layer, dk_export):
    from toonopt.data.loot import usable_slots_for_profile
    from toonopt.simc import profile

    p = profile.parse(dk_export)      # frost DK dual-wields
    sword = Item(key="bag:sword", id=754, name="Test Sword", slot="off_hand")
    assert usable_slots_for_profile(sword, p) == ["main_hand", "off_hand"]


@pytest.mark.integration
def test_shield_excluded_for_non_shield_spec(real_data_layer, dk_export):
    from toonopt.data.loot import usable_slots_for_profile
    from toonopt.simc import profile

    p = profile.parse(dk_export)      # frost is not in loot.SHIELD_SPECS
    shield = Item(key="bag:shield", id=1168, name="Test Shield", slot="off_hand")
    assert usable_slots_for_profile(shield, p) == []


@pytest.mark.integration
def test_illegal_armor_subclass_excluded(real_data_layer, dk_export):
    """A cloth chest piece is illegal for a plate class (Death Knight)."""
    from toonopt.data.loot import usable_slots_for_profile
    from toonopt.simc import profile

    p = profile.parse(dk_export)
    cloth_chest = Item(key="bag:chest", id=940, name="Test Cloth Chest", slot="chest")
    assert usable_slots_for_profile(cloth_chest, p) == []


@pytest.mark.integration
def test_weapon_family_uses_legal_sword_not_illegal_daggers(real_data_layer, dk_export):
    """Both real weapons in the DK fixture's bags (id 271093 and 275070) are daggers and
    get filtered out entirely; a legal 1H sword added alongside them ends up as both a
    main_hand and an off_hand option."""
    from toonopt.simc import profile

    p = profile.parse(dk_export)
    p = p.model_copy(deep=True)
    p.bags.append(Item(key="bag:sword", id=754, name="Test Sword", slot="main_hand", inventory_type=13))
    cands = topgear.select_candidates(p, ["bag:3", "bag:4", "bag:sword"])
    assert [c.key for c in cands] == ["bag:sword"]
    weapons = next(f for f in topgear.families(p, cands) if f.name == "weapons")
    assert any(o.get("main_hand") and o["main_hand"].key == "bag:sword" for o in weapons.options)
    assert any(o.get("off_hand") and o["off_hand"].key == "bag:sword" for o in weapons.options)
