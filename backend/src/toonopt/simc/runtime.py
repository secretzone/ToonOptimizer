"""Manage SimulationCraft binaries.

Weekly Windows builds come from https://github.com/sortbek/simc-builds (asset
``simc-windows-x64.zip``, which contains a single ``simc.exe`` at the zip root).
Installed builds live in ``SIMC_DIR/<tag>/simc.exe``; ``SIMC_DIR/current.json``
records which tag is active. A user-supplied binary can be pointed at with the
``SIMC_PATH`` environment variable and always wins.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from toonopt.config import SIMC_DIR, settings
from toonopt.simc.results import wow_version as _wow_version_from_player

RELEASES_URL = "https://api.github.com/repos/sortbek/simc-builds/releases"
ASSET_NAME = "simc-windows-x64.zip" if sys.platform == "win32" else "simc-linux-x64.tar.gz"
EXE_NAME = "simc.exe" if sys.platform == "win32" else "simc"
CURRENT_FILE = SIMC_DIR / "current.json"

ProgressCb = Callable[[str, int, int], None]  # (message, done_bytes, total_bytes)


class SimcNotInstalled(RuntimeError):
    pass


@dataclass(frozen=True)
class InstalledSimc:
    path: Path
    tag: str
    version_string: str      # full first line SimC prints, e.g. "SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live (hotfix ...)"
    simc_version: str        # "1210-01"
    wow_version: str         # "12.1.0.69875"

    def to_dict(self) -> dict:
        return {
            "path": str(self.path), "tag": self.tag, "version_string": self.version_string,
            "simc_version": self.simc_version, "wow_version": self.wow_version,
        }


_probe_cache: dict[tuple[str, float], tuple[str, str, str]] = {}

# Root cause (see backend/CLAUDE.md task notes): running ``simc.exe`` with no arguments and
# parsing its "Nothing to sim!" banner is *inherently* flaky, not a bug in how this process
# captures output. Looping the bare invocation 20x with stdout/stderr captured separately
# showed: returncode==0 every time, stderr empty every time, but stdout empty on ~40-60% of
# runs (varies by machine/load) -- SimC's own startup path sometimes exits before the banner
# hits the pipe. Retrying a few times (the previous fix) just lowers the odds of hitting an
# empty run without eliminating them, so the suite could still flake.
#
# A real (if trivial) sim run does not have this problem: it always writes a well-formed
# ``json2`` report before exiting, and that report carries the version deterministically
# (``version`` / ``git_revision`` top-level keys, ``players[0].dbc.<version_used>.wow_version``
# -- see simc/results.py). So probe by running one iteration of a minimal profile and reading
# the json2 report instead of scraping the banner.
_PROBE_INPUT = (
    'warrior="ToonOptimizerProbe"\n'
    "level=80\n"
    "race=orc\n"
    "spec=arms\n"
    "talents=CcEAAAAAAAAAAAAAAAAAAAAAAAzMzsMzMmZGAAAghphxYmxyMzMzgxMDAAAAgZWmZAhxyyALgBMDTIzgNwMjtx2ALzsMAzMAYGGA\n"
    "main_hand=,id=268210,enchant_id=3368,bonus_id=13335/13848\n"
    "iterations=1\n"
    "max_time=1\n"
)


def _version_string(version: str, wow_ver: str, used: str, entry: dict) -> str:
    parts = [f"SimulationCraft {version} for World of Warcraft {wow_ver}".rstrip()]
    if used:
        parts.append(used)
    hotfix_date, hotfix_build = entry.get("hotfix_date"), entry.get("hotfix_build")
    if hotfix_date and hotfix_build:
        parts.append(f"(hotfix {hotfix_date}/{hotfix_build})")
    return " ".join(parts)


def _probe_once(exe: Path) -> tuple[str, str, str]:
    """Run one trivial sim (1 iteration, 1s fight) and read the version from its json2 report."""
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    with tempfile.TemporaryDirectory(prefix="toonopt-probe-") as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "probe.simc").write_text(_PROBE_INPUT, "utf-8")
        json_path = tmpdir / "probe.json"
        try:
            subprocess.run(
                [str(exe), "probe.simc", "json2=probe.json"], capture_output=True, text=True,
                timeout=60, creationflags=flags, cwd=str(tmpdir), errors="replace", check=False,
            )
            data = json.loads(json_path.read_text("utf-8"))
        except (OSError, subprocess.SubprocessError, ValueError):
            return "", "", ""
    version = str(data.get("version") or "")
    if not version:
        return "", "", ""
    players = ((data.get("sim") or {}).get("players")) or []
    player = players[0] if players else {}
    dbc = player.get("dbc") or {}
    used = str(dbc.get("version_used") or "Live")
    entry = dbc.get(used) or {}
    wow_ver = _wow_version_from_player(player)
    return _version_string(version, wow_ver, used, entry), version, wow_ver


_PROBE_MAX_ATTEMPTS = 2  # the sim-based probe is deterministic; this only guards against a
# genuinely transient OS-level hiccup (e.g. antivirus holding a lock on a just-extracted exe).


def probe_version(exe: Path) -> tuple[str, str, str]:
    """Return (version_string, simc_version, wow_version) for *exe*, probed at most once.

    Probing runs a trivial real sim and reads its json2 report (see ``_probe_once`` for why
    the no-argument banner is not used). Results are cached in-memory for the process lifetime
    and persisted to ``SIMC_DIR/current.json`` keyed by the exe's path + mtime, so a given
    installed tag is only ever probed once across process restarts too.
    """
    key = (str(exe), exe.stat().st_mtime)
    if key in _probe_cache:
        return _probe_cache[key]
    persisted = _read_persisted_probe(exe)
    if persisted:
        _probe_cache[key] = persisted
        return persisted
    result = ("", "", "")
    for _ in range(_PROBE_MAX_ATTEMPTS):
        result = _probe_once(exe)
        if result[0]:
            break
    if result[0]:
        _probe_cache[key] = result
        _persist_probe(exe, result)
    return result


def _find_exe(folder: Path) -> Path | None:
    direct = folder / EXE_NAME
    if direct.is_file():
        return direct
    for p in folder.rglob(EXE_NAME):
        if p.is_file():
            return p
    return None


def _read_current() -> dict:
    try:
        return json.loads(CURRENT_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_current(tag: str, exe: Path) -> None:
    data = _read_current()
    data["tag"] = tag
    data["path"] = str(exe)
    CURRENT_FILE.write_text(json.dumps(data, indent=2), "utf-8")


def _read_persisted_probe(exe: Path) -> tuple[str, str, str] | None:
    """A probe result for *exe* persisted by an earlier process, if it still matches."""
    entry = (_read_current().get("probes") or {}).get(str(exe))
    if isinstance(entry, dict) and entry.get("mtime") == exe.stat().st_mtime and entry.get("simc_version"):
        return str(entry.get("version_string", "")), str(entry["simc_version"]), str(entry.get("wow_version", ""))
    return None


def _persist_probe(exe: Path, result: tuple[str, str, str]) -> None:
    """Save a probe result for *exe* into ``current.json`` so future processes skip re-probing."""
    vs, sv, wv = result
    data = _read_current()
    probes = data.get("probes") if isinstance(data.get("probes"), dict) else {}
    probes[str(exe)] = {"mtime": exe.stat().st_mtime, "version_string": vs, "simc_version": sv, "wow_version": wv}
    data["probes"] = probes
    CURRENT_FILE.write_text(json.dumps(data, indent=2), "utf-8")


def installed() -> InstalledSimc | None:
    """The active SimC binary, or None. Order: $SIMC_PATH, current.json, settings.simc_tag."""
    env = os.environ.get("SIMC_PATH")
    if env:
        p = Path(env)
        if p.is_dir():
            p = _find_exe(p) or p
        if p.is_file():
            vs, sv, wv = probe_version(p)
            return InstalledSimc(p, "custom", vs, sv, wv)
    cur = _read_current()
    candidates: list[tuple[str, Path | None]] = []
    if cur.get("path"):
        candidates.append((cur.get("tag", ""), Path(cur["path"])))
    if cur.get("tag"):
        candidates.append((cur["tag"], _find_exe(SIMC_DIR / cur["tag"])))
    if settings.simc_tag:
        candidates.append((settings.simc_tag, _find_exe(SIMC_DIR / settings.simc_tag)))
    for tag, exe in candidates:
        if exe and exe.is_file():
            vs, sv, wv = probe_version(exe)
            return InstalledSimc(exe, tag, vs, sv, wv)
    # last resort: newest tag folder that has an exe
    if SIMC_DIR.exists():
        for d in sorted((d for d in SIMC_DIR.iterdir() if d.is_dir()), reverse=True):
            exe = _find_exe(d)
            if exe:
                vs, sv, wv = probe_version(exe)
                return InstalledSimc(exe, d.name, vs, sv, wv)
    return None


def require() -> InstalledSimc:
    inst = installed()
    if inst is None:
        raise SimcNotInstalled("SimulationCraft is not installed; POST /api/simc/install first")
    return inst


_latest_cache: dict[str, object] = {"at": 0.0, "value": None}
LATEST_TTL = 600.0


def _releases(client: httpx.Client) -> list[dict]:
    r = client.get(RELEASES_URL, params={"per_page": 10}, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    return r.json()


def _pick_release(releases: list[dict], tag: str | None) -> tuple[str, str, int]:
    """Return (tag, asset_url, asset_size) for the requested or latest weekly release."""
    for rel in releases:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        rtag = rel.get("tag_name", "")
        if tag and rtag != tag:
            continue
        if not tag and not rtag.startswith("weekly-"):
            continue
        for asset in rel.get("assets", []):
            if asset.get("name") == ASSET_NAME:
                return rtag, asset["browser_download_url"], int(asset.get("size") or 0)
    raise RuntimeError(f"no release with asset {ASSET_NAME}" + (f" for tag {tag}" if tag else ""))


def latest_tag(force: bool = False) -> str | None:
    """Latest weekly tag from GitHub (cached for LATEST_TTL seconds); None when offline."""
    now = time.time()
    if not force and _latest_cache["value"] and now - float(_latest_cache["at"]) < LATEST_TTL:
        return str(_latest_cache["value"])
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            tag, _, _ = _pick_release(_releases(client), None)
    except (httpx.HTTPError, RuntimeError, ValueError):
        return str(_latest_cache["value"]) if _latest_cache["value"] else None
    _latest_cache.update(at=now, value=tag)
    return tag


def _extract(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    else:
        import tarfile

        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")


def install(tag: str | None = None, progress_cb: ProgressCb | None = None) -> InstalledSimc:
    """Download and unpack a build, make it current, and return it."""
    cb = progress_cb or (lambda *_: None)
    cb("Resolving release", 0, 0)
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        rtag, url, size = _pick_release(_releases(client), tag)
        target_dir = SIMC_DIR / rtag
        exe = _find_exe(target_dir) if target_dir.exists() else None
        if exe is None:
            archive = SIMC_DIR / f"{rtag}-{ASSET_NAME}"
            part = archive.with_suffix(archive.suffix + ".part")
            cb(f"Downloading {rtag}", 0, size)
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("content-length") or size or 0)
                done = 0
                last = 0.0
                with part.open("wb") as fh:
                    for chunk in resp.iter_bytes(1 << 16):
                        fh.write(chunk)
                        done += len(chunk)
                        if time.time() - last > 0.2:
                            cb(f"Downloading {rtag}", done, total)
                            last = time.time()
                cb(f"Downloading {rtag}", done, total)
            part.replace(archive)
            cb(f"Extracting {rtag}", size, size)
            _extract(archive, target_dir)
            archive.unlink(missing_ok=True)
            exe = _find_exe(target_dir)
            if exe is None:
                raise RuntimeError(f"{ASSET_NAME} did not contain {EXE_NAME}")
    cb("Probing version", size, size)
    vs, sv, wv = probe_version(exe)
    _write_current(rtag, exe)
    settings.simc_tag = rtag
    settings.save()
    cb(f"Installed {rtag}", size, size)
    return InstalledSimc(exe, rtag, vs, sv, wv)
