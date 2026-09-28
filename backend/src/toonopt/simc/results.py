"""Parse SimC ``json2`` output into :class:`SimResult`.

json2 paths used (SimC 1210-01, report_version 2.0.0):

* ``version`` / ``git_revision`` – SimC version.
* ``sim.options.iterations`` and ``sim.statistics.elapsed_time_seconds`` – timing.
* ``sim.players[0].dbc.<version_used>.wow_version`` – WoW version SimC used.
* ``sim.players[0].collected_data.dps.{mean,mean_std_dev,count}`` – baseline.
* ``sim.profilesets.results[].{name,mean,mean_stddev,mean_error,iterations}`` – profileset rows.
* ``sim.players[0].stats[]`` – abilities. ``type=="damage"``, ``portion_aps.mean`` (dps),
  ``portion_amount`` (fraction), ``num_executes.mean``, ``direct_results|tick_results.{hit,crit}.count.mean``
  and ``.crit.pct``.
* ``sim.players[0].stats_pets`` – ``{pet_name: [stat, ...]}`` same shape as ``stats``.
* ``sim.players[0].buffs[].{name,uptime}`` – uptime already in percent.
* ``sim.players[0].scale_factors`` – ``{"Str": w, "Crit": w, ...}``; errors are not in
  json2 so they are parsed from stdout (``Str=71.371073(4.559063)``).
* ``sim.players[0].valid_fight_style`` – bool, straight through to ``SimResult.valid_fight_style``.

Metrics (API.md "Raidbots parity, wave 1" M5) -- verified by running a 3-profileset sim with
``profileset_metric=dps,prioritydps,dtps,hps,dmg_taken`` (always emitted, see simc/input.py)
and inspecting json2:

* ``sim.profilesets.metric`` – display name of whichever metric is FIRST in
  ``profileset_metric`` (always "dps" here, i.e. "Damage per Second") -- this is also what
  ``results[].mean`` / ``mean_error`` / ``mean_stddev`` report.
* ``sim.profilesets.results[].additional_metrics[]`` – one entry per remaining
  ``profileset_metric`` entry, each ``{"metric": <display name>, "mean": ..., ...}``; display
  names: "Damage per Second", "Damage per Second to Priority Target/Boss", "Damage Taken per
  Second", "Healing per Second", "Damage Taken" (see METRIC_DISPLAY below).
* The baseline actor has no profileset row, so its per-metric numbers come from
  ``sim.players[0].collected_data`` instead: ``dps.mean`` (dps) and ``target_metric.mean``
  (prioritydps -- matches the profileset "Damage per Second to Priority Target/Boss" value
  within sampling noise) and ``hps.mean`` (hps) are named as expected, but SimC's own
  ``dtps`` collected-data key is actually the fight-total damage taken (confirmed against a
  tank sim: ``dtps.mean / fight_length.mean`` reproduces the profileset "Damage Taken per
  Second" figure to within ~1%), so it is used for ``dmg_taken`` and divided by fight length
  for ``dtps``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from toonopt.models import (
    Baseline,
    BreakdownRow,
    ResultRow,
    SimResult,
    StatWeights,
    Timing,
    UptimeRow,
)

# SimC scale-factor abbreviations -> our stat names
SCALE_NAMES: dict[str, str] = {
    "Str": "strength", "Agi": "agility", "Int": "intellect", "Sta": "stamina", "Spi": "spirit",
    "Crit": "crit", "Haste": "haste", "Mastery": "mastery", "Vers": "versatility",
    "AP": "attack_power", "SP": "spell_power", "Wdps": "weapon_dps", "WOHdps": "weapon_offhand_dps",
    "Armor": "armor", "BonusArmor": "bonus_armor", "Leech": "leech", "Avoidance": "avoidance",
    "Speed": "speed", "Corruption": "corruption", "CorruptionResistance": "corruption_resistance",
}
# our stat names -> Pawn stat names
PAWN_NAMES: dict[str, str] = {
    "strength": "Strength", "agility": "Agility", "intellect": "Intellect", "stamina": "Stamina",
    "crit": "CritRating", "haste": "HasteRating", "mastery": "MasteryRating", "versatility": "Versatility",
    "weapon_dps": "Dps", "armor": "Armor", "leech": "Leech", "avoidance": "Avoidance", "speed": "MovementSpeed",
}
PAWN_CLASS: dict[str, str] = {
    "death_knight": "DeathKnight", "demon_hunter": "DemonHunter", "druid": "Druid", "evoker": "Evoker",
    "hunter": "Hunter", "mage": "Mage", "monk": "Monk", "paladin": "Paladin", "priest": "Priest",
    "rogue": "Rogue", "shaman": "Shaman", "warlock": "Warlock", "warrior": "Warrior",
}

_SF_LINE_RE = re.compile(r"(\w+)=(-?[\d.]+)\((-?[\d.]+)\)")

# our metric key -> SimC's json2 display name (sim.profilesets.metric / additional_metrics[].metric)
METRIC_DISPLAY: dict[str, str] = {
    "dps": "Damage per Second",
    "prioritydps": "Damage per Second to Priority Target/Boss",
    "dtps": "Damage Taken per Second",
    "hps": "Healing per Second",
    "dmg_taken": "Damage Taken",
}
_DISPLAY_METRIC: dict[str, str] = {v: k for k, v in METRIC_DISPLAY.items()}
# metrics where a lower value is the better outcome (tanking/damage-taken figures)
LOWER_IS_BETTER: frozenset[str] = frozenset({"dtps", "dmg_taken"})


def load(json_path: Path) -> dict:
    with json_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _mean(obj, key: str = "mean") -> float:
    if isinstance(obj, dict):
        v = obj.get(key)
        return float(v) if v is not None else 0.0
    if isinstance(obj, (int, float)):
        return float(obj)
    return 0.0


def _result_counts(res: dict | None) -> tuple[float, float, float]:
    """(hits, crits, crit_pct) from a direct_results / tick_results block."""
    if not res:
        return 0.0, 0.0, 0.0
    hit = sum(_mean(v.get("count")) for k, v in res.items() if isinstance(v, dict) and k not in ("crit", "crit_block", "crit_glance"))
    crit = sum(_mean(v.get("count")) for k, v in res.items() if isinstance(v, dict) and k.startswith("crit"))
    crit_pct = sum(float(v.get("pct", 0.0)) for k, v in res.items() if isinstance(v, dict) and k.startswith("crit"))
    return hit, crit, crit_pct


def _stat_rows(stats: list[dict], kind: str | None, prefix: str = "") -> list[BreakdownRow]:
    rows: list[BreakdownRow] = []
    for s in stats or []:
        if s.get("type") != "damage":
            continue
        dps = _mean(s.get("portion_aps"))
        if dps <= 0:
            continue
        periodic = "tick_results" in s and "direct_results" not in s
        res = s.get("direct_results") or s.get("tick_results")
        hit, crit, crit_pct = _result_counts(res)
        rows.append(BreakdownRow(
            name=prefix + (s.get("spell_name") or s.get("name") or "?"),
            id=int(s.get("id") or 0),
            type=kind or ("periodic" if periodic else "direct"),
            total=dps,
            pct=float(s.get("portion_amount") or 0.0) * 100.0,
            count=_mean(s.get("num_executes")),
            hit=hit, crit=crit, crit_pct=crit_pct,
        ))
    return rows


def breakdown(player: dict) -> list[BreakdownRow]:
    rows = _stat_rows(player.get("stats") or [], None)
    pets = player.get("stats_pets") or {}
    if isinstance(pets, dict):
        for pet, stats in pets.items():
            rows.extend(_stat_rows(stats, "pet", f"{pet}: "))
    elif isinstance(pets, list):
        for entry in pets:
            rows.extend(_stat_rows(entry.get("stats", []), "pet", f"{entry.get('name', 'pet')}: "))
    rows.sort(key=lambda r: r.total, reverse=True)
    return rows


def uptimes(player: dict, min_pct: float = 0.5) -> list[UptimeRow]:
    out = []
    for b in player.get("buffs") or []:
        up = float(b.get("uptime") or 0.0)
        if up >= min_pct:
            out.append(UptimeRow(name=b.get("spell_name") or b.get("name") or "?", pct=up))
    out.sort(key=lambda r: r.pct, reverse=True)
    return out


def scale_factor_errors(stdout: str) -> dict[str, float]:
    """Parse ``Str=71.37(4.56) Crit=...`` from the text report's Scale Factors block."""
    errors: dict[str, float] = {}
    block = stdout.split("Scale Factors:")[-1] if "Scale Factors:" in stdout else ""
    for m in _SF_LINE_RE.finditer(block):
        name = SCALE_NAMES.get(m.group(1), m.group(1).lower())
        errors[name] = float(m.group(3))
    return errors


