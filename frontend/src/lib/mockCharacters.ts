// Characters/Advisor/Reports fixtures for VITE_MOCK=1 (see API.md "Characters, Advisor, Reports").
// Deliberately has no import from lib/mock.ts (mock.ts imports *from* here) to avoid a circular
// module — shared item/rng helpers live in lib/mockShared.ts instead.
import type {
  AdvisorCandidate, AdvisorEffort, AdvisorOptions, AdvisorPathStep, AdvisorResult, AdvisorSlot, AdvisorVerdict,
  CharacterProfile, CharacterReport, CharacterSummary, Currency, DropSource, HistoryEntry, Item, ItemSource,
} from './types'
import { hash, leatherStats, mkItem, rng, type ItemSeed } from './mockShared'
import { averageIlvl, characterSlug, primaryStatFor, SLOT_LABELS } from './wow'

export const SEASON = 'Midnight Season 2 (12.1)'
const SIMC_VERSION = 'SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live (hotfix 2026-09-16/69875)'
const TIER_SET_HUNTER = 1991
const RAID = 'March on Quel\'Danas'
const raidSrc = (boss: string, difficulty = 'Normal'): ItemSource => ({ type: 'raid', name: RAID, boss, difficulty })
const dungSrc = (name: string, key_level = 8): ItemSource => ({ type: 'dungeon', name, key_level })
const craftSrc = (): ItemSource => ({ type: 'crafted', name: 'Leatherworking' })
const worldSrc = (): ItemSource => ({ type: 'world_boss', name: 'Oronok, Voidbound Colossus' })
const delveSrc = (tier = 8): ItemSource => ({ type: 'delve', name: 'Bountiful Delve', difficulty: `Tier ${tier}` })

const HUNTER_SEC: [string, string] = ['crit', 'haste']
const eqH = (s: ItemSeed, src: ItemSource, sec: [string, string] = HUNTER_SEC) => mkItem(`equipped:${s.slot}`, s, src, sec, leatherStats(s.slot, s.ilevel, sec))

// ---------- Testhunter-Testrealm: Marksmanship Hunter, avg ilvl 293, 4 tier pieces ----------
// ilvls picked so averageIlvl() below lands on exactly 293.0: 4 tier pieces @298, main_hand @298
// (counted twice — ranged weapon, inventory_type 15, no off_hand), 2 trinkets @294, the remaining
// 8 slots @289. See averageIlvl in lib/wow.ts for the two-hander/ranged-weapon doubling rule.
const EQUIPPED_TESTHUNTER: Record<string, Item> = {
  head: eqH({ id: 300101, name: 'Testrealmian Warhood', slot: 'head', inv: 1, ilevel: 298, icon: 'inv_helmet_28', set: TIER_SET_HUNTER }, raidSrc('Grand Marshal Kaz\'rok')),
  neck: eqH({ id: 300102, name: 'Chain of the Silver Hand', slot: 'neck', inv: 2, ilevel: 289, icon: 'inv_jewelry_necklace_07' }, dungSrc('The Shadowgate')),
  shoulder: eqH({ id: 300103, name: 'Testrealmian Mantle', slot: 'shoulder', inv: 3, ilevel: 298, icon: 'inv_shoulder_23', set: TIER_SET_HUNTER }, raidSrc('The Rootless Sentinel')),
  back: eqH({ id: 300104, name: 'Cloak of Fading Light', slot: 'back', inv: 16, ilevel: 289, icon: 'inv_misc_cape_20' }, dungSrc('Halls of Blood')),
  chest: eqH({ id: 300105, name: 'Testrealmian Warvest', slot: 'chest', inv: 5, ilevel: 298, icon: 'inv_chest_leather_09', set: TIER_SET_HUNTER }, raidSrc('Skyreach Vanguard')),
  wrist: eqH({ id: 300106, name: 'Bracers of the Long Hunt', slot: 'wrist', inv: 9, ilevel: 289, icon: 'inv_bracer_09', crafted: [[36, 32], 4] }, craftSrc()),
  hands: eqH({ id: 300107, name: 'Testrealmian Grips', slot: 'hands', inv: 10, ilevel: 298, icon: 'inv_gauntlets_18', set: TIER_SET_HUNTER }, raidSrc('Grand Marshal Kaz\'rok')),
  waist: eqH({ id: 300108, name: 'Girdle of Silent Steps', slot: 'waist', inv: 6, ilevel: 289, icon: 'inv_belt_28' }, dungSrc('Eco-Dome Al\'dani')),
  legs: eqH({ id: 300109, name: 'Legguards of the Wild Hunt', slot: 'legs', inv: 7, ilevel: 289, icon: 'inv_pants_04' }, worldSrc()),
  feet: eqH({ id: 300110, name: 'Boots of the Restless Trail', slot: 'feet', inv: 8, ilevel: 289, icon: 'inv_boots_09' }, dungSrc('Tazavesh Reforged')),
  finger1: eqH({ id: 300111, name: 'Signet of the Wayfarer', slot: 'finger1', inv: 11, ilevel: 289, icon: 'inv_jewelry_ring_16' }, delveSrc(8)),
  finger2: eqH({ id: 300112, name: 'Band of Fading Embers', slot: 'finger2', inv: 11, ilevel: 289, icon: 'inv_jewelry_ring_30' }, dungSrc('Vault of the Wardens')),
  trinket1: eqH({ id: 300113, name: 'Sentinel\'s Fading Ember', slot: 'trinket1', inv: 12, ilevel: 294, icon: 'inv_trinket_naxxramas04', unique: 'Unique-Equipped' }, raidSrc('The Sundered Choir', 'Heroic')),
  trinket2: eqH({ id: 300114, name: 'Hunter\'s Old Compass', slot: 'trinket2', inv: 12, ilevel: 294, icon: 'inv_misc_pocketwatch_02' }, worldSrc()),
  main_hand: eqH({ id: 300115, name: 'Longbow of the Arathi Vanguard', slot: 'main_hand', inv: 15, ilevel: 298, icon: 'inv_weapon_bow_16' }, raidSrc('The Sundered Choir', 'Heroic'), ['haste', 'crit']),
}

