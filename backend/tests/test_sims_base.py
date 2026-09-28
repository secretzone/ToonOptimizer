"""Tests for toonopt.sims.base: staged precision ("Smart Sim", API.md H5)."""
from __future__ import annotations

import re

from toonopt.models import Baseline, ResultMeta, ResultRow, SimOptions, SimResult
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, precision_stages, run_staged


def test_precision_stages():
    assert precision_stages("low") == [1.0, 0.2]
    assert precision_stages("medium") == [1.0, 0.2, 0.1]
    assert precision_stages("high") == [1.0, 0.2, 0.05]


class StagedFakeCtx:
    """A fake JobContext: returns decreasing dps_error per stage from a canned table and
    records what each ctx.sim() call actually saw, so run_staged's pruning/stage-tracking
    can be exercised without a real runner."""

    def __init__(self, dps_table: dict[str, list[tuple[float, float]]]):
        self.dps_table = dps_table
        self.stage_labels: list[str] = []
        self.seen_names_per_call: list[list[str]] = []
        self.texts: list[str] = []

    def check_cancelled(self) -> None:
        pass

    def sim(self, simc_text, options, *, klass="", spec="", stage_label=""):
        stage_idx = len(self.stage_labels)
        self.stage_labels.append(stage_label)
        self.texts.append(simc_text)
        names = sorted(set(re.findall(r'profileset\."([^"]+)"', simc_text)))
        self.seen_names_per_call.append(names)
        rows = [ResultRow(name=n, label=n, dps=self.dps_table[n][stage_idx][0],
                           dps_error=self.dps_table[n][stage_idx][1]) for n in names]
        res = SimResult(job_id="j", type="topgear", baseline=Baseline(dps=1000.0), metric=options.metric)
        res.results = rows
        return res


def _named_plan(names: list[str]) -> Plan:
    plan = Plan(simc_text="")
    for n in names:
        plan.profilesets.append(Profileset(name=n, label=n, overrides=[f"head=,id={n}"]))
        plan.labels[n] = n
        plan.meta[n] = ResultMeta()
    return plan


def test_run_staged_with_builder_drops_rows_and_tracks_stage():
    full_plan = _named_plan(["a", "b", "c"])

    def build_stage(stage_options: SimOptions, keep: set[str] | None) -> Plan:
        psets = full_plan.profilesets if keep is None else [ps for ps in full_plan.profilesets if ps.name in keep]
        text = "\n".join(f'profileset."{ps.name}"+={ps.overrides[0]}' for ps in psets) + "\n"
        return Plan(text, full_plan.labels, full_plan.meta, psets)

    dps_table = {
        "a": [(1100.0, 50.0), (1105.0, 10.0)],
        "b": [(1080.0, 50.0), (1082.0, 10.0)],
        "c": [(900.0, 50.0)],          # eliminated after stage 1, never simmed again
    }
    ctx = StagedFakeCtx(dps_table)
    res = run_staged(ctx, build_stage, SimOptions(iterations=10), [1.0, 0.2], klass="death_knight", spec="frost")

    assert ctx.stage_labels == [
        "Precision 1/2 (target_error 1.0)",
        "Precision 2/2 (target_error 0.2)",
    ]
    assert ctx.seen_names_per_call[0] == ["a", "b", "c"]
    assert ctx.seen_names_per_call[1] == ["a", "b"]        # c dropped after stage 1

    by_name = {r.name: r for r in res.results}
    assert set(by_name) == {"a", "b", "c"}
    assert by_name["a"].meta.stage == 2 and by_name["a"].dps == 1105.0
    assert by_name["b"].meta.stage == 2 and by_name["b"].dps == 1082.0
    # dropped row keeps its last (stage 1) result and stage number, frozen
    assert by_name["c"].meta.stage == 1 and by_name["c"].dps == 900.0
    assert res.results == sorted(res.results, key=lambda r: r.dps, reverse=True)


def test_run_staged_stops_after_low_stage_list():
    full_plan = _named_plan(["a", "b"])

    def build_stage(stage_options: SimOptions, keep: set[str] | None) -> Plan:
        psets = full_plan.profilesets if keep is None else [ps for ps in full_plan.profilesets if ps.name in keep]
        text = "\n".join(f'profileset."{ps.name}"+={ps.overrides[0]}' for ps in psets) + "\n"
        return Plan(text, full_plan.labels, full_plan.meta, psets)

    dps_table = {"a": [(1000.0, 5.0), (1000.0, 1.0)], "b": [(999.0, 5.0), (999.0, 1.0)]}
    ctx = StagedFakeCtx(dps_table)
    res = run_staged(ctx, build_stage, SimOptions(), precision_stages("low"), klass="x", spec="y")
    assert len(ctx.stage_labels) == 2      # "low" never reaches a 3rd stage
    assert all(r.meta.stage == 2 for r in res.results)


