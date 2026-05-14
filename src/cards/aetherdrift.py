"""
Aetherdrift (DFT) Card Implementations

Real card data fetched from Scryfall API.
276 cards in set.
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_enchantment_creature,
    make_instant,
    make_land,
    make_planeswalker,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, create_target_choice, create_modal_choice,
    make_cycling_setup, make_exhaust_ability,
    make_activate_exhaust_trigger, make_activated_cost_reduction,
    make_animate_via_exhaust, make_attack_trigger,
    make_exhaust_reset_effect, make_upkeep_trigger,
    make_activated_ability,
    # Phase 5b: normalize Target object / raw ID inputs from resolve fns
    normalize_target,
    # Modal helper + ModeSpec
    make_modal_resolve, ModeSpec,
)
import re

# Phase 5b cast-time target requirements
from src.engine.targeting import (
    target_creature, target_any, target_player, target_spell,
    TargetRequirement, TargetFilter, creature_filter, permanent_filter,
    spell_filter, card_in_graveyard_filter,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

def perilous_snare_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """
    O-Ring style effect:
    When this artifact enters, exile target nonland permanent an opponent controls
    until this artifact leaves the battlefield.

    Uses the player choice system for target selection.
    """
    # Use a mutable container to track the exiled card ID across closures
    exiled_card = {'id': None}

    def get_legal_targets(state: GameState) -> list[str]:
        """Get all legal targets: opponent's nonland permanents."""
        targets = []
        for obj_id, game_obj in state.objects.items():
            # Must be on battlefield, controlled by opponent, and nonland
            if game_obj.zone != ZoneType.BATTLEFIELD:
                continue
            if game_obj.controller == obj.controller:
                continue
            if CardType.LAND in game_obj.characteristics.types:
                continue
            targets.append(obj_id)
        return targets

    def handle_target_choice(choice, selected: list, game_state: GameState) -> list[Event]:
        """Handler called when player selects a target."""
        if not selected:
            return []

        target_id = selected[0]

        # Store the exiled card ID for the leaves-battlefield trigger
        exiled_card['id'] = target_id

        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.EXILE,
                'exiled_by': obj.id  # Track which card exiled this
            },
            source=obj.id,
            controller=obj.controller
        )]

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        """When Perilous Snare enters, create target choice for nonland permanent an opponent controls."""
        legal_targets = get_legal_targets(state)
        if not legal_targets:
            # No legal targets, effect fizzles
            return []

        # Create the target choice - this pauses the game for player input
        create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=legal_targets,
            prompt="Choose a nonland permanent an opponent controls to exile",
            min_targets=1,
            max_targets=1,
            callback_data={'handler': handle_target_choice}
        )

        # Return empty events to pause and wait for player choice
        return []

    def leaves_battlefield_filter(event: Event, state: GameState) -> bool:
        """Filter for when Perilous Snare leaves the battlefield."""
        return (event.type == EventType.ZONE_CHANGE and
                event.payload.get('object_id') == obj.id and
                event.payload.get('from_zone_type') == ZoneType.BATTLEFIELD)

    def leaves_battlefield_effect(event: Event, state: GameState) -> list[Event]:
        """When Perilous Snare leaves, return the exiled card to the battlefield."""
        if not exiled_card['id']:
            return []

        # Check if the exiled card still exists and is in exile
        exiled_obj = state.objects.get(exiled_card['id'])
        if not exiled_obj or exiled_obj.zone != ZoneType.EXILE:
            return []

        return [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': exiled_card['id'],
                'from_zone_type': ZoneType.EXILE,
                'to_zone_type': ZoneType.BATTLEFIELD
            },
            source=obj.id,
            controller=obj.controller
        )]

    # Create the ETB trigger
    etb_trigger = make_etb_trigger(obj, etb_effect)

    # Create the leaves-battlefield trigger
    # This trigger needs to persist even after the source leaves (duration='until_leaves')
    leaves_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=leaves_battlefield_filter,
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=leaves_battlefield_effect(e, s)
        ),
        duration='until_leaves'  # Stays registered to fire after leaving
    )

    return [etb_trigger, leaves_trigger]


# =============================================================================
# EXHAUST SETUP FUNCTIONS
# =============================================================================
#
# Exhaust is a once-per-game activated ability. The mechanic is wired through
# ``make_exhaust_ability`` (interceptor_helpers) which sets ``once_per_game``
# on the resulting ActivatedAbility — once activated, the ability is gone for
# good on that specific permanent. Re-entering the battlefield (a fresh GameObject)
# starts a new copy from scratch.

def _emit_self_counters(obj: GameObject, amount: int) -> list[Event]:
    """Helper: put N +1/+1 counters on self."""
    return [Event(
        type=EventType.COUNTER_ADDED,
        payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': amount},
        source=obj.id, controller=obj.controller,
    )]


def _emit_create_token(
    obj: GameObject,
    *,
    name: str,
    power: int,
    toughness: int,
    subtypes: set,
    colors: set,
    keywords: list,
    is_artifact: bool = False,
) -> Event:
    """Helper: create a creature token with the given characteristics."""
    types = {CardType.CREATURE}
    if is_artifact:
        types.add(CardType.ARTIFACT)
    return Event(
        type=EventType.OBJECT_CREATED,
        payload={
            'name': name,
            'controller': obj.controller,
            'owner': obj.controller,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'types': types,
            'subtypes': set(subtypes),
            'colors': set(colors),
            'power': power,
            'toughness': toughness,
            'abilities': list(keywords),
            'is_token': True,
        },
        source=obj.id, controller=obj.controller,
    )


def keen_buccaneer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {1}{U}: Loot + put a +1/+1 counter on this creature."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(type=EventType.DRAW,
                  payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller),
            Event(type=EventType.DISCARD_CHOICE,
                  payload={'player': o.controller, 'count': 1},
                  source=o.id, controller=o.controller),
            *_emit_self_counters(o, 1),
        ]
    make_exhaust_ability(
        obj, cost="{1}{U}", effect_fn=_effect,
        description="{1}{U}: Draw a card, then discard a card. Put a +1/+1 counter on this creature.",
    )
    return []


def skystreak_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {4}{U}: Put two +1/+1 counters on this creature."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return _emit_self_counters(o, 2)
    make_exhaust_ability(
        obj, cost="{4}{U}", effect_fn=_effect,
        description="{4}{U}: Put two +1/+1 counters on this creature.",
    )
    return []


def pacesetter_paragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {2}{R}: +1/+1 counter and double strike until end of turn."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            *_emit_self_counters(o, 1),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': o.id, 'keyword': 'double strike',
                         'duration': 'end_of_turn'},
                source=o.id, controller=o.controller,
            ),
        ]
    make_exhaust_ability(
        obj, cost="{2}{R}", effect_fn=_effect,
        description="{2}{R}: Put a +1/+1 counter on this creature. It gains double strike until end of turn.",
    )
    return []


def prowcatcher_specialist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {3}{R}: Put two +1/+1 counters on this creature."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return _emit_self_counters(o, 2)
    make_exhaust_ability(
        obj, cost="{3}{R}", effect_fn=_effect,
        description="{3}{R}: Put two +1/+1 counters on this creature.",
    )
    return []


def hazard_of_the_dunes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {6}{G}: Put three +1/+1 counters on this creature."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return _emit_self_counters(o, 3)
    make_exhaust_ability(
        obj, cost="{6}{G}", effect_fn=_effect,
        description="{6}{G}: Put three +1/+1 counters on this creature.",
    )
    return []


def stampeding_scurryfoot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {3}{G}: +1/+1 counter and create a 3/3 green Elephant token."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            *_emit_self_counters(o, 1),
            _emit_create_token(
                o, name="Elephant", power=3, toughness=3,
                subtypes={"Elephant"}, colors={Color.GREEN}, keywords=[],
            ),
        ]
    make_exhaust_ability(
        obj, cost="{3}{G}", effect_fn=_effect,
        description="{3}{G}: Put a +1/+1 counter on this creature. Create a 3/3 green Elephant creature token.",
    )
    return []


def camera_launcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {3}: +1/+1 counter and create a 1/1 colorless Thopter token with flying."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            *_emit_self_counters(o, 1),
            _emit_create_token(
                o, name="Thopter", power=1, toughness=1,
                subtypes={"Thopter"}, colors=set(), keywords=["flying"],
                is_artifact=True,
            ),
        ]
    make_exhaust_ability(
        obj, cost="{3}", effect_fn=_effect,
        description="{3}: Put a +1/+1 counter on this creature. Create a 1/1 colorless Thopter artifact creature token with flying.",
    )
    return []


# -----------------------------------------------------------------------------
# Exhaust-ecosystem cards (W2 engine extension)
# -----------------------------------------------------------------------------


def boom_scholar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Boom Scholar.

    Static: Exhaust abilities of OTHER permanents you control cost {2} less to
    activate. (Coloured pips never reduce.)

    Plus its own Exhaust — {4}{R}{G}: Creatures and Vehicles you control gain
    trample until end of turn. Put two +1/+1 counters on this creature.
    """
    obj_id = obj.id
    obj_controller = obj.controller

    def _applies(ability, src, st: GameState) -> bool:
        # Reduce only Exhaust abilities of OTHER permanents I control.
        if ability is None or src is None:
            return False
        if not getattr(ability, 'is_exhaust', False):
            return False
        if getattr(src, 'id', None) == obj_id:
            return False  # Don't reduce own Exhaust ability.
        if getattr(src, 'controller', None) != obj_controller:
            return False
        return True

    def _exhaust_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events: list[Event] = []
        for other_id, other in st.objects.items():
            if other.zone != ZoneType.BATTLEFIELD:
                continue
            if other.controller != o.controller:
                continue
            if (CardType.CREATURE in other.characteristics.types or
                    'Vehicle' in other.characteristics.subtypes):
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': other_id, 'keyword': 'trample',
                             'duration': 'end_of_turn'},
                    source=o.id, controller=o.controller,
                ))
        events.extend(_emit_self_counters(o, 2))
        return events

    make_exhaust_ability(
        obj, cost="{4}{R}{G}", effect_fn=_exhaust_effect,
        description="{4}{R}{G}: Creatures and Vehicles you control gain trample until end of turn. Put two +1/+1 counters on this creature.",
    )

    return [make_activated_cost_reduction(
        obj, amount=2, applies_filter=_applies,
    )]


def afterburner_expert_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Afterburner Expert (battlefield half) — Exhaust: +1/+1 counters x2."""
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return _emit_self_counters(o, 2)
    make_exhaust_ability(
        obj, cost="{2}{G}{G}", effect_fn=_effect,
        description="{2}{G}{G}: Put two +1/+1 counters on this creature.",
    )
    return []


def riverchurn_monument_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {2}{U}{U}, {T}: Each opponent mills cards equal to their graveyard size.

    Card text says "Any number of target players each mill cards equal to the
    number of cards in their graveyard." We approximate with each-opponent
    targeting since target-multiselect-of-players isn't a clean fit for the
    activated-ability surface; this preserves the most useful combat case
    (mill all opponents). The {1}, {T} non-Exhaust ability remains unwired.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events: list[Event] = []
        for opp_id, opp in st.players.items():
            if opp_id == o.controller:
                continue
            gy_zone = st.zones.get(f'graveyard_{opp_id}')
            mill_count = len(gy_zone.objects) if gy_zone else 0
            if mill_count > 0:
                events.append(Event(
                    type=EventType.MILL,
                    payload={'player': opp_id, 'amount': mill_count},
                    source=o.id, controller=o.controller,
                ))
        return events

    make_exhaust_ability(
        obj, cost="{2}{U}{U}, {T}", effect_fn=_effect,
        description="{2}{U}{U}, {T}: Each opponent mills cards equal to the number of cards in their graveyard.",
    )
    return []


def afterburner_expert_in_graveyard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Afterburner Expert (graveyard half).

    "Whenever you activate an exhaust ability, return Afterburner Expert from
    your graveyard to the battlefield."

    Returns an interceptor that fires on any exhaust activation by the card's
    controller while this card is in the graveyard.
    """
    def _trigger_effect(event: Event, st: GameState) -> list[Event]:
        # Defensive: fire only if the source object still exists and is in GY.
        current = st.objects.get(obj.id)
        if current is None or current.zone != ZoneType.GRAVEYARD:
            return []
        return [Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': obj.id,
                'controller': obj.controller,
                'player': obj.controller,
                'destination': 'battlefield',
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [make_activate_exhaust_trigger(
        obj, _trigger_effect,
        controller_only=True,
        while_in_zone=ZoneType.GRAVEYARD,
    )]


def rangers_refueler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rangers' Refueler.

    Trigger: "Whenever you activate an exhaust ability, draw a card."
    Plus Exhaust — {4}: This Vehicle becomes an artifact creature with base
    3/3 P/T until end of turn, then put a +1/+1 counter on it.
    """

    def _draw(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    make_animate_via_exhaust(
        obj, cost="{4}", power=3, toughness=3, plus_one_counters=1,
    )
    return [make_activate_exhaust_trigger(obj, _draw, controller_only=True)]


def greasewrench_goblin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {2}{R}: Discard up to two cards, then draw that many cards.
    Put a +1/+1 counter on this creature.

    Implementation: open a discard PendingChoice with min=0, max=2 over the
    controller's hand. The handler emits one DISCARD event per selected card
    plus a DRAW for that count, plus a +1/+1 counter on the source.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        from src.engine.types import PendingChoice
        hand = st.zones.get(f'hand_{o.controller}')
        hand_ids = list(hand.objects) if hand else []
        max_discard = min(2, len(hand_ids))

        # If the player has no cards, just emit the +1/+1 counter rider.
        if max_discard == 0:
            return [*_emit_self_counters(o, 1)]

        def _on_discard(choice, selected, gs: GameState) -> list[Event]:
            count = len(selected or [])
            evs: list[Event] = []
            for cid in (selected or []):
                evs.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': o.controller, 'object_id': cid},
                    source=o.id, controller=o.controller,
                ))
            if count > 0:
                evs.append(Event(
                    type=EventType.DRAW,
                    payload={'player': o.controller, 'count': count},
                    source=o.id, controller=o.controller,
                ))
            # +1/+1 counter rider always fires.
            evs.extend(_emit_self_counters(o, 1))
            return evs

        st.pending_choice = PendingChoice(
            choice_type="discard",
            player=o.controller,
            prompt="Discard up to two cards (Greasewrench Goblin):",
            options=hand_ids,
            source_id=o.id,
            min_choices=0,
            max_choices=max_discard,
            callback_data={'handler': _on_discard},
        )
        return []

    make_exhaust_ability(
        obj, cost="{2}{R}", effect_fn=_effect,
        description="{2}{R}: Discard up to two cards, then draw that many cards. Put a +1/+1 counter on this creature.",
    )
    return []


def skyserpent_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {4}: Reveal cards from the top of your library until you reveal two
    land cards. Put those land cards onto the battlefield tapped and the rest on the
    bottom of your library in a random order. Put a +1/+1 counter on this creature.

    Engine constraint: ``REVEAL_UNTIL_LAND`` has no handler (engine gap), so we
    approximate with a SEARCH_LIBRARY for two land cards directly to battlefield
    tapped. The +1/+1 counter rider is emitted alongside.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': o.controller,
                    'card_type': 'land',
                    'amount': 2,
                    'min_count': 0,
                    'destination': 'battlefield',
                    'tapped': True,
                    'shuffle_after': True,
                },
                source=o.id, controller=o.controller,
            ),
            *_emit_self_counters(o, 1),
        ]

    make_exhaust_ability(
        obj, cost="{4}", effect_fn=_effect,
        description="{4}: Find up to two land cards from your library; put them onto the battlefield tapped. Put a +1/+1 counter on this creature.",
    )
    return []


def redshift_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exhaust — {10}{R}{G}: Put any number of permanent cards from your hand onto
    the battlefield.

    Implementation: open a target_with_callback PendingChoice over the
    controller's hand, filtered to permanent card types
    (CREATURE / ARTIFACT / ENCHANTMENT / PLANESWALKER / LAND). On submit,
    emit one ZONE_CHANGE per selected card moving from hand → battlefield.
    """
    def _effect(o: GameObject, st: GameState, targets) -> list[Event]:
        from src.engine.types import PendingChoice
        permanent_types = {
            CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT,
            CardType.PLANESWALKER, CardType.LAND,
        }
        hand = st.zones.get(f'hand_{o.controller}')
        hand_ids = list(hand.objects) if hand else []
        eligible: list[str] = []
        for cid in hand_ids:
            ho = st.objects.get(cid)
            if ho is None:
                continue
            if any(t in permanent_types for t in ho.characteristics.types):
                eligible.append(cid)
        if not eligible:
            return []

        def _on_choose(choice, selected, gs: GameState) -> list[Event]:
            evs: list[Event] = []
            for cid in (selected or []):
                evs.append(Event(
                    type=EventType.ZONE_CHANGE,
                    payload={
                        'object_id': cid,
                        'from_zone_type': ZoneType.HAND,
                        'from_zone': f'hand_{o.controller}',
                        'to_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone': 'battlefield',
                    },
                    source=o.id, controller=o.controller,
                ))
            return evs

        st.pending_choice = PendingChoice(
            choice_type="target_with_callback",
            player=o.controller,
            prompt="Choose any number of permanent cards from your hand to put onto the battlefield (Redshift):",
            options=eligible,
            source_id=o.id,
            min_choices=0,
            max_choices=len(eligible),
            callback_data={'handler': _on_choose},
        )
        return []

    make_exhaust_ability(
        obj, cost="{10}{R}{G}", effect_fn=_effect,
        description="{10}{R}{G}: Put any number of permanent cards from your hand onto the battlefield.",
    )
    return []


def loot_pathfinder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Three separate Exhaust abilities. Proves multi-Exhaust-per-card.
    Engine gap: per-cost {T} cost on each — make_activated_ability already
    handles tap costs in the cost string.

    - Exhaust — {G}, {T}: Add three mana of any one color.
    - Exhaust — {U}, {T}: Draw three cards.
    - Exhaust — {R}, {T}: Loot deals 3 damage to any target.
    """
    from src.cards.interceptor_helpers import create_modal_choice

    # Exhaust 1: {G}, {T} — Add three mana of any one color.
    def _g_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        modes = [
            {"index": 0, "text": "Add {W}{W}{W}"},
            {"index": 1, "text": "Add {U}{U}{U}"},
            {"index": 2, "text": "Add {B}{B}{B}"},
            {"index": 3, "text": "Add {R}{R}{R}"},
            {"index": 4, "text": "Add {G}{G}{G}"},
        ]
        color_map = {
            0: Color.WHITE, 1: Color.BLUE, 2: Color.BLACK,
            3: Color.RED, 4: Color.GREEN,
        }

        def _on_pick(choice, selected, gs: GameState) -> list[Event]:
            if not selected:
                return []
            try:
                idx = int(selected[0])
            except (TypeError, ValueError):
                return []
            color = color_map.get(idx)
            if color is None:
                return []
            return [Event(
                type=EventType.MANA_PRODUCED,
                payload={'player': o.controller, 'color': color, 'amount': 3},
                source=o.id, controller=o.controller,
            )]

        choice = create_modal_choice(
            state=st,
            player_id=o.controller,
            source_id=o.id,
            modes=modes,
            min_modes=1, max_modes=1,
            prompt="Loot, the Pathfinder — choose a color for three mana:",
        )
        choice.choice_type = "modal_with_callback"
        choice.callback_data['handler'] = _on_pick
        return []

    # Exhaust 2: {U}, {T} — Draw three cards.
    def _u_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': o.controller, 'count': 3},
            source=o.id, controller=o.controller,
        )]

    # Exhaust 3: {R}, {T} — Loot deals 3 damage to any target.
    def _r_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        if not targets:
            return []
        t = targets[0]
        target_id = getattr(t, "object_id", None) or getattr(t, "player_id", None) or getattr(t, "id", None) or t
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': o.id},
            source=o.id, controller=o.controller,
        )]

    make_exhaust_ability(
        obj, cost="{G}, {T}", effect_fn=_g_effect,
        description="{G}, {T}: Add three mana of any one color.",
    )
    make_exhaust_ability(
        obj, cost="{U}, {T}", effect_fn=_u_effect,
        description="{U}, {T}: Draw three cards.",
    )
    make_exhaust_ability(
        obj, cost="{R}, {T}", effect_fn=_r_effect,
        description="{R}, {T}: Loot deals 3 damage to any target.",
        targets_required=1, target_kind="any",
    )
    return []