const BAGS_TESTHUNTER: Item[] = [
  mkItem('bag:0', { id: 300201, name: 'Warboots of the Silver Hand', slot: 'feet', inv: 8, ilevel: 294, icon: 'inv_boots_11' }, dungSrc('Algeth\'ar Academy', 10), ['haste', 'crit']),
  mkItem('bag:1', { id: 300202, name: 'Signet of the Rootless Sentinel', slot: 'finger', inv: 11, ilevel: 296, icon: 'inv_jewelry_ring_43' }, raidSrc('The Rootless Sentinel', 'Heroic'), ['crit', 'mastery']),
  mkItem('bag:2', { id: 300203, name: 'Sureshot, the Arathi Longbow', slot: 'main_hand', inv: 15, ilevel: 312, icon: 'inv_weapon_bow_22' }, raidSrc('The Sundered Choir', 'Heroic'), ['haste', 'crit']),
]

const VAULT_TESTHUNTER: Item[] = [
  mkItem('vault:0', { id: 300301, name: 'Hunter\'s Old Compass', slot: 'trinket', inv: 12, ilevel: 305, icon: 'inv_misc_pocketwatch_02' }, { type: 'vault', name: 'Great Vault', boss: 'Raid slot 1' }, ['crit', 'haste']),
  mkItem('vault:1', { id: 300302, name: 'Cinch of the Wayfarer', slot: 'waist', inv: 6, ilevel: 296, icon: 'inv_belt_15' }, { type: 'vault', name: 'Great Vault', boss: 'Dungeon slot 1' }, ['haste', 'mastery']),
]

const TALENTS_TESTHUNTER = 'CoPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYWZmZMzYmZmZmxsMzMzMDDbGxsbGZmZmZmxMzYmZmxwMzMzMYAAAAAAAAAAWA'
const CURRENCIES_TESTHUNTER: Currency[] = [
  { id: 3111, kind: 'currency', amount: 15, name: 'Weathered Crest', icon: 'inv_currency_crest_weathered', crest: 'Weathered', max_quantity: 2000 },
  { id: 3112, kind: 'currency', amount: 40, name: 'Carved Crest', icon: 'inv_currency_crest_carved', crest: 'Carved', max_quantity: 2000 },
]

export const TESTHUNTER_SLUG = characterSlug('Testhunter', 'Testrealm')

