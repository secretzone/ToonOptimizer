# ToonOptimizer API contract

Backend: FastAPI on `http://127.0.0.1:8790`, all routes under `/api`. Frontend (Vite dev on :5173)
talks to it via the `/api` proxy in `vite.config.ts`. JSON everywhere except SSE and report HTML.
Slugs: class/spec use SimC names (`death_knight`, `frost`). Slots use SimC slot names:
`head neck shoulder back chest wrist hands waist legs feet finger1 finger2 trinket1 trinket2 main_hand off_hand`.

## Models

```ts
type Item = {
  key: string            // stable id within a profile: "equipped:head", "bag:3", "vault:1", "drop:<itemid>:<bonus>"
  id: number
  name: string
  slot: string           // SimC slot this item can go in (finger/trinket resolved to finger1 etc. at combo time)
  inventory_type: number // DB2 InventoryType, for slot rules (2H, off-hand, ...)
  ilevel: number
  quality: number        // 0-8
  icon: string           // icon file name, rendered as https://wow.zamimg.com/images/wow/icons/large/<icon>.jpg
  bonus_ids: number[]
  sockets: number         // empty + filled sockets, decoded from bonus_ids (data.bonuses.socket_count);
                          // 0 for an item resolved without the data layer. len(gem_ids) may be < sockets
                          // for an item with an empty socket.
  gem_ids: number[]
  enchant_id: number | null
  crafted_stats: number[]
  crafting_quality: number | null
  unique_equipped: string | null   // limit category name, null if none
  set_id: number | null
  stats: Record<string, number>    // {"agility": 1234, "crit": 345, ...} as SimC would see them
  source?: { type: "raid"|"dungeon"|"world_boss"|"delve"|"crafted"|"vault"|"bag"|"equipped"; name: string; boss?: string; difficulty?: string; key_level?: number }
  simc_string: string    // e.g. "head=,id=212345,bonus_id=1/2/3,ilevel=639,gem_id=...,enchant_id=..."
  resolved: boolean       // false if the data layer could not enrich this item (bare/unnamed
                          // stub: id and whatever the export itself said, nothing else); see
                          // CharacterProfile.warnings for why
}

type Currency = {
  id: number
  kind: "currency" | "item"             // "item" for item-based upgrade currencies (Crafter's Marks etc.)
  amount: number
  name: string; icon: string            // "" when the data layer couldn't resolve this id
  crest: string | null                  // matches UpgradeInfo.crest exactly when this currency is a crest;
                                         // null for non-crest currencies (Valorstones, catalyst mats, ...)
  max_quantity: number | null           // CurrencyTypes.MaxQty; null when uncapped/unknown
}

type CharacterProfile = {
  name: string; realm: string; region: string
  level: number; race: string; klass: string; spec: string; role: "attack"|"tank"|"heal"
  talents: string                       // loadout string as exported
  professions: Record<string, number>
  equipped: Record<string, Item>        // by slot
  bags: Item[]
  vault: Item[]
  currencies: Currency[]                // from the addon's "### Additional Character Info" comments
                                         // (catalyst_currencies, upgrade_currencies, bonus_roll_currencies);
                                         // [] when the export carries none (e.g. hand-written .simc)
  catalyst_charges: number | null       // this season's catalyst currency amount (catalyst_currencies can list
                                         // several currencies from past seasons too; the season's one wins by id,
                                         // falling back to the first entry); null when that line is absent
  catalyst_charges_max: number | null   // that currency's max_quantity (CurrencyTypes.MaxQty), when known
  simc_header: string                   // the actor block lines up to (not incl.) gear
  raw: string                           // full pasted export
  imported_at: string
  warnings: string[]                    // e.g. "3 item(s) could not be resolved (reason: ...) —
                                         // refresh data in Settings"; empty when every item resolved
  source?: "paste"|"addon"|"armory"|null // how it was imported: POST /api/import/simc -> "paste",
                                         // /api/import/addon -> "addon", /api/import/armory -> "armory";
                                         // null on profiles saved before this field existed
}

type SimOptions = {
  fight_style: "Patchwerk"|"DungeonSlice"|"HecticAddCleave"|"CleaveAdd"|"LightMovement"|"HeavyMovement"|"CastingPatchwerk"
  max_time: number                      // seconds, default 300
  vary_combat_length: number            // default 0.2
  desired_targets: number               // default 1
  iterations: number | null             // null -> use target_error
  target_error: number | null
  buffs: Record<string, boolean>        // bloodlust, arcane_intellect, battle_shout, mark_of_the_wild, power_word_fortitude, chaos_brand, mystic_touch, skyfury, hunters_mark, bleeding, windfury_totem
  consumables: { flask?: string; food?: string; potion?: string; augmentation?: string; temporary_enchant?: string } // SimC names or "" for none
  enchant_all: boolean                  // Top Gear: give every candidate the season's best enchant for its slot
  socket_all: boolean                   // Top Gear/Droptimizer: fill every socket with the season's gem
  talents_override: string | null
  ptr: boolean
  threads: number | null                // null -> settings.threads
}

type JobStatus = "queued"|"running"|"done"|"failed"|"cancelled"
type Job = {
  id: string; type: "quick"|"topgear"|"droptimizer"|"statweights"|"gearcompare"|"talentcompare"|"advanced"|"simc_install"|"data_refresh"|"surrogate_train"
  status: JobStatus
  progress: { phase: string; current: number; total: number; pct: number; message: string }
  character?: string; spec?: string
  created: string; started?: string; finished?: string; error?: string
}

type ResultRow = {
  name: string                           // profileset name (unique)
  label: string                          // human label
  dps: number; dps_error: number
  delta: number; delta_pct: number       // vs baseline
  meta: {
    item?: Item; items?: Item[]; loadout?: string; source?: Item["source"]; changes?: Record<string, Item> // slot -> new item
    predicted_dps?: number               // experimental: set only by Top Gear "smart" mode (see toonopt.surrogate)
  }
}

type SimResult = {
  job_id: string; type: Job["type"]; character: string; spec: string; klass: string
  simc_version: string; wow_version: string; options: SimOptions
  baseline: { name: string; dps: number; dps_error: number; label: string }
  results: ResultRow[]                   // sorted by dps desc; empty for quick
  breakdown: { name: string; id: number; type: "direct"|"periodic"|"pet"; total: number; pct: number; count: number; hit: number; crit: number; crit_pct: number }[]
  uptimes: { name: string; pct: number }[]
  stat_weights?: { weights: Record<string, number>; normalized: Record<string, number>; pawn: string; error: Record<string, number> }
  timing: { seconds: number; iterations: number }
  input_file: string                     // relative path of the .simc used
  notes: string[]                        // human sentences for non-fatal skips, e.g. "Skipped 16 slot(s)
                                          // with no remaining upgrade: head, neck, ... (already at max
                                          // rank or no crest track)"; empty when nothing was skipped.
                                          // Filled by the upgrades and gems engines; render above results.
}
```

