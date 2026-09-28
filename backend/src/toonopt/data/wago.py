"""wago.tools DB2 CSV cache.

Every game table the data layer needs is fetched from
``https://wago.tools/db2/<Table>/csv?build=<build>`` (the ``build`` query parameter is what
localbots verified works; never trust wago's default, it sometimes points at a test build)
and stored as raw CSV under ``CACHE_DIR/<build>/<Table>.csv``. Two extra files ride along:

* ``bonuses.json`` -- Raidbots' public bonus-id map (upgrade tracks, sockets, item levels).
  It is the community-standard decode and the only practical source for "bonus id 12854 =
  Myth 6/6 = item level 334": the DB2 ``ItemBonus`` rows for track bonuses (type 34) point at
  an upgrade group, not at a level.
* ``sc_scale_data.inc`` -- SimulationCraft's generated combat-rating / stamina multiplier
  curves per item level. wago does not publish ``CombatRatingsMultByILvl``/``StaminaMultByILvl``
  for the current build (HTTP 404), and these curves are what turn a stat allocation into the
  number on the tooltip.

Tables are read with polars and cached in memory per (build, table, columns).
"""
from __future__ import annotations

import json
import shutil
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import httpx
import polars as pl

from toonopt.config import CACHE_DIR, settings

BASE_URL = "https://wago.tools/db2/{table}/csv?build={build}"
USER_AGENT = "ToonOptimizer (local SimulationCraft frontend)"

# Journal / instances
_JOURNAL = [
    "JournalTier", "JournalTierXInstance", "JournalInstance", "JournalEncounter",
    "JournalEncounterItem", "JournalItemXDifficulty", "DungeonEncounter", "Map",
    "MapChallengeMode", "MythicPlusSeasonTrackedMap", "MythicPlusSeason",
]
# Items, sets, icons
_ITEMS = [
    "Item", "ItemSparse", "ItemSet", "ItemSetSpell", "ItemLimitCategory",
    "ItemAppearance", "ItemModifiedAppearance", "ManifestInterfaceData", "CraftingData",
    "SpellItemEnchantment",
]
# Stat budgets, weapon damage, armour
_STATS = ["RandPropPoints", "ItemDamageOneHand", "ItemDamageTwoHand", "ItemArmorTotal", "ArmorLocation"]
# Bonus ids, upgrade tracks, drop levels
_BONUS = [
    "ItemBonus", "ItemXBonusTree", "ItemBonusTreeNode", "ItemBonusListGroupEntry",
    "ItemBonusListLevelDelta",
]
# Currencies (crests, catalyst charges, etc.) -- toonopt.data.currencies
_CURRENCIES = ["CurrencyTypes"]
# Talents
_TRAITS = [
    "TraitTree", "TraitNode", "TraitNodeEntry", "TraitDefinition", "TraitNodeXTraitNodeEntry",
    "TraitEdge", "TraitSubTree", "TraitTreeLoadout", "TraitNodeGroup", "TraitNodeGroupXTraitNode",
    "TraitNodeGroupXTraitCond", "TraitNodeXTraitCond", "TraitCond", "SpecSetMember",
    "ChrSpecialization", "ChrClasses", "SpellName", "SpellMisc",
]
TABLES: list[str] = _JOURNAL + _ITEMS + _STATS + _BONUS + _TRAITS + _CURRENCIES

EXTRA_FILES: dict[str, str] = {
    "bonuses.json": "https://www.raidbots.com/static/data/live/bonuses.json",
    "sc_scale_data.inc":
        "https://raw.githubusercontent.com/simulationcraft/simc/midnight/engine/dbc/generated/sc_scale_data.inc",
}
META_FILE = "meta.json"

ProgressCb = Callable[[int, int, str], None]

_lock = threading.Lock()
_frames: dict[tuple[str, str, tuple[str, ...] | None], pl.DataFrame] = {}


def build() -> str:
    """The build the cache is keyed on (``settings.wow_build``)."""
    return settings.wow_build or "unknown"


def cache_dir(build_: str | None = None) -> Path:
    return CACHE_DIR / (build_ or build())


def table_path(name: str, build_: str | None = None) -> Path:
    return cache_dir(build_) / f"{name}.csv"


def extra_path(name: str, build_: str | None = None) -> Path:
    return cache_dir(build_) / name


def _download(client: httpx.Client, url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with client.stream("GET", url, headers={"User-Agent": USER_AGENT}, timeout=600) as resp:
        resp.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    # wago answers 200 with a JSON error body for unknown tables
    with tmp.open("rb") as fh:
        head = fh.read(64)
    if head.startswith(b'{"errors"'):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"wago.tools returned an error for {url}: {head!r}")
    tmp.replace(dest)


