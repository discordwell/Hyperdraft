"""
Shared helpers for the Pokemon Beyond Ravnica spice pack v1.

These functions are the named primitives the depth scorer recognizes (see
`src/depth/engine_profiles.py:PKM_PROFILE`) and the building blocks for the
card effect_fns added in this pass. Engine-realistic — every helper maps to
existing engine state and event types.

Two categories:

1. **Action helpers** (`pkm_*`) — perform a single mechanical action and
   return the events emitted. Used inside attack effect_fns and Trainer
   resolve callbacks.

2. **Filter / count helpers** (`count_*`) — read game state and return an
   integer. Used inside effect_fns for conditional payoffs (typed-energy
   gates, evolution-stage payoffs, status-condition payoffs).
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from src.engine.pokemon_status import apply_status, remove_status
from src.engine.types import (
    CardType, Event, EventType, GameObject, GameState, PendingChoice, ZoneType,
)


# ===========================================================================
# Action helpers — modal choices, opponent-forced decisions, zone moves.
#
# All return list[Event] for pipeline-friendly composition. The "choice"
# helpers are deterministic in v1 (heuristic picks); future PR adds a
# PendingChoice path for UI/AI integration.
# ===========================================================================


def _resolve_pending_choice_inline(state: GameState) -> tuple[list[Event], list]:
    """Synchronously resolve ``state.pending_choice`` for an AI-controlled
    player.

    Returns ``(events_emitted, selected)`` so callers can read both the
    dispatcher's resulting events (for modal cards) and the raw selection
    (for target helpers that just want the picked ID back).

    Phase 1a contract: looks up the AI handler from
    ``state._game.turn_manager`` and calls ``ai.make_choice(...)``; the
    selection is then routed through ``Game._process_choice`` so the
    callback_data handler runs (mirroring MTG's session.py flow).

    For non-AI players we fall back to ``[0]`` for now; a future PR wires
    the server-side suspend/resume path so human players see the choice
    in the API response and submit it back.

    Guarantees ``state.pending_choice`` is cleared on return, even on
    handler errors, so the engine doesn't deadlock.
    """
    choice = state.pending_choice
    if choice is None:
        return [], []
    try:
        game = getattr(state, '_game', None)
        selected: list = []
        if game is not None:
            turn_mgr = getattr(game, 'turn_manager', None)
            ai_handler = getattr(turn_mgr, 'pokemon_ai_handler', None)
            ai_players = getattr(turn_mgr, 'ai_players', set()) or set()
            if ai_handler and choice.player in ai_players:
                try:
                    selected = ai_handler.make_choice(choice.player, choice, state) or []
                except Exception:
                    selected = []
        if not selected:
            # Default fallback: prefer the precomputed heuristic_pick the
            # helper stored, else first option.
            preset = (choice.callback_data or {}).get('heuristic_pick')
            if preset is None:
                selected = [0]
            elif isinstance(preset, list):
                selected = preset
            else:
                selected = [preset]
        events: list[Event] = []
        if game is not None:
            try:
                events = game._process_choice(choice, selected) or []
            except Exception:
                events = []
        else:
            # No game wiring (rare; mostly direct-resolver tests). Honor
            # the handler manually so the mode effect still runs.
            handler = (choice.callback_data or {}).get('handler')
            if handler:
                try:
                    events = handler(choice, selected, state) or []
                except Exception:
                    events = []
        return events, selected
    finally:
        state.pending_choice = None


def _pkm_modal_resolve_handler(choice: PendingChoice, selected: list, state: GameState) -> list[Event]:
    """``Game._process_choice`` dispatcher hook for ``pkm_modal_with_callback``.

    Reads the chosen mode_effects callable from ``choice.callback_data``
    and executes it. Emits one ``PKM_USE_ABILITY`` log event followed by
    the events the chosen mode produced.
    """
    if not selected:
        return []
    idx = selected[0]
    mode_effects = (choice.callback_data or {}).get('mode_effects') or ()
    if not isinstance(idx, int) or not (0 <= idx < len(mode_effects)):
        return []
    mode_name = ""
    if idx < len(choice.options):
        opt = choice.options[idx]
        if isinstance(opt, dict):
            mode_name = str(opt.get('text', f"mode_{idx}"))
    events: list[Event] = [Event(
        type=EventType.PKM_USE_ABILITY,
        payload={
            'player': choice.player,
            'mode_idx': idx,
            'mode_name': mode_name,
            'source': choice.source_id,
        },
        source=choice.source_id or None,
    )]
    try:
        extras = mode_effects[idx](state) or []
        events.extend(extras)
    except Exception:
        pass
    return events


def create_pkm_modal_choice(
    player_id: str,
    state: GameState,
    *,
    source: Optional[str],
    modes: list[dict],
    mode_effects: tuple,
    heuristic_pick: Optional[int] = None,
    prompt: str = "Choose a mode:",
) -> PendingChoice:
    """Create a Pokemon modal PendingChoice and stash it on ``state``.

    ``modes`` is a parallel list to ``mode_effects`` — each entry is a dict
    like ``{"index": 0, "text": "Draw 3"}`` for display. The choice's
    ``callback_data`` carries:

    - ``handler``: ``_pkm_modal_resolve_handler`` (the dispatcher hook)
    - ``mode_effects``: the parallel tuple of callables
    - ``heuristic_pick`` (optional): the AI's default pick if no policy
      runs

    Does NOT immediately resolve — callers either invoke
    ``_resolve_pending_choice_inline(state)`` themselves or rely on the
    enclosing turn-manager site (``_play_trainer``) to resolve.
    """
    choice = PendingChoice(
        choice_type="pkm_modal_with_callback",
        player=player_id,
        prompt=prompt,
        options=list(modes),
        source_id=source or "",
        min_choices=1,
        max_choices=1,
    )
    choice.callback_data['mode_effects'] = mode_effects
    choice.callback_data['handler'] = _pkm_modal_resolve_handler
    if heuristic_pick is not None:
        choice.callback_data['heuristic_pick'] = heuristic_pick
    state.pending_choice = choice
    return choice


def pkm_modal_choice(
    player_id: str,
    state: GameState,
    *,
    source: Optional[str] = None,
    mode_names: tuple[str, ...] = (),
    mode_effects: tuple[Callable[[GameState], list[Event]], ...] = (),
    heuristic_pick: Optional[int] = None,
) -> list[Event]:
    """Resolve a modal "choose one" effect for `player_id`.

    Phase 1a (post-PendingChoice): now creates a real PendingChoice via
    ``create_pkm_modal_choice`` and synchronously resolves it through
    ``Game._process_choice``. AI players consult ``ai.make_choice`` to
    pick the mode; if no AI handler is wired (tests, direct calls), we
    fall back to ``heuristic_pick`` (if provided) or mode 0.

    Returns the events emitted by the chosen mode. The signature is
    unchanged from v1 so all 14 spice-card callers keep working.
    """
    if not mode_effects:
        return []
    modes: list[dict] = []
    for i, name in enumerate(mode_names or ()):
        modes.append({"index": i, "text": str(name)})
    while len(modes) < len(mode_effects):
        modes.append({"index": len(modes), "text": f"mode_{len(modes)}"})
    create_pkm_modal_choice(
        player_id, state,
        source=source,
        modes=modes,
        mode_effects=mode_effects,
        heuristic_pick=heuristic_pick,
    )
    events, _selected = _resolve_pending_choice_inline(state)
    return events


def _resolve_target_choice_now(
    state: GameState,
    *,
    chooser_id: str,
    options: list,
    heuristic_pick,
    source: Optional[str] = None,
    prompt: str = "Choose a target:",
    min_choices: int = 1,
    max_choices: int = 1,
):
    """Build a ``pkm_target_choice`` PendingChoice from ``options`` and
    immediately resolve it. Returns the AI/heuristic-selected value(s).

    The selection format matches the input shape:
    - ``options`` is a list of target IDs / option strings.
    - ``heuristic_pick`` is the helper's default pick (single value or
      list). It's stored in callback_data so the dispatcher can honor it
      when the AI doesn't override.
    - Returns the first selected option (single-pick) or the list of
      selections (multi-pick) depending on ``max_choices``.

    Single-pick callers should pass ``max_choices=1`` and read the
    return as the single selected value. Multi-pick callers should pass
    ``max_choices=n`` and read the full list.
    """
    if not options:
        return None if max_choices == 1 else []
    choice = PendingChoice(
        choice_type="pkm_target_choice",
        player=chooser_id,
        prompt=prompt,
        options=list(options),
        source_id=source or "",
        min_choices=min_choices,
        max_choices=max_choices,
    )
    choice.callback_data['heuristic_pick'] = heuristic_pick
    state.pending_choice = choice
    _events, selected = _resolve_pending_choice_inline(state)
    if max_choices == 1:
        return selected[0] if selected else None
    return list(selected)


def pkm_force_opp_choose_bench(
    opp_id: str,
    state: GameState,
    *,
    source: Optional[str] = None,
) -> Optional[str]:
    """Opponent picks one of their Benched Pokemon (against their interest).

    Phase 1a: creates a ``pkm_target_choice`` PendingChoice. The chooser
    is ``opp_id`` (per real rules — the opponent picks), but the
    heuristic_pick is "the bench Pokemon with the highest investment"
    (the one opp would naturally NOT want to lose). AI's make_choice can
    override this — useful for opp-pilot strategies that want to
    sandbag here.
    """
    bench = state.zones.get(f"bench_{opp_id}")
    if not bench or not bench.objects:
        return None
    candidates = []
    for bid in bench.objects:
        if not bid:
            continue
        obj = state.objects.get(bid)
        if not obj or not obj.card_def:
            continue
        investment = (
            len(getattr(obj.state, 'attached_energy', []) or []) * 10
            + (obj.card_def.hp or 0) - (getattr(obj.state, 'damage_counters', 0) * 10)
        )
        candidates.append((investment, bid))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return _resolve_target_choice_now(
        state, chooser_id=opp_id, options=[bid for _, bid in candidates],
        heuristic_pick=candidates[0][1], source=source,
        prompt="Choose a Benched Pokemon to bring up:",
    )


def pkm_choose_pokemon_target(
    state: GameState,
    *,
    controller: str,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
    prefer_active: bool = True,
    chooser_id: Optional[str] = None,
) -> Optional[str]:
    """Pick a Pokemon owned by ``controller`` matching ``filter_fn``.

    Phase 1a: creates a ``pkm_target_choice`` PendingChoice. ``chooser_id``
    defaults to ``controller`` (the controller of the candidate Pokemon
    is also the player choosing — own-Pokemon target). For
    cross-controller targets (opp Pokemon), pass ``chooser_id`` explicitly.

    v1 heuristic preserved: prefer Active if it matches, else first
    matching Bench Pokemon.
    """
    candidates: list[str] = []
    active_id = None
    active = state.zones.get(f"active_spot_{controller}")
    if active and active.objects:
        cand = active.objects[0]
        obj = state.objects.get(cand)
        if obj and (filter_fn is None or filter_fn(obj, state)):
            active_id = cand
            candidates.append(cand)
    bench = state.zones.get(f"bench_{controller}")
    if bench:
        for bid in bench.objects:
            if not bid:
                continue
            obj = state.objects.get(bid)
            if obj and (filter_fn is None or filter_fn(obj, state)):
                if bid not in candidates:
                    candidates.append(bid)
    if not candidates:
        return None
    heuristic = active_id if (prefer_active and active_id) else candidates[0]
    return _resolve_target_choice_now(
        state, chooser_id=chooser_id or controller, options=candidates,
        heuristic_pick=heuristic,
        prompt="Choose a Pokemon target:",
    )


def pkm_target_card_in_hand_choice(
    state: GameState,
    *,
    target_controller: str,
    card_type_filter: Optional[CardType] = None,
    chooser_id: Optional[str] = None,
) -> Optional[str]:
    """Pick a card in ``target_controller``'s hand matching ``card_type_filter``.

    Phase 1a: creates a ``pkm_target_choice`` PendingChoice. ``chooser_id``
    is the player making the decision — for hand-disruption (Jace, Dimir
    Interrogation, Tezzy's Test mode 3) the chooser is the source's
    controller, NOT ``target_controller``. Falls back to
    ``state.active_player`` if not given (the active turn's player), and
    finally to ``target_controller`` if active_player is also missing.

    v1 heuristic preserved: pick the first matching card (which by hand
    order tends to be the most-recently-drawn).
    """
    hand = state.zones.get(f"hand_{target_controller}")
    if not hand or not hand.objects:
        return None
    candidates: list[str] = []
    for cid in hand.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if card_type_filter is not None and card_type_filter not in obj.characteristics.types:
            continue
        candidates.append(cid)
    if not candidates:
        return None
    chooser = chooser_id or getattr(state, 'active_player', None) or target_controller
    return _resolve_target_choice_now(
        state, chooser_id=chooser, options=candidates,
        heuristic_pick=candidates[0],
        prompt=f"Choose a card from {target_controller}'s hand:",
    )


def pkm_choose_from_hand_n(
    state: GameState,
    *,
    controller: str,
    n: int,
    filter_fn: Optional[Callable[[GameObject, GameState], bool]] = None,
) -> list[str]:
    """Pick up to ``n`` cards from ``controller``'s hand.

    Phase 1a: creates a ``pkm_target_choice`` PendingChoice with
    ``max_choices=n``. v1 heuristic preserved: pick matching cards in
    hand order (used by Cremate to feed the Lost Zone). AI's
    make_choice can override per Phase 2 / pilot policy.
    """
    hand = state.zones.get(f"hand_{controller}")
    if not hand:
        return []
    candidates: list[str] = []
    for cid in hand.objects:
        obj = state.objects.get(cid)
        if not obj:
            continue
        if filter_fn is not None and not filter_fn(obj, state):
            continue
        candidates.append(cid)
    if not candidates:
        return []
    heuristic = candidates[:n]
    result = _resolve_target_choice_now(
        state, chooser_id=controller, options=candidates,
        heuristic_pick=heuristic, prompt=f"Choose up to {n} cards from your hand:",
        min_choices=0, max_choices=n,
    )
    return list(result) if result else []


def pkm_move_to_lost_zone(card_id: str, state: GameState, *, source: Optional[str] = None) -> list[Event]:
    """Move a card to the shared Lost Zone. Returns the events emitted.

    Lost Zone is a one-way exile — cards moved here cannot return to any
    other zone. Engine has `state.zones['lost_zone']` as a shared zone.
    """
    card = state.objects.get(card_id)
    if not card:
        return []
    lost = state.zones.get('lost_zone')
    if lost is None:
        return []
    # Find and remove from current zone.
    current_zone_key = _find_zone_containing(state, card_id)
    if current_zone_key:
        current = state.zones[current_zone_key]
        if card_id in current.objects:
            current.objects.remove(card_id)
    # Also clear from any attached_energy/attached_tools list if it's an energy/tool.
    for obj in state.objects.values():
        if hasattr(obj, 'state'):
            attached = getattr(obj.state, 'attached_energy', None)
            if attached and card_id in attached:
                attached.remove(card_id)
    lost.objects.append(card_id)
    card.zone = ZoneType.LOST_ZONE
    return [Event(
        type=EventType.PKM_LOST_ZONE,
        payload={'card_id': card_id, 'source': source, 'controller_of_card': card.controller},
        source=source,
    )]


def pkm_apply_prize_tax(
    opp_id: str,
    state: GameState,
    *,
    amount: int = 1,
    duration: str = "next_ko",
    source: Optional[str] = None,
) -> list[Event]:
    """Mark `opp_id`'s next prize-draw event to take `amount` fewer prizes.

    Implementation: writes `state.players[opp_id].prize_tax = amount` (new
    int field, defaulted to 0). Pokemon's combat module's prize-take logic
    will need to consume this — for v1 we just write the marker so the AI
    sees it; engine consumption is wired in a follow-up.
    """
    player = state.players.get(opp_id)
    if not player:
        return []
    current_tax = getattr(player, 'prize_tax', 0) or 0
    setattr(player, 'prize_tax', current_tax + amount)
    return [Event(
        type=EventType.PKM_PRIZE_TAX,
        payload={'target_player': opp_id, 'amount': amount, 'duration': duration, 'source': source},
        source=source,
    )]


def pkm_skip_evolution_stage(
    state: GameState,
    *,
    basic_id: str,
    evolution_card_def,
    source: Optional[str] = None,
) -> list[Event]:
    """Rare-Candy-style: evolve a Basic directly to a Stage 2 (skipping Stage 1).

    Replaces the Basic Pokemon's card_def with `evolution_card_def`,
    preserving attached energy / damage counters. Emits PKM_EVOLVE.
    """
    basic = state.objects.get(basic_id)
    if not basic:
        return []
    basic.card_def = evolution_card_def
    basic.name = evolution_card_def.name
    if evolution_card_def.characteristics:
        basic.characteristics = evolution_card_def.characteristics
    # Status conditions clear on evolve (per real rules).
    if hasattr(basic.state, 'status_conditions'):
        basic.state.status_conditions = set()
    return [Event(
        type=EventType.PKM_EVOLVE,
        payload={'pokemon_id': basic_id, 'to_name': evolution_card_def.name,
                 'skipped_stage': True, 'source': source},
        source=source,
    )]


def pkm_force_switch_opp(
    opp_id: str,
    state: GameState,
    *,
    new_active_id: str,
    source: Optional[str] = None,
) -> list[Event]:
    """Force opp to switch their Active with `new_active_id` (a Bench Pokemon).

    Used by Boss's-Orders-style effects and the build-around build-around
    cards (Niv-Mizzet's Quandary). Removes status conditions from the
    incoming active per real rules.
    """
    active_zone = state.zones.get(f"active_spot_{opp_id}")
    bench = state.zones.get(f"bench_{opp_id}")
    if not active_zone or not bench:
        return []
    if not active_zone.objects or new_active_id not in bench.objects:
        return []
    old_active_id = active_zone.objects[0]
    # Swap.
    active_zone.objects[0] = new_active_id
    bench.objects.remove(new_active_id)
    bench.objects.append(old_active_id)
    # Zone-attr updates.
    new_active = state.objects.get(new_active_id)
    old_active = state.objects.get(old_active_id)
    if new_active:
        new_active.zone = ZoneType.ACTIVE_SPOT
        # Status conditions clear on retreat-to-bench per real rules.
    if old_active:
        old_active.zone = ZoneType.BENCH
        if hasattr(old_active.state, 'status_conditions'):
            old_active.state.status_conditions = set()
    return [Event(
        type=EventType.PKM_FORCE_SWITCH,
        payload={'target_player': opp_id, 'new_active': new_active_id,
                 'previous_active': old_active_id, 'source': source},
        source=source,
    )]


def pkm_reveal_opp_hand(opp_id: str, state: GameState, *, source: Optional[str] = None) -> list[Event]:
    """Force opponent to reveal their hand. Information asymmetry signal.

    Engine doesn't currently track "revealed" cards persistently — the
    information is available to the card's effect_fn at resolution time,
    but doesn't leak to subsequent turns. PKM_REVEAL_HAND event is emitted
    for log/AI consumption.
    """
    hand = state.zones.get(f"hand_{opp_id}")
    if not hand:
        return []
    revealed_ids = list(hand.objects)
    return [Event(
        type=EventType.PKM_REVEAL_HAND,
        payload={'target_player': opp_id, 'revealed_card_ids': revealed_ids, 'source': source},
        source=source,
    )]


def pkm_move_energy(
    energy_id: str,
    *,
    new_pokemon_id: str,
    state: GameState,
    source: Optional[str] = None,
) -> list[Event]:
    """Move an Energy card from its current Pokemon to `new_pokemon_id`.

    Used by Niv-Mizzet's Quandary (cross-controller energy re-distribution).
    """
    energy = state.objects.get(energy_id)
    new_holder = state.objects.get(new_pokemon_id)
    if not energy or not new_holder:
        return []
    # Find current holder.
    current_holder_id = None
    for obj in state.objects.values():
        attached = getattr(getattr(obj, 'state', None), 'attached_energy', None)
        if attached and energy_id in attached:
            current_holder_id = obj.id
            attached.remove(energy_id)
            break
    new_attached = getattr(new_holder.state, 'attached_energy', None)
    if new_attached is None:
        return []
    new_attached.append(energy_id)
    return [Event(
        type=EventType.PKM_MOVE_ENERGY,
        payload={'energy_id': energy_id, 'from_pokemon': current_holder_id,
                 'to_pokemon': new_pokemon_id, 'source': source},
        source=source,
    )]


# ===========================================================================
# Filter / count helpers — read state, return int. Recognized by the
# depth scorer as filter_factories, which contribute to Synergy Hook.
# ===========================================================================


def count_pokemon_by_stage(controller: str, stage: str, state: GameState) -> int:
    """Count Pokemon controlled by `controller` whose evolution_stage matches.

    `stage` is one of "Basic", "Stage 1", "Stage 2".
    """
    n = 0
    for zone_key in (f"active_spot_{controller}", f"bench_{controller}"):
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for obj_id in zone.objects:
            if not obj_id:
                continue
            obj = state.objects.get(obj_id)
            if obj and obj.card_def and getattr(obj.card_def, 'evolution_stage', None) == stage:
                n += 1
    return n


def count_pokemon_in_play(controller: str, state: GameState) -> int:
    """Count Pokemon controlled by `controller` in Active + Bench."""
    n = 0
    for zone_key in (f"active_spot_{controller}", f"bench_{controller}"):
        zone = state.zones.get(zone_key)
        if zone:
            n += sum(1 for o in zone.objects if o)
    return n


def count_typed_energy_attached(pokemon_id: str, energy_type: str, state: GameState) -> int:
    """Count attached Energy of `energy_type` (e.g. "R", "W") on a Pokemon."""
    pokemon = state.objects.get(pokemon_id)
    if not pokemon:
        return 0
    n = 0
    for eid in getattr(pokemon.state, 'attached_energy', []) or []:
        energy = state.objects.get(eid)
        if not energy or not energy.card_def:
            continue
        if getattr(energy.card_def, 'pokemon_type', None) == energy_type:
            n += 1
    return n


def count_typed_energy_in_hand(controller: str, energy_type: str, state: GameState) -> int:
    """Count typed Energy cards in controller's hand."""
    hand = state.zones.get(f"hand_{controller}")
    if not hand:
        return 0
    n = 0
    for cid in hand.objects:
        obj = state.objects.get(cid)
        if not obj or not obj.characteristics:
            continue
        if CardType.ENERGY not in obj.characteristics.types:
            continue
        if obj.card_def and getattr(obj.card_def, 'pokemon_type', None) == energy_type:
            n += 1
    return n


def count_poisoned_pokemon(controller: str, state: GameState) -> int:
    """Count `controller`'s Pokemon (Active+Bench) currently Poisoned."""
    n = 0
    for zone_key in (f"active_spot_{controller}", f"bench_{controller}"):
        zone = state.zones.get(zone_key)
        if not zone:
            continue
        for obj_id in zone.objects:
            if not obj_id:
                continue
            obj = state.objects.get(obj_id)
            if obj and 'poisoned' in (getattr(obj.state, 'status_conditions', None) or set()):
                n += 1
    return n


def count_pokemon_in_lost_zone(controller: str, state: GameState) -> int:
    """Count cards in the shared Lost Zone originally owned by `controller`.

    The Lost Zone is shared; we filter by `card.controller` (the player who
    sent the card there OR who owned it originally — we use the latter).
    """
    lost = state.zones.get('lost_zone')
    if not lost:
        return 0
    n = 0
    for cid in lost.objects:
        obj = state.objects.get(cid)
        if obj and obj.controller == controller:
            n += 1
    return n


# ===========================================================================
# Internal utilities.
# ===========================================================================


def _find_zone_containing(state: GameState, card_id: str) -> Optional[str]:
    """Find the zone key that currently contains `card_id`."""
    for key, zone in state.zones.items():
        if card_id in zone.objects:
            return key
    return None


def _get_opp_id(player_id: str, state: GameState) -> Optional[str]:
    return next((p for p in state.players if p != player_id), None)


def _get_opp_active(opp_id: str, state: GameState) -> Optional[GameObject]:
    """Convenience: get the GameObject sitting on opp's Active spot."""
    zone = state.zones.get(f"active_spot_{opp_id}")
    if not zone or not zone.objects:
        return None
    return state.objects.get(zone.objects[0])


def _place_damage_counters_on_opp_active(
    state: GameState,
    *,
    attacker_controller: str,
    counters: int,
    source: Optional[str] = None,
) -> list[Event]:
    """Emit a PKM_PLACE_DAMAGE_COUNTERS targeting opp Active. Cross-controller helper."""
    opp_id = _get_opp_id(attacker_controller, state)
    if not opp_id:
        return []
    target = _get_opp_active(opp_id, state)
    if not target:
        return []
    target.state.damage_counters = getattr(target.state, 'damage_counters', 0) + counters
    return [Event(
        type=EventType.PKM_PLACE_DAMAGE_COUNTERS,
        payload={'pokemon_id': target.id, 'counters': counters, 'source': source},
        source=source,
    )]


def discard_attached_energy_cross_ctrl(
    state: GameState,
    *,
    target_pokemon_id: str,
    count: int = 1,
    source: Optional[str] = None,
) -> list[Event]:
    """Cross-controller-friendly variant of the existing `_discard_attached_energy`
    pattern. Discards `count` energy cards from `target_pokemon_id` (which may
    be on either side of the table) and emits PKM_DISCARD_ENERGY events.

    Owner of the energy card determines which graveyard receives the energy.
    """
    target = state.objects.get(target_pokemon_id)
    if not target:
        return []
    events: list[Event] = []
    discarded = 0
    for energy_id in list(getattr(target.state, 'attached_energy', []) or []):
        if discarded >= count:
            break
        target.state.attached_energy.remove(energy_id)
        energy_obj = state.objects.get(energy_id)
        if energy_obj:
            grave = state.zones.get(f"graveyard_{energy_obj.controller}")
            if grave:
                grave.objects.append(energy_id)
            energy_obj.zone = ZoneType.GRAVEYARD
        discarded += 1
        events.append(Event(
            type=EventType.PKM_DISCARD_ENERGY,
            payload={'pokemon_id': target_pokemon_id, 'energy_id': energy_id, 'source': source},
            source=source,
        ))
    return events