## Routes

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/api/health` | | `{ok, version}` |
| GET | `/api/status` | | `{ simc: {installed, tag, path, version_string, wow_version, latest_tag, update_available}, data: {build, cached_tables: string[], ready, refreshed_at, effective_build, ready_builds: string[]}, gpu: {available, name}, threads, wow_build, mismatch: {simc, data, simc_wow_version, data_build, game_build} }` |
| POST | `/api/simc/install` | `{tag?: string}` (default latest weekly) | `Job` |
| POST | `/api/data/refresh` | `{build?: string}` | `Job` |
| GET | `/api/data/season` | | contents of `data/season.json` |
| GET | `/api/data/loot/sources` | `?klass=&spec=` | `{ raids: [{instance_id, name, difficulties: [{name, ilevel}], bosses: [{encounter_id, name, order}]}], dungeons: [{instance_id, name}], key_levels: [{level, ilevel}], world_bosses: [...], delves: [{tier, ilevel}], crafted: {...} }` |
| GET | `/api/data/items/{id}` | `?bonus_ids=1/2/3&ilevel=` | `Item` |
| GET | `/api/data/talents/{klass}/{spec}` | | `{ class_tree: Node[], spec_tree: Node[], hero_trees: [...] }` |
| POST | `/api/data/talents/decode` | `{klass, spec, loadout}` | `{ selected: {node_id: rank}[] , hero_tree }` |
| POST | `/api/data/talents/encode` | `{klass, spec, selections, hero_tree?}` | `{ string }` -- inverse of decode; `selections` is either a `decode()` result or its bare `selected` list |
| POST | `/api/data/talents/modify` | `{klass, spec, base, add: string[], remove: string[]}` | `{ string, changes: {action, name, node_id, section}[], errors: string[], points }` -- resolves talent names (case-insensitive spell/definition name; choice nodes: name the entry), removes then adds at max rank, validating point budgets/gates/prerequisites; illegal edits are skipped and reported per talent in `errors` rather than baked into `string` |
| POST | `/api/data/talents/names` | `{klass, spec, loadout}` | `{ class: string[], spec: string[], hero: string[], hero_tree }` -- selected talent names grouped by section, `" (N)"` suffix above rank 1 |
| POST | `/api/import/simc` | `{text}` | `CharacterProfile` |
| GET | `/api/import/armory` | `?region=&realm=&name=` | `CharacterProfile` (best effort, raider.io public) |
| GET | `/api/import/addon` | | `{installed: boolean, wow_dir: string\|null, files: string[], captures: AddonCapture[]}` -- see "Import from addon" |
| POST | `/api/import/addon` | `{key?: string\|null, all?: boolean}` (default `{}`) | `CharacterProfile`, or `AddonImportResult[]` when `all: true` -- see "Import from addon" |
| POST | `/api/sims/quick` | `{profile, options}` | `Job` |
| POST | `/api/sims/topgear` | `{profile, options, candidate_keys: string[], max_combos: number, smart: boolean, min_ilevel?: number}` | `Job` |
| POST | `/api/sims/droptimizer` | `{profile, options, sources: DropSource[], upgrade: "drop"|"max"|number, min_ilevel?: number}` | `Job` |
| POST | `/api/sims/statweights` | `{profile, options, stats: string[]}` | `Job` |
| POST | `/api/sims/gearcompare` | `{profile, options, sets: [{name, changes: Record<slot, Item>}]}` | `Job` |
| POST | `/api/sims/talentcompare` | `{profile, options, loadouts: [{name, string}]}` | `Job` |
| POST | `/api/sims/advanced` | `{simc_text, options?}` | `Job` |
| GET | `/api/jobs` | | `Job[]` |
| GET | `/api/jobs/{id}` | | `Job` |
| GET | `/api/jobs/{id}/events` | SSE | events `progress` (Job), `done` (Job), `failed` (Job) |
| POST | `/api/jobs/{id}/cancel` | | `Job` |
| GET | `/api/jobs/{id}/result` | | `SimResult` |
| GET | `/api/jobs/{id}/input` | | text/plain .simc |
| GET | `/api/jobs/{id}/report.html` | | self-contained HTML report |
| GET | `/api/history` | | `{id, type, character, spec, created, summary: string}[]` |
| DELETE | `/api/history/{id}` | | `{ok}` |
| GET | `/api/settings` | | `Settings` (see backend/src/toonopt/config.py) |
| PUT | `/api/settings` | partial `Settings` | `Settings` |
| GET | `/api/surrogate/status` | | `{ available: boolean, device: "cuda"\|"cpu"\|"unavailable", models: [{klass, spec, samples, val_mae_pct, trained_at}] }` |
| POST | `/api/surrogate/train` | `{klass, spec, min_samples?: number, epochs?: number}` | `Job` (job type `surrogate_train`; result is `{samples, val_mae_pct, epochs, device, path}`) |

```ts
type DropSource =
  | { type: "raid"; instance_id: number; difficulty: "lfr"|"normal"|"heroic"|"mythic"; bosses?: number[] }
  | { type: "dungeon"; instance_ids?: number[]; key_level: number }        // key_level 0 = mythic0, -1 = vault (max)
  | { type: "world_boss" }
  | { type: "delve"; tier: number }
  | { type: "crafted"; ilevel: number; stats: [string, string] }
