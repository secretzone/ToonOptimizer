"""Unit tests for the startup auto data-refresh in toonopt.main (FastAPI lifespan)."""
from __future__ import annotations

from toonopt import jobs
from toonopt import main as main_mod
from toonopt.config import Settings
from toonopt.data import wago


def _stub_refresh_wow_build(monkeypatch, build: str) -> None:
    # `settings` is a pydantic BaseModel instance; you can't monkeypatch a method onto an
    # instance directly (pydantic rejects assigning non-field attributes), so patch the
    # class method instead -- monkeypatch still restores it after the test.
    monkeypatch.setattr(Settings, "refresh_wow_build", lambda self: build)


def test_submits_refresh_job_when_cache_missing(monkeypatch):
    _stub_refresh_wow_build(monkeypatch, "12.1.0.69933")
    monkeypatch.setattr(wago, "is_ready", lambda build=None: False)
    calls: list[tuple] = []
    monkeypatch.setattr(jobs.manager, "submit", lambda *a, **k: calls.append((a, k)))

    main_mod._maybe_start_data_refresh()

    assert len(calls) == 1
    (job_type, run_fn), _kwargs = calls[0]
    assert job_type == "data_refresh"
    assert callable(run_fn)


def test_skips_when_cache_already_ready(monkeypatch):
    _stub_refresh_wow_build(monkeypatch, "12.1.0.69933")
    monkeypatch.setattr(wago, "is_ready", lambda build=None: True)
    calls: list[tuple] = []
    monkeypatch.setattr(jobs.manager, "submit", lambda *a, **k: calls.append((a, k)))

    main_mod._maybe_start_data_refresh()

    assert calls == []


def test_skips_when_no_live_build_detected(monkeypatch):
    _stub_refresh_wow_build(monkeypatch, "")
    calls: list[tuple] = []
    monkeypatch.setattr(jobs.manager, "submit", lambda *a, **k: calls.append((a, k)))

    main_mod._maybe_start_data_refresh()

    assert calls == []


def test_never_raises_when_readiness_check_breaks(monkeypatch):
    """A broken cache dir (permissions, corrupt meta.json, ...) must not crash startup."""
    _stub_refresh_wow_build(monkeypatch, "12.1.0.69933")

    def boom(build=None):
        raise OSError("disk is unhappy")

    monkeypatch.setattr(wago, "is_ready", boom)
    calls: list[tuple] = []
    monkeypatch.setattr(jobs.manager, "submit", lambda *a, **k: calls.append((a, k)))

    main_mod._maybe_start_data_refresh()  # must not raise

    assert calls == []


def test_lifespan_runs_through_testclient(monkeypatch):
    """End-to-end: entering the app via `with TestClient(app)` actually runs the lifespan
    and reaches _maybe_start_data_refresh (verifying the wiring, not just the helper)."""
    from fastapi.testclient import TestClient

    called = []
    monkeypatch.setattr(main_mod, "_maybe_start_data_refresh", lambda: called.append(True))

    with TestClient(main_mod.app):
        pass

    assert called == [True]
