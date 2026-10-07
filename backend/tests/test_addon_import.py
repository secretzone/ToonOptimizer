from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from toonopt import addon_import, characters, config
from toonopt.main import app
from toonopt.simc import profile as profile_mod

FIXTURE = Path(__file__).parent / "fixtures" / "ToonOptimizer_sv.lua"


# --- parser -----------------------------------------------------------------

def test_parse_escapes():
    d = addon_import.parse_savedvariables(r'X = "a\nb\t\"q\" \\ \65\066 \r"')
    assert d["X"] == 'a\nb\t"q" \\ AB \r'


def test_parse_nesting_numbers_and_literals():
    d = addon_import.parse_savedvariables(
        'T = { ["a"] = { ["b"] = -1.5, c = 2, e = 1e3 }, ["t"] = true, ["f"] = false, ["n"] = nil, }')
    assert d["T"]["a"] == {"b": -1.5, "c": 2, "e": 1000.0}
    assert d["T"]["t"] is True and d["T"]["f"] is False and d["T"]["n"] is None


def test_parse_arrays_comments_numeric_keys():
    text = '''-- header comment
L = {
"one", -- [1]
"two", -- [2]
{ 1, 2 }, -- [3]
}
K = { [1] = "a", [2] = "b" }
S = { [1] = "a", [3] = "c" }
'''
    d = addon_import.parse_savedvariables(text)
    assert d["L"] == ["one", "two", [1, 2]]
    assert d["K"] == ["a", "b"]
    assert d["S"] == {1: "a", 3: "c"}


def test_parse_multiple_assignments_and_empty_table():
    d = addon_import.parse_savedvariables('A = {}\nB = 1\nC = "x";\n')
    assert d == {"A": {}, "B": 1, "C": "x"}


@pytest.mark.parametrize("bad", ['X = {', 'X = "abc', 'X = ', 'X = {["a"] = }', "= 3"])
def test_parse_malformed(bad):
    with pytest.raises(addon_import.LuaParseError):
        addon_import.parse_savedvariables(bad)


def test_parse_fixture():
    db = addon_import.parse_savedvariables(FIXTURE.read_text("utf-8"))["ToonOptimizerDB"]
    assert db["version"] == 1 and db["settings"] == {"auto": True}
    assert db["characters"]["Testhunter-Testrealm"]["ilvl"] == 278.5


# --- discovery + import -----------------------------------------------------

def _wow(tmp_path, accounts=("ACC1",), install=True) -> Path:
    wow = tmp_path / "wow"
    for acc in accounts:
        sv = wow / "_retail_" / "WTF" / "Account" / acc / "SavedVariables"
        sv.mkdir(parents=True)
        shutil.copyfile(FIXTURE, sv / "ToonOptimizer.lua")
    if install:
        toc = wow / "_retail_" / "Interface" / "AddOns" / "ToonOptimizer"
        toc.mkdir(parents=True)
        (toc / "ToonOptimizer.toc").write_text("## Title: ToonOptimizer\n", "utf-8")
    return wow


@pytest.fixture
def wow(tmp_path, monkeypatch):
    d = _wow(tmp_path)
    monkeypatch.setattr(config.settings, "wow_dir", str(d))
    return d


def test_files_and_installed(tmp_path):
    d = _wow(tmp_path, accounts=("A", "B"))
    assert len(addon_import.savedvariables_files(d)) == 2
    assert len(addon_import.savedvariables_files(d / "_retail_")) == 2
    assert addon_import.addon_installed(d) and addon_import.addon_installed(d / "_retail_")
    assert not addon_import.addon_installed(tmp_path / "nope")
    assert addon_import.savedvariables_files("") == []


def test_list_captures(wow):
    caps = addon_import.list_captures()
    assert len(caps) == 1
    c = caps[0]
    assert c["key"] == "Testhunter-Testrealm" and c["account"] == "ACC1"
    assert c["class"] == "HUNTER" and c["spec"] == "Marksmanship" and c["ilvl"] == 278.5
    assert c["captured_at"] == "2026-10-07T00:00:00+00:00"
    assert c["saved_slug"] == "testhunter-testrealm"
    assert c["saved_imported_at"] is None and c["newer_than_saved"] is True


