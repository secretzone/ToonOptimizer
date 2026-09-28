import { useMemo, useState } from 'react'
import { AlertTriangle, Download, ArrowUpDown, Info } from 'lucide-react'
import type { BreakdownRow, SimResult } from '../lib/types'
import { api } from '../lib/api'
import { fmtDps, fmtDuration, downloadText } from '../lib/format'
import { CLASS_COLORS, metricLabel, titleCase } from '../lib/wow'
import { CopyButton, Card } from './ui'
import { useStore } from '../store'

/** Warns when `json2 players[0].valid_fight_style` came back false — the fight style couldn't
 * actually be applied as requested (e.g. an APL with no movement handling on LightMovement). */
export function FightStyleWarning({ result }: { result: SimResult }) {
  if (result.valid_fight_style !== false) return null
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-600/50 bg-amber-500/10 p-3 text-sm text-amber-200">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-400" />
      <span>SimC reported this APL could not fully honor the <span className="font-medium">{result.options.fight_style}</span> fight style — results may not reflect the intended scenario.</span>
    </div>
  )
}

export function DpsHero({ result }: { result: SimResult }) {
  const color = CLASS_COLORS[result.klass] ?? '#fff'
  const errPct = result.baseline.dps ? (result.baseline.dps_error / result.baseline.dps) * 100 : 0
  const metric = metricLabel(result.metric)
  return (
    <div className="flex flex-col gap-3">
      <div className="card flex flex-wrap items-center gap-6 p-5" style={{ borderLeft: `4px solid ${color}` }}>
        <div>
          <div className="label">{result.baseline.label}</div>
          <div className="text-4xl font-bold tabular-nums tracking-tight">{fmtDps(result.baseline.dps)}<span className="ml-2 text-base font-normal text-muted">{metric}</span></div>
          <div className="text-sm text-muted">± {fmtDps(result.baseline.dps_error)} ({errPct.toFixed(2)}%)</div>
        </div>
        <div className="ml-auto grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-4">
          <div><div className="label">Character</div><div className="text-sm text-text" style={{ color }}>{result.character} · {titleCase(result.spec)}</div></div>
          <div><div className="label">Fight</div><div className="text-sm text-text">{result.options.fight_style} · {result.options.max_time}s · {result.options.desired_targets}T</div></div>
          <div><div className="label">Iterations</div><div className="text-sm text-text">{result.timing.iterations.toLocaleString()} in {fmtDuration(result.timing.seconds)}</div></div>
          <div><div className="label">SimC</div><div className="truncate text-sm text-text" title={result.simc_version}>{result.wow_version || result.simc_version}</div></div>
        </div>
      </div>
      <FightStyleWarning result={result} />
    </div>
  )
}

/** Info box for non-fatal skips the upgrades/gems engines surface (e.g. slots with no
 * remaining upgrade, items with no sockets). Renders nothing when there's nothing to say. */
export function ResultNotes({ notes }: { notes?: string[] }) {
  if (!notes || notes.length === 0) return null
  return (
    <div className="card flex flex-col gap-1.5 border-l-4 border-info bg-info/5 p-3">
      {notes.map((note, i) => (
        <div key={i} className="flex items-start gap-2 text-sm text-muted">
          <Info size={14} className="mt-0.5 shrink-0 text-info" />
          <span>{note}</span>
        </div>
      ))}
    </div>
  )
}

export function ResultActions({ result }: { result: SimResult }) {
  const toast = useStore((s) => s.toast)
  return (
    <div className="flex flex-wrap gap-2">
      <CopyButton label="Copy simc input" text={() => api.input(result.job_id)} />
      <button type="button" className="btn btn-sm" onClick={() => api.input(result.job_id).then((t) => downloadText(`${result.character}-${result.type}-${result.job_id}.simc`, t)).catch((e: Error) => toast(e.message, 'error'))}>
        <Download size={13} /> .simc
      </button>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => api.report(result.job_id).then((html) => downloadText(`${result.character}-${result.type}-${result.job_id}.html`, html, 'text/html')).catch((e: Error) => toast(e.message, 'error'))}
      >
        <Download size={13} /> Report
      </button>
      <a className="btn btn-sm" href={api.reportUrl(result.job_id)} target="_blank" rel="noreferrer">Open report</a>
      <a className="btn btn-sm" href={api.simcReportUrl(result.job_id)} target="_blank" rel="noreferrer">SimC report</a>
    </div>
  )
}

