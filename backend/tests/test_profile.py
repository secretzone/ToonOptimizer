from __future__ import annotations

import sys
import types

import pytest

from toonopt.models import Item
from toonopt.simc import profile


def test_parse_dk_export(dk_export):
    p = profile.parse(dk_export)
    assert (p.name, p.realm, p.region) == ("Frostbyte", "area_52", "us")
    assert (p.klass, p.spec, p.level, p.race, p.role) == ("death_knight", "frost", 90, "human", "attack")
    assert p.professions == {"blacksmithing": 100, "mining": 75}
    assert p.talents.startswith("CsPAAAA")
    assert len(p.equipped) == 16
    head = p.equipped["head"]
    assert head.key == "equipped:head" and head.id == 271474 and head.name == "Baleful Graveknight's Casque"
    assert head.ilevel == 334                      # from the "# Name (334)" comment
    assert head.bonus_ids == [4786, 12854, 13692, 13698, 13750] and head.gem_ids == [240983]
    assert head.simc_string.startswith("head=,id=271474,") and "redirected_base_stats=251126" in head.simc_string
    wrist = p.equipped["wrist"]
    assert wrist.crafted_stats == [32, 49] and wrist.crafting_quality == 5
    assert p.equipped["legs"].ilevel == 344 and p.equipped["legs"].enchant_id == 8159
    assert p.equipped["off_hand"].id == 268202 and p.equipped["main_hand"].enchant_id == 3368
    assert p.equipped["shoulder"].id == 271472      # addon writes "shoulder="
    assert p.raw == dk_export.replace("\r\n", "\n")


def test_bags_and_vault(dk_profile):
    p = dk_profile
    assert [i.key for i in p.bags] == ["bag:1", "bag:2", "bag:3", "bag:4", "bag:5"]
    assert [i.slot for i in p.bags] == ["finger", "trinket", "main_hand", "off_hand", "hands"]
    assert p.bags[0].name == "Apex Brute's Claw Ring" and p.bags[0].ilevel == 334
    assert p.bags[0].source and p.bags[0].source.type == "bag"
    assert p.bags[2].simc_string == "main_hand=,id=271093,bonus_id=13662/13848,enchant_id=8689"
    assert [i.key for i in p.vault] == ["vault:1", "vault:2"]
    assert p.vault[0].slot == "feet" and p.vault[0].source.type == "vault" and p.vault[1].id == 268256
    # "Additional Character Info" comment lines are not items
    assert all(i.id for i in p.bags + p.vault)


def test_header_excludes_gear_and_comments(dk_profile):
    header = dk_profile.simc_header.splitlines()
    assert header[0] == 'deathknight="Frostbyte"'
    assert "spec=frost" in header and "talents=" + dk_profile.talents in header
    assert "omnium_talents=136822:1/136819:1/136817:1" in header
    assert not any(ln.startswith("#") for ln in header)
    assert not any(ln.startswith(("head=", "main_hand=")) for ln in header)


def test_saved_loadouts(dk_export, mage_export):
    lo = profile.saved_loadouts(dk_export)
    assert [x["name"] for x in lo] == ["Raid ST", "M+ Cleave"]
    assert lo[1]["string"].endswith("AwB") and lo[1]["kind"] == "talents"
    assert profile.saved_loadouts(mage_export)[0]["name"] == "Cleave"


def test_profile_saved_loadouts_loot_spec_and_high_watermarks(dk_profile):
    p = dk_profile
    assert [lo.kind for lo in p.saved_loadouts] == ["active", "saved", "saved"]
    assert p.saved_loadouts[0].name == "Raid ST (active)" and p.saved_loadouts[0].string == p.talents
    assert [lo.name for lo in p.saved_loadouts[1:]] == ["Raid ST", "M+ Cleave"]
    assert p.saved_loadouts[2].string.endswith("AwB")
    assert p.loot_spec == "frost"
    assert p.high_watermarks == {"neck": 344}      # "# slot_high_watermarks=1:344:344" -> Neck


