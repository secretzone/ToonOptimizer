# Third-party notices

## SimulationCraft
The simulation engine. https://github.com/simulationcraft/simc — GPL-3.0.
Prebuilt weekly Windows binaries are downloaded at runtime from
https://github.com/sortbek/simc-builds (not bundled in this repository).

## localbots
Parts of the data pipeline (wago.tools table selection, item-level / upgrade-track
logic, droptimizer loot-source mapping, season configuration) are ported from
https://github.com/balovich-matje/localbots, MIT License, Copyright (c) 2025 balovich-matje.
Ported code lives under `backend/src/toonopt/data/` and `data/season.json`.

## wago.tools
Game database (DB2) CSV exports are fetched at runtime from https://wago.tools/db2/.

## Raidbots static data
Public, versioned static-data JSON published alongside https://www.raidbots.com (not the
Raidbots application itself, and not code -- these are plain data files describing the current
season, fetched/cached the same way as the wago.tools CSVs):
- `bonuses.json` (https://www.raidbots.com/static/data/live/bonuses.json) -- bonus-id decoding
  (item level / upgrade track / socket / quality / crafted stats), used by
  `backend/src/toonopt/data/bonuses.py` since wave 1.
- `seasons.json` (https://www.raidbots.com/static/data/live/seasons.json) -- per-season metadata
  (upgrade track season ids, the Catalyst's charge currency), used to verify
  `data/season.json`'s `catalyst.currency_id`.
- `item-conversions.json` (https://www.raidbots.com/static/data/live/item-conversions.json) --
  the Catalyst's slot/class -> tier-item-id mapping (item-conversion 13 this season), the source
  for `data/season.json`'s `catalyst.items`/`catalyst.set_ids` (transcribed into
  `backend/src/toonopt/data/season.py::CATALYST_CLASSES`, cross-checked against DB2
  `ItemSet`/`ItemSetSpell`).

## Item icons
Icons are loaded from Wowhead's CDN (wow.zamimg.com) by the browser.

## SimulationCraft addon (vendored)
`addons/Simulationcraft/` is an unmodified copy of the in-game SimulationCraft addon,
release 12.1.0-04 (its TOC still reads 12.1.0-03), from https://github.com/simulationcraft/simc-addon (Theck, navv_, seriallos). It is a
separate work distributed alongside ToonOptimizer, not part of it, and is installed next to the
ToonOptimizer addon, which calls its public SimulationcraftAPI. Its own LICENSE (the Unlicense,
public domain) ships in that folder, and bundled libraries (Ace3, LibStub, LibRealmInfo, LibDBIcon,
LibDataBroker) keep their own licenses and notices. Refresh it with scripts/Update-SimcAddon.ps1.
