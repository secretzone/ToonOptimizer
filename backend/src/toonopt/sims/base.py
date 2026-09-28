"""Shared plumbing for the sim engines.

Every engine exposes ``build(...) -> Plan`` (the ``.simc`` text plus label/meta maps
keyed by profileset name) and ``execute(ctx, ...) -> SimResult`` that runs the plan
through a :class:`toonopt.jobs.JobContext` and post-processes the rows.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from toonopt.models import (
    CharacterProfile,
    Item,
    ResultMeta,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.simc.input import Profileset, ProfilesetNames
from toonopt.simc.results import LOWER_IS_BETTER

PRIMARY_STAT: dict[str, str] = {
    "death_knight": "strength", "paladin": "strength", "warrior": "strength",
    "demon_hunter": "agility", "hunter": "agility", "rogue": "agility", "monk": "agility",
    "druid": "agility", "shaman": "agility", "evoker": "intellect",
    "mage": "intellect", "priest": "intellect", "warlock": "intellect",
}
INT_SPECS = {("druid", "balance"), ("druid", "restoration"), ("shaman", "elemental"), ("shaman", "restoration"),
             ("monk", "mistweaver"), ("paladin", "holy")}
TWO_HAND_TYPES = {15, 17, 25, 26}        # bow, 2H, thrown, gun/crossbow/wand
OFF_HAND_TYPES = {14, 22, 23}            # shield, off-hand weapon, held in off-hand
ONE_HAND_TYPES = {13, 21}                # one-hand, main-hand only
DUAL_WIELD_SPECS = {("rogue", "assassination"), ("rogue", "outlaw"), ("rogue", "subtlety"),
                    ("death_knight", "frost"), ("warrior", "fury"), ("shaman", "enhancement"),
                    ("monk", "windwalker"), ("monk", "brewmaster"), ("demon_hunter", "havoc"),
                    ("demon_hunter", "vengeance"), ("demon_hunter", "devourer"), ("hunter", "survival")}


def primary_stat(profile: CharacterProfile) -> str:
    if (profile.klass, profile.spec) in INT_SPECS:
        return "intellect"
    return PRIMARY_STAT.get(profile.klass, "agility")


def is_two_hand(item: Item, profile: CharacterProfile) -> bool:
    if item.inventory_type:
        return item.inventory_type in TWO_HAND_TYPES
    # no data layer: mirror the currently equipped weapon setup
    return "off_hand" not in profile.equipped


def is_off_hand_only(item: Item) -> bool:
    return item.inventory_type in OFF_HAND_TYPES if item.inventory_type else item.slot == "off_hand"


def can_dual_wield(profile: CharacterProfile) -> bool:
    return (profile.klass, profile.spec) in DUAL_WIELD_SPECS


def item_label(item: Item) -> str:
    return f"{item.name or item.id}" + (f" ({item.ilevel})" if item.ilevel else "")


@dataclass
class Plan:
    simc_text: str
    labels: dict[str, str] = field(default_factory=dict)
    meta: dict[str, ResultMeta] = field(default_factory=dict)
    profilesets: list[Profileset] = field(default_factory=list)
    # profileset name -> predicted (dps / baseline_dps). Only Top Gear "smart" mode fills
    # this in; execute() rescales it into ResultMeta.predicted_dps once the real baseline
    # dps from the same sim run is known.
    predicted_norm: dict[str, float] = field(default_factory=dict)
    # human sentences describing non-fatal skips (e.g. slots with no remaining upgrade, items
    # without sockets); engines that populate this have execute() copy it onto SimResult.notes.
    notes: list[str] = field(default_factory=list)


def new_names() -> ProfilesetNames:
    return ProfilesetNames()


def _metric_value(row: ResultRow, metric: str) -> float:
    """``row.metrics[metric]``, falling back to ``row.dps`` when the row has no per-metric
    breakdown (e.g. rows built directly in tests, or a stage's SimResult.metric not being
    "dps")."""
    return row.metrics.get(metric, row.dps)


def apply_meta(result: SimResult, plan: Plan) -> SimResult:
    """Relabel rows, attach meta and recompute deltas against the baseline."""
    base = result.baseline.dps
    lower_is_better = result.metric in LOWER_IS_BETTER
    rows: list[ResultRow] = []
    for row in result.results:
        row.label = plan.labels.get(row.name, row.label)
        row.meta = plan.meta.get(row.name, row.meta)
        row.delta = row.dps - base
        row.delta_pct = (row.delta / base * 100.0) if base else 0.0
        rows.append(row)
    rows.sort(key=lambda r: _metric_value(r, result.metric), reverse=not lower_is_better)
    result.results = rows
    return result


def apply_season(item: Item, slot: str, options: SimOptions, profile: CharacterProfile) -> Item:
    """Apply ``enchant_all`` / ``socket_all`` using the season data layer when present.

    Expects ``toonopt.data.season.best_enchant(slot, profile) -> int | None`` and
    ``toonopt.data.season.best_gems(item, profile) -> list[int]`` (gem ids for every
    socket the item has, [] when none). Missing data layer -> item returned unchanged.
    """
    if not (options.enchant_all or options.socket_all):
        return item
    try:
        from toonopt.data import season  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - data layer optional
        return item
    update: dict[str, object] = {}
    if options.enchant_all and hasattr(season, "best_enchant"):
        try:
            ench = season.best_enchant(slot, profile)
        except Exception:  # noqa: BLE001
            ench = None
        if ench:
            update["enchant_id"] = int(ench)
    if options.socket_all and hasattr(season, "best_gems"):
        try:
            gems = list(season.best_gems(item, profile))
        except Exception:  # noqa: BLE001
            gems = []
        if gems:
            update["gem_ids"] = [int(g) for g in gems]
    return item.model_copy(update=update) if update else item


# --------------------------------------------------------------------------------------
# Staged precision ("Smart Sim", API.md "Raidbots parity, wave 1" H5)
# --------------------------------------------------------------------------------------

PrecisionStageBuilder = Callable[[SimOptions, set[str] | None], Plan]


def precision_stages(precision: Literal["low", "medium", "high"]) -> list[float]:
    """``target_error`` sequence for :func:`run_staged` from a ``SimOptions.precision`` value.

    ``low`` -> ``[1.0, 0.2]``; ``medium`` -> ``[1.0, 0.2, 0.1]``; ``high`` -> ``[1.0, 0.2, 0.05]``.
    """
    stages = [1.0, 0.2]
    if precision == "medium":
        stages.append(0.1)
    elif precision == "high":
        stages.append(0.05)
    return stages


_PSET_LINE = re.compile(r'^profileset\."([^"]+)"\+=')


def _restage_text(simc_text: str, target_error: float, keep: set[str] | None) -> str:
    """Rewrite a ready ``.simc`` text for a new precision stage in place: force
    ``target_error=<target_error>``/``iterations=0`` and, when *keep* is given, drop every
    ``profileset."name"+=...`` line whose name isn't in it. Used by :func:`run_staged` when
    it is handed a plain :class:`Plan` instead of a builder callable.
    """
    lines = simc_text.splitlines()
    out: list[str] = []
    saw_target_error = False
    for ln in lines:
        m = _PSET_LINE.match(ln)
        if m:
            if keep is not None and m.group(1) not in keep:
                continue
            out.append(ln)
            continue
        if ln.startswith("iterations="):
            out.append("iterations=0")
            continue
        if ln.startswith("target_error="):
            out.append(f"target_error={target_error}")
            saw_target_error = True
            continue
        out.append(ln)
    if not saw_target_error:
        for i, ln in enumerate(out):
            if ln == "iterations=0":
                out.insert(i, f"target_error={target_error}")
                break
    return "\n".join(out).rstrip("\n") + "\n"


def run_staged(
    ctx,
    plan_builder_or_plan: Plan | PrecisionStageBuilder,
    options: SimOptions,
    stages: list[float],
    *,
    klass: str = "",
    spec: str = "",
) -> SimResult:
    """Staged-precision ("Smart Sim") runner for any profileset plan.

    Runs the same profilesets through progressively tighter ``target_error`` values
    (``stages``, typically :func:`precision_stages` from ``options.precision``), dropping
    rows that can no longer contend for the top spot after each stage so later, pricier
    stages only re-sim survivors. A row survives stage *n* when
    ``row.dps + row.dps_error >= max(r.dps - r.dps_error for r in that stage's rows)``. When
    ``SimResult.metric`` is one of ``results.LOWER_IS_BETTER`` (``dtps``/``dmg_taken``, lower is
    better), both this rule and the final sort flip: a row survives when
    ``metric - error <= min(metric + error for r in that stage's rows)``, and results sort
    ascending on the metric instead of descending. ``metric`` values come from
    ``row.metrics[metric]``, falling back to ``row.dps`` when the row has no per-metric
    breakdown. Baselines are re-run at every stage (harmless: they're needed for ``delta`` anyway).

    Every row keeps a ``meta.stage`` = the highest stage it actually ran at. Rows dropped
    at stage *n* are NOT re-simmed afterwards -- they keep stage *n*'s dps/dps_error/label
    frozen, so the caller (and the UI) can show them greyed out next to rows that made it
    all the way to the last stage.

    ``plan_builder_or_plan`` is either:

    * a callable ``(stage_options, keep) -> Plan`` -- called with ``keep=None`` for stage 1
      (build every profileset) and ``keep={surviving profileset names}`` for every later
      stage, so it can hand back a smaller Plan and skip re-running dropped rows. This is
      the form Top Gear uses (see ``sims/topgear.py: _execute_precision``), and the one a
      caller with a big candidate list (e.g. Droptimizer) should prefer::

          full_plan = build(profile, options, items)   # stable names/labels/meta

          def build_stage(stage_options, keep):
              psets = full_plan.profilesets if keep is None else [
                  ps for ps in full_plan.profilesets if ps.name in keep
              ]
              return Plan(simc_input.build(profile, stage_options, psets),
                          full_plan.labels, full_plan.meta, psets)

          res = run_staged(ctx, build_stage, options, precision_stages(options.precision),
                            klass=profile.klass, spec=profile.spec)

    * a plain, already-built :class:`Plan` -- ``run_staged`` rewrites its ``simc_text`` for
      each stage itself (new ``target_error``/``iterations`` lines, profileset lines pruned
      to survivors) via a small regex pass (:func:`_restage_text`). Less code for a caller
      that doesn't want to write a builder::

          plan = build(profile, options, items)
          res = run_staged(ctx, plan, options, precision_stages(options.precision),
                            klass=profile.klass, spec=profile.spec)

    Returns the final stage's :class:`SimResult`, with every row from every stage present
    (dropped rows reinserted from their last stage), sorted on ``result.metric`` like any
    other result (see :func:`apply_meta`).
    """
    if callable(plan_builder_or_plan):
        builder: PrecisionStageBuilder = plan_builder_or_plan
    else:
        base_plan = plan_builder_or_plan

        def _from_plan(stage_options: SimOptions, keep: set[str] | None) -> Plan:
            text = _restage_text(base_plan.simc_text, stage_options.target_error or 0.1, keep)
            psets = base_plan.profilesets if keep is None else [
                ps for ps in base_plan.profilesets if ps.name in keep
            ]
            return Plan(text, base_plan.labels, base_plan.meta, psets, base_plan.predicted_norm, base_plan.notes)

        builder = _from_plan

    kept_rows: dict[str, ResultRow] = {}
    result: SimResult | None = None
    keep: set[str] | None = None
    for stage_num, target_error in enumerate(stages, start=1):
        stage_options = options.model_copy(update={"target_error": target_error, "iterations": 0})
        plan = builder(stage_options, keep)
        res = ctx.sim(
            plan.simc_text, stage_options, klass=klass, spec=spec,
            stage_label=f"Precision {stage_num}/{len(stages)} (target_error {target_error})",
        )
        res = apply_meta(res, plan)
        ctx.check_cancelled()
        for row in res.results:
            row.meta.stage = stage_num
            kept_rows[row.name] = row
        result = res
        if not res.results:
            break
        stage_lower_is_better = res.metric in LOWER_IS_BETTER
        if stage_lower_is_better:
            cutoff = min(_metric_value(r, res.metric) + r.dps_error for r in res.results)
            keep = {r.name for r in res.results if _metric_value(r, res.metric) - r.dps_error <= cutoff}
        else:
            cutoff = max(_metric_value(r, res.metric) - r.dps_error for r in res.results)
            keep = {r.name for r in res.results if _metric_value(r, res.metric) + r.dps_error >= cutoff}
        if stage_num == len(stages):
            break

    result = result if result is not None else SimResult(job_id="", type="topgear")
    present = {r.name for r in result.results}
    missing = [row for name, row in kept_rows.items() if name not in present]
    if missing:
        result_lower_is_better = result.metric in LOWER_IS_BETTER
        result.results = sorted(
            [*result.results, *missing],
            key=lambda r: _metric_value(r, result.metric),
            reverse=not result_lower_is_better,
        )
    return result
