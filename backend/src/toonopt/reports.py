"""Per-character report store (see API.md "Reports").

Layout, all under :data:`toonopt.config.REPORTS_DIR` (repo root ``reports/``, gitignored)::

    reports/<slug>.json            the CharacterReport
    reports/<slug>.md              human-readable markdown rendering of the same report
    reports/<slug>.history.json    [{updated_at, summary}, ...] newest first, last 20

``CharacterReport.sections`` are plain dicts (see ``models.CharacterReport`` docstring);
:func:`validate_report` checks each one against its declared ``kind`` before it is written.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from toonopt.config import REPORTS_DIR
from toonopt.models import CharacterReport, Item, now_iso

log = logging.getLogger(__name__)

MAX_HISTORY = 20
VALID_KINDS = {"markdown", "upgrades", "bis", "talents", "kv"}


class ReportValidationError(ValueError):
    pass


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ReportValidationError(msg)


def _validate_markdown(sec: dict) -> None:
    _require(isinstance(sec.get("title"), str), "markdown section needs a string 'title'")
    _require(isinstance(sec.get("body"), str), "markdown section needs a string 'body'")


def _validate_upgrades(sec: dict) -> None:
    _require(isinstance(sec.get("title"), str), "upgrades section needs a string 'title'")
    rows = sec.get("rows")
    _require(isinstance(rows, list), "upgrades section needs a 'rows' list")
    for i, row in enumerate(rows):
        _require(isinstance(row, dict), f"upgrades row {i} must be an object")
        for key in ("slot", "current", "option", "verdict", "gain"):
            _require(isinstance(row.get(key), str), f"upgrades row {i} needs a string '{key}'")
        _require(isinstance(row.get("how", []), list), f"upgrades row {i}.how must be a list")
        sim = row.get("sim")
        if sim is not None:
            _require(isinstance(sim, dict) and "job_id" in sim and "delta_pct" in sim,
                      f"upgrades row {i}.sim must be {{job_id, delta_pct}}")


def _validate_bis(sec: dict) -> None:
    _require(isinstance(sec.get("title"), str), "bis section needs a string 'title'")
    rows = sec.get("rows")
    _require(isinstance(rows, list), "bis section needs a 'rows' list")
    for i, row in enumerate(rows):
        _require(isinstance(row, dict), f"bis row {i} must be an object")
        _require(isinstance(row.get("slot"), str), f"bis row {i} needs a string 'slot'")
        _require(isinstance(row.get("source"), str), f"bis row {i} needs a string 'source'")
        _require(isinstance(row.get("you_have"), bool), f"bis row {i} needs a boolean 'you_have'")
        try:
            Item.model_validate(row.get("item"))
        except Exception as e:
            raise ReportValidationError(f"bis row {i}.item is not a valid Item: {e}") from e


def _validate_talents(sec: dict) -> None:
    _require(isinstance(sec.get("title"), str), "talents section needs a string 'title'")
    entries = sec.get("entries")
    _require(isinstance(entries, list), "talents section needs an 'entries' list")
    for i, e in enumerate(entries):
        _require(isinstance(e, dict), f"talents entry {i} must be an object")
        for key in ("context", "loadout", "notes"):
            _require(isinstance(e.get(key), str), f"talents entry {i} needs a string '{key}'")


def _validate_kv(sec: dict) -> None:
    _require(isinstance(sec.get("title"), str), "kv section needs a string 'title'")
    items = sec.get("items")
    _require(isinstance(items, list), "kv section needs an 'items' list")
    for i, it in enumerate(items):
        _require(isinstance(it, dict), f"kv item {i} must be an object")
        _require(isinstance(it.get("label"), str), f"kv item {i} needs a string 'label'")
        _require(isinstance(it.get("value"), str), f"kv item {i} needs a string 'value'")


_VALIDATORS = {
    "markdown": _validate_markdown, "upgrades": _validate_upgrades, "bis": _validate_bis,
    "talents": _validate_talents, "kv": _validate_kv,
}


def validate_report(report: CharacterReport) -> None:
    for i, sec in enumerate(report.sections):
        if not isinstance(sec, dict):
            raise ReportValidationError(f"section {i} must be an object")
        kind = sec.get("kind")
        if kind not in VALID_KINDS:
            raise ReportValidationError(f"section {i} has unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}")
        _VALIDATORS[kind](sec)


# ---------------------------------------------------------------------------
# markdown rendering

def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |")
    return "\n".join(out)


def _render_section(sec: dict) -> str:
    kind = sec["kind"]
    title = sec.get("title", "")
    if kind == "markdown":
        return f"## {title}\n\n{sec['body']}\n"
    if kind == "upgrades":
        rows = [[r["slot"], r["current"], r["option"], r["verdict"], r["gain"], "; ".join(r.get("how", [])),
                 (f"{r['sim']['delta_pct']:+.2f}% ({r['sim']['job_id']})" if r.get("sim") else "")]
                for r in sec["rows"]]
        table = _md_table(["Slot", "Current", "Option", "Verdict", "Gain", "How", "Sim"], rows)
        return f"## {title}\n\n{table}\n"
    if kind == "bis":
        rows = [[r["slot"], r["item"].get("name", "") if isinstance(r["item"], dict) else "", r["source"],
                 "yes" if r["you_have"] else "no", r.get("theorycraft_says", "")]
                for r in sec["rows"]]
        table = _md_table(["Slot", "Item", "Source", "You have", "Theorycraft"], rows)
        return f"## {title}\n\n{table}\n"
    if kind == "talents":
        rows = [[e["context"], e["loadout"], e["notes"], e.get("source_url", "")] for e in sec["entries"]]
        table = _md_table(["Context", "Loadout", "Notes", "Source"], rows)
        return f"## {title}\n\n{table}\n"
    if kind == "kv":
        rows = [[it["label"], it["value"], it.get("note", "")] for it in sec["items"]]
        table = _md_table(["Label", "Value", "Note"], rows)
        return f"## {title}\n\n{table}\n"
    return ""  # pragma: no cover - unreachable, validate_report rejects unknown kinds first


def render_markdown(report: CharacterReport) -> str:
    lines = [
        f"# {report.character} ({report.realm}) -- {report.klass}/{report.spec}",
        "",
        f"_Updated {report.updated_at} -- ilvl {report.ilevel_equipped:g} -- {report.season} -- SimC {report.simc_version}_",
        "",
        report.summary,
        "",
    ]
    for sec in report.sections:
        lines.append(_render_section(sec))
        lines.append("")
    if report.sim_refs:
        lines.append("## Sim references")
        lines.append("")
        for ref in report.sim_refs:
            lines.append(f"- [{ref.label}](/#/history/{ref.job_id}) ({ref.type})")
        lines.append("")
    if report.sources:
        lines.append("## Sources")
        lines.append("")
        for src in report.sources:
            lines.append(f"- [{src.title}]({src.url}) (fetched {src.fetched_at})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# store

def _path(slug: str) -> Path:
    return REPORTS_DIR / f"{slug}.json"


def _md_path(slug: str) -> Path:
    return REPORTS_DIR / f"{slug}.md"


def _history_path(slug: str) -> Path:
    return REPORTS_DIR / f"{slug}.history.json"


def _read_history(slug: str) -> list[dict]:
    p = _history_path(slug)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except (ValueError, OSError):
        return []


def save(slug: str, report: CharacterReport) -> CharacterReport:
    """Validate, stamp ``updated_at``, and persist ``report`` (json + markdown + history)."""
    report = report.model_copy(update={"slug": slug, "updated_at": now_iso()})
    validate_report(report)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _path(slug).write_text(report.model_dump_json(indent=2), "utf-8")
    _md_path(slug).write_text(render_markdown(report), "utf-8")
    history = [{"updated_at": report.updated_at, "summary": report.summary}, *_read_history(slug)]
    _history_path(slug).write_text(json.dumps(history[:MAX_HISTORY], indent=2), "utf-8")
    return report


def get(slug: str) -> CharacterReport | None:
    p = _path(slug)
    if not p.exists():
        return None
    try:
        return CharacterReport.model_validate_json(p.read_text("utf-8"))
    except (ValueError, OSError) as e:
        log.warning("could not load report %s: %s", slug, e)
        return None


def history(slug: str) -> list[dict]:
    return _read_history(slug)


def list_reports() -> list[dict]:
    if not REPORTS_DIR.exists():
        return []
    out = []
    for p in sorted(REPORTS_DIR.glob("*.json")):
        try:
            report = CharacterReport.model_validate_json(p.read_text("utf-8"))
        except (ValueError, OSError) as e:
            log.warning("skipping report file %s: %s", p.name, e)
            continue
        out.append({
            "slug": report.slug, "character": report.character, "klass": report.klass, "spec": report.spec,
            "updated_at": report.updated_at, "summary": report.summary,
        })
    out.sort(key=lambda r: r["character"].lower())
    return out


def delete(slug: str) -> bool:
    existed = _path(slug).exists()
    _path(slug).unlink(missing_ok=True)
    _md_path(slug).unlink(missing_ok=True)
    _history_path(slug).unlink(missing_ok=True)
    return existed
