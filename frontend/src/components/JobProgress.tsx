import { useEffect, useRef, useState } from 'react'
import { XCircle, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import type { Job } from '../lib/types'
import { isTerminal } from '../lib/api'
import { fmtDuration } from '../lib/format'
import { Spinner } from './ui'

type Timing = { eta: number | null; elapsed: number }

// The backend has no structured "warning" flag on progress; it just reuses `message` for the
// note it sets when Top Gear's smart (GPU surrogate) mode has no trained model and falls back
// to the normal search (see toonopt.sims.topgear.execute). Detect it by content instead.
const SURROGATE_FALLBACK_RE = /falling back|no surrogate model/i
function isSurrogateWarning(job: Job): boolean {
  return job.type === 'topgear' && SURROGATE_FALLBACK_RE.test(job.progress.message)
}

/** Progress card with ETA from the observed rate of pct change. */
export function JobProgress({ job, onCancel, compact = false }: { job: Job; onCancel?: () => void; compact?: boolean }) {
  const terminal = isTerminal(job)
  const [timing, setTiming] = useState<Timing>({ eta: null, elapsed: 0 })
  const latest = useRef({ pct: job.progress.pct, started: job.started ?? null })
  const samples = useRef<{ t: number; pct: number }[]>([])

  // Keep the latest progress in a ref so the ticker can read it without re-subscribing.
  useEffect(() => {
    latest.current = { pct: job.progress.pct, started: job.started ?? null }
  }, [job.progress.pct, job.started])

  // Sample + compute on a timer (external system: the wall clock).
  useEffect(() => {
    if (terminal) return
    samples.current = []
    const tick = () => {
      const now = Date.now()
      const { pct, started } = latest.current
      const s = samples.current
      if (!s.length || s[s.length - 1].pct !== pct) s.push({ t: now, pct })
      if (s.length > 30) s.splice(0, s.length - 30)
      let eta: number | null = null
      if (s.length >= 2) {
        const first = s[0]
        const last = s[s.length - 1]
        const rate = (last.pct - first.pct) / Math.max(1, last.t - first.t)
        if (rate > 0) eta = ((100 - pct) / rate) / 1000
      }
      setTiming({ eta, elapsed: started ? (now - new Date(started).getTime()) / 1000 : 0 })
    }
    const id = setInterval(tick, 500)
    return () => clearInterval(id)
  }, [terminal, job.id])

  const pct = Math.max(0, Math.min(100, job.progress.pct || 0))
  const total = job.started && job.finished ? (new Date(job.finished).getTime() - new Date(job.started).getTime()) / 1000 : null
  const warning = isSurrogateWarning(job)
  // surrogate_train's message carries the epoch/val_mae detail; always worth showing, not just on sm+.
  const alwaysShowMessage = job.type === 'surrogate_train'
  const hasMessage = job.progress.message && job.progress.message !== job.progress.phase

  const status =
    job.status === 'done' ? <span className="flex items-center gap-1 text-good"><CheckCircle2 size={14} /> Done</span>
    : job.status === 'failed' ? <span className="flex items-center gap-1 text-bad"><AlertTriangle size={14} /> Failed</span>
    : job.status === 'cancelled' ? <span className="flex items-center gap-1 text-muted"><XCircle size={14} /> Cancelled</span>
    : job.status === 'queued' ? <span className="flex items-center gap-1 text-muted"><Clock size={14} /> Queued</span>
    : <span className="flex items-center gap-1.5 text-accent"><Spinner /> Running</span>

  return (
    <div className={`card ${compact ? 'p-3' : 'p-4'}`} aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-sm">
          {status}
          <span className="text-muted capitalize">{job.progress.phase}</span>
          {hasMessage && !warning && (
            <span className={`mono text-xs text-faint ${alwaysShowMessage ? 'inline' : 'hidden sm:inline'}`}>{job.progress.message}</span>
          )}
        </div>
        <div className="flex items-center gap-3 text-xs tabular-nums text-muted">
          {!terminal && job.started && <span>elapsed {fmtDuration(timing.elapsed)}</span>}
          {!terminal && timing.eta != null && <span>eta {fmtDuration(timing.eta)}</span>}
          {terminal && total != null && <span>{fmtDuration(total)}</span>}
          <span className="w-10 text-right font-medium text-text">{pct.toFixed(0)}%</span>
          {onCancel && !terminal && (
            <button type="button" onClick={onCancel} className="btn btn-sm btn-danger">Cancel</button>
          )}
        </div>
      </div>
      <div className="relative mt-2.5 h-2 overflow-hidden rounded-full bg-surface-3">
        <div className={`h-full rounded-full transition-[width] duration-300 ${job.status === 'failed' ? 'bg-bad' : job.status === 'cancelled' ? 'bg-faint' : 'bar-fill'}`} style={{ width: `${pct}%` }} />
        {!terminal && <div className="shimmer absolute inset-0" />}
      </div>
      {warning && (
        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-accent-dim bg-accent/10 px-2 py-1.5 text-xs text-accent-strong">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>{job.progress.message}</span>
        </div>
      )}
      {job.error && <div className="mt-2 text-xs text-bad">{job.error}</div>}
      <div className="mono mt-1.5 text-[10px] text-faint">job {job.id}{job.progress.total ? ` · ${job.progress.current.toLocaleString()} / ${job.progress.total.toLocaleString()}` : ''}</div>
    </div>
  )
}
