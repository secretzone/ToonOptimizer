import { useEffect, useMemo, useState } from 'react'
import { Play, Search, Trophy, X } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { ItemCard } from '../components/ItemCard'
import { ChangedSlots } from '../components/ChangedSlots'
import { useWowheadRefresh } from '../lib/wowhead'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Checkbox, Field, Input, PageTitle, Select, Spinner, Toggle } from '../components/ui'
import { fmtDps, fmtPct } from '../lib/format'
import { iconUrl, isLowerBetter, SLOT_LABELS, STAT_LABELS, baseSlot, lowestEquippedIlevel, titleCase } from '../lib/wow'
import { profileKey } from '../store'
import type { Item, ItemSearchResult, ResultRow, SeasonData, SurrogateStatus, UpgradeTrackDef } from '../lib/types'

const SLOT_ORDER = ['head', 'neck', 'shoulder', 'back', 'chest', 'wrist', 'hands', 'waist', 'legs', 'feet', 'finger', 'trinket', 'main_hand', 'off_hand']

/** Suffix chips for a result row's variant items — key prefixes per API.md ("catalyst:",
 * "socket:", "voidforge:", "crafted:"). */
function variantChips(row: ResultRow): { key: string; label: string }[] {
  const items = row.meta.items ?? Object.values(row.meta.changes ?? {})
  const chips: { key: string; label: string }[] = []
  for (const it of items) {
    if (it.key.startsWith('catalyst:')) chips.push({ key: `cat-${it.key}`, label: 'Catalyst' })
    else if (it.key.startsWith('socket:')) chips.push({ key: `sock-${it.key}`, label: '+socket' })
    else if (it.key.startsWith('voidforge:')) chips.push({ key: `vf-${it.key}`, label: 'Voidforged' })
    else if (it.key.startsWith('crafted:')) chips.push({ key: `cr-${it.key}`, label: it.name.match(/\(recraft [^)]+\)/)?.[0].replace(/[()]/g, '') ?? 'Recraft' })
  }
  return chips
}

type RecraftSpec = { stats: [string, string]; embellishment_id?: number; quality_bonus?: number }

/** Small inline popover (not a portal — the candidate list already scrolls) for recrafting a
 * crafted item: stat pair from `crafted.stat_ids`, embellishment from `crafted.embellishments`,
 * and a max-quality checkbox. */
