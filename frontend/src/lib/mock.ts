// Fixture backend used when VITE_MOCK=1. Realistic-looking data with fake progress so every page
// is demonstrable without SimC. Never imported by the real bundle (lazy import in api.ts).
import type { ApiClient, JobListener, Unsubscribe } from './api'
import type {
  AddonImportResult, BreakdownRow, CharacterProfile, CharacterReport, CharacterSummary, ConsumableCategory, ConsumableOptions, ConsumablesBody,
  ConsumablesCustomSet, Currency, DecodedTalents, DropSource, EnchantRef, GemRef, GemsCustomSet, GemsMode, HistoryEntry,
  Item, ItemSearchResult, ItemSource, Job, JobType, LootSources, OmniumBody, OmniumChoice, OmniumCustomSet, OmniumMode,
  OmniumRow, Precision, RawUpgradeTrack, Recommendations, ReportListEntry, ResultGroup, ResultRow, SeasonData, Settings,
  SimOptions, SimResult, Status, SurrogateModel, SurrogateStatus, UpgradeInfo,
} from './types'
import { SLOTS } from './types'
import { CONSUMABLE_CATEGORY_LABELS, characterSlug, defaultOptions, prettifySimcName, SLOT_LABELS, titleCase } from './wow'

// Deterministic prng, item-fixture helpers: shared with lib/mockCharacters.ts (see mockShared.ts).
import { hash, mkItem, rng, sleep, type ItemSeed } from './mockShared'
// Characters/Advisor/Reports fixtures (see API.md "Characters, Advisor, Reports").
import {
  buildAdvisorResult, characterSummaryFromProfile, TESTHUNTER_EXTRA_HISTORY, TESTHUNTER_PROFILE, TESTHUNTER_REPORT,
  TESTHUNTER_REPORT_LIST_ENTRY, TESTHUNTER_SLUG, TESTHUNTER_SUMMARY,
} from './mockCharacters'

const RAID = 'March on Quel\'Danas'
const TIER_SET = 1987
const eq = (s: ItemSeed, src: ItemSource, sec: [string, string]) => mkItem(`equipped:${s.slot}`, s, src, sec)
const raidSrc = (boss: string, difficulty = 'Heroic'): ItemSource => ({ type: 'raid', name: RAID, boss, difficulty })
const dungSrc = (name: string, key_level = 10): ItemSource => ({ type: 'dungeon', name, key_level })

const EQUIPPED: Record<string, Item> = {
  head: eq({ id: 237631, name: 'Cryptbound Warlord\'s Visage', slot: 'head', inv: 1, ilevel: 678, icon: 'inv_plate_raiddeathknightgoblin_d_01_helm', set: TIER_SET, gems: [213743], enchant: null }, raidSrc('Kael\'thas Reborn'), ['crit', 'mastery']),
  // Deliberately one gem short of its socket count so the Gems page's custom editor and item
  // tooltips have a real empty-socket case to demonstrate.
  neck: eq({ id: 237568, name: 'Sunwell Warden\'s Chain', slot: 'neck', inv: 2, ilevel: 675, icon: 'inv_jewelry_necklace_58', gems: [213743], sockets: 2 }, raidSrc('Lady Liadrin'), ['haste', 'crit']),
  shoulder: eq({ id: 237629, name: 'Cryptbound Warlord\'s Pauldrons', slot: 'shoulder', inv: 3, ilevel: 675, icon: 'inv_plate_raiddeathknightgoblin_d_01_shoulder', set: TIER_SET }, raidSrc('Voidcaller Zaelith'), ['haste', 'mastery']),
  back: eq({ id: 237577, name: 'Drape of the Fallen Sun', slot: 'back', inv: 16, ilevel: 672, icon: 'inv_plate_raiddeathknightgoblin_d_01_cape', enchant: 7409 }, raidSrc('Sunblade Vanguard'), ['crit', 'versatility']),
  chest: eq({ id: 237634, name: 'Cryptbound Warlord\'s Cuirass', slot: 'chest', inv: 5, ilevel: 678, icon: 'inv_plate_raiddeathknightgoblin_d_01_chest', set: TIER_SET, enchant: 7364 }, raidSrc('The Voidbound Council'), ['crit', 'haste']),
  wrist: eq({ id: 221105, name: 'Everforged Vambraces', slot: 'wrist', inv: 9, ilevel: 675, icon: 'inv_plate_raiddeathknightgoblin_d_01_bracer', crafted: [[36, 32], 5], enchant: 7385, gems: [213743] }, { type: 'crafted', name: 'Blacksmithing' }, ['crit', 'haste']),
  hands: eq({ id: 237632, name: 'Cryptbound Warlord\'s Gauntlets', slot: 'hands', inv: 10, ilevel: 675, icon: 'inv_plate_raiddeathknightgoblin_d_01_glove', set: TIER_SET }, raidSrc('Kael\'thas Reborn'), ['haste', 'crit']),
  waist: eq({ id: 221103, name: 'Everforged Waistguard', slot: 'waist', inv: 6, ilevel: 675, icon: 'inv_plate_raiddeathknightgoblin_d_01_belt', crafted: [[36, 40], 5], gems: [213743] }, { type: 'crafted', name: 'Blacksmithing' }, ['crit', 'mastery']),
  legs: eq({ id: 237630, name: 'Cryptbound Warlord\'s Greaves', slot: 'legs', inv: 7, ilevel: 672, icon: 'inv_plate_raiddeathknightgoblin_d_01_pant', set: TIER_SET, enchant: 7601 }, raidSrc('Lady Liadrin'), ['crit', 'haste']),
  feet: eq({ id: 234010, name: 'Voidtouched Sabatons', slot: 'feet', inv: 8, ilevel: 672, icon: 'inv_plate_raiddeathknightgoblin_d_01_boot', enchant: 7418 }, dungSrc('Halls of Blood'), ['haste', 'versatility']),
  finger1: eq({ id: 237570, name: 'Seal of the Sin\'dorei', slot: 'finger1', inv: 11, ilevel: 675, icon: 'inv_jewelry_ring_82', gems: [213743, 213743], enchant: 7340 }, raidSrc('Voidcaller Zaelith'), ['crit', 'haste']),
  finger2: eq({ id: 234031, name: 'Band of Ceaseless Whispers', slot: 'finger2', inv: 11, ilevel: 672, icon: 'inv_70_dungeon_ring2c', gems: [213743, 213746], enchant: 7340 }, dungSrc('The Shadowgate'), ['haste', 'mastery']),
  trinket1: eq({ id: 237571, name: 'Heart of the Sunwell', slot: 'trinket1', inv: 12, ilevel: 678, icon: 'inv_trinket_80_titan01a', unique: 'Unique-Equipped' }, raidSrc('Kil\'jaeden\'s Shadow'), ['crit', 'haste']),
  trinket2: eq({ id: 234036, name: 'Signet of the Endless Hunger', slot: 'trinket2', inv: 12, ilevel: 672, icon: 'inv_gizmo_khoriumpowercore' }, dungSrc('Tazavesh Reforged'), ['crit', 'haste']),
  // Myth-max ilevel (693 = UPGRADE_TRACKS.Myth's top rank) so it's eligible for Voidforge —
  // demonstrates the wave-2 Voidforge toggle/chip on Top Gear, Droptimizer and Upgrades.
  main_hand: eq({ id: 237580, name: 'Quel\'Serrar, Reforged', slot: 'main_hand', inv: 13, ilevel: 693, icon: 'inv_sword_1h_nerubianraid_d_01', enchant: 7448 }, raidSrc('Kil\'jaeden\'s Shadow', 'Mythic'), ['crit', 'haste']),
  off_hand: eq({ id: 237581, name: 'Sunstrider Warblade', slot: 'off_hand', inv: 13, ilevel: 675, icon: 'inv_sword_1h_nerubianraid_d_01', enchant: 7448 }, raidSrc('Sunblade Vanguard'), ['haste', 'mastery']),
}

const BAGS: Item[] = [
  mkItem('bag:0', { id: 234020, name: 'Helm of the Shattered Star', slot: 'head', inv: 1, ilevel: 675, icon: 'inv_plate_raiddeathknightemerald_d_01_helm', gems: [213743] }, dungSrc('Eco-Dome Al\'dani'), ['haste', 'versatility']),
  mkItem('bag:1', { id: 234022, name: 'Cinch of Devoured Light', slot: 'waist', inv: 6, ilevel: 678, icon: 'inv_plate_raiddeathknightemerald_d_01_belt' }, dungSrc('Halls of Blood', 12), ['crit', 'haste']),
  mkItem('bag:2', { id: 234027, name: 'Ring of Hollow Promises', slot: 'finger', inv: 11, ilevel: 678, icon: 'inv_70_dungeon_ring1a', gems: [213743, 213743] }, dungSrc('The Shadowgate', 12), ['crit', 'mastery']),
  mkItem('bag:3', { id: 234038, name: 'Voidglass Reliquary', slot: 'trinket', inv: 12, ilevel: 672, icon: 'inv_misc_enggizmos_18' }, dungSrc('Vault of the Wardens', 10), ['haste', 'crit']),
  mkItem('bag:4', { id: 237578, name: 'Cloak of the Eternal Dawn', slot: 'back', inv: 16, ilevel: 678, icon: 'inv_plate_raiddeathknightemerald_d_01_cape' }, raidSrc('Voidcaller Zaelith', 'Mythic'), ['haste', 'crit']),
  mkItem('bag:5', { id: 234019, name: 'Warboots of the Unburied', slot: 'feet', inv: 8, ilevel: 665, icon: 'inv_plate_raiddeathknightemerald_d_01_boot' }, dungSrc('Algeth\'ar Academy', 8), ['crit', 'mastery']),
  mkItem('bag:6', { id: 221108, name: 'Everforged Stoneplate Greaves', slot: 'legs', inv: 7, ilevel: 675, icon: 'inv_plate_raiddeathknightemerald_d_01_pant', crafted: [[36, 32], 5] }, { type: 'crafted', name: 'Blacksmithing' }, ['crit', 'haste']),
  mkItem('bag:7', { id: 234040, name: 'Fist of the Forgotten', slot: 'main_hand', inv: 13, ilevel: 672, icon: 'inv_mace_1h_nerubianraid_d_01' }, dungSrc('Tazavesh Reforged', 10), ['crit', 'versatility']),
]
const VAULT: Item[] = [
  mkItem('vault:0', { id: 237573, name: 'Sunfury Signet', slot: 'finger', inv: 11, ilevel: 684, icon: 'inv_jewelry_ring_43', gems: [213743, 213743] }, { type: 'vault', name: 'Great Vault', boss: 'Raid slot 1' }, ['haste', 'crit']),
  mkItem('vault:1', { id: 237633, name: 'Cryptbound Warlord\'s Greaves', slot: 'legs', inv: 7, ilevel: 684, icon: 'inv_plate_raiddeathknightgoblin_d_01_pant', set: TIER_SET }, { type: 'vault', name: 'Great Vault', boss: 'Raid slot 2' }, ['crit', 'haste']),
  mkItem('vault:2', { id: 234037, name: 'Chalice of Whispered Ruin', slot: 'trinket', inv: 12, ilevel: 684, icon: 'inv_trinket_revendreth_01_gold' }, { type: 'vault', name: 'Great Vault', boss: 'Dungeon slot 1' }, ['crit', 'haste']),
]

const TALENTS = 'CwPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYmZmZMzYmxwMzMzMDzMbmxsNzMNmZmZmZmxMzYmZmBzMzMzMYAAAAAAAAAAWA'

// ---------- "unresolved item" scenario ----------
// `?mockScenario=unresolved` in the URL (dev-mode only) demonstrates the Import page's warning
// banner and the unresolved-item placeholder/chip without needing a real backend lookup miss.
function mockScenario(): string | null {
  if (typeof window === 'undefined') return null
  return new URLSearchParams(window.location.search).get('mockScenario')
}

const UNRESOLVED_WARNINGS = [
  'Item 268252 could not be resolved against the cached game data (build 12.1.0.69875). Refresh data in Settings, then re-import.',
]

function unresolvedBagItem(): Item {
  const item = mkItem('bag:unresolved', { id: 268252, name: 'Unknown Item', slot: 'trinket', inv: 12, ilevel: 0, icon: '' }, { type: 'bag', name: 'Bags' }, ['crit', 'haste'])
  return { ...item, icon: '', quality: 1, stats: {}, gem_ids: [], enchant_id: null, resolved: false }
}

/** Applies the unresolved-item / no-currencies scenarios to a freshly imported/looked-up profile
 * when the URL asks for it (`?mockScenario=unresolved` or `?mockScenario=nocurrencies`); a no-op
 * otherwise. `nocurrencies` demonstrates the Upgrades page's re-export hint for an older SimC
 * addon export that predates the "# upgrade_currencies=" line. */
function withMockScenario(profile: CharacterProfile): CharacterProfile {
  const scenario = mockScenario()
  if (scenario === 'unresolved') {
    return { ...profile, bags: [...profile.bags, unresolvedBagItem()], warnings: [...UNRESOLVED_WARNINGS] }
  }
  if (scenario === 'nocurrencies') {
    return { ...profile, currencies: [], catalyst_charges: null }
  }
  return profile
}

// ---------- crest currencies — CharacterProfile.currencies ----------
// crest strings match UPGRADE_TRACKS[*].crest below, since that's what ResultRow.meta.upgrade.crest
// is set to and Currency.crest must match it for the Upgrades page to look up owned amounts.
const CURRENCIES: Currency[] = [
  { id: 3110, kind: 'currency', amount: 120, name: 'Gilded Crest', icon: 'inv_currency_crest_gilded', crest: 'Gilded', max_quantity: 2000 },
  { id: 3109, kind: 'currency', amount: 30, name: 'Runed Crest', icon: 'inv_currency_crest_runed', crest: 'Runed', max_quantity: 2000 },
]