export const TESTHUNTER_PROFILE: CharacterProfile = {
  name: 'Testhunter',
  realm: 'Testrealm',
  region: 'us',
  level: 90,
  race: 'dwarf',
  klass: 'hunter',
  spec: 'marksmanship',
  role: 'attack',
  talents: TALENTS_TESTHUNTER,
  professions: { leatherworking: 100, skinning: 100 },
  equipped: EQUIPPED_TESTHUNTER,
  bags: BAGS_TESTHUNTER,
  vault: VAULT_TESTHUNTER,
  simc_header: [
    'hunter="Testhunter"', 'level=90', 'race=dwarf', 'region=us', 'server=testrealm', 'role=attack',
    'professions=leatherworking=100/skinning=100', 'spec=marksmanship', `talents=${TALENTS_TESTHUNTER}`,
  ].join('\n'),
  raw: '',
  imported_at: '2026-09-24T18:40:00Z',
  currencies: CURRENCIES_TESTHUNTER,
  catalyst_charges: 1,
  saved_loadouts: [
    { name: 'Marksmanship (Single Target)', string: TALENTS_TESTHUNTER, kind: 'active' },
    { name: 'Marksmanship (AoE)', string: 'CoPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYGZmZMzYmZmZmxsMzMzMDDbGxsbGZmZmZmxMzYGZmxwMzMzMYAAAAAAAAAAWA', kind: 'saved' },
  ],
  loot_spec: 'marksmanship',
  high_watermarks: { head: 298, shoulder: 298, chest: 298, hands: 298 },
}
TESTHUNTER_PROFILE.raw = [
  '# Testhunter - Marksmanship - 2026-09-24 18:40 - US/Testrealm', '# SimC Addon 12.1.0-01',
  `# upgrade_currencies=${CURRENCIES_TESTHUNTER.map((c) => `${c.name}:${c.amount}`).join(',')}`,
  TESTHUNTER_PROFILE.simc_header, '',
  ...Object.values(EQUIPPED_TESTHUNTER).map((i) => i.simc_string), '',
  '### Gear from Bags', ...BAGS_TESTHUNTER.map((i) => `# ${i.name} (${i.ilevel})\n# ${i.simc_string}`), '',
  '### Weekly Reward Choices', ...VAULT_TESTHUNTER.map((i) => `# ${i.name} (${i.ilevel})\n# ${i.simc_string}`),
].join('\n')

export function characterSummaryFromProfile(profile: CharacterProfile, slug?: string): CharacterSummary {
  return {
    slug: slug ?? characterSlug(profile.name, profile.realm),
    name: profile.name,
    realm: profile.realm,
    klass: profile.klass,
    spec: profile.spec,
    ilevel_equipped: Math.round(averageIlvl(profile.equipped) * 10) / 10,
    imported_at: profile.imported_at,
  }
}

export const TESTHUNTER_SUMMARY: CharacterSummary = characterSummaryFromProfile(TESTHUNTER_PROFILE, TESTHUNTER_SLUG)

// ---------- Advisor (POST /api/advisor/obvious-upgrades) — generic over any CharacterProfile ----------
type Archetype = {
  label: string
  effort: AdvisorEffort
  weekly?: boolean
  ilvlRange: [number, number]
  multiStep?: boolean
  crest?: string
  sourceFor: (slot: string, r: () => number) => ItemSource
  pathFor: (slot: string, item: Item, r: () => number) => AdvisorPathStep[]
}

const DROP_ADJ = ['Sunfury', 'Voidforged', "Magister's", "Blood Knight's", 'Dawnbringer', 'Eclipsed', 'Phoenix', 'Felscarred', 'Starlit', 'Duskwarden']
const DROP_NOUN: Record<string, string[]> = {
  head: ['Helm', 'Crown', 'Faceguard'], neck: ['Pendant', 'Choker', 'Amulet'], shoulder: ['Pauldrons', 'Spaulders', 'Mantle'], back: ['Cloak', 'Drape', 'Shroud'],
  chest: ['Breastplate', 'Chestguard', 'Cuirass'], wrist: ['Bracers', 'Vambraces', 'Wristguards'], hands: ['Gauntlets', 'Handguards', 'Grips'], waist: ['Girdle', 'Belt', 'Waistguard'],
  legs: ['Legplates', 'Greaves', 'Legguards'], feet: ['Sabatons', 'Warboots', 'Stompers'], finger1: ['Band', 'Ring', 'Seal', 'Loop'], finger2: ['Band', 'Ring', 'Seal', 'Loop'],
  trinket1: ['Idol', 'Reliquary', 'Talisman', 'Sigil'], trinket2: ['Idol', 'Reliquary', 'Talisman', 'Sigil'], main_hand: ['Longbow', 'Warblade', 'Edge'], off_hand: ['Sidearm', 'Fang', 'Razor'],
}
const UPGRADE_TRACK_NAMES: { name: string; crest: string }[] = [
  { name: 'Veteran', crest: 'Weathered' }, { name: 'Champion', crest: 'Carved' }, { name: 'Hero', crest: 'Runed' }, { name: 'Myth', crest: 'Gilded' },
]