type SortKey = keyof BreakdownRow
export function BreakdownTable({ rows }: { rows: BreakdownRow[] }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'total', dir: -1 })
  const sorted = useMemo(() => {
    const out = [...rows]
    out.sort((a, b) => {
      const x = a[sort.key]
      const y = b[sort.key]
      if (typeof x === 'number' && typeof y === 'number') return (x - y) * sort.dir
      return String(x).localeCompare(String(y)) * sort.dir
    })
    return out
  }, [rows, sort])
  const maxPct = Math.max(...rows.map((r) => r.pct), 1)
  const th = (key: SortKey, label: string, cls = '') => (
    <th className={`cursor-pointer select-none px-2 py-1.5 text-xs font-medium text-muted hover:text-text ${cls}`} onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : -1 }))}>
      <span className="inline-flex items-center gap-1">{label}{sort.key === key && <ArrowUpDown size={11} className="text-accent" />}</span>
    </th>
  )
  const typeColor: Record<string, string> = { direct: 'text-text', periodic: 'text-info', pet: 'text-violet-300' }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left">
            {th('name', 'Ability')}
            {th('type', 'Type')}
            {th('pct', '% of total', 'text-right')}
            {th('total', 'Damage', 'text-right')}
            {th('count', 'Count', 'text-right')}
            {th('hit', 'Avg hit', 'text-right')}
            {th('crit', 'Avg crit', 'text-right')}
            {th('crit_pct', 'Crit %', 'text-right')}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={`${r.id}-${r.name}-${r.type}`} className="border-b border-border/50 hover:bg-surface-2">
              <td className="px-2 py-1.5 font-medium">{r.name}</td>
              <td className={`px-2 py-1.5 text-xs ${typeColor[r.type] ?? ''}`}>{r.type}</td>
              <td className="px-2 py-1.5 text-right tabular-nums">
                <div className="flex items-center justify-end gap-2">
                  <div className="h-1.5 w-20 overflow-hidden rounded bg-bg-soft"><div className="bar-fill h-full" style={{ width: `${(r.pct / maxPct) * 100}%` }} /></div>
                  <span className="w-12">{r.pct.toFixed(1)}%</span>
                </div>
              </td>
              <td className="px-2 py-1.5 text-right tabular-nums">{fmtDps(r.total)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums text-muted">{fmtDps(r.count, 1)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums text-muted">{fmtDps(r.hit)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums text-muted">{fmtDps(r.crit)}</td>
              <td className="px-2 py-1.5 text-right tabular-nums text-muted">{r.crit_pct.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Uptimes({ rows }: { rows: { name: string; pct: number }[] }) {
  const sorted = [...rows].sort((a, b) => b.pct - a.pct)
  return (
    <div className="flex flex-col gap-1.5">
      {sorted.map((u, i) => (
        <div key={`${u.name}-${i}`} className="flex items-center gap-2 text-sm">
          <span className="w-44 truncate" title={u.name}>{u.name}</span>
          <div className="h-2 flex-1 overflow-hidden rounded bg-bg-soft"><div className="h-full rounded bg-info/70" style={{ width: `${Math.min(100, u.pct)}%` }} /></div>
          <span className="w-12 text-right tabular-nums text-muted">{u.pct.toFixed(1)}%</span>
        </div>
      ))}
    </div>
  )
}

/** Full single-actor result: hero, breakdown, uptimes, actions. */
export function SingleResult({ result }: { result: SimResult }) {
  return (
    <div className="flex flex-col gap-4">
      <DpsHero result={result} />
      <ResultActions result={result} />
      <ResultNotes notes={result.notes} />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[2fr_1fr]">
        <Card title="Ability breakdown">
          {result.breakdown.length ? <BreakdownTable rows={result.breakdown} /> : <div className="text-sm text-muted">No breakdown available.</div>}
        </Card>
        <Card title="Buff uptimes">
          {result.uptimes.length ? <Uptimes rows={result.uptimes} /> : <div className="text-sm text-muted">No uptime data.</div>}
        </Card>
      </div>
    </div>
  )
}