```

Errors: FastAPI default `{detail: string}` with 4xx/5xx.

### Import from addon [D: addon_import.py]

The in-game ToonOptimizer addon keeps the `/simc` export in SavedVariables, which WoW only writes on
`/reload`, logout or exit: `<wow_dir>/_retail_/WTF/Account/<ACCOUNT>/SavedVariables/ToonOptimizer.lua`
(`wow_dir` from Settings; may also point at `_retail_` itself). The addon counts as installed when
`_retail_/Interface/AddOns/ToonOptimizer/ToonOptimizer.toc` exists.

```ts
type AddonCapture = {
  key: string                  // "Name-Realm", as stored by the addon
  account: string              // WoW account folder the capture came from
  name: string; realm: string
  class: string                // e.g. "HUNTER"
  spec: string; ilvl: number | null
  captured_at: string          // ISO8601 UTC, from the addon's epoch seconds
  saved_slug: string           // characters slug this capture maps to
  saved_imported_at: string | null  // imported_at of the saved profile, null if not saved yet
  newer_than_saved: boolean    // captured_at > saved_imported_at (true when nothing saved)
}
```

- `GET /api/import/addon` -> `{installed, wow_dir (null when unset), files: string[], captures: AddonCapture[]}`.
  Captures are newest first; a key present in several accounts keeps its newest; entries without a
  `simc` string are skipped, and a malformed file is skipped with a logged warning. Never errors.
- `POST /api/import/addon` body `{key?: string|null, all?: boolean}` (body optional). No `key` imports the
  newest capture; `key` imports that `Name-Realm` (case-insensitive) and always overwrites. Either returns a
  `CharacterProfile` parsed like `/api/import/simc`, saved to the Characters store with `source: "addon"`
  and `imported_at` = the capture's `captured_at`.
  `all: true` instead returns `AddonImportResult[]`, one per capture, newest first, each isolated from the
  others (one failure never aborts the batch or turns it into a 4xx):
  ```ts
  type AddonImportResult = {
    key: string
    status: "imported" | "skipped" | "error"  // skipped: saved profile is not older than the capture
    detail: string | null                     // reason for skipped/error, else null
    profile: CharacterProfile | null          // only when imported
  }
  ```
  Errors: 404 when there is no addon data ("No ToonOptimizer addon data found. Install the addon, log in,
  then /reload or log out -- WoW only writes addon data then.") or the key is unknown; 422 when a single
  `key`/newest import fails to parse (never for `all`).
- `saved_slug` is derived from the export's `server=` token (like a paste), falling back to the realm part
  of `key`; `realm` stays the display name.

`smart: true` on `/api/sims/topgear` is experimental: if a GPU surrogate model has been
trained for the profile's (klass, spec) (`toonopt.surrogate`, `POST /api/surrogate/train`),
it scores every valid gear combination (bounded by an internal ~2M hard cap) and sims only
the best `max_combos` of them (plus every single-item swap) exactly through SimC, setting
`predicted_dps` on those rows. Without a trained model it falls back to the normal 2-stage
pruning search and reports that in the job's `progress.message`.

`min_ilevel` (both routes, optional, default `null` = no filter) drops bag/vault/loot
candidates below the given item level before any simming happens, so they are never sent to
SimC. On `/api/sims/topgear` it only ever removes candidates (equipped items are always kept,
even if below the threshold). On `/api/sims/droptimizer` it filters the drop candidates
returned by the loot data layer before profilesets are built; a job's `progress.message`
reports how many candidates were skipped this way.

`wow_build` (in `Settings`) is the live game build: `wow_build_override` if set (an
explicit pin, empty by default = auto), else whatever was last read from `<wow_dir>/.build.info`.
It is re-detected on every backend startup and on every `GET /api/status`/`POST /api/data/refresh`
call, so it tracks a live game patch without a restart; `PUT /api/settings` rejects a direct
`wow_build` write (set `wow_build_override` instead).

Game-data reads (item/talent/loot resolution -- everything under `toonopt.data.*`) do **not**
always read the live build: `toonopt.data.wago.effective_build()` is the live build if its DB2
cache is fully downloaded, otherwise the newest fully-cached build on disk, otherwise the live
build anyway. This is what keeps a fresh WoW patch (client updates, `<wow_dir>/.build.info`
changes, `wow_build` follows it) from turning every imported item into a bare, unresolved stub
the instant the client patches but before `data/cache/<new build>/` has been downloaded --
reads keep serving the last build that's actually cached. The backend also submits a background
`data_refresh` job for the live build automatically on startup whenever its cache isn't ready
(never blocking startup, and never auto-installing SimC -- that stays a user click). `data` in
`/api/status` is `{build, cached_tables, ready, refreshed_at}` for whichever build was asked
about, plus `effective_build` (what reads are actually using right now) and `ready_builds`
(every fully-cached build on disk, newest first).

`/api/status.mismatch` flags when the installed SimC or the game-data build actually being read
has fallen behind the current `game_build`: `simc` compares `major.minor.patch` only (a SimC
binary lagging just the trailing hotfix/build number is fine); `data` compares `game_build`
against `effective_build`, which can differ after a patch until "Refresh data" catches up (or
the automatic startup refresh finishes). `simc_wow_version` and `data_build` (the effective
data build) are the raw values being compared, for the UI to explain the mismatch.

`CharacterProfile.warnings` and `Item.resolved` surface the same failure mode at import time:
if an item's id can't be resolved against the data layer (unknown id, cache missing for the
build in play, etc.) the item comes back as a bare, unenriched stub with `resolved: false`, and
the profile gets one aggregated warning (not one per item) naming how many items failed and why,
telling the user to refresh data in Settings.
## Upgrades, Gems & Enchants, Recommendations

Job types `upgrades` and `gems` are added to `JobType` in models.py.

## Recommendations

GET `/api/data/recommendations?klass=&spec=` →
```ts
{
  season: string,                                // e.g. "Midnight Season 2 (12.1)"
  gems: {
    default: GemRef,                             // the season gem for this spec's best secondary
    by_stat: Record<"crit"|"haste"|"mastery"|"versatility", GemRef>,
    unique: GemRef[]                             // unique-equipped / limited gems worth one socket, if any this season
                                                 // (`limit` + `limit_category`: max equipped per character, per category)
  },
  enchants: Record<slot, EnchantRef[]>,          // options per enchantable slot, recommended first
  consumables: { flask, food, potion, augmentation, temporary_enchant }   // SimC names
}
type GemRef = { id: number; name: string; icon: string; stat: string; limit?: number; limit_category?: string }
type EnchantRef = { id: number; name: string; icon?: string; stat?: string; recommended: boolean }
```
Backed by `toonopt.data.season.recommendations(klass, spec)`. Names/icons via the Item and
SpellItemEnchantment tables. `best_gems`/`best_enchant` must agree with this (single source).

## Upgrades

POST `/api/sims/upgrades` body:
```ts
{ profile, options, slots?: string[],            // default: every equipped slot with an upgrade track
  max_ranks?: number | null,                     // default: up to the track maximum
  min_ilevel?: number | null }
