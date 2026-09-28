"""Training rows for the GPU surrogate, built from the user's own sim history.

Walks ``HISTORY_DIR/<id>/{job.json,result.json,profile.json}`` for jobs of type
topgear / droptimizer / gearcompare / quick, reconstructs the full gear set for every
result row (baseline profile's ``equipped`` + ``ResultMeta.changes``) and emits one
training example per row. The target is ``dps / baseline_dps`` for that run, so runs
simmed with different fight-style/target settings can be mixed in one dataset -- the
fight style and target count are themselves part of the feature vector (see
``toonopt.surrogate.features``), which is how the model tells those runs apart.

Needs ``profile.json``, which ``toonopt.jobs.JobManager`` only started writing once this
phase landed (see the docstring at the top of ``jobs.py``); history recorded before that
change has no ``profile.json`` and is silently skipped here.

Known gap: ``ResultMeta.changes`` only records slots an engine *set* to a new item, not
slots it cleared (e.g. Top Gear swapping to a two-hander drops the off-hand but does not
record ``off_hand: None`` in ``changes`` -- see ``sims/topgear.py::combos_from``). Rows
built from such a combo will show a stale off-hand item that SimC itself ignored. This is
an accepted approximation for an experimental model; it affects a minority of rows
(one- vs two-handed weapon swaps only).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from toonopt.config import HISTORY_DIR
from toonopt.models import SLOTS, CharacterProfile, Item, JobType, SimResult
from toonopt.surrogate.features import VECTOR_LENGTH, gear_vector

log = logging.getLogger(__name__)

DATASET_JOB_TYPES: frozenset[JobType] = frozenset({"topgear", "droptimizer", "gearcompare", "quick"})

Gear = dict[str, Item | None]


@dataclass
class Row:
    job_id: str
    row_name: str            # "baseline" or the profileset name
    vector: np.ndarray
    target: float             # dps / baseline_dps for this run
    dps: float
    baseline_dps: float


@dataclass
class Dataset:
    klass: str
    spec: str
    rows: list[Row] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def X(self) -> np.ndarray:
        if not self.rows:
            return np.zeros((0, VECTOR_LENGTH), dtype=np.float32)
        return np.stack([r.vector for r in self.rows]).astype(np.float32)

    @property
    def y(self) -> np.ndarray:
        return np.array([r.target for r in self.rows], dtype=np.float32)


def _apply_changes(profile: CharacterProfile, changes: dict[str, Item] | None) -> Gear:
    gear: Gear = {slot: profile.equipped.get(slot) for slot in SLOTS}
    for slot, item in (changes or {}).items():
        if slot in gear:
            gear[slot] = item
    return gear


def _load_job(job_dir: Path) -> tuple[dict, SimResult, CharacterProfile] | None:
    job_path, result_path, profile_path = (job_dir / n for n in ("job.json", "result.json", "profile.json"))
    if not (job_path.is_file() and result_path.is_file() and profile_path.is_file()):
        return None
    try:
        job = json.loads(job_path.read_text("utf-8"))
        if job.get("type") not in DATASET_JOB_TYPES or job.get("status") != "done":
            return None
        result = SimResult.model_validate_json(result_path.read_text("utf-8"))
        profile = CharacterProfile.model_validate_json(profile_path.read_text("utf-8"))
    except (ValueError, OSError) as e:
        log.warning("skipping history entry %s: %s", job_dir.name, e)
        return None
    return job, result, profile


def build(klass: str, spec: str, history_dir: Path = HISTORY_DIR) -> Dataset:
    """Collect every usable (gear vector, normalised dps) pair for one (klass, spec)."""
    ds = Dataset(klass=klass, spec=spec)
    if not history_dir.exists():
        return ds
    for job_dir in sorted(history_dir.iterdir()):
        if not job_dir.is_dir():
            continue
        loaded = _load_job(job_dir)
        if loaded is None:
            continue
        _job, result, profile = loaded
        if profile.klass != klass or profile.spec != spec:
            continue
        baseline_dps = result.baseline.dps
        if not baseline_dps:
            continue
        options = result.options
        baseline_gear: Gear = {slot: profile.equipped.get(slot) for slot in SLOTS}
        ds.rows.append(Row(
            job_id=job_dir.name, row_name="baseline",
            vector=gear_vector(profile, baseline_gear, options),
            target=1.0, dps=baseline_dps, baseline_dps=baseline_dps,
        ))
        for row in result.results:
            if not row.dps:
                continue
            gear = _apply_changes(profile, row.meta.changes)
            ds.rows.append(Row(
                job_id=job_dir.name, row_name=row.name,
                vector=gear_vector(profile, gear, options),
                target=row.dps / baseline_dps, dps=row.dps, baseline_dps=baseline_dps,
            ))
    return ds
