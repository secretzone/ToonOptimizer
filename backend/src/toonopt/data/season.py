"""Season configuration: ``data/season.json``.

``load()`` returns the file (cached by mtime). ``generate(build)`` rebuilds it from the DB2
cache plus the curated constants below and ``write()`` stores it; run
``uv run python -m toonopt.data.season`` after a data refresh or a season change.

How the live season is identified (build 12.1.0.69875):

* ``MythicPlusSeasonTrackedMap`` -- the highest ``DisplaySeasonID`` (37) lists this season's
  keystone pool. 37 is also the ``seasonId`` Raidbots attaches to the live upgrade tracks.
* ``JournalTierXInstance`` for the "Current Season" tier (505) groups instances by
  ``AvailabilityCondition``; the group holding the keystone dungeons (156363) is the live one
  and also holds the season's raids (The Tidebound Grotto, The Venomous Abyss). The older
  group 149388 holds the season-1 raids.
* World bosses are the ungated (condition 0) ``JournalInstance`` with Flags & 2 ("Midnight").

Everything hand-curated (delve tiers, world-boss level, consumables, enchants, gems) is marked
with ``verified``/``source`` notes in the output.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import polars as pl

from toonopt.config import DATA_DIR
from toonopt.data import bonuses, droplevels, items, wago
from toonopt.models import CharacterProfile, Item

SEASON_FILE = DATA_DIR / "season.json"
DELVE_FILE = DATA_DIR / "delve-loot.json"

CURRENT_SEASON_TIER = 505     # JournalTier "Current Season" -- stable across seasons
CURRENT_EXPANSION = 11        # Map/ItemSparse ExpansionID for Midnight
UPGRADE_SEASON_ID = 37        # Raidbots seasonId of the live upgrade tracks (Midnight S2)

# ---------------------------------------------------------------------------
# curated: consumables (SimC names from the simc repo's profiles/MID2/*.simc, 2026-09)

_RAW_CONSUMABLES: dict[str, dict[str, str]] = {
    "death_knight_blood": {"flask": "flask_of_thalassian_resistance_2", "food": "silvermoon_parade", "potion": "draught_of_rampant_abandon_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "death_knight_frost": {"flask": "flask_of_the_shattered_sun_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "death_knight_unholy": {"flask": "flask_of_the_blood_knights_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "demon_hunter_devourer": {"flask": "flask_of_the_magisters_2", "food": "blooming_feast", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "demon_hunter_havoc": {"flask": "flask_of_the_shattered_sun_2", "food": "blooming_feast", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "demon_hunter_vengeance": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "druid_feral": {"flask": "flask_of_the_magisters_2", "food": "harandar_celebration", "potion": "liquid_luster_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "hunter_beast_mastery": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "hunter_marksmanship": {"flask": "flask_of_the_shattered_sun_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "hunter_survival": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "mage_arcane": {"flask": "flask_of_the_blood_knights_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched_augment_rune", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "mage_fire": {"flask": "flask_of_thalassian_resistance_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched_augment_rune", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "mage_frost": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "potion_of_recklessness_2", "augmentation": "void_touched_augment_rune", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "monk_brewmaster": {"flask": "flask_of_thalassian_resistance_2", "food": "harandar_celebration", "potion": "draught_of_rampant_abandon_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "monk_windwalker": {"flask": "flask_of_the_blood_knights_2", "food": "harandar_celebration", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "paladin_protection": {"flask": "flask_of_the_blood_knights_2", "food": "silvermoon_parade", "potion": "liquid_luster_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "paladin_retribution": {"flask": "flask_of_the_magisters_2", "food": "royal_roast", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "priest_shadow": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "rogue_assassination": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "rogue_outlaw": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "rogue_subtlety": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "shaman_elemental": {"flask": "flask_of_the_magisters_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "shaman_enhancement": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": ""},
    "warlock_affliction": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "liquid_luster_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "warlock_demonology": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "liquid_luster_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "warlock_destruction": {"flask": "flask_of_the_magisters_2", "food": "harandar_celebration", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "warrior_arms": {"flask": "flask_of_the_blood_knights_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "warrior_fury": {"flask": "flask_of_the_magisters_2", "food": "harandar_celebration", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2"},
    "warrior_protection": {"flask": "flask_of_the_shattered_sun_2", "food": "harandar_celebration", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
}
# specs the simc repo ships no MID2 profile for: defaults by primary stat / role
_CONSUMABLES_BY_PRIMARY: dict[str, dict[str, str]] = {
    "agility": {"flask": "flask_of_the_shattered_sun_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "strength": {"flask": "flask_of_the_blood_knights_2", "food": "silvermoon_parade", "potion": "potion_of_recklessness_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "intellect": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
}
_CONSUMABLES_BY_ROLE: dict[str, dict[str, str]] = {
    "attack": _CONSUMABLES_BY_PRIMARY["agility"],
    "tank": {"flask": "flask_of_thalassian_resistance_2", "food": "silvermoon_parade", "potion": "draught_of_rampant_abandon_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
    "heal": {"flask": "flask_of_the_magisters_2", "food": "silvermoon_parade", "potion": "lights_potential_2", "augmentation": "void_touched", "temporary_enchant": "main_hand:thalassian_phoenix_oil_2"},
}
# Every SimC name this build's binary actually accepts (verified: scratchpad
# w2/consumables_s37.json, one sim per candidate name against SimulationCraft 1210-01), so the
# frontend can offer a dropdown instead of free text (Raidbots parity, wave 2). Only the
# highest-quality (``_2``) variant of names that take a quality suffix is listed; unsuffixed/
# ``_1`` names are the same items at a lower crafted rank and are intentionally omitted.
CONSUMABLE_OPTIONS = {
    "flask": [
        {"value": "flask_of_the_shattered_sun_2", "label": "Flask of the Shattered Sun (Crit)"},
        {"value": "flask_of_the_blood_knights_2", "label": "Flask of the Blood Knights (Haste)"},
        {"value": "flask_of_the_magisters_2", "label": "Flask of the Magisters (Mastery)"},
        {"value": "flask_of_thalassian_resistance_2", "label": "Flask of Thalassian Resistance (Versatility)"},
    ],
    "food": [
        {"value": "silvermoon_parade", "label": "Silvermoon Parade (feast)"},
        {"value": "harandar_celebration", "label": "Harandar Celebration (feast)"},
        {"value": "blooming_feast", "label": "Blooming Feast"},
        {"value": "royal_roast", "label": "Royal Roast (primary stat)"},
        {"value": "impossibly_royal_roast", "label": "Impossibly Royal Roast (primary stat)"},
        {"value": "queldorei_medley", "label": "Quel'dorei Medley (highest secondary)"},
        {"value": "arcano_cutlets", "label": "Arcano Cutlets (Crit)"},
        {"value": "warped_wise_wings", "label": "Warped Wise Wings (Mastery)"},
        {"value": "feast_of_knowledge", "label": "Feast of Knowledge"},
        {"value": "spellfire_filet", "label": "Spellfire Filet"},
        {"value": "crimson_calamari", "label": "Crimson Calamari"},
        {"value": "null_and_void_plate", "label": "Null and Void Plate"},
        {"value": "amani_cornucopia", "label": "Amani Cornucopia"},
        {"value": "twilight_anglers_medley", "label": "Twilight Anglers Medley"},
        {"value": "loas_gathering", "label": "Loa's Gathering"},
        {"value": "champions_bento", "label": "Champions Bento"},
        {"value": "hearthflame_supper", "label": "Hearthflame Supper"},
        {"value": "sunwell_delight", "label": "Sunwell Delight"},
        {"value": "puffer_plate", "label": "Puffer Plate"},
        {"value": "glitter_skewers", "label": "Glitter Skewers"},
        {"value": "bloom_skewers", "label": "Bloom Skewers"},
        {"value": "braised_blood_hunter", "label": "Braised Blood Hunter"},
        {"value": "buttered_root_crab", "label": "Buttered Root Crab"},
        {"value": "eversong_pudding", "label": "Eversong Pudding"},
        {"value": "farstrider_rations", "label": "Farstrider Rations"},
        {"value": "felberry_figs", "label": "Felberry Figs"},
        {"value": "flora_frenzy", "label": "Flora Frenzy"},
        {"value": "foragers_medley", "label": "Foragers Medley"},
        {"value": "fried_bloomtail", "label": "Fried Bloomtail"},
        {"value": "portable_snack", "label": "Portable Snack"},
        {"value": "quick_sandwich", "label": "Quick Sandwich"},
        {"value": "silvermoon_standard", "label": "Silvermoon Standard"},
        {"value": "spiced_biscuits", "label": "Spiced Biscuits"},
        {"value": "tasty_smoked_tetra", "label": "Tasty Smoked Tetra"},
        {"value": "wise_tails", "label": "Wise Tails"},
        {"value": "felkissed_filet", "label": "Fel-Kissed Filet (Haste)"},
        {"value": "voidkissed_fish_rolls", "label": "Void-Kissed Fish Rolls (Versatility)"},
        {"value": "sunseared_lumifin", "label": "Sun-Seared Lumifin"},
        {"value": "manainfused_stew", "label": "Mana-Infused Stew"},
        {"value": "venomspiced_cutlets", "label": "Venom-Spiced Cutlets"},
        {"value": "sweetandsour_skewers", "label": "Sweet-and-Sour Skewers"},
        {"value": "bloodthistlewrapped_cutlets", "label": "Bloodthistle-Wrapped Cutlets"},
    ],
    "potion": [
        {"value": "draught_of_rampant_abandon_2", "label": "Draught of Rampant Abandon"},
        {"value": "lights_potential_2", "label": "Light's Potential"},
        {"value": "liquid_luster_2", "label": "Liquid Luster"},
        {"value": "potion_of_recklessness_2", "label": "Potion of Recklessness"},
        {"value": "potion_of_zealotry_2", "label": "Potion of Zealotry"},
        {"value": "alluring_nostrum_2", "label": "Alluring Nostrum"},
    ],
    "augmentation": [
        {"value": "void_touched", "label": "Void-Touched Augment Rune"},
        {"value": "void_touched_augment_rune", "label": "Void-Touched Augment Rune (caster alias)"},
    ],
    "temporary_enchant": [
        {"value": "main_hand:thalassian_phoenix_oil_2", "label": "Thalassian Phoenix Oil"},
        {"value": "main_hand:oil_of_dawn_2", "label": "Oil of Dawn"},
        {"value": "main_hand:refulgent_whetstone_2", "label": "Refulgent Whetstone"},
        {"value": "main_hand:refulgent_weightstone_2", "label": "Refulgent Weightstone"},
        {"value": "main_hand:refulgent_razorstone_2", "label": "Refulgent Razorstone"},
    ],
}

# ---------------------------------------------------------------------------
# curated: enchants (SpellItemEnchantment ids; usage counted over the MID2 SimC profiles)

ENCHANTS_BEST: dict[str, int] = {
    "head": 8017, "shoulder": 8001, "chest": 7987, "legs": 8159, "feet": 7963,
    "finger1": 7967, "finger2": 7967, "main_hand": 8689, "off_hand": 8689,
}
ENCHANTS_BY_STAT: dict[str, dict[str, int]] = {
    "legs": {"agility": 8159, "strength": 8159, "intellect": 7935},
    "finger1": {"crit": 7997, "haste": 8025, "mastery": 7969, "versatility": 8027, "default": 7967},
    "finger2": {"crit": 7997, "haste": 8025, "mastery": 7969, "versatility": 8027, "default": 7967},
    "main_hand": {"default": 8689, "intellect": 8039, "agility": 7981, "strength": 7979},
    "off_hand": {"default": 8689, "intellect": 8039, "agility": 7981, "strength": 7979},
}
ENCHANT_OPTIONS: dict[str, list[dict]] = {
    "weapon": [
        {"id": 8689, "label": "Rite of the Hash'ey"},
        {"id": 7979, "label": "Strength of Halazzi"}, {"id": 7981, "label": "Jan'alai's Precision"},
        {"id": 7983, "label": "Berserker's Rage"}, {"id": 8011, "label": "Worldsoul Tenacity"},
        {"id": 8037, "label": "Flames of the Sin'dorei"}, {"id": 8039, "label": "Acuity of the Ren'dorei"},
        {"id": 8041, "label": "Arcane Mastery"},
        {"id": 8007, "label": "Worldsoul Cradle", "dps": False}, {"id": 8009, "label": "Worldsoul Aegis", "dps": False},
    ],
    "chest": [
        {"id": 7987, "label": "Mark of the Worldsoul", "stat": "all"},
        {"id": 7957, "label": "Mark of Nalorakk", "stat": "strength"},
        {"id": 7985, "label": "Mark of the Rootwarden", "stat": "agility"},
        {"id": 8013, "label": "Mark of the Magister", "stat": "intellect"},
    ],
    "head": [
        {"id": 7961, "label": "Empowered Hex of Leeching", "dps": False},
        {"id": 7991, "label": "Empowered Blessing of Speed", "dps": False},
        {"id": 8017, "label": "Empowered Rune of Avoidance", "dps": False},
    ],
    # Midnight brought shoulder enchants back; all are utility (speed / avoidance / leech).
    # Top-rank ids from SpellItemEnchantment 12.1.0.69933, cross-checked against the
    # `shoulders=...,enchant_id=` lines of simulationcraft/simc profiles/MID2 (8001 x16,
    # 8031 x13, 7973 x7, 7971 x1) and warcraft.wiki.gg/wiki/Midnight_Enchanting.
    "shoulder": [
        {"id": 8001, "label": "Amirdrassil's Grace", "dps": False},
        {"id": 8031, "label": "Silvermoon's Mending", "dps": False},
        {"id": 7973, "label": "Akil'zon's Swiftness", "dps": False},
        {"id": 7971, "label": "Flight of the Eagle", "dps": False},
        {"id": 7999, "label": "Nature's Grace", "dps": False},
        {"id": 8029, "label": "Thalassian Recovery", "dps": False},
    ],
    "feet": [
        {"id": 7963, "label": "Lynx's Dexterity", "dps": False},
        {"id": 7993, "label": "Shaladrassil's Roots", "dps": False},
        {"id": 8019, "label": "Farstrider's Hunt", "dps": False},
    ],
    "ring": [
        {"id": 7967, "label": "Eyes of the Eagle"},
        {"id": 7965, "label": "Amani Mastery"}, {"id": 7969, "label": "Zul'jin's Mastery"},
        {"id": 7995, "label": "Nature's Wrath"}, {"id": 7997, "label": "Nature's Fury"},
        {"id": 8021, "label": "Thalassian Haste"}, {"id": 8025, "label": "Silvermoon's Alacrity"},
        {"id": 8023, "label": "Thalassian Versatility"}, {"id": 8027, "label": "Silvermoon's Tenacity"},
    ],
    "legs": [
        {"id": 8159, "label": "Leg kit: Agi/Str + Stamina", "stat": "attack"},
        {"id": 8163, "label": "Leg kit: Agi/Str + Armor", "stat": "attack"},
        {"id": 8161, "label": "Leg kit: Agi/Str", "stat": "attack"},
        {"id": 7935, "label": "Spellthread: Int + Stamina", "stat": "intellect"},
        {"id": 7937, "label": "Spellthread: Int + Mana", "stat": "intellect"},
    ],
}

# ---------------------------------------------------------------------------
# curated: gems (item ids; adjective = main secondary, most-used colour per adjective)

GEMS: dict[str, int] = {
    "default": 240908,          # Flawless Masterful Garnet
    "crit": 240898,             # Flawless Deadly Amethyst
    "haste": 240900,            # Flawless Quick Amethyst
    "mastery": 240908,          # Flawless Masterful Garnet
    "versatility": 240894,      # Flawless Versatile Peridot
    "diamond": 240967,          # Powerful Eversong Diamond (main stat, unique special socket)
}
GEM_OPTIONS = [
    {"id": 240898, "label": "Flawless Deadly Amethyst"}, {"id": 240904, "label": "Flawless Deadly Garnet"},
    {"id": 240914, "label": "Flawless Deadly Lapis"}, {"id": 240890, "label": "Flawless Deadly Peridot"},
    {"id": 240896, "label": "Flawless Masterful Amethyst"}, {"id": 240908, "label": "Flawless Masterful Garnet"},
    {"id": 240918, "label": "Flawless Masterful Lapis"}, {"id": 240892, "label": "Flawless Masterful Peridot"},
    {"id": 240900, "label": "Flawless Quick Amethyst"}, {"id": 240906, "label": "Flawless Quick Garnet"},
    {"id": 240916, "label": "Flawless Quick Lapis"}, {"id": 240888, "label": "Flawless Quick Peridot"},
    {"id": 240902, "label": "Flawless Versatile Amethyst"}, {"id": 240910, "label": "Flawless Versatile Garnet"},
    {"id": 240912, "label": "Flawless Versatile Lapis"}, {"id": 240894, "label": "Flawless Versatile Peridot"},
]
DIAMONDS = {
    "options": [
        {"id": 240967, "label": "Powerful Eversong Diamond (main stat)"},
        {"id": 240969, "label": "Telluric Eversong Diamond"},
        {"id": 240971, "label": "Stoic Eversong Diamond"},
        {"id": 240983, "label": "Indecipherable Eversong Diamond"},
    ],
    "known_ids": [240966, 240967, 240968, 240969, 240970, 240971, 240982, 240983],
}

# ---------------------------------------------------------------------------
# curated: drop levels that are not in the DB2 tables

# M+ end-of-dungeon / vault (localbots season.json, cross-checked against the 12.1 bonus
# trees: end-of-dungeon key <=5 -> Champion, >=6 -> Hero; vault <=9 -> Hero, >=10 -> Myth)
MPLUS_END = {0: 292, 2: 295, 3: 295, 4: 298, 5: 302, 6: 305, 7: 305, 8: 308, 9: 308, 10: 311, 11: 311, 12: 311}
MPLUS_VAULT = {0: 302, 2: 305, 3: 305, 4: 308, 5: 308, 6: 311, 7: 315, 8: 315, 9: 315, 10: 318, 11: 318, 12: 318}
WORLD_BOSS_ILEVEL = 302
# Delves: tier 8+ bountiful coffer = Champion 2/6 (295), vault = Hero 1/6 (305) per localbots'
# season-2 notes; tiers 1-7 are an extrapolated ladder (NOT confirmed in game).
DELVES = [
    {"tier": 1, "ilevel": 266, "vault_ilevel": 276}, {"tier": 2, "ilevel": 269, "vault_ilevel": 279},
    {"tier": 3, "ilevel": 272, "vault_ilevel": 282}, {"tier": 4, "ilevel": 279, "vault_ilevel": 285},
    {"tier": 5, "ilevel": 282, "vault_ilevel": 289}, {"tier": 6, "ilevel": 285, "vault_ilevel": 292},
    {"tier": 7, "ilevel": 292, "vault_ilevel": 298}, {"tier": 8, "ilevel": 295, "vault_ilevel": 305},
    {"tier": 9, "ilevel": 295, "vault_ilevel": 305}, {"tier": 10, "ilevel": 295, "vault_ilevel": 305},
    {"tier": 11, "ilevel": 295, "vault_ilevel": 305},
]
CRAFTED = {
    "max_ilevel": 331,
    "crafting_quality": 5,
    "bonus_ids": [12214, 13751, 13836, 9627],   # crafted tiers + quality-5 offset = 331
    "voidforged_ilevel": 341,                   # weapons / trinkets with an Ascendant Voidcore
    "stats": {"32": "crit", "36": "haste", "40": "versatility", "49": "mastery"},
    # wave 2 (Raidbots parity): recraft support -- SimC crafted_stats codes by name, the bonus
    # ids that override crafted_stats= outright (strip before recrafting to a new pair, verified
    # scratchpad w2/q8*.py: 8790 crit/haste .. 8795 crit/vers), the "max" crafting-quality offset
    # bonus (+13 ilvl, 12497 verified equivalent to the legacy 9627), the embellishment marker
    # bonus id, and the app-enforced embellished-item cap.
    "stat_ids": {"crit": 32, "haste": 36, "versatility": 40, "mastery": 49},
    "stat_bonus_ids": [8790, 8791, 8792, 8793, 8794, 8795],
    "quality_bonus_max": 12497,
    "embellish_marker": 8960,
    "max_embellished": 2,
    "embellishment_marker_bonus_ids": [8960, 13555],
    "embellishments": [
        {"key": "darkmoon_hunt", "label": "Darkmoon Sigil: Hunt", "bonus": 12693},
        {"key": "arcanoweave", "label": "Arcanoweave Lining", "bonus": 12384},
        {"key": "darkmoon_void", "label": "Darkmoon Sigil: Void", "bonus": 13640},
        {"key": "iris", "label": "Prismatic Focusing Iris", "bonus": 13453},
        {"key": "iris_bandolier", "label": "Iris + Stabilizing Bandolier (pair)", "bonus": 13453, "second_bonus": 13454},
        {"key": "devouring", "label": "Devouring Banding", "bonus": 12685},
        {"key": "spore", "label": "Primal Spore Binding", "bonus": 12687},
        {"key": "sunfire", "label": "Sunfire Silk Lining", "bonus": 12385},
        {"key": "darkmoon_blood", "label": "Darkmoon Sigil: Blood", "bonus": 12705},
        {"key": "darkmoon_rot", "label": "Darkmoon Sigil: Rot", "bonus": 12692},
        {"key": "ammolite", "label": "Polished Ammolite", "bonus": 13768},
        {"key": "snakeskin", "label": "Snakeskin Lining", "bonus": 13764},
        {"key": "adorned_fang", "label": "Adorned Fang", "bonus": 13767},
        {"key": "ritual_stone", "label": "Hunter's Ritual Stone", "bonus": 13771},
    ],
    # wave 3 (Advisor parity): the crafted-gear upgrade ladder. A crafted epic starts at 305
    # for a Spark (no crests), then upgrades like any other track: 318 with 80 Hero-tier crests,
    # 331 with 80 Myth-tier crests (Styka's datamined Midnight S2 table, cross-checked against
    # the flat 331 ``max_ilevel``/``bonus_ids`` above -- those still describe the item's bonus
    # ids at max quality; only the acquisition ``ilevel`` differs per tier, same trick the
    # advisor's crafted candidates already use via ``CraftedSource.ilevel``). ``crest`` names
    # are exactly ``upgrade_tracks[*].crest.name`` so ``advisor.py`` can look up owned amounts
    # the same way ``upgrade_path`` does. ``spark_id`` is the character-export currency id for
    # Spark of Tides (``kind="item"`` in ``CharacterProfile.currencies``, not a WoW currency).
    "spark_id": 274476,
    "spark_name": "Spark of Tides",
    "tiers": [
        {"ilevel": 305, "crest": None, "cost": 0, "requires": "spark"},
        {"ilevel": 318, "crest": "Hero Mistcrest", "cost": 80},
        {"ilevel": 331, "crest": "Myth Mistcrest", "cost": 80},
    ],
}
# Only a Myth-track Voidforge exists this season (research: scratchpad w2 v_q5_* sims against
# SimC 1210-01 -- appending/replacing the Myth track bonus with 13848 both resolve to ilvl 344,
# there is no Hero/crafted Voidforged variant this season). OPEN QUESTION: which slots can
# actually be Voidforged in-game beyond weapons/trinkets was not verified against a live
# Voidsmith NPC, only against the bonus ids SimC's MID2 profiles carry -- see data/README.md.
VOIDFORGED = {"slots": ["main_hand", "off_hand", "trinket1", "trinket2"], "myth_ilevel": 344, "bonus_id": 13848}
# known crafting-quality offset bonus ids (0 or +13 ilvl); crafted_variant() swaps between them
_CRAFTED_QUALITY_BONUS_IDS = {9627, 12493, 12497}
CREST_ACHIEVEMENTS = {"Adventurer": 62410, "Veteran": 62411, "Champion": 62412, "Hero": 62414, "Myth": 62416}

# ---------------------------------------------------------------------------
# curated: sockets (Raidbots parity, wave 2). Add-socket bonus id 1808 (Raidbots parity name;
# SimC applies every gem_id regardless of socket count, so the app must cap gems itself --
# scratchpad w2/q4.py + v_q4_*). 8781/8782 are the DB2 "N sockets" bonuses (2/3). Vault reward
# sockets land on head/wrist/waist; the Jewelbinder (item 263897) sockets neck + both rings.
SOCKETS = {
    "add_bonus_id": 1808,
    "two": 8781,
    "three": 8782,
    "vault_slots": ["head", "wrist", "waist"],
    "jewelbinder_slots": ["neck", "finger1", "finger2"],
    "jewelbinder_item": 263897,
}

# ---------------------------------------------------------------------------
# curated: Catalyst (Raidbots parity, wave 2). Transcribed from Raidbots' item-conversions.json
# (conversion id 13) cross-checked against DB2 ItemSet/ItemSetSpell for build 12.1.0.69933
# (scratchpad w2/cat.py); see THIRD_PARTY.md. SimC line:
#   <slot>=,id=<tier item id>,bonus_id=<source bonus ids>[/13662],gem_id=<source gems>,
#   enchant_id=<source enchant>,redirected_base_stats=<source item id>
# 13662 (item-conversion marker) is cosmetic -- SimC 1210-01 ignores it (verified identical
# stats/dps with and without, scratchpad w2/v_q1h_*).
CATALYST_CONVERSION_ID = 13
CATALYST_CURRENCY_ID = 3465
CATALYST_CURRENCY_NAME = "Venomblight Manaflux"
CATALYST_MARKER_BONUS_IDS = [13662]
CATALYST_TIER_SLOTS = ["head", "shoulder", "chest", "hands", "legs"]
CATALYST_NON_TIER_SLOTS = ["back", "wrist", "waist", "feet"]
CATALYST_SLOTS = CATALYST_TIER_SLOTS + CATALYST_NON_TIER_SLOTS
# inventory type -> slot for the *source* item being catalyzed (20 = robe -> chest)
CATALYST_SOURCE_INV_TYPES: dict[int, str] = {
    1: "head", 3: "shoulder", 5: "chest", 20: "chest", 6: "waist",
    7: "legs", 8: "feet", 9: "wrist", 10: "hands", 16: "back",
}
# per class: set id, tier item ids by slot, 2pc/4pc set-bonus spell ids by spec (SimC spec slug).
CATALYST_CLASSES: dict[str, dict] = {
    "warrior": {
        "set_id": 2067, "chest_inventory_type": 5,
        "items": {"head": 271456, "shoulder": 271454, "chest": 271459, "hands": 271457, "legs": 271455, "back": 271451, "wrist": 271452, "waist": 271453, "feet": 271458},
        "set_bonuses": {"arms": {"2": 1296643, "4": 1296644}, "fury": {"2": 1296645, "4": 1296646}, "protection": {"2": 1296647, "4": 1296648}},
    },
    "paladin": {
        "set_id": 2062, "chest_inventory_type": 5,
        "items": {"head": 271465, "shoulder": 271463, "chest": 271468, "hands": 271466, "legs": 271464, "back": 271460, "wrist": 271461, "waist": 271462, "feet": 271467},
        "set_bonuses": {"holy": {"2": 1296656, "4": 1296657}, "protection": {"2": 1296658, "4": 1296659}, "retribution": {"2": 1296660, "4": 1296661}},
    },
    "hunter": {
        "set_id": 2059, "chest_inventory_type": 5,
        "items": {"head": 271492, "shoulder": 271490, "chest": 271495, "hands": 271493, "legs": 271491, "back": 271487, "wrist": 271488, "waist": 271489, "feet": 271494},
        "set_bonuses": {"beast_mastery": {"2": 1296631, "4": 1296632}, "marksmanship": {"2": 1296633, "4": 1296634}, "survival": {"2": 1296636, "4": 1296635}},
    },
    "rogue": {
        "set_id": 2064, "chest_inventory_type": 5,
        "items": {"head": 271510, "shoulder": 271508, "chest": 271513, "hands": 271511, "legs": 271509, "back": 271505, "wrist": 271506, "waist": 271507, "feet": 271512},
        "set_bonuses": {"assassination": {"2": 1296590, "4": 1296591}, "outlaw": {"2": 1296588, "4": 1296589}, "subtlety": {"2": 1296592, "4": 1296593}},
    },
    "priest": {
        "set_id": 2063, "chest_inventory_type": 20,
        "items": {"head": 271555, "shoulder": 271553, "chest": 271558, "hands": 271556, "legs": 271554, "back": 271550, "wrist": 271551, "waist": 271552, "feet": 271557},
        "set_bonuses": {"discipline": {"2": 1296577, "4": 1296578}, "holy": {"2": 1296575, "4": 1296576}, "shadow": {"2": 1296579, "4": 1296580}},
    },
    "death_knight": {
        "set_id": 2055, "chest_inventory_type": 5,
        "items": {"head": 271474, "shoulder": 271472, "chest": 271477, "hands": 271475, "legs": 271473, "back": 271469, "wrist": 271470, "waist": 271471, "feet": 271476},
        "set_bonuses": {"blood": {"2": 1296650, "4": 1296651}, "frost": {"2": 1296652, "4": 1296653}, "unholy": {"2": 1296654, "4": 1296655}},
    },
    "shaman": {
        "set_id": 2065, "chest_inventory_type": 20,
        "items": {"head": 271483, "shoulder": 271481, "chest": 271486, "hands": 271484, "legs": 271482, "back": 271478, "wrist": 271479, "waist": 271480, "feet": 271485},
        "set_bonuses": {"elemental": {"2": 1296625, "4": 1296626}, "enhancement": {"2": 1296627, "4": 1296628}, "restoration": {"2": 1296629, "4": 1296630}},
    },
    "mage": {
        "set_id": 2060, "chest_inventory_type": 20,
        "items": {"head": 271564, "shoulder": 271562, "chest": 271567, "hands": 271565, "legs": 271563, "back": 271559, "wrist": 271560, "waist": 271561, "feet": 271566},
        "set_bonuses": {"arcane": {"2": 1296581, "4": 1296582}, "fire": {"2": 1296583, "4": 1296584}, "frost": {"2": 1296585, "4": 1296586}},
    },
    "warlock": {
        "set_id": 2066, "chest_inventory_type": 20,
        "items": {"head": 271546, "shoulder": 271544, "chest": 271549, "hands": 271547, "legs": 271545, "back": 271541, "wrist": 271542, "waist": 271543, "feet": 271548},
        "set_bonuses": {"affliction": {"2": 1296568, "4": 1296569}, "demonology": {"2": 1296573, "4": 1296574}, "destruction": {"2": 1296571, "4": 1296572}},
    },
    "monk": {
        "set_id": 2061, "chest_inventory_type": 5,
        "items": {"head": 271519, "shoulder": 271517, "chest": 271522, "hands": 271520, "legs": 271518, "back": 271514, "wrist": 271515, "waist": 271516, "feet": 271521},
        "set_bonuses": {"brewmaster": {"2": 1296617, "4": 1296618}, "windwalker": {"2": 1296621, "4": 1296624}, "mistweaver": {"2": 1296619, "4": 1296620}},
    },
    "druid": {
        "set_id": 2057, "chest_inventory_type": 20,
        "items": {"head": 271528, "shoulder": 271526, "chest": 271531, "hands": 271529, "legs": 271527, "back": 271523, "wrist": 271524, "waist": 271525, "feet": 271530},
        "set_bonuses": {"balance": {"2": 1296603, "4": 1296604}, "feral": {"2": 1296605, "4": 1296606}, "guardian": {"2": 1296607, "4": 1296608}, "restoration": {"2": 1296609, "4": 1296610}},
    },
    "demon_hunter": {
        "set_id": 2056, "chest_inventory_type": 5,
        "items": {"head": 271537, "shoulder": 271535, "chest": 271540, "hands": 271538, "legs": 271536, "back": 271532, "wrist": 271533, "waist": 271534, "feet": 271539},
        "set_bonuses": {"havoc": {"2": 1296611, "4": 1296612}, "vengeance": {"2": 1296613, "4": 1296614}, "devourer": {"2": 1296615, "4": 1296616}},
    },
    "evoker": {
        "set_id": 2058, "chest_inventory_type": 5,
        "items": {"head": 271501, "shoulder": 271499, "chest": 271504, "hands": 271502, "legs": 271500, "back": 271496, "wrist": 271497, "waist": 271498, "feet": 271503},
        "set_bonuses": {"devastation": {"2": 1296639, "4": 1296640}, "preservation": {"2": 1296641, "4": 1296642}, "augmentation": {"2": 1296637, "4": 1296638}},
    },
}


def _catalyst_payload() -> dict:
    """The season.json ``catalyst`` block: same class data as ``CATALYST_CLASSES`` but
    ``items`` re-keyed by source inventory type (str) so ``catalyst_item_for`` can look a
    dropped/bagged item's tier twin up directly off its ``inventory_type`` -- both possible
    chest inventory types (5 plate/mail/leather, 20 robe) map to the same tier chest item id
    for every class, so ``inventory_type=20`` always resolves ("type 20 -> chest")."""
    items_by_class: dict[str, dict[str, int]] = {}
    for klass, e in CATALYST_CLASSES.items():
        by_inv: dict[str, int] = {}
        for slot, item_id in e["items"].items():
            if slot == "chest":
                by_inv["5"] = item_id
                by_inv["20"] = item_id
            else:
                inv = next(i for i, s in CATALYST_SOURCE_INV_TYPES.items() if s == slot)
                by_inv[str(inv)] = item_id
        items_by_class[klass] = by_inv
    return {
        "conversion_id": CATALYST_CONVERSION_ID,
        "currency_id": CATALYST_CURRENCY_ID,
        "currency_name": CATALYST_CURRENCY_NAME,
        "marker_bonus_ids": CATALYST_MARKER_BONUS_IDS,
        "slots": CATALYST_SLOTS,
        "tier_slots": CATALYST_TIER_SLOTS,
        "non_tier_slots": CATALYST_NON_TIER_SLOTS,
        "set_ids": {k: v["set_id"] for k, v in CATALYST_CLASSES.items()},
        "items": items_by_class,
        "set_bonus_spells": {k: v["set_bonuses"] for k, v in CATALYST_CLASSES.items()},
    }


# ---------------------------------------------------------------------------
# curated: Omnium Folio (Raidbots parity, wave 2). TraitTree 1186 (TraitSystem 48), 5 rows /
# one choice each; transcribed from DB2 TraitTree/TraitNode/TraitNodeEntry/TraitNodeXEntry +
# Spell (build 12.1.0.69933, scratchpad w2/omn.py -> omnium_tree_1186.json). Export format:
# ``omnium_talents=<entry_id>:<rank>/...``; SimC also accepts the ``simc_token`` runes
# separated by ``/`` (scratchpad w2/v_q6_*).
OMNIUM_TREE_ID = 1186
OMNIUM_ROWS: list[dict] = [
    {"row": 1, "node_id": 110275, "choices": [
        {"entry_id": 136825, "token": "rune_of_voidtouched_orbs", "name": "Rune of Void-Touched Orbs", "icon": "inv_12_dh_void_ability_soulfragments"},
        {"entry_id": 136822, "token": "rune_of_unleashed_fire", "name": "Rune of Unleashed Fire", "icon": "inv_summerfest_firespirit"},
    ]},
    {"row": 2, "node_id": 110274, "choices": [
        {"entry_id": 136819, "token": "rune_of_selfmending", "name": "Rune of Self-Mending", "icon": "spell_shadow_felmending"},
        {"entry_id": 136816, "token": "rune_of_voidtainted_shell", "name": "Rune of Void-Tainted Shell", "icon": "ability_rhyolith_magmaflow_wave"},
        {"entry_id": 136823, "token": "rune_of_lynxlike_reflexes", "name": "Rune of Lynxlike Reflexes", "icon": "inv_babyarathilynx_gold"},
    ]},
    {"row": 3, "node_id": 110273, "choices": [
        {"entry_id": 136817, "token": "rune_of_lingering", "name": "Rune of Lingering", "icon": "item_shadowcloth"},
    ]},
    {"row": 4, "node_id": 110272, "choices": [
        {"entry_id": 136815, "token": "rune_of_critical_power", "name": "Rune of Critical Power", "icon": "spell_mage_overpowered"},
        {"entry_id": 136821, "token": "rune_of_burning_haste", "name": "Rune of Burning Haste", "icon": "spell_fire_burningspeed"},
        {"entry_id": 136818, "token": "rune_of_masterful_cunning", "name": "Rune of Masterful Cunning", "icon": "ability_hunter_fervor"},
        {"entry_id": 136820, "token": "rune_of_the_versatile_warrior", "name": "Rune of the Versatile Warrior", "icon": "ability_warrior_stalwartprotector"},
    ]},
    {"row": 5, "node_id": 110271, "choices": [
        {"entry_id": 136814, "token": "rune_of_overload", "name": "Rune of Overload", "icon": "ability_siege_engineer_overload"},
        {"entry_id": 136824, "token": "rune_of_residual_energy", "name": "Rune of Residual Energy", "icon": "inv_112_raidtrinkets_etherealenergystoragesphere_purple"},
        {"entry_id": 136826, "token": "rune_of_echoes", "name": "Rune of Echoes", "icon": "spell_rogue_shadow_reflection"},
    ]},
]


# ---------------------------------------------------------------------------

def _clean_consumable(v: str) -> str:
    v = v.split(",if=")[0].strip()
    if v == "disabled":
        return ""
    if v == "magisters_2":
        v = "flask_of_the_magisters_2"
    return v


def consumables_for(klass: str, spec: str, role: str = "attack", primary: str | None = None) -> dict[str, str]:
    key = f"{klass.replace('deathknight', 'death_knight').replace('demonhunter', 'demon_hunter')}_{spec}"
    base = _RAW_CONSUMABLES.get(key)
    if base is None:
        base = _CONSUMABLES_BY_PRIMARY.get(primary or "", None) or _CONSUMABLES_BY_ROLE.get(role, _CONSUMABLES_BY_ROLE["attack"])
    return {k: _clean_consumable(v) for k, v in base.items()}


def _track_for_ilevel(tracks: dict[str, dict], ilevel: int) -> tuple[str, int] | None:
    """(track, rank) whose ladder contains ``ilevel``; the highest track wins on overlaps."""
    best = None
    for name, t in tracks.items():
        if ilevel in t["ilevels"]:
            best = (name, t["ilevels"].index(ilevel) + 1)
    return best


def _keys(build: str | None, tracks: dict[str, dict]) -> list[dict]:
    out = []
    for level in sorted(MPLUS_END):
        il, vl = MPLUS_END[level], MPLUS_VAULT[level]
        t = _track_for_ilevel(tracks, il)
        vt = _track_for_ilevel(tracks, vl)
        out.append({
            "level": level, "ilevel": il, "vault_ilevel": vl,
            "track": t[0] if t else None, "rank": t[1] if t else None,
            "vault_track": vt[0] if vt else None, "vault_rank": vt[1] if vt else None,
            "bonus_ids": [tracks[t[0]]["bonus_ids"][t[1] - 1]] if t else [],
            "vault_bonus_ids": [tracks[vt[0]]["bonus_ids"][vt[1] - 1]] if vt else [],
        })
    return out


def _delves(tracks: dict[str, dict]) -> list[dict]:
    out = []
    for d in DELVES:
        t = _track_for_ilevel(tracks, d["ilevel"])
        vt = _track_for_ilevel(tracks, d["vault_ilevel"])
        out.append({
            **d,
            "track": t[0] if t else None, "rank": t[1] if t else None,
            "vault_track": vt[0] if vt else None, "vault_rank": vt[1] if vt else None,
            "bonus_ids": [tracks[t[0]]["bonus_ids"][t[1] - 1]] if t else [],
            "vault_bonus_ids": [tracks[vt[0]]["bonus_ids"][vt[1] - 1]] if vt else [],
            "verified": d["tier"] >= 8,
        })
    return out


def journal(build: str | None = None) -> dict:
    """Live-season instances from the journal tables (see module docstring)."""
    txi = wago.table("JournalTierXInstance", build)
    ji = wago.table("JournalInstance", build, ["ID", "Name_lang", "MapID", "Flags"])
    mp = wago.table("Map", build, ["ID", "InstanceType", "ExpansionID"])
    je = wago.table("JournalEncounter", build, ["ID", "Name_lang", "JournalInstanceID", "OrderIndex", "DungeonEncounterID", "DifficultyMask"])
    jei = wago.table("JournalEncounterItem", build, ["ID", "JournalEncounterID", "ItemID"])
    mt = wago.table("MythicPlusSeasonTrackedMap", build)
    mc = wago.table("MapChallengeMode", build, ["ID", "Name_lang", "MapID"])

    mplus_season = int(mt["DisplaySeasonID"].max())
    pool_maps = mt.filter(pl.col("DisplaySeasonID") == mplus_season).join(mc, left_on="MapChallengeModeID", right_on="ID")
    pool_map_ids = set(pool_maps["MapID"].to_list())

    tier = txi.filter(pl.col("JournalTierID") == CURRENT_SEASON_TIER) \
        .join(ji, left_on="JournalInstanceID", right_on="ID") \
        .join(mp, left_on="MapID", right_on="ID", how="left")
    groups = {int(c) for c, m in zip(tier["AvailabilityCondition"].to_list(), tier["MapID"].to_list(), strict=True) if int(m) in pool_map_ids}
    groups.add(0)
    newest = tier.filter(pl.col("ExpansionID") == CURRENT_EXPANSION)["AvailabilityCondition"].max()
    if newest is not None:
        groups.add(int(newest))
    live = tier.filter(pl.col("AvailabilityCondition").is_in(list(groups)))

    def bosses_of(inst_id: int) -> list[dict]:
        rows = je.filter(pl.col("JournalInstanceID") == inst_id).sort("OrderIndex")
        out = []
        for order, r in enumerate(rows.iter_rows(named=True)):
            n_items = int(jei.filter(pl.col("JournalEncounterID") == r["ID"]).height)
            if n_items == 0:
                continue
            out.append({
                "encounter_id": int(r["ID"]), "name": str(r["Name_lang"]), "order": order,
                "dungeon_encounter_id": int(r["DungeonEncounterID"] or 0),
                "sequence": droplevels.sequence_level(int(r["DungeonEncounterID"] or 0), build),
                "item_count": n_items,
            })
        return out

    raids, dungeons, world = [], [], []
    for r in live.sort("OrderIndex").iter_rows(named=True):
        inst = {"instance_id": int(r["JournalInstanceID"]), "journal_instance_id": int(r["JournalInstanceID"]),
                "name": str(r["Name_lang"]), "map_id": int(r["MapID"]), "bosses": bosses_of(int(r["JournalInstanceID"]))}
        if not inst["bosses"]:
            continue
        if int(r["Flags"] or 0) & 2:
            world.append(inst)
        elif int(r["InstanceType"] or 0) == 2:
            raids.append(inst)
        elif int(r["MapID"]) in pool_map_ids:
            dungeons.append(inst)
    # dungeons named in the pool but sitting outside the tier (returning dungeons)
    seen = {d["map_id"] for d in dungeons}
    for m in pool_maps.iter_rows(named=True):
        if int(m["MapID"]) in seen:
            continue
        cand = ji.filter(pl.col("MapID") == int(m["MapID"])).sort("ID", descending=True)
        if cand.height:
            c = cand.row(0, named=True)
            dungeons.append({"instance_id": int(c["ID"]), "journal_instance_id": int(c["ID"]), "name": str(c["Name_lang"]),
                             "map_id": int(c["MapID"]), "bosses": bosses_of(int(c["ID"]))})
    return {"mplus_season_id": mplus_season, "condition_groups": sorted(groups), "raids": raids, "dungeons": dungeons,
            "world_bosses": world, "pool": [{"map_id": int(m["MapID"]), "name": str(m["Name_lang"])} for m in pool_maps.iter_rows(named=True)]}


def _raid_difficulties(raid: dict, build: str | None) -> dict:
    """Per-difficulty drop levels for a raid: first boss level at instance level, per boss below."""
    jei = wago.table("JournalEncounterItem", build, ["JournalEncounterID", "ItemID"])
    diffs: dict[str, dict] = {}
    for boss in raid["bosses"]:
        seq = boss.get("sequence")
        items = jei.filter(pl.col("JournalEncounterID") == boss["encounter_id"])["ItemID"].to_list()
        drops: dict[str, dict] = {}
        for item in items:
            if seq is None:
                break
            d = droplevels.drops_for(int(item), seq, build)
            if d:
                drops = d
                break
        boss["drops"] = drops
        for diff, d in drops.items():
            cur = diffs.get(diff)
            if cur is None or d["ilevel"] < cur["ilevel"]:
                diffs[diff] = {"ilevel": d["ilevel"], "track": d["track"], "rank": d["step"],
                               "bonus_ids": [droplevels.DIFFICULTY_TAG_BONUS[diff], d["bonus_id"]]}
    for diff, d in diffs.items():
        d["max_ilevel"] = max((b["drops"][diff]["ilevel"] for b in raid["bosses"] if diff in b.get("drops", {})), default=d["ilevel"])
    return diffs


def generate(build: str | None = None) -> dict:
    build = build or wago.effective_build()
    tracks = bonuses.season_tracks(UPGRADE_SEASON_ID, build)
    for name, t in tracks.items():
        t["achievement_id"] = CREST_ACHIEVEMENTS.get(name)
        t.setdefault("crest", {})["discounted_cost"] = 10
    j = journal(build)
    for raid in j["raids"]:
        raid["difficulties"] = _raid_difficulties(raid, build)
    wb = _track_for_ilevel(tracks, WORLD_BOSS_ILEVEL)
    cons_by_spec = {k: {kk: _clean_consumable(vv) for kk, vv in v.items()} for k, v in _RAW_CONSUMABLES.items()}
    return {
        "season": "Midnight Season 2 (12.1)",
        "season_id": UPGRADE_SEASON_ID,
        "build": build,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "verified_against": (
            "DB2 12.1.0.69875: MythicPlusSeasonTrackedMap.DisplaySeasonID=37 pool = "
            + ", ".join(p["name"] for p in j["pool"])
            + "; JournalTier 505 condition group 156363 holds that pool plus The Tidebound Grotto / The Venomous Abyss; "
            "Raidbots bonuses.json upgrade seasonId 37 (groups 614-618); simc profiles/MID2 gear carries 12854/13848 (Myth 6/6 334, Voidforged 344); "
            "cross-checked with localbots data/season.json (Midnight Season 2, upgradeSeasonId 37, same 8 keystone dungeons)."
        ),
        "notes": {
            "raids": "Per-boss drop levels come from DungeonEncounter.ItemSequenceLevel + the item's bonus tree (see droplevels.py); instance-level 'ilevel' is the first boss, 'max_ilevel' the last.",
            "key_levels": "M+ table from localbots (season 2), track split cross-checked against the 12.1 keystone bonus-tree nodes.",
            "delves": "Tier 8+ from localbots' season-2 notes; tiers 1-7 extrapolated along the track ladders, not verified in game.",
            "world_bosses": "302 (Champion 4/6) from localbots; not verified in game.",
            "consumables": "Defaults per spec from simulationcraft/simc profiles/MID2; specs without a profile fall back by primary stat / role.",
            "enchants": "Ids per slot from SpellItemEnchantment; picks are the enchant_id most used by simulationcraft/simc profiles/MID2 (head/shoulder/feet are utility only and are not simmed).",
            "tier_sets": "Tier pieces are not in the raid loot journal for these raids (obtained through the Catalyst); see data/README.md limitations.",
        },
        "mplus_season_id": j["mplus_season_id"],
        "raids": j["raids"],
        "dungeons": [{k: v for k, v in d.items()} for d in j["dungeons"]],
        "world_bosses": [{**w, "ilevel": WORLD_BOSS_ILEVEL, "track": wb[0] if wb else None, "rank": wb[1] if wb else None,
                          "bonus_ids": [tracks[wb[0]]["bonus_ids"][wb[1] - 1]] if wb else []} for w in j["world_bosses"]],
        "key_levels": _keys(build, tracks),
        "delves": _delves(tracks),
        "upgrade_tracks": tracks,
        "crest_cost": 20,
        "crest_cost_discounted": 10,
        "crafted": CRAFTED,
        "voidforged": VOIDFORGED,
        "max_ilevel": VOIDFORGED["myth_ilevel"],
        "catalyst": _catalyst_payload(),
        "sockets": SOCKETS,
        "omnium": {"tree_id": OMNIUM_TREE_ID, "rows": OMNIUM_ROWS},
        "consumables": {"by_spec": cons_by_spec, "by_primary": _CONSUMABLES_BY_PRIMARY, "by_role": _CONSUMABLES_BY_ROLE,
                        "options": CONSUMABLE_OPTIONS},
        "enchants": ENCHANTS_BEST,
        "enchants_by_stat": ENCHANTS_BY_STAT,
        "enchant_options": ENCHANT_OPTIONS,
        "gems": GEMS,
        "gem_options": GEM_OPTIONS,
        "diamonds": DIAMONDS,
    }


def write(build: str | None = None, path: Path = SEASON_FILE) -> dict:
    data = generate(build)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    load.cache_clear()
    return data


@lru_cache(maxsize=1)
def _load_cached(mtime: float) -> dict:
    return json.loads(SEASON_FILE.read_text("utf-8"))


def load() -> dict:
    """The season config (``data/season.json``); regenerated on the fly when missing."""
    if not SEASON_FILE.exists():
        if wago.is_ready():
            return write()
        raise FileNotFoundError(f"{SEASON_FILE} missing and the DB2 cache is not ready")
    return _load_cached(SEASON_FILE.stat().st_mtime)


load.cache_clear = _load_cached.cache_clear  # type: ignore[attr-defined]


def delve_pool() -> list[dict]:
    """Curated delve item pool (``data/delve-loot.json``): [{id?, name?}]."""
    if not DELVE_FILE.exists():
        return []
    try:
        return json.loads(DELVE_FILE.read_text("utf-8")).get("items", [])
    except Exception:  # noqa: BLE001 - a corrupt curated file just yields no delve pool
        return []


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ---------------------------------------------------------------------------
# helpers for the sim engines (sims/base.py::apply_season) and /api/data/recommendations
#
# ``_pick_enchant``/``_pick_gem`` are the single source of truth: ``best_enchant``/
# ``best_gems`` (used by ``enchant_all``/``socket_all``) and ``recommendations()`` (the
# `/api/data/recommendations` payload and the gems/upgrades sim engines) all resolve
# through them so they can never disagree about which enchant/gem is "the" recommendation.

_WEAPON_INV_TYPES = {13, 15, 17, 21, 22, 26}
STAT_KEYS: tuple[str, ...] = ("crit", "haste", "mastery", "versatility")
# SimC slot -> ENCHANT_OPTIONS/ENCHANTS_BY_STAT generic key
SLOT_ENCHANT_KEY: dict[str, str] = {
    "head": "head", "shoulder": "shoulder", "chest": "chest", "legs": "legs", "feet": "feet",
    "finger1": "ring", "finger2": "ring", "main_hand": "weapon", "off_hand": "weapon",
}


def utility_enchant_slots() -> list[str]:
    """Enchantable slots whose every option is utility only (``dps: false``), e.g. Midnight's
    head/shoulder/feet speed/leech/avoidance enchants: they exist, but simming them is moot."""
    options: dict[str, list[dict]] = load().get("enchant_options", ENCHANT_OPTIONS)
    return [
        slot for slot, generic in SLOT_ENCHANT_KEY.items()
        if options.get(generic) and all(o.get("dps", True) is False for o in options[generic])
    ]


def _pick_enchant(slot: str, prim: str | None, s: dict | None = None) -> int | None:
    s = s if s is not None else load()
    best: dict[str, int] = s.get("enchants", ENCHANTS_BEST)
    by_stat: dict[str, dict[str, int]] = s.get("enchants_by_stat", ENCHANTS_BY_STAT)
    variants = by_stat.get(slot, {})
    if prim and prim in variants and slot in ("legs",):
        return variants[prim]
    return best.get(slot) or (variants.get("default") if variants else None)


def best_enchant(slot: str, profile: CharacterProfile) -> int | None:
    """The season's best enchant_id for a SimC slot, given the character's primary stat.

    None for slots without an enchant this season (neck, back, wrist, hands, waist,
    trinkets) and for an off-hand that is not a weapon (shield, held item). Head, shoulder
    and feet only have utility enchants; their entry is the one SimC's MID2 profiles use most.
    """
    from toonopt.data.loot import primary_stat
    if slot == "off_hand":
        oh = profile.equipped.get("off_hand")
        if oh is not None and oh.inventory_type not in _WEAPON_INV_TYPES:
            return None
    prim = primary_stat(profile.klass, profile.spec)
    return _pick_enchant(slot, prim)


# flask name substring -> the secondary stat it favours (matches CONSUMABLE_OPTIONS' labels)
_FLASK_SECONDARY: dict[str, str] = {
    "shattered_sun": "crit", "blood_knights": "haste", "magisters": "mastery", "thalassian_resistance": "versatility",
}


def _spec_secondary(profile: CharacterProfile) -> str | None:
    """The secondary stat this spec's curated flask favours, so gems/enchants agree with it
    instead of defaulting to mastery for every spec."""
    flask = consumables_for(profile.klass, profile.spec, profile.role).get("flask", "")
    for key, stat in _FLASK_SECONDARY.items():
        if key in flask:
            return stat
    return None


def _pick_gem(stat: str | None, s: dict | None = None) -> int:
    s = s if s is not None else load()
    gems: dict[str, int] = s.get("gems", GEMS)
    return (gems.get(stat) if stat else None) or gems["default"]


def best_gems(item: Item, profile: CharacterProfile) -> list[int]:
    """Gem ids filling every socket of ``item`` (from its socket bonus ids).

    Sockets on current-season loot are granted by a bonus id (``ItemBonus`` type 6 /
    Raidbots' ``socket`` flag), not by ``ItemSparse.SocketType`` -- that column is a static
    per-item-id placeholder and does not reflect whether *this* bonus roll actually has the
    socket (e.g. item 268265 carries ``SocketType_0`` regardless of whether bonus id 13668,
    the one that actually grants the socket, is present). So only the bonus ids on this
    concrete item count.
    """
    s = load()
    n = bonuses.socket_count(item.bonus_ids)
    if n == 0 and item.gem_ids:
        n = len(item.gem_ids)
    if n <= 0:
        return []
    # keep a diamond the character already put in this item; never invent one
    diamonds = set(s.get("diamonds", DIAMONDS).get("known_ids", []))
    kept = [g for g in item.gem_ids if g in diamonds][:1]
    gem_id = _pick_gem(_spec_secondary(profile), s)
    return kept + [gem_id] * (n - len(kept))


# ---------------------------------------------------------------------------
# names/icons for gems (Item/ItemSparse) and enchants (SpellItemEnchantment)

@lru_cache(maxsize=4)
def _enchant_rows(build: str | None = None) -> dict[int, dict]:
    df = wago.table("SpellItemEnchantment", build, ["ID", "Name_lang", "IconFileDataID"])
    return {int(r["ID"]): r for r in df.iter_rows(named=True)}


def _icon_file_names(file_ids: list[int], build: str | None = None) -> dict[int, str]:
    if not file_ids:
        return {}
    mid = wago.table("ManifestInterfaceData", build, ["ID", "FileName"])
    df = mid.filter(pl.col("ID").is_in(file_ids))
    out = {}
    for i, n in zip(df["ID"].to_list(), df["FileName"].to_list(), strict=True):
        name = str(n or "")
        if name.lower().endswith(".blp"):
            name = name[:-4]
        out[int(i)] = name.lower()
    return out


@lru_cache(maxsize=4)
def _limit_quantities(build: str | None = None) -> dict[int, tuple[str, int]]:
    df = wago.table("ItemLimitCategory", build, ["ID", "Name_lang", "Quantity"])
    return {
        int(i): (str(n), int(q or 0))
        for i, n, q in zip(df["ID"].to_list(), df["Name_lang"].to_list(), df["Quantity"].to_list(), strict=True)
    }


def gem_limit(gem_id: int, build: str | None = None) -> tuple[str, int] | None:
    """``(limit category name, max equipped)`` for a unique-equipped gem, else None.

    Limits are per *category*, not per gem id: every Eversong Diamond (all ranks, all
    variants) shares ItemLimitCategory 698 "Thalassian Diamond", Quantity 1 -- one diamond
    per character. Read from ItemSparse.LimitCategory; falls back to the curated diamond ids
    when the DB2 cache is unavailable.
    """
    try:
        r = items.row(gem_id, build)
    except Exception:  # noqa: BLE001 - DB2 cache optional
        r = None
    if r:
        lc = int(r.get("LimitCategory") or 0)
        if not lc:
            return None
        name, qty = _limit_quantities(build).get(lc, (f"limit category {lc}", 1))
        return name, max(1, qty)
    if int(gem_id) in set(load().get("diamonds", DIAMONDS).get("known_ids", [])):
        return "Thalassian Diamond", 1
    return None


def gem_name(gem_id: int, build: str | None = None) -> str:
    r = items.row(gem_id, build)
    return str(r.get("Display_lang") or "") if r else ""


def _gem_ref(gem_id: int, stat: str, limited: bool = False, build: str | None = None) -> dict:
    r = items.row(gem_id, build)
    out = {
        "id": int(gem_id),
        "name": str(r.get("Display_lang") or "") if r else "",
        "icon": items.icon(gem_id, build) if r else "",
        "stat": stat,
    }
    if limited:
        category, qty = gem_limit(gem_id, build) or ("Thalassian Diamond", 1)
        out["limit"] = qty
        out["limit_category"] = category
    return out


# SpellItemEnchantment.Name_lang carries chat-link/atlas markup (|A:...|a, |T...|t); some
# entries (leg armor kits) store an unresolved tooltip formula ("+$k2 Agility...") instead
# of a real name -- fall back to the curated label from ENCHANT_OPTIONS for those.
_ENCHANT_MARKUP_RE = re.compile(r"\|[Aa]:[^|]*\|a|\|T[^|]*\|t")


def _clean_enchant_name(raw: str, fallback: str) -> str:
    name = _ENCHANT_MARKUP_RE.sub("", raw).strip()
    return name if name and "$" not in name else fallback


def _enchant_ref(enchant_id: int, stat: str | None, recommended: bool, build: str | None = None,
                  fallback: str = "") -> dict:
    r = _enchant_rows(build).get(int(enchant_id), {})
    name = _clean_enchant_name(str(r.get("Name_lang") or ""), fallback or str(enchant_id))
    out: dict = {"id": int(enchant_id), "name": name, "recommended": recommended}
    file_id = int(r.get("IconFileDataID") or 0)
    if file_id:
        icon = _icon_file_names([file_id], build).get(file_id)
        if icon:
            out["icon"] = icon
    if stat:
        out["stat"] = stat
    return out


def recommendations(klass: str, spec: str, build: str | None = None) -> dict:
    """The `/api/data/recommendations` payload: season gems/enchants/consumables for a
    klass/spec, resolved through the same ``_pick_enchant``/``_pick_gem`` helpers
    ``best_enchant``/``best_gems`` use, so the two never disagree.
    """
    s = load()
    profile = CharacterProfile(name="", klass=klass, spec=spec)
    try:
        from toonopt.data.loot import primary_stat
        prim = primary_stat(klass, spec)
    except Exception:  # noqa: BLE001 - loot layer optional
        prim = None
    stat = _spec_secondary(profile)

    by_stat_gems = {st: _gem_ref(_pick_gem(st, s), st, build=build) for st in STAT_KEYS}
    gem_default = _gem_ref(_pick_gem(stat, s), stat or "mastery", build=build)
    diamonds = s.get("diamonds", DIAMONDS)
    unique = [
        _gem_ref(int(d["id"]), "primary" if d["id"] == diamonds.get("options", [{}])[0].get("id") else "special",
                 limited=True, build=build)
        for d in diamonds.get("options", [])
    ]

    options: dict[str, list[dict]] = s.get("enchant_options", ENCHANT_OPTIONS)
    enchants: dict[str, list[dict]] = {}
    for slot, generic in SLOT_ENCHANT_KEY.items():
        opts = [o for o in options.get(generic, []) if o.get("dps", True) is not False]
        if not opts:
            continue
        rec_id = _pick_enchant(slot, prim, s)
        refs = [_enchant_ref(o["id"], o.get("stat"), o["id"] == rec_id, build, fallback=o.get("label", "")) for o in opts]
        refs.sort(key=lambda r: not r["recommended"])
        enchants[slot] = refs

    cat = s.get("catalyst", {})
    omn = s.get("omnium", {})
    return {
        "season": s.get("season", "Season"),
        "gems": {"default": gem_default, "by_stat": by_stat_gems, "unique": unique},
        "enchants": enchants,
        "consumables": consumables_for(klass, spec, primary=prim),
        "catalyst": {"charges_currency_id": cat.get("currency_id"), "slots": cat.get("slots", [])},
        "omnium": {"rows": omn.get("rows", [])},
    }


# ---------------------------------------------------------------------------
# upgrade tracks (sims/upgrades.py)

@dataclass
class UpgradeStep:
    rank: int
    ilevel: int
    bonus_ids: list[int] = field(default_factory=list)   # item.bonus_ids with the track bonus swapped in
    crest: str = ""
    cost: int = 0                                         # crests for this single rank (flat per track)


def upgrade_path(item: Item, build: str | None = None) -> list[UpgradeStep]:
    """Remaining upgrade ranks for ``item``, detected from its bonus ids.

    Empty when the item carries no bonus id from this season's upgrade tracks (crafted
    gear, last season's leftovers, already at max rank, or a track missing from
    ``season.json``).
    """
    up = bonuses.upgrade_of(item.bonus_ids, build, season_id=UPGRADE_SEASON_ID)
    if not up:
        return []
    s = load()
    tracks: dict[str, dict] = s.get("upgrade_tracks", {})
    track = tracks.get(up["track"])
    if not track:
        return []
    old_bonus_id = up["bonus_id"]
    current_rank = up["level"]
    crest = track.get("crest", {})
    crest_name = crest.get("name") or up["track"]
    per_rank_cost = int(crest.get("cost") or 0)
    out: list[UpgradeStep] = []
    for step in track.get("steps", []):
        rank = int(step["rank"])
        if rank <= current_rank:
            continue
        new_bonus_ids = [step["bonus_id"] if b == old_bonus_id else b for b in item.bonus_ids]
        out.append(UpgradeStep(rank=rank, ilevel=int(step["ilevel"]), bonus_ids=new_bonus_ids,
                               crest=crest_name, cost=per_rank_cost))
    return out


# ---------------------------------------------------------------------------
# Raidbots parity, wave 2: Catalyst, sockets, Voidforge, crafted recraft, Omnium Folio,
# consumable options. These build variant ``Item``s for the sim engines (Top Gear/Droptimizer
# own the combination logic; this module only knows how to make one variant of one item).
#
# ``models.py`` is owned by another agent this wave and carries no dedicated field for SimC's
# ``redirected_base_stats=`` line -- ``catalyst_variant`` appends it to the returned Item's
# ``simc_string`` (``Item.to_simc()`` output does not include it). Engines that build a
# .simc file from a catalyzed Item MUST use ``item.simc_string`` verbatim for that item's gear
# line rather than re-rendering it with ``to_simc()``, or the redirect is silently dropped.

def _preserve_ilevel(new_bonus_ids: list[int], current_ilevel: int) -> int | None:
    """``None`` (let ``items.resolve_item`` derive the level from ``new_bonus_ids``) unless
    the bonus ids alone can't produce one, in which case fall back to ``current_ilevel`` so an
    item with an explicit ``ilevel=`` override (no level-bearing bonus id at all) doesn't lose
    its level when only its gems/embellishment/etc. change."""
    return None if bonuses.ilevel_from_bonuses(new_bonus_ids) else current_ilevel


def catalyst() -> dict:
    """The season.json ``catalyst`` block (see the module docstring / API.md)."""
    return load().get("catalyst", {})


def catalyst_set_id(klass: str) -> int | None:
    """This class's Catalyst tier-set id (``ItemSet``), or None for an unknown class."""
    return catalyst().get("set_ids", {}).get(klass)


