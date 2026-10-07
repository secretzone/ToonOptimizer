"""Import characters captured by the in-game ToonOptimizer addon.

The addon stores the SimulationCraft export string in its SavedVariables file, which WoW
writes on /reload, logout or exit::

    <wow_dir>/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ToonOptimizer.lua

This module parses that Lua file (a small subset: table constructors, strings, numbers,
booleans, nil) without any dependency, lists the captures and imports one as a
:class:`toonopt.models.CharacterProfile` with ``source="addon"``.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from toonopt import characters, config
from toonopt.models import CharacterProfile
from toonopt.simc import profile as profile_mod

log = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = (
    "No ToonOptimizer addon data found. Install the addon, log in, then /reload or log out "
    "-- WoW only writes addon data then."
)


class LuaParseError(ValueError):
    pass


class AddonImportError(Exception):
    """Base class for import errors (``ProfileError`` from the SimC parser passes through)."""


class NoAddonData(AddonImportError):
    """No SavedVariables file / no usable capture."""


class UnknownCapture(AddonImportError):
    """The requested ``Name-Realm`` key is not among the captures."""


# ---------------------------------------------------------------------------
# Lua subset parser

_NUM_RE = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LONG_OPEN_RE = re.compile(r"\[(=*)\[")
_LONG_COMMENT_RE = re.compile(r"--\[(=*)\[")
_DEC_ESC_RE = re.compile(r"\d{1,3}")
_HEX_ESC_RE = re.compile(r"[0-9a-fA-F]{2}")
_AFTER_IDENT_EQ_RE = re.compile(r"\s*=(?!=)")
_SIMPLE_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
               "\\": "\\", '"': '"', "'": "'", "\n": "\n"}


class _Parser:
    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0

    def err(self, msg: str) -> LuaParseError:
        line = self.s.count("\n", 0, self.i) + 1
        return LuaParseError(f"{msg} (line {line})")

    def skip(self) -> None:
        s, n = self.s, len(self.s)
        while self.i < n:
            c = s[self.i]
            if c in " \t\r\n":
                self.i += 1
            elif s.startswith("--", self.i):
                m = _LONG_COMMENT_RE.match(s, self.i)
                if m:
                    end = s.find("]" + m.group(1) + "]", self.i)
                    self.i = n if end < 0 else end + len(m.group(1)) + 2
                else:
                    nl = s.find("\n", self.i)
                    self.i = n if nl < 0 else nl + 1
            else:
                break

    def peek(self) -> str:
        self.skip()
        return self.s[self.i] if self.i < len(self.s) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            raise self.err(f"expected {ch!r}")
        self.i += 1

    def assignments(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        while self.peek():
            m = _IDENT_RE.match(self.s, self.i)
            if not m:
                raise self.err("expected identifier")
            self.i = m.end()
            self.expect("=")
            out[m.group(0)] = self.value()
            if self.peek() == ";":
                self.i += 1
        return out

    def value(self) -> Any:
        c = self.peek()
        if c == "{":
            return self.table()
        if c in ('"', "'"):
            return self.string()
        if c == "[" and _LONG_OPEN_RE.match(self.s, self.i):
            return self.long_string()
        m = _NUM_RE.match(self.s, self.i)
        if m:
            self.i = m.end()
            tok = m.group(0)
            if "x" in tok.lower():
                return int(tok, 16)
            if re.fullmatch(r"-?\d+", tok):
                return int(tok)
            return float(tok)
        m = _IDENT_RE.match(self.s, self.i)
        if m:
            self.i = m.end()
            word = m.group(0)
            if word == "true":
                return True
            if word == "false":
                return False
            if word == "nil":
                return None
            raise self.err(f"unexpected identifier {word!r}")
        raise self.err("unexpected character")

    def long_string(self) -> str:
        m = _LONG_OPEN_RE.match(self.s, self.i)
        assert m
        close = "]" + m.group(1) + "]"
        start = m.end()
        end = self.s.find(close, start)
        if end < 0:
            raise self.err("unterminated long string")
        self.i = end + len(close)
        body = self.s[start:end]
        return body.removeprefix("\n")

    def string(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        s, n = self.s, len(self.s)
        buf = bytearray()   # decimal/hex escapes are raw bytes (WoW writes UTF-8 that way)
        while self.i < n:
            c = s[self.i]
            if c == quote:
                self.i += 1
                return buf.decode("utf-8", errors="replace")
            if c == "\n":
                raise self.err("unterminated string")
            if c != "\\":
                buf += c.encode("utf-8", errors="replace")
                self.i += 1
                continue
            self.i += 1
            if self.i >= n:
                break
            e = s[self.i]
            if e in _SIMPLE_ESC:
                buf += _SIMPLE_ESC[e].encode()
                self.i += 1
            elif e.isdigit():
                m = _DEC_ESC_RE.match(s, self.i)
                assert m
                val = int(m.group(0))
                if val > 255:
                    raise self.err("decimal escape too large")
                buf.append(val)
                self.i = m.end()
            elif e == "x":
                m = _HEX_ESC_RE.match(s, self.i + 1)
                if not m:
                    raise self.err("bad hex escape")
                buf.append(int(m.group(0), 16))
                self.i = m.end()
            elif e == "z":
                self.i += 1
                while self.i < n and s[self.i] in " \t\r\n":
                    self.i += 1
            else:
                raise self.err(f"bad escape \\{e}")
        raise self.err("unterminated string")

    def table(self) -> Any:
        self.expect("{")
        keyed: dict[Any, Any] = {}
        pos = 0
        while True:
            c = self.peek()
            if c == "}":
                self.i += 1
                break
            if c == "":
                raise self.err("unterminated table")
            if c == "[" and not _LONG_OPEN_RE.match(self.s, self.i):
                self.i += 1
                key = self.value()
                self.expect("]")
                self.expect("=")
                keyed[key] = self.value()
            else:
                m = _IDENT_RE.match(self.s, self.i)
                if m and _AFTER_IDENT_EQ_RE.match(self.s, m.end()):
                    self.i = m.end()
                    self.expect("=")
                    keyed[m.group(0)] = self.value()
                else:
                    pos += 1
                    keyed[pos] = self.value()
            if self.peek() in (",", ";"):
                self.i += 1
        if keyed and all(isinstance(k, int) and not isinstance(k, bool) for k in keyed) \
                and sorted(keyed) == list(range(1, len(keyed) + 1)):
            return [keyed[k] for k in range(1, len(keyed) + 1)]
        return keyed


def parse_savedvariables(text: str) -> dict[str, Any]:
    """Parse ``Name = <value>`` top-level assignments into ``{Name: value}``.

    Tables become dicts, except pure sequential ``1..n`` integer-keyed tables, which become lists.
    Raises :class:`LuaParseError` on malformed input."""
    text = text.removeprefix("﻿")
    try:
        return _Parser(text).assignments()
    except LuaParseError:
        raise
    except (ValueError, OverflowError) as e:
        raise LuaParseError(str(e)) from e


# ---------------------------------------------------------------------------
# Locating files

def _retail_dir(wow_dir: str | Path) -> Path | None:
    if not str(wow_dir):
        return None
    p = Path(wow_dir)
    return p if p.name.lower() == "_retail_" else p / "_retail_"


def savedvariables_files(wow_dir: str | Path) -> list[Path]:
    retail = _retail_dir(wow_dir)
    if retail is None or not retail.is_dir():
        return []
    return sorted(retail.glob("WTF/Account/*/SavedVariables/ToonOptimizer.lua"))


def addon_installed(wow_dir: str | Path) -> bool:
    retail = _retail_dir(wow_dir)
    return retail is not None and (retail / "Interface" / "AddOns" / "ToonOptimizer" / "ToonOptimizer.toc").is_file()


# ---------------------------------------------------------------------------
# Captures

_SERVER_RE = re.compile(r"^[ \t]*server=([^\s,]+)", re.MULTILINE)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat(timespec="seconds")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _raw_captures(wow_dir: str | Path) -> list[dict[str, Any]]:
    """Every usable capture across accounts (newest per key), each with its ``simc`` text."""
    best: dict[str, dict[str, Any]] = {}
    for f in savedvariables_files(wow_dir):
        try:
            data = parse_savedvariables(f.read_text("utf-8", errors="replace"))
        except (LuaParseError, OSError, RecursionError) as e:
            log.warning("skipping unreadable addon file %s: %s", f, e)
            continue
        db = data.get("ToonOptimizerDB")
        chars = db.get("characters") if isinstance(db, dict) else None
        if not isinstance(chars, dict):
            continue
        account = f.parent.parent.name
        for key, entry in chars.items():
            if not isinstance(entry, dict):
                continue
            simc = entry.get("simc")
            if not isinstance(simc, str) or not simc.strip():
                continue
            ts = entry.get("captured_at")
            if not isinstance(ts, (int, float)) or isinstance(ts, bool):
                ts = 0
            try:
                captured_iso = _iso(ts)
            except (OverflowError, OSError, ValueError):
                log.warning("skipping addon capture %s in %s: bad captured_at %r", key, f, ts)
                continue
            name = str(entry.get("name") or str(key).split("-", 1)[0])
            key_realm = str(key).split("-", 1)[1] if "-" in str(key) else ""
            realm = str(entry.get("realm") or key_realm)
            m = _SERVER_RE.search(simc)
            slug_realm = m.group(1) if m else key_realm or realm
            ilvl = entry.get("ilvl")
            cap = {
                "key": str(key), "account": account, "name": name, "realm": realm,
                "class": str(entry.get("class") or ""), "spec": str(entry.get("spec") or ""),
                "ilvl": float(ilvl) if isinstance(ilvl, (int, float)) and not isinstance(ilvl, bool) else None,
                "_ts": float(ts), "captured_at": captured_iso, "simc": simc, "_slug_realm": slug_realm,
            }
            cur = best.get(cap["key"])
            if cur is None or cap["_ts"] > cur["_ts"]:
                best[cap["key"]] = cap
    return sorted(best.values(), key=lambda c: c["_ts"], reverse=True)


def _public(cap: dict[str, Any]) -> dict[str, Any]:
    slug = characters.slugify(cap["name"], cap["_slug_realm"])
    saved = characters.get(slug)
    saved_at = saved.imported_at if saved else None
    cap_dt, saved_dt = _parse_iso(cap["captured_at"]), _parse_iso(saved_at)
    newer = saved is None or saved_dt is None or (cap_dt is not None and cap_dt > saved_dt)
    out = {k: v for k, v in cap.items() if k not in ("simc", "_ts", "_slug_realm")}
    out.update(saved_slug=slug, saved_imported_at=saved_at, newer_than_saved=newer)
    return out


def list_captures(wow_dir: str | Path | None = None) -> list[dict[str, Any]]:
    wow = config.settings.wow_dir if wow_dir is None else wow_dir
    return [_public(c) for c in _raw_captures(wow)]


def import_capture(key: str | None = None, wow_dir: str | Path | None = None,
                   save: bool = True) -> CharacterProfile:
    """Import the capture ``key`` (``Name-Realm``), or the newest one when ``key`` is None.

    Raises :class:`NoAddonData`, :class:`UnknownCapture` or ``profile.ProfileError``."""
    wow = config.settings.wow_dir if wow_dir is None else wow_dir
    caps = _raw_captures(wow)
    if not caps:
        raise NoAddonData(NOT_FOUND_MESSAGE)
    if key is None:
        cap = caps[0]
    else:
        cap = next((c for c in caps if c["key"] == key or c["key"].lower() == key.lower()), None)
        if cap is None:
            raise UnknownCapture(f"No addon capture for {key!r}. Available: {', '.join(c['key'] for c in caps)}")
    profile = profile_mod.parse(cap["simc"])
    profile.imported_at = cap["captured_at"]
    profile.source = "addon"
    if save:
        try:
            characters.save(profile)
        except Exception:
            log.exception("could not save imported character %s-%s", profile.name, profile.realm)
    return profile


def import_all(wow_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """Import every capture that is newer than what is saved; one result per capture, never raises
    for a single bad capture. Result: ``{key, status: imported|skipped|error, detail, profile}``."""
    wow = config.settings.wow_dir if wow_dir is None else wow_dir
    results: list[dict[str, Any]] = []
    for cap in _raw_captures(wow):
        key = cap["key"]
        pub = _public(cap)
        if not pub["newer_than_saved"]:
            results.append({"key": key, "status": "skipped", "profile": None,
                            "detail": "saved profile is already up to date (not older than this capture)"})
            continue
        try:
            profile = import_capture(key, wow)
        except Exception as e:  # noqa: BLE001 - per-capture isolation
            results.append({"key": key, "status": "error", "profile": None, "detail": str(e)})
            continue
        results.append({"key": key, "status": "imported", "profile": profile, "detail": None})
    return results