const ARCHETYPES: Archetype[] = [
  {
    label: 'vault', effort: 'trivial', weekly: true, ilvlRange: [4, 12],
    sourceFor: () => ({ type: 'vault', name: 'Great Vault' }),
    pathFor: () => [{ step: 'Pick this slot in the Great Vault (weekly)' }],
  },
  {
    label: 'dungeon', effort: 'easy', ilvlRange: [2, 10],
    sourceFor: (_slot, r) => ({ type: 'dungeon', name: ['Halls of Blood', 'The Shadowgate', "Tazavesh Reforged"][Math.floor(r() * 3)], key_level: 8 }),
    pathFor: (_slot, item) => [{ step: `Drop from ${item.source?.name ?? 'a dungeon'} (+8) ${item.ilevel}` }],
  },
  {
    label: 'raidHeroic', effort: 'medium', ilvlRange: [4, 16],
    sourceFor: (_slot, r) => ({ type: 'raid', name: RAID, boss: ['Grand Marshal Kaz\'rok', 'The Rootless Sentinel', 'Skyreach Vanguard', 'The Sundered Choir'][Math.floor(r() * 4)], difficulty: 'Heroic' }),
    pathFor: (_slot, item) => [{ step: `Drop from ${item.source?.boss ?? 'a boss'} (Heroic) ${item.ilevel}` }],
  },
  {
    label: 'delve', effort: 'easy', ilvlRange: [1, 8], multiStep: true, crest: 'Weathered',
    sourceFor: () => ({ type: 'delve', name: 'Bountiful Delve', difficulty: 'Tier 8' }),
    pathFor: (_slot, item) => [
      { step: `Clear a Tier 8 Delve for ${item.ilevel - 3}` },
      { step: 'Upgrade Veteran 2/8 → 5/8', crest: 'Weathered', cost: 30 },
    ],
  },
  {
    label: 'crafted', effort: 'medium', ilvlRange: [-2, 6],
    sourceFor: () => ({ type: 'crafted', name: 'Crafted (best stat pair)' }),
    pathFor: () => [{ step: 'Commission from a max-tier crafter with the spec\'s best stat pair' }],
  },
  {
    label: 'raidMythic', effort: 'hard', ilvlRange: [10, 24],
    sourceFor: (_slot, r) => ({ type: 'raid', name: RAID, boss: ['Grand Marshal Kaz\'rok', 'The Sundered Choir'][Math.floor(r() * 2)], difficulty: 'Mythic' }),
    pathFor: (_slot, item) => [{ step: `Drop from ${item.source?.boss ?? 'a boss'} (Mythic) ${item.ilevel}` }],
  },
  {
    label: 'upgrade', effort: 'trivial', ilvlRange: [3, 9],
    sourceFor: () => ({ type: 'equipped', name: 'Owned crests' }),
    pathFor: (_slot, item, r) => {
      const t = UPGRADE_TRACK_NAMES[Math.floor(r() * UPGRADE_TRACK_NAMES.length)]
      return [{ step: `Upgrade ${t.name} on the item you already have (ilvl ${item.ilevel})`, crest: t.crest, cost: 15 + Math.floor(r() * 30) }]
    },
  },
]

const TRINKET_OR_WEAPON = new Set(['trinket1', 'trinket2', 'main_hand', 'off_hand'])

function classifyVerdict(slot: string, ilevelGain: number, statScoreDelta: number, breaksTier: boolean): AdvisorVerdict {
  if (TRINKET_OR_WEAPON.has(slot)) {
    if (ilevelGain <= -4) return 'downgrade'
    if (Math.abs(ilevelGain) < 4 && Math.abs(statScoreDelta) < 40) return 'sidegrade'
    return 'sim_to_confirm'
  }
  if (breaksTier) return 'sim_to_confirm'
  if (ilevelGain >= 6 && statScoreDelta >= 0) return 'obvious'
  if (ilevelGain >= 13) return 'likely'
  if (Math.abs(ilevelGain) < 6 && statScoreDelta > 0) return 'sim_to_confirm'
  if (Math.abs(ilevelGain) <= 2 && Math.abs(statScoreDelta) < 30) return 'sidegrade'
  return 'downgrade'
}

function statScoreFor(item: Item, order: string[]): number {
  const weights = [1.2, 1.0, 0.8, 0.6, 0.4]
  let score = 0
  order.forEach((stat, i) => { score += (item.stats[stat] ?? 0) * (weights[i] ?? 0.3) })
  return Math.round(score)
}