export const PROFILE: CharacterProfile = {
  name: 'Frostbyte',
  realm: 'Area 52',
  region: 'us',
  level: 90,
  race: 'blood_elf',
  klass: 'death_knight',
  spec: 'frost',
  role: 'attack',
  talents: TALENTS,
  professions: { blacksmithing: 100, engineering: 100 },
  equipped: EQUIPPED,
  bags: BAGS,
  vault: VAULT,
  simc_header: [
    'deathknight="Frostbyte"', 'level=90', 'race=blood_elf', 'region=us', 'server=area_52', 'role=attack',
    'professions=blacksmithing=100/engineering=100', 'spec=frost', `talents=${TALENTS}`,
  ].join('\n'),
  raw: '',
  imported_at: new Date().toISOString(),
  currencies: CURRENCIES,
  catalyst_charges: 2,
  saved_loadouts: [
    { name: 'Frost (Raid)', string: TALENTS, kind: 'active' },
    { name: 'Frost (M+)', string: 'CwPAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYWZmZMzYmxwMzMzMDzMbmxsNzMNmZmZmZmxMzYGZmxwMzMzMYAAAAAAAAAAWA', kind: 'saved' },
    { name: 'Unholy pivot', string: 'CwPQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYmZmZMzYmxwMzMzMDzMbmxsNzMNmZmZmZmxMzYmZmBzMzMzMYAAAAAAAAAAWA', kind: 'saved' },
  ],
  loot_spec: 'frost',
  high_watermarks: { head: 678, chest: 678, legs: 672 },
  // First choice of each Omnium Folio row (see OMNIUM_ROWS below) — entry_id -> rank.
  omnium: { '118601': 1, '118611': 1, '118621': 1, '118631': 1, '118641': 1 },
}
PROFILE.raw = [
  '# Frostbyte - Frost - 2026-09-21 20:14 - US/Area 52', '# SimC Addon 12.1.0-01',
  `# upgrade_currencies=${CURRENCIES.map((c) => `${c.name}:${c.amount}`).join(',')}`,
  PROFILE.simc_header, '',
  ...Object.values(EQUIPPED).map((i) => i.simc_string), '',
  '### Gear from Bags', ...BAGS.map((i) => `# ${i.name} (${i.ilevel})\n# ${i.simc_string}`), '',
  '### Weekly Reward Choices', ...VAULT.map((i) => `# ${i.name} (${i.ilevel})\n# ${i.simc_string}`),
].join('\n')

// ---------- result fixtures ----------
const BASE_DPS = 2_412_870

const BREAKDOWN: BreakdownRow[] = [
  ['Obliterate', 49020, 'direct', 27.4, 148, 0.71],
  ['Frost Strike', 49143, 'direct', 16.9, 121, 0.68],
  ['Howling Blast', 49184, 'direct', 8.2, 62, 0.66],
  ['Frost Fever', 55095, 'periodic', 4.1, 0, 0.61],
  ['Breath of Sindragosa', 152279, 'periodic', 12.6, 0, 0.64],
  ['Remorseless Winter', 196770, 'periodic', 3.3, 0, 0.6],
  ['Razorice', 50401, 'direct', 5.9, 590, 0.69],
  ['Glacial Advance', 194913, 'direct', 1.8, 14, 0.7],
  ['Reaper\'s Mark', 439843, 'direct', 3.9, 6, 0.75],
  ['Wave of Souls', 439656, 'direct', 1.1, 12, 0.66],
  ['Exterminate', 441378, 'direct', 2.7, 9, 0.72],
  ['Frostwhelp\'s Aid', 377226, 'pet', 1.4, 5, 0.63],
  ['Chill Streak', 305392, 'direct', 1.0, 9, 0.62],
  ['Abomination Limb', 383269, 'periodic', 2.1, 0, 0.6],
  ['Soul Reaper', 343294, 'periodic', 1.9, 8, 0.7],
  ['Icy Death Torrent', 435010, 'direct', 1.6, 34, 0.66],
  ['Death and Decay', 43265, 'periodic', 0.7, 0, 0.58],
  ['Frostscythe', 207230, 'direct', 0.5, 4, 0.7],
  ['Unholy Strength', 53365, 'direct', 0.9, 0, 0.6],
  ['Auto Attack', 6603, 'direct', 1.0, 512, 0.62],
].map(([name, id, type, pct, count, critPct]) => {
  const total = (BASE_DPS * 300 * (pct as number)) / 100
  const hits = (count as number) || Math.round(total / 400000)
  return {
    name: name as string, id: id as number, type: type as BreakdownRow['type'], total, pct: pct as number,
    count: hits, hit: total / Math.max(1, hits) / (1 + (critPct as number)), crit: (total / Math.max(1, hits)) * 1.35, crit_pct: (critPct as number) * 100,
  }
})

const UPTIMES = [
  ['Killing Machine', 61.4], ['Rime', 38.2], ['Pillar of Frost', 32.5], ['Icy Talons', 96.8], ['Unleashed Frenzy', 91.2],
  ['Breath of Sindragosa', 41.7], ['Bloodlust', 13.3], ['Razorice (5)', 88.9], ['Frost Fever', 99.1], ['Enduring Strength', 28.4],
  ['Bonegrinder', 21.0], ['Cold Heart', 54.6], ['Reaper\'s Mark', 18.7], ['Empower Rune Weapon', 12.1], ['Frostwhelp\'s Aid', 34.0],
].map(([name, pct]) => ({ name: name as string, pct: pct as number }))

const STAT_WEIGHTS = {
  weights: { strength: 1.0, haste: 0.74, crit: 0.67, mastery: 0.59, versatility: 0.55, weapon_dps: 3.21 },
  normalized: { strength: 1.0, haste: 0.74, crit: 0.67, mastery: 0.59, versatility: 0.55, weapon_dps: 3.21 },
  error: { strength: 0.012, haste: 0.021, crit: 0.019, mastery: 0.023, versatility: 0.02, weapon_dps: 0.11 },
  pawn: '( Pawn: v1: "Frostbyte-Frost": Class=DeathKnight, Spec=Frost, Strength=1.00, Haste=0.74, CritRating=0.67, MasteryRating=0.59, Versatility=0.55, Dps=3.21 )',
}

/** Every metric SimC reports for a row (profileset_metric=dps,prioritydps,dtps,hps,dmg_taken is
 * always emitted per API.md), scaled off whatever the row's primary `dps` field holds. */
function metricsFor(dps: number, r: () => number): Record<string, number> {
  return {
    dps, prioritydps: dps * (0.72 + r() * 0.08), dtps: dps * (0.11 + r() * 0.03),
    hps: dps * (0.04 + r() * 0.02), dmg_taken: dps * (0.13 + r() * 0.03),
  }
}

/** Highest Smart Sim precision stage each row reached (1..3, higher = more precise) when
 * `options.precision` is set — the best-looking rows "survive" to stage 3, others get dropped
 * earlier, mirroring the staged pruning described in API.md. No-op (leaves meta.stage unset)
 * when precision is off. */
function applyPrecisionStages(rows: ResultRow[], precision: Precision | null | undefined): void {
  if (!precision || !rows.length) return
  const ranked = [...rows].sort((a, b) => b.delta_pct - a.delta_pct)
  const n = ranked.length
  ranked.forEach((row, i) => {
    const frac = i / n
    row.meta.stage = frac < 0.4 ? 3 : frac < 0.75 ? 2 : 1
  })
}

/** Fills in the metric/precision/valid_fight_style fields the wave-1 contract adds to every
 * result, regardless of job type. Mutates and returns `result` for easy chaining. */
function finalizeResult(result: SimResult): SimResult {
  const r = rng(hash(result.job_id) ^ 0x6d6f636b)
  result.metric = result.options.metric ?? 'dps'
  // Demonstrates the warning banner: pick CastingPatchwerk in the fight style select to see it.
  result.valid_fight_style = result.options.fight_style !== 'CastingPatchwerk'
  result.baseline.metrics = metricsFor(result.baseline.dps, r)
  for (const row of result.results) row.metrics = metricsFor(row.dps, r)
  applyPrecisionStages(result.results, result.options.precision)
  return result
}

function baseResult(id: string, type: JobType, options: SimOptions, dps = BASE_DPS): SimResult {
  return {
    job_id: id, type, character: PROFILE.name, spec: PROFILE.spec, klass: PROFILE.klass,
    simc_version: 'SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live (hotfix 2026-09-16/69875)',
    wow_version: '12.1.0.69875', options,
    baseline: { name: 'baseline', label: 'Current gear', dps, dps_error: dps * (options.target_error ?? 0.1) / 100 },
    results: [], breakdown: BREAKDOWN, uptimes: UPTIMES,
    timing: { seconds: 0, iterations: options.iterations ?? 10000 }, input_file: `runtime/work/${id}/input.simc`,
  }
}

type TopGearVariants = {
  catalyst?: { keys: string[]; min_set_pieces?: 0 | 2 | 4 }
  add_socket?: { keys: string[]; gem_id?: number }
  voidforge?: { keys: string[] }
  crafted?: { key: string; stats: [string, string]; embellishment_id?: number; quality_bonus?: number }[]
}

function topGearRows(
  id: string, candidateKeys: string[], maxCombos: number, predictModel?: SurrogateModel | null, minIlevel?: number | null,
  extraItems: Item[] = [], loadouts: { name: string; string: string }[] = [], variants: TopGearVariants = {},
): ResultRow[] {
  const all = [...BAGS, ...VAULT, ...Object.values(EQUIPPED), ...extraItems]
  const byKey = new Map(all.map((i) => [i.key, i]))
  const cands = all.filter((i) => candidateKeys.includes(i.key) && !i.key.startsWith('equipped:') && (minIlevel == null || i.ilevel >= minIlevel))
  // Variant twins (catalyst/+socket/voidforge/recraft) are offered alongside the plain candidates,
  // keyed with their kind prefix per API.md ("catalyst:", "socket:", "voidforge:", "crafted:").
  const variantExtras: Item[] = []
  for (const k of variants.catalyst?.keys ?? []) { const base = byKey.get(k); if (base) variantExtras.push(catalystTwin(base)) }
  for (const k of variants.add_socket?.keys ?? []) { const base = byKey.get(k); if (base) variantExtras.push(socketTwin(base, variants.add_socket?.gem_id)) }
  for (const k of variants.voidforge?.keys ?? []) { const base = byKey.get(k); if (base) variantExtras.push(voidforgeTwin(base)) }
  for (const c of variants.crafted ?? []) { const base = byKey.get(c.key); if (base) variantExtras.push(craftedTwin(base, c.stats, c.embellishment_id, !!c.quality_bonus)) }
  const pool = [...cands, ...variantExtras]
  const minSetPieces = variants.catalyst?.min_set_pieces ?? 0
  const resolveSlot = (slot: string, used: Set<string>) =>
    slot === 'finger' ? (used.has('finger1') ? 'finger2' : 'finger1') : slot === 'trinket' ? (used.has('trinket1') ? 'trinket2' : 'trinket1') : slot
  const variantBonus = (key: string) =>
    key.startsWith('catalyst:') ? 0.0015 : key.startsWith('socket:') ? 0.0009 : key.startsWith('voidforge:') ? 0.0022 : key.startsWith('crafted:') ? 0.0008 : 0
  const r = rng(hash(id))
  const rows: ResultRow[] = []
  const n = Math.min(maxCombos, 40)
  for (let i = 0; i < n; i++) {
    const k = 1 + Math.floor(r() * Math.min(3, pool.length || 1))
    const picks: Item[] = []
    const used = new Set<string>()
    for (let j = 0; j < k && pool.length; j++) {
      const c = pool[Math.floor(r() * pool.length)]
      if (picks.some((p) => p.key === c.key)) continue
      const s = resolveSlot(c.slot, used)
      if (used.has(s)) continue
      used.add(s)
      picks.push({ ...c, slot: s })
    }
    if (!picks.length) continue
    if (minSetPieces && countSetPieces(picks) < minSetPieces) continue
    const changes: Record<string, Item> = {}
    for (const p of picks) changes[p.slot] = p
    // Each combo is simmed per loadout when loadouts were given — round-robin over them here.
    const loadout = loadouts.length ? loadouts[i % loadouts.length] : null
    const loadoutBias = loadout ? ((hash(loadout.string) % 1000) / 1000 - 0.5) * 0.01 : 0
    const gain = picks.reduce((a, p) => a + (p.ilevel - (EQUIPPED[p.slot]?.ilevel ?? 670)) * 0.0011 + (r() - 0.45) * 0.004 + variantBonus(p.key), 0) + loadoutBias
    const dps = BASE_DPS * (1 + gain)
    // Experimental "smart" surrogate: predicted dps close to, but not exactly, the simmed value.
    const predicted_dps = predictModel ? dps * (1 + (r() - 0.5) * (predictModel.val_mae_pct / 100)) : undefined
    rows.push({
      name: `combo_${i + 1}${loadout ? `_${loadout.name}` : ''}`,
      label: picks.map((p) => p.name).join(' + ') + (loadout ? ` [${loadout.name}]` : ''),
      dps, dps_error: dps * 0.003,
      delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes, items: picks, predicted_dps, loadout: loadout?.name },
    })
  }
  // Guarantee at least one row per requested variant so toggling one in the UI always shows a
  // result with the corresponding suffix chip, even on an unlucky random draw above.
  for (const v of variantExtras) {
    if (rows.some((rw) => rw.meta.items?.some((p) => p.key === v.key))) continue
    const slot = resolveSlot(v.slot, new Set())
    const gain = (v.ilevel - (EQUIPPED[slot]?.ilevel ?? 670)) * 0.0011 + variantBonus(v.key) + 0.0004
    if (minSetPieces && countSetPieces([{ ...v, slot }]) < minSetPieces) continue
    const dps = BASE_DPS * (1 + gain)
    rows.push({
      name: `combo_variant_${v.key}`, label: v.name, dps, dps_error: dps * 0.003,
      delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes: { [slot]: { ...v, slot } }, items: [{ ...v, slot }] },
    })
  }
  rows.sort((a, b) => b.dps - a.dps)
  return rows
}