def draconautics_engineer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Two Exhaust abilities.

    - Exhaust — {R}: Other creatures you control gain haste until end of turn.
      Put a +1/+1 counter on this creature.
    - Exhaust — {3}{R}: Create a 4/4 red Dinosaur Dragon creature token with flying.
    """
    def _r_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        events: list[Event] = []
        for other in st.objects.values():
            if (other.id != o.id
                    and other.controller == o.controller
                    and other.zone == ZoneType.BATTLEFIELD
                    and CardType.CREATURE in other.characteristics.types):
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        'object_id': other.id,
                        'keyword': 'haste',
                        'duration': 'end_of_turn',
                    },
                    source=o.id, controller=o.controller,
                ))
        events.extend(_emit_self_counters(o, 1))
        return events

    def _3r_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return [_emit_create_token(
            o, name="Dinosaur Dragon", power=4, toughness=4,
            subtypes={"Dinosaur", "Dragon"}, colors={Color.RED},
            keywords=["flying"],
        )]

    make_exhaust_ability(
        obj, cost="{R}", effect_fn=_r_effect,
        description="{R}: Other creatures you control gain haste until end of turn. Put a +1/+1 counter on this creature.",
    )
    make_exhaust_ability(
        obj, cost="{3}{R}", effect_fn=_3r_effect,
        description="{3}{R}: Create a 4/4 red Dinosaur Dragon creature token with flying.",
    )
    return []


# -----------------------------------------------------------------------------
# X-cost Exhaust cards (W2 engine extension — {X} mana in activation cost)
# -----------------------------------------------------------------------------
#
# These cards' Exhaust abilities use {X} in the cost; the priority system
# threads PlayerAction.x_value through can_pay_activation / pay_activation_cost
# and into the resolve closure via the kw-arg ``x_value`` shim. The effect
# function should accept ``x_value: int = 0`` as a kwarg.


def mindspring_merfolk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mindspring Merfolk.

    Exhaust — {X}{U}{U}, {T}: Draw X cards. Put a +1/+1 counter on each Merfolk
    creature you control.

    The "+1/+1 counter on each Merfolk" rider is part of the printed text but
    is left out of the v1 wiring to keep the X-draw the focus; the Merfolk
    counter rider can be added later without engine work.
    """
    def _effect(o: GameObject, st: GameState, targets, x_value: int = 0) -> list[Event]:
        if x_value <= 0:
            return []
        return [Event(
            type=EventType.DRAW,
            payload={'player': o.controller, 'count': x_value},
            source=o.id, controller=o.controller,
        )]

    make_exhaust_ability(
        obj, cost="{X}{U}{U}, {T}", effect_fn=_effect,
        description="{X}{U}{U}, {T}: Draw X cards.",
    )
    return []


def boommobile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Boommobile.

    Exhaust — {X}{2}{R}: Boommobile deals X damage to any target.

    The "Put a +1/+1 counter on this Vehicle" rider from the printed text is
    omitted in v1 to keep the X-damage the focus; the +1/+1 rider is trivial
    to add later.
    """
    def _effect(o: GameObject, st: GameState, targets, x_value: int = 0) -> list[Event]:
        if x_value <= 0 or not targets:
            return []
        t = targets[0]
        target_id = (
            getattr(t, "object_id", None)
            or getattr(t, "player_id", None)
            or getattr(t, "id", None)
            or t
        )
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': x_value, 'source': o.id},
            source=o.id, controller=o.controller,
        )]

    make_exhaust_ability(
        obj, cost="{X}{2}{R}", effect_fn=_effect,
        description="{X}{2}{R}: Boommobile deals X damage to any target.",
        targets_required=1, target_kind="any",
    )
    return []


def sita_varma_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sita Varma, Masked Racer.

    Exhaust — {X}{G}{G}{U}: Sita Varma's base power and toughness become X/X
    until end of turn.

    Implementation note: PT_MODIFICATION is delta-based (no absolute "set"
    mode in this engine), so we compute the delta from the printed P/T at
    activation time. With no other +1/+1 counters or pumps, this yields
    X/X exactly. With other modifiers stacked, the result will be
    X + extra_modifiers (a v1 approximation; an absolute-set mode in the
    PT pipeline would be more correct).
    """
    def _effect(o: GameObject, st: GameState, targets, x_value: int = 0) -> list[Event]:
        printed_p = o.characteristics.power or 0
        printed_t = o.characteristics.toughness or 0
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': o.id,
                'power_mod': x_value - printed_p,
                'toughness_mod': x_value - printed_t,
                'duration': 'end_of_turn',
            },
            source=o.id, controller=o.controller,
        )]

    make_exhaust_ability(
        obj, cost="{X}{G}{G}{U}", effect_fn=_effect,
        description="{X}{G}{G}{U}: Sita Varma's base power and toughness become X/X until end of turn.",
    )
    return []


# -----------------------------------------------------------------------------
# Elvish Refueler / Winter, Cursed Rider — wired with the W19/W27 helpers
# (EXHAUST_RESET, exile_from_graveyard cost step). W27 extended the cost
# parser to handle "X" counts and typed filters ("X artifact cards"), so
# Winter, Cursed Rider now uses the full printed cost end-to-end — no
# effect_fn workaround. Elvish Refueler models the printed "you may
# activate exhaust abilities as though they hadn't been activated"
# permission as an upkeep-time reset of every exhaust the controller owns —
# a v1 simplification that captures the spirit (one fresh wave per turn).
# -----------------------------------------------------------------------------


def elvish_refueler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Elvish Refueler.

    Printed text:
      "During your turn, as long as you haven't activated an exhaust
       ability this turn, you may activate exhaust abilities as though
       they haven't been activated.
       Exhaust — {1}{G}: Put a +1/+1 counter on this creature."

    v1 model:
      * At the beginning of the controller's upkeep, reset every Exhaust
        ability that controller owns (including Elvish Refueler's own).
        That gives one fresh window of exhaust activations per turn,
        matching the practical effect of the printed permission. The
        EXHAUST_RESET marker event is emitted for observers/UI.
      * The card's own Exhaust ability is registered through
        ``make_exhaust_ability`` like every other Aetherdrift exhaust.
    """
    def _own_exhaust_effect(o: GameObject, st: GameState, targets) -> list[Event]:
        return _emit_self_counters(o, 1)

    make_exhaust_ability(
        obj, cost="{1}{G}", effect_fn=_own_exhaust_effect,
        description="{1}{G}: Put a +1/+1 counter on this creature.",
    )

    def _upkeep_reset(event: Event, st: GameState) -> list[Event]:
        # Re-enable every Exhaust ability the controller owns. The helper
        # both flips ``once_per_game_used`` flags AND emits an
        # EXHAUST_RESET marker event for observers / logging / UI.
        return make_exhaust_reset_effect(obj, st, controller=obj.controller)

    return [make_upkeep_trigger(obj, _upkeep_reset)]


def winter_cursed_rider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Winter, Cursed Rider.

    Printed text (relevant portion):
      "Exhaust — {X}{2}{U}{B}, {T}, Exile X artifact cards from your
       graveyard: Each other nonartifact creature gets -X/-X until
       end of turn."

    v1 model:
      * Cost parsed by ``make_activated_ability`` is the full printed
        ``{X}{2}{U}{B}, {T}, Exile X artifact cards from your graveyard``.
        After W27, the casting-cost parser supports the "X" count token
        and the typed "artifact cards" filter, so the GY-exile portion
        is now a real ``exile_from_graveyard`` ``CostStep`` with
        ``count_is_x=True`` and ``subtype_filter=CardType.ARTIFACT``.
        ``can_pay_activation`` consults ``action.x_value`` to gate
        legality (need X artifacts in GY) and ``pay_activation_cost``
        emits the X EXILE events from the cost side, so ``effect_fn``
        only owns the -X/-X PT modifications.
      * The (Ward — Pay 2 life) static from the rest of the printed text
        is owned by W25 and not modeled here.
    """

    def _effect(o: GameObject, st: GameState, targets, x_value: int = 0) -> list[Event]:
        new_events: list[Event] = []
        x = max(0, int(x_value or 0))
        if x <= 0:
            return new_events
        # -X/-X to every other nonartifact creature on the battlefield.
        # The X artifact-card exiles are emitted by pay_activation_cost
        # (W27) — effect_fn only handles the post-cost PT swing.
        bf = st.zones.get("battlefield")
        if bf is None:
            return new_events
        for other_id in list(bf.objects):
            if other_id == o.id:
                continue
            other = st.objects.get(other_id)
            if other is None:
                continue
            if CardType.CREATURE not in other.characteristics.types:
                continue
            if CardType.ARTIFACT in other.characteristics.types:
                continue
            new_events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': other_id,
                    'power_mod': -x,
                    'toughness_mod': -x,
                    'duration': 'end_of_turn',
                },
                source=o.id, controller=o.controller,
            ))
        return new_events

    make_activated_ability(
        obj,
        cost="{X}{2}{U}{B}, {T}, Exile X artifact cards from your graveyard",
        effect_fn=_effect,
        description=(
            "Exhaust — {X}{2}{U}{B}, {T}, Exile X artifact cards from your "
            "graveyard: Each other nonartifact creature gets -X/-X until end of turn."
        ),
        once_per_game=True,
    )
    return []


# Round-9 vehicle animation (W2.3): Rocketeer Boostbuggy + Marshals' Pathcruiser
# wire their attack/ETB triggers plus the animate-exhaust ability.

def rocketeer_boostbuggy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rocketeer Boostbuggy.

    "Whenever this Vehicle attacks, create a Treasure token."
    Plus Exhaust — {3}: Becomes a 3/2 artifact creature; +1/+1 counter rider.
    """
    def _attack_make_treasure(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'token_data': {
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'colors': set(),
                    'mana_cost': '',
                    'text': '{T}, Sacrifice this token: Add one mana of any color.',
                    'is_token': True,
                },
            },
            source=obj.id, controller=obj.controller,
        )]

    make_animate_via_exhaust(
        obj, cost="{3}", power=3, toughness=2, plus_one_counters=1,
    )
    return [make_attack_trigger(obj, _attack_make_treasure)]


def marshals_pathcruiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Marshals' Pathcruiser.

    ETB: search library for a basic land card, reveal it, put it into hand.
    Exhaust — {W}{U}{B}{R}{G}: Becomes a 4/4 artifact creature; two +1/+1 counters.
    """
    def _etb_search(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'filter': 'basic_land',
                'destination': 'hand',
                'amount': 1,
            },
            source=obj.id, controller=obj.controller,
        )]

    make_animate_via_exhaust(
        obj, cost="{W}{U}{B}{R}{G}",
        power=4, toughness=4, plus_one_counters=2,
    )
    return [make_etb_trigger(obj, _etb_search)]


# =============================================================================
# SPELL RESOLVE FUNCTIONS
# =============================================================================

def _aetherdrift_spell_id(state: GameState, spell_name: str) -> str:
    """Locate the spell object on the stack (Phase 5b: targets pre-supplied,
    we just need the source_id for emitted events). Falls back to a synthetic
    id if the spell isn't on the stack (e.g. resolve invoked directly in a test).
    """
    stack_zone = state.zones.get('stack')
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == spell_name:
                return obj.id
    return f"{spell_name.lower().replace(' ', '_').replace(chr(39), '')}_spell"


def _lightning_strike_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Lightning Strike after target selection - deal 3 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    # Check if target is a player or permanent
    if target_id in state.players:
        # Target is a player
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        # Target is a permanent (creature or planeswalker)
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []  # Target no longer valid

        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]


def lightning_strike_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Lightning Strike: Deal 3 damage to any target.

    Phase 5b: target picking happens at cast time via ``target_requirements``.
    """
    spell_id = _aetherdrift_spell_id(state, "Lightning Strike")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        if not is_player:
            obj = state.objects.get(tid)
            if obj is None or obj.zone != ZoneType.BATTLEFIELD:
                continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={'target': tid, 'amount': 3, 'source': spell_id,
                     'is_combat': False, 'is_player': is_player},
            source=spell_id,
        ))
    return events


# -----------------------------------------------------------------------------
# BOUNCE OFF - Return target creature or Vehicle to its owner's hand
# -----------------------------------------------------------------------------

def _bounce_off_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bounce Off - return target to hand."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.HAND,
            'to_zone_owner': target.owner
        },
        source=choice.source_id
    )]


def bounce_off_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Bounce Off: Return target creature or Vehicle to owner's hand.

    Phase 5b: target picking happens at cast time via ``target_requirements``.
    """
    spell_id = _aetherdrift_spell_id(state, "Bounce Off")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        if is_player:
            continue
        target = state.objects.get(tid)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            continue
        events.append(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': tid,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND,
                'to_zone_owner': target.owner,
            },
            source=spell_id,
        ))
    return events


# -----------------------------------------------------------------------------
# GALLANT STRIKE - Destroy target creature with toughness 4 or greater
# -----------------------------------------------------------------------------

def _gallant_strike_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Gallant Strike - destroy target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def gallant_strike_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Gallant Strike: Destroy target creature with toughness 4 or greater.

    Phase 5b: target picking happens at cast time via ``target_requirements``.
    """
    spell_id = _aetherdrift_spell_id(state, "Gallant Strike")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        if is_player:
            continue
        target = state.objects.get(tid)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            continue
        events.append(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': tid},
            source=spell_id,
        ))
    return events


# -----------------------------------------------------------------------------
# RIDE'S END - Exile target creature or Vehicle
# -----------------------------------------------------------------------------

def _rides_end_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Ride's End - exile target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.EXILE
        },
        source=choice.source_id
    )]


def rides_end_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Ride's End via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Ride's End")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_rides_end_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# SPIN OUT - Destroy target creature or Vehicle
# -----------------------------------------------------------------------------

def _spin_out_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Spin Out - destroy target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def spin_out_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Spin Out via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Spin Out")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_spin_out_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# SYPHON FUEL - Target creature gets -6/-6 until end of turn. You gain 2 life.
# -----------------------------------------------------------------------------

def _syphon_fuel_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Syphon Fuel - give -6/-6 and gain 2 life."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFY,
            payload={'object_id': target_id, 'power': -6, 'toughness': -6, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': 2},
            source=choice.source_id
        )
    ]


def syphon_fuel_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Syphon Fuel via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Syphon Fuel")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_syphon_fuel_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# LOCUST SPRAY - Target creature gets -1/-1 until end of turn
# -----------------------------------------------------------------------------

def _locust_spray_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Locust Spray - give -1/-1."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PT_MODIFY,
        payload={'object_id': target_id, 'power': -1, 'toughness': -1, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def locust_spray_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Locust Spray via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Locust Spray")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_locust_spray_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# MAXIMUM OVERDRIVE - +1/+1 counter, deathtouch, indestructible until EOT
# -----------------------------------------------------------------------------

def _maximum_overdrive_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Maximum Overdrive - +1/+1 counter and grant abilities."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': '+1/+1', 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_ABILITY,
            payload={'object_id': target_id, 'abilities': ['deathtouch', 'indestructible'], 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def maximum_overdrive_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Maximum Overdrive via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Maximum Overdrive")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_maximum_overdrive_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# LIGHTSHIELD PARRY - Target creature gets +2/+2 until end of turn
# -----------------------------------------------------------------------------

def _lightshield_parry_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Lightshield Parry - give +2/+2."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.PT_MODIFY,
        payload={'object_id': target_id, 'power': 2, 'toughness': 2, 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def lightshield_parry_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Lightshield Parry via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Lightshield Parry")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_lightshield_parry_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# BESTOW GREATNESS - Target creature gets +4/+4 and trample until end of turn
# -----------------------------------------------------------------------------

def _bestow_greatness_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Bestow Greatness - give +4/+4 and trample."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.PT_MODIFY,
            payload={'object_id': target_id, 'power': 4, 'toughness': 4, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_ABILITY,
            payload={'object_id': target_id, 'abilities': ['trample'], 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def bestow_greatness_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Bestow Greatness via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Bestow Greatness")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_bestow_greatness_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# BROKEN WINGS - Destroy target artifact, enchantment, or creature with flying
# -----------------------------------------------------------------------------

def _broken_wings_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Broken Wings - destroy target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def broken_wings_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Broken Wings via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Broken Wings")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_broken_wings_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# SKYCRASH - Destroy target artifact
# -----------------------------------------------------------------------------

def _skycrash_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Skycrash - destroy target artifact."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def skycrash_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Skycrash via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Skycrash")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_skycrash_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# ROAD RAGE - Deal X damage to target creature/planeswalker (X = 2 + mounts/vehicles)
# -----------------------------------------------------------------------------

def _road_rage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Road Rage - deal X damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Count Mounts and Vehicles controlled by the caster
    mount_vehicle_count = 0
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == choice.player:
            if "Mount" in obj.characteristics.subtypes or "Vehicle" in obj.characteristics.subtypes:
                mount_vehicle_count += 1

    damage = 2 + mount_vehicle_count

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': damage, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def road_rage_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Road Rage via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Road Rage")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_road_rage_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# BROADSIDE BARRAGE - Deal 5 damage to target creature/planeswalker, draw then discard
# -----------------------------------------------------------------------------

def _broadside_barrage_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Broadside Barrage - deal 5 damage, draw, discard."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 5, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        ),
        Event(
            type=EventType.DISCARD,
            payload={'player': choice.player, 'amount': 1, 'random': False},
            source=choice.source_id
        )
    ]


def broadside_barrage_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Broadside Barrage via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Broadside Barrage")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_broadside_barrage_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# COLLISION COURSE (Modal) - Deal X damage to creature OR destroy artifact
# -----------------------------------------------------------------------------

def _collision_course_mode1_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 1: Deal X damage to target creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Count creatures and Vehicles controlled by caster
    count = 0
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == choice.player:
            if CardType.CREATURE in obj.characteristics.types or "Vehicle" in obj.characteristics.subtypes:
                count += 1

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': count, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def _collision_course_mode2_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 2: Destroy target artifact."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _collision_course_modal_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle modal selection for Collision Course."""
    mode = selected[0] if selected else None
    if mode is None:
        return []

    caster_id = choice.player
    spell_id = choice.source_id

    if mode == 0:
        # Mode 1: damage to creature
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature for Collision Course damage",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _collision_course_mode1_execute
    else:
        # Mode 2: destroy artifact
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.ARTIFACT in obj.characteristics.types:
                valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose an artifact to destroy",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _collision_course_mode2_execute

    return []


