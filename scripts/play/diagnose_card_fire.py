"""Auto-diagnose 'why doesn't this card fire under heuristic AI?'

Walks the 6-step decision tree once used manually for BRV's gap-closure
(Voidmage, Mirko, Aurelia, Pithing, Negate, Jarad). The same diagnosis
that took ~40 minutes by hand becomes one shell command.

Supports two engines (inferred from the --p1 deck name, or set --engine):
    # Pokemon
    python -m scripts.play.diagnose_card_fire \\
        --card "Voidmage Apprentice" \\
        --p1 dimir --p2 golgari \\
        --p1-bias lz_engine --p2-bias lz_engine \\
        --games 3 --max-turns 30
    # SCP (cards AND activated/modal abilities)
    python -m scripts.play.diagnose_card_fire \\
        --card "SZB Public Spectacle Suite" \\
        --p1 site_zero_masquerade --p2 site_zero_masquerade \\
        --games 4 --max-turns 25 --engine scp

Decision tree (Pokemon framing; the SCP path maps the same six steps to
drawn / deployed / fired / scored vs threshold / cost / precondition — see
diagnose_scp):
    1. Is the card drawn >=1x across the trace?
    2. Is the card in legal_pokemon_actions when in hand?
    3. What does its scorer return when in hand?
    4. If it's an evolution, is its prerequisite ever in play?
    5. If it's an attacker, are required energies ever attached when Active?
    6. Does the AI rank it below alternatives at action-selection time?

Output: human-readable diagnosis + suggested patch.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# =============================================================================
# Per-engine adapters
# =============================================================================

def _resolve_pokemon_deck(name: str):
    """Resolve a deck builder name to a deck list (Pokemon engine)."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.pokemon.beyond.ravnica import GUILD_DECK_BUILDERS
    if name not in GUILD_DECK_BUILDERS:
        raise SystemExit(
            f"Unknown deck: {name}. Known: {sorted(GUILD_DECK_BUILDERS)}"
        )
    return GUILD_DECK_BUILDERS[name]()


def _resolve_engine(engine: Optional[str], p1_deck: str) -> str:
    """Resolve the engine: explicit --engine wins, else infer from the --p1 deck.

    An SCP deck name (a key in scp_tournament.SCP_STARTER_DECKS) implies the SCP
    engine; otherwise default to Pokemon (the historical default).
    """
    if engine:
        return engine
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        try:
            from scripts.play.scp_tournament import SCP_STARTER_DECKS
            if p1_deck in SCP_STARTER_DECKS:
                return "scp"
        except Exception:
            pass
    return "pokemon"


def _find_card_in_decks(card_name: str, decks: dict[str, list]) -> dict[str, int]:
    """Map deck-name -> count of this card in that deck."""
    out: dict[str, int] = {}
    for deck_name, deck in decks.items():
        n = sum(1 for cd in deck if getattr(cd, "name", "") == card_name)
        if n > 0:
            out[deck_name] = n
    return out


# =============================================================================
# Per-game telemetry container
# =============================================================================

@dataclass
class CardTelemetry:
    """Telemetry captured for one card across one game."""
    card_name: str
    games_run: int = 0
    drawn_count: int = 0  # turns where this card was in any hand
    legal_action_seen: int = 0  # turns where it appears in legal_pokemon_actions
    legal_action_eligible: int = 0  # turns in hand AND type-precondition met
    # Scorer invocations bucketed by which scorer wrapped them. The
    # 'primary' bucket maps to the scorer_kind classified for this card —
    # diagnose() consults that one for the Step 3 pass/fail call.
    scorer_invocations: dict[str, list[float]] = field(
        default_factory=lambda: {
            "trainer": [], "basic_play": [],
            "evolution": [], "attacker": [],
        })
    scorer_kind: str = ""  # "trainer" / "basic_play" / "attacker" / "evolution"
    evolution_prereq_in_play: int = 0  # for evolutions: turns where prereq was in play (with turns_in_play >= 1)
    evolution_prereq_name: str = ""
    active_turns: int = 0  # turns where this card was Active
    active_with_required_energy: int = 0  # turns where Active AND can attack
    required_energies: list[dict] = field(default_factory=list)  # min cost
    ranked_below_alternatives: int = 0  # turns where alternatives were picked instead
    alternatives_picked: list[tuple[str, float, float]] = field(default_factory=list)
    times_played: int = 0  # actually played from hand
    times_attacked_from_active: int = 0
    deck_count_p1: int = 0
    deck_count_p2: int = 0
    # -- SCP-engine fields (unused by the Pokemon path; default 0/False) -------
    scp_has_ability: bool = False        # card carries an activated/modal ability
    scp_on_battlefield_turns: int = 0    # turns the card was deployed (any player)
    scp_times_fired: int = 0             # SCP_ABILITY_ACTIVATED events for this card
    scp_gain: list[float] = field(default_factory=list)  # _estimate_ability_value captures
    scp_cost: list[float] = field(default_factory=list)  # _cost_value captures
    scp_fire_threshold: float = 0.5      # _ability_fire_threshold at runtime

    def primary_scores(self) -> list[float]:
        """Return scorer outputs from the scorer that owns this card's kind."""
        if self.scorer_kind and self.scorer_kind in self.scorer_invocations:
            return list(self.scorer_invocations[self.scorer_kind])
        # Fall back to any bucket with data.
        for bucket in self.scorer_invocations.values():
            if bucket:
                return list(bucket)
        return []

    def merge(self, other: "CardTelemetry") -> None:
        """Merge per-game telemetry into a multi-game aggregate."""
        self.games_run += other.games_run
        self.drawn_count += other.drawn_count
        self.legal_action_seen += other.legal_action_seen
        self.legal_action_eligible += other.legal_action_eligible
        for k, v in other.scorer_invocations.items():
            self.scorer_invocations.setdefault(k, []).extend(v)
        self.scorer_kind = self.scorer_kind or other.scorer_kind
        self.evolution_prereq_in_play += other.evolution_prereq_in_play
        self.evolution_prereq_name = self.evolution_prereq_name or other.evolution_prereq_name
        self.active_turns += other.active_turns
        self.active_with_required_energy += other.active_with_required_energy
        if not self.required_energies and other.required_energies:
            self.required_energies = other.required_energies
        self.ranked_below_alternatives += other.ranked_below_alternatives
        self.alternatives_picked.extend(other.alternatives_picked)
        self.times_played += other.times_played
        self.times_attacked_from_active += other.times_attacked_from_active
        self.deck_count_p1 += other.deck_count_p1
        self.deck_count_p2 += other.deck_count_p2
        self.scp_has_ability = self.scp_has_ability or other.scp_has_ability
        self.scp_on_battlefield_turns += other.scp_on_battlefield_turns
        self.scp_times_fired += other.scp_times_fired
        self.scp_gain.extend(other.scp_gain)
        self.scp_cost.extend(other.scp_cost)
        self.scp_fire_threshold = other.scp_fire_threshold or self.scp_fire_threshold