const RAID_BOSSES = ['Sunblade Vanguard', 'Lady Liadrin', 'Voidcaller Zaelith', 'The Voidbound Council', 'Kael\'thas Reborn', 'Grand Magister Rommath', 'Kil\'jaeden\'s Shadow', 'The Sunwell Unbound']
const DUNGEONS = ['Halls of Blood', 'The Shadowgate', 'Eco-Dome Al\'dani', 'Tazavesh Reforged', 'Vault of the Wardens', 'Algeth\'ar Academy', 'Magisters\' Terrace', 'Sunwell Plateau: Depths']
const DROP_ICONS: Record<string, string> = {
  head: 'inv_plate_raiddeathknightemerald_d_01_helm', neck: 'inv_jewelry_necklace_58', shoulder: 'inv_plate_raiddeathknightemerald_d_01_shoulder', back: 'inv_plate_raiddeathknightemerald_d_01_cape',
  chest: 'inv_plate_raiddeathknightemerald_d_01_chest', wrist: 'inv_plate_raiddeathknightemerald_d_01_bracer', hands: 'inv_plate_raiddeathknightemerald_d_01_glove', waist: 'inv_plate_raiddeathknightemerald_d_01_belt',
  legs: 'inv_plate_raiddeathknightemerald_d_01_pant', feet: 'inv_plate_raiddeathknightemerald_d_01_boot', finger: 'inv_jewelry_ring_43', trinket: 'inv_trinket_maldraxxus_02_yellow',
  main_hand: 'inv_axe_1h_nerubianraid_d_01', off_hand: 'inv_sword_1h_nerubianraid_d_01',
}
const DROP_ADJ = ['Sunfury', 'Voidforged', 'Magister\'s', 'Blood Knight\'s', 'Dawnbringer', 'Eclipsed', 'Phoenix', 'Felscarred', 'Starlit', 'Duskwarden']
const DROP_NOUN: Record<string, string[]> = {
  head: ['Helm', 'Crown', 'Faceguard'], neck: ['Pendant', 'Choker', 'Amulet'], shoulder: ['Pauldrons', 'Spaulders', 'Mantle'], back: ['Cloak', 'Drape', 'Shroud'],
  chest: ['Breastplate', 'Chestguard', 'Cuirass'], wrist: ['Bracers', 'Vambraces', 'Wristguards'], hands: ['Gauntlets', 'Handguards', 'Grips'], waist: ['Girdle', 'Belt', 'Waistguard'],
  legs: ['Legplates', 'Greaves', 'Legguards'], feet: ['Sabatons', 'Warboots', 'Stompers'], finger: ['Band', 'Ring', 'Seal', 'Loop'], trinket: ['Idol', 'Reliquary', 'Talisman', 'Sigil'],
  main_hand: ['Cleaver', 'Warblade', 'Edge'], off_hand: ['Sidearm', 'Fang', 'Razor'],
}
const SECS: [string, string][] = [['crit', 'haste'], ['haste', 'mastery'], ['crit', 'mastery'], ['haste', 'versatility'], ['crit', 'versatility'], ['mastery', 'versatility']]

/** Your equipped catalyst-slot items catalyzed at a chosen track/rank (API.md's `sources +=
 * { type: "catalyst" }`) — a droptimizer "source" of its own, not tied to any external drop. */
function catalystSourceRows(id: string, track: string, rank: number | undefined): ResultRow[] {
  const r = rng(hash(id) ^ 0x43617461)
  const rows: ResultRow[] = []
  const known = (Object.keys(UPGRADE_TRACKS) as TrackName[]).includes(track as TrackName) ? UPGRADE_TRACKS[track as TrackName] : null
  const ilevel = known ? ilevelAtRank(track as TrackName, Math.max(1, Math.min(rank ?? known.maxRank, known.maxRank))) : 678
  for (const slot of CATALYST_SLOTS) {
    const current = EQUIPPED[slot]
    if (!current) continue
    const twin = catalystTwin({ ...current, key: `equipped:${slot}`, ilevel })
    const gain = (ilevel - current.ilevel) * 0.0011 + 0.0018 + (r() - 0.5) * 0.001
    const dps = BASE_DPS * (1 + gain)
    rows.push({
      name: `catalyst_src_${slot}`, label: `${twin.name} (${track}${rank ? ` ${rank}` : ''})`, dps, dps_error: dps * 0.0028,
      delta: dps - BASE_DPS, delta_pct: gain * 100,
      meta: { item: twin, source: { type: 'catalyst', name: 'Catalyzed' }, changes: { [slot]: twin } },
    })
  }
  return rows
}

type DroptimizerVariantOpts = { includeCatalyst?: boolean; addSocket?: boolean; preferredGem?: number; catalystSource?: { track: string; rank?: number } }

function droptimizerRows(id: string, sourcesCount: number, minIlevel?: number | null, opts: DroptimizerVariantOpts = {}): ResultRow[] {
  const r = rng(hash(id) ^ 0x9e3779b9)
  const rows: ResultRow[] = []
  const slots = ['head', 'neck', 'shoulder', 'back', 'chest', 'wrist', 'hands', 'waist', 'legs', 'feet', 'finger', 'trinket', 'main_hand', 'off_hand']
  let n = 0
  const push = (source: ItemSource, ilevel: number, seedId: number) => {
    if (minIlevel != null && ilevel < minIlevel) return   // mirrors the backend: dropped before it's ever "simmed"
    const slot = slots[Math.floor(r() * slots.length)]
    const adj = DROP_ADJ[Math.floor(r() * DROP_ADJ.length)]
    const nouns = DROP_NOUN[slot]
    const name = `${adj} ${nouns[Math.floor(r() * nouns.length)]}`
    const sec = SECS[Math.floor(r() * SECS.length)]
    const item = mkItem(`drop:${seedId}:${ilevel}`, { id: seedId, name, slot, inv: 0, ilevel, icon: DROP_ICONS[slot], gems: slot === 'finger' || slot === 'neck' ? [] : undefined }, source, sec)
    const eqSlot = slot === 'finger' ? 'finger2' : slot === 'trinket' ? 'trinket2' : slot
    const current = EQUIPPED[eqSlot]?.ilevel ?? 670
    const gain = (ilevel - current) * 0.0012 + (r() - 0.55) * 0.012 + (sec[0] === 'haste' || sec[1] === 'haste' ? 0.003 : 0)
    const dps = BASE_DPS * (1 + gain)
    rows.push({
      name: `drop_${seedId}`, label: name, dps, dps_error: dps * 0.0028, delta: dps - BASE_DPS, delta_pct: gain * 100,
      meta: { item, source, changes: { [eqSlot]: { ...item, slot: eqSlot } } },
    })
    n++
    // Every drop in a catalyst slot also gets its catalyzed twin (source "catalyst", API.md).
    if (opts.includeCatalyst && catalystEligible(slot)) {
      const catItem = catalystTwin(item)
      const catGain = gain + 0.0015
      const catDps = BASE_DPS * (1 + catGain)
      rows.push({
        name: `drop_${seedId}_catalyst`, label: `${name} (Catalyst)`, dps: catDps, dps_error: catDps * 0.0028,
        delta: catDps - BASE_DPS, delta_pct: catGain * 100,
        meta: { item: catItem, source: { type: 'catalyst', name: 'Catalyzed' }, changes: { [eqSlot]: { ...catItem, slot: eqSlot } } },
      })
    }
    // Drops in vault_slots/Jewelbinder slots also get an added-socket twin.
    if (opts.addSocket && socketEligible(slot)) {
      const sockItem = socketTwin(item, opts.preferredGem)
      const sockGain = gain + 0.0009
      const sockDps = BASE_DPS * (1 + sockGain)
      rows.push({
        name: `drop_${seedId}_socket`, label: `${name} (+socket)`, dps: sockDps, dps_error: sockDps * 0.0028,
        delta: sockDps - BASE_DPS, delta_pct: sockGain * 100,
        meta: { item: sockItem, source, changes: { [eqSlot]: { ...sockItem, slot: eqSlot } } },
      })
    }
  }
  let seed = 240000
  const diffs = ['Normal', 'Heroic', 'Mythic']
  for (const boss of RAID_BOSSES) {
    const diff = diffs[Math.min(2, Math.floor(sourcesCount / 2))] ?? 'Heroic'
    const il = diff === 'Mythic' ? 691 : diff === 'Heroic' ? 678 : 665
    for (let i = 0; i < 6; i++) push({ type: 'raid', name: RAID, boss, difficulty: diff }, il + (i % 2 && boss.includes('Kil') ? 6 : 0), seed++)
  }
  for (const d of DUNGEONS) for (let i = 0; i < 7; i++) push({ type: 'dungeon', name: d, key_level: 10 }, 678, seed++)
  for (let i = 0; i < 6; i++) push({ type: 'world_boss', name: 'Oronok, Voidbound Colossus' }, 665, seed++)
  for (let i = 0; i < 6; i++) push({ type: 'delve', name: 'Bountiful Delve', difficulty: 'Tier 8' }, 678, seed++)
  for (let c = 0; c < 4; c++) push({ type: 'crafted', name: 'Crafted (Blacksmithing)' }, 684, seed++)
  // Bounded by attempts (not just `n < 120`): a high minIlevel can filter out every fixed-ilevel
  // pull above, and this loop's own ilevel (678) may itself be below the threshold.
  for (let attempts = 0; n < 120 && attempts < 400; attempts++) {
    push({ type: 'raid', name: RAID, boss: RAID_BOSSES[attempts % RAID_BOSSES.length], difficulty: 'Heroic' }, 678, seed++)
  }
  if (opts.catalystSource) rows.push(...catalystSourceRows(id, opts.catalystSource.track, opts.catalystSource.rank))
  rows.sort((a, b) => b.dps - a.dps)
  return rows.slice(0, 120)
}

/** SimResult.groups — rolls droptimizer rows up by drop source (boss/dungeon/delve/world_boss/
 * crafted) per API.md: best = max delta in the group, ev = mean(max(0, delta)) assuming equal
 * drop odds, upgrade_share = fraction of items that were an upgrade at all. */
function buildDroptimizerGroups(rows: ResultRow[], baselineDps: number): ResultGroup[] {
  type Bucket = { kind: ResultGroup['kind']; label: string; items: ResultRow[] }
  const buckets = new Map<string, Bucket>()
  for (const row of rows) {
    const src = row.meta.source ?? row.meta.item?.source
    if (!src) continue
    const kind: ResultGroup['kind'] | null =
      src.type === 'raid' ? 'boss' : src.type === 'dungeon' ? 'dungeon' : src.type === 'delve' ? 'delve'
        : src.type === 'world_boss' ? 'world_boss' : src.type === 'crafted' ? 'crafted' : src.type === 'catalyst' ? 'catalyst' : null
    if (!kind) continue
    // Matches DroptimizerPage's groupKeyForRow exactly (kind:label key), which for every kind but
    // "boss" uses the source's own name — "catalyst" sources are all named "Catalyzed" (see
    // catalystTwin/catalystSourceRows), so this naturally collapses into a single group row.
    const label = kind === 'boss' ? (src.boss ?? src.name) : src.name
    const key = `${kind}:${label}`
    if (!buckets.has(key)) buckets.set(key, { kind, label, items: [] })
    buckets.get(key)!.items.push(row)
  }
  const groups: ResultGroup[] = []
  for (const [key, b] of buckets) {
    const deltas = b.items.map((row) => row.delta)
    const best = Math.max(...deltas)
    const bestRow = b.items.find((row) => row.delta === best) ?? b.items[0]
    const ev = deltas.reduce((a, d) => a + Math.max(0, d), 0) / deltas.length
    groups.push({
      key, label: b.label, kind: b.kind, n: b.items.length,
      best, best_pct: (best / baselineDps) * 100, best_label: bestRow.label,
      ev, ev_pct: (ev / baselineDps) * 100, upgrade_share: deltas.filter((d) => d > 0).length / deltas.length,
    })
  }
  groups.sort((a, b) => b.best - a.best)
  return groups
}

// ---------- jobs ----------
type Runner = { job: Job; listeners: Set<JobListener>; result?: SimResult; timer?: ReturnType<typeof setInterval>; input: string }
const jobs = new Map<string, Runner>()
let jobSeq = 41
// Exported so mockCharacters.ts's Testhunter fixtures can push a couple of history rows that
// upgrades-section sim refs / the report footer can link to.
export const history: HistoryEntry[] = [
  { id: 'a8f31c2e', type: 'topgear', character: 'Frostbyte', spec: 'frost', created: '2026-09-20T21:14:00Z', summary: 'Best: Sunfury Signet + Chalice of Whispered Ruin (+2.41%)' },
  { id: 'b17e9d04', type: 'droptimizer', character: 'Frostbyte', spec: 'frost', created: '2026-09-19T18:02:00Z', summary: 'March on Quel\'Danas Heroic, 48 drops; best +1.92%' },
  { id: 'c9d02a11', type: 'quick', character: 'Frostbyte', spec: 'frost', created: '2026-09-18T09:30:00Z', summary: '2,398,114 DPS ± 0.1%' },
  { id: 'd44b7e90', type: 'statweights', character: 'Frostbyte', spec: 'frost', created: '2026-09-15T22:47:00Z', summary: 'Str 1.00 > Haste 0.74 > Crit 0.67 > Mast 0.59 > Vers 0.55' },
  { id: 'e3ab1f7c', type: 'quick', character: 'Grimreaver', spec: 'unholy', created: '2026-09-12T17:11:00Z', summary: '2,301,552 DPS ± 0.1%' },
  // Jobs with no character/spec/dates (simc_install, data_refresh, advanced without a named actor)
  // — demonstrates the HistoryPage null-field guard fix; see API.md Job.character/spec ("?").
  { id: 'f501c8aa', type: 'data_refresh', character: null, spec: null, created: null, summary: 'Refreshed game data for build 12.1.0.69933' },
  { id: 'a02de771', type: 'simc_install', character: null, spec: null, created: '2026-09-10T08:00:00Z', summary: 'Installed nightly-2026-09-10' },
]
// Testhunter's two jobs so the report footer's sim_refs / the upgrades section's sim chips resolve to
// a real (reopenable) history row.
history.unshift(...TESTHUNTER_EXTRA_HISTORY)