def test_active_loadout_named_after_matching_saved_loadout():
    text = (
        'hunter="Testhunter"\nlevel=90\nspec=marksmanship\n'
        "talents=ABC\n"
        "# Saved Loadout: Solo\n# talents=XYZ\n"
        "# Saved Loadout: AOE/Raid\n# talents=ABC\n"
        "head=,id=1\n"
    )
    p = profile.parse(text)
    assert p.saved_loadouts[0].name == "AOE/Raid (active)"      # never the character name


def test_saved_loadouts_active_name_falls_back_when_no_name_parsed():
    text = (
        'deathknight=""\nlevel=90\nspec=frost\n'
        "talents=ABC\n"
        "head=,id=1\n"
    )
    p = profile.parse(text)
    assert [lo.kind for lo in p.saved_loadouts] == ["active"]
    assert p.saved_loadouts[0].name == "Active" and p.saved_loadouts[0].string == "ABC"
    assert p.loot_spec is None and p.high_watermarks == {}


def test_two_hander_and_caster_offhand(warrior_export, mage_export):
    w = profile.parse(warrior_export)
    assert (w.klass, w.spec, w.region, w.realm) == ("warrior", "arms", "eu", "draenor")
    assert "off_hand" not in w.equipped and w.equipped["main_hand"].id == 268210
    assert "trinket2" not in w.equipped
    assert [b.slot for b in w.bags] == ["main_hand", "hands"]
    m = profile.parse(mage_export)
    assert m.klass == "mage" and m.race == "void_elf"
    assert m.equipped["off_hand"].id == 245769 and m.equipped["main_hand"].name == "Cookie's Stirring Rod"
    assert m.bags[1].slot == "off_hand" and m.bags[1].ilevel == 340


def test_simc_repo_profile_aliases(fixtures):
    p = profile.parse((fixtures / "MID2_Death_Knight_Frost.simc").read_text("utf-8"))
    assert p.name == "MID2_Death_Knight_Frost" and p.klass == "death_knight"
    assert "shoulder" in p.equipped and "wrist" in p.equipped      # shoulders=/wrists= normalised
    assert p.equipped["shoulder"].simc_string.startswith("shoulder=baleful_graveknights_gibbets,id=271472")
    assert p.equipped["head"].name == "Baleful Graveknights Casque"  # tokenised name, no comment
    header = p.simc_header.splitlines()
    assert "actions.precombat=snapshot_stats" in header and any(ln.startswith("actions.variables+=/variable,name=frostscythe_priority") for ln in header)
    assert "potion=potion_of_recklessness_2" in header and not any(ln.startswith("head=") for ln in header)


def test_errors():
    with pytest.raises(profile.ProfileError):
        profile.parse("# nothing here\nlevel=80\n")
    with pytest.raises(profile.ProfileError):
        profile.parse('mage="X"\nlevel=80\n')       # no spec


def test_parse_item_line():
    slot, f = profile.parse_item_line("wrists=name_here,id=1,bonus_id=1/2/3,ilevel=5,gem_id=7,enchant_id=9,crafted_stats=32/49,crafting_quality=5,content_tuning=883")
    assert slot == "wrist" and f["name"] == "name_here" and f["id"] == 1 and f["bonus_id"] == [1, 2, 3]
    assert f["crafted_stats"] == [32, 49] and f["content_tuning"] == 883 and f["gem_id"] == [7]


