// Mirrors /API.md. Keep in sync with backend/src/toonopt/models.py.

export const SLOTS = [
  'head', 'neck', 'shoulder', 'back', 'chest', 'wrist', 'hands', 'waist', 'legs', 'feet',
  'finger1', 'finger2', 'trinket1', 'trinket2', 'main_hand', 'off_hand',
] as const
export type Slot = (typeof SLOTS)[number]

export type SourceType = 'raid' | 'dungeon' | 'world_boss' | 'delve' | 'crafted' | 'vault' | 'bag' | 'equipped' | 'catalyst'

export type ItemSource = {
  type: SourceType
  name: string
  boss?: string | null
  difficulty?: string | null
  key_level?: number | null
}

export type Item = {
  key: string
  id: number
  name: string
  slot: string
  inventory_type: number
  ilevel: number
  quality: number
  icon: string
  bonus_ids: number[]
  gem_ids: number[]
  /** Count of sockets on the item (from bonus ids), including empty ones — so `sockets -
   * gem_ids.length` empty sockets can be shown. Additive/optional: absent means assume
   * `gem_ids.length` (no empty sockets known). */
  sockets?: number
  enchant_id: number | null
  crafted_stats: number[]
  crafting_quality: number | null
  unique_equipped: string | null
  set_id: number | null
  stats: Record<string, number>
  source?: ItemSource | null
  simc_string: string
  /** False when the backend could not look this item up against the cached game data.
   * Additive/optional: absent (or true) means resolved normally. */
  resolved?: boolean
}

export type Role = 'attack' | 'tank' | 'heal'

/** A crest or catalyst-adjacent currency from the export's "# upgrade_currencies=" line.
 * `crest` equals the string used in `ResultRow.meta.upgrade.crest` when this currency is a
 * crest (e.g. "Gilded"), so upgrade rows are matched to owned amounts by that string; `null`
 * for non-crest currencies. */
export type Currency = {
  id: number
  kind: 'currency' | 'item'
  amount: number
  name: string
  icon: string
  crest: string | null
  max_quantity?: number | null
}

/** One saved talent loadout from the export's loadout comments; "active" is the currently
 * equipped loadout, "saved" are the other Blizzard loadout slots. */
export type SavedLoadout = { name: string; string: string; kind: 'active' | 'saved' }

export type CharacterProfile = {
  name: string
  realm: string
  region: string
  level: number
  race: string
  klass: string
  spec: string
  role: Role
  talents: string
  professions: Record<string, number>
  equipped: Record<string, Item>
  bags: Item[]
  vault: Item[]
  simc_header: string
  raw: string
  imported_at: string
  /** Non-fatal import/lookup warnings from the backend, e.g. items it couldn't resolve.
   * Additive/optional: absent or empty means no warnings. */
  warnings?: string[]
  /** Crest/upgrade currencies from the export's "# upgrade_currencies=" line. Additive/optional:
   * absent or empty means an older addon export with no currency data (SimC addon needs a
   * re-export to include it). */
  currencies?: Currency[]
  /** Weekly Catalyst charges remaining, if the export included them. Additive/optional. */
  catalyst_charges?: number | null
  /** In-game talent loadouts from the export's loadout comments. Additive/optional: absent or
   * empty means the export had no loadout list (older addon, or hand-written .simc). */
  saved_loadouts?: SavedLoadout[]
  /** "# loot_spec=" if present. Additive/optional. */
  loot_spec?: string | null
  /** "# slot_high_watermarks=" slot -> ilvl, for gold-only upgrades later. Additive/optional. */
  high_watermarks?: Record<string, number>
  /** Current Omnium Folio picks, parsed from the export's "omnium_talents=" header line:
   * entry_id -> rank (always 1 this tree). Additive/optional: absent means no Omnium selection
   * found (e.g. older export, or a class without the tree). */
  omnium?: Record<string, number>
}

export const FIGHT_STYLES = [
  'Patchwerk', 'DungeonSlice', 'HecticAddCleave', 'CleaveAdd', 'LightMovement', 'HeavyMovement', 'CastingPatchwerk',
  'TargetDummy', 'ExecutePatchwerk',
] as const
export type FightStyle = (typeof FIGHT_STYLES)[number]

