import { useEffect, useMemo, useState } from 'react'
import { Gem, Play } from 'lucide-react'
import { api } from '../lib/api'
import { useStore } from '../store'
import { usePageJob } from '../hooks/useJob'
import { OptionsPanel } from '../components/OptionsPanel'
import { JobProgress } from '../components/JobProgress'
import { ResultBars } from '../components/ResultBars'
import { ItemCard, ItemIcon, SourceChip, WowheadOrFallback } from '../components/ItemCard'
import { qualityColor } from '../lib/items'
import { useWowheadRefresh, useWowheadActive } from '../lib/wowhead'
import { ChangedSlots } from '../components/ChangedSlots'
import { DpsHero, ResultActions, ResultNotes } from '../components/ResultView'
import { NeedProfile, EmptyState } from '../components/EmptyState'
import { Card, Checkbox, Collapsible, Field, Input, PageTitle, Select, Spinner, Tabs, Toggle } from '../components/ui'
import { isLowerBetter, SLOT_LABELS, STAT_LABELS, baseSlot, lowestEquippedIlevel, titleCase } from '../lib/wow'
import { fmtPct } from '../lib/format'
import type { DropSource, GemRef, LootSources, Recommendations, ResultGroup, ResultRow, SeasonData, Upgrade, UpgradeTrackDef } from '../lib/types'

type RaidSel = { enabled: boolean; difficulty: 'lfr' | 'normal' | 'heroic' | 'mythic'; bosses: number[] }

/** One droptimizer result row's left-hand icon/label, with a Wowhead link (or our fallback
 * tooltip) on both the icon and the item name. */
function DropRowLeft({ row: r }: { row: ResultRow }) {
  const item = r.meta.item
  const active = useWowheadActive(item)
  const src = r.meta.source ?? item?.source
  // meta.item.slot can be the generic "finger"/"trinket" candidates() emits; meta.changes is
  // keyed by the concrete slot this particular row targets (finger1 vs finger2, ...), so prefer
  // that for display.
  const slot = Object.keys(r.meta.changes ?? {})[0] ?? item?.slot ?? ''
  const label = item?.resolved === false ? `Item ${item.id}` : r.label
  return (
    <div className="flex min-w-0 items-center gap-2">
      {item && <WowheadOrFallback item={item} active={active}><ItemIcon item={item} size={28} /></WowheadOrFallback>}
      <div className="min-w-0">
        <div className="truncate text-sm font-medium" style={{ color: item ? qualityColor(item.quality) : undefined }}>
          {item ? (
            <WowheadOrFallback item={item} active={active}><span>{label}</span></WowheadOrFallback>
          ) : label}
          {' '}
          {item && <span className="text-xs font-normal text-accent">{item.ilevel}</span>}
          {item?.resolved === false && <span className="chip ml-1 text-amber-300 border-amber-700/60">unresolved</span>}
          {(item?.key?.startsWith('catalyst:') || src?.type === 'catalyst') && <span className="chip ml-1 text-accent">Catalyst</span>}
          {item?.key?.startsWith('socket:') && <span className="chip ml-1 text-accent">+socket</span>}
        </div>
        <div className="flex items-center gap-1 text-[11px] text-muted"><span>{SLOT_LABELS[slot] ?? slot}</span><SourceChip source={src} /></div>
      </div>
    </div>
  )
}

