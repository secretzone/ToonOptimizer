"""Integration tests against the real DB2 cache (skipped when it is not downloaded)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from toonopt.data import wago

pytestmark = pytest.mark.integration

if not wago.is_ready():
    pytest.skip("DB2 cache not downloaded (POST /api/data/refresh)", allow_module_level=True)


@pytest.fixture(autouse=True)
def _use_real_data_layer(real_data_layer):
    """Every test in this module needs the genuine DB2-backed data layer, not the
    ``no_data_layer`` autouse stub (conftest.py) that unit tests rely on. Without this,
    running this file in isolation (rather than after another test that happens to have
    already undone the stub) fails every test here with
    ``ModuleNotFoundError: import of toonopt.data.items halted; None in sys.modules``."""
    return real_data_layer


@pytest.fixture(scope="module")
def client() -> TestClient:
    from toonopt.main import app
    return TestClient(app)


def test_status_lists_every_table() -> None:
    s = wago.status(wago.build())
    assert s["ready"] and set(s["cached_tables"]) == set(wago.TABLES)


def test_resolve_known_items() -> None:
    from toonopt.data import items
    neck = items.resolve_item(268265, [13335, 13668, 13848, 13987], None, key="t")
    assert (neck.name, neck.slot, neck.ilevel, neck.quality) == ("Aqirbane Reliquary", "neck", 344, 4)
    assert neck.icon.startswith("inv_") and neck.stats["stamina"] > 0 and neck.stats["crit"] > 0
    assert neck.simc_string == "neck=,id=268265,bonus_id=13335/13668/13848/13987,ilevel=344"
    assert neck.sockets == 1                                          # bonus 13668 grants a socket
    weapon = items.resolve_item(271092, [13335, 12854], None, key="t")
    assert weapon.slot == "main_hand" and weapon.ilevel == 334 and weapon.unique_equipped == "Unique-Equipped"
    assert weapon.stats["weapon_dps"] > 0 and weapon.stats["intellect"] > 0
    assert weapon.sockets == 0                                        # no socket bonus id -> no sockets
    tier = items.resolve_item(271483, [12854], None, key="t", slot_hint="head")
    assert tier.set_id == 2065 and tier.ilevel == 334 and tier.stats["armor"] > 0
    crafted = items.resolve_item(244581, [1808, 8793, 8960, 12214, 12384, 13751, 13836, 9627], None, key="t")
    assert crafted.ilevel == 331 and crafted.crafted_stats == [49, 36] and crafted.unique_equipped == "Embellished"
    assert "mastery" in crafted.stats and "haste" in crafted.stats and "crit" not in crafted.stats
    assert crafted.sockets == 1                                       # bonus 1808 grants a socket
    # bonus 12854 alone grants no socket (socket_count == 0); an existing gem still counts,
    # falling back to len(gem_ids) -- same fallback toonopt.data.season.best_gems relies on
    withdiamond = items.resolve_item(271483, [12854], None, key="t", gem_ids=[240967])
    assert withdiamond.sockets == 1 and withdiamond.gem_ids == [240967]
    ring = items.resolve_item(159459, [], 334, key="t", slot_hint="finger2")
    assert ring.slot == "finger2" and ring.ilevel == 334


def test_season_and_tracks() -> None:
    from toonopt.data import season
    s = season.load()
    assert s["season_id"] == 37 and s["mplus_season_id"] == 37
    assert {r["name"] for r in s["raids"]} == {"The Tidebound Grotto", "The Venomous Abyss"}
    assert len(s["dungeons"]) == 8 and {d["name"] for d in s["dungeons"]} >= {"Altar of Fangs", "Kings' Rest"}
    assert s["upgrade_tracks"]["Myth"]["ilevels"] == [318, 321, 324, 328, 331, 334]
    va = next(r for r in s["raids"] if r["name"] == "The Venomous Abyss")
    assert va["difficulties"]["heroic"]["ilevel"] == 308 and va["difficulties"]["heroic"]["max_ilevel"] == 318
    assert va["bosses"][-1]["drops"]["mythic"]["ilevel"] == 331
    assert next(k for k in s["key_levels"] if k["level"] == 10)["ilevel"] == 311
    assert s["enchants"]["chest"] == 7987 and s["gems"]["default"] == 240908
    assert season.consumables_for("mage", "fire")["flask"] == "flask_of_thalassian_resistance_2"
    assert season.consumables_for("evoker", "devastation", primary="intellect")["potion"]


def test_best_enchant_and_gems() -> None:
    from toonopt.data import season
    from toonopt.models import CharacterProfile, Item
    mage = CharacterProfile(name="x", klass="mage", spec="fire", equipped={
        "off_hand": Item(key="o", id=245769, slot="off_hand", inventory_type=23, ilevel=331)})
    rogue = CharacterProfile(name="y", klass="rogue", spec="subtlety")
    assert season.best_enchant("legs", mage) == 7935 and season.best_enchant("legs", rogue) == 8159
    assert season.best_enchant("chest", mage) == 7987 and season.best_enchant("back", mage) is None
    assert season.best_enchant("off_hand", mage) is None and season.best_enchant("off_hand", rogue) == 8689
    # mage_fire's curated flask is Thalassian Resistance (versatility), so its gem should be
    # the versatility gem, not always the mastery/"default" one.
    neck = Item(key="n", id=268265, slot="neck", inventory_type=2, ilevel=344, bonus_ids=[13335, 13668, 13848, 13987])
    assert season.best_gems(neck, mage) == [240894]
    plain = Item(key="n", id=268265, slot="neck", inventory_type=2, ilevel=344, bonus_ids=[13335])
    assert season.best_gems(plain, mage) == []
    withdiamond = Item(key="h", id=271483, slot="head", inventory_type=1, ilevel=334, bonus_ids=[12854, 13750], gem_ids=[240967])
    assert season.best_gems(withdiamond, mage) == [240967]


def test_recommendations_shape() -> None:
    from toonopt.data import season

    r = season.recommendations("death_knight", "frost")
    assert r["season"] == season.load()["season"]
    for ref in [r["gems"]["default"], *r["gems"]["by_stat"].values(), *r["gems"]["unique"]]:
        assert ref["id"] and ref["name"] and ref["stat"]
    assert set(r["gems"]["by_stat"]) == {"crit", "haste", "mastery", "versatility"}
    # frost DK's curated flask (Shattered Sun) favours crit
    assert r["gems"]["default"]["stat"] == "crit" and r["gems"]["default"]["id"] == season.GEMS["crit"]
    assert r["gems"]["unique"] and all(g["limit"] == 1 for g in r["gems"]["unique"])
    # head/feet have no dps-relevant enchant this season (ENCHANT_OPTIONS marks them dps=False)
    assert set(r["enchants"]) >= {"chest", "legs", "main_hand"} and "head" not in r["enchants"]
    for options in r["enchants"].values():
        assert options and sum(o["recommended"] for o in options) == 1
        assert options[0]["recommended"]                      # sorted recommended-first
        for o in options:
            assert o["id"] and o["name"] and "$" not in o["name"]
    assert r["consumables"] == season.consumables_for("death_knight", "frost")
    # single source of truth: best_enchant/best_gems must agree with the payload
    from toonopt.models import CharacterProfile
    dk = CharacterProfile(name="x", klass="death_knight", spec="frost")
    chest_rec = next(o for o in r["enchants"]["chest"] if o["recommended"])
    assert chest_rec["id"] == season.best_enchant("chest", dk)


def test_upgrade_path_known_track() -> None:
    from toonopt.data import items, season
    from toonopt.models import Item

    item = Item(key="t", id=268265, slot="neck", ilevel=305, bonus_ids=[13335, 12841])
    steps = season.upgrade_path(item)
    assert [s.rank for s in steps] == [2, 3, 4, 5, 6]
    assert [s.ilevel for s in steps] == [308, 311, 315, 318, 321]
    assert all(s.cost == 20 and s.crest == "Hero Mistcrest" for s in steps)
    # bonus ids swap only the track bonus, keeping the rest of the item's bonus ids intact
    assert steps[0].bonus_ids == [13335, 12842]
    # verify against the real item resolver: the upgraded bonus ids must resolve to the
    # step's own ilevel
    last = steps[-1]
    upgraded = items.resolve_item(item.id, last.bonus_ids, None, key="t2")
    assert upgraded.ilevel == last.ilevel == 321
    # an item with no upgrade-track bonus id at all has no path
    assert season.upgrade_path(Item(key="t3", id=268265, slot="neck", ilevel=300, bonus_ids=[])) == []


def test_loot_sources_and_candidates() -> None:
    from toonopt.data import loot
    from toonopt.models import CharacterProfile, DungeonSource, RaidSource
    src = loot.sources("mage", "fire")
    assert src["raids"][1]["usable"] > 20 and len(src["dungeons"]) == 8 and src["crafted"]["usable"] > 0
    p = CharacterProfile(name="x", klass="mage", spec="fire")
    c = loot.candidates(p, [RaidSource(instance_id=1320, difficulty="heroic", bosses=[2895]), DungeonSource(key_level=10, instance_ids=[1322])], "drop")
    assert c and all(x.key.startswith("drop:") and x.source is not None for x in c)
    assert all(x.stats.get("intellect", 0) > 0 or x.slot.startswith("trinket") or x.slot in ("finger", "neck", "back") for x in c)
    heroic = [x for x in c if x.source.type == "raid"]
    assert heroic and all(x.ilevel == 318 and 13334 in x.bonus_ids for x in heroic)
    maxed = loot.candidates(p, [RaidSource(instance_id=1320, difficulty="heroic", bosses=[2895])], "max")
    assert all(x.ilevel == 321 for x in maxed)


def test_talents_tree_and_decode() -> None:
    from toonopt.data import talents
    t = talents.tree("mage", "fire")
    assert t["spec_id"] == 63 and len(t["class_tree"]) > 30 and len(t["spec_tree"]) > 30
    assert {h["name"] for h in t["hero_trees"]} == {"Sunfury", "Frostfire"}
    d = talents.decode("mage", "fire", "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB")
    assert d["supported"] and d["spec_id"] == 63 and d["hero_tree"]["name"] == "Sunfury"
    names = {x["name"] for x in d["selected"]}
    assert {"Combustion", "Pyroblast", "Fire Blast"} <= names
    wrong = talents.decode("mage", "frost", "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB")
    assert "warning" in wrong


def _all_bits(s: str) -> list[int]:
    from toonopt.data.talents import _Bits

    bits = _Bits(s)
    out: list[int] = []
    try:
        while True:
            out.append(bits.read(1))
    except ValueError:
        pass
    return out


def _assert_bit_equal(a: str, b: str) -> None:
    """Same meaningful content: identical up to the shorter string's length, and whatever
    tail the longer one has beyond that is all zero padding (see talents.encode's docstring)."""
    ba, bb = _all_bits(a), _all_bits(b)
    n = min(len(ba), len(bb))
    assert ba[:n] == bb[:n], f"bit streams diverge within the shared prefix ({a!r} vs {b!r})"
    assert all(x == 0 for x in ba[n:]) and all(x == 0 for x in bb[n:]), "extra tail bits aren't padding"


GUIDE_STRINGS_MM_HUNTER = [
    "C4PAAAAAAAAAAAAAAAAAAAAAAwCMwMGzYZAjZwGAAAAAAAAYGzYmFzYmZMDGTzYwYbZmZmZmZmZWYmlBzAAAGzMjBwM22gBYjZ2mxAA",
    "C4PAAAAAAAAAAAAAAAAAAAAAAwCMwMGzYZAjZwGAAAAAAAAYGzYmFzYmZMDGTzYwstZmZmZmZmZWYmlhZAAAGzMjBwM22gBYjZ2mxAA",
    "C4PAAAAAAAAAAAAAAAAAAAAAAwGMwMGzYZAjZwGAAAAAAAAYGzMzYbGzMjZYZMNjBzy22MzMzMzMzswMLDzAAA4BGjBgZsBGgNmZbGD",
    "C4PAAAAAAAAAAAAAAAAAAAAAAwCMwMGNWGAzgNAAAAAAAAwMmZmhZMzMmBjpZMYW2WmZmZmZmZmFmZZYGAAg5BGzAgZabDGgNmZbGD",
]


def test_talents_encode_round_trips_guide_strings() -> None:
    from toonopt.data import talents

    for s in GUIDE_STRINGS_MM_HUNTER:
        d = talents.decode("hunter", "marksmanship", s)
        assert d["supported"]
        out = talents.encode("hunter", "marksmanship", d)
        _assert_bit_equal(s, out)


def test_talents_encode_round_trips_mage_fixture() -> None:
    from toonopt.data import talents

    s = "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB"
    d = talents.decode("mage", "fire", s)
    out = talents.encode("mage", "fire", d)
    _assert_bit_equal(s, out)


def test_talents_encode_round_trips_saved_character_loadouts(hunter_mm_export) -> None:
    from toonopt.data import talents
    from toonopt.simc import profile as profile_mod

    char = profile_mod.parse(hunter_mm_export)
    klass, spec = char.klass, char.spec
    strings = [char.talents] + [sl.string for sl in char.saved_loadouts]
    assert strings
    for s in strings:
        d = talents.decode(klass, spec, s)
        assert d["supported"], d.get("error")
        out = talents.encode(klass, spec, d)
        _assert_bit_equal(s, out)


def test_talents_names_groups_by_section() -> None:
    from toonopt.data import talents

    n = talents.names("hunter", "marksmanship", GUIDE_STRINGS_MM_HUNTER[0])
    assert "Survival of the Fittest" in n["class"]
    assert n["spec"] and n["hero"]
    assert n["hero_tree"]["name"] == "Sentinel"
    bad = talents.names("hunter", "marksmanship", "not-a-real-string")
    assert bad["class"] == [] and "error" in bad


def test_talents_modify_swap_and_errors() -> None:
    from toonopt.data import talents

    base = GUIDE_STRINGS_MM_HUNTER[0]
    before = talents.names("hunter", "marksmanship", base)

    # unknown talent name is reported, not silently ignored
    res = talents.modify("hunter", "marksmanship", base, add=["Not A Real Talent"], remove=[])
    assert any("unknown talent" in e for e in res["errors"])

    # removing a talent something else depends on is refused with a clear error, and the
    # resulting string still decodes cleanly (nothing partially applied for that talent):
    # Binding Shot's only prerequisite is Scout's Instincts, and both are picked in this build
    res = talents.modify("hunter", "marksmanship", base, add=[], remove=["Scout's Instincts"])
    assert res["errors"] and "prerequisite" in res["errors"][0]

    # a legal swap within a choice node succeeds with no errors and changes only that node:
    # Tar-Coated Bindings/Horsehair Tether share a leaf node (nothing depends on either side)
    swap = talents.modify("hunter", "marksmanship", base, add=["Tar-Coated Bindings"], remove=["Horsehair Tether"])
    assert swap["errors"] == []
    assert {c["action"] for c in swap["changes"]} == {"add", "remove"}
    d = talents.decode("hunter", "marksmanship", swap["string"])
    assert d["supported"]
    after_names = {x["name"] for x in d["selected"]}
    assert "Tar-Coated Bindings" in after_names and "Horsehair Tether" not in after_names
    # everything else about the build is untouched
    after = talents.names("hunter", "marksmanship", swap["string"])
    assert set(before["hero"]) == set(after["hero"])


def test_routes(client: TestClient) -> None:
    assert client.get("/api/data/season").json()["season_id"] == 37
    r = client.get("/api/data/loot/sources", params={"klass": "rogue", "spec": "assassination"})
    assert r.status_code == 200 and r.json()["raids"]
    r = client.get("/api/data/items/268265", params={"bonus_ids": "13335/13848", "ilevel": ""})
    assert r.status_code == 200 and r.json()["ilevel"] == 344
    assert client.get("/api/data/items/1").status_code == 404
    r = client.get("/api/data/talents/mage/fire")
    assert r.status_code == 200 and r.json()["hero_trees"]
    r = client.post("/api/data/talents/decode", json={"klass": "mage", "spec": "fire", "loadout": "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB"})
    assert r.status_code == 200 and r.json()["hero_tree"]["name"] == "Sunfury"
    decoded = r.json()
    r = client.post("/api/data/talents/encode", json={"klass": "mage", "spec": "fire", "selections": decoded})
    assert r.status_code == 200
    _assert_bit_equal(r.json()["string"], "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB")
    r = client.post("/api/data/talents/names", json={"klass": "hunter", "spec": "marksmanship", "loadout": GUIDE_STRINGS_MM_HUNTER[0]})
    assert r.status_code == 200 and r.json()["hero_tree"]["name"] == "Sentinel"
    r = client.post("/api/data/talents/modify", json={
        "klass": "hunter", "spec": "marksmanship", "base": GUIDE_STRINGS_MM_HUNTER[0],
        "add": ["Tar-Coated Bindings"], "remove": ["Horsehair Tether"],
    })
    assert r.status_code == 200 and r.json()["errors"] == [] and r.json()["string"]


# --- item search (API.md "Raidbots parity, wave 1") --------------------------

def test_search_items_band_for_frost_dk_returns_rings_only() -> None:
    from toonopt.data import items
    res = items.search_items("band", klass="death_knight", spec="frost", limit=25)
    assert res and {r["slot"] for r in res} == {"finger"}
    assert all(r["id"] and r["name"] and r["icon"] and r["quality"] >= 2 for r in res)


def test_search_items_plate_chest_for_mage_returns_nothing() -> None:
    from toonopt.data import items
    assert items.search_items("Reckless Spirit Breastplate", klass="mage", spec="arcane") == []
    # without a klass/spec filter the same query still finds the (plate) item
    assert items.search_items("Reckless Spirit Breastplate") != []


def test_search_items_slot_filter_and_no_query() -> None:
    from toonopt.data import items
    assert items.search_items("") == []
    # "band" substring-matches a couple of real trinkets too (e.g. "...Bandages"); the slot
    # filter should narrow to just those, not the (far more numerous) rings.
    trinkets = items.search_items("band", klass="death_knight", spec="frost", slot="trinket1", limit=10)
    assert trinkets and all(r["slot"] == "trinket" for r in trinkets)
    rings = items.search_items("band", klass="death_knight", spec="frost", slot="finger1", limit=5)
    assert rings and all(r["slot"] == "finger" for r in rings)


def test_resolve_track_rank_gives_right_ilevel() -> None:
    from toonopt.data import items, season
    s = season.load()
    assert s["upgrade_tracks"]["Myth"]["ilevels"][2] == 324
    ids, ilvl = items.resolve_track_rank("Myth", 3)
    assert ilvl == 324 and ids == [s["upgrade_tracks"]["Myth"]["bonus_ids"][2]]
    assert items.resolve_track_rank("Nonsense", 3) == ([], None)
    assert items.resolve_track_rank("Myth", 99) == ([], None)


def test_search_and_track_rank_routes(client: TestClient) -> None:
    r = client.get("/api/data/items/search", params={"q": "band", "klass": "death_knight", "spec": "frost"})
    assert r.status_code == 200
    payload = r.json()["items"]
    assert payload and {it["slot"] for it in payload} == {"finger"}

    r = client.get("/api/data/items/search", params={"q": "Reckless Spirit Breastplate", "klass": "mage", "spec": "arcane"})
    assert r.status_code == 200 and r.json()["items"] == []

    r = client.get("/api/data/items/268265", params={"track": "Myth", "rank": 3})
    assert r.status_code == 200
    item = r.json()
    assert item["ilevel"] == 324 and item["key"] == "search:268265:12851"

    assert client.get("/api/data/items/268265", params={"track": "Nonsense", "rank": 3}).status_code == 400
