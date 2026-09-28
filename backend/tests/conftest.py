from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_data_layer(monkeypatch):
    """Unit tests exercise the bare parser; the data layer is another agent's module."""
    import sys

    monkeypatch.setitem(sys.modules, "toonopt.data.items", None)
    monkeypatch.setitem(sys.modules, "toonopt.data.season", None)
    monkeypatch.setitem(sys.modules, "toonopt.data.currencies", None)


@pytest.fixture(autouse=True)
def isolated_character_store(tmp_path, monkeypatch):
    """Sandbox the Characters/Reports stores so importing a profile in a test never writes
    into the real repo's ``characters/``/``reports/`` directories."""
    from toonopt import characters, reports

    monkeypatch.setattr(characters, "CHARACTERS_DIR", tmp_path / "characters")
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def real_data_layer(monkeypatch):
    """Undo the autouse ``no_data_layer`` stub for tests that need the real DB2-backed data
    layer (e.g. class/weapon/armour legality, which isn't derivable from a bare parsed
    Item at all). Skipped when the cache hasn't been downloaded."""
    import sys

    from toonopt.data import wago

    if not wago.is_ready():
        pytest.skip("DB2 cache not downloaded (POST /api/data/refresh)")
    monkeypatch.delitem(sys.modules, "toonopt.data.items", raising=False)
    monkeypatch.delitem(sys.modules, "toonopt.data.season", raising=False)
    monkeypatch.delitem(sys.modules, "toonopt.data.currencies", raising=False)


@pytest.fixture
def dk_export() -> str:
    return (FIXTURES / "export_dk_frost.simc").read_text("utf-8")


@pytest.fixture
def warrior_export() -> str:
    return (FIXTURES / "export_warrior_arms.simc").read_text("utf-8")


@pytest.fixture
def mage_export() -> str:
    return (FIXTURES / "export_mage_frost.simc").read_text("utf-8")


@pytest.fixture
def dk_profile(dk_export):
    from toonopt.simc import profile

    return profile.parse(dk_export)


@pytest.fixture
def dk_unforged_export() -> str:
    """Copy of ``export_dk_frost.simc`` with main_hand's Voidforge bonus (13848) swapped back
    for the Myth 6/6 track bonus (12854, ilvl 334) so the Upgrades Voidforge step and the Top
    Gear voidforge variant can actually be exercised (the base fixture is already Voidforged
    on every eligible slot)."""
    return (FIXTURES / "export_dk_frost_unforged.simc").read_text("utf-8")


@pytest.fixture
def dk_unforged_profile(dk_unforged_export):
    from toonopt.simc import profile

    return profile.parse(dk_unforged_export)


@pytest.fixture
def hunter_mm_export() -> str:
    """Anonymized real-world hunter export (name/realm scrubbed to Testhunter/testrealm;
    gear, talents, saved loadouts and currencies are untouched) -- used by tests that used
    to read a saved character profile or job history snapshot from ``characters/`` or
    ``history/``, which only ever exist on the original developer's machine."""
    return (FIXTURES / "export_hunter_mm.simc").read_text("utf-8")


@pytest.fixture
def hunter_mm_profile(hunter_mm_export):
    from toonopt.simc import profile

    return profile.parse(hunter_mm_export)


def load_fixture_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text("utf-8"))


@pytest.fixture
def job_manager(tmp_path, monkeypatch):
    """A JobManager on temp dirs, swapped into every module that imported the global one."""
    from toonopt import jobs
    from toonopt.api import history, sims, status
    from toonopt.api import jobs as jobs_api

    mgr = jobs.JobManager(tmp_path / "history", tmp_path / "work")
    for mod in (jobs, sims, jobs_api, history, status):
        monkeypatch.setattr(mod, "manager", mgr)
    return mgr


@pytest.fixture
def fake_simc(monkeypatch, tmp_path):
    """Replace runner.run with a stub that drops a json2 fixture in the workdir.

    The stub picks the profilesets fixture when the input has profilesets, the
    scale-factor one when it asks for scale factors, otherwise the pets one.
    """
    from toonopt.simc import runner, runtime

    calls: list[dict] = []
    monkeypatch.setattr(runtime, "installed", lambda: runtime.InstalledSimc(
        Path("simc.exe"), "weekly-test", "SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live", "1210-01", "12.1.0.69875"))

    def fake_run(input_text, workdir, threads=None, progress_cb=None, cancel_event=None, *, html=False,
                 input_name="input.simc", json_name="out.json"):
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / input_name).write_text(input_text, "utf-8")
        if "profileset." in input_text:
            src = "json2_profilesets.json"
        elif "calculate_scale_factors=1" in input_text:
            src = "json2_scalefactors.json"
        else:
            src = "json2_pets.json"
        shutil.copyfile(FIXTURES / src, workdir / json_name)
        stdout = (FIXTURES / src.replace(".json", "_stdout.txt")).read_text("utf-8", "replace")
        if progress_cb:
            progress_cb("baseline", 500, 1000, "half")
            progress_cb("baseline", 1000, 1000, "done")
        calls.append({"input": input_text, "workdir": workdir, "threads": threads})
        html_path = None
        if html:
            from pathlib import Path

            html_path = workdir / (Path(json_name).stem + ".html")
            html_path.write_text("<html><body>fake simc report</body></html>", "utf-8")
        return runner.RunOutput(workdir / json_name, html_path, stdout, 0.5, 0, workdir / input_name)

    monkeypatch.setattr(runner, "run", fake_run)
    return calls


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: needs an installed SimC binary (slow)")
    config.addinivalue_line("markers", "slow: takes more than ~10s (e.g. a real training loop)")
