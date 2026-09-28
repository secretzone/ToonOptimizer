# ToonOptimizer

A Raidbots that runs on your own PC. Paste your in-game `/simc` export and run Quick Sim, Top Gear,
Droptimizer, crest Upgrades, Gems & Enchants, Stat Weights and talent comparisons. The simulations
use [SimulationCraft](https://github.com/simulationcraft/simc) on every CPU core you have: no queue,
no account, no premium tier.

Windows only for now.

## Install

The fast way: clone the repo (step 2 below), open the folder in
[Claude Code](https://claude.com/claude-code) and say **"set up ToonOptimizer"**. The `setup` skill
installs what's missing and checks everything works.

By hand:

1. Install the tools (PowerShell):
   ```powershell
   winget install Git.Git OpenJS.NodeJS.LTS astral-sh.uv
   ```
2. Clone and start:
   ```powershell
   git clone https://github.com/secretzone/ToonOptimizer.git
   cd ToonOptimizer
   .\run.ps1
   ```
   The first start installs Python and Node packages, which takes a few minutes.
3. In the browser tab that opens (http://localhost:5173), go to **Settings**:
   - Check the WoW folder. It's auto-detected; fix it if it's wrong.
   - Click **Install SimC**, then **Refresh data**. Both are one-time downloads: about 160 MB,
     or 260 MB once unpacked.
4. In game, install the [SimulationCraft addon](https://www.curseforge.com/wow/addons/simulationcraft).

## Use

1. In game type `/simc`, then Ctrl+A, Ctrl+C.
2. **Import** page: paste, Import. Your bags, Great Vault choices and crests come along.
3. Pick a sim from the sidebar. Every run is kept under **History**.

Stop the app with Ctrl+C in its window, or `.\run.ps1 -Stop`. Other switches: `-NoBrowser`, and
`-BackendPort`/`-FrontendPort` if 8790 or 5173 is taken. An amber **MOCK DATA** banner means
you're on a developer test window; close it and use the tab `run.ps1` opened.

What each page answers, plus the Raidbots-style options, is in [docs/FEATURES.md](docs/FEATURES.md).

## Using it with Claude Code

Open the folder in [Claude Code](https://claude.com/claude-code) while the app is running, and just
ask. Skills in `.claude/skills/` pick the right sims, run them on your app, and explain the result.

| Skill | Ask something like | What you get |
|---|---|---|
| `setup` | "set up ToonOptimizer", "it won't start" | Tools installed, SimC and game data downloaded, your first character imported. |
| `run-sim` | "is this trinket better?", "what should I get from heroic raid?", "where do my crests go?", "best flask for me" | The right sim with sensible options, top results, and in-game steps. |
| `raid-talents` | "best raid build for cleave", "which loadout for Ula'tek?" | Your loadouts vs guide builds at 1, 2, 3 and 5 targets and with adds, plus a boss-by-boss pick. |
| `dungeon-talents` | "talents per dungeon", "what should I swap for Murder Row?" | Named M+ loadouts, each covering the dungeons that share it, checked in sims. |
| `obvious-upgrades` | "what should I upgrade on Thrall?", "compare me to BiS" | A full report on the **Reports** page: upgrades by effort, best in slot, talents, and a weekly roadmap. |

Name the character in the question. Otherwise the skills use your most recently imported one.
Results are saved to that character's report, so the **Reports** page stays current.

## After a WoW patch

Restart the app. If **Settings** shows a mismatch warning, click **Update SimC** and/or
**Refresh data**. A new season also needs `data/season.json` updated.

## Limitations

- Results are SimulationCraft's: healers aren't simmable, and drop chances aren't modelled.
- Delve loot pools and some season rules are maintained by hand in `data/`.

## Development

Conventions are in `CLAUDE.md`, and the HTTP contract is in `API.md`.

## License

MIT. SimulationCraft is GPL-3.0 and is downloaded at runtime, not bundled. Other sources are listed
in `THIRD_PARTY.md`.
