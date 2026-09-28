"""Tests for the experimental GPU surrogate: toonopt.surrogate.{features,dataset,model}
and the "smart" Top Gear code path in toonopt.sims.topgear."""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from toonopt.models import (
    Baseline,
    CharacterProfile,
    Item,
    ResultMeta,
    ResultRow,
    SimOptions,
    SimResult,
)
from toonopt.surrogate import dataset as dataset_mod
from toonopt.surrogate import features


def _item(key: str, item_id: int, slot: str, ilevel: int, stats: dict | None = None, **kw) -> Item:
    return Item(key=key, id=item_id, name=key, slot=slot, ilevel=ilevel, stats=stats or {}, **kw)


def _profile(klass: str = "death_knight", spec: str = "frost") -> CharacterProfile:
    equipped = {
        "head": _item("equipped:head", 1, "head", 600, {"strength": 100, "crit": 50}),
        "main_hand": _item("equipped:main_hand", 2, "main_hand", 610, {"strength": 120}),
    }
    return CharacterProfile(name="Test", klass=klass, spec=spec, equipped=equipped)


# ---- features ---------------------------------------------------------------------


def test_gear_vector_fixed_length_and_dtype():
    profile = _profile()
    vec = features.gear_vector(profile, dict(profile.equipped))
    assert vec.shape == (features.VECTOR_LENGTH,)
    assert vec.dtype == np.float32
    assert features.vector_length() == features.VECTOR_LENGTH


def test_gear_vector_deterministic():
    profile = _profile()
    gear = dict(profile.equipped)
    assert np.array_equal(features.gear_vector(profile, gear), features.gear_vector(profile, gear))


def test_gear_vector_reacts_to_gear_changes():
    profile = _profile()
    base = features.gear_vector(profile, dict(profile.equipped))
    swapped = dict(profile.equipped)
    swapped["head"] = _item("bag:1", 99, "head", 700, {"strength": 200})
    other = features.gear_vector(profile, swapped)
    assert not np.array_equal(base, other)
    assert base.shape == other.shape


def test_gear_vector_empty_slots_are_zero():
    profile = CharacterProfile(name="Bare", klass="mage", spec="frost", equipped={})
    vec = features.gear_vector(profile, {})
    assert vec.shape == (features.VECTOR_LENGTH,)
    # everything except the trailing fight-style/targets context block should be zero
    context_len = len(features.FIGHT_STYLES) + 1
    assert float(vec[:-context_len].sum()) == 0.0


def test_gear_vector_context_features_differ_by_options():
    profile = _profile()
    gear = dict(profile.equipped)
    patchwerk = features.gear_vector(profile, gear, SimOptions(fight_style="Patchwerk", desired_targets=1))
    cleave = features.gear_vector(profile, gear, SimOptions(fight_style="CleaveAdd", desired_targets=5))
    assert not np.array_equal(patchwerk, cleave)
    # only the trailing context block (fight-style one-hot + targets) should differ
    context_len = len(features.FIGHT_STYLES) + 1
    assert np.array_equal(patchwerk[:-context_len], cleave[:-context_len])


def test_trinket_and_set_bonus_buckets_are_populated():
    profile = _profile()
    gear = dict(profile.equipped)
    gear["trinket1"] = _item("equipped:trinket1", 12345, "trinket1", 600, set_id=42)
    vec = features.gear_vector(profile, gear)
    assert vec.sum() > 0


# ---- dataset ------------------------------------------------------------------------


def _write_history_job(
    history_dir: Path, job_id: str, *, job_type: str, klass: str, spec: str,
    baseline_dps: float, rows: list[ResultRow], status: str = "done",
) -> CharacterProfile:
    d = history_dir / job_id
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"id": job_id, "type": job_type, "status": status}), "utf-8")
    profile = _profile(klass, spec)
    (d / "profile.json").write_text(profile.model_dump_json(), "utf-8")
    result = SimResult(job_id=job_id, type=job_type, klass=klass, spec=spec,
                        baseline=Baseline(dps=baseline_dps), results=rows)
    (d / "result.json").write_text(result.model_dump_json(), "utf-8")
    return profile