def test_run_staged_with_plain_plan_uses_regex_restage():
    """Handing run_staged a ready Plan (no builder) works via the regex text rewrite."""
    plan = Plan(
        simc_text=(
            "fight_style=Patchwerk\n"
            "target_error=0.3\n"
            "iterations=0\n"
            'profileset."a"+=head=,id=1\n'
            'profileset."b"+=head=,id=2\n'
        ),
        labels={"a": "A", "b": "B"},
        meta={"a": ResultMeta(), "b": ResultMeta()},
        profilesets=[
            Profileset(name="a", label="A", overrides=["head=,id=1"]),
            Profileset(name="b", label="B", overrides=["head=,id=2"]),
        ],
    )
    dps_table = {"a": [(1100.0, 50.0), (1105.0, 10.0)], "b": [(900.0, 50.0)]}
    ctx = StagedFakeCtx(dps_table)
    res = run_staged(ctx, plan, SimOptions(iterations=10), [1.0, 0.2])

    assert "target_error=1.0" in ctx.texts[0] and "iterations=0" in ctx.texts[0]
    assert 'profileset."a"' in ctx.texts[0] and 'profileset."b"' in ctx.texts[0]
    assert "target_error=0.2" in ctx.texts[1]
    assert 'profileset."b"' not in ctx.texts[1]     # b was dropped after stage 1

    by_name = {r.name: r for r in res.results}
    assert by_name["a"].meta.stage == 2
    assert by_name["b"].meta.stage == 1 and by_name["b"].dps == 900.0


def test_apply_meta_sorts_ascending_for_lower_is_better_metric():
    """dtps (and dmg_taken) are "lower is better" -- apply_meta must sort ascending on the
    metric instead of descending on dps."""
    plan = _named_plan(["a", "b", "c"])
    result = SimResult(
        job_id="j", type="topgear", metric="dtps",
        baseline=Baseline(dps=100.0),
        results=[
            ResultRow(name="a", label="a", dps=120.0),
            ResultRow(name="b", label="b", dps=80.0),
            ResultRow(name="c", label="c", dps=100.0),
        ],
    )
    out = apply_meta(result, plan)
    assert [r.name for r in out.results] == ["b", "c", "a"]
    # delta/delta_pct keep results.py's convention: value - baseline, no metric-specific flip
    by_name = {r.name: r for r in out.results}
    assert by_name["a"].delta == 20.0
    assert by_name["b"].delta == -20.0


def test_run_staged_with_dtps_metric_keeps_low_rows():
    """The survivor cutoff and final sort flip for a lower-is-better metric: rows with the
    lowest dtps (not the highest) are the ones that should keep contending."""
    full_plan = _named_plan(["a", "b", "c"])

    def build_stage(stage_options: SimOptions, keep: set[str] | None) -> Plan:
        psets = full_plan.profilesets if keep is None else [ps for ps in full_plan.profilesets if ps.name in keep]
        text = "\n".join(f'profileset."{ps.name}"+={ps.overrides[0]}' for ps in psets) + "\n"
        return Plan(text, full_plan.labels, full_plan.meta, psets)

    dps_table = {
        "a": [(80.0, 5.0), (81.0, 1.0)],   # lowest dtps -> best, survives
        "b": [(82.0, 5.0), (83.0, 1.0)],   # close enough to survive stage 1
        "c": [(200.0, 5.0)],               # much higher dtps -> eliminated after stage 1
    }
    ctx = StagedFakeCtx(dps_table)
    res = run_staged(
        ctx, build_stage, SimOptions(iterations=10, metric="dtps"), [1.0, 0.2],
        klass="death_knight", spec="frost",
    )

    assert ctx.seen_names_per_call[0] == ["a", "b", "c"]
    assert ctx.seen_names_per_call[1] == ["a", "b"]        # c dropped (worst dtps)

    by_name = {r.name: r for r in res.results}
    assert by_name["a"].meta.stage == 2 and by_name["a"].dps == 81.0
    assert by_name["b"].meta.stage == 2 and by_name["b"].dps == 83.0
    assert by_name["c"].meta.stage == 1 and by_name["c"].dps == 200.0
    # ascending on dtps: best (lowest) first
    assert [r.name for r in res.results] == ["a", "b", "c"]
