import type { ConsumableOption, ConsumableOptions, FightStyle, Metric, SimOptions } from './types'

export const CLASS_COLORS: Record<string, string> = {
  death_knight: '#C41E3A',
  demon_hunter: '#A330C9',
  druid: '#FF7C0A',
  evoker: '#33937F',
  hunter: '#AAD372',
  mage: '#3FC7EB',
  monk: '#00FF98',
  paladin: '#F48CBA',
  priest: '#FFFFFF',
  rogue: '#FFF468',
  shaman: '#0070DD',
  warlock: '#8788EE',
  warrior: '#C69B3A',
}

export const QUALITY_COLORS: Record<number, string> = {
  0: '#9d9d9d',
  1: '#ffffff',
  2: '#1eff00',
  3: '#0070dd',
  4: '#a335ee',
  5: '#ff8000',
  6: '#e6cc80',
  7: '#00ccff',
  8: '#00ccff',
}

export const QUALITY_NAMES: Record<number, string> = {
  0: 'Poor', 1: 'Common', 2: 'Uncommon', 3: 'Rare', 4: 'Epic', 5: 'Legendary', 6: 'Artifact', 7: 'Heirloom', 8: 'Token',
}

export const SLOT_LABELS: Record<string, string> = {
  head: 'Head', neck: 'Neck', shoulder: 'Shoulder', back: 'Back', chest: 'Chest', wrist: 'Wrist',
  hands: 'Hands', waist: 'Waist', legs: 'Legs', feet: 'Feet', finger1: 'Ring 1', finger2: 'Ring 2',
  finger: 'Ring', trinket1: 'Trinket 1', trinket2: 'Trinket 2', trinket: 'Trinket',
  main_hand: 'Main Hand', off_hand: 'Off Hand',
}

/** Paperdoll layout: left column, right column (Blizzard character pane order). */
export const PAPERDOLL_LEFT = ['head', 'neck', 'shoulder', 'back', 'chest', 'wrist'] as const
export const PAPERDOLL_RIGHT = ['hands', 'waist', 'legs', 'feet', 'finger1', 'finger2', 'trinket1', 'trinket2'] as const
export const PAPERDOLL_BOTTOM = ['main_hand', 'off_hand'] as const

export const STAT_LABELS: Record<string, string> = {
  strength: 'Strength', agility: 'Agility', intellect: 'Intellect', stamina: 'Stamina',
  crit: 'Critical Strike', haste: 'Haste', mastery: 'Mastery', versatility: 'Versatility',
  leech: 'Leech', avoidance: 'Avoidance', speed: 'Speed', armor: 'Armor',
  weapon_dps: 'Weapon DPS', attack_power: 'Attack Power', spell_power: 'Spell Power',
}

export const SECONDARY_STATS = ['crit', 'haste', 'mastery', 'versatility'] as const

export function primaryStatFor(klass: string, spec: string): string {
  const intClasses = ['mage', 'warlock', 'priest', 'evoker']
  if (intClasses.includes(klass)) return 'intellect'
  if (klass === 'paladin') return spec === 'holy' ? 'intellect' : 'strength'
  if (klass === 'shaman') return spec === 'restoration' || spec === 'elemental' ? 'intellect' : 'agility'
  if (klass === 'druid') return spec === 'balance' || spec === 'restoration' ? 'intellect' : 'agility'
  if (klass === 'monk') return spec === 'mistweaver' ? 'intellect' : 'agility'
  if (['death_knight', 'warrior'].includes(klass)) return 'strength'
  return 'agility'
}

export const FIGHT_STYLE_INFO: Record<FightStyle, string> = {
  Patchwerk: 'Single target, stand still. The baseline raid boss.',
  DungeonSlice: 'M+ style: alternating trash packs and bosses.',
  HecticAddCleave: 'Constant adds and heavy movement.',
  CleaveAdd: 'Periodic adds that must be cleaved down.',
  LightMovement: 'Single target with occasional movement.',
  HeavyMovement: 'Single target with frequent movement.',
  CastingPatchwerk: 'Patchwerk where the boss casts (interrupts matter).',
  TargetDummy: 'Patchwerk with every buff/consumable/raid override stripped, against a training dummy — closest to a raw tooltip parse.',
  ExecutePatchwerk: 'Patchwerk against one or more targets pinned at 20% health, to isolate execute-range damage.',
}

