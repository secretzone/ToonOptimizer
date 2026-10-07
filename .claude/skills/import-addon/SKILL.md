---
name: import-addon
description: Import or refresh a character from the ToonOptimizer in-game addon, with no /simc copy-paste. Use for "import my character", "pull from the addon", "refresh my gear", "update <name>", "I just logged out, grab my changes", or before a sim when the saved profile looks older than the last play session.
---

# Import from the addon

The ToonOptimizer addon (`addons/ToonOptimizer`, needs the SimulationCraft addon) saves the
SimulationCraft export of every character you log into. WoW writes that data to disk only on
`/reload`, logout or exit, so a change made in game shows up here after one of those.

## Steps

1. `GET http://127.0.0.1:8790/api/health`. If there's no answer, ask them to start `.\run.ps1`.
   Don't start it yourself.
2. `GET /api/import/addon`. It returns `{installed, wow_dir, files, captures}`, newest first.
   - `installed` false or no `files`: the addon isn't set up. Offer to run
     `.\scripts\Install-Addons.ps1` (it copies `addons/*` into the game's AddOns folder; a new
     addon needs a full game restart). Pasting a `/simc` export on the Import page still works.
   - No captures, but files exist: they haven't logged into a character, or reloaded, since
     installing. Ask them to log in and `/reload` or log out.
3. Pick the capture: the character they named (match `name`, case-insensitive, and realm if
   given), else the newest. If the one they asked for is missing, list the `key`s you have.
4. Before importing, keep the current saved profile for comparison:
   `GET /api/characters/<saved_slug>` (a 404 means it's a new character).
   Then `POST /api/import/addon {"key": "<key>"}`. The result is the saved `CharacterProfile`,
   the same thing a `/simc` paste produces. For "import everyone", use `{"all": true}`: it skips
   captures that aren't newer than what's saved and reports each character's result.
5. Compare the new profile with the one you kept. Report briefly:
   - when it was captured (`captured_at`, in local time) and whether that was newer than what
     was saved (`newer_than_saved`);
   - item level, gear swaps by slot (item names and ilvl), and talent loadout changes;
   - crest and catalyst counts if they moved.
6. If `captured_at` is older than they'd expect (they say they just changed gear), the game
   hasn't written it yet: ask for `/reload` or a logout, then run this again.

Never invent gear. If parsing fails (422), say so and ask for a `/simc` paste instead.

## Finish

End with the next steps as a short numbered list, for example: open **Import** to check it, or
"want me to run the upgrade report for <name>?" (the `obvious-upgrades` skill).
