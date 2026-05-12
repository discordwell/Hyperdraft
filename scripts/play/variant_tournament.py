"""
Variant tournament harness — discover a format's meta by running named
AI variants in a round-robin against each other.

Use this when porting the spice-pass methodology to a new engine:
before trusting capability scores, run a variant tournament to find
out what playing the format actually rewards. Then tune the AI to
lean into the winning variant, THEN run capability tests.

Usage:
    # Minecraft
    python scripts/play/variant_tournament.py --engine minecraft \
        --variants balanced,aggro,ramp,explore,workers,random,largest \
        --decks builder,miner,raider --games 6 \
        --out logs/mc_variants.json

    # MTG (uses existing aggro/control/midrange/ultra strategies)
    python scripts/play/variant_tournament.py --engine mtg \
        --variants aggro,control,midrange,ultra \
        --decks MONO_RED_AGGRO,MONO_BLUE_CONTROL,MONO_GREEN_RAMP \
        --games 6 --out logs/mtg_variants.json

    # Pokemon TCG (local two-pilot substitute for LLM-vs-LLM)
    python scripts/play/variant_tournament.py --engine pokemon \
        --variants medium,hard,ultra \
        --decks izzet,rakdos,gruul,orzhov \
        --games 4 --out logs/pokemon_variants.json

    # Hearthstone custom-set pilots
    python scripts/play/variant_tournament.py --engine hearthstone \
        --variants aggro,control,midrange,ultra,random \
        --decks stormrift_pyromancer,stormrift_cryomancer \
        --games 2 --max-turns 30 --out logs/hs_variants.json

    # Yu-Gi-Oh! local two-pilot substitute for LLM-vs-LLM
    python scripts/play/variant_tournament.py --engine yugioh \
        --variants balanced,deck_strategy,aggro,control,burn,random \
        --decks goat_control,chain_burn,kamigawa:samurai,kamigawa:ninja \
        --games 2 --max-turns 40 --out logs/ygo_variants.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Engine dispatch
# ---------------------------------------------------------------------------


@dataclass
class GameOutcome:
    p1_variant: str
    p2_variant: str
    p1_deck_label: str
    p2_deck_label: str
    winner_variant: Optional[str]  # "p1_variant" or "p2_variant" or None
    turns: int
    duration_s: float
    error: Optional[str] = None
    winner_reason: Optional[str] = None
    p1_prizes_remaining: Optional[int] = None
    p2_prizes_remaining: Optional[int] = None


# Engine adapters: (deck_resolver, variant_runner, default_decks, default_variants)
# Each engine plugs in its game runner and variant universe.

def _mc_decks(deck_names: list[str]) -> dict[str, list]:
    from src.cards.minecraft import MINECRAFT_STARTER_DECKS
    out = {}
    for name in deck_names:
        factory = MINECRAFT_STARTER_DECKS.get(name)
        if not factory:
            raise ValueError(f"Unknown MC deck: {name!r}. "
                             f"Available: {list(MINECRAFT_STARTER_DECKS.keys())}")
        out[name] = factory()
    return out


async def _mc_run_one(
    deck1: list, deck2: list,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
    custom_presets: Optional[dict[str, dict]] = None,
) -> GameOutcome:
    """Custom presets override built-in MC_BIAS_PRESETS by name. The
    bias is passed as a dict (not a string) so MinecraftAIAdapter
    skips the registry lookup. Built-in names fall through as strings
    and resolve via the adapter's normal preset lookup."""
    from scripts.play.minecraft_capability_test import play_one_minecraft_game
    custom_presets = custom_presets or {}
    bias_p1 = custom_presets.get(p1_variant, p1_variant)
    bias_p2 = custom_presets.get(p2_variant, p2_variant)
    start = time.perf_counter()
    r = await play_one_minecraft_game(
        deck1, deck2, p1_label=p1_variant, p2_label=p2_variant,
        bias_p1=bias_p1, bias_p2=bias_p2,
        max_turns=max_turns,
    )
    return GameOutcome(
        p1_variant=p1_variant,
        p2_variant=p2_variant,
        p1_deck_label=p1_label,
        p2_deck_label=p2_label,
        winner_variant=r.winner_label,
        turns=r.turns,
        duration_s=r.duration_s,
        error=r.error,
    )


def _mtg_decks(deck_names: list[str]) -> dict[str, list]:
    from src.decks import standard_decks as sd
    from src.decks.deck import load_deck
    from src.cards import ALL_CARDS
    out = {}
    for name in deck_names:
        deck_obj = getattr(sd, name, None)
        if deck_obj is None:
            available = [n for n in dir(sd) if not n.startswith("_") and n.isupper()]
            raise ValueError(f"Unknown MTG deck: {name!r}. Available: {available[:10]}...")
        out[name] = load_deck(ALL_CARDS, deck_obj)
    return out


