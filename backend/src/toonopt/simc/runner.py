"""Run simc.exe on an input file and stream progress.

Observed stdout (segments separated by ``\\r``, lines by ``\\r\\n``)::

    SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live (hotfix 2026-09-19/69875, git build midnight 774babd)
    Simulating... ( iterations=1000, threads=8, target_error=0.000, max_time=300, ... )
    Generating Baseline: MID2_Death_Knight_Frost 1/4 [=====>..............] 286/1000 149.704
    Generating Baseline: 1/1 [===================>] 111/111 88.359 Mean=233027 Error=0.479% 157msec   (target_error mode)
    Profilesets (2*4): 2/3 [============>.......] avg=411.795ms done=2s left=411.795ms
    Generating reports...

The ``a/b`` right after the label is SimC's internal work-unit counter, the
``cur/total`` after the bar is iterations. Only the latter is reported.
"""
from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from toonopt.config import settings
from toonopt.simc import runtime

ProgressCb = Callable[[str, int, int, str], None]   # (phase, current, total, message)

_BASELINE_RE = re.compile(r"Generating Baseline:.*?\[[^\]]*\]\s+(\d+)/(\d+)")
_PROFILESET_RE = re.compile(r"Profilesets\s*(?:\([^)]*\))?:\s*(\d+)/(\d+)")
_REPORTS_RE = re.compile(r"Generating reports")
_SIMULATING_RE = re.compile(r"Simulating\.\.\.")
_PROFILESET_LINE_RE = re.compile(r"^\s*profileset\.", re.MULTILINE)


class SimcError(RuntimeError):
    def __init__(self, message: str, stdout: str = "", returncode: int | None = None):
        super().__init__(message)
        self.stdout = stdout
        self.returncode = returncode


class SimcCancelled(SimcError):
    pass


@dataclass
class RunOutput:
    json_path: Path
    html_path: Path | None
    stdout: str
    seconds: float
    returncode: int = 0
    input_path: Path | None = None


def _ensure_option(text: str, key: str, value: str) -> str:
    if re.search(rf"^\s*{re.escape(key)}\s*=", text, re.MULTILINE):
        return text
    return text.rstrip("\n") + f"\n{key}={value}\n"


def prepare_input(input_text: str, threads: int) -> str:
    """Add the options the runner always wants in the file (for reproducibility)."""
    text = input_text
    if _PROFILESET_LINE_RE.search(text):
        text = _ensure_option(text, "profileset_work_threads", str(settings.profileset_work_threads))
        text = _ensure_option(text, "single_actor_batch", "1")
    text = _ensure_option(text, "threads", str(threads))
    return text


def ensure_report_details(input_text: str) -> str:
    """Ensure ``report_details=1`` is set (native SimC HTML report, see API.md M6)."""
    return _ensure_option(input_text, "report_details", "1")


def parse_progress(segment: str) -> tuple[str, int, int] | None:
    """Map one stdout segment to (phase, current, total) or None when not a progress line."""
    m = _PROFILESET_RE.search(segment)
    if m:
        return "profilesets", int(m.group(1)), int(m.group(2))
    m = _BASELINE_RE.search(segment)
    if m:
        return "baseline", int(m.group(1)), int(m.group(2))
    if _REPORTS_RE.search(segment):
        return "reports", 1, 1
    if _SIMULATING_RE.search(segment):
        return "init", 0, 0
    return None


def _reader(pipe, q: queue.Queue) -> None:
    buf = b""
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            buf += chunk
            while True:
                idx_r, idx_n = buf.find(b"\r"), buf.find(b"\n")
                idx = min(i for i in (idx_r, idx_n) if i >= 0) if (idx_r >= 0 or idx_n >= 0) else -1
                if idx < 0:
                    break
                seg, buf = buf[:idx], buf[idx + 1:]
                if seg:
                    q.put(seg.decode("utf-8", "replace"))
        if buf:
            q.put(buf.decode("utf-8", "replace"))
    finally:
        q.put(None)


def run(
    input_text: str,
    workdir: Path,
    threads: int | None = None,
    progress_cb: ProgressCb | None = None,
    cancel_event: threading.Event | None = None,
    *,
    html: bool = False,
    input_name: str = "input.simc",
    json_name: str = "out.json",
) -> RunOutput:
    """Write ``input.simc`` to *workdir*, run SimC with ``json2=out.json`` and return the paths."""
    inst = runtime.require()
    threads = threads or settings.threads
    workdir.mkdir(parents=True, exist_ok=True)
    input_path = workdir / input_name
    input_path.write_text(prepare_input(input_text, threads), "utf-8")
    json_path = workdir / json_name
    html_path = workdir / (Path(json_name).stem + ".html") if html else None
    for p in (json_path, html_path):
        if p and p.exists():
            p.unlink()

    cmd = [str(inst.path), input_path.name, f"json2={json_path.name}", f"threads={threads}"]
    if html_path:
        cmd.append(f"html={html_path.name}")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    cb = progress_cb or (lambda *_: None)
    cb("init", 0, 0, "Starting SimulationCraft")
    t0 = time.time()
    proc = subprocess.Popen(
        cmd, cwd=str(workdir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, creationflags=flags,
    )
    q: queue.Queue = queue.Queue()
    reader = threading.Thread(target=_reader, args=(proc.stdout, q), daemon=True)
    reader.start()
    segments: list[str] = []
    last_phase, last_cur, last_total = "", -1, -1
    last_emit = 0.0
    cancelled = False
    while True:
        if cancel_event is not None and cancel_event.is_set() and not cancelled:
            cancelled = True
            proc.kill()
        try:
            seg = q.get(timeout=0.25)
        except queue.Empty:
            continue
        if seg is None:
            break
        segments.append(seg)
        prog = parse_progress(seg)
        if prog is None:
            continue
        phase, cur, total = prog
        now = time.time()
        changed = (phase != last_phase) or (cur == total) or (now - last_emit > 0.3 and (cur, total) != (last_cur, last_total))
        if changed:
            last_phase, last_cur, last_total, last_emit = phase, cur, total, now
            cb(phase, cur, total, seg.strip())
    proc.wait()
    reader.join(timeout=5)
    seconds = time.time() - t0
    stdout = "\n".join(s for s in segments if s.strip())
    if cancelled:
        raise SimcCancelled("cancelled", stdout, proc.returncode)
    if proc.returncode != 0 or not json_path.exists():
        tail = "\n".join(stdout.splitlines()[-15:])
        raise SimcError(f"simc exited with {proc.returncode}: {tail}", stdout, proc.returncode)
    return RunOutput(json_path, html_path, stdout, seconds, proc.returncode, input_path)