def test_duplicate_key_keeps_newest(tmp_path, monkeypatch):
    d = _wow(tmp_path, accounts=("A", "B"))
    f = d / "_retail_/WTF/Account/B/SavedVariables/ToonOptimizer.lua"
    f.write_text(FIXTURE.read_text("utf-8").replace("1791331200", "1791331300"), "utf-8")
    monkeypatch.setattr(config.settings, "wow_dir", str(d))
    caps = addon_import.list_captures()
    assert len(caps) == 1 and caps[0]["account"] == "B"


def test_skips_malformed_and_empty(tmp_path, monkeypatch, caplog):
    d = _wow(tmp_path, accounts=("A", "B", "C"))
    base = d / "_retail_/WTF/Account"
    (base / "B/SavedVariables/ToonOptimizer.lua").write_text("ToonOptimizerDB = {", "utf-8")
    (base / "C/SavedVariables/ToonOptimizer.lua").write_text(
        'ToonOptimizerDB = { ["characters"] = { ["X-Y"] = { ["simc"] = "" } } }', "utf-8")
    monkeypatch.setattr(config.settings, "wow_dir", str(d))
    with caplog.at_level("WARNING"):
        caps = addon_import.list_captures()
    assert [c["account"] for c in caps] == ["A"]
    assert "skipping unreadable addon file" in caplog.text


def test_import_matches_paste(wow, hunter_mm_export):
    prof = addon_import.import_capture()
    expected = profile_mod.parse(hunter_mm_export)
    assert prof.source == "addon" and prof.imported_at == "2026-10-07T00:00:00+00:00"
    a = prof.model_dump(exclude={"imported_at", "source"})
    b = expected.model_dump(exclude={"imported_at", "source"})
    assert a == b
    saved = characters.get("testhunter-testrealm")
    assert saved is not None and saved.source == "addon"
    caps = addon_import.list_captures()
    assert caps[0]["saved_imported_at"] == prof.imported_at and caps[0]["newer_than_saved"] is False


def test_import_errors(tmp_path, monkeypatch, wow):
    with pytest.raises(addon_import.UnknownCapture):
        addon_import.import_capture("Nobody-Nowhere")
    monkeypatch.setattr(config.settings, "wow_dir", str(tmp_path / "empty"))
    with pytest.raises(addon_import.NoAddonData):
        addon_import.import_capture()


# --- API --------------------------------------------------------------------

@pytest.fixture
def client():
    return TestClient(app)


def test_api_get(client, wow):
    r = client.get("/api/import/addon")
    assert r.status_code == 200
    body = r.json()
    assert body["installed"] is True and body["wow_dir"] == str(wow)
    assert len(body["files"]) == 1 and body["captures"][0]["key"] == "Testhunter-Testrealm"


def test_api_get_no_wow(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "wow_dir", "")
    body = client.get("/api/import/addon").json()
    assert body == {"installed": False, "wow_dir": None, "wow_dir_valid": False, "files": [], "captures": []}


def test_api_post(client, wow):
    r = client.post("/api/import/addon", json={})
    assert r.status_code == 200
    assert r.json()["source"] == "addon" and r.json()["name"] == "Testhunter"
    assert client.post("/api/import/addon").status_code == 200
    r = client.post("/api/import/addon", json={"key": "Testhunter-Testrealm"})
    assert r.status_code == 200
    r = client.post("/api/import/addon", json={"all": True})
    # the profile was just imported from this very capture, so a batch run skips it
    assert r.status_code == 200 and [(x["key"], x["status"]) for x in r.json()] == [("Testhunter-Testrealm", "skipped")]
    assert client.get("/api/characters/testhunter-testrealm").json()["source"] == "addon"


def test_api_post_404(client, wow, tmp_path, monkeypatch):
    r = client.post("/api/import/addon", json={"key": "Nobody-Nowhere"})
    assert r.status_code == 404 and "Nobody-Nowhere" in r.json()["detail"]
    monkeypatch.setattr(config.settings, "wow_dir", str(tmp_path / "empty"))
    for body in ({}, {"all": True}):
        r = client.post("/api/import/addon", json=body)
        assert r.status_code == 404 and "No ToonOptimizer addon data found" in r.json()["detail"]


def test_api_post_422(client, wow):
    f = next(wow.glob("_retail_/WTF/Account/*/SavedVariables/ToonOptimizer.lua"))
    f.write_text('ToonOptimizerDB = { ["characters"] = { ["X-Y"] = { ["simc"] = "garbage", ["captured_at"] = 5 } } }', "utf-8")
    assert client.post("/api/import/addon", json={}).status_code == 422