```
One profileset per (slot, target rank strictly above current). Result rows:
```ts
ResultRow.meta.changes = { [slot]: upgradedItem }        // Item with the new rank's bonus ids + ilevel
ResultRow.meta.upgrade = {
  slot, item_id, track: string,                          // "Veteran"|"Champion"|"Hero"|"Myth"|...
  from_rank, to_rank, max_rank, from_ilevel, to_ilevel,
  crest: string,                                         // crest type name for this step of the track;
                                                          // matches a Currency.crest string exactly
  cost: number,                                          // crests from from_rank to to_rank
  steps: { rank: number; ilevel: number; crest: string; cost: number }[],
  affordable: boolean | null                             // cost <= the profile's Currency.amount for `crest`;
                                                          // null when the profile has no currency info at all
}
```
Label: `"Head: Hero 3/6 → 5/6 (ilvl 312 → 318, 30 Gilded)"`. Items without a recognised track are
skipped and counted in progress message. Backed by `toonopt.data.season.upgrade_path(item) ->
list[UpgradeStep]` (track detected from bonus ids via bonuses.py upgrade groups; costs from
season.json `upgrade_tracks[*].ranks[*].{ilevel, crest, cost}`; port localbots `crests.js` if
the cost table is missing). `affordable` lets the Upgrades page default its "Suggested spend"
crest inputs to what `CharacterProfile.currencies` actually reports for the player, instead of
always starting from zero.

## Gems & Enchants

POST `/api/sims/gems` body:
```ts
{ profile, options,
  mode: "uniform" | "per_socket" | "custom",
  gem_pool?: number[],                 // default: recommendations.gems.by_stat values + unique
  include_enchants?: boolean,          // default true: add one row per (slot, enchant option) from recommendations.enchants
  enchant_slots?: string[],
  sets?: { name: string; gems: Record<slot, number[]>; enchants: Record<slot, number> }[]   // custom mode
}
```
- uniform: rows = one per gem in the pool, every socket on every equipped item filled with it,
  plus a row "Recommended" (= recommendations default/unique mix). Baseline keeps current gems.
- per_socket: rows = one per (item socket, gem in pool); label `"Neck socket 1: Haste gem"`;
  `meta.gem = { slot, socket_index, gem_id, gem_name, stat }`.
- custom: rows = the given sets; `meta.changes` = items with the new gem_ids/enchant_id.
- enchants (any mode when include_enchants): rows per (slot, option) that differs from current;
  `meta.enchant = { slot, enchant_id, name, stat }`.

Unique-equipped gems: limits are per ItemLimitCategory, shared across gem ids (every Eversong Diamond,
any variant or rank, counts against "Thalassian Diamond", max 1). `season.gem_limit(gem_id)` reads it
from ItemSparse.LimitCategory / ItemLimitCategory.Quantity. No generated row exceeds a limit:
- uniform, limited gem: placed in at most `limit` sockets -- a socket already holding that category
  (swap in place), else the neck, else the first socket in slot order. Every other socket keeps its
  current gem. Label `"Neck: Indecipherable Eversong Diamond, other sockets unchanged"`.
- uniform, stat gem: fills every socket except a limited gem the character already wears, which stays;
  label `"All sockets: Haste gem (kept Indecipherable Eversong Diamond in Finger1)"`.
- per_socket: the tested socket wins; another socket over the limit gets the spec's default stat gem and
  the label says so: `"Neck socket 1: Powerful Eversong Diamond (Finger1 Indecipherable Eversong Diamond
  -> Mastery gem: unique-equipped)"`; that item is in `meta.changes` too.
- Recommended: `best_gems` per item, then fitted to the limits (one diamond kept, never invented).
- custom: sets are simmed as given; a set over a limit adds a note to `SimResult.notes`.
- Rows identical to the current gems (e.g. the diamond is already in its socket) are dropped.

Enchant notes: slots whose only enchants are utility (Midnight head/shoulder/feet: speed, leech,
avoidance; `dps: false` in season.json `enchant_options`, `season.utility_enchant_slots()`) are named
in their own note; slots with no enchant at all (neck, back, wrist, hands, waist, trinkets) in another.
Socket count per item from `best_gems` logic (bonus ids). Cap rows at 400 with a clear error.

Add to `ResultMeta`: `upgrade?: UpgradeInfo`, `gem?: GemChange`, `enchant?: EnchantChange`.

## Frontend

- Nav: "Upgrades" and "Gems & Enchants" pages after Droptimizer.
- Upgrades page: slot checklist (default all upgradeable, shows current track/rank per slot),
  max ranks, run; results ranked by gain with columns gain, cost, gain per crest; a
  "Suggested spend" card: inputs for crests owned per type, greedy pick of best gain-per-crest
  rows (one per slot, non-overlapping) within budget, showing total predicted gain (labelled as
  a sum of independent sims).
- Gems page: mode tabs; pool picker (chips with gem icons); enchant toggle; custom set editor
  (per equipped item: N socket selects + enchant select) with a "Use recommended" button that
  fills from `/api/data/recommendations`; results as ranked bars; in per-socket mode also a
  "best per socket" summary table.
- OptionsPanel: tooltips on socket_all / enchant_all name the recommended gem and enchants
  (fetch recommendations once per profile spec).
- History labels for the two new job types.
## Raidbots parity, wave 1

All additive. Job types unchanged. Owners in brackets are the implementing agents.

### SimOptions additions [C: simc/input.py, simc/results.py, jobs.py]
```ts
fight_style: ... | "TargetDummy" | "ExecutePatchwerk"
  // Neither is a real SimC fight_style (verified against SimC 1210-01: both raise "Invalid
  // fight style"); both emit fight_style=Patchwerk instead, plus an explicit enemy= block:
  // TargetDummy: fight_style=Patchwerk, optimal_raid=0, every override.*=0 (including the
  //   override.blessing_of_the_bronze=1 every other fight style gets), all consumables
  //   disabled regardless of the request, then AFTER the actor lines:
  //   enemy=Target_Dummy + enemy_fixed_health_percentage=100
  // ExecutePatchwerk: buffs/consumables unaffected; after the actor lines, one
  //   enemy=Execute_Target_N + enemy_initial_health_percentage=20 per target (desired_targets,
  //   1-indexed) -- desired_targets itself is left as requested, it isn't forced to N
  // DungeonSlice: server forces max_time=360, desired_targets=1; 400 for demon_hunter havoc/vengeance/devourer
buffs.power_infusion?: boolean      // default false -> external_buffs.power_infusion=0/120/240... up to
  // (not including) the effective max_time; an actor-scoped option (emitted inside the actor
  // block, like flask=/potion=), confirmed against SimC 1210-01's own external_buffs.power_infusion
precision?: "low" | "medium" | "high" | null
  // staged Smart Sim for any profileset sim: stage 1 target_error=1.0, keep rows with dps+err >= max(dps-err),
  // stage 2 0.2, stage 3 (medium) 0.1, (high) 0.05. null = single pass with iterations/target_error as today.
metric?: "dps" | "prioritydps" | "dtps" | "hps" | "dmg_taken"     // default dps; emits profileset_metric=dps,prioritydps,dtps,hps,dmg_taken always
expert?: { header?: string; pre_actor?: string; post_actor?: string; footer?: string }
  // raw SimC lines spliced at those positions (header: very top of the file; pre_actor: after
  // globals, before the actor block; post_actor: right after the actor block/gear/enemy lines;
  // footer: very end, after profilesets); threads=, json2=, html=, output=, xml=,
  // profileset_work_threads= lines are always stripped since those stay under the runner's/job
  // manager's own control
```
Metrics -- exact json2 paths (verified by running a real 3-profileset sim with
`profileset_metric=dps,prioritydps,dtps,hps,dmg_taken`, always emitted; see simc/results.py's
module docstring for the full trace):
* `sim.profilesets.metric` / `results[].mean` / `.mean_error` / `.mean_stddev` — display name +
  value of whichever metric is FIRST in `profileset_metric` (always "dps"/"Damage per Second"
  here, since the list order above is fixed).
