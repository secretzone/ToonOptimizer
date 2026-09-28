"""Paths and persisted settings.

Repo layout (see /API.md and /CLAUDE.md):
  <root>/runtime/simc/<tag>/   downloaded SimC builds (gitignored)
  <root>/data/                 season.json, delve-loot.json, cache/ (gitignored)
  <root>/history/              finished jobs (gitignored)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - non-Windows dev/test environments
    winreg = None  # type: ignore[assignment]

_CANDIDATE_WOW_DIRS = (
    r"C:\Program Files (x86)\World of Warcraft",
    r"C:\Program Files\World of Warcraft",
    r"C:\Games\World of Warcraft",
    r"D:\World of Warcraft",
    r"D:\Games\World of Warcraft",
)


def _battlenet_wow_dir() -> str:
    """Read the Battle.net install path for World of Warcraft from the registry.

    Returns "" if the key doesn't exist, isn't readable, or we're not on Windows --
    never raises. A trailing ``_retail_`` component (Battle.net stores the retail
    subdirectory itself) is stripped so callers get the same shape as the other
    candidates (a directory that itself contains ``.build.info``... actually
    ``_retail_/.build.info``, but detect_wow_build already expects the game dir).
    """
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "InstallPath")
    except OSError:
        return ""
    value = value.rstrip("\\/")
    if value.lower().endswith("_retail_"):
        value = value[: -len("_retail_")].rstrip("\\/")
    return value


def detect_wow_dir() -> str:
    """Best-effort auto-detect of the WoW install directory on this machine.

    Precedence: ``WOW_DIR`` env var, else the first existing well-known path, else the
    Battle.net registry install path (if readable), else "" (caller falls back to a
    default that simply won't resolve a build -- status should report that clearly
    rather than crash).
    """
    env = os.environ.get("WOW_DIR")
    if env:
        return env
    for candidate in _CANDIDATE_WOW_DIRS:
        if Path(candidate).is_dir():
            return candidate
    registry_path = _battlenet_wow_dir()
    if registry_path and Path(registry_path).is_dir():
        return registry_path
    return ""

ROOT = Path(__file__).resolve().parents[3]          # repo root
RUNTIME_DIR = ROOT / "runtime"
SIMC_DIR = RUNTIME_DIR / "simc"
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
HISTORY_DIR = ROOT / "history"
WORK_DIR = RUNTIME_DIR / "work"                      # per-job .simc inputs and json outputs
FRONTEND_DIST = ROOT / "frontend" / "dist"
SETTINGS_FILE = DATA_DIR / "settings.json"
CHARACTERS_DIR = ROOT / "characters"                 # saved CharacterProfile snapshots (gitignored)
REPORTS_DIR = ROOT / "reports"                       # per-character reports (gitignored)

for _d in (RUNTIME_DIR, SIMC_DIR, CACHE_DIR, HISTORY_DIR, WORK_DIR, CHARACTERS_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseModel):
    port: int = 8790
    threads: int = max(1, (os.cpu_count() or 4))
    profileset_work_threads: int = 4
    default_iterations: int = 10000
    default_target_error: float = 0.1          # quick sims
    profileset_target_error: float = 0.3       # top gear / droptimizer per profileset
    wow_dir: str = Field(default_factory=detect_wow_dir)
    wow_build: str = ""                         # effective build: override, else last-detected build
    wow_build_override: str = ""                # explicit pin; empty = auto-detect from .build.info
    simc_tag: str = ""                          # installed sortbek/simc-builds tag
    region: str = "us"
    ptr: bool = False

    @classmethod
    def load(cls) -> Settings:
        if SETTINGS_FILE.exists():
            try:
                return cls.model_validate(json.loads(SETTINGS_FILE.read_text("utf-8")))
            except Exception:  # noqa: BLE001, S110 - corrupt settings fall back to defaults
                pass
        return cls()

    def save(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(self.model_dump(), indent=2), "utf-8")

    def refresh_wow_build(self) -> str:
        """Re-read ``<wow_dir>/.build.info`` and update ``wow_build``, the effective build.

        Precedence: an explicit ``wow_build_override`` always wins. Otherwise a freshly
        detected build wins. If detection fails (WoW not installed/mounted at ``wow_dir``
        right now), ``wow_build`` keeps whatever was last successfully detected (or loaded
        from ``data/settings.json``) rather than going blank. Never writes to
        ``wow_build_override`` -- that field only ever changes via an explicit PUT.
        """
        if self.wow_build_override:
            self.wow_build = self.wow_build_override
            return self.wow_build
        detected = detect_wow_build(self.wow_dir)
        if detected:
            self.wow_build = detected
        return self.wow_build


def detect_wow_build(wow_dir: str) -> str:
    """Read the retail build (e.g. '12.1.0.69875') from <wow_dir>/.build.info."""
    p = Path(wow_dir) / ".build.info"
    try:
        lines = p.read_text("utf-8").splitlines()
        header = lines[0].split("|")
        idx_ver = next(i for i, h in enumerate(header) if h.startswith("Version"))
        idx_prod = next(i for i, h in enumerate(header) if h.startswith("Product"))
        for line in lines[1:]:
            cols = line.split("|")
            if len(cols) > max(idx_ver, idx_prod) and cols[idx_prod] == "wow":
                return cols[idx_ver]
    except Exception:  # noqa: BLE001, S110 - no WoW install is fine
        pass
    return ""


settings = Settings.load()
settings.refresh_wow_build()
