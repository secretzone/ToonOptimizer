"""End-to-end against a real simc.exe. Skipped when SimC is not installed.

Run with: uv run pytest -m integration -q
"""
from __future__ import annotations

import threading

import pytest

from toonopt.models import SimOptions
from toonopt.simc import input as simc_input
from toonopt.simc import profile, results, runner, runtime
from toonopt.simc.input import Profileset

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def simc():
    inst = runtime.installed()
    if inst is None:
        pytest.skip("SimC not installed")
    return inst


@pytest.fixture(scope="module")
def mid2_profile():
    from tests.conftest import FIXTURES

    return profile.parse((FIXTURES / "MID2_Death_Knight_Frost.simc").read_text("utf-8"))


def test_version_probe(simc):
    assert simc.simc_version and simc.wow_version.count(".") == 3
    assert simc.version_string.startswith("SimulationCraft ")


def test_quick_sim_end_to_end(simc, mid2_profile, tmp_path):
    events = []
    opts = SimOptions(iterations=200, threads=4)
    text = simc_input.build(mid2_profile, opts)
    out = runner.run(text, tmp_path, 4, lambda *a: events.append(a))
    assert out.json_path.exists() and out.seconds > 0
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 10000 and res.baseline.dps_error > 0
    assert res.wow_version == simc.wow_version and res.simc_version.startswith(simc.simc_version)
    assert res.breakdown and res.uptimes and res.timing.iterations >= 200
    phases = [e[0] for e in events]
    assert "baseline" in phases and any(e[1] == e[2] and e[2] >= 200 for e in events if e[0] == "baseline")


def test_profilesets_end_to_end(simc, mid2_profile, tmp_path):
    events = []
    ring = mid2_profile.equipped["finger2"]
    sets = [
        Profileset("ring_swap", "Ring swap", [simc_input.item_line(ring, "finger1")]),
        Profileset("no_trinket2", "No trinket 2", ["trinket2="]),
        Profileset("talents_same", "Same talents", [f"talents={mid2_profile.talents}"]),
    ]
    text = simc_input.build(mid2_profile, SimOptions(iterations=200, threads=4), sets)
    out = runner.run(text, tmp_path, 4, lambda *a: events.append(a))
    res = results.parse_file(out.json_path, out.stdout)
    assert {r.name for r in res.results} == {"ring_swap", "no_trinket2", "talents_same"}
    no_trinket = next(r for r in res.results if r.name == "no_trinket2")
    assert no_trinket.delta < 0 and no_trinket.delta_pct < 0
    assert any(e[0] == "profilesets" and e[1] == e[2] == 3 for e in events)
    assert "single_actor_batch=1" in out.input_path.read_text("utf-8")


