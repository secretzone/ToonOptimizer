---
name: run-sim
description: Pick the right ToonOptimizer sim and its options from a plain question, run it, and explain the result. Use for "sim my character", "is this trinket better", "what drops should I get from <raid/dungeon>", "where should my crests go", "best gems/enchants/flask", "stat weights", "compare these two sets", or any request to run a sim without naming every option.
---

# Run a sim

Turn a question into one sim with sensible options, run it on the person's app, and answer in a
few lines. For a full character review use `obvious-upgrades`; for talent questions use
`raid-talents` or `dungeon-talents`.

## Before running

1. `GET http://127.0.0.1:8790/api/health`. If there's no answer, ask them to start `.\run.ps1`.
   Don't start it yourself.
2. Character: the one named, or the most recently imported (`GET /api/characters`). Fetch the
   profile with `GET /api/characters/<slug>`. Every sim body needs the full `profile` object.
   If the import looks older than their last play session, refresh it with the `import-addon`
   skill first; ask for a fresh `/simc` paste only when the addon has nothing newer.
3. If `GET /api/status` shows a mismatch, say so. Sims still run.

## Choosing the sim

| They ask | Sim | Key options |
|---|---|---|
| What's my DPS / breakdown | `quick` | as below |
| Is X better than what I wear / best combo of my bags and vault | `topgear` | `candidate_keys` = the items they mean (or all bag/vault ≥ lowest equipped ilvl), `max_combos` 40 |
| What should I get from a raid, dungeon or delve | `droptimizer` | `sources` for what they named; `upgrade: "max"`, `upgrade_equipped: "match"`, `min_ilevel` = lowest equipped |
| Where do my crests go | `upgrades` | all slots; the result's `affordable` flags use their crests |
| Gems or enchants | `gems` | `mode: "uniform"`, `include_enchants: true` |
| Flask, food, potion, oil | `consumables` | categories they asked about, else all |
| Stat weights / Pawn string | `statweights` | defaults |
| A vs B for specific items | `gearcompare` | one set per option |

Fight options, inferred from what they said:
- Raid boss or single target: `Patchwerk`, 1 target, 300 s.
- "Cleave" or two bosses: `Patchwerk` with 2 targets.
- Adds: `CleaveAdd`.
- M+ or dungeon: `DungeonSlice` (not for Demon Hunters), or `HecticAddCleave` with 5 targets
  for trash.
- Tank: set `metric: "dtps"` when they ask about survivability.

Use `precision: "low"` unless they ask for more. Use the season consumables from
`GET /api/data/recommendations` unless they say otherwise. Include Catalyst keys only when
`catalyst_charges > 0`.

If the question is ambiguous in a way that changes the sim, for example which raid difficulty,
ask one short question. Otherwise pick and state the choice.

## Running and answering

`POST /api/sims/<type>`, then poll `GET /api/jobs/{id}` until the status is done. Then read
`GET /api/jobs/{id}/result`.

Answer with:
- the top 3-5 rows, with DPS gain and error;
- rows within about 2× error called ties;
- any `notes` the result carries;
- a link to `http://localhost:5173/history`.

If the job failed, quote its error and say what to change. End with numbered in-game steps, for
example "equip X, upgrade Y with 40 Hero crests".

If a report exists for the character (`GET /api/reports/<slug>`), offer to add the result to it.
