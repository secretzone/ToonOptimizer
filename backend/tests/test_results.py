from __future__ import annotations

import pytest

from tests.conftest import FIXTURES, load_fixture_json
from toonopt.simc import results, runner


def test_profilesets_parse():
    stdout = (FIXTURES / "json2_profilesets_stdout.txt").read_text("utf-8", "replace")
    r = results.parse(load_fixture_json("json2_profilesets.json"), stdout)
    assert r.character == "MID2_Death_Knight_Frost" and (r.klass, r.spec) == ("death_knight", "frost")
    assert r.simc_version.startswith("1210-01") and r.wow_version == "12.1.0.69875"
    # dps_error is a 95%-confidence band: 1.96 * the baseline's 1-sigma mean_std_dev (245.78),
    # and SimC's own mean_error for profileset rows (already ~1.96 * their mean_stddev).
    assert round(r.baseline.dps) == 249795 and 450 < r.baseline.dps_error < 500
    assert [x.name for x in r.results] == ["talent_b", "ring_swap", "no_trinket2"]      # sorted desc
    worst = r.results[-1]
    assert worst.delta < 0 and round(worst.delta_pct, 2) == -9.34 and round(worst.dps_error) == 442
    assert r.timing.iterations == 1007 and r.timing.seconds > 0
    assert r.breakdown[0].name == "Howling Blast" and r.breakdown[0].type == "direct"
    assert 0 < r.breakdown[0].crit_pct < 100 and r.breakdown[0].hit > 0 and r.breakdown[0].count > 0
    assert any(b.type == "periodic" for b in r.breakdown)
    assert r.uptimes[0].pct >= 80.0 and all(u.pct >= 0.5 for u in r.uptimes) and r.uptimes == sorted(r.uptimes, key=lambda u: -u.pct)
    assert r.stat_weights is None


def test_scale_factors_and_pawn():
    stdout = (FIXTURES / "json2_scalefactors_stdout.txt").read_text("utf-8", "replace")
    r = results.parse(load_fixture_json("json2_scalefactors.json"), stdout)
    sw = r.stat_weights
    assert sw is not None
    assert set(sw.weights) == {"strength", "crit", "haste", "mastery", "versatility"}
    assert sw.normalized["strength"] == 1.0 and 0.9 < sw.normalized["crit"] < 1.0
    assert round(sw.error["strength"], 3) == 4.559 and round(sw.error["versatility"], 3) == 4.419
    assert sw.pawn.startswith('( Pawn: v1: "ToonOptimizer: MID2_Death_Knight_Frost": Class=DeathKnight, Spec=Frost, Strength=1.00, CritRating=0.93')
    assert sw.pawn.endswith(" )")


def test_pet_breakdown():
    r = results.parse(load_fixture_json("json2_pets.json"))
    assert (r.klass, r.spec) == ("warlock", "demonology")
    pets = [b for b in r.breakdown if b.type == "pet"]
    assert pets and pets[0].name.split(":")[0] in ("felguard", "grimoire_imp_lord", "demonic_tyrant", "wild_imp")
    assert r.timing.iterations == 119


def test_metrics_and_valid_fight_style():
    """From a real 3-profileset SimC run with profileset_metric=dps,prioritydps,dtps,hps,dmg_taken
    (tests/fixtures/json2_metrics.json, generated against the real weekly binary -- see also
    the module docstring for the exact json2 paths)."""
    r = results.parse(load_fixture_json("json2_metrics.json"))
    assert r.valid_fight_style is True
    assert r.metric == "dps"
    assert set(r.baseline.metrics) == {"dps", "prioritydps", "dtps", "hps", "dmg_taken"}
    assert r.baseline.metrics["dps"] == r.baseline.dps
    # this run never populated a separate target_metric (single-target, no adds) -- prioritydps
    # falls back to dps rather than silently going to 0.
    assert r.baseline.metrics["prioritydps"] == r.baseline.metrics["dps"]
    assert r.baseline.metrics["dtps"] == 0.0 and r.baseline.metrics["hps"] == 0.0
    names = [row.name for row in r.results]
    assert set(names) == {"talent_b", "ring_swap", "no_trinket2"}
    for row in r.results:
        assert set(row.metrics) == {"dps", "prioritydps", "dtps", "hps", "dmg_taken"}
        assert row.metrics["dps"] == row.dps                      # default metric="dps": dps field IS the metric
        assert row.metrics["prioritydps"] == pytest.approx(row.dps, rel=0.05)
    # sorted desc by dps (default metric)
    assert [row.dps for row in r.results] == sorted((row.dps for row in r.results), reverse=True)


def test_metric_selection_changes_row_value_and_sort_direction():
    data = load_fixture_json("json2_metrics.json")
    r_dps = results.parse(data, metric="dps")
    assert r_dps.metric == "dps"
    r_dmg_taken = results.parse(data, metric="dmg_taken")
    assert r_dmg_taken.metric == "dmg_taken"
    # dmg_taken is 0 for every row in this fixture (a DPS run) -- but the metric selection still
    # switches which key row.dps mirrors and how the baseline value is computed.
    for row in r_dmg_taken.results:
        assert row.dps == row.metrics["dmg_taken"] == 0.0
    assert r_dmg_taken.baseline.dps == r_dmg_taken.baseline.metrics["dmg_taken"]


def test_profileset_rows_sorts_lower_is_better_for_dtps():
    sim = {
        "profilesets": {
            "metric": "Damage Taken per Second",
            "results": [
                {"name": "a", "mean": 100.0, "additional_metrics": []},
                {"name": "b", "mean": 50.0, "additional_metrics": []},
                {"name": "c", "mean": 200.0, "additional_metrics": []},
            ],
        }
    }
    rows = results.profileset_rows(sim, baseline_dps=0.0, metric="dps")
    assert [r.name for r in rows] == ["c", "a", "b"]      # dps: higher is better
    rows = results.profileset_rows(sim, baseline_dps=0.0, metric="dtps")
    assert [r.name for r in rows] == ["b", "a", "c"]      # dtps: lower is better


def test_split_specialization():
    assert results.split_specialization("Beast Mastery Hunter") == ("beast_mastery", "hunter")
    assert results.split_specialization("Havoc Demon Hunter") == ("havoc", "demon_hunter")
    assert results.split_specialization("Frost Death Knight") == ("frost", "death_knight")


def test_progress_parsing():
    raw = (FIXTURES / "json2_profilesets_stdout.txt").read_bytes().decode()
    segs = [s for s in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") if s.strip()]
    seen = [runner.parse_progress(s) for s in segs]
    seen = [s for s in seen if s]
    assert seen[0] == ("init", 0, 0)
    assert ("baseline", 286, 1000) in seen and ("baseline", 1000, 1000) in seen
    assert ("profilesets", 2, 3) in seen and ("profilesets", 3, 3) in seen
    assert seen[-1] == ("reports", 1, 1)
    assert runner.parse_progress("Generating Baseline: 1/1 [===================>] 111/111 88.359 Mean=233027 Error=0.479% 157msec") == ("baseline", 111, 111)
    assert runner.parse_progress("DPS Ranking:") is None


def test_prepare_input_adds_runner_options():
    text = runner.prepare_input('mage="x"\nprofileset."a"+=head=,id=1\n', 6)
    assert "threads=6" in text and "profileset_work_threads=" in text and "single_actor_batch=1" in text
    text2 = runner.prepare_input("threads=2\nmage=\"x\"\n", 6)
    assert text2.count("threads=") == 1 and "profileset_work_threads" not in text2
