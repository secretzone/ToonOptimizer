import { useMemo, useState } from 'react'
import { Play, Plus, Shirt, Trash2, X } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { ItemCard, ItemIcon, WowheadOrFallback } from '../components/ItemCard'
import { qualityColor } from '../lib/items'
import { useWowheadRefresh, useWowheadActive } from '../lib/wowhead'
import { ChangedSlots } from '../components/ChangedSlots'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Field, Input, PageTitle, Select } from '../components/ui'
import { isLowerBetter, SLOT_LABELS, lowestEquippedIlevel, slotsForItem } from '../lib/wow'
import { SLOTS, type Item, type ResultRow } from '../lib/types'

type GearSet = { id: number; name: string; changes: Record<string, Item> }
let setSeq = 1

/** A slot picker's icon: Wowhead tooltip when active, our fallback ItemTooltip otherwise. Its
 * own component (rather than inlined in a .map()) so useWowheadActive's hooks stay legal. */
function GearSlotIcon({ item }: { item: Item | undefined }) {
  const active = useWowheadActive(item)
  if (!item) return null
  return <WowheadOrFallback item={item} active={active}><ItemIcon item={item} size={22} /></WowheadOrFallback>
}

/** Clone an item with a new ilvl; patch simc_string so the backend can use it verbatim. */
function withIlvl(item: Item, ilevel: number): Item {
  const simc = item.simc_string.includes('ilevel=') ? item.simc_string.replace(/ilevel=\d+/, `ilevel=${ilevel}`) : `${item.simc_string},ilevel=${ilevel}`
  const scale = item.ilevel ? Math.pow(1.055, ilevel - item.ilevel) : 1
  const stats = Object.fromEntries(Object.entries(item.stats ?? {}).map(([k, v]) => [k, Math.round(v * scale)]))
  return { ...item, ilevel, simc_string: simc, stats }
}