def test_modified_talent_string_accepted_by_simc(simc, tmp_path):
    """A string produced by ``talents.modify()`` (remove one spec talent, add another legal
    one) must be a loadout SimC itself accepts -- run a real 50-iteration Quick Sim with it."""
    from tests.conftest import FIXTURES
    from toonopt.data import talents, wago

    if not wago.is_ready():
        pytest.skip("DB2 cache not downloaded (POST /api/data/refresh)")
    raw = (FIXTURES / "export_hunter_mm.simc").read_text("utf-8")
    base_profile = profile.parse(raw)
    result = talents.modify("hunter", "marksmanship", base_profile.talents,
                             add=["Tactical Reload"], remove=["Unstable Trigger"])
    assert not result["errors"], result["errors"]
    prof = profile.parse(raw)
    prof.talents = result["string"]
    text = simc_input.build(prof, SimOptions(iterations=50, threads=4))
    out = runner.run(text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0
    low = out.stdout.lower()
    assert "invalid talent" not in low and "illegal" not in low and "unable to parse talent" not in low


@pytest.mark.parametrize("fixture_name", ["export_dk_frost.simc", "export_warrior_arms.simc", "export_mage_frost.simc"])
def test_quick_sim_class_fixtures(simc, tmp_path, fixture_name):
    """Every synthetic class fixture (used across the unit test suite) must carry a
    talent string SimC actually accepts -- a 100-iteration Quick Sim should just work."""
    from tests.conftest import FIXTURES

    prof = profile.parse((FIXTURES / fixture_name).read_text("utf-8"))
    text = simc_input.build(prof, SimOptions(iterations=100, threads=4))
    out = runner.run(text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0


def test_cancel_kills_process(simc, mid2_profile, tmp_path):
    cancel = threading.Event()
    text = simc_input.build(mid2_profile, SimOptions(iterations=20000, threads=2))

    def cb(phase, cur, total, msg):
        if phase == "baseline" and cur > 0:
            cancel.set()

    with pytest.raises(runner.SimcCancelled):
        runner.run(text, tmp_path, 2, cb, cancel)


# ---------------------------------------------------------------------------
# Raidbots parity, wave 2: Catalyst variant, Consumables, Omnium Folio end-to-end.


@pytest.fixture(scope="module")
def dk_frost_profile():
    from tests.conftest import FIXTURES

    return profile.parse((FIXTURES / "export_dk_frost.simc").read_text("utf-8"))


def test_topgear_catalyst_variant_end_to_end(simc, dk_frost_profile, tmp_path):
    """bag:5 (Chosen Bloodslayer's Fanged Grips, id 271511 -- a rogue tier hands piece) is a
    legitimate non-tier Catalyst source for a Death Knight: catalyzing it should redirect to
    the DK's own tier hands item (271475) while carrying redirected_base_stats=271511 into the
    generated .simc input, and SimC must accept and sim it without error."""
    from toonopt.sims import topgear

    plan = topgear.build(
        dk_frost_profile, SimOptions(iterations=200, threads=4), ["bag:5"],
        catalyst=topgear.CatalystRequest(keys=["bag:5"]),
    )
    assert any("(Catalyst)" in lbl for lbl in plan.labels.values())
    catalyst_lines = [ln for ln in plan.simc_text.splitlines() if "redirected_base_stats=271511" in ln]
    assert catalyst_lines, "catalyzed hands line with redirected_base_stats missing from .simc input"
    assert "id=271475" in catalyst_lines[0]           # the DK's own tier hands item id
    out = runner.run(plan.simc_text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0
    assert all(r.dps > 0 for r in res.results)


def test_consumables_flask_potion_end_to_end(simc, real_data_layer, dk_frost_profile, tmp_path):
    from toonopt.sims import consumables

    plan = consumables.build(dk_frost_profile, SimOptions(iterations=200, threads=4),
                              categories=["flask", "potion"])
    assert plan.profilesets
    out = runner.run(plan.simc_text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0
    assert {r.name for r in res.results} == {ps.name for ps in plan.profilesets}
    assert all(r.dps > 0 for r in res.results)
    cats = {plan.meta[r.name].consumable.category for r in res.results}
    assert cats == {"flask", "potion"}


def test_omnium_per_row_end_to_end(simc, real_data_layer, dk_frost_profile, tmp_path):
    from toonopt.sims import omnium

    plan = omnium.build(dk_frost_profile, SimOptions(iterations=200, threads=4), "per_row")
    assert plan.profilesets
    assert any("omnium_talents=" in o for ps in plan.profilesets for o in ps.overrides)
    out = runner.run(plan.simc_text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0
    assert all(r.dps > 0 for r in res.results)
    rows = {plan.meta[r.name].omnium.row for r in res.results}
    # row 3 has only one choice this season (rune_of_lingering) and the fixture's character
    # already has it picked, so per_row correctly offers no alternative for that row.
    assert rows == {1, 2, 4, 5}


@pytest.fixture(scope="module")
def dk_frost_unforged_profile():
    """Like ``dk_frost_profile`` but main_hand is Myth 6/6 (bonus 12854, ilvl 334) instead of
    already Voidforged, so the Upgrades engine's Voidforge step has something to build (see
    ``tests/fixtures/export_dk_frost_unforged.simc``)."""
    from tests.conftest import FIXTURES

    return profile.parse((FIXTURES / "export_dk_frost_unforged.simc").read_text("utf-8"))


def test_upgrades_voidforge_end_to_end(simc, real_data_layer, dk_frost_unforged_profile, tmp_path):
    from toonopt.sims import upgrades

    plan, skipped = upgrades.build(
        dk_frost_unforged_profile, SimOptions(iterations=100, threads=4), slots=["main_hand"],
    )
    assert skipped == 0
    vf_name, vf_meta = next(
        (name, m) for name, m in plan.meta.items() if m.upgrade and m.upgrade.track == "Voidforged"
    )
    assert vf_meta.upgrade.to_ilevel == 344 and vf_meta.upgrade.crest == "Ascendant Voidcore"
    out = runner.run(plan.simc_text, tmp_path, 4, lambda *a: None)
    res = results.parse_file(out.json_path, out.stdout)
    assert res.baseline.dps > 0
    row = next(r for r in res.results if r.name == vf_name)
    assert row.dps > 0