* `sim.profilesets.results[].additional_metrics[]` — one `{metric: <display name>, mean, ...}`
  per remaining `profileset_metric` entry; display names: "Damage per Second", "Damage per
  Second to Priority Target/Boss", "Damage Taken per Second", "Healing per Second", "Damage Taken".
* `sim.players[0].valid_fight_style` — bool, straight into `SimResult.valid_fight_style`.
* Baseline (no profileset row of its own) reads `sim.players[0].collected_data`: `dps.mean` and
  `hps.mean` are named as expected; `target_metric.mean` is prioritydps (falls back to dps when
  the run never tracked a separate priority target, e.g. no adds); SimC's own `dtps` key there is
  actually the fight-total damage taken, not a per-second rate (confirmed: `dtps.mean /
  fight_length.mean` reproduces the profileset "Damage Taken per Second" figure to ~1%), so it
  backs `dmg_taken` directly and is divided by fight length for `dtps`.
Results:
```ts
ResultRow.meta.stage?: number            // highest precision stage this row reached (1..3)
ResultRow.metrics?: Record<string, number>   // every metric SimC returned for the row
SimResult.baseline.metrics?: Record<string, number>
SimResult.metric: string                 // the metric rows AND baseline.dps are reported/sorted on;
  // sorted descending except dtps/dmg_taken (lower is better); delta/delta_pct are computed on
  // this metric too -- baseline.dps and every row's dps mirror whichever metric was requested,
  // not necessarily literal dps, so existing dps-reading UI/engines are unaffected when metric
  // defaults to "dps"
SimResult.valid_fight_style?: boolean    // json2 players[0].valid_fight_style
```
Routes: `GET /api/jobs/{id}/simc.html` — SimC's own HTML report (jobs pass html=True + report_details=1
in the input text; persisted as `simc.html` in the job's history directory).

### CharacterProfile additions [D: simc/profile.py]
```ts
saved_loadouts: { name: string; string: string; kind: "active" | "saved" }[]   // from the export's loadout comments
loot_spec: string | null                  // "# loot_spec=" if present
high_watermarks: Record<string, number>   // "# slot_high_watermarks=" slot -> ilvl, for gold-only upgrades later
```

### Item search [D: data/items.py, api/data.py]
`GET /api/data/items/search?q=<name substring>&klass=&spec=&slot=&limit=25` →
`{ items: [{ id, name, icon, quality, inventory_type, slot, base_ilevel, expansion_hint?: string }] }`
filtered to items the spec can equip (loot.usable_slots), current expansion first.
`GET /api/data/items/{id}?bonus_ids=&ilevel=&track=&rank=` — existing route gains `track`+`rank`
(e.g. track=Myth&rank=3) which resolves the bonus ids and ilevel via season upgrade tracks. Returned
Item key is `search:<id>:<bonus>`.

### Top Gear request additions [A: sims/topgear.py, sims/base.py]
```ts
loadouts?: { name: string; string: string }[]   // each combo is simmed per loadout (profileset adds talents=); combo cap applies to the product
extra_items?: Item[]                             // items from search, treated like bag candidates (key "search:...")
```
Rules: at most ONE `vault:` item per combination; existing unique/limit rules unchanged.
`ResultRow.meta.loadout` carries the loadout name when loadouts were used.

### Droptimizer request additions [B: sims/droptimizer.py, data/loot.py]
```ts
upgrade_equipped?: "none" | "match" | "max"     // upgrade the baseline's equipped gear along its track: none (default) / to the drop upgrade level / to max
include_offspec?: boolean                       // default false
DungeonSource.vault?: boolean                   // true = use the vault ilvl for that key level instead of end-of-dungeon
```
Result:
```ts
SimResult.groups?: { key: string; label: string; kind: "boss" | "dungeon" | "delve" | "world_boss" | "crafted"; n: number;
                     best: number; best_pct: number; best_label: string; ev: number; ev_pct: number; upgrade_share: number }[]
// per item take the best of its slot rows first; best = max delta; ev = mean(max(0, delta)) assuming each item equally likely; upgrade_share = share of items with delta > 0
```
Notes list the slots upgraded by upgrade_equipped.

### Frontend [E]
- OptionsPanel: fight style list with the two new styles and DungeonSlice guard (disable for the three DH specs, force 360 s / 1 target); Power Infusion toggle; Precision select (Off / Low / Medium / High with "Smart Sim: staged 1% → 0.2% → 0.05%" help); Metric select (shown for tanks by default: dtps); Expert mode collapsible with four textareas.
- Import: list saved loadouts; talent override becomes a dropdown of them (plus custom).
- Talent Compare: seeds one card per saved loadout.
- Top Gear: loadouts multi-select; "Add item" search box (name → pick → track/rank → added as candidate with key search:...); results: stage chip per row when precision was used; "Sidegrades" grouping (rows with dps >= top.dps - 2*top.dps_error) with a "Prefer fewest changes" toggle.
- Droptimizer: "Upgrade my equipped gear" select; "Include off-spec" toggle; per key-level "Vault" toggle; results gain a "Group by" tab (boss / dungeon / delve) showing Best, Expected value, Upgrade share, with a note that EV assumes equal drop odds.
- Result views: metric-aware axis label, lower-is-better handling, and a "SimC report" link to /api/jobs/{id}/simc.html.
## Raidbots parity, wave 2 (Catalyst, sockets, Voidforge, crafted, consumables, Omnium)

