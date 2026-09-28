"""In-process job manager: one worker thread, one SimC process at a time.

``submit(job_type, run_fn)`` queues ``run_fn(ctx)``; the function returns either a
:class:`SimResult` (sim jobs) or a JSON-serialisable dict (install/refresh jobs).
Finished jobs are persisted to ``HISTORY_DIR/<id>/`` as ``job.json``, ``result.json``,
``input.simc``, ``out.json``, ``report.html`` and, when ``submit()`` was given a
``profile``, ``profile.json`` (the input :class:`CharacterProfile`, added so
``toonopt.surrogate.dataset`` can reconstruct the exact gear set for every past result
row -- earlier history recorded before this field existed has no ``profile.json`` and is
skipped by the dataset builder). Progress is broadcast to SSE subscribers through
per-subscriber asyncio queues.
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import shutil
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from toonopt.config import HISTORY_DIR, WORK_DIR, settings
from toonopt.models import (
    CharacterProfile,
    Job,
    JobType,
    Progress,
    SimOptions,
    SimResult,
    now_iso,
)
from toonopt.simc import results as results_mod
from toonopt.simc import runner

log = logging.getLogger(__name__)


class JobCancelled(Exception):
    pass


class JobContext:
    """What a job's run function gets: progress reporting, cancel flag and a SimC runner."""

    def __init__(self, manager: JobManager, job: Job, workdir: Path, profile: CharacterProfile | None = None):
        self.manager = manager
        self.job = job
        self.workdir = workdir
        self.profile = profile
        self.cancel_event = threading.Event()
        self.last_run: runner.RunOutput | None = None
        self._stage = 0

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled()

    def progress(self, phase: str, current: int = 0, total: int = 0, message: str = "") -> None:
        pct = (100.0 * current / total) if total else 0.0
        self.job.progress = Progress(phase=phase, current=current, total=total, pct=round(pct, 1), message=message)
        self.manager._broadcast("progress", self.job)

    def run_simc(self, simc_text: str, *, stage_label: str = "", threads: int | None = None,
                 html: bool = True) -> runner.RunOutput:
        """Run SimC in this job's workdir; progress phases are prefixed with *stage_label*.

        Always requests SimC's own HTML report (``html=True``) plus ``report_details=1`` in
        the input text, so every job's native report can be served from
        ``GET /api/jobs/{id}/simc.html`` (API.md "Raidbots parity, wave 1" M6).
        """
        self.check_cancelled()
        self._stage += 1
        prefix = f"{stage_label}: " if stage_label else ""

        def cb(phase: str, cur: int, total: int, msg: str) -> None:
            self.progress(prefix + phase, cur, total, msg)

        text = runner.ensure_report_details(simc_text)
        out = runner.run(
            text, self.workdir, threads or settings.threads, cb, self.cancel_event, html=html,
            input_name=f"input{'' if self._stage == 1 else '_' + str(self._stage)}.simc",
            json_name=f"out{'' if self._stage == 1 else '_' + str(self._stage)}.json",
        )
        self.last_run = out
        return out

    def sim(self, simc_text: str, options: SimOptions, *, klass: str = "", spec: str = "",
            stage_label: str = "") -> SimResult:
        """Run SimC and parse json2 into a SimResult with job fields filled in."""
        out = self.run_simc(simc_text, stage_label=stage_label, threads=options.threads)
        self.progress("parsing", 0, 0, "Parsing results")
        res = results_mod.parse_file(out.json_path, out.stdout, klass=klass, spec=spec, metric=options.metric)
        res.job_id = self.job.id
        res.type = self.job.type
        if self.job.character:
            res.character = self.job.character
        res.options = options
        res.input_file = f"{self.job.id}/{out.input_path.name}" if out.input_path else ""
        if out.seconds and not res.timing.seconds:
            res.timing.seconds = out.seconds
        return res


RunFn = Callable[[JobContext], Any]