export function GearComparePage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const { job, result, running, run, cancel } = usePageJob('gearcompare')
  const [sets, setSets] = useState<GearSet[]>([{ id: setSeq++, name: 'Set A', changes: {} }])
  const [selected, setSelected] = useState<ResultRow | null>(null)
  // `null` = not touched yet -> defaults to the profile's lowest equipped ilevel.
  const [minIlevelInput, setMinIlevelInput] = useState<number | null>(null)
  const minIlevel = minIlevelInput ?? (profile ? lowestEquippedIlevel(profile.equipped) : 0)

  const pool = useMemo(() => {
    if (!profile) return []
    return [
      ...Object.values(profile.equipped).map((item) => ({ item, origin: 'equipped' as const })),
      ...profile.bags.map((item) => ({ item, origin: 'bag' as const })),
      ...profile.vault.map((item) => ({ item, origin: 'vault' as const })),
    ]
  }, [profile])

  useWowheadRefresh([sets, result])

  if (!profile) return <><PageTitle title="Gear Compare" /><NeedProfile /></>

  const update = (id: number, patch: Partial<GearSet>) => setSets(sets.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  // Equipped items are always offered; bag/vault items below the min ilevel are hidden, unless
  // it's the item already chosen for this slot (so raising the threshold doesn't blank a pick).
  const candidatesFor = (slot: string, keepKey?: string) =>
    pool.filter((p) => slotsForItem(p.item.slot).includes(slot) && (p.origin === 'equipped' || p.item.ilevel >= minIlevel || p.item.key === keepKey))
  const setSlot = (set: GearSet, slot: string, key: string) => {
    const changes = { ...set.changes }
    if (!key) delete changes[slot]
    else {
      const found = pool.find((p) => p.item.key === key)
      if (found) changes[slot] = { ...found.item, slot }
    }
    update(set.id, { changes })
  }
  const setIlvl = (set: GearSet, slot: string, ilevel: number) => {
    const cur = set.changes[slot] ?? profile.equipped[slot]
    if (!cur) return
    update(set.id, { changes: { ...set.changes, [slot]: withIlvl({ ...cur, slot }, ilevel) } })
  }
  const valid = sets.filter((s) => Object.keys(s.changes).length > 0)

  return (
    <div>
      <PageTitle
        title="Gear Compare"
        subtitle="Build a few sets from what you own and see how they stack up against your current gear."
        actions={
          <button type="button" className="btn btn-primary" disabled={running || !valid.length} onClick={() => { setSelected(null); void run(() => api.gearcompare({ profile, options, sets: valid.map(({ name, changes }) => ({ name, changes })) })) }}>
            <Play size={15} /> Compare {valid.length} set{valid.length === 1 ? '' : 's'}
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 2xl:grid-cols-2">
            {sets.map((set) => (
              <Card
                key={set.id}
                title={<Input value={set.name} onChange={(e) => update(set.id, { name: e.target.value })} className="w-40 py-1 text-sm font-semibold" />}
                actions={
                  <>
                    <span className="text-xs text-muted">{Object.keys(set.changes).length} change{Object.keys(set.changes).length === 1 ? '' : 's'}</span>
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSets(sets.filter((s) => s.id !== set.id))} disabled={sets.length === 1} aria-label="Remove set"><Trash2 size={13} /></button>
                  </>
                }
              >
                <div className="flex flex-col gap-1">
                  {SLOTS.map((slot) => {
                    const chosen = set.changes[slot]
                    const current = profile.equipped[slot]
                    const cands = candidatesFor(slot, chosen?.key)
                    if (!cands.length && !current) return null
                    return (
                      <div key={slot} className={`grid grid-cols-[76px_1fr_60px_20px] items-center gap-2 rounded px-1 py-0.5 ${chosen ? 'bg-accent/5' : ''}`}>
                        <span className="text-xs text-muted">{SLOT_LABELS[slot]}</span>
                        <div className="flex min-w-0 items-center gap-1.5">
                          <GearSlotIcon item={chosen ?? current} />
                          <Select value={chosen ? (pool.find((p) => p.item.id === chosen.id && p.item.key === chosen.key)?.item.key ?? chosen.key) : ''} onChange={(e) => setSlot(set, slot, e.target.value)} className="py-1 text-xs" style={{ color: chosen ? qualityColor(chosen.quality) : undefined }}>
                            <option value="">{current ? `(current) ${current.name}` : '(empty)'}</option>
                            {cands.map((c) => <option key={c.item.key} value={c.item.key}>{c.item.name} · {c.item.ilevel} ({c.origin})</option>)}
                          </Select>
                        </div>
                        <Input type="number" className="py-1 text-xs" title="Override item level" value={chosen?.ilevel ?? current?.ilevel ?? ''} onChange={(e) => setIlvl(set, slot, Number(e.target.value) || 0)} />
                        {chosen ? <button type="button" className="text-muted hover:text-text" onClick={() => setSlot(set, slot, '')} aria-label="Reset slot"><X size={14} /></button> : <span />}
                      </div>
                    )
                  })}
                </div>
              </Card>
            ))}
          </div>
          <div className="flex items-end gap-3">
            <button type="button" className="btn self-start" onClick={() => setSets([...sets, { id: setSeq++, name: `Set ${String.fromCharCode(65 + sets.length)}`, changes: {} }])} disabled={sets.length >= 8}>
              <Plus size={14} /> Add set
            </button>
            <Field label="Min item level" hint="Hides low-ilevel bag/vault items from the pickers above" className="w-40">
              <Input type="number" min={0} value={minIlevel} onChange={(e) => setMinIlevelInput(Math.max(0, Number(e.target.value) || 0))} />
            </Field>
          </div>

          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />
              <div className={`grid grid-cols-1 gap-4 ${selected ? '2xl:grid-cols-[1fr_380px]' : ''}`}>
                <Card title="Sets">
                  <ResultBars baseline={result.baseline} rows={result.results} selected={selected?.name} onSelect={setSelected} showRank={false} lowerBetter={isLowerBetter(result.metric)} />
                </Card>
                {selected && (
                  <Card className="order-first 2xl:order-none" title={selected.label} actions={<button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelected(null)}>Close</button>}>
                    <ChangedSlots row={selected} profile={profile} />
                  </Card>
                )}
              </div>
            </>
          ) : !job && (
            <EmptyState icon={<Shirt size={32} strokeWidth={1.5} />} title="Build a set" body="Change at least one slot in a set. Type a different item level to test an upgraded version of an item." />
          )}
          {valid.length > 0 && !result && !job && (
            <Card title="Preview">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {valid.map((s) => (
                  <div key={s.id}>
                    <div className="label mb-1">{s.name}</div>
                    <div className="flex flex-col gap-0.5">{Object.entries(s.changes).map(([slot, it]) => <ItemCard key={slot} item={it} compact slotLabel={SLOT_LABELS[slot]} />)}</div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
        <OptionsPanel options={options} onChange={setOptions} show={{ gear: false }} />
      </div>
    </div>
  )
}
