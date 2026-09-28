from __future__ import annotations

import pytest

from toonopt.config import settings
from toonopt.models import Consumables, ExpertOptions, Item, SimOptions
from toonopt.simc import input as inp
from toonopt.simc.input import Profileset, ProfilesetNames


def test_globals_and_actor(dk_profile):
    opts = SimOptions(iterations=500, desired_targets=3, fight_style="HecticAddCleave", ptr=True,
                      buffs={"bloodlust": False, "windfury_totem": True, "arcane_intellect": True},
                      consumables=Consumables(flask="flask_of_the_shattered_sun_2", potion="potion_of_recklessness_2"))
    text = inp.build(dk_profile, opts, threads=4)
    lines = text.splitlines()
    for expected in ("fight_style=HecticAddCleave", "max_time=300", "vary_combat_length=0.2", "desired_targets=3",
                     "iterations=500", "optimal_raid=0", "override.bloodlust=0",
                     "override.arcane_intellect=1", "ptr=1", "threads=4", 'deathknight="Frostbyte"',
                     "flask=flask_of_the_shattered_sun_2", "potion=potion_of_recklessness_2"):
        assert expected in lines, expected
    assert "target_error" not in text and "profileset." not in text and "windfury" not in text
    assert "food=disabled" in lines                   # empty selection always disables SimC's own default
    assert "override.blessing_of_the_bronze=1" in lines
    assert lines.index('deathknight="Frostbyte"') > lines.index("threads=4")
    gear = [ln for ln in lines if ln.startswith(("head=", "off_hand="))]
    assert gear[0] == "head=,id=271474,bonus_id=4786/12854/13692/13698/13750,gem_id=240983,redirected_base_stats=251126"
    assert gear[1] == "off_hand=,id=268202,bonus_id=13847/13848,enchant_id=3847"


def test_target_error_defaults(dk_profile):
    text = inp.build(dk_profile, SimOptions())
    assert f"target_error={settings.default_target_error}" in text and "iterations=0" in text
    ps = [Profileset("a", "A", ["head=,id=1"])]
    text = inp.build(dk_profile, SimOptions(), ps)
    assert f"target_error={settings.profileset_target_error}" in text
    assert 'profileset."a"+=head=,id=1' in text
    assert "single_actor_batch=1" in text and f"profileset_work_threads={settings.profileset_work_threads}" in text
    text = inp.build(dk_profile, SimOptions(target_error=0.5), ps)
    assert "target_error=0.5" in text


def test_talent_override_and_disabled_consumables(dk_profile):
    p = dk_profile.model_copy(update={"simc_header": dk_profile.simc_header + "\npotion=elemental_potion\nfood=feast"})
    text = inp.build(p, SimOptions(talents_override="XYZ", consumables=Consumables(food="fish")))
    lines = text.splitlines()
    assert "talents=XYZ" in lines and lines.index("talents=XYZ") > lines.index("talents=" + dk_profile.talents)
    # every empty consumable slot is always disabled -- not just the ones the header happened
    # to set -- otherwise SimC substitutes its own default and skews DPS by ~10%.
    assert "potion=disabled" in lines and "food=fish" in lines
    assert "flask=disabled" in lines and "augmentation=disabled" in lines and "temporary_enchant=disabled" in lines


def test_item_line_keeps_extras_and_applies_fields(dk_profile):
    head = dk_profile.equipped["head"].model_copy(update={"enchant_id": 1234, "gem_ids": [1, 2]})
    line = inp.item_line(head, "head")
    assert line == "head=,id=271474,bonus_id=4786/12854/13692/13698/13750,gem_id=1/2,enchant_id=1234,redirected_base_stats=251126"
    ring = dk_profile.bags[0]
    assert inp.item_line(ring, "finger2").startswith("finger2=,id=268252,bonus_id=13534,ilevel=334,gem_id=240908,enchant_id=7967")
    bare = Item(key="k", id=5, slot="trinket", bonus_ids=[1], ilevel=300)
    assert inp.item_line(bare, "trinket1") == "trinket1=,id=5,bonus_id=1,ilevel=300"
    named = Item(key="k", id=5, slot="head", simc_string="head=fancy_hat,id=5,bonus_id=9,content_tuning=1")
    assert inp.item_line(named) == "head=fancy_hat,id=5,content_tuning=1"


