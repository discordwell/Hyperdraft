"""
Per-card capability test for spice cards.

The Wave-22 R5 result showed a key methodology gap: the tournament's
generic deckbuilder filters out build-around mythics (5 of 8 PKH spice
cards never made the deck). Tournament winrate isn't a useful signal for
"is this build-around card good?" because the card never gets a deck
designed to support it.

This harness fixes that. For each focal card, it:
  1. Looks up the card's hand-curated synergy package (8-12 partner
     names from the same set, declared in `<set>_synergies.py`).
  2. Builds a 60-card synergy deck: 4 copies of focal + 2 copies of each
     partner + filler from the same set + a basic-land mana base.
  3. Runs N games of synergy deck vs a generic baseline deck (built via
     `build_set_deck` for a fair "untuned vs tuned" comparison).
  4. Reports per-focal-card metrics: cast rate, win-rate-when-in-play,
     capability score (= cast × winrate-when-in-play), and overall
     synergy-deck winrate.

A card "passes" if its capability score >= 0.30 (heuristic — cast at
least 30% of copies AND win the field at least 50% of the time when in
play). The threshold is tunable.

Usage (CLI):
    python scripts/play/capability_test.py --set PKH --card "Charizard, Mega Evolved" --games 10
    python scripts/play/capability_test.py --set PKH --all  # all spice in PKH

Programmatic:
    from scripts.play.capability_test import run_capability_test
    result = run_capability_test(
        focal_name="Charizard, Mega Evolved",
        synergy_partners=[...],
        set_cards=PKH_CARDS,
        games=10,
    )
"""

import argparse
import asyncio
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.engine.types import CardType, Color
from src.engine.mana import ManaCost
from src.ai import AIEngine
from src.cards.custom import CUSTOM_SETS

# Reuse the existing tournament harness primitives.
from scripts.play.custom_set_tournament import (
    play_one_game,
    build_set_deck,
    BASIC_LAND_BY_COLOR,
    primary_color,
    card_types,
    card_colors,
    get_cmc,
)


# ----------------------------------------------------------------------
# Synergy registry resolution
# ----------------------------------------------------------------------

def _load_synergy_registry(set_code: str) -> dict[str, list[str]]:
    """Import `src.cards.custom.<set>_synergies` and return its package map.

    Convention: each set's synergy registry lives at
    `src/cards/custom/<lowercase_set>_synergies.py` and exposes a single
    `<UPPER>_SYNERGY_PACKAGES: dict[str, list[str]]`.
    """
    set_to_module = {
        "PKH": ("pokemon_horizons_synergies", "PKH_SYNERGY_PACKAGES"),
    }
    if set_code not in set_to_module:
        raise ValueError(
            f"No synergy registry registered for set '{set_code}'. "
            f"Add an entry in capability_test._load_synergy_registry."
        )
    mod_name, attr_name = set_to_module[set_code]
    mod = importlib.import_module(f"src.cards.custom.{mod_name}")
    return getattr(mod, attr_name)


# ----------------------------------------------------------------------
# Synergy deck construction
# ----------------------------------------------------------------------

