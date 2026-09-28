from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from toonopt.models import Baseline, Job, ResultRow, SimResult


def _wait(mgr, job_id, timeout=10.0):
    """Wait for a job to reach a terminal status AND for its history artifacts to be
    fully persisted.

    ``JobManager._execute`` flips ``job.status`` to done/failed/cancelled *before* it
    calls ``_persist`` (so progress/status can be observed promptly by SSE clients),
    which means a caller that only polls ``job.status`` can race ``_persist`` and see
    a terminal status with ``history/<id>/`` not fully written yet (e.g. ``simc.html``
    still missing). ``_persist`` writes ``job.json`` last specifically as a "finished
    persisting" sentinel (see its docstring) -- wait for that too.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = mgr.get(job_id)
        if job.status in ("done", "failed", "cancelled") and (mgr.job_dir(job_id) / "job.json").exists():
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_submit_persist_history(job_manager, tmp_path):
    def run(ctx):
        ctx.progress("baseline", 5, 10, "half")
        (ctx.workdir / "input.simc").write_text("mage=\"x\"\n", "utf-8")
        res = SimResult(job_id=ctx.job.id, type="quick", character="X", baseline=Baseline(dps=1234.5))
        res.results = [ResultRow(name="a", label="A", dps=1300.0, delta=65.5, delta_pct=5.3)]
        return res

    job = job_manager.submit("quick", run, character="X", spec="frost")
    assert job.status == "queued" and job.type == "quick"
    done = _wait(job_manager, job.id)
    assert done.status == "done" and done.progress.pct == 100.0 and done.started and done.finished
    d = job_manager.job_dir(job.id)
    assert (d / "job.json").exists() and (d / "result.json").exists() and (d / "report.html").exists()
    assert (d / "input.simc").read_text("utf-8").startswith('mage="x"')
    assert not (tmp_path / "work" / job.id).exists()
    assert job_manager.sim_result(job.id).baseline.dps == 1234.5
    hist = job_manager.history()
    assert hist[0]["id"] == job.id and "1,234 dps" in hist[0]["summary"] and "best A" in hist[0]["summary"]
    assert json.loads((d / "job.json").read_text())["status"] == "done"
    # reload from disk in a fresh manager
    from toonopt.jobs import JobManager

    mgr2 = JobManager(job_manager.history_dir, job_manager.work_dir)
    assert mgr2.get(job.id).status == "done" and mgr2.sim_result(job.id).baseline.dps == 1234.5
    assert job_manager.delete(job.id) and job_manager.get(job.id) is None and not d.exists()


def test_run_simc_requests_html_and_report_details(job_manager, fake_simc, monkeypatch):
    """API.md M6: every job's SimC invocation asks for the native HTML report plus
    report_details=1, and the resulting simc.html is persisted alongside the other
    per-job artifacts."""
    captured: dict = {}

    def run(ctx):
        out = ctx.run_simc('mage="x"\nspec=fire\nlevel=80\nrole=attack\n')
        captured["html_path"] = out.html_path
        return {"message": "ok"}

    job = job_manager.submit("quick", run)
    _wait(job_manager, job.id)
    assert fake_simc[-1]["input"].count("report_details=1") == 1
    d = job_manager.job_dir(job.id)
    assert (d / "simc.html").exists()
    assert (d / "simc.html").read_text("utf-8") == "<html><body>fake simc report</body></html>"


def test_failure_and_cancel(job_manager):
    def boom(ctx):
        raise RuntimeError("kaboom")

    job = _wait(job_manager, job_manager.submit("quick", boom).id)
    assert job.status == "failed" and "kaboom" in job.error
    assert job_manager.history()[0]["summary"] == "kaboom"

    gate = {"go": False}

    def slow(ctx):
        while not gate["go"]:
            ctx.check_cancelled()
            time.sleep(0.01)
        return {"message": "ok"}

    j1 = job_manager.submit("data_refresh", slow)
    j2 = job_manager.submit("data_refresh", slow)
    time.sleep(0.1)
    assert job_manager.get(j1.id).status == "running" and job_manager.get(j2.id).status == "queued"
    assert job_manager.cancel(j2.id).status == "cancelled"
    job_manager.cancel(j1.id)
    assert _wait(job_manager, j1.id).status == "cancelled"
    assert job_manager.list_jobs()[0].id == j2.id      # newest first


def test_concurrent_submit_starts_only_one_worker(tmp_path, monkeypatch):
    """Regression: _ensure_worker() used to run outside the lock, so two submit() calls
    racing the "is a worker already running?" check could both decide to start one."""
    from toonopt.jobs import JobManager

    mgr = JobManager(tmp_path / "history", tmp_path / "work")
    started: list[threading.Thread] = []
    real_ensure_worker = mgr._ensure_worker

    def racy_ensure_worker() -> None:
        # widen the check-then-act window the old, unlocked version was exposed to
        if mgr._worker is None or not mgr._worker.is_alive():
            time.sleep(0.02)
        real_ensure_worker()
        if mgr._worker is not None:
            started.append(mgr._worker)

    monkeypatch.setattr(mgr, "_ensure_worker", racy_ensure_worker)

    barrier = threading.Barrier(6)

    def submit_one() -> None:
        barrier.wait(timeout=5)
        mgr.submit("quick", lambda ctx: None)

    threads = [threading.Thread(target=submit_one) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len({id(t) for t in started}) == 1, "more than one worker thread was started"


def test_load_history_demotes_done_job_missing_result(tmp_path):
    """A 'done' job whose result.json is missing (e.g. the process died mid-persist)
    should surface as failed, not as a done job whose /result 404s."""
    from toonopt.jobs import JobManager

    history = tmp_path / "history"
    d = history / "abc123"
    d.mkdir(parents=True)
    job = Job(id="abc123", type="quick", status="done")
    (d / "job.json").write_text(job.model_dump_json(), "utf-8")

    mgr = JobManager(history, tmp_path / "work")
    loaded = mgr.get("abc123")
    assert loaded is not None
    assert loaded.status == "failed"
    assert loaded.error == "result missing"


def test_load_history_keeps_done_job_with_result(tmp_path):
    from toonopt.jobs import JobManager

    history = tmp_path / "history"
    d = history / "def456"
    d.mkdir(parents=True)
    job = Job(id="def456", type="quick", status="done")
    (d / "job.json").write_text(job.model_dump_json(), "utf-8")
    (d / "result.json").write_text(json.dumps({"message": "ok"}), "utf-8")

    mgr = JobManager(history, tmp_path / "work")
    assert mgr.get("def456").status == "done"


def test_persist_writes_result_and_profile_before_job_json(job_manager, monkeypatch):
    """job.json is the marker _load_history trusts; every other artifact must land first."""
    write_order: list[str] = []
    orig_write_text = Path.write_text

    def spy_write_text(self, *a, **k):
        if self.name in ("job.json", "result.json", "profile.json"):
            write_order.append(self.name)
        return orig_write_text(self, *a, **k)

    monkeypatch.setattr(Path, "write_text", spy_write_text)
    job = job_manager.submit("quick", lambda ctx: {"message": "ok"})
    _wait(job_manager, job.id)

    assert write_order and write_order[-1] == "job.json"
    assert write_order.index("result.json") < write_order.index("job.json")


def test_cancel_queued_job_broadcasts_once(job_manager):
    """Regression: cancel() used to broadcast "failed" itself for a queued job, and then
    _execute() broadcast "failed" again once it dequeued it -- two terminal SSE events
    for one cancelled job."""
    events: list[tuple[str, str]] = []
    orig_broadcast = job_manager._broadcast

    def spy_broadcast(event, job):
        events.append((event, job.id))
        return orig_broadcast(event, job)

    job_manager._broadcast = spy_broadcast

    gate = {"go": False}

    def slow(ctx):
        while not gate["go"]:
            ctx.check_cancelled()
            time.sleep(0.01)
        return {"message": "ok"}

    j1 = job_manager.submit("data_refresh", slow)
    j2 = job_manager.submit("data_refresh", slow)
    time.sleep(0.1)
    assert job_manager.get(j2.id).status == "queued"
    assert job_manager.cancel(j2.id).status == "cancelled"

    gate["go"] = True
    _wait(job_manager, j1.id)
    _wait(job_manager, j2.id)

    terminal_for_j2 = [e for e in events if e[1] == j2.id and e[0] in ("done", "failed")]
    assert len(terminal_for_j2) == 1


def test_sse_broadcast(job_manager):
    async def main():
        q = job_manager.subscribe("pending")
        events = []

        def run(ctx):
            ctx.progress("baseline", 1, 2, "x")
            return {"message": "done"}

        # subscribe to the real id once we have it
        job = job_manager.submit("simc_install", run)
        q = job_manager.subscribe(job.id)
        while True:
            ev, payload = await asyncio.wait_for(q.get(), timeout=5)
            events.append((ev, payload["status"], payload["progress"]["phase"]))
            if ev in ("done", "failed"):
                break
        job_manager.unsubscribe(job.id, q)
        return events

    events = asyncio.run(main())
    assert events[-1][0] == "done" and events[-1][1] == "done"
    assert any(e[0] == "progress" for e in events)