export const PRECISIONS = ['low', 'medium', 'high'] as const
export type Precision = (typeof PRECISIONS)[number]

export const METRICS = ['dps', 'prioritydps', 'dtps', 'hps', 'dmg_taken'] as const
export type Metric = (typeof METRICS)[number]

/** Raw SimC lines spliced into the generated input at those positions (see SimOptions.expert).
 * threads=, json2=, html=, output=, xml= lines are stripped by the backend. */
export type ExpertOptions = { header?: string; pre_actor?: string; post_actor?: string; footer?: string }

export type Consumables = {
  flask?: string
  food?: string
  potion?: string
  augmentation?: string
  temporary_enchant?: string
}

export type SimOptions = {
  fight_style: FightStyle
  max_time: number
  vary_combat_length: number
  desired_targets: number
  iterations: number | null
  target_error: number | null
  buffs: Record<string, boolean>
  consumables: Consumables
  enchant_all: boolean
  socket_all: boolean
  talents_override: string | null
  ptr: boolean
  threads: number | null
  /** Staged "Smart Sim" for any profileset sim: null (default) = single pass with
   * iterations/target_error as today. Additive/optional. */
  precision?: Precision | null
  /** Which SimC metric results are ranked by. Additive/optional: absent means "dps". */
  metric?: Metric
  /** Raw SimC lines spliced into the generated input. Additive/optional. */
  expert?: ExpertOptions | null
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export type JobType =
  | 'quick' | 'topgear' | 'droptimizer' | 'statweights' | 'gearcompare' | 'talentcompare' | 'advanced'
  | 'upgrades' | 'gems' | 'consumables' | 'omnium'
  | 'simc_install' | 'data_refresh' | 'surrogate_train'

export type JobProgressInfo = { phase: string; current: number; total: number; pct: number; message: string }

export type Job = {
  id: string
  type: JobType
  status: JobStatus
  progress: JobProgressInfo
  character?: string | null
  spec?: string | null
  created: string
  started?: string | null
  finished?: string | null
  error?: string | null
}

/** GET /api/data/recommendations gem reference: id/name/icon/stat, `limit` for unique-equipped gems. */
export type GemRef = { id: number; name: string; icon: string; stat: string; limit?: number }
/** GET /api/data/recommendations enchant option for a slot; `recommended` marks the season's pick. */
export type EnchantRef = { id: number; name: string; icon?: string; stat?: string; recommended: boolean }

/** One Omnium Folio choice within a row (GET /api/data/recommendations, season.json's `omnium`). */
export type OmniumChoice = { entry_id: number; token: string; name: string; icon: string }
/** One Omnium Folio row (TraitTree 1186 has 5, one choice picked per row). */
export type OmniumRow = { row: number; node_id: number; choices: OmniumChoice[] }

/** GET /api/data/recommendations `catalyst` — which slots this spec's tier set can catalyze into,
 * and the currency id backing `CharacterProfile.catalyst_charges`. */
export type CatalystRecommendation = { charges_currency_id: number; slots: string[] }

export type Recommendations = {
  season: string
  gems: {
    default: GemRef
    by_stat: Record<'crit' | 'haste' | 'mastery' | 'versatility', GemRef>
    unique: GemRef[]
  }
  enchants: Record<string, EnchantRef[]>
  consumables: Consumables
  /** Additive/optional: absent means this spec has no catalyzable slots this season. */
  catalyst?: CatalystRecommendation
  /** Additive/optional: absent means the Omnium Folio tree wasn't available for this spec. */
  omnium?: { rows: OmniumRow[] }
}

/** One rank->rank step within an upgrade track (see UpgradeInfo.steps). */
export type UpgradeStep = { rank: number; ilevel: number; crest: string; cost: number }

/** ResultRow.meta.upgrade — set by the `upgrades` job type. */
export type UpgradeInfo = {
  slot: string
  item_id: number
  track: string
  from_rank: number
  to_rank: number
  max_rank: number
  from_ilevel: number
  to_ilevel: number
  crest: string
  cost: number
  steps: UpgradeStep[]
  /** cost <= amount of the matching crest currency (by `Currency.crest`); null if unknown
   * (e.g. the profile has no currencies). Additive/optional: absent means unknown, same as null. */
  affordable?: boolean | null
}

/** ResultRow.meta.gem — set by the `gems` job type in `per_socket` mode. */
export type GemChange = { slot: string; socket_index: number; gem_id: number; gem_name: string; stat: string }
/** ResultRow.meta.enchant — set by the `gems` job type when `include_enchants` produces a row. */
export type EnchantChange = { slot: string; enchant_id: number; name: string; stat?: string | null }

export type ResultMeta = {
  item?: Item | null
  items?: Item[] | null
  loadout?: string | null
  source?: ItemSource | null
  changes?: Record<string, Item> | null
  /** Experimental: set only by Top Gear "smart" mode (see toonopt.surrogate). */
  predicted_dps?: number | null
  upgrade?: UpgradeInfo | null
  gem?: GemChange | null
  enchant?: EnchantChange | null
  /** Highest Smart Sim precision stage this row reached (1..3), when `SimOptions.precision` was
   * set. Additive/optional: absent means precision wasn't used (or this is the baseline). */
  stage?: number | null
  /** ResultRow.meta.consumable — set by the `consumables` job type. Additive/optional. */
  consumable?: { category: string; name: string } | null
  /** ResultRow.meta.omnium — set by the `omnium` job type in per_row mode (combos mode uses
   * `meta.loadout` instead, per API.md). Additive/optional. */
  omnium?: { row: number; entry_id: number; name: string } | null
}

export type ResultRow = {
  name: string
  label: string
  dps: number
  dps_error: number
  delta: number
  delta_pct: number
  meta: ResultMeta
  /** Every metric SimC returned for this row (dps, prioritydps, dtps, hps, dmg_taken, ...).
   * Additive/optional: absent means only `dps`/`dps_error` are known. */
  metrics?: Record<string, number> | null
}

export type BreakdownRow = {
  name: string
  id: number
  type: 'direct' | 'periodic' | 'pet'
  total: number
  pct: number
  count: number
  hit: number
  crit: number
  crit_pct: number
}

export type StatWeights = {
  weights: Record<string, number>
  normalized: Record<string, number>
  pawn: string
  error: Record<string, number>
}

/** SimResult.groups — per-drop-source rollup for the Droptimizer "Group by" view. Best/EV are
 * computed from the best row per item in the group (see API.md). EV assumes equal drop odds
 * across the items in the group. */
export type ResultGroup = {
  key: string
  label: string
  kind: 'boss' | 'dungeon' | 'delve' | 'world_boss' | 'crafted' | 'catalyst'
  n: number
  best: number
  best_pct: number
  best_label: string
  ev: number
  ev_pct: number
  upgrade_share: number
}

export type SimResult = {
  job_id: string
  type: JobType
  character: string
  spec: string
  klass: string
  simc_version: string
  wow_version: string
  options: SimOptions
  baseline: { name: string; dps: number; dps_error: number; label: string; metrics?: Record<string, number> | null }
  results: ResultRow[]
  breakdown: BreakdownRow[]
  uptimes: { name: string; pct: number }[]
  stat_weights?: StatWeights | null
  timing: { seconds: number; iterations: number }
  input_file: string
  notes?: string[]
  /** The metric rows are sorted/ranked by; lower is better for dtps/dmg_taken. Additive/optional:
   * absent means "dps". */
  metric?: string
  /** json2 players[0].valid_fight_style — false when the fight style couldn't be applied as
   * requested (e.g. an APL that ignores movement). Additive/optional: absent means unknown. */
  valid_fight_style?: boolean | null
  /** Droptimizer "Group by" rollup (boss/dungeon/delve/world_boss/crafted). Additive/optional:
   * absent means the backend hasn't computed groups for this job. */
  groups?: ResultGroup[]
}

export type DropSource =
  | { type: 'raid'; instance_id: number; difficulty: 'lfr' | 'normal' | 'heroic' | 'mythic'; bosses?: number[] }
  | { type: 'dungeon'; instance_ids?: number[]; key_level: number; vault?: boolean }
  | { type: 'world_boss' }
  | { type: 'delve'; tier: number }
  | { type: 'crafted'; ilevel: number; stats: [string, string] }
  /** Your equipped/bag items catalyzed at the given track (uses catalyst charges). Additive. */
  | { type: 'catalyst'; track: string; rank?: number }

export type Upgrade = 'drop' | 'max' | number

export type LootSources = {
  raids: {
    instance_id: number
    name: string
    difficulties: { name: string; ilevel: number }[]
    bosses: { encounter_id: number; name: string; order: number }[]
  }[]
  dungeons: { instance_id: number; name: string }[]
  key_levels: { level: number; ilevel: number }[]
  world_bosses: { name: string; ilevel?: number; [k: string]: unknown }[]
  delves: { tier: number; ilevel: number }[]
  crafted: { ilevels?: number[]; stats?: string[]; [k: string]: unknown }
}

export type Status = {
  simc: {
    installed: boolean
    tag: string
    path: string
    version_string: string
    wow_version: string
    latest_tag: string
    update_available: boolean
  }
  data: { build: string; cached_tables: string[]; ready: boolean; refreshed_at: string | null }
  gpu: { available: boolean; name: string }
  threads: number
  wow_build: string
  mismatch: {
    simc: boolean          // installed SimC's WoW version (major.minor.patch) differs from game_build
    data: boolean          // cached data build differs from game_build
    simc_wow_version: string
    data_build: string
    game_build: string
  }
}

// Experimental GPU surrogate (see toonopt.surrogate). GET /api/surrogate/status.
export type SurrogateModel = {
  klass: string
  spec: string
  samples: number
  val_mae_pct: number
  trained_at: string
}

export type SurrogateStatus = {
  available: boolean
  device: 'cuda' | 'cpu' | 'unavailable'
  models: SurrogateModel[]
}

// backend/src/toonopt/config.py Settings
export type Settings = {
  port: number
  threads: number
  profileset_work_threads: number
  default_iterations: number
  default_target_error: number
  profileset_target_error: number
  wow_dir: string
  wow_build: string           // effective build (read-only: override, else auto-detected)
  wow_build_override: string  // explicit pin; '' = auto-detect from wow_dir/.build.info
  simc_tag: string
  region: string
  ptr: boolean
}

/** GET /api/history entries for non-sim jobs (simc_install, data_refresh, advanced without a named
 * actor) carry no character/spec/created — HistoryPage must guard these, not assume every row is
 * a finished sim on a named character. */
export type HistoryEntry = {
  id: string
  type: JobType
  character: string | null
  spec: string | null
  created: string | null
  summary: string
}

export type TalentNode = { id: number; name?: string; [k: string]: unknown }
export type TalentTrees = { class_tree: TalentNode[]; spec_tree: TalentNode[]; hero_trees: unknown[] }
// API.md: `{ selected: {node_id: rank}[], hero_tree }` — accepted as either a list of {node_id, rank}
// objects or a single map of node_id -> rank; see normalizeDecoded in lib/talents.ts.
export type DecodedTalents = {
  selected: ({ node_id: number; rank: number } | Record<string, number>)[] | Record<string, number>
  // toonopt.data.talents.decode() returns {id, name} (or null when no hero talent is chosen),
  // never a bare string/number.
  hero_tree?: { id: number; name: string } | null
}

/** One rank->rank step of a season upgrade track (Adventurer/Veteran/Champion/Hero/Myth/...).
 * Used to populate the Top Gear "Add item" track/rank selects. This is the *normalized* shape —
 * see `RawUpgradeTrack` for what the backend actually sends and `normalizeUpgradeTracks` in
 * lib/api.ts for the conversion (the only place this normalization happens). */
export type UpgradeTrackDef = { name: string; ranks: { rank: number; ilevel: number; crest?: string; cost?: number }[] }

/** Raw per-track entry as returned by GET /api/data/season's `upgrade_tracks` (keyed by track
 * name, e.g. `{"Myth": {...}}`) — confirmed against the live backend 2026-09-24. `steps` carries
 * one entry per rank; `crest` is a single object for the whole track (same crest/cost at every
 * rank of that track). */
export type RawUpgradeTrack = {
  name: string
  group?: number
  max?: number
  steps: { rank: number; ilevel: number; bonus_id?: number }[]
  crest?: { name: string; currency_id?: number; cost?: number; icon?: string; discounted_cost?: number } | null
  ilevels?: number[]
  bonus_ids?: number[]
  achievement_id?: number
}

/** One selectable SimC name for a consumable category, as the backend actually sends it
 * (`data/season.py::consumable_options` / `CONSUMABLE_OPTIONS`) — `value` is the SimC token,
 * `label` is the display name. */
export type ConsumableOption = { value: string; label: string }

/** SimC names accepted by the installed binary for each consumable category (season.json
 * `consumables.options`, wave 2). Populates the OptionsPanel/Consumables page dropdowns. */
export type ConsumableOptions = {
  flask: ConsumableOption[]
  food: ConsumableOption[]
  potion: ConsumableOption[]
  augmentation: ConsumableOption[]
  temporary_enchant: ConsumableOption[]
}

/** `SeasonData.catalyst` — season.json's Catalyst mapping (wave 2). */
export type CatalystSeasonData = {
  conversion_id: number
  currency_id: number
  slots: string[]
  set_ids?: Record<string, number>
  items?: Record<string, Record<string, number>>
  set_bonus_spells?: Record<string, Record<string, Record<string, number>>>
}

/** `SeasonData.sockets` — add-socket bonus ids and which slots can take a vault/Jewelbinder
 * socket (wave 2). */
export type SocketsSeasonData = {
  add_bonus_id: number
  two: number
  three: number
  vault_slots: string[]
  jewelbinder_slots: string[]
  jewelbinder_item: number
}

/** `SeasonData.voidforged` — this season only has a Myth-track Voidforge (wave 2). */
export type VoidforgedSeasonData = { slots: string[]; myth_ilevel: number; bonus_id: number }

/** `SeasonData.crafted` — recraft stat/embellishment/quality bonus ids (wave 2). */
export type CraftedSeasonData = {
  stat_ids: Record<string, number>
  stat_bonus_ids: number[]
  quality_bonus_max: number
  embellishments: { id: number; name: string; icon?: string }[]
  embellish_marker: number
  max_embellished: number
}

/** `SeasonData.omnium` — Omnium Folio tree (TraitTree 1186), wave 2. */
export type OmniumSeasonData = { tree_id: number; rows: OmniumRow[] }

export type SeasonData = {
  consumables?: Consumables & { options?: ConsumableOptions }
  /** Post-normalization shape returned by `api.season()`. On the wire (both the real backend and
   * the mock fixtures) `upgrade_tracks` is actually an object keyed by track name
   * (`Record<string, RawUpgradeTrack>`), not an array — `api.season()` in lib/api.ts is the one
   * place that normalizes it to `UpgradeTrackDef[]` before handing it to pages, so everything
   * downstream (e.g. TopGearPage's track/rank selects) can just treat this as an array. */
  upgrade_tracks?: UpgradeTrackDef[]
  /** Wave 2 additions — all additive/optional; see API.md "Raidbots parity, wave 2". */
  catalyst?: CatalystSeasonData
  sockets?: SocketsSeasonData
  voidforged?: VoidforgedSeasonData
  crafted?: CraftedSeasonData
  omnium?: OmniumSeasonData
  [k: string]: unknown
}

/** GET /api/data/items/search result — an item search hit, filtered to what the spec can equip. */
export type ItemSearchResult = {
  id: number
  name: string
  icon: string
  quality: number
  inventory_type: number
  slot: string
  base_ilevel: number
  expansion_hint?: string
}

// Request bodies
export type QuickBody = { profile: CharacterProfile; options: SimOptions }
export type TopGearBody = QuickBody & {
  candidate_keys: string[]
  max_combos: number
  smart: boolean
  min_ilevel?: number | null
  /** Each combo is simmed per loadout (profileset adds talents=); the combo cap applies to the
   * product. Additive/optional. */
  loadouts?: { name: string; string: string }[]
  /** Items from search, treated like bag candidates (key "search:..."). Additive/optional. */
  extra_items?: Item[]
  /** Candidate keys to also offer as their catalyzed twin (key "catalyst:<orig key>"); combos may
   * not catalyze more items than `profile.catalyst_charges` (null = unlimited). Additive/optional. */
  catalyst?: { keys: string[]; min_set_pieces?: 0 | 2 | 4 }
  /** Offer a +socket variant (bonus 1808 + preferred/default gem) for those items; at most one
   * vault-socket item per combo in `season.sockets.vault_slots`. Additive/optional. */
  add_socket?: { keys: string[]; gem_id?: number }
  /** Offer the Myth voidforged twin for max-Myth items in `season.voidforged.slots`. Additive/optional. */
  voidforge?: { keys: string[] }
  /** Recraft variants of owned crafted items (strip 8790-8795, set crafted_stats). Additive/optional. */
  crafted?: { key: string; stats: [string, string]; embellishment_id?: number; quality_bonus?: number }[]
}
export type DroptimizerBody = QuickBody & {
  sources: DropSource[]
  upgrade: Upgrade
  min_ilevel?: number | null
  /** Upgrade the baseline's equipped gear along its track before simming drops. Additive/optional:
   * absent means "none". */
  upgrade_equipped?: 'none' | 'match' | 'max'
  /** Additive/optional: absent means false. */
  include_offspec?: boolean
  /** Every drop in a catalyst slot also gets its catalyzed twin (source "catalyst"). Additive/optional. */
  include_catalyst?: boolean
  /** Drops in `season.sockets.vault_slots` get bonus 1808 + `preferred_gem`/the default gem. Additive/optional. */
  add_socket?: boolean
  /** Gem id used by `add_socket` (and the vault-socket variant); default when absent. Additive/optional. */
  preferred_gem?: number
}
export type StatWeightsBody = QuickBody & { stats: string[] }
export type GearCompareBody = QuickBody & { sets: { name: string; changes: Record<string, Item> }[] }
export type TalentCompareBody = QuickBody & { loadouts: { name: string; string: string }[] }
export type AdvancedBody = { simc_text: string; options?: SimOptions }
export type SurrogateTrainBody = { klass: string; spec: string; min_samples?: number; epochs?: number }
export type UpgradesBody = QuickBody & { slots?: string[]; max_ranks?: number | null; min_ilevel?: number | null }

export type GemsMode = 'uniform' | 'per_socket' | 'custom'
export type GemsCustomSet = { name: string; gems: Record<string, number[]>; enchants: Record<string, number> }
export type GemsBody = QuickBody & {
  mode: GemsMode
  gem_pool?: number[]
  include_enchants?: boolean
  enchant_slots?: string[]
  sets?: GemsCustomSet[]
}

export type ConsumableCategory = 'flask' | 'food' | 'potion' | 'augmentation' | 'temporary_enchant'
export type ConsumablesCustomSet = { name: string } & Partial<Record<ConsumableCategory, string>>
export type ConsumablesBody = QuickBody & {
  categories?: ConsumableCategory[]
  custom?: ConsumablesCustomSet[]
}

export type OmniumMode = 'per_row' | 'combos' | 'custom'
export type OmniumCustomSet = { name: string; entries: number[] }
export type OmniumBody = QuickBody & {
  mode: OmniumMode
  sets?: OmniumCustomSet[]
}

// ---------- Characters, Advisor, Reports (see API.md "Characters, Advisor, Reports") ----------

/** GET /api/characters row — one saved character (server-side store of imported profiles). */
export type CharacterSummary = {
  slug: string
  name: string
  realm: string
  klass: string
  spec: string
  ilevel_equipped: number
  imported_at: string
}

export type AdvisorEffort = 'trivial' | 'easy' | 'medium' | 'hard' | 'very_hard'
export type AdvisorVerdict = 'obvious' | 'likely' | 'sim_to_confirm' | 'sidegrade' | 'downgrade'

/** One stepping stone toward acquiring/upgrading an AdvisorCandidate, e.g. "Drop from Nek'zali
 * (Heroic) 308" then "Upgrade Hero 1/6→6/6 (75 Runed)". */
export type AdvisorPathStep = { step: string; crest?: string; cost?: number }

export type AdvisorCandidate = {
  item: Item
  /** Same item fully upgraded on its track. Additive/optional. */
  max_item?: Item
  source: ItemSource & { effort: AdvisorEffort; weekly?: boolean }
  ilevel_gain: number
  ilevel_gain_max: number
  stat_score: number
  stat_score_delta: number
  verdict: AdvisorVerdict
  reasons: string[]
  path: AdvisorPathStep[]
  /** Other sources of the same item id. */
  alternatives: string[]
}

export type AdvisorSlot = {
  slot: string
  equipped: { item: Item; ilevel: number; stat_score: number; track?: string; rank?: string }
  /** Sorted: obvious first, then by expected value desc. */
  candidates: AdvisorCandidate[]
  /** Best candidate at max upgrade by ilevel then stat_score. */
  bis_heuristic: AdvisorCandidate | null
}

export type AdvisorResult = {
  slug: string
  character: string
  klass: string
  spec: string
  generated_at: string
  stat_priority: {
    source: 'statweights_job' | 'recommendation'
    order: string[]
    weights?: Record<string, number>
    job_id?: string
  }
  ilevel_equipped: number
  slots: AdvisorSlot[]
  tier: { set_id: number | null; equipped_pieces: number; slots_with_tier: string[]; catalyst_charges: number | null }
  sim_plan: { droptimizer: DropSource[]; topgear_candidate_keys: string[]; upgrades_slots: string[]; note: string }
  notes: string[]
}

/** POST /api/advisor/obvious-upgrades body — one of `slug`/`profile` is required. */
export type AdvisorOptions = {
  key_level?: number
  delve_tier?: number
  raid_difficulties?: string[]
  min_ilevel_gain?: number
  /** Not in the base contract's Rules list, but mirrors every other sim body's include-downgrades
   * escape hatch; harmless if the backend ignores it. Additive/optional. */
  include_downgrades?: boolean
}
export type AdvisorBody = { slug?: string; profile?: CharacterProfile; options?: AdvisorOptions }

/** GET /api/reports row. */
export type ReportListEntry = { slug: string; character: string; klass: string; spec: string; updated_at: string; summary: string }

export type ReportSection =
  | { kind: 'markdown'; title: string; body: string }
  | {
      kind: 'upgrades'
      title: string
      rows: { slot: string; current: string; option: string; verdict: string; gain: string; how: string[]; sim?: { job_id: string; delta_pct: number } }[]
    }
  | { kind: 'bis'; title: string; rows: { slot: string; item: Item; source: string; you_have: boolean; theorycraft_says?: string }[] }
  | { kind: 'talents'; title: string; entries: { context: string; loadout: string; notes: string; source_url?: string }[] }
  | { kind: 'kv'; title: string; items: { label: string; value: string; note?: string }[] }

/** GET/PUT /api/reports/{slug} — maintained by the Claude Code "obvious-upgrades" skill, not
 * generated live by the app (see the Advisor endpoint for the live/synchronous equivalent). */
export type CharacterReport = {
  slug: string
  character: string
  realm: string
  klass: string
  spec: string
  updated_at: string
  ilevel_equipped: number
  season: string
  simc_version: string
  /** 2-4 sentences, plain prose. */
  summary: string
  /** Rendered in order. */
  sections: ReportSection[]
  /** The raw advisor output used to write this report, if any. Additive/optional. */
  advisor?: AdvisorResult
  sim_refs: { job_id: string; type: string; label: string }[]
  sources: { title: string; url: string; fetched_at: string }[]
}
