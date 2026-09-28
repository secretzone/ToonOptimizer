---
name: dungeon-talents
description: Build Mythic+ talent loadouts per dungeon for a character, grouping dungeons that share the same build and naming each set, validated in ToonOptimizer sims. Use for "talents for <dungeon>", "dungeon talent sets", "M+ loadouts", or "what should I swap for this key".
---

# Dungeon talents

Top players rarely change damage talents between dungeons; they swap one or two utility points
for each dungeon's mechanics. Produce a small set of named loadouts, each covering several
dungeons.

## Steps

1. **Character and app**: as in `run-sim`.
2. **Base build**:
   - Start from the current guide M+ build for the spec (Icy Veins, Method).
   - Compare it with the character's saved M+ loadout in a `talentcompare` on `DungeonSlice`.
   - If theirs is within noise, use theirs as the base; people keep what they know.
3. **Dungeon pool**: the current M+ dungeons, from `GET /api/data/loot/sources`.
4. **Per dungeon, find what the mechanics call for**:
   - enrage or Magic buffs to purge;
   - poison, disease or curse to remove;
   - fixates or runners to slow or stop;
   - mandatory stops or interrupts;
   - heavy magic damage.

   Where to look:
   - Top-player strings per dungeon: Raider.IO leaderboard runs for the spec, the most common
     string per dungeon.
   - Dungeon guides that list dispellable abilities.
   - Enemy spell flags in game data, if you need to confirm one.

   Cite the URL and date for each.
5. **Build the variants**: for each dungeon, turn what it needs into add and remove swaps against
   the base.
   - Call `POST /api/data/talents/modify {klass, spec, base, add, remove}`. If it returns
     errors, such as a missing prerequisite, fix the swap instead of forcing it.
   - Prefer a real top-player string when it matches.
   - Check every result with `POST /api/data/talents/names`: the only differences from the base
     should be the intended swaps.
6. **Validate**: run one `talentcompare` with every variant, the base and the active loadout, on
   `DungeonSlice` and on 5-target `HecticAddCleave`, `precision: "low"`.
   - If a variant is well below the base (more than about 1%), say so and justify it, or drop
     the swap.
7. **Group and name**:
   - Dungeons whose builds are identical share one loadout.
   - Name each set by what it handles, then list its dungeons, for example
     "M+ Enrage: Voidscar Arena, Den of Nalorakk" or "M+ Poison & Kite: …".
   - Keep names short enough for the in-game loadout name box, and put the dungeons in the notes.
   - Also offer a reduced three-set version, by merging sets that differ only by a point that
     has nothing to do in the merged dungeon.
   - Note affix-driven exceptions, for example keeping a dispel on weeks when an affix applies
     one.
8. **Save**: if a report exists, `PUT /api/reports/<slug>` with a `talents` section "Dungeon
   talent sets" (one entry per set: context = name plus dungeons, loadout string, notes) and a
   markdown section with the sim table and the three-set option. Keep the other sections
   unchanged. Append the job ids to `sim_refs`.

## Reply

- A table: set name | dungeons | swap from base.
- The DPS check, as one sentence.
- Import steps in game: Talents → Import → paste → save under the set name, then switch
  before each key.
