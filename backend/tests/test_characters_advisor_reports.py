"""Characters store, Advisor engine and Reports store (see API.md "Characters, Advisor, Reports")."""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from toonopt.models import CharacterProfile, CharacterReport, Item

# ---------------------------------------------------------------------------
# Characters


def _profile(name="Testhunter", realm="testrealm", **kw) -> CharacterProfile:
    base = {"name": name, "realm": realm, "klass": "hunter", "spec": "marksmanship"}
    base.update(kw)
    return CharacterProfile(**base)


def test_slugify_ascii_lowercase():
    from toonopt import characters

    assert characters.slugify("Testhunter", "testrealm") == "testhunter-testrealm"
    assert characters.slugify("Thérèse", "Aréas") == "therese-areas"


def test_save_list_get_delete_roundtrip(tmp_path, monkeypatch):
    from toonopt import characters

    monkeypatch.setattr(characters, "CHARACTERS_DIR", tmp_path / "characters")
    profile = _profile(equipped={"head": Item(key="equipped:head", id=1, slot="head", ilevel=300)})
    slug = characters.save(profile)
    assert slug == "testhunter-testrealm"

    summaries = characters.list_characters()
    assert len(summaries) == 1
    assert summaries[0].slug == slug
    assert summaries[0].ilevel_equipped == 300

    loaded = characters.get(slug)
    assert loaded is not None and loaded.name == "Testhunter"

    assert characters.get("nope") is None
    assert characters.delete(slug) is True
    assert characters.get(slug) is None
    assert characters.delete(slug) is False


def test_save_keeps_last_10_history_snapshots(tmp_path, monkeypatch):
    from toonopt import characters

    monkeypatch.setattr(characters, "CHARACTERS_DIR", tmp_path / "characters")
    for i in range(15):
        profile = _profile(imported_at=f"2026-01-01T00:00:{i:02d}+00:00")
        characters.save(profile)
    hdir = tmp_path / "characters" / "testhunter-testrealm.history"
    assert len(list(hdir.glob("*.json"))) == characters.MAX_HISTORY


def test_backfill_seeds_from_newest_history_profile(tmp_path, monkeypatch):
    from toonopt import characters

    history_dir = tmp_path / "history"
    (history_dir / "job1").mkdir(parents=True)
    (history_dir / "job2").mkdir(parents=True)
    old = _profile(imported_at="2026-01-01T00:00:00+00:00")
    new = _profile(imported_at="2026-06-01T00:00:00+00:00", level=90)
    (history_dir / "job1" / "profile.json").write_text(old.model_dump_json(), "utf-8")
    (history_dir / "job2" / "profile.json").write_text(new.model_dump_json(), "utf-8")

    monkeypatch.setattr(characters, "CHARACTERS_DIR", tmp_path / "characters")
    monkeypatch.setattr(characters, "HISTORY_DIR", history_dir)

    n = characters.backfill()
    assert n == 1
    loaded = characters.get("testhunter-testrealm")
    assert loaded is not None and loaded.level == 90

    # backfill is a no-op once the store is non-empty
    assert characters.backfill() == 0


def test_import_simc_saves_character(tmp_path, monkeypatch, dk_export):
    """API.md hook: a successful /api/import/simc save()s the profile to the store."""
    from toonopt import characters
    from toonopt.api import importer

    monkeypatch.setattr(characters, "CHARACTERS_DIR", tmp_path / "characters")
    profile = importer.import_simc(importer.ImportRequest(text=dk_export))
    slug = characters.slugify(profile.name, profile.realm)
    assert characters.get(slug) is not None


# ---------------------------------------------------------------------------
# Reports


def _report(**kw) -> CharacterReport:
    base = {"slug": "testhunter-testrealm", "character": "Testhunter", "realm": "testrealm", "klass": "hunter", "spec": "marksmanship"}
    base.update(kw)
    return CharacterReport(**base)


