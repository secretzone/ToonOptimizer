import { useMemo, useState, type ReactNode } from 'react'
import type { ResultRow, SimResult } from '../lib/types'
import { fmtDps, fmtPct } from '../lib/format'

const PAGE = 100

type Props = {
  baseline: SimResult['baseline']
  rows: ResultRow[]
  selected?: string | null
  onSelect?: (row: ResultRow | null) => void
  renderLeft?: (row: ResultRow) => ReactNode
  renderExtra?: (row: ResultRow) => ReactNode
  labelWidth?: number
  showRank?: boolean
  /** True for metrics where a lower value is the improvement (dtps, dmg_taken) — see
   * lib/wow.isLowerBetter. Flips the good/bad color and the "worse than baseline" bar style. */
  lowerBetter?: boolean
}

type RowProps = {
  label: string; dps: number; err: number; deltaPct: number | null; isBase: boolean; rank?: number
  w: number; e: number; sel: boolean; onClick?: () => void; left?: ReactNode; extra?: ReactNode; showRank: boolean; labelWidth: number
  lowerBetter?: boolean; stage?: number | null
}

function BarRow({ label, dps, err, deltaPct, isBase, rank, w, e, sel, onClick, left, extra, showRank, labelWidth, lowerBetter, stage }: RowProps) {
  const worse = deltaPct != null && (lowerBetter ? deltaPct > 0 : deltaPct < 0)
  const neg = worse
  return (
    <div
      className={`group flex items-center gap-3 rounded-md px-2 py-1 ${isBase ? 'sticky top-0 z-10 border-b border-border bg-surface' : ''} ${onClick ? 'cursor-pointer hover:bg-surface-2' : ''} ${sel ? 'bg-accent/10 ring-1 ring-accent/50' : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onClick() } } : undefined}
    >
      {showRank && <span className="w-7 shrink-0 text-right text-xs tabular-nums text-faint">{isBase ? '—' : rank}</span>}
      <div className="flex min-w-0 shrink-0 items-center gap-2" style={{ width: labelWidth }}>
        {left ?? <span className={`truncate text-sm ${isBase ? 'font-semibold text-info' : ''}`} title={label}>{label}</span>}
      </div>
      <div className="relative h-5 min-w-0 flex-1 overflow-hidden rounded bg-bg-soft">
        <div className={`h-full rounded ${isBase ? 'bar-fill-base' : neg ? 'bar-fill-neg' : 'bar-fill'}`} style={{ width: `${w}%` }} />
        {e > 0 && (
          <div className="absolute top-1/2 h-2.5 -translate-y-1/2 border-x border-white/60" style={{ left: `${w - e}%`, width: `${2 * e}%` }}>
            <div className="absolute top-1/2 h-px w-full bg-white/60" />
          </div>
        )}
      </div>
      <div className="flex w-[210px] shrink-0 items-baseline justify-end gap-2 text-right tabular-nums">
        <span className="text-sm font-medium">{fmtDps(dps)}</span>
        <span className="w-14 text-[11px] text-faint">± {fmtDps(err)}</span>
        <span className={`w-16 text-xs font-medium ${deltaPct == null ? 'text-faint' : (lowerBetter ? deltaPct <= 0 : deltaPct >= 0) ? 'text-good' : 'text-bad'}`}>{deltaPct == null ? '' : fmtPct(deltaPct)}</span>
      </div>
      {stage != null && <span className="chip shrink-0 text-[10px] text-muted" title={`Reached Smart Sim precision stage ${stage}`}>stage {stage}</span>}
      {extra && <div className="shrink-0">{extra}</div>}
    </div>
  )
}

/** Ranked horizontal bars scaled to max dps. Baseline pinned to top. Paginated above 200 rows. */
export function ResultBars({ baseline, rows, selected, onSelect, renderLeft, renderExtra, labelWidth = 260, showRank = true, lowerBetter = false }: Props) {
  const [page, setPage] = useState(0)
  const paginated = rows.length > 200
  const safePage = Math.min(page, Math.max(0, Math.ceil(rows.length / PAGE) - 1))
  const pageRows = paginated ? rows.slice(safePage * PAGE, (safePage + 1) * PAGE) : rows
  const { max, floor } = useMemo(() => {
    const mx = Math.max(baseline.dps, ...rows.map((r) => r.dps))
    const mn = Math.min(baseline.dps, ...rows.map((r) => r.dps))
    // Scale bars so differences are visible: bar length spans from a bit below min to max.
    return { max: mx, floor: Math.max(0, mn - (mx - mn) * 0.15) }
  }, [rows, baseline.dps])
  const width = (dps: number) => (max === floor ? 100 : ((dps - floor) / (max - floor)) * 100)
  const errW = (err: number) => (max === floor ? 0 : (err / (max - floor)) * 100)

  return (
    <div className="flex flex-col">
      <BarRow label={baseline.label} dps={baseline.dps} err={baseline.dps_error} deltaPct={null} isBase w={width(baseline.dps)} e={errW(baseline.dps_error)} sel={false} showRank={showRank} labelWidth={labelWidth} lowerBetter={lowerBetter} />
      <div className="mt-1 flex flex-col">
        {pageRows.map((r, i) => {
          const sel = selected === r.name
          return (
            <BarRow
              key={r.name}
              label={r.label}
              dps={r.dps}
              err={r.dps_error}
              deltaPct={r.delta_pct}
              isBase={false}
              rank={(paginated ? safePage * PAGE : 0) + i + 1}
              w={width(r.dps)}
              e={errW(r.dps_error)}
              sel={sel}
              onClick={onSelect ? () => onSelect(sel ? null : r) : undefined}
              left={renderLeft?.(r)}
              extra={renderExtra?.(r)}
              showRank={showRank}
              labelWidth={labelWidth}
              lowerBetter={lowerBetter}
              stage={r.meta?.stage}
            />
          )
        })}
      </div>
      {paginated && (
        <div className="mt-3 flex items-center justify-between text-xs text-muted">
          <span>{rows.length} results · page {safePage + 1} / {Math.ceil(rows.length / PAGE)}</span>
          <div className="flex gap-1">
            <button type="button" className="btn btn-sm" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>Prev</button>
            <button type="button" className="btn btn-sm" disabled={(safePage + 1) * PAGE >= rows.length} onClick={() => setPage(safePage + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
