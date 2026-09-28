"""Print a handful of current-season items so the numbers can be checked against Wowhead.

    uv run python -m toonopt.data.eyeball
"""
from __future__ import annotations

from toonopt.data import items, loot, season, talents
from toonopt.models import CharacterProfile, DungeonSource, RaidSource

SAMPLES: list[tuple[int, list[int], int | None, str]] = [
    (268265, [13335, 13668, 13848, 13987], None, "raid neck, Mythic + Voidforged (wowhead item=268265 @344)"),
    (271092, [13335, 12854], None, "Jan'thrazet dagger, Myth 6/6"),
    (270173, [13334, 12846], None, "Zul'jin's Guillotine Technique trinket, Hero 6/6"),
    (271483, [12854], None, "Ophidian Oracle head (shaman tier)"),
    (244581, [1808, 8793, 8960, 12214, 12384, 13751, 13836, 9627], None, "crafted belt q5, embellished"),
    (249610, [12834], None, "delve dagger, Champion 2/6"),
    (273796, [13440, 12843], None, "Altar of Fangs trinket, +10 (Hero 3/6)"),
    (159459, [12854, 13440, 13668], None, "Ritual Binder's Ring (Kings' Rest), Myth 6/6"),
]


def main() -> None:
    for iid, bids, il, note in SAMPLES:
        it = items.resolve_item(iid, bids, il, key=f"eyeball:{iid}")
        st = ", ".join(f"{k}={v:g}" for k, v in it.stats.items())
        print(f"{it.name} [{note}]\n  slot={it.slot} ilevel={it.ilevel} quality={it.quality} icon={it.icon} "
              f"unique={it.unique_equipped} set={it.set_id}\n  {st}\n  {it.simc_string}")
    s = season.load()
    print(f"\nseason: {s['season']} (id {s['season_id']}), raids={[r['name'] for r in s['raids']]}")
    for r in s["raids"]:
        print(f"  {r['name']}: " + ", ".join(f"{k} {v['ilevel']}-{v['max_ilevel']}" for k, v in r["difficulties"].items()))
    p = CharacterProfile(name="eyeball", klass="mage", spec="fire")
    cands = loot.candidates(p, [RaidSource(instance_id=1320, difficulty="heroic", bosses=[2895]), DungeonSource(key_level=10, instance_ids=[1322])], "drop")
    print(f"\nfire mage candidates (Ula'tek heroic + Altar of Fangs +10): {len(cands)}")
    for c in cands[:8]:
        print(f"  {c.key}: {c.name} {c.ilevel} {c.slot} {c.stats}")
    d = talents.decode("mage", "fire", "C8DAAAAAAAAAAAAAAAAAAAAAAYGGLzMzswMzIzMGAAAGAwMz0sstMDAwmZmx2MzMzYBAAAAALmZmZAAgZMmZmZMzsMAMzQGjBMDjB")
    print(f"\ntalents: spec {d['spec_id']} hero={d['hero_tree']} counts={d['counts']}")


if __name__ == "__main__":
    main()