def test_dataset_build_reconstructs_baseline_and_swap_rows(tmp_path):
    hist = tmp_path / "history"
    new_head = _item("bag:1", 55, "head", 650, {"strength": 300})
    rows = [ResultRow(name="c1", label="head swap", dps=1100.0, meta=ResultMeta(changes={"head": new_head}))]
    _write_history_job(hist, "job1", job_type="topgear", klass="death_knight", spec="frost",
                        baseline_dps=1000.0, rows=rows)

    ds = dataset_mod.build("death_knight", "frost", history_dir=hist)
    assert len(ds) == 2   # baseline row + the one swap row
    assert ds.X.shape == (2, features.VECTOR_LENGTH)
    targets = sorted(ds.y.tolist())
    assert targets[0] == pytest.approx(1.0)
    assert targets[1] == pytest.approx(1.1)


def test_dataset_skips_history_without_profile_json(tmp_path):
    """History recorded before jobs.py started writing profile.json is skipped, not crashed on."""
    hist = tmp_path / "history"
    d = hist / "job2"
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"id": "job2", "type": "topgear", "status": "done"}), "utf-8")
    result = SimResult(job_id="job2", type="topgear", baseline=Baseline(dps=500.0))
    (d / "result.json").write_text(result.model_dump_json(), "utf-8")

    ds = dataset_mod.build("death_knight", "frost", history_dir=hist)
    assert len(ds) == 0


def test_dataset_filters_by_klass_and_spec(tmp_path):
    hist = tmp_path / "history"
    _write_history_job(hist, "jobA", job_type="quick", klass="mage", spec="frost",
                        baseline_dps=800.0, rows=[])
    ds = dataset_mod.build("death_knight", "frost", history_dir=hist)
    assert len(ds) == 0
    ds_mage = dataset_mod.build("mage", "frost", history_dir=hist)
    assert len(ds_mage) == 1   # baseline row only, no results


def test_dataset_ignores_unrelated_job_types(tmp_path):
    hist = tmp_path / "history"
    _write_history_job(hist, "jobB", job_type="talentcompare", klass="death_knight", spec="frost",
                        baseline_dps=900.0, rows=[])
    ds = dataset_mod.build("death_knight", "frost", history_dir=hist)
    assert len(ds) == 0


# ---- model (torch optional) --------------------------------------------------------


@pytest.mark.slow
def test_train_and_predict_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    from toonopt.surrogate import model as surrogate_model

    monkeypatch.setattr(surrogate_model, "MODEL_DIR", tmp_path / "surrogate")

    n = 260
    rng = np.random.default_rng(0)
    X = rng.normal(size=(n, features.VECTOR_LENGTH)).astype(np.float32)
    true_w = rng.normal(size=features.VECTOR_LENGTH).astype(np.float32)
    y = (1.0 + X @ true_w * 0.001).astype(np.float32)

    class FakeDataset:
        def __len__(self) -> int:
            return n

        @property
        def X(self) -> np.ndarray:
            return X

        @property
        def y(self) -> np.ndarray:
            return y

    import toonopt.surrogate.dataset as ds_mod

    monkeypatch.setattr(ds_mod, "build", lambda klass, spec: FakeDataset())

    report = surrogate_model.train("death_knight", "frost", min_samples=200, epochs=5)
    assert report.samples == n
    assert report.device in ("cpu", "cuda")
    assert Path(report.path).exists()

    assert surrogate_model.has_model("death_knight", "frost")
    preds = surrogate_model.predict("death_knight", "frost", X[:4])
    assert preds.shape == (4,)
    assert np.all(np.isfinite(preds))


