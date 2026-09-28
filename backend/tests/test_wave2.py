"""Raidbots parity, wave 2 engine tests: Top Gear catalyst/socket/voidforge/crafted variants,
Droptimizer catalyst twins, Upgrades' Voidforge step, the new Consumables/Omnium sims, and
``CharacterProfile.omnium`` parsing. Season lookups are monkeypatched at each module's own
``_season_mod``/private hooks (mirrors how test_upgrades.py/test_droptimizer.py stub theirs) so
these run without the real DB2 cache; a few cross-checks use ``real_data_layer`` instead.
"""
from __future__ import annotations

import re

import pytest

from toonopt.data.season import UpgradeStep
from toonopt.models import (
    Baseline,
    CharacterProfile,
    Item,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.sims import consumables, droptimizer, omnium, topgear, upgrades

_PS_NAME_RE = re.compile(r'profileset\."([^"]+)"\+=')


class _FakeCtx:
    def __init__(self):
        self.progress_messages: list[str] = []

    def progress(self, phase, current=0, total=0, message=""):
        self.progress_messages.append(message)

    def check_cancelled(self):
        pass

    def sim(self, simc_text, options, *, klass="", spec="", stage_label=""):
        names = list(dict.fromkeys(_PS_NAME_RE.findall(simc_text)))
        rows = [ResultRow(name=n, label=n, dps=1000.0 + i) for i, n in enumerate(names)]
        return SimResult(job_id="j", type="topgear", baseline=Baseline(dps=1000.0), results=rows)


# ---------------------------------------------------------------------------
# Top Gear: catalyst / +socket / Voidforge / crafted variants


class FakeTopGearSeason:
    """Stands in for ``toonopt.data.season`` in Top Gear's variant-building tests."""

    def load(self):
        return {
            "crafted": {
                "embellishments": [{"bonus": 9001}, {"bonus": 9002, "second_bonus": 9003}],
                "max_embellished": 2,
            },
            "sockets": {"vault_slots": ["head", "wrist", "waist"]},
        }

    def catalyst_set_id(self, klass):
        return 4242 if klass == "death_knight" else None

    def socket_rules(self):
        return {"vault_slots": ["head", "wrist", "waist"]}

    def catalyst_variant(self, item, klass):
        if item.key == "no_variant":
            return None
        return item.model_copy(update={"id": 99900, "key": f"catalyst:{item.key}", "set_id": 4242})

    def socket_variant(self, item, gem_id):
        return item.model_copy(update={"key": f"socket:{item.key}", "gem_ids": [*item.gem_ids, gem_id]})

    def voidforge_variant(self, item):
        if item.slot not in ("main_hand", "off_hand", "trinket1", "trinket2"):
            return None
        return item.model_copy(update={"key": f"voidforge:{item.key}", "ilevel": 344})

    def crafted_variant(self, item, stats, embellishment_id=None, quality_bonus=None):
        return item.model_copy(update={"key": f"crafted:{item.key}", "crafted_stats": [1, 2]})

    def recommendations(self, klass, spec):
        return {"gems": {"default": {"id": 240908}}}


@pytest.fixture(autouse=True)
def _stub_topgear_season(monkeypatch):
    monkeypatch.setattr(topgear, "_season_mod", lambda: FakeTopGearSeason())


def test_build_variant_candidates_keys_and_label_suffixes(dk_profile):
    catalyst = topgear.CatalystRequest(keys=["bag:5"])
    add_socket = topgear.SocketRequest(keys=["equipped:head"])
    voidforge = topgear.VoidforgeRequest(keys=["equipped:main_hand"])
    crafted = [topgear.CraftedRequest(key="equipped:wrist", stats=("crit", "haste"))]
    out = topgear.build_variant_candidates(dk_profile, catalyst, add_socket, voidforge, crafted)
    by_prefix = {v.key.split(":", 1)[0]: v for v in out}
    assert by_prefix["catalyst"].key == "catalyst:bag:5" and by_prefix["catalyst"].name.endswith("(Catalyst)")
    assert by_prefix["socket"].key == "socket:equipped:head" and by_prefix["socket"].name.endswith("(+socket)")
    assert by_prefix["voidforge"].key == "voidforge:equipped:main_hand"
    assert by_prefix["voidforge"].name.endswith("(Voidforged)")
    assert by_prefix["crafted"].key == "crafted:equipped:wrist"
    assert by_prefix["crafted"].name.endswith("(recraft Crit/Haste)")


def test_build_variant_candidates_voidforge_real_data_layer(monkeypatch, real_data_layer, dk_unforged_profile):
    """Cross-check against the real season/bonus tables (no fake season, see
    ``test_bump_to_track_real_data_layer`` above): ``export_dk_frost_unforged.simc``'s
    main_hand is Myth 6/6 (bonus 12854, ilvl 334) rather than already Voidforged, so this is
    the one fixture that can actually exercise the real ``voidforge_variant`` codepath end to
    end -- ``export_dk_frost.simc`` itself carries bonus 13848 on every eligible slot already."""
    from toonopt.data import season

    monkeypatch.setattr(topgear, "_season_mod", lambda: season)
    out = topgear.build_variant_candidates(
        dk_unforged_profile, voidforge=topgear.VoidforgeRequest(keys=["equipped:main_hand"]),
    )
    assert len(out) == 1
    vf = out[0]
    assert vf.key == "voidforge:equipped:main_hand"
    assert 13848 in vf.bonus_ids
    assert vf.ilevel == 344
    assert vf.name.endswith("(Voidforged)")


def test_build_variant_candidates_skips_unknown_keys_and_none_variants(dk_profile):
    out = topgear.build_variant_candidates(dk_profile, topgear.CatalystRequest(keys=["not_a_real_key"]))
    assert out == []


def test_build_variant_candidates_socket_defaults_to_recommended_gem(dk_profile):
    out = topgear.build_variant_candidates(dk_profile, None, topgear.SocketRequest(keys=["equipped:head"]))
    assert out[0].gem_ids[-1] == 240908


def test_valid_catalyst_charges_limit():
    a = Item(key="catalyst:a", id=1, slot="head")
    b = Item(key="catalyst:b", id=2, slot="wrist")
    limits = topgear.VariantLimits(catalyst_charges=1)
    assert topgear._valid({"head": a}, limits) is True
    assert topgear._valid({"head": a, "wrist": b}, limits) is False
    # non-catalyzed items never count against charges
    c = Item(key="equipped:waist", id=3, slot="waist")
    assert topgear._valid({"head": a, "waist": c}, limits) is True


def test_valid_min_set_pieces():
    tier1 = Item(key="catalyst:a", id=1, slot="head", set_id=99)
    tier2 = Item(key="catalyst:b", id=2, slot="wrist", set_id=99)
    non_tier = Item(key="equipped:waist", id=3, slot="waist", set_id=None)
    limits = topgear.VariantLimits(min_set_pieces=2, catalyst_set_id=99)
    assert topgear._valid({"head": tier1}, limits) is False
    assert topgear._valid({"head": tier1, "waist": non_tier}, limits) is False
    assert topgear._valid({"head": tier1, "wrist": tier2}, limits) is True


def test_valid_vault_socket_cap():
    a = Item(key="socket:a", id=1, slot="head")
    b = Item(key="socket:b", id=2, slot="wrist")
    limits = topgear.VariantLimits(vault_slots=("head", "wrist", "waist"))
    assert topgear._valid({"head": a}, limits) is True
    assert topgear._valid({"head": a, "wrist": b}, limits) is False


def test_valid_embellished_cap():
    a = Item(key="a", id=1, slot="head", bonus_ids=[9001])
    b = Item(key="b", id=2, slot="wrist", bonus_ids=[9002])
    c = Item(key="c", id=3, slot="waist", bonus_ids=[9003])
    limits = topgear.VariantLimits(max_embellished=2, embellishment_bonus_ids=frozenset({9001, 9002, 9003}))
    assert topgear._valid({"head": a, "wrist": b}, limits) is True
    assert topgear._valid({"head": a, "wrist": b, "waist": c}, limits) is False


def test_build_offers_catalyst_variant_as_family_option(dk_profile):
    plan = topgear.build(dk_profile, SimOptions(iterations=10), [], catalyst=topgear.CatalystRequest(keys=["bag:5"]))
    assert any("(Catalyst)" in lbl for lbl in plan.labels.values())
    hands_changes = [m.changes["hands"] for m in plan.meta.values() if m.changes and "hands" in m.changes]
    assert any(it.key == "catalyst:bag:5" for it in hands_changes)


def test_build_min_set_pieces_filters_below_threshold(dk_profile):
    catalyst = topgear.CatalystRequest(keys=["bag:5"], min_set_pieces=2)
    plan = topgear.build(dk_profile, SimOptions(iterations=10), [], catalyst=catalyst)
    # the fixture's equipped gear carries no set_id (bare parse, no data layer) -- catalyzing
    # only bag:5's hands gives exactly 1 tier piece, below min_set_pieces=2.
    assert len(plan.profilesets) == 0


def test_execute_reports_catalyst_row(dk_profile):
    ctx = _FakeCtx()
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), [], max_combos=50,
                           catalyst=topgear.CatalystRequest(keys=["bag:5"]))
    assert any("(Catalyst)" in r.label for r in res.results)