def test_paste_sets_source(client, dk_export):
    assert client.post("/api/import/simc", json={"text": dk_export}).json()["source"] == "paste"


# --- review fixes -----------------------------------------------------------

def _lua_entry(key, simc, ts, name, realm):
    esc = simc.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return (f'["{key}"] = {{ ["simc"] = "{esc}", ["captured_at"] = {ts}, ["name"] = "{name}", '
            f'["realm"] = "{realm}", ["class"] = "HUNTER", ["spec"] = "Marksmanship", ["ilvl"] = 1, }},\n')


def _write_sv(wow, *entries):
    f = next(wow.glob("_retail_/WTF/Account/*/SavedVariables/ToonOptimizer.lua"))
    f.write_text('ToonOptimizerDB = { ["characters"] = {\n' + "".join(entries) + "}, }\n", "utf-8")


def test_slug_uses_server_token(wow, hunter_mm_export):
    simc = hunter_mm_export.replace("server=testrealm", "server=malganis").replace("Testrealm", "Mal'Ganis")
    _write_sv(wow, _lua_entry("Testhunter-Mal'Ganis", simc, 1791331200, "Testhunter", "Mal'Ganis"))
    cap = addon_import.list_captures()[0]
    assert cap["realm"] == "Mal'Ganis"
    pasted = profile_mod.parse(simc)
    assert cap["saved_slug"] == characters.slugify(pasted.name, pasted.realm) == "testhunter-malganis"
    assert cap["newer_than_saved"] is True
    addon_import.import_capture()
    cap = addon_import.list_captures()[0]
    assert cap["saved_imported_at"] == cap["captured_at"] and cap["newer_than_saved"] is False


def test_slug_falls_back_to_key_realm(wow):
    _write_sv(wow, _lua_entry("Foo-Bar", "hunter=\"Foo\"\nlevel=80", 5, "Foo", "Display Realm"))
    assert addon_import.list_captures()[0]["saved_slug"] == "foo-bar"


def test_import_all_per_item(client, wow, hunter_mm_export, dk_export):
    older = hunter_mm_export.replace("Testhunter", "Oldtoon")
    _write_sv(
        wow,
        _lua_entry("Testhunter-Testrealm", hunter_mm_export, 1791331200, "Testhunter", "Testrealm"),
        _lua_entry("Oldtoon-Testrealm", older, 1791331300, "Oldtoon", "Testrealm"),
        _lua_entry("Bad-Testrealm", "garbage", 1791331100, "Bad", "Testrealm"),
    )
    # a newer paste of Oldtoon is already saved -> its capture must not overwrite it
    saved = profile_mod.parse(older)
    saved.imported_at = "2030-01-01T00:00:00+00:00"
    characters.save(saved)
    r = client.post("/api/import/addon", json={"all": True})
    assert r.status_code == 200
    res = {x["key"]: x for x in r.json()}
    assert res["Testhunter-Testrealm"]["status"] == "imported"
    assert res["Testhunter-Testrealm"]["profile"]["source"] == "addon"
    assert res["Oldtoon-Testrealm"]["status"] == "skipped" and res["Oldtoon-Testrealm"]["profile"] is None
    assert res["Bad-Testrealm"]["status"] == "error" and res["Bad-Testrealm"]["detail"]
    assert characters.get("oldtoon-testrealm").imported_at == "2030-01-01T00:00:00+00:00"
    assert characters.get("testhunter-testrealm") is not None


def test_bad_captured_at_is_skipped(wow, hunter_mm_export, caplog):
    _write_sv(
        wow,
        _lua_entry("A-B", hunter_mm_export, "1e999", "A", "B"),
        _lua_entry("Testhunter-Testrealm", hunter_mm_export, 1791331200, "Testhunter", "Testrealm"),
    )
    with caplog.at_level("WARNING"):
        caps = addon_import.list_captures()
    assert [c["key"] for c in caps] == ["Testhunter-Testrealm"] and "bad captured_at" in caplog.text


def test_huge_int_does_not_raise_valueerror(tmp_path):
    with pytest.raises(addon_import.LuaParseError):
        addon_import.parse_savedvariables("X = " + "9" * 5000)


def test_utf8_byte_escapes():
    d = addon_import.parse_savedvariables(r'X = "\195\169|\xc3\xa9|\255"')
    assert d["X"] == "é|é|\ufffd"