def test_target_dummy_fight_style(dk_profile):
    opts = SimOptions(fight_style="TargetDummy", buffs={"bloodlust": True, "arcane_intellect": True},
                       consumables=Consumables(flask="flask_of_the_shattered_sun_2"))
    text = inp.build(dk_profile, opts)
    lines = text.splitlines()
    assert "fight_style=Patchwerk" in lines and "optimal_raid=0" in lines
    # every override.* forced to 0, including the blessing_of_the_bronze one restored by default
    assert "override.bloodlust=0" in lines and "override.arcane_intellect=0" in lines
    assert "override.blessing_of_the_bronze=0" in lines
    assert not any(ln.startswith("override.") and ln.endswith("=1") for ln in lines)
    # every consumable forced disabled even though flask was set
    for key in ("flask", "food", "potion", "augmentation", "temporary_enchant"):
        assert f"{key}=disabled" in lines
    # enemy lines land AFTER the actor block (after the gear)
    gear_idx = max(i for i, ln in enumerate(lines) if ln.startswith("head="))
    assert lines.index("enemy=Target_Dummy") > gear_idx
    assert lines.index("enemy_fixed_health_percentage=100") == lines.index("enemy=Target_Dummy") + 1


def test_execute_patchwerk_fight_style(dk_profile):
    opts = SimOptions(fight_style="ExecutePatchwerk", desired_targets=2)
    text = inp.build(dk_profile, opts)
    lines = text.splitlines()
    assert "fight_style=Patchwerk" in lines
    assert "desired_targets=2" in lines            # unaffected -- only TargetDummy/DungeonSlice force this
    gear_idx = max(i for i, ln in enumerate(lines) if ln.startswith("head="))
    assert lines.index("enemy=Execute_Target_1") > gear_idx
    assert lines.index("enemy=Execute_Target_2") > lines.index("enemy=Execute_Target_1")
    assert lines.count("enemy_initial_health_percentage=20") == 2
    # consumables/buffs are untouched for ExecutePatchwerk (unlike TargetDummy)
    assert "flask=disabled" in lines  # empty selection still defaults to disabled, as always


def test_dungeon_slice_forces_max_time_and_targets(dk_profile):
    text = inp.build(dk_profile, SimOptions(fight_style="DungeonSlice", max_time=600, desired_targets=5))
    lines = text.splitlines()
    assert "max_time=360" in lines and "desired_targets=1" in lines
    assert "max_time=600" not in lines and "desired_targets=5" not in lines


def test_validate_options_rejects_dungeon_slice_for_devil_hunters(dk_profile):
    dh = dk_profile.model_copy(update={"klass": "demon_hunter", "spec": "havoc"})
    with pytest.raises(ValueError, match="DungeonSlice"):
        inp.validate_options(dh, SimOptions(fight_style="DungeonSlice"))
    # unaffected spec/style combos are fine
    inp.validate_options(dk_profile, SimOptions(fight_style="DungeonSlice"))
    inp.validate_options(dh, SimOptions(fight_style="Patchwerk"))


# ---------------------------------------------------------------------------
# Raidbots parity, wave 2: Vantus Rune + consumable-name validation


def test_vantus_rune_emits_actor_line(dk_profile):
    opts = SimOptions(buffs={**SimOptions().buffs, "vantus_rune": True})
    text = inp.build(dk_profile, opts)
    assert "set_custom_buff=vantus,stat_value=162_versatility" in text.splitlines()