def test_validate_report_rejects_unknown_kind():
    from toonopt import reports

    report = _report(sections=[{"kind": "bogus", "title": "x"}])
    with pytest.raises(reports.ReportValidationError):
        reports.validate_report(report)


def test_validate_report_rejects_malformed_upgrades_section():
    from toonopt import reports

    report = _report(sections=[{"kind": "upgrades", "title": "Upgrades", "rows": [{"slot": "head"}]}])
    with pytest.raises(reports.ReportValidationError):
        reports.validate_report(report)


def test_validate_report_accepts_every_kind():
    from toonopt import reports

    report = _report(sections=[
        {"kind": "markdown", "title": "Summary", "body": "Some *markdown* text."},
        {"kind": "upgrades", "title": "Upgrades", "rows": [
            {"slot": "head", "current": "Old Helm (285)", "option": "New Helm (308)",
             "verdict": "obvious", "gain": "+23 ilvl", "how": ["Heroic Tidebound Grotto"]},
        ]},
        {"kind": "bis", "title": "BiS list", "rows": [
            {"slot": "head", "item": Item(key="drop:1:head", id=1, slot="head", ilevel=320).model_dump(),
             "source": "Mythic Boss", "you_have": False},
        ]},
        {"kind": "talents", "title": "Talents", "entries": [
            {"context": "Single target", "loadout": "ABCDEF", "notes": "Standard build"},
        ]},
        {"kind": "kv", "title": "Stat priority", "items": [{"label": "Crit", "value": "1.0"}]},
    ])
    reports.validate_report(report)  # does not raise


def test_reports_save_get_history_and_markdown(tmp_path, monkeypatch):
    from toonopt import reports

    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    report = _report(summary="First pass.", sections=[{"kind": "markdown", "title": "Notes", "body": "Body text"}])
    saved = reports.save("testhunter-testrealm", report)
    assert saved.updated_at

    loaded = reports.get("testhunter-testrealm")
    assert loaded is not None and loaded.summary == "First pass."

    md = (tmp_path / "reports" / "testhunter-testrealm.md").read_text("utf-8")
    assert "Testhunter" in md and "Notes" in md and "Body text" in md

    hist = json.loads((tmp_path / "reports" / "testhunter-testrealm.history.json").read_text("utf-8"))
    assert hist == [{"updated_at": saved.updated_at, "summary": "First pass."}]

    listed = reports.list_reports()
    assert listed and listed[0]["slug"] == "testhunter-testrealm"

    assert reports.delete("testhunter-testrealm") is True
    assert reports.get("testhunter-testrealm") is None


def test_reports_save_rejects_invalid_section(tmp_path, monkeypatch):
    from toonopt import reports

    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    report = _report(sections=[{"kind": "kv", "title": "x", "items": "not-a-list"}])
    with pytest.raises(reports.ReportValidationError):
        reports.save("testhunter-testrealm", report)


def test_reports_history_keeps_last_20(tmp_path, monkeypatch):
    from toonopt import reports

    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    for i in range(25):
        reports.save("testhunter-testrealm", _report(summary=f"pass {i}"))
    hist = reports.history("testhunter-testrealm")
    assert len(hist) == 20
    assert hist[0]["summary"] == "pass 24"  # newest first


# ---------------------------------------------------------------------------
# Advisor (needs the real DB2-backed data layer)
#
# Uses ``hunter_mm_profile`` (tests/fixtures/export_hunter_mm.simc, conftest.py): an
# anonymized copy of a real hunter export (gear/talents/currencies untouched, name/realm
# scrubbed to Testhunter/testrealm) so these tests are reproducible on any checkout instead
# of depending on this machine's history/characters directories.