# =============================================================================
# Pokemon-engine probe
# =============================================================================

def _pokemon_card_def_from_decks(card_name: str, decks: list[list]):
    """Find the CardDefinition by name in any of the decks."""
    for deck in decks:
        for cd in deck:
            if getattr(cd, "name", "") == card_name:
                return cd
    return None


def _classify_scorer_kind(card_def) -> str:
    """Decide which scorer applies to this card."""
    try:
        from src.engine.types import CardType
    except Exception:
        return "trainer"
    types = getattr(getattr(card_def, "characteristics", None), "types", None) or set()
    if CardType.POKEMON in types:
        if getattr(card_def, "evolves_from", None):
            return "evolution"
        return "basic_play"
    return "trainer"


def _get_zone_objects(state, key: str) -> list:
    zone = state.zones.get(key)
    if not zone:
        return []
    return [state.objects[oid] for oid in list(zone.objects) if oid in state.objects]


async def _run_pokemon_diagnostic_game(
    *,
    card_name: str,
    p1_deck_name: str,
    p2_deck_name: str,
    p1_bias: str,
    p2_bias: str,
    max_turns: int,
    capture_top_actions: bool = True,
) -> CardTelemetry:
    """Run one game, instrument the AI, return telemetry for this card."""
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.ai.pokemon_adapter import PokemonAIAdapter
        from src.engine.pokemon_legal_actions import legal_pokemon_actions
        from src.engine.types import CardType, ZoneType
        from src.engine.pokemon_energy import PokemonEnergySystem

    deck1 = _resolve_pokemon_deck(p1_deck_name)
    deck2 = _resolve_pokemon_deck(p2_deck_name)

    tele = CardTelemetry(card_name=card_name, games_run=1)
    tele.deck_count_p1 = sum(1 for cd in deck1 if getattr(cd, "name", "") == card_name)
    tele.deck_count_p2 = sum(1 for cd in deck2 if getattr(cd, "name", "") == card_name)

    target_card_def = _pokemon_card_def_from_decks(card_name, [deck1, deck2])
    if target_card_def is not None:
        tele.scorer_kind = _classify_scorer_kind(target_card_def)
        if tele.scorer_kind == "evolution":
            tele.evolution_prereq_name = getattr(target_card_def, "evolves_from", "") or ""
        # Capture required energy cost for attacker check
        attacks = getattr(target_card_def, "attacks", None) or []
        if attacks:
            cheapest_attack = min(
                attacks,
                key=lambda a: sum(req.get("count", 0) for req in a.get("cost", [])),
            )
            tele.required_energies = list(cheapest_attack.get("cost") or [])

    game = Game(mode="pokemon")
    p1 = game.add_player(f"P1-{p1_deck_name}")
    p2 = game.add_player(f"P2-{p2_deck_name}")
    game.setup_pokemon_player(p1, deck1)
    game.setup_pokemon_player(p2, deck2)
    ai = PokemonAIAdapter(difficulty="medium", bias=p1_bias)
    ai.player_difficulties[p1.id] = "medium"
    ai.player_difficulties[p2.id] = "medium"
    ai.set_player_bias(p1.id, p1_bias)
    ai.set_player_bias(p2.id, p2_bias)
    game.turn_manager.set_ai_handler(ai)
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)

    # -- INSTRUMENTATION ----------------------------------------------------
    # Wrap each scorer so we capture invocations targeting our card.
    original_score_trainer = ai._score_trainer
    original_score_attacker = ai._score_attacker
    original_score_basic = ai._score_basic_play
    original_score_evolution = ai._score_evolution

    def _matches(obj) -> bool:
        return obj is not None and getattr(obj, "name", "") == card_name

    def traced_score_trainer(card, state, player_id):
        score = original_score_trainer(card, state, player_id)
        if _matches(card):
            tele.scorer_invocations["trainer"].append(float(score))
        return score

    def traced_score_attacker(pokemon, state, player_id):
        score = original_score_attacker(pokemon, state, player_id)
        if _matches(pokemon):
            tele.scorer_invocations["attacker"].append(float(score))
        return score

    def traced_score_basic_play(card, state, player_id):
        score = original_score_basic(card, state, player_id)
        if _matches(card):
            tele.scorer_invocations["basic_play"].append(float(score))
        return score

    def traced_score_evolution(base, evolution, state, player_id):
        score = original_score_evolution(base, evolution, state, player_id)
        if _matches(evolution):
            tele.scorer_invocations["evolution"].append(float(score))
        return score

    ai._score_trainer = traced_score_trainer
    ai._score_attacker = traced_score_attacker
    ai._score_basic_play = traced_score_basic_play
    ai._score_evolution = traced_score_evolution

    # Trace plays + attacks via pipeline.emit wrap.
    pipeline = getattr(game, "pipeline", None)
    original_emit = None
    if pipeline and hasattr(pipeline, "emit"):
        original_emit = pipeline.emit

        def trace_emit(event):
            try:
                etype = event.type.name
                payload = event.payload or {}
                # Card-played markers
                if etype in (
                    "PKM_PLAY_BASIC", "PKM_PLAY_ITEM", "PKM_PLAY_SUPPORTER",
                    "PKM_PLAY_STADIUM", "PKM_EVOLVE",
                ):
                    name = payload.get("card_name") or payload.get("pokemon_name") or ""
                    if name == card_name:
                        tele.times_played += 1
                elif etype == "PKM_ATTACK_DECLARE":
                    pid = payload.get("attacker_id")
                    obj = game.state.objects.get(pid) if pid else None
                    if obj and obj.name == card_name:
                        tele.times_attacked_from_active += 1
            except Exception:
                pass
            return original_emit(event)

        pipeline.emit = trace_emit

    # -- RUN GAME ------------------------------------------------------------
    try:
        await game.turn_manager.setup_game()
    except Exception as exc:
        # Restore and bail with partial telemetry.
        ai._score_trainer = original_score_trainer
        ai._score_attacker = original_score_attacker
        ai._score_basic_play = original_score_basic
        ai._score_evolution = original_score_evolution
        if original_emit is not None:
            pipeline.emit = original_emit
        raise

    turns = 0
    try:
        for _ in range(max_turns):
            if game.is_game_over():
                break

            # Per-turn telemetry sampling for BOTH players (only those running
            # this card's deck are interesting, but we capture both for safety).
            for pid in (p1.id, p2.id):
                # Step 1: hand presence
                hand_objs = _get_zone_objects(game.state, f"hand_{pid}")
                if any(o.name == card_name for o in hand_objs):
                    tele.drawn_count += 1

                # Step 2: legal-action visibility.
                # Two counters: how often it APPEARS, vs how often its
                # type-specific precondition is MET (so we can distinguish
                # 'bench full so Basic correctly hidden' from 'card type
                # never iterated in legal_pokemon_actions').
                hand_match_objs = [o for o in hand_objs if o.name == card_name]
                if hand_match_objs:
                    try:
                        legal = legal_pokemon_actions(game, pid)
                    except Exception:
                        legal = []
                    card_ids_in_hand = {o.id for o in hand_match_objs}
                    appears = False
                    for action in legal:
                        payload = action.get("payload") or {}
                        cid = payload.get("card_id") or payload.get("energy_id")
                        if cid in card_ids_in_hand:
                            appears = True
                            break
                    if appears:
                        tele.legal_action_seen += 1

                    # Eligibility: type-specific precondition met?
                    sample_obj = hand_match_objs[0]
                    card_def = sample_obj.card_def
                    types = (sample_obj.characteristics.types
                             if sample_obj.characteristics else set()) or set()
                    eligible = False
                    bench_objs = _get_zone_objects(
                        game.state, f"bench_{pid}")
                    active_objs = _get_zone_objects(
                        game.state, f"active_spot_{pid}")
                    own_pokemon_objs = active_objs + bench_objs
                    player_obj = game.state.players.get(pid)
                    if CardType.POKEMON in types and card_def:
                        if card_def.evolution_stage == "Basic":
                            eligible = len(bench_objs) < 5
                        elif getattr(card_def, "evolves_from", None):
                            # Eligible if any own pokemon's name matches and is
                            # not blocked by play-turn / already-evolved.
                            evo_from = card_def.evolves_from
                            for op in own_pokemon_objs:
                                if (op.name == evo_from
                                        and getattr(op.state,
                                                    "turns_in_play", 0) >= 1
                                        and not getattr(op.state,
                                                        "evolved_this_turn",
                                                        False)):
                                    eligible = True
                                    break
                    elif CardType.SUPPORTER in types and player_obj:
                        eligible = (
                            not getattr(player_obj,
                                        "supporter_played_this_turn", False)
                        )
                    elif CardType.STADIUM in types and player_obj:
                        eligible = (
                            not getattr(player_obj,
                                        "stadium_played_this_turn", False)
                        )
                    elif CardType.ITEM in types:
                        eligible = True
                    elif CardType.POKEMON_TOOL in types:
                        eligible = any(
                            not getattr(p.state, "attached_tool", None)
                            for p in own_pokemon_objs
                        )
                    elif CardType.ENERGY in types and player_obj:
                        eligible = (
                            not getattr(player_obj,
                                        "energy_attached_this_turn", False)
                            and len(own_pokemon_objs) > 0
                        )
                    if eligible:
                        tele.legal_action_eligible += 1

                # Step 4: evolution prereq presence
                if tele.scorer_kind == "evolution" and tele.evolution_prereq_name:
                    in_play = (
                        _get_zone_objects(game.state, f"active_spot_{pid}")
                        + _get_zone_objects(game.state, f"bench_{pid}")
                    )
                    for obj in in_play:
                        if (obj.name == tele.evolution_prereq_name
                                and getattr(obj.state, "turns_in_play", 0) >= 1):
                            tele.evolution_prereq_in_play += 1
                            break

                # Step 5: energy when Active
                active_objs = _get_zone_objects(game.state, f"active_spot_{pid}")
                if any(o.name == card_name for o in active_objs):
                    tele.active_turns += 1
                    if tele.required_energies:
                        # Use PokemonEnergySystem to check whether the cheapest
                        # attack's cost is paid.
                        try:
                            es = PokemonEnergySystem(game.state)
                            target_obj = next(
                                (o for o in active_objs if o.name == card_name),
                                None,
                            )
                            if target_obj and es.can_pay_cost(
                                    target_obj.id, tele.required_energies):
                                tele.active_with_required_energy += 1
                        except Exception:
                            pass

                # Step 6: action selection. For each action TYPE the card
                # can participate in (PKM_PLAY_BASIC, PKM_EVOLVE, ...),
                # compare its score only against alternatives of the same
                # type — scores aren't comparable across types.
                if capture_top_actions and any(o.name == card_name for o in hand_objs):
                    try:
                        legal = legal_pokemon_actions(game, pid)
                    except Exception:
                        legal = []
                    # Bucket by action type.
                    per_type: dict[str, list[tuple[str, float, bool]]] = {}
                    for action in legal:
                        payload = action.get("payload") or {}
                        atype = action.get("type")
                        cid = payload.get("card_id")
                        if not cid:
                            continue
                        obj = game.state.objects.get(cid)
                        if not obj:
                            continue
                        try:
                            if atype == "PKM_PLAY_BASIC":
                                s = ai._score_basic_play(obj, game.state, pid)
                            elif atype in ("PKM_PLAY_SUPPORTER",
                                            "PKM_PLAY_ITEM",
                                            "PKM_PLAY_STADIUM"):
                                s = ai._score_trainer(obj, game.state, pid)
                            elif atype == "PKM_EVOLVE":
                                base_id = payload.get("target_id")
                                base = game.state.objects.get(base_id)
                                if not base:
                                    continue
                                s = ai._score_evolution(
                                    base, obj, game.state, pid)
                            else:
                                continue
                        except Exception:
                            continue
                        label = action.get("label", obj.name)
                        is_target = (obj.name == card_name)
                        per_type.setdefault(atype, []).append(
                            (label, float(s), is_target))
                    # For each type, check whether our card was beaten.
                    for atype, cands in per_type.items():
                        target_entry = next(
                            (c for c in cands if c[2]), None)
                        if target_entry is None:
                            continue
                        target_label, target_score, _ = target_entry
                        sorted_cands = sorted(
                            cands, key=lambda x: x[1], reverse=True)
                        top_label, top_score, top_is_target = sorted_cands[0]
                        if not top_is_target and target_score < top_score:
                            tele.ranked_below_alternatives += 1
                            tele.alternatives_picked.append(
                                (top_label, top_score, target_score))

            await game.turn_manager.run_turn()
            turns += 1
    finally:
        # Restore.
        ai._score_trainer = original_score_trainer
        ai._score_attacker = original_score_attacker
        ai._score_basic_play = original_score_basic
        ai._score_evolution = original_score_evolution
        if original_emit is not None:
            pipeline.emit = original_emit

    return tele