/** POST /api/advisor/obvious-upgrades fixture — generic over any profile, so both the Frost DK
 * and the Marksmanship Hunter fixtures (and any freshly-imported character) get a plausible
 * result from the "Refresh advisor" button, not just Testhunter's pre-baked report. */
export function buildAdvisorResult(slug: string, profile: CharacterProfile, options?: AdvisorOptions): AdvisorResult {
  const minGain = options?.min_ilevel_gain ?? 6
  const primary = primaryStatFor(profile.klass, profile.spec)
  const order = [primary, 'crit', 'haste', 'mastery', 'versatility'].filter((s, i, arr) => arr.indexOf(s) === i)
  const weights = Object.fromEntries(order.map((s, i) => [s, [1.2, 1.0, 0.8, 0.6, 0.4][i] ?? 0.3]))

  const tierSetIds = new Set(Object.values(profile.equipped).map((i) => i.set_id).filter((id): id is number => id != null))
  const tierSetId = tierSetIds.size ? [...tierSetIds][0] : null
  const slotsWithTier = Object.entries(profile.equipped).filter(([, i]) => i.set_id != null).map(([slot]) => slot)

  const slots: AdvisorSlot[] = Object.entries(profile.equipped).map(([slot, equippedItem]) => {
    const r = rng(hash(`${slug}:${slot}`))
    const equippedScore = statScoreFor(equippedItem, order)
    const n = 3 + Math.floor(r() * 4) // 3..6
    const shuffled = [...ARCHETYPES].sort(() => r() - 0.5).slice(0, Math.min(n, ARCHETYPES.length))
    let seedId = 900000 + hash(`${slug}:${slot}`) % 90000
    const candidates: AdvisorCandidate[] = shuffled.map((arch) => {
      const [lo, hi] = arch.ilvlRange
      const delta = Math.round(lo + r() * (hi - lo))
      const ilevel = Math.max(1, equippedItem.ilevel + delta)
      const isUpgradeInPlace = arch.label === 'upgrade'
      const adj = DROP_ADJ[Math.floor(r() * DROP_ADJ.length)]
      const nouns = DROP_NOUN[slot] ?? ['Item']
      const name = isUpgradeInPlace ? equippedItem.name : `${adj} ${nouns[Math.floor(r() * nouns.length)]}`
      const source = arch.sourceFor(slot, r)
      const willBreakTier = equippedItem.set_id != null && !isUpgradeInPlace && r() > 0.6
      const seed: ItemSeed = {
        id: isUpgradeInPlace ? equippedItem.id : seedId++,
        name, slot: equippedItem.slot, inv: equippedItem.inventory_type, ilevel,
        icon: equippedItem.icon, quality: equippedItem.quality,
        set: willBreakTier ? null : equippedItem.set_id,
      }
      const item = isUpgradeInPlace ? { ...equippedItem, ilevel, key: `advisor:${slug}:${slot}:upgrade` } : mkItem(`advisor:${slug}:${slot}:${arch.label}:${seed.id}`, seed, source, [order[1] ?? 'crit', order[2] ?? 'haste'], leatherStats(equippedItem.slot, ilevel, [order[1] ?? 'crit', order[2] ?? 'haste']))
      const statScore = statScoreFor(item, order)
      const statScoreDelta = statScore - equippedScore
      const ilevelGain = ilevel - equippedItem.ilevel
      const ilevelGainMax = ilevelGain + Math.round(r() * 6)
      const verdict = classifyVerdict(slot, ilevelGain, statScoreDelta, willBreakTier)
      const reasons: string[] = []
      reasons.push(`${ilevelGain >= 0 ? '+' : ''}${ilevelGain} ilvl`)
      if (statScoreDelta >= 0) reasons.push(`${order[1] ?? 'secondary'}/${order[2] ?? 'secondary'} matches priority`)
      else reasons.push('worse secondary spread than equipped')
      if (TRINKET_OR_WEAPON.has(slot)) reasons.push(slot.startsWith('trinket') ? 'trinket: effect needs sim' : 'weapon: needs a sim to confirm')
      if (willBreakTier) reasons.push('loses tier set bonus')
      if (arch.weekly) reasons.push('weekly vault pick')
      const path = arch.pathFor(slot, item, r)
      const alternatives: string[] = []
      if (r() > 0.5) alternatives.push(`Also drops from ${['Grand Marshal Kaz\'rok', 'The Rootless Sentinel', 'Skyreach Vanguard'][Math.floor(r() * 3)]}`)
      if (r() > 0.7) alternatives.push('Also available from the Great Vault')
      const candidate: AdvisorCandidate = {
        item, source: { ...source, effort: arch.effort, weekly: arch.weekly },
        ilevel_gain: ilevelGain, ilevel_gain_max: ilevelGainMax,
        stat_score: statScore, stat_score_delta: statScoreDelta,
        verdict, reasons, path, alternatives,
      }
      return candidate
    })
    // Obvious first, then by expected value (stat_score_delta) desc — matches API.md's ordering rule.
    candidates.sort((a, b) => {
      const rank: Record<AdvisorVerdict, number> = { obvious: 0, likely: 1, sim_to_confirm: 2, sidegrade: 3, downgrade: 4 }
      if (rank[a.verdict] !== rank[b.verdict]) return rank[a.verdict] - rank[b.verdict]
      return b.stat_score_delta - a.stat_score_delta
    })
    const bisHeuristic = candidates.length
      ? [...candidates].sort((a, b) => (b.item.ilevel - a.item.ilevel) || (b.stat_score - a.stat_score))[0]
      : null
    return {
      slot,
      equipped: { item: equippedItem, ilevel: equippedItem.ilevel, stat_score: equippedScore },
      // Downgrades are excluded from the pool unless explicitly asked for, per the obvious-upgrades
      // rules; guarantee at least 3 survivors per slot so every slot still has something to show.
      candidates: (() => {
        const kept = candidates.filter((c) => options?.include_downgrades || c.verdict !== 'downgrade')
        return kept.length >= 3 ? kept : candidates.slice(0, Math.max(3, kept.length))
      })(),
      bis_heuristic: bisHeuristic,
    }
  })

  const upgradesSlots = slots.filter((s) => s.candidates.some((c) => c.source.type === 'equipped')).map((s) => s.slot)
  const topgearKeys = [...profile.bags, ...profile.vault].map((i) => i.key)

  return {
    slug, character: profile.name, klass: profile.klass, spec: profile.spec,
    generated_at: new Date().toISOString(),
    stat_priority: { source: 'recommendation', order, weights },
    ilevel_equipped: averageIlvl(profile.equipped),
    slots,
    tier: { set_id: tierSetId, equipped_pieces: slotsWithTier.length, slots_with_tier: slotsWithTier, catalyst_charges: profile.catalyst_charges ?? null },
    sim_plan: {
      droptimizer: [
        { type: 'raid', instance_id: 1302, difficulty: 'heroic' },
        { type: 'dungeon', key_level: options?.key_level ?? 10 },
        { type: 'delve', tier: options?.delve_tier ?? 8 },
      ] as DropSource[],
      topgear_candidate_keys: topgearKeys,
      upgrades_slots: upgradesSlots,
      note: 'Sync this into Droptimizer/Top Gear/Upgrades to confirm with a real sim before committing crests.',
    },
    notes: [
      slotsWithTier.length > 0
        ? `${slotsWithTier.length}/5 tier pieces equipped (${slotsWithTier.map((s) => SLOT_LABELS[s] ?? s).join(', ')}); candidates that would break the set say so under "reasons".`
        : 'No tier pieces currently equipped.',
      `Candidates below a ${minGain} ilvl gain with worse stats are marked sim_to_confirm or sidegrade rather than dropped, per the obvious-upgrades rules.`,
    ],
  }
}

