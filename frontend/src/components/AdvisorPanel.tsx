import { useMemo, useState } from 'react'
import type { AdvisorCandidate, AdvisorResult, AdvisorVerdict } from '../lib/types'
import { SLOT_LABELS, titleCase } from '../lib/wow'
import { ItemCard } from './ItemCard'
import { Collapsible } from './ui'

const VERDICTS: AdvisorVerdict[] = ['obvious', 'likely', 'sim_to_confirm', 'sidegrade', 'downgrade']

const VERDICT_STYLE: Record<AdvisorVerdict, string> = {
  obvious: 'text-good border-emerald-700/60',
  likely: 'text-info border-sky-800/60',
  sim_to_confirm: 'text-amber-300 border-amber-700/60',
  sidegrade: 'text-muted',
  downgrade: 'text-bad border-red-900/60',
}

const VERDICT_LABEL: Record<AdvisorVerdict, string> = {
  obvious: 'Obvious', likely: 'Likely', sim_to_confirm: 'Sim to confirm', sidegrade: 'Sidegrade', downgrade: 'Downgrade',
}

export function VerdictChip({ verdict }: { verdict: AdvisorVerdict }) {
  return <span className={`chip ${VERDICT_STYLE[verdict]}`}>{VERDICT_LABEL[verdict]}</span>
}

const EFFORT_LABEL: Record<string, string> = { trivial: 'Trivial', easy: 'Easy', medium: 'Medium', hard: 'Hard', very_hard: 'Very hard' }

function CandidateRow({ candidate }: { candidate: AdvisorCandidate }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-border bg-bg-soft p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <ItemCard item={candidate.item} className="min-w-0 flex-1" />
        <VerdictChip verdict={candidate.verdict} />
        <span className="chip">{EFFORT_LABEL[candidate.source.effort] ?? candidate.source.effort}</span>
        {candidate.source.weekly && <span className="chip text-fuchsia-300 border-fuchsia-900/60">weekly</span>}
        <span className="text-xs tabular-nums text-muted">
          {candidate.ilevel_gain >= 0 ? '+' : ''}{candidate.ilevel_gain} ilvl
          {candidate.ilevel_gain_max !== candidate.ilevel_gain ? ` (max ${candidate.ilevel_gain_max >= 0 ? '+' : ''}${candidate.ilevel_gain_max})` : ''}
        </span>
      </div>
      {candidate.reasons.length > 0 && (
        <div className="flex flex-wrap gap-1 text-xs text-muted">
          {candidate.reasons.map((r, i) => <span key={i} className="chip">{r}</span>)}
        </div>
      )}
      {candidate.path.length > 0 && (
        <ol className="ml-4 list-decimal text-xs text-muted">
          {candidate.path.map((step, i) => (
            <li key={i}>
              {step.step}
              {step.crest && <span className="text-faint"> ({step.cost ?? '?'} {step.crest})</span>}
            </li>
          ))}
        </ol>
      )}
      {candidate.alternatives.length > 0 && (
        <div className="text-[11px] text-faint">{candidate.alternatives.join(' · ')}</div>
      )}
    </div>
  )
}

/** Renders a raw AdvisorResult (POST /api/advisor/obvious-upgrades) — verdict filter chips plus a
 * per-slot accordion of candidates. Used both for the report detail page's "Refresh advisor" panel
 * and could stand alone for any freshly-fetched advisor result. */
export function AdvisorPanel({ result }: { result: AdvisorResult }) {
  const [active, setActive] = useState<Set<AdvisorVerdict>>(new Set(VERDICTS))

  const toggle = (v: AdvisorVerdict) => setActive((s) => {
    const next = new Set(s)
    if (next.has(v)) next.delete(v); else next.add(v)
    return next
  })

  const counts = useMemo(() => {
    const c: Record<AdvisorVerdict, number> = { obvious: 0, likely: 0, sim_to_confirm: 0, sidegrade: 0, downgrade: 0 }
    for (const slot of result.slots) for (const cand of slot.candidates) c[cand.verdict]++
    return c
  }, [result])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>
          Stat priority: {result.stat_priority.order.map((s) => titleCase(s)).join(' > ')}
          {' · '}{result.tier.equipped_pieces}/5 tier equipped
          {result.tier.catalyst_charges != null && ` · ${result.tier.catalyst_charges} catalyst charge${result.tier.catalyst_charges === 1 ? '' : 's'}`}
        </span>
        <span className="text-faint">Generated {new Date(result.generated_at).toLocaleString()}</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {VERDICTS.map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => toggle(v)}
            className={`chip cursor-pointer ${VERDICT_STYLE[v]} ${active.has(v) ? '' : 'opacity-35'}`}
          >
            {VERDICT_LABEL[v]} ({counts[v]})
          </button>
        ))}
      </div>
      {result.notes.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-muted">
          {result.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
      <div className="flex flex-col">
        {result.slots.map((slot) => {
          const shown = slot.candidates.filter((c) => active.has(c.verdict))
          return (
            <Collapsible
              key={slot.slot}
              title={
                <span className="flex items-center gap-2">
                  <span>{SLOT_LABELS[slot.slot] ?? titleCase(slot.slot)}</span>
                  <span className="text-faint">— {slot.equipped.item.name} (ilvl {slot.equipped.ilevel})</span>
                </span>
              }
              right={<span>{shown.length}/{slot.candidates.length} shown</span>}
            >
              {shown.length === 0 ? (
                <div className="text-xs text-faint">No candidates match the active verdict filters.</div>
              ) : (
                <div className="flex flex-col gap-2">
                  {shown.map((c, i) => <CandidateRow key={`${c.item.key}-${i}`} candidate={c} />)}
                </div>
              )}
            </Collapsible>
          )
        })}
      </div>
    </div>
  )
}