// ---------- Characters, Advisor, Reports (see API.md) ----------
// Every successful import "saves" the profile server-side (API.md "Characters"); the mock mirrors
// that with these two plain, mutable collections instead of a real characters/ directory.
const FROSTBYTE_SLUG = characterSlug(PROFILE.name, PROFILE.realm)
const CHARACTER_PROFILES: Record<string, CharacterProfile> = {
  [FROSTBYTE_SLUG]: PROFILE,
  [TESTHUNTER_SLUG]: TESTHUNTER_PROFILE,
}
const CHARACTER_SUMMARIES: CharacterSummary[] = [
  characterSummaryFromProfile(PROFILE, FROSTBYTE_SLUG),
  TESTHUNTER_SUMMARY,
]
// Only Testhunter has a report fixture — Frostbyte deliberately has none, so the Reports index page has
// a real "no report yet" greyed-out card to demonstrate.
const REPORTS: Record<string, CharacterReport> = { [TESTHUNTER_SLUG]: TESTHUNTER_REPORT }
const REPORT_LIST: ReportListEntry[] = [TESTHUNTER_REPORT_LIST_ENTRY]

/** Saves (or updates) a character in the mock's characters/ stand-in — called after every
 * successful importSimc/importArmory, mirroring the real backend's "every import also saves to
 * characters/<slug>.json" behavior (API.md). Returns the slug so callers can report it. */
function upsertCharacter(profile: CharacterProfile): string {
  const slug = characterSlug(profile.name, profile.realm)
  CHARACTER_PROFILES[slug] = profile
  const summary = characterSummaryFromProfile(profile, slug)
  const i = CHARACTER_SUMMARIES.findIndex((c) => c.slug === slug)
  if (i >= 0) CHARACTER_SUMMARIES[i] = summary
  else CHARACTER_SUMMARIES.push(summary)
  return slug
}

function newJob(type: JobType, character?: string, spec?: string): Job {
  const id = `${(jobSeq++).toString(16).padStart(4, '0')}${hash(String(Date.now())).toString(16).slice(0, 4)}`
  return { id, type, status: 'queued', progress: { phase: 'queued', current: 0, total: 0, pct: 0, message: 'Waiting for worker' }, character, spec, created: new Date().toISOString() }
}

function startJob(type: JobType, totalUnits: number, unitsPerTick: number, build: (id: string) => SimResult | undefined, input = '', character = PROFILE.name, spec = PROFILE.spec): Job {
  const job = newJob(type, character, spec)
  const runner: Runner = { job, listeners: new Set(), input }
  jobs.set(job.id, runner)
  const emit = () => runner.listeners.forEach((l) => l({ ...runner.job, progress: { ...runner.job.progress } }))
  const phases = type === 'simc_install'
    ? ['downloading', 'extracting', 'verifying']
    : type === 'data_refresh' ? ['downloading', 'indexing'] : ['generating input', 'simulating', 'parsing results']
  let tick = 0
  setTimeout(() => {
    runner.job.status = 'running'
    runner.job.started = new Date().toISOString()
    runner.job.progress = { phase: phases[0], current: 0, total: totalUnits, pct: 0, message: type === 'simc_install' ? 'simc-windows-x64.zip' : 'Writing profile' }
    emit()
    runner.timer = setInterval(() => {
      tick++
      const cur = Math.min(totalUnits, tick * unitsPerTick)
      const pct = (cur / totalUnits) * 100
      const phase = pct < 8 ? phases[0] : pct < 96 ? phases[1] : phases[phases.length - 1]
      const msg = phase === 'simulating' ? `${cur.toLocaleString()} / ${totalUnits.toLocaleString()} ${type === 'quick' || type === 'advanced' || type === 'statweights' ? 'iterations' : 'profilesets'}` : phase
      runner.job.progress = { phase, current: cur, total: totalUnits, pct, message: msg }
      if (cur >= totalUnits) {
        clearInterval(runner.timer)
        runner.job.status = 'done'
        runner.job.finished = new Date().toISOString()
        runner.job.progress = { phase: 'done', current: totalUnits, total: totalUnits, pct: 100, message: 'Complete' }
        const res = build(job.id)
        if (res) {
          res.timing.seconds = (Date.now() - new Date(runner.job.started!).getTime()) / 1000
          runner.result = res
          const summary = res.results.length
            ? `${res.results.length} results; best ${res.results[0].label} (${res.results[0].delta_pct >= 0 ? '+' : ''}${res.results[0].delta_pct.toFixed(2)}%)`
            : `${Math.round(res.baseline.dps).toLocaleString()} DPS`
          history.unshift({ id: job.id, type, character: res.character, spec: res.spec, created: runner.job.created, summary })
        }
      }
      emit()
    }, 200)
  }, 400)
  return { ...job }
}

/** Mimics toonopt.surrogate.model.train's epoch/val_mae progress callback, ~3s total. */
function startSurrogateTrainJob(klass: string, spec: string): Job {
  const job = newJob('surrogate_train', klass, spec)
  const runner: Runner = { job, listeners: new Set(), input: '' }
  jobs.set(job.id, runner)
  const emit = () => runner.listeners.forEach((l) => l({ ...runner.job, progress: { ...runner.job.progress } }))
  const totalEpochs = 12
  const r = rng(hash(`${klass}:${spec}:${job.id}`))
  let tick = 0
  setTimeout(() => {
    runner.job.status = 'running'
    runner.job.started = new Date().toISOString()
    runner.job.progress = { phase: 'loading dataset', current: 0, total: totalEpochs, pct: 0, message: 'Collecting training samples from history' }
    emit()
    runner.timer = setInterval(() => {
      tick++
      const epoch = Math.min(totalEpochs, tick)
      const pct = (epoch / totalEpochs) * 100
      const valMae = Math.max(3.8, 9 - epoch * 0.45 + (r() - 0.5) * 0.2)
      runner.job.progress = { phase: 'training', current: epoch, total: totalEpochs, pct, message: `epoch ${epoch}/${totalEpochs} val_mae=${valMae.toFixed(2)}%` }
      if (epoch >= totalEpochs) {
        clearInterval(runner.timer)
        runner.job.status = 'done'
        runner.job.finished = new Date().toISOString()
        runner.job.progress = { phase: 'done', current: totalEpochs, total: totalEpochs, pct: 100, message: 'Complete' }
        const samples = 300 + Math.round(r() * 200)
        const valMaePct = Number((3.8 + r() * 0.4).toFixed(2))
        upsertSurrogateModel({ klass, spec, samples, val_mae_pct: valMaePct, trained_at: new Date().toISOString() })
      }
      emit()
    }, 250)
  }, 300)
  return { ...job }
}

// ---------- static data ----------
const STATUS: Status = {
  simc: { installed: true, tag: 'nightly-2026-09-14', path: 'runtime/simc/nightly-2026-09-14/simc.exe', version_string: 'SimulationCraft 1210-01 for World of Warcraft 12.1.0.69875 Live', wow_version: '12.1.0.69875', latest_tag: 'nightly-2026-09-21', update_available: true },
  data: { build: '12.1.0.69875', cached_tables: ['ItemSparse', 'ItemBonus', 'ItemEffect', 'JournalEncounter', 'JournalEncounterItem', 'JournalInstance', 'SpellItemEnchantment', 'ItemSet', 'RandPropPoints'], ready: true, refreshed_at: '2026-09-17T06:40:00Z' },
  gpu: { available: true, name: 'NVIDIA GeForce RTX 4090' },
  threads: 24,
  wow_build: '12.1.0.69875',
  mismatch: { simc: false, data: false, simc_wow_version: '12.1.0.69875', data_build: '12.1.0.69875', game_build: '12.1.0.69875' },
}
// A second variant with a fresh patch: SimC and the data cache both still target the old build.
// Not wired up by default -- swap STATUS below for STATUS_PATCHED to preview the warning banner.
export const STATUS_PATCHED: Status = {
  ...STATUS,
  wow_build: '12.1.1.70102',
  simc: { ...STATUS.simc, wow_version: '12.1.0.69875', update_available: true },
  data: { ...STATUS.data, build: '12.1.0.69875' },
  mismatch: { simc: true, data: true, simc_wow_version: '12.1.0.69875', data_build: '12.1.0.69875', game_build: '12.1.1.70102' },
}
let SETTINGS: Settings = {
  port: 8790, threads: 24, profileset_work_threads: 4, default_iterations: 10000, default_target_error: 0.1, profileset_target_error: 0.3,
  wow_dir: 'C:\\Games\\World of Warcraft', wow_build: '12.1.0.69875', wow_build_override: '', simc_tag: 'nightly-2026-09-14', region: 'us', ptr: false,
}
let SURROGATE_STATUS: SurrogateStatus = {
  available: true,
  device: 'cuda',
  models: [
    { klass: 'death_knight', spec: 'frost', samples: 360, val_mae_pct: 3.8, trained_at: '2026-09-18T04:22:00Z' },
  ],
}
function upsertSurrogateModel(model: SurrogateModel): void {
  SURROGATE_STATUS = {
    ...SURROGATE_STATUS,
    models: [...SURROGATE_STATUS.models.filter((m) => !(m.klass === model.klass && m.spec === model.spec)), model],
  }
}
const LOOT: LootSources = {
  raids: [
    {
      instance_id: 1302, name: RAID,
      difficulties: [{ name: 'lfr', ilevel: 652 }, { name: 'normal', ilevel: 665 }, { name: 'heroic', ilevel: 678 }, { name: 'mythic', ilevel: 691 }],
      bosses: RAID_BOSSES.map((name, i) => ({ encounter_id: 3100 + i, name, order: i })),
    },
    {
      instance_id: 1273, name: 'Nerub-ar Palace (Legacy)',
      difficulties: [{ name: 'lfr', ilevel: 597 }, { name: 'normal', ilevel: 610 }, { name: 'heroic', ilevel: 623 }, { name: 'mythic', ilevel: 636 }],
      bosses: ['Ulgrax the Devourer', 'The Bloodbound Horror', 'Sikran', 'Rasha\'nan', 'Broodtwister Ovi\'nax', 'Nexus-Princess Ky\'veza', 'The Silken Court', 'Queen Ansurek'].map((name, i) => ({ encounter_id: 2900 + i, name, order: i })),
    },
  ],
  dungeons: DUNGEONS.map((name, i) => ({ instance_id: 1400 + i, name })),
  key_levels: [{ level: 0, ilevel: 655 }, ...[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15].map((level) => ({ level, ilevel: Math.min(684, 658 + level * 2) })), { level: -1, ilevel: 691 }],
  world_bosses: [{ name: 'Oronok, Voidbound Colossus', ilevel: 665 }],
  delves: [4, 5, 6, 7, 8, 9, 10, 11].map((tier) => ({ tier, ilevel: 640 + tier * 4 })),
  crafted: { ilevels: [665, 671, 678, 684, 691], stats: ['crit', 'haste', 'mastery', 'versatility'] },
}

// ---------- recommendations (gems, enchants) — GET /api/data/recommendations ----------
const GEM_HASTE: GemRef = { id: 213743, name: 'Sundered Onyx', icon: 'inv_jewelcrafting_gem_haste_uncommon', stat: 'haste' }
const GEM_CRIT: GemRef = { id: 213746, name: 'Fractured Onyx', icon: 'inv_jewelcrafting_gem_crit_uncommon', stat: 'crit' }
const GEM_MASTERY: GemRef = { id: 213747, name: 'Zircon Onyx', icon: 'inv_jewelcrafting_gem_mastery_uncommon', stat: 'mastery' }
const GEM_VERS: GemRef = { id: 213748, name: 'Sequenced Onyx', icon: 'inv_jewelcrafting_gem_versatility_uncommon', stat: 'versatility' }
const GEM_UNIQUE: GemRef = { id: 213749, name: 'Ember of Nazjar', icon: 'inv_jewelcrafting_gem_epic_purple', stat: 'versatility', limit: 1 }
const GEM_POOL_ALL: GemRef[] = [GEM_HASTE, GEM_CRIT, GEM_MASTERY, GEM_VERS, GEM_UNIQUE]

function enchantOpt(id: number, name: string, stat: string, recommended: boolean, icon = 'inv_enchant_essenceeternallarge'): EnchantRef {
  return { id, name, icon, stat, recommended }
}