def catalyst_item_for(klass: str, inventory_type: int) -> int | None:
    """The tier item id ``klass`` gets from the Catalyst for a source item of
    ``inventory_type`` (DB2 ``InventoryType``; 20 -- robe -- resolves to the chest tier item,
    same as 5), or None if that class/inventory type isn't a Catalyst slot."""
    return catalyst().get("items", {}).get(klass, {}).get(str(inventory_type))


def catalyst_variant(item: Item, klass: str) -> Item | None:
    """The Catalyst's converted twin of ``item`` for ``klass``: the tier item id, ``item``'s own
    bonus ids/gems/enchant (the source dictates track/ilvl/sockets), and a
    ``redirected_base_stats=<source item id>`` note on ``simc_string`` (see the module
    docstring). None when ``item``'s inventory type isn't a Catalyst slot, or it already *is*
    the tier item (already catalyzed)."""
    tier_id = catalyst_item_for(klass, item.inventory_type)
    if tier_id is None or tier_id == item.id:
        return None
    new = items.resolve_item(
        tier_id, list(item.bonus_ids), _preserve_ilevel(item.bonus_ids, item.ilevel),
        key=f"catalyst:{item.key}", slot_hint=item.slot, gem_ids=tuple(item.gem_ids),
        enchant_id=item.enchant_id,
    )
    new.simc_string = f"{new.simc_string},redirected_base_stats={item.id}"
    return new