def test_prepare_warns_when_season_unavailable(dk_profile, monkeypatch):
    monkeypatch.setattr(topgear, "_season_mod", lambda: None)
    msgs = []
    _, fams = topgear.prepare(dk_profile, SimOptions(), [], warn=msgs.append,
                               catalyst=topgear.CatalystRequest(keys=["bag:5"]))
    assert any("season data layer unavailable" in m for m in msgs)
    assert fams == []          # no candidates at all in this call (candidate_keys=[])


# ---------------------------------------------------------------------------
# Droptimizer: Catalyst twins (include_catalyst, CatalystSource) + add_socket


class FakeDropSeason:
    def catalyst(self):
        return {"slots": ["head", "hands"]}

    def catalyst_variant(self, item, klass):
        return item.model_copy(update={"id": 88800, "key": f"catalyst:{item.key}"})

    def socket_rules(self):
        return {"vault_slots": ["head", "wrist", "waist"]}

    def socket_variant(self, item, gem_id):
        return item.model_copy(update={"key": f"socket:{item.key}", "gem_ids": [gem_id]})

    def recommendations(self, klass, spec):
        return {"gems": {"default": {"id": 111}}}


def _drop_item(**kw) -> Item:
    base = {"key": "drop:1:0", "id": 700, "slot": "head", "ilevel": 350, "name": "Test Head"}
    base.update(kw)
    return Item(**base)