export function DroptimizerPage() {
  const profile = useStore((s) => s.profile)
  const options = useStore((s) => s.options)
  const setOptions = useStore((s) => s.setOptions)
  const toast = useStore((s) => s.toast)
  const { job, result, running, run, cancel } = usePageJob('droptimizer')

  const [loot, setLoot] = useState<LootSources | null>(null)
  const [lootFor, setLootFor] = useState<string | null>(null)
  const lootKey = profile ? `${profile.klass}:${profile.spec}` : ''
  const loading = !!profile && lootFor !== lootKey
  const [raids, setRaids] = useState<Record<number, RaidSel>>({})
  const [dungeon, setDungeon] = useState<{ enabled: boolean; key_level: number; ids: number[]; vault: boolean }>({ enabled: false, key_level: 10, ids: [], vault: false })
  const [worldBoss, setWorldBoss] = useState(false)
  const [delve, setDelve] = useState<{ enabled: boolean; tier: number }>({ enabled: false, tier: 8 })
  const [crafted, setCrafted] = useState<{ enabled: boolean; ilevel: number; stats: [string, string] }>({ enabled: false, ilevel: 0, stats: ['crit', 'haste'] })
  const [upgradeMode, setUpgradeMode] = useState<'drop' | 'max' | 'rank'>('drop')
  const [rank, setRank] = useState(4)
  const [upgradeEquipped, setUpgradeEquipped] = useState<'none' | 'match' | 'max'>('none')
  const [includeOffspec, setIncludeOffspec] = useState(false)
  const [selected, setSelected] = useState<ResultRow | null>(null)
  const [filter, setFilter] = useState<{ source: string; slot: string; minGain: number; minIlvl: number; upgradesOnly: boolean }>({ source: '', slot: '', minGain: 0, minIlvl: 0, upgradesOnly: false })
  const [groupBy, setGroupBy] = useState<ResultGroup['kind']>('boss')
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  // Min item level sent to the backend: candidates below it are never simmed at all. `null`
  // means "not touched yet" -- falls back to the profile's lowest equipped ilevel.
  const [minIlevelInput, setMinIlevelInput] = useState<number | null>(null)
  const minIlevel = minIlevelInput ?? (profile ? lowestEquippedIlevel(profile.equipped) : 0)

  const [includeCatalyst, setIncludeCatalyst] = useState(false)
  const [addSocket, setAddSocket] = useState(false)
  const [preferredGem, setPreferredGem] = useState<number | undefined>(undefined)
  const [catalystSource, setCatalystSource] = useState<{ enabled: boolean; track: string; rank: number }>({ enabled: false, track: '', rank: 1 })
  const [season, setSeason] = useState<SeasonData | null>(null)
  const [upgradeTracks, setUpgradeTracks] = useState<UpgradeTrackDef[]>([])
  const recsCache = useStore((s) => s.recommendations)
  const setRecommendations = useStore((s) => s.setRecommendations)
  const recKey = profile ? `${profile.klass}:${profile.spec}` : null
  const recs: Recommendations | null = recKey ? (recsCache[recKey] ?? null) : null

  useEffect(() => { void api.season().then((s) => { setSeason(s); setUpgradeTracks(s.upgrade_tracks ?? []); setCatalystSource((c) => ({ ...c, track: c.track || s.upgrade_tracks?.[0]?.name || '' })) }).catch(() => undefined) }, [])
  useEffect(() => {
    if (!profile || !recKey || recsCache[recKey]) return
    api.recommendations(profile.klass, profile.spec).then((r) => setRecommendations(recKey, r)).catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recKey])
  const gemPool: GemRef[] = recs ? [...Object.values(recs.gems.by_stat), ...recs.gems.unique] : []

  useEffect(() => {
    if (!profile) return
    const key = `${profile.klass}:${profile.spec}`
    api.lootSources(profile.klass, profile.spec)
      .then((l) => {
        setLoot(l)
        setLootFor(key)
        const first = l.raids[0]
        setRaids(Object.fromEntries(l.raids.map((r, i) => [r.instance_id, { enabled: i === 0, difficulty: 'heroic', bosses: r.bosses.map((b) => b.encounter_id) }])))
        if (first) setDungeon((d) => ({ ...d, ids: l.dungeons.map((x) => x.instance_id) }))
        if (l.crafted?.ilevels?.length) setCrafted((c) => ({ ...c, ilevel: l.crafted.ilevels![l.crafted.ilevels!.length - 1] }))
        if (l.delves?.length) setDelve((d) => ({ ...d, tier: l.delves[l.delves.length - 1].tier }))
      })
      .catch((e: Error) => { setLootFor(key); toast(`Could not load loot sources: ${e.message}`, 'error') })
  }, [profile?.klass, profile?.spec]) // eslint-disable-line react-hooks/exhaustive-deps

  const sources = useMemo<DropSource[]>(() => {
    const out: DropSource[] = []
    for (const [id, sel] of Object.entries(raids)) {
      if (!sel.enabled || !sel.bosses.length) continue
      const raid = loot?.raids.find((r) => r.instance_id === Number(id))
      const all = raid ? raid.bosses.length === sel.bosses.length : false
      out.push({ type: 'raid', instance_id: Number(id), difficulty: sel.difficulty, ...(all ? {} : { bosses: sel.bosses }) })
    }
    if (dungeon.enabled && dungeon.ids.length) {
      const all = loot ? loot.dungeons.length === dungeon.ids.length : false
      out.push({ type: 'dungeon', key_level: dungeon.key_level, ...(all ? {} : { instance_ids: dungeon.ids }), ...(dungeon.vault ? { vault: true } : {}) })
    }
    if (worldBoss) out.push({ type: 'world_boss' })
    if (delve.enabled) out.push({ type: 'delve', tier: delve.tier })
    if (crafted.enabled && crafted.ilevel) out.push({ type: 'crafted', ilevel: crafted.ilevel, stats: crafted.stats })
    if (catalystSource.enabled && catalystSource.track) out.push({ type: 'catalyst', track: catalystSource.track, rank: catalystSource.rank || undefined })
    return out
  }, [raids, dungeon, worldBoss, delve, crafted, loot, catalystSource])

  const upgrade: Upgrade = upgradeMode === 'rank' ? rank : upgradeMode

  /** Mirrors the backend's SimResult.groups keying (see API.md) so clicking a group row can
   * filter the drop list down to just its items. */
  const groupKeyForRow = (r: ResultRow): string | null => {
    const src = r.meta.source ?? r.meta.item?.source
    if (!src) return null
    const kind: ResultGroup['kind'] | null =
      src.type === 'raid' ? 'boss' : src.type === 'dungeon' ? 'dungeon' : src.type === 'delve' ? 'delve'
        : src.type === 'world_boss' ? 'world_boss' : src.type === 'crafted' ? 'crafted' : src.type === 'catalyst' ? 'catalyst' : null
    if (!kind) return null
    return `${kind}:${kind === 'boss' ? (src.boss ?? src.name) : src.name}`
  }

  const filtered = useMemo(() => {
    if (!result) return []
    return result.results.filter((r) => {
      const src = r.meta.source ?? r.meta.item?.source
      if (filter.source && `${src?.type}:${src?.name}` !== filter.source && src?.type !== filter.source) return false
      const slot = r.meta.item?.slot ?? Object.keys(r.meta.changes ?? {})[0] ?? ''
      if (filter.slot && baseSlot(slot) !== filter.slot) return false
      if (filter.upgradesOnly && r.delta <= 0) return false
      if (filter.minGain && r.delta_pct < filter.minGain) return false
      const ilevel = r.meta.item?.ilevel
      if (filter.minIlvl && (ilevel == null || ilevel < filter.minIlvl)) return false
      if (selectedGroup && groupKeyForRow(r) !== selectedGroup) return false
      return true
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, filter, selectedGroup])

  const groupsForKind = useMemo(() => (result?.groups ?? []).filter((g) => g.kind === groupBy), [result, groupBy])
  const groupKinds = useMemo(() => [...new Set((result?.groups ?? []).map((g) => g.kind))], [result])
  useEffect(() => {
    if (groupKinds.length && !groupKinds.includes(groupBy)) setGroupBy(groupKinds[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupKinds])

  const sourceOptions = useMemo(() => {
    if (!result) return []
    const m = new Map<string, string>()
    for (const r of result.results) {
      const s = r.meta.source ?? r.meta.item?.source
      if (!s) continue
      m.set(`${s.type}:${s.name}`, `${titleCase(s.type)} · ${s.name}`)
    }
    return [...m.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [result])

  useWowheadRefresh([filtered])

  if (!profile) return <><PageTitle title="Droptimizer" /><NeedProfile /></>

  const craftStats = loot?.crafted?.stats ?? ['crit', 'haste', 'mastery', 'versatility']
  const craftIlvls = loot?.crafted?.ilevels ?? []

  return (
    <div>
      <PageTitle
        title="Droptimizer"
        subtitle="Which drops would actually be upgrades?"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            disabled={running || !sources.length}
            onClick={() => {
              setSelected(null)
              setSelectedGroup(null)
              void run(() => api.droptimizer({
                profile, options, sources, upgrade, min_ilevel: minIlevel, upgrade_equipped: upgradeEquipped, include_offspec: includeOffspec,
                include_catalyst: includeCatalyst, add_socket: addSocket, preferred_gem: addSocket ? preferredGem : undefined,
              }))
            }}
          >
            <Play size={15} /> Run droptimizer
          </button>
        }
      />
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[380px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Sources" actions={loading ? <Spinner /> : <span className="text-xs text-muted">{sources.length} selected</span>}>
            {!loot && !loading && <div className="text-sm text-muted">Loot sources unavailable.</div>}
            {loot && (
              <div className="flex flex-col">
                {loot.raids.map((raid) => {
                  const sel = raids[raid.instance_id] ?? { enabled: false, difficulty: 'heroic' as const, bosses: [] }
                  const set = (p: Partial<RaidSel>) => setRaids({ ...raids, [raid.instance_id]: { ...sel, ...p } })
                  return (
                    <Collapsible key={raid.instance_id} defaultOpen={sel.enabled} title={<Checkbox checked={sel.enabled} onChange={(v) => set({ enabled: v })} label={raid.name} />} right={`${sel.bosses.length}/${raid.bosses.length} bosses`}>
                      <Tabs
                        className="mb-2"
                        value={sel.difficulty}
                        onChange={(d) => set({ difficulty: d })}
                        tabs={(raid.difficulties.length ? raid.difficulties : [{ name: 'lfr', ilevel: 0 }, { name: 'normal', ilevel: 0 }, { name: 'heroic', ilevel: 0 }, { name: 'mythic', ilevel: 0 }]).map((d) => ({
                          value: d.name as RaidSel['difficulty'],
                          label: <span>{titleCase(d.name)}{d.ilevel ? <span className="ml-1 text-[10px] text-faint">{d.ilevel}</span> : null}</span>,
                        }))}
                      />
                      <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                        {[...raid.bosses].sort((a, b) => a.order - b.order).map((b) => (
                          <Checkbox key={b.encounter_id} checked={sel.bosses.includes(b.encounter_id)} onChange={(v) => set({ bosses: v ? [...sel.bosses, b.encounter_id] : sel.bosses.filter((x) => x !== b.encounter_id), enabled: true })} label={b.name} />
                        ))}
                      </div>
                      <div className="mt-1.5 flex gap-1.5">
                        <button type="button" className="btn btn-sm" onClick={() => set({ bosses: raid.bosses.map((b) => b.encounter_id) })}>All</button>
                        <button type="button" className="btn btn-sm" onClick={() => set({ bosses: [] })}>None</button>
                      </div>
                    </Collapsible>
                  )
                })}

                <Collapsible title={<Checkbox checked={dungeon.enabled} onChange={(v) => setDungeon({ ...dungeon, enabled: v })} label="Mythic+" />} right={`${dungeon.ids.length}/${loot.dungeons.length}`}>
                  <div className="mb-2 flex items-end gap-3">
                    <Field label="Key level">
                      <Select value={dungeon.key_level} onChange={(e) => setDungeon({ ...dungeon, key_level: Number(e.target.value), enabled: true })}>
                        {loot.key_levels.map((k) => (
                          <option key={k.level} value={k.level}>{k.level === 0 ? 'Mythic 0' : k.level === -1 ? 'Great Vault (max)' : `+${k.level}`} · {k.ilevel}</option>
                        ))}
                      </Select>
                    </Field>
                    <div className="pb-1.5" title="Use the vault's ilvl for this key level instead of the end-of-dungeon ilvl">
                      <Toggle checked={dungeon.vault} onChange={(v) => setDungeon({ ...dungeon, vault: v, enabled: true })} label="Vault" />
                    </div>
                  </div>
                  <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                    {loot.dungeons.map((d) => (
                      <Checkbox key={d.instance_id} checked={dungeon.ids.includes(d.instance_id)} onChange={(v) => setDungeon({ ...dungeon, enabled: true, ids: v ? [...dungeon.ids, d.instance_id] : dungeon.ids.filter((x) => x !== d.instance_id) })} label={d.name} />
                    ))}
                  </div>
                </Collapsible>

                <Collapsible title={<Checkbox checked={worldBoss} onChange={setWorldBoss} label="World bosses" />} right={loot.world_bosses.map((w) => w.name).join(', ')}>
                  <div className="text-xs text-muted">{loot.world_bosses.length ? loot.world_bosses.map((w) => `${w.name}${w.ilevel ? ` (${w.ilevel})` : ''}`).join(', ') : 'No active world boss data.'}</div>
                </Collapsible>

                <Collapsible title={<Checkbox checked={delve.enabled} onChange={(v) => setDelve({ ...delve, enabled: v })} label="Delves" />} right={`Tier ${delve.tier}`}>
                  <Field label="Tier">
                    <Select value={delve.tier} onChange={(e) => setDelve({ tier: Number(e.target.value), enabled: true })}>
                      {loot.delves.map((d) => <option key={d.tier} value={d.tier}>Tier {d.tier} · {d.ilevel}</option>)}
                    </Select>
                  </Field>
                </Collapsible>

                <Collapsible title={<Checkbox checked={crafted.enabled} onChange={(v) => setCrafted({ ...crafted, enabled: v })} label="Crafted" />} right={crafted.enabled ? `${crafted.ilevel} ${crafted.stats.join('/')}` : ''}>
                  <div className="grid grid-cols-3 gap-2">
                    <Field label="Item level">
                      {craftIlvls.length ? (
                        <Select value={crafted.ilevel} onChange={(e) => setCrafted({ ...crafted, ilevel: Number(e.target.value), enabled: true })}>
                          {craftIlvls.map((i) => <option key={i} value={i}>{i}</option>)}
                        </Select>
                      ) : (
                        <Input type="number" value={crafted.ilevel || ''} onChange={(e) => setCrafted({ ...crafted, ilevel: Number(e.target.value), enabled: true })} />
                      )}
                    </Field>
                    <Field label="Stat 1">
                      <Select value={crafted.stats[0]} onChange={(e) => setCrafted({ ...crafted, stats: [e.target.value, crafted.stats[1]] })}>
                        {craftStats.map((s) => <option key={s} value={s}>{STAT_LABELS[s] ?? s}</option>)}
                      </Select>
                    </Field>
                    <Field label="Stat 2">
                      <Select value={crafted.stats[1]} onChange={(e) => setCrafted({ ...crafted, stats: [crafted.stats[0], e.target.value] })}>
                        {craftStats.map((s) => <option key={s} value={s}>{STAT_LABELS[s] ?? s}</option>)}
                      </Select>
                    </Field>
                  </div>
                </Collapsible>

                <Collapsible
                  title={<Checkbox checked={catalystSource.enabled} onChange={(v) => setCatalystSource({ ...catalystSource, enabled: v })} label="Catalyst" />}
                  right={catalystSource.enabled ? `${catalystSource.track || '—'}${catalystSource.rank ? ` ${catalystSource.rank}` : ''}` : ''}
                >
                  <div className="mb-1.5 text-xs text-faint">Your equipped/bag items in a catalyzable slot, catalyzed at this track/rank (uses Catalyst charges).</div>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Track">
                      <Select value={catalystSource.track} onChange={(e) => setCatalystSource({ ...catalystSource, track: e.target.value, enabled: true })}>
                        {upgradeTracks.map((t) => <option key={t.name} value={t.name}>{t.name}</option>)}
                        {!upgradeTracks.length && <option value="">Unknown</option>}
                      </Select>
                    </Field>
                    <Field label="Rank">
                      <Select value={catalystSource.rank} onChange={(e) => setCatalystSource({ ...catalystSource, rank: Number(e.target.value), enabled: true })}>
                        {(upgradeTracks.find((t) => t.name === catalystSource.track)?.ranks.map((rk) => rk.rank) ?? [1, 2, 3, 4, 5, 6, 7, 8]).map((rk) => <option key={rk} value={rk}>{rk}</option>)}
                      </Select>
                    </Field>
                  </div>
                </Collapsible>

                <div className="mt-3 border-t border-border pt-3">
                  <div className="label mb-1.5">Upgrade level (the drop)</div>
                  <div className="flex items-center gap-2">
                    <Tabs value={upgradeMode} onChange={setUpgradeMode} tabs={[{ value: 'drop', label: 'As dropped' }, { value: 'max', label: 'Fully upgraded' }, { value: 'rank', label: 'Rank' }]} />
                    {upgradeMode === 'rank' && <Input type="number" min={1} max={8} value={rank} onChange={(e) => setRank(Math.max(1, Number(e.target.value) || 1))} className="w-16" />}
                  </div>
                </div>

                <div className="mt-3 border-t border-border pt-3">
                  <Field label="Upgrade my equipped gear" hint="Comparing a maxed-out drop against under-upgraded current gear overstates the gain — this upgrades the baseline first">
                    <Select value={upgradeEquipped} onChange={(e) => setUpgradeEquipped(e.target.value as typeof upgradeEquipped)}>
                      <option value="none">No changes</option>
                      <option value="match">Match drop level</option>
                      <option value="max">Max</option>
                    </Select>
                  </Field>
                  <div className="mt-2">
                    <Toggle checked={includeOffspec} onChange={setIncludeOffspec} label="Include off-spec items" description="Also consider drops usable by another spec of this class" />
                  </div>
                </div>

                <div className="mt-3 border-t border-border pt-3">
                  <Toggle
                    checked={includeCatalyst}
                    onChange={setIncludeCatalyst}
                    label="Include Catalyst versions"
                    description={`Every drop in a catalyst slot${season?.catalyst?.slots?.length ? ` (${season.catalyst.slots.map((s) => SLOT_LABELS[s] ?? s).join(', ')})` : ''} also simmed as its catalyzed twin`}
                  />
                  <div className="mt-2 flex flex-wrap items-end gap-3">
                    <Toggle checked={addSocket} onChange={setAddSocket} label="Add vault socket" description="Drops in a vault-socket slot also simmed with an added socket" />
                    {addSocket && (
                      <Field label="Preferred gem" className="w-48">
                        <Select value={preferredGem ?? ''} onChange={(e) => setPreferredGem(e.target.value ? Number(e.target.value) : undefined)} className="py-1 text-xs">
                          <option value="">Season default</option>
                          {gemPool.map((g) => <option key={g.id} value={g.id}>{g.name} ({titleCase(g.stat)})</option>)}
                        </Select>
                      </Field>
                    )}
                  </div>
                </div>

                <div className="mt-3 border-t border-border pt-3">
                  <Field label="Min item level" hint="Drops below this are never simmed">
                    <Input type="number" min={0} value={minIlevel} onChange={(e) => setMinIlevelInput(Math.max(0, Number(e.target.value) || 0))} className="w-24" />
                  </Field>
                </div>
              </div>
            )}
          </Card>
          <OptionsPanel options={options} onChange={setOptions} />
        </div>

        <div className="flex flex-col gap-4">
          {job && <JobProgress job={job} onCancel={cancel} />}
          {result ? (
            <>
              <DpsHero result={result} />
              <ResultActions result={result} />
              <ResultNotes notes={result.notes} />
              {!!result.groups?.length && (
                <Card
                  title="Group by"
                  actions={<Tabs value={groupBy} onChange={(v) => { setGroupBy(v); setSelectedGroup(null) }} tabs={groupKinds.map((k) => ({ value: k, label: titleCase(k) }))} />}
                >
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted">
                          <th className="px-2 py-1">{titleCase(groupBy)}</th>
                          <th className="px-2 py-1 text-right">n</th>
                          <th className="px-2 py-1 text-right">Best</th>
                          <th className="px-2 py-1 text-right">Expected value</th>
                          <th className="px-2 py-1 text-right">Upgrade share</th>
                        </tr>
                      </thead>
                      <tbody>
                        {groupsForKind.map((g) => (
                          <tr
                            key={g.key}
                            className={`cursor-pointer border-b border-border/50 hover:bg-surface-2 ${selectedGroup === g.key ? 'bg-accent/10' : ''}`}
                            onClick={() => setSelectedGroup(selectedGroup === g.key ? null : g.key)}
                          >
                            <td className="px-2 py-1.5 font-medium">{g.label}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums text-muted">{g.n}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums text-good" title={g.best_label}>{fmtPct(g.best_pct)}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums">{fmtPct(g.ev_pct)}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums text-muted">{(g.upgrade_share * 100).toFixed(0)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-2 text-xs text-faint">Expected value assumes every item in a group is equally likely to drop. Click a row to filter the drops below to just that {groupBy === 'boss' ? 'boss' : groupBy}.</div>
                </Card>
              )}
              <Card
                title={`${filtered.length} of ${result.results.length} drops${selectedGroup ? ' (filtered by group)' : ''}`}
                actions={
                  <div className="flex flex-wrap items-center gap-2">
                    {selectedGroup && <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelectedGroup(null)}>Clear group filter</button>}
                    <Select value={filter.source} onChange={(e) => setFilter({ ...filter, source: e.target.value })} className="w-56 py-1 text-xs">
                      <option value="">All sources</option>
                      {sourceOptions.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </Select>
                    <Select value={filter.slot} onChange={(e) => setFilter({ ...filter, slot: e.target.value })} className="w-32 py-1 text-xs">
                      <option value="">All slots</option>
                      {['head', 'neck', 'shoulder', 'back', 'chest', 'wrist', 'hands', 'waist', 'legs', 'feet', 'finger', 'trinket', 'main_hand', 'off_hand'].map((s) => <option key={s} value={s}>{SLOT_LABELS[s]}</option>)}
                    </Select>
                    <label className="flex items-center gap-1 text-xs text-muted">min gain
                      <Input type="number" step={0.1} value={filter.minGain} onChange={(e) => setFilter({ ...filter, minGain: Number(e.target.value) || 0 })} className="w-16 py-1 text-xs" />%
                    </label>
                    <label className="flex items-center gap-1 text-xs text-muted">min ilvl
                      <Input type="number" min={0} value={filter.minIlvl || ''} onChange={(e) => setFilter({ ...filter, minIlvl: Number(e.target.value) || 0 })} className="w-16 py-1 text-xs" />
                    </label>
                    <Toggle checked={filter.upgradesOnly} onChange={(v) => setFilter({ ...filter, upgradesOnly: v })} label={<span className="text-xs">Upgrades only</span>} />
                  </div>
                }
              >
                <div className={`grid grid-cols-1 gap-4 ${selected ? '2xl:grid-cols-[1fr_380px]' : ''}`}>
                  <ResultBars
                    baseline={result.baseline}
                    rows={filtered}
                    selected={selected?.name}
                    onSelect={setSelected}
                    labelWidth={330}
                    lowerBetter={isLowerBetter(result.metric)}
                    renderLeft={(r) => <DropRowLeft row={r} />}
                  />
                  {selected && (
                    <div className="order-first 2xl:order-none">
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-sm font-semibold">Upgrade details</span>
                        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setSelected(null)}>Close</button>
                      </div>
                      {selected.meta.item && <div className="mb-2"><ItemCard item={selected.meta.item} showSource /></div>}
                      <ChangedSlots row={selected} profile={profile} />
                    </div>
                  )}
                </div>
              </Card>
            </>
          ) : !job && (
            <EmptyState icon={<Gem size={32} strokeWidth={1.5} />} title="Choose where you'll be looting" body="Pick raid bosses, a key level, delve tier or crafted piece, then run. Every possible drop is simmed in your current gear." />
          )}
        </div>
      </div>
    </div>
  )
}
