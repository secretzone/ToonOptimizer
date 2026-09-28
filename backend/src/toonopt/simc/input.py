"""Build ``.simc`` input text from a profile, options and profilesets."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from toonopt.config import settings
from toonopt.models import SLOTS, CharacterProfile, Item, SimOptions

# SimOptions.buffs key -> SimC override name. ``windfury_totem`` has no override in
# SimC 1210-01 ("Unknown option 'override.windfury_totem'"), so it is not emitted.
BUFF_OVERRIDES: dict[str, str] = {
    "bloodlust": "bloodlust", "arcane_intellect": "arcane_intellect", "battle_shout": "battle_shout",
    "mark_of_the_wild": "mark_of_the_wild", "power_word_fortitude": "power_word_fortitude",
    "chaos_brand": "chaos_brand", "mystic_touch": "mystic_touch", "skyfury": "skyfury",
    "hunters_mark": "hunters_mark", "bleeding": "bleeding",
}
CONSUMABLE_KEYS = ("flask", "food", "potion", "augmentation", "temporary_enchant")
_NAME_BAD = re.compile(r"[^A-Za-z0-9_\-]+")
_SLOT_PREFIX = re.compile(r"^\w+=")

# Metrics always requested from every profileset run (see API.md "Raidbots parity, wave 1" M5).
PROFILESET_METRICS: tuple[str, ...] = ("dps", "prioritydps", "dtps", "hps", "dmg_taken")

# DungeonSlice is unsupported for these (klass, spec) pairs (server-side 400, see validate_options).
DUNGEON_SLICE_BANNED_SPECS: frozenset[tuple[str, str]] = frozenset({
    ("demon_hunter", "havoc"), ("demon_hunter", "vengeance"), ("demon_hunter", "devourer"),
})

# Expert-mode lines that would clash with options the runner/job manager always manages itself
# (json2/html/output/xml paths, thread counts) are stripped from every spliced block.
_EXPERT_BANNED_PREFIXES = ("threads=", "json2=", "html=", "output=", "xml=", "profileset_work_threads=")


def _consumable_options() -> dict[str, set[str]] | None:
    """``{category: {valid SimC name, ...}}`` from ``toonopt.data.season.consumable_options()``,
    or ``None`` when the season data layer isn't importable (validation is then skipped --
    free strings stay free strings, as before this wave)."""
    try:
        from toonopt.data.season import consumable_options
    except Exception:  # noqa: BLE001 - data layer optional
        return None
    try:
        return {cat: {o["value"] for o in opts} for cat, opts in consumable_options().items()}
    except Exception:  # noqa: BLE001 - a malformed season.json shouldn't block every sim
        return None


def validate_options(profile: CharacterProfile, options: SimOptions) -> None:
    """Raise ``ValueError`` for option/profile combinations the API rejects with 400.

    Called by ``api/sims.py`` before a job is submitted.
    """
    if options.fight_style == "DungeonSlice" and (profile.klass, profile.spec) in DUNGEON_SLICE_BANNED_SPECS:
        raise ValueError(
            f"DungeonSlice fight style is not supported for {profile.klass}/{profile.spec}"
        )
    valid = _consumable_options()
    if valid is not None:
        for key in CONSUMABLE_KEYS:
            val = (getattr(options.consumables, key, "") or "").strip()
            if not val:
                continue
            allowed = valid.get(key, set())
            if key == "temporary_enchant":
                # a value may combine two hands ("main_hand:x/off_hand:x"); each side must be
                # one of the season's known options, allowing the off_hand mirror of a
                # main_hand-listed oil/stone (the catalogue only lists the main_hand form).
                allowed_oh = {p.replace("main_hand:", "off_hand:", 1) for p in allowed if p.startswith("main_hand:")}
                ok = all(part in allowed or part in allowed_oh for part in val.split("/"))
            else:
                ok = val in allowed
            if not ok:
                raise ValueError(
                    f"invalid {key} {val!r}; valid options: {sorted(allowed)}"
                )


def effective_fight_style(options: SimOptions) -> str:
    """The SimC ``fight_style=`` value to emit -- TargetDummy/ExecutePatchwerk are not native
    SimC fight styles (verified against SimC 1210-01: both raise "Invalid fight style"); both
    are built on top of ``Patchwerk`` plus an explicit ``enemy=`` block (see enemy_lines)."""
    if options.fight_style in ("TargetDummy", "ExecutePatchwerk"):
        return "Patchwerk"
    return options.fight_style


def effective_max_time(options: SimOptions) -> int:
    if options.fight_style == "DungeonSlice":
        return 360
    return int(options.max_time)


def effective_desired_targets(options: SimOptions) -> int:
    if options.fight_style == "DungeonSlice":
        return 1
    return int(options.desired_targets)


def power_infusion_times(options: SimOptions) -> list[int]:
    """0, 120, 240, ... up to (not including) the effective max_time."""
    max_t = effective_max_time(options)
    times = list(range(0, max(max_t, 1), 120))
    return times or [0]


def enemy_lines(options: SimOptions) -> list[str]:
    """Lines appended AFTER the actor block for the two Raidbots-style meta fight styles."""
    if options.fight_style == "TargetDummy":
        return ["enemy=Target_Dummy", "enemy_fixed_health_percentage=100"]
    if options.fight_style == "ExecutePatchwerk":
        lines: list[str] = []
        for i in range(1, max(1, int(options.desired_targets)) + 1):
            lines.append(f"enemy=Execute_Target_{i}")
            lines.append("enemy_initial_health_percentage=20")
        return lines
    return []


def _expert_lines(text: str | None) -> list[str]:
    if not text:
        return []
    out = []
    for ln in text.splitlines():
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith(_EXPERT_BANNED_PREFIXES):
            continue
        out.append(ln)
    return out


@dataclass
class Profileset:
    name: str                     # unique SimC-safe name
    label: str
    overrides: list[str] = field(default_factory=list)


class ProfilesetNames:
    """Hands out unique SimC-safe profileset names and remembers the label for each."""

    def __init__(self) -> None:
        self.labels: dict[str, str] = {}
        self._used: set[str] = set()

    def make(self, label: str, hint: str | None = None) -> str:
        base = _NAME_BAD.sub("_", (hint or label).strip()).strip("_") or "ps"
        base = base[:60]
        name, n = base, 1
        while name in self._used:
            n += 1
            name = f"{base}_{n}"
        self._used.add(name)
        self.labels[name] = label
        return name


def profileset(name: str, overrides: list[str]) -> str:
    """Render ``profileset."name"+=override`` lines."""
    return "\n".join(f'profileset."{name}"+={o}' for o in overrides)


_FIELD_TOKENS = ("id", "bonus_id", "ilevel", "gem_id", "enchant_id", "crafted_stats", "crafting_quality")


def item_line(item: Item, slot: str | None = None) -> str:
    """Item as a SimC gear line for *slot*.

    The Item's fields are authoritative (so enchant/gem/bonus changes show up), but
    tokens SimC needs that the model does not carry (``redirected_base_stats``,
    ``content_tuning``, ``gem_bonus_id``, ``titan_disc_id`` ...) are kept from the
    original export string.
    """
    slot = slot or item.slot
    if not item.simc_string:
        return item.to_simc(slot)
    body = item.simc_string.split("=", 1)[1] if "=" in item.simc_string else item.simc_string
    parts = body.split(",")
    name, rest = ("", parts) if "=" in parts[0] else (parts[0].strip(), parts[1:])
    extras: list[str] = []
    for p in rest:
        if "=" not in p:
            continue
        k = p.split("=", 1)[0].strip()
        if k not in _FIELD_TOKENS:
            extras.append(p.strip())
    had = {p.split("=", 1)[0].strip() for p in rest if "=" in p}
    own = item.to_simc(slot).split(",")[1:]          # drop "slot=" token
    if "ilevel" not in had:                          # ilevel came from the "# Name (ilvl)" comment
        own = [t for t in own if not t.startswith("ilevel=")]
    return ",".join([f"{slot}={name}", *own, *extras])


def empty_slot(slot: str) -> str:
    return f"{slot}="


def precision_lines(options: SimOptions, profilesets: bool) -> list[str]:
    if options.iterations:
        return [f"iterations={int(options.iterations)}"]
    te = options.target_error
    if te is None or te <= 0:
        te = settings.profileset_target_error if profilesets else settings.default_target_error
    return [f"target_error={te}", "iterations=0"]


def global_lines(options: SimOptions, *, profilesets: bool, threads: int | None = None) -> list[str]:
    dummy = options.fight_style == "TargetDummy"
    lines = [
        f"fight_style={effective_fight_style(options)}",
        f"max_time={effective_max_time(options)}",
        f"vary_combat_length={options.vary_combat_length}",
        f"desired_targets={effective_desired_targets(options)}",
        *precision_lines(options, profilesets),
        "optimal_raid=0",
        # optimal_raid=0 turns off SimC's automatic raid buffs; blessing_of_the_bronze isn't
        # one of the buffs it withholds a toggle for via SimOptions.buffs, but Raidbots always
        # applies it, so restore parity here rather than silently losing it -- except on
        # TargetDummy, whose contract is "every override.*=0".
        f"override.blessing_of_the_bronze={0 if dummy else 1}",
    ]
    for key, override in BUFF_OVERRIDES.items():
        if dummy:
            lines.append(f"override.{override}=0")
        elif key in options.buffs:
            lines.append(f"override.{override}={1 if options.buffs[key] else 0}")
    lines.append(f"ptr={1 if options.ptr else 0}")
    lines.append(f"threads={threads or options.threads or settings.threads}")
    if profilesets:
        lines.append(f"profileset_work_threads={settings.profileset_work_threads}")
        lines.append("single_actor_batch=1")
    # Always requested so every profileset row (and, via results.py, the baseline) carries a
    # full metrics breakdown regardless of which one SimOptions.metric sorts/labels by.
    lines.append(f"profileset_metric={','.join(PROFILESET_METRICS)}")
    return lines


def actor_lines(profile: CharacterProfile, options: SimOptions) -> list[str]:
    lines = [ln for ln in profile.simc_header.splitlines() if ln.strip()]
    if not lines:
        lines = [f'{profile.klass}="{profile.name}"', f"spec={profile.spec}", f"level={profile.level}"]
        if profile.race:
            lines.append(f"race={profile.race}")
        lines.append(f"role={profile.role}")
        if profile.talents:
            lines.append(f"talents={profile.talents}")
    if options.talents_override:
        lines.append(f"talents={options.talents_override}")
    dummy = options.fight_style == "TargetDummy"
    for key in CONSUMABLE_KEYS:
        if dummy:
            # TargetDummy contract: all consumables disabled, regardless of the user's choice.
            lines.append(f"{key}=disabled")
            continue
        val = getattr(options.consumables, key, "") or ""
        # An empty selection must always be sent as "disabled" -- otherwise SimC falls back
        # to its own default flask/food/potion for the spec (a ~10% DPS swing), silently
        # ignoring the user's choice of "None".
        lines.append(f"{key}={val}" if val else f"{key}=disabled")
    if options.buffs.get("power_infusion"):
        lines.append("external_buffs.power_infusion=" + "/".join(str(t) for t in power_infusion_times(options)))
    if options.buffs.get("vantus_rune") and not dummy:
        # Raidbots parity, wave 2: Vantus Rune raid consumable (162 versatility, verified
        # accepted by SimulationCraft 1210-01 -- see tests/test_input.py).
        lines.append("set_custom_buff=vantus,stat_value=162_versatility")
    lines.append("")
    for slot in SLOTS:
        item = profile.equipped.get(slot)
        if item is not None:
            lines.append(item_line(item, slot))
    return lines


def build(
    profile: CharacterProfile,
    options: SimOptions,
    profilesets: list[Profileset] | None = None,
    *,
    extra_globals: list[str] | None = None,
    threads: int | None = None,
) -> str:
    """Complete ``.simc`` text: globals, actor block, gear, then profilesets.

    ``options.expert`` (SimOptions.expert) splices raw SimC text at four points: ``header``
    (very top of the file), ``pre_actor`` (after globals, before the actor block), ``post_actor``
    (right after the actor block/gear/enemy lines) and ``footer`` (very end, after profilesets).
    Lines starting with threads=/json2=/html=/output=/xml=/profileset_work_threads= are always
    stripped since those stay under the runner's/job manager's control.
    """
    sets = profilesets or []
    expert = options.expert
    header = _expert_lines(expert.header if expert else None)
    pre_actor = _expert_lines(expert.pre_actor if expert else None)
    post_actor = _expert_lines(expert.post_actor if expert else None)
    footer = _expert_lines(expert.footer if expert else None)
    parts: list[str] = [
        "# Generated by ToonOptimizer",
        *header,
        *global_lines(options, profilesets=bool(sets), threads=threads),
        *(extra_globals or []),
        *pre_actor,
        "",
        *actor_lines(profile, options),
        *enemy_lines(options),
        *post_actor,
        "",
    ]
    for ps in sets:
        parts.append(profileset(ps.name, ps.overrides))
    parts.extend(footer)
    return "\n".join(parts).rstrip("\n") + "\n"