# =============================================================================
# SCP-engine probe
# =============================================================================

async def _run_scp_diagnostic_game(
    *,
    card_name: str,
    p1_deck_name: str,
    p2_deck_name: str,
    difficulty: str,
    max_turns: int,
    seed: int,
) -> CardTelemetry:
    """Run one SCP game, instrument the heuristic AI, return telemetry.

    Mirrors the Pokemon probe but for SCP's two fire modes — DEPLOY (play the
    card onto the battlefield via ``open_dossier``) and ACTIVATE (the AI fires a
    registered activated/modal ability via ``_consider_activated_abilities``).
    The six steps map to: drawn / legal (deployed + ability offered) / scored
    (gain−cost vs threshold) / precondition (conditional value_hint) / cost
    (``can_pay_scp_cost``) / fired (``SCP_ABILITY_ACTIVATED``).
    """
    import random
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.engine.types import ZoneType
        from src.ai.scp_adapter import SCPAIAdapter
        from src.engine.scp_abilities import is_scp_ability
        from scripts.play.scp_tournament import SCP_STARTER_DECKS, _DispatchSCPAIAdapter

    if p1_deck_name not in SCP_STARTER_DECKS or p2_deck_name not in SCP_STARTER_DECKS:
        raise SystemExit(
            f"Unknown SCP deck. Known: {sorted(SCP_STARTER_DECKS)}"
        )

    random.seed(seed)
    deck1 = SCP_STARTER_DECKS[p1_deck_name]()
    deck2 = SCP_STARTER_DECKS[p2_deck_name]()

    tele = CardTelemetry(card_name=card_name, games_run=1)
    tele.deck_count_p1 = sum(1 for cd in deck1 if getattr(cd, "name", "") == card_name)
    tele.deck_count_p2 = sum(1 for cd in deck2 if getattr(cd, "name", "") == card_name)

    game = Game(mode="scp")
    p1 = game.add_player(f"P1-{p1_deck_name}")
    p2 = game.add_player(f"P2-{p2_deck_name}")
    game.setup_scp_player(p1, deck1)
    game.setup_scp_player(p2, deck2)
    game.shuffle_library(p1.id)
    game.shuffle_library(p2.id)
    a1 = SCPAIAdapter(difficulty=difficulty)
    a2 = SCPAIAdapter(difficulty=difficulty)
    tele.scp_fire_threshold = float(getattr(a1, "_ability_fire_threshold", 0.5))
    game.turn_manager.set_ai_player(p1.id)
    game.turn_manager.set_ai_player(p2.id)
    game.turn_manager.set_ai_handler(_DispatchSCPAIAdapter({p1.id: a1, p2.id: a2}))

    # -- INSTRUMENTATION: capture activation gain/cost for the target card -----
    def _matches(obj) -> bool:
        return obj is not None and getattr(obj, "name", "") == card_name

    for a in (a1, a2):
        _orig_est = a._estimate_ability_value
        _orig_cost = a._cost_value

        def _make_est(orig):
            def traced(obj, state, player_id, hint):
                v = orig(obj, state, player_id, hint)
                if _matches(obj) and hint is not None:
                    tele.scp_gain.append(float(v))
                return v
            return traced

        def _make_cost(orig):
            def traced(obj, state, player_id, cost):
                v = orig(obj, state, player_id, cost)
                if _matches(obj):
                    tele.scp_cost.append(float(v))
                return v
            return traced

        a._estimate_ability_value = _make_est(_orig_est)
        a._cost_value = _make_cost(_orig_cost)

    # -- RUN GAME -----------------------------------------------------------
    target_obj_ids: set[str] = set()
    await game.start_game()
    for _ in range(max_turns * 2):
        if game.is_game_over():
            break
        await game.run_turn()
        for pid in (p1.id, p2.id):
            hand = _get_zone_objects(game.state, f"hand_{pid}")
            if any(o.name == card_name for o in hand):
                tele.drawn_count += 1
            bf = [
                o for o in game.state.objects.values()
                if getattr(o, "name", "") == card_name
                and o.controller == pid and o.zone == ZoneType.BATTLEFIELD
            ]
            if not bf:
                continue
            tele.scp_on_battlefield_turns += 1
            obj = bf[0]
            target_obj_ids.add(obj.id)
            abilities = [
                ab for ab in (getattr(obj.state, "activated_abilities", None) or [])
                if is_scp_ability(ab)
            ]
            if abilities:
                tele.scp_has_ability = True

    # Count actual fires from the event log (object_id seen on the battlefield).
    for e in game.state.event_log:
        if e.type.name == "SCP_ABILITY_ACTIVATED":
            oid = (e.payload or {}).get("object_id")
            obj = game.state.objects.get(oid) if oid else None
            if (oid in target_obj_ids) or (obj is not None and obj.name == card_name):
                tele.scp_times_fired += 1
    if tele.scp_on_battlefield_turns > 0:
        tele.times_played = 1  # reached the battlefield at least once this game
    return tele


