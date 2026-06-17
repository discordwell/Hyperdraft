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

    An SCP deck name (a key in ``src.cards.scp.decks.SCP_FOUNDATION_DECKS`` /
    ``SCP_INSURGENCY_DECKS``) implies the SCP engine; otherwise default to Pokemon
    (the historical default).
    """
    if engine:
        return engine
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        try:
            from src.cards.scp import decks as _scp_decks
            if (p1_deck in _scp_decks.SCP_FOUNDATION_DECKS
                    or p1_deck in _scp_decks.SCP_INSURGENCY_DECKS):
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
    # -- SCP-engine fields (asymmetric Foundation-vs-Insurgency engine; Pokemon path leaves at 0) --
    # "Fire" in scp = the heuristic AI actually *plays* the card in self-play (CLAUDE.md's
    # level-3 / AI-dead gate). play_card emits SCP_INSTALL for *every* kind (anomaly / layer /
    # asset / tool / operative / operation / event) carrying the card's object_id, so matching
    # that object_id back to the card name is reliable per-card attribution; activate_ability
    # emits SCP_ACTIVATE the same way. (The old symmetric-SCP ability scorer is gone.)
    scp_has_ability: bool = False        # card_def carries a callable scp_ability (asset/tool)
    scp_kind: str = ""                   # the card's scp_kind enum name (ANOMALY / OPERATION / ...)
    scp_on_battlefield_turns: int = 0    # turns a copy was a deployed permanent (sampled post-turn)
    scp_times_played: int = 0            # SCP_INSTALL events attributable to this card (deploy / resolve)
    scp_times_activated: int = 0         # SCP_ACTIVATE events attributable to this card (ability fires)

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
        self.scp_kind = self.scp_kind or other.scp_kind
        self.scp_on_battlefield_turns += other.scp_on_battlefield_turns
        self.scp_times_played += other.scp_times_played
        self.scp_times_activated += other.scp_times_activated


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

def _normalize_scp_difficulty(difficulty: str) -> str:
    """Normalize a difficulty string for the SCP engine.

    The script-wide default (``--difficulty balanced``) is Pokemon-centric, but
    ``SCPAIAdapter`` only accepts easy/medium/hard and raises on anything else — so map any
    value it would reject to ``medium``. Used both to drive the probe and to label the report,
    so the header shows the difficulty actually run.
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.ai.scp_adapter import validate_scp_difficulty
    try:
        return validate_scp_difficulty(difficulty)
    except ValueError:
        return "medium"


def _resolve_scp_matchup(p1_deck_name: str, p2_deck_name: str) -> tuple[str, str]:
    """SCP is asymmetric — order the two deck labels into (foundation, insurgency).

    Raises SystemExit with a helpful message if the pair isn't exactly one Foundation
    deck + one Insurgency deck (the only legal scp matchup).
    """
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.cards.scp import decks as D
    fdecks, idecks = D.SCP_FOUNDATION_DECKS, D.SCP_INSURGENCY_DECKS
    pair = (p1_deck_name, p2_deck_name)
    unknown = [n for n in pair if n not in fdecks and n not in idecks]
    if unknown:
        raise SystemExit(
            f"Unknown SCP deck(s): {unknown}.\n"
            f"  Foundation decks: {sorted(fdecks)}\n"
            f"  Insurgency decks: {sorted(idecks)}"
        )
    found = [n for n in pair if n in fdecks]
    insur = [n for n in pair if n in idecks]
    if len(found) != 1 or len(insur) != 1:
        raise SystemExit(
            "SCP is asymmetric — pass exactly one Foundation deck and one Insurgency "
            f"deck via --p1/--p2 (got Foundation={found}, Insurgency={insur})."
        )
    return found[0], insur[0]