def collision_course_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Collision Course: Choose one - damage to creature OR destroy artifact."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Collision Course":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "collision_course_spell"

    # Create modal choice
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=[
            {"index": 0, "text": "Deal X damage to target creature (X = creatures + Vehicles you control)"},
            {"index": 1, "text": "Destroy target artifact"}
        ],
        min_modes=1,
        max_modes=1,
        prompt="Choose a mode for Collision Course:"
    )

    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _collision_course_modal_handler

    return []


# -----------------------------------------------------------------------------
# CRASH AND BURN (Modal) - Destroy Vehicle OR deal 6 damage to creature/planeswalker
# -----------------------------------------------------------------------------

def _crash_and_burn_mode1_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 1: Destroy target Vehicle."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _crash_and_burn_mode2_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 2: Deal 6 damage to target creature or planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 6, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def _crash_and_burn_modal_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle modal selection for Crash and Burn."""
    mode = selected[0] if selected else None
    if mode is None:
        return []

    caster_id = choice.player
    spell_id = choice.source_id

    if mode == 0:
        # Mode 1: destroy Vehicle
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and "Vehicle" in obj.characteristics.subtypes:
                valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a Vehicle to destroy",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _crash_and_burn_mode1_execute
    else:
        # Mode 2: deal 6 damage
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types:
                    valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a creature or planeswalker for 6 damage",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _crash_and_burn_mode2_execute

    return []


def crash_and_burn_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Crash and Burn: Choose one - destroy Vehicle OR deal 6 damage."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Crash and Burn":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "crash_and_burn_spell"

    # Create modal choice
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=[
            {"index": 0, "text": "Destroy target Vehicle"},
            {"index": 1, "text": "Deal 6 damage to target creature or planeswalker"}
        ],
        min_modes=1,
        max_modes=1,
        prompt="Choose a mode for Crash and Burn:"
    )

    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _crash_and_burn_modal_handler

    return []


# -----------------------------------------------------------------------------
# STALL OUT - Tap target creature/Vehicle and put 3 stun counters on it
# -----------------------------------------------------------------------------

def _stall_out_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Stall Out - tap and add stun counters."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.TAP,
            payload={'object_id': target_id},
            source=choice.source_id
        ),
        Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 3},
            source=choice.source_id
        )
    ]


def stall_out_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Stall Out via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Stall Out")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_stall_out_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# TRIP UP - Owner puts target nonland permanent on top or bottom of library
# -----------------------------------------------------------------------------

def _trip_up_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Trip Up - put permanent on library (top or bottom)."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # For simplicity, we'll put it on top (a proper implementation would ask the owner)
    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.BATTLEFIELD,
            'to_zone_type': ZoneType.LIBRARY,
            'library_position': 'top'
        },
        source=choice.source_id
    )]


def trip_up_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Trip Up via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Trip Up")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_trip_up_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# ROADSIDE BLOWOUT - Return opponent's creature/Vehicle to hand, draw a card
# -----------------------------------------------------------------------------

def _roadside_blowout_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Roadside Blowout - bounce and draw."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [
        Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND,
                'to_zone_owner': target.owner
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.DRAW,
            payload={'player': choice.player, 'amount': 1},
            source=choice.source_id
        )
    ]


def roadside_blowout_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Roadside Blowout via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Roadside Blowout")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_roadside_blowout_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# HELLISH SIDESWIPE - Destroy target creature or Vehicle (requires sacrifice)
# -----------------------------------------------------------------------------

def _hellish_sideswipe_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Hellish Sideswipe - destroy target."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # Note: The sacrifice cost is handled during casting, not during resolution
    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def hellish_sideswipe_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Hellish Sideswipe: Destroy target creature or Vehicle."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Hellish Sideswipe":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "hellish_sideswipe_spell"

    # Find valid targets: creatures and Vehicles
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types:
                valid_targets.append(obj.id)
            elif "Vehicle" in obj.characteristics.subtypes:
                valid_targets.append(obj.id)

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or Vehicle to destroy",
        min_targets=1,
        max_targets=1
    )

    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _hellish_sideswipe_execute

    return []


# -----------------------------------------------------------------------------
# RUN OVER - Your creature deals damage equal to its power to opponent's creature
# -----------------------------------------------------------------------------

def _run_over_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Run Over - deal damage equal to creature's power."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    target_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    target_creature = state.objects.get(target_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not target_creature or target_creature.zone != ZoneType.BATTLEFIELD:
        return []

    power = get_power(your_creature, state)

    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_creature_id, 'amount': power, 'source': your_creature_id, 'is_combat': False},
        source=choice.source_id
    )]


def run_over_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Run Over: Target creature you control deals damage equal to its power to target opponent's creature."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Run Over":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "run_over_spell"

    # Find your creatures
    your_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                your_creatures.append(obj.id)

    # Find opponent's creatures
    opponent_creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller != caster_id:
            if CardType.CREATURE in obj.characteristics.types:
                opponent_creatures.append(obj.id)

    if not your_creatures or not opponent_creatures:
        return []

    # For simplicity, create a single choice that combines both targets
    # A full implementation would chain two choices
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=your_creatures + opponent_creatures,
        prompt="Choose your creature, then target opponent's creature",
        min_targets=2,
        max_targets=2
    )

    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _run_over_execute

    return []


# -----------------------------------------------------------------------------
# PLOW THROUGH (Modal) - Fight OR destroy Vehicle
# -----------------------------------------------------------------------------

def _plow_through_fight_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 1: Fight - your creature fights opponent's creature."""
    if len(selected) < 2:
        return []

    your_creature_id = selected[0]
    opponent_creature_id = selected[1]

    your_creature = state.objects.get(your_creature_id)
    opponent_creature = state.objects.get(opponent_creature_id)

    if not your_creature or your_creature.zone != ZoneType.BATTLEFIELD:
        return []
    if not opponent_creature or opponent_creature.zone != ZoneType.BATTLEFIELD:
        return []

    your_power = get_power(your_creature, state)
    opponent_power = get_power(opponent_creature, state)

    return [
        Event(
            type=EventType.DAMAGE,
            payload={'target': opponent_creature_id, 'amount': your_power, 'source': your_creature_id, 'is_combat': False},
            source=choice.source_id
        ),
        Event(
            type=EventType.DAMAGE,
            payload={'target': your_creature_id, 'amount': opponent_power, 'source': opponent_creature_id, 'is_combat': False},
            source=choice.source_id
        )
    ]


def _plow_through_destroy_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 2: Destroy target Vehicle."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': target_id},
        source=choice.source_id
    )]


def _plow_through_modal_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle modal selection for Plow Through."""
    mode = selected[0] if selected else None
    if mode is None:
        return []

    caster_id = choice.player
    spell_id = choice.source_id

    if mode == 0:
        # Mode 1: Fight
        your_creatures = []
        opponent_creatures = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
                if obj.controller == caster_id:
                    your_creatures.append(obj.id)
                else:
                    opponent_creatures.append(obj.id)

        if not your_creatures or not opponent_creatures:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=your_creatures + opponent_creatures,
            prompt="Choose your creature, then opponent's creature to fight",
            min_targets=2,
            max_targets=2
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _plow_through_fight_execute
    else:
        # Mode 2: destroy Vehicle
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and "Vehicle" in obj.characteristics.subtypes:
                valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a Vehicle to destroy",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _plow_through_destroy_execute

    return []


def plow_through_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Plow Through: Choose one - your creature fights opponent's creature OR destroy target Vehicle."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Plow Through":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "plow_through_spell"

    # Create modal choice
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=[
            {"index": 0, "text": "Target creature you control fights target creature an opponent controls"},
            {"index": 1, "text": "Destroy target Vehicle"}
        ],
        min_modes=1,
        max_modes=1,
        prompt="Choose a mode for Plow Through:"
    )

    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _plow_through_modal_handler

    return []


# -----------------------------------------------------------------------------
# DEFEND THE RIDER (Modal) - Hexproof+indestructible OR create Pilot token
# -----------------------------------------------------------------------------

def _defend_rider_mode1_execute(choice, selected, state: GameState) -> list[Event]:
    """Mode 1: Target permanent gains hexproof and indestructible until EOT."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    return [Event(
        type=EventType.GRANT_ABILITY,
        payload={'object_id': target_id, 'abilities': ['hexproof', 'indestructible'], 'duration': 'end_of_turn'},
        source=choice.source_id
    )]


def _defend_rider_modal_handler(choice, selected, state: GameState) -> list[Event]:
    """Handle modal selection for Defend the Rider."""
    mode = selected[0] if selected else None
    if mode is None:
        return []

    caster_id = choice.player
    spell_id = choice.source_id

    if mode == 0:
        # Mode 1: hexproof + indestructible
        valid_targets = []
        for obj in state.objects.values():
            if obj.zone == ZoneType.BATTLEFIELD and obj.controller == caster_id:
                valid_targets.append(obj.id)

        if not valid_targets:
            return []

        target_choice = create_target_choice(
            state=state,
            player_id=caster_id,
            source_id=spell_id,
            legal_targets=valid_targets,
            prompt="Choose a permanent you control to grant hexproof and indestructible",
            min_targets=1,
            max_targets=1
        )
        target_choice.choice_type = "target_with_callback"
        target_choice.callback_data['handler'] = _defend_rider_mode1_execute
    else:
        # Mode 2: create Pilot token - immediate, no targeting needed
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': caster_id,
                'name': 'Pilot',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Pilot'},
                'text': 'This token saddles Mounts and crews Vehicles as though its power were 2 greater.'
            },
            source=spell_id
        )]

    return []


def defend_the_rider_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Defend the Rider: Choose one - hexproof+indestructible OR create Pilot token."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Defend the Rider":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "defend_the_rider_spell"

    # Create modal choice
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=[
            {"index": 0, "text": "Target permanent you control gains hexproof and indestructible until end of turn"},
            {"index": 1, "text": "Create a 1/1 colorless Pilot creature token"}
        ],
        min_modes=1,
        max_modes=1,
        prompt="Choose a mode for Defend the Rider:"
    )

    choice.choice_type = "modal_with_callback"
    choice.callback_data['handler'] = _defend_rider_modal_handler

    return []


# -----------------------------------------------------------------------------
# SPECTRAL INTERFERENCE - Counter target artifact/creature spell unless pay {4}
# -----------------------------------------------------------------------------

def _spectral_interference_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Spectral Interference - counter unless pay {4}."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.STACK:
        return []

    # For simplicity, this will counter the spell (a full implementation would
    # give the opponent a choice to pay {4})
    return [Event(
        type=EventType.COUNTER_SPELL,
        payload={'spell_id': target_id},
        source=choice.source_id
    )]


def spectral_interference_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Spectral Interference via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Spectral Interference")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_spectral_interference_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# SPELL PIERCE - Counter target noncreature spell unless controller pays {2}
# -----------------------------------------------------------------------------

def _spell_pierce_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Spell Pierce - counter unless pay {2}."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.STACK:
        return []

    return [Event(
        type=EventType.COUNTER_SPELL,
        payload={'spell_id': target_id},
        source=choice.source_id
    )]


def spell_pierce_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Spell Pierce via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Spell Pierce")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_spell_pierce_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# FUEL THE FLAMES - Deal 2 damage to each creature
# -----------------------------------------------------------------------------

def fuel_the_flames_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Fuel the Flames: Deal 2 damage to each creature."""
    stack_zone = state.zones.get('stack')
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Fuel the Flames":
                spell_id = obj.id
                break

    if spell_id is None:
        spell_id = "fuel_the_flames_spell"

    # Deal 2 damage to each creature
    events = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': obj.id, 'amount': 2, 'source': spell_id, 'is_combat': False},
                source=spell_id
            ))

    return events


# -----------------------------------------------------------------------------
# TUNE UP - Return target artifact from graveyard to battlefield
# -----------------------------------------------------------------------------

def _tune_up_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Tune Up - return artifact from graveyard."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.GRAVEYARD:
        return []

    return [Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': target_id,
            'from_zone_type': ZoneType.GRAVEYARD,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'becomes_creature': "Vehicle" in target.characteristics.subtypes
        },
        source=choice.source_id
    )]


def tune_up_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Tune Up via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Tune Up")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_tune_up_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# BACK ON TRACK - Return creature/Vehicle from graveyard, create Pilot token
# -----------------------------------------------------------------------------

def _back_on_track_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Back on Track - return from graveyard and create token."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.GRAVEYARD:
        return []

    return [
        Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': target_id,
                'from_zone_type': ZoneType.GRAVEYARD,
                'to_zone_type': ZoneType.BATTLEFIELD
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': choice.player,
                'name': 'Pilot',
                'power': 1,
                'toughness': 1,
                'types': {CardType.CREATURE},
                'subtypes': {'Pilot'},
                'text': 'This token saddles Mounts and crews Vehicles as though its power were 2 greater.'
            },
            source=choice.source_id
        )
    ]


def back_on_track_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Back on Track via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Back on Track")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    # Find caster for life-gain / loot riders.
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    # Synthetic choice so we can reuse the existing _execute logic.
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_back_on_track_execute(synth, [tid], state))
    return events

# -----------------------------------------------------------------------------
# HAUNT THE NETWORK - Target opponent loses X life, create Thopters
# -----------------------------------------------------------------------------

def _haunt_the_network_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Haunt the Network - create thopters and drain life."""
    target_player = selected[0] if selected else None
    if not target_player or target_player not in state.players:
        return []

    # Count artifacts the caster controls
    artifact_count = 0
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and obj.controller == choice.player:
            if CardType.ARTIFACT in obj.characteristics.types:
                artifact_count += 1

    events = [
        # Create two Thopter tokens
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': choice.player,
                'name': 'Thopter',
                'power': 1,
                'toughness': 1,
                'types': {CardType.ARTIFACT, CardType.CREATURE},
                'subtypes': {'Thopter'},
                'keywords': ['flying']
            },
            source=choice.source_id
        ),
        Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': choice.player,
                'name': 'Thopter',
                'power': 1,
                'toughness': 1,
                'types': {CardType.ARTIFACT, CardType.CREATURE},
                'subtypes': {'Thopter'},
                'keywords': ['flying']
            },
            source=choice.source_id
        ),
    ]

    # Add 2 for the new thopters to the count
    total_artifacts = artifact_count + 2

    # Opponent loses life, you gain life
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': target_player, 'amount': -total_artifacts},
        source=choice.source_id
    ))
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': total_artifacts},
        source=choice.source_id
    ))

    return events


def haunt_the_network_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Haunt the Network: Choose target opponent. Create 2 Thopters. Target loses X life, you gain X (X = artifacts)."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == "Haunt the Network":
                caster_id = obj.controller
                spell_id = obj.id
                break

    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = "haunt_the_network_spell"

    # Find valid targets: opponents
    valid_targets = [p_id for p_id in state.players if p_id != caster_id]

    if not valid_targets:
        return []

    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose target opponent",
        min_targets=1,
        max_targets=1
    )

    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _haunt_the_network_execute

    return []


# -----------------------------------------------------------------------------
# PEDAL TO THE METAL - Target creature gets +X/+0 and first strike
# -----------------------------------------------------------------------------