def test_data_layer_enrichment(monkeypatch, dk_export):
    calls = []

    def resolve_item(item_id, bonus_ids, ilevel, *, key, slot_hint=None, gem_ids=(), enchant_id=None,
                     crafted_stats=(), crafting_quality=None):
        calls.append((item_id, key, slot_hint))
        return Item(key="x", id=item_id, name=f"Resolved {item_id}", slot=slot_hint or "head", inventory_type=17 if slot_hint == "main_hand" else 1,
                    ilevel=ilevel or 0, quality=4, icon="inv_x", bonus_ids=list(bonus_ids), stats={"strength": 100})

    mod = types.ModuleType("toonopt.data.items")
    mod.resolve_item = resolve_item
    monkeypatch.setitem(sys.modules, "toonopt.data.items", mod)
    p = profile.parse(dk_export)
    head = p.equipped["head"]
    assert head.name == "Resolved 271474" and head.key == "equipped:head" and head.icon == "inv_x"
    assert head.simc_string.startswith("head=,id=271474")        # export string kept
    assert head.stats == {"strength": 100}
    assert p.bags[2].inventory_type == 17 and p.bags[2].key == "bag:3" and p.bags[2].source.type == "bag"
    assert any(k == "bag:1" and s == "finger" for _, k, s in calls)
    assert p.warnings == []
    assert all(item.resolved for item in p.equipped.values())


def test_no_data_layer_gives_one_resolved_false_warning(dk_profile):
    # the autouse `no_data_layer` conftest fixture stubs toonopt.data.items to None for
    # every item in this fixture -- the "toonopt.data missing entirely" branch.
    assert dk_profile.warnings == ["toonopt.data is not available; items could not be resolved"]
    assert all(not item.resolved for item in dk_profile.equipped.values())
    assert all(not item.resolved for item in dk_profile.bags + dk_profile.vault)


def test_resolve_failure_marks_items_unresolved_with_one_aggregated_warning(monkeypatch, dk_export):
    def resolve_item(item_id, bonus_ids, ilevel, *, key, slot_hint=None, gem_ids=(), enchant_id=None,
                     crafted_stats=(), crafting_quality=None):
        raise FileNotFoundError("DB2 table ItemSparse is not cached for build 12.1.0.69933; run data refresh")

    mod = types.ModuleType("toonopt.data.items")
    mod.resolve_item = resolve_item
    monkeypatch.setitem(sys.modules, "toonopt.data.items", mod)

    p = profile.parse(dk_export)

    total = len(p.equipped) + len(p.bags) + len(p.vault)
    assert all(not item.resolved for item in p.equipped.values())
    assert all(not item.resolved for item in p.bags + p.vault)
    assert len(p.warnings) == 1
    assert p.warnings[0] == (
        f"{total} item(s) could not be resolved (reason: FileNotFoundError: DB2 table ItemSparse "
        "is not cached for build 12.1.0.69933; run data refresh) — refresh data in Settings"
    )
    # the underlying failure was logged with the item id, not silently swallowed
    # (see toonopt.simc.profile.make_item)


def test_parse_currencies(dk_profile):
    # bare fallback (no data layer, per the autouse conftest stub): ids/kinds/amounts parse
    # correctly from the three "### Additional Character Info" comment lines even though
    # name/icon/crest can't be resolved without toonopt.data.currencies.
    p = dk_profile
    assert p.catalyst_charges == 2
    by_id = {c.id: c for c in p.currencies}
    assert set(by_id) == {3116, 3110, 3111}
    assert by_id[3116].kind == "currency" and by_id[3116].amount == 2      # catalyst_currencies=3116:2:0
    assert by_id[3110].kind == "currency" and by_id[3110].amount == 120    # upgrade_currencies=c:3110:120
    assert by_id[3111].kind == "currency" and by_id[3111].amount == 30     # upgrade_currencies=c:3111:30
    assert all(c.name == "" and c.crest is None for c in p.currencies)     # data layer unavailable


