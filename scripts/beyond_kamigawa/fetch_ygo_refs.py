#!/usr/bin/env python3
"""
Beyond Kamigawa — fetch YGO card art as a style-reference library.

Builds a curated library of ~60 well-known Yu-Gi-Oh! cards covering the
(Type × Attribute × Level-band) matrix that Beyond Kamigawa actually uses.
Each reference is downloaded from YGOProDeck's cropped-art endpoint and
saved locally so the downstream OAI image-generation pass can pick the
closest reference per Beyond-Kamigawa card and pass it as ``input_image``.

The library is also written as a JSON manifest so the gen step can match
BK cards to refs by (type, attribute, level_band) without re-querying.

Usage::

    python scripts/beyond_kamigawa/fetch_ygo_refs.py             # download all
    python scripts/beyond_kamigawa/fetch_ygo_refs.py --dry-run   # show plan
    python scripts/beyond_kamigawa/fetch_ygo_refs.py --force     # re-download

Outputs:
    assets/card_art/beyond/kamigawa/refs/<key>.jpg   (one per library entry)
    assets/card_art/beyond/kamigawa/refs/_manifest.json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFS_DIR = PROJECT_ROOT / "assets" / "card_art" / "beyond" / "kamigawa" / "refs"
MANIFEST_PATH = REFS_DIR / "_manifest.json"


@dataclass
class LibraryEntry:
    """One slot in the style library.

    ``key`` is the slug-style identifier the gen step uses to look up
    references (e.g. ``warrior_light_lv7_8``). ``ygo_name`` is the exact
    card name to query against YGOProDeck. ``description`` is a one-line
    note on why this card was chosen for this slot — useful when picking
    a substitute.
    """
    key: str
    ygo_name: str
    description: str
    # Filled in during fetch:
    card_id: int | None = None
    attribute: str | None = None
    type: str | None = None
    race: str | None = None        # YGO "Race" — the monster Type subtype
    level: int | None = None
    atk: int | None = None
    def_val: int | None = None
    art_url: str | None = None
    local_path: str | None = None


# =============================================================================
# Curated style library — covers the matrix Beyond Kamigawa actually uses
# =============================================================================

# Coverage rationale:
# - Samurai (Warrior + LIGHT/EARTH/DARK/FIRE × Lv 1-8)
# - Ninja (Warrior + DARK/WATER/WIND × Lv 2-8)
# - Spirit Dragons (Dragon + LIGHT/DARK/EARTH/WATER/FIRE/DIVINE × Lv 1-12)
# - Moonfolk (Spellcaster + Wing Beast + WATER/WIND × Lv 2-7)
# - Modified (Machine + EARTH/WIND × Lv 1-7)
# - Plus Spell/Trap card frames and Extra-Deck (Synchro/Xyz/Fusion/Pendulum/Link)
# - Plus minor types used in staples: Plant, Rock, Fairy, Beast, Beast-Warrior,
#   Reptile, Pyro, Fiend, Insect

LIBRARY: list[LibraryEntry] = [
    # === Warriors (Samurai / Ninja / Modified-Cyborg) ===
    LibraryEntry("warrior_light_lv3_4", "Marauding Captain",
                 "LIGHT Lv 3 noble swarm-warrior — exemplar Samurai mid-curve"),
    LibraryEntry("warrior_light_lv5_6", "Command Knight",
                 "FIRE Lv 4 armored noble — substitute for LIGHT mid-tier samurai"),
    LibraryEntry("warrior_light_lv7_8", "Buster Blader",
                 "EARTH Lv 7 anti-dragon swordmaster — Konda-tier hero"),
    LibraryEntry("warrior_dark_lv3_4", "Dark Blade",
                 "DARK Lv 4 cloaked warrior — generic dark-honor samurai"),
    LibraryEntry("warrior_dark_lv4", "Vorse Raider",
                 "DARK Lv 4 vicious raider — ronin/ninja vibes"),
    LibraryEntry("warrior_dark_lv5_6", "Goyo Guardian",
                 "EARTH Lv 6 enforcer Synchro — high-stat dark warrior"),
    LibraryEntry("warrior_earth_lv3_4", "Battle Ox",
                 "EARTH Lv 4 brute beast-warrior — peasant-soldier samurai"),
    LibraryEntry("warrior_earth_lv4_brute", "Gene-Warped Warwolf",
                 "EARTH Lv 4 powerful beast-warrior"),
    LibraryEntry("warrior_water_lv3_4", "Aqua Armor Ninja",
                 "WATER Lv 3 ninja warrior — direct match for Ninja archetype"),
    LibraryEntry("warrior_dark_lv2_ninja", "Strike Ninja",
                 "DARK Lv 4 silent strike ninja"),

    # === Dragons (Spirit Dragons cycle) ===
    LibraryEntry("dragon_light_lv7_9", "Blue-Eyes White Dragon",
                 "LIGHT Lv 8 iconic noble dragon — Yosei-tier"),
    LibraryEntry("dragon_dark_lv7_9", "Red-Eyes Black Dragon",
                 "DARK Lv 7 menacing crimson dragon — Kokusho-tier"),
    LibraryEntry("dragon_earth_lv7_9", "Felgrand Dragon",
                 "LIGHT Lv 8 stone-armored dragon — Jugan substitute (EARTH-flavor)"),
    LibraryEntry("dragon_water_lv7_9", "Water Dragon",
                 "WATER Lv 8 oceanic dragon — Keiga-tier"),
    LibraryEntry("dragon_fire_lv7_9", "Hieratic Dragon of Tefnuit",
                 "LIGHT Lv 5 hieratic dragon — Ryusei substitute (FIRE-flavor)"),
    LibraryEntry("dragon_light_lv4", "Alexandrite Dragon",
                 "LIGHT Lv 4 small radiant dragon"),
    LibraryEntry("dragon_wind_lv4", "Luster Dragon",
                 "WIND Lv 4 emerald-scale dragon"),
    LibraryEntry("dragon_dark_lv6_7", "Spear Dragon",
                 "WIND Lv 4 piercing dragon — small/mid-tier dragon ref"),
    LibraryEntry("dragon_divine_lv10", "Slifer the Sky Dragon",
                 "DIVINE Lv 10 god-tier serpent dragon — O-Kagachi-tier"),
    LibraryEntry("dragon_light_lv1", "Petit Dragon",
                 "WIND Lv 2 small dragonling — Iname-tier fodder"),

    # === Spellcasters (Samurai mages, Moonfolk, Spirits) ===
    LibraryEntry("spellcaster_light_lv1_2", "Magician of Faith",
                 "LIGHT Lv 1 priestess — frail but iconic"),
    LibraryEntry("spellcaster_light_lv3_4", "Mystical Elf",
                 "LIGHT Lv 4 chanting protector"),
    LibraryEntry("spellcaster_dark_lv3_4", "Witch of the Black Forest",
                 "DARK Lv 4 forest witch"),
    LibraryEntry("spellcaster_dark_lv5_6", "Dark Magician",
                 "DARK Lv 7 iconic mage"),
    LibraryEntry("spellcaster_dark_lv7_8", "Cosmo Queen",
                 "DARK Lv 8 starborn queen mage"),
    LibraryEntry("spellcaster_water_lv4", "Lady of Faith",
                 "LIGHT Lv 3 — substitute for water-mage role"),
    LibraryEntry("spellcaster_water_lv6_7", "Magician of Black Chaos",
                 "DARK Lv 8 chaos mage — high-tier finisher"),
    LibraryEntry("spellcaster_neutral_tuner", "Effect Veiler",
                 "LIGHT Lv 1 hand-trap tuner — small-mage iconic"),

    # === Machines (Modified / Cyber-Kamigawa) ===
    LibraryEntry("machine_light_lv5", "Cyber Dragon",
                 "LIGHT Lv 5 metal serpent — modern cyber boss"),
    LibraryEntry("machine_earth_lv4", "Ancient Gear Soldier",
                 "EARTH Lv 4 steam-mech — Modified mid-curve"),
    LibraryEntry("machine_earth_lv6", "Ancient Gear Beast",
                 "EARTH Lv 6 mech beast"),
    LibraryEntry("machine_wind_lv4", "Mecha Phantom Beast Tetherwolf",
                 "WIND Lv 4 sleek mecha"),
    LibraryEntry("machine_lv10_boss", "Cyber End Dragon",
                 "LIGHT Lv 10 mecha boss"),

    # === Wing Beasts (Moonfolk fliers) ===
    LibraryEntry("wingbeast_wind_lv4", "Harpie Lady",
                 "WIND Lv 4 winged warrior — fliers"),
    LibraryEntry("wingbeast_wind_lv7", "Simorgh, Bird of Divinity",
                 "WIND Lv 7 mythic bird"),

    # === Beasts / Beast-Warriors (Samurai noble beasts, Spirit kitsune) ===
    LibraryEntry("beast_light_lv4", "Manticore of Darkness",
                 "DARK Lv 6 — substitute for noble beast"),
    LibraryEntry("beast_earth_lv4", "Berserk Gorilla",
                 "EARTH Lv 4 raging ape"),
    LibraryEntry("beastwarrior_earth_lv4", "Inpachi",
                 "EARTH Lv 4 — substitute for stout beast-warrior"),

    # === Fiends (Iname spirits, Yukora) ===
    LibraryEntry("fiend_dark_lv1_2", "Sangan",
                 "DARK Lv 3 small fiend scout — Iname-tier"),
    LibraryEntry("fiend_dark_lv5_6", "Summoned Skull",
                 "DARK Lv 6 powerful fiend — Yukora-tier"),
    LibraryEntry("fiend_dark_lv7", "Mefist the Infernal General",
                 "DARK Lv 6 dark commander"),

    # === Plants / Reptile / Rock / Pyro / Insect / Fairy ===
    LibraryEntry("plant_earth_lv2", "Dandylion",
                 "EARTH Lv 3 plant fodder"),
    LibraryEntry("rock_earth_lv1_2", "Giant Soldier of Stone",
                 "EARTH Lv 3 stone soldier — Mox Diamond / Greaves Bearer ref"),
    LibraryEntry("pyro_fire_lv1", "UFO Turtle",
                 "FIRE Lv 4 — substitute for small fire utility"),
    LibraryEntry("insect_earth_lv2", "Man-Eater Bug",
                 "EARTH Lv 2 flip-effect insect"),
    LibraryEntry("fairy_light_lv4", "Dunames Dark Witch",
                 "LIGHT Lv 4 winged fairy — substitute for kami spirits"),
    LibraryEntry("reptile_earth_lv3", "Hyper Synchron",
                 "EARTH Lv 4 — substitute for serpent/reptile mid-tier"),

    # === Spell card art refs ===
    LibraryEntry("spell_normal", "Dark Hole",
                 "Normal Spell — destruction art"),
    LibraryEntry("spell_quickplay", "Mystical Space Typhoon",
                 "Quick-Play Spell — vortex art"),
    LibraryEntry("spell_continuous", "Black Garden",
                 "Continuous Spell — locale + flora art"),
    LibraryEntry("spell_equip", "Mage Power",
                 "Equip Spell — magical empowerment art"),
    LibraryEntry("spell_field", "Yami",
                 "Field Spell — DARK realm locale art"),
    LibraryEntry("spell_field_machine", "Geartown",
                 "Field Spell — machine-themed locale (Modified flavor)"),
    LibraryEntry("spell_ritual", "Black Luster Ritual",
                 "Ritual Spell — mystic-ceremony art"),

    # === Trap card art refs ===
    LibraryEntry("trap_normal", "Mirror Force",
                 "Normal Trap — reflective destruction art"),
    LibraryEntry("trap_normal_attacker", "Sakuretsu Armor",
                 "Normal Trap — attacker-counter art"),
    LibraryEntry("trap_continuous", "Skill Drain",
                 "Continuous Trap — power-negation art"),
    LibraryEntry("trap_counter", "Solemn Judgment",
                 "Counter Trap — divine-negation art"),

    # === Extra Deck (Synchro / Xyz / Fusion / Pendulum / Link) ===
    LibraryEntry("synchro_dragon_lv8", "Stardust Dragon",
                 "Synchro Lv 8 dragon — iconic"),
    LibraryEntry("synchro_warrior_lv5", "Junk Warrior",
                 "Synchro Lv 5 warrior"),
    LibraryEntry("xyz_warrior_rank4", "Number 39: Utopia",
                 "Xyz Rank 4 warrior — iconic"),
    LibraryEntry("fusion_dragon_high", "Blue-Eyes Ultimate Dragon",
                 "Fusion Lv 12 dragon — boss-tier"),
    LibraryEntry("link_warrior", "Decode Talker",
                 "Link 3 cyber warrior"),
    LibraryEntry("pendulum_dragon", "Odd-Eyes Pendulum Dragon",
                 "Pendulum Lv 7 dragon"),
]


# =============================================================================
# YGOProDeck API
# =============================================================================

API_BASE = "https://db.ygoprodeck.com/api/v7/cardinfo.php"


def fetch_card_info(card_name: str) -> dict | None:
    """Query YGOProDeck for a single card by exact name."""
    encoded = urllib.parse.quote(card_name)
    url = f"{API_BASE}?name={encoded}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hyperdraft/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            entries = data.get('data') or []
            return entries[0] if entries else None
    except (urllib.error.HTTPError, urllib.error.URLError,
            json.JSONDecodeError, KeyError) as exc:
        print(f"  WARN: lookup failed for '{card_name}': {exc}", file=sys.stderr)
        return None


def cropped_art_url(card_id: int) -> str:
    return f"https://images.ygoprodeck.com/images/cards_cropped/{card_id}.jpg"


def download_image(url: str, dest: Path) -> bool:
    """Download bytes from url to dest. Returns True on success."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Hyperdraft/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f"  WARN: download failed {url}: {exc}", file=sys.stderr)
        return False