async def _run_scp_diagnostic_game(
    *,
    card_name: str,
    p1_deck_name: str,
    p2_deck_name: str,
    difficulty: str,
    max_turns: int,
    seed: int,
) -> CardTelemetry:
    """Run one asymmetric SCP self-play game and return per-card *fire* telemetry.

    The current SCP engine (Foundation vs Chaos Insurgency, modeled on Netrunner) has no
    activated-ability *scorer* to instrument — that belonged to the old symmetric engine
    removed on 2026-05-31. Here "fire" means the heuristic AI actually *plays* the card in
    self-play (CLAUDE.md's level-3 / AI-dead gate). Attribution is exact: ``play_card`` emits
    ``SCP_INSTALL`` carrying the card's ``object_id`` for every kind (anomaly/layer/asset/tool/
    operative/operation/event), and ``activate_ability`` emits ``SCP_ACTIVATE`` likewise — so
    we match those payloads back to the card name. We also sample battlefield presence each
    turn (for persistent permanents) and read ``scp_ability`` off the card_def.
    """
    import random as _random
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        from src.engine.game import Game
        from src.engine.types import ZoneType
        from src.engine import scp
        from src.cards.scp import decks as D
        from src.ai.scp_adapter import SCPAIAdapter

    difficulty = _normalize_scp_difficulty(difficulty)
    foundation_label, insurgency_label = _resolve_scp_matchup(p1_deck_name, p2_deck_name)
    fident, fbuild = D.SCP_FOUNDATION_DECKS[foundation_label]
    iident, ibuild = D.SCP_INSURGENCY_DECKS[insurgency_label]
    foundation_deck, insurgency_deck = fbuild(), ibuild()

    _random.seed(seed)  # in-game choices (HQ pick / discard / damage) read the global rng too,
    #                     so seeding it makes the probe reproducible across runs.

    tele = CardTelemetry(card_name=card_name, games_run=1)
    # Report deck presence in the P1/P2 order the user typed (not foundation/insurgency).
    p1_deck = foundation_deck if p1_deck_name == foundation_label else insurgency_deck
    p2_deck = foundation_deck if p2_deck_name == foundation_label else insurgency_deck
    tele.deck_count_p1 = sum(1 for cd in p1_deck if getattr(cd, "name", "") == card_name)
    tele.deck_count_p2 = sum(1 for cd in p2_deck if getattr(cd, "name", "") == card_name)
    # Static facts about the target card (whichever deck holds it).
    for cd in (*foundation_deck, *insurgency_deck):
        if getattr(cd, "name", "") == card_name:
            tele.scp_has_ability = callable(getattr(cd, "scp_ability", None))
            kind = getattr(cd, "scp_kind", None)
            tele.scp_kind = kind.name if kind is not None else ""
            break

    game = Game(mode="scp")
    f = game.add_player("Foundation")
    i = game.add_player("Insurgency")
    scp.setup_scp_game(game, f, i, foundation_deck=foundation_deck,
                       insurgency_deck=insurgency_deck, foundation_identity=fident,
                       insurgency_identity=iident, rng=_random.Random(seed))
    # One faction-branching adapter drives both seats (matches tests/test_scp_selfplay.py,
    # the canonical scp fire gate).
    adapter = SCPAIAdapter(difficulty)
    game.turn_manager.set_ai_handler(adapter)
    game.turn_manager.set_ai_player(f.id)
    game.turn_manager.set_ai_player(i.id)

    # -- RUN GAME ------------------------------------------------------------
    all_events: list = []
    for _ in range(max_turns * 2):
        if game.is_game_over():
            break
        events = await game.turn_manager.run_turn()
        all_events.extend(events or [])
        for pid in (f.id, i.id):
            hand = [game.state.objects.get(o) for o in scp.hand_ids(game.state, pid)]
            if any(o is not None and o.name == card_name for o in hand):
                tele.drawn_count += 1
            deployed = any(
                getattr(o, "name", "") == card_name
                and o.controller == pid and o.zone == ZoneType.BATTLEFIELD
                and getattr(o.state, "scp_role", None) != "identity"
                for o in game.state.objects.values()
            )
            if deployed:
                tele.scp_on_battlefield_turns += 1

    # Attribute plays / activations from the event stream via object_id -> card name.
    for e in all_events:
        ename = e.type.name
        if ename not in ("SCP_INSTALL", "SCP_ACTIVATE"):
            continue
        oid = (e.payload or {}).get("object_id")
        obj = game.state.objects.get(oid) if oid else None
        if obj is None or getattr(obj, "name", "") != card_name:
            continue
        if ename == "SCP_INSTALL":
            tele.scp_times_played += 1
        else:
            tele.scp_times_activated += 1
    tele.times_played = tele.scp_times_played  # feed the generic main() progress line
    return tele


