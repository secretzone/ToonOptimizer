"""Paths and persisted settings.

Repo layout (see /API.md and /CLAUDE.md):
  <root>/runtime/simc/<tag>/   downloaded SimC builds (gitignored)
  <root>/data/                 season.json, delve-loot.json, cache/ (gitignored)
  <root>/history/              finished jobs (gitignored)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

try:
    import winreg  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - non-Windows dev/test environments
    winreg = None  # type: ignore[assignment]

_REGISTRY_KEYS = (
    (r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft", "InstallPath"),
    (r"SOFTWARE\Blizzard Entertainment\World of Warcraft", "InstallPath"),
    (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\World of Warcraft",
     "InstallLocation"),
)
_SCAN_SUBPATHS = (
    "World of Warcraft",
    r"Games\World of Warcraft",
    r"Program Files (x86)\World of Warcraft",
    r"Program Files\World of Warcraft",
    r"Blizzard\World of Warcraft",
    r"Battle.net\World of Warcraft",
)
_RETAIL_RE = re.compile(r"(^|[\\/])_retail_([\\/]|$)", re.IGNORECASE)


def normalize_wow_dir(raw: str | None) -> str:
    """Normalize user/registry input to the WoW root (the folder that contains ``_retail_``).

    Strips whitespace/quotes/trailing slashes, expands ``~`` and env vars, and cuts any
    path at its ``_retail_`` component (so ``X\\_retail_`` and ``X\\_retail_\\Wow.exe``
    both give ``X``). A path to a file such as ``.build.info`` gives its folder.
    """
    if not raw:
        return ""
    value = raw.strip().strip("\"'").strip()
    if not value:
        return ""
    value = os.path.expandvars(os.path.expanduser(value))
    m = _RETAIL_RE.search(value)
    if m:
        value = value[: m.start()] if m.group(1) else ""
    elif os.path.isfile(value):
        value = os.path.dirname(value)
    stripped = value.rstrip("\\/")
    if len(stripped) == 2 and stripped[1] == ":":  # "C:" -> keep the root slash
        return stripped + "\\"
    return stripped


def is_wow_dir(path: str | os.PathLike[str] | None) -> bool:
    """True if ``path`` looks like a WoW install root, i.e. ``<path>/_retail_`` is a directory."""
    if not path:
        return False
    try:
        return (Path(path) / "_retail_").is_dir()
    except OSError:
        return False


def _registry_paths() -> list[str]:
    """Raw WoW install paths from the registry (empty off Windows). Never raises."""
    if winreg is None:
        return []
    out: list[str] = []
    for subkey, name in _REGISTRY_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            out.append(value)
    return out


def _list_drives() -> list[str]:
    """Roots of fixed local drives (``C:\\`` ...). Empty off Windows.

    Uses GetDriveTypeW == DRIVE_FIXED so disconnected network drives are never touched.
    """
    if os.name != "nt":
        return []
    try:
        import ctypes

        get_type = ctypes.windll.kernel32.GetDriveTypeW  # type: ignore[attr-defined]
        return [
            f"{letter}:\\"
            for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            if get_type(f"{letter}:\\") == 3
        ]
    except Exception:  # noqa: BLE001 - detection must never crash
        return []


def wow_dir_candidates() -> list[dict[str, str]]:
    """Valid WoW install roots, priority order: env, registry, drive scan (deduped)."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(raw: str | None, source: str) -> None:
        path = normalize_wow_dir(raw)
        key = os.path.normcase(os.path.normpath(path)).lower() if path else ""
        if not path or key in seen or not is_wow_dir(path):
            return
        seen.add(key)
        found.append({"path": path, "source": source})

    add(os.environ.get("WOW_DIR"), "env")
    for raw in _registry_paths():
        add(raw, "registry")
    for drive in _list_drives():
        for sub in _SCAN_SUBPATHS:
            add(os.path.join(drive, sub), "scan")
    return found


def detect_wow_dir() -> str:
    """First valid candidate path, or "" when WoW can't be found."""
    cands = wow_dir_candidates()
    return cands[0]["path"] if cands else ""


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
        loaded: Settings | None = None
        if SETTINGS_FILE.exists():
            try:
                loaded = cls.model_validate(json.loads(SETTINGS_FILE.read_text("utf-8")))
            except Exception:  # noqa: BLE001, S110 - corrupt settings fall back to defaults
                pass
        if loaded is None:
            return cls()
        env = normalize_wow_dir(os.environ.get("WOW_DIR"))
        if env and is_wow_dir(env):
            wanted = env
        elif is_wow_dir(loaded.wow_dir):
            wanted = normalize_wow_dir(loaded.wow_dir)
        else:
            wanted = detect_wow_dir() or loaded.wow_dir
        if wanted != loaded.wow_dir:
            loaded.wow_dir = wanted
            try:
                loaded.save()
            except OSError:
                pass
        return loaded

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
