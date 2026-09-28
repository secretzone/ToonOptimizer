import { useMemo, useState } from 'react'
import { ArrowUpCircle, Check, Play } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ChangedSlots } from '../components/ChangedSlots'
import { CurrencyStrip } from '../components/CurrencyStrip'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Checkbox, Field, Input, PageTitle } from '../components/ui'
import { fmtPct } from '../lib/format'
import { SLOT_LABELS, lowestEquippedIlevel } from '../lib/wow'
import { SLOTS, type CharacterProfile, type ResultRow } from '../lib/types'

/** Amounts owned per crest type, keyed by `Currency.crest` (same string as
 * `ResultRow.meta.upgrade.crest`), from the imported profile's currencies. */
function importedBudgetFor(profile: CharacterProfile | null): Record<string, number> {
  const budget: Record<string, number> = {}
  for (const c of profile?.currencies ?? []) if (c.crest) budget[c.crest] = c.amount
  return budget
}

/** Best gain-per-crest first, one row per slot, until each crest type's budget runs out. Skips
 * rows the profile's owned crests can't afford (`meta.upgrade.affordable === false`) even if the
 * (user-edited) budget above would allow it. Each row is an independent sim (see API.md), so the
 * summed gain is only an estimate. */
function greedySuggestedSpend(rows: ResultRow[], budget: Record<string, number>): { chosen: ResultRow[]; remaining: Record<string, number> } {
  const withUpgrade = rows.filter((r) => r.meta.upgrade && r.delta_pct > 0 && r.meta.upgrade.affordable !== false)
  const sorted = [...withUpgrade].sort((a, b) => {
    const ga = a.delta_pct / Math.max(1, a.meta.upgrade!.cost)
    const gb = b.delta_pct / Math.max(1, b.meta.upgrade!.cost)
    return gb - ga
  })
  const remaining = { ...budget }
  const chosenSlots = new Set<string>()
  const chosen: ResultRow[] = []
  for (const row of sorted) {
    const u = row.meta.upgrade!
    if (chosenSlots.has(u.slot)) continue
    const have = remaining[u.crest] ?? 0
    if (have < u.cost) continue
    remaining[u.crest] = have - u.cost
    chosenSlots.add(u.slot)
    chosen.push(row)
  }
  return { chosen, remaining }
}

type SortKey = 'gain' | 'cost' | 'perCrest'

