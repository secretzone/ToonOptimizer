"""Pydantic models shared by the data layer, sim engines and API. Mirrors /API.md exactly."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

SLOTS: tuple[str, ...] = (
    "head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist", "legs", "feet",
    "finger1", "finger2", "trinket1", "trinket2", "main_hand", "off_hand",
)
FightStyle = Literal[
    "Patchwerk", "DungeonSlice", "HecticAddCleave", "CleaveAdd",
    "LightMovement", "HeavyMovement", "CastingPatchwerk",
    "TargetDummy", "ExecutePatchwerk",
]
Metric = Literal["dps", "prioritydps", "dtps", "hps", "dmg_taken"]
SourceType = Literal[
    "raid", "dungeon", "world_boss", "delve", "crafted", "vault", "bag", "equipped", "catalyst", "upgrade",
]
EffortLevel = Literal["trivial", "easy", "medium", "hard", "very_hard"]
AdvisorVerdict = Literal["obvious", "likely", "sim_to_confirm", "sidegrade", "downgrade"]
JobType = Literal[
    "quick", "topgear", "droptimizer", "statweights", "gearcompare", "talentcompare", "advanced",
    "simc_install", "data_refresh", "surrogate_train", "upgrades", "gems", "consumables", "omnium",
]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ItemSource(BaseModel):
    type: SourceType
    name: str
    boss: str | None = None
    difficulty: str | None = None
    key_level: int | None = None


class Item(BaseModel):
    key: str
    id: int
    name: str = ""
    slot: str                      # SimC slot; "finger"/"trinket" allowed for unplaced candidates
    inventory_type: int = 0
    ilevel: int = 0
    quality: int = 0
    icon: str = ""
    bonus_ids: list[int] = Field(default_factory=list)
    sockets: int = 0                # empty + filled sockets, from bonus ids (see data.bonuses.socket_count)
    gem_ids: list[int] = Field(default_factory=list)
    enchant_id: int | None = None
    crafted_stats: list[int] = Field(default_factory=list)
    crafting_quality: int | None = None
    unique_equipped: str | None = None
    set_id: int | None = None
    stats: dict[str, float] = Field(default_factory=dict)
    source: ItemSource | None = None
    simc_string: str = ""
    resolved: bool = True                          # False if the data layer could not enrich this item

    def to_simc(self, slot: str | None = None) -> str:
        """Render `slot=,id=..,bonus_id=..` for the given (or own) slot."""
        parts = [f"{slot or self.slot}=", f"id={self.id}"]
        if self.bonus_ids:
            parts.append("bonus_id=" + "/".join(str(b) for b in self.bonus_ids))
        if self.ilevel:
            parts.append(f"ilevel={self.ilevel}")
        if self.gem_ids:
            parts.append("gem_id=" + "/".join(str(g) for g in self.gem_ids))
        if self.enchant_id:
            parts.append(f"enchant_id={self.enchant_id}")
        if self.crafted_stats:
            parts.append("crafted_stats=" + "/".join(str(s) for s in self.crafted_stats))
        if self.crafting_quality:
            parts.append(f"crafting_quality={self.crafting_quality}")
        return ",".join(parts)


class Currency(BaseModel):
    id: int
    kind: Literal["currency", "item"] = "currency"
    amount: int = 0
    name: str = ""
    icon: str = ""
    crest: str | None = None      # exact string used in UpgradeInfo.crest, when this is a crest
    max_quantity: int | None = None


class SavedLoadout(BaseModel):
    name: str
    string: str
    kind: Literal["active", "saved"]


class CharacterProfile(BaseModel):
    name: str
    realm: str = ""
    region: str = "us"
    level: int = 80
    race: str = ""
    klass: str
    spec: str
    role: Literal["attack", "tank", "heal"] = "attack"
    talents: str = ""
    professions: dict[str, int] = Field(default_factory=dict)
    equipped: dict[str, Item] = Field(default_factory=dict)
    bags: list[Item] = Field(default_factory=list)
    vault: list[Item] = Field(default_factory=list)
    currencies: list[Currency] = Field(default_factory=list)   # from the addon's /simc export currency comments
    catalyst_charges: int | None = None                        # None: export carried no catalyst_currencies line
    catalyst_charges_max: int | None = None                    # that currency's CurrencyTypes.MaxQty, when known
    simc_header: str = ""
    raw: str = ""
    imported_at: str = Field(default_factory=now_iso)
    warnings: list[str] = Field(default_factory=list)   # e.g. items that failed to resolve on import
    saved_loadouts: list[SavedLoadout] = Field(default_factory=list)  # from the export's loadout comments
    loot_spec: str | None = None                        # "# loot_spec=" if present
    high_watermarks: dict[str, int] = Field(default_factory=dict)  # "# slot_high_watermarks=" slot -> ilvl
    omnium: dict[int, int] = Field(default_factory=dict)  # "omnium_talents=<entry_id>:<rank>/..." entry_id -> rank
    source: Literal["paste", "addon", "armory"] | None = None   # how the profile was imported


class Consumables(BaseModel):
    flask: str = ""
    food: str = ""
    potion: str = ""
    augmentation: str = ""
    temporary_enchant: str = ""


DEFAULT_BUFFS: dict[str, bool] = {
    "bloodlust": True, "arcane_intellect": True, "battle_shout": True, "mark_of_the_wild": True,
    "power_word_fortitude": True, "chaos_brand": True, "mystic_touch": True, "skyfury": True,
    "hunters_mark": True, "bleeding": True, "windfury_totem": False, "power_infusion": False,
    "vantus_rune": False,
}


class ExpertOptions(BaseModel):
    """Raw SimC text spliced into the generated input; see simc/input.py::build."""
    header: str | None = None
    pre_actor: str | None = None
    post_actor: str | None = None
    footer: str | None = None


class SimOptions(BaseModel):
    fight_style: FightStyle = "Patchwerk"
    max_time: int = 300
    vary_combat_length: float = 0.2
    desired_targets: int = 1
    iterations: int | None = None
    target_error: float | None = None
    buffs: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_BUFFS))
    consumables: Consumables = Field(default_factory=Consumables)
    enchant_all: bool = False
    socket_all: bool = False
    talents_override: str | None = None
    ptr: bool = False
    threads: int | None = None
    metric: Metric = "dps"
    expert: ExpertOptions | None = None
    precision: Literal["low", "medium", "high"] | None = None   # staged "Smart Sim"; see sims.base.run_staged


class RaidSource(BaseModel):
    type: Literal["raid"] = "raid"
    instance_id: int
    difficulty: Literal["lfr", "normal", "heroic", "mythic"]
    bosses: list[int] | None = None


class DungeonSource(BaseModel):
    type: Literal["dungeon"] = "dungeon"
    instance_ids: list[int] | None = None
    key_level: int = 10          # 0 = mythic0, -1 = vault (max)
    vault: bool = False          # use this key level's vault ilvl/bonus ids instead of end-of-dungeon


class WorldBossSource(BaseModel):
    type: Literal["world_boss"] = "world_boss"


class DelveSource(BaseModel):
    type: Literal["delve"] = "delve"
    tier: int = 8


class CraftedSource(BaseModel):
    type: Literal["crafted"] = "crafted"
    ilevel: int
    stats: tuple[str, str]


class CatalystSource(BaseModel):
    """Raidbots parity, wave 2: the character's own equipped/bag items in a Catalyst slot,
    catalyzed at ``track``/``rank`` (default: that track's max rank) rather than at their
    current rank -- see sims/droptimizer.py::_catalyst_source_items."""
    type: Literal["catalyst"] = "catalyst"
    track: str
    rank: int | None = None


DropSource = RaidSource | DungeonSource | WorldBossSource | DelveSource | CraftedSource | CatalystSource


class Progress(BaseModel):
    phase: str = "queued"
    current: int = 0
    total: int = 0
    pct: float = 0.0
    message: str = ""


class Job(BaseModel):
    id: str
    type: JobType
    status: JobStatus = "queued"
    progress: Progress = Field(default_factory=Progress)
    character: str | None = None
    spec: str | None = None
    created: str = Field(default_factory=now_iso)
    started: str | None = None
    finished: str | None = None
    error: str | None = None


class UpgradeStepInfo(BaseModel):
    rank: int
    ilevel: int
    crest: str
    cost: int


class UpgradeInfo(BaseModel):
    slot: str
    item_id: int
    track: str                            # "Veteran"|"Champion"|"Hero"|"Myth"|...
    from_rank: int
    to_rank: int
    max_rank: int
    from_ilevel: int
    to_ilevel: int
    crest: str                            # crest type name for this step of the track
    cost: int                             # crests from from_rank to to_rank
    steps: list[UpgradeStepInfo] = Field(default_factory=list)
    affordable: bool | None = None        # cost <= the profile's amount of `crest`; None: no currency info


class GemChange(BaseModel):
    slot: str
    socket_index: int
    gem_id: int
    gem_name: str
    stat: str


class EnchantChange(BaseModel):
    slot: str
    enchant_id: int
    name: str
    stat: str | None = None


class ConsumableChange(BaseModel):
    category: Literal["flask", "food", "potion", "augmentation", "temporary_enchant"]
    name: str


class OmniumChange(BaseModel):
    row: int
    entry_id: int
    name: str


class ResultMeta(BaseModel):
    item: Item | None = None
    items: list[Item] | None = None
    loadout: str | None = None
    source: ItemSource | None = None
    changes: dict[str, Item] | None = None
    predicted_dps: float | None = None    # experimental: set by the GPU surrogate ("smart" Top Gear)
    upgrade: UpgradeInfo | None = None
    gem: GemChange | None = None
    enchant: EnchantChange | None = None
    consumable: ConsumableChange | None = None
    omnium: OmniumChange | None = None
    stage: int | None = None    # highest staged-precision stage this row reached (1..len(stages)); see sims.base.run_staged


class ResultRow(BaseModel):
    name: str
    label: str
    dps: float
    dps_error: float = 0.0
    delta: float = 0.0
    delta_pct: float = 0.0
    meta: ResultMeta = Field(default_factory=ResultMeta)
    metrics: dict[str, float] = Field(default_factory=dict)   # every metric SimC returned (dps/prioritydps/dtps/hps/dmg_taken)


class Baseline(BaseModel):
    name: str = "baseline"
    label: str = "Current gear"
    dps: float = 0.0
    dps_error: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)


class BreakdownRow(BaseModel):
    name: str
    id: int = 0
    type: Literal["direct", "periodic", "pet"] = "direct"
    total: float = 0.0
    pct: float = 0.0
    count: float = 0.0
    hit: float = 0.0
    crit: float = 0.0
    crit_pct: float = 0.0


class UptimeRow(BaseModel):
    name: str
    pct: float


class StatWeights(BaseModel):
    weights: dict[str, float]
    normalized: dict[str, float]
    pawn: str
    error: dict[str, float] = Field(default_factory=dict)


class Timing(BaseModel):
    seconds: float = 0.0
    iterations: int = 0


class Group(BaseModel):
    """Per drop-source summary for Droptimizer (see API.md 'Raidbots parity, wave 1').

    Built from the *best* row of each distinct item (a ring/trinket still has 2 rows in
    ``SimResult.results`` -- one per slot -- but counts once here, via its higher-dps row).
    """
    key: str
    label: str
    kind: Literal["boss", "dungeon", "delve", "world_boss", "crafted", "catalyst"]
    n: int
    best: float
    best_pct: float
    best_label: str
    ev: float               # mean(max(0, delta)) across the group's items, equal drop odds assumed
    ev_pct: float
    upgrade_share: float     # share of the group's items with delta > 0


class SimResult(BaseModel):
    job_id: str
    type: JobType
    character: str = ""
    spec: str = ""
    klass: str = ""
    simc_version: str = ""
    wow_version: str = ""
    options: SimOptions = Field(default_factory=SimOptions)
    baseline: Baseline = Field(default_factory=Baseline)
    results: list[ResultRow] = Field(default_factory=list)
    breakdown: list[BreakdownRow] = Field(default_factory=list)
    uptimes: list[UptimeRow] = Field(default_factory=list)
    stat_weights: StatWeights | None = None
    timing: Timing = Field(default_factory=Timing)
    input_file: str = ""
    notes: list[str] = Field(default_factory=list)  # human sentences surfacing non-fatal skips (upgrades/gems)
    groups: list[Group] | None = None  # Droptimizer per-source summary; None for other job types
    metric: Metric = "dps"                      # metric rows/baseline are reported and sorted on
    valid_fight_style: bool | None = None        # json2 players[0].valid_fight_style


# ---------------------------------------------------------------------------
# Characters, Advisor, Reports (see API.md)

class CharacterSummary(BaseModel):
    slug: str
    name: str
    realm: str
    klass: str
    spec: str
    ilevel_equipped: float
    imported_at: str


class StatPriority(BaseModel):
    source: Literal["statweights_job", "recommendation"]
    order: list[str]
    weights: dict[str, float] | None = None
    job_id: str | None = None


class AdvisorEquipped(BaseModel):
    item: Item
    ilevel: int
    stat_score: float
    track: str | None = None
    rank: str | None = None                     # e.g. "3/6"


class AdvisorPathStep(BaseModel):
    step: str
    crest: str | None = None
    cost: int | None = None


class AdvisorSource(ItemSource):
    effort: EffortLevel
    weekly: bool = False


class AdvisorCandidate(BaseModel):
    item: Item
    max_item: Item | None = None
    source: AdvisorSource
    ilevel_gain: int
    ilevel_gain_max: int
    stat_score: float
    stat_score_delta: float
    verdict: AdvisorVerdict
    reasons: list[str] = Field(default_factory=list)
    path: list[AdvisorPathStep] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class AdvisorSlot(BaseModel):
    slot: str
    equipped: AdvisorEquipped
    candidates: list[AdvisorCandidate] = Field(default_factory=list)
    bis_heuristic: AdvisorCandidate | None = None


class AdvisorTier(BaseModel):
    set_id: int | None = None
    equipped_pieces: int = 0
    slots_with_tier: list[str] = Field(default_factory=list)
    catalyst_charges: int | None = None


class AdvisorSimPlan(BaseModel):
    droptimizer: list[DropSource] = Field(default_factory=list)
    topgear_candidate_keys: list[str] = Field(default_factory=list)
    upgrades_slots: list[str] = Field(default_factory=list)
    note: str = ""


class AdvisorResult(BaseModel):
    slug: str
    character: str
    klass: str
    spec: str
    generated_at: str = Field(default_factory=now_iso)
    stat_priority: StatPriority
    ilevel_equipped: float
    slots: list[AdvisorSlot] = Field(default_factory=list)
    tier: AdvisorTier = Field(default_factory=AdvisorTier)
    sim_plan: AdvisorSimPlan = Field(default_factory=AdvisorSimPlan)
    notes: list[str] = Field(default_factory=list)


ReportSectionKind = Literal["markdown", "upgrades", "bis", "talents", "kv"]


class ReportSimRef(BaseModel):
    job_id: str
    type: str
    label: str


class ReportSource(BaseModel):
    title: str
    url: str
    fetched_at: str


class ReportHistoryEntry(BaseModel):
    updated_at: str
    summary: str


class CharacterReport(BaseModel):
    """Loosely typed: ``sections`` are plain dicts validated by ``kind`` in ``toonopt.reports``
    rather than a pydantic union, per the API.md contract's ``ReportSection`` shapes."""
    slug: str
    character: str
    realm: str = ""
    klass: str
    spec: str
    updated_at: str = Field(default_factory=now_iso)
    ilevel_equipped: float = 0.0
    season: str = ""
    simc_version: str = ""
    summary: str = ""
    sections: list[dict] = Field(default_factory=list)
    advisor: AdvisorResult | None = None
    sim_refs: list[ReportSimRef] = Field(default_factory=list)
    sources: list[ReportSource] = Field(default_factory=list)