def diagnose_scp(tele: CardTelemetry) -> tuple[list["StepResult"], str, str]:
    """Walk the six-step fire tree against SCP telemetry.

    Returns (steps, verdict, patch). The card "fires" if it activated an ability
    (``scp_times_fired``) or — for a card with no activated ability — simply got
    played onto the battlefield.
    """
    steps: list[StepResult] = []
    deck_total = tele.deck_count_p1 + tele.deck_count_p2
    fired = tele.scp_times_fired > 0
    deployed = tele.scp_on_battlefield_turns > 0

    # Step 0 — in a deck.
    if deck_total == 0:
        steps.append(StepResult("Step 0: card in deck", False,
                                "Card is in NEITHER deck. Cannot fire."))
        return steps, "FAIL", (
            "Card is not in either deck under test. Add it to a deck builder, or\n"
            "point --p1/--p2 at decks that run it, or fix the --card spelling\n"
            "(must match the CardDefinition `name` exactly)."
        )

    # Step 1 — drawn. Reaching play (or firing) implies it was drawn: a card
    # drawn-and-played in the same turn is never sampled in hand post-turn, so
    # treat deploy/fire as proof it was drawn.
    reached_game = (tele.drawn_count > 0 or deployed or fired)
    if not reached_game:
        steps.append(StepResult("Step 1: drawn into hand at least once", False,
                                f"never drawn or played across {tele.games_run} games "
                                f"(deck count: P1={tele.deck_count_p1}, P2={tele.deck_count_p2})"))
        return steps, "FAIL", (
            "Card never entered the game (not drawn, not played). Likely causes:\n"
            f"  - Deck count too low (P1={tele.deck_count_p1}, P2={tele.deck_count_p2}) — add copies\n"
            "  - SCP games are short and breach-dominated; a 1-of payoff can end up\n"
            "    undrawn before the game ends. Try --max-turns higher / more --games,\n"
            "    or the deck/format is too fast for this payoff (a deck-speed item)."
        )
    steps.append(StepResult("Step 1: drawn into hand at least once", True,
                            f"in hand on {tele.drawn_count} player-turns "
                            f"(reached play on {tele.scp_on_battlefield_turns} turns) "
                            f"across {tele.games_run} games"))

    # Step 2 — reached play (deploy). A card can't fire from hand.
    if not deployed:
        steps.append(StepResult("Step 2: deployed to the battlefield", False,
                                f"drawn on {tele.drawn_count} turns but NEVER played onto the "
                                f"battlefield"))
        return steps, "FAIL", (
            "Card is drawn but the AI never deploys it. Likely causes:\n"
            "  - It loses the per-turn deploy race in scp_adapter.score() — a 1-of\n"
            "    facility sits at flat rank 2 behind every personnel/procedure.\n"
            "    Confirm _carries_signature_bomb() promotes payoff cards to rank 0.\n"
            "  - Its red_tape is high and the open-loop breaks before reaching it.\n"
            "  - Inspect scp_adapter.score() and the deploy loop in take_turn()."
        )
    steps.append(StepResult("Step 2: deployed to the battlefield", True,
                            f"on the battlefield for {tele.scp_on_battlefield_turns} turns"))

    # No activated ability → "fire" == "got played". Done.
    if not tele.scp_has_ability:
        steps.append(StepResult("Step 3-6: no activated ability (fire == deploy)", True,
                                "card has no SCP activated ability; reaching the battlefield is "
                                "its fire"))
        return steps, "PASS", "No patch needed; card reaches play under heuristic AI."

    # Step 3 — did the ability actually fire? (ground truth from the event log)
    if fired:
        steps.append(StepResult("Step 3: ability fired in a game", True,
                                f"fired {tele.scp_times_fired}x across {tele.games_run} games"))
        return steps, "PASS", "No patch needed; the AI fires this ability under heuristic play."
    steps.append(StepResult("Step 3: ability fired in a game", False,
                            f"deployed for {tele.scp_on_battlefield_turns} turns but never fired"))

    # Step 4 — was the ability ever even scored for firing? _estimate_ability_value
    # / _cost_value are reached only AFTER can_pay + once_per_turn/precondition gates,
    # so an empty capture means it was gated out before the value check.
    if not tele.scp_gain:
        return steps, "FAIL", (
            "The AI never scored the ability's value — it is gated out before the\n"
            "value check in _consider_activated_abilities. Causes, in order to check:\n"
            "  - Cost never affordable (can_pay_scp_cost False): an ethics/briefing\n"
            "    cost the deck never accrues, OR exhaust_self with no turn-reset (the\n"
            "    once-per-game bug) — confirm reset_turn_abilities() runs each turn.\n"
            "  - once_per_turn / precondition_fn permanently true.\n"
            "  - The object isn't in the controlled-objects list the AI iterates.\n"
            "  - Inspect scp_adapter._consider_activated_abilities + scp_costs.can_pay_scp_cost."
        )

    # Step 4 — does the value estimate clear the fire threshold (gain − cost)?
    thr = tele.scp_fire_threshold
    best_gain = max(tele.scp_gain)
    min_cost = min(tele.scp_cost) if tele.scp_cost else 0.0
    best_net = best_gain - min_cost
    avg_gain = sum(tele.scp_gain) / len(tele.scp_gain)
    if best_net <= thr:
        steps.append(StepResult("Step 4: value clears the fire threshold", False,
                                f"best (gain − cost) = {best_gain:.2f} − {min_cost:.2f} = "
                                f"{best_net:.2f}, never exceeds threshold {thr:.2f}"))
        return steps, "FAIL", (
            f"The ability's value never clears the fire bar (best net {best_net:.2f} "
            f"<= {thr:.2f}).\n"
            f"  - gain: max={best_gain:.2f} avg={avg_gain:.2f} over {len(tele.scp_gain)} evals; "
            f"cost~{min_cost:.2f}.\n"
            "  - If gain is ~0 most turns, the value_hint is a CONDITIONAL cliff —\n"
            "    credit progress toward the condition (see _public_spectacle_value),\n"
            "    don't return 0.0 until it's crossed.\n"
            "  - If gain is decent but cost too high, re-check _cost_value (exhaust_self\n"
            "    is 0.1 facility / 0.5 personnel) or lower _ability_fire_threshold."
        )
    steps.append(StepResult("Step 4: value clears the fire threshold", True,
                            f"best (gain − cost) = {best_net:.2f} > threshold {thr:.2f}"))

    # Value clears the bar yet it never fired — a timing / single-pass issue.
    steps.append(StepResult("Step 5: fires despite clearing the bar", False,
                            "value clears the threshold but the ability still never fired"))
    return steps, "WARN", (
        "The value clears the fire bar on some evaluation, yet the ability never\n"
        "fired — a timing/single-pass issue (e.g. it only clears the bar on a turn\n"
        "_consider_activated_abilities isn't reached, or a modal-mode race). Increase\n"
        "--games / --max-turns, then trace the _consider ordering in take_turn."
    )


