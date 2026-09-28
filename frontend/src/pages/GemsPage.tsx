import { useEffect, useMemo, useState } from 'react'
import { Play, Plus, Sparkles, Trash2, Wand2 } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { ChangedSlots } from '../components/ChangedSlots'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Input, PageTitle, Select, Tabs, Toggle } from '../components/ui'
import { fmtPct } from '../lib/format'
import { iconUrl, isLowerBetter, SLOT_LABELS, titleCase } from '../lib/wow'
import { socketCount } from '../lib/items'
import { SLOTS, type EnchantRef, type GemRef, type GemsCustomSet, type GemsMode, type Recommendations, type ResultRow } from '../lib/types'

type CustomSet = { id: number; name: string; gems: Record<string, number[]>; enchants: Record<string, number> }
let setSeq = 1

function GemChip({ gem, on, onClick }: { gem: GemRef; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs transition-colors ${on ? 'border-accent-dim bg-accent/10 text-text' : 'border-border bg-bg-soft text-muted opacity-60'}`}
      title={`${gem.name} · ${titleCase(gem.stat)}${gem.limit ? ' · unique' : ''}`}
    >
      <img src={iconUrl(gem.icon)} alt="" className="h-4 w-4 rounded-sm" onError={(e) => { e.currentTarget.style.visibility = 'hidden' }} />
      {gem.name}
    </button>
  )
}

/** Pool of gems the recommendations endpoint suggests: best secondary per stat + unique-equipped. */
function recPool(recs: Recommendations | null): GemRef[] {
  if (!recs) return []
  return [...Object.values(recs.gems.by_stat), ...recs.gems.unique]
}

/** Options for one socket's <select>: an "(empty)" placeholder when there's no gem in it, or the
 * current gem (deduped against the pool — if the current id is also in the pool, it gets one
 * option labelled "Name (current)" instead of two options fighting over the same value). */
function socketOptions(currentGemId: number | undefined, pool: GemRef[]): { value: number; label: string }[] {
  if (currentGemId == null) return [{ value: 0, label: '(empty)' }, ...pool.map((g) => ({ value: g.id, label: g.name }))]
  const inPool = pool.find((g) => g.id === currentGemId)
  const options = [{ value: currentGemId, label: inPool ? `${inPool.name} (current)` : '(current)' }]
  for (const g of pool) if (g.id !== currentGemId) options.push({ value: g.id, label: g.name })
  return options
}

/** Options for a slot's enchant <select>: the current enchant first, labelled with its name from
 * recommendations when known ("Name (current)"), falling back to "(current enchant)" only when
 * the id isn't among the offered options -- then every option, deduped against the current id. */
function enchantOptions(currentEnchantId: number | null, opts: EnchantRef[]): { value: number; label: string }[] {
  const current = currentEnchantId ?? 0
  const known = opts.find((o) => o.id === current)
  const options = [{ value: current, label: known ? `${known.name} (current)` : '(current enchant)' }]
  for (const o of opts) if (o.id !== current) options.push({ value: o.id, label: o.name })
  return options
}

function applyRecommendedToSet(set: CustomSet, equipped: Record<string, { gem_ids: number[]; enchant_id: number | null; sockets?: number }>, recs: Recommendations): CustomSet {
  const gems: Record<string, number[]> = {}
  let usedUnique = false
  for (const [slot, item] of Object.entries(equipped)) {
    const n = socketCount(item)
    if (!n) continue
    const ids = new Array(n).fill(recs.gems.default.id)
    if (!usedUnique && recs.gems.unique.length) { ids[0] = recs.gems.unique[0].id; usedUnique = true }
    gems[slot] = ids
  }
  const enchants: Record<string, number> = {}
  for (const [slot, opts] of Object.entries(recs.enchants)) {
    if (!equipped[slot]) continue
    const rec = opts.find((o) => o.recommended) ?? opts[0]
    if (rec) enchants[slot] = rec.id
  }
  return { ...set, gems, enchants }
}

export function GemsPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('gems')

  const recsCache = useStore((s) => s.recommendations)
  const setRecommendations = useStore((s) => s.setRecommendations)
  const recKey = profile ? `${profile.klass}:${profile.spec}` : null
  const recs = recKey ? (recsCache[recKey] ?? null) : null
  useEffect(() => {
    if (!profile || !recKey || recsCache[recKey]) return
    api.recommendations(profile.klass, profile.spec).then((r) => setRecommendations(recKey, r)).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recKey])

  const [mode, setMode] = useState<GemsMode>('uniform')
  const [poolIds, setPoolIds] = useState<number[] | null>(null) // null = every gem in the recommended pool
  const [includeEnchants, setIncludeEnchants] = useState(true)
  const [sets, setSets] = useState<CustomSet[]>([{ id: setSeq++, name: 'Set A', gems: {}, enchants: {} }])
  const [selected, setSelected] = useState<ResultRow | null>(null)

  const pool = useMemo(() => recPool(recs), [recs])
  const activePoolIds = poolIds ?? pool.map((g) => g.id)
  const togglePoolGem = (id: number) => {
    const base = poolIds ?? pool.map((g) => g.id)
    setPoolIds(base.includes(id) ? base.filter((g) => g !== id) : [...base, id])
  }

  // All hooks must run unconditionally, so everything below stays null-safe until the
  // `!profile` early return further down.
  const equippedSlots = useMemo<string[]>(() => (profile ? SLOTS.filter((s) => profile.equipped[s]) : []), [profile])

  useEffect(() => setSelected(null), [mode])

  const gemRows = result ? result.results.filter((r) => !r.meta.enchant) : []
  const enchantRows = result ? result.results.filter((r) => r.meta.enchant) : []
  const enchantBySlot = useMemo(() => {
    const m = new Map<string, ResultRow[]>()
    for (const r of enchantRows) {
      const slot = r.meta.enchant!.slot
      if (!m.has(slot)) m.set(slot, [])
      m.get(slot)!.push(r)
    }
    return [...m.entries()]
  }, [enchantRows])

  const bestPerSocket = useMemo(() => {
    if (mode !== 'per_socket') return []
    const m = new Map<string, ResultRow>()
    for (const r of gemRows) {
      const g = r.meta.gem
      if (!g) continue
      const key = `${g.slot}#${g.socket_index}`
      const cur = m.get(key)
      if (!cur || r.dps > cur.dps) m.set(key, r)
    }
    return [...m.values()].sort((a, b) => (a.meta.gem!.slot === b.meta.gem!.slot ? a.meta.gem!.socket_index - b.meta.gem!.socket_index : equippedSlots.indexOf(a.meta.gem!.slot) - equippedSlots.indexOf(b.meta.gem!.slot)))
  }, [mode, gemRows, equippedSlots])

  if (!profile) return <><PageTitle title="Gems & Enchants" /><NeedProfile /></>

  const socketSlots = equippedSlots.filter((s) => socketCount(profile.equipped[s]) > 0)
  const enchantableSlots = recs ? equippedSlots.filter((s) => recs.enchants[s]) : []
  const editableSlots = [...new Set([...socketSlots, ...enchantableSlots])].sort((a, b) => equippedSlots.indexOf(a) - equippedSlots.indexOf(b))

  const updateSet = (id: number, patch: Partial<CustomSet>) => setSets(sets.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  const setSocketGem = (set: CustomSet, slot: string, idx: number, gemId: number) => {
    const cur = set.gems[slot] ?? [...profile.equipped[slot].gem_ids]
    const next = [...cur]
    next[idx] = gemId
    updateSet(set.id, { gems: { ...set.gems, [slot]: next } })
  }
  const setEnchant = (set: CustomSet, slot: string, enchantId: number) => updateSet(set.id, { enchants: { ...set.enchants, [slot]: enchantId } })

  const customSetsValid = sets.filter((s) => Object.keys(s.gems).length || Object.keys(s.enchants).length)
  const canRun = mode === 'custom' ? customSetsValid.length > 0 : activePoolIds.length > 0

  const toBody = (): GemsCustomSet[] | undefined =>
    mode === 'custom' ? customSetsValid.map(({ name, gems, enchants }) => ({ name, gems, enchants })) : undefined

  return (
    <div>
      <PageTitle
        title="Gems & Enchants"
        subtitle="Which gems and enchants are actually worth it, given what you have equipped."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || !canRun}
            onClick={() => {
              setSelected(null)
              void run(() => api.runGems({
                profile, options, mode,
                gem_pool: mode === 'custom' ? undefined : activePoolIds,
                include_enchants: includeEnchants,
                sets: toBody(),
              }))
            }}
          >
            <Play size={15} /> Run
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[400px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Mode">
            <Tabs
              value={mode}
              onChange={setMode}
              tabs={[{ value: 'uniform', label: 'Uniform' }, { value: 'per_socket', label: 'Per socket' }, { value: 'custom', label: 'Custom' }]}
              className="mb-3"
            />

            {mode !== 'custom' && (
              <div className="mb-3">
                <div className="label mb-1.5">Gem pool</div>
                {!recs && <div className="text-xs text-muted">Loading recommendations…</div>}
                <div className="flex flex-wrap gap-1.5">
                  {pool.map((g) => <GemChip key={g.id} gem={g} on={activePoolIds.includes(g.id)} onClick={() => togglePoolGem(g.id)} />)}
                </div>
              </div>
            )}

            <Toggle checked={includeEnchants} onChange={setIncludeEnchants} label="Include enchants" description="Add one row per (slot, enchant option) that differs from what's equipped" />

            {mode === 'custom' && (
              <div className="mt-3 flex flex-col gap-3 border-t border-border pt-3">
                {sets.map((set) => (
                  <div key={set.id} className="rounded-md border border-border p-2.5">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <Input value={set.name} onChange={(e) => updateSet(set.id, { name: e.target.value })} className="w-32 py-1 text-sm font-semibold" />
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={!recs}
                          title="Fill every socket and enchant from /api/data/recommendations"
                          onClick={() => recs && updateSet(set.id, applyRecommendedToSet(set, profile.equipped, recs))}
                        >
                          <Wand2 size={12} /> Use recommended
                        </button>
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSets(sets.filter((s) => s.id !== set.id))} disabled={sets.length === 1} aria-label="Remove set"><Trash2 size={13} /></button>
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {editableSlots.map((slot) => {
                        const item = profile.equipped[slot]
                        const n = socketCount(item)
                        const enchOpts = recs?.enchants[slot]
                        return (
                          <div key={slot} className="flex flex-wrap items-center gap-1.5">
                            <span className="w-16 shrink-0 text-xs text-muted">{SLOT_LABELS[slot]}</span>
                            {Array.from({ length: n }).map((_, i) => {
                              const currentGemId = item.gem_ids[i]
                              const value = set.gems[slot]?.[i] ?? currentGemId ?? 0
                              return (
                                <Select key={i} value={value} onChange={(e) => setSocketGem(set, slot, i, Number(e.target.value))} className="w-32 py-1 text-xs">
                                  {socketOptions(currentGemId, pool).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                                </Select>
                              )
                            })}
                            {enchOpts && (
                              <Select value={set.enchants[slot] ?? item.enchant_id ?? 0} onChange={(e) => setEnchant(set, slot, Number(e.target.value))} className="w-40 py-1 text-xs">
                                {enchantOptions(item.enchant_id, enchOpts).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                              </Select>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
                <button type="button" className="btn self-start" onClick={() => setSets([...sets, { id: setSeq++, name: `Set ${String.fromCharCode(65 + sets.length)}`, gems: {}, enchants: {} }])} disabled={sets.length >= 6}>
                  <Plus size={14} /> Add set
                </button>
              </div>
            )}
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
                icon={<Sparkles size={32} strokeWidth={1.5} />}
                title="Nothing to gem or enchant"
                body="Every socketed item already has its best gem and no enchant option differs from what's equipped."
              />
            </>
          ) : (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />

              {mode === 'per_socket' && bestPerSocket.length > 0 && (
                <Card title="Best per socket">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted">
                        <th className="px-2 py-1">Slot</th>
                        <th className="px-2 py-1">Socket</th>
                        <th className="px-2 py-1">Best gem</th>
                        <th className="px-2 py-1 text-right">Gain</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bestPerSocket.map((r) => (
                        <tr key={r.name} className="border-b border-border/50">
                          <td className="px-2 py-1">{SLOT_LABELS[r.meta.gem!.slot] ?? r.meta.gem!.slot}</td>
                          <td className="px-2 py-1 tabular-nums text-muted">{r.meta.gem!.socket_index}</td>
                          <td className="px-2 py-1">{r.meta.gem!.gem_name} <span className="text-xs text-muted">({titleCase(r.meta.gem!.stat)})</span></td>
                          <td className="px-2 py-1 text-right tabular-nums text-good">{fmtPct(r.delta_pct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}

              <div className={`grid grid-cols-1 gap-4 ${selected ? '2xl:grid-cols-[1fr_360px]' : ''}`}>
                <Card title={`${gemRows.length} gem result${gemRows.length === 1 ? '' : 's'}`}>
                  <ResultBars baseline={result.baseline} rows={gemRows} selected={selected?.name} onSelect={setSelected} showRank={mode !== 'per_socket'} lowerBetter={isLowerBetter(result.metric)} />
                </Card>
                {selected && (
                  <Card className="order-first 2xl:order-none" title={selected.label} actions={<button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelected(null)}>Close</button>}>
                    {selected.meta.changes ? <ChangedSlots row={selected} profile={profile} /> : (
                      <div className="text-sm text-muted">
                        {selected.meta.gem && <div>{SLOT_LABELS[selected.meta.gem.slot] ?? selected.meta.gem.slot} · socket {selected.meta.gem.socket_index} · {selected.meta.gem.gem_name} ({titleCase(selected.meta.gem.stat)})</div>}
                      </div>
                    )}
                  </Card>
                )}
              </div>

              {includeEnchants && enchantBySlot.length > 0 && (
                <Card title="Enchants (by slot)">
                  <div className="flex flex-col gap-3">
                    {enchantBySlot.map(([slot, rows]) => (
                      <div key={slot}>
                        <div className="label mb-1">{SLOT_LABELS[slot] ?? slot}</div>
                        <ResultBars baseline={result.baseline} rows={rows} showRank={false} labelWidth={280} lowerBetter={isLowerBetter(result.metric)} />
                      </div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          ) : !job && (
            <EmptyState icon={<Sparkles size={32} strokeWidth={1.5} />} title="Pick a mode and run" body="Uniform fills every socket with one gem; per-socket tries every gem in every socket; custom lets you build exact sets." />
          )}
        </div>
      </div>
    </div>
  )
}
