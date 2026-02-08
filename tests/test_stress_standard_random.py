#!/usr/bin/env python3
"""
Randomized Standard stress test (engine-only, no server).

Goal: exercise a broad slice of Standard card text/interceptors and ensure the
game loop doesn't crash or corrupt zone bookkeeping.

Usage:
  python tests/test_stress_standard_random.py --games 50
  python tests/test_stress_standard_random.py --games 200 --seed 123
  python tests/test_stress_standard_random.py --per-set 5
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from dataclasses import dataclass
from pathlib import Path
import re

sys.path.insert(0, ".")

from src.ai import AIEngine, BoardEvaluator
from src.cards import ALL_CARDS
from src.cards.set_registry import SETS, get_cards_in_set
from src.engine import (
    ActionType,
    AttackDeclaration,
    BlockDeclaration,
    CardType,
    Color,
    Game,
    PlayerAction,
    ZoneType,
)


_STANDARD_SET_CODES = [
    code for code, info in SETS.items()
    if info.set_type == "standard"
]


_BASIC_LANDS_BY_COLOR: dict[Color, str] = {
    Color.WHITE: "Plains",
    Color.BLUE: "Island",
    Color.BLACK: "Swamp",
    Color.RED: "Mountain",
    Color.GREEN: "Forest",
}


@dataclass(frozen=True)
class _BuiltDeck:
    set_code: str
    colors: tuple[Color, ...]
    cards: list  # list[CardDefinition]


def _pick_colors(rng: random.Random) -> tuple[Color, ...]:
    # Prefer mono/two-color decks for castability.
    all_colors = [Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN]
    if rng.random() < 0.65:
        return (rng.choice(all_colors),)
    a, b = rng.sample(all_colors, 2)
    return (a, b)

_CARD_LINE_RE = re.compile(r"^(?P<qty>\d+)\s+(?P<name>.+?)\s*$")

# Names of cards that appear in any downloaded netdeck decklist. When populated
# (via --exclude-netdeck-cards), the random deck builder will avoid these to
# bias towards "shitty" cards.
_EXCLUDED_NETDECK_NAMES: set[str] = set()


def _repo_root() -> Path:
    # tests/test_stress_standard_random.py -> tests -> repo root
    return Path(__file__).resolve().parents[1]


def _load_netdeck_card_names() -> set[str]:
    root = _repo_root() / "data" / "netdecks" / "mtggoldfish"
    if not root.exists():
        return set()

    names: set[str] = set()
    for path in sorted(root.glob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.lower().startswith("sideboard"):
                continue

            m = _CARD_LINE_RE.match(line)
            if not m:
                continue

            name = m.group("name").strip()
            # MTGGoldfish exports some multi-face cards as "Front // Back".
            if " // " in name:
                name = name.split(" // ", 1)[0].strip()
            elif "/" in name and "//" not in name:
                name = name.split("/", 1)[0].strip()

            if name:
                names.add(name)

    return names


def _build_random_deck_for_set(set_code: str, rng: random.Random) -> _BuiltDeck:
    colors = _pick_colors(rng)
    allowed = set(colors)

    set_cards = list(get_cards_in_set(set_code).values())
    nonlands = [
        c for c in set_cards
        if CardType.LAND not in c.characteristics.types
        and (c.characteristics.mana_cost or "").strip() != ""
        and (set(c.characteristics.colors or set()) <= allowed)
        and (c.name not in _EXCLUDED_NETDECK_NAMES)
    ]

    # Keep some colorless artifacts/etc. regardless of color identity.
    colorless = [
        c for c in set_cards
        if CardType.LAND not in c.characteristics.types
        and (c.characteristics.mana_cost or "").strip() != ""
        and not (c.characteristics.colors or set())
        and (c.name not in _EXCLUDED_NETDECK_NAMES)
    ]

    pool = list({id(c): c for c in (nonlands + colorless)}.values())
    if not pool:
        raise RuntimeError(f"No castable nonland cards for set {set_code} with colors {colors}")

    creatures = [c for c in pool if CardType.CREATURE in c.characteristics.types]
    others = [c for c in pool if CardType.CREATURE not in c.characteristics.types]

    rng.shuffle(creatures)
    rng.shuffle(others)

    spells: list = []
    # Aim for ~20 creatures if possible.
    spells.extend(creatures[: min(20, len(creatures))])
    remaining = 36 - len(spells)
    if remaining > 0:
        spells.extend(others[: min(remaining, len(others))])
    remaining = 36 - len(spells)
    if remaining > 0:
        spells.extend(pool[:remaining])

    # Lands: basics only (deterministic and low-risk).
    if len(colors) == 1:
        land_names = [_BASIC_LANDS_BY_COLOR[colors[0]]] * 24
    else:
        land_names = [_BASIC_LANDS_BY_COLOR[colors[0]]] * 12 + [_BASIC_LANDS_BY_COLOR[colors[1]]] * 12

    lands = [ALL_CARDS[name] for name in land_names]

    cards = lands + spells
    rng.shuffle(cards)
    return _BuiltDeck(set_code=set_code, colors=colors, cards=cards[:60])


def _check_zone_invariants(game: Game) -> None:
    """
    Basic bookkeeping checks:
    - no duplicates within zones
    - objects referenced by zones exist
    - object.zone matches membership for common zones
    """
    state = game.state

    # No duplicates within any zone list.
    for zone_key, zone in state.zones.items():
        ids = list(zone.objects)
        if len(ids) != len(set(ids)):
            raise AssertionError(f"Duplicate object IDs in zone {zone_key}")

    # Every zone member exists in state.objects.
    for zone_key, zone in state.zones.items():
        for obj_id in zone.objects:
            if obj_id not in state.objects:
                raise AssertionError(f"Zone {zone_key} references missing object {obj_id}")

    # Every object should appear in exactly one zone list.
    zone_membership_counts: dict[str, int] = {}
    for zone in state.zones.values():
        for obj_id in zone.objects:
            zone_membership_counts[obj_id] = zone_membership_counts.get(obj_id, 0) + 1

    for obj_id, obj in state.objects.items():
        count = zone_membership_counts.get(obj_id, 0)
        if count != 1:
            raise AssertionError(
                f"Object {obj.name} ({obj_id}) appears in {count} zones (expected exactly 1)"
            )

    # For every zone membership, obj.zone should match the zone's type.
    for zone_key, zone in state.zones.items():
        for obj_id in zone.objects:
            obj = state.objects[obj_id]
            if obj.zone != zone.type:
                raise AssertionError(
                    f"Object {obj.name} ({obj_id}) in {zone_key} but obj.zone={obj.zone} zone.type={zone.type}"
                )

    # Spot-check object.zone against expected zone types for common keyed zones.
    for pid in state.players.keys():
        for zone_type, zone_key in (
            (ZoneType.HAND, f"hand_{pid}"),
            (ZoneType.LIBRARY, f"library_{pid}"),
            (ZoneType.GRAVEYARD, f"graveyard_{pid}"),
        ):
            zone = state.zones.get(zone_key)
            if not zone:
                continue
            for obj_id in zone.objects:
                obj = state.objects[obj_id]
                if obj.zone != zone_type:
                    raise AssertionError(
                        f"Object {obj.name} ({obj_id}) in {zone_key} but obj.zone={obj.zone}"
                    )


async def _run_one_game(deck1: _BuiltDeck, deck2: _BuiltDeck, rng: random.Random, max_turns: int) -> None:
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    game.set_ai_player(p1.id)
    game.set_ai_player(p2.id)

    ai1 = AIEngine(difficulty="hard")
    ai2 = AIEngine(difficulty="hard")

    def _ai_action(player_id, state, legal_actions):
        pending = game.get_pending_choice()
        if pending and pending.player == player_id:
            ai = ai1 if player_id == p1.id else ai2
            selected = ai.make_choice(player_id, pending, state)
            ok, msg, _events = game.submit_choice(pending.id, player_id, selected)
            if not ok:
                # Fallback: minimum required selection (best-effort).
                fallback = list(pending.options[: pending.min_choices])
                game.submit_choice(pending.id, player_id, fallback)
            return PlayerAction(type=ActionType.PASS, player_id=player_id)

        ai = ai1 if player_id == p1.id else ai2
        return ai.get_action(player_id, state, legal_actions)

    def _attacks(player_id: str, legal_attackers: list[str]) -> list[AttackDeclaration]:
        # Use AI strategy when possible; fallback: all attackers.
        ai = ai1 if player_id == p1.id else ai2
        evaluator = BoardEvaluator(game.state)
        try:
            return ai.strategy.plan_attacks(game.state, player_id, evaluator, legal_attackers)
        except Exception:
            defender = p2.id if player_id == p1.id else p1.id
            return [AttackDeclaration(attacker_id=a, defending_player_id=defender) for a in legal_attackers]

    def _blocks(player_id: str, attackers: list[AttackDeclaration], legal_blockers: list[str]) -> list[BlockDeclaration]:
        ai = ai1 if player_id == p1.id else ai2
        evaluator = BoardEvaluator(game.state)
        try:
            return ai.strategy.plan_blocks(game.state, player_id, evaluator, attackers, legal_blockers)
        except Exception:
            blocks: list[BlockDeclaration] = []
            avail = list(legal_blockers)
            for atk in attackers:
                if not avail:
                    break
                blocks.append(BlockDeclaration(blocker_id=avail.pop(0), blocking_attacker_id=atk.attacker_id))
            return blocks

    game.set_ai_action_handler(_ai_action)
    game.set_attack_handler(_attacks)
    game.set_block_handler(_blocks)

    for card_def in deck1.cards:
        game.add_card_to_library(p1.id, card_def)
    game.shuffle_library(p1.id)

    for card_def in deck2.cards:
        game.add_card_to_library(p2.id, card_def)
    game.shuffle_library(p2.id)

    await game.start_game()
    _check_zone_invariants(game)

    turns = 0
    while not game.is_game_over() and turns < max_turns:
        turns += 1
        await game.turn_manager.run_turn()
        _check_zone_invariants(game)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Random Standard engine stress test")
    p.add_argument("--games", type=int, default=50, help="Number of games to run (default: 50)")
    p.add_argument("--per-set", type=int, default=0, help="If >0, run N games per Standard set code")
    p.add_argument("--seed", type=int, default=None, help="Random seed")
    p.add_argument("--turns", type=int, default=60, help="Max turns per game (default: 60)")
    p.add_argument(
        "--exclude-netdeck-cards",
        action="store_true",
        help="Exclude any card name that appears in downloaded MTGGoldfish netdecks (non-meta mode)",
    )
    args = p.parse_args(argv)

    seed = args.seed if args.seed is not None else random.randrange(1_000_000_000)
    rng = random.Random(seed)

    print(f"Seed: {seed}")
    print(f"Standard sets: {_STANDARD_SET_CODES}")

    global _EXCLUDED_NETDECK_NAMES
    if args.exclude_netdeck_cards:
        _EXCLUDED_NETDECK_NAMES = _load_netdeck_card_names()
        print(f"Excluding netdeck cards: {len(_EXCLUDED_NETDECK_NAMES)} names")

    try:
        if args.per_set and args.per_set > 0:
            for set_code in _STANDARD_SET_CODES:
                for i in range(args.per_set):
                    deck1 = _build_random_deck_for_set(set_code, rng)
                    deck2 = _build_random_deck_for_set(set_code, rng)
                    print(f"[{set_code}] game {i + 1}/{args.per_set} colors1={deck1.colors} colors2={deck2.colors}")
                    asyncio.run(_run_one_game(deck1, deck2, rng, args.turns))
            print("OK")
            return 0

        for i in range(args.games):
            set1 = rng.choice(_STANDARD_SET_CODES)
            set2 = rng.choice(_STANDARD_SET_CODES)
            deck1 = _build_random_deck_for_set(set1, rng)
            deck2 = _build_random_deck_for_set(set2, rng)
            print(f"game {i + 1}/{args.games} {set1}->{set2} colors1={deck1.colors} colors2={deck2.colors}")
            asyncio.run(_run_one_game(deck1, deck2, rng, args.turns))
        print("OK")
        return 0
    except Exception as e:
        print("FAILED")
        print(repr(e))
        raise


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