def pawn_string(name: str, klass: str, spec: str, normalized: dict[str, float]) -> str:
    parts = [f"Class={PAWN_CLASS.get(klass, klass.title().replace('_', ''))}", f"Spec={spec.title().replace('_', '')}"]
    for stat, w in normalized.items():
        pawn = PAWN_NAMES.get(stat)
        if pawn and w != 0:
            parts.append(f"{pawn}={w:.2f}")
    return f'( Pawn: v1: "{name}": ' + ", ".join(parts) + " )"


def stat_weights(player: dict, stdout: str, klass: str, spec: str, label: str) -> StatWeights | None:
    raw = player.get("scale_factors")
    if not isinstance(raw, dict) or not raw:
        return None
    weights = {SCALE_NAMES.get(k, k.lower()): float(v) for k, v in raw.items()}
    weights = {k: v for k, v in weights.items() if v != 0.0 or k in ("crit", "haste", "mastery", "versatility")}
    if not weights:
        return None
    primary = next((s for s in ("strength", "agility", "intellect") if weights.get(s)), None)
    base = weights[primary] if primary else max(abs(v) for v in weights.values()) or 1.0
    normalized = {k: (v / base if base else 0.0) for k, v in weights.items()}
    errors = scale_factor_errors(stdout)
    return StatWeights(
        weights=weights, normalized=normalized,
        pawn=pawn_string(label, klass, spec, normalized),
        error={k: errors[k] for k in weights if k in errors},
    )