/** (klass, spec) pairs where the server forces a different DungeonSlice max_time (400s instead
 * of the usual 360s) — the UI disables picking DungeonSlice for them so the "360s / 1 target"
 * hint doesn't lie. */
const DUNGEON_SLICE_DISABLED = new Set(['demon_hunter:havoc', 'demon_hunter:vengeance', 'demon_hunter:devourer'])

/** Non-null when DungeonSlice should be disabled in the fight style picker for this (klass, spec). */
export function dungeonSliceDisabledReason(klass?: string | null, spec?: string | null): string | null {
  if (!klass || !spec || !DUNGEON_SLICE_DISABLED.has(`${klass}:${spec}`)) return null
  return 'DungeonSlice forces a 400s fight for this spec instead of the usual 360s/1 target — disabled here to avoid a mismatched hint.'
}

export const PRECISION_HELP = 'Smart Sim: staged 1% → 0.2% → 0.05%; lower precision rows are dropped early'

export const METRIC_LABELS: Record<Metric, string> = {
  dps: 'DPS',
  prioritydps: 'Priority target DPS',
  dtps: 'DTPS (damage taken/s)',
  hps: 'HPS',
  dmg_taken: 'Damage taken',
}

/** Metrics where a *lower* value is the improvement (damage taken, not damage dealt). */
export const LOWER_IS_BETTER_METRICS = new Set<string>(['dtps', 'dmg_taken'])

export function metricLabel(metric?: string | null): string {
  return METRIC_LABELS[(metric ?? 'dps') as Metric] ?? metric ?? 'DPS'
}

export function isLowerBetter(metric?: string | null): boolean {
  return LOWER_IS_BETTER_METRICS.has(metric ?? 'dps')
}

export const BUFF_LABELS: Record<string, string> = {
  bloodlust: 'Bloodlust / Heroism',
  arcane_intellect: 'Arcane Intellect',
  battle_shout: 'Battle Shout',
  mark_of_the_wild: 'Mark of the Wild',
  power_word_fortitude: 'Power Word: Fortitude',
  chaos_brand: 'Chaos Brand',
  mystic_touch: 'Mystic Touch',
  skyfury: 'Skyfury',
  hunters_mark: "Hunter's Mark",
  bleeding: 'Bleeding',
  windfury_totem: 'Windfury Totem (unsupported by this SimC build)',
  vantus_rune: 'Vantus Rune',
}

/** Buffs with no ``override.<name>`` in the installed SimC (see simc/input.py BUFF_OVERRIDES);
 * toggling them in the UI has no effect on the sim, so the checkbox is shown disabled. */
export const UNSUPPORTED_BUFFS = new Set(['windfury_totem'])

export const DEFAULT_BUFFS: Record<string, boolean> = {
  bloodlust: true, arcane_intellect: true, battle_shout: true, mark_of_the_wild: true,
  power_word_fortitude: true, chaos_brand: true, mystic_touch: true, skyfury: true,
  hunters_mark: true, bleeding: true, windfury_totem: false, vantus_rune: false,
}

/** Fallback consumables when no per-spec recommendation is available (yet, or at all): every
 * category empty, which the backend treats as "disabled" rather than "use SimC default" — never
 * a real SimC name, so it can't be rejected by `validate_options`. The real per-spec defaults come
 * from `GET /api/data/recommendations?klass=&spec=` (`Recommendations.consumables`), cached in the
 * store per "klass:spec" and applied by `seedConsumablesForProfile` (store.ts) — see API.md. */
export const EMPTY_CONSUMABLES: SimOptions['consumables'] = {
  flask: '', food: '', potion: '', augmentation: '', temporary_enchant: '',
}

/** Consumable category -> UI label. "Weapon rune" reads better than "temporary enchant" for the
 * SimC `temporary_enchant` slot (weapon oils/runes/sharpening stones). */
export const CONSUMABLE_CATEGORY_LABELS: Record<string, string> = {
  flask: 'Flask', food: 'Food', potion: 'Potion', augmentation: 'Augmentation', temporary_enchant: 'Weapon rune',
}

