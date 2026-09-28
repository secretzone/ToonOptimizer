"""Self-contained HTML report (inline CSS, no JavaScript) for a SimResult."""
from __future__ import annotations

from html import escape

from toonopt.models import SimResult

_CSS = """
:root{--bg:#0f1115;--panel:#181b22;--fg:#e6e6e6;--muted:#9aa0a6;--bar:#4f8ef7;--base:#8b8f97;--pos:#3ecf8e;--neg:#f06a6a;--line:#2a2e37}
*{box-sizing:border-box}body{margin:0;padding:24px;font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.sub{color:var(--muted);margin-bottom:18px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
table{width:100%;border-collapse:collapse}th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--line);vertical-align:middle}
th{color:var(--muted);font-weight:600;font-size:12px}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.bar{position:relative;height:18px;background:#22262e;border-radius:3px;min-width:160px}.bar>i{position:absolute;left:0;top:0;bottom:0;background:var(--bar);border-radius:3px}
.bar.base>i{background:var(--base)}.pos{color:var(--pos)}.neg{color:var(--neg)}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;word-break:break-all}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px 16px}.kv div b{display:block;color:var(--muted);font-size:11px;font-weight:600}
"""


def _fmt(n: float, digits: int = 0) -> str:
    return f"{n:,.{digits}f}"


def _delta_cls(d: float) -> str:
    return "pos" if d > 0 else ("neg" if d < 0 else "")


def render(res: SimResult) -> str:
    rows = res.results
    base = res.baseline
    max_dps = max([base.dps, *(r.dps for r in rows)]) or 1.0
    parts: list[str] = []
    title = f"{res.character or 'Sim'} - {res.spec.replace('_', ' ').title()} {res.klass.replace('_', ' ').title()}".strip(" -")
    parts.append(f"<h1>{escape(title)}</h1>")
    parts.append(
        f"<div class='sub'>{escape(res.type)} | {escape(res.simc_version)} | WoW {escape(res.wow_version)} | "
        f"{escape(res.options.fight_style)} {res.options.max_time}s x{res.options.desired_targets} | "
        f"{_fmt(res.timing.iterations)} iterations in {_fmt(res.timing.seconds, 1)}s</div>"
    )
    # ranking
    parts.append("<h2>Ranking</h2><div class='panel'><table><tr><th>#</th><th>Profile</th><th></th><th class='num'>DPS</th><th class='num'>+/-</th><th class='num'>Delta</th><th class='num'>%</th></tr>")

    def bar(dps: float, cls: str = "") -> str:
        w = max(0.0, min(100.0, dps / max_dps * 100.0))
        return f"<td><div class='bar {cls}'><i style='width:{w:.1f}%'></i></div></td>"

    ranked = sorted([("baseline", base.label, base.dps, base.dps_error, 0.0, 0.0, "base")]
                    + [(r.name, r.label, r.dps, r.dps_error, r.delta, r.delta_pct, "") for r in rows],
                    key=lambda t: t[2], reverse=True)
    for i, (_, label, dps, err, delta, pct, cls) in enumerate(ranked, 1):
        dcls = _delta_cls(delta)
        parts.append(
            f"<tr><td>{i}</td><td>{escape(label)}</td>{bar(dps, cls)}<td class='num'>{_fmt(dps)}</td>"
            f"<td class='num'>&plusmn;{_fmt(err)}</td><td class='num {dcls}'>{delta:+,.0f}</td><td class='num {dcls}'>{pct:+.2f}%</td></tr>"
        )
    parts.append("</table></div>")
    # stat weights
    if res.stat_weights:
        sw = res.stat_weights
        parts.append("<h2>Stat weights</h2><div class='panel'><table><tr><th>Stat</th><th class='num'>Weight</th><th class='num'>Normalized</th><th class='num'>Error</th></tr>")
        for stat, w in sorted(sw.weights.items(), key=lambda kv: kv[1], reverse=True):
            parts.append(f"<tr><td>{escape(stat)}</td><td class='num'>{w:.3f}</td><td class='num'>{sw.normalized.get(stat, 0):.3f}</td><td class='num'>{sw.error.get(stat, 0):.3f}</td></tr>")
        parts.append(f"</table><p class='mono'>{escape(sw.pawn)}</p></div>")
    # breakdown
    if res.breakdown:
        parts.append("<h2>Damage breakdown</h2><div class='panel'><table><tr><th>Ability</th><th>Type</th><th class='num'>DPS</th><th class='num'>%</th><th class='num'>Count</th><th class='num'>Hits</th><th class='num'>Crits</th><th class='num'>Crit %</th></tr>")
        for b in res.breakdown[:60]:
            parts.append(
                f"<tr><td>{escape(b.name)}</td><td>{b.type}</td><td class='num'>{_fmt(b.total)}</td><td class='num'>{b.pct:.1f}%</td>"
                f"<td class='num'>{b.count:.1f}</td><td class='num'>{b.hit:.1f}</td><td class='num'>{b.crit:.1f}</td><td class='num'>{b.crit_pct:.1f}%</td></tr>"
            )
        parts.append("</table></div>")
    # uptimes
    if res.uptimes:
        parts.append("<h2>Buff uptimes</h2><div class='panel'><table><tr><th>Buff</th><th></th><th class='num'>Uptime</th></tr>")
        for u in res.uptimes[:60]:
            parts.append(f"<tr><td>{escape(u.name)}</td><td><div class='bar'><i style='width:{min(100.0, u.pct):.1f}%'></i></div></td><td class='num'>{u.pct:.1f}%</td></tr>")
        parts.append("</table></div>")
    # options
    o = res.options
    parts.append("<h2>Options</h2><div class='panel kv'>")
    for k, v in (("Fight", o.fight_style), ("Length", f"{o.max_time}s +/-{o.vary_combat_length * 100:.0f}%"), ("Targets", o.desired_targets),
                 ("Precision", f"{o.iterations} iterations" if o.iterations else f"target error {o.target_error}"),
                 ("Buffs", ", ".join(k for k, on in o.buffs.items() if on) or "none"),
                 ("Consumables", ", ".join(f"{k}={v}" for k, v in o.consumables.model_dump().items() if v) or "none"),
                 ("PTR", "yes" if o.ptr else "no"), ("Input", res.input_file)):
        parts.append(f"<div><b>{escape(str(k))}</b>{escape(str(v))}</div>")
    parts.append("</div>")
    return (
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(title)}</title><style>{_CSS}</style></head><body>" + "".join(parts) + "</body></html>"
    )
