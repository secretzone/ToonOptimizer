"""Unit tests for wow_build detection/precedence in toonopt.config."""
from __future__ import annotations

import json
from pathlib import Path

from toonopt.config import Settings, detect_wow_build


def _write_build_info(wow_dir: Path, version: str) -> None:
    wow_dir.mkdir(parents=True, exist_ok=True)
    header = "Branch!STRING:0|Active!DEC:1|Product!STRING:0|Version!STRING:0"
    row = f"wowt|1|wow|{version}"
    (wow_dir / ".build.info").write_text(f"{header}\n{row}\n", "utf-8")


def test_detect_wow_build_reads_build_info(tmp_path):
    _write_build_info(tmp_path, "12.1.0.69875")
    assert detect_wow_build(str(tmp_path)) == "12.1.0.69875"


def test_detect_wow_build_missing_install_is_empty(tmp_path):
    assert detect_wow_build(str(tmp_path / "does_not_exist")) == ""


def test_wow_build_precedence_override_detected_stored(tmp_path):
    """override > freshly detected > stored fallback (when detection fails)."""
    good_dir = tmp_path / "wow"
    _write_build_info(good_dir, "12.1.0.69875")
    missing_dir = tmp_path / "missing"

    # No override, detection fails (WoW not mounted at wow_dir): keep the stored value.
    s = Settings(wow_dir=str(missing_dir), wow_build="10.0.0.1")
    assert s.refresh_wow_build() == "10.0.0.1"
    assert s.wow_build == "10.0.0.1"

    # No override, detection succeeds: the freshly detected build wins over the stale stored one.
    s.wow_dir = str(good_dir)
    assert s.refresh_wow_build() == "12.1.0.69875"
    assert s.wow_build == "12.1.0.69875"

    # An explicit override always wins, even though detection would still succeed.
    s.wow_build_override = "99.9.9.99999"
    assert s.refresh_wow_build() == "99.9.9.99999"
    assert s.wow_build == "99.9.9.99999"

    # Clearing the override reverts to auto-detection.
    s.wow_build_override = ""
    assert s.refresh_wow_build() == "12.1.0.69875"


def test_save_never_writes_detected_value_into_override(tmp_path, monkeypatch):
    from toonopt import config

    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    _write_build_info(tmp_path, "12.1.0.69875")
    s = Settings(wow_dir=str(tmp_path))
    s.refresh_wow_build()
    s.save()
    saved = json.loads((tmp_path / "settings.json").read_text("utf-8"))
    assert saved["wow_build"] == "12.1.0.69875"
    assert saved["wow_build_override"] == ""