def test_catalyst_twin_tags_source_type(dk_profile, monkeypatch):
    item = _drop_item()
    twin = droptimizer._catalyst_twin(item, dk_profile, FakeDropSeason())
    assert twin.key == "catalyst:drop:1:0"
    assert twin.source.type == "catalyst"
    assert twin.name.endswith("(Catalyst)")


def test_apply_vault_socket_only_touches_vault_slots(dk_profile):
    head = _drop_item(slot="head")
    ring = _drop_item(key="drop:2:0", id=701, slot="finger")
    season = FakeDropSeason()
    assert droptimizer._apply_vault_socket(head, dk_profile, None, season).key == "socket:drop:1:0"
    assert droptimizer._apply_vault_socket(ring, dk_profile, None, season) is ring


def test_execute_include_catalyst_adds_twin_rows(monkeypatch, dk_profile):
    monkeypatch.setattr(droptimizer, "_season_mod", lambda: FakeDropSeason())
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [_drop_item()])
    ctx = _FakeCtx()
    res = droptimizer.execute(ctx, dk_profile, SimOptions(iterations=10), sources=[], upgrade="drop",
                               include_catalyst=True)
    assert any("(Catalyst)" in r.label for r in res.results)
    assert any("Catalyst" in n for n in res.notes)
    assert any(g.kind == "catalyst" for g in res.groups)


def test_execute_add_socket_mutates_vault_slot_drops(monkeypatch, dk_profile):
    monkeypatch.setattr(droptimizer, "_season_mod", lambda: FakeDropSeason())
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [_drop_item(slot="head")])
    ctx = _FakeCtx()
    res = droptimizer.execute(ctx, dk_profile, SimOptions(iterations=10), sources=[], upgrade="drop",
                               add_socket=True, preferred_gem=555)
    assert any(r.meta.changes and r.meta.changes["head"].key == "socket:drop:1:0" for r in res.results)


