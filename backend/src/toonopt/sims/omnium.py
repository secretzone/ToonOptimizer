"""Omnium Folio: one profileset per row choice (``per_row``), the full row cross product
(``combos``), or named entry-id sets (``custom``), against the season's 5-row Omnium Folio
(``toonopt.data.season.omnium_rows()``).

The character's current picks come from ``CharacterProfile.omnium`` (parsed from the export's
``omnium_talents=<entry_id>:<rank>/...`` line by ``toonopt.simc.profile``); a row with no
current pick at all falls back to its first listed choice when it isn't the row under test.
"""
from __future__ import annotations

import itertools

from pydantic import BaseModel, Field

from toonopt.models import (
    CharacterProfile,
    OmniumChange,
    ResultMeta,
    SimOptions,
    SimResult,
)
from toonopt.simc import input as simc_input
from toonopt.simc.input import Profileset
from toonopt.sims.base import Plan, apply_meta, new_names

MAX_ROWS = 100
MODES = ("per_row", "combos", "custom")


class OmniumSet(BaseModel):
    name: str
    entries: list[int] = Field(default_factory=list)


class DataUnavailable(RuntimeError):
    pass


class TooManyRows(ValueError):
    pass


def available() -> bool:
    try:
        from toonopt.data.season import omnium_rows  # noqa: F401
    except Exception:  # noqa: BLE001 - data layer optional
        return False
    return True


def _rows() -> list[dict]:
    try:
        from toonopt.data.season import omnium_rows
    except Exception as e:
        raise DataUnavailable(f"season data layer unavailable: {e}") from e
    return omnium_rows()


def _current_choice(row: dict, current: dict[int, int]) -> dict | None:
    return next((c for c in row["choices"] if current.get(c["entry_id"])), None)


def _fallback_entry(row: dict, current: dict[int, int]) -> int:
    cur = _current_choice(row, current)
    return cur["entry_id"] if cur else row["choices"][0]["entry_id"]


def _talents_line(entries: list[int]) -> str:
    return "omnium_talents=" + "/".join(f"{e}:1" for e in entries)


def _validate_one_per_row(entries: list[int], rows: list[dict]) -> None:
    row_of: dict[int, int] = {c["entry_id"]: row["row"] for row in rows for c in row["choices"]}
    seen: set[int] = set()
    for e in entries:
        r = row_of.get(e)
        if r is None:
            continue
        if r in seen:
            raise ValueError(f"omnium: more than one choice picked for row {r}")
        seen.add(r)


def build(
    profile: CharacterProfile, options: SimOptions, mode: str, sets: list[OmniumSet] | None = None,
) -> Plan:
    if mode not in MODES:
        raise ValueError(f"invalid omnium mode: {mode!r}")
    rows = _rows()
    current = dict(profile.omnium or {})
    names = new_names()
    plan = Plan(simc_text="")
    i = 0

    if mode == "per_row":
        for row in rows:
            cur_choice = _current_choice(row, current)
            for choice in row["choices"]:
                if cur_choice and choice["entry_id"] == cur_choice["entry_id"]:
                    continue
                i += 1
                entries = [
                    choice["entry_id"] if r["row"] == row["row"] else _fallback_entry(r, current)
                    for r in rows
                ]
                label = f"Row {row['row']}: {choice['name']}"
                name = names.make(label, hint=f"o{i}")
                plan.profilesets.append(Profileset(name=name, label=label, overrides=[_talents_line(entries)]))
                plan.labels[name] = label
                plan.meta[name] = ResultMeta(
                    omnium=OmniumChange(row=row["row"], entry_id=choice["entry_id"], name=choice["name"])
                )
    elif mode == "combos":
        for combo in itertools.product(*(row["choices"] for row in rows)):
            entries = [c["entry_id"] for c in combo]
            if all(current.get(e) for e in entries):
                continue    # identical to the character's current picks
            i += 1
            label = " / ".join(f"R{row['row']}: {c['name']}" for row, c in zip(rows, combo, strict=True))
            name = names.make(label, hint=f"o{i}")
            plan.profilesets.append(Profileset(name=name, label=label, overrides=[_talents_line(entries)]))
            plan.labels[name] = label
            plan.meta[name] = ResultMeta(loadout=label)
    else:  # custom
        for s in sets or []:
            _validate_one_per_row(s.entries, rows)
            i += 1
            name = names.make(s.name, hint=f"o{i}")
            plan.profilesets.append(Profileset(name=name, label=s.name, overrides=[_talents_line(s.entries)]))
            plan.labels[name] = s.name
            plan.meta[name] = ResultMeta(loadout=s.name)

    if len(plan.profilesets) > MAX_ROWS:
        raise TooManyRows(
            f"omnium would run {len(plan.profilesets)} rows (cap is {MAX_ROWS}); narrow the mode or sets"
        )
    plan.simc_text = simc_input.build(profile, options, plan.profilesets)
    return plan


def execute(ctx, profile: CharacterProfile, options: SimOptions, mode: str,
            sets: list[OmniumSet] | None = None) -> SimResult:
    ctx.progress("candidates", 0, 0, f"Building {mode} Omnium Folio rows")
    plan = build(profile, options, mode, sets)
    res = ctx.sim(plan.simc_text, options, klass=profile.klass, spec=profile.spec)
    res = apply_meta(res, plan)
    return res
