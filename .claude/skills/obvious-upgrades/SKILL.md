---
name: obvious-upgrades
description: Build or refresh a character's optimization report in ToonOptimizer. Use when someone asks what to upgrade, where to get gear, what best-in-slot is, how their character compares to the guides, or which talents to use for a raid boss or dungeon. Combines the tool's quick upgrade check, current class guides and confirming SimulationCraft runs, and writes the result to the character's Reports page.
---

# Obvious upgrades

Maintains `reports/<slug>.json` for one character, shown on the **Reports** page.

- **Which character:** the one named. If none is named, use the most recently imported one from
  `GET /api/characters` and say which you picked.
- **Approach:** reason first, sim second. Most upgrades are obvious from item level and stat
  priority. The sims confirm the rest: trinkets, weapons, set pieces, small item-level steps and
  embellishments.

## Preconditions

1. `GET http://127.0.0.1:8790/api/health` answers. If it doesn't, ask the person to start the app
   with `.\run.ps1` in their own window; don't start it yourself. If it has never been set up,
   use the `setup` skill.
2. `GET /api/status` shows `mismatch.simc` and `mismatch.data` both false. Otherwise ask them to
   press Update SimC and Refresh data in Settings.
3. `GET /api/characters/<slug>` returns the profile. If it's older than their last play session,
   ask for a fresh `/simc` paste first. Never invent gear.

Every sim and advisor call takes the full `profile` object from step 3, not just the slug.

## Steps

1. **Stat weights**: run `POST /api/sims/statweights`, so the next step uses the character's real
   stat priority.
2. **Advisor** (no sim, seconds): `POST /api/advisor/obvious-upgrades`. Keep the raw result for
   the report's `advisor` field. Use its `stat_priority`, `tier`, per-slot `candidates` with
   their verdicts, and `sim_plan`.
3. **Guides**: reuse the report's `sources` if they were fetched within 7 days for this spec.
   Otherwise research current guides (Icy Veins, Method, Wowhead, Raider.IO, Archon) and collect:
   - stat priority;
   - best in slot per slot, with 2-3 easier alternatives;
   - trinket and weapon rankings;
   - crafted picks and embellishments;
   - talent strings for raid single target, raid cleave, M+ and delves;
   - Omnium Folio picks;
   - consumables.
   Every claim needs a URL and a date. Hand this research to a subagent if one is available.
4. **Reconcile**: trust the guides on trinkets, weapons and set-bonus value. Trust the advisor on
   item level, crest costs and what the character owns. Note any disagreements.
5. **Sims**: poll `GET /api/jobs/{id}` until each one finishes. Use `precision: "low"`
   throughout and record every job id.
   - Droptimizer with `sim_plan.droptimizer`, `upgrade: "max"` and `upgrade_equipped: "match"`.
     Set `min_ilevel` to the lowest equipped item level.
   - Top Gear with `sim_plan.topgear_candidate_keys` and `max_combos: 40`. Add Catalyst keys only
     when the character has charges.
   - Upgrades, for all slots.
   - Raid talents: follow the `raid-talents` skill (builds × fights, per-boss map).
   - Dungeon talents: follow the `dungeon-talents` skill (named per-dungeon sets).
   - Omnium: `POST /api/sims/omnium` in `per_row` mode.
6. **Write the report**: `PUT /api/reports/<slug>`, using the `CharacterReport` shape in
   `API.md`. Sections, in this order:
   1. What changed since the last report (only when a previous report exists).
   2. At a glance: item level, tier pieces, crests, catalyst charges, stat priority.
   3. Obvious upgrades: the best option per slot. Add a cheaper stepping stone when it gets most
      of the gain. List the steps to get each option.
   4. Confirmed by sim: only the rows the sims actually ranked.
   5. Best in slot, guide vs owned.
   6. Talents by context, then the raid cleave comparison, then the dungeon sets.
   7. Roadmap: 3-6 actions for this week, each with its expected gain.
   8. Notes and disagreements.

   The `summary` is 2-4 plain sentences. `sources` lists every URL used.
7. **Reply** with the summary, the top three actions, the link
   `http://localhost:5173/reports/<slug>`, and numbered in-game steps.

## Rules

- Never recommend gear the character can't equip, or anything SimC rejected. Name any sim
  that failed and say why.
- Under 6 item levels is not "obvious". Trinkets and weapons are never obvious.
- Keep the 4-piece set unless a sim says otherwise.
- Keep each sim to a few minutes.
- Update the report instead of overwriting it: keep `sim_refs` that still apply, and the
  `sources` cache.
