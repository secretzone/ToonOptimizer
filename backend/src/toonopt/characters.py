"""Server-side store of imported character profiles (see API.md "Characters").

Every successful ``POST /api/import/simc`` / ``GET /api/import/armory`` saves the resulting
:class:`toonopt.models.CharacterProfile` here via :func:`save` (hooked in
``toonopt.api.importer``). Layout, all under :data:`toonopt.config.CHARACTERS_DIR`
(repo root ``characters/``, gitignored)::

    characters/<slug>.json                     latest profile
    characters/<slug>.history/<imported_at>.json   last 10 snapshots

``slug`` is ``name-realm`` lowercased and transliterated to ascii (e.g. ``testhunter-testrealm``).

On import (of this module, done once at startup by ``toonopt.api.characters``),
:func:`backfill` seeds the store from the newest ``history/<job>/profile.json`` per character
when ``characters/`` is empty, so a fresh checkout (or one that predates this module) still
shows characters that only ever appeared as sim job inputs.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from toonopt.config import CHARACTERS_DIR, HISTORY_DIR
from toonopt.models import CharacterProfile, CharacterSummary

log = logging.getLogger(__name__)

MAX_HISTORY = 10


def slugify(name: str, realm: str) -> str:
    raw = f"{name}-{realm}".strip("-")
    ascii_ = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")
    return slug or "character"


def _path(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.json"


def _history_dir(slug: str) -> Path:
    return CHARACTERS_DIR / f"{slug}.history"


def _ilevel_equipped(profile: CharacterProfile) -> float:
    items = list(profile.equipped.values())
    if not items:
        return 0.0
    return round(sum(it.ilevel for it in items) / len(items), 2)


def summarize(slug: str, profile: CharacterProfile) -> CharacterSummary:
    return CharacterSummary(
        slug=slug, name=profile.name, realm=profile.realm, klass=profile.klass, spec=profile.spec,
        ilevel_equipped=_ilevel_equipped(profile), imported_at=profile.imported_at,
    )


def save(profile: CharacterProfile) -> str:
    """Persist ``profile`` as the latest snapshot for its character; keep a history sidecar
    of the last :data:`MAX_HISTORY` imports. Returns the character's slug."""
    slug = slugify(profile.name, profile.realm)
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    _path(slug).write_text(profile.model_dump_json(indent=2), "utf-8")

    hdir = _history_dir(slug)
    hdir.mkdir(parents=True, exist_ok=True)
    stamp = re.sub(r"[^0-9A-Za-z]+", "-", profile.imported_at)
    (hdir / f"{stamp}.json").write_text(profile.model_dump_json(indent=2), "utf-8")
    snapshots = sorted(hdir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for stale in snapshots[:-MAX_HISTORY]:
        stale.unlink(missing_ok=True)
    return slug


def list_characters() -> list[CharacterSummary]:
    if not CHARACTERS_DIR.exists():
        return []
    out: list[CharacterSummary] = []
    for p in sorted(CHARACTERS_DIR.glob("*.json")):
        try:
            profile = CharacterProfile.model_validate_json(p.read_text("utf-8"))
        except (ValueError, OSError) as e:
            log.warning("skipping character file %s: %s", p.name, e)
            continue
        out.append(summarize(p.stem, profile))
    out.sort(key=lambda c: c.name.lower())
    return out


def get(slug: str) -> CharacterProfile | None:
    p = _path(slug)
    if not p.exists():
        return None
    try:
        return CharacterProfile.model_validate_json(p.read_text("utf-8"))
    except (ValueError, OSError) as e:
        log.warning("could not load character %s: %s", slug, e)
        return None


def delete(slug: str) -> bool:
    p = _path(slug)
    existed = p.exists()
    p.unlink(missing_ok=True)
    hdir = _history_dir(slug)
    if hdir.exists():
        for f in hdir.glob("*.json"):
            f.unlink(missing_ok=True)
        try:
            hdir.rmdir()
        except OSError:
            pass
    return existed


def _has_any_character() -> bool:
    return CHARACTERS_DIR.exists() and any(CHARACTERS_DIR.glob("*.json"))


def backfill() -> int:
    """Seed ``characters/`` from the newest ``history/<job>/profile.json`` per character,
    when the store is empty. Returns the number of characters seeded."""
    if _has_any_character() or not HISTORY_DIR.exists():
        return 0
    newest: dict[str, tuple[str, CharacterProfile]] = {}
    for jd in HISTORY_DIR.iterdir():
        p = jd / "profile.json"
        if not p.is_file():
            continue
        try:
            profile = CharacterProfile.model_validate_json(p.read_text("utf-8"))
        except (ValueError, OSError):
            continue
        slug = slugify(profile.name, profile.realm)
        cur = newest.get(slug)
        if cur is None or profile.imported_at > cur[0]:
            newest[slug] = (profile.imported_at, profile)
    for _ts, profile in newest.values():
        save(profile)
    if newest:
        log.info("backfilled %d character(s) from history/*/profile.json", len(newest))
    return len(newest)