_CLASS_WORDS = ("Death Knight", "Demon Hunter", "Druid", "Evoker", "Hunter", "Mage", "Monk", "Paladin",
                "Priest", "Rogue", "Shaman", "Warlock", "Warrior")


def split_specialization(spec_name: str) -> tuple[str, str]:
    """"Beast Mastery Hunter" -> ("beast_mastery", "hunter")."""
    for cls in _CLASS_WORDS:
        if spec_name.endswith(cls):
            spec = spec_name[: -len(cls)].strip()
            return spec.lower().replace(" ", "_"), cls.lower().replace(" ", "_")
    return "", ""


def wow_version(player: dict) -> str:
    dbc = player.get("dbc") or {}
    used = dbc.get("version_used") or "Live"
    return str((dbc.get(used) or {}).get("wow_version") or "")


def _row_metrics(r: dict) -> dict[str, float]:
    """Every metric SimC reported for one profileset row: ``mean`` is whichever metric is
    first in ``profileset_metric`` (always "dps", see simc/input.py), the rest come from
    ``additional_metrics``."""
    metrics: dict[str, float] = {"dps": float(r.get("mean") or 0.0)}
    for am in r.get("additional_metrics") or []:
        key = _DISPLAY_METRIC.get(am.get("metric"))
        if key:
            metrics[key] = float(am.get("mean") or 0.0)
    return metrics