// Two slots (chest, rings) deliberately have a *better* option than what's currently equipped so
// the Gems & Enchants page and the enchant_all tooltip both have something to demonstrate.
export const RECOMMENDATIONS: Recommendations = {
  season: 'Midnight Season 2 (12.1)',
  gems: {
    default: GEM_HASTE,
    by_stat: { crit: GEM_CRIT, haste: GEM_HASTE, mastery: GEM_MASTERY, versatility: GEM_VERS },
    unique: [GEM_UNIQUE],
  },
  enchants: {
    back: [enchantOpt(7409, 'Chant of Winged Grace', 'avoidance', true), enchantOpt(7411, 'Chant of Armored Leech', 'leech', false)],
    chest: [enchantOpt(7365, 'Enchant Chest - Crystalline Radiance', 'versatility', true), enchantOpt(7364, 'Enchant Chest - Waking Stats', 'haste', false)],
    wrist: [enchantOpt(7385, 'Enchant Bracer - Devotion of Haste', 'haste', true), enchantOpt(7386, 'Enchant Bracer - Devotion of Mastery', 'mastery', false)],
    legs: [enchantOpt(7601, 'Stormbound Armor Kit', 'haste', true), enchantOpt(7602, 'Frosted Armor Kit', 'crit', false)],
    feet: [enchantOpt(7418, "Enchant Boots - Scout's March", 'haste', true), enchantOpt(7419, "Enchant Boots - Cavalry's March", 'versatility', false)],
    finger1: [enchantOpt(7341, 'Enchant Ring - Radiant Haste', 'haste', true), enchantOpt(7340, 'Enchant Ring - Radiant Critical Strike', 'crit', false)],
    finger2: [enchantOpt(7341, 'Enchant Ring - Radiant Haste', 'haste', true), enchantOpt(7340, 'Enchant Ring - Radiant Critical Strike', 'crit', false)],
    main_hand: [enchantOpt(7448, 'Enchant Weapon - Authority of Radiant Power', 'haste', true), enchantOpt(7449, 'Enchant Weapon - Authority of Fiery Weapon', 'crit', false)],
    off_hand: [enchantOpt(7448, 'Enchant Weapon - Authority of Radiant Power', 'haste', true), enchantOpt(7449, 'Enchant Weapon - Authority of Fiery Weapon', 'crit', false)],
  },
  // The recommended pick per category for the mock's death_knight/frost profile — one of
  // CONSUMABLE_OPTION_VALUES below (a real fixture value, not defaultOptions()'s empty fallback,
  // so "Season defaults" and a fresh import have something to demonstrate in mock mode).
  consumables: {
    flask: 'flask_of_alchemical_chaos_3',
    food: 'feast_of_the_divine_day',
    potion: 'tempered_potion_3',
    augmentation: 'crystallized',
    temporary_enchant: 'main_hand:algari_mana_oil_3',
  },
  catalyst: { charges_currency_id: 3465, slots: ['head', 'shoulder', 'chest', 'hands', 'legs'] },
  omnium: { rows: [] }, // filled below once OMNIUM_ROWS is defined (RECOMMENDATIONS.omnium = { rows: OMNIUM_ROWS })
}

// ---------- wave 2: catalyst, sockets, voidforge, crafted, Omnium Folio, consumable options ----------
/** Slots this season's tier catalyst can convert into (matches the DK fixture's tier pieces:
 * head/shoulder/chest/hands/legs). */
const CATALYST_SLOTS = ['head', 'shoulder', 'chest', 'hands', 'legs']
/** Vault-socket-eligible slots (head/wrist/waist) + Jewelbinder-socket-eligible slots (neck/rings). */
const SOCKET_VAULT_SLOTS = ['head', 'wrist', 'waist']
const SOCKET_JEWEL_SLOTS = ['neck', 'finger1', 'finger2']
/** Slots where a Myth-max item can be Voidforged this season — main hand is the fixture's demo case. */
const VOIDFORGE_SLOTS = ['main_hand', 'off_hand', 'trinket1', 'trinket2']
const CRAFTED_STAT_IDS: Record<string, number> = { crit: 32, haste: 36, versatility: 40, mastery: 49 }
const CRAFTED_STAT_BONUS_IDS = [8790, 8791, 8792, 8793, 8794, 8795]
const VOIDFORGE_BONUS_ID = 13848
const MYTH_BONUS_IDS = [12849, 12850, 12851, 12852, 12853, 12854]

const OMNIUM_CHOICE_ICONS = ['spell_holy_surgeoflight', 'spell_fire_felflamering_red', 'spell_nature_lightning', 'spell_shadow_shadowbolt', 'spell_frost_frostbolt02']
function omniumChoice(entry: number, token: string, name: string, icon: string) {
  return { entry_id: entry, token, name, icon }
}
/** TraitTree 1186, 5 rows with 2/3/1/4/3 choices per API.md's wave-2 deliverable. */
const OMNIUM_ROWS: OmniumRow[] = [
  { row: 1, node_id: 118600, choices: [omniumChoice(118601, 'omnium_ember', 'Ember Reserve', OMNIUM_CHOICE_ICONS[1]), omniumChoice(118602, 'omnium_frost', 'Frost Reserve', OMNIUM_CHOICE_ICONS[4])] },
  { row: 2, node_id: 118610, choices: [omniumChoice(118611, 'omnium_focus', 'Focused Casting', OMNIUM_CHOICE_ICONS[0]), omniumChoice(118612, 'omnium_haste', 'Hastened Casting', OMNIUM_CHOICE_ICONS[2]), omniumChoice(118613, 'omnium_crit', 'Precise Casting', OMNIUM_CHOICE_ICONS[3])] },
  { row: 3, node_id: 118620, choices: [omniumChoice(118621, 'omnium_core', 'Omnium Core', OMNIUM_CHOICE_ICONS[0])] },
  { row: 4, node_id: 118630, choices: [omniumChoice(118631, 'omnium_surge', 'Arcane Surge', OMNIUM_CHOICE_ICONS[0]), omniumChoice(118632, 'omnium_bulwark', 'Runic Bulwark', OMNIUM_CHOICE_ICONS[2]), omniumChoice(118633, 'omnium_wild', 'Wildfire', OMNIUM_CHOICE_ICONS[1]), omniumChoice(118634, 'omnium_tide', 'Tidebinder', OMNIUM_CHOICE_ICONS[4])] },
  { row: 5, node_id: 118640, choices: [omniumChoice(118641, 'omnium_echo', 'Resonant Echo', OMNIUM_CHOICE_ICONS[3]), omniumChoice(118642, 'omnium_bloom', 'Void Bloom', OMNIUM_CHOICE_ICONS[4]), omniumChoice(118643, 'omnium_zeal', 'Zealous Rune', OMNIUM_CHOICE_ICONS[0])] },
]
RECOMMENDATIONS.omnium = { rows: OMNIUM_ROWS }

// Raw SimC names per category — kept separate from CONSUMABLE_OPTIONS (the `{value, label}[]`
// shape the real backend sends, see `data/season.py::consumable_options`) so buildConsumablesRows
// below can iterate plain strings while the season() fixture emits the wire shape.
const CONSUMABLE_OPTION_VALUES: Record<ConsumableCategory, string[]> = {
  flask: ['flask_of_alchemical_chaos_3', 'flask_of_tempered_aggression_3', 'flask_of_tempered_mastery_3', 'flask_of_tempered_versatility_3', 'flask_of_tempered_swiftness_3'],
  food: ['feast_of_the_divine_day', 'grilled_wildfowl_breast', 'revenge_served_cold', 'salted_meat_mash'],
  potion: ['tempered_potion_3', 'potion_of_unwavering_focus_3', 'potion_of_the_shocking_disclosure_3'],
  augmentation: ['crystallized', 'diamond_flask'],
  temporary_enchant: ['main_hand:algari_mana_oil_3', 'main_hand:algari_healing_oil_3', 'main_hand:ironclaw_whetstone_3', 'main_hand:witchs_brew_3'],
}
const CONSUMABLE_OPTIONS: ConsumableOptions = Object.fromEntries(
  (Object.entries(CONSUMABLE_OPTION_VALUES) as [ConsumableCategory, string[]][]).map(
    ([cat, values]) => [cat, values.map((value) => ({ value, label: prettifySimcName(value) }))],
  ),
) as ConsumableOptions

function catalystEligible(baseSlot: string): boolean {
  return CATALYST_SLOTS.includes(baseSlot)
}
function socketEligible(slot: string): boolean {
  if (slot === 'finger' || slot === 'finger1' || slot === 'finger2') return true
  return SOCKET_VAULT_SLOTS.includes(slot) || SOCKET_JEWEL_SLOTS.includes(slot)
}
function voidforgeEligible(item: Item): boolean {
  return VOIDFORGE_SLOTS.includes(item.slot) && item.quality >= 4
}

/** "<orig> (Catalyst)" — the tier-set twin of a candidate in a catalyzable slot. Mirrors the
 * `<slot>=,id=<tier item id>,...,redirected_base_stats=<source item id>` shape from API.md, though
 * the mock keeps the source item's own stats for a stable-looking DPS delta. */
function catalystTwin(item: Item): Item {
  return {
    ...item,
    key: `catalyst:${item.key}`,
    name: `${item.name} (Catalyst)`,
    set_id: TIER_SET,
    source: { type: 'catalyst', name: 'Catalyzed' },
    simc_string: `${item.simc_string},redirected_base_stats=${item.id}`,
  }
}
/** "<orig> (+socket)" — adds bonus id 1808 and fills the new socket with `gemId` (or the season
 * default gem). */
function socketTwin(item: Item, gemId?: number): Item {
  const g = gemId ?? RECOMMENDATIONS.gems.default.id
  const n = (item.sockets ?? item.gem_ids.length) + 1
  return {
    ...item,
    key: `socket:${item.key}`,
    name: `${item.name} (+socket)`,
    sockets: n,
    gem_ids: [...item.gem_ids, g],
    bonus_ids: [...item.bonus_ids, 1808],
  }
}
/** "<orig> (Voidforged)" — swaps the Myth track bonus for 13848 (ilvl 344 per API.md; the mock
 * bumps the fixture's own ilevel instead so the DPS delta stays visible at this profile's scale). */
function voidforgeTwin(item: Item): Item {
  return {
    ...item,
    key: `voidforge:${item.key}`,
    name: `${item.name} (Voidforged)`,
    ilevel: item.ilevel + 6,
    bonus_ids: [...item.bonus_ids.filter((b) => !MYTH_BONUS_IDS.includes(b)), VOIDFORGE_BONUS_ID],
  }
}
/** "<orig> (recraft Stat1/Stat2)" — strips the old crafted_stats override bonus ids and sets new
 * ones, optionally swapping the embellishment and/or bumping to max quality. */
function craftedTwin(item: Item, stats: [string, string], embellishmentId?: number, maxQuality?: boolean): Item {
  const ids = [CRAFTED_STAT_IDS[stats[0]] ?? 32, CRAFTED_STAT_IDS[stats[1]] ?? 36]
  const bonus = item.bonus_ids.filter((b) => !CRAFTED_STAT_BONUS_IDS.includes(b) && b !== 8960)
  if (embellishmentId) bonus.push(embellishmentId, 8960)
  return {
    ...item,
    key: `crafted:${item.key}`,
    name: `${item.name} (recraft ${titleCase(stats[0])}/${titleCase(stats[1])})`,
    crafted_stats: ids,
    crafting_quality: maxQuality ? 5 : item.crafting_quality,
    bonus_ids: bonus,
  }
}
/** Total equipped tier-set pieces after applying a Top Gear combo's picks — backs the
 * "Minimum set pieces" filter (0/2/4). */
function countSetPieces(picks: Item[]): number {
  const merged: Record<string, Item> = { ...EQUIPPED }
  for (const p of picks) merged[p.slot] = p
  return Object.values(merged).filter((i) => i.set_id === TIER_SET).length
}

// ---------- upgrades (crest tracks) — POST /api/sims/upgrades ----------
type TrackName = 'Veteran' | 'Champion' | 'Hero' | 'Myth'
// baseIlevel/ilevelPerRank tuned so the fixture's 672-678 equipped gear spans two tracks
// (mostly Hero, with a few pieces already into Myth) -- see API.md's Hero/Myth example label.
const UPGRADE_TRACKS: Record<TrackName, { maxRank: number; crest: string; costPerRank: number; ilevelPerRank: number; baseIlevel: number }> = {
  Veteran: { maxRank: 8, crest: 'Weathered', costPerRank: 10, ilevelPerRank: 3, baseIlevel: 597 },
  Champion: { maxRank: 8, crest: 'Carved', costPerRank: 15, ilevelPerRank: 3, baseIlevel: 623 },
  Hero: { maxRank: 7, crest: 'Runed', costPerRank: 15, ilevelPerRank: 4, baseIlevel: 652 },
  Myth: { maxRank: 6, crest: 'Gilded', costPerRank: 20, ilevelPerRank: 3, baseIlevel: 678 },
}
// Crafted gear (wrist/waist in this fixture) upgrades on its own quality track, not a crest track,
// so it's left out of the candidate slot list -- mirrors the backend skipping items with no
// recognised track (see API.md "Upgrades").
const UPGRADE_SLOTS = ['head', 'neck', 'shoulder', 'back', 'chest', 'hands', 'legs', 'feet', 'finger1', 'finger2', 'trinket1', 'trinket2', 'main_hand', 'off_hand']

function trackForIlevel(ilevel: number): { track: TrackName; rank: number } {
  const order: TrackName[] = ['Myth', 'Hero', 'Champion', 'Veteran']
  for (const t of order) {
    const cfg = UPGRADE_TRACKS[t]
    if (ilevel >= cfg.baseIlevel) {
      const rank = Math.min(cfg.maxRank, Math.max(1, Math.floor((ilevel - cfg.baseIlevel) / cfg.ilevelPerRank) + 1))
      return { track: t, rank }
    }
  }
  return { track: 'Veteran', rank: 1 }
}

function ilevelAtRank(track: TrackName, rank: number): number {
  const cfg = UPGRADE_TRACKS[track]
  return cfg.baseIlevel + (rank - 1) * cfg.ilevelPerRank
}

