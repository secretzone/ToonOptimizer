# Features

| Page | Answers |
|---|---|
| Quick Sim | What is my DPS now, and where does it come from? |
| Top Gear | Which combination of what I own is best? |
| Droptimizer | Which drops from this raid, key level or delve tier are upgrades? |
| Upgrades | Where should my crests go next? Ranked by gain per crest, with a spend plan for what you own. |
| Gems & Enchants | Best gem per socket and enchant per slot; "Use recommended" fills the season's picks. |
| Consumables | Best flask, food, potion, rune and weapon oil. |
| Stat Weights | Pawn string for your current gear. |
| Gear Compare | Any set A vs set B. |
| Talent Compare | Loadout strings side by side; the Omnium Folio tab sims rune choices. |
| Advanced | Raw SimC input. |
| Reports | Per-character reports written by the `obvious-upgrades` skill. |

## Raidbots-style options

- **Precision**: Low, Medium and High work like Raidbots' Smart Sim. Every candidate runs at 1%
  error, the ones that can't win are dropped, and the rest rerun more precisely.
- **Top Gear**:
  - one Great Vault item per combination;
  - several talent loadouts per combination;
  - add any item by name with a track and rank;
  - Catalyst, vault socket, Voidforge and recraft variants;
  - a minimum item level filter;
  - sidegrade grouping.
- **Droptimizer**:
  - can upgrade your equipped gear first, so drops aren't flattered;
  - a Group by tab shows best drop and expected value per boss, dungeon or delve tier.
- **Fight styles**: Patchwerk, Dungeon Slice, Hectic Add Cleave, Cleave Add, movement variants,
  Target Dummy and Execute. Targets, length, raid buffs and consumables are set per sim.
- **Metrics**: DPS, priority-target DPS, DTPS, HPS and damage taken.
- **Expert mode**: add raw SimC lines at four positions.

## GPU

SimulationCraft can't use a GPU, so all numbers come from your CPU. An optional, experimental model
predicts DPS on the GPU to prune huge Top Gear searches before the exact sims. To enable it:

```powershell
cd backend; uv sync --extra gpu   # PyTorch with CUDA, about 3 GB
```

Then run a few Top Gear or Droptimizer sims for a spec and press **Train** in Settings.

## Ports

The app uses 8790 (backend) and 5173 (UI). `run.ps1` refuses to start if either is taken and shows
what holds it.

- `.\run.ps1 -Stop` stops the app.
- `.\run.ps1 -Stop -All` also stops test servers on other ports.
