# toonopt.data — game-data layer

Everything the sims need from the game client's own database, read only through this
package. Ported from [localbots](https://github.com/balovich-matje/localbots) (MIT, see
`/THIRD_PARTY.md`); the bonus-id / item-level / upgrade-track rules it discovered are kept
and re-verified against build 12.1.0.69875 (see each module's docstring for the evidence).

| module | public API |
|---|---|
| `wago.py` | `TABLES`, `ensure_tables(build, progress_cb=None, force=False)`, `refresh(build, progress_cb)`, `status(build)`, `table(name, build=None, columns=None)` |
| `items.py` | `resolve_item(item_id, bonus_ids, ilevel, *, key, slot_hint=None, gem_ids=(), enchant_id=None, crafted_stats=(), crafting_quality=None) -> Item`, `item_icon_url(icon)` |
| `season.py` | `load()`, `generate(build)`, `write(build)`, `consumables_for(klass, spec, role, primary)`, `best_enchant(slot, profile)`, `best_gems(item, profile)`, `delve_pool()`, `recommendations(klass, spec)`; wave 2 (Catalyst/sockets/Voidforge/crafted/Omnium): `catalyst()`, `catalyst_item_for(klass, inventory_type)`, `catalyst_set_id(klass)`, `catalyst_variant(item, klass)`, `socket_rules()`, `socket_variant(item, gem_id)`, `voidforge_variant(item)`, `crafted_variant(item, stats, embellishment_id=None, quality_bonus=None)`, `omnium_rows()`, `consumable_options()` |
| `loot.py` | `sources(klass, spec)`, `candidates(profile, sources, upgrade)`, `usable_slots(...)`, `primary_stat(klass, spec)` |
| `talents.py` | `tree(klass, spec)`, `decode(klass, spec, loadout)`, `spec_id(klass, spec)` |
| `bonuses.py` | bonus-id decoding (`upgrade_of`, `ilevel_from_bonuses`, `socket_count`, `season_tracks`) |
| `stats.py` | `compute(...)` item stats at an item level |
| `droplevels.py` | per-boss raid drop levels from `DungeonEncounter.ItemSequenceLevel` + bonus trees |

Cache: `data/cache/<build>/<Table>.csv` (49 wago.tools tables, ~140 MB for 12.1.0.69875,
about 90 s to download) plus Raidbots' `bonuses.json` and SimC's `sc_scale_data.inc`.
Derived files end in `.derived.json` and are rebuilt on refresh. Regenerate `data/season.json`
with `uv run python -m toonopt.data.season`; eyeball current items with
`uv run python -m toonopt.data.eyeball`.

## Season identification (12.1.0.69875)

* `MythicPlusSeasonTrackedMap.DisplaySeasonID` max = **37**: Kings' Rest, Temple of Sethraliss,
  Ruby Life Pools, The Blinding Vale, Voidscar Arena, Den of Nalorakk, Murder Row, Altar of Fangs.
* `JournalTier` 505 ("Current Season"): `AvailabilityCondition` group 156363 holds that pool and the
  raids **The Tidebound Grotto** (1317) and **The Venomous Abyss** (1320); group 149388 holds the
  season-1 raids (Dreamrift, Voidspire, March on Quel'Danas, Sporefall).
* Raidbots' live bonus map tags upgrade groups 614–618 (bonus ids 12817–12856) with `seasonId` 37;
  the simc repo's `profiles/MID2` gear carries 12854 / 13848 (Myth 6/6 = 334, Voidforged = 344).
* localbots' `data/season.json` agrees: "Midnight Season 2 (12.1)", `upgradeSeasonId` 37, same pool.

## What is exact, what is approximate

Exact (from DB2 + Raidbots): item names/icons/quality/slots, upgrade-track ladders and crest ids,
raid drop levels per boss and difficulty, M0 level, tier-set ids, unique-equipped, crafted ilevels.

Approximate / curated:
* **Stats** follow SimC's `scaled_stat` formula with the epic/superior/good `RandPropPoints` budget and
  SimC's rating/stamina curves; bonus-id stat modifiers (`ItemBonus` type 2, e.g. "of the Peerless"
  suffixes) and item effects are not applied. Combined primaries (DB2 71–74) are reported as
  `primary` by `resolve_item` and renamed to the spec's stat by `loot.candidates`.
* **M+ key-level levels** and the **world-boss level** are the localbots season-2 table; the track split
  was cross-checked against the 12.1 keystone bonus-tree nodes but not against a tooltip.
* **Delve tiers 1–7** are extrapolated along the track ladders; tiers 8+ (Champion 2/6 bountiful,
  Hero 1/6 vault) come from localbots' notes. `delves[].verified` says which.
* **Consumables** are the simc repo's MID2 profile defaults; specs without a profile (healers,
  evokers, balance/guardian druid...) fall back by primary stat / role.
* **Enchants/gems**: most-used ids in the MID2 profiles; ring/weapon/leg variants per stat.

