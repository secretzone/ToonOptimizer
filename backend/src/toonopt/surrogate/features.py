"""Fixed-length feature vector for the GPU surrogate: (profile, slot -> Item) -> gear vector.

Layout, in order, all indices deterministic and documented so a saved checkpoint's
weights line up with any vector built later against the same ``FEATURE_VERSION``::

    for slot in models.SLOTS (16 slots, that fixed order):
        ilevel                                          1
        per-slot stat totals (STAT_KEYS order)           len(STAT_KEYS)
    -> len(SLOTS) * (1 + len(STAT_KEYS))

    summed stat totals across all equipped slots         len(STAT_KEYS)
    set-bonus bucket counts   (set_id  % SET_BUCKETS)     SET_BUCKETS
    trinket id-hash buckets   (item.id % TRINKET_BUCKETS) TRINKET_BUCKETS
    weapon id-hash buckets    (item.id % WEAPON_BUCKETS)  WEAPON_BUCKETS
    embellishment id-hash buckets (item.id % EMBELLISH_BUCKETS) EMBELLISH_BUCKETS
    context: fight_style one-hot (FIGHT_STYLES order) + desired_targets   +1

Every "hashed embedding" here is a plain modulo hash into a fixed number of buckets: no
vocabulary, no learned embedding table, stable across game patches because a new item id
always lands in *some* bucket. Collisions (two different trinkets in the same bucket) are
an accepted approximation for an experimental model.

An item is treated as an "embellishment" the same way ``toonopt.sims.topgear`` treats the
allow-2 unique-equipped category: ``unique_equipped`` containing "embellish"
(case-insensitive). The Item model has no dedicated embellishment flag, so this is a
heuristic, not a guarantee.

Bump FEATURE_VERSION whenever this layout changes; ``toonopt.surrogate.model`` stores the
version a checkpoint was trained with and refuses to score with a mismatched one.
"""
from __future__ import annotations

from typing import get_args

import numpy as np

from toonopt.models import SLOTS, CharacterProfile, FightStyle, Item, SimOptions

FEATURE_VERSION = 1

# SimC-ish short stat names as toonopt.data.stats.STAT_KEYS produces them on Item.stats.
STAT_KEYS: tuple[str, ...] = (
    "agility", "strength", "intellect", "stamina", "crit", "haste",
    "mastery", "versatility", "leech", "speed", "avoidance",
)
FIGHT_STYLES: tuple[str, ...] = get_args(FightStyle)

SET_BUCKETS = 16
TRINKET_BUCKETS = 32
WEAPON_BUCKETS = 32
EMBELLISH_BUCKETS = 16

_PER_SLOT = 1 + len(STAT_KEYS)
VECTOR_LENGTH = (
    len(SLOTS) * _PER_SLOT
    + len(STAT_KEYS)
    + SET_BUCKETS
    + TRINKET_BUCKETS
    + WEAPON_BUCKETS
    + EMBELLISH_BUCKETS
    + len(FIGHT_STYLES)
    + 1
)

Gear = dict[str, Item | None]


def vector_length() -> int:
    return VECTOR_LENGTH


def _bucket(item_id: int, n: int) -> int:
    return item_id % n if n > 0 else 0


def _is_embellishment(item: Item) -> bool:
    return bool(item.unique_equipped) and "embellish" in item.unique_equipped.lower()


def gear_vector(profile: CharacterProfile, gear: Gear, options: SimOptions | None = None) -> np.ndarray:
    """Encode one gear set (plus fight context) as a fixed-length ``float32`` vector.

    ``gear`` maps SimC slot name -> Item (or ``None``/absent for an empty slot). ``profile``
    is accepted for symmetry with the spec and future per-class features; it is not read
    today. ``options`` supplies the fight-style/targets context; when omitted it defaults
    to Patchwerk / 1 target, which is fine when scoring many candidates for one job (they
    all share the same options anyway).
    """
    del profile  # not used yet; kept in the signature per the surrogate spec
    vec = np.zeros(VECTOR_LENGTH, dtype=np.float32)
    totals = np.zeros(len(STAT_KEYS), dtype=np.float32)
    set_counts = np.zeros(SET_BUCKETS, dtype=np.float32)
    trinket_counts = np.zeros(TRINKET_BUCKETS, dtype=np.float32)
    weapon_counts = np.zeros(WEAPON_BUCKETS, dtype=np.float32)
    embellish_counts = np.zeros(EMBELLISH_BUCKETS, dtype=np.float32)

    off = 0
    for slot in SLOTS:
        item = gear.get(slot)
        vec[off] = float(item.ilevel) if item else 0.0
        off += 1
        for si, stat in enumerate(STAT_KEYS):
            v = float(item.stats.get(stat, 0.0)) if item else 0.0
            vec[off + si] = v
            totals[si] += v
        off += len(STAT_KEYS)
        if item is not None:
            if item.set_id:
                set_counts[_bucket(item.set_id, SET_BUCKETS)] += 1.0
            if slot in ("trinket1", "trinket2"):
                trinket_counts[_bucket(item.id, TRINKET_BUCKETS)] += 1.0
            if slot in ("main_hand", "off_hand"):
                weapon_counts[_bucket(item.id, WEAPON_BUCKETS)] += 1.0
            if _is_embellishment(item):
                embellish_counts[_bucket(item.id, EMBELLISH_BUCKETS)] += 1.0

    vec[off:off + len(STAT_KEYS)] = totals
    off += len(STAT_KEYS)
    vec[off:off + SET_BUCKETS] = set_counts
    off += SET_BUCKETS
    vec[off:off + TRINKET_BUCKETS] = trinket_counts
    off += TRINKET_BUCKETS
    vec[off:off + WEAPON_BUCKETS] = weapon_counts
    off += WEAPON_BUCKETS
    vec[off:off + EMBELLISH_BUCKETS] = embellish_counts
    off += EMBELLISH_BUCKETS

    fight_style = options.fight_style if options else "Patchwerk"
    targets = float(options.desired_targets) if options else 1.0
    for i, fs in enumerate(FIGHT_STYLES):
        vec[off + i] = 1.0 if fs == fight_style else 0.0
    off += len(FIGHT_STYLES)
    vec[off] = targets
    off += 1
    assert off == VECTOR_LENGTH, (off, VECTOR_LENGTH)
    return vec