def socket_rules() -> dict:
    """The season.json ``sockets`` block (see the module docstring / API.md)."""
    return load().get("sockets", SOCKETS)


def socket_variant(item: Item, gem_id: int) -> Item:
    """``item`` with an extra socket (bonus 1808) and ``gem_id`` filling it, capped at the
    item's new socket count (SimC applies every ``gem_id`` regardless of socket count -- see
    ``SOCKETS`` docstring -- so a second call on an already-socketed item still only ever adds
    one more filled socket, never more gems than sockets)."""
    rules = socket_rules()
    add_bonus = int(rules.get("add_bonus_id", SOCKETS["add_bonus_id"]))
    new_bonus_ids = [*item.bonus_ids, add_bonus]
    cap = bonuses.socket_count(new_bonus_ids) or (item.sockets + 1)
    new_gems = [*item.gem_ids, int(gem_id)][:cap] if cap else [*item.gem_ids, int(gem_id)]
    return items.resolve_item(
        item.id, new_bonus_ids, _preserve_ilevel(new_bonus_ids, item.ilevel),
        key=f"socket:{item.key}", slot_hint=item.slot, gem_ids=tuple(new_gems),
        enchant_id=item.enchant_id, crafted_stats=tuple(item.crafted_stats),
        crafting_quality=item.crafting_quality,
    )