class JobManager:
    def __init__(self, history_dir: Path = HISTORY_DIR, work_dir: Path = WORK_DIR):
        self.history_dir = history_dir
        self.work_dir = work_dir
        self._jobs: dict[str, Job] = {}
        self._results: dict[str, Any] = {}
        self._contexts: dict[str, JobContext] = {}
        self._seq: dict[str, int] = {}
        self._queue: queue.Queue[tuple[str, RunFn] | None] = queue.Queue()
        self._subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._load_history()

    # ---- lifecycle -----------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._loop, name="toonopt-jobs", daemon=True)
            self._worker.start()

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            job_id, fn = item
            try:
                self._execute(job_id, fn)
            except Exception:                    # pragma: no cover - last-resort guard
                log.exception("job %s crashed the worker", job_id)

    def _execute(self, job_id: str, fn: RunFn) -> None:
        job = self._jobs[job_id]
        ctx = self._contexts[job_id]
        if ctx.cancelled:
            job.status = "cancelled"
            job.finished = now_iso()
            self._persist(job, None, ctx)
            self._broadcast("failed", job)
            return
        job.status = "running"
        job.started = now_iso()
        ctx.progress("starting", 0, 0, "Starting")
        try:
            result = fn(ctx)
            if ctx.cancelled:
                raise JobCancelled()
            job.status = "done"
            job.progress = Progress(phase="done", current=1, total=1, pct=100.0, message="Finished")
            self._results[job_id] = result
        except (JobCancelled, runner.SimcCancelled):
            job.status = "cancelled"
            job.error = "cancelled"
            result = None
        except Exception as e:  # noqa: BLE001 - job failures are reported, not raised
            log.error("job %s failed: %s\n%s", job_id, e, traceback.format_exc())
            job.status = "failed"
            job.error = str(e)[:2000]
            result = None
        job.finished = now_iso()
        try:
            self._persist(job, result, ctx)
        except Exception:
            log.exception("persisting job %s failed", job_id)
        self._broadcast("done" if job.status == "done" else "failed", job)

    # ---- public API ----------------------------------------------------------------
    def submit(self, job_type: JobType, run_fn: RunFn, *, character: str | None = None,
               spec: str | None = None, profile: CharacterProfile | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], type=job_type, character=character, spec=spec)
        workdir = self.work_dir / job.id
        workdir.mkdir(parents=True, exist_ok=True)
        ctx = JobContext(self, job, workdir, profile=profile)
        with self._lock:
            self._jobs[job.id] = job
            self._contexts[job.id] = ctx
            self._seq[job.id] = len(self._seq)
            # Both the check-and-start in _ensure_worker and the queue put must happen
            # while holding the lock: two concurrent submit() calls racing the "is there
            # already a live worker?" check outside the lock could otherwise both decide
            # to start one, leaving two worker threads (and so two simc.exe) running.
            self._ensure_worker()
            self._queue.put((job.id, run_fn))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: (j.created, self._seq.get(j.id, -1)), reverse=True)

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        ctx = self._contexts.get(job_id)
        if job.status in ("queued", "running") and ctx is not None:
            ctx.cancel_event.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.finished = now_iso()
                # Don't broadcast here: the queue entry is still there, so the worker will
                # dequeue it, see ctx.cancelled, and persist + broadcast "failed" itself
                # (JobManager._execute) once it gets to it. Broadcasting from both places
                # sent two terminal events for the same cancelled-while-queued job.
        return job

    def result(self, job_id: str) -> Any | None:
        if job_id in self._results:
            return self._results[job_id]
        p = self.history_dir / job_id / "result.json"
        if p.exists():
            data = json.loads(p.read_text("utf-8"))
            job = self._jobs.get(job_id)
            if job and job.type not in ("simc_install", "data_refresh"):
                try:
                    data = SimResult.model_validate(data)
                except ValueError:
                    log.warning("result.json for %s is not a SimResult", job_id)
            self._results[job_id] = data
            return data
        return None

    def sim_result(self, job_id: str) -> SimResult | None:
        r = self.result(job_id)
        return r if isinstance(r, SimResult) else None

    def job_dir(self, job_id: str) -> Path:
        return self.history_dir / job_id

    def input_text(self, job_id: str) -> str | None:
        p = self.history_dir / job_id / "input.simc"
        if p.exists():
            return p.read_text("utf-8")
        ctx = self._contexts.get(job_id)
        if ctx and ctx.last_run and ctx.last_run.input_path and ctx.last_run.input_path.exists():
            return ctx.last_run.input_path.read_text("utf-8")
        return None

    def delete(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in ("queued", "running"):
                self.cancel(job_id)
            self._jobs.pop(job_id, None)
            self._seq.pop(job_id, None)
            self._results.pop(job_id, None)
            self._contexts.pop(job_id, None)
        d = self.history_dir / job_id
        existed = d.exists()
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(self.work_dir / job_id, ignore_errors=True)
        return existed or job is not None

    def history(self) -> list[dict]:
        out = []
        for job in self.list_jobs():
            if job.status not in ("done", "failed", "cancelled"):
                continue
            out.append({
                "id": job.id, "type": job.type, "character": job.character, "spec": job.spec,
                "created": job.created, "status": job.status, "summary": self._summary(job),
            })
        return out

    def _summary(self, job: Job) -> str:
        if job.status != "done":
            return job.error or job.status
        res = self.result(job.id)
        if isinstance(res, SimResult):
            base = f"{res.baseline.dps:,.0f} dps"
            if res.results:
                top = res.results[0]
                return f"{base}; best {top.label}: {top.delta:+,.0f} ({top.delta_pct:+.2f}%)"
            return base
        if isinstance(res, dict):
            return str(res.get("message") or res.get("tag") or "done")
        return "done"

    # ---- SSE ------------------------------------------------------------------------
    def subscribe(self, job_id: str) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, []).append((loop, q))
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            self._subscribers[job_id] = [(loop, qq) for loop, qq in subs if qq is not q]

    def _broadcast(self, event: str, job: Job) -> None:
        payload = (event, job.model_dump())
        with self._lock:
            subs = list(self._subscribers.get(job.id, []))
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, payload)
            except RuntimeError:
                pass

    # ---- persistence -----------------------------------------------------------------
    @staticmethod
    def _copy_artifact(src: Path, dst: Path) -> None:
        """Copy a SimC output file into history, tolerating a transient lock on *src*
        (observed on Windows right after simc.exe exits, most often on the ~1MB html
        report -- looks like AV real-time scanning briefly holding the freshly-written
        file). One retry after a short pause; a still-failing copy is logged, not
        raised, so it can never abort the rest of _persist (in particular job.json,
        whose absence would otherwise turn a "done" job into an unreadable one -- see
        _load_history).
        """
        try:
            shutil.copyfile(src, dst)
        except OSError:
            try:
                time.sleep(0.2)
                shutil.copyfile(src, dst)
            except OSError:
                log.exception("failed to copy artifact %s -> %s", src, dst)

    def _persist(self, job: Job, result: Any, ctx: JobContext) -> None:
        # job.json is written LAST: _load_history treats its presence as "this job's
        # result and other artifacts finished writing", so a crash mid-persist leaves an
        # entry with no job.json (skipped entirely) rather than a "done" job whose
        # result.json 404s. See _load_history's belt-and-braces check too.
        d = self.history_dir / job.id
        d.mkdir(parents=True, exist_ok=True)
        if ctx.profile is not None:
            (d / "profile.json").write_text(ctx.profile.model_dump_json(indent=2), "utf-8")
        if isinstance(result, SimResult):
            (d / "result.json").write_text(result.model_dump_json(indent=2), "utf-8")
            try:
                from toonopt.report import render

                (d / "report.html").write_text(render(result), "utf-8")
            except Exception:
                log.exception("report generation failed for %s", job.id)
        elif result is not None:
            (d / "result.json").write_text(json.dumps(result, indent=2, default=str), "utf-8")
        run = ctx.last_run
        if run is not None:
            if run.input_path and run.input_path.exists():
                self._copy_artifact(run.input_path, d / "input.simc")
            if run.json_path.exists():
                self._copy_artifact(run.json_path, d / "out.json")
            if run.html_path and run.html_path.exists():
                self._copy_artifact(run.html_path, d / "simc.html")
            (d / "stdout.txt").write_text(run.stdout, "utf-8")
        elif ctx.workdir.exists():
            for name in ("input.simc",):
                src = ctx.workdir / name
                if src.exists():
                    shutil.copyfile(src, d / name)
        (d / "job.json").write_text(job.model_dump_json(indent=2), "utf-8")
        shutil.rmtree(ctx.workdir, ignore_errors=True)

    def _load_history(self) -> None:
        if not self.history_dir.exists():
            return
        loaded: list[tuple[Job, Path]] = []
        for jd in self.history_dir.iterdir():
            p = jd / "job.json"
            if not p.is_file():
                continue
            try:
                job = Job.model_validate_json(p.read_text("utf-8"))
            except (ValueError, OSError) as e:
                log.warning("skipping history entry %s: %s", jd.name, e)
                continue
            if job.status in ("queued", "running"):   # server died mid-job
                job.status = "failed"
                job.error = "interrupted"
            elif job.status == "done" and not (jd / "result.json").exists():
                # job.json is written last (see _persist); this should only happen if the
                # server died between writing result.json and job.json, or result.json was
                # removed afterwards. Either way /result would 404 for a "done" job.
                job.status = "failed"
                job.error = "result missing"
            loaded.append((job, jd))
        # restore _seq (used to order jobs created within the same second) in created order
        for job, _jd in sorted(loaded, key=lambda pair: pair[0].created):
            self._jobs[job.id] = job
            self._seq[job.id] = len(self._seq)


manager = JobManager()