def build_synergy_deck(
    focal_name: str,
    synergy_partners: list[str],
    set_cards: dict,
    *,
    focal_copies: int = 4,
    partner_copies: int = 2,
    deck_size: int = 60,
    land_count: int = 24,
) -> list:
    """Build a 60-card synergy deck centered on `focal_name`.

    Returns a list[CardDefinition] (the same shape `play_one_game` accepts).
    Layout:
      - `focal_copies` of the focal card
      - `partner_copies` of each name in `synergy_partners` that exists
        in `set_cards` (silently skips missing partners — the test
        harness validates the registry separately)
      - filler from the same set, cheap creatures preferred, until
        `deck_size - land_count` spells
      - `land_count` basic lands of the deck's primary color
    """
    if focal_name not in set_cards:
        raise ValueError(f"Focal '{focal_name}' not in set_cards.")

    deck: list = []
    used_names: set[str] = set()

    # 1. Focal copies.
    deck.extend([set_cards[focal_name]] * focal_copies)
    used_names.add(focal_name)

    # 2. Synergy partners (skip missing).
    for name in synergy_partners:
        if name not in set_cards or name == focal_name:
            continue
        partner = set_cards[name]
        if CardType.LAND in card_types(partner):
            continue  # no double-counting lands; mana base added below
        copies = partner_copies
        # Non-creatures get one copy by default (matches build_set_deck).
        if CardType.CREATURE not in card_types(partner):
            copies = max(1, partner_copies // 2)
        deck.extend([partner] * copies)
        used_names.add(name)

    # 3. Filler — cheap mono-primary-color spells from the same set.
    target_spells = deck_size - land_count
    if len(deck) < target_spells:
        primary = primary_color(set_cards)
        candidates = []
        for name, cd in set_cards.items():
            if name in used_names or CardType.LAND in card_types(cd):
                continue
            cost = cd.characteristics.mana_cost or ""
            try:
                cc = ManaCost.parse(cost).colors
            except Exception:
                cc = set()
            if cc - {primary}:  # off-color
                continue
            candidates.append(cd)
        # Prefer cheap creatures (mirrors build_set_deck quality).
        candidates.sort(key=lambda c: (
            -1 if CardType.CREATURE in card_types(c) else 0,
            abs(get_cmc(c) - 3),
            c.name,
        ))
        copies_taken: dict[str, int] = {}
        for cd in candidates:
            if len(deck) >= target_spells:
                break
            taken = copies_taken.get(cd.name, 0)
            if taken >= 4:
                continue
            deck.append(cd)
            copies_taken[cd.name] = taken + 1
            used_names.add(cd.name)

    # If we still didn't fill (very small set), repeat.
    if len(deck) < target_spells and deck:
        i = 0
        guard = 0
        while len(deck) < target_spells and guard < 1000:
            cd = deck[i % len(deck)]
            if CardType.LAND not in card_types(cd):
                deck.append(cd)
            i += 1
            guard += 1

    # Truncate if we overshot (e.g., partner_copies=2 with many partners).
    if len(deck) > target_spells:
        deck = deck[:target_spells]

    # 4. Mana base.
    primary = primary_color(set_cards)
    target_subtype = {
        Color.WHITE: "Plains", Color.BLUE: "Island", Color.BLACK: "Swamp",
        Color.RED: "Mountain", Color.GREEN: "Forest",
    }.get(primary, "Mountain")
    set_basic = None
    for cd in set_cards.values():
        if CardType.LAND in card_types(cd) and target_subtype in (cd.characteristics.subtypes or set()):
            set_basic = cd
            break
    basic = set_basic or BASIC_LAND_BY_COLOR.get(primary)
    if basic:
        deck.extend([basic] * land_count)

    return deck[:deck_size]


# ----------------------------------------------------------------------
# Capability metrics
# ----------------------------------------------------------------------

def _focal_metrics(result, focal_name: str) -> dict:
    """Pull the focal card's stats from a single GameResult."""
    p1_label = result.p1_domain
    p2_label = result.p2_domain
    # Card stats are keyed "<label>::<card_name>".
    for ref, stats in (result.card_stats or {}).items():
        label, name = ref.split("::", 1)
        if name == focal_name and label == p1_label:
            return dict(stats)
    return {}


def _make_stack_focal_hook(focal_name: str, copies_to_stack: int = 1):
    """Return a `pre_start_hook` that moves up to `copies_to_stack` copies
    of the focal card from p1's library to the top, ensuring they're drawn
    in the opening hand.

    Reasoning: the synergy capability metric should answer "given the
    focal lands, does the deck win?" — not "does the focal happen to be
    drawn?". Stacking the opener removes draw-variance noise so the
    metric reflects card strength, not luck. Real MTG playtesting
    follows this convention (and any deck with tutors achieves it
    indirectly).
    """
    def hook(game, p1_id: str, p2_id: str) -> None:
        library = game.state.zones.get(f"library_{p1_id}")
        if not library or not library.objects:
            return
        # Find indices of focal copies in p1's library.
        focal_indices: list[int] = []
        for i, oid in enumerate(library.objects):
            obj = game.state.objects.get(oid)
            if not obj:
                continue
            if obj.name == focal_name:
                focal_indices.append(i)
                if len(focal_indices) >= copies_to_stack:
                    break
        # Move each found copy to the top, preserving relative order.
        # (top = position 0, drawn first.)
        for slot, src_idx in enumerate(focal_indices):
            # Re-find current index (it may shift after earlier swaps).
            current = library.objects.index(library.objects[src_idx]) if src_idx < len(library.objects) else None
            if current is None:
                continue
            library.objects.insert(slot, library.objects.pop(current))
    return hook


async def _run_one_game(
    deck1, deck2, label1, label2,
    *, max_turns: int = 14, per_turn_timeout_s: float = 4.0, wall_deadline_s: float = 25.0,
    focal_in_opener: Optional[str] = None,
):
    """One game; reuses `play_one_game` with safer-than-default timeouts.

    When `focal_in_opener` is set, p1's library is rearranged so a copy
    of that card is at the top — guaranteeing it's drawn in the opening
    hand. Used by the capability test to remove draw variance from the
    measurement.
    """
    ai1 = AIEngine(difficulty="hard")
    ai2 = AIEngine(difficulty="hard")
    hook = _make_stack_focal_hook(focal_in_opener) if focal_in_opener else None
    return await play_one_game(
        deck1, deck2, ai1, ai2, label1, label2,
        max_turns=max_turns,
        per_turn_timeout_s=per_turn_timeout_s,
        wall_deadline_s=wall_deadline_s,
        pre_start_hook=hook,
    )


def run_capability_test(
    focal_name: str,
    synergy_partners: list[str],
    set_cards: dict,
    set_code: str,
    *,
    games: int = 10,
    max_turns: int = 14,
    per_turn_timeout_s: float = 4.0,
    wall_deadline_s: float = 25.0,
    focal_in_opener: bool = True,
) -> dict:
    """Build a synergy deck around `focal_name` and play it vs a generic
    baseline of the same set. Returns aggregated capability metrics.
    """
    synergy_deck = build_synergy_deck(focal_name, synergy_partners, set_cards)
    baseline_deck, _ = build_set_deck(set_code, set_cards)

    # Sanity: the focal MUST be in the synergy deck.
    focal_count = sum(1 for c in synergy_deck if c.name == focal_name)
    if focal_count == 0:
        raise RuntimeError(f"Focal '{focal_name}' didn't make it into the synergy deck.")

    label_synergy = f"{set_code}_SYN"
    label_base = f"{set_code}_BASE"

    started = time.perf_counter()
    wins = 0
    losses = 0
    draws = 0
    errors = 0
    cast_total = 0
    deck_copies_total = 0
    in_play_total = 0
    on_winning_total = 0
    dmg_total = 0
    kills_total = 0

    for g in range(games):
        try:
            result = asyncio.run(_run_one_game(
                synergy_deck, baseline_deck, label_synergy, label_base,
                max_turns=max_turns,
                per_turn_timeout_s=per_turn_timeout_s,
                wall_deadline_s=wall_deadline_s,
                focal_in_opener=focal_name if focal_in_opener else None,
            ))
        except Exception as exc:
            errors += 1
            print(f"  game {g}: ERROR {type(exc).__name__}: {str(exc)[:80]}", flush=True)
            continue

        if result.error:
            errors += 1
            print(f"  game {g}: ERROR {result.error[:60]}", flush=True)
            continue

        if result.winner_domain == label_synergy:
            wins += 1
        elif result.winner_domain == label_base:
            losses += 1
        else:
            draws += 1

        m = _focal_metrics(result, focal_name)
        cast_total += int(m.get("cast", 0))
        deck_copies_total += int(m.get("deck_copies", 0))
        in_play_total += int(m.get("in_play_at_end", 0))
        on_winning_total += int(m.get("on_winning_side", 0))
        dmg_total += int(m.get("dmg_dealt", 0))
        kills_total += int(m.get("kills", 0))

    elapsed = time.perf_counter() - started
    completed = wins + losses + draws
    win_rate = (wins / completed) if completed else 0.0
    cast_per_copy = (cast_total / deck_copies_total) if deck_copies_total else 0.0
    cast_per_game = (cast_total / completed) if completed else 0.0
    win_rate_in_play = (on_winning_total / in_play_total) if in_play_total else 0.0
    # Capability score = cast_per_game × win-correlation. For permanents
    # (creatures, artifacts, enchantments, equipment) the win-correlation
    # is win-rate-when-in-play (WR-IP) — they're on the board at game
    # end. For one-shot spells (instants, sorceries) WR-IP is always 0
    # because the spell goes to graveyard after resolving; the natural
    # win-correlation there is the synergy deck's overall winrate.
    # Detect via the focal card's types.
    focal_def = set_cards.get(focal_name)
    is_permanent = True
    if focal_def is not None:
        types = focal_def.characteristics.types or set()
        if (CardType.SORCERY in types or CardType.INSTANT in types) and CardType.CREATURE not in types:
            is_permanent = False
    win_correlation = win_rate_in_play if is_permanent else win_rate
    capability_score = cast_per_game * win_correlation

    return {
        "focal": focal_name,
        "set": set_code,
        "games_run": games,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "errors": errors,
        "synergy_deck_winrate": round(win_rate, 3),
        "focal_cast_per_copy": round(cast_per_copy, 3),
        "focal_cast_per_game": round(cast_per_game, 3),
        "focal_win_rate_in_play": round(win_rate_in_play, 3),
        "focal_is_permanent": is_permanent,
        "capability_score": round(capability_score, 3),
        "focal_dmg_per_game": round(dmg_total / max(completed, 1), 1),
        "focal_kills_per_game": round(kills_total / max(completed, 1), 2),
        "passed_threshold": capability_score >= 0.30,
        "elapsed_s": round(elapsed, 1),
        "synergy_partners_used": [p for p in synergy_partners if p in set_cards],
        "synergy_partners_missing": [p for p in synergy_partners if p not in set_cards],
    }


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def _print_report(report: dict) -> None:
    p = report
    bar = "PASS" if p["passed_threshold"] else "FAIL"
    print(f"\n{'='*60}")
    print(f"  Capability test: {p['focal']}  [{p['set']}]   {bar}")
    print(f"{'='*60}")
    print(f"  Games: {p['games_run']}  W/L/D/Err: {p['wins']}/{p['losses']}/{p['draws']}/{p['errors']}")
    print(f"  Synergy-deck winrate:  {p['synergy_deck_winrate']*100:5.1f}%")
    print(f"  Focal cast/game:       {p['focal_cast_per_game']:.2f}")
    print(f"  Focal cast/copy:       {p['focal_cast_per_copy']:.2f}")
    print(f"  Focal WR-in-play:      {p['focal_win_rate_in_play']*100:5.1f}%")
    print(f"  Capability score:      {p['capability_score']:.2f}  "
          f"(threshold 0.30 → {'PASS' if p['passed_threshold'] else 'FAIL'})")
    print(f"  Focal damage/game:     {p['focal_dmg_per_game']:.1f}")
    print(f"  Focal kills/game:      {p['focal_kills_per_game']:.2f}")
    if p["synergy_partners_missing"]:
        print(f"  ⚠ Missing partners: {p['synergy_partners_missing']}")
    print(f"  Elapsed: {p['elapsed_s']:.0f}s")


def main():
    parser = argparse.ArgumentParser(description="Per-card capability test for spice cards.")
    parser.add_argument("--set", required=True, choices=list(CUSTOM_SETS.keys()),
                        help="custom set code (e.g. PKH)")
    parser.add_argument("--card", default=None,
                        help="focal card name; omit with --all to test every "
                             "card in the synergy registry")
    parser.add_argument("--all", action="store_true",
                        help="run capability test for every card in the synergy registry")
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--max-turns", type=int, default=14)
    parser.add_argument("--per-turn-timeout", type=float, default=4.0)
    parser.add_argument("--wall-deadline", type=float, default=25.0)
    parser.add_argument("--out", type=str, default=None,
                        help="optional JSON output path")
    parser.add_argument("--no-focal-in-opener", action="store_true",
                        help="DISABLE focal-card opening-hand stacking. Default "
                             "is to stack so cast/copy isolates 'card carries "
                             "deck' from 'card was drawn'.")
    args = parser.parse_args()

    if not args.card and not args.all:
        parser.error("specify --card or --all")
    if args.card and args.all:
        parser.error("specify only one of --card or --all")

    set_cards = CUSTOM_SETS[args.set]
    registry = _load_synergy_registry(args.set)

    targets = list(registry.keys()) if args.all else [args.card]
    if args.card and args.card not in registry:
        parser.error(f"Card '{args.card}' has no synergy package in {args.set} registry. "
                     f"Available: {list(registry.keys())}")

    reports = []
    for focal in targets:
        partners = registry[focal]
        rep = run_capability_test(
            focal_name=focal,
            synergy_partners=partners,
            set_cards=set_cards,
            set_code=args.set,
            games=args.games,
            max_turns=args.max_turns,
            per_turn_timeout_s=args.per_turn_timeout,
            wall_deadline_s=args.wall_deadline,
            focal_in_opener=not args.no_focal_in_opener,
        )
        _print_report(rep)
        reports.append(rep)

    # Summary if --all.
    if args.all:
        print(f"\n{'='*60}")
        print(f"  Summary: {args.set}  ({len(reports)} cards)")
        print(f"{'='*60}")
        print(f"  {'Card':<35} {'Score':>6} {'Win%':>6} {'Cast/g':>6} {'WR-IP':>6}  Status")
        for r in sorted(reports, key=lambda r: -r["capability_score"]):
            status = "PASS" if r["passed_threshold"] else "FAIL"
            print(f"  {r['focal']:<35} {r['capability_score']:>6.2f} "
                  f"{r['synergy_deck_winrate']*100:>5.1f}% {r['focal_cast_per_game']:>6.2f} "
                  f"{r['focal_win_rate_in_play']*100:>5.1f}%  {status}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(reports, f, indent=2)
        print(f"\nReports written to {args.out}")


if __name__ == "__main__":
    main()
