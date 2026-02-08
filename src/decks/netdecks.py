"""
Standard Netdecks

Downloaded decklists stored under: data/netdecks/mtggoldfish/

Notes:
- These decklists are sourced from MTGGoldfish and are expected to be Standard legal
  for the event/date they were published.
- We keep the decklists as text files so they can be refreshed without editing
  Python code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .deck import Deck, DeckEntry


_WUBRG_ORDER = ["W", "U", "B", "R", "G"]
_CARD_LINE_RE = re.compile(r"^(?P<qty>\d+)\s+(?P<name>.+?)\s*$")


def _repo_root() -> Path:
    # src/decks/netdecks.py -> src/decks -> src -> repo root
    return Path(__file__).resolve().parents[2]


def _mtggoldfish_dir() -> Path:
    return _repo_root() / "data" / "netdecks" / "mtggoldfish"


def _parse_mtggoldfish_decklist(deck_id: int) -> tuple[list[DeckEntry], list[DeckEntry]]:
    """
    Parse an MTGGoldfish "Text File (Default)" deck export.

    Format:
      4 Card Name
      ...

      2 Sideboard Card
      ...
    """
    path = _mtggoldfish_dir() / f"{deck_id}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing MTGGoldfish decklist file: {path} (deck_id={deck_id})"
        )

    text = path.read_text(encoding="utf-8", errors="replace")
    mainboard: list[DeckEntry] = []
    sideboard: list[DeckEntry] = []
    cur = mainboard

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cur = sideboard
            continue
        if line.lower().startswith("sideboard"):
            cur = sideboard
            continue

        m = _CARD_LINE_RE.match(line)
        if not m:
            raise ValueError(f"Unparseable deck line in {path}: {raw_line!r}")

        qty = int(m.group("qty"))
        name = m.group("name").strip()

        # MTGGoldfish exports multi-face / Room-style cards as "Front/Back".
        # Our card registry keys such cards by the front-face name only.
        if " // " in name:
            name = name.split(" // ", 1)[0].strip()
        elif "/" in name and "//" not in name:
            name = name.split("/", 1)[0].strip()

        cur.append(DeckEntry(name, qty))

    return mainboard, sideboard


def _colors_list(colors: str) -> list[str]:
    """Convert a compact color string like 'GRU' into ['U', 'R', 'G'] (WUBRG order)."""
    if not colors:
        return []
    color_set = {c.upper() for c in colors if c.upper() in set(_WUBRG_ORDER)}
    return [c for c in _WUBRG_ORDER if c in color_set]


@dataclass(frozen=True)
class _NetdeckMeta:
    id: str
    mtggoldfish_deck_id: int
    name: str
    archetype: str
    colors: str  # compact letters, e.g. "RU"
    description: str
    author: str | None = None
    source: str | None = None


_DECKS: list[_NetdeckMeta] = [
    # Keep stable IDs used by UI/tests.
    _NetdeckMeta(
        id="mono_red_netdeck",
        mtggoldfish_deck_id=7612489,
        name="Mono-Red Aggro",
        archetype="Aggro",
        colors="R",
        description="MTGGoldfish Standard Challenge 32 (2026-02-05) decklist.",
        author="quinniac",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-05",
    ),
    _NetdeckMeta(
        id="izzet_aggro_netdeck",
        mtggoldfish_deck_id=7612481,
        name="Izzet Elementals",
        archetype="Midrange",
        colors="RU",
        description="MTGGoldfish Standard Challenge 32 (2026-02-05) decklist.",
        author="_IlNano_",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-05",
    ),
    _NetdeckMeta(
        id="dimir_midrange_netdeck",
        mtggoldfish_deck_id=7612482,
        name="Dimir Midrange",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 32 (2026-02-05) decklist.",
        author="pedronametala",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-05",
    ),
    _NetdeckMeta(
        id="simic_ouroboroid_netdeck",
        mtggoldfish_deck_id=7612496,
        name="Simic Ouroboroid",
        archetype="Combo",
        colors="UG",
        description="MTGGoldfish Standard Challenge 32 (2026-02-05) decklist.",
        author="MTGHolic",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-05",
    ),
    _NetdeckMeta(
        id="jeskai_control_netdeck",
        mtggoldfish_deck_id=7608383,
        name="Jeskai Control",
        archetype="Control",
        colors="URW",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed decklist.",
        author="Marco Belacca",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="golgari_midrange_netdeck",
        mtggoldfish_deck_id=7601561,
        name="Golgari Midrange",
        archetype="Midrange",
        colors="BG",
        description="MTGGoldfish Standard Challenge 32 (2026-01-22) decklist.",
        author="tchuco",
        source="https://www.mtggoldfish.com/archetype/standard-golgari-midrange",
    ),
    _NetdeckMeta(
        id="azorius_simulacrum_netdeck",
        mtggoldfish_deck_id=7607670,
        name="Azorius Control",
        archetype="Control",
        colors="UW",
        description="MTGGoldfish Standard RC Super Qualifier (2026-02-01) 2nd place decklist.",
        author="jtl005",
        source="https://www.mtggoldfish.com/tournament/standard-rc-super-qualifier-2026-02-01",
    ),

    # Additional downloaded netdecks for breadth.
    _NetdeckMeta(
        id="ptle_2026_dimir_excruciator_netdeck",
        mtggoldfish_deck_id=7608380,
        name="Dimir Excruciator",
        archetype="Combo",
        colors="UB",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed (1st place) decklist.",
        author="Christoffer Larsen",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="ptle_2026_temur_harmonizer_netdeck",
        mtggoldfish_deck_id=7608381,
        name="Temur Harmonizer",
        archetype="Combo",
        colors="URG",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed (2nd place) decklist.",
        author="Toni Portolan",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="ptle_2026_izzet_lessons_netdeck",
        mtggoldfish_deck_id=7608384,
        name="Izzet Lessons",
        archetype="Midrange",
        colors="UR",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed (5th place) decklist.",
        author="Francisco Sanchez",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="ptle_2026_bant_airbending_netdeck",
        mtggoldfish_deck_id=7608386,
        name="Bant Airbending",
        archetype="Midrange",
        colors="UGW",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed (7th place) decklist.",
        author="Cyprien Tron",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="ptle_2026_five_color_rhythm_netdeck",
        mtggoldfish_deck_id=7608388,
        name="Five-Color Rhythm",
        archetype="Midrange",
        colors="WUBRG",
        description="MTGGoldfish Pro Tour Lorwyn Eclipsed (8th place) decklist.",
        author="Guglielmo Lupi",
        source="https://www.mtggoldfish.com/tournament/61376",
    ),
    _NetdeckMeta(
        id="sc_2026_02_05_mono_green_landfall_netdeck",
        mtggoldfish_deck_id=7612485,
        name="Mono-Green Landfall",
        archetype="Aggro",
        colors="G",
        description="MTGGoldfish Standard Challenge 32 (2026-02-05) 1st place decklist.",
        author="Tetsubou",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-05",
    ),
    _NetdeckMeta(
        id="rcsq_2026_02_01_boros_dragons_netdeck",
        mtggoldfish_deck_id=7607680,
        name="Boros Dragons",
        archetype="Midrange",
        colors="RW",
        description="MTGGoldfish Standard RC Super Qualifier (2026-02-01) 3rd place decklist.",
        author="PedraStone",
        source="https://www.mtggoldfish.com/tournament/standard-rc-super-qualifier-2026-02-01",
    ),
    _NetdeckMeta(
        id="rcsq_2026_02_01_selesnya_landfall_netdeck",
        mtggoldfish_deck_id=7607654,
        name="Selesnya Landfall",
        archetype="Aggro",
        colors="GW",
        description="MTGGoldfish Standard RC Super Qualifier (2026-02-01) 6th place decklist.",
        author="Svetliy",
        source="https://www.mtggoldfish.com/tournament/standard-rc-super-qualifier-2026-02-01",
    ),
    _NetdeckMeta(
        id="rcsq_2026_02_01_mono_green_landfall_netdeck",
        mtggoldfish_deck_id=7607683,
        name="Mono-Green Landfall",
        archetype="Aggro",
        colors="G",
        description="MTGGoldfish Standard RC Super Qualifier (2026-02-01) 7th place decklist.",
        author="Zoza",
        source="https://www.mtggoldfish.com/tournament/standard-rc-super-qualifier-2026-02-01",
    ),

    # Standard Challenge 64 (2026-02-02)
    _NetdeckMeta(
        id="sc64_2026_02_02_1st_ub_netdeck",
        mtggoldfish_deck_id=7609539,
        name="UB",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 1st place decklist.",
        author="VictorEsquici",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_2nd_izzet_spellementals_netdeck",
        mtggoldfish_deck_id=7609520,
        name="Izzet Spellementals",
        archetype="Midrange",
        colors="UR",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 2nd place decklist.",
        author="renatoaraujo",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_3rd_mono_red_aggro_netdeck",
        mtggoldfish_deck_id=7609515,
        name="Mono-Red Aggro",
        archetype="Aggro",
        colors="R",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 3rd place decklist.",
        author="Boin",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_4th_rakdos_monument_netdeck",
        mtggoldfish_deck_id=7609536,
        name="Rakdos Monument",
        archetype="Midrange",
        colors="BR",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 4th place decklist.",
        author="SpockVidaLoka",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_5th_dimir_midrange_netdeck",
        mtggoldfish_deck_id=7609521,
        name="Dimir Midrange",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 5th place decklist.",
        author="O_danielakos",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_6th_four_color_elementals_netdeck",
        mtggoldfish_deck_id=7609540,
        name="4c Elementals",
        archetype="Midrange",
        colors="UBRG",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 6th place decklist.",
        author="BeoulveHeart",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_7th_ub_netdeck",
        mtggoldfish_deck_id=7609534,
        name="UB",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 7th place decklist.",
        author="Chichichi",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),
    _NetdeckMeta(
        id="sc64_2026_02_02_8th_ub_netdeck",
        mtggoldfish_deck_id=7609545,
        name="UB",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 64 (2026-02-02) 8th place decklist.",
        author="VitorCarvalho01",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-64-2026-02-02",
    ),

    # Standard Challenge 32 (2026-02-03)
    _NetdeckMeta(
        id="sc32_2026_02_03_1st_mono_green_landfall_netdeck",
        mtggoldfish_deck_id=7610806,
        name="Mono-Green Landfall",
        archetype="Aggro",
        colors="G",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 1st place decklist.",
        author="Randompurple",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_2nd_mono_red_aggro_netdeck",
        mtggoldfish_deck_id=7610801,
        name="Mono-Red Aggro",
        archetype="Aggro",
        colors="R",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 2nd place decklist.",
        author="Arkany1",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_3rd_dimir_control_netdeck",
        mtggoldfish_deck_id=7610802,
        name="Dimir Control",
        archetype="Control",
        colors="UB",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 3rd place decklist.",
        author="Univerce",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_4th_izzet_lessons_netdeck",
        mtggoldfish_deck_id=7610807,
        name="Izzet Lessons",
        archetype="Midrange",
        colors="UR",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 4th place decklist.",
        author="groot02",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_5th_izzet_spellementals_netdeck",
        mtggoldfish_deck_id=7610792,
        name="Izzet Spellementals",
        archetype="Midrange",
        colors="UR",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 5th place decklist.",
        author="Manny-",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_6th_izzet_lessons_netdeck",
        mtggoldfish_deck_id=7610787,
        name="Izzet Lessons",
        archetype="Midrange",
        colors="UR",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 6th place decklist.",
        author="pirol94",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_7th_ub_netdeck",
        mtggoldfish_deck_id=7610779,
        name="UB",
        archetype="Midrange",
        colors="UB",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 7th place decklist.",
        author="rastaf",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
    _NetdeckMeta(
        id="sc32_2026_02_03_8th_mono_red_aggro_netdeck",
        mtggoldfish_deck_id=7610795,
        name="Mono-Red Aggro",
        archetype="Aggro",
        colors="R",
        description="MTGGoldfish Standard Challenge 32 (2026-02-03) 8th place decklist.",
        author="deleon91",
        source="https://www.mtggoldfish.com/tournament/standard-challenge-32-2026-02-03",
    ),
]


def _build_netdecks() -> dict[str, Deck]:
    decks: dict[str, Deck] = {}
    for meta in _DECKS:
        mainboard, sideboard = _parse_mtggoldfish_decklist(meta.mtggoldfish_deck_id)
        decks[meta.id] = Deck(
            name=meta.name,
            archetype=meta.archetype,
            colors=_colors_list(meta.colors),
            description=meta.description,
            mainboard=mainboard,
            sideboard=sideboard,
            author=meta.author,
            source=meta.source,
            format="Standard",
        )
    return decks


NETDECKS = _build_netdecks()


def get_netdeck(deck_id: str) -> Deck:
    """Get a netdeck by ID."""
    deck = NETDECKS.get(deck_id)
    if not deck:
        raise ValueError(f"Unknown netdeck: {deck_id}. Available: {list(NETDECKS.keys())}")
    return deck
