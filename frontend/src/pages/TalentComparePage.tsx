import { useEffect, useRef, useState } from 'react'
import { GitBranch, Play, Plus, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, CopyButton, Input, PageTitle, Tabs } from '../components/ui'
import { diffTalents, nodeNameLookup, normalizeDecoded, type TalentDiff } from '../lib/talents'
import { iconUrl, isLowerBetter } from '../lib/wow'
import type { OmniumCustomSet, OmniumMode, OmniumRow, Recommendations, TalentTrees } from '../lib/types'

type Loadout = { id: number; name: string; string: string }
let seq = 1

function DiffView({ diff, nameOf }: { diff: TalentDiff; nameOf: (id: number) => string }) {
  return (
    <div className="flex flex-wrap gap-1 text-[11px]">
      {diff.added.map((a) => <span key={`a${a.id}`} className="chip text-good">+ {nameOf(a.id)}{a.rank > 1 ? ` (${a.rank})` : ''}</span>)}
      {diff.removed.map((a) => <span key={`r${a.id}`} className="chip text-bad">- {nameOf(a.id)}</span>)}
      {diff.changed.map((a) => <span key={`c${a.id}`} className="chip text-accent">{nameOf(a.id)} {a.from}→{a.to}</span>)}
      {!diff.added.length && !diff.removed.length && !diff.changed.length && <span className="text-muted">identical</span>}
    </div>
  )
}

/** Omnium Folio tab: 5 rows, choices as icon buttons; the currently-picked entry (from
 * `profile.omnium`) is highlighted; Per row / Combos / Custom modes. */