// ---------- Report (GET/PUT/DELETE /api/reports/{slug}) ----------
export const TESTHUNTER_ADVISOR: AdvisorResult = buildAdvisorResult(TESTHUNTER_SLUG, TESTHUNTER_PROFILE)

/** Two History rows so the report footer's `sim_refs` and the upgrades section's `sim` chips have
 * somewhere real to link (History → reopen the job). Spliced into lib/mock.ts's own `history`
 * array once, at import time — see mock.ts. */
export const TESTHUNTER_EXTRA_HISTORY: HistoryEntry[] = [
  { id: 'f9a1e001', type: 'droptimizer', character: 'Testhunter', spec: 'marksmanship', created: '2026-09-24T19:05:00Z', summary: 'March on Quel\'Danas Heroic + M+10 drops; best +2.10%' },
  { id: 'f9a1e002', type: 'topgear', character: 'Testhunter', spec: 'marksmanship', created: '2026-09-23T14:20:00Z', summary: 'Best: Sureshot, the Arathi Longbow (+1.60%)' },
]

const BIS_TRINKET1 = mkItem('bis:trinket1', { id: 300401, name: 'Heart of the Silver Hand', slot: 'trinket1', inv: 12, ilevel: 320, icon: 'inv_trinket_80_titan01a', unique: 'Unique-Equipped' }, raidSrc('The Sundered Choir', 'Mythic'), ['crit', 'haste'])
const BIS_MAIN_HAND = mkItem('bis:main_hand', { id: 300115, name: 'Longbow of the Arathi Vanguard', slot: 'main_hand', inv: 15, ilevel: 298, icon: 'inv_weapon_bow_16' }, raidSrc('The Sundered Choir', 'Heroic'), ['haste', 'crit'])
const BIS_WAIST = mkItem('bis:waist', { id: 300302, name: 'Cinch of the Wayfarer', slot: 'waist', inv: 6, ilevel: 296, icon: 'inv_belt_15' }, { type: 'vault', name: 'Great Vault' }, ['haste', 'mastery'])
const BIS_LEGS = mkItem('bis:legs', { id: 300402, name: 'Testrealmian Legguards', slot: 'legs', inv: 7, ilevel: 298, icon: 'inv_pants_08', set: TIER_SET_HUNTER }, raidSrc('Skyreach Vanguard', 'Heroic'), ['crit', 'haste'])
const BIS_FEET = mkItem('bis:feet', { id: 300201, name: 'Warboots of the Silver Hand', slot: 'feet', inv: 8, ilevel: 294, icon: 'inv_boots_11' }, dungSrc('Algeth\'ar Academy', 10), ['haste', 'crit'])