# =============================================================================
# Diagnosis logic — translate telemetry to a verdict + suggested patch
# =============================================================================

@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str


def diagnose(tele: CardTelemetry) -> tuple[list[StepResult], str, str]:
    """Walk the 6-step decision tree against captured telemetry.

    Returns (steps, overall_verdict, suggested_patch).
    """
    steps: list[StepResult] = []

    # Step 0 (sanity): card present in any deck.
    deck_total = tele.deck_count_p1 + tele.deck_count_p2
    if deck_total == 0:
        steps.append(StepResult(
            "Step 0: card in deck",
            False,
            "Card is in NEITHER deck. Cannot fire.",
        ))
        verdict = "FAIL"
        patch = (
            "Card is not in either deck under test. Either:\n"
            "  - Add the card to one of the deck builders\n"
            "  - Run with --p1/--p2 set to a deck that contains the card\n"
            "  - Verify the spelling of --card matches the card definition's"
            " `name` exactly."
        )
        return steps, verdict, patch

    # Step 1: drawn at least once across games.
    if tele.drawn_count == 0:
        steps.append(StepResult(
            "Step 1: drawn into hand at least once",
            False,
            f"never drawn across {tele.games_run} games "
            f"(deck count: P1={tele.deck_count_p1}, P2={tele.deck_count_p2})",
        ))
        patch = (
            "Card was never drawn into the hand across all games. Likely causes:\n"
            f"  - Deck count is too low (current: P1={tele.deck_count_p1}, "
            f"P2={tele.deck_count_p2}) — consider bumping to 2-4 copies\n"
            "  - Mulligan / prize lottery isn't surfacing it; check whether the"
            " deck has enough Pokeballs / search trainers to find it\n"
            "  - Game ends too early — try --max-turns 50 or larger sample"
        )
        return steps, "FAIL", patch
    steps.append(StepResult(
        "Step 1: drawn into hand at least once",
        True,
        f"in hand on {tele.drawn_count} player-turns across {tele.games_run} games",
    ))

    # Step 2: appears in legal_pokemon_actions when in hand AND its
    # type-precondition is met. We FAIL only if the card is eligible
    # (precondition met) on at least one turn yet never appears — that's
    # the POKEMON_TOOL-class bug.
    if tele.legal_action_eligible == 0:
        # Card was in hand but its precondition was never met. Not a Step 2
        # failure per se — could be 'bench always full' (bad luck or
        # competing demand). Pass it but flag the symptom.
        steps.append(StepResult(
            "Step 2: appears in legal_pokemon_actions when eligible",
            True,
            f"card was in hand on {tele.drawn_count} turns, but its"
            f" type-specific precondition was never met (e.g. bench full,"
            f" supporter already played) so it had no chance to appear",
        ))
    elif tele.legal_action_seen == 0:
        steps.append(StepResult(
            "Step 2: appears in legal_pokemon_actions when eligible",
            False,
            f"card was eligible to appear on {tele.legal_action_eligible}"
            f" turns (precondition met) yet NEVER appeared in the legal-"
            f"action packet returned for its controller",
        ))
        patch = (
            "Card is gated out of legal_pokemon_actions even when eligible."
            " Common causes:\n"
            "  - Card type not handled in legal_pokemon_actions (e.g. "
            "POKEMON_TOOL needs a holder; STADIUM needs no stadium already in"
            " play; SUPPORTER needs no supporter played this turn)\n"
            "  - Card has a hidden precondition not yet wired (e.g. "
            "evolves_from but evolves_from target is None)\n"
            "  - Inspect src/engine/pokemon_legal_actions.py and ensure the"
            " card's CardType is iterated."
        )
        return steps, "FAIL", patch
    else:
        steps.append(StepResult(
            "Step 2: appears in legal_pokemon_actions when eligible",
            True,
            f"appears in legal action packet on {tele.legal_action_seen}/"
            f"{tele.legal_action_eligible} turns where it was eligible",
        ))

    # Step 3: scorer returns >0 baseline.
    primary = tele.primary_scores()
    if not primary:
        steps.append(StepResult(
            "Step 3: scorer produces a usable score",
            False,
            f"primary scorer ({tele.scorer_kind or '?'}) was never invoked for"
            f" this card despite it appearing in hand and in legal actions — "
            f"the AI flow never reaches the scoring loop for it",
        ))
        patch = (
            "Scorer was never invoked. The AI phase that scores this card type"
            " ({}) is skipping it. Inspect src/ai/pokemon/adapter.py's"
            " _do_play_<phase> for the matching kind.".format(tele.scorer_kind or "?")
        )
        return steps, "FAIL", patch
    max_score = max(primary)
    min_score = min(primary)
    avg_score = sum(primary) / len(primary)
    if max_score <= 0:
        steps.append(StepResult(
            "Step 3: scorer produces a usable score",
            False,
            f"scorer ({tele.scorer_kind}) returns <=0 on every invocation "
            f"({len(primary)} calls, max={max_score:.1f}, "
            f"avg={avg_score:.1f})",
        ))
        scorer_fn = {
            "trainer": "_score_trainer",
            "basic_play": "_score_basic_play",
            "evolution": "_score_evolution",
            "attacker": "_score_attacker",
        }.get(tele.scorer_kind, "_score_trainer")
        patch = (
            f"Scorer returns <=0 ({max_score:.1f} max). The card is being"
            f" classified as 'do not play'.\n"
            f"  - Inspect src/ai/pokemon/scoring.py::{scorer_fn} for a hardcoded"
            f" -100/-999 workaround targeting this card name\n"
            f"  - Check src/ai/pokemon/biases.py for a negative card bias entry\n"
            f"  - If the card text exercises an effect not yet wired, the"
            f" scorer may fall through to a 0-baseline path"
        )
        return steps, "FAIL", patch
    steps.append(StepResult(
        "Step 3: scorer produces a usable score",
        True,
        f"{tele.scorer_kind} scorer returns max={max_score:.1f}, "
        f"avg={avg_score:.1f}, min={min_score:.1f} "
        f"({len(primary)} invocations)",
    ))

    # Step 4: evolution prereq.
    if tele.scorer_kind == "evolution":
        if tele.evolution_prereq_in_play == 0:
            steps.append(StepResult(
                "Step 4: evolution prerequisite is in play with turns_in_play>=1",
                False,
                f"Prerequisite '{tele.evolution_prereq_name}' is never in"
                f" play long enough to evolve from",
            ))
            patch = (
                f"The prerequisite Pokemon '{tele.evolution_prereq_name}' never"
                f" survives long enough for this evolution to occur. Either:\n"
                f"  - The prereq is too weak to stay benched/active for 1 turn\n"
                f"  - It's competing with other Basics for bench slots and"
                f" losing the score race\n"
                f"  - It's being KO'd before the next turn (HP too low or"
                f" wrong matchup)\n"
                f"  - Inspect choose_setup_active and _score_basic_play biases"
                f" so the prereq wins more opening Active slots"
            )
            return steps, "FAIL", patch
        steps.append(StepResult(
            "Step 4: evolution prerequisite is in play with turns_in_play>=1",
            True,
            f"'{tele.evolution_prereq_name}' was in play and eligible "
            f"on {tele.evolution_prereq_in_play} turns",
        ))

    # Step 5: energy when active (attacker check).
    # If the card actually attacked, energy was paid; no need to fail.
    if tele.scorer_kind in ("basic_play", "evolution") and tele.required_energies:
        if tele.active_turns == 0:
            steps.append(StepResult(
                "Step 5: becomes Active",
                False,
                "card never reached the Active spot, so its attack cost is moot",
            ))
            patch = (
                "Card never becomes Active. Likely losing the choose_setup_active"
                " race for opening Active OR never being chosen as the retreat-into"
                " target. Inspect:\n"
                "  - src/ai/pokemon/adapter.py::choose_setup_active for the"
                " opening-Active heuristic\n"
                "  - The bias preset's promotion-bias parameters"
            )
            return steps, "FAIL", patch
        if (tele.active_with_required_energy == 0
                and tele.times_attacked_from_active == 0):
            steps.append(StepResult(
                "Step 5: required energy attached while Active",
                False,
                f"reached Active on {tele.active_turns} turns but never had its"
                f" attack cost paid (cost: {tele.required_energies})",
            ))
            patch = (
                "Card reaches Active but never has its energy cost paid."
                " Likely causes:\n"
                "  - Energy plan bias missing — the AI is attaching energy to"
                " another Pokemon\n"
                "  - Inspect _score_energy_attachment in"
                " src/ai/pokemon/scoring.py and the active-archetype biases\n"
                "  - For mid-cost attackers, ensure the bias preset's"
                " energy_priority maps this card's type to a non-zero weight"
            )
            return steps, "FAIL", patch
        steps.append(StepResult(
            "Step 5: required energy attached while Active",
            True,
            f"Active {tele.active_turns} turns; "
            f"{tele.active_with_required_energy} of those had cost paid"
            f" (attacked {tele.times_attacked_from_active}x)",
        ))

    # Step 6: ranked below alternatives.
    # 'Played' here means anything that brings the card into the game — that
    # includes opening-Active selection (no PKM_PLAY_BASIC), real
    # PKM_PLAY_BASIC plays, supporter/item plays, and attacks. If the card
    # actually attacks at least once, it has fired regardless of bench score
    # competition.
    card_fired = (
        tele.times_played > 0
        or tele.times_attacked_from_active > 0
        or tele.active_turns > 0
    )
    if tele.ranked_below_alternatives > 0 and not card_fired:
        unique_alts = sorted(
            set((label, round(score_top, 1), round(score_target, 1))
                for label, score_top, score_target in tele.alternatives_picked[:6])
        )
        alt_summary = "\n     ".join(
            f"'{label}' (top={top}, this={tgt})" for label, top, tgt in unique_alts
        )
        steps.append(StepResult(
            "Step 6: not consistently ranked below alternatives",
            False,
            f"ranked below an alternative on "
            f"{tele.ranked_below_alternatives} turns of the same action"
            f" type; never reached play (0 plays, 0 active turns).\n"
            f"     Most common winners:\n     {alt_summary}",
        ))
        patch = (
            "Card scores positive but loses the per-turn competition for its"
            " phase slot every time. To buff its priority:\n"
            "  - Add a card-name bias entry in src/ai/pokemon/biases.py for"
            " the active preset (`apply_trainer_bias` / `apply_attack_bias`)\n"
            "  - Bump its score in src/ai/pokemon/scoring.py for the specific"
            " scorer (trainer / basic_play / evolution)\n"
            "  - If it's a utility-Basic competing with a stat-line Basic,"
            " consider adding a utility bonus akin to the Voidmage opener fix"
            " in choose_setup_active"
        )
        return steps, "FAIL", patch
    steps.append(StepResult(
        "Step 6: ranked competitively at action selection",
        True,
        f"ranked below same-type alternatives on "
        f"{tele.ranked_below_alternatives} turns; actually played "
        f"{tele.times_played}x, was Active on {tele.active_turns} turns,"
        f" attacked {tele.times_attacked_from_active}x",
    ))

    # All steps passed.
    if not card_fired:
        return (
            steps,
            "WARN",
            "All decision-tree steps pass but the card never actually played"
            " or reached play. This may indicate a deeper issue not covered"
            " by the 6-step diagnostic: try increasing --games or --max-turns,"
            " then inspect the trace by running"
            " scripts/play/brv_spice_event_trace.py.",
        )
    return steps, "PASS", "No patch needed; card fires under heuristic AI."