async def _mtg_run_one(
    deck1: list, deck2: list,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from scripts.play.custom_set_tournament import play_one_game, make_ai
    ai1 = make_ai(p1_variant)
    ai2 = make_ai(p2_variant)
    start = time.perf_counter()
    r = await play_one_game(
        deck1, deck2, ai1, ai2,
        p1_label=p1_variant, p2_label=p2_variant,
        max_turns=max_turns,
    )
    return GameOutcome(
        p1_variant=p1_variant,
        p2_variant=p2_variant,
        p1_deck_label=p1_label,
        p2_deck_label=p2_label,
        winner_variant=r.winner_domain,
        turns=r.turns,
        duration_s=r.duration_s,
        error=r.error,
    )


def _pkm_decks(deck_names: list[str]) -> dict[str, list]:
    from src.cards.pokemon.deck_builder import (
        build_sv_starter_deck,
        list_sv_starter_decks,
    )
    from src.cards.pokemon.beyond.ravnica.deck_builder import (
        build_ravnica_guild_deck,
        list_ravnica_guild_decks,
    )

    svs = set(list_sv_starter_decks())
    guilds = set(list_ravnica_guild_decks())
    out = {}
    for raw_name in deck_names:
        name = raw_name.strip().lower()
        if name.startswith("svs:"):
            starter = name.split(":", 1)[1]
            if starter not in svs:
                raise ValueError(f"Unknown Pokemon SVS deck: {raw_name!r}. Available: {sorted(svs)}")
            deck, _strategy = build_sv_starter_deck(starter, enforce_quality=False)
            out[raw_name] = deck
        elif name.startswith("brv:"):
            guild = name.split(":", 1)[1]
            if guild not in guilds:
                raise ValueError(f"Unknown Pokemon BRV guild: {raw_name!r}. Available: {sorted(guilds)}")
            deck, _strategy = build_ravnica_guild_deck(guild, enforce_balance=False)
            out[raw_name] = deck
        elif name in svs:
            deck, _strategy = build_sv_starter_deck(name, enforce_quality=False)
            out[raw_name] = deck
        elif name in guilds:
            deck, _strategy = build_ravnica_guild_deck(name, enforce_balance=False)
            out[raw_name] = deck
        else:
            available = sorted([f"svs:{n}" for n in svs] + [f"brv:{g}" for g in guilds])
            raise ValueError(f"Unknown Pokemon deck: {raw_name!r}. Available: {available}")
    return out


_PKM_VARIANT_TO_DIFFICULTY = {
    "easy": "easy",
    "random": "easy",
    "medium": "medium",
    "balanced": "medium",
    "hard": "hard",
    "ultra": "ultra",
    "optimized": "ultra",
}


def _pkm_difficulty(variant: str) -> str:
    try:
        return _PKM_VARIANT_TO_DIFFICULTY[variant]
    except KeyError as exc:
        available = ", ".join(sorted(_PKM_VARIANT_TO_DIFFICULTY))
        raise ValueError(f"Unknown Pokemon variant {variant!r}. Available: {available}") from exc


def _pkm_loss_reason(game, player) -> str:
    if getattr(player, "prizes_remaining", 6) == 0:
        return "prizes"
    if not getattr(player, "has_lost", False):
        return "not_lost"
    lib_key = f"library_{player.id}"
    active_key = f"active_spot_{player.id}"
    bench_key = f"bench_{player.id}"
    library = game.state.zones.get(lib_key)
    active = game.state.zones.get(active_key)
    bench = game.state.zones.get(bench_key)
    if library is not None and not library.objects:
        return "deck_out"
    if (active is None or not active.objects) and (bench is None or not bench.objects):
        return "no_pokemon"
    return "unknown_loss"


async def _pkm_run_one(
    deck1: list, deck2: list,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from src.ai.pokemon_adapter import PokemonAIAdapter
    from src.engine.game import Game

    start = time.perf_counter()
    game = Game(mode="pokemon")
    p1 = game.add_player(f"{p1_label}:{p1_variant}")
    p2 = game.add_player(f"{p2_label}:{p2_variant}")
    game.setup_pokemon_player(p1, deck1)
    game.setup_pokemon_player(p2, deck2)

    ai = PokemonAIAdapter(difficulty="medium")
    ai.player_difficulties[p1.id] = _pkm_difficulty(p1_variant)
    ai.player_difficulties[p2.id] = _pkm_difficulty(p2_variant)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    await game.turn_manager.setup_game()
    turns = 0
    for _ in range(max_turns):
        if game.is_game_over():
            break
        await game.turn_manager.run_turn()
        turns += 1

    # Calling is_game_over refreshes Pokemon win-condition side effects.
    game_over = game.is_game_over()
    winner_variant: Optional[str] = None
    winner_reason: Optional[str] = None
    if game_over:
        if getattr(p1, "has_lost", False) and not getattr(p2, "has_lost", False):
            winner_variant = p2_variant
            winner_reason = "prizes" if p2.prizes_remaining == 0 else _pkm_loss_reason(game, p1)
        elif getattr(p2, "has_lost", False) and not getattr(p1, "has_lost", False):
            winner_variant = p1_variant
            winner_reason = "prizes" if p1.prizes_remaining == 0 else _pkm_loss_reason(game, p2)
        elif p1.prizes_remaining == 0 and p2.prizes_remaining != 0:
            winner_variant = p1_variant
            winner_reason = "prizes"
        elif p2.prizes_remaining == 0 and p1.prizes_remaining != 0:
            winner_variant = p2_variant
            winner_reason = "prizes"
        else:
            winner_reason = "draw"
    else:
        winner_reason = "max_turns"

    return GameOutcome(
        p1_variant=p1_variant,
        p2_variant=p2_variant,
        p1_deck_label=p1_label,
        p2_deck_label=p2_label,
        winner_variant=winner_variant,
        turns=turns,
        duration_s=time.perf_counter() - start,
        winner_reason=winner_reason,
        p1_prizes_remaining=p1.prizes_remaining,
        p2_prizes_remaining=p2.prizes_remaining,
    )


def _hs_deck_specs() -> dict[str, dict]:
    from src.cards.hearthstone.decks import HEARTHSTONE_DECKS
    from src.cards.hearthstone.heroes import HEROES
    from src.cards.hearthstone.hero_powers import HERO_POWERS
    from src.cards.hearthstone.stormrift import (
        STORMRIFT_DECKS,
        STORMRIFT_HEROES,
        STORMRIFT_HERO_POWERS,
        install_stormrift_modifiers,
    )
    from src.cards.hearthstone.frierenrift import (
        FRIERENRIFT_DECKS,
        FRIERENRIFT_HEROES,
        FRIERENRIFT_HERO_POWERS,
        install_frierenrift_modifiers,
    )
    from src.cards.hearthstone.riftclash import (
        RIFTCLASH_DECKS,
        RIFTCLASH_HEROES,
        RIFTCLASH_HERO_POWERS,
        install_riftclash_modifiers,
    )

    specs: dict[str, dict] = {}
    for hero_class, deck in HEARTHSTONE_DECKS.items():
        specs[hero_class.lower()] = {
            "label": hero_class,
            "deck": deck,
            "hero": HEROES[hero_class],
            "hero_power": HERO_POWERS[hero_class],
            "modifier": None,
        }

    specs.update({
        "stormrift_pyromancer": {
            "label": "Stormrift Pyromancer",
            "deck": STORMRIFT_DECKS["Pyromancer"],
            "hero": STORMRIFT_HEROES["Pyromancer"],
            "hero_power": STORMRIFT_HERO_POWERS["Pyromancer"],
            "modifier": install_stormrift_modifiers,
        },
        "stormrift_cryomancer": {
            "label": "Stormrift Cryomancer",
            "deck": STORMRIFT_DECKS["Cryomancer"],
            "hero": STORMRIFT_HEROES["Cryomancer"],
            "hero_power": STORMRIFT_HERO_POWERS["Cryomancer"],
            "modifier": install_stormrift_modifiers,
        },
        "frieren": {
            "label": "Frierenrift Frieren",
            "deck": FRIERENRIFT_DECKS["Frieren"],
            "hero": FRIERENRIFT_HEROES["Frieren"],
            "hero_power": FRIERENRIFT_HERO_POWERS["Frieren"],
            "modifier": install_frierenrift_modifiers,
        },
        "macht": {
            "label": "Frierenrift Macht",
            "deck": FRIERENRIFT_DECKS["Macht"],
            "hero": FRIERENRIFT_HEROES["Macht"],
            "hero_power": FRIERENRIFT_HERO_POWERS["Macht"],
            "modifier": install_frierenrift_modifiers,
        },
        "riftclash_pyromancer": {
            "label": "Riftclash Pyromancer",
            "deck": RIFTCLASH_DECKS["Pyromancer"],
            "hero": RIFTCLASH_HEROES["Pyromancer"],
            "hero_power": RIFTCLASH_HERO_POWERS["Pyromancer"],
            "modifier": install_riftclash_modifiers,
        },
        "riftclash_cryomancer": {
            "label": "Riftclash Cryomancer",
            "deck": RIFTCLASH_DECKS["Cryomancer"],
            "hero": RIFTCLASH_HEROES["Cryomancer"],
            "hero_power": RIFTCLASH_HERO_POWERS["Cryomancer"],
            "modifier": install_riftclash_modifiers,
        },
    })
    return specs


def _hs_decks(deck_names: list[str]) -> dict[str, dict]:
    specs = _hs_deck_specs()
    aliases = {
        "stormrift_pyro": "stormrift_pyromancer",
        "stormrift_cryo": "stormrift_cryomancer",
        "frierenrift_frieren": "frieren",
        "frierenrift_macht": "macht",
        "riftclash_pyro": "riftclash_pyromancer",
        "riftclash_cryo": "riftclash_cryomancer",
    }
    out = {}
    for raw_name in deck_names:
        name = raw_name.strip().lower()
        key = aliases.get(name, name)
        spec = specs.get(key)
        if not spec:
            available = ", ".join(sorted(specs))
            raise ValueError(f"Unknown Hearthstone deck: {raw_name!r}. Available: {available}")
        out[raw_name] = spec
    return out


def _hs_variant_config(variant: str) -> tuple[str, Optional[str]]:
    name = variant.lower()
    if name in {"aggro", "control", "midrange"}:
        return "hard", name
    if name in {"ultra", "llm_guided", "llm-guided"}:
        return "ultra", None
    if name == "random":
        return "random", None
    if name == "easy":
        return "easy", None
    if name in {"medium", "hard"}:
        return name, None
    raise ValueError(
        f"Unknown Hearthstone variant {variant!r}. "
        "Use aggro, control, midrange, ultra, random, medium, or hard."
    )


async def _hs_run_one(
    deck1: dict, deck2: dict,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter
    from src.engine.game import Game
    from src.engine.types import CardType

    started = time.perf_counter()
    try:
        game = Game(mode="hearthstone")
        p1 = game.add_player(f"P1_{p1_label}_{p1_variant}", life=30)
        p2 = game.add_player(f"P2_{p2_label}_{p2_variant}", life=30)

        game.setup_hearthstone_player(p1, deck1["hero"], deck1["hero_power"])
        game.setup_hearthstone_player(p2, deck2["hero"], deck2["hero_power"])

        modifiers = []
        for modifier in (deck1.get("modifier"), deck2.get("modifier")):
            if modifier and modifier not in modifiers:
                modifiers.append(modifier)
        for modifier in modifiers:
            modifier(game)

        for card_def in deck1["deck"]:
            game.add_card_to_library(p1.id, card_def)
        for card_def in deck2["deck"]:
            game.add_card_to_library(p2.id, card_def)

        game.shuffle_library(p1.id)
        game.shuffle_library(p2.id)

        p1_difficulty, p1_archetype = _hs_variant_config(p1_variant)
        p2_difficulty, p2_archetype = _hs_variant_config(p2_variant)
        adapter = HearthstoneAIAdapter(difficulty="hard")
        adapter.player_difficulties[p1.id] = p1_difficulty
        adapter.player_difficulties[p2.id] = p2_difficulty
        if p1_archetype:
            adapter.set_player_archetype(p1.id, p1_archetype)
        if p2_archetype:
            adapter.set_player_archetype(p2.id, p2_archetype)

        game.turn_manager.hearthstone_ai_handler = adapter
        game.turn_manager.ai_players = {p1.id, p2.id}
        game.get_mulligan_decision = lambda pid, hand, count: True

        await game.start_game()
        if not game.state.active_player:
            game.state.active_player = p1.id

        turns = 0
        while turns < max_turns:
            turns += 1
            if game.is_game_over() or p1.life <= 0 or p2.life <= 0:
                break
            await game.turn_manager.run_turn()

            battlefield = game.state.zones.get("battlefield")
            if battlefield:
                for pid in (p1.id, p2.id):
                    minions = sum(
                        1 for oid in battlefield.objects
                        if oid in game.state.objects
                        and game.state.objects[oid].controller == pid
                        and CardType.MINION in game.state.objects[oid].characteristics.types
                    )
                    if minions > 7:
                        raise RuntimeError(f"player {pid} has {minions} minions")

        winner_variant = None
        winner_reason = "max_turns"
        if (p1.has_lost or p1.life <= 0) and not (p2.has_lost or p2.life <= 0):
            winner_variant = p2_variant
            winner_reason = "lethal"
        elif (p2.has_lost or p2.life <= 0) and not (p1.has_lost or p1.life <= 0):
            winner_variant = p1_variant
            winner_reason = "lethal"
        elif turns >= max_turns:
            p1_effective = p1.life + p1.armor
            p2_effective = p2.life + p2.armor
            if p1_effective > p2_effective:
                winner_variant = p1_variant
                winner_reason = "life_total_timeout"
            elif p2_effective > p1_effective:
                winner_variant = p2_variant
                winner_reason = "life_total_timeout"
            else:
                winner_reason = "draw"

        return GameOutcome(
            p1_variant=p1_variant,
            p2_variant=p2_variant,
            p1_deck_label=p1_label,
            p2_deck_label=p2_label,
            winner_variant=winner_variant,
            turns=turns,
            duration_s=time.perf_counter() - started,
            winner_reason=winner_reason,
        )
    except Exception as exc:
        return GameOutcome(
            p1_variant=p1_variant,
            p2_variant=p2_variant,
            p1_deck_label=p1_label,
            p2_deck_label=p2_label,
            winner_variant=None,
            turns=0,
            duration_s=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )


def _ygo_copy_strategy(strategy: Optional[dict]) -> Optional[dict]:
    if not strategy:
        return None
    out = dict(strategy)
    for key in ("priorities", "summon_priority", "set_priority"):
        if key in out:
            out[key] = list(out[key])
    return out


def _ygo_decks(deck_names: list[str]) -> dict[str, dict]:
    from src.cards.yugioh.ygo_starter import (
        WARRIOR_DECK, WARRIOR_EXTRA_DECK,
        SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK,
    )
    from src.cards.yugioh.ygo_classic import (
        YUGI_DECK, YUGI_EXTRA_DECK,
        KAIBA_DECK, KAIBA_EXTRA_DECK,
    )
    from src.cards.yugioh.deck_builder import build_ygo_optimized_deck, list_ygo_optimized_decks
    from src.cards.yugioh.beyond.kamigawa import (
        build_kamigawa_deck,
        kamigawa_strategy,
        list_kamigawa_archetypes,
    )

    fixed = {
        "starter:warrior": (WARRIOR_DECK, WARRIOR_EXTRA_DECK, None),
        "starter:spellcaster": (SPELLCASTER_DECK, SPELLCASTER_EXTRA_DECK, None),
        "classic:yugi": (YUGI_DECK, YUGI_EXTRA_DECK, None),
        "classic:kaiba": (KAIBA_DECK, KAIBA_EXTRA_DECK, None),
    }
    optimized = set(list_ygo_optimized_decks())
    kamigawa = set(list_kamigawa_archetypes())

    out = {}
    for raw_name in deck_names:
        name = raw_name.strip()
        key = name.lower()
        if key in fixed:
            main, extra, strategy = fixed[key]
            out[name] = {
                "main": list(main),
                "extra": list(extra),
                "strategy": _ygo_copy_strategy(strategy),
            }
            continue

        if name in optimized:
            main, extra, strategy = build_ygo_optimized_deck(name)
            out[name] = {"main": main, "extra": extra, "strategy": _ygo_copy_strategy(strategy)}
            continue

        archetype = name.split(":", 1)[1] if name.startswith("kamigawa:") else name
        if archetype in kamigawa:
            main, extra = build_kamigawa_deck(archetype)
            out[name] = {
                "main": main,
                "extra": extra,
                "strategy": kamigawa_strategy(archetype),
            }
            continue

        available = (
            sorted(fixed)
            + sorted(optimized)
            + [f"kamigawa:{archetype}" for archetype in sorted(kamigawa)]
        )
        raise ValueError(f"Unknown Yu-Gi-Oh! deck: {raw_name!r}. Available: {', '.join(available)}")
    return out


YGO_GENERIC_STRATEGIES: dict[str, dict] = {
    "aggro": {
        "name": "YGO Aggro Pilot",
        "archetype": "Beatdown / Aggro",
        "summon_priority": [],
        "set_priority": [],
    },
    "control": {
        "name": "YGO Control Pilot",
        "archetype": "Control",
        "summon_priority": [],
        "set_priority": [],
    },
    "burn": {
        "name": "YGO Burn Pilot",
        "archetype": "Burn / Stall",
        "summon_priority": [],
        "set_priority": ["Stealth Bird", "Des Koala", "Marshmallon", "Giant Germ"],
    },
}


def _ygo_variant_adapter(variant: str, deck_strategy: Optional[dict]):
    from src.ai.yugioh_adapter import YugiohAIAdapter

    name = variant.strip().lower()
    if name in {"random", "easy"}:
        ai = YugiohAIAdapter(difficulty="easy")
    elif name in {"balanced", "medium"}:
        ai = YugiohAIAdapter(difficulty="medium")
    elif name in {"hard"}:
        ai = YugiohAIAdapter(difficulty="hard")
    elif name in {"deck_strategy", "strategy", "llm_guided", "llm-guided"}:
        ai = YugiohAIAdapter(difficulty="hard")
        ai.strategy = _ygo_copy_strategy(deck_strategy)
    elif name in {"ultra", "ultra_strategy"}:
        ai = YugiohAIAdapter(difficulty="ultra")
        ai.strategy = _ygo_copy_strategy(deck_strategy)
    elif name in YGO_GENERIC_STRATEGIES:
        ai = YugiohAIAdapter(difficulty="hard")
        ai.strategy = _ygo_copy_strategy(YGO_GENERIC_STRATEGIES[name])
    else:
        raise ValueError(
            f"Unknown Yu-Gi-Oh! variant {variant!r}. "
            "Use balanced, deck_strategy, aggro, control, burn, ultra, random, easy, medium, or hard."
        )
    return ai


class _YGODispatchAdapter:
    def __init__(self, adapters: dict[str, Any]):
        self.adapters = adapters

    def _adapter(self, player_id: str):
        return self.adapters[player_id]

    def get_main_phase_action(self, player_id: str, state: Any, turn_state: Any) -> dict:
        return self._adapter(player_id).get_main_phase_action(player_id, state, turn_state)

    def get_battle_action(self, player_id: str, state: Any, turn_state: Any) -> dict:
        return self._adapter(player_id).get_battle_action(player_id, state, turn_state)

    def should_enter_battle(self, player_id: str, state: Any) -> bool:
        return self._adapter(player_id).should_enter_battle(player_id, state)


def _ygo_board_score(game: Any, player_id: str) -> int:
    zone = game.state.zones.get(f"monster_zone_{player_id}")
    if not zone:
        return 0
    score = 0
    for oid in zone.objects:
        obj = game.state.objects.get(oid) if oid else None
        if not obj or not obj.card_def:
            continue
        atk = getattr(obj.card_def, "atk", 0) or 0
        defense = getattr(obj.card_def, "def_val", 0) or 0
        score += max(atk, defense) // 100
    return score


async def _ygo_run_one(
    deck1: dict, deck2: dict,
    p1_variant: str, p2_variant: str,
    p1_label: str, p2_label: str,
    max_turns: int,
) -> GameOutcome:
    from src.engine.game import Game

    started = time.perf_counter()
    try:
        game = Game(mode="yugioh")
        p1 = game.add_player(f"P1_{p1_label}_{p1_variant}")
        p2 = game.add_player(f"P2_{p2_label}_{p2_variant}")
        game.setup_yugioh_player(p1, deck1["main"], deck1.get("extra") or [])
        game.setup_yugioh_player(p2, deck2["main"], deck2.get("extra") or [])

        ai1 = _ygo_variant_adapter(p1_variant, deck1.get("strategy"))
        ai2 = _ygo_variant_adapter(p2_variant, deck2.get("strategy"))
        game.turn_manager.set_ai_handler(_YGODispatchAdapter({p1.id: ai1, p2.id: ai2}))
        game.turn_manager.ai_players.add(p1.id)
        game.turn_manager.ai_players.add(p2.id)

        await game.turn_manager.setup_game()
        turns = 0
        while turns < max_turns:
            if game.is_game_over():
                break
            await game.turn_manager.run_turn()
            turns += 1

        winner = game.get_winner()
        winner_variant = None
        winner_reason = "draw"
        if winner == p1.id:
            winner_variant = p1_variant
            winner_reason = "lethal"
        elif winner == p2.id:
            winner_variant = p2_variant
            winner_reason = "lethal"
        elif turns >= max_turns:
            p1_score = p1.lp + _ygo_board_score(game, p1.id)
            p2_score = p2.lp + _ygo_board_score(game, p2.id)
            if p1_score > p2_score:
                winner_variant = p1_variant
                winner_reason = "lp_board_timeout"
            elif p2_score > p1_score:
                winner_variant = p2_variant
                winner_reason = "lp_board_timeout"

        return GameOutcome(
            p1_variant=p1_variant,
            p2_variant=p2_variant,
            p1_deck_label=p1_label,
            p2_deck_label=p2_label,
            winner_variant=winner_variant,
            turns=turns,
            duration_s=time.perf_counter() - started,
            winner_reason=winner_reason,
        )
    except Exception as exc:
        return GameOutcome(
            p1_variant=p1_variant,
            p2_variant=p2_variant,
            p1_deck_label=p1_label,
            p2_deck_label=p2_label,
            winner_variant=None,
            turns=0,
            duration_s=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )


ENGINES: dict[str, dict] = {
    "minecraft": {
        "deck_resolver": _mc_decks,
        "run_one": _mc_run_one,
        "default_decks": ["builder", "miner", "raider"],
        # Single-axis card-pick variants + cross-axis full-strategy
        # variants + random/largest baselines.
        "default_variants": [
            "balanced", "aggro", "ramp", "explore", "workers",
            "iron_rush", "avatar_burn", "wall_grinder", "passive_econ", "wood_economy",
            "random", "largest",
        ],
        "default_max_turns": 30,
    },
    "mtg": {
        "deck_resolver": _mtg_decks,
        "run_one": _mtg_run_one,
        "default_decks": ["MONO_RED_AGGRO", "DIMIR_CONTROL", "MONO_GREEN_RAMP", "BOROS_AGGRO"],
        "default_variants": ["aggro", "control", "midrange"],
        "default_max_turns": 20,
    },
    "pokemon": {
        "deck_resolver": _pkm_decks,
        "run_one": _pkm_run_one,
        "default_decks": ["izzet", "rakdos", "gruul", "orzhov"],
        "default_variants": ["medium", "hard", "ultra"],
        "default_max_turns": 80,
    },
    "hearthstone": {
        "deck_resolver": _hs_decks,
        "run_one": _hs_run_one,
        "default_decks": [
            "stormrift_pyromancer", "stormrift_cryomancer",
            "frieren", "macht",
            "riftclash_pyromancer", "riftclash_cryomancer",
        ],
        "default_variants": ["aggro", "control", "midrange", "ultra", "random"],
        "default_max_turns": 30,
    },
    "yugioh": {
        "deck_resolver": _ygo_decks,
        "run_one": _ygo_run_one,
        "default_decks": [
            "goat_control",
            "chain_burn",
            "dragon_beatdown",
            "kamigawa:samurai",
            "kamigawa:ninja",
            "kamigawa:moonfolk",
        ],
        "default_variants": ["balanced", "deck_strategy", "aggro", "control", "burn", "random"],
        "default_max_turns": 40,
    },
}


# ---------------------------------------------------------------------------
# Tournament loop
# ---------------------------------------------------------------------------


async def run_variant_tournament(
    engine: str,
    deck_pool: dict[str, list],
    variants: list[str],
    games_per_pair_per_deck: int = 4,
    max_turns: Optional[int] = None,
    verbose: bool = True,
    custom_presets: Optional[dict[str, dict]] = None,
) -> list[GameOutcome]:
    """
    Round-robin: every variant pair plays N games on every deck pair
    (synergy-against-itself eliminated; deck pair = one deck per seat).

    Pair list: for variants V and decks D, pairings = C(|V|, 2) * |D|^2 * N.
    To keep cost down, default sweep is variants pairs * decks (each
    deck with same deck on both sides) * N games.
    """
    cfg = ENGINES.get(engine)
    if not cfg:
        raise ValueError(f"Unknown engine: {engine!r}. Available: {list(ENGINES)}")
    run_one = cfg["run_one"]
    if max_turns is None:
        max_turns = cfg["default_max_turns"]

    deck_labels = list(deck_pool.keys())
    pairings: list[tuple[str, str, str, str]] = []

    # All variant pairs (i < j), each deck combination, alternating seats
    # so first-player advantage cancels.
    for i, v1 in enumerate(variants):
        for v2 in variants[i + 1:]:
            for deck_name in deck_labels:
                deck = deck_pool[deck_name]
                for g in range(games_per_pair_per_deck):
                    if g % 2 == 0:
                        pairings.append((v1, v2, deck_name, deck_name))
                    else:
                        pairings.append((v2, v1, deck_name, deck_name))

    if verbose:
        print(f"\n=== Variant tournament: {engine} ===", flush=True)
        print(f"  variants ({len(variants)}): {', '.join(variants)}", flush=True)
        print(f"  decks ({len(deck_labels)}): {', '.join(deck_labels)}", flush=True)
        print(f"  games per pair per deck: {games_per_pair_per_deck}", flush=True)
        print(f"  total games: {len(pairings)}", flush=True)
        print(f"  max_turns: {max_turns}", flush=True)

    started = time.perf_counter()
    outcomes: list[GameOutcome] = []
    # Only the MC runner takes custom_presets — pass it when supported.
    import inspect
    accepts_presets = "custom_presets" in inspect.signature(run_one).parameters
    for i, (v1, v2, d1_label, d2_label) in enumerate(pairings):
        deck1 = deck_pool[d1_label]
        deck2 = deck_pool[d2_label]
        try:
            if accepts_presets:
                outcome = await run_one(deck1, deck2, v1, v2, d1_label, d2_label, max_turns,
                                        custom_presets=custom_presets)
            else:
                outcome = await run_one(deck1, deck2, v1, v2, d1_label, d2_label, max_turns)
        except Exception as exc:
            outcome = GameOutcome(
                p1_variant=v1, p2_variant=v2,
                p1_deck_label=d1_label, p2_deck_label=d2_label,
                winner_variant=None, turns=0, duration_s=0.0,
                error=f"{type(exc).__name__}: {exc}",
            )
        outcomes.append(outcome)
        if verbose and (i + 1) % max(1, len(pairings) // 10) == 0:
            elapsed = time.perf_counter() - started
            pct = (i + 1) * 100 // len(pairings)
            print(f"    {pct:3d}% ({i+1}/{len(pairings)})  elapsed={elapsed:.1f}s",
                  flush=True)

    return outcomes


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------


def aggregate(outcomes: list[GameOutcome], variants: list[str]) -> dict[str, Any]:
    # Pairwise win matrix: matrix[a][b] = wins when a was a player vs b.
    wins = defaultdict(lambda: defaultdict(int))
    games = defaultdict(lambda: defaultdict(int))
    overall_wins = defaultdict(int)
    overall_games = defaultdict(int)
    reason_counts = defaultdict(int)
    error_count = 0
    draw_count = 0

    for o in outcomes:
        if o.error and o.winner_variant is None:
            error_count += 1
        if o.winner_variant is None:
            draw_count += 1
        if o.winner_reason:
            reason_counts[o.winner_reason] += 1
        a, b = o.p1_variant, o.p2_variant
        games[a][b] += 1
        games[b][a] += 1
        overall_games[a] += 1
        overall_games[b] += 1
        if o.winner_variant == a:
            wins[a][b] += 1
            overall_wins[a] += 1
        elif o.winner_variant == b:
            wins[b][a] += 1
            overall_wins[b] += 1

    matrix = {}
    for a in variants:
        matrix[a] = {}
        for b in variants:
            if a == b:
                matrix[a][b] = None
                continue
            n = games[a][b]
            matrix[a][b] = round(wins[a][b] / n, 3) if n else 0.0

    ranking = sorted(
        variants,
        key=lambda v: (overall_wins[v] / overall_games[v]) if overall_games[v] else 0,
        reverse=True,
    )

    return {
        "variants": variants,
        "win_matrix": matrix,
        "ranking": [
            {
                "variant": v,
                "wins": overall_wins[v],
                "games": overall_games[v],
                "winrate": round(overall_wins[v] / overall_games[v], 3) if overall_games[v] else 0.0,
            }
            for v in ranking
        ],
        "totals": {
            "games": len(outcomes),
            "draws": draw_count,
            "errors": error_count,
            "winner_reasons": dict(sorted(reason_counts.items())),
        },
    }


def render_report(aggregated: dict[str, Any]) -> str:
    variants = aggregated["variants"]
    matrix = aggregated["win_matrix"]
    ranking = aggregated["ranking"]

    lines: list[str] = []
    width = max(8, max(len(v) for v in variants) + 1)
    lines.append("\n" + "=" * 60)
    lines.append("VARIANT TOURNAMENT — WIN MATRIX")
    lines.append("=" * 60)
    header = " " * (width + 1) + "".join(f"{v:>{width}}" for v in variants)
    lines.append(header)
    for a in variants:
        row = f"{a:<{width}} "
        for b in variants:
            cell = matrix[a][b]
            if cell is None:
                row += f"{'--':>{width}}"
            else:
                row += f"{cell:>{width}.2f}"
        lines.append(row)

    lines.append("\n" + "=" * 60)
    lines.append("OVERALL RANKING")
    lines.append("=" * 60)
    lines.append(f"{'Rank':<6}{'Variant':<{width}}{'Winrate':>10}{'W':>6}{'G':>6}")
    for i, entry in enumerate(ranking, 1):
        lines.append(
            f"{i:<6}{entry['variant']:<{width}}"
            f"{entry['winrate']:>10.3f}{entry['wins']:>6}{entry['games']:>6}"
        )

    lines.append("\n" + "=" * 60)
    lines.append("DISCOVERED META")
    lines.append("=" * 60)
    if ranking:
        winner = ranking[0]
        loser = ranking[-1]
        margin = winner["winrate"] - loser["winrate"]
        lines.append(
            f"Best variant: {winner['variant']!r} ({winner['winrate']:.1%} winrate)."
        )
        lines.append(
            f"Worst variant: {loser['variant']!r} ({loser['winrate']:.1%}). "
            f"Margin {margin:.1%}."
        )
        if margin < 0.10:
            lines.append(
                "  Margin under 10% — variants are roughly equal. "
                "Either the format is balanced or the variant set isn't "
                "expressing meaningful strategic differences yet."
            )
        else:
            lines.append(
                f"  Lean further into {winner['variant']!r}: increase its "
                f"key bonuses, or design more cards that reward its plan."
            )

    totals = aggregated["totals"]
    lines.append(
        f"\nTotal games: {totals['games']}   draws: {totals['draws']}   "
        f"errors: {totals['errors']}"
    )
    if totals.get("winner_reasons"):
        reason_text = ", ".join(
            f"{reason}={count}"
            for reason, count in totals["winner_reasons"].items()
        )
        lines.append(f"Winner reasons: {reason_text}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=list(ENGINES.keys()), required=True)
    parser.add_argument("--variants", type=str, default=None,
                        help="Comma-separated variant names. Default: engine's default set.")
    parser.add_argument("--decks", type=str, default=None,
                        help="Comma-separated deck names. Default: engine's default set.")
    parser.add_argument("--games", type=int, default=4,
                        help="Games per variant pair per deck (default 4).")
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--seed", type=int, default=None,
                        help="Optional random seed for reproducible tournament runs.")
    parser.add_argument("--variants-file", type=str, default=None,
                        help="JSON file with extra named variants. Shape: "
                             "{'variants': {'name': {'preset': {...}, 'rationale': '...'}}}")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    cfg = ENGINES[args.engine]
    deck_names = (args.decks.split(",") if args.decks
                  else list(cfg["default_decks"]))

    # Load custom presets from a JSON file (e.g. brainstormed by a subagent).
    custom_presets: dict[str, dict] = {}
    custom_rationales: dict[str, str] = {}
    if args.variants_file:
        with open(args.variants_file) as fh:
            payload = json.load(fh)
        for name, spec in (payload.get("variants") or {}).items():
            preset = spec.get("preset") if isinstance(spec, dict) else None
            if not isinstance(preset, dict):
                raise ValueError(f"Variant {name!r} in {args.variants_file} missing 'preset' dict")
            custom_presets[name] = preset
            custom_rationales[name] = spec.get("rationale", "")

    if args.variants:
        variants = args.variants.split(",")
    elif custom_presets:
        # Default: include all loaded custom variants + key benchmarks.
        variants = list(custom_presets.keys()) + ["balanced", "passive_econ", "random", "fully_random"]
    else:
        variants = list(cfg["default_variants"])

    deck_pool = cfg["deck_resolver"](deck_names)

    if custom_presets:
        print("\n=== Custom variants loaded ===", flush=True)
        for name in custom_presets:
            print(f"  {name}: {custom_rationales.get(name, '<no rationale>')}",
                  flush=True)

    outcomes = asyncio.run(run_variant_tournament(
        args.engine, deck_pool, variants,
        games_per_pair_per_deck=args.games,
        max_turns=args.max_turns,
        custom_presets=custom_presets or None,
    ))

    aggregated = aggregate(outcomes, variants)
    print(render_report(aggregated))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({
                "engine": args.engine,
                "variants": variants,
                "decks": deck_names,
                "games_per_pair_per_deck": args.games,
                "seed": args.seed,
                "outcomes": [o.__dict__ for o in outcomes],
                "aggregated": aggregated,
            }, fh, indent=2)
        print(f"\nWrote {args.out}")


if __name__ == "__main__":
    _cli()