export const TESTHUNTER_REPORT: CharacterReport = {
  slug: TESTHUNTER_SLUG,
  character: TESTHUNTER_PROFILE.name,
  realm: TESTHUNTER_PROFILE.realm,
  klass: TESTHUNTER_PROFILE.klass,
  spec: TESTHUNTER_PROFILE.spec,
  updated_at: '2026-09-24T19:10:00Z',
  ilevel_equipped: TESTHUNTER_SUMMARY.ilevel_equipped,
  season: SEASON,
  simc_version: SIMC_VERSION,
  summary: 'Testhunter is sitting at 293 average item level with the Marksmanship 4-piece tier bonus active. '
    + 'Both trinkets and the main-hand bow are the biggest open questions and need a sim to confirm; every other '
    + 'slot already has at least one obvious upgrade in reach from the vault, a Tier 8 Delve, or a crest upgrade.',
  sections: [
    {
      kind: 'markdown',
      title: 'Where the DPS is',
      body: [
        '## Where the DPS is',
        '',
        '**Testhunter** is 293 ilvl with the Marksmanship **4-piece** tier bonus active. Priorities this week:',
        '',
        '- Clear the weekly **Great Vault** for a trinket shot — see the upgrades table below',
        '- Push at least one **Tier 8 Delve** for the waist upgrade',
        '- Sim the [Sureshot, the Arathi Longbow](https://www.wowhead.com/item=300203) drop before spending crests on the current bow',
        '',
        '| Slot | Current | Biggest lever |',
        '| --- | --- | --- |',
        '| Trinket 1 | Sentinel\'s Fading Ember | Great Vault trinket |',
        '| Main Hand | Longbow of the Arathi Vanguard | Heroic drop + upgrade |',
        '| Waist | Girdle of Silent Steps | Tier 8 Delve |',
        '',
        'See *Sources* at the bottom of this report for the theorycraft this is based on.',
      ].join('\n'),
    },
    {
      kind: 'upgrades',
      title: 'Upgrade priorities',
      rows: [
        {
          slot: 'trinket1', current: 'Sentinel\'s Fading Ember (294)', option: 'Hunter\'s Old Compass — Great Vault (305)',
          verdict: 'Sim to confirm', gain: '+11 ilvl, trinket effect needs sim',
          how: ['Pick the trinket slot in the Great Vault (weekly)', 'Equip directly, no crests needed'],
          sim: { job_id: 'f9a1e001', delta_pct: 2.1 },
        },
        {
          slot: 'main_hand', current: 'Longbow of the Arathi Vanguard (298)', option: 'Sureshot, the Arathi Longbow (Heroic, 312)',
          verdict: 'Likely', gain: '+14 ilvl',
          how: ['Drop from The Sundered Choir (Heroic) 312', 'Upgrade Champion 1/8 → 4/8 (45 Carved)'],
          sim: { job_id: 'f9a1e002', delta_pct: 1.6 },
        },
        {
          slot: 'waist', current: 'Girdle of Silent Steps (289)', option: 'Cinch of the Wayfarer — Tier 8 Delve (296)',
          verdict: 'Obvious', gain: '+7 ilvl, haste/crit matches priority',
          how: ['Clear a Tier 8 Delve', 'Upgrade Veteran 2/8 → 5/8 (30 Weathered)'],
        },
        {
          slot: 'legs', current: 'Legguards of the Wild Hunt (289)', option: 'Upgrade in place',
          verdict: 'Obvious', gain: '+6 ilvl',
          how: ['Upgrade Veteran 3/8 → 5/8 (20 Weathered)'],
        },
        {
          slot: 'finger2', current: 'Band of Fading Embers (289)', option: 'Signet of the Rootless Sentinel — Heroic (296)',
          verdict: 'Sidegrade', gain: '+7 ilvl, similar secondary spread',
          how: ['Drop from The Rootless Sentinel (Heroic) 296'],
        },
      ],
    },
    {
      kind: 'bis',
      title: 'Best in slot',
      rows: [
        { slot: 'trinket1', item: BIS_TRINKET1, source: 'The Sundered Choir (Mythic)', you_have: false, theorycraft_says: 'Top MM trinket per Icy Veins — highest sustained DPET at this budget.' },
        { slot: 'main_hand', item: BIS_MAIN_HAND, source: 'The Sundered Choir (Heroic)', you_have: true, theorycraft_says: 'Already equipped; Sureshot (bag) is worth simming as a sidegrade.' },
        { slot: 'waist', item: BIS_WAIST, source: 'Great Vault', you_have: false, theorycraft_says: 'Best waist itemization (haste/mastery) available at this ilvl band.' },
        { slot: 'legs', item: BIS_LEGS, source: 'Skyreach Vanguard (Heroic)', you_have: false, theorycraft_says: 'Tier legs — closes the 4pc/5pc gap once available.' },
        { slot: 'feet', item: BIS_FEET, source: 'Algeth\'ar Academy +10', you_have: true },
      ],
    },
    {
      kind: 'talents',
      title: 'Talent builds',
      entries: [
        { context: 'Single target / Patchwerk', loadout: TALENTS_TESTHUNTER, notes: 'Current loadout; leans into Trueshot uptime over cleave nodes.', source_url: 'https://www.icy-veins.com/wow/marksmanship-hunter-pve-dps-talent-build' },
        { context: 'M+ / cleave', loadout: 'CoPgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYGZmZMzYmZmZmxsMzMzMDDbGxsbGZmZmZmxMzYGZmxwMzMzMYAAAAAAAAAAWA', notes: 'Trades single-target nodes for Bombardment/Trick Shots value on packs.', source_url: 'https://www.wowhead.com/guide/classes/hunter/marksmanship/talent-builds' },
      ],
    },
    {
      kind: 'kv',
      title: 'Quick facts',
      items: [
        { label: 'Stat priority', value: 'Agility > Crit ≈ Haste > Mastery > Versatility', note: 'From season recommendation order (no statweights job on file yet).' },
        { label: 'Tier bonus', value: '4/5 equipped — 4-piece active', note: 'Legs is the only non-tier armor slot; see Best in slot.' },
        { label: 'Catalyst charges', value: '1' },
        { label: 'Crests owned', value: 'Carved 40, Weathered 15' },
      ],
    },
  ],
  advisor: TESTHUNTER_ADVISOR,
  sim_refs: [
    { job_id: 'f9a1e001', type: 'droptimizer', label: 'Droptimizer: raid + M+10 drops' },
    { job_id: 'f9a1e002', type: 'topgear', label: 'Top Gear: bag/vault candidates' },
  ],
  sources: [
    { title: 'Marksmanship Hunter PvE Guide', url: 'https://www.icy-veins.com/wow/marksmanship-hunter-pve-dps-guide', fetched_at: '2026-09-24T12:00:00Z' },
    { title: 'Marksmanship Hunter Stat Priority', url: 'https://www.wowhead.com/guide/classes/hunter/marksmanship/stat-priority-dps', fetched_at: '2026-09-24T12:05:00Z' },
  ],
}

export const TESTHUNTER_REPORT_LIST_ENTRY = {
  slug: TESTHUNTER_SLUG, character: TESTHUNTER_REPORT.character, klass: TESTHUNTER_REPORT.klass, spec: TESTHUNTER_REPORT.spec,
  updated_at: TESTHUNTER_REPORT.updated_at, summary: TESTHUNTER_REPORT.summary,
}