/** Sentinel value for the OptionsPanel/Consumables custom-set editor's "Custom…" option — never a
 * real SimC name, so it can't collide with `season.consumables.options`. */
export const CUSTOM_CONSUMABLE = '__custom__'

/** True when `value` is `main_hand:<X>/off_hand:<X>` for some `main_hand:<X>` in `opts` — the
 * dual-wielder mirroring API.md documents for `temporary_enchant` (the catalogue only lists the
 * main_hand form, but `validate_options` accepts the off_hand-mirrored one too). */
function isMirroredDualWieldEnchant(value: string, opts: ConsumableOption[]): boolean {
  const slash = value.indexOf('/')
  if (slash < 0) return false
  const mainHand = value.slice(0, slash)
  const offHand = value.slice(slash + 1)
  const stem = mainHand.startsWith('main_hand:') ? mainHand.slice('main_hand:'.length) : null
  return stem !== null && offHand === `off_hand:${stem}` && opts.some((o) => o.value === mainHand)
}

/** First consumable category whose value is non-empty but isn't one of the SimC names this binary
 * accepts (`season.consumables.options[category]`), or null when every set value is valid.
 * `seasonOptions` unknown/not loaded yet -> can't validate, so treat as valid (null) rather than
 * blocking submission on a slow/failed `GET /api/data/season`. Used right before a sim job is
 * submitted (see store.ts `runJob`) so a stale/custom name is caught client-side instead of
 * round-tripping to a 400 from `validate_options`. */
export function invalidConsumableCategory(
  consumables: SimOptions['consumables'],
  seasonOptions: ConsumableOptions | null | undefined,
): keyof SimOptions['consumables'] | null {
  if (!seasonOptions) return null
  for (const cat of Object.keys(consumables) as (keyof SimOptions['consumables'])[]) {
    const value = consumables[cat]
    if (!value) continue
    const opts = seasonOptions[cat] ?? []
    if (opts.some((o) => o.value === value)) continue
    if (cat === 'temporary_enchant' && isMirroredDualWieldEnchant(value, opts)) continue
    return cat
  }
  return null
}

/** "flask_of_alchemical_chaos_3" -> "Flask Of Alchemical Chaos 3" for consumable dropdown labels
 * when the backend doesn't send a display name, just the SimC token. Tolerates non-string input
 * (e.g. a `{value, label}` option object slipping through unnormalized) so a shape mismatch
 * degrades to an empty/odd label instead of throwing and taking down the whole page. */
export function prettifySimcName(name: unknown): string {
  if (typeof name !== 'string') return String(name ?? '')
  return name.split(/[_:]/).filter(Boolean).map((w) => (/^\d+$/.test(w) ? w : w[0].toUpperCase() + w.slice(1))).join(' ')
}

export function defaultOptions(): SimOptions {
  return {
    fight_style: 'Patchwerk',
    max_time: 300,
    vary_combat_length: 0.2,
    desired_targets: 1,
    iterations: null,
    target_error: 0.1,
    buffs: { ...DEFAULT_BUFFS },
    consumables: { ...EMPTY_CONSUMABLES },
    enchant_all: false,
    socket_all: false,
    talents_override: null,
    ptr: false,
    threads: null,
  }
}

export const JOB_TYPE_LABELS: Record<string, string> = {
  quick: 'Quick Sim', topgear: 'Top Gear', droptimizer: 'Droptimizer', statweights: 'Stat Weights',
  gearcompare: 'Gear Compare', talentcompare: 'Talent Compare', advanced: 'Advanced',
  upgrades: 'Upgrades', gems: 'Gems & Enchants', consumables: 'Consumables', omnium: 'Omnium Folio',
  simc_install: 'SimC Install', data_refresh: 'Data Refresh', surrogate_train: 'Surrogate Train',
}

export const JOB_TYPE_ROUTES: Record<string, string> = {
  quick: '/quick', topgear: '/topgear', droptimizer: '/droptimizer', statweights: '/statweights',
  gearcompare: '/gearcompare', talentcompare: '/talentcompare', advanced: '/advanced',
  upgrades: '/upgrades', gems: '/gems', consumables: '/consumables', omnium: '/talentcompare',
}

export function titleCase(s: string): string {
  return s.split(/[_\s]+/).filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ')
}

