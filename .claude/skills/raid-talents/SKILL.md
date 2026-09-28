---
name: raid-talents
description: Find a character's best raid talent builds by fight type (single target, two-target cleave, boss plus adds, sustained AoE) and per boss, comparing their saved loadouts with current guide builds in ToonOptimizer sims. Use for "best raid build", "which talents for cleave/AoE", "which loadout for <boss>", or "is my build good".
---

# Raid talents

Single-target sims can't rank cleave or AoE builds, so compare builds across several fights,
find the crossover points, and map bosses to builds.

## Steps

1. **Character and app**: as in `run-sim`, including the health check, profile fetch and
   freshness check.
2. **Candidate builds**:
   - the active loadout and every saved loadout (`profile.saved_loadouts`);
   - the current guide builds for the spec, from Icy Veins, Method and Wowhead: raid single
     target, raid cleave, AoE, and any hero-tree alternatives.

   Reuse sources from the character's report (`GET /api/reports/<slug>`) if they're under
   7 days old. Otherwise look them up and note the URL and date. Before simming, check each
   string with `POST /api/data/talents/names`. Drop strings that fail, and say so.
3. **Sims**: one `POST /api/sims/talentcompare` per fight, all with `precision: "low"`:

   | Fight | Options |
   |---|---|
   | Single target | Patchwerk, 1 target |
   | Two-target cleave | Patchwerk, 2 targets |
   | Three targets | Patchwerk, 3 targets |
   | Sustained AoE | Patchwerk, 5 targets |
   | Boss plus adds | CleaveAdd |

4. **Read the result**:
   - Build a table of build × fight, with DPS.
   - Treat builds within about 0.5% as tied.
   - Name the winner for each fight and where the crossover is, for example "Hydra up to
     2 targets, Trick Shots from 3".
   - When a saved loadout matches a guide build within noise, tell them to keep using theirs.
   - Use `POST /api/data/talents/names` to say what makes the winners differ, in two or three
     talents.
5. **Per boss**: for each boss in the current raids (`GET /api/data/loot/sources`), map it to a
   fight type. Use guides for the mechanics: number of targets, add waves, priority damage.
   Name the build for it, and cite a per-boss note from a guide when there is one.
6. **Save**: if a report exists, `PUT /api/reports/<slug>` with the table added as a markdown
   section "Raid talents: which build" and the per-boss list added as a `talents` section. Keep
   the other sections unchanged. Append the job ids to `sim_refs`.

## Reply

- The winner per fight type and the crossover.
- Which of their saved loadouts to use where.
- New strings to import, if any, each with a short name to save it under.
- Numbered in-game steps.