# =============================================================================
# Driver
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='Print plan without fetching')
    parser.add_argument('--force', action='store_true',
                        help='Re-download even if file exists')
    parser.add_argument('--rate', type=float, default=0.15,
                        help='Sleep seconds between API calls (default 0.15)')
    args = parser.parse_args()

    REFS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Beyond Kamigawa style-reference fetcher")
    print(f"  Library size : {len(LIBRARY)}")
    print(f"  Output dir   : {REFS_DIR}")
    print(f"  Rate limit   : {args.rate}s between API calls")
    print()

    if args.dry_run:
        print("DRY RUN — listing planned fetches:")
        for entry in LIBRARY:
            print(f"  {entry.key:36s} <- {entry.ygo_name}")
        print(f"\n{len(LIBRARY)} entries.")
        return 0

    # Preserve metadata across runs: load existing manifest if present so
    # cached image files still report their race/attribute/level/atk/def.
    prior_meta: dict[str, dict] = {}
    if MANIFEST_PATH.exists() and not args.force:
        try:
            prior = json.loads(MANIFEST_PATH.read_text())
            for e in prior.get('entries', []):
                if e.get('key'):
                    prior_meta[e['key']] = e
        except (json.JSONDecodeError, OSError):
            pass

    successes: list[LibraryEntry] = []
    skipped = 0
    failed: list[str] = []

    for i, entry in enumerate(LIBRARY, 1):
        dest = REFS_DIR / f"{entry.key}.jpg"
        prefix = f"[{i:02d}/{len(LIBRARY):02d}] {entry.key:36s}"

        if dest.exists() and not args.force:
            print(f"{prefix} SKIP (cached)")
            skipped += 1
            entry.local_path = str(dest.relative_to(PROJECT_ROOT))
            # Restore metadata from prior manifest if available
            prev = prior_meta.get(entry.key)
            if prev:
                entry.card_id = prev.get('card_id')
                entry.attribute = prev.get('attribute')
                entry.type = prev.get('type')
                entry.race = prev.get('race')
                entry.level = prev.get('level')
                entry.atk = prev.get('atk')
                entry.def_val = prev.get('def_val')
                entry.art_url = prev.get('art_url')
            successes.append(entry)
            continue

        info = fetch_card_info(entry.ygo_name)
        if not info:
            print(f"{prefix} FAIL  (lookup miss for '{entry.ygo_name}')")
            failed.append(entry.key)
            continue

        entry.card_id = info.get('id')
        entry.attribute = info.get('attribute')
        entry.type = info.get('type')          # YGO "Type" — Effect Monster, Spell Card, etc.
        entry.race = info.get('race')          # YGO "Race" — Warrior, Dragon, etc.
        entry.level = info.get('level')
        entry.atk = info.get('atk')
        entry.def_val = info.get('def')

        if not entry.card_id:
            print(f"{prefix} FAIL  (no card_id in API response)")
            failed.append(entry.key)
            continue

        entry.art_url = cropped_art_url(entry.card_id)

        if download_image(entry.art_url, dest):
            entry.local_path = str(dest.relative_to(PROJECT_ROOT))
            successes.append(entry)
            print(f"{prefix} OK    id={entry.card_id} race={entry.race} attr={entry.attribute} lv={entry.level}")
        else:
            failed.append(entry.key)
            print(f"{prefix} FAIL  (download error)")

        time.sleep(args.rate)

    # Manifest
    manifest = {
        'version': 1,
        'fetched_at': _dt.datetime.utcnow().isoformat() + 'Z',
        'library_size': len(LIBRARY),
        'fetched': len(successes),
        'skipped_cached': skipped,
        'failed': failed,
        'entries': [asdict(e) for e in successes],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")

    print()
    print(f"Done. {len(successes)} fetched/cached, {len(failed)} failed.")
    print(f"Manifest: {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    if failed:
        print(f"Failed keys: {failed}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