def test_advisor_stat_priority_from_recommendation(real_data_layer, hunter_mm_export):
    from toonopt import advisor
    from toonopt.data import loot, season
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export)
    notes: list[str] = []
    sp = advisor.stat_priority_for(profile, season, loot, notes)
    assert sp.source in ("statweights_job", "recommendation")
    assert sp.order and sp.order[0] in ("agility", "strength", "intellect") or sp.weights
    if sp.source == "recommendation":
        assert notes  # cites the heuristic, per API.md
        assert sp.weights is not None and sp.weights.get("agility") == pytest.approx(1.2)


def test_advisor_evaluate_hunter_smoke(real_data_layer, hunter_mm_export):
    """End-to-end smoke test against the anonymized real hunter profile: structure + <10s
    budget (API.md: "must run in < 10s for a real profile")."""
    from toonopt import advisor
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export)
    t0 = time.time()
    result = advisor.evaluate(profile, "testhunter-testrealm")
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"advisor.evaluate took {elapsed:.1f}s"

    assert result.slug == "testhunter-testrealm"
    assert result.character == "Testhunter"
    assert {s.slot for s in result.slots} == set(profile.equipped.keys())
    assert result.tier.set_id is not None
    assert result.tier.equipped_pieces >= 1
    assert result.sim_plan.droptimizer
    for slot in result.slots:
        assert len(slot.candidates) <= advisor.MAX_CANDIDATES_PER_SLOT
        for c in slot.candidates:
            assert c.verdict != "downgrade"  # default include_downgrades=False

    # a second call for the same spec/sources should be fast (candidate cache hit)
    t1 = time.time()
    advisor.evaluate(profile, "testhunter-testrealm")
    assert time.time() - t1 < 3.0


def test_advisor_include_downgrades_option(real_data_layer, hunter_mm_export):
    from toonopt import advisor
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export)
    result = advisor.evaluate(profile, "testhunter-testrealm", include_downgrades=True)
    # with downgrades included the option must at least not crash and may surface some
    assert isinstance(result.slots, list)


def test_advisor_tier_reason_on_losing_4pc(real_data_layer, hunter_mm_export):
    from toonopt import advisor
    from toonopt.data import loot, season
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export)
    tier_set_id = season.catalyst_set_id(loot.normalize_class(profile.klass))
    head = profile.equipped["head"]
    assert head.set_id == tier_set_id  # this hunter has all 5 tier pieces; head is one of them

    non_tier_head = head.model_copy(update={"id": 999999, "set_id": None, "key": "test:non-tier-head"})
    rc = advisor.RawCandidate(item=non_tier_head, effort="easy", weekly=False, path=[])
    tier_slots = set(season.catalyst().get("tier_slots", []))
    candidate = advisor._build_candidate(
        rc, "head", head, 0.0, {}, "agility", tier_set_id, tier_slots, 4, 6, season,
    )
    assert "loses 4pc" in candidate.reasons
    assert candidate.verdict == "sim_to_confirm"


def test_advisor_crafted_gear_is_one_candidate_per_tier(real_data_layer, hunter_mm_export):
    """API.md/advisor brief: crafted gear is a ladder (305 Spark-only / 318 Hero crests / 331
    Myth crests this season), not a single flat "Crafted gear <max ilvl>" candidate. This
    hunter owns Myth 40, Champion 60, Veteran 100, Hero 20, and Spark of Tides 2, so the 305
    tier (Spark only) is fully affordable and the 331 tier (max) is not -- exactly the "best
    affordable tier plus the max tier" pair the cap should keep."""
    from toonopt import advisor
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export)
    result = advisor.evaluate(profile, "testhunter-testrealm")

    slot = next(s for s in result.slots if s.slot == "feet")
    crafted = [c for c in slot.candidates if c.source.type == "crafted"]
    assert len(crafted) == 2, [c.item.ilevel for c in crafted]

    by_ilevel = {c.item.ilevel: c for c in crafted}
    assert set(by_ilevel) == {305, 331}

    base = by_ilevel[305]
    assert base.source.effort == "trivial"
    assert [s.step for s in base.path] == ["Craft with 1 Spark of Tides (305)"]
    assert not any("needs" in r for r in base.reasons)

    top = by_ilevel[331]
    assert top.source.effort in ("hard", "medium")
    assert [s.step for s in top.path] == [
        "Craft with 1 Spark of Tides (305)",
        "+80 Hero Mistcrest → 318",
        "+80 Myth Mistcrest → 331",
    ]
    assert "needs 60 more Hero Mistcrest" in top.reasons
    assert "needs 40 more Myth Mistcrest" in top.reasons

    # same underlying crafted item id, distinguishable acquisition-path keys
    assert base.item.id == top.item.id
    assert base.item.key != top.item.key