## Raidbots parity, wave 2 (Catalyst, sockets, Voidforge, crafted recraft, Omnium Folio)

* **Catalyst** (`season["catalyst"]`): item-conversion 13 mapping (13 classes x 9 slots) is
  transcribed from Raidbots' `item-conversions.json`/`seasons.json` cross-checked cheaply against
  DB2 `ItemSet`/`ItemSetSpell` for build 12.1.0.69933 (see THIRD_PARTY.md and
  `season.py::CATALYST_CLASSES`). `items` is keyed by the *source* item's inventory type (both
  chest inventory types, 5 and 20, map to the same tier chest item id per class) so
  `catalyst_item_for(klass, inventory_type)` needs no separate slot lookup. `catalyst_variant`
  builds the SimC `redirected_base_stats=` line on `Item.simc_string` since `models.py` (owned
  elsewhere this wave) has no dedicated field for it -- **engines building a .simc file for a
  catalyzed item must use `Item.simc_string` verbatim**, not re-render it with `Item.to_simc()`.
* **Sockets** (`season["sockets"]`): the add-socket bonus id (1808) and the DB2 "N sockets"
  bonuses (8781/8782) are exact; `vault_slots`/`jewelbinder_slots` are curated from the season's
  vault/Jewelbinder tooltips, not walked from a DB2 table. SimC applies every `gem_id` on an item
  regardless of its actual socket count, so `socket_variant` (and any engine adding sockets)
  must cap gem lists to the item's socket count itself.
* **Voidforge**: only a Myth-track Voidforge exists this season (`VOIDFORGED` no longer carries
  `hero_ilevel`/`crafted_ilevel` -- see the bug note above). **Open question, not resolved by
  this research pass**: whether Voidforge is actually restricted in-game to weapons/trinkets
  (`voidforged.slots`) or could reach other Myth-max slots too -- this was only verified against
  the bonus ids SimC's MID2 profiles carry (scratchpad `w2/v_q5_*`), not against a live Voidsmith
  NPC or a datamined eligibility list. Treat `voidforged.slots` as "confirmed eligible", not
  "the complete set".
* **Crafted recraft**: `crafted.stat_bonus_ids` (8790-8795) override `crafted_stats=` outright;
  `crafted_variant` strips them and sets `crafted_stats` explicitly instead of relying on a
  bonus id, which also means a recrafted item's `crafted_stats` no longer round-trips back to a
  single bonus id the way a freshly-imported crafted item's does.
* **Omnium Folio** (`season["omnium"]`): TraitTree 1186, 5 rows / one choice each, transcribed
  from DB2 `TraitTree`/`TraitNode`/`TraitNodeEntry` + `Spell` for build 12.1.0.69933. The weekly
  unlock gating (`RequiredLevel 90` per node) is server-side and not modelled here -- every row
  is always offered.
* **Consumable options** (`season["consumables"]["options"]`): the full set of names
  `SimulationCraft 1210-01` actually accepts, verified empirically (one sim per candidate name,
  scratchpad `w2/consumables_s37.json`) rather than read from a DB2 table, since SimC's own
  accepted-name list isn't itself in the game database. Only the highest-quality (`_2`) variant
  of names that take a rank suffix is offered.

## LIMITATIONS

* **Tier tokens / set pieces**: the 12.1 raid journal lists no tier tokens or set items for The
  Venomous Abyss (the class sets 2055–2067 are obtained through the Catalyst; the MID2 profiles show
  them as `redirected_base_stats=`). The droptimizer therefore never offers a tier piece directly,
  but wave 2's `season.catalyst_variant`/`season["catalyst"]` now model the Catalyst conversion
  itself (tier item id, set id, source bonus ids) for engines that want to offer a "catalyzed"
  twin of a non-tier drop/bag item; `json2` doesn't expose worn set bonuses at all, so counting
  active set pieces for a combo is still up to the engine (by `Item.set_id`), not this layer.
* **Vault**: `DungeonSource.key_level = -1` uses the highest key level's vault track; no per-level vault
  selection beyond `season["key_levels"][].vault_ilevel`.
* **Voidforged (Ascendant Voidcore)** levels are published in `season["voidforged"]` but `candidates`
  does not add them on top of a maxed track; the engine can bump weapons/trinkets itself.
* **Last season's gear**: only season-37 tracks are decoded as upgradeable (`bonuses.upgrade_of(..., season_id=37)`).
* **Talent decoder** handles loadout format version 2 (11.0+). Ranks of selected-but-granted nodes
  are reported as 1; node visibility per spec follows `TraitCond` spec sets and may include a few
  internal/off-screen nodes (filtered by x/y > 0).
* **Enchant values** are ids only; `best_enchant` returns None for off-hands that are not weapons.
* Icons need `ItemModifiedAppearance`; ~1% of very old items resolve to an empty icon.
* **Progress callbacks**: `ensure_tables`/`refresh` call `progress_cb(current, total, message)`; the
  API route adapts it to the job manager's `ctx.progress(phase, current, total, message)`.
