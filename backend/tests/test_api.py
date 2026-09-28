from __future__ import annotations

import time
import types

import pytest
from fastapi.testclient import TestClient

from toonopt.data.season import UpgradeStep
from toonopt.main import app


@pytest.fixture
def client(job_manager, fake_simc, monkeypatch, tmp_path):
    from toonopt import config
    from toonopt.simc import runtime

    monkeypatch.setattr(runtime, "latest_tag", lambda force=False: "weekly-test")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return TestClient(app)


def _wait(client, job_id, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_status(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["simc"]["installed"] is True and body["simc"]["tag"] == "weekly-test"
    assert body["simc"]["wow_version"] == "12.1.0.69875" and body["simc"]["update_available"] is False
    assert body["data"]["cached_tables"] == [] or isinstance(body["data"]["cached_tables"], list)
    assert "available" in body["gpu"] and body["threads"] > 0 and "wow_build" in body


def test_import_simc(client, dk_export):
    r = client.post("/api/import/simc", json={"text": dk_export})
    assert r.status_code == 200
    p = r.json()
    assert p["klass"] == "death_knight" and len(p["equipped"]) == 16 and len(p["bags"]) == 5 and len(p["vault"]) == 2
    assert p["equipped"]["head"]["key"] == "equipped:head" and p["imported_at"]
    assert client.post("/api/import/simc", json={"text": "garbage"}).status_code == 400


def test_import_armory(client, monkeypatch):
    import httpx

    from toonopt.api import importer

    payload = {
        "name": "Frostbyte", "realm": "Area 52", "region": "us", "class": "Death Knight", "race": "Human",
        "active_spec_name": "Frost", "active_spec_role": "DPS",
        "gear": {"items": {"head": {"item_id": 271474, "item_level": 334, "name": "Casque", "bonuses": [1, 2], "gems": [], "enchant": None, "icon": "inv_helm"},
                           "mainhand": {"item_id": 268209, "item_level": 344, "name": "Axe", "bonuses": [], "gems": [], "enchant": 3368, "icon": "inv_axe"}}},
        "talentLoadout": {"loadout_text": "CsPAAAA"},
    }

    class Resp:
        status_code = 200

        def json(self):
            return payload

    monkeypatch.setattr(importer.httpx, "get", lambda *a, **k: Resp())
    r = client.get("/api/import/armory", params={"region": "us", "realm": "area-52", "name": "Frostbyte"})
    assert r.status_code == 200
    p = r.json()
    assert p["klass"] == "death_knight" and p["spec"] == "frost" and set(p["equipped"]) == {"head", "main_hand"}
    assert p["equipped"]["main_hand"]["enchant_id"] == 3368 and p["equipped"]["head"]["icon"] == "inv_helm"
    assert 'deathknight="Frostbyte"' not in p["simc_header"] and 'death_knight="Frostbyte"' in p["simc_header"]

    class Missing:
        status_code = 400

        def json(self):
            return {}

    monkeypatch.setattr(importer.httpx, "get", lambda *a, **k: Missing())
    assert client.get("/api/import/armory", params={"region": "us", "realm": "x", "name": "y"}).status_code == 404

    def raise_err(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(importer.httpx, "get", raise_err)
    assert client.get("/api/import/armory", params={"region": "us", "realm": "x", "name": "y"}).status_code == 502


def test_quick_sim_flow(client, dk_export, fake_simc):
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/quick", json={"profile": profile, "options": {"iterations": 100}})
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "quick" and job["character"] == "Frostbyte" and job["spec"] == "frost"
    done = _wait(client, job["id"])
    assert done["status"] == "done", done
    res = client.get(f"/api/jobs/{job['id']}/result").json()
    assert res["job_id"] == job["id"] and res["type"] == "quick" and res["results"] == []
    assert res["baseline"]["dps"] > 0 and res["breakdown"] and res["uptimes"] and res["options"]["iterations"] == 100
    assert res["input_file"] == f"{job['id']}/input.simc" and res["klass"] == "death_knight"
    text = client.get(f"/api/jobs/{job['id']}/input").text
    assert 'deathknight="Frostbyte"' in text and "iterations=100" in text
    html = client.get(f"/api/jobs/{job['id']}/report.html")
    assert html.status_code == 200 and "<html" in html.text and "Frostbyte" in html.text and "<script" not in html.text
    simc_html = client.get(f"/api/jobs/{job['id']}/simc.html")
    assert simc_html.status_code == 200 and "fake simc report" in simc_html.text
    jobs = client.get("/api/jobs").json()
    assert jobs[0]["id"] == job["id"]
    hist = client.get("/api/history").json()
    assert hist[0]["id"] == job["id"] and "dps" in hist[0]["summary"]
    assert client.delete(f"/api/history/{job['id']}").json() == {"ok": True}
    assert client.get(f"/api/jobs/{job['id']}").status_code == 404
    assert client.delete(f"/api/history/{job['id']}").status_code == 404


def test_profileset_sims(client, dk_export, fake_simc):
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/topgear", json={"profile": profile, "options": {}, "candidate_keys": ["bag:5", "vault:1"], "max_combos": 100, "smart": True})
    assert r.status_code == 200
    done = _wait(client, r.json()["id"])
    assert done["status"] == "done", done
    res = client.get(f"/api/jobs/{done['id']}/result").json()
    # the fixture only knows 3 profileset names; rows keep SimC names, labels come from the plan when they match
    assert len(res["results"]) == 3 and res["results"][0]["dps"] >= res["results"][-1]["dps"]
    r = client.post("/api/sims/talentcompare", json={"profile": profile, "loadouts": [{"name": "A", "string": "AAA"}]})
    assert _wait(client, r.json()["id"])["status"] == "done"
    r = client.post("/api/sims/gearcompare", json={"profile": profile, "sets": [{"name": "S", "changes": {"head": profile["bags"][4]}}]})
    assert _wait(client, r.json()["id"])["status"] == "done"
    r = client.post("/api/sims/statweights", json={"profile": profile, "stats": ["strength", "crit", "haste"]})
    done = _wait(client, r.json()["id"])
    res = client.get(f"/api/jobs/{done['id']}/result").json()
    assert res["stat_weights"]["pawn"].startswith("( Pawn: v1:")
    assert "scale_only=strength,crit,haste" in fake_simc[-1]["input"]
    r = client.post("/api/sims/advanced", json={"simc_text": 'warlock="Adv"\nspec=demonology\nlevel=90\n'})
    job = r.json()
    assert job["character"] == "Adv" and job["spec"] == "demonology"
    assert _wait(client, job["id"])["status"] == "done"
    assert client.post("/api/sims/gearcompare", json={"profile": profile, "sets": []}).status_code == 400


def test_dungeon_slice_rejected_for_demon_hunter(client, dk_export):
    """API.md M1: DungeonSlice returns 400 for demon_hunter havoc/vengeance/devourer."""
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    dh_profile = {**profile, "klass": "demon_hunter", "spec": "havoc"}
    r = client.post("/api/sims/quick", json={"profile": dh_profile, "options": {"fight_style": "DungeonSlice"}})
    assert r.status_code == 400 and "DungeonSlice" in r.json()["detail"]
    # unaffected spec is fine
    r = client.post("/api/sims/quick", json={"profile": profile, "options": {"fight_style": "DungeonSlice"}})
    assert r.status_code == 200


def test_droptimizer_503_without_data(client, dk_export, monkeypatch):
    from toonopt.sims import droptimizer

    monkeypatch.setattr(droptimizer, "available", lambda: False)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/droptimizer", json={"profile": profile, "sources": [{"type": "world_boss"}], "upgrade": "drop"})
    assert r.status_code == 503


def test_droptimizer_400_on_invalid_upgrade(client, dk_export, monkeypatch):
    from toonopt.sims import droptimizer

    monkeypatch.setattr(droptimizer, "available", lambda: True)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/droptimizer", json={"profile": profile, "sources": [{"type": "world_boss"}], "upgrade": "bogus"})
    assert r.status_code == 400 and "invalid upgrade value" in r.json()["detail"]


def test_upgrades_503_without_data(client, dk_export, monkeypatch):
    from toonopt.sims import upgrades

    monkeypatch.setattr(upgrades, "available", lambda: False)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/upgrades", json={"profile": profile, "options": {}})
    assert r.status_code == 503


def test_gems_503_without_data(client, dk_export, monkeypatch):
    from toonopt.sims import gems

    monkeypatch.setattr(gems, "available", lambda: False)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/gems", json={"profile": profile, "options": {}, "mode": "uniform"})
    assert r.status_code == 503


def test_gems_400_on_invalid_mode(client, dk_export, monkeypatch):
    from toonopt.sims import gems

    monkeypatch.setattr(gems, "available", lambda: True)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/gems", json={"profile": profile, "options": {}, "mode": "bogus"})
    assert r.status_code == 400


def test_gems_400_on_empty_custom_sets(client, dk_export, monkeypatch):
    from toonopt.sims import gems

    monkeypatch.setattr(gems, "available", lambda: True)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/gems", json={"profile": profile, "options": {}, "mode": "custom", "sets": []})
    assert r.status_code == 400


def test_upgrades_route_happy_path(client, dk_export, fake_simc, monkeypatch):
    """Season/bonus lookups are stubbed at the engine's own hooks (see test_upgrades.py) so
    this exercises only the route -> job -> result plumbing, with the fake_simc runner."""
    from toonopt.sims import upgrades

    monkeypatch.setattr(upgrades, "available", lambda: True)
    monkeypatch.setattr(upgrades, "_current_track", lambda item: {"track": "Hero", "level": 1, "bonus_id": 12841})
    monkeypatch.setattr(upgrades, "_upgrade_path",
                        lambda item: [UpgradeStep(rank=2, ilevel=308, bonus_ids=[12842], crest="Hero Mistcrest", cost=20)])
    monkeypatch.setattr(upgrades, "_max_rank", lambda track: 6)
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    r = client.post("/api/sims/upgrades", json={"profile": profile, "options": {"iterations": 100}, "slots": ["head"]})
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "upgrades"
    done = _wait(client, job["id"])
    assert done["status"] == "done", done
    res = client.get(f"/api/jobs/{job['id']}/result").json()
    # the fake_simc json2_profilesets fixture only knows 3 static profileset names (see
    # test_profileset_sims); labels/meta only attach when a name happens to match the plan
    assert len(res["results"]) == 3


def test_gems_route_happy_path(client, dk_export, fake_simc, monkeypatch):
    from toonopt.sims import gems

    monkeypatch.setattr(gems, "available", lambda: True)
    monkeypatch.setattr(gems, "_data", lambda: (
        types.SimpleNamespace(socket_count=lambda bonus_ids, build=None: 0),
        types.SimpleNamespace(
            best_gems=lambda item, profile: [1] * len(item.gem_ids) if item.gem_ids else [],
            best_enchant=lambda slot, profile: None,
            recommendations=lambda klass, spec: {
                "season": "Test", "gems": {
                    "default": {"id": 1, "name": "Gem", "icon": "", "stat": "mastery"},
                    "by_stat": {"crit": {"id": 11, "name": "Crit Gem", "icon": "", "stat": "crit"}},
                    "unique": [],
                },
                "enchants": {}, "consumables": {},
            },
        ),
    ))
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    profile["equipped"]["neck"]["gem_ids"] = [0]
    r = client.post("/api/sims/gems", json={
        "profile": profile, "options": {"iterations": 100}, "mode": "uniform",
        "gem_pool": [11], "include_enchants": False,
    })
    assert r.status_code == 200
    job = r.json()
    assert job["type"] == "gems"
    done = _wait(client, job["id"])
    assert done["status"] == "done", done
    res = client.get(f"/api/jobs/{job['id']}/result").json()
    assert len(res["results"]) == 3


def test_cancel_and_events(client, job_manager):
    import time as _t

    def slow(ctx):
        for _ in range(200):
            ctx.check_cancelled()
            ctx.progress("baseline", 1, 200, "tick")
            _t.sleep(0.01)
        return {"message": "ok"}

    job = job_manager.submit("data_refresh", slow)
    r = client.post(f"/api/jobs/{job.id}/cancel")
    assert r.status_code == 200
    assert _wait(client, job.id)["status"] == "cancelled"
    with client.stream("GET", f"/api/jobs/{job.id}/events") as s:
        body = "".join(s.iter_text())
    assert "event: failed" in body and '"cancelled"' in body
    assert client.post("/api/jobs/nope/cancel").status_code == 404


def test_settings(client):
    s = client.get("/api/settings").json()
    assert "threads" in s and "simc_tag" in s
    r = client.put("/api/settings", json={"profileset_work_threads": 3})
    assert r.status_code == 200 and r.json()["profileset_work_threads"] == 3
    assert client.get("/api/settings").json()["profileset_work_threads"] == 3
    assert client.put("/api/settings", json={"bogus": 1}).status_code == 400
    assert client.put("/api/settings", json={"threads": "many"}).status_code == 400
    client.put("/api/settings", json={"profileset_work_threads": s["profileset_work_threads"]})


def test_simc_install_route(client, job_manager, monkeypatch):
    from pathlib import Path

    from toonopt.api import status as status_api
    from toonopt.simc import runtime

    def fake_install(tag, cb):
        cb("Downloading weekly-test", 50, 100)
        return runtime.InstalledSimc(Path("simc.exe"), tag or "weekly-test", "v", "1210-01", "12.1.0")

    monkeypatch.setattr(status_api.runtime, "install", fake_install)
    job = client.post("/api/simc/install", json={}).json()
    assert job["type"] == "simc_install"
    assert _wait(client, job["id"])["status"] == "done"
    assert client.get(f"/api/jobs/{job['id']}/result").status_code == 404     # not a sim result