function RecraftPopover({
  item, season, value, onChange, onClose,
}: {
  item: Item
  season: SeasonData | null
  value: RecraftSpec | undefined
  onChange: (v: RecraftSpec | undefined) => void
  onClose: () => void
}) {
  const statIds = season?.crafted?.stat_ids ?? { crit: 32, haste: 36, versatility: 40, mastery: 49 }
  const stats = Object.keys(statIds)
  const embellishments = season?.crafted?.embellishments ?? []
  const current: RecraftSpec = value ?? { stats: [stats[0] ?? 'crit', stats[1] ?? 'haste'] }
  const set = (patch: Partial<RecraftSpec>) => onChange({ ...current, ...patch })
  return (
    <div className="mt-1 flex flex-wrap items-end gap-2 rounded-md border border-accent-dim bg-accent/5 p-2">
      <Field label="Stat 1" className="w-28">
        <Select value={current.stats[0]} onChange={(e) => set({ stats: [e.target.value, current.stats[1]] })} className="py-1 text-xs">
          {stats.map((s) => <option key={s} value={s}>{STAT_LABELS[s] ?? titleCase(s)}</option>)}
        </Select>
      </Field>
      <Field label="Stat 2" className="w-28">
        <Select value={current.stats[1]} onChange={(e) => set({ stats: [current.stats[0], e.target.value] })} className="py-1 text-xs">
          {stats.map((s) => <option key={s} value={s}>{STAT_LABELS[s] ?? titleCase(s)}</option>)}
        </Select>
      </Field>
      <Field label="Embellishment" className="w-40">
        <Select value={current.embellishment_id ?? 0} onChange={(e) => set({ embellishment_id: Number(e.target.value) || undefined })} className="py-1 text-xs">
          <option value={0}>None</option>
          {embellishments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </Select>
      </Field>
      <Checkbox checked={!!current.quality_bonus} onChange={(v) => set({ quality_bonus: v ? 1 : undefined })} label="Max quality" className="pb-1.5" />
      <div className="flex gap-1.5 pb-0.5">
        <button type="button" className="btn btn-sm btn-primary" onClick={() => { onChange(current); onClose() }}>Apply</button>
        {value && <button type="button" className="btn btn-sm btn-ghost" onClick={() => { onChange(undefined); onClose() }}>Remove</button>}
        <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>Cancel</button>
      </div>
      <div className="w-full text-[10px] text-faint">{item.name}</div>
    </div>
  )
}

/** Debounced name search -> pick -> track/rank -> resolved Item, appended to the "Searched
 * items" candidate group. Its own component so the debounce effect's lifecycle is self-contained. */
function AddItemSearch({ profile, tracks, onAdd }: { profile: { klass: string; spec: string }; tracks: UpgradeTrackDef[]; onAdd: (item: Item) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ItemSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [picked, setPicked] = useState<ItemSearchResult | null>(null)
  const [track, setTrack] = useState('')
  const [rank, setRank] = useState(1)
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    const trimmed = query.trim()
    // Skip re-searching right after a pick (query was just set to the picked item's own name).
    if (!trimmed || picked) return
    setSearching(true)
    const t = setTimeout(() => {
      api.itemSearch(trimmed, profile.klass, profile.spec)
        .then((r) => setResults(r.items))
        .catch(() => setResults([]))
        .finally(() => setSearching(false))
    }, 300)
    return () => clearTimeout(t)
  }, [query, picked, profile.klass, profile.spec])

  const pick = (item: ItemSearchResult) => {
    setPicked(item)
    setResults([])
    setQuery(item.name)
    const first = tracks[0]
    setTrack(first?.name ?? '')
    setRank(1)
  }

  const selectedTrack = tracks.find((t) => t.name === track)

  const add = async () => {
    if (!picked || !track) return
    setAdding(true)
    try {
      const item = await api.itemByTrack(picked.id, track, rank)
      onAdd(item)
      setPicked(null)
      setQuery('')
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="rounded-md border border-border p-2">
      <div className="relative">
        <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-faint" />
        <Input
          className="pl-7 text-xs"
          placeholder="Search items by name (e.g. band)…"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setPicked(null); if (!e.target.value.trim()) setResults([]) }}
        />
        {searching && <Spinner className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5" />}
      </div>
      {results.length > 0 && (
        <div className="mt-1 flex max-h-48 flex-col gap-0.5 overflow-y-auto">
          {results.map((r) => (
            <button key={r.id} type="button" className="flex items-center gap-2 rounded px-1 py-1 text-left text-xs hover:bg-surface-2" onClick={() => pick(r)}>
              <img src={iconUrl(r.icon)} alt="" className="h-5 w-5 rounded" />
              <span className="min-w-0 flex-1 truncate">{r.name}</span>
              <span className="text-faint">{SLOT_LABELS[r.slot] ?? r.slot} · {r.base_ilevel}</span>
            </button>
          ))}
        </div>
      )}
      {picked && (
        <div className="mt-2 flex flex-wrap items-end gap-2 border-t border-border pt-2">
          <img src={iconUrl(picked.icon)} alt="" className="h-6 w-6 rounded" />
          <Field label="Track" className="w-28">
            <Select value={track} onChange={(e) => { setTrack(e.target.value); setRank(1) }}>
              {tracks.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
              {!tracks.length && <option value="">Unknown</option>}
            </Select>
          </Field>
          <Field label="Rank" className="w-20">
            <Select value={rank} onChange={(e) => setRank(Number(e.target.value))}>
              {(selectedTrack?.ranks.map((rk) => rk.rank) ?? [1, 2, 3, 4, 5, 6, 7, 8]).map((rk) => <option key={rk} value={rk}>{rk}</option>)}
            </Select>
          </Field>
          <button type="button" className="btn btn-sm btn-primary" disabled={adding} onClick={add}>{adding ? <Spinner className="h-3.5 w-3.5" /> : 'Add'}</button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setPicked(null); setQuery('') }}>Cancel</button>
        </div>
      )}
    </div>
  )
}

