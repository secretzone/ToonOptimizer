# ToonOptimizer

Local Raidbots: a FastAPI backend (`backend/`) that drives SimulationCraft, a React UI (`frontend/`),
and Claude Code skills (`.claude/skills/`). `API.md` is the contract between backend and frontend;
read it before touching a route or `frontend/src/lib/api.ts`.

## Skills
- `setup`: install, first run, SimC and data download, first character import.
- `run-sim`: question → one sim with inferred options → short answer.
- `raid-talents`: builds × fight types (1/2/3/5 targets, adds), crossover, per-boss map.
- `dungeon-talents`: per-dungeon utility swaps → grouped, named M+ loadouts.
- `obvious-upgrades`: full character report (advisor + guides + sims), which uses the two
  talent skills.

When a skill is added or changed, update README.md's skills table in the same commit.

## Run and test
- `.\run.ps1` starts backend :8790 + UI :5173; `-Stop` stops it; `-Build` serves the built UI
  from :8790.
- Backend: `cd backend; uv run pytest -q; uv run ruff check .`
  (`-m integration` needs SimC and the data cache).
- Frontend: `cd frontend; npm run build; npm run lint; npm run dev:mock` (fixture data, shows a
  MOCK banner).

## Rules
- The user's app owns ports 8790 and 5173. Agents, tests and your own servers use 8795-8799 /
  5195-5199. Never stop processes you didn't start, and never run `-Stop -All`.
- Processes started from a Claude Code session die with it. Don't start the user's app for them;
  ask them to run `.\run.ps1` themselves.
- Long work goes through `toonopt.jobs` (one SimC process at a time). SimC is called only via
  `toonopt.simc.runner`, game data only via `toonopt.data.*`, and paths only from `toonopt.config`.
- Frontend: strict TypeScript and Tailwind. `src/lib/api.ts` is the only place that calls fetch;
  `src/lib/types.ts` mirrors `API.md`.
- Never commit `runtime/`, `data/cache/`, `history/`, `characters/`, `reports/` or
  `data/settings.json`. They hold per-user data.

## Facts
- WoW build: read from `<wow_dir>/.build.info` (Settings → WoW folder, auto-detected).
- SimC: weekly Windows builds from https://github.com/sortbek/simc-builds.
- Game data: `https://wago.tools/db2/<Table>/csv?build=<build>`, cached per build.
- Season rules (raids, tracks, crests, catalyst, consumables): `data/season.json`, maintained by hand.