# =============================================================================
# Output formatting
# =============================================================================

def format_report(card_name: str, p1: str, p2: str,
                   p1_bias: str, p2_bias: str, games: int,
                   max_turns: int, elapsed: float,
                   steps: list[StepResult], verdict: str,
                   patch: str, tele: CardTelemetry) -> str:
    lines = []
    bar = "=" * 60
    lines.append(bar)
    lines.append(f"  {card_name} — DIAGNOSIS")
    lines.append(bar)
    lines.append(f"  matchup: {p1}({p1_bias}) vs {p2}({p2_bias})")
    lines.append(f"  games:   {games} (max {max_turns} turns each)")
    lines.append(f"  elapsed: {elapsed:.1f}s")
    lines.append(f"  deck presence: P1={tele.deck_count_p1}, P2={tele.deck_count_p2}")
    lines.append("")
    for st in steps:
        prefix = "[PASS]" if st.passed else "[FAIL]"
        lines.append(f"  {prefix} {st.name}")
        for sub in st.detail.split("\n"):
            lines.append(f"         {sub}")
    lines.append("")
    lines.append(f"OVERALL: {verdict}")
    lines.append("")
    lines.append("SUGGESTED PATCH:")
    for line in patch.split("\n"):
        lines.append(f"  {line}")
    lines.append(bar)
    return "\n".join(lines)