// ---------- item search — GET /api/data/items/search & /api/data/items/{id}?track=&rank= ----------
// Every entry's name contains "band" (case-insensitive) so the fixture demonstrates the search
// flow end to end: typing "band" returns all ten, spanning several slots.
const SEARCH_CATALOG: (ItemSearchResult & { icon: string })[] = [
  { id: 250001, name: 'Band of Ceaseless Whispers', icon: 'inv_70_dungeon_ring2c', quality: 4, inventory_type: 11, slot: 'finger', base_ilevel: 675 },
  { id: 250002, name: 'Sunfury Signet Band', icon: 'inv_jewelry_ring_43', quality: 4, inventory_type: 11, slot: 'finger', base_ilevel: 678 },
  { id: 250003, name: "Bandit's Insignia", icon: 'inv_misc_enggizmos_18', quality: 4, inventory_type: 12, slot: 'trinket', base_ilevel: 665, expansion_hint: 'Midnight' },
  { id: 250004, name: 'Bloodbound Wristbands', icon: 'inv_plate_raiddeathknightgoblin_d_01_bracer', quality: 4, inventory_type: 9, slot: 'wrist', base_ilevel: 672 },
  { id: 250005, name: 'Bandolier of the Void', icon: 'inv_plate_raiddeathknightgoblin_d_01_belt', quality: 4, inventory_type: 6, slot: 'waist', base_ilevel: 678 },
  { id: 250006, name: 'Band of Eternal Frost', icon: 'inv_jewelry_ring_82', quality: 3, inventory_type: 11, slot: 'finger', base_ilevel: 610, expansion_hint: 'Legacy' },
  { id: 250007, name: 'Contraband Chain', icon: 'inv_jewelry_necklace_58', quality: 4, inventory_type: 2, slot: 'neck', base_ilevel: 675 },
  { id: 250008, name: 'Bandaged Grips', icon: 'inv_plate_raiddeathknightgoblin_d_01_glove', quality: 4, inventory_type: 10, slot: 'hands', base_ilevel: 665 },
  { id: 250009, name: 'Warband Standard', icon: 'inv_trinket_80_titan01a', quality: 4, inventory_type: 12, slot: 'trinket', base_ilevel: 684 },
  { id: 250010, name: 'Sunwell Bandolier', icon: 'inv_plate_raiddeathknightgoblin_d_01_belt', quality: 4, inventory_type: 6, slot: 'waist', base_ilevel: 691 },
]

/** Resolves an id+track+rank into a full Item, mirroring GET /api/data/items/{id}?track=&rank=.
 * Key is "search:<id>:<bonus>" per API.md. Falls back to a generic stub for ids not in the
 * fixture catalog (e.g. one picked from a different search query). */
function resolveSearchItem(id: number, track: string, rank: number): Item {
  const entry = SEARCH_CATALOG.find((i) => i.id === id)
  const known = (Object.keys(UPGRADE_TRACKS) as TrackName[]).includes(track as TrackName) ? UPGRADE_TRACKS[track as TrackName] : null
  const ilevel = known ? ilevelAtRank(track as TrackName, Math.max(1, Math.min(rank, known.maxRank))) : (entry?.base_ilevel ?? 600) + (Math.max(1, rank) - 1) * 3
  const bonus = [ilevel > 660 ? 10390 : 10353, 1808, Math.round(ilevel / 3)]
  const seed: ItemSeed = {
    id, name: entry?.name ?? `Item ${id}`, slot: entry?.slot ?? 'trinket', inv: entry?.inventory_type ?? 12,
    ilevel, icon: entry?.icon ?? 'inv_misc_questionmark', quality: entry?.quality ?? 4, bonus,
  }
  return mkItem(`search:${id}:${bonus.join('/')}`, seed, { type: 'bag', name: 'Item search' }, ['crit', 'haste'])
}

function buildUpgradeRows(id: string, profile: CharacterProfile, slots: string[] | undefined, maxRanks: number | null | undefined, minIlevel: number | null | undefined): { rows: ResultRow[]; skipped: number; notes: string[] } {
  const r = rng(hash(id) ^ 0x2545f491)
  const rows: ResultRow[] = []
  const skippedSlots: string[] = []
  const currencyByCrest = new Map((profile.currencies ?? []).filter((c) => c.crest).map((c) => [c.crest, c]))
  const knownCurrencies = !!profile.currencies?.length
  const eligible = UPGRADE_SLOTS.filter((slot) => !slots || !slots.length || slots.includes(slot))
  eligible.forEach((slot, idx) => {
    const item = profile.equipped[slot]
    if (!item) return
    if (item.crafting_quality) { skippedSlots.push(slot); return }
    if (minIlevel != null && item.ilevel < minIlevel) return
    const { track, rank: fromRank } = trackForIlevel(item.ilevel)
    const cfg = UPGRADE_TRACKS[track]
    const cap = maxRanks != null && maxRanks > 0 ? Math.min(cfg.maxRank, maxRanks) : cfg.maxRank
    if (fromRank >= cap) {
      // Myth-max weapons/trinkets get a Voidforge step instead of being a dead end (API.md wave 2:
      // "rows for Myth-max weapons/trinkets gain a Voidforge step ... meta.upgrade.track = Voidforged").
      if (track === 'Myth' && fromRank >= cfg.maxRank && voidforgeEligible(item)) {
        const upgraded = voidforgeTwin({ ...item, key: `equipped:${slot}` })
        const gain = Math.max(0.0003, (upgraded.ilevel - item.ilevel) * 0.0011 + 0.0018)
        const dps = BASE_DPS * (1 + gain)
        const step = { rank: fromRank, ilevel: upgraded.ilevel, crest: 'Ascendant Voidcore', cost: 1 }
        rows.push({
          name: `upg_${slot}_voidforge`,
          label: `${SLOT_LABELS[slot] ?? slot}: Voidforge (ilvl ${item.ilevel} → ${upgraded.ilevel})`,
          dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100,
          meta: {
            changes: { [slot]: upgraded },
            upgrade: {
              slot, item_id: item.id, track: 'Voidforged', from_rank: fromRank, to_rank: fromRank, max_rank: cfg.maxRank,
              from_ilevel: item.ilevel, to_ilevel: upgraded.ilevel, crest: step.crest, cost: step.cost, steps: [step], affordable: null,
            },
          },
        })
      } else {
        skippedSlots.push(slot)
      }
      return
    }
    const targets = new Set<number>([fromRank + 1])
    if (cap > fromRank + 1 && (idx % 2 === 0 || r() > 0.5)) targets.add(cap)
    for (const toRank of [...targets].sort((a, b) => a - b)) {
      const steps = []
      for (let rk = fromRank + 1; rk <= toRank; rk++) steps.push({ rank: rk, ilevel: ilevelAtRank(track, rk), crest: cfg.crest, cost: cfg.costPerRank })
      const cost = steps.reduce((a, s) => a + s.cost, 0)
      const fromIlevel = ilevelAtRank(track, fromRank)
      const toIlevel = ilevelAtRank(track, toRank)
      const gain = Math.max(0.0002, (toIlevel - fromIlevel) * 0.0011 + (r() - 0.3) * 0.0012)
      const dps = BASE_DPS * (1 + gain)
      const upgraded: Item = { ...item, ilevel: toIlevel, simc_string: item.simc_string.includes('ilevel=') ? item.simc_string.replace(/ilevel=\d+/, `ilevel=${toIlevel}`) : `${item.simc_string},ilevel=${toIlevel}` }
      const affordable = knownCurrencies ? (currencyByCrest.get(cfg.crest)?.amount ?? 0) >= cost : null
      const upgrade: UpgradeInfo = {
        slot, item_id: item.id, track, from_rank: fromRank, to_rank: toRank, max_rank: cfg.maxRank,
        from_ilevel: fromIlevel, to_ilevel: toIlevel, crest: cfg.crest, cost, steps, affordable,
      }
      rows.push({
        name: `upg_${slot}_${toRank}`,
        label: `${SLOT_LABELS[slot] ?? slot}: ${track} ${fromRank}/${cfg.maxRank} → ${toRank}/${cfg.maxRank} (ilvl ${fromIlevel} → ${toIlevel}, ${cost} ${cfg.crest})`,
        dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100,
        meta: { changes: { [slot]: upgraded }, upgrade },
      })
    }
  })
  rows.sort((a, b) => b.delta_pct - a.delta_pct)
  const notes = skippedSlots.length
    ? [`Skipped ${skippedSlots.length} slot(s) with no remaining upgrade: ${skippedSlots.map((s) => SLOT_LABELS[s] ?? s).join(', ')} (already at max rank or no crest track).`]
    : []
  return { rows, skipped: skippedSlots.length, notes }
}

// ---------- gems & enchants — POST /api/sims/gems ----------
function socketCount(item: Item): number {
  return item.sockets ?? item.gem_ids?.length ?? 0
}
function itemsWithSockets(profile: CharacterProfile): Item[] {
  return Object.values(profile.equipped).filter((i) => socketCount(i) > 0)
}
function gemRefFromPool(id: number): GemRef {
  return GEM_POOL_ALL.find((g) => g.id === id) ?? { id, name: `Gem ${id}`, icon: 'inv_misc_gem_variety_01', stat: 'haste' }
}
function defaultGemPool(): GemRef[] {
  return GEM_POOL_ALL
}
function statWeight(stat: string | undefined): number {
  return (STAT_WEIGHTS.normalized as Record<string, number>)[stat ?? ''] ?? 0.5
}

function buildGemsUniformRows(profile: CharacterProfile, pool: GemRef[], r: () => number): ResultRow[] {
  const items = itemsWithSockets(profile)
  const totalSockets = items.reduce((a, i) => a + socketCount(i), 0)
  const rows: ResultRow[] = []
  for (const gem of pool) {
    const changes: Record<string, Item> = {}
    for (const it of items) changes[it.slot] = { ...it, gem_ids: new Array(socketCount(it)).fill(gem.id) }
    const gain = (totalSockets * 190 * statWeight(gem.stat)) / 150_000 + (r() - 0.5) * 0.0006
    const dps = BASE_DPS * (1 + gain)
    rows.push({ name: `gem_uniform_${gem.id}`, label: gem.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes } })
  }
  const rec = RECOMMENDATIONS.gems.default
  const uniq = RECOMMENDATIONS.gems.unique[0]
  const changes: Record<string, Item> = {}
  let usedUnique = false
  for (const it of items) {
    const n = socketCount(it)
    const ids = new Array(n).fill(rec.id)
    if (uniq && !usedUnique && n > 0) { ids[0] = uniq.id; usedUnique = true }
    changes[it.slot] = { ...it, gem_ids: ids }
  }
  const uniqueSockets = usedUnique ? 1 : 0
  const gain = ((totalSockets - uniqueSockets) * 190 * statWeight(rec.stat) + uniqueSockets * 190 * statWeight(uniq?.stat) * 1.2) / 150_000 + 0.0012
  const dps = BASE_DPS * (1 + gain)
  rows.push({ name: 'gem_uniform_recommended', label: 'Recommended', dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes } })
  return rows
}

function buildGemsPerSocketRows(profile: CharacterProfile, pool: GemRef[], r: () => number): ResultRow[] {
  const items = itemsWithSockets(profile)
  const rows: ResultRow[] = []
  for (const it of items) {
    const n = socketCount(it)
    for (let i = 0; i < n; i++) {
      for (const gem of pool) {
        const gain = (190 * statWeight(gem.stat)) / 150_000 + (r() - 0.5) * 0.00015
        const dps = BASE_DPS * (1 + gain)
        rows.push({
          name: `gem_socket_${it.slot}_${i + 1}_${gem.id}`,
          label: `${SLOT_LABELS[it.slot] ?? it.slot} socket ${i + 1}: ${gem.name}`,
          dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100,
          meta: { gem: { slot: it.slot, socket_index: i + 1, gem_id: gem.id, gem_name: gem.name, stat: gem.stat } },
        })
      }
    }
  }
  return rows
}

function buildGemsCustomRows(profile: CharacterProfile, sets: GemsCustomSet[] | undefined, r: () => number): ResultRow[] {
  const rows: ResultRow[] = []
  for (const set of sets ?? []) {
    const changes: Record<string, Item> = {}
    for (const [slot, gemIds] of Object.entries(set.gems ?? {})) {
      const cur = profile.equipped[slot]
      if (!cur) continue
      changes[slot] = { ...cur, gem_ids: gemIds }
    }
    for (const [slot, enchId] of Object.entries(set.enchants ?? {})) {
      const base = changes[slot] ?? profile.equipped[slot]
      if (!base) continue
      changes[slot] = { ...base, enchant_id: enchId }
    }
    let gain = 0
    for (const [slot, it] of Object.entries(changes)) {
      const cur = profile.equipped[slot]
      const curSet = new Set(cur?.gem_ids ?? [])
      for (const gid of it.gem_ids ?? []) if (!curSet.has(gid)) gain += (190 * statWeight(gemRefFromPool(gid).stat)) / 150_000
      if (it.enchant_id && it.enchant_id !== cur?.enchant_id) gain += 0.0008
    }
    gain += (r() - 0.5) * 0.0015
    const dps = BASE_DPS * (1 + gain)
    rows.push({ name: `gem_custom_${set.name}`, label: set.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes } })
  }
  return rows
}

function buildEnchantRows(profile: CharacterProfile, enchantSlots: string[] | undefined, r: () => number): ResultRow[] {
  const rows: ResultRow[] = []
  for (const [slot, opts] of Object.entries(RECOMMENDATIONS.enchants)) {
    if (enchantSlots && enchantSlots.length && !enchantSlots.includes(slot)) continue
    const current = profile.equipped[slot]
    if (!current) continue
    for (const opt of opts) {
      if (opt.id === current.enchant_id) continue
      const gain = (90 * statWeight(opt.stat)) / 150_000 + (opt.recommended ? 0.0012 : 0) + (r() - 0.5) * 0.0003
      const dps = BASE_DPS * (1 + gain)
      rows.push({
        name: `ench_${slot}_${opt.id}`,
        label: `${SLOT_LABELS[slot] ?? slot}: ${opt.name}`,
        dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100,
        meta: { enchant: { slot, enchant_id: opt.id, name: opt.name, stat: opt.stat } },
      })
    }
  }
  return rows
}

function buildGemsRows(id: string, profile: CharacterProfile, mode: GemsMode, gemPoolIds: number[] | undefined, includeEnchants: boolean | undefined, enchantSlots: string[] | undefined, sets: GemsCustomSet[] | undefined): ResultRow[] {
  const r = rng(hash(id) ^ 0x51ed270b)
  const pool = gemPoolIds && gemPoolIds.length ? gemPoolIds.map(gemRefFromPool) : defaultGemPool()
  let rows: ResultRow[] =
    mode === 'uniform' ? buildGemsUniformRows(profile, pool, r)
    : mode === 'per_socket' ? buildGemsPerSocketRows(profile, pool, r)
    : buildGemsCustomRows(profile, sets, r)
  if (includeEnchants !== false) rows = rows.concat(buildEnchantRows(profile, enchantSlots, r))
  rows.sort((a, b) => b.dps - a.dps)
  return rows.slice(0, 400)
}

