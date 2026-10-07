---
name: setup
description: Install and verify ToonOptimizer on a new Windows PC. Use when someone asks to set up, install or update ToonOptimizer, or says it won't start, shows a mismatch warning, or can't find their WoW folder.
---

# Setup

Get a working ToonOptimizer: tools installed, app starting on 5173/8790, SimC and game data
downloaded, WoW folder detected. Check each step before moving on; skip the ones already done.
Explain in plain words: the person is a WoW player, not a developer.

## 1. Prerequisites

Check each with `<tool> --version`: `git`, `node` (20+), `npm`, `uv`. Install whatever is missing,
after saying what you're about to install:

```powershell
winget install --silent Git.Git OpenJS.NodeJS.LTS astral-sh.uv
```

Newly installed tools aren't on PATH in the current shell. Tell the person to close and reopen
Claude Code, or call the tools by full path. Python comes from uv; don't install it separately.

## 2. Dependencies and tests

From the repo root:

```powershell
cd backend; uv sync; uv run pytest -q
cd ..\frontend; npm install; npm run build
```

Unit tests must pass. Tests marked as needing SimC or data will skip on a fresh install; that's
expected. If something fails, fix it or report the exact error. Don't paper over it.

## 3. First start

The person starts the app, not you: anything you start dies when your session ends. Ask them to
run this in their own PowerShell window and leave it open. Then wait for them to say it's running,
or poll `GET http://127.0.0.1:8790/api/health`, before step 4.

```powershell
.\run.ps1
```

A browser tab opens at http://localhost:5173. Useful switches:
- `-Stop` stops the app.
- `-NoBrowser` skips opening the tab.
- `-BackendPort` and `-FrontendPort` use other ports.
- `-Build` serves a built UI from the backend alone.

If it says a port is in use, have them run `.\run.ps1 -Stop` and start it again. Don't stop
processes yourself unless they ask.

If the tab shows an amber **MOCK DATA** banner, it's a developer test window (`npm run dev:mock`)
with fixture data, not their app. Tell them to close it and use the tab `run.ps1` opened.

Optional desktop shortcuts, created only if they want them:
- **ToonOptimizer**: target `powershell.exe`, arguments `-NoExit -ExecutionPolicy Bypass -File "<repo>\run.ps1"`.
- **Stop ToonOptimizer**: the same target with `-Stop` added to the arguments.

Use `WScript.Shell` `CreateShortcut` to make them.

## 4. SimC, data and WoW folder

Once `GET http://127.0.0.1:8790/api/health` answers:

1. `GET /api/settings`: check `wow_dir` points at the folder that holds `_retail_`. If it's
   empty or wrong, find the install. Look for `World of Warcraft\_retail_\Wow.exe` on the
   fixed drives, or read the Battle.net registry key. Then `PUT /api/settings {"wow_dir": ...}`.
2. `GET /api/status`: if `simc.installed` is false, `POST /api/simc/install`. If `data.ready` is
   false, `POST /api/data/refresh`. Poll `GET /api/jobs/{id}` until done. SimC is a
   16 MB download (about 120 MB unpacked) and the game data about 140 MB. Both take a minute or
   two.
3. Confirm `GET /api/status` shows `mismatch.simc` and `mismatch.data` both false.

## 5. Import their first character

The tool ships with no characters, so walk them through this:

1. Install the addons with `.\scripts\Install-Addons.ps1` from the repo folder. It copies the
   ToonOptimizer addon and the SimulationCraft addon it needs into the game's AddOns folder
   (it leaves a CurseForge-managed SimulationCraft alone if that one is current). New addons
   need a full game restart, not just `/reload`.
2. In game, log into the character they want to optimize, then type `/reload` or log out. WoW
   writes addon data only then.
3. On the **Import** page at http://localhost:5173, click **Import from addon** (or use the
   `import-addon` skill). Fallback if the addon can't be used: type `/simc`, Ctrl+A, Ctrl+C,
   paste it on the Import page and click Import.
4. Confirm with `GET /api/characters`. It should list that character with the right class, spec
   and item level. If the class is wrong or a MOCK banner is showing, they're on a mock-mode
   window. Have them close it and use the window `run.ps1` opened.

Then offer to build their first report: "want me to run the upgrade report for <name>?" That
uses the `obvious-upgrades` skill.

Finish with a short summary of what was installed and what was already there, then the next steps
as a numbered list.

## Getting the code

If the repo isn't cloned yet: `git clone https://github.com/secretzone/ToonOptimizer.git`, then
work from that folder.

## Updating later

`git pull`, then `uv sync` in `backend/` and `npm install` in `frontend/`. Ask the person to restart
the app. If Settings shows a mismatch after a WoW patch, run step 4 again.
