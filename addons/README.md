# Companion addons

- `ToonOptimizer/` saves your SimulationCraft export of each character to SavedVariables
  (`ToonOptimizerDB`) so the app can import it without copy/paste. It captures quietly after
  gear, talent, spec, bag or vault changes (about 10 s later) and at login. Give it a few
  seconds after a change before you `/reload` or log out. Commands: `/topt` (capture now),
  `/topt status`, `/topt on`, `/topt off` (also `/toonopt`).
- `Simulationcraft/` is a vendored, unmodified copy of the SimulationCraft addon (a dependency
  of ToonOptimizer). See `THIRD_PARTY.md`.

## Install
```powershell
.\scripts\Install-Addons.ps1            # copy into <WoW>\_retail_\Interface\AddOns
.\scripts\Install-Addons.ps1 -Link      # junctions instead (edits show up live)
.\scripts\Install-Addons.ps1 -Only ToonOptimizer -Force
```
The WoW folder comes from `-WowDir`, `data/settings.json` (`wow_dir`), `$env:WOW_DIR`, the
Battle.net registry entries, or a scan of your fixed drives (the folder must contain `_retail_`). An existing Simulationcraft install that is as new as
the vendored one is left alone unless `-Force`. Replaced folders are backed up to
`runtime\addon-backups\`. A newly installed addon needs a full game restart.

## Using it
WoW writes SavedVariables only on `/reload`, logout or exit. After playing, `/reload` once (or log
out) and then import in the app. The file is
`WTF\Account\<ACCOUNT>\SavedVariables\ToonOptimizer.lua`.

## Refresh the vendored Simulationcraft
```powershell
.\scripts\Update-SimcAddon.ps1          # latest release
.\scripts\Update-SimcAddon.ps1 -Tag v12.1.0-04
```