// ---------- consumables — POST /api/sims/consumables ----------
function buildConsumablesRows(id: string, categories: ConsumableCategory[] | undefined, custom: ConsumablesCustomSet[] | undefined): ResultRow[] {
  const r = rng(hash(id) ^ 0x636f6e73)
  const cats = categories && categories.length ? categories : (Object.keys(CONSUMABLE_OPTION_VALUES) as ConsumableCategory[])
  const rows: ResultRow[] = []
  for (const cat of cats) {
    const opts = CONSUMABLE_OPTION_VALUES[cat]
    for (const name of opts) {
      const gain = ((hash(name) % 1000) / 1000) * 0.01 + (r() - 0.5) * 0.0008
      const dps = BASE_DPS * (1 + gain)
      rows.push({
        name: `cons_${cat}_${name}`, label: `${CONSUMABLE_CATEGORY_LABELS[cat] ?? cat}: ${prettifySimcName(name)}`,
        dps, dps_error: dps * 0.0025, delta: dps - BASE_DPS, delta_pct: gain * 100,
        meta: { consumable: { category: cat, name } },
      })
    }
    // "None (disabled)" row so the ranked list also shows the cost of skipping this category.
    const noneGain = -0.004 + (r() - 0.5) * 0.0005
    const noneDps = BASE_DPS * (1 + noneGain)
    rows.push({
      name: `cons_${cat}_none`, label: `${CONSUMABLE_CATEGORY_LABELS[cat] ?? cat}: None`, dps: noneDps, dps_error: noneDps * 0.0025,
      delta: noneDps - BASE_DPS, delta_pct: noneGain * 100, meta: { consumable: { category: cat, name: '' } },
    })
  }
  for (const set of custom ?? []) {
    const gain = ((hash(set.name) % 1000) / 1000 - 0.5) * 0.015
    const dps = BASE_DPS * (1 + gain)
    rows.push({ name: `cons_custom_${set.name}`, label: set.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: {} })
  }
  rows.sort((a, b) => b.dps - a.dps)
  return rows
}

// ---------- Omnium Folio — POST /api/sims/omnium ----------
function currentOmniumEntry(profile: CharacterProfile, row: OmniumRow): number {
  const sel = profile.omnium ?? {}
  const picked = row.choices.find((c) => sel[String(c.entry_id)] != null)
  return picked?.entry_id ?? row.choices[0].entry_id
}
function omniumGainFor(entryId: number, r: () => number): number {
  return ((hash(String(entryId)) % 1000) / 1000) * 0.012 + (r() - 0.5) * 0.0006
}
function buildOmniumRows(id: string, profile: CharacterProfile, mode: OmniumMode, sets: OmniumCustomSet[] | undefined): ResultRow[] {
  const r = rng(hash(id) ^ 0x6f6d6e69)
  const rows: ResultRow[] = []
  if (mode === 'per_row') {
    for (const row of OMNIUM_ROWS) {
      const current = currentOmniumEntry(profile, row)
      for (const choice of row.choices) {
        if (choice.entry_id === current) continue
        const gain = omniumGainFor(choice.entry_id, r)
        const dps = BASE_DPS * (1 + gain)
        rows.push({
          name: `omnium_row${row.row}_${choice.entry_id}`, label: `Row ${row.row}: ${choice.name}`,
          dps, dps_error: dps * 0.0025, delta: dps - BASE_DPS, delta_pct: gain * 100,
          meta: { omnium: { row: row.row, entry_id: choice.entry_id, name: choice.name } },
        })
      }
    }
  } else if (mode === 'combos') {
    let combos: OmniumChoice[][] = [[]]
    for (const row of OMNIUM_ROWS) {
      const next: OmniumChoice[][] = []
      for (const combo of combos) for (const choice of row.choices) next.push([...combo, choice])
      combos = next
    }
    for (const combo of combos.slice(0, 72)) {
      const gain = combo.reduce((a, c) => a + omniumGainFor(c.entry_id, r), 0) / combo.length
      const dps = BASE_DPS * (1 + gain)
      rows.push({
        name: `omnium_combo_${combo.map((c) => c.entry_id).join('_')}`, label: combo.map((c) => c.name).join(' + '),
        dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100,
        meta: { loadout: combo.map((c) => c.token).join('/') },
      })
    }
  } else {
    const allChoices = OMNIUM_ROWS.flatMap((row) => row.choices)
    for (const set of sets ?? []) {
      const choices = set.entries.map((eid) => allChoices.find((c) => c.entry_id === eid)).filter((c): c is OmniumChoice => !!c)
      const gain = choices.reduce((a, c) => a + omniumGainFor(c.entry_id, r), 0) / Math.max(1, choices.length)
      const dps = BASE_DPS * (1 + gain)
      rows.push({ name: `omnium_custom_${set.name}`, label: set.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { loadout: set.entries.join('/') } })
    }
  }
  rows.sort((a, b) => b.dps - a.dps)
  return rows
}