def profileset_rows(sim: dict, baseline_dps: float, metric: str = "dps") -> list[ResultRow]:
    rows: list[ResultRow] = []
    for r in (sim.get("profilesets") or {}).get("results") or []:
        metrics = _row_metrics(r)
        value = metrics.get(metric, metrics.get("dps", 0.0))
        delta = value - baseline_dps
        # mean_error is SimC's own 95%-confidence error estimate for a profileset (what
        # Raidbots shows); mean_stddev is a 1-sigma figure and understates it by ~2x, so only
        # fall back to it when SimC didn't report mean_error. That error is only reported for
        # the *first* (mean) metric; non-dps metrics inherit it as an approximation.
        rows.append(ResultRow(
            name=str(r.get("name")), label=str(r.get("name")), dps=value,
            dps_error=float(r.get("mean_error") or r.get("mean_stddev") or 0.0),
            delta=delta, delta_pct=(delta / baseline_dps * 100.0) if baseline_dps else 0.0,
            metrics=metrics,
        ))
    rows.sort(key=lambda r: r.dps, reverse=metric not in LOWER_IS_BETTER)
    return rows


def baseline_metrics(player: dict) -> dict[str, float]:
    """Per-metric baseline numbers built from ``collected_data`` -- see the module docstring
    for the ``dtps``-is-actually-a-total caveat this works around."""
    cd = player.get("collected_data") or {}
    fight_length = _mean(cd.get("fight_length")) or 0.0
    dps = _mean(cd.get("dps"))
    dmg_taken = _mean(cd.get("dmg_taken")) or _mean(cd.get("dtps"))
    return {
        "dps": dps,
        "prioritydps": _mean(cd.get("target_metric")) or dps,
        "hps": _mean(cd.get("hps")),
        "dmg_taken": dmg_taken,
        "dtps": (dmg_taken / fight_length) if fight_length else 0.0,
    }


# collected_data key backing each metric's 95%-confidence error (see baseline_metrics); "dtps"
# is derived (dmg_taken / fight_length) so it has no clean error figure of its own.
_METRIC_ERROR_KEY: dict[str, str] = {"dps": "dps", "hps": "hps", "prioritydps": "target_metric", "dmg_taken": "dtps"}


def _metric_error_95(cd: dict, metric: str) -> float:
    key = _METRIC_ERROR_KEY.get(metric)
    stat = cd.get(key) if key else None
    return 1.96 * _mean(stat, "mean_std_dev") if isinstance(stat, dict) else 0.0


def parse(data: dict, stdout: str = "", *, klass: str = "", spec: str = "", metric: str = "dps") -> SimResult:
    """Build a SimResult (job/type/options are filled in by the caller)."""
    sim = data.get("sim") or {}
    players = sim.get("players") or []
    player = players[0] if players else {}
    cd = player.get("collected_data") or {}
    dps = cd.get("dps") or {}
    bmetrics = baseline_metrics(player)
    baseline_value = bmetrics.get(metric, bmetrics.get("dps", 0.0))
    name = str(player.get("name") or "player")
    guess_spec, guess_klass = split_specialization(str(player.get("specialization") or ""))
    spec = spec or guess_spec
    klass = klass or guess_klass
    opts = sim.get("options") or {}
    stats = sim.get("statistics") or {}
    iterations = int(opts.get("iterations") or dps.get("count") or 0)
    valid_fight_style = player.get("valid_fight_style")
    return SimResult(
        job_id="", type="quick", character=name, spec=spec, klass=klass,
        simc_version=f"{data.get('version', '')} ({data.get('git_revision', '')})".strip(),
        wow_version=wow_version(player),
        # The baseline actor has no profileset "mean_error"; collected_data only gives the
        # 1-sigma mean_std_dev, so scale it to the same 95%-confidence band SimC/Raidbots use
        # for everything else (dps_error on profileset rows, scale-factor errors, ...).
        baseline=Baseline(
            name=name, label="Current gear", dps=baseline_value,
            dps_error=_metric_error_95(cd, metric), metrics=bmetrics,
        ),
        results=profileset_rows(sim, baseline_value, metric),
        breakdown=breakdown(player),
        uptimes=uptimes(player),
        stat_weights=stat_weights(player, stdout, klass, spec, f"ToonOptimizer: {name}"),
        timing=Timing(seconds=float(stats.get("elapsed_time_seconds") or 0.0), iterations=iterations),
        metric=metric,
        valid_fight_style=bool(valid_fight_style) if valid_fight_style is not None else None,
    )


def parse_file(json_path: Path, stdout: str = "", **kw) -> SimResult:
    return parse(load(json_path), stdout, **kw)