Facts verified against SimC 1210-01 and DB2 12.1.0.69933 (see research in scratchpad `w2/`):
- Catalyst piece in SimC = `<slot>=,id=<tier item id>,bonus_id=<source's bonus ids>,gem_id=…,enchant_id=…,redirected_base_stats=<source item id>`; bonus 13662 is optional (no effect in SimC). Set bonuses are counted from item ids; json2 does not expose them, count set pieces locally by `set_id`.
- Season 37 catalyst mapping: scratchpad `catalyst_s37.json` (13 classes × 9 slots: head/shoulder/chest/hands/legs tier + back/wrist/waist/feet; inventory type 20 robe → chest). Currency 3465 (Venomblight Manaflux) = catalyst charges.
- Sockets: add-socket bonus id **1808** (Raidbots parity); 8781 = 2 sockets, 8782 = 3. SimC applies every `gem_id` regardless of sockets, so the app must cap gems to socket count. Vault socket slots: head, wrist, waist; Jewelbinder (item 263897) socket: neck, finger.
- Voidforge: only Myth exists this season: replace the Myth track bonus (12849-12854) with **13848** → ilvl 344. No Hero/crafted variant. `bonuses.ilevel_from_bonuses` must take the max ilvl on priority ties (bug: `[12854,13848]` returns 334).
- Crafted: `crafted_stats=A/B` with A,B ∈ {32 crit, 36 haste, 40 vers, 49 mastery}; bonus ids 8790-8795 override crafted_stats → strip them when overriding; quality via bonus 12497 (max); `crafting_quality=` is cosmetic; embellishments = their bonus id (+8960 marker), max 2 embellished items enforced by app.
- Omnium Folio: TraitTree 1186, 5 rows, one choice per row; profileset line `omnium_talents=<entry>:1/<entry>:1/...` (entry ids and name tokens both accepted); scratchpad `omnium_tree_1186.json` has rows/choices/names/icons. App enforces one per row.
- Consumables: accepted SimC names in scratchpad `consumables_s37.json` (always use explicit `_2` quality suffix for flasks/potions/oils). Vantus rune = actor line `set_custom_buff=vantus,stat_value=162_versatility`.

### season.json additions [data agent]
```
catalyst: { conversion_id: 13, currency_id: 3465, slots: [...], set_ids: {klass: id}, items: {klass: {inventory_type: item_id}}, set_bonus_spells: {klass: {spec: {2: id, 4: id}}} }
sockets: { add_bonus_id: 1808, two: 8781, three: 8782, vault_slots: [head, wrist, waist], jewelbinder_slots: [neck, finger1, finger2], jewelbinder_item: 263897 }
voidforged: { slots: [...], myth_ilevel: 344, bonus_id: 13848 }          // remove hero_ilevel / crafted_ilevel
crafted: { stat_ids: {crit: 32, haste: 36, versatility: 40, mastery: 49}, stat_bonus_ids: [8790..8795], quality_bonus_max: 12497, embellishments: [...existing...], embellish_marker: 8960, max_embellished: 2 }
omnium: { tree_id: 1186, rows: [{row, node_id, choices: [{entry_id, token, name, icon}]}] }
consumables.options: { flask: [...], food: [...], potion: [...], augmentation: [...], temporary_enchant: [...] }   // SimC names accepted by this binary
```
`/api/data/season` returns all of it; `/api/data/recommendations` gains `catalyst: {charges_currency_id, slots}` and `omnium: rows`.

### Requests [engine agent]
Top Gear:
```ts
catalyst?: { keys: string[]; min_set_pieces?: 0|2|4 }   // candidate keys to also offer as their catalyzed twin (key "catalyst:<orig key>"); combos may not catalyze more items than profile.catalyst_charges (null = unlimited); min_set_pieces rejects combos below it
add_socket?: { keys: string[]; gem_id?: number }       // offer a +socket variant (bonus 1808 + preferred/default gem) for those items; at most one vault-socket item per combo in vault_slots
voidforge?: { keys: string[] }                          // offer the Myth voidforged twin for max-Myth items in voidforged.slots
crafted?: { key: string; stats: [string,string]; embellishment_id?: number; quality_bonus?: number }[]   // recraft variants of owned crafted items (strip 8790-8795, set crafted_stats)
```
Droptimizer:
```ts
include_catalyst?: boolean      // every drop in a catalyst slot also gets its catalyzed twin (source "catalyst")
add_socket?: boolean            // drops in vault_slots get bonus 1808 + default gem
preferred_gem?: number
sources += { type: "catalyst"; track: string; rank?: number }   // your equipped/bag items catalyzed at that track (uses charges)
```
Upgrades: rows for Myth-max weapons/trinkets gain a "Voidforge" step (ilvl 344, cost: 1 Ascendant Voidcore if a currency id is known, else unknown) with `meta.upgrade.track = "Voidforged"`.
New sim types:
- `POST /api/sims/consumables` `{profile, options, categories?: ("flask"|"food"|"potion"|"augmentation"|"temporary_enchant")[], custom?: {name, flask, food, potion, augmentation, temporary_enchant}[]}` → one profileset per option per category (others held at current), plus custom sets. `meta.consumable = {category, name}`. JobType "consumables".
- `POST /api/sims/omnium` `{profile, options, mode: "per_row"|"combos"|"custom", sets?: {name, entries: number[]}[]}` → per_row: for each row, each choice with other rows fixed at current; combos: full cross product (≤ 72); `meta.omnium = {row, entry_id, name}` or `meta.loadout` for combos. JobType "omnium". Current selection parsed from the profile's `omnium_talents=` header line → `CharacterProfile.omnium: {entry_id: rank}`.
Result rows for catalyst/socket/voidforge/crafted variants carry the variant `Item` in `meta.changes` with `key` prefixes `catalyst:`, `socket:`, `voidforge:`, `crafted:` and a human label suffix "(Catalyst)", "(+socket)", "(Voidforged)", "(recraft Crit/Haste)".

### Frontend [E2]
- Top Gear: candidate rows get variant toggles (Catalyst when the slot is catalyzable and charges remain, +Socket for vault slots, Voidforge for eligible Myth-max items); a "Catalyst charges" chip with the count from the profile; "Minimum set pieces" select (0/2/4); crafted items get a "Recraft…" popover (stat pair, embellishment, max quality).
- Droptimizer: "Include Catalyst versions" toggle, "Add vault socket" toggle with preferred gem select, a "Catalyst" source card (track/rank) alongside raids; catalyst rows show a Catalyst chip.
- Upgrades: Voidforge steps shown with their own chip.
- New page "Consumables": category checkboxes, run, ranked bars grouped by category; custom set editor.
- Talent Compare gains an "Omnium Folio" tab: 5 rows with the choices as icon buttons showing the current pick; Per row / Combos / Custom modes; results ranked with the row/choice label.
- Options: Vantus rune toggle (raid buff list) and consumable dropdowns populated from `season.consumables.options` instead of free text ("SimC default", named options, "None").

### Engine notes / precision [implemented in sims/topgear.py, sims/droptimizer.py, sims/upgrades.py, sims/consumables.py, sims/omnium.py, models.py, api/sims.py, simc/input.py, simc/profile.py]