def test_execute_catalyst_source_bumps_and_catalyzes_gear(monkeypatch, dk_profile):
    monkeypatch.setattr(droptimizer, "_season_mod", lambda: FakeDropSeason())
    monkeypatch.setattr(droptimizer, "_bump_to_track", lambda item, track, rank, season: item.model_copy(
        update={"ilevel": 344}
    ))
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [])
    from toonopt.models import CatalystSource

    ctx = _FakeCtx()
    res = droptimizer.execute(ctx, dk_profile, SimOptions(iterations=10),
                               sources=[CatalystSource(track="Myth", rank=6)], upgrade="drop")
    assert any("(Catalyst)" in r.label for r in res.results)
    assert any("Myth" in n and "charge" in n for n in res.notes)


def test_execute_catalyst_source_without_season_notes_unavailable(monkeypatch, dk_profile):
    monkeypatch.setattr(droptimizer, "_season_mod", lambda: None)
    monkeypatch.setattr(droptimizer, "fetch_candidates", lambda p, s, u, o=False: [])
    from toonopt.models import CatalystSource

    ctx = _FakeCtx()
    res = droptimizer.execute(ctx, dk_profile, SimOptions(iterations=10),
                               sources=[CatalystSource(track="Myth")], upgrade="drop")
    assert any("unavailable" in n for n in res.notes)


def test_bump_to_track_real_data_layer(real_data_layer):
    """Cross-check against the real season/bonus tables (no fake season): bumping a Myth
    6/6 head down to Hero rank 3 swaps its track bonus id and ilevel."""
    from toonopt.data import season

    src = Item(key="k", id=251126, slot="head", bonus_ids=[4786, 12854, 13692, 13698, 13750])
    bumped = droptimizer._bump_to_track(src, "Hero", 3, season)
    assert bumped is not None
    hero = season.load()["upgrade_tracks"]["Hero"]
    assert bumped.ilevel == hero["ilevels"][2]
    assert hero["bonus_ids"][2] in bumped.bonus_ids
    assert 12854 not in bumped.bonus_ids


# ---------------------------------------------------------------------------
# Upgrades: Voidforge step


def _up_item(**kw) -> Item:
    base = {"key": "equipped:main_hand", "id": 900, "slot": "main_hand", "ilevel": 321, "name": "Test Weapon",
            "bonus_ids": [13335, 12854]}
    base.update(kw)
    return Item(**base)


def test_voidforge_row_added_for_myth_max_item(monkeypatch):
    vf_item = _up_item(bonus_ids=[13335, 13848], ilevel=344, key="voidforge:equipped:main_hand")
    monkeypatch.setattr(upgrades, "_current_track", lambda item: None)   # no normal track left
    monkeypatch.setattr(upgrades, "_upgrade_path", lambda item: [])
    monkeypatch.setattr(upgrades, "_voidforge_variant", lambda item: vf_item)
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost",
                               equipped={"main_hand": _up_item()})
    plan, skipped = upgrades.build(profile, SimOptions())
    assert skipped == 0
    assert len(plan.profilesets) == 1
    meta = next(iter(plan.meta.values()))
    assert meta.upgrade.track == "Voidforged"
    assert meta.upgrade.to_ilevel == 344 and meta.upgrade.crest == "Ascendant Voidcore"
    assert meta.changes["main_hand"].key == "voidforge:equipped:main_hand"


def test_voidforge_row_alongside_normal_steps(monkeypatch):
    steps = [UpgradeStep(rank=6, ilevel=321, bonus_ids=[12846], crest="Myth Mistcrest", cost=15)]
    monkeypatch.setattr(upgrades, "_current_track", lambda item: {"track": "Myth", "level": 5, "bonus_id": 12854})
    monkeypatch.setattr(upgrades, "_upgrade_path", lambda item: steps)
    monkeypatch.setattr(upgrades, "_max_rank", lambda track: 6)
    vf_item = _up_item(bonus_ids=[13335, 13848], ilevel=344, key="voidforge:equipped:main_hand")
    monkeypatch.setattr(upgrades, "_voidforge_variant", lambda item: vf_item)
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost",
                               equipped={"main_hand": _up_item()})
    plan, skipped = upgrades.build(profile, SimOptions())
    assert skipped == 0
    assert len(plan.profilesets) == 2      # 1 normal rank + 1 voidforge
    tracks = {m.upgrade.track for m in plan.meta.values()}
    assert tracks == {"Myth", "Voidforged"}