function inputFor(profile: CharacterProfile, options: SimOptions, extra = ''): string {
  return [
    profile.simc_header, '', ...Object.values(profile.equipped).map((i) => i.simc_string), '',
    `fight_style=${options.fight_style}`, `max_time=${options.max_time}`, `vary_combat_length=${options.vary_combat_length}`,
    `desired_targets=${options.desired_targets}`, options.iterations ? `iterations=${options.iterations}` : `target_error=${options.target_error}`,
    `threads=${options.threads ?? SETTINGS.threads}`, `optimal_raid=0`,
    ...Object.entries(options.buffs).map(([k, v]) => `override.${k}=${v ? 1 : 0}`),
    ...Object.entries(options.consumables).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`), extra,
  ].join('\n')
}

export const mock: ApiClient = {
  async health() { return { ok: true, version: '0.1.0-mock' } },
  async status() { await sleep(150); return { ...STATUS, threads: SETTINGS.threads } },
  async installSimc(tag) {
    const j = startJob('simc_install', 100, 3, () => undefined, '', undefined, undefined)
    setTimeout(() => { STATUS.simc.tag = tag ?? STATUS.simc.latest_tag; STATUS.simc.update_available = false }, 8000)
    return j
  },
  async refreshData() {
    const j = startJob('data_refresh', 60, 2, () => undefined, '', undefined, undefined)
    setTimeout(() => { STATUS.data.refreshed_at = new Date().toISOString() }, 7000)
    return j
  },
  async season() {
    // Mirrors the real GET /api/data/season shape: upgrade_tracks is an OBJECT keyed by track
    // name (not an array) — see lib/api.ts's normalizeUpgradeTracks, which is what actually turns
    // this into UpgradeTrackDef[] for pages. Emitting the raw shape here (rather than the already
    // -normalized array) exercises that normalizer in mock mode too.
    const upgrade_tracks: Record<string, RawUpgradeTrack> = {}
    for (const name of Object.keys(UPGRADE_TRACKS) as TrackName[]) {
      const cfg = UPGRADE_TRACKS[name]
      const steps = Array.from({ length: cfg.maxRank }, (_, i) => ({ rank: i + 1, ilevel: ilevelAtRank(name, i + 1), bonus_id: 12800 + i }))
      upgrade_tracks[name] = {
        name, max: cfg.maxRank, steps,
        crest: { name: cfg.crest, cost: cfg.costPerRank, discounted_cost: Math.round(cfg.costPerRank / 2) },
        ilevels: steps.map((s) => s.ilevel),
        bonus_ids: steps.map((s) => s.bonus_id),
      }
    }
    return {
      season: 'Midnight Season 1',
      consumables: { ...defaultOptions().consumables, options: CONSUMABLE_OPTIONS },
      upgrade_tracks,
      catalyst: {
        conversion_id: 13, currency_id: 3465, slots: CATALYST_SLOTS,
        set_ids: { death_knight: TIER_SET },
        items: { death_knight: { 1: 237631, 3: 237629, 5: 237634, 10: 237632, 7: 237630 } }, // inventory_type -> tier item id
        set_bonus_spells: { death_knight: { frost: { 2: 1145000, 4: 1145001 } } },
      },
      sockets: {
        add_bonus_id: 1808, two: 8781, three: 8782,
        vault_slots: SOCKET_VAULT_SLOTS, jewelbinder_slots: SOCKET_JEWEL_SLOTS, jewelbinder_item: 263897,
      },
      voidforged: { slots: VOIDFORGE_SLOTS, myth_ilevel: 344, bonus_id: VOIDFORGE_BONUS_ID },
      crafted: {
        stat_ids: CRAFTED_STAT_IDS, stat_bonus_ids: CRAFTED_STAT_BONUS_IDS, quality_bonus_max: 12497,
        embellishments: [
          { id: 8901, name: 'Comprehension of the Chosen', icon: 'inv_enchant_disenchantcrystal' },
          { id: 8933, name: 'Cauldron of Woe', icon: 'inv_alchemy_80_boltoffungus' },
          { id: 8944, name: "Ricochet Lure", icon: 'inv_ability_bossfishing' },
        ],
        embellish_marker: 8960, max_embellished: 2,
      },
      omnium: { tree_id: 1186, rows: OMNIUM_ROWS },
    } as unknown as SeasonData
  },
  async lootSources() { await sleep(200); return LOOT },
  async item(id) { const all = [...BAGS, ...VAULT, ...Object.values(EQUIPPED)]; const f = all.find((i) => i.id === id); if (!f) throw new Error('Item not found'); return f },
  async itemSearch(qStr, _klass, _spec, slot, limit = 25) {
    await sleep(180)
    const needle = qStr.trim().toLowerCase()
    const hits = SEARCH_CATALOG.filter((i) => (!needle || i.name.toLowerCase().includes(needle)) && (!slot || i.slot === slot || (slot === 'finger' && i.slot === 'finger') || (slot === 'trinket' && i.slot === 'trinket')))
    return { items: hits.slice(0, limit).map(({ id, name, icon, quality, inventory_type, slot: s, base_ilevel, expansion_hint }) => ({ id, name, icon, quality, inventory_type, slot: s, base_ilevel, expansion_hint })) }
  },
  async itemByTrack(id, track, rank) {
    await sleep(150)
    return resolveSearchItem(id, track, rank)
  },
  async recommendations() { await sleep(150); return RECOMMENDATIONS },
  async talents() { return { class_tree: [], spec_tree: [], hero_trees: [] } },
  async decodeTalents(_k, _s, loadout): Promise<DecodedTalents> {
    const r = rng(hash(loadout))
    const selected: { node_id: number; rank: number }[] = []
    for (let i = 0; i < 60; i++) if (r() > 0.25) selected.push({ node_id: 96000 + i * 3, rank: r() > 0.8 ? 2 : 1 })
    const name = r() > 0.5 ? 'Deathbringer' : 'Rider of the Apocalypse'
    return { selected, hero_tree: { id: name === 'Deathbringer' ? 1 : 2, name } }
  },
  async importSimc(text) {
    await sleep(500)
    if (!text.trim()) throw new Error('Empty export')
    const m = /^(\w+)="([^"]+)"/m.exec(text)
    const name = m?.[2] ?? PROFILE.name
    const profile = withMockScenario({ ...PROFILE, name, raw: text, imported_at: new Date().toISOString() })
    // Dev-only hooks so VITE_MOCK=1 can exercise store.ts's `syncProfileToServer` (persisted
    // profile vs. server-side characters/<slug>.json) without a real backend: a magic first line
    // in the pasted text simulates the server-side store being behind, or missing, what ends up
    // persisted in this browser — paste it, Import, then reload (or use "Re-sync to server").
    if (/^#\s*mock:no-server-save/m.test(text)) {
      // Simulates a profile that only ever reached this browser's localStorage (e.g. imported
      // before the server-side character store existed) — never save it server-side.
      return profile
    }
    if (/^#\s*mock:stale-server/m.test(text)) {
      // Simulates a server copy that predates this browser's persisted one.
      upsertCharacter({ ...profile, imported_at: '2020-01-01T00:00:00Z' })
      return profile
    }
    upsertCharacter(profile) // every successful import is also saved to characters/<slug>.json (API.md)
    return profile
  },
  // Addon import. Dev hook: open the app with `?addon=empty` (or `?addon=missing`) for the empty states.
  async addonCaptures() {
    await sleep(300)
    const mode = new URLSearchParams(window.location.search).get('addon')
    if (mode === 'missing') return { installed: false, wow_dir: null, wow_dir_valid: false, files: [], captures: [] }
    if (mode === 'empty') return { installed: true, wow_dir: 'C:\\Games\\World of Warcraft', files: [], captures: [] }
    const now = Date.now()
    return {
      installed: true,
      wow_dir: 'C:\\Games\\World of Warcraft',
      files: ['WTF/Account/TESTACCOUNT/SavedVariables/ToonOptimizer.lua'],
      captures: [
        {
          key: 'Testhunter-Testrealm', account: 'TESTACCOUNT', name: 'Testhunter', realm: 'Testrealm', class: 'HUNTER',
          spec: 'Marksmanship', ilvl: 681, captured_at: new Date(now - 12 * 60_000).toISOString(),
          saved_slug: TESTHUNTER_SLUG, saved_imported_at: TESTHUNTER_PROFILE.imported_at, newer_than_saved: true,
        },
        {
          key: 'Testalt-Testrealm', account: 'TESTACCOUNT', name: 'Testalt', realm: 'Testrealm', class: 'MAGE',
          spec: 'Frost', ilvl: 652, captured_at: new Date(now - 3 * 86_400_000).toISOString(),
          saved_slug: characterSlug('Testalt', 'Testrealm'), saved_imported_at: null, newer_than_saved: true,
        },
      ],
    }
  },
  async importAddon(key) {
    await sleep(600)
    const status = await mock.addonCaptures()
    const cap = key ? status.captures.find((c) => c.key === key) : status.captures[0]
    if (!cap) throw new Error('No addon data found for that character')
    const base = cap.name === TESTHUNTER_PROFILE.name ? TESTHUNTER_PROFILE : { ...TESTHUNTER_PROFILE, name: cap.name }
    const profile = withMockScenario({ ...base, source: 'addon' as const, imported_at: new Date().toISOString() })
    upsertCharacter(profile)
    return profile
  },
  async importAddonAll() {
    await sleep(900)
    const status = await mock.addonCaptures()
    if (!status.captures.length) throw new Error('No addon data found')
    const out: AddonImportResult[] = []
    for (const c of status.captures) {
      if (!c.newer_than_saved) { out.push({ key: c.key, status: 'skipped', detail: 'not newer than saved', profile: null }); continue }
      out.push({ key: c.key, status: 'imported', detail: null, profile: await mock.importAddon(c.key) })
    }
    return out
  },
  async importArmory(region, realm, name) {
    await sleep(900)
    if (!name) throw new Error('Character name required')
    const profile = withMockScenario({ ...PROFILE, name: name[0].toUpperCase() + name.slice(1).toLowerCase(), realm, region, imported_at: new Date().toISOString() })
    upsertCharacter(profile)
    return profile
  },
  async quick({ profile, options }) {
    const iters = options.iterations ?? 10000
    return startJob('quick', iters, Math.ceil(iters / 30), (id) => finalizeResult(baseResult(id, 'quick', options)), inputFor(profile, options), profile.name, profile.spec)
  },
  async topgear({ profile, options, candidate_keys, max_combos, smart, min_ilevel, loadouts, extra_items, catalyst, add_socket, voidforge, crafted }) {
    const n = Math.min(max_combos, 40) + 1
    const model = smart ? SURROGATE_STATUS.models.find((m) => m.klass === profile.klass && m.spec === profile.spec) : null
    return startJob(
      'topgear', n, 1,
      (id) => finalizeResult({
        ...baseResult(id, 'topgear', options),
        results: topGearRows(id, candidate_keys, max_combos, model, min_ilevel, extra_items, loadouts, { catalyst, add_socket, voidforge, crafted }),
      }),
      inputFor(profile, options, `# ${candidate_keys.length} candidates${loadouts?.length ? `, ${loadouts.length} loadouts` : ''}`), profile.name, profile.spec,
    )
  },
  async droptimizer({ profile, options, sources, min_ilevel, upgrade_equipped, include_offspec, include_catalyst, add_socket, preferred_gem }) {
    const catalystSrc = sources.find((s): s is Extract<DropSource, { type: 'catalyst' }> => s.type === 'catalyst')
    return startJob('droptimizer', 121, 3, (id) => {
      const rows = droptimizerRows(id, sources.length, min_ilevel, {
        includeCatalyst: include_catalyst, addSocket: add_socket, preferredGem: preferred_gem,
        catalystSource: catalystSrc ? { track: catalystSrc.track, rank: catalystSrc.rank } : undefined,
      })
      const result = finalizeResult({ ...baseResult(id, 'droptimizer', options), results: rows, groups: buildDroptimizerGroups(rows, BASE_DPS) })
      const notes = [...(result.notes ?? [])]
      if (upgrade_equipped && upgrade_equipped !== 'none') notes.push(`Baseline gear upgraded to its ${upgrade_equipped === 'max' ? 'max' : 'drop-matching'} rank along each slot's track before simming drops.`)
      if (include_offspec) notes.push('Off-spec items included as drop candidates.')
      if (include_catalyst) notes.push('Catalyst-slot drops also simmed as their catalyzed (tier) twin.')
      if (add_socket) notes.push('Vault-socket-eligible drops also simmed with an added socket.')
      return { ...result, notes }
    }, inputFor(profile, options, `# ${sources.length} sources`), profile.name, profile.spec)
  },
  async statweights({ profile, options, stats }) {
    return startJob('statweights', 10000 * (stats.length + 1), 1800, (id) => {
      const pick = (o: Record<string, number>) => Object.fromEntries(Object.entries(o).filter(([k]) => stats.includes(k)))
      return finalizeResult({ ...baseResult(id, 'statweights', options), stat_weights: { ...STAT_WEIGHTS, weights: pick(STAT_WEIGHTS.weights), normalized: pick(STAT_WEIGHTS.normalized), error: pick(STAT_WEIGHTS.error) } })
    }, inputFor(profile, options, `calculate_scale_factors=1\nscale_only=${stats.join(',')}`), profile.name, profile.spec)
  },
  async gearcompare({ profile, options, sets }) {
    return startJob('gearcompare', sets.length + 1, 1, (id) => {
      const r = rng(hash(id))
      const rows: ResultRow[] = sets.map((s, i) => {
        const gain = Object.values(s.changes).reduce((a, it) => a + (it.ilevel - (profile.equipped[it.slot]?.ilevel ?? 670)) * 0.0012, 0) + (r() - 0.5) * 0.006
        const dps = BASE_DPS * (1 + gain)
        return { name: `set_${i + 1}`, label: s.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { changes: s.changes, items: Object.values(s.changes) } }
      }).sort((a, b) => b.dps - a.dps)
      return finalizeResult({ ...baseResult(id, 'gearcompare', options), results: rows })
    }, inputFor(profile, options), profile.name, profile.spec)
  },
  async talentcompare({ profile, options, loadouts }) {
    return startJob('talentcompare', loadouts.length + 1, 1, (id) => {
      const rows: ResultRow[] = loadouts.map((l, i) => {
        const gain = ((hash(l.string) % 1000) / 1000 - 0.5) * 0.05
        const dps = BASE_DPS * (1 + gain)
        return { name: `loadout_${i + 1}`, label: l.name, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: { loadout: l.string } }
      }).sort((a, b) => b.dps - a.dps)
      return finalizeResult({ ...baseResult(id, 'talentcompare', options), results: rows })
    }, inputFor(profile, options), profile.name, profile.spec)
  },
  async advanced({ simc_text, options }) {
    const opts = options ?? defaultOptions()
    const sets = [...simc_text.matchAll(/^profileset\."?([^"=.]+)"?/gm)].map((m) => m[1])
    const uniq = [...new Set(sets)]
    return startJob('advanced', 10000, 500, (id) => {
      const rows: ResultRow[] = uniq.map((n) => {
        const gain = ((hash(n) % 1000) / 1000 - 0.5) * 0.04
        const dps = BASE_DPS * (1 + gain)
        return { name: n, label: n, dps, dps_error: dps * 0.003, delta: dps - BASE_DPS, delta_pct: gain * 100, meta: {} }
      }).sort((a, b) => b.dps - a.dps)
      return finalizeResult({ ...baseResult(id, 'advanced', opts), results: rows, character: /^\w+="([^"]+)"/m.exec(simc_text)?.[1] ?? 'Custom', spec: /^spec=(\w+)/m.exec(simc_text)?.[1] ?? '' })
    }, simc_text)
  },
  async runUpgrades({ profile, options, slots, max_ranks, min_ilevel }) {
    return startJob('upgrades', 40, 2, (id) => {
      const { rows, notes } = buildUpgradeRows(id, profile, slots, max_ranks, min_ilevel)
      return finalizeResult({ ...baseResult(id, 'upgrades', options), results: rows, notes })
    }, inputFor(profile, options, `# upgrades: ${slots?.length ? slots.join(',') : 'all slots'}`), profile.name, profile.spec)
  },
  async runGems({ profile, options, mode, gem_pool, include_enchants, enchant_slots, sets }) {
    return startJob('gems', 60, 2, (id) => finalizeResult({ ...baseResult(id, 'gems', options), results: buildGemsRows(id, profile, mode, gem_pool, include_enchants, enchant_slots, sets) }), inputFor(profile, options, `# gems mode=${mode}`), profile.name, profile.spec)
  },
  async runConsumables({ profile, options, categories, custom }: ConsumablesBody) {
    return startJob('consumables', 30, 2, (id) => finalizeResult({ ...baseResult(id, 'consumables', options), results: buildConsumablesRows(id, categories, custom) }), inputFor(profile, options, `# consumables categories=${categories?.join(',') ?? 'all'}`), profile.name, profile.spec)
  },
  async runOmnium({ profile, options, mode, sets }: OmniumBody) {
    return startJob('omnium', 40, 2, (id) => finalizeResult({ ...baseResult(id, 'omnium', options), results: buildOmniumRows(id, profile, mode, sets) }), inputFor(profile, options, `# omnium mode=${mode}`), profile.name, profile.spec)
  },
  async jobs() { return [...jobs.values()].map((r) => ({ ...r.job })) },
  async job(id) { const r = jobs.get(id); if (!r) throw new Error('Job not found'); return { ...r.job } },
  async cancel(id) {
    const r = jobs.get(id)
    if (!r) throw new Error('Job not found')
    if (r.job.status === 'queued' || r.job.status === 'running') {
      if (r.timer) clearInterval(r.timer)
      r.job.status = 'cancelled'
      r.job.finished = new Date().toISOString()
      r.job.progress = { ...r.job.progress, phase: 'cancelled', message: 'Cancelled by user' }
      r.listeners.forEach((l) => l({ ...r.job }))
    }
    return { ...r.job }
  },
  async result(id) {
    const r = jobs.get(id)
    if (r?.result) return r.result
    // History entries from a "previous session": synthesize on demand.
    const h = history.find((e) => e.id === id)
    if (!h) throw new Error('Result not found')
    const opts = defaultOptions()
    const base = baseResult(id, h.type, opts)
    base.character = h.character ?? 'Unknown'
    base.spec = h.spec ?? ''
    if (h.type === 'topgear') base.results = topGearRows(id, [...BAGS, ...VAULT].map((i) => i.key), 40)
    if (h.type === 'droptimizer') { base.results = droptimizerRows(id, 2); base.groups = buildDroptimizerGroups(base.results, base.baseline.dps) }
    if (h.type === 'statweights') base.stat_weights = STAT_WEIGHTS
    return finalizeResult(base)
  },
  async input(id) { return jobs.get(id)?.input || inputFor(PROFILE, defaultOptions()) },
  reportUrl: (id) => `/api/jobs/${id}/report.html`,
  simcReportUrl: (id) => `/api/jobs/${id}/simc.html`,
  async report(id) {
    const r = jobs.get(id)?.result
    return `<!doctype html><html><head><meta charset="utf-8"><title>ToonOptimizer report ${id}</title></head><body style="font-family:sans-serif;background:#111;color:#eee;padding:24px"><h1>${r?.character ?? 'Report'} - ${r?.spec ?? ''}</h1><p>${r ? Math.round(r.baseline.dps).toLocaleString() : ''} DPS</p><pre>${JSON.stringify(r, null, 2)}</pre></body></html>`
  },
  async history() { await sleep(120); return [...history] },
  async deleteHistory(id) { const i = history.findIndex((h) => h.id === id); if (i >= 0) history.splice(i, 1); jobs.delete(id); return { ok: true } },
  async characters() { await sleep(150); return [...CHARACTER_SUMMARIES] },
  async character(slug) {
    await sleep(150)
    const p = CHARACTER_PROFILES[slug]
    if (!p) throw new Error(`Character '${slug}' not found`)
    return p
  },
  async deleteCharacter(slug) {
    delete CHARACTER_PROFILES[slug]
    const i = CHARACTER_SUMMARIES.findIndex((c) => c.slug === slug)
    if (i >= 0) CHARACTER_SUMMARIES.splice(i, 1)
    return { ok: true }
  },
  async advisor({ slug, profile, options }) {
    await sleep(400)
    const prof = profile ?? (slug ? CHARACTER_PROFILES[slug] : undefined)
    if (!prof) throw new Error('advisor requires a slug or a profile')
    return buildAdvisorResult(slug ?? characterSlug(prof.name, prof.realm), prof, options)
  },
  async reports() { await sleep(150); return [...REPORT_LIST] },
  async characterReport(slug) {
    await sleep(150)
    const r = REPORTS[slug]
    if (!r) throw new Error(`Report '${slug}' not found`)
    return r
  },
  async putCharacterReport(slug, report) {
    await sleep(200)
    const updated: CharacterReport = { ...report, slug, updated_at: new Date().toISOString() }
    REPORTS[slug] = updated
    const entry: ReportListEntry = { slug, character: updated.character, klass: updated.klass, spec: updated.spec, updated_at: updated.updated_at, summary: updated.summary }
    const i = REPORT_LIST.findIndex((r2) => r2.slug === slug)
    if (i >= 0) REPORT_LIST[i] = entry
    else REPORT_LIST.push(entry)
    return updated
  },
  async deleteCharacterReport(slug) {
    delete REPORTS[slug]
    const i = REPORT_LIST.findIndex((r) => r.slug === slug)
    if (i >= 0) REPORT_LIST.splice(i, 1)
    return { ok: true }
  },
  async wowDir() {
    await sleep(200)
    return {
      current: SETTINGS.wow_dir,
      valid: !/invalid/i.test(SETTINGS.wow_dir),
      candidates: [
        { path: 'C:\\Games\\World of Warcraft', source: 'registry' as const },
        { path: 'D:\\Games\\World of Warcraft', source: 'scan' as const },
      ],
    }
  },
  async settings() { return { ...SETTINGS } },
  async putSettings(patch) {
    if (patch.wow_dir !== undefined && /invalid/i.test(patch.wow_dir)) throw new Error('No _retail_ folder found in that directory')
    SETTINGS = { ...SETTINGS, ...patch }
    STATUS.threads = SETTINGS.threads
    return { ...SETTINGS }
  },
  async surrogateStatus() { await sleep(150); return { ...SURROGATE_STATUS, models: [...SURROGATE_STATUS.models] } },
  async surrogateTrain(klass, spec) { return startSurrogateTrainJob(klass, spec) },
  subscribeJob(id, listener): Unsubscribe {
    const r = jobs.get(id)
    if (!r) return () => undefined
    r.listeners.add(listener)
    setTimeout(() => listener({ ...r.job }), 0)
    return () => r.listeners.delete(listener)
  },
}

export const MOCK_SLOTS = SLOTS
