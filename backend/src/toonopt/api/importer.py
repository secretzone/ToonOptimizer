"""POST /import/simc, GET /import/armory."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from toonopt import characters
from toonopt.models import CharacterProfile, Item, ItemSource
from toonopt.simc import profile as profile_mod

log = logging.getLogger(__name__)
router = APIRouter(tags=["import"])


def _save_character(profile: CharacterProfile) -> None:
    """Best-effort: never fail an import over the character store (see API.md "Characters")."""
    try:
        characters.save(profile)
    except Exception:
        log.exception("could not save imported character %s-%s", profile.name, profile.realm)

RAIDERIO_URL = "https://raider.io/api/v1/characters/profile"
RAIDERIO_SLOTS: dict[str, str] = {
    "head": "head", "neck": "neck", "shoulder": "shoulder", "back": "back", "chest": "chest",
    "wrist": "wrist", "hands": "hands", "waist": "waist", "legs": "legs", "feet": "feet",
    "finger1": "finger1", "finger2": "finger2", "trinket1": "trinket1", "trinket2": "trinket2",
    "mainhand": "main_hand", "offhand": "off_hand",
}
RIO_CLASS = {"Death Knight": "death_knight", "Demon Hunter": "demon_hunter"}


class ImportRequest(BaseModel):
    text: str


@router.post("/import/simc", response_model=CharacterProfile)
def import_simc(req: ImportRequest) -> CharacterProfile:
    if not req.text.strip():
        raise HTTPException(400, "empty export")
    try:
        profile = profile_mod.parse(req.text)
        _save_character(profile)
        return profile
    except profile_mod.ProfileError as e:
        raise HTTPException(400, f"could not parse /simc export: {e}") from e
    except Exception as e:                                   # pragma: no cover - defensive
        raise HTTPException(400, f"could not parse /simc export: {e}") from e


def _rio_item(slot: str, data: dict) -> Item:
    bonus = [int(b) for b in data.get("bonuses") or []]
    gems = [int(g) for g in data.get("gems") or []]
    ench = data.get("enchant")
    item = Item(
        key=f"equipped:{slot}", id=int(data.get("item_id") or 0), name=str(data.get("name") or ""),
        slot=slot, ilevel=int(data.get("item_level") or 0), quality=int(data.get("item_quality") or 0),
        icon=str(data.get("icon") or ""), bonus_ids=bonus, gem_ids=gems,
        enchant_id=int(ench) if ench else None, source=ItemSource(type="equipped", name="Armory"),
    )
    item.simc_string = item.to_simc(slot)
    return item


def profile_from_raiderio(data: dict) -> CharacterProfile:
    klass = str(data.get("class") or "")
    klass_slug = RIO_CLASS.get(klass, klass.lower().replace(" ", "_"))
    spec = str(data.get("active_spec_name") or "").lower().replace(" ", "_")
    role = {"DPS": "attack", "TANK": "tank", "HEALING": "heal"}.get(str(data.get("active_spec_role") or "DPS"), "attack")
    gear = (data.get("gear") or {}).get("items") or {}
    equipped: dict[str, Item] = {}
    for rio_slot, slot in RAIDERIO_SLOTS.items():
        if gear.get(rio_slot):
            equipped[slot] = _rio_item(slot, gear[rio_slot])
    talents = str(data.get("talentLoadout", {}).get("loadout_text") or data.get("talents") or "")
    race = str(data.get("race") or "").lower().replace(" ", "_")
    name = str(data.get("name") or "")
    realm = str(data.get("realm") or "")
    region = str(data.get("region") or "us").lower()
    header = [f'{klass_slug}="{name}"', f"level={80}", f"race={race}", f"region={region}",
              f"server={realm.lower().replace(' ', '_').replace(chr(39), '')}", f"role={role}", f"spec={spec}"]
    if talents:
        header.append(f"talents={talents}")
    return CharacterProfile(
        name=name, realm=realm, region=region, race=race, klass=klass_slug, spec=spec, role=role,
        talents=talents, equipped=equipped, simc_header="\n".join(header), raw="",
    )


@router.get("/import/armory", response_model=CharacterProfile)
def import_armory(region: str = Query(...), realm: str = Query(...), name: str = Query(...)) -> CharacterProfile:
    params = {"region": region.lower(), "realm": realm, "name": name, "fields": "gear,talents"}
    try:
        r = httpx.get(RAIDERIO_URL, params=params, timeout=15, follow_redirects=True)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"raider.io unreachable: {e}") from e
    if r.status_code != 200:
        raise HTTPException(404, f"character not found on raider.io ({r.status_code})")
    data = r.json()
    if not data.get("class"):
        raise HTTPException(404, "character not found on raider.io")
    prof = profile_from_raiderio(data)
    if not prof.equipped:
        raise HTTPException(404, "raider.io has no gear for this character")
    _save_character(prof)
    return prof