def _pedal_to_the_metal_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Pedal to the Metal - give +X/+0 and first strike."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []

    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []

    # X value would need to be stored during casting - for now default to 0
    x_value = choice.callback_data.get('x_value', 0)

    return [
        Event(
            type=EventType.PT_MODIFY,
            payload={'object_id': target_id, 'power': x_value, 'toughness': 0, 'duration': 'end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_ABILITY,
            payload={'object_id': target_id, 'abilities': ['first_strike'], 'duration': 'end_of_turn'},
            source=choice.source_id
        )
    ]


def pedal_to_the_metal_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Pedal to the Metal via Phase 5b targets[0] (engine-emitted PendingChoice)."""
    spell_id = _aetherdrift_spell_id(state, "Pedal to the Metal")
    events: list[Event] = []
    if not (targets and targets[0]):
        return events
    caster_id = state.active_player
    obj = state.objects.get(spell_id)
    if obj is not None:
        caster_id = obj.controller
    class _SyntheticChoice:
        source_id = spell_id
        player = caster_id
    synth = _SyntheticChoice()
    for t in targets[0]:
        tid, is_player = normalize_target(t, state)
        events.extend(_pedal_to_the_metal_execute(synth, [tid], state))
    return events


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

AIR_RESPONSE_UNIT = make_artifact(
    name="Air Response Unit",
    mana_cost="{2}{W}",
    text="Flying, vigilance\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

ALACRIAN_ARMORY = make_artifact(
    name="Alacrian Armory",
    mana_cost="{3}{W}",
    text="Creatures you control get +0/+1 and have vigilance.\nAt the beginning of combat on your turn, choose up to one target Mount or Vehicle you control. Until end of turn, that permanent becomes saddled if it's a Mount and becomes an artifact creature if it's a Vehicle.",
    rarity="uncommon",
)

BASRI_TOMORROWS_CHAMPION = make_creature(
    name="Basri, Tomorrow's Champion",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="{W}, {T}, Exert Basri: Create a 1/1 white Cat creature token with lifelink. (An exerted creature won't untap during your next untap step.)\nCycling {2}{W} ({2}{W}, Discard this card: Draw a card.)\nWhen you cycle this card, Cats you control gain hexproof and indestructible until end of turn.",
    rarity="rare",
)
# Engine gap: "When you cycle this card" rider trigger (Cats gain hexproof + indestructible) not yet supported.
BASRI_TOMORROWS_CHAMPION.setup_in_hand = make_cycling_setup("{2}{W}")

BRIGHTFIELD_GLIDER = make_creature(
    name="Brightfield Glider",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Possum"},
    text="Vigilance\nWhenever this creature attacks while saddled, it gets +1/+2 and gains flying until end of turn.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="common",
)

BRIGHTFIELD_MUSTANG = make_creature(
    name="Brightfield Mustang",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Horse", "Mount"},
    text="Whenever this creature attacks while saddled, untap it and put a +1/+1 counter on it.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="common",
)

BROADCAST_RAMBLER = make_artifact(
    name="Broadcast Rambler",
    mana_cost="{4}{W}",
    text="When this Vehicle enters, create a 1/1 colorless Thopter artifact creature token with flying.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

BULWARK_OX = make_creature(
    name="Bulwark Ox",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Ox"},
    text="Whenever this creature attacks while saddled, put a +1/+1 counter on target creature.\nSacrifice this creature: Creatures you control with counters on them gain hexproof and indestructible until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="rare",
)

CANYON_VAULTER = make_creature(
    name="Canyon Vaulter",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kor", "Pilot"},
    text="Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gains flying until end of turn.",
    rarity="uncommon",
)

CLOUDSPIRE_CAPTAIN = make_creature(
    name="Cloudspire Captain",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="Mounts and Vehicles you control get +1/+1.\nThis creature saddles Mounts and crews Vehicles as though its power were 2 greater.",
    rarity="uncommon",
)

COLLISION_COURSE = make_sorcery(
    name="Collision Course",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Collision Course deals X damage to target creature, where X is the number of permanents you control that are creatures and/or Vehicles.\n• Destroy target artifact.",
    rarity="common",
    resolve=collision_course_resolve,
)

DARING_MECHANIC = make_creature(
    name="Daring Mechanic",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="{3}{W}: Put a +1/+1 counter on target Mount or Vehicle.",
    rarity="common",
)

DETENTION_CHARIOT = make_artifact(
    name="Detention Chariot",
    mana_cost="{4}{W}{W}",
    text="When this Vehicle enters, exile target artifact or creature an opponent controls until this Vehicle leaves the battlefield.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)\nCycling {W} ({W}, Discard this card: Draw a card.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)
DETENTION_CHARIOT.setup_in_hand = make_cycling_setup("{W}")

GALLANT_STRIKE = make_instant(
    name="Gallant Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Destroy target creature with toughness 4 or greater.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
    resolve=gallant_strike_resolve,
    target_requirements=[target_creature(count=1, toughness_min=4)],
)
GALLANT_STRIKE.setup_in_hand = make_cycling_setup("{2}")

GLORYHEATH_LYNX = make_creature(
    name="Gloryheath Lynx",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Mount"},
    text="Lifelink\nWhenever this creature attacks while saddled, search your library for a basic Plains card, reveal it, put it into your hand, then shuffle.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="uncommon",
)

GUARDIAN_SUNMARE = make_creature(
    name="Guardian Sunmare",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Horse", "Mount"},
    text="Ward {2}\nWhenever this creature attacks while saddled, search your library for a nonland permanent card with mana value 3 or less, put it onto the battlefield, then shuffle.\nSaddle 4",
    rarity="rare",
)

GUIDELIGHT_SYNERGIST = make_artifact_creature(
    name="Guidelight Synergist",
    power=0, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Robot"},
    text="Flying\nThis creature gets +1/+0 for each artifact you control.",
    rarity="uncommon",
)

INTERFACE_ACE = make_artifact_creature(
    name="Interface Ace",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Pilot", "Robot"},
    text="This creature saddles Mounts and crews Vehicles using its toughness rather than its power.\nWhenever this creature becomes tapped during your turn, untap it. This ability triggers only once each turn.",
    rarity="common",
)

LEONIN_SURVEYOR = make_creature(
    name="Leonin Surveyor",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Scout"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nDuring your turn, this creature has first strike.\nMax speed — {3}, Exile this card from your graveyard: Draw a card.",
    rarity="common",
)

LIGHTSHIELD_PARRY = make_instant(
    name="Lightshield Parry",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
    resolve=lightshield_parry_resolve,
    target_requirements=[target_creature(count=1)],
)
LIGHTSHIELD_PARRY.setup_in_hand = make_cycling_setup("{2}")

LIGHTWHEEL_ENHANCEMENTS = make_enchantment(
    name="Lightwheel Enhancements",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Enchant creature or Vehicle\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nEnchanted permanent gets +1/+1 and has vigilance.\nMax speed — You may cast this card from your graveyard.",
    rarity="common",
    subtypes={"Aura"},
)

LOTUSGUARD_DISCIPLE = make_creature(
    name="Lotusguard Disciple",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Cleric"},
    text="Flying\nWhen this creature enters, target creature or Vehicle gains lifelink and indestructible until end of turn.",
    rarity="common",
)

NESTING_BOT = make_artifact_creature(
    name="Nesting Bot",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Robot"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this creature dies, create a 1/1 colorless Servo artifact creature token.\nMax speed — This creature gets +1/+0.",
    rarity="uncommon",
)

PERILOUS_SNARE = make_artifact(
    name="Perilous Snare",
    mana_cost="{2}{W}",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this artifact enters, exile target nonland permanent an opponent controls until this artifact leaves the battlefield.\nMax speed — {T}: Put a +1/+1 counter on target creature or Vehicle you control. Activate only as a sorcery.",
    rarity="rare",
    setup_interceptors=perilous_snare_setup,
)

PRIDE_OF_THE_ROAD = make_creature(
    name="Pride of the Road",
    power=2, toughness=5,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Cat", "Warrior", "Zombie"},
    text="Vigilance\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — At the beginning of combat on your turn, target creature or Vehicle you control gains double strike until end of turn.",
    rarity="uncommon",
)

RIDES_END = make_instant(
    name="Ride's End",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {3} less to cast if it targets a tapped permanent.\nExile target creature or Vehicle.",
    rarity="common",
    resolve=rides_end_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.BATTLEFIELD],
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target creature or Vehicle",
    )],
)

ROADSIDE_ASSISTANCE = make_enchantment(
    name="Roadside Assistance",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Enchant creature or Vehicle\nWhen this Aura enters, create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\"\nEnchanted permanent gets +1/+1 and has lifelink.",
    rarity="uncommon",
    subtypes={"Aura"},
)

SALVATION_ENGINE = make_artifact(
    name="Salvation Engine",
    mana_cost="{4}{W}",
    text="Other artifact creatures you control get +2/+2.\nWhenever this Vehicle attacks, return up to one target artifact card from your graveyard to the battlefield.\nCrew 6",
    rarity="mythic",
    subtypes={"Vehicle"},
)

SKYSEERS_CHARIOT = make_artifact(
    name="Skyseer's Chariot",
    mana_cost="{1}{W}",
    text="Flying\nAs this Vehicle enters, choose a nonland card name.\nActivated abilities of sources with the chosen name cost {2} more to activate.\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
)

SPECTACULAR_PILEUP = make_sorcery(
    name="Spectacular Pileup",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="All creatures and Vehicles lose indestructible until end of turn, then destroy all creatures and Vehicles.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="rare",
)
SPECTACULAR_PILEUP.setup_in_hand = make_cycling_setup("{2}")

SPOTCYCLE_SCOUTER = make_artifact(
    name="Spotcycle Scouter",
    mana_cost="{1}{W}",
    text="When this Vehicle enters, scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

SUNDIAL_DAWN_TYRANT = make_artifact_creature(
    name="Sundial, Dawn Tyrant",
    power=3, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Construct"},
    supertypes={"Legendary"},
    text="",
    rarity="uncommon",
)

SWIFTWING_ASSAILANT = make_creature(
    name="Swiftwing Assailant",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Warrior"},
    text="Flying\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — This creature gets +0/+1 and has vigilance.",
    rarity="common",
)

TUNE_UP = make_sorcery(
    name="Tune Up",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Return target artifact card from your graveyard to the battlefield. If it's a Vehicle, it becomes an artifact creature.",
    rarity="uncommon",
    resolve=tune_up_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.ARTIFACT},
            zones=[ZoneType.GRAVEYARD],
            controller='you',
        ),
        count=1,
        label="target artifact card from your graveyard",
    )],
)

UNSWERVING_SLOTH = make_creature(
    name="Unswerving Sloth",
    power=5, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Mount", "Sloth"},
    text="Whenever this creature attacks while saddled, it gains indestructible until end of turn. Untap all creatures you control.\nSaddle 4 (Tap any number of other creatures you control with total power 4 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="uncommon",
)

VALORS_FLAGSHIP = make_artifact(
    name="Valor's Flagship",
    mana_cost="{4}{W}{W}{W}",
    text="Flying, first strike, lifelink\nCrew 3\nCycling {X}{2}{W} ({X}{2}{W}, Discard this card: Draw a card.)\nWhen you cycle this card, create X 1/1 colorless Pilot creature tokens with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\"",
    rarity="mythic",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)
# Engine gap: "When you cycle this card" rider trigger (create X Pilot tokens) not yet supported.
VALORS_FLAGSHIP.setup_in_hand = make_cycling_setup("{X}{2}{W}")

VOYAGER_GLIDECAR = make_artifact(
    name="Voyager Glidecar",
    mana_cost="{W}",
    text="When this Vehicle enters, scry 1.\nTap three other untapped creatures you control: Until end of turn, this Vehicle becomes an artifact creature and gains flying. Put a +1/+1 counter on it.\nCrew 1",
    rarity="rare",
    subtypes={"Vehicle"},
)

VOYAGER_QUICKWELDER = make_artifact_creature(
    name="Voyager Quickwelder",
    power=2, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Robot"},
    text="Artifact spells you cast cost {1} less to cast.",
    rarity="common",
)

AETHER_SYPHON = make_artifact(
    name="Aether Syphon",
    mana_cost="{1}{U}{U}",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{2}, {T}: Draw a card.\nMax speed — Whenever you draw a card, each opponent mills two cards. (Each opponent puts the top two cards of their library into their graveyard.)",
    rarity="uncommon",
)

BOUNCE_OFF = make_instant(
    name="Bounce Off",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature or Vehicle to its owner's hand.",
    rarity="common",
    resolve=bounce_off_resolve,
    # "target creature or Vehicle" — Vehicle is a subtype check we approximate
    # by using a creature filter (most Vehicles are also creatures when crewed;
    # uncrewed Vehicles need a custom filter, but for cast-time engine prompt
    # the simpler creature/Vehicle subtype handling is left as a small gap).
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.BATTLEFIELD],
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target creature or Vehicle",
    )],
)

CAELORNA_CORAL_TYRANT = make_creature(
    name="Caelorna, Coral Tyrant",
    power=0, toughness=8,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus"},
    supertypes={"Legendary"},
    text="",
    rarity="uncommon",
)

DIVERSION_UNIT = make_artifact_creature(
    name="Diversion Unit",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot"},
    text="Flying\n{U}, Sacrifice this creature: Counter target instant or sorcery spell unless its controller pays {3}.",
    rarity="uncommon",
)

FLOOD_THE_ENGINE = make_enchantment(
    name="Flood the Engine",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Enchant creature or Vehicle\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent loses all abilities and doesn't untap during its controller's untap step.",
    rarity="common",
    subtypes={"Aura"},
)

GEARSEEKER_SERPENT = make_creature(
    name="Gearseeker Serpent",
    power=5, toughness=6,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\n{5}{U}: This creature can't be blocked this turn.",
    rarity="common",
)

GLITCH_GHOST_SURVEYOR = make_creature(
    name="Glitch Ghost Surveyor",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Scout", "Spirit"},
    text="Flying\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {3}, Exile this card from your graveyard: Draw a card.",
    rarity="common",
)

GUIDELIGHT_OPTIMIZER = make_artifact_creature(
    name="Guidelight Optimizer",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot"},
    text="{T}: Add {U}. Spend this mana only to cast an artifact spell or activate an ability.",
    rarity="common",
)

HOWLERS_HEAVY = make_creature(
    name="Howler's Heavy",
    power=3, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Pirate", "Seal"},
    text="Cycling {1}{U} ({1}{U}, Discard this card: Draw a card.)\nWhen you cycle this card, target creature or Vehicle an opponent controls gets -3/-0 until end of turn.",
    rarity="common",
)
# Engine gap: "When you cycle this card" rider trigger (-3/-0 until EOT) not yet supported.
HOWLERS_HEAVY.setup_in_hand = make_cycling_setup("{1}{U}")

HULLDRIFTER = make_artifact(
    name="Hulldrifter",
    mana_cost="{3}{U}{U}",
    text="Flying\nWhen this Vehicle enters, draw two cards.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

KEEN_BUCCANEER = make_creature(
    name="Keen Buccaneer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus", "Pirate"},
    text="Vigilance\nExhaust — {1}{U}: Draw a card, then discard a card. Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=keen_buccaneer_setup,
)

MEMORY_GUARDIAN = make_artifact_creature(
    name="Memory Guardian",
    power=3, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Robot"},
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nFlying",
    rarity="uncommon",
)

MIDNIGHT_MANGLER = make_artifact(
    name="Midnight Mangler",
    mana_cost="{1}{U}",
    text="During turns other than yours, this Vehicle is an artifact creature.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

MINDSPRING_MERFOLK = make_creature(
    name="Mindspring Merfolk",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Wizard"},
    text="Exhaust — {X}{U}{U}, {T}: Draw X cards. Put a +1/+1 counter on each Merfolk creature you control. (Activate each exhaust ability only once.)",
    rarity="rare",
    setup_interceptors=mindspring_merfolk_setup,
)

MU_YANLING_WIND_RIDER = make_creature(
    name="Mu Yanling, Wind Rider",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pilot", "Wizard"},
    supertypes={"Legendary"},
    text="When Mu Yanling enters, create a 3/2 colorless Vehicle artifact token with crew 1.\nVehicles you control have flying.\nWhenever one or more creatures you control with flying deal combat damage to a player, draw a card.",
    rarity="mythic",
)

NIMBLE_THOPTERIST = make_creature(
    name="Nimble Thopterist",
    power=3, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Vedalken"},
    text="When this creature enters, create a 1/1 colorless Thopter artifact creature token with flying.",
    rarity="common",
)

POSSESSION_ENGINE = make_artifact(
    name="Possession Engine",
    mana_cost="{3}{U}{U}",
    text="When this Vehicle enters, gain control of target creature an opponent controls for as long as you control this Vehicle. That creature can't attack or block for as long as you control this Vehicle.\nCrew 3",
    rarity="rare",
    subtypes={"Vehicle"},
)

RANGERS_REFUELER = make_artifact(
    name="Rangers' Refueler",
    mana_cost="{1}{U}",
    text="Whenever you activate an exhaust ability, draw a card.\nExhaust — {4}: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it. (Activate each exhaust ability only once.)\nCrew 2",
    rarity="uncommon",
    subtypes={"Vehicle"},
    setup_interceptors=rangers_refueler_setup,
)

REPURPOSING_BAY = make_artifact(
    name="Repurposing Bay",
    mana_cost="{2}{U}",
    text="{2}, {T}, Sacrifice another artifact: Search your library for an artifact card with mana value equal to 1 plus the sacrificed artifact's mana value, put that card onto the battlefield, then shuffle. Activate only as a sorcery.",
    rarity="rare",
)

RIVERCHURN_MONUMENT = make_artifact(
    name="Riverchurn Monument",
    mana_cost="{1}{U}",
    text="{1}, {T}: Any number of target players each mill two cards. (Each of them puts the top two cards of their library into their graveyard.)\nExhaust — {2}{U}{U}, {T}: Any number of target players each mill cards equal to the number of cards in their graveyard. (Activate each exhaust ability only once.)",
    rarity="rare",
    setup_interceptors=riverchurn_monument_setup,
)

ROADSIDE_BLOWOUT = make_sorcery(
    name="Roadside Blowout",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="This spell costs {2} less to cast if it targets a permanent with mana value 1.\nReturn target creature or Vehicle an opponent controls to its owner's hand.\nDraw a card.",
    rarity="uncommon",
    resolve=roadside_blowout_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.BATTLEFIELD],
            controller='opponent',
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target opponent's creature or Vehicle",
    )],
)

SABOTAGE_STRATEGIST = make_creature(
    name="Sabotage Strategist",
    power=2, toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Ranger", "Vedalken"},
    text="Flying, vigilance\nWhenever one or more creatures attack you, those creatures get -1/-0 until end of turn.\nExhaust — {5}{U}{U}: Put three +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
)

SCROUNGING_SKYRAY = make_creature(
    name="Scrounging Skyray",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Pirate"},
    text="Flying\nWhenever you discard one or more cards, put that many +1/+1 counters on this creature.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
)
SCROUNGING_SKYRAY.setup_in_hand = make_cycling_setup("{2}")

SKYSTREAK_ENGINEER = make_creature(
    name="Skystreak Engineer",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pilot"},
    text="Flying\nExhaust — {4}{U}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=skystreak_engineer_setup,
)

SLICK_IMITATOR = make_creature(
    name="Slick Imitator",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Ooze"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {1}, Sacrifice this creature: Copy target spell you control. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)",
    rarity="uncommon",
)

SPECTRAL_INTERFERENCE = make_instant(
    name="Spectral Interference",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target artifact or creature spell unless its controller pays {4}.",
    rarity="common",
    resolve=spectral_interference_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.ARTIFACT, CardType.CREATURE},
            zones=[ZoneType.STACK],
        ),
        count=1,
        label="target artifact or creature spell",
    )],
)

SPELL_PIERCE = make_instant(
    name="Spell Pierce",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target noncreature spell unless its controller pays {2}.",
    rarity="uncommon",
    resolve=spell_pierce_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            zones=[ZoneType.STACK],
            custom_filter=lambda obj, st: CardType.CREATURE not in obj.characteristics.types,
        ),
        count=1,
        label="target noncreature spell",
    )],
)

SPIKESHELL_HARRIER = make_artifact_creature(
    name="Spikeshell Harrier",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Turtle"},
    text="When this creature enters, return target creature or Vehicle an opponent controls to its owner's hand. If that opponent's speed is greater than each other player's speed, reduce that opponent's speed by 1. This effect can't reduce their speed below 1.",
    rarity="uncommon",
)

STALL_OUT = make_sorcery(
    name="Stall Out",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature or Vehicle, then put three stun counters on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
    resolve=stall_out_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.BATTLEFIELD],
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target creature or Vehicle",
    )],
)
STALL_OUT.setup_in_hand = make_cycling_setup("{2}")

STOCK_UP = make_sorcery(
    name="Stock Up",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom of your library in any order.",
    rarity="uncommon",
)

THOPTER_FABRICATOR = make_artifact(
    name="Thopter Fabricator",
    mana_cost="{2}{U}",
    text="Flying\nWhenever you draw your second card each turn, create a 1/1 colorless Thopter artifact creature token with flying.\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
)

TRADE_THE_HELM = make_sorcery(
    name="Trade the Helm",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="Exchange control of target artifact or creature you control and target artifact or creature an opponent controls.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
)
TRADE_THE_HELM.setup_in_hand = make_cycling_setup("{2}")

TRANSIT_MAGE = make_creature(
    name="Transit Mage",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, you may search your library for an artifact card with mana value 4 or 5, reveal it, put it into your hand, then shuffle.",
    rarity="uncommon",
)

TRIP_UP = make_instant(
    name="Trip Up",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Target nonland permanent's owner puts it on their choice of the top or bottom of their library.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
    resolve=trip_up_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER},
            zones=[ZoneType.BATTLEFIELD],
        ),
        count=1,
        label="target nonland permanent",
    )],
)
TRIP_UP.setup_in_hand = make_cycling_setup("{2}")

UNSTOPPABLE_PLAN = make_enchantment(
    name="Unstoppable Plan",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="At the beginning of your end step, untap all nonland permanents you control.",
    rarity="rare",
)

VNWXT_VERBOSE_HOST = make_creature(
    name="Vnwxt, Verbose Host",
    power=0, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Homunculus"},
    supertypes={"Legendary"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nYou have no maximum hand size.\nMax speed — If you would draw a card, draw two cards instead.",
    rarity="rare",
)

WAXEN_SHAPETHIEF = make_creature(
    name="Waxen Shapethief",
    power=0, toughness=0,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter"},
    text="Flash\nYou may have this creature enter as a copy of an artifact or creature you control.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="rare",
)
WAXEN_SHAPETHIEF.setup_in_hand = make_cycling_setup("{2}")

ANCIENT_VENDETTA = make_sorcery(
    name="Ancient Vendetta",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Choose a card name. Search target opponent's graveyard, hand, and library for up to four cards with that name and exile them. Then that player shuffles.",
    rarity="uncommon",
)

BACK_ON_TRACK = make_sorcery(
    name="Back on Track",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature or Vehicle card from your graveyard to the battlefield. Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\"",
    rarity="uncommon",
    resolve=back_on_track_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.GRAVEYARD],
            controller='you',
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target creature or Vehicle card from your graveyard",
    )],
)

BLOODGHAST = make_creature(
    name="Bloodghast",
    power=2, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Vampire"},
    text="This creature can't block.\nThis creature has haste as long as an opponent has 10 or less life.\nLandfall — Whenever a land you control enters, you may return this card from your graveyard to the battlefield.",
    rarity="rare",
)

CARRION_CRUISER = make_artifact(
    name="Carrion Cruiser",
    mana_cost="{2}{B}",
    text="When this Vehicle enters, mill two cards. Then return a creature or Vehicle card from your graveyard to your hand. (To mill two cards, put the top two cards of your library into your graveyard.)\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

CHITIN_GRAVESTALKER = make_creature(
    name="Chitin Gravestalker",
    power=5, toughness=4,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Warrior"},
    text="This spell costs {1} less to cast for each artifact and/or creature card in your graveyard.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
)
CHITIN_GRAVESTALKER.setup_in_hand = make_cycling_setup("{2}")

CRYPTCALLER_CHARIOT = make_artifact(
    name="Cryptcaller Chariot",
    mana_cost="{3}{B}",
    text="Menace\nWhenever you discard one or more cards, create that many tapped 2/2 black Zombie creature tokens.\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
)

CURSECLOTH_WRAPPINGS = make_artifact(
    name="Cursecloth Wrappings",
    mana_cost="{2}{B}{B}",
    text="Zombies you control get +1/+1.\n{T}: Target creature card in your graveyard gains embalm until end of turn. The embalm cost is equal to its mana cost. (Exile that card and pay its embalm cost: Create a token that's a copy of it, except it's a white Zombie in addition to its other types and has no mana cost. Embalm only as a sorcery.)",
    rarity="rare",
)

DEATHLESS_PILOT = make_creature(
    name="Deathless Pilot",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Pilot", "Zombie"},
    text="This creature saddles Mounts and crews Vehicles as though its power were 2 greater.\n{3}{B}: Return this card from your graveyard to your hand.",
    rarity="common",
)

DEMONIC_JUNKER = make_artifact(
    name="Demonic Junker",
    mana_cost="{6}{B}",
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nWhen this Vehicle enters, for each player, destroy up to one target creature that player controls. If a creature you controlled was destroyed this way, put two +1/+1 counters on this Vehicle.\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
)

ENGINE_RAT = make_creature(
    name="Engine Rat",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat", "Zombie"},
    text="Deathtouch\n{5}{B}: Each opponent loses 2 life.",
    rarity="common",
)

GAS_GUZZLER = make_creature(
    name="Gas Guzzler",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nThis creature enters tapped.\nMax speed — {B}, Sacrifice another creature or Vehicle: Draw a card.",
    rarity="rare",
)

GASTAL_RAIDER = make_creature(
    name="Gastal Raider",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Rogue", "Vampire"},
    text="Start your engines!\nWhen this creature enters, target opponent reveals their hand. You choose an instant or sorcery card from it. That player discards that card.\nMax speed — This creature gets +1/+1 and has menace.",
    rarity="uncommon",
)

GONTI_NIGHT_MINISTER = make_creature(
    name="Gonti, Night Minister",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Aetherborn", "Rogue"},
    supertypes={"Legendary"},
    text="Whenever a player casts a spell they don't own, that player creates a Treasure token.\nWhenever a creature deals combat damage to one of your opponents, its controller looks at the top card of that opponent's library and exiles it face down. They may play that card for as long as it remains exiled. Mana of any type can be spent to cast a spell this way.",
    rarity="rare",
)

GRIM_BAUBLE = make_artifact(
    name="Grim Bauble",
    mana_cost="{B}",
    text="When this artifact enters, target creature an opponent controls gets -2/-2 until end of turn.\n{2}{B}, {T}, Sacrifice this artifact: Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    rarity="common",
)

GRIM_JAVELINEER = make_creature(
    name="Grim Javelineer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="Whenever you attack, target attacking creature gets +1/+0 until end of turn. When that creature dies this turn, surveil 1. (Look at the top card of your library. You may put that card into your graveyard.)",
    rarity="common",
)

HELLISH_SIDESWIPE = make_sorcery(
    name="Hellish Sideswipe",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice an artifact or creature.\nDestroy target creature or Vehicle. If the sacrificed permanent was a Vehicle, draw a card.",
    rarity="uncommon",
    resolve=hellish_sideswipe_resolve,
)

HOUR_OF_VICTORY = make_enchantment(
    name="Hour of Victory",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Start your engines!\nWhen this enchantment enters, create a 2/2 black Zombie creature token.\nMax speed — {1}{B}, Sacrifice this enchantment: Search your library for a card, put it into your hand, then shuffle. Activate only as a sorcery.",
    rarity="uncommon",
)

INTIMIDATION_TACTICS = make_sorcery(
    name="Intimidation Tactics",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose an artifact or creature card from it. Exile that card.\nCycling {3} ({3}, Discard this card: Draw a card.)",
    rarity="uncommon",
)
INTIMIDATION_TACTICS.setup_in_hand = make_cycling_setup("{3}")

KALAKSCION_HUNGER_TYRANT = make_creature(
    name="Kalakscion, Hunger Tyrant",
    power=7, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Crocodile"},
    supertypes={"Legendary"},
    text="",
    rarity="uncommon",
)

THE_LAST_RIDE = make_artifact(
    name="The Last Ride",
    mana_cost="{B}",
    text="The Last Ride gets -X/-X, where X is your life total.\n{2}{B}, Pay 2 life: Draw a card.\nCrew 2",
    rarity="mythic",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

LOCUST_SPRAY = make_instant(
    name="Locust Spray",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn.\nCycling {B} ({B}, Discard this card: Draw a card.)",
    rarity="uncommon",
    resolve=locust_spray_resolve,
    target_requirements=[target_creature(count=1)],
)
LOCUST_SPRAY.setup_in_hand = make_cycling_setup("{B}")

MAXIMUM_OVERDRIVE = make_instant(
    name="Maximum Overdrive",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Put a +1/+1 counter on target creature. It gains deathtouch and indestructible until end of turn.",
    rarity="common",
    resolve=maximum_overdrive_resolve,
    target_requirements=[target_creature(count=1)],
)

MOMENTUM_BREAKER = make_enchantment(
    name="Momentum Breaker",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this enchantment enters, each opponent sacrifices a creature or Vehicle of their choice. Each opponent who can't discards a card.\n{2}, Sacrifice this enchantment: You gain life equal to your speed.",
    rarity="uncommon",
)

MUTANT_SURVEYOR = make_creature(
    name="Mutant Surveyor",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Mutant", "Scout"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{2}: This creature gets +1/+1 until end of turn.\nMax speed — {3}, Exile this card from your graveyard: Draw a card.",
    rarity="common",
)

PACTDOLL_TERROR = make_artifact_creature(
    name="Pactdoll Terror",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Toy"},
    text="Whenever this creature or another artifact you control enters, each opponent loses 1 life and you gain 1 life.",
    rarity="common",
)

QUAG_FEAST = make_sorcery(
    name="Quag Feast",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose target creature, planeswalker, or Vehicle. Mill two cards, then destroy the chosen permanent if its mana value is less than or equal to the number of cards in your graveyard.",
    rarity="rare",
)

RIPCLAW_WRANGLER = make_artifact(
    name="Ripclaw Wrangler",
    mana_cost="{3}{B}",
    text="When this Vehicle enters, each opponent discards a card.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

RISEN_NECROREGENT = make_creature(
    name="Risen Necroregent",
    power=5, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Cat", "Knight", "Zombie"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — At the beginning of your end step, create a 2/2 black Zombie creature token.",
    rarity="uncommon",
)

RISKY_SHORTCUT = make_sorcery(
    name="Risky Shortcut",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Draw two cards. Each player loses 2 life.",
    rarity="common",
)

SHEFET_ARCHFIEND = make_creature(
    name="Shefet Archfiend",
    power=5, toughness=5,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying\nWhen this creature enters, all other creatures get -2/-2 until end of turn.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
)
SHEFET_ARCHFIEND.setup_in_hand = make_cycling_setup("{2}")

THE_SPEED_DEMON = make_creature(
    name="The Speed Demon",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, trample\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nAt the beginning of your end step, you draw X cards and lose X life, where X is your speed.",
    rarity="mythic",
)

SPIN_OUT = make_instant(
    name="Spin Out",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature or Vehicle.",
    rarity="common",
    resolve=spin_out_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.ARTIFACT},
            zones=[ZoneType.BATTLEFIELD],
            custom_filter=lambda obj, st: (
                CardType.CREATURE in obj.characteristics.types
                or 'Vehicle' in obj.characteristics.subtypes
            ),
        ),
        count=1,
        label="target creature or Vehicle",
    )],
)

STREAKING_OILGORGER = make_creature(
    name="Streaking Oilgorger",
    power=3, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying, haste\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — This creature has lifelink.",
    rarity="common",
)

SYPHON_FUEL = make_instant(
    name="Syphon Fuel",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Target creature gets -6/-6 until end of turn. You gain 2 life.",
    rarity="common",
    resolve=syphon_fuel_resolve,
    target_requirements=[target_creature(count=1)],
)

WICKERFOLK_INDOMITABLE = make_artifact_creature(
    name="Wickerfolk Indomitable",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Scarecrow"},
    text="You may cast this card from your graveyard by paying 2 life and sacrificing an artifact or creature in addition to paying its other costs.",
    rarity="uncommon",
)

WRECKAGE_WICKERFOLK = make_artifact_creature(
    name="Wreckage Wickerfolk",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scarecrow"},
    text="Flying\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    rarity="common",
)

WRETCHED_DOLL = make_artifact_creature(
    name="Wretched Doll",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Toy"},
    text="{B}, {T}: Surveil 1. (Look at the top card of your library. You may put that card into your graveyard.)",
    rarity="uncommon",
)

ADRENALINE_JOCKEY = make_creature(
    name="Adrenaline Jockey",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Pilot"},
    text="Whenever a player casts a spell, if it's not their turn, this creature deals 4 damage to them.\nWhenever you activate an exhaust ability, put a +1/+1 counter on this creature.",
    rarity="uncommon",
)

BOOMMOBILE = make_artifact(
    name="Boommobile",
    mana_cost="{2}{R}{R}",
    text="When this Vehicle enters, add four mana of any one color. Spend this mana only to activate abilities.\nExhaust — {X}{2}{R}: This Vehicle deals X damage to any target. Put a +1/+1 counter on this Vehicle. (Activate each exhaust ability only once.)\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
    setup_interceptors=boommobile_setup,
)

BURNER_ROCKET = make_artifact(
    name="Burner Rocket",
    mana_cost="{1}{R}",
    text="Flash\nWhen this Vehicle enters, target creature you control gets +2/+0 and gains trample until end of turn.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

BURNOUT_BASHTRONAUT = make_creature(
    name="Burnout Bashtronaut",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Menace\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{2}: This creature gets +1/+0 until end of turn.\nMax speed — This creature has double strike.",
    rarity="rare",
)

CHANDRA_SPARK_HUNTER = make_planeswalker(
    name="Chandra, Spark Hunter",
    mana_cost="{3}{R}",
    colors={Color.RED},
    loyalty=4,
    subtypes={"Chandra"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, choose up to one target Vehicle you control. Until end of turn, it becomes an artifact creature and gains haste.\n+2: You may sacrifice an artifact or discard a card. If you do, draw a card.\n0: Create a 3/2 colorless Vehicle artifact token with crew 1.\n−7: You get an emblem with \"Whenever an artifact you control enters, this emblem deals 3 damage to any target.\"",
    rarity="mythic",
)

CLAMOROUS_IRONCLAD = make_artifact(
    name="Clamorous Ironclad",
    mana_cost="{3}{R}",
    text="Menace (This creature can't be blocked except by two or more creatures.)\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)\nCycling {R} ({R}, Discard this card: Draw a card.)",
    rarity="common",
    subtypes={"Vehicle"},
)
CLAMOROUS_IRONCLAD.setup_in_hand = make_cycling_setup("{R}")

COUNT_ON_LUCK = make_enchantment(
    name="Count on Luck",
    mana_cost="{R}{R}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, exile the top card of your library. You may play that card this turn.",
    rarity="rare",
)

CRASH_AND_BURN = make_instant(
    name="Crash and Burn",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Choose one —\n• Destroy target Vehicle.\n• Crash and Burn deals 6 damage to target creature or planeswalker.",
    rarity="common",
    resolve=crash_and_burn_resolve,
)

DARETTI_ROCKETEER_ENGINEER = make_creature(
    name="Daretti, Rocketeer Engineer",
    power=0, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Goblin"},
    supertypes={"Legendary"},
    text="Daretti's power is equal to the greatest mana value among artifacts you control.\nWhenever Daretti enters or attacks, choose target artifact card in your graveyard. You may sacrifice an artifact. If you do, return the chosen card to the battlefield.",
    rarity="rare",
)

DRACONAUTICS_ENGINEER = make_creature(
    name="Draconautics Engineer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Goblin"},
    text="Exhaust — {R}: Other creatures you control gain haste until end of turn. Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)\nExhaust — {3}{R}: Create a 4/4 red Dinosaur Dragon creature token with flying.",
    rarity="rare",
    setup_interceptors=draconautics_engineer_setup,
)

DRACOSAUR_AUXILIARY = make_creature(
    name="Dracosaur Auxiliary",
    power=4, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Dragon", "Mount"},
    text="Flying, haste\nWhenever this creature attacks while saddled, it deals 2 damage to any target.\nSaddle 3 (Tap any number of other creatures you control with total power 3 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="uncommon",
)

DYNAMITE_DIVER = make_creature(
    name="Dynamite Diver",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Pilot"},
    text="This creature saddles Mounts and crews Vehicles as though its power were 2 greater.\nWhen this creature dies, it deals 1 damage to any target.",
    rarity="common",
)

ENDRIDER_CATALYZER = make_creature(
    name="Endrider Catalyzer",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {T}: Add {R}{R}.",
    rarity="common",
)

ENDRIDER_SPIKESPITTER = make_creature(
    name="Endrider Spikespitter",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="Reach\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — At the beginning of your upkeep, exile the top card of your library. You may play that card this turn.",
    rarity="uncommon",
)

FUEL_THE_FLAMES = make_instant(
    name="Fuel the Flames",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Fuel the Flames deals 2 damage to each creature.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
    resolve=fuel_the_flames_resolve,
)
FUEL_THE_FLAMES.setup_in_hand = make_cycling_setup("{2}")

FULL_THROTTLE = make_sorcery(
    name="Full Throttle",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="After this main phase, there are two additional combat phases.\nAt the beginning of each combat this turn, untap all creatures that attacked this turn.",
    rarity="rare",
)

GASTAL_BLOCKBUSTER = make_creature(
    name="Gastal Blockbuster",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Berserker", "Human"},
    text="When this creature enters, you may sacrifice a creature or Vehicle. When you do, destroy target artifact an opponent controls.",
    rarity="common",
)

GASTAL_THRILLROLLER = make_artifact(
    name="Gastal Thrillroller",
    mana_cost="{2}{R}",
    text="Trample, haste\nWhen this Vehicle enters, it becomes an artifact creature until end of turn.\nCrew 2\n{2}{R}, Discard a card: Return this card from your graveyard to the battlefield with a finality counter on it. Activate only as a sorcery.",
    rarity="rare",
    subtypes={"Vehicle"},
)

GILDED_GHODA = make_creature(
    name="Gilded Ghoda",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Horse", "Mount"},
    text="Whenever this creature attacks while saddled, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="common",
)

GOBLIN_SURVEYOR = make_creature(
    name="Goblin Surveyor",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Scout"},
    text="Trample\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {3}, Exile this card from your graveyard: Draw a card.",
    rarity="common",
)

GREASEWRENCH_GOBLIN = make_creature(
    name="Greasewrench Goblin",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Goblin"},
    text="Exhaust — {2}{R}: Discard up to two cards, then draw that many cards. Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
    setup_interceptors=greasewrench_goblin_setup,
)

HAZORET_GODSEEKER = make_creature(
    name="Hazoret, Godseeker",
    power=5, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Indestructible, haste\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{1}, {T}: Target creature with power 2 or less can't be blocked this turn.\nHazoret can't attack or block unless you have max speed.",
    rarity="mythic",
)

HOWLSQUAD_HEAVY = make_creature(
    name="Howlsquad Heavy",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Mercenary"},
    text="Start your engines!\nOther Goblins you control have haste.\nAt the beginning of combat on your turn, create a 1/1 red Goblin creature token. That token attacks this combat if able.\nMax speed — {T}: Add {R} for each Goblin you control.",
    rarity="rare",
)

KICKOFF_CELEBRATIONS = make_enchantment(
    name="Kickoff Celebrations",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this enchantment enters, you may discard a card. If you do, draw two cards.\nMax speed — Sacrifice this enchantment: Creatures and Vehicles you control gain haste until end of turn.",
    rarity="common",
)

LIGHTNING_STRIKE = make_instant(
    name="Lightning Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lightning Strike deals 3 damage to any target.",
    rarity="common",
    resolve=lightning_strike_resolve,
    target_requirements=[target_any(count=1)],
)

MAGMAKIN_ARTILLERIST = make_creature(
    name="Magmakin Artillerist",
    power=1, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Pirate"},
    text="Whenever you discard one or more cards, this creature deals that much damage to each opponent.\nCycling {1}{R} ({1}{R}, Discard this card: Draw a card.)\nWhen you cycle this card, it deals 1 damage to each opponent.",
    rarity="common",
)
# Engine gap: "When you cycle this card" rider trigger (1 damage to each opponent) not yet supported.
MAGMAKIN_ARTILLERIST.setup_in_hand = make_cycling_setup("{1}{R}")

MARAUDING_MAKO = make_creature(
    name="Marauding Mako",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Pirate", "Shark"},
    text="Whenever you discard one or more cards, put that many +1/+1 counters on this creature.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
)
MARAUDING_MAKO.setup_in_hand = make_cycling_setup("{2}")

OUTPACE_OBLIVION = make_enchantment(
    name="Outpace Oblivion",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this enchantment enters, it deals 5 damage to up to one target creature or planeswalker.\n{2}, Sacrifice this enchantment: It deals 2 damage to each player who doesn't have max speed.",
    rarity="uncommon",
)

PACESETTER_PARAGON = make_creature(
    name="Pacesetter Paragon",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pilot"},
    text="Exhaust — {2}{R}: Put a +1/+1 counter on this creature. It gains double strike until end of turn. (Activate each exhaust ability only once.)",
    rarity="uncommon",
    setup_interceptors=pacesetter_paragon_setup,
)

PEDAL_TO_THE_METAL = make_instant(
    name="Pedal to the Metal",
    mana_cost="{X}{R}",
    colors={Color.RED},
    text="Target creature gets +X/+0 and gains first strike until end of turn.",
    rarity="common",
    resolve=pedal_to_the_metal_resolve,
    target_requirements=[target_creature(count=1)],
)

PROWCATCHER_SPECIALIST = make_creature(
    name="Prowcatcher Specialist",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Haste\nExhaust — {3}{R}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=prowcatcher_specialist_setup,
)

PUSH_THE_LIMIT = make_sorcery(
    name="Push the Limit",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    text="Return all Mount and Vehicle cards from your graveyard to the battlefield. Sacrifice them at the beginning of the next end step.\nVehicles you control become artifact creatures until end of turn. Creatures you control gain haste until end of turn.",
    rarity="uncommon",
)

RECKLESS_VELOCITAUR = make_creature(
    name="Reckless Velocitaur",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Pilot"},
    text="Whenever this creature saddles a Mount or crews a Vehicle during your main phase, that Mount or Vehicle gets +2/+0 and gains trample until end of turn.",
    rarity="uncommon",
)

ROAD_RAGE = make_instant(
    name="Road Rage",
    mana_cost="{R}",
    colors={Color.RED},
    text="Road Rage deals X damage to target creature or planeswalker, where X is 2 plus the number of Mounts and Vehicles you control.",
    rarity="uncommon",
    resolve=road_rage_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.PLANESWALKER},
            zones=[ZoneType.BATTLEFIELD],
        ),
        count=1,
        label="target creature or planeswalker",
    )],
)

SKYCRASH = make_instant(
    name="Skycrash",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact.\nCycling {R} ({R}, Discard this card: Draw a card.)",
    rarity="uncommon",
    resolve=skycrash_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(types={CardType.ARTIFACT}, zones=[ZoneType.BATTLEFIELD]),
        count=1,
        label="target artifact",
    )],
)
SKYCRASH.setup_in_hand = make_cycling_setup("{R}")

SPIRE_MECHCYCLE = make_artifact(
    name="Spire Mechcycle",
    mana_cost="{4}{R}",
    text="Haste\nExhaust — Tap another untapped Mount or Vehicle you control: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it for each Mount and/or Vehicle you control other than this Vehicle. (Activate each exhaust ability only once.)\nCrew 2",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

THUNDERHEAD_GUNNER = make_creature(
    name="Thunderhead Gunner",
    power=4, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Pirate", "Shark"},
    text="Reach\nDiscard a card: Draw a card. Activate only as a sorcery and only once each turn.",
    rarity="common",
)

TYROX_SAURID_TYRANT = make_creature(
    name="Tyrox, Saurid Tyrant",
    power=4, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dinosaur", "Warrior"},
    supertypes={"Legendary"},
    text="",
    rarity="uncommon",
)

AFTERBURNER_EXPERT = make_creature(
    name="Afterburner Expert",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Artificer", "Goblin"},
    text="Exhaust — {2}{G}{G}: Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)\nWhenever you activate an exhaust ability, return this card from your graveyard to the battlefield.",
    rarity="rare",
    setup_interceptors=afterburner_expert_setup,
)
AFTERBURNER_EXPERT.setup_in_graveyard = afterburner_expert_in_graveyard_setup

AGONASAUR_REX = make_creature(
    name="Agonasaur Rex",
    power=8, toughness=8,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nCycling {2}{G} ({2}{G}, Discard this card: Draw a card.)\nWhen you cycle this card, put two +1/+1 counters on up to one target creature or Vehicle. It gains trample and indestructible until end of turn.",
    rarity="rare",
)
# Engine gap: "When you cycle this card" rider trigger (two +1/+1 counters and trample) not yet supported.
AGONASAUR_REX.setup_in_hand = make_cycling_setup("{2}{G}")

ALACRIAN_JAGUAR = make_creature(
    name="Alacrian Jaguar",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Mount"},
    text="Vigilance\nWhenever this creature attacks while saddled, it gets +2/+2 until end of turn.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="common",
)

AUTARCH_MAMMOTH = make_creature(
    name="Autarch Mammoth",
    power=5, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant", "Mount"},
    text="When this creature enters and whenever it attacks while saddled, create a 3/3 green Elephant creature token.\nSaddle 5 (Tap any number of other creatures you control with total power 5 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="uncommon",
)

BEASTRIDER_VANGUARD = make_creature(
    name="Beastrider Vanguard",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Knight"},
    text="{4}{G}: Look at the top three cards of your library. You may reveal a permanent card from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
    rarity="common",
)

BESTOW_GREATNESS = make_instant(
    name="Bestow Greatness",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 and gains trample until end of turn.",
    rarity="common",
    resolve=bestow_greatness_resolve,
    target_requirements=[target_creature(count=1)],
)

BROKEN_WINGS = make_instant(
    name="Broken Wings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying.",
    rarity="common",
    resolve=broken_wings_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.CREATURE},
            zones=[ZoneType.BATTLEFIELD],
            custom_filter=lambda obj, st: (
                CardType.ARTIFACT in obj.characteristics.types
                or CardType.ENCHANTMENT in obj.characteristics.types
                or (CardType.CREATURE in obj.characteristics.types
                    and any((a.get('keyword') if isinstance(a, dict) else str(a)).lower() == 'flying'
                            for a in (obj.characteristics.abilities or [])))
            ),
        ),
        count=1,
        label="target artifact, enchantment, or creature with flying",
    )],
)

DEFEND_THE_RIDER = make_instant(
    name="Defend the Rider",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Target permanent you control gains hexproof and indestructible until end of turn.\n• Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\"",
    rarity="uncommon",
    resolve=defend_the_rider_resolve,
)

DISTRICT_MASCOT = make_creature(
    name="District Mascot",
    power=0, toughness=0,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Dog", "Mount"},
    text="This creature enters with a +1/+1 counter on it.\n{1}{G}, Remove two +1/+1 counters from this creature: Destroy target artifact.\nWhenever this creature attacks while saddled, put a +1/+1 counter on it.\nSaddle 1",
    rarity="rare",
)

DREDGERS_INSIGHT = make_enchantment(
    name="Dredger's Insight",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Whenever one or more artifact and/or creature cards leave your graveyard, you gain 1 life.\nWhen this enchantment enters, mill four cards. You may put an artifact, creature, or land card from among the milled cards into your hand. (To mill four cards, put the top four cards of your library into your graveyard.)",
    rarity="uncommon",
)

EARTHRUMBLER = make_artifact(
    name="Earthrumbler",
    mana_cost="{4}{G}",
    text="Vigilance, trample\nExile an artifact or creature card from your graveyard: This Vehicle becomes an artifact creature until end of turn.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

ELVISH_REFUELER = make_creature(
    name="Elvish Refueler",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elf"},
    text="During your turn, as long as you haven't activated an exhaust ability this turn, you may activate exhaust abilities as though they haven't been activated.\nExhaust — {1}{G}: Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
    setup_interceptors=elvish_refueler_setup,
)

FANG_GUARDIAN = make_creature(
    name="Fang Guardian",
    power=4, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ape", "Druid"},
    text="Flash\nWhen this creature enters, another target creature or Vehicle you control gets +2/+2 until end of turn.",
    rarity="uncommon",
)

FANGDRUID_SUMMONER = make_creature(
    name="Fang-Druid Summoner",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ape", "Druid"},
    text="Reach\nWhen this creature enters, you may search your library and/or graveyard for a creature card with no abilities, reveal it, and put it into your hand. If you search your library this way, shuffle.",
    rarity="uncommon",
)

GREENBELT_GUARDIAN = make_creature(
    name="Greenbelt Guardian",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Ranger"},
    text="{G}: Target creature gains trample until end of turn.\nExhaust — {3}{G}: Put three +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
)

HAZARD_OF_THE_DUNES = make_creature(
    name="Hazard of the Dunes",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Wurm"},
    text="Trample, reach\nExhaust — {6}{G}: Put three +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=hazard_of_the_dunes_setup,
)

JIBBIRIK_OMNIVORE = make_creature(
    name="Jibbirik Omnivore",
    power=3, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="",
    rarity="common",
)

LOXODON_SURVEYOR = make_creature(
    name="Loxodon Surveyor",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant", "Scout"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — {3}, Exile this card from your graveyard: Draw a card.",
    rarity="common",
)

LUMBERING_WORLDWAGON = make_artifact(
    name="Lumbering Worldwagon",
    mana_cost="{2}{G}",
    text="This Vehicle's power is equal to the number of lands you control.\nWhenever this Vehicle enters or attacks, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nCrew 4",
    rarity="rare",
    subtypes={"Vehicle"},
)

MARCH_OF_THE_WORLD_OOZE = make_enchantment(
    name="March of the World Ooze",
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control have base power and toughness 6/6 and are Oozes in addition to their other types.\nWhenever an opponent casts a spell, if it's not their turn, you create a 3/3 green Elephant creature token.",
    rarity="mythic",
)

MIGRATING_KETRADON = make_creature(
    name="Migrating Ketradon",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Reach\nWhen this creature enters, you gain 4 life.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
)
MIGRATING_KETRADON.setup_in_hand = make_cycling_setup("{2}")

MOLT_TENDER = make_creature(
    name="Molt Tender",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Insect"},
    text="{T}: Mill a card. (Put the top card of your library into your graveyard.)\n{T}, Exile a card from your graveyard: Add one mana of any color.",
    rarity="uncommon",
)

OOZE_PATROL = make_creature(
    name="Ooze Patrol",
    power=2, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Ooze"},
    text="When this creature enters, mill two cards, then put a +1/+1 counter on this creature for each artifact and/or creature card in your graveyard. (To mill two cards, put the top two cards of your library into your graveyard.)",
    rarity="uncommon",
)

OVIYA_AUTOMECH_ARTISAN = make_creature(
    name="Oviya, Automech Artisan",
    power=1, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="Each creature that's attacking one of your opponents has trample.\n{G}, {T}: You may put a creature or Vehicle card from your hand onto the battlefield. If you put an artifact onto the battlefield this way, put two +1/+1 counters on it.",
    rarity="rare",
)

PLOW_THROUGH = make_sorcery(
    name="Plow Through",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Target creature you control fights target creature an opponent controls. (Each deals damage equal to its power to the other.)\n• Destroy target Vehicle.",
    rarity="uncommon",
    resolve=plow_through_resolve,
)

POINT_THE_WAY = make_enchantment(
    name="Point the Way",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{3}{G}, Sacrifice this enchantment: Search your library for up to X basic land cards, where X is your speed. Put those cards onto the battlefield tapped, then shuffle.",
    rarity="uncommon",
)

POTHOLE_MOLE = make_creature(
    name="Pothole Mole",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Mole"},
    text="When this creature enters, mill three cards, then you may return a land card from your graveyard to your hand. (To mill three cards, put the top three cards of your library into your graveyard.)",
    rarity="common",
)

REGAL_IMPERIOSAUR = make_creature(
    name="Regal Imperiosaur",
    power=5, toughness=4,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Other Dinosaurs you control get +1/+1.",
    rarity="rare",
)

RISE_FROM_THE_WRECK = make_sorcery(
    name="Rise from the Wreck",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Return up to one target creature card, up to one target Mount card, up to one target Vehicle card, and up to one target creature card with no abilities from your graveyard to your hand.",
    rarity="uncommon",
)

RUN_OVER = make_instant(
    name="Run Over",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="This spell costs {1} less to cast if it targets a Mount or Vehicle you control.\nTarget creature you control deals damage equal to its power to target creature an opponent controls.",
    rarity="common",
    resolve=run_over_resolve,
)

SILKEN_STRENGTH = make_enchantment(
    name="Silken Strength",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Flash\nEnchant creature or Vehicle\nWhen this Aura enters, untap enchanted permanent.\nEnchanted permanent gets +1/+2 and has reach.",
    rarity="common",
    subtypes={"Aura"},
)

STAMPEDING_SCURRYFOOT = make_creature(
    name="Stampeding Scurryfoot",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Mouse"},
    text="Exhaust — {3}{G}: Put a +1/+1 counter on this creature. Create a 3/3 green Elephant creature token. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=stampeding_scurryfoot_setup,
)

TERRIAN_WORLD_TYRANT = make_creature(
    name="Terrian, World Tyrant",
    power=9, toughness=7,
    mana_cost="{2}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur", "Ooze"},
    supertypes={"Legendary"},
    text="",
    rarity="uncommon",
)

THUNDEROUS_VELOCIPEDE = make_artifact(
    name="Thunderous Velocipede",
    mana_cost="{1}{G}{G}",
    text="Trample\nEach other Vehicle and creature you control enters with an additional +1/+1 counter on it if its mana value is 4 or less. Otherwise, it enters with three additional +1/+1 counters on it.\nCrew 3",
    rarity="mythic",
    subtypes={"Vehicle"},
)

VELOHEART_BIKE = make_artifact(
    name="Veloheart Bike",
    mana_cost="{2}{G}",
    text="When this Vehicle enters, you gain 2 life.\n{T}: Add one mana of any color.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="common",
    subtypes={"Vehicle"},
)

VENOMSAC_LAGAC = make_creature(
    name="Venomsac Lagac",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard", "Mount"},
    text="Deathtouch\nWhenever this creature attacks while saddled, it gets +0/+3 until end of turn.\nSaddle 2 (Tap any number of other creatures you control with total power 2 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="common",
)

WEBSTRIKE_ELITE = make_creature(
    name="Webstrike Elite",
    power=3, toughness=3,
    mana_cost="{G}{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Insect"},
    text="Reach\nCycling {X}{G}{G} ({X}{G}{G}, Discard this card: Draw a card.)\nWhen you cycle this card, destroy up to one target artifact or enchantment with mana value X.",
    rarity="rare",
)
# Engine gap: "When you cycle this card" rider trigger (destroy artifact/enchantment with MV X) not yet supported.
WEBSTRIKE_ELITE.setup_in_hand = make_cycling_setup("{X}{G}{G}")

AATCHIK_EMERALD_RADIAN = make_creature(
    name="Aatchik, Emerald Radian",
    power=3, toughness=3,
    mana_cost="{3}{B}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Druid", "Insect"},
    supertypes={"Legendary"},
    text="When Aatchik enters, create a 1/1 green Insect creature token for each artifact and/or creature card in your graveyard.\nWhenever another Insect you control dies, put a +1/+1 counter on Aatchik. Each opponent loses 1 life.",
    rarity="rare",
)

APOCALYPSE_RUNNER = make_artifact(
    name="Apocalypse Runner",
    mana_cost="{2}{B}{R}",
    text="{T}: Target creature you control with power 2 or less gains lifelink until end of turn and can't be blocked this turn.\nCrew 3 (Tap any number of creatures you control with total power 3 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

BOOM_SCHOLAR = make_creature(
    name="Boom Scholar",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Advisor", "Goblin"},
    text="Exhaust abilities of other permanents you control cost {2} less to activate.\nExhaust — {4}{R}{G}: Creatures and Vehicles you control gain trample until end of turn. Put two +1/+1 counters on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
    setup_interceptors=boom_scholar_setup,
)

BOOSTED_SLOOP = make_artifact(
    name="Boosted Sloop",
    mana_cost="{1}{U}{R}",
    text="Menace\nWhenever you attack, draw a card, then discard a card.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

BRIGHTGLASS_GEARHULK = make_artifact_creature(
    name="Brightglass Gearhulk",
    power=4, toughness=4,
    mana_cost="{G}{G}{W}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Construct"},
    text="First strike, trample\nWhen this creature enters, you may search your library for up to two artifact, creature, and/or enchantment cards with mana value 1 or less, reveal them, put them into your hand, then shuffle.",
    rarity="mythic",
)

BROADSIDE_BARRAGE = make_instant(
    name="Broadside Barrage",
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Broadside Barrage deals 5 damage to target creature or planeswalker. Draw a card, then discard a card.",
    rarity="uncommon",
    resolve=broadside_barrage_resolve,
    target_requirements=[TargetRequirement(
        filter=TargetFilter(
            types={CardType.CREATURE, CardType.PLANESWALKER},
            zones=[ZoneType.BATTLEFIELD],
        ),
        count=1,
        label="target creature or planeswalker",
    )],
)

BROODHEART_ENGINE = make_artifact(
    name="Broodheart Engine",
    mana_cost="{B}{G}",
    text="At the beginning of your upkeep, surveil 1.\n{2}{B}{G}, {T}, Sacrifice this artifact: Return target creature or Vehicle card from your graveyard to the battlefield. Activate only as a sorcery.",
    rarity="uncommon",
)

CAPTAIN_HOWLER_SEA_SCOURGE = make_creature(
    name="Captain Howler, Sea Scourge",
    power=5, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Pirate", "Shark"},
    supertypes={"Legendary"},
    text="Ward—{2}, Pay 2 life.\nWhenever you discard one or more cards, target creature gets +2/+0 until end of turn for each card discarded this way. Whenever that creature deals combat damage to a player this turn, you draw a card.",
    rarity="rare",
)

CARADORA_HEART_OF_ALACRIA = make_creature(
    name="Caradora, Heart of Alacria",
    power=4, toughness=2,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="When Caradora enters, you may search your library for a Mount or Vehicle card, reveal it, put it into your hand, then shuffle.\nIf one or more +1/+1 counters would be put on a creature or Vehicle you control, that many plus one +1/+1 counters are put on it instead.",
    rarity="rare",
)

CLOUDSPIRE_COORDINATOR = make_creature(
    name="Cloudspire Coordinator",
    power=3, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="When this creature enters, scry 2.\n{T}: Create X 1/1 colorless Pilot creature tokens, where X is the number of Mounts and/or Vehicles that entered the battlefield under your control this turn. The tokens have \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\"",
    rarity="uncommon",
)

CLOUDSPIRE_SKYCYCLE = make_artifact(
    name="Cloudspire Skycycle",
    mana_cost="{2}{R}{W}",
    text="Flying\nWhen this Vehicle enters, distribute two +1/+1 counters among one or two other target Vehicles and/or creatures you control.\nCrew 1",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

COALSTOKE_GEARHULK = make_artifact_creature(
    name="Coalstoke Gearhulk",
    power=5, toughness=4,
    mana_cost="{1}{B}{B}{R}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Construct"},
    text="Menace, deathtouch\nWhen this creature enters, put target creature card with mana value 4 or less from a graveyard onto the battlefield under your control with a finality counter on it. That creature gains menace, deathtouch, and haste. At the beginning of your next end step, exile that creature.",
    rarity="mythic",
)

DEBRIS_BEETLE = make_artifact(
    name="Debris Beetle",
    mana_cost="{2}{B}{G}",
    text="Trample\nWhen this Vehicle enters, each opponent loses 3 life and you gain 3 life.\nCrew 2",
    rarity="rare",
    subtypes={"Vehicle"},
)

DUNE_DRIFTER = make_artifact(
    name="Dune Drifter",
    mana_cost="{X}{W}{B}",
    text="When this Vehicle enters, return target artifact or creature card with mana value X or less from your graveyard to the battlefield.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

EMBALMED_ASCENDANT = make_creature(
    name="Embalmed Ascendant",
    power=1, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Zombie"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this creature enters, create a 2/2 black Zombie creature token.\nMax speed — Whenever a creature you control dies, each opponent loses 1 life and you gain 1 life.",
    rarity="uncommon",
)

EXPLOSIVE_GETAWAY = make_sorcery(
    name="Explosive Getaway",
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Exile up to one target artifact or creature. Return it to the battlefield under its owner's control at the beginning of the next end step.\nExplosive Getaway deals 4 damage to each creature.",
    rarity="rare",
)

FAR_FORTUNE_END_BOSS = make_creature(
    name="Far Fortune, End Boss",
    power=4, toughness=5,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhenever you attack, Far Fortune deals 1 damage to each opponent.\nMax speed — If a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that much damage plus 1 instead.",
    rarity="rare",
)

FEARLESS_SWASHBUCKLER = make_creature(
    name="Fearless Swashbuckler",
    power=3, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Fish", "Pirate"},
    text="Haste\nVehicles you control have haste.\nWhenever you attack, if a Pirate and a Vehicle attacked this combat, draw three cards, then discard two cards.",
    rarity="rare",
)

GASTAL_THRILLSEEKER = make_creature(
    name="Gastal Thrillseeker",
    power=2, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Berserker", "Lizard"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this creature enters, it deals 1 damage to target opponent and you gain 1 life.\nMax speed — This creature has deathtouch and haste.",
    rarity="uncommon",
)

GUIDELIGHT_PATHMAKER = make_artifact(
    name="Guidelight Pathmaker",
    mana_cost="{4}{W}{U}",
    text="Vigilance\nWhen this Vehicle enters, you may search your library for an artifact card and reveal it. Put it onto the battlefield if its mana value is 2 or less. Otherwise, put it into your hand. If you search your library this way, shuffle.\nCrew 2",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

HAUNT_THE_NETWORK = make_sorcery(
    name="Haunt the Network",
    mana_cost="{3}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    text="Choose target opponent. Create two 1/1 colorless Thopter artifact creature tokens with flying. Then the chosen player loses X life and you gain X life, where X is the number of artifacts you control.",
    rarity="uncommon",
    resolve=haunt_the_network_resolve,
)

HAUNTED_HELLRIDE = make_artifact(
    name="Haunted Hellride",
    mana_cost="{1}{U}{B}",
    text="Whenever you attack, target creature you control gets +1/+0 and gains deathtouch until end of turn. Untap it.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

KETRAMOSE_THE_NEW_DAWN = make_creature(
    name="Ketramose, the New Dawn",
    power=4, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Menace, lifelink, indestructible\nKetramose can't attack or block unless there are seven or more cards in exile.\nWhenever one or more cards are put into exile from graveyards and/or the battlefield during your turn, you draw a card and lose 1 life.",
    rarity="mythic",
)

KOLODIN_TRIUMPH_CASTER = make_creature(
    name="Kolodin, Triumph Caster",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="Mounts and Vehicles you control have haste.\nWhenever a Mount you control enters, it becomes saddled until end of turn.\nWhenever a Vehicle you control enters, it becomes an artifact creature until end of turn.",
    rarity="rare",
)

LAGORIN_SOUL_OF_ALACRIA = make_creature(
    name="Lagorin, Soul of Alacria",
    power=1, toughness=1,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Beast", "Mount"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Lagorin attacks while saddled, put a +1/+1 counter on each of up to two target Mounts and/or Vehicles.\nSaddle 1 (Tap any number of other creatures you control with total power 1 or more: This Mount becomes saddled until end of turn. Saddle only as a sorcery.)",
    rarity="uncommon",
)

LOOT_THE_PATHFINDER = make_creature(
    name="Loot, the Pathfinder",
    power=2, toughness=4,
    mana_cost="{2}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Beast", "Noble"},
    supertypes={"Legendary"},
    text="Double strike, vigilance, haste\nExhaust — {G}, {T}: Add three mana of any one color. (Activate each exhaust ability only once.)\nExhaust — {U}, {T}: Draw three cards.\nExhaust — {R}, {T}: Loot deals 3 damage to any target.",
    rarity="mythic",
    setup_interceptors=loot_pathfinder_setup,
)

MENDICANT_CORE_GUIDELIGHT = make_artifact_creature(
    name="Mendicant Core, Guidelight",
    power=0, toughness=3,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Robot"},
    supertypes={"Legendary"},
    text="Mendicant Core's power is equal to the number of artifacts you control.\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — Whenever you cast an artifact spell, you may pay {1}. If you do, copy it. (The copy becomes a token.)",
    rarity="rare",
)

MIMEOPLASM_REVERED_ONE = make_creature(
    name="Mimeoplasm, Revered One",
    power=0, toughness=0,
    mana_cost="{X}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Ooze"},
    supertypes={"Legendary"},
    text="As Mimeoplasm enters, exile up to X creature cards from your graveyard. It enters with three +1/+1 counters on it for each creature card exiled this way.\n{2}: Mimeoplasm becomes a copy of target creature card exiled with it, except it's 0/0 and has this ability.",
    rarity="mythic",
)

OILDEEP_GEARHULK = make_artifact_creature(
    name="Oildeep Gearhulk",
    power=4, toughness=4,
    mana_cost="{U}{U}{B}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Construct"},
    text="Lifelink, ward {1}\nWhen this creature enters, look at target player's hand. You may choose a card from it. If you do, that player discards that card, then draws a card.",
    rarity="mythic",
)

PYREWOOD_GEARHULK = make_artifact_creature(
    name="Pyrewood Gearhulk",
    power=7, toughness=7,
    mana_cost="{2}{R}{R}{G}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Construct"},
    text="Vigilance, menace\nWhen this creature enters, other creatures you control get +2/+2 and gain vigilance and menace until end of turn. Damage can't be prevented this turn.",
    rarity="mythic",
)

RANGERS_AETHERHIVE = make_artifact(
    name="Rangers' Aetherhive",
    mana_cost="{1}{G}{U}",
    text="Vigilance\nWhenever you activate an exhaust ability, create a 1/1 colorless Thopter artifact creature token with flying.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)

REDSHIFT_ROCKETEER_CHIEF = make_creature(
    name="Redshift, Rocketeer Chief",
    power=2, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Goblin", "Pilot"},
    supertypes={"Legendary"},
    text="Vigilance\n{T}: Add X mana of any one color, where X is Redshift's power. Spend this mana only to activate abilities.\nExhaust — {10}{R}{G}: Put any number of permanent cards from your hand onto the battlefield. (Activate each exhaust ability only once.)",
    rarity="rare",
    setup_interceptors=redshift_setup,
)

RIPTIDE_GEARHULK = make_artifact_creature(
    name="Riptide Gearhulk",
    power=2, toughness=5,
    mana_cost="{1}{W}{W}{U}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Construct"},
    text="Double strike\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, for each opponent, put up to one target nonland permanent that player controls into its owner's library third from the top.",
    rarity="mythic",
)

ROCKETEER_BOOSTBUGGY = make_artifact(
    name="Rocketeer Boostbuggy",
    mana_cost="{R}{G}",
    text="Whenever this Vehicle attacks, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nExhaust — {3}: This Vehicle becomes an artifact creature. Put a +1/+1 counter on it. (Activate each exhaust ability only once.)\nCrew 1",
    rarity="uncommon",
    subtypes={"Vehicle"},
    setup_interceptors=rocketeer_boostbuggy_setup,
)

SABSUNEN_LUXA_EMBODIED = make_creature(
    name="Sab-Sunen, Luxa Embodied",
    power=6, toughness=6,
    mana_cost="{3}{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Reach, trample, indestructible\nSab-Sunen can't attack or block unless it has an even number of counters on it. (Zero is even.)\nAt the beginning of your first main phase, put a +1/+1 counter on Sab-Sunen. Then if it has an odd number of counters on it, draw two cards.",
    rarity="mythic",
)

SAMUT_THE_DRIVING_FORCE = make_creature(
    name="Samut, the Driving Force",
    power=4, toughness=5,
    mana_cost="{3}{R}{G}{W}",
    colors={Color.GREEN, Color.RED, Color.WHITE},
    subtypes={"Cleric", "Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, vigilance, haste\nStart your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nOther creatures you control get +X/+0, where X is your speed.\nNoncreature spells you cast cost {X} less to cast, where X is your speed.",
    rarity="rare",
)

SITA_VARMA_MASKED_RACER = make_creature(
    name="Sita Varma, Masked Racer",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Exhaust — {X}{G}{G}{U}: Put X +1/+1 counters on Sita Varma. Then you may have the base power and toughness of each other creature you control become equal to Sita Varma's power until end of turn. (Activate each exhaust ability only once.)",
    rarity="rare",
    setup_interceptors=sita_varma_setup,
)

SKYSERPENT_SEEKER = make_creature(
    name="Skyserpent Seeker",
    power=1, toughness=1,
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Snake"},
    text="Flying, deathtouch\nExhaust — {4}: Reveal cards from the top of your library until you reveal two land cards. Put those land cards onto the battlefield tapped and the rest on the bottom of your library in a random order. Put a +1/+1 counter on this creature. (Activate each exhaust ability only once.)",
    rarity="uncommon",
    setup_interceptors=skyserpent_seeker_setup,
)

THUNDERING_BROODWAGON = make_artifact(
    name="Thundering Broodwagon",
    mana_cost="{2}{B}{B}{G}{G}",
    text="Menace, reach\nWhen this Vehicle enters, destroy target nonland permanent an opponent controls with mana value 4 or less.\nCrew 3\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="uncommon",
    subtypes={"Vehicle"},
)
THUNDERING_BROODWAGON.setup_in_hand = make_cycling_setup("{2}")

VETERAN_BEASTRIDER = make_creature(
    name="Veteran Beastrider",
    power=3, toughness=4,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Knight"},
    text="At the beginning of your end step, untap each creature you control.\n{2}{G}{W}: Creatures you control get +1/+1 until end of turn.",
    rarity="uncommon",
)

VOYAGE_HOME = make_sorcery(
    name="Voyage Home",
    mana_cost="{5}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nYou draw three cards and gain 3 life.",
    rarity="uncommon",
)

WINTER_CURSED_RIDER = make_creature(
    name="Winter, Cursed Rider",
    power=3, toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward—Pay 2 life.\nArtifacts you control have \"Ward—Pay 2 life.\"\nExhaust — {2}{U}{B}, {T}, Exile X artifact cards from your graveyard: Each other nonartifact creature gets -X/-X until end of turn. (Activate each exhaust ability only once.)",
    rarity="rare",
    setup_interceptors=winter_cursed_rider_setup,
)

ZAHUR_GLORYS_PAST = make_creature(
    name="Zahur, Glory's Past",
    power=3, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Cat", "Warrior", "Zombie"},
    supertypes={"Legendary"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nSacrifice another creature: Surveil 1. Activate only once each turn.\nMax speed — Whenever a nontoken creature you control dies, create a tapped 2/2 black Zombie creature token.",
    rarity="rare",
)

AETHERJACKET = make_artifact_creature(
    name="Aetherjacket",
    power=2, toughness=1,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Thopter"},
    text="Flying, vigilance\n{2}, {T}, Sacrifice this creature: Destroy another target artifact. Activate only as a sorcery.",
    rarity="common",
)

THE_AETHERSPARK = make_planeswalker(
    name="The Aetherspark",
    mana_cost="{4}",
    colors=set(),
    loyalty=4,
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="As long as The Aetherspark is attached to a creature, The Aetherspark can't be attacked and has \"Whenever equipped creature deals combat damage during your turn, put that many loyalty counters on The Aetherspark.\"\n+1: Attach The Aetherspark to up to one target creature you control. Put a +1/+1 counter on that creature.\n−5: Draw two cards.\n−10: Add ten mana of any one color.",
    rarity="mythic",
)

CAMERA_LAUNCHER = make_artifact_creature(
    name="Camera Launcher",
    power=2, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct"},
    text="Exhaust — {3}: Put a +1/+1 counter on this creature. Create a 1/1 colorless Thopter artifact creature token with flying. (Activate each exhaust ability only once.)",
    rarity="common",
    setup_interceptors=camera_launcher_setup,
)

GUIDELIGHT_MATRIX = make_artifact(
    name="Guidelight Matrix",
    mana_cost="{2}",
    text="When this artifact enters, draw a card.\n{2}, {T}: Target Mount you control becomes saddled until end of turn. Activate only as a sorcery.\n{2}, {T}: Target Vehicle you control becomes an artifact creature until end of turn.",
    rarity="common",
)

LIFECRAFT_ENGINE = make_artifact(
    name="Lifecraft Engine",
    mana_cost="{3}",
    text="As this Vehicle enters, choose a creature type.\nVehicle creatures you control are the chosen creature type in addition to their other types.\nEach creature you control of the chosen type other than this Vehicle gets +1/+1.\nCrew 3",
    rarity="rare",
    subtypes={"Vehicle"},
)

MARKETBACK_WALKER = make_artifact_creature(
    name="Marketback Walker",
    power=0, toughness=0,
    mana_cost="{X}{X}",
    colors=set(),
    subtypes={"Construct"},
    text="This creature enters with X +1/+1 counters on it.\n{4}: Put a +1/+1 counter on this creature.\nWhen this creature dies, draw a card for each +1/+1 counter on it.",
    rarity="rare",
)

MARSHALS_PATHCRUISER = make_artifact(
    name="Marshals' Pathcruiser",
    mana_cost="{3}",
    text="When this Vehicle enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle.\nExhaust — {W}{U}{B}{R}{G}: This Vehicle becomes an artifact creature. Put two +1/+1 counters on it. (Activate each exhaust ability only once.)\nCrew 5",
    rarity="uncommon",
    subtypes={"Vehicle"},
    setup_interceptors=marshals_pathcruiser_setup,
)

MONUMENT_TO_ENDURANCE = make_artifact(
    name="Monument to Endurance",
    mana_cost="{3}",
    text="Whenever you discard a card, choose one that hasn't been chosen this turn —\n• Draw a card.\n• Create a Treasure token.\n• Each opponent loses 3 life.",
    rarity="rare",
)

PIT_AUTOMATON = make_artifact_creature(
    name="Pit Automaton",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="Defender\n{T}: Add {C}{C}. Spend this mana only to activate abilities.\n{2}, {T}: When you next activate an exhaust ability that isn't a mana ability this turn, copy it. You may choose new targets for the copy.",
    rarity="uncommon",
)

RACERS_SCOREBOARD = make_artifact(
    name="Racers' Scoreboard",
    mana_cost="{4}",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nWhen this artifact enters, draw two cards, then discard a card.\nMax speed — Spells you cast cost {1} less to cast.",
    rarity="uncommon",
)

RADIANT_LOTUS = make_artifact(
    name="Radiant Lotus",
    mana_cost="{6}",
    text="{T}, Sacrifice one or more artifacts: Choose a color. Target player adds three mana of the chosen color for each artifact sacrificed this way.",
    rarity="mythic",
)

ROVER_BLADES = make_artifact(
    name="Rover Blades",
    mana_cost="{3}",
    text="Double strike\nEquipped creature has double strike.\nEquip {4}\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn. Creatures can't be attached to other permanents.)",
    rarity="uncommon",
    subtypes={"Equipment", "Vehicle"},
)

SCRAP_COMPACTOR = make_artifact(
    name="Scrap Compactor",
    mana_cost="{1}",
    text="{3}, {T}, Sacrifice this artifact: It deals 3 damage to target creature.\n{6}, {T}, Sacrifice this artifact: Destroy target creature or Vehicle.",
    rarity="common",
)

SKYBOX_FERRY = make_artifact(
    name="Skybox Ferry",
    mana_cost="{5}",
    text="Flying\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
    subtypes={"Vehicle"},
)
SKYBOX_FERRY.setup_in_hand = make_cycling_setup("{2}")

STARTING_COLUMN = make_artifact(
    name="Starting Column",
    mana_cost="{3}",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{T}: Add one mana of any color.\nMax speed — {T}, Sacrifice this artifact: Draw two cards, then discard a card.",
    rarity="common",
)

TICKET_TORTOISE = make_artifact_creature(
    name="Ticket Tortoise",
    power=3, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Turtle"},
    text="Defender\nWhen this creature enters, if an opponent controls more lands than you, you create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    rarity="common",
)

WALKING_SARCOPHAGUS = make_artifact_creature(
    name="Walking Sarcophagus",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Cat", "Zombie"},
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\nMax speed — This creature gets +1/+2.",
    rarity="common",
)

WRECK_REMOVER = make_artifact_creature(
    name="Wreck Remover",
    power=3, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Construct"},
    text="Whenever this creature enters or attacks, exile up to one target card from a graveyard. You gain 1 life.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    rarity="common",
)
WRECK_REMOVER.setup_in_hand = make_cycling_setup("{2}")

AMONKHET_RACEWAY = make_land(
    name="Amonkhet Raceway",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{T}: Add {C}.\nMax speed — {T}: Target creature gains haste until end of turn.",
    rarity="uncommon",
)

AVISHKAR_RACEWAY = make_land(
    name="Avishkar Raceway",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{T}: Add {C}.\nMax speed — {3}, {T}, Discard a card: Draw a card.",
    rarity="common",
)

BLEACHBONE_VERGE = make_land(
    name="Bleachbone Verge",
    text="{T}: Add {B}.\n{T}: Add {W}. Activate only if you control a Plains or a Swamp.",
    rarity="rare",
)

BLOODFELL_CAVES = make_land(
    name="Bloodfell Caves",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {R}.",
    rarity="common",
)

BLOSSOMING_SANDS = make_land(
    name="Blossoming Sands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {W}.",
    rarity="common",
)

COUNTRY_ROADS = make_land(
    name="Country Roads",
    text="This land enters tapped unless you control a Mount or Vehicle.\n{T}: Add {W}.\n{1}{W}, {T}, Sacrifice this land: Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\" Activate only as a sorcery.",
    rarity="uncommon",
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {B}.",
    rarity="common",
)

FOUL_ROADS = make_land(
    name="Foul Roads",
    text="This land enters tapped unless you control a Mount or Vehicle.\n{T}: Add {B}.\n{1}{B}, {T}, Sacrifice this land: Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\" Activate only as a sorcery.",
    rarity="uncommon",
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {G}.",
    rarity="common",
)

MURAGANDA_RACEWAY = make_land(
    name="Muraganda Raceway",
    text="Start your engines! (If you have no speed, it starts at 1. It increases once on each of your turns when an opponent loses life. Max speed is 4.)\n{T}: Add {C}.\nMax speed — {T}: Add {C}{C}.",
    rarity="rare",
)

NIGHT_MARKET = make_land(
    name="Night Market",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.\nCycling {3} ({3}, Discard this card: Draw a card.)",
    rarity="common",
)
NIGHT_MARKET.setup_in_hand = make_cycling_setup("{3}")

REEF_ROADS = make_land(
    name="Reef Roads",
    text="This land enters tapped unless you control a Mount or Vehicle.\n{T}: Add {U}.\n{1}{U}, {T}, Sacrifice this land: Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\" Activate only as a sorcery.",
    rarity="uncommon",
)

RIVERPYRE_VERGE = make_land(
    name="Riverpyre Verge",
    text="{T}: Add {R}.\n{T}: Add {U}. Activate only if you control an Island or a Mountain.",
    rarity="rare",
)

ROCKY_ROADS = make_land(
    name="Rocky Roads",
    text="This land enters tapped unless you control a Mount or Vehicle.\n{T}: Add {R}.\n{1}{R}, {T}, Sacrifice this land: Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\" Activate only as a sorcery.",
    rarity="uncommon",
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {G}.",
    rarity="common",
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {B}.",
    rarity="common",
)

SUNBILLOW_VERGE = make_land(
    name="Sunbillow Verge",
    text="{T}: Add {W}.\n{T}: Add {R}. Activate only if you control a Mountain or a Plains.",
    rarity="rare",
)

SWIFTWATER_CLIFFS = make_land(
    name="Swiftwater Cliffs",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {R}.",
    rarity="common",
)

THORNWOOD_FALLS = make_land(
    name="Thornwood Falls",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {G} or {U}.",
    rarity="common",
)

TRANQUIL_COVE = make_land(
    name="Tranquil Cove",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {U}.",
    rarity="common",
)

WASTEWOOD_VERGE = make_land(
    name="Wastewood Verge",
    text="{T}: Add {G}.\n{T}: Add {B}. Activate only if you control a Swamp or a Forest.",
    rarity="rare",
)

WILD_ROADS = make_land(
    name="Wild Roads",
    text="This land enters tapped unless you control a Mount or Vehicle.\n{T}: Add {G}.\n{1}{G}, {T}, Sacrifice this land: Create a 1/1 colorless Pilot creature token with \"This token saddles Mounts and crews Vehicles as though its power were 2 greater.\" Activate only as a sorcery.",
    rarity="uncommon",
)

WILLOWRUSH_VERGE = make_land(
    name="Willowrush Verge",
    text="{T}: Add {U}.\n{T}: Add {G}. Activate only if you control a Forest or an Island.",
    rarity="rare",
)

WINDSCARRED_CRAG = make_land(
    name="Wind-Scarred Crag",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {W}.",
    rarity="common",
)

PLAINS = make_land(
    name="Plains",
    text="({T}: Add {W}.)",
    rarity="common",
    subtypes={"Plains"},
    supertypes={"Basic"},
)

ISLAND = make_land(
    name="Island",
    text="({T}: Add {U}.)",
    rarity="common",
    subtypes={"Island"},
    supertypes={"Basic"},
)

SWAMP = make_land(
    name="Swamp",
    text="({T}: Add {B}.)",
    rarity="common",
    subtypes={"Swamp"},
    supertypes={"Basic"},
)

MOUNTAIN = make_land(
    name="Mountain",
    text="({T}: Add {R}.)",
    rarity="common",
    subtypes={"Mountain"},
    supertypes={"Basic"},
)

FOREST = make_land(
    name="Forest",
    text="({T}: Add {G}.)",
    rarity="common",
    subtypes={"Forest"},
    supertypes={"Basic"},
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

AETHERDRIFT_CARDS = {
    "Air Response Unit": AIR_RESPONSE_UNIT,
    "Alacrian Armory": ALACRIAN_ARMORY,
    "Basri, Tomorrow's Champion": BASRI_TOMORROWS_CHAMPION,
    "Brightfield Glider": BRIGHTFIELD_GLIDER,
    "Brightfield Mustang": BRIGHTFIELD_MUSTANG,
    "Broadcast Rambler": BROADCAST_RAMBLER,
    "Bulwark Ox": BULWARK_OX,
    "Canyon Vaulter": CANYON_VAULTER,
    "Cloudspire Captain": CLOUDSPIRE_CAPTAIN,
    "Collision Course": COLLISION_COURSE,
    "Daring Mechanic": DARING_MECHANIC,
    "Detention Chariot": DETENTION_CHARIOT,
    "Gallant Strike": GALLANT_STRIKE,
    "Gloryheath Lynx": GLORYHEATH_LYNX,
    "Guardian Sunmare": GUARDIAN_SUNMARE,
    "Guidelight Synergist": GUIDELIGHT_SYNERGIST,
    "Interface Ace": INTERFACE_ACE,
    "Leonin Surveyor": LEONIN_SURVEYOR,
    "Lightshield Parry": LIGHTSHIELD_PARRY,
    "Lightwheel Enhancements": LIGHTWHEEL_ENHANCEMENTS,
    "Lotusguard Disciple": LOTUSGUARD_DISCIPLE,
    "Nesting Bot": NESTING_BOT,
    "Perilous Snare": PERILOUS_SNARE,
    "Pride of the Road": PRIDE_OF_THE_ROAD,
    "Ride's End": RIDES_END,
    "Roadside Assistance": ROADSIDE_ASSISTANCE,
    "Salvation Engine": SALVATION_ENGINE,
    "Skyseer's Chariot": SKYSEERS_CHARIOT,
    "Spectacular Pileup": SPECTACULAR_PILEUP,
    "Spotcycle Scouter": SPOTCYCLE_SCOUTER,
    "Sundial, Dawn Tyrant": SUNDIAL_DAWN_TYRANT,
    "Swiftwing Assailant": SWIFTWING_ASSAILANT,
    "Tune Up": TUNE_UP,
    "Unswerving Sloth": UNSWERVING_SLOTH,
    "Valor's Flagship": VALORS_FLAGSHIP,
    "Voyager Glidecar": VOYAGER_GLIDECAR,
    "Voyager Quickwelder": VOYAGER_QUICKWELDER,
    "Aether Syphon": AETHER_SYPHON,
    "Bounce Off": BOUNCE_OFF,
    "Caelorna, Coral Tyrant": CAELORNA_CORAL_TYRANT,
    "Diversion Unit": DIVERSION_UNIT,
    "Flood the Engine": FLOOD_THE_ENGINE,
    "Gearseeker Serpent": GEARSEEKER_SERPENT,
    "Glitch Ghost Surveyor": GLITCH_GHOST_SURVEYOR,
    "Guidelight Optimizer": GUIDELIGHT_OPTIMIZER,
    "Howler's Heavy": HOWLERS_HEAVY,
    "Hulldrifter": HULLDRIFTER,
    "Keen Buccaneer": KEEN_BUCCANEER,
    "Memory Guardian": MEMORY_GUARDIAN,
    "Midnight Mangler": MIDNIGHT_MANGLER,
    "Mindspring Merfolk": MINDSPRING_MERFOLK,
    "Mu Yanling, Wind Rider": MU_YANLING_WIND_RIDER,
    "Nimble Thopterist": NIMBLE_THOPTERIST,
    "Possession Engine": POSSESSION_ENGINE,
    "Rangers' Refueler": RANGERS_REFUELER,
    "Repurposing Bay": REPURPOSING_BAY,
    "Riverchurn Monument": RIVERCHURN_MONUMENT,
    "Roadside Blowout": ROADSIDE_BLOWOUT,
    "Sabotage Strategist": SABOTAGE_STRATEGIST,
    "Scrounging Skyray": SCROUNGING_SKYRAY,
    "Skystreak Engineer": SKYSTREAK_ENGINEER,
    "Slick Imitator": SLICK_IMITATOR,
    "Spectral Interference": SPECTRAL_INTERFERENCE,
    "Spell Pierce": SPELL_PIERCE,
    "Spikeshell Harrier": SPIKESHELL_HARRIER,
    "Stall Out": STALL_OUT,
    "Stock Up": STOCK_UP,
    "Thopter Fabricator": THOPTER_FABRICATOR,
    "Trade the Helm": TRADE_THE_HELM,
    "Transit Mage": TRANSIT_MAGE,
    "Trip Up": TRIP_UP,
    "Unstoppable Plan": UNSTOPPABLE_PLAN,
    "Vnwxt, Verbose Host": VNWXT_VERBOSE_HOST,
    "Waxen Shapethief": WAXEN_SHAPETHIEF,
    "Ancient Vendetta": ANCIENT_VENDETTA,
    "Back on Track": BACK_ON_TRACK,
    "Bloodghast": BLOODGHAST,
    "Carrion Cruiser": CARRION_CRUISER,
    "Chitin Gravestalker": CHITIN_GRAVESTALKER,
    "Cryptcaller Chariot": CRYPTCALLER_CHARIOT,
    "Cursecloth Wrappings": CURSECLOTH_WRAPPINGS,
    "Deathless Pilot": DEATHLESS_PILOT,
    "Demonic Junker": DEMONIC_JUNKER,
    "Engine Rat": ENGINE_RAT,
    "Gas Guzzler": GAS_GUZZLER,
    "Gastal Raider": GASTAL_RAIDER,
    "Gonti, Night Minister": GONTI_NIGHT_MINISTER,
    "Grim Bauble": GRIM_BAUBLE,
    "Grim Javelineer": GRIM_JAVELINEER,
    "Hellish Sideswipe": HELLISH_SIDESWIPE,
    "Hour of Victory": HOUR_OF_VICTORY,
    "Intimidation Tactics": INTIMIDATION_TACTICS,
    "Kalakscion, Hunger Tyrant": KALAKSCION_HUNGER_TYRANT,
    "The Last Ride": THE_LAST_RIDE,
    "Locust Spray": LOCUST_SPRAY,
    "Maximum Overdrive": MAXIMUM_OVERDRIVE,
    "Momentum Breaker": MOMENTUM_BREAKER,
    "Mutant Surveyor": MUTANT_SURVEYOR,
    "Pactdoll Terror": PACTDOLL_TERROR,
    "Quag Feast": QUAG_FEAST,
    "Ripclaw Wrangler": RIPCLAW_WRANGLER,
    "Risen Necroregent": RISEN_NECROREGENT,
    "Risky Shortcut": RISKY_SHORTCUT,
    "Shefet Archfiend": SHEFET_ARCHFIEND,
    "The Speed Demon": THE_SPEED_DEMON,
    "Spin Out": SPIN_OUT,
    "Streaking Oilgorger": STREAKING_OILGORGER,
    "Syphon Fuel": SYPHON_FUEL,
    "Wickerfolk Indomitable": WICKERFOLK_INDOMITABLE,
    "Wreckage Wickerfolk": WRECKAGE_WICKERFOLK,
    "Wretched Doll": WRETCHED_DOLL,
    "Adrenaline Jockey": ADRENALINE_JOCKEY,
    "Boommobile": BOOMMOBILE,
    "Burner Rocket": BURNER_ROCKET,
    "Burnout Bashtronaut": BURNOUT_BASHTRONAUT,
    "Chandra, Spark Hunter": CHANDRA_SPARK_HUNTER,
    "Clamorous Ironclad": CLAMOROUS_IRONCLAD,
    "Count on Luck": COUNT_ON_LUCK,
    "Crash and Burn": CRASH_AND_BURN,
    "Daretti, Rocketeer Engineer": DARETTI_ROCKETEER_ENGINEER,
    "Draconautics Engineer": DRACONAUTICS_ENGINEER,
    "Dracosaur Auxiliary": DRACOSAUR_AUXILIARY,
    "Dynamite Diver": DYNAMITE_DIVER,
    "Endrider Catalyzer": ENDRIDER_CATALYZER,
    "Endrider Spikespitter": ENDRIDER_SPIKESPITTER,
    "Fuel the Flames": FUEL_THE_FLAMES,
    "Full Throttle": FULL_THROTTLE,
    "Gastal Blockbuster": GASTAL_BLOCKBUSTER,
    "Gastal Thrillroller": GASTAL_THRILLROLLER,
    "Gilded Ghoda": GILDED_GHODA,
    "Goblin Surveyor": GOBLIN_SURVEYOR,
    "Greasewrench Goblin": GREASEWRENCH_GOBLIN,
    "Hazoret, Godseeker": HAZORET_GODSEEKER,
    "Howlsquad Heavy": HOWLSQUAD_HEAVY,
    "Kickoff Celebrations": KICKOFF_CELEBRATIONS,
    "Lightning Strike": LIGHTNING_STRIKE,
    "Magmakin Artillerist": MAGMAKIN_ARTILLERIST,
    "Marauding Mako": MARAUDING_MAKO,
    "Outpace Oblivion": OUTPACE_OBLIVION,
    "Pacesetter Paragon": PACESETTER_PARAGON,
    "Pedal to the Metal": PEDAL_TO_THE_METAL,
    "Prowcatcher Specialist": PROWCATCHER_SPECIALIST,
    "Push the Limit": PUSH_THE_LIMIT,
    "Reckless Velocitaur": RECKLESS_VELOCITAUR,
    "Road Rage": ROAD_RAGE,
    "Skycrash": SKYCRASH,
    "Spire Mechcycle": SPIRE_MECHCYCLE,
    "Thunderhead Gunner": THUNDERHEAD_GUNNER,
    "Tyrox, Saurid Tyrant": TYROX_SAURID_TYRANT,
    "Afterburner Expert": AFTERBURNER_EXPERT,
    "Agonasaur Rex": AGONASAUR_REX,
    "Alacrian Jaguar": ALACRIAN_JAGUAR,
    "Autarch Mammoth": AUTARCH_MAMMOTH,
    "Beastrider Vanguard": BEASTRIDER_VANGUARD,
    "Bestow Greatness": BESTOW_GREATNESS,
    "Broken Wings": BROKEN_WINGS,
    "Defend the Rider": DEFEND_THE_RIDER,
    "District Mascot": DISTRICT_MASCOT,
    "Dredger's Insight": DREDGERS_INSIGHT,
    "Earthrumbler": EARTHRUMBLER,
    "Elvish Refueler": ELVISH_REFUELER,
    "Fang Guardian": FANG_GUARDIAN,
    "Fang-Druid Summoner": FANGDRUID_SUMMONER,
    "Greenbelt Guardian": GREENBELT_GUARDIAN,
    "Hazard of the Dunes": HAZARD_OF_THE_DUNES,
    "Jibbirik Omnivore": JIBBIRIK_OMNIVORE,
    "Loxodon Surveyor": LOXODON_SURVEYOR,
    "Lumbering Worldwagon": LUMBERING_WORLDWAGON,
    "March of the World Ooze": MARCH_OF_THE_WORLD_OOZE,
    "Migrating Ketradon": MIGRATING_KETRADON,
    "Molt Tender": MOLT_TENDER,
    "Ooze Patrol": OOZE_PATROL,
    "Oviya, Automech Artisan": OVIYA_AUTOMECH_ARTISAN,
    "Plow Through": PLOW_THROUGH,
    "Point the Way": POINT_THE_WAY,
    "Pothole Mole": POTHOLE_MOLE,
    "Regal Imperiosaur": REGAL_IMPERIOSAUR,
    "Rise from the Wreck": RISE_FROM_THE_WRECK,
    "Run Over": RUN_OVER,
    "Silken Strength": SILKEN_STRENGTH,
    "Stampeding Scurryfoot": STAMPEDING_SCURRYFOOT,
    "Terrian, World Tyrant": TERRIAN_WORLD_TYRANT,
    "Thunderous Velocipede": THUNDEROUS_VELOCIPEDE,
    "Veloheart Bike": VELOHEART_BIKE,
    "Venomsac Lagac": VENOMSAC_LAGAC,
    "Webstrike Elite": WEBSTRIKE_ELITE,
    "Aatchik, Emerald Radian": AATCHIK_EMERALD_RADIAN,
    "Apocalypse Runner": APOCALYPSE_RUNNER,
    "Boom Scholar": BOOM_SCHOLAR,
    "Boosted Sloop": BOOSTED_SLOOP,
    "Brightglass Gearhulk": BRIGHTGLASS_GEARHULK,
    "Broadside Barrage": BROADSIDE_BARRAGE,
    "Broodheart Engine": BROODHEART_ENGINE,
    "Captain Howler, Sea Scourge": CAPTAIN_HOWLER_SEA_SCOURGE,
    "Caradora, Heart of Alacria": CARADORA_HEART_OF_ALACRIA,
    "Cloudspire Coordinator": CLOUDSPIRE_COORDINATOR,
    "Cloudspire Skycycle": CLOUDSPIRE_SKYCYCLE,
    "Coalstoke Gearhulk": COALSTOKE_GEARHULK,
    "Debris Beetle": DEBRIS_BEETLE,
    "Dune Drifter": DUNE_DRIFTER,
    "Embalmed Ascendant": EMBALMED_ASCENDANT,
    "Explosive Getaway": EXPLOSIVE_GETAWAY,
    "Far Fortune, End Boss": FAR_FORTUNE_END_BOSS,
    "Fearless Swashbuckler": FEARLESS_SWASHBUCKLER,
    "Gastal Thrillseeker": GASTAL_THRILLSEEKER,
    "Guidelight Pathmaker": GUIDELIGHT_PATHMAKER,
    "Haunt the Network": HAUNT_THE_NETWORK,
    "Haunted Hellride": HAUNTED_HELLRIDE,
    "Ketramose, the New Dawn": KETRAMOSE_THE_NEW_DAWN,
    "Kolodin, Triumph Caster": KOLODIN_TRIUMPH_CASTER,
    "Lagorin, Soul of Alacria": LAGORIN_SOUL_OF_ALACRIA,
    "Loot, the Pathfinder": LOOT_THE_PATHFINDER,
    "Mendicant Core, Guidelight": MENDICANT_CORE_GUIDELIGHT,
    "Mimeoplasm, Revered One": MIMEOPLASM_REVERED_ONE,
    "Oildeep Gearhulk": OILDEEP_GEARHULK,
    "Pyrewood Gearhulk": PYREWOOD_GEARHULK,
    "Rangers' Aetherhive": RANGERS_AETHERHIVE,
    "Redshift, Rocketeer Chief": REDSHIFT_ROCKETEER_CHIEF,
    "Riptide Gearhulk": RIPTIDE_GEARHULK,
    "Rocketeer Boostbuggy": ROCKETEER_BOOSTBUGGY,
    "Sab-Sunen, Luxa Embodied": SABSUNEN_LUXA_EMBODIED,
    "Samut, the Driving Force": SAMUT_THE_DRIVING_FORCE,
    "Sita Varma, Masked Racer": SITA_VARMA_MASKED_RACER,
    "Skyserpent Seeker": SKYSERPENT_SEEKER,
    "Thundering Broodwagon": THUNDERING_BROODWAGON,
    "Veteran Beastrider": VETERAN_BEASTRIDER,
    "Voyage Home": VOYAGE_HOME,
    "Winter, Cursed Rider": WINTER_CURSED_RIDER,
    "Zahur, Glory's Past": ZAHUR_GLORYS_PAST,
    "Aetherjacket": AETHERJACKET,
    "The Aetherspark": THE_AETHERSPARK,
    "Camera Launcher": CAMERA_LAUNCHER,
    "Guidelight Matrix": GUIDELIGHT_MATRIX,
    "Lifecraft Engine": LIFECRAFT_ENGINE,
    "Marketback Walker": MARKETBACK_WALKER,
    "Marshals' Pathcruiser": MARSHALS_PATHCRUISER,
    "Monument to Endurance": MONUMENT_TO_ENDURANCE,
    "Pit Automaton": PIT_AUTOMATON,
    "Racers' Scoreboard": RACERS_SCOREBOARD,
    "Radiant Lotus": RADIANT_LOTUS,
    "Rover Blades": ROVER_BLADES,
    "Scrap Compactor": SCRAP_COMPACTOR,
    "Skybox Ferry": SKYBOX_FERRY,
    "Starting Column": STARTING_COLUMN,
    "Ticket Tortoise": TICKET_TORTOISE,
    "Walking Sarcophagus": WALKING_SARCOPHAGUS,
    "Wreck Remover": WRECK_REMOVER,
    "Amonkhet Raceway": AMONKHET_RACEWAY,
    "Avishkar Raceway": AVISHKAR_RACEWAY,
    "Bleachbone Verge": BLEACHBONE_VERGE,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Country Roads": COUNTRY_ROADS,
    "Dismal Backwater": DISMAL_BACKWATER,
    "Foul Roads": FOUL_ROADS,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Muraganda Raceway": MURAGANDA_RACEWAY,
    "Night Market": NIGHT_MARKET,
    "Reef Roads": REEF_ROADS,
    "Riverpyre Verge": RIVERPYRE_VERGE,
    "Rocky Roads": ROCKY_ROADS,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Scoured Barrens": SCOURED_BARRENS,
    "Sunbillow Verge": SUNBILLOW_VERGE,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Tranquil Cove": TRANQUIL_COVE,
    "Wastewood Verge": WASTEWOOD_VERGE,
    "Wild Roads": WILD_ROADS,
    "Willowrush Verge": WILLOWRUSH_VERGE,
    "Wind-Scarred Crag": WINDSCARRED_CRAG,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(AETHERDRIFT_CARDS)} Aetherdrift cards")
