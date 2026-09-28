"""Advanced: raw ``.simc`` text passthrough. The runner adds ``json2=``/``threads=``."""
from __future__ import annotations

import re

from toonopt.models import SimOptions, SimResult

_CLASS_LINE = re.compile(r'^(deathknight|death_knight|demonhunter|demon_hunter|druid|evoker|hunter|mage|monk|paladin|priest|rogue|shaman|warlock|warrior)\s*=\s*"?([^"\n]*)"?', re.MULTILINE)
_SPEC_LINE = re.compile(r"^spec\s*=\s*(\w+)", re.MULTILINE)


def describe(simc_text: str) -> tuple[str | None, str | None]:
    """(character, spec) guessed from the text for the Job record."""
    m = _CLASS_LINE.search(simc_text)
    s = _SPEC_LINE.search(simc_text)
    return (m.group(2).strip() if m else None), (s.group(1) if s else None)


def execute(ctx, simc_text: str, options: SimOptions | None = None) -> SimResult:
    options = options or SimOptions()
    return ctx.sim(simc_text, options)