# =============================================================================
# Entry point
# =============================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True,
                        help="Card name as it appears in the card definition")
    parser.add_argument("--p1", default="dimir", help="Player 1 deck name")
    parser.add_argument("--p2", default="golgari", help="Player 2 deck name")
    parser.add_argument("--p1-bias", default="lz_engine")
    parser.add_argument("--p2-bias", default="lz_engine")
    parser.add_argument("--games", type=int, default=5)
    parser.add_argument("--max-turns", type=int, default=40)
    parser.add_argument("--engine", default=None,
                        help="Engine to use: 'pokemon' or 'scp'. If omitted, "
                             "inferred from the --p1 deck name.")
    parser.add_argument("--difficulty", default="balanced",
                        help="SCP heuristic difficulty/pilot (SCP engine only)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-essential output")
    args = parser.parse_args()

    engine = _resolve_engine(args.engine, args.p1)
    if engine not in ("pokemon", "scp"):
        print(f"Engine '{engine}' is not supported (pokemon | scp).", file=sys.stderr)
        return 2

    aggregate = CardTelemetry(card_name=args.card)
    start = time.perf_counter()

    for i in range(args.games):
        try:
            if engine == "scp":
                tele = asyncio.run(_run_scp_diagnostic_game(
                    card_name=args.card,
                    p1_deck_name=args.p1,
                    p2_deck_name=args.p2,
                    difficulty=args.difficulty,
                    max_turns=args.max_turns,
                    seed=i,
                ))
            else:
                tele = asyncio.run(_run_pokemon_diagnostic_game(
                    card_name=args.card,
                    p1_deck_name=args.p1,
                    p2_deck_name=args.p2,
                    p1_bias=args.p1_bias,
                    p2_bias=args.p2_bias,
                    max_turns=args.max_turns,
                ))
        except Exception as exc:
            print(f"Game {i+1} CRASHED: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            if not args.quiet:
                traceback.print_exc()
            continue
        if not args.quiet:
            print(f"  game {i+1}/{args.games} done "
                  f"(drawn={tele.drawn_count}, played={tele.times_played})",
                  file=sys.stderr)
        aggregate.merge(tele)

    elapsed = time.perf_counter() - start

    # Average deck count across games (single per-game value would re-add).
    if aggregate.games_run > 0:
        aggregate.deck_count_p1 = aggregate.deck_count_p1 // aggregate.games_run
        aggregate.deck_count_p2 = aggregate.deck_count_p2 // aggregate.games_run

    if engine == "scp":
        steps, verdict, patch = diagnose_scp(aggregate)
        bias_label = args.difficulty
    else:
        steps, verdict, patch = diagnose(aggregate)
        bias_label = args.p1_bias
    report = format_report(
        args.card, args.p1, args.p2,
        bias_label, args.p2_bias if engine == "pokemon" else args.difficulty,
        args.games, args.max_turns, elapsed, steps, verdict, patch, aggregate,
    )
    print(report)
    return 0 if verdict in ("PASS", "WARN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