def test_no_voidforge_row_when_not_eligible(monkeypatch):
    monkeypatch.setattr(upgrades, "_current_track", lambda item: None)
    monkeypatch.setattr(upgrades, "_upgrade_path", lambda item: [])
    monkeypatch.setattr(upgrades, "_voidforge_variant", lambda item: None)
    profile = CharacterProfile(name="x", klass="death_knight", spec="frost", equipped={"head": _up_item(slot="head")})
    plan, skipped = upgrades.build(profile, SimOptions())
    assert skipped == 1 and len(plan.profilesets) == 0


def test_voidforge_row_real_data_layer_unforged_fixture(real_data_layer, dk_unforged_profile):
    """Same cross-check as ``test_build_variant_candidates_voidforge_real_data_layer`` but for
    the Upgrades engine: ``export_dk_frost_unforged.simc``'s main_hand is Myth 6/6 (no ranks
    left on the normal track), so its only row should be the Voidforge step, built entirely
    from the real season/bonus tables (no monkeypatched ``_current_track``/``_voidforge_variant``)."""
    plan, skipped = upgrades.build(dk_unforged_profile, SimOptions(), slots=["main_hand"])
    assert skipped == 0
    assert len(plan.profilesets) == 1
    meta = next(iter(plan.meta.values()))
    assert meta.upgrade.track == "Voidforged"
    assert meta.upgrade.to_ilevel == 344
    assert meta.upgrade.crest == "Ascendant Voidcore"
    assert meta.upgrade.cost == 1
    assert meta.changes["main_hand"].key == "voidforge:equipped:main_hand"
    assert meta.changes["main_hand"].ilevel == 344
    assert 13848 in meta.changes["main_hand"].bonus_ids


# ---------------------------------------------------------------------------
# Consumables sim


_FAKE_OPTIONS = {
    "flask": [{"value": "flask_a_2", "label": "Flask A"}, {"value": "flask_b_2", "label": "Flask B"}],
    "potion": [{"value": "potion_a_2", "label": "Potion A"}],
    "food": [{"value": "food_a", "label": "Food A"}],
    "augmentation": [{"value": "aug_a", "label": "Aug A"}],
    "temporary_enchant": [{"value": "main_hand:oil_a", "label": "Oil A"}],
}


@pytest.fixture(autouse=True)
def _stub_consumable_options(monkeypatch):
    monkeypatch.setattr(consumables, "_options", lambda: _FAKE_OPTIONS)


def test_available_false_when_season_stubbed():
    # the autouse no_data_layer fixture (conftest) stubs toonopt.data.season to None
    assert upgrades.available() is False


def test_build_one_row_per_option_excluding_current(dk_profile):
    plan = consumables.build(dk_profile, SimOptions(), categories=["flask", "potion"])
    labels = list(plan.labels.values())
    assert labels == ["Flask: Flask A", "Flask: Flask B", "Potion: Potion A"]
    meta = next(iter(plan.meta.values()))
    assert meta.consumable.category == "flask" and meta.consumable.name == "Flask A"


def test_build_skips_option_matching_current_selection(dk_profile):
    from toonopt.models import Consumables as ConsumablesOptions

    opts = SimOptions(consumables=ConsumablesOptions(flask="flask_a_2"))
    plan = consumables.build(dk_profile, opts, categories=["flask"])
    labels = list(plan.labels.values())
    assert labels == ["Flask: Flask B"]


def test_build_custom_sets_have_no_changes_meta(dk_profile):
    cs = consumables.CustomConsumableSet(name="My Set", flask="flask_a_2", potion="potion_a_2")
    plan = consumables.build(dk_profile, SimOptions(), categories=[], custom=[cs])
    assert len(plan.profilesets) == 1
    name = plan.profilesets[0].name
    assert plan.meta[name].loadout == "My Set" and plan.meta[name].changes is None
    assert "flask=flask_a_2" in plan.profilesets[0].overrides
    assert "potion=potion_a_2" in plan.profilesets[0].overrides