def test_parse_currencies_catalyst_charges_falls_back_to_first_entry_without_data_layer():
    """No data layer (autouse ``no_data_layer`` stub) -> this season's catalyst currency id
    can't be resolved, so catalyst_charges falls back to the first catalyst entry's amount --
    the DK fixture's raw ``catalyst_currencies=3116:2:0`` (see export_dk_frost.simc). That
    trailing ``:0`` is not a real third field: the addon's GetCatalystCurrencies
    (core.lua ~748-757) only ever emits ``id:quantity`` joined by ``/``; the second field is
    already the quantity, and any (ignored) third field some exports carry is not "earned this
    season" or a max -- it's just not part of the addon's own format."""
    text = (
        'deathknight="X"\nlevel=90\nspec=frost\n'
        "head=,id=1\n"
        "### Additional Character Info\n"
        "#\n# catalyst_currencies=3116:2:0\n#\n# upgrade_currencies=\n#\n# bonus_roll_currencies=\n"
    )
    p = profile.parse(text)
    assert p.catalyst_charges == 2
    assert p.catalyst_charges_max is None       # no data layer -> Currency.max_quantity unresolved


def test_parse_currencies_catalyst_charges_uses_season_currency_not_sum(real_data_layer):
    """Regression (a real hunter export, see tests/fixtures/export_hunter_mm.simc): the addon
    writes one ``catalyst_currencies`` entry per catalyst currency it has ever tracked across
    seasons (``Simulationcraft.catalystCurrencies``, extras.lua has 5), most reading a stale
    leftover amount from a past season -- only the one matching this season's catalyst
    (``season.catalyst.currency_id`` == 3465, "Venomblight Manaflux") is real. Summing every
    entry (the old bug) gave 32; the fix picks the season's entry by id, which is 0 here
    (``catalyst_charges_max`` is that currency's ``CurrencyTypes.MaxQty``, 8)."""
    text = (
        'hunter="Testhunter"\nlevel=90\nspec=marksmanship\n'
        "head=,id=1\n"
        "### Additional Character Info\n"
        "#\n# catalyst_currencies=2813:8/3269:8/3116:8/3378:8/3465:0\n#\n"
        "# upgrade_currencies=\n#\n# bonus_roll_currencies=\n"
    )
    p = profile.parse(text)
    catalyst_ids = {2813, 3269, 3116, 3378, 3465}
    assert sum(c.amount for c in p.currencies if c.id in catalyst_ids) == 32   # the old (wrong) sum
    assert p.catalyst_charges == 0
    assert p.catalyst_charges_max == 8


def test_parse_currencies_no_catalyst_line_is_none():
    text = (
        'deathknight="X"\nlevel=90\nspec=frost\n'
        "head=,id=1\n"
        "### Additional Character Info\n"
        "#\n# upgrade_currencies=\n#\n# bonus_roll_currencies=\n"
    )
    p = profile.parse(text)
    assert p.catalyst_charges is None
    assert p.currencies == []


def test_parse_currencies_item_based_upgrade_currency():
    text = (
        'deathknight="X"\nlevel=90\nspec=frost\n'
        "head=,id=1\n"
        "### Additional Character Info\n"
        "#\n# catalyst_currencies=\n#\n# upgrade_currencies=i:173381:3,c:3110:20\n"
    )
    p = profile.parse(text)
    by_id = {c.id: c for c in p.currencies}
    assert by_id[173381].kind == "item" and by_id[173381].amount == 3
    assert by_id[3110].kind == "currency" and by_id[3110].amount == 20


def test_resolve_failure_logs_each_item_id(monkeypatch, dk_export, caplog):
    import logging

    def resolve_item(item_id, bonus_ids, ilevel, *, key, slot_hint=None, gem_ids=(), enchant_id=None,
                     crafted_stats=(), crafting_quality=None):
        raise KeyError(f"unknown item id {item_id}")

    mod = types.ModuleType("toonopt.data.items")
    mod.resolve_item = resolve_item
    monkeypatch.setitem(sys.modules, "toonopt.data.items", mod)

    with caplog.at_level(logging.WARNING, logger="toonopt.simc.profile"):
        p = profile.parse(dk_export)

    assert p.equipped["head"].resolved is False
    warning_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "271474" in warning_text          # head's item id shows up in at least one log line
    assert "key=equipped:head" in warning_text