def voidforge_variant(item: Item) -> Item | None:
    """The Myth-track Voidforged twin of ``item``: its Myth upgrade-track bonus id replaced by
    ``voidforged.bonus_id`` (13848 -> ilvl 344). None when ``item``'s slot isn't Voidforge-
    eligible (``voidforged.slots``) or it isn't currently at Myth max rank (only a Myth
    Voidforge exists this season -- see ``VOIDFORGED`` docstring)."""
    vf = load().get("voidforged", VOIDFORGED)
    if item.slot not in vf.get("slots", VOIDFORGED["slots"]):
        return None
    up = bonuses.upgrade_of(item.bonus_ids, season_id=UPGRADE_SEASON_ID)
    if not up or up["track"] != "Myth" or not up.get("max") or up["level"] < up["max"]:
        return None
    bonus_id = int(vf.get("bonus_id", VOIDFORGED["bonus_id"]))
    new_bonus_ids = [bonus_id if b == up["bonus_id"] else b for b in item.bonus_ids]
    return items.resolve_item(
        item.id, new_bonus_ids, None, key=f"voidforge:{item.key}", slot_hint=item.slot,
        gem_ids=tuple(item.gem_ids), enchant_id=item.enchant_id,
        crafted_stats=tuple(item.crafted_stats), crafting_quality=item.crafting_quality,
    )