export function TopGearPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const candidateKeys = useStore((s) => s.candidateKeys)
  const setCandidateKeys = useStore((s) => s.setCandidateKeys)
  const minIlevelByProfile = useStore((s) => s.minIlevelByProfile)
  const setMinIlevelForProfile = useStore((s) => s.setMinIlevel)
  const { job, result, running, run, cancel } = usePageJob('topgear')
  const [maxCombos, setMaxCombos] = useState(200)
  const [smart, setSmart] = useState(true)
  const [excludedEquipped, setExcludedEquipped] = useState<string[]>([])
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [surrogate, setSurrogate] = useState<SurrogateStatus | null>(null)
  const [searchedItems, setSearchedItems] = useState<Item[]>([])
  const [upgradeTracks, setUpgradeTracks] = useState<UpgradeTrackDef[]>([])
  const [selectedLoadouts, setSelectedLoadouts] = useState<Set<string>>(() => new Set(profile?.saved_loadouts?.filter((l) => l.kind === 'active').map((l) => l.name) ?? []))
  const [sidegrades, setSidegrades] = useState(false)
  const [preferFewestChanges, setPreferFewestChanges] = useState(false)
  const [season, setSeason] = useState<SeasonData | null>(null)
  const [catalystKeys, setCatalystKeys] = useState<Set<string>>(new Set())
  const [socketKeys, setSocketKeys] = useState<Set<string>>(new Set())
  const [voidforgeKeys, setVoidforgeKeys] = useState<Set<string>>(new Set())
  const [minSetPieces, setMinSetPieces] = useState<0 | 2 | 4>(0)
  const [recrafts, setRecrafts] = useState<Record<string, RecraftSpec>>({})
  const [recraftOpenKey, setRecraftOpenKey] = useState<string | null>(null)

  useEffect(() => { void api.surrogateStatus().then(setSurrogate).catch(() => undefined) }, [])
  useEffect(() => { void api.season().then((s) => { setUpgradeTracks(s.upgrade_tracks ?? []); setSeason(s) }).catch(() => undefined) }, [])

  const catalystSlots = season?.catalyst?.slots ?? []
  const socketSlots = [...(season?.sockets?.vault_slots ?? []), ...(season?.sockets?.jewelbinder_slots ?? [])]
  const voidforgeSlots = season?.voidforged?.slots ?? []
  const hasCatalystCharges = profile == null || profile.catalyst_charges == null || profile.catalyst_charges > 0
  const isCatalystEligible = (item: Item) => hasCatalystCharges && (catalystSlots.includes(item.slot) || catalystSlots.includes(baseSlot(item.slot)))
  const isSocketEligible = (item: Item) => socketSlots.includes(item.slot) || socketSlots.includes(baseSlot(item.slot))
  const isVoidforgeEligible = (item: Item) => (voidforgeSlots.includes(item.slot) || voidforgeSlots.includes(baseSlot(item.slot))) && item.quality >= 4
  const toggleInSet = (setState: typeof setCatalystKeys, key: string) =>
    setState((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next })
  const hasModel = !!profile && !!surrogate?.models.some((m) => m.klass === profile.klass && m.spec === profile.spec)
  // Smart mode needs a trained model for this spec; the toggle is disabled without one, but also
  // derive the effective value at render time rather than fighting the disabled state with an effect.
  const effectiveSmart = smart && hasModel

  const groups = useMemo(() => {
    if (!profile) return []
    const all: { item: Item; origin: 'equipped' | 'bag' | 'vault' }[] = [
      ...Object.values(profile.equipped).map((item) => ({ item, origin: 'equipped' as const })),
      ...profile.bags.map((item) => ({ item, origin: 'bag' as const })),
      ...profile.vault.map((item) => ({ item, origin: 'vault' as const })),
    ]
    const by = new Map<string, typeof all>()
    for (const e of all) {
      const s = baseSlot(e.item.slot)
      if (!by.has(s)) by.set(s, [])
      by.get(s)!.push(e)
    }
    return SLOT_ORDER.filter((s) => by.has(s)).map((s) => ({ slot: s, entries: by.get(s)! }))
  }, [profile])

  useWowheadRefresh([groups, result])

  const top = result?.results[0]
  const sidegradeRows = useMemo(() => {
    if (!result || !top) return []
    const threshold = top.dps - 2 * top.dps_error
    return result.results.filter((r) => r.name !== top.name && r.dps >= threshold)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, top?.name])
  const orderedSidegrades = useMemo(() => {
    if (!preferFewestChanges) return sidegradeRows
    return [...sidegradeRows].sort((a, b) => Object.keys(a.meta.changes ?? {}).length - Object.keys(b.meta.changes ?? {}).length)
  }, [sidegradeRows, preferFewestChanges])

  if (!profile) return <><PageTitle title="Top Gear" /><NeedProfile /></>

  const pKey = profileKey(profile)
  const minIlevel = minIlevelByProfile[pKey] ?? lowestEquippedIlevel(profile.equipped)
  const setMinIlevel = (v: number) => setMinIlevelForProfile(pKey, v)
  const eligible = (item: Item) => item.ilevel >= minIlevel

  const isOn = (e: { item: Item; origin: string }) =>
    e.origin === 'equipped' ? !excludedEquipped.includes(e.item.key) : candidateKeys.includes(e.item.key) && eligible(e.item)
  const toggle = (e: { item: Item; origin: string }, on: boolean) => {
    if (e.origin === 'equipped') setExcludedEquipped(on ? excludedEquipped.filter((k) => k !== e.item.key) : [...excludedEquipped, e.item.key])
    else setCandidateKeys(on ? [...new Set([...candidateKeys, e.item.key])] : candidateKeys.filter((k) => k !== e.item.key))
  }
  const findCandidateItem = (k: string) => profile.bags.find((i) => i.key === k) ?? profile.vault.find((i) => i.key === k) ?? searchedItems.find((i) => i.key === k)
  const allKeys = () => [
    ...Object.values(profile.equipped).map((i) => i.key).filter((k) => !excludedEquipped.includes(k)),
    ...candidateKeys.filter((k) => {
      const it = findCandidateItem(k)
      return it && eligible(it)
    }),
  ]
  const extraCount = candidateKeys.filter((k) => !k.startsWith('equipped:')).filter((k) => {
    const it = findCandidateItem(k)
    return it && eligible(it)
  }).length
  const selectAllAboveThreshold = () => {
    setCandidateKeys([...profile.bags, ...profile.vault].filter(eligible).map((i) => i.key))
  }
  const addSearchedItem = (item: Item) => {
    setSearchedItems((prev) => [...prev.filter((i) => i.key !== item.key), item])
    setCandidateKeys([...new Set([...candidateKeys, item.key])])
  }
  const removeSearchedItem = (key: string) => {
    setSearchedItems((prev) => prev.filter((i) => i.key !== key))
    setCandidateKeys(candidateKeys.filter((k) => k !== key))
  }
  const toggleLoadout = (name: string, on: boolean) => setSelectedLoadouts((prev) => {
    const next = new Set(prev)
    if (on) next.add(name); else next.delete(name)
    return next
  })
  const chosenLoadouts = (profile.saved_loadouts ?? []).filter((l) => selectedLoadouts.has(l.name)).map(({ name, string }) => ({ name, string }))
  const extraItemsForRun = searchedItems.filter((i) => candidateKeys.includes(i.key) && eligible(i))
  const sidegradePick = orderedSidegrades[0]

  return (
    <div>
      <PageTitle
        title="Top Gear"
        subtitle="Find the best combination of the items you own."
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || extraCount === 0}
            onClick={() => {
              setSelected(null)
              void run(() => api.topgear({
                profile, options, candidate_keys: allKeys(), max_combos: maxCombos, smart: effectiveSmart, min_ilevel: minIlevel,
                loadouts: chosenLoadouts.length ? chosenLoadouts : undefined,
                extra_items: extraItemsForRun.length ? extraItemsForRun : undefined,
                catalyst: catalystKeys.size ? { keys: [...catalystKeys], min_set_pieces: minSetPieces || undefined } : undefined,
                add_socket: socketKeys.size ? { keys: [...socketKeys] } : undefined,
                voidforge: voidforgeKeys.size ? { keys: [...voidforgeKeys] } : undefined,
                crafted: Object.keys(recrafts).length ? Object.entries(recrafts).map(([key, spec]) => ({ key, ...spec })) : undefined,
              }))
            }}
          >
            <Play size={15} /> Find top gear
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[360px_1fr]">
        <div className="flex flex-col gap-4">
          <Card
            title="Candidates"
            actions={
              <div className="flex items-center gap-2">
                {profile.catalyst_charges != null && (
                  <span className="chip text-accent" title="Weekly Catalyst charges remaining on this profile">Catalyst charges: {profile.catalyst_charges}</span>
                )}
                <span className="text-xs text-muted">{extraCount} extra item{extraCount === 1 ? '' : 's'}</span>
              </div>
            }
          >
            <div className="mb-3 grid grid-cols-2 gap-3">
              <Field label="Max combos" hint="Cap on profilesets simulated">
                <Input type="number" min={1} max={5000} value={maxCombos} onChange={(e) => setMaxCombos(Math.max(1, Number(e.target.value) || 1))} />
              </Field>
              <div className="pt-5" title={hasModel ? undefined : `No surrogate model trained for ${profile.klass}/${profile.spec} yet — train one on the Settings page`}>
                <Toggle
                  checked={effectiveSmart}
                  onChange={setSmart}
                  disabled={!hasModel}
                  label="Smart (GPU surrogate, experimental)"
                  description={hasModel ? 'Score every combo with the trained model, then sim only the best ones exactly' : 'No trained model for this spec yet'}
                />
              </div>
            </div>
            {!!catalystSlots.length && (
              <div className="mb-3">
                <Field label="Minimum set pieces" hint="Reject combos with fewer catalyzed/tier pieces than this" className="w-48">
                  <Select value={minSetPieces} onChange={(e) => setMinSetPieces(Number(e.target.value) as 0 | 2 | 4)}>
                    <option value={0}>No minimum</option>
                    <option value={2}>2 pieces</option>
                    <option value={4}>4 pieces</option>
                  </Select>
                </Field>
              </div>
            )}
            <div className="mb-3 flex items-end gap-2">
              <Field label="Min item level" hint="Bag/vault items below this are excluded" className="w-36">
                <Input type="number" min={0} value={minIlevel} onChange={(e) => setMinIlevel(Math.max(0, Number(e.target.value) || 0))} />
              </Field>
              <button type="button" className="btn btn-sm mb-0.5" onClick={selectAllAboveThreshold}>
                Select all ≥ {minIlevel}
              </button>
            </div>
            <div className="mb-3">
              <div className="label mb-1">Add item</div>
              <AddItemSearch profile={profile} tracks={upgradeTracks} onAdd={addSearchedItem} />
            </div>
            <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto pr-1">
              {searchedItems.length > 0 && (
                <div>
                  <div className="label mb-1">Searched items</div>
                  <div className="flex flex-col gap-0.5">
                    {searchedItems.map((item) => {
                      const belowThreshold = !eligible(item)
                      return (
                        <div key={item.key} className="flex items-center gap-1">
                          <Checkbox checked={isOn({ item, origin: 'search' })} onChange={(v) => toggle({ item, origin: 'search' }, v)} disabled={belowThreshold} label="" className="pl-1" />
                          <ItemCard item={item} compact dim={belowThreshold} className="flex-1" right={<span className="chip text-accent">search</span>} />
                          <button type="button" className="text-muted hover:text-bad" onClick={() => removeSearchedItem(item.key)} aria-label="Remove searched item"><X size={14} /></button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              {groups.map((g) => (
                <div key={g.slot}>
                  <div className="label mb-1">{SLOT_LABELS[g.slot] ?? g.slot}</div>
                  <div className="flex flex-col gap-0.5">
                    {g.entries.map((e) => {
                      const belowThreshold = e.origin !== 'equipped' && !eligible(e.item)
                      const item = e.item
                      const showCatalyst = isCatalystEligible(item)
                      const showSocket = isSocketEligible(item)
                      const showVoidforge = isVoidforgeEligible(item)
                      const isCrafted = item.crafting_quality != null
                      const recraft = recrafts[item.key]
                      return (
                        <div key={item.key} className="flex flex-col gap-1">
                          <div className="flex items-center gap-1">
                            <Checkbox checked={isOn(e)} onChange={(v) => toggle(e, v)} disabled={belowThreshold} label="" className="pl-1" />
                            <ItemCard
                              item={item}
                              compact
                              dim={belowThreshold}
                              className="flex-1"
                              right={<span className={`chip ${e.origin === 'equipped' ? 'text-info' : e.origin === 'vault' ? 'text-fuchsia-300' : ''}`}>{e.origin}</span>}
                            />
                          </div>
                          {(showCatalyst || showSocket || showVoidforge || isCrafted) && (
                            <div className="ml-6 flex flex-wrap items-center gap-1.5">
                              {showCatalyst && (
                                <button
                                  type="button"
                                  className={`chip ${catalystKeys.has(item.key) ? 'border-accent-dim bg-accent/10 text-accent' : ''}`}
                                  title="Offer this item's catalyzed (tier) twin as a candidate"
                                  onClick={() => toggleInSet(setCatalystKeys, item.key)}
                                >
                                  Catalyst
                                </button>
                              )}
                              {showSocket && (
                                <button
                                  type="button"
                                  className={`chip ${socketKeys.has(item.key) ? 'border-accent-dim bg-accent/10 text-accent' : ''}`}
                                  title="Offer a +socket twin (bonus 1808 + a gem)"
                                  onClick={() => toggleInSet(setSocketKeys, item.key)}
                                >
                                  +Socket
                                </button>
                              )}
                              {showVoidforge && (
                                <button
                                  type="button"
                                  className={`chip ${voidforgeKeys.has(item.key) ? 'border-accent-dim bg-accent/10 text-accent' : ''}`}
                                  title="Offer the Myth Voidforged twin"
                                  onClick={() => toggleInSet(setVoidforgeKeys, item.key)}
                                >
                                  Voidforge
                                </button>
                              )}
                              {isCrafted && (
                                <button
                                  type="button"
                                  className={`chip ${recraft ? 'border-accent-dim bg-accent/10 text-accent' : ''}`}
                                  onClick={() => setRecraftOpenKey(recraftOpenKey === item.key ? null : item.key)}
                                >
                                  {recraft ? `Recraft (${titleCase(recraft.stats[0])}/${titleCase(recraft.stats[1])})` : 'Recraft…'}
                                </button>
                              )}
                            </div>
                          )}
                          {recraftOpenKey === item.key && (
                            <RecraftPopover
                              item={item}
                              season={season}
                              value={recrafts[item.key]}
                              onChange={(v) => setRecrafts((prev) => {
                                const next = { ...prev }
                                if (v) next[item.key] = v; else delete next[item.key]
                                return next
                              })}
                              onClose={() => setRecraftOpenKey(null)}
                            />
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </Card>
          {!!profile.saved_loadouts?.length && (
            <Card title="Loadouts" actions={<span className="text-xs text-muted">{chosenLoadouts.length ? `${chosenLoadouts.length} selected` : 'active only'}</span>}>
              <div className="flex flex-col gap-1">
                {profile.saved_loadouts.map((l) => (
                  <Checkbox key={l.name} checked={selectedLoadouts.has(l.name)} onChange={(v) => toggleLoadout(l.name, v)} label={<span>{l.name} <span className="chip ml-1 text-[10px]">{l.kind}</span></span>} />
                ))}
              </div>
              <div className="mt-2 text-xs text-faint">Each combo is simmed once per selected loadout (the combo cap applies to the total).</div>
            </Card>
          )}
          <OptionsPanel options={options} onChange={setOptions} />
        </div>
        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />
              {result.results.some((r) => r.meta.predicted_dps != null) && (
                <div className="rounded-md border border-accent-dim bg-accent/10 px-3 py-2 text-xs text-accent-strong">
                  Smart mode's GPU surrogate only chose which combos to sim — every DPS above is still an exact SimC result;
                  &quot;predicted&quot; is what the model guessed beforehand.
                </div>
              )}
              {sidegradeRows.length > 0 && (
                <div className="flex flex-wrap items-center gap-4 rounded-md border border-border px-3 py-2">
                  <Toggle checked={sidegrades} onChange={setSidegrades} label="Sidegrades" description={`${sidegradeRows.length} row(s) within 2× the top result's error`} />
                  {sidegrades && <Toggle checked={preferFewestChanges} onChange={setPreferFewestChanges} label="Prefer fewest changes" description="Reorder the sidegrade group so the smallest change comes first" />}
                </div>
              )}
              {sidegrades && orderedSidegrades.length > 0 && (
                <Card title={`${orderedSidegrades.length} sidegrade${orderedSidegrades.length === 1 ? '' : 's'}`} actions={<span className="text-xs text-muted">within noise of the top result</span>}>
                  <ResultBars
                    baseline={result.baseline}
                    rows={orderedSidegrades}
                    selected={sidegradePick?.name}
                    showRank={false}
                    lowerBetter={isLowerBetter(result.metric)}
                    renderExtra={(r) => r.name === sidegradePick?.name ? <span className="chip text-accent">pick{preferFewestChanges ? ' · fewest changes' : ''}</span> : undefined}
                  />
                </Card>
              )}
              <div className={`grid grid-cols-1 gap-4 ${selected ? '2xl:grid-cols-[1fr_380px]' : ''}`}>
                <Card title={`${result.results.length} combinations`} actions={<span className="text-xs text-muted">click a row to see the changes</span>}>
                  <ResultBars
                    baseline={result.baseline}
                    rows={result.results}
                    selected={selected?.name}
                    onSelect={setSelected}
                    lowerBetter={isLowerBetter(result.metric)}
                    renderExtra={(r) => {
                      const chips = variantChips(r)
                      if (r.meta.predicted_dps == null && !chips.length) return undefined
                      return (
                        <div className="flex items-center gap-1.5">
                          {r.meta.predicted_dps != null && (
                            <span
                              className="chip text-accent"
                              title={`Surrogate predicted ${fmtDps(r.meta.predicted_dps)} DPS before this was simmed exactly`}
                            >
                              predicted {fmtDps(r.meta.predicted_dps)} ({fmtPct(((r.meta.predicted_dps - r.dps) / r.dps) * 100)})
                            </span>
                          )}
                          {chips.map((c) => <span key={c.key} className="chip text-accent">{c.label}</span>)}
                        </div>
                      )
                    }}
                  />
                </Card>
                {selected && (
                  <Card className="order-first 2xl:order-none" title="Changes" actions={<button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelected(null)}>Close</button>}>
                    <div className="mb-2 text-sm">
                      <span className="font-medium">{selected.label}</span>
                      <span className={`ml-2 ${selected.delta_pct >= 0 ? 'text-good' : 'text-bad'}`}>{selected.delta_pct >= 0 ? '+' : ''}{selected.delta_pct.toFixed(2)}%</span>
                    </div>
                    <ChangedSlots row={selected} profile={profile} />
                  </Card>
                )}
              </div>
            </>
          ) : !job && (
            <EmptyState icon={<Trophy size={32} strokeWidth={1.5} />} title="Pick candidates and run" body="Equipped items are always considered; tick bag and vault items to add them to the pool." />
          )}
        </div>
      </div>
    </div>
  )
}