def test_advisor_marksmanship_default_stat_order_is_crit_mastery_vers_haste():
    """Current guides (checked 2026-09): MM's secondary priority is crit > mastery >
    versatility > haste, not the generic crit-first bucket's crit/haste/mastery/versatility."""
    from toonopt import advisor

    assert advisor._default_secondary_order("hunter_marksmanship") == [
        "crit", "mastery", "versatility", "haste",
    ]


# ---------------------------------------------------------------------------
# API routes


@pytest.fixture
def client(monkeypatch, tmp_path):
    from toonopt import config
    from toonopt.main import app

    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    return TestClient(app)


def test_characters_api_roundtrip(client, dk_export):
    from toonopt.characters import slugify

    assert client.get("/api/characters").json() == []
    profile = client.post("/api/import/simc", json={"text": dk_export}).json()
    slug = slugify(profile["name"], profile["realm"])

    listed = client.get("/api/characters").json()
    assert any(c["slug"] == slug for c in listed)

    got = client.get(f"/api/characters/{slug}")
    assert got.status_code == 200 and got.json()["name"] == profile["name"]

    assert client.get("/api/characters/nope").status_code == 404
    assert client.delete(f"/api/characters/{slug}").json() == {"ok": True}
    assert client.get(f"/api/characters/{slug}").status_code == 404
    assert client.delete(f"/api/characters/{slug}").status_code == 404


def test_reports_api_roundtrip(client):
    body = {
        "slug": "x", "character": "Frostbyte", "realm": "Area 52", "klass": "death_knight", "spec": "frost",
        "summary": "Looking solid.", "sections": [{"kind": "kv", "title": "Stats", "items": [{"label": "ilvl", "value": "320"}]}],
    }
    assert client.get("/api/reports/frostbyte-area-52").status_code == 404
    r = client.put("/api/reports/frostbyte-area-52", json=body)
    assert r.status_code == 200 and r.json()["slug"] == "frostbyte-area-52"

    got = client.get("/api/reports/frostbyte-area-52")
    assert got.status_code == 200 and got.json()["summary"] == "Looking solid."

    listed = client.get("/api/reports").json()
    assert any(x["slug"] == "frostbyte-area-52" for x in listed)

    bad = {**body, "sections": [{"kind": "kv", "title": "x"}]}   # missing 'items'
    assert client.put("/api/reports/frostbyte-area-52", json=bad).status_code == 400

    assert client.delete("/api/reports/frostbyte-area-52").json() == {"ok": True}
    assert client.get("/api/reports/frostbyte-area-52").status_code == 404


def test_advisor_api_requires_slug_or_profile(client):
    r = client.post("/api/advisor/obvious-upgrades", json={})
    assert r.status_code in (400, 503)  # 503 first if the data cache genuinely isn't ready


def test_advisor_api_unknown_slug_404(client, real_data_layer):
    r = client.post("/api/advisor/obvious-upgrades", json={"slug": "does-not-exist"})
    assert r.status_code == 404


def test_advisor_api_with_inline_profile(client, real_data_layer, hunter_mm_export):
    from toonopt.simc import profile as profile_mod

    profile = profile_mod.parse(hunter_mm_export).model_dump(mode="json")
    r = client.post("/api/advisor/obvious-upgrades", json={"profile": profile})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["character"] == "Testhunter" and body["slots"]