def test_train_requires_min_samples(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    from toonopt.surrogate import model as surrogate_model

    monkeypatch.setattr(surrogate_model, "MODEL_DIR", tmp_path / "surrogate")

    class EmptyDataset:
        def __len__(self) -> int:
            return 3

    import toonopt.surrogate.dataset as ds_mod

    monkeypatch.setattr(ds_mod, "build", lambda klass, spec: EmptyDataset())
    with pytest.raises(ValueError, match="only 3 training rows"):
        surrogate_model.train("death_knight", "frost", min_samples=200)


def test_predict_without_trained_model_raises(tmp_path, monkeypatch):
    from toonopt.surrogate import model as surrogate_model

    monkeypatch.setattr(surrogate_model, "MODEL_DIR", tmp_path / "surrogate")
    with pytest.raises(surrogate_model.NotTrained):
        surrogate_model.predict("death_knight", "frost", np.zeros((1, features.VECTOR_LENGTH)))


def test_status_reports_unavailable_without_torch(tmp_path, monkeypatch):
    from toonopt.surrogate import model as surrogate_model

    monkeypatch.setattr(surrogate_model, "MODEL_DIR", tmp_path / "surrogate")

    def no_torch():
        raise surrogate_model.SurrogateUnavailable("nope")

    monkeypatch.setattr(surrogate_model, "_torch", no_torch)
    st = surrogate_model.status()
    assert st == {"available": False, "device": "unavailable", "models": []}


# ---- smart Top Gear path, with a fake predictor -------------------------------------


class FakeSmartCtx:
    """Runs a topgear plan through a canned SimResult; records what was simmed."""

    def __init__(self, baseline_dps: float = 1000.0):
        self.baseline_dps = baseline_dps
        self.runs: list[tuple[str, list[str]]] = []

    def check_cancelled(self) -> None:
        pass

    def progress(self, *a, **k) -> None:
        pass

    def sim(self, simc_text: str, options: SimOptions, *, klass: str = "", spec: str = "",
            stage_label: str = "") -> SimResult:
        names = sorted(set(re.findall(r'profileset\."([^"]+)"', simc_text)))
        rows = [ResultRow(name=n, label=n, dps=self.baseline_dps) for n in names]
        res = SimResult(job_id="j", type="topgear", baseline=Baseline(dps=self.baseline_dps))
        res.results = rows
        self.runs.append((stage_label, names))
        return res


def test_smart_path_scores_with_surrogate_and_sets_predicted_dps(dk_profile, monkeypatch):
    from toonopt.sims import topgear
    from toonopt.surrogate import model as surrogate_model

    keys = ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5", "vault:1", "vault:2"]
    monkeypatch.setattr(topgear, "_smart_available", lambda klass, spec: True)
    monkeypatch.setattr(surrogate_model, "predict", lambda klass, spec, vecs: np.full(len(vecs), 1.2, dtype=np.float32))

    ctx = FakeSmartCtx(baseline_dps=1000.0)
    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), keys, max_combos=6, smart=True)

    assert len(ctx.runs) == 1 and ctx.runs[0][0].startswith("Smart")
    assert res.results, "smart path should still produce rows to sim"
    assert all(row.meta.predicted_dps == pytest.approx(1200.0) for row in res.results)


def test_smart_path_falls_back_without_a_trained_model(dk_profile, monkeypatch):
    from toonopt.sims import topgear

    keys = ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5", "vault:1", "vault:2"]
    monkeypatch.setattr(topgear, "_smart_available", lambda klass, spec: False)

    messages: list[str] = []
    ctx = FakeSmartCtx(baseline_dps=1000.0)
    monkeypatch.setattr(ctx, "progress", lambda phase, current=0, total=0, message="": messages.append(message))

    res = topgear.execute(ctx, dk_profile, SimOptions(iterations=10), keys, max_combos=8, smart=True)

    assert any("No surrogate model" in m for m in messages)
    assert ctx.runs and ctx.runs[0][0].startswith("Stage 1/2")     # fell back to the normal search
    assert all(row.meta.predicted_dps is None for row in res.results)