def crafted_variant(item: Item, stats: tuple[str, str], embellishment_id: int | None = None,
                     quality_bonus: int | None = None) -> Item:
    """A recraft of ``item``: strips any ``stat_bonus_ids`` (8790-8795, which override
    ``crafted_stats=`` outright) and sets ``crafted_stats`` to ``stats`` instead; optionally
    swaps in a new embellishment (marker bonus id + the embellishment's own bonus id, replacing
    any existing embellishment) and/or a new crafting-quality bonus (replacing 9627/12493/12497,
    the known quality-offset ids)."""
    crafted = load().get("crafted", CRAFTED)
    stat_bonus_ids = set(crafted.get("stat_bonus_ids", CRAFTED["stat_bonus_ids"]))
    stat_ids: dict[str, int] = crafted.get("stat_ids", CRAFTED["stat_ids"])
    marker = int(crafted.get("embellish_marker", CRAFTED["embellish_marker"]))
    embellishment_ids = {int(e["bonus"]) for e in crafted.get("embellishments", []) if e.get("bonus")}
    embellishment_ids |= {int(e["second_bonus"]) for e in crafted.get("embellishments", []) if e.get("second_bonus")}
    kept = [b for b in item.bonus_ids if b not in stat_bonus_ids]
    if embellishment_id is not None:
        kept = [b for b in kept if b not in embellishment_ids and b != marker]
        kept += [marker, int(embellishment_id)]
    if quality_bonus is not None:
        kept = [b for b in kept if b not in _CRAFTED_QUALITY_BONUS_IDS]
        kept.append(int(quality_bonus))
    new_stats = tuple(stat_ids[s] for s in stats)
    return items.resolve_item(
        item.id, kept, _preserve_ilevel(kept, item.ilevel), key=f"crafted:{item.key}",
        slot_hint=item.slot, gem_ids=tuple(item.gem_ids), enchant_id=item.enchant_id,
        crafted_stats=new_stats, crafting_quality=item.crafting_quality,
    )


def omnium_rows() -> list[dict]:
    """The season.json ``omnium.rows`` (Omnium Folio: 5 rows, one choice each)."""
    return load().get("omnium", {}).get("rows", OMNIUM_ROWS)


def consumable_options() -> dict:
    """The season.json ``consumables.options`` (accepted SimC names per category)."""
    return load().get("consumables", {}).get("options", CONSUMABLE_OPTIONS)


if __name__ == "__main__":
    b = sys.argv[1] if len(sys.argv) > 1 else None
    d = write(b)
    print(f"wrote {SEASON_FILE}: {d['season']} raids={[r['name'] for r in d['raids']]} dungeons={len(d['dungeons'])}")