export function iconUrl(icon: string): string {
  return `https://wow.zamimg.com/images/wow/icons/large/${icon || 'inv_misc_questionmark'}.jpg`
}

export const QUESTIONMARK_ICON_URL = 'https://wow.zamimg.com/images/wow/icons/large/inv_misc_questionmark.jpg'

/** Short 2-letter code shown in the icon placeholder when an item has no icon, or its icon
 * (and the wowhead question-mark fallback) both fail to load. */
export const SLOT_ABBR: Record<string, string> = {
  head: 'HD', neck: 'NK', shoulder: 'SH', back: 'BK', chest: 'CH', wrist: 'WR', hands: 'HA',
  waist: 'WA', legs: 'LG', feet: 'FT', finger: 'RG', finger1: 'RG', finger2: 'RG',
  trinket: 'TR', trinket1: 'TR', trinket2: 'TR', main_hand: 'MH', off_hand: 'OH',
}

export function slotAbbr(slot: string): string {
  return SLOT_ABBR[slot] ?? slot.slice(0, 2).toUpperCase()
}

/** Slots an item with a generic slot ("finger", "trinket") can be equipped in. */
export function slotsForItem(slot: string): string[] {
  if (slot === 'finger' || slot === 'finger1' || slot === 'finger2') return ['finger1', 'finger2']
  if (slot === 'trinket' || slot === 'trinket1' || slot === 'trinket2') return ['trinket1', 'trinket2']
  return [slot]
}

/** Base slot for grouping: finger1/finger2 -> finger, trinket1/2 -> trinket. */
export function baseSlot(slot: string): string {
  if (slot.startsWith('finger')) return 'finger'
  if (slot.startsWith('trinket')) return 'trinket'
  return slot
}

/** Lowest ilevel among currently equipped items; used as the default "min item level" filter. */
export function lowestEquippedIlevel(equipped: Record<string, { ilevel: number }>): number {
  const levels = Object.values(equipped).map((i) => i.ilevel).filter((n) => Number.isFinite(n))
  return levels.length ? Math.min(...levels) : 0
}

/** "Sundered Onyx (Haste) · Ember of Nazjar (Versatility, unique)" — for the socket_all toggle's tooltip. */
export function recommendedGemSummary(recs: import('./types').Recommendations): string {
  const parts = [`${recs.gems.default.name} (${titleCase(recs.gems.default.stat)})`]
  for (const g of recs.gems.unique) parts.push(`${g.name} (${titleCase(g.stat)}, unique)`)
  return parts.join(' · ')
}

/** "Back: Chant of Winged Grace · Chest: Enchant Chest - Crystalline Radiance · ..." — for the
 * enchant_all toggle's tooltip; only the recommended option per slot. */
export function recommendedEnchantSummary(recs: import('./types').Recommendations): string {
  return Object.entries(recs.enchants)
    .map(([slot, opts]) => [slot, opts.find((o) => o.recommended) ?? opts[0]] as const)
    .filter(([, o]) => !!o)
    .map(([slot, o]) => `${SLOT_LABELS[slot] ?? titleCase(slot)}: ${o!.name}`)
    .join(' · ')
}

/** `name-realm` lowercased, ascii — matches the backend's `characters/<slug>.json` naming
 * (API.md "Characters"), e.g. "Testhunter-Testrealm" -> "testhunter-testrealm". Computed client-side so the
 * Import page can show "Saved as <slug>" right from the import response without the backend
 * needing to echo it back. */
export function characterSlug(name: string, realm: string): string {
  const ascii = (s: string) =>
    s.normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase()
  return [ascii(name), ascii(realm)].filter(Boolean).join('-')
}

export function averageIlvl(equipped: Record<string, { ilevel: number; inventory_type?: number }>): number {
  const items = Object.entries(equipped)
  if (!items.length) return 0
  let total = 0
  let n = 0
  for (const [slot, it] of items) {
    if (slot === 'shirt' || slot === 'tabard') continue
    total += it.ilevel
    n += 1
  }
  // Two-handers count twice.
  const mh = equipped.main_hand
  if (mh && !equipped.off_hand && (mh.inventory_type === 17 || mh.inventory_type === 15 || mh.inventory_type === 26)) {
    total += mh.ilevel
    n += 1
  }
  return n ? total / n : 0
}
