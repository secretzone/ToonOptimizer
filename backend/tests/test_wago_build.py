"""Unit tests for toonopt.data.wago's effective_build()/ready_builds()/status().

Covers the bug fix: after a WoW patch, ``settings.wow_build`` follows the new build before
``data/cache/<new build>/`` has been downloaded. ``effective_build()`` is what keeps every
other data read on the last fully-cached build instead of raising ``FileNotFoundError``.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from toonopt.data import wago


def _make_build(cache_dir, build: str, *, ready: bool, refreshed_at: str | None = None) -> None:
    d = cache_dir / build
    d.mkdir(parents=True, exist_ok=True)
    tables = wago.TABLES if ready else wago.TABLES[:-1]
    for t in tables:
        (d / f"{t}.csv").write_text("ID\n1\n", "utf-8")
    meta = {"build": build, "refreshed_at": refreshed_at or datetime.now(UTC).isoformat(timespec="seconds")}
    (d / wago.META_FILE).write_text(json.dumps(meta), "utf-8")


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(wago, "CACHE_DIR", tmp_path)
    wago.clear_memory()
    yield tmp_path
    wago.clear_memory()


def test_effective_build_prefers_live_when_ready(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=True)
    _make_build(temp_cache, "12.1.0.69875", ready=True, refreshed_at="2026-09-20T00:00:00+00:00")
    assert wago.effective_build() == "12.1.0.69933"


def test_effective_build_falls_back_to_newest_ready_build(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)          # patched, not downloaded yet
    _make_build(temp_cache, "12.1.0.69875", ready=True, refreshed_at="2026-09-01T00:00:00+00:00")
    _make_build(temp_cache, "12.0.5.60000", ready=True, refreshed_at="2026-01-01T00:00:00+00:00")
    assert wago.effective_build() == "12.1.0.69875"


def test_effective_build_falls_back_to_live_when_nothing_ready(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    assert wago.effective_build() == "12.1.0.69933"


def test_effective_build_empty_cache_dir(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    assert wago.effective_build() == "12.1.0.69933"


def test_ready_builds_sorted_newest_first(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    _make_build(temp_cache, "12.1.0.69875", ready=True, refreshed_at="2026-09-01T00:00:00+00:00")
    _make_build(temp_cache, "12.0.5.60000", ready=True, refreshed_at="2026-01-01T00:00:00+00:00")
    assert wago.ready_builds() == ["12.1.0.69875", "12.0.5.60000"]


def test_status_exposes_effective_build_and_ready_builds(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    _make_build(temp_cache, "12.1.0.69875", ready=True)
    st = wago.status("12.1.0.69933")
    assert st["build"] == "12.1.0.69933"
    assert st["ready"] is False
    assert st["effective_build"] == "12.1.0.69875"
    assert st["ready_builds"] == ["12.1.0.69875"]


def test_status_defaults_to_effective_build(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    _make_build(temp_cache, "12.1.0.69875", ready=True)
    assert wago.status()["build"] == "12.1.0.69875"


def test_is_ready_defaults_to_effective_build(monkeypatch, temp_cache):
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    _make_build(temp_cache, "12.1.0.69875", ready=True)
    assert wago.is_ready() is True                    # the newest ready build, not the live one
    assert wago.is_ready("12.1.0.69933") is False      # explicit build is still respected


def test_table_reads_effective_build_by_default(monkeypatch, temp_cache):
    """The bug this fixes: live build patched, cache not downloaded yet -- table() must
    keep serving the last fully-cached build instead of raising FileNotFoundError."""
    monkeypatch.setattr(wago.settings, "wow_build", "12.1.0.69933")
    _make_build(temp_cache, "12.1.0.69933", ready=False)
    # the (incomplete) new build's Item.csv exists but must NOT be the one read from
    (temp_cache / "12.1.0.69933" / "Item.csv").write_text("ID\n999\n", "utf-8")
    _make_build(temp_cache, "12.1.0.69875", ready=True)

    df = wago.table("Item")
    assert df["ID"].to_list() == [1]                  # served from the old, fully-cached build

    with pytest.raises(FileNotFoundError):
        # _make_build(ready=False) omits wago.TABLES[-1] for 12.1.0.69933
        wago.table(wago.TABLES[-1], build="12.1.0.69933")  # an explicit build is never silently swapped