Additive Python-level shapes backing the wire contract above (not already spelled out precisely):
```ts
// models.py
SourceType += "catalyst"
JobType += "consumables" | "omnium"
Group.kind += "catalyst"
CharacterProfile.omnium: Record<number, number>          // entry_id -> rank, parsed from "omnium_talents="
SimOptions.buffs.vantus_rune?: boolean                    // default false; DEFAULT_BUFFS entry
ResultMeta.consumable?: { category: "flask"|"food"|"potion"|"augmentation"|"temporary_enchant"; name: string }
ResultMeta.omnium?: { row: number; entry_id: number; name: string }
DropSource += { type: "catalyst"; track: string; rank?: number }   // CatalystSource
```
`/api/sims/topgear` request gains `catalyst?: {keys, min_set_pieces}`, `add_socket?: {keys, gem_id?}`,
`voidforge?: {keys}`, `crafted?: [{key, stats, embellishment_id?, quality_bonus?}]` per the contract above
(Pydantic models `CatalystRequest`/`SocketRequest`/`VoidforgeRequest`/`CraftedRequest` in `sims/topgear.py`,
mirroring how `Loadout`/`GearSet`/`GemSet` already live next to their engines). `/api/sims/droptimizer` gains
`include_catalyst`, `add_socket`, `preferred_gem`. `/api/sims/consumables` body additionally accepts
`custom[]` as `CustomConsumableSet` (`sims/consumables.py`); `/api/sims/omnium` `sets[]` is `OmniumSet`
(`sims/omnium.py`). Both new routes 503 when the season data layer isn't ready and cap rows (consumables
300, omnium 100 -- `TooManyRows`, surfaced as a failed job like Gems'/Upgrades' own caps, not a 400) --
`omnium`'s `combos` mode tops out at 72 for this season's 5-row/2-3-1-4-3-choice tree, well under the cap.
`omnium`'s `custom` mode additionally rejects (`ValueError`, failed job) an entry set naming two choices in
the same row, per the "enforce one per row" rule.

`item_line()` (`simc/input.py`) already renders any token on `Item.simc_string` that isn't one of its known
fields (id/bonus_id/ilevel/gem_id/enchant_id/crafted_stats/crafting_quality) verbatim as an "extra" --
`redirected_base_stats=<source item id>` falls out of this for free for every catalyzed twin (`catalyst_variant`
appends it to `simc_string`) and for any already-catalyzed item straight from a `/simc` export; verified against
a real SimC run (`tests/test_integration.py::test_topgear_catalyst_variant_end_to_end`). No change to that
function was needed.

Voidforge `affordable` (Upgrades) reuses the same `Currency.crest`-matching helper every other upgrade step
uses, checked against the literal crest name `"Ascendant Voidcore"` -- `season.json`'s `voidforged` block
carries no dedicated currency id this wave (see data/README.md), so "if a currency id is known" is
approximated by name; `None` unless the profile happens to carry a currency resolved to that name.

`SimOptions.consumables` (free strings, all sim types) now validates non-empty values against
`season.consumable_options()` in `validate_options()` (`simc/input.py`, called by every `/api/sims/*` route
via `_submit`) and raises `ValueError` -> 400 `{detail: "invalid <key> '<value>'; valid options: [...]"}` on a
mismatch; `temporary_enchant` accepts the season's `main_hand:...` option mirrored onto `off_hand:...` for
dual-wielders, since the catalogue only lists the main_hand form. Skipped entirely (free strings stay free)
when the season data layer isn't importable.

## Characters, Advisor, Reports

### Characters (server-side store of imported profiles)
Every successful `POST /api/import/simc` and `GET /api/import/armory` also saves the profile to
`characters/<slug>.json` (slug = `name-realm` lowercased, ascii, e.g. `thrall-area-52`), keeping
`characters/<slug>.history/<imported_at>.json` (last 10). Directory `characters/` at repo root, gitignored.
- `GET /api/characters` -> `[{slug, name, realm, klass, spec, ilevel_equipped, imported_at}]`
- `GET /api/characters/{slug}` -> `CharacterProfile` (latest)
- `DELETE /api/characters/{slug}` -> `{ok}`
Backfill: on startup, if `characters/` is empty, seed it from the newest `history/*/profile.json` per character
(`toonopt.characters.backfill`, called from `toonopt.main`'s lifespan hook -- not at router import time, so it
never fires in a plain `TestClient(app)` that isn't used as a context manager, matching how
`_maybe_start_data_refresh` already behaves in tests).
`ilevel_equipped` is the mean item level over `CharacterProfile.equipped` (no 2H double-counting).