def test_vantus_rune_off_by_default(dk_profile):
    text = inp.build(dk_profile, SimOptions())
    assert "vantus" not in text.lower()


def test_vantus_rune_suppressed_on_target_dummy(dk_profile):
    opts = SimOptions(fight_style="TargetDummy", buffs={**SimOptions().buffs, "vantus_rune": True})
    text = inp.build(dk_profile, opts)
    assert "vantus" not in text.lower()


def test_validate_options_skips_consumable_check_without_data_layer(dk_profile):
    # autouse no_data_layer fixture stubs toonopt.data.season -- free strings stay free.
    inp.validate_options(dk_profile, SimOptions(consumables=Consumables(flask="not_a_real_flask_at_all")))


def test_validate_options_rejects_unknown_consumable_name(real_data_layer, dk_profile):
    with pytest.raises(ValueError, match="invalid flask"):
        inp.validate_options(dk_profile, SimOptions(consumables=Consumables(flask="not_a_real_flask_at_all")))
    # a valid option from the season's catalogue is accepted
    inp.validate_options(dk_profile, SimOptions(consumables=Consumables(flask="flask_of_the_shattered_sun_2")))


def test_validate_options_allows_dual_wield_temporary_enchant(real_data_layer, dk_profile):
    # the catalogue only lists the main_hand form; the off_hand mirror must still validate
    inp.validate_options(dk_profile, SimOptions(consumables=Consumables(
        temporary_enchant="main_hand:thalassian_phoenix_oil_2/off_hand:thalassian_phoenix_oil_2",
    )))
    with pytest.raises(ValueError, match="invalid temporary_enchant"):
        inp.validate_options(dk_profile, SimOptions(consumables=Consumables(
            temporary_enchant="main_hand:not_a_real_oil",
        )))


def test_power_infusion_buff(dk_profile):
    text = inp.build(dk_profile, SimOptions(max_time=300, buffs={"power_infusion": True}))
    assert "external_buffs.power_infusion=0/120/240" in text
    # default (False) emits nothing
    text = inp.build(dk_profile, SimOptions(max_time=300))
    assert "external_buffs.power_infusion" not in text


def test_profileset_metric_always_emitted(dk_profile):
    text = inp.build(dk_profile, SimOptions())
    assert "profileset_metric=dps,prioritydps,dtps,hps,dmg_taken" in text


def test_expert_mode_splices_and_strips_banned_lines(dk_profile):
    expert = ExpertOptions(
        header="# custom header\nthreads=99",
        pre_actor="max_time=42",
        post_actor="enemy=Custom_Add\njson2=evil.json",
        footer="# the end\nhtml=evil.html",
    )
    text = inp.build(dk_profile, SimOptions(expert=expert))
    lines = text.splitlines()
    assert lines[0] == "# Generated by ToonOptimizer"
    assert "# custom header" in lines and "threads=99" not in lines
    assert lines.index("max_time=42") > lines.index("fight_style=Patchwerk")
    gear_idx = max(i for i, ln in enumerate(lines) if ln.startswith("head="))
    assert lines.index("enemy=Custom_Add") > gear_idx     # post_actor lands after the actor
    assert "json2=evil.json" not in lines and "html=evil.html" not in lines
    assert lines[-1] == "# the end"


def test_profileset_names_unique_and_safe():
    names = ProfilesetNames()
    a = names.make("Ring A (344) [finger1], Trinket.X")
    b = names.make("Ring A (344) [finger1], Trinket.X")
    assert a != b and "." not in a and " " not in a and "(" not in a
    assert names.labels[b] == "Ring A (344) [finger1], Trinket.X"
    c = names.make("label", hint="c1")
    assert c == "c1" and names.labels["c1"] == "label"
    assert inp.profileset("c1", ["head=,id=1", "off_hand="]) == 'profileset."c1"+=head=,id=1\nprofileset."c1"+=off_hand='