def ensure_tables(build: str, progress_cb: ProgressCb | None = None, force: bool = False) -> None:
    """Download every table (and extra file) missing from the cache for ``build``.

    ``progress_cb(current, total, message)`` is called before each download. With ``force``
    everything is re-fetched. Writes ``meta.json`` when done and drops the in-memory frames.
    """
    d = cache_dir(build)
    d.mkdir(parents=True, exist_ok=True)
    targets: list[tuple[str, str, Path]] = []
    for t in TABLES:
        targets.append((t, BASE_URL.format(table=t, build=build), table_path(t, build)))
    for name, url in EXTRA_FILES.items():
        targets.append((name, url, extra_path(name, build)))
    todo = [x for x in targets if force or not x[2].exists() or x[2].stat().st_size == 0]
    total = len(todo)
    started = time.time()
    with httpx.Client(follow_redirects=True) as client:
        for i, (name, url, dest) in enumerate(todo):
            if progress_cb:
                progress_cb(i, total, f"Downloading {name}")
            try:
                _download(client, url, dest)
            except Exception as e:  # extras are optional; tables are not
                if name in EXTRA_FILES and not dest.exists():
                    continue
                if name in EXTRA_FILES:
                    continue
                raise RuntimeError(f"failed to download {name}: {e}") from e
    if progress_cb:
        progress_cb(total, total, "Download complete")
    meta = {
        "build": build,
        "refreshed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "tables": [t for t in TABLES if table_path(t, build).exists()],
        "seconds": round(time.time() - started, 1),
        "bytes": sum(p.stat().st_size for p in d.iterdir() if p.is_file()),
    }
    (d / META_FILE).write_text(json.dumps(meta, indent=2), "utf-8")
    clear_memory(build)


def refresh(build: str, progress_cb: ProgressCb | None = None) -> None:
    """Force a full re-download of ``build`` (old files are replaced in place)."""
    # derived caches (loot db etc.) live next to the tables and must be rebuilt too
    d = cache_dir(build)
    for p in d.glob("*.derived.json"):
        p.unlink(missing_ok=True)
    ensure_tables(build, progress_cb, force=True)


def _base_status(build_: str) -> dict:
    d = cache_dir(build_)
    cached = [t for t in TABLES if (d / f"{t}.csv").exists() and (d / f"{t}.csv").stat().st_size > 0]
    refreshed_at: str | None = None
    meta_path = d / META_FILE
    if meta_path.exists():
        try:
            refreshed_at = json.loads(meta_path.read_text("utf-8")).get("refreshed_at")
        except Exception:  # noqa: BLE001 - a corrupt meta.json just falls back to file mtimes
            refreshed_at = None
    if refreshed_at is None and cached:
        newest = max((d / f"{t}.csv").stat().st_mtime for t in cached)
        refreshed_at = datetime.fromtimestamp(newest, tz=UTC).isoformat(timespec="seconds")
    return {
        "build": build_,
        "cached_tables": cached,
        "ready": len(cached) == len(TABLES),
        "refreshed_at": refreshed_at,
    }


def ready_builds() -> list[str]:
    """Every build under ``CACHE_DIR`` whose cache is fully downloaded, newest first."""
    try:
        candidates = [d.name for d in CACHE_DIR.iterdir() if d.is_dir()]
    except OSError:
        return []
    scored: list[tuple[float, str]] = []
    for b in candidates:
        st = _base_status(b)
        if not st["ready"]:
            continue
        ts = 0.0
        if st["refreshed_at"]:
            try:
                ts = datetime.fromisoformat(st["refreshed_at"]).timestamp()
            except ValueError:
                ts = 0.0
        scored.append((ts, b))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [b for _, b in scored]


def effective_build() -> str:
    """The build every data read should use by default.

    Precedence: the live game build (``settings.wow_build``) if its cache is fully ready,
    else the newest fully-cached build on disk (by ``refreshed_at``), else the live build
    anyway (so a missing-cache error still names the build that's actually live). This is
    what keeps a fresh WoW patch from turning every imported item into a bare, unresolved
    stub the moment the client updates but ``data/cache/<new build>/`` hasn't been
    downloaded yet -- callers keep reading whatever build IS cached until a refresh catches
    up, instead of hard-failing on the brand-new one.
    """
    live = build()
    if live and _base_status(live)["ready"]:
        return live
    ready = ready_builds()
    return ready[0] if ready else live


def status(build_: str | None = None) -> dict:
    b = build_ or effective_build()
    out = _base_status(b)
    out["effective_build"] = effective_build()
    out["ready_builds"] = ready_builds()
    return out


def is_ready(build_: str | None = None) -> bool:
    return _base_status(build_ or effective_build())["ready"]


def table(name: str, build: str | None = None, columns: Sequence[str] | None = None) -> pl.DataFrame:
    """Read a cached table (a polars DataFrame, memoised per build/table/columns)."""
    b = build or effective_build()
    key = (b, name, tuple(columns) if columns else None)
    with _lock:
        df = _frames.get(key)
    if df is not None:
        return df
    path = table_path(name, b)
    if not path.exists():
        raise FileNotFoundError(f"DB2 table {name} is not cached for build {b}; run data refresh")
    df = pl.read_csv(
        path,
        columns=list(columns) if columns else None,
        infer_schema_length=None,
        encoding="utf8",
        quote_char='"',
    )
    with _lock:
        _frames[key] = df
    return df


def clear_memory(build: str | None = None) -> None:
    with _lock:
        if build is None:
            _frames.clear()
        else:
            for k in [k for k in _frames if k[0] == build]:
                del _frames[k]


def delete_cache(build: str) -> None:
    shutil.rmtree(cache_dir(build), ignore_errors=True)
    clear_memory(build)
