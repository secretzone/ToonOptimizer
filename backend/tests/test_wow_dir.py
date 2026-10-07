"""WoW install detection, normalization, Settings.load re-detect and the wow-dir API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from toonopt import config
from toonopt.config import Settings, is_wow_dir, normalize_wow_dir


def _make_wow(root: Path) -> Path:
    (root / "_retail_").mkdir(parents=True)
    return root


@pytest.fixture(autouse=True)
def no_real_machine(monkeypatch):
    """Never touch the real registry, drives or WOW_DIR."""
    monkeypatch.delenv("WOW_DIR", raising=False)
    monkeypatch.setattr(config, "_registry_paths", list)
    monkeypatch.setattr(config, "_list_drives", list)


def test_normalize_cases(tmp_path):
    assert normalize_wow_dir("") == ""
    assert normalize_wow_dir(None) == ""
    assert normalize_wow_dir(r'  "C:\Games\World of Warcraft\"  ') == r"C:\Games\World of Warcraft"
    assert normalize_wow_dir(r"C:\Games\World of Warcraft\_retail_") == r"C:\Games\World of Warcraft"
    assert normalize_wow_dir(r"C:\Games\World of Warcraft\_retail_\\") == r"C:\Games\World of Warcraft"
    assert normalize_wow_dir(r"C:\Games\World of Warcraft\_RETAIL_\Wow.exe") == r"C:\Games\World of Warcraft"
    assert normalize_wow_dir("/g/wow/_retail_/Interface/AddOns") == "/g/wow"
    assert normalize_wow_dir("'D:/WoW/'") == "D:/WoW"


def test_normalize_existing_file_and_env(tmp_path, monkeypatch):
    root = _make_wow(tmp_path / "wow")
    f = root / ".build.info"
    f.write_text("x", "utf-8")
    assert normalize_wow_dir(str(f)) == str(root)
    monkeypatch.setenv("TOON_TEST_ROOT", str(tmp_path))
    assert normalize_wow_dir("$TOON_TEST_ROOT/wow/").replace("\\", "/") \
        == str(root).replace("\\", "/")


def test_is_wow_dir(tmp_path):
    root = _make_wow(tmp_path / "wow")
    assert is_wow_dir(root)
    assert is_wow_dir(str(root))
    assert not is_wow_dir(tmp_path)
    assert not is_wow_dir("")
    assert not is_wow_dir(None)
    assert not is_wow_dir(tmp_path / "nope")


def test_candidates_order_and_dedup(tmp_path, monkeypatch):
    env_root = _make_wow(tmp_path / "envwow")
    reg_root = _make_wow(tmp_path / "reg" / "World of Warcraft")
    scan_drive = tmp_path / "drive"
    _make_wow(scan_drive / "Games" / "World of Warcraft")
    _make_wow(scan_drive / "World of Warcraft")
    (scan_drive / "Blizzard" / "World of Warcraft").mkdir(parents=True)  # no _retail_: invalid

    monkeypatch.setenv("WOW_DIR", str(env_root))
    monkeypatch.setattr(config, "_registry_paths", lambda: [
        str(reg_root) + "\\_retail_",          # registry stores _retail_ itself
        str(reg_root).upper(),                 # case-insensitive duplicate
        str(tmp_path / "gone"),                # invalid, dropped
        str(env_root),                         # duplicate of env, dropped
    ])
    monkeypatch.setattr(config, "_list_drives", lambda: [str(scan_drive)])

    cands = config.wow_dir_candidates()
    assert [c["source"] for c in cands] == ["env", "registry", "scan", "scan"]
    assert cands[0]["path"] == str(env_root)
    assert Path(cands[1]["path"]) == reg_root
    assert Path(cands[2]["path"]) == scan_drive / "World of Warcraft"
    assert Path(cands[3]["path"]) == scan_drive / "Games" / "World of Warcraft"
    assert config.detect_wow_dir() == str(env_root)


def test_detect_empty_when_nothing(tmp_path):
    assert config.wow_dir_candidates() == []
    assert config.detect_wow_dir() == ""


def test_invalid_env_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("WOW_DIR", str(tmp_path / "missing"))
    assert config.detect_wow_dir() == ""


def test_load_redetects_stale_saved_path(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)
    real = _make_wow(tmp_path / "real")
    monkeypatch.setattr(config, "_registry_paths", lambda: [str(real)])
    settings_file.write_text(json.dumps({"wow_dir": str(tmp_path / "stale"), "region": "eu"}), "utf-8")

    s = Settings.load()
    assert s.wow_dir == str(real)
    assert s.region == "eu"
    assert json.loads(settings_file.read_text("utf-8"))["wow_dir"] == str(real)


def test_load_keeps_valid_saved_and_env_wins(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)
    saved = _make_wow(tmp_path / "saved")
    settings_file.write_text(json.dumps({"wow_dir": str(saved)}), "utf-8")
    assert Settings.load().wow_dir == str(saved)

    env_root = _make_wow(tmp_path / "env")
    monkeypatch.setenv("WOW_DIR", str(env_root))
    assert Settings.load().wow_dir == str(env_root)


def test_load_stale_and_nothing_found_keeps_value(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)
    settings_file.write_text(json.dumps({"wow_dir": str(tmp_path / "stale")}), "utf-8")
    assert Settings.load().wow_dir == str(tmp_path / "stale")


# ---- API ----------------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    from toonopt.main import app

    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config.settings, "wow_dir", "")
    return TestClient(app)


def test_put_wow_dir_validates_and_normalizes(client, tmp_path):
    root = _make_wow(tmp_path / "wow")
    bad = client.put("/api/settings", json={"wow_dir": str(tmp_path / "nothing")})
    assert bad.status_code == 400
    assert bad.json()["detail"].startswith("That folder doesn't look like a World of Warcraft install")

    ok = client.put("/api/settings", json={"wow_dir": f'"{root}\\_retail_\\Wow.exe"'})
    assert ok.status_code == 200
    assert ok.json()["wow_dir"] == str(root)

    cleared = client.put("/api/settings", json={"wow_dir": ""})
    assert cleared.status_code == 200 and cleared.json()["wow_dir"] == ""


def test_get_wow_dir_endpoint(client, tmp_path, monkeypatch):
    root = _make_wow(tmp_path / "wow")
    monkeypatch.setattr(config, "_registry_paths", lambda: [str(root)])
    body = client.get("/api/settings/wow-dir").json()
    assert body == {"current": "", "valid": False, "candidates": [{"path": str(root), "source": "registry"}]}

    client.put("/api/settings", json={"wow_dir": str(root)})
    body = client.get("/api/settings/wow-dir").json()
    assert body["current"] == str(root) and body["valid"] is True


def test_addon_and_status_report_validity(client, tmp_path):
    root = _make_wow(tmp_path / "wow")
    client.put("/api/settings", json={"wow_dir": str(root)})
    assert client.get("/api/import/addon").json()["wow_dir_valid"] is True
    status = client.get("/api/status").json()
    assert status["wow_dir"] == str(root) and status["wow_dir_valid"] is True

    config.settings.wow_dir = ""
    assert client.get("/api/import/addon").json()["wow_dir_valid"] is False