function OmniumFolioTab() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('omnium')

  const recsCache = useStore((s) => s.recommendations)
  const setRecommendations = useStore((s) => s.setRecommendations)
  const recKey = profile ? `${profile.klass}:${profile.spec}` : null
  const recs: Recommendations | null = recKey ? (recsCache[recKey] ?? null) : null
  useEffect(() => {
    if (!profile || !recKey || recsCache[recKey]) return
    api.recommendations(profile.klass, profile.spec).then((r) => setRecommendations(recKey, r)).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recKey])
  const rows: OmniumRow[] = recs?.omnium?.rows ?? []

  const [mode, setMode] = useState<OmniumMode>('per_row')
  const [picks, setPicks] = useState<Record<number, number>>({})
  const [sets, setSets] = useState<(OmniumCustomSet & { id: number })[]>([])
  const setSeqRef = useRef(1)

  if (!profile) return <div className="text-sm text-muted">Import a character to see its Omnium Folio.</div>
  if (!rows.length) return <div className="text-sm text-muted">No Omnium Folio data for this spec yet.</div>

  const currentEntryFor = (row: OmniumRow): number | undefined => {
    const sel = profile.omnium ?? {}
    return row.choices.find((c) => sel[String(c.entry_id)] != null)?.entry_id ?? row.choices[0]?.entry_id
  }
  const canAddSet = rows.every((row) => picks[row.row] != null)
  const addSet = () => {
    if (!canAddSet) return
    setSets((prev) => [...prev, { id: setSeqRef.current++, name: `Set ${String.fromCharCode(65 + prev.length)}`, entries: rows.map((row) => picks[row.row]) }])
    setPicks({})
  }
  const canRun = mode === 'custom' ? sets.length > 0 : true

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Omnium Folio"
        actions={<Tabs value={mode} onChange={setMode} tabs={[{ value: 'per_row', label: 'Per row' }, { value: 'combos', label: 'Combos' }, { value: 'custom', label: 'Custom' }]} />}
      >
        <div className="flex flex-col gap-3">
          {rows.map((row) => {
            const current = currentEntryFor(row)
            return (
              <div key={row.row}>
                <div className="label mb-1">Row {row.row}</div>
                <div className="flex flex-wrap gap-2">
                  {row.choices.map((choice) => {
                    const isCurrent = current === choice.entry_id
                    const isPicked = mode === 'custom' && picks[row.row] === choice.entry_id
                    return (
                      <button
                        key={choice.entry_id}
                        type="button"
                        disabled={mode !== 'custom'}
                        onClick={() => setPicks((p) => ({ ...p, [row.row]: choice.entry_id }))}
                        title={`${choice.name}${isCurrent ? ' (current)' : ''}`}
                        className={`flex w-20 flex-col items-center gap-1 rounded-md border p-1.5 text-center transition-colors ${
                          isPicked ? 'border-accent bg-accent/10' : isCurrent ? 'border-info' : 'border-border'
                        } ${mode === 'custom' ? 'cursor-pointer hover:bg-surface-2' : 'cursor-default'}`}
                      >
                        <img src={iconUrl(choice.icon)} alt="" className="h-8 w-8 rounded" onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} />
                        <span className="w-full truncate text-[10px]">{choice.name}</span>
                        {isCurrent && <span className="chip text-[9px] text-info">current</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>

        {mode === 'custom' && (
          <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
            <div className="flex items-center gap-2">
              <button type="button" className="btn btn-sm" disabled={!canAddSet} onClick={addSet}><Plus size={13} /> Add set</button>
              <span className="text-xs text-muted">{canAddSet ? 'Pick one choice per row, then add.' : `Pick a choice for all ${rows.length} rows to add a set.`}</span>
            </div>
            {sets.length > 0 && (
              <div className="flex flex-col gap-1">
                {sets.map((s) => (
                  <div key={s.id} className="flex items-center justify-between rounded bg-bg-soft/50 px-2 py-1 text-sm">
                    <span>{s.name}</span>
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSets(sets.filter((x) => x.id !== s.id))} aria-label="Remove set"><Trash2 size={12} /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-3 border-t border-border pt-3">
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || !canRun}
            onClick={() => run(() => api.runOmnium({ profile, options, mode, sets: mode === 'custom' ? sets.map(({ name, entries }) => ({ name, entries })) : undefined }))}
          >
            <Play size={15} /> Run {mode === 'per_row' ? 'per row' : mode === 'combos' ? 'combos' : `${sets.length} set${sets.length === 1 ? '' : 's'}`}
          </button>
        </div>
      </Card>

      <OptionsPanel options={options} onChange={setOptions} show={{ gear: false, talents: false }} />

      {job && <JobProgress job={job} onCancel={cancel} />}
      {result && (
        <>
          <DpsHero result={result} />
          <ResultActions result={result} />
          <ResultNotes notes={result.notes} />
          <Card title={`${result.results.length} result${result.results.length === 1 ? '' : 's'}`}>
            <ResultBars baseline={result.baseline} rows={result.results} labelWidth={260} lowerBetter={isLowerBetter(result.metric)} />
          </Card>
        </>
      )}
    </div>
  )
}

export function TalentComparePage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('talentcompare')
  const [tab, setTab] = useState<'loadouts' | 'omnium'>('loadouts')
  // Seed one card per saved loadout when the page has no cards yet; otherwise the usual
  // "Current" (imported talents) + one blank starter card.
  const [loadouts, setLoadouts] = useState<Loadout[]>(() =>
    profile?.saved_loadouts?.length
      ? profile.saved_loadouts.map((l) => ({ id: seq++, name: l.name, string: l.string }))
      : [
          { id: seq++, name: 'Current', string: profile?.talents ?? '' },
          { id: seq++, name: 'Alternative', string: '' },
        ],
  )
  const [decoded, setDecoded] = useState<Record<string, { map: Map<number, number>; hero?: { id: number; name: string } | null }>>({})
  const inflight = useRef(new Set<string>())
  const [trees, setTrees] = useState<TalentTrees | null>(null)
  const [decodeOk, setDecodeOk] = useState<boolean | null>(null)

  useEffect(() => {
    if (!profile) return
    api.talents(profile.klass, profile.spec).then(setTrees).catch(() => setTrees(null))
  }, [profile?.klass, profile?.spec]) // eslint-disable-line react-hooks/exhaustive-deps

  // Decode loadouts when the result arrives (only for strings we haven't decoded).
  useEffect(() => {
    if (!result || !profile) return
    const strings = result.results.map((r) => r.meta.loadout).filter((s): s is string => !!s)
    for (const s of strings) {
      if (s in decoded || inflight.current.has(s)) continue
      inflight.current.add(s)
      api.decodeTalents(profile.klass, profile.spec, s)
        .then((d) => { setDecodeOk(true); setDecoded((prev) => ({ ...prev, [s]: { map: normalizeDecoded(d), hero: d.hero_tree } })) })
        .catch(() => setDecodeOk(false))
        .finally(() => inflight.current.delete(s))
    }
  }, [result, profile]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!profile) return <><PageTitle title="Talent Compare" /><NeedProfile /></>

  const valid = loadouts.filter((l) => l.string.trim())
  const update = (id: number, patch: Partial<Loadout>) => setLoadouts(loadouts.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  const nameOf = nodeNameLookup(trees)
  const baseString = result?.results.find((r) => r.meta.loadout === profile.talents)?.meta.loadout ?? result?.results[0]?.meta.loadout ?? null
  const baseDecoded = baseString ? decoded[baseString] : null

  return (
    <div>
      <PageTitle
        title="Talent Compare"
        subtitle="Sim several loadout strings side by side, or explore the Omnium Folio."
        actions={
          tab === 'loadouts' ? (
            <button type="button" className="btn btn-primary" disabled={running || !valid.length} onClick={() => run(() => api.talentcompare({ profile, options, loadouts: valid.map(({ name, string }) => ({ name, string: string.trim() })) }))}>
              <Play size={15} /> Compare {valid.length} loadout{valid.length === 1 ? '' : 's'}
            </button>
          ) : undefined
        }
      />
      <Tabs className="mb-4" value={tab} onChange={setTab} tabs={[{ value: 'loadouts', label: 'Loadouts' }, { value: 'omnium', label: 'Omnium Folio' }]} />
      {tab === 'omnium' ? (
        <OmniumFolioTab />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {loadouts.map((l) => (
                <Card
                  key={l.id}
                  title={<Input value={l.name} onChange={(e) => update(l.id, { name: e.target.value })} className="w-44 py-1 text-sm font-semibold" />}
                  actions={
                    <>
                      {l.string.trim() === profile.talents && <span className="chip text-info">imported</span>}
                      <button type="button" className="btn btn-sm btn-ghost" disabled={loadouts.length === 1} onClick={() => setLoadouts(loadouts.filter((x) => x.id !== l.id))} aria-label="Remove loadout"><Trash2 size={13} /></button>
                    </>
                  }
                >
                  <textarea className="input mono h-20 resize-y text-xs" placeholder="Paste a talent loadout string" value={l.string} onChange={(e) => update(l.id, { string: e.target.value })} spellCheck={false} />
                </Card>
              ))}
            </div>
            <button type="button" className="btn self-start" disabled={loadouts.length >= 10} onClick={() => setLoadouts([...loadouts, { id: seq++, name: `Loadout ${loadouts.length + 1}`, string: '' }])}><Plus size={14} /> Add loadout</button>

            {job && <JobProgress job={job} onCancel={cancel} />}
            {result ? (
              <>
                <DpsHero result={result} />
                <ResultActions result={result} />
                <ResultNotes notes={result.notes} />
                <Card title="Loadouts">
                  <ResultBars baseline={result.baseline} rows={result.results} showRank={false} labelWidth={200} lowerBetter={isLowerBetter(result.metric)} />
                </Card>
                <Card title="Loadout details" actions={decodeOk === false ? <span className="text-xs text-muted">decode unavailable — showing names only</span> : undefined}>
                  <div className="flex flex-col gap-3">
                    {result.results.map((r) => {
                      const s = r.meta.loadout ?? ''
                      const d = s ? decoded[s] : null
                      return (
                        <div key={r.name} className="rounded-md border border-border bg-bg-soft/40 p-3">
                          <div className="flex items-center justify-between gap-2">
                            <div className="text-sm font-medium">{r.label} <span className={`ml-1 text-xs ${r.delta_pct >= 0 ? 'text-good' : 'text-bad'}`}>{r.delta_pct >= 0 ? '+' : ''}{r.delta_pct.toFixed(2)}%</span></div>
                            <div className="flex items-center gap-2">
                              {d?.hero?.name && <span className="chip text-accent">{d.hero.name}</span>}
                              {d && <span className="text-xs text-muted">{d.map.size} nodes</span>}
                              {s && <CopyButton text={s} label="Copy" />}
                            </div>
                          </div>
                          {s && <div className="mono mt-1 truncate text-[10px] text-faint" title={s}>{s}</div>}
                          {d && baseDecoded && s !== baseString && (
                            <div className="mt-2"><div className="label mb-1">vs {result.results.find((x) => x.meta.loadout === baseString)?.label ?? 'first'}</div><DiffView diff={diffTalents(baseDecoded.map, d.map)} nameOf={nameOf} /></div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </Card>
              </>
            ) : !job && (
              <EmptyState icon={<GitBranch size={32} strokeWidth={1.5} />} title="Add loadout strings" body="Export loadouts from the in-game talent UI and paste them here. Your imported talents are pre-filled." />
            )}
          </div>
          <OptionsPanel options={options} onChange={setOptions} show={{ gear: false, talents: false }} />
        </div>
      )}
    </div>
  )
}