### Advisor
`POST /api/advisor/obvious-upgrades` body `{slug?: string, profile?: CharacterProfile, options?: {key_level?: number, delve_tier?: number, raid_difficulties?: string[], min_ilevel_gain?: number, include_downgrades?: boolean}}`
(`include_downgrades` -- default `false` -- is an additive field beyond the originally sketched options
shape, needed to make the "downgrade... excluded unless `include_downgrades`" verdict rule below reachable
from the API at all.)
Synchronous (no SimC), returns:
```ts
type AdvisorResult = {
  slug: string; character: string; klass: string; spec: string; generated_at: string
  stat_priority: { source: "statweights_job" | "recommendation"; order: string[]; weights?: Record<string, number>; job_id?: string }
  ilevel_equipped: number
  slots: AdvisorSlot[]
  tier: { set_id: number | null; equipped_pieces: number; slots_with_tier: string[]; catalyst_charges: number | null }
  sim_plan: { droptimizer: DropSource[]; topgear_candidate_keys: string[]; upgrades_slots: string[]; note: string }
  notes: string[]
}
type AdvisorSlot = {
  slot: string
  equipped: { item: Item; ilevel: number; stat_score: number; track?: string; rank?: string }   // rank "3/6"
  candidates: AdvisorCandidate[]          // sorted: obvious first, then by expected value desc
  bis_heuristic: AdvisorCandidate | null  // best candidate at max upgrade by ilevel then stat_score
}
type AdvisorCandidate = {
  item: Item                              // resolved at the acquisition ilvl (as dropped)
  max_item?: Item                         // same item fully upgraded on its track
  source: ItemSource & { effort: "trivial" | "easy" | "medium" | "hard" | "very_hard"; weekly?: boolean }
  ilevel_gain: number; ilevel_gain_max: number
  stat_score: number; stat_score_delta: number           // vs equipped, from stat_priority weights
  verdict: "obvious" | "likely" | "sim_to_confirm" | "sidegrade" | "downgrade"
  reasons: string[]                       // e.g. "+10 ilvl", "haste/crit matches priority", "trinket: effect needs sim", "loses 4pc"
  path: { step: string; crest?: string; cost?: number }[]   // stepping stones, e.g. ["Drop from Nek'zali (Heroic) 308", "Upgrade Hero 1/6->6/6 (75 Runed)"]
  alternatives: string[]                  // other sources of the same item id
}
```
Rules:
- Candidate pool: `loot.candidates` for current raids (LFR/Normal/Heroic/Mythic), M+ at `key_level` (default 10) end-of-dungeon and vault, delves at `delve_tier` (default 8) and 11, world bosses, crafted at max quality with the spec's best stat pair, catalyst twins of equipped/bag items in catalyst slots, and `season.upgrade_path`/`voidforge_variant` steps for equipped items (source type `"upgrade"`, an additive `SourceType`/`Item.source.type` value alongside wave 2's `"catalyst"`).
- Effort: bag/vault/upgrade-with-owned-crests = trivial; LFR/Normal/M+ <= 8/delve 8 = easy; Heroic/M+ 9-10/delve >8 = medium; Mythic raid/M+ 11+ = hard; last two Mythic bosses = very_hard; catalyst = trivial when the profile has catalyst charges, else easy. `weekly` set for Great Vault (dungeon) candidates and world bosses.
- stat_score = sum(weight[stat] * amount) over primary + secondaries using `stat_priority.weights` (from the newest `statweights` job for this character in `history/`, matched by `Job.character`; else `recommendations()`'s flask/gem secondary as the top slot, a per-spec heuristic order for the rest -- cited in `notes` -- mapped to weights 1.0/0.8/0.6/0.4 with primary 1.2).
- verdict: `obvious` if `ilevel_gain >= min_ilevel_gain` (default 6) and `stat_score_delta >= 0` and not a trinket/weapon/tier-piece-count change/embellishment; `likely` if `ilevel_gain >= 13` with `stat_score_delta < 0`; `sim_to_confirm` for trinkets, weapons, tier-piece-count changes (`"loses 4pc"`/`"loses 2pc"`/`"completes 4pc"`/`"completes 2pc"`), embellishments, or `|ilevel_gain| < min_ilevel_gain` with better stats; `sidegrade` if equal ilvl and stat_score within 2%; `downgrade` otherwise (excluded unless `include_downgrades`).
- Tier: equipped pieces counted by `set_id == catalyst_set_id(klass)`; a non-tier candidate replacing an equipped tier piece is downgraded to `sim_to_confirm` with reason `"loses 4pc"` (from 4) or `"loses 2pc"` (from 2); a catalyst/tier candidate replacing a non-tier piece gets `"completes 4pc"` (from 3) or `"completes 2pc"` (from 1) and the same `sim_to_confirm` treatment (a set-bonus swing is exactly the kind of non-linear result this heuristic can't score, so it always asks for a sim rather than ever calling it "obvious").
- Paths: for a drop at ilvl X on track T rank r, steps = `["<source name> (<difficulty|+key>) <X>", "Upgrade T r->max (<n> <crest>)"]` with `cost` (the second step only when the drop isn't already at its track's max); "stepping stone" alternatives fall out of the candidate pool itself -- every raid difficulty and both delve tiers are fetched together, so an easier/lower-ilvl source that still beats equipped is already a separate candidate in the same slot's list rather than a nested field.
- `sim_plan`: `droptimizer` is the exact `DropSource[]` used to build the candidate pool (plus a `CatalystSource` when any catalyst candidate was offered) -- directly postable to `/api/sims/droptimizer`; `topgear_candidate_keys` are the `item.key`s of non-downgrade bag/vault/catalyst candidates -- directly postable to `/api/sims/topgear`'s `candidate_keys`; `upgrades_slots` are equipped slots with a remaining upgrade-track rank.
- Multiple options per slot are expected: up to 8 candidates per slot, deduplicated by item id (other sources of the same id go to `alternatives`), with at least one candidate per effort tier represented when available before the cap.
- Candidate pool and `loot.candidates()` results are cached in memory per `(klass, spec, sources)` (`toonopt.advisor._CANDIDATES_CACHE`) so a repeat call for the same spec/options is fast -- this trades a little accuracy for characters of the same class/spec with an unusual weapon setup (e.g. dual-wield vs. two-hand) against the <10s budget, per this brief's explicit caching instruction.

### Reports (per character, maintained by the skill)
Stored at `reports/<slug>.json` (+ `reports/<slug>.md` rendered copy), gitignored. Routes:
- `GET /api/reports` -> `[{slug, character, klass, spec, updated_at, summary}]`
- `GET /api/reports/{slug}` -> `CharacterReport`
- `PUT /api/reports/{slug}` body `CharacterReport` (server sets `updated_at`, keeps `history: [{updated_at, summary}]` last 20 in a `<slug>.history.json` sidecar, newest first)
- `DELETE /api/reports/{slug}`
```ts
type CharacterReport = {
  slug: string; character: string; realm: string; klass: string; spec: string
  updated_at: string; ilevel_equipped: number; season: string; simc_version: string
  summary: string                                   // 2-4 sentences, plain prose
  sections: ReportSection[]                         // rendered in order
  advisor?: AdvisorResult                           // the raw advisor output used
  sim_refs: { job_id: string; type: string; label: string }[]   // links to History
  sources: { title: string; url: string; fetched_at: string }[] // theorycraft sources
}
type ReportSection =
  | { kind: "markdown"; title: string; body: string }
  | { kind: "upgrades"; title: string; rows: { slot: string; current: string; option: string; verdict: string; gain: string; how: string[]; sim?: { job_id: string; delta_pct: number } }[] }
  | { kind: "bis"; title: string; rows: { slot: string; item: Item; source: string; you_have: boolean; theorycraft_says?: string }[] }
  | { kind: "talents"; title: string; entries: { context: string; loadout: string; notes: string; source_url?: string }[] }
  | { kind: "kv"; title: string; items: { label: string; value: string; note?: string }[] }
```
`toonopt.models.CharacterReport` keeps `sections: list[dict]`, not a pydantic discriminated union;
`toonopt.reports.validate_report` checks each section's shape against its `kind` (`ReportValidationError` ->
400 on `PUT`) and `render_markdown` renders each kind as a markdown table for `<slug>.md`.
Frontend: "Reports" nav page: list of characters with a report (and characters without one, greyed, "run the
skill"), per-character view rendering sections; header with character, ilvl, updated_at, "Load this character"
button (sets the store profile from `/api/characters/{slug}`), links to sim_refs in History, sources list. A
small character switcher in the top bar listing `/api/characters`.

Advisor note (crafted gear): crafted candidates are the exception to the "one candidate per item id"
rule. One candidate is emitted per crafted tier from `season.crafted.tiers` (305 spark-only, 318 with
Hero crests, 331 with Myth crests), trimmed to the best tier the character can afford plus the max tier,
each with a cumulative path and "needs N more <crest>" reasons.