export function UpgradesPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('upgrades')

  const [selectedSlots, setSelectedSlots] = useState<string[] | null>(null) // null = all
  const [maxRanksInput, setMaxRanksInput] = useState<number | ''>('')
  const [minIlevelInput, setMinIlevelInput] = useState<number | null>(null)
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'gain', dir: -1 })
  const importedBudget = useMemo(() => importedBudgetFor(profile), [profile])
  const [budget, setBudget] = useState<Record<string, number>>(() => ({ ...importedBudget }))
  // Re-seed the budget from the imported profile's owned crests whenever a (different) profile
  // is imported, so "Suggested spend" defaults to what the character actually has instead of
  // blank. Adjusted during render (not an effect) per React's "resetting state on prop change".
  const [seenImportedAt, setSeenImportedAt] = useState(profile?.imported_at)
  if (profile?.imported_at !== seenImportedAt) {
    setSeenImportedAt(profile?.imported_at)
    setBudget({ ...importedBudget })
  }

  const currencyByCrest = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of profile?.currencies ?? []) if (c.crest) m.set(c.crest, c.amount)
    return m
  }, [profile])

  const minIlevel = minIlevelInput ?? (profile ? lowestEquippedIlevel(profile.equipped) : 0)
  const equippedSlots = useMemo(() => (profile ? SLOTS.filter((s) => profile.equipped[s]) : []), [profile])
  const isChecked = (slot: string) => !selectedSlots || selectedSlots.includes(slot)
  const toggleSlot = (slot: string, on: boolean) => {
    const base = selectedSlots ?? [...equippedSlots]
    setSelectedSlots(on ? [...new Set([...base, slot])] : base.filter((s) => s !== slot))
  }
  const activeSlots = selectedSlots ?? equippedSlots

  const sortedRows = useMemo(() => {
    if (!result) return []
    const rows = [...result.results]
    rows.sort((a, b) => {
      const ka = a.meta.upgrade
      const kb = b.meta.upgrade
      let x = 0
      let y = 0
      if (sort.key === 'gain') { x = a.delta_pct; y = b.delta_pct }
      else if (sort.key === 'cost') { x = ka?.cost ?? 0; y = kb?.cost ?? 0 }
      else { x = ka ? a.delta_pct / Math.max(1, ka.cost) : 0; y = kb ? b.delta_pct / Math.max(1, kb.cost) : 0 }
      return (x - y) * sort.dir
    })
    return rows
  }, [result, sort])

  const crestTypes = useMemo(() => {
    if (!result) return []
    return [...new Set(result.results.map((r) => r.meta.upgrade?.crest).filter((c): c is string => !!c))]
  }, [result])

  const { chosen, remaining } = useMemo(
    () => (result ? greedySuggestedSpend(result.results, budget) : { chosen: [] as ResultRow[], remaining: {} as Record<string, number> }),
    [result, budget],
  )
  const totalGain = chosen.reduce((a, r) => a + r.delta_pct, 0)

  if (!profile) return <><PageTitle title="Upgrades" /><NeedProfile /></>

  const th = (key: SortKey, label: string) => (
    <th className="cursor-pointer select-none px-2 py-1.5 text-right text-xs font-medium text-muted hover:text-text" onClick={() => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : -1 }))}>
      {label}{sort.key === key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
    </th>
  )

  return (
    <div>
      <PageTitle
        title="Upgrades"
        subtitle="Crest-track upgrades for what you already have equipped, ranked by gain."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || !activeSlots.length}
            onClick={() => {
              setSelected(null)
              void run(() => api.runUpgrades({
                profile, options,
                slots: selectedSlots && selectedSlots.length !== equippedSlots.length ? selectedSlots : undefined,
                max_ranks: maxRanksInput === '' ? null : Number(maxRanksInput),
                min_ilevel: minIlevel,
              }))
            }}
          >
            <Play size={15} /> Run upgrades
          </button>
        }
      />
      <Card title="Your currencies" className="mb-4">
        {profile.currencies?.length || profile.catalyst_charges != null ? (
          <CurrencyStrip currencies={profile.currencies} catalystCharges={profile.catalyst_charges} showNames size={32} />
        ) : (
          <div className="text-sm text-muted">
            No crest currencies in this profile — the SimC addon export includes crest counts, so re-run <span className="mono text-text">/simc</span> and re-import to see them here.
          </div>
        )}
      </Card>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Slots" actions={<span className="text-xs text-muted">{activeSlots.length} / {equippedSlots.length}</span>}>
            <div className="mb-2 flex gap-1.5">
              <button type="button" className="btn btn-sm" onClick={() => setSelectedSlots(null)}>All</button>
              <button type="button" className="btn btn-sm" onClick={() => setSelectedSlots([])}>None</button>
            </div>
            <div className="flex flex-col gap-1">
              {equippedSlots.map((slot) => {
                const item = profile.equipped[slot]
                const crafted = !!item.crafting_quality
                return (
                  <div key={slot} className={`flex items-center justify-between gap-2 rounded px-1 py-0.5 ${crafted ? 'opacity-50' : ''}`} title={crafted ? 'Crafted gear upgrades on its own quality track, not a crest track' : undefined}>
                    <Checkbox checked={isChecked(slot) && !crafted} disabled={crafted} onChange={(v) => toggleSlot(slot, v)} label={SLOT_LABELS[slot] ?? slot} />
                    <span className="text-xs tabular-nums text-muted">ilvl {item.ilevel}{crafted ? ' · crafted' : ''}</span>
                  </div>
                )
              })}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border pt-3">
              <Field label="Max ranks" hint="blank = track max">
                <Input type="number" min={1} placeholder="max" value={maxRanksInput} onChange={(e) => setMaxRanksInput(e.target.value === '' ? '' : Math.max(1, Number(e.target.value) || 1))} />
              </Field>
              <Field label="Min item level" hint="Skip slots below this">
                <Input type="number" min={0} value={minIlevel} onChange={(e) => setMinIlevelInput(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
            </div>
          </Card>
          <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
        </div>

        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? result.results.length === 0 ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />
              <EmptyState
                icon={<ArrowUpCircle size={32} strokeWidth={1.5} />}
                title="Nothing to upgrade"
                body="Every equipped item is at the top of its track or has no crest track."
              />
            </>
          ) : (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />

              {crestTypes.length > 0 && (
                <Card title="Suggested spend" actions={<span className="text-xs text-muted">greedy: best gain per crest first, one slot each</span>}>
                  <div className="mb-3 flex flex-wrap items-end gap-3">
                    {crestTypes.map((c) => (
                      <Field key={c} label={`${c} crests owned`} className="w-40">
                        <Input type="number" min={0} value={budget[c] ?? 0} onChange={(e) => setBudget({ ...budget, [c]: Math.max(0, Number(e.target.value) || 0) })} />
                      </Field>
                    ))}
                    {Object.keys(importedBudget).length > 0 && (
                      <button type="button" className="btn btn-sm btn-ghost" onClick={() => setBudget({ ...importedBudget })}>
                        Reset to imported
                      </button>
                    )}
                  </div>
                  {chosen.length ? (
                    <>
                      <div className="flex flex-col gap-1">
                        {chosen.map((r) => (
                          <div key={r.name} className="flex items-center justify-between rounded bg-bg-soft/50 px-2 py-1 text-sm">
                            <span className="truncate">{r.label}</span>
                            <span className="shrink-0 text-good">{fmtPct(r.delta_pct)}</span>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 flex items-center justify-between border-t border-border pt-2 text-sm">
                        <span className="text-muted">Total predicted gain (sum of independent sims, not simmed together)</span>
                        <span className="font-semibold text-good">{fmtPct(totalGain)}</span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
                        {Object.entries(remaining).map(([crest, amt]) => (
                          <span key={crest}>{crest} remaining: <span className="tabular-nums text-text">{amt}</span></span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <div className="text-sm text-muted">Enter how many crests you have to see what to spend them on.</div>
                  )}
                </Card>
              )}

              <Card title={`${result.results.length} upgrade steps`}>
                <div className={`grid grid-cols-1 gap-4 ${selected ? '2xl:grid-cols-[1fr_360px]' : ''}`}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left">
                          <th className="px-2 py-1.5 text-xs font-medium text-muted">Upgrade</th>
                          {th('gain', 'Gain')}
                          {th('cost', 'Cost')}
                          {th('perCrest', 'Gain / crest')}
                          <th className="px-2 py-1.5 text-right text-xs font-medium text-muted">Affordable</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedRows.map((r) => {
                          const u = r.meta.upgrade
                          const perCrest = u ? r.delta_pct / Math.max(1, u.cost) : 0
                          const sel = selected?.name === r.name
                          const owned = u ? currencyByCrest.get(u.crest) : undefined
                          const affordable = u ? (u.affordable ?? (owned != null ? owned >= u.cost : null)) : null
                          const needed = u && owned != null ? Math.max(0, u.cost - owned) : null
                          return (
                            <tr key={r.name} className={`cursor-pointer border-b border-border/50 hover:bg-surface-2 ${sel ? 'bg-accent/10' : ''}`} onClick={() => setSelected(sel ? null : r)}>
                              <td className="px-2 py-1.5">
                                {r.label}
                                {u?.track === 'Voidforged' && <span className="chip ml-1.5 text-accent">Voidforged</span>}
                              </td>
                              <td className="px-2 py-1.5 text-right tabular-nums text-good">{fmtPct(r.delta_pct)}</td>
                              <td className="px-2 py-1.5 text-right tabular-nums text-muted">{u ? `${u.cost} ${u.crest}` : '—'}</td>
                              <td className="px-2 py-1.5 text-right tabular-nums">{perCrest.toFixed(3)}%</td>
                              <td className="px-2 py-1.5 text-right text-xs">
                                {affordable === true && (
                                  <span className="inline-flex items-center gap-1 text-good" title="Affordable with crests owned">
                                    <Check size={13} /> Yes
                                  </span>
                                )}
                                {affordable === false && (
                                  <span className="text-muted">needs {needed} more {u?.crest}</span>
                                )}
                                {affordable == null && <span className="text-faint">—</span>}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                  {selected && (
                    <div className="order-first 2xl:order-none">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-sm font-semibold">Upgrade details</span>
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelected(null)}>Close</button>
                      </div>
                      <ChangedSlots row={selected} profile={profile} />
                    </div>
                  )}
                </div>
              </Card>
            </>
          ) : !job && (
            <EmptyState icon={<ArrowUpCircle size={32} strokeWidth={1.5} />} title="Pick slots and run" body="Every equipped slot with a crest upgrade track is simmed at each rank above its current one." />
          )}
        </div>
      </div>
    </div>
  )
}