def diagnose_scp(tele: CardTelemetry) -> tuple[list["StepResult"], str, str]:
    """Walk the SCP fire tree against telemetry from the asymmetric engine.

    "Fire" = the heuristic AI plays the card in self-play (CLAUDE.md's level-3 / AI-dead
    gate). The steps are: in a deck → drawn → played (the fire for most cards) → and, for
    cards that carry an activated ability, also activated. This is the FIRE gate only —
    a card the AI *plays* whose effect_fn returns ``[]`` is a *level-1* (effect-dead) bug
    that /test-interceptors catches, not this tool.

    Returns (steps, verdict, patch).
    """
    steps: list[StepResult] = []
    deck_total = tele.deck_count_p1 + tele.deck_count_p2
    played = tele.scp_times_played > 0
    activated = tele.scp_times_activated > 0
    kind = tele.scp_kind or "card"

    # Step 0 — in a deck.
    if deck_total == 0:
        steps.append(StepResult("Step 0: card in deck", False,
                                "Card is in NEITHER deck. Cannot fire."))
        return steps, "FAIL", (
            "Card is not in either deck under test. Add it to a deck builder, or\n"
            "point --p1/--p2 at decks that run it, or fix the --card spelling\n"
            "(must match the CardDefinition `name` exactly).\n"
            "Note: SCP is asymmetric — one --p1/--p2 deck must be Foundation, the other Insurgency."
        )

    # Step 1 — drawn. Reaching play implies it was drawn: a card drawn-and-played in the
    # same turn is never sampled in hand post-turn, so treat play as proof it was drawn.
    reached_game = (tele.drawn_count > 0 or played or activated)
    if not reached_game:
        steps.append(StepResult("Step 1: drawn into hand at least once", False,
                                f"never drawn or played across {tele.games_run} games "
                                f"(deck count: P1={tele.deck_count_p1}, P2={tele.deck_count_p2})"))
        return steps, "FAIL", (
            "Card never entered the game (not drawn, not played). Likely causes:\n"
            f"  - Deck count too low (P1={tele.deck_count_p1}, P2={tele.deck_count_p2}) — add copies.\n"
            "  - SCP games can close fast; a 1-of can stay undrawn. Try --max-turns higher /\n"
            "    more --games. If it still never appears, the format may be too fast for it."
        )
    steps.append(StepResult("Step 1: drawn into hand at least once", True,
                            f"in hand on {tele.drawn_count} player-turns "
                            f"(deployed on {tele.scp_on_battlefield_turns} turns) "
                            f"across {tele.games_run} games"))

    # Step 2 — the AI actually plays it. This is the fire for every non-ability card.
    if not played:
        steps.append(StepResult("Step 2: played by the AI (SCP_INSTALL)", False,
                                f"drawn on {tele.drawn_count} turns but NEVER played "
                                f"(kind={kind})"))
        return steps, "FAIL", (
            f"Card is drawn but the heuristic AI never plays it (kind={kind}). This is a\n"
            "level-3 (AI-dead) gap — the effect may be correct but no decision path picks it.\n"
            "Where to look in src/ai/scp_adapter.py:\n"
            "  - Foundation cards → _foundation_action (anomalies / layers / ops / assets each\n"
            "    have a branch; a new op needs a clause that recognises and plays it).\n"
            "  - Insurgency cards → _insurgency_action (breakers / events / operatives likewise).\n"
            "  - Confirm scp_cost is affordable in the sampled games — an unaffordable card is\n"
            "    skipped, and a card the AI has no branch for is invisible even when affordable."
        )
    steps.append(StepResult("Step 2: played by the AI (SCP_INSTALL)", True,
                            f"played {tele.scp_times_played}x across {tele.games_run} games"))

    # Step 3 — for cards that carry an activated ability, the meaningful fire is activation.
    if tele.scp_has_ability:
        if activated:
            steps.append(StepResult("Step 3: activated ability fired (SCP_ACTIVATE)", True,
                                    f"activated {tele.scp_times_activated}x"))
            return steps, "PASS", "No patch needed; the AI plays and activates this card."
        steps.append(StepResult("Step 3: activated ability fired (SCP_ACTIVATE)", False,
                                f"installed {tele.scp_times_played}x but the ability never fired"))
        return steps, "WARN", (
            "The card is installed but the AI never activates its ability. Check, in order:\n"
            "  - scp_adapter calls scp.activate_ability for this asset/tool's class of effect\n"
            "    (search _foundation_action / _insurgency_action for activate_ability).\n"
            "  - Its activation cost (scp_ability_ap / scp_ability_cost) is affordable on the\n"
            "    turns it is installed.\n"
            "  - Its activation precondition (a target present, exposed>=N, ...) is ever met in\n"
            "    the sampled games — raise --games / --max-turns if it is a narrow window."
        )

    # No activated ability → played IS the fire. Done.
    steps.append(StepResult("Step 3: no activated ability (fire == play)", True,
                            f"{kind} fires by being played; no ability to activate"))
    return steps, "PASS", "No patch needed; the AI plays this card under heuristic self-play."


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
        # Show the difficulty the probe actually ran (it normalizes the Pokemon-centric
        # default 'balanced' to 'medium'), not the raw flag.
        bias_label = _normalize_scp_difficulty(args.difficulty)
    else:
        steps, verdict, patch = diagnose(aggregate)
        bias_label = args.p1_bias
    report = format_report(
        args.card, args.p1, args.p2,
        bias_label, args.p2_bias if engine == "pokemon" else bias_label,
        args.games, args.max_turns, elapsed, steps, verdict, patch, aggregate,
    )
    print(report)
    return 0 if verdict in ("PASS", "WARN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