def test_build_caps_rows(monkeypatch, dk_profile):
    monkeypatch.setattr(consumables, "MAX_ROWS", 1)
    with pytest.raises(consumables.TooManyRows):
        consumables.build(dk_profile, SimOptions(), categories=["flask"])


def test_execute_runs_and_labels_rows(dk_profile):
    ctx = _FakeCtx()
    res = consumables.execute(ctx, dk_profile, SimOptions(iterations=10), categories=["flask", "potion"])
    assert len(res.results) == 3
    assert all(r.meta.consumable is not None for r in res.results)


# ---------------------------------------------------------------------------
# Omnium sim


_FAKE_ROWS = [
    {"row": 1, "node_id": 1, "choices": [{"entry_id": 10, "token": "a", "name": "A", "icon": ""},
                                          {"entry_id": 11, "token": "b", "name": "B", "icon": ""}]},
    {"row": 2, "node_id": 2, "choices": [{"entry_id": 20, "token": "c", "name": "C", "icon": ""},
                                          {"entry_id": 21, "token": "d", "name": "D", "icon": ""}]},
]


@pytest.fixture(autouse=True)
def _stub_omnium_rows(monkeypatch):
    monkeypatch.setattr(omnium, "_rows", lambda: _FAKE_ROWS)


def test_per_row_offers_non_current_choices(dk_profile):
    profile = dk_profile.model_copy(update={"omnium": {10: 1, 20: 1}})
    plan = omnium.build(profile, SimOptions(), "per_row")
    labels = list(plan.labels.values())
    assert labels == ["Row 1: B", "Row 2: D"]
    meta = plan.meta[plan.profilesets[0].name]
    assert meta.omnium.row == 1 and meta.omnium.entry_id == 11 and meta.omnium.name == "B"
    # row 1's swap keeps row 2 at its current pick (20), and vice versa
    assert "omnium_talents=11:1/20:1" in plan.profilesets[0].overrides
    assert "omnium_talents=10:1/21:1" in plan.profilesets[1].overrides


def test_per_row_falls_back_to_first_choice_when_no_current(dk_profile):
    plan = omnium.build(dk_profile, SimOptions(), "per_row")   # profile.omnium empty
    assert len(plan.profilesets) == 4    # every choice in both rows offered


def test_combos_full_cross_product_minus_current(dk_profile):
    profile = dk_profile.model_copy(update={"omnium": {10: 1, 20: 1}})
    plan = omnium.build(profile, SimOptions(), "combos")
    assert len(plan.profilesets) == 3    # 2x2 - 1 (current combo excluded)
    assert all(m.loadout is not None for m in plan.meta.values())


def test_custom_mode_enforces_one_choice_per_row(dk_profile):
    bad = omnium.OmniumSet(name="Bad", entries=[10, 11])
    with pytest.raises(ValueError, match="row 1"):
        omnium.build(dk_profile, SimOptions(), "custom", sets=[bad])
    good = omnium.OmniumSet(name="Good", entries=[10, 21])
    plan = omnium.build(dk_profile, SimOptions(), "custom", sets=[good])
    assert plan.profilesets[0].overrides == ["omnium_talents=10:1/21:1"]


def test_invalid_mode_raises(dk_profile):
    with pytest.raises(ValueError, match="invalid omnium mode"):
        omnium.build(dk_profile, SimOptions(), "bogus")


def test_caps_rows(monkeypatch, dk_profile):
    monkeypatch.setattr(omnium, "MAX_ROWS", 1)
    with pytest.raises(omnium.TooManyRows):
        omnium.build(dk_profile, SimOptions(), "combos")


def test_execute_runs_per_row(dk_profile):
    ctx = _FakeCtx()
    res = omnium.execute(ctx, dk_profile, SimOptions(iterations=10), "per_row")
    assert len(res.results) == 4
    assert all(r.meta.omnium is not None for r in res.results)


# ---------------------------------------------------------------------------
# CharacterProfile.omnium parsing (simc/profile.py)


def test_profile_parses_omnium_talents(dk_export):
    from toonopt.simc import profile

    p = profile.parse(dk_export)
    assert p.omnium == {136822: 1, 136819: 1, 136817: 1}
