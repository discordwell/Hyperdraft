"""
Tarkir: Dragonstorm (TDM) Card Implementations

Real card data fetched from Scryfall API.
277 cards in set.
"""

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
    create_target_choice,
    create_modal_choice,
    make_etb_trigger,
    make_death_trigger,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create instant card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.INSTANT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, resolve=None):
    """Helper to create sorcery card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.SORCERY},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_enchantment_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                              subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create enchantment creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            power=power,
            toughness=toughness,
            mana_cost=mana_cost
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", rarity: str = None, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create land card definitions."""
    return CardDefinition(
        name=name,
        mana_cost="",
        characteristics=Characteristics(
            types={CardType.LAND},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            mana_cost=""
        ),
        text=text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", rarity: str = None, setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    loyalty_text = f"[Loyalty: {loyalty}] " + text if text else f"[Loyalty: {loyalty}]"
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.PLANESWALKER},
            subtypes=subtypes or set(),
            supertypes=base_supertypes,
            colors=colors,
            mana_cost=mana_cost
        ),
        text=loyalty_text,
        rarity=rarity,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# RESOLVE FUNCTIONS FOR TARGETED SPELLS
# =============================================================================

def _find_spell_on_stack(state: GameState, spell_name: str) -> tuple[str, str]:
    """Helper to find a spell on the stack and return (caster_id, spell_id)."""
    stack_zone = state.zones.get('stack')
    caster_id = None
    spell_id = None
    if stack_zone:
        for obj_id in stack_zone.objects:
            obj = state.objects.get(obj_id)
            if obj and obj.name == spell_name:
                caster_id = obj.controller
                spell_id = obj.id
                break
    if caster_id is None:
        caster_id = state.active_player
    if spell_id is None:
        spell_id = f"{spell_name.lower().replace(' ', '_')}_spell"
    return caster_id, spell_id


def _get_creatures_on_battlefield(state: GameState, filter_fn=None) -> list[str]:
    """Get all creatures on battlefield, optionally filtered."""
    creatures = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            if filter_fn is None or filter_fn(obj, state):
                creatures.append(obj.id)
    return creatures


def _get_permanents_on_battlefield(state: GameState, types=None, controller=None, opponent_of=None) -> list[str]:
    """Get permanents on battlefield, optionally filtered by type and controller."""
    permanents = []
    for obj in state.objects.values():
        if obj.zone != ZoneType.BATTLEFIELD:
            continue
        if types is not None:
            if not any(t in obj.characteristics.types for t in types):
                continue
        if controller is not None and obj.controller != controller:
            continue
        if opponent_of is not None and obj.controller == opponent_of:
            continue
        permanents.append(obj.id)
    return permanents


# -----------------------------------------------------------------------------
# DRAGON'S PREY - Destroy target creature. (Costs {2} more if target is Dragon)
# -----------------------------------------------------------------------------
def _dragons_prey_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Dragon's Prey after target selection - destroy target creature."""
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


def dragons_prey_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Dragon's Prey: Destroy target creature."""
    caster_id, spell_id = _find_spell_on_stack(state, "Dragon's Prey")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _dragons_prey_execute
    return []


# -----------------------------------------------------------------------------
# CAUSTIC EXHALE - Target creature gets -3/-3 until end of turn
# -----------------------------------------------------------------------------
def _caustic_exhale_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Caustic Exhale - give target creature -3/-3."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.PT_CHANGE,
        payload={'object_id': target_id, 'power': -3, 'toughness': -3, 'duration': 'until_end_of_turn'},
        source=choice.source_id
    )]


def caustic_exhale_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Caustic Exhale: Target creature gets -3/-3 until end of turn."""
    caster_id, spell_id = _find_spell_on_stack(state, "Caustic Exhale")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to give -3/-3",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _caustic_exhale_execute
    return []


# -----------------------------------------------------------------------------
# SALT ROAD SKIRMISH - Destroy target creature. Create two 1/1 Warriors.
# -----------------------------------------------------------------------------
def _salt_road_skirmish_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Salt Road Skirmish - destroy creature and create tokens."""
    target_id = selected[0] if selected else None
    events = []
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': target_id},
                source=choice.source_id
            ))
    # Create two Warrior tokens regardless
    caster_id = choice.player
    for _ in range(2):
        events.append(Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'name': 'Warrior Token',
                'controller': caster_id,
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Warrior'],
                'colors': [Color.RED],
                'token': True,
                'haste': True,  # Gain haste until end of turn
                'sacrifice_at_end_step': True
            },
            source=choice.source_id
        ))
    return events


def salt_road_skirmish_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Salt Road Skirmish: Destroy target creature, create two 1/1 Warriors."""
    caster_id, spell_id = _find_spell_on_stack(state, "Salt Road Skirmish")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to destroy",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _salt_road_skirmish_execute
    return []


# -----------------------------------------------------------------------------
# WORTHY COST - Exile target creature or planeswalker (additional cost: sacrifice)
# -----------------------------------------------------------------------------
def _worthy_cost_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Worthy Cost - exile target creature or planeswalker."""
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


def worthy_cost_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Worthy Cost: Exile target creature or planeswalker."""
    caster_id, spell_id = _find_spell_on_stack(state, "Worthy Cost")
    valid_targets = _get_permanents_on_battlefield(
        state,
        types={CardType.CREATURE, CardType.PLANESWALKER}
    )
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker to exile",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _worthy_cost_execute
    return []


# -----------------------------------------------------------------------------
# CHANNELED DRAGONFIRE - Deal 2 damage to any target
# -----------------------------------------------------------------------------
def _channeled_dragonfire_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Channeled Dragonfire - deal 2 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    if target_id in state.players:
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]
    else:
        target = state.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
            source=choice.source_id
        )]


def channeled_dragonfire_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Channeled Dragonfire: Deal 2 damage to any target."""
    caster_id, spell_id = _find_spell_on_stack(state, "Channeled Dragonfire")
    valid_targets = []
    # Add creatures and planeswalkers
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types:
                valid_targets.append(obj.id)
    # Add players
    for player_id in state.players:
        valid_targets.append(player_id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a target for Channeled Dragonfire (2 damage)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _channeled_dragonfire_execute
    return []


# -----------------------------------------------------------------------------
# MOLTEN EXHALE - Deal 4 damage to target creature or planeswalker
# -----------------------------------------------------------------------------
def _molten_exhale_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Molten Exhale - deal 4 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def molten_exhale_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Molten Exhale: Deal 4 damage to target creature or planeswalker."""
    caster_id, spell_id = _find_spell_on_stack(state, "Molten Exhale")
    valid_targets = _get_permanents_on_battlefield(
        state,
        types={CardType.CREATURE, CardType.PLANESWALKER}
    )
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker for Molten Exhale (4 damage)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _molten_exhale_execute
    return []


# -----------------------------------------------------------------------------
# NARSET'S REBUKE - Deal 5 damage to target creature
# -----------------------------------------------------------------------------
def _narsets_rebuke_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Narset's Rebuke - deal 5 damage and add mana."""
    target_id = selected[0] if selected else None
    events = []
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 5, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))
    # Add {U}{R}{W} mana
    events.append(Event(
        type=EventType.ADD_MANA,
        payload={'player': choice.player, 'colors': ['U', 'R', 'W']},
        source=choice.source_id
    ))
    return events


def narsets_rebuke_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Narset's Rebuke: Deal 5 damage to target creature, add {U}{R}{W}."""
    caster_id, spell_id = _find_spell_on_stack(state, "Narset's Rebuke")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature for Narset's Rebuke (5 damage)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _narsets_rebuke_execute
    return []


# -----------------------------------------------------------------------------
# TWIN BOLT - Deal 2 damage divided among one or two targets
# -----------------------------------------------------------------------------
def _twin_bolt_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Twin Bolt - deal 2 damage divided among targets."""
    events = []
    if len(selected) == 1:
        target_id = selected[0]
        if target_id in state.players:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))
        else:
            target = state.objects.get(target_id)
            if target and target.zone == ZoneType.BATTLEFIELD:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target_id, 'amount': 2, 'source': choice.source_id, 'is_combat': False},
                    source=choice.source_id
                ))
    elif len(selected) == 2:
        for target_id in selected:
            if target_id in state.players:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': target_id, 'amount': 1, 'source': choice.source_id, 'is_combat': False},
                    source=choice.source_id
                ))
            else:
                target = state.objects.get(target_id)
                if target and target.zone == ZoneType.BATTLEFIELD:
                    events.append(Event(
                        type=EventType.DAMAGE,
                        payload={'target': target_id, 'amount': 1, 'source': choice.source_id, 'is_combat': False},
                        source=choice.source_id
                    ))
    return events


def twin_bolt_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Twin Bolt: Deal 2 damage divided among one or two targets."""
    caster_id, spell_id = _find_spell_on_stack(state, "Twin Bolt")
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            if CardType.CREATURE in obj.characteristics.types or CardType.PLANESWALKER in obj.characteristics.types:
                valid_targets.append(obj.id)
    for player_id in state.players:
        valid_targets.append(player_id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose one or two targets for Twin Bolt (2 damage divided)",
        min_targets=1,
        max_targets=2
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _twin_bolt_execute
    return []


# -----------------------------------------------------------------------------
# OSSEOUS EXHALE - Deal 5 damage to target attacking or blocking creature
# -----------------------------------------------------------------------------
def _osseous_exhale_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Osseous Exhale - deal 5 damage."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    events = [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 5, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]
    # If Dragon was beheld, gain 2 life
    if choice.callback_data.get('dragon_beheld'):
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': choice.player, 'amount': 2},
            source=choice.source_id
        ))
    return events


def osseous_exhale_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Osseous Exhale: Deal 5 damage to target attacking or blocking creature."""
    caster_id, spell_id = _find_spell_on_stack(state, "Osseous Exhale")
    # Get attacking or blocking creatures
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in obj.characteristics.types:
            if getattr(obj.state, 'attacking', False) or getattr(obj.state, 'blocking', False):
                valid_targets.append(obj.id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose an attacking or blocking creature for Osseous Exhale (5 damage)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _osseous_exhale_execute
    return []


# -----------------------------------------------------------------------------
# LIGHTFOOT TECHNIQUE - Put +1/+1 counter, gain flying and indestructible
# -----------------------------------------------------------------------------
def _lightfoot_technique_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Lightfoot Technique - buff target creature."""
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
            payload={'object_id': target_id, 'abilities': ['flying', 'indestructible'], 'duration': 'until_end_of_turn'},
            source=choice.source_id
        )
    ]


def lightfoot_technique_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Lightfoot Technique: +1/+1 counter, flying and indestructible."""
    caster_id, spell_id = _find_spell_on_stack(state, "Lightfoot Technique")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/+1 counter, flying and indestructible",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _lightfoot_technique_execute
    return []


# -----------------------------------------------------------------------------
# REBELLIOUS STRIKE - Target creature gets +3/+0, draw a card
# -----------------------------------------------------------------------------
def _rebellious_strike_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Rebellious Strike - pump and draw."""
    target_id = selected[0] if selected else None
    events = []
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.PT_CHANGE,
                payload={'object_id': target_id, 'power': 3, 'toughness': 0, 'duration': 'until_end_of_turn'},
                source=choice.source_id
            ))
    # Draw a card regardless
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    ))
    return events


def rebellious_strike_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Rebellious Strike: Target creature gets +3/+0, draw a card."""
    caster_id, spell_id = _find_spell_on_stack(state, "Rebellious Strike")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +3/+0",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _rebellious_strike_execute
    return []


# -----------------------------------------------------------------------------
# ALESHA'S LEGACY - Target creature gains deathtouch and indestructible
# -----------------------------------------------------------------------------
def _aleshas_legacy_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Alesha's Legacy - grant deathtouch and indestructible."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.GRANT_ABILITY,
        payload={'object_id': target_id, 'abilities': ['deathtouch', 'indestructible'], 'duration': 'until_end_of_turn'},
        source=choice.source_id
    )]


def aleshas_legacy_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Alesha's Legacy: Target creature you control gains deathtouch and indestructible."""
    caster_id, spell_id = _find_spell_on_stack(state, "Alesha's Legacy")
    valid_targets = _get_creatures_on_battlefield(
        state,
        filter_fn=lambda obj, s: obj.controller == caster_id
    )
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature you control to gain deathtouch and indestructible",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _aleshas_legacy_execute
    return []


# -----------------------------------------------------------------------------
# DESPERATE MEASURES - Target creature gets +1/-1, draw 2 if it dies
# -----------------------------------------------------------------------------
def _desperate_measures_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Desperate Measures - modify creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.PT_CHANGE,
        payload={'object_id': target_id, 'power': 1, 'toughness': -1, 'duration': 'until_end_of_turn'},
        source=choice.source_id
    )]


def desperate_measures_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Desperate Measures: Target creature gets +1/-1 until end of turn."""
    caster_id, spell_id = _find_spell_on_stack(state, "Desperate Measures")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +1/-1",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _desperate_measures_execute
    return []


# -----------------------------------------------------------------------------
# SNAKESKIN VEIL - Put +1/+1 counter, gain hexproof
# -----------------------------------------------------------------------------
def _snakeskin_veil_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Snakeskin Veil - counter and hexproof."""
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
            payload={'object_id': target_id, 'abilities': ['hexproof'], 'duration': 'until_end_of_turn'},
            source=choice.source_id
        )
    ]


def snakeskin_veil_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Snakeskin Veil: +1/+1 counter and hexproof until end of turn."""
    caster_id, spell_id = _find_spell_on_stack(state, "Snakeskin Veil")
    valid_targets = _get_creatures_on_battlefield(
        state,
        filter_fn=lambda obj, s: obj.controller == caster_id
    )
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature you control to get +1/+1 and hexproof",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _snakeskin_veil_execute
    return []


# -----------------------------------------------------------------------------
# WILD RIDE - Target creature gets +3/+0 and gains haste
# -----------------------------------------------------------------------------
def _wild_ride_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Wild Ride - pump and grant haste."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [
        Event(
            type=EventType.PT_CHANGE,
            payload={'object_id': target_id, 'power': 3, 'toughness': 0, 'duration': 'until_end_of_turn'},
            source=choice.source_id
        ),
        Event(
            type=EventType.GRANT_ABILITY,
            payload={'object_id': target_id, 'abilities': ['haste'], 'duration': 'until_end_of_turn'},
            source=choice.source_id
        )
    ]


def wild_ride_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Wild Ride: Target creature gets +3/+0 and gains haste."""
    caster_id, spell_id = _find_spell_on_stack(state, "Wild Ride")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to get +3/+0 and haste",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _wild_ride_execute
    return []


# -----------------------------------------------------------------------------
# URENI'S REBUFF - Return target creature to its owner's hand
# -----------------------------------------------------------------------------
def _urenis_rebuff_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Ureni's Rebuff - bounce creature."""
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
            'to_zone_type': ZoneType.HAND
        },
        source=choice.source_id
    )]


def urenis_rebuff_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Ureni's Rebuff: Return target creature to its owner's hand."""
    caster_id, spell_id = _find_spell_on_stack(state, "Ureni's Rebuff")
    valid_targets = _get_creatures_on_battlefield(state)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature to return to its owner's hand",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _urenis_rebuff_execute
    return []


# -----------------------------------------------------------------------------
# AURORAL PROCESSION - Return target card from your graveyard to your hand
# -----------------------------------------------------------------------------
def _auroral_procession_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Auroral Procession - return card from graveyard."""
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
            'to_zone_type': ZoneType.HAND
        },
        source=choice.source_id
    )]


def auroral_procession_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Auroral Procession: Return target card from your graveyard to your hand."""
    caster_id, spell_id = _find_spell_on_stack(state, "Auroral Procession")
    # Get cards in controller's graveyard
    graveyard_key = f"graveyard_{caster_id}"
    if graveyard_key not in state.zones:
        return []
    valid_targets = list(state.zones[graveyard_key].objects)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a card from your graveyard to return to your hand",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _auroral_procession_execute
    return []


# -----------------------------------------------------------------------------
# DEFIBRILLATING CURRENT - Deal 4 damage to target creature/planeswalker, gain 2 life
# -----------------------------------------------------------------------------
def _defibrillating_current_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Defibrillating Current - damage and lifegain."""
    target_id = selected[0] if selected else None
    events = []
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': target_id, 'amount': 4, 'source': choice.source_id, 'is_combat': False},
                source=choice.source_id
            ))
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': 2},
        source=choice.source_id
    ))
    return events


def defibrillating_current_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Defibrillating Current: Deal 4 damage to target, gain 2 life."""
    caster_id, spell_id = _find_spell_on_stack(state, "Defibrillating Current")
    valid_targets = _get_permanents_on_battlefield(
        state,
        types={CardType.CREATURE, CardType.PLANESWALKER}
    )
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a creature or planeswalker for Defibrillating Current (4 damage)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _defibrillating_current_execute
    return []


# -----------------------------------------------------------------------------
# INEVITABLE DEFEAT - Exile target nonland permanent, drain 3 life
# -----------------------------------------------------------------------------
def _inevitable_defeat_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Inevitable Defeat - exile and drain."""
    target_id = selected[0] if selected else None
    events = []
    if target_id:
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.BATTLEFIELD:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone_type': ZoneType.BATTLEFIELD,
                    'to_zone_type': ZoneType.EXILE
                },
                source=choice.source_id
            ))
            # Target's controller loses 3 life
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': target.controller, 'amount': -3},
                source=choice.source_id
            ))
    # Caster gains 3 life
    events.append(Event(
        type=EventType.LIFE_CHANGE,
        payload={'player': choice.player, 'amount': 3},
        source=choice.source_id
    ))
    return events


def inevitable_defeat_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Inevitable Defeat: Exile target nonland permanent, drain 3 life."""
    caster_id, spell_id = _find_spell_on_stack(state, "Inevitable Defeat")
    # Get nonland permanents
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD and CardType.LAND not in obj.characteristics.types:
            valid_targets.append(obj.id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a nonland permanent to exile",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _inevitable_defeat_execute
    return []


# -----------------------------------------------------------------------------
# KIN-TREE SEVERANCE - Exile target permanent with MV 3 or greater
# -----------------------------------------------------------------------------
def _kintree_severance_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Kin-Tree Severance - exile permanent."""
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


def kintree_severance_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Kin-Tree Severance: Exile target permanent with mana value 3 or greater."""
    caster_id, spell_id = _find_spell_on_stack(state, "Kin-Tree Severance")
    # Get permanents with MV >= 3
    valid_targets = []
    for obj in state.objects.values():
        if obj.zone == ZoneType.BATTLEFIELD:
            mv = obj.characteristics.mana_value if hasattr(obj.characteristics, 'mana_value') else 0
            if mv >= 3:
                valid_targets.append(obj.id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a permanent with mana value 3 or greater to exile",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _kintree_severance_execute
    return []


# -----------------------------------------------------------------------------
# PERENNATION - Return target permanent card from graveyard to battlefield
# -----------------------------------------------------------------------------
def _perennation_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Perennation - return permanent with counters."""
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
                'to_zone_type': ZoneType.BATTLEFIELD,
                'enter_with_counters': ['hexproof', 'indestructible']
            },
            source=choice.source_id
        )
    ]


def perennation_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Perennation: Return target permanent from graveyard with hexproof and indestructible counters."""
    caster_id, spell_id = _find_spell_on_stack(state, "Perennation")
    # Get permanent cards in controller's graveyard
    graveyard_key = f"graveyard_{caster_id}"
    if graveyard_key not in state.zones:
        return []
    valid_targets = []
    for card_id in state.zones[graveyard_key].objects:
        card = state.objects.get(card_id)
        if card:
            types = card.characteristics.types
            # Permanents are creatures, artifacts, enchantments, planeswalkers, lands
            if any(t in types for t in [CardType.CREATURE, CardType.ARTIFACT, CardType.ENCHANTMENT, CardType.PLANESWALKER, CardType.LAND]):
                valid_targets.append(card_id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a permanent card from your graveyard to return to the battlefield",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _perennation_execute
    return []


# -----------------------------------------------------------------------------
# MODAL SPELLS
# -----------------------------------------------------------------------------

# COORDINATED MANEUVER - Choose one: damage or destroy enchantment
def _coordinated_maneuver_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Coordinated Maneuver mode 0 - deal damage to creature/planeswalker."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    # Count creatures controlled by caster
    creature_count = len([o for o in state.objects.values()
                          if o.zone == ZoneType.BATTLEFIELD and
                          o.controller == choice.player and
                          CardType.CREATURE in o.characteristics.types])
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': creature_count, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def _coordinated_maneuver_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Coordinated Maneuver mode 1 - destroy enchantment."""
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


def coordinated_maneuver_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Coordinated Maneuver: Modal spell."""
    caster_id, spell_id = _find_spell_on_stack(state, "Coordinated Maneuver")
    modes = [
        {"index": 0, "text": "Deal damage equal to creatures you control to target creature or planeswalker."},
        {"index": 1, "text": "Destroy target enchantment."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Coordinated Maneuver - Choose one:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('creature_or_planeswalker', _coordinated_maneuver_mode_0_execute),
        1: ('enchantment', _coordinated_maneuver_mode_1_execute)
    }
    return []


# SARKHAN'S RESOLVE - Choose one: +3/+3 or destroy creature with flying
def _sarkhans_resolve_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Sarkhan's Resolve mode 0 - +3/+3."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.PT_CHANGE,
        payload={'object_id': target_id, 'power': 3, 'toughness': 3, 'duration': 'until_end_of_turn'},
        source=choice.source_id
    )]


def _sarkhans_resolve_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Sarkhan's Resolve mode 1 - destroy creature with flying."""
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


def sarkhans_resolve_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Sarkhan's Resolve: Modal spell."""
    caster_id, spell_id = _find_spell_on_stack(state, "Sarkhan's Resolve")
    modes = [
        {"index": 0, "text": "Target creature gets +3/+3 until end of turn."},
        {"index": 1, "text": "Destroy target creature with flying."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Sarkhan's Resolve - Choose one:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('creature', _sarkhans_resolve_mode_0_execute),
        1: ('creature_with_flying', _sarkhans_resolve_mode_1_execute)
    }
    return []


# HERITAGE RECLAMATION - Choose one: destroy artifact, destroy enchantment, or exile card from graveyard + draw
def _heritage_reclamation_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Heritage Reclamation mode 0 - destroy artifact."""
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


def _heritage_reclamation_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Heritage Reclamation mode 1 - destroy enchantment."""
    return _heritage_reclamation_mode_0_execute(choice, selected, state)


def _heritage_reclamation_mode_2_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Heritage Reclamation mode 2 - exile from graveyard and draw."""
    events = []
    # Exile is optional ("up to one")
    if selected:
        target_id = selected[0]
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.GRAVEYARD:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.EXILE
                },
                source=choice.source_id
            ))
    events.append(Event(
        type=EventType.DRAW,
        payload={'player': choice.player, 'amount': 1},
        source=choice.source_id
    ))
    return events


def heritage_reclamation_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Heritage Reclamation: Modal spell."""
    caster_id, spell_id = _find_spell_on_stack(state, "Heritage Reclamation")
    modes = [
        {"index": 0, "text": "Destroy target artifact."},
        {"index": 1, "text": "Destroy target enchantment."},
        {"index": 2, "text": "Exile up to one target card from a graveyard. Draw a card."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Heritage Reclamation - Choose one:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('artifact', _heritage_reclamation_mode_0_execute),
        1: ('enchantment', _heritage_reclamation_mode_1_execute),
        2: ('graveyard_card_optional', _heritage_reclamation_mode_2_execute)
    }
    return []


# OVERWHELMING SURGE - Choose one or both: 3 damage to creature, destroy noncreature artifact
def _overwhelming_surge_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Overwhelming Surge mode 0 - 3 damage to creature."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    target = state.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    return [Event(
        type=EventType.DAMAGE,
        payload={'target': target_id, 'amount': 3, 'source': choice.source_id, 'is_combat': False},
        source=choice.source_id
    )]


def _overwhelming_surge_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Overwhelming Surge mode 1 - destroy noncreature artifact."""
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


def overwhelming_surge_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Overwhelming Surge: Choose one or both."""
    caster_id, spell_id = _find_spell_on_stack(state, "Overwhelming Surge")
    modes = [
        {"index": 0, "text": "Deal 3 damage to target creature."},
        {"index": 1, "text": "Destroy target noncreature artifact."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        min_modes=1,
        max_modes=2,
        prompt="Overwhelming Surge - Choose one or both:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('creature', _overwhelming_surge_mode_0_execute),
        1: ('noncreature_artifact', _overwhelming_surge_mode_1_execute)
    }
    return []


# RIVERWALK TECHNIQUE - Choose one: tuck nonland permanent or counter noncreature spell
def _riverwalk_technique_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Riverwalk Technique mode 0 - put on top or bottom of library."""
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
            'to_zone_type': ZoneType.LIBRARY,
            'to_position': 'top_or_bottom'  # Owner chooses
        },
        source=choice.source_id
    )]


def _riverwalk_technique_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Riverwalk Technique mode 1 - counter noncreature spell."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    return [Event(
        type=EventType.COUNTER_SPELL,
        payload={'spell_id': target_id},
        source=choice.source_id
    )]


def riverwalk_technique_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Riverwalk Technique: Modal spell."""
    caster_id, spell_id = _find_spell_on_stack(state, "Riverwalk Technique")
    modes = [
        {"index": 0, "text": "The owner of target nonland permanent puts it on top or bottom of their library."},
        {"index": 1, "text": "Counter target noncreature spell."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Riverwalk Technique - Choose one:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('nonland_permanent', _riverwalk_technique_mode_0_execute),
        1: ('noncreature_spell', _riverwalk_technique_mode_1_execute)
    }
    return []


# WAIL OF WAR - Choose one: -1/-1 to opponent's creatures or return 2 creatures from graveyard
def _wail_of_war_mode_0_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Wail of War mode 0 - -1/-1 to target opponent's creatures."""
    target_id = selected[0] if selected else None
    if not target_id or target_id not in state.players:
        return []
    events = []
    for obj in state.objects.values():
        if (obj.zone == ZoneType.BATTLEFIELD and
            obj.controller == target_id and
            CardType.CREATURE in obj.characteristics.types):
            events.append(Event(
                type=EventType.PT_CHANGE,
                payload={'object_id': obj.id, 'power': -1, 'toughness': -1, 'duration': 'until_end_of_turn'},
                source=choice.source_id
            ))
    return events


def _wail_of_war_mode_1_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Wail of War mode 1 - return creatures from graveyard."""
    events = []
    for target_id in selected[:2]:  # Up to 2
        target = state.objects.get(target_id)
        if target and target.zone == ZoneType.GRAVEYARD:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone_type': ZoneType.HAND
                },
                source=choice.source_id
            ))
    return events


def wail_of_war_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Wail of War: Modal spell."""
    caster_id, spell_id = _find_spell_on_stack(state, "Wail of War")
    modes = [
        {"index": 0, "text": "Creatures target opponent controls get -1/-1 until end of turn."},
        {"index": 1, "text": "Return up to two target creature cards from your graveyard to your hand."}
    ]
    choice = create_modal_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        modes=modes,
        prompt="Wail of War - Choose one:"
    )
    choice.callback_data['mode_handlers'] = {
        0: ('opponent', _wail_of_war_mode_0_execute),
        1: ('creature_cards_in_graveyard', _wail_of_war_mode_1_execute)
    }
    return []


# =============================================================================
# COUNTERSPELLS
# =============================================================================

# DISPELLING EXHALE - Counter unless pays {2} (or {4} with Dragon beheld)
def _dispelling_exhale_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Dispelling Exhale - counter spell unless controller pays."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    cost = 4 if choice.callback_data.get('dragon_beheld') else 2
    return [Event(
        type=EventType.COUNTER_SPELL_UNLESS_PAY,
        payload={'spell_id': target_id, 'cost': cost},
        source=choice.source_id
    )]


def dispelling_exhale_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Dispelling Exhale: Counter target spell unless controller pays {2} (or {4})."""
    caster_id, spell_id = _find_spell_on_stack(state, "Dispelling Exhale")
    # Get spells on stack (excluding self)
    stack_zone = state.zones.get('stack')
    valid_targets = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != spell_id:
                valid_targets.append(obj_id)
    if not valid_targets:
        return []
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a spell to counter (unless controller pays)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _dispelling_exhale_execute
    return []


# SPECTRAL DENIAL - Counter unless pays {X}
def _spectral_denial_execute(choice, selected, state: GameState) -> list[Event]:
    """Execute Spectral Denial - counter spell unless controller pays X."""
    target_id = selected[0] if selected else None
    if not target_id:
        return []
    x_value = choice.callback_data.get('x_value', 0)
    return [Event(
        type=EventType.COUNTER_SPELL_UNLESS_PAY,
        payload={'spell_id': target_id, 'cost': x_value},
        source=choice.source_id
    )]


def spectral_denial_resolve(targets: list, state: GameState) -> list[Event]:
    """Resolve Spectral Denial: Counter target spell unless controller pays {X}."""
    caster_id, spell_id = _find_spell_on_stack(state, "Spectral Denial")
    # Get spells on stack (excluding self)
    stack_zone = state.zones.get('stack')
    valid_targets = []
    if stack_zone:
        for obj_id in stack_zone.objects:
            if obj_id != spell_id:
                valid_targets.append(obj_id)
    if not valid_targets:
        return []
    # X value would be determined from spell's mana cost payment
    # For now, assume X is stored somewhere in the spell object
    choice = create_target_choice(
        state=state,
        player_id=caster_id,
        source_id=spell_id,
        legal_targets=valid_targets,
        prompt="Choose a spell to counter (unless controller pays X)",
        min_targets=1,
        max_targets=1
    )
    choice.choice_type = "target_with_callback"
    choice.callback_data['handler'] = _spectral_denial_execute
    return []


# =============================================================================
# SETUP INTERCEPTOR FUNCTIONS FOR ETB CREATURES WITH TARGETING
# =============================================================================

# --- ICERIDGE SERPENT ---
# When this creature enters, return target creature an opponent controls to its owner's hand.
def iceridge_serpent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Get opponent's creatures
        valid_targets = []
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                o.controller != obj.controller):
                valid_targets.append(o.id)
        if not valid_targets:
            return []
        # Create target choice
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an opponent's creature to return to their hand",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': sel[0],
                'from_zone_type': ZoneType.BATTLEFIELD,
                'to_zone_type': ZoneType.HAND
            },
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- CONSTRICTOR SAGE ---
# When this creature enters, tap target creature an opponent controls and put a stun counter on it.
def constrictor_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Get opponent's creatures
        valid_targets = []
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                o.controller != obj.controller):
                valid_targets.append(o.id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to tap and stun",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        def handler(c, sel, s):
            if not sel:
                return []
            target_id = sel[0]
            return [
                Event(type=EventType.TAP, payload={'object_id': target_id}, source=c.source_id),
                Event(type=EventType.COUNTER_ADDED, payload={'object_id': target_id, 'counter_type': 'stun', 'amount': 1}, source=c.source_id)
            ]
        choice.callback_data['handler'] = handler
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- HUMBLING ELDER ---
# When this creature enters, target creature an opponent controls gets -2/-0 until end of turn.
def humbling_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                o.controller != obj.controller):
                valid_targets.append(o.id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to get -2/-0",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.PT_CHANGE,
            payload={'object_id': sel[0], 'power': -2, 'toughness': 0, 'duration': 'until_end_of_turn'},
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- GURMAG RAKSHASA ---
# When this creature enters, target creature an opponent controls gets -2/-2
# and target creature you control gets +2/+2 until end of turn.
def gurmag_rakshasa_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        opp_creatures = []
        own_creatures = []
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD and CardType.CREATURE in o.characteristics.types:
                if o.controller != obj.controller:
                    opp_creatures.append(o.id)
                else:
                    own_creatures.append(o.id)
        if not opp_creatures or not own_creatures:
            return []
        # First choose opponent's creature
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=opp_creatures,
            prompt="Choose an opponent's creature to get -2/-2",
            min_targets=1,
            max_targets=1,
            callback_data={'own_creatures': own_creatures}
        )
        choice.choice_type = "target_with_callback"
        def handler(c, sel, s):
            if not sel:
                return []
            opp_target = sel[0]
            # Need to create second choice for own creature
            events = [Event(
                type=EventType.PT_CHANGE,
                payload={'object_id': opp_target, 'power': -2, 'toughness': -2, 'duration': 'until_end_of_turn'},
                source=c.source_id
            )]
            # Add +2/+2 to first own creature for simplicity
            own = c.callback_data.get('own_creatures', [])
            if own:
                events.append(Event(
                    type=EventType.PT_CHANGE,
                    payload={'object_id': own[0], 'power': 2, 'toughness': 2, 'duration': 'until_end_of_turn'},
                    source=c.source_id
                ))
            return events
        choice.callback_data['handler'] = handler
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- SUMMIT INTIMIDATOR ---
# When this creature enters, target creature can't block this turn.
def summit_intimidator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = _get_creatures_on_battlefield(state)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature that can't block this turn",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.GRANT_RESTRICTION,
            payload={'object_id': sel[0], 'restriction': 'cant_block', 'duration': 'until_end_of_turn'},
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- SAGE OF THE FANG ---
# When this creature enters, put a +1/+1 counter on target creature.
def sage_of_the_fang_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = _get_creatures_on_battlefield(state)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to get a +1/+1 counter",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': sel[0], 'counter_type': '+1/+1', 'amount': 1},
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- REPUTABLE MERCHANT ---
# When this creature enters or dies, put a +1/+1 counter on target creature you control.
def reputable_merchant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and
                CardType.CREATURE in o.characteristics.types and
                o.controller == obj.controller):
                valid_targets.append(o.id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature you control to get a +1/+1 counter",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': sel[0], 'counter_type': '+1/+1', 'amount': 1},
            source=c.source_id
        )] if sel else []
        return []

    return [
        make_etb_trigger(obj, effect_fn),
        make_death_trigger(obj, effect_fn)
    ]


# --- REIGNING VICTOR ---
# When this creature enters, target creature gets +1/+0 and gains indestructible until end of turn.
def reigning_victor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = _get_creatures_on_battlefield(state)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a creature to get +1/+0 and indestructible",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [
            Event(type=EventType.PT_CHANGE, payload={'object_id': sel[0], 'power': 1, 'toughness': 0, 'duration': 'until_end_of_turn'}, source=c.source_id),
            Event(type=EventType.GRANT_ABILITY, payload={'object_id': sel[0], 'abilities': ['indestructible'], 'duration': 'until_end_of_turn'}, source=c.source_id)
        ] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- SONIC SHRIEKER ---
# When this creature enters, it deals 2 damage to any target and you gain 2 life.
def sonic_shrieker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD:
                if CardType.CREATURE in o.characteristics.types or CardType.PLANESWALKER in o.characteristics.types:
                    valid_targets.append(o.id)
        for player_id in state.players:
            valid_targets.append(player_id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a target for Sonic Shrieker (2 damage)",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        def handler(c, sel, s):
            if not sel:
                return []
            target_id = sel[0]
            events = [
                Event(type=EventType.DAMAGE, payload={'target': target_id, 'amount': 2, 'source': c.source_id, 'is_combat': False}, source=c.source_id),
                Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=c.source_id)
            ]
            # If player was dealt damage, they discard
            if target_id in s.players:
                events.append(Event(type=EventType.DISCARD, payload={'player': target_id, 'amount': 1}, source=c.source_id))
            return events
        choice.callback_data['handler'] = handler
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- MAGMATIC HELLKITE ---
# When this creature enters, destroy target nonbasic land an opponent controls.
def magmatic_hellkite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        # Get nonbasic lands opponents control
        valid_targets = []
        for o in state.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD and
                CardType.LAND in o.characteristics.types and
                o.controller != obj.controller and
                'Basic' not in o.characteristics.supertypes):
                valid_targets.append(o.id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a nonbasic land to destroy",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sel[0]},
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- DISRUPTIVE STORMBROOD ---
# When this creature enters, destroy up to one target artifact or enchantment.
def disruptive_stormbrood_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = []
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD:
                if CardType.ARTIFACT in o.characteristics.types or CardType.ENCHANTMENT in o.characteristics.types:
                    valid_targets.append(o.id)
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose an artifact or enchantment to destroy (up to one)",
            min_targets=0,  # "up to one"
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': sel[0]},
            source=c.source_id
        )] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# --- WATCHER OF THE WAYSIDE ---
# When this creature enters, target player mills two cards. You gain 2 life.
def watcher_of_the_wayside_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        valid_targets = list(state.players.keys())
        if not valid_targets:
            return []
        choice = create_target_choice(
            state=state,
            player_id=obj.controller,
            source_id=obj.id,
            legal_targets=valid_targets,
            prompt="Choose a player to mill two cards",
            min_targets=1,
            max_targets=1
        )
        choice.choice_type = "target_with_callback"
        choice.callback_data['handler'] = lambda c, sel, s: [
            Event(type=EventType.MILL, payload={'player': sel[0], 'amount': 2}, source=c.source_id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 2}, source=c.source_id)
        ] if sel else []
        return []
    return [make_etb_trigger(obj, effect_fn)]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

UGIN_EYE_OF_THE_STORMS = make_planeswalker(
    name="Ugin, Eye of the Storms",
    mana_cost="{7}",
    colors=set(),
    loyalty=7,
    subtypes={"Ugin"},
    supertypes={"Legendary"},
    text="When you cast this spell, exile up to one target permanent that's one or more colors.\nWhenever you cast a colorless spell, exile up to one target permanent that's one or more colors.\n+2: You gain 3 life and draw a card.\n0: Add {C}{C}{C}.\n−11: Search your library for any number of colorless nonland cards, exile them, then shuffle. Until end of turn, you may cast those cards without paying their mana costs.",
    rarity="mythic",
)

ANAFENZA_UNYIELDING_LINEAGE = make_creature(
    name="Anafenza, Unyielding Lineage",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Soldier", "Spirit"},
    supertypes={"Legendary"},
    text="Flash\nFirst strike\nWhenever another nontoken creature you control dies, Anafenza endures 2. (Put two +1/+1 counters on it or create a 2/2 white Spirit creature token.)",
    rarity="rare",
)

ARASHIN_SUNSHIELD = make_creature(
    name="Arashin Sunshield",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="When this creature enters, exile up to two target cards from a single graveyard.\n{W}, {T}: Tap target creature.",
    rarity="common",
)

BEARER_OF_GLORY = make_creature(
    name="Bearer of Glory",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="During your turn, this creature has first strike.\n{4}{W}: Creatures you control get +1/+1 until end of turn.",
    rarity="common",
)

CLARION_CONQUEROR = make_creature(
    name="Clarion Conqueror",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nActivated abilities of artifacts, creatures, and planeswalkers can't be activated.",
    rarity="rare",
)

COORDINATED_MANEUVER = make_instant(
    name="Coordinated Maneuver",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Coordinated Maneuver deals damage equal to the number of creatures you control to target creature or planeswalker.\n• Destroy target enchantment.",
    rarity="common",
    resolve=coordinated_maneuver_resolve,
)

DALKOVAN_PACKBEASTS = make_creature(
    name="Dalkovan Packbeasts",
    power=0, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Ox"},
    text="Vigilance\nMobilize 3 (Whenever this creature attacks, create three tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)",
    rarity="uncommon",
)

DESCENDANT_OF_STORMS = make_creature(
    name="Descendant of Storms",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature attacks, you may pay {1}{W}. If you do, it endures 1. (Put a +1/+1 counter on it or create a 1/1 white Spirit creature token.)",
    rarity="uncommon",
)

DRAGONBACK_LANCER = make_creature(
    name="Dragonback Lancer",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Flying\nMobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)",
    rarity="common",
)

DUTY_BEYOND_DEATH = make_instant(
    name="Duty Beyond Death",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="As an additional cost to cast this spell, sacrifice a creature.\nCreatures you control gain indestructible until end of turn. Put a +1/+1 counter on each creature you control. (Damage and effects that say \"destroy\" don't destroy those creatures.)",
    rarity="uncommon",
)

ELSPETH_STORM_SLAYER = make_planeswalker(
    name="Elspeth, Storm Slayer",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    loyalty=5,
    subtypes={"Elspeth"},
    supertypes={"Legendary"},
    text="If one or more tokens would be created under your control, twice that many of those tokens are created instead.\n+1: Create a 1/1 white Soldier creature token.\n0: Put a +1/+1 counter on each creature you control. Those creatures gain flying until your next turn.\n−3: Destroy target creature an opponent controls with mana value 3 or greater.",
    rarity="mythic",
)

FORTRESS_KINGUARD = make_creature(
    name="Fortress Kin-Guard",
    power=1, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Dog", "Soldier"},
    text="When this creature enters, it endures 1. (Put a +1/+1 counter on it or create a 1/1 white Spirit creature token.)",
    rarity="common",
)

FURIOUS_FOREBEAR = make_creature(
    name="Furious Forebear",
    power=3, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Warrior"},
    text="Whenever a creature you control dies while this card is in your graveyard, you may pay {1}{W}. If you do, return this card from your graveyard to your hand.",
    rarity="uncommon",
)

LIGHTFOOT_TECHNIQUE = make_instant(
    name="Lightfoot Technique",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Put a +1/+1 counter on target creature. It gains flying and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    rarity="common",
    resolve=lightfoot_technique_resolve,
)

LOXODON_BATTLE_PRIEST = make_creature(
    name="Loxodon Battle Priest",
    power=3, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Elephant"},
    text="At the beginning of combat on your turn, put a +1/+1 counter on another target creature you control.",
    rarity="uncommon",
)

MARDU_DEVOTEE = make_creature(
    name="Mardu Devotee",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When this creature enters, scry 2. (Look at the top two cards of your library, then put any number of them on the bottom and the rest on top in any order.)\n{1}: Add {R}, {W}, or {B}. Activate only once each turn.",
    rarity="common",
)

OSSEOUS_EXHALE = make_instant(
    name="Osseous Exhale",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="As an additional cost to cast this spell, you may behold a Dragon. (You may choose a Dragon you control or reveal a Dragon card from your hand.)\nOsseous Exhale deals 5 damage to target attacking or blocking creature. If a Dragon was beheld, you gain 2 life.",
    rarity="common",
    resolve=osseous_exhale_resolve,
)

POISED_PRACTITIONER = make_creature(
    name="Poised Practitioner",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flurry — Whenever you cast your second spell each turn, put a +1/+1 counter on this creature. Scry 1. (Look at the top card of your library. You may put that card on the bottom.)",
    rarity="common",
)

RALLY_THE_MONASTERY = make_instant(
    name="Rally the Monastery",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="This spell costs {2} less to cast if you've cast another spell this turn.\nChoose one —\n• Create two 1/1 white Monk creature tokens with prowess.\n• Up to two target creatures you control each get +2/+2 until end of turn.\n• Destroy target creature with power 4 or greater.",
    rarity="uncommon",
)

REBELLIOUS_STRIKE = make_instant(
    name="Rebellious Strike",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature gets +3/+0 until end of turn.\nDraw a card.",
    rarity="common",
    resolve=rebellious_strike_resolve,
)

RILING_DAWNBREAKER = make_creature(
    name="Riling Dawnbreaker",
    power=3, toughness=4,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Dragon"},
    text="Flying, vigilance\nAt the beginning of combat on your turn, another target creature you control gets +1/+0 until end of turn.\n// Adventure — Signaling Roar {1}{W} (Sorcery)\nCreate a 2/2 white Soldier creature token. (Then shuffle this card into its owner's library.)",
    rarity="common",
)

SAGE_OF_THE_SKIES = make_creature(
    name="Sage of the Skies",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk"},
    text="When you cast this spell, if you've cast another spell this turn, copy this spell. (The copy becomes a token.)\nFlying, lifelink",
    rarity="rare",
)

SALT_ROAD_PACKBEAST = make_creature(
    name="Salt Road Packbeast",
    power=4, toughness=3,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Beast"},
    text="Affinity for creatures (This spell costs {1} less to cast for each creature you control.)\nWhen this creature enters, draw a card.",
    rarity="common",
)

SMILE_AT_DEATH = make_enchantment(
    name="Smile at Death",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, return up to two target creature cards with power 2 or less from your graveyard to the battlefield. Put a +1/+1 counter on each of those creatures.",
    rarity="mythic",
)

STARRYEYED_SKYRIDER = make_creature(
    name="Starry-Eyed Skyrider",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Flying\nWhenever this creature attacks, another target creature you control gains flying until end of turn.\nAttacking tokens you control have flying.",
    rarity="uncommon",
)

STATIC_SNARE = make_enchantment(
    name="Static Snare",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="Flash\nThis spell costs {1} less to cast for each attacking creature.\nWhen this enchantment enters, exile target artifact or creature an opponent controls until this enchantment leaves the battlefield.",
    rarity="uncommon",
)

STORMBEACON_BLADE = make_artifact(
    name="Stormbeacon Blade",
    mana_cost="{1}{W}",
    text="Equipped creature gets +3/+0.\nWhenever equipped creature attacks, draw a card if you control three or more attacking creatures.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    rarity="uncommon",
    subtypes={"Equipment"},
)

STORMPLAIN_DETAINMENT = make_enchantment(
    name="Stormplain Detainment",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield.",
    rarity="common",
)

SUNPEARL_KIRIN = make_creature(
    name="Sunpearl Kirin",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Kirin"},
    text="Flash\nFlying\nWhen this creature enters, return up to one other target nonland permanent you control to its owner's hand. If it was a token, draw a card.",
    rarity="uncommon",
)

TEEMING_DRAGONSTORM = make_enchantment(
    name="Teeming Dragonstorm",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="When this enchantment enters, create two 2/2 white Soldier creature tokens.\nWhen a Dragon you control enters, return this enchantment to its owner's hand.",
    rarity="uncommon",
)

TEMPEST_HAWK = make_creature(
    name="Tempest Hawk",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    text="Flying\nWhenever this creature deals combat damage to a player, you may search your library for a card named Tempest Hawk, reveal it, put it into your hand, then shuffle.\nA deck can have any number of cards named Tempest Hawk.",
    rarity="common",
)

UNITED_BATTLEFRONT = make_sorcery(
    name="United Battlefront",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Look at the top seven cards of your library. Put up to two noncreature, nonland permanent cards with mana value 3 or less from among them onto the battlefield. Put the rest on the bottom of your library in a random order.",
    rarity="rare",
)

VOICE_OF_VICTORY = make_creature(
    name="Voice of Victory",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bard", "Human"},
    text="Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)\nYour opponents can't cast spells during your turn.",
    rarity="rare",
)

WAYSPEAKER_BODYGUARD = make_creature(
    name="Wayspeaker Bodyguard",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Monk", "Orc"},
    text="When this creature enters, return target nonland permanent card with mana value 2 or less from your graveyard to your hand.\nFlurry — Whenever you cast your second spell each turn, tap target creature an opponent controls.",
    rarity="uncommon",
)

AEGIS_SCULPTOR = make_creature(
    name="Aegis Sculptor",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Wizard"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\nAt the beginning of your upkeep, you may exile two cards from your graveyard. If you do, put a +1/+1 counter on this creature.",
    rarity="uncommon",
)

AGENT_OF_KOTIS = make_creature(
    name="Agent of Kotis",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="Renew — {3}{U}, Exile this card from your graveyard: Put two +1/+1 counters on target creature. Activate only as a sorcery.",
    rarity="common",
)

AMBLING_STORMSHELL = make_creature(
    name="Ambling Stormshell",
    power=5, toughness=9,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Turtle"},
    text="Ward {2}\nWhenever this creature attacks, put three stun counters on it and draw three cards. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you cast a Turtle spell, untap this creature.",
    rarity="rare",
)

BEWILDERING_BLIZZARD = make_instant(
    name="Bewildering Blizzard",
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Creatures your opponents control get -3/-0 until end of turn.",
    rarity="uncommon",
)

CONSTRICTOR_SAGE = make_creature(
    name="Constrictor Sage",
    power=4, toughness=4,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Snake", "Wizard"},
    text="When this creature enters, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nRenew — {2}{U}, Exile this card from your graveyard: Tap target creature an opponent controls and put a stun counter on it. Activate only as a sorcery.",
    rarity="uncommon",
    setup_interceptors=constrictor_sage_setup,
)

DIRGUR_ISLAND_DRAGON = make_creature(
    name="Dirgur Island Dragon",
    power=4, toughness=4,
    mana_cost="{5}{U}",
    colors={Color.BLUE},
    subtypes={"Dragon"},
    text="Flying\nWard {2} (Whenever this creature becomes the target of a spell or ability an opponent controls, counter it unless that player pays {2}.)\n// Adventure — Skimming Strike {1}{U} (Instant)\nTap up to one target creature. Draw a card. (Then shuffle this card into its owner's library.)",
    rarity="common",
)

DISPELLING_EXHALE = make_instant(
    name="Dispelling Exhale",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, you may behold a Dragon. (You may choose a Dragon you control or reveal a Dragon card from your hand.)\nCounter target spell unless its controller pays {2}. If a Dragon was beheld, counter that spell unless its controller pays {4} instead.",
    rarity="common",
    resolve=dispelling_exhale_resolve,
)

DRAGONOLOGIST = make_creature(
    name="Dragonologist",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, look at the top six cards of your library. You may reveal an instant, sorcery, or Dragon card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.\nUntapped Dragons you control have hexproof.",
    rarity="rare",
)

DRAGONSTORM_FORECASTER = make_creature(
    name="Dragonstorm Forecaster",
    power=0, toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="{2}, {T}: Search your library for a card named Dragonstorm Globe or Boulderborn Dragon, reveal it, put it into your hand, then shuffle.",
    rarity="uncommon",
)

ESSENCE_ANCHOR = make_artifact(
    name="Essence Anchor",
    mana_cost="{2}{U}",
    text="At the beginning of your upkeep, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{T}: Create a 2/2 black Zombie Druid creature token. Activate only during your turn and only if a card left your graveyard this turn.",
    rarity="uncommon",
)

FOCUS_THE_MIND = make_instant(
    name="Focus the Mind",
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    text="This spell costs {2} less to cast if you've cast another spell this turn.\nDraw three cards, then discard a card.",
    rarity="common",
)

FRESH_START = make_enchantment(
    name="Fresh Start",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant creature\nEnchanted creature gets -5/-0 and loses all abilities.",
    rarity="uncommon",
    subtypes={"Aura"},
)

HIGHSPIRE_BELLRINGER = make_creature(
    name="Highspire Bell-Ringer",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Djinn", "Monk"},
    text="Flying\nThe second spell you cast each turn costs {1} less to cast.",
    rarity="common",
)

HUMBLING_ELDER = make_creature(
    name="Humbling Elder",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Monk"},
    text="Flash\nWhen this creature enters, target creature an opponent controls gets -2/-0 until end of turn.",
    rarity="common",
    setup_interceptors=humbling_elder_setup,
)

ICERIDGE_SERPENT = make_creature(
    name="Iceridge Serpent",
    power=3, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent"},
    text="When this creature enters, return target creature an opponent controls to its owner's hand.",
    rarity="common",
    setup_interceptors=iceridge_serpent_setup,
)

KISHLA_TRAWLERS = make_creature(
    name="Kishla Trawlers",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, you may exile a creature card from your graveyard. When you do, return target instant or sorcery card from your graveyard to your hand.",
    rarity="uncommon",
)

MARANG_RIVER_REGENT = make_creature(
    name="Marang River Regent",
    power=6, toughness=7,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, return up to two other target nonland permanents to their owners' hands.\n// Adventure — Coil and Catch {3}{U} (Instant)\nDraw three cards, then discard a card. (Then shuffle this card into its owner's library.)",
    rarity="rare",
)

NAGA_FLESHCRAFTER = make_creature(
    name="Naga Fleshcrafter",
    power=0, toughness=0,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter", "Snake"},
    text="You may have this creature enter as a copy of any creature on the battlefield.\nRenew — {2}{U}, Exile this card from your graveyard: Put a +1/+1 counter on target nonlegendary creature you control. Each other creature you control becomes a copy of that creature until end of turn. Activate only as a sorcery.",
    rarity="rare",
)

RINGING_STRIKE_MASTERY = make_enchantment(
    name="Ringing Strike Mastery",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\nEnchanted creature has \"{5}: Untap this creature.\"",
    rarity="common",
    subtypes={"Aura"},
)

RIVERWALK_TECHNIQUE = make_instant(
    name="Riverwalk Technique",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Choose one —\n• The owner of target nonland permanent puts it on their choice of the top or bottom of their library.\n• Counter target noncreature spell.",
    rarity="common",
    resolve=riverwalk_technique_resolve,
)

ROILING_DRAGONSTORM = make_enchantment(
    name="Roiling Dragonstorm",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="When this enchantment enters, draw two cards, then discard a card.\nWhen a Dragon you control enters, return this enchantment to its owner's hand.",
    rarity="uncommon",
)

SIBSIG_APPRAISER = make_creature(
    name="Sibsig Appraiser",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Advisor", "Zombie"},
    text="When this creature enters, look at the top two cards of your library. Put one of them into your hand and the other into your graveyard.",
    rarity="common",
)

SNOWMELT_STAG = make_creature(
    name="Snowmelt Stag",
    power=2, toughness=5,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Elk"},
    text="Vigilance\nDuring your turn, this creature has base power and toughness 5/2.\n{5}{U}{U}: This creature can't be blocked this turn.",
    rarity="common",
)

SPECTRAL_DENIAL = make_instant(
    name="Spectral Denial",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="This spell costs {1} less to cast for each creature you control with power 4 or greater.\nCounter target spell unless its controller pays {X}.",
    rarity="uncommon",
    resolve=spectral_denial_resolve,
)

STILLNESS_IN_MOTION = make_enchantment(
    name="Stillness in Motion",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="At the beginning of your upkeep, mill three cards. Then if your library has no cards in it, exile this enchantment and put five cards from your graveyard on top of your library in any order.",
    rarity="rare",
)

TAIGAM_MASTER_OPPORTUNIST = make_creature(
    name="Taigam, Master Opportunist",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Flurry — Whenever you cast your second spell each turn, copy it, then exile the spell you cast with four time counters on it. If it doesn't have suspend, it gains suspend. (At the beginning of its owner's upkeep, they remove a time counter. When the last is removed, they may play it without paying its mana cost. If it's a creature, it has haste.)",
    rarity="mythic",
)

TEMUR_DEVOTEE = make_creature(
    name="Temur Devotee",
    power=3, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Druid", "Human"},
    text="Defender\n{1}: Add {G}, {U}, or {R}. Activate only once each turn.",
    rarity="common",
)

UNENDING_WHISPER = make_sorcery(
    name="Unending Whisper",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Draw a card.\nHarmonize {5}{U} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="common",
)

URENIS_REBUFF = make_sorcery(
    name="Ureni's Rebuff",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand.\nHarmonize {5}{U} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="uncommon",
    resolve=urenis_rebuff_resolve,
)

VETERAN_ICE_CLIMBER = make_creature(
    name="Veteran Ice Climber",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Scout"},
    text="Vigilance\nThis creature can't be blocked.\nWhenever this creature attacks, up to one target player mills cards equal to this creature's power. (They put that many cards from the top of their library into their graveyard.)",
    rarity="uncommon",
)

WINGBLADE_DISCIPLE = make_creature(
    name="Wingblade Disciple",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Monk"},
    text="Flying\nFlurry — Whenever you cast your second spell each turn, create a 1/1 white Bird creature token with flying.",
    rarity="uncommon",
)

WINGSPAN_STRIDE = make_enchantment(
    name="Wingspan Stride",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nEnchanted creature gets +1/+1 and has flying.\n{2}{U}: Return this Aura to its owner's hand.",
    rarity="common",
    subtypes={"Aura"},
)

WINTERNIGHT_STORIES = make_sorcery(
    name="Winternight Stories",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards. Then discard two cards unless you discard a creature card.\nHarmonize {4}{U} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="rare",
)

ABZAN_DEVOTEE = make_creature(
    name="Abzan Devotee",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Dog"},
    text="{1}: Add {W}, {B}, or {G}. Activate only once each turn.\n{2}{B}: Return this card from your graveyard to your hand.",
    rarity="common",
)

ADORNED_CROCODILE = make_creature(
    name="Adorned Crocodile",
    power=5, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Crocodile"},
    text="When this creature dies, create a 2/2 black Zombie Druid creature token.\nRenew — {B}, Exile this card from your graveyard: Put a +1/+1 counter on target creature. Activate only as a sorcery.",
    rarity="common",
)

AGGRESSIVE_NEGOTIATIONS = make_sorcery(
    name="Aggressive Negotiations",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it and exile that card. Put a +1/+1 counter on up to one target creature you control.",
    rarity="common",
)

ALCHEMISTS_ASSISTANT = make_creature(
    name="Alchemist's Assistant",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Monkey"},
    text="Lifelink\nRenew — {1}{B}, Exile this card from your graveyard: Put a lifelink counter on target creature. Activate only as a sorcery.",
    rarity="uncommon",
)

ALESHAS_LEGACY = make_instant(
    name="Alesha's Legacy",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature you control gains deathtouch and indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    rarity="common",
    resolve=aleshas_legacy_resolve,
)

AVENGER_OF_THE_FALLEN = make_creature(
    name="Avenger of the Fallen",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="Deathtouch\nMobilize X, where X is the number of creature cards in your graveyard. (Whenever this creature attacks, create X tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)",
    rarity="rare",
)

CAUSTIC_EXHALE = make_instant(
    name="Caustic Exhale",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, behold a Dragon or pay {1}. (To behold a Dragon, choose a Dragon you control or reveal a Dragon card from your hand.)\nTarget creature gets -3/-3 until end of turn.",
    rarity="common",
    resolve=caustic_exhale_resolve,
)

CORRODING_DRAGONSTORM = make_enchantment(
    name="Corroding Dragonstorm",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="When this enchantment enters, each opponent loses 2 life and you gain 2 life. Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\nWhen a Dragon you control enters, return this enchantment to its owner's hand.",
    rarity="uncommon",
)

CRUEL_TRUTHS = make_instant(
    name="Cruel Truths",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Surveil 2, then draw two cards. You lose 2 life. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    rarity="common",
)

DELTA_BLOODFLIES = make_creature(
    name="Delta Bloodflies",
    power=1, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Insect"},
    text="Flying\nWhenever this creature attacks, if you control a creature with a counter on it, each opponent loses 1 life.",
    rarity="common",
)

DESPERATE_MEASURES = make_instant(
    name="Desperate Measures",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets +1/-1 until end of turn. When it dies under your control this turn, draw two cards.",
    rarity="uncommon",
    resolve=desperate_measures_resolve,
)

DRAGONS_PREY = make_instant(
    name="Dragon's Prey",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="This spell costs {2} more to cast if it targets a Dragon.\nDestroy target creature.",
    rarity="common",
    resolve=dragons_prey_resolve,
)

FERAL_DEATHGORGER = make_creature(
    name="Feral Deathgorger",
    power=3, toughness=5,
    mana_cost="{5}{B}",
    colors={Color.BLACK},
    subtypes={"Dragon"},
    text="Flying, deathtouch\nWhen this creature enters, exile up to two target cards from a single graveyard.\n// Adventure — Dusk Sight {1}{B} (Sorcery)\nPut a +1/+1 counter on up to one target creature. Draw a card. (Then shuffle this card into its owner's library.)",
    rarity="common",
)

GURMAG_RAKSHASA = make_creature(
    name="Gurmag Rakshasa",
    power=5, toughness=5,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, target creature an opponent controls gets -2/-2 until end of turn and target creature you control gets +2/+2 until end of turn.",
    rarity="uncommon",
    setup_interceptors=gurmag_rakshasa_setup,
)

HUNDREDBATTLE_VETERAN = make_creature(
    name="Hundred-Battle Veteran",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Warrior", "Zombie"},
    text="As long as there are three or more different kinds of counters among creatures you control, this creature gets +2/+4.\nYou may cast this card from your graveyard. If you do, it enters with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
    rarity="uncommon",
)

KINTREE_NURTURER = make_creature(
    name="Kin-Tree Nurturer",
    power=2, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Druid", "Human"},
    text="Lifelink\nWhen this creature enters, it endures 1. (Put a +1/+1 counter on it or create a 1/1 white Spirit creature token.)",
    rarity="common",
)

KRUMAR_INITIATE = make_creature(
    name="Krumar Initiate",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Human"},
    text="{X}{B}, {T}, Pay X life: This creature endures X. Activate only as a sorcery. (Put X +1/+1 counters on it or create an X/X white Spirit creature token.)",
    rarity="uncommon",
)

NIGHTBLADE_BRIGADE = make_creature(
    name="Nightblade Brigade",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Soldier"},
    text="Deathtouch\nMobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)\nWhen this creature enters, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    rarity="common",
)

QARSI_REVENANT = make_creature(
    name="Qarsi Revenant",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire"},
    text="Flying, deathtouch, lifelink\nRenew — {2}{B}, Exile this card from your graveyard: Put a flying counter, a deathtouch counter, and a lifelink counter on target creature. Activate only as a sorcery.",
    rarity="rare",
)

ROTCURSE_RAKSHASA = make_creature(
    name="Rot-Curse Rakshasa",
    power=5, toughness=5,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Trample\nDecayed (This creature can't block. When it attacks, sacrifice it at end of combat.)\nRenew — {X}{B}{B}, Exile this card from your graveyard: Put a decayed counter on each of X target creatures. Activate only as a sorcery.",
    rarity="mythic",
)

SALT_ROAD_SKIRMISH = make_sorcery(
    name="Salt Road Skirmish",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Create two 1/1 red Warrior creature tokens. They gain haste until end of turn. Sacrifice them at the beginning of the next end step.",
    rarity="uncommon",
    resolve=salt_road_skirmish_resolve,
)

SANDSKITTER_OUTRIDER = make_creature(
    name="Sandskitter Outrider",
    power=2, toughness=1,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhen this creature enters, it endures 2. (Put two +1/+1 counters on it or create a 2/2 white Spirit creature token.)",
    rarity="common",
)

SCAVENGER_REGENT = make_creature(
    name="Scavenger Regent",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Dragon"},
    text="Flying\nWard—Discard a card.\n// Adventure — Exude Toxin {X}{B}{B} (Sorcery)\nEach non-Dragon creature gets -X/-X until end of turn. (Then shuffle this card into its owner's library.)",
    rarity="rare",
)

THE_SIBSIG_CEREMONY = make_enchantment(
    name="The Sibsig Ceremony",
    mana_cost="{B}{B}{B}",
    colors={Color.BLACK},
    text="Creature spells you cast cost {2} less to cast.\nWhenever a creature you control enters, if you cast it, destroy that creature, then create a 2/2 black Zombie Druid creature token.",
    rarity="rare",
    supertypes={"Legendary"},
)

SIDISI_REGENT_OF_THE_MIRE = make_creature(
    name="Sidisi, Regent of the Mire",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Snake", "Warlock", "Zombie"},
    supertypes={"Legendary"},
    text="{T}, Sacrifice a creature you control with mana value X other than Sidisi: Return target creature card with mana value X plus 1 from your graveyard to the battlefield. Activate only as a sorcery.",
    rarity="rare",
)

SINKHOLE_SURVEYOR = make_creature(
    name="Sinkhole Surveyor",
    power=1, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhenever this creature attacks, you lose 1 life and this creature endures 1. (Put a +1/+1 counter on it or create a 1/1 white Spirit creature token.)",
    rarity="rare",
)

STRATEGIC_BETRAYAL = make_sorcery(
    name="Strategic Betrayal",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target opponent exiles a creature they control and their graveyard.",
    rarity="uncommon",
)

UNBURIED_EARTHCARVER = make_creature(
    name="Unburied Earthcarver",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="{2}, Sacrifice another creature: Put a +1/+1 counter on this creature.",
    rarity="common",
)

UNROOTED_ANCESTOR = make_creature(
    name="Unrooted Ancestor",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Spirit"},
    text="Flash\n{1}, Sacrifice another creature: This creature gains indestructible until end of turn. Tap it. (Damage and effects that say \"destroy\" don't destroy it.)",
    rarity="uncommon",
)

VENERATED_STORMSINGER = make_creature(
    name="Venerated Stormsinger",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Cleric", "Orc"},
    text="Mobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)\nWhenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.",
    rarity="uncommon",
)

WAIL_OF_WAR = make_instant(
    name="Wail of War",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• Creatures target opponent controls get -1/-1 until end of turn.\n• Return up to two target creature cards from your graveyard to your hand.",
    rarity="uncommon",
    resolve=wail_of_war_resolve,
)

WORTHY_COST = make_sorcery(
    name="Worthy Cost",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature.\nExile target creature or planeswalker.",
    rarity="common",
    resolve=worthy_cost_resolve,
)

YATHAN_TOMBGUARD = make_creature(
    name="Yathan Tombguard",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever a creature you control with a counter on it deals combat damage to a player, you draw a card and you lose 1 life.",
    rarity="uncommon",
)

BREACHING_DRAGONSTORM = make_enchantment(
    name="Breaching Dragonstorm",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="When this enchantment enters, exile cards from the top of your library until you exile a nonland card. You may cast it without paying its mana cost if that spell's mana value is 8 or less. If you don't, put that card into your hand.\nWhen a Dragon you control enters, return this enchantment to its owner's hand.",
    rarity="uncommon",
)

CHANNELED_DRAGONFIRE = make_sorcery(
    name="Channeled Dragonfire",
    mana_cost="{R}",
    colors={Color.RED},
    text="Channeled Dragonfire deals 2 damage to any target.\nHarmonize {5}{R}{R} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="uncommon",
    resolve=channeled_dragonfire_resolve,
)

CORISTEEL_CUTTER = make_artifact(
    name="Cori-Steel Cutter",
    mana_cost="{1}{R}",
    text="Equipped creature gets +1/+1 and has trample and haste.\nFlurry — Whenever you cast your second spell each turn, create a 1/1 white Monk creature token with prowess. You may attach this Equipment to it. (Whenever you cast a noncreature spell, the token gets +1/+1 until end of turn.)\nEquip {1}{R}",
    rarity="rare",
    subtypes={"Equipment"},
)

ACORISTEEL_CUTTER = make_artifact(
    name="A-Cori-Steel Cutter",
    mana_cost="{1}{R}",
    text="Equipped creature has haste.\nFlurry — Whenever you cast your second spell each turn, create a 1/1 white Monk creature token with prowess. You may attach this Equipment to it.\nEquip {1}{R}",
    rarity="rare",
    subtypes={"Equipment"},
)

DEVOTED_DUELIST = make_creature(
    name="Devoted Duelist",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Monk"},
    text="Haste\nFlurry — Whenever you cast your second spell each turn, this creature deals 1 damage to each opponent.",
    rarity="common",
)

DRACOGENESIS = make_enchantment(
    name="Dracogenesis",
    mana_cost="{6}{R}{R}",
    colors={Color.RED},
    text="You may cast Dragon spells without paying their mana costs.",
    rarity="mythic",
)

EQUILIBRIUM_ADEPT = make_creature(
    name="Equilibrium Adept",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Monk"},
    text="When this creature enters, exile the top card of your library. Until the end of your next turn, you may play that card.\nFlurry — Whenever you cast your second spell each turn, this creature gains double strike until end of turn.",
    rarity="uncommon",
)

FIRERIM_FORM = make_enchantment(
    name="Fire-Rim Form",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Flash\nEnchant creature\nWhen this Aura enters, enchanted creature gains first strike until end of turn.\nEnchanted creature gets +2/+0.",
    rarity="common",
    subtypes={"Aura"},
)

FLEETING_EFFIGY = make_creature(
    name="Fleeting Effigy",
    power=2, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste\nAt the beginning of your end step, return this creature to its owner's hand. (Return it only if it's on the battlefield.)\n{2}{R}: This creature gets +2/+0 until end of turn.",
    rarity="uncommon",
)

IRIDESCENT_TIGER = make_creature(
    name="Iridescent Tiger",
    power=3, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Cat"},
    text="When this creature enters, if you cast it, add {W}{U}{B}{R}{G}.",
    rarity="uncommon",
)

JESKAI_DEVOTEE = make_creature(
    name="Jeskai Devotee",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Monk", "Orc"},
    text="Flurry — Whenever you cast your second spell each turn, this creature gets +1/+1 until end of turn.\n{1}: Add {U}, {R}, or {W}. Activate only once each turn.",
    rarity="common",
)

MAGMATIC_HELLKITE = make_creature(
    name="Magmatic Hellkite",
    power=4, toughness=5,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, destroy target nonbasic land an opponent controls. Its controller searches their library for a basic land card, puts it onto the battlefield tapped with a stun counter on it, then shuffles. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
    rarity="rare",
    setup_interceptors=magmatic_hellkite_setup,
)

METICULOUS_ARTISAN = make_creature(
    name="Meticulous Artisan",
    power=3, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Artificer", "Djinn"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhen this creature enters, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    rarity="common",
)

MOLTEN_EXHALE = make_sorcery(
    name="Molten Exhale",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="You may cast this spell as though it had flash if you behold a Dragon as an additional cost to cast it. (To behold a Dragon, choose a Dragon you control or reveal a Dragon card from your hand.)\nMolten Exhale deals 4 damage to target creature or planeswalker.",
    rarity="common",
    resolve=molten_exhale_resolve,
)

NARSETS_REBUKE = make_instant(
    name="Narset's Rebuke",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Narset's Rebuke deals 5 damage to target creature. Add {U}{R}{W}. If that creature would die this turn, exile it instead.",
    rarity="common",
    resolve=narsets_rebuke_resolve,
)

OVERWHELMING_SURGE = make_instant(
    name="Overwhelming Surge",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose one or both —\n• Overwhelming Surge deals 3 damage to target creature.\n• Destroy target noncreature artifact.",
    rarity="uncommon",
    resolve=overwhelming_surge_resolve,
)

RESCUE_LEOPARD = make_creature(
    name="Rescue Leopard",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Cat"},
    text="Whenever this creature becomes tapped, you may discard a card. If you do, draw a card.",
    rarity="common",
)

REVERBERATING_SUMMONS = make_enchantment(
    name="Reverberating Summons",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="At the beginning of each combat, if you've cast two or more spells this turn, this enchantment becomes a 3/3 Monk creature with haste in addition to its other types until end of turn.\n{1}{R}, Discard your hand, Sacrifice this enchantment: Draw two cards.",
    rarity="uncommon",
)

SARKHAN_DRAGON_ASCENDANT = make_creature(
    name="Sarkhan, Dragon Ascendant",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Druid", "Human"},
    supertypes={"Legendary"},
    text="When Sarkhan enters, you may behold a Dragon. If you do, create a Treasure token. (To behold a Dragon, choose a Dragon you control or reveal a Dragon card from your hand.)\nWhenever a Dragon you control enters, put a +1/+1 counter on Sarkhan. Until end of turn, Sarkhan becomes a Dragon in addition to its other types and gains flying.",
    rarity="rare",
)

SEIZE_OPPORTUNITY = make_instant(
    name="Seize Opportunity",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose one —\n• Exile the top two cards of your library. Until the end of your next turn, you may play those cards.\n• Up to two target creatures each get +2/+1 until end of turn.",
    rarity="common",
)

SHOCK_BRIGADE = make_creature(
    name="Shock Brigade",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Soldier"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nMobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)",
    rarity="common",
)

SHOCKING_SHARPSHOOTER = make_creature(
    name="Shocking Sharpshooter",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Archer", "Human"},
    text="Reach\nWhenever another creature you control enters, this creature deals 1 damage to target opponent.",
    rarity="uncommon",
)

STADIUM_HEADLINER = make_creature(
    name="Stadium Headliner",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="Mobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)\n{1}{R}, Sacrifice this creature: It deals damage equal to the number of creatures you control to target creature.",
    rarity="rare",
)

STORMSCALE_SCION = make_creature(
    name="Stormscale Scion",
    power=4, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nOther Dragons you control get +1/+1.\nStorm (When you cast this spell, copy it for each spell cast before it this turn. Copies become tokens.)",
    rarity="mythic",
)

STORMSHRIEK_FERAL = make_creature(
    name="Stormshriek Feral",
    power=3, toughness=3,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying, haste\n{1}{R}: This creature gets +1/+0 until end of turn.\n// Adventure — Flush Out {1}{R} (Sorcery)\nDiscard a card. If you do, draw two cards. (Then shuffle this card into its owner's library.)",
    rarity="common",
)

SUMMIT_INTIMIDATOR = make_creature(
    name="Summit Intimidator",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Yeti"},
    text="Reach\nWhen this creature enters, target creature can't block this turn.",
    rarity="common",
    setup_interceptors=summit_intimidator_setup,
)

SUNSET_STRIKEMASTER = make_creature(
    name="Sunset Strikemaster",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    text="{T}: Add {R}.\n{2}{R}, {T}, Sacrifice this creature: It deals 6 damage to target creature with flying.",
    rarity="uncommon",
)

TERSA_LIGHTSHATTER = make_creature(
    name="Tersa Lightshatter",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Orc", "Wizard"},
    supertypes={"Legendary"},
    text="Haste\nWhen Tersa Lightshatter enters, discard up to two cards, then draw that many cards.\nWhenever Tersa Lightshatter attacks, if there are seven or more cards in your graveyard, exile a card at random from your graveyard. You may play that card this turn.",
    rarity="rare",
)

TWIN_BOLT = make_instant(
    name="Twin Bolt",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Twin Bolt deals 2 damage divided as you choose among one or two targets.",
    rarity="common",
    resolve=twin_bolt_resolve,
)

UNDERFOOT_UNDERDOGS = make_creature(
    name="Underfoot Underdogs",
    power=1, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
    text="When this creature enters, create a 1/1 red Goblin creature token.\n{1}, {T}: Target creature you control with power 2 or less can't be blocked this turn.",
    rarity="common",
)

UNSPARING_BOLTCASTER = make_creature(
    name="Unsparing Boltcaster",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Wizard"},
    text="When this creature enters, it deals 5 damage to target creature an opponent controls that was dealt damage this turn.",
    rarity="uncommon",
)

WAR_EFFORT = make_enchantment(
    name="War Effort",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0.\nWhenever you attack, create a 1/1 red Warrior creature token that's tapped and attacking. Sacrifice it at the beginning of the next end step.",
    rarity="uncommon",
)

WILD_RIDE = make_sorcery(
    name="Wild Ride",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains haste until end of turn.\nHarmonize {4}{R} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="common",
    resolve=wild_ride_resolve,
)

ZURGOS_VANGUARD = make_creature(
    name="Zurgo's Vanguard",
    power=0, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Soldier"},
    text="Mobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)\nZurgo's Vanguard's power is equal to the number of creatures you control.",
    rarity="uncommon",
)

AINOK_WAYFARER = make_creature(
    name="Ainok Wayfarer",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dog", "Scout"},
    text="When this creature enters, mill three cards. You may put a land card from among them into your hand. If you don't, put a +1/+1 counter on this creature. (To mill three cards, put the top three cards of your library into your graveyard.)",
    rarity="common",
)

ATTUNED_HUNTER = make_creature(
    name="Attuned Hunter",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="Trample\nWhenever one or more cards leave your graveyard during your turn, put a +1/+1 counter on this creature.",
    rarity="uncommon",
)

BLOOMVINE_REGENT = make_creature(
    name="Bloomvine Regent",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon"},
    text="Flying\nWhenever this creature or another Dragon you control enters, you gain 3 life.\n// Adventure — Claim Territory {2}{G} (Sorcery)\nSearch your library for up to two basic Forest cards, reveal them, put one onto the battlefield tapped and the other into your hand, then shuffle. (Also shuffle this card.)",
    rarity="rare",
)

CHAMPION_OF_DUSAN = make_creature(
    name="Champion of Dusan",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    text="Trample\nRenew — {1}{G}, Exile this card from your graveyard: Put a +1/+1 counter and a trample counter on target creature. Activate only as a sorcery.",
    rarity="common",
)

CRATERHOOF_BEHEMOTH = make_creature(
    name="Craterhoof Behemoth",
    power=5, toughness=5,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Haste\nWhen this creature enters, creatures you control gain trample and get +X/+X until end of turn, where X is the number of creatures you control.",
    rarity="mythic",
)

DRAGON_SNIPER = make_creature(
    name="Dragon Sniper",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Archer", "Human"},
    text="Vigilance, reach, deathtouch",
    rarity="uncommon",
)

DRAGONBROODS_RELIC = make_artifact(
    name="Dragonbroods' Relic",
    mana_cost="{1}{G}",
    text="{T}, Tap an untapped creature you control: Add one mana of any color.\n{3}{W}{U}{B}{R}{G}, Sacrifice this artifact: Create a 4/4 Dragon creature token named Reliquary Dragon that's all colors. It has flying, lifelink, and \"When this token enters, it deals 3 damage to any target.\" Activate only as a sorcery.",
    rarity="uncommon",
)

DUSYUT_EARTHCARVER = make_creature(
    name="Dusyut Earthcarver",
    power=4, toughness=4,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elephant"},
    text="Reach\nWhen this creature enters, it endures 3. (Put three +1/+1 counters on it or create a 3/3 white Spirit creature token.)",
    rarity="common",
)

ENCROACHING_DRAGONSTORM = make_enchantment(
    name="Encroaching Dragonstorm",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="When this enchantment enters, search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle.\nWhen a Dragon you control enters, return this enchantment to its owner's hand.",
    rarity="uncommon",
)

FORMATION_BREAKER = make_creature(
    name="Formation Breaker",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Creatures with power less than this creature's power can't block it.\nAs long as you control a creature with a counter on it, this creature gets +1/+2.",
    rarity="uncommon",
)

HERD_HEIRLOOM = make_artifact(
    name="Herd Heirloom",
    mana_cost="{1}{G}",
    text="{T}: Add one mana of any color. Spend this mana only to cast a creature spell.\n{T}: Until end of turn, target creature you control with power 4 or greater gains trample and \"Whenever this creature deals combat damage to a player, draw a card.\"",
    rarity="rare",
)

HERITAGE_RECLAMATION = make_instant(
    name="Heritage Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Destroy target artifact.\n• Destroy target enchantment.\n• Exile up to one target card from a graveyard. Draw a card.",
    rarity="common",
    resolve=heritage_reclamation_resolve,
)

INSPIRITED_VANGUARD = make_creature(
    name="Inspirited Vanguard",
    power=3, toughness=2,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Soldier"},
    text="Whenever this creature enters or attacks, it endures 2. (Put two +1/+1 counters on it or create a 2/2 white Spirit creature token.)",
    rarity="uncommon",
)

KNOCKOUT_MANEUVER = make_sorcery(
    name="Knockout Maneuver",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control, then it deals damage equal to its power to target creature an opponent controls.",
    rarity="uncommon",
)

KROTIQ_NESTGUARD = make_creature(
    name="Krotiq Nestguard",
    power=4, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Defender\n{2}{G}: This creature can attack this turn as though it didn't have defender.",
    rarity="common",
)

LASYD_PROWLER = make_creature(
    name="Lasyd Prowler",
    power=5, toughness=5,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Ranger", "Snake"},
    text="When this creature enters, you may mill cards equal to the number of lands you control.\nRenew — {1}{G}, Exile this card from your graveyard: Put X +1/+1 counters on target creature, where X is the number of land cards in your graveyard. Activate only as a sorcery.",
    rarity="rare",
)

NATURES_RHYTHM = make_sorcery(
    name="Nature's Rhythm",
    mana_cost="{X}{G}{G}",
    colors={Color.GREEN},
    text="Search your library for a creature card with mana value X or less, put it onto the battlefield, then shuffle.\nHarmonize {X}{G}{G}{G}{G} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by an amount of generic mana equal to its power. Then exile this spell.)",
    rarity="rare",
)

PIERCING_EXHALE = make_instant(
    name="Piercing Exhale",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="As an additional cost to cast this spell, you may behold a Dragon. (You may choose a Dragon you control or reveal a Dragon card from your hand.)\nTarget creature you control deals damage equal to its power to target creature or planeswalker. If a Dragon was beheld, surveil 2.",
    rarity="common",
)

RAINVEIL_REJUVENATOR = make_creature(
    name="Rainveil Rejuvenator",
    power=2, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Elephant"},
    text="When this creature enters, you may mill three cards. (You may put the top three cards of your library into your graveyard.)\n{T}: Add an amount of {G} equal to this creature's power.",
    rarity="uncommon",
)

RITE_OF_RENEWAL = make_sorcery(
    name="Rite of Renewal",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Return up to two target permanent cards from your graveyard to your hand. Target player shuffles up to four target cards from their graveyard into their library. Exile Rite of Renewal.",
    rarity="uncommon",
)

ROAMERS_ROUTINE = make_sorcery(
    name="Roamer's Routine",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nHarmonize {4}{G} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="common",
)

SAGE_OF_THE_FANG = make_creature(
    name="Sage of the Fang",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Human"},
    text="When this creature enters, put a +1/+1 counter on target creature.\nRenew — {3}{G}, Exile this card from your graveyard: Put a +1/+1 counter on target creature, then double the number of +1/+1 counters on that creature. Activate only as a sorcery.",
    rarity="uncommon",
    setup_interceptors=sage_of_the_fang_setup,
)

SAGU_PUMMELER = make_creature(
    name="Sagu Pummeler",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Reach\nRenew — {4}{G}, Exile this card from your graveyard: Put two +1/+1 counters and a reach counter on target creature. Activate only as a sorcery.",
    rarity="common",
)

SAGU_WILDLING = make_creature(
    name="Sagu Wildling",
    power=3, toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, you gain 3 life.\n// Adventure — Roost Seek {G} (Sorcery)\nSearch your library for a basic land card, reveal it, put it into your hand, then shuffle. (Also shuffle this card.)",
    rarity="common",
)

SARKHANS_RESOLVE = make_instant(
    name="Sarkhan's Resolve",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Target creature gets +3/+3 until end of turn.\n• Destroy target creature with flying.",
    rarity="common",
    resolve=sarkhans_resolve_resolve,
)

SNAKESKIN_VEIL = make_instant(
    name="Snakeskin Veil",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Put a +1/+1 counter on target creature you control. It gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.)",
    rarity="common",
    resolve=snakeskin_veil_resolve,
)

SULTAI_DEVOTEE = make_creature(
    name="Sultai Devotee",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Druid", "Snake", "Zombie"},
    text="Deathtouch\n{1}: Add {B}, {G}, or {U}. Activate only once each turn.",
    rarity="common",
)

SURRAK_ELUSIVE_HUNTER = make_creature(
    name="Surrak, Elusive Hunter",
    power=4, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="This spell can't be countered.\nTrample\nWhenever a creature you control or a creature spell you control becomes the target of a spell or ability an opponent controls, draw a card.",
    rarity="rare",
)

SYNCHRONIZED_CHARGE = make_sorcery(
    name="Synchronized Charge",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Distribute two +1/+1 counters among one or two target creatures you control. Creatures you control with counters on them gain vigilance and trample until end of turn.\nHarmonize {4}{G} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="uncommon",
)

TRADE_ROUTE_ENVOY = make_creature(
    name="Trade Route Envoy",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Dog", "Soldier"},
    text="When this creature enters, draw a card if you control a creature with a counter on it. If you don't draw a card this way, put a +1/+1 counter on this creature.",
    rarity="common",
)

TRAVELING_BOTANIST = make_creature(
    name="Traveling Botanist",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dog", "Scout"},
    text="Whenever this creature becomes tapped, look at the top card of your library. If it's a land card, you may reveal it and put it into your hand. If you don't put the card into your hand, you may put it into your graveyard.",
    rarity="uncommon",
)

UNDERGROWTH_LEOPARD = make_creature(
    name="Undergrowth Leopard",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Cat"},
    text="Vigilance\n{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
    rarity="common",
)

WARDEN_OF_THE_GROVE = make_creature(
    name="Warden of the Grove",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Hydra"},
    text="At the beginning of your end step, put a +1/+1 counter on this creature.\nWhenever another nontoken creature you control enters, it endures X, where X is the number of counters on this creature. (Put X +1/+1 counters on the creature that entered or create an X/X white Spirit creature token.)",
    rarity="rare",
)

ALLOUT_ASSAULT = make_enchantment(
    name="All-Out Assault",
    mana_cost="{2}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="Creatures you control get +1/+1 and have deathtouch.\nWhen this enchantment enters, if it's your main phase, there is an additional combat phase after this phase followed by an additional main phase. When you next attack this turn, untap each creature you control.",
    rarity="mythic",
)

ARMAMENT_DRAGON = make_creature(
    name="Armament Dragon",
    power=3, toughness=4,
    mana_cost="{3}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, distribute three +1/+1 counters among one, two, or three target creatures you control.",
    rarity="uncommon",
)

AURORAL_PROCESSION = make_instant(
    name="Auroral Procession",
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    text="Return target card from your graveyard to your hand.",
    rarity="uncommon",
    resolve=auroral_procession_resolve,
)

AWAKEN_THE_HONORED_DEAD = make_enchantment(
    name="Awaken the Honored Dead",
    mana_cost="{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Destroy target nonland permanent.\nII — Mill three cards.\nIII — You may discard a card. When you do, return target creature or land card from your graveyard to your hand.",
    rarity="rare",
    subtypes={"Saga"},
)

BARRENSTEPPE_SIEGE = make_enchantment(
    name="Barrensteppe Siege",
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    text="As this enchantment enters, choose Abzan or Mardu.\n• Abzan — At the beginning of your end step, put a +1/+1 counter on each creature you control.\n• Mardu — At the beginning of your end step, if a creature died under your control this turn, each opponent sacrifices a creature of their choice.",
    rarity="rare",
)

BETOR_KIN_TO_ALL = make_creature(
    name="Betor, Kin to All",
    power=5, toughness=7,
    mana_cost="{2}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Dragon", "Spirit"},
    supertypes={"Legendary"},
    text="Flying\nAt the beginning of your end step, if creatures you control have total toughness 10 or greater, draw a card. Then if creatures you control have total toughness 20 or greater, untap each creature you control. Then if creatures you control have total toughness 40 or greater, each opponent loses half their life, rounded up.",
    rarity="mythic",
)

BONECAIRN_BUTCHER = make_creature(
    name="Bone-Cairn Butcher",
    power=4, toughness=4,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Demon"},
    text="Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)\nAttacking tokens you control have deathtouch.",
    rarity="uncommon",
)

CALL_THE_SPIRIT_DRAGONS = make_enchantment(
    name="Call the Spirit Dragons",
    mana_cost="{W}{U}{B}{R}{G}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN, Color.RED, Color.WHITE},
    text="Dragons you control have indestructible.\nAt the beginning of your upkeep, for each color, put a +1/+1 counter on a Dragon you control of that color. If you put +1/+1 counters on five Dragons this way, you win the game.",
    rarity="mythic",
)

CORI_MOUNTAIN_STALWART = make_creature(
    name="Cori Mountain Stalwart",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Monk"},
    text="Flurry — Whenever you cast your second spell each turn, this creature deals 2 damage to each opponent and you gain 2 life.",
    rarity="uncommon",
)

DEATH_BEGETS_LIFE = make_sorcery(
    name="Death Begets Life",
    mana_cost="{5}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    text="Destroy all creatures and enchantments. Draw a card for each permanent destroyed this way.",
    rarity="mythic",
)

DEFIBRILLATING_CURRENT = make_sorcery(
    name="Defibrillating Current",
    mana_cost="{2/R}{2/W}{2/B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="Defibrillating Current deals 4 damage to target creature or planeswalker and you gain 2 life.",
    rarity="uncommon",
    resolve=defibrillating_current_resolve,
)

DISRUPTIVE_STORMBROOD = make_creature(
    name="Disruptive Stormbrood",
    power=3, toughness=3,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, destroy up to one target artifact or enchantment.\n// Adventure — Petty Revenge {1}{B} (Sorcery)\nDestroy target creature with power 3 or less. (Then shuffle this card into its owner's library.)",
    rarity="uncommon",
    setup_interceptors=disruptive_stormbrood_setup,
)

DRAGONBACK_ASSAULT = make_enchantment(
    name="Dragonback Assault",
    mana_cost="{3}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    text="When this enchantment enters, it deals 3 damage to each creature and each planeswalker.\nLandfall — Whenever a land you control enters, create a 4/4 red Dragon creature token with flying.",
    rarity="mythic",
)

DRAGONCLAW_STRIKE = make_sorcery(
    name="Dragonclaw Strike",
    mana_cost="{2/G}{2/U}{2/R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    text="Double the power and toughness of target creature you control until end of turn. Then it fights up to one target creature an opponent controls. (Each deals damage equal to its power to the other.)",
    rarity="uncommon",
)

EFFORTLESS_MASTER = make_creature(
    name="Effortless Master",
    power=4, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Monk", "Orc"},
    text="Vigilance\nMenace (This creature can't be blocked except by two or more creatures.)\nThis creature enters with two +1/+1 counters on it if you've cast two or more spells this turn.",
    rarity="uncommon",
)

ESHKI_DRAGONCLAW = make_creature(
    name="Eshki Dragonclaw",
    power=4, toughness=4,
    mana_cost="{1}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance, trample, ward {1}\nAt the beginning of combat on your turn, if you've cast both a creature spell and a noncreature spell this turn, draw a card and put two +1/+1 counters on Eshki Dragonclaw.",
    rarity="rare",
)

FANGKEEPERS_FAMILIAR = make_creature(
    name="Fangkeeper's Familiar",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Snake"},
    text="Flash\nWhen this creature enters, choose one —\n• You gain 3 life and surveil 3. (Look at the top three cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)\n• Destroy target enchantment.\n• Counter target creature spell.",
    rarity="rare",
)

FELOTHAR_DAWN_OF_THE_ABZAN = make_creature(
    name="Felothar, Dawn of the Abzan",
    power=3, toughness=3,
    mana_cost="{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Trample\nWhenever Felothar enters or attacks, you may sacrifice a nonland permanent. When you do, put a +1/+1 counter on each creature you control.",
    rarity="rare",
)

FLAMEHOLD_GRAPPLER = make_creature(
    name="Flamehold Grappler",
    power=3, toughness=3,
    mana_cost="{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Human", "Monk"},
    text="First strike\nWhen this creature enters, copy the next spell you cast this turn when you cast it. You may choose new targets for the copy. (A copy of a permanent spell becomes a token.)",
    rarity="rare",
)

FRONTLINE_RUSH = make_instant(
    name="Frontline Rush",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Choose one —\n• Create two 1/1 red Goblin creature tokens.\n• Target creature gets +X/+X until end of turn, where X is the number of creatures you control.",
    rarity="uncommon",
)

FROSTCLIFF_SIEGE = make_enchantment(
    name="Frostcliff Siege",
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="As this enchantment enters, choose Jeskai or Temur.\n• Jeskai — Whenever one or more creatures you control deal combat damage to a player, draw a card.\n• Temur — Creatures you control get +1/+0 and have trample and haste.",
    rarity="rare",
)

GLACIAL_DRAGONHUNT = make_sorcery(
    name="Glacial Dragonhunt",
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Draw a card, then you may discard a card. When you discard a nonland card this way, Glacial Dragonhunt deals 3 damage to target creature.\nHarmonize {4}{U}{R} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="uncommon",
)

GLACIERWOOD_SIEGE = make_enchantment(
    name="Glacierwood Siege",
    mana_cost="{1}{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    text="As this enchantment enters, choose Temur or Sultai.\n• Temur — Whenever you cast an instant or sorcery spell, target player mills four cards.\n• Sultai — You may play lands from your graveyard.",
    rarity="rare",
)

GURMAG_NIGHTWATCH = make_creature(
    name="Gurmag Nightwatch",
    power=3, toughness=3,
    mana_cost="{2/B}{2/G}{2/U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="When this creature enters, look at the top three cards of your library. You may put one of those cards back on top of your library. Put the rest into your graveyard.",
    rarity="common",
)

HARDENED_TACTICIAN = make_creature(
    name="Hardened Tactician",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="{1}, Sacrifice a token: Draw a card.",
    rarity="uncommon",
)

HOLLOWMURK_SIEGE = make_enchantment(
    name="Hollowmurk Siege",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="As this enchantment enters, choose Sultai or Abzan.\n• Sultai — Whenever a counter is put on a creature you control, draw a card. This ability triggers only once each turn.\n• Abzan — Whenever you attack, put a +1/+1 counter on target attacking creature. It gains menace until end of turn.",
    rarity="rare",
)

HOST_OF_THE_HEREAFTER = make_creature(
    name="Host of the Hereafter",
    power=2, toughness=2,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Warlock", "Zombie"},
    text="This creature enters with two +1/+1 counters on it.\nWhenever this creature or another creature you control dies, if it had counters on it, put its counters on up to one target creature you control.",
    rarity="uncommon",
)

INEVITABLE_DEFEAT = make_instant(
    name="Inevitable Defeat",
    mana_cost="{1}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="This spell can't be countered.\nExile target nonland permanent. Its controller loses 3 life and you gain 3 life.",
    rarity="rare",
    resolve=inevitable_defeat_resolve,
)

JESKAI_BRUSHMASTER = make_creature(
    name="Jeskai Brushmaster",
    power=2, toughness=4,
    mana_cost="{1}{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Monk", "Orc"},
    text="Double strike\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
    rarity="uncommon",
)

JESKAI_REVELATION = make_instant(
    name="Jeskai Revelation",
    mana_cost="{4}{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    text="Return target spell or permanent to its owner's hand. Jeskai Revelation deals 4 damage to any target. Create two 1/1 white Monk creature tokens with prowess. Draw two cards. You gain 4 life.",
    rarity="mythic",
)

JESKAI_SHRINEKEEPER = make_creature(
    name="Jeskai Shrinekeeper",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Dragon"},
    text="Flying, haste\nWhenever this creature deals combat damage to a player, you gain 1 life and draw a card.",
    rarity="uncommon",
)

KARAKYK_GUARDIAN = make_creature(
    name="Karakyk Guardian",
    power=6, toughness=5,
    mana_cost="{3}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Dragon"},
    text="Flying, vigilance, trample\nThis creature has hexproof if it hasn't dealt damage yet. (It can't be the target of spells or abilities your opponents control.)",
    rarity="uncommon",
)

KHERU_GOLDKEEPER = make_creature(
    name="Kheru Goldkeeper",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Dragon"},
    text="Flying\nWhenever one or more cards leave your graveyard during your turn, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\nRenew — {2}{B}{G}{U}, Exile this card from your graveyard: Put two +1/+1 counters and a flying counter on target creature. Activate only as a sorcery.",
    rarity="uncommon",
)

KINTREE_SEVERANCE = make_instant(
    name="Kin-Tree Severance",
    mana_cost="{2/W}{2/B}{2/G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    text="Exile target permanent with mana value 3 or greater.",
    rarity="uncommon",
    resolve=kintree_severance_resolve,
)

KISHLA_SKIMMER = make_creature(
    name="Kishla Skimmer",
    power=2, toughness=2,
    mana_cost="{G}{U}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Bird", "Scout"},
    text="Flying\nWhenever a card leaves your graveyard during your turn, draw a card. This ability triggers only once each turn.",
    rarity="uncommon",
)

KOTIS_THE_FANGKEEPER = make_creature(
    name="Kotis, the Fangkeeper",
    power=2, toughness=1,
    mana_cost="{1}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Warrior", "Zombie"},
    supertypes={"Legendary"},
    text="Indestructible\nWhenever Kotis deals combat damage to a player, exile the top X cards of their library, where X is the amount of damage dealt. You may cast any number of spells with mana value X or less from among them without paying their mana costs.",
    rarity="rare",
)

LIE_IN_WAIT = make_sorcery(
    name="Lie in Wait",
    mana_cost="{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    text="Return target creature card from your graveyard to your hand. Lie in Wait deals damage equal to that card's power to target creature.",
    rarity="uncommon",
)

LOTUSLIGHT_DANCERS = make_creature(
    name="Lotuslight Dancers",
    power=3, toughness=6,
    mana_cost="{2}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Bard", "Zombie"},
    text="Lifelink\nWhen this creature enters, search your library for a black card, a green card, and a blue card. Put those cards into your graveyard, then shuffle.",
    rarity="rare",
)

MAMMOTH_BELLOW = make_sorcery(
    name="Mammoth Bellow",
    mana_cost="{2}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    text="Create a 5/5 green Elephant creature token.\nHarmonize {5}{G}{U}{R} (You may cast this card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile this spell.)",
    rarity="uncommon",
)

MARDU_SIEGEBREAKER = make_creature(
    name="Mardu Siegebreaker",
    power=4, toughness=4,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="Deathtouch, haste\nWhen this creature enters, exile up to one other target creature you control until this creature leaves the battlefield.\nWhenever this creature attacks, for each opponent, create a tapped token that's a copy of the exiled card attacking that opponent. At the beginning of your next end step, sacrifice those tokens.",
    rarity="rare",
)

MARSHAL_OF_THE_LOST = make_creature(
    name="Marshal of the Lost",
    power=3, toughness=3,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Orc", "Warrior"},
    text="Deathtouch\nWhenever you attack, target creature gets +X/+X until end of turn, where X is the number of attacking creatures.",
    rarity="uncommon",
)

MONASTERY_MESSENGER = make_creature(
    name="Monastery Messenger",
    power=2, toughness=3,
    mana_cost="{2/U}{2/R}{2/W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Bird", "Scout"},
    text="Flying, vigilance\nWhen this creature enters, put up to one target noncreature, nonland card from your graveyard on top of your library.",
    rarity="common",
)

NARSET_JESKAI_WAYMASTER = make_creature(
    name="Narset, Jeskai Waymaster",
    power=3, toughness=4,
    mana_cost="{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, you may discard your hand. If you do, draw cards equal to the number of spells you've cast this turn.",
    rarity="rare",
)

NERIV_HEART_OF_THE_STORM = make_creature(
    name="Neriv, Heart of the Storm",
    power=4, toughness=5,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Dragon", "Spirit"},
    supertypes={"Legendary"},
    text="Flying\nIf a creature you control that entered this turn would deal damage, it deals twice that much damage instead.",
    rarity="mythic",
)

NEW_WAY_FORWARD = make_instant(
    name="New Way Forward",
    mana_cost="{2}{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    text="The next time a source of your choice would deal damage to you this turn, prevent that damage. When damage is prevented this way, New Way Forward deals that much damage to that source's controller and you draw that many cards.",
    rarity="rare",
)

PERENNATION = make_sorcery(
    name="Perennation",
    mana_cost="{3}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    text="Return target permanent card from your graveyard to the battlefield with a hexproof counter and an indestructible counter on it.",
    rarity="mythic",
    resolve=perennation_resolve,
)

PURGING_STORMBROOD = make_creature(
    name="Purging Stormbrood",
    power=4, toughness=4,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Dragon"},
    text="Flying\nWard—Pay 2 life.\nWhen this creature enters, remove all counters from up to one target creature.\n// Adventure — Absorb Essence {1}{W} (Instant)\nTarget creature gets +2/+2 and gains lifelink and hexproof until end of turn. (Then shuffle this card into its owner's library.)",
    rarity="uncommon",
)

RAKSHASAS_BARGAIN = make_instant(
    name="Rakshasa's Bargain",
    mana_cost="{2/B}{2/G}{2/U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    text="Look at the top four cards of your library. Put two of them into your hand and the rest into your graveyard.",
    rarity="uncommon",
)

REDISCOVER_THE_WAY = make_enchantment(
    name="Rediscover the Way",
    mana_cost="{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Look at the top three cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order.\nIII — Whenever you cast a noncreature spell this turn, target creature you control gains double strike until end of turn.",
    rarity="rare",
    subtypes={"Saga"},
)

REIGNING_VICTOR = make_creature(
    name="Reigning Victor",
    power=3, toughness=3,
    mana_cost="{2/R}{2/W}{2/B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Orc", "Warrior"},
    text="Mobilize 1 (Whenever this creature attacks, create a tapped and attacking 1/1 red Warrior creature token. Sacrifice it at the beginning of the next end step.)\nWhen this creature enters, target creature gets +1/+0 and gains indestructible until end of turn. (Damage and effects that say \"destroy\" don't destroy it.)",
    rarity="common",
    setup_interceptors=reigning_victor_setup,
)

REPUTABLE_MERCHANT = make_creature(
    name="Reputable Merchant",
    power=2, toughness=2,
    mana_cost="{2/W}{2/B}{2/G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Citizen", "Human"},
    text="When this creature enters or dies, put a +1/+1 counter on target creature you control.",
    rarity="common",
    setup_interceptors=reputable_merchant_setup,
)

REVIVAL_OF_THE_ANCESTORS = make_enchantment(
    name="Revival of the Ancestors",
    mana_cost="{1}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Create three 1/1 white Spirit creature tokens.\nII — Distribute three +1/+1 counters among one, two, or three target creatures you control.\nIII — Creatures you control gain trample and lifelink until end of turn.",
    rarity="rare",
    subtypes={"Saga"},
)

RIVERWHEEL_SWEEP = make_sorcery(
    name="Riverwheel Sweep",
    mana_cost="{2/U}{2/R}{2/W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    text="Tap target creature. Put three stun counters on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nExile the top two cards of your library. Choose one of them. Until the end of your next turn, you may play that card.",
    rarity="uncommon",
)

ROAR_OF_ENDLESS_SONG = make_enchantment(
    name="Roar of Endless Song",
    mana_cost="{2}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Create a 5/5 green Elephant creature token.\nIII — Double the power and toughness of each creature you control until end of turn.",
    rarity="rare",
    subtypes={"Saga"},
)

RUNESCALE_STORMBROOD = make_creature(
    name="Runescale Stormbrood",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    text="Flying\nWhenever you cast a noncreature spell or a Dragon spell, this creature gets +2/+0 until end of turn.\n// Adventure — Chilling Screech {1}{U} (Instant)\nCounter target spell with mana value 2 or less. (Then shuffle this card into its owner's library.)",
    rarity="uncommon",
)

SEVERANCE_PRIEST = make_creature(
    name="Severance Priest",
    power=3, toughness=3,
    mana_cost="{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Cleric", "Djinn"},
    text="Deathtouch\nWhen this creature enters, target opponent reveals their hand. You may choose a nonland card from it. If you do, exile that card.\nWhen this creature leaves the battlefield, the exiled card's owner creates an X/X white Spirit creature token, where X is the mana value of the exiled card.",
    rarity="rare",
)

SHIKO_PARAGON_OF_THE_WAY = make_creature(
    name="Shiko, Paragon of the Way",
    power=4, toughness=5,
    mana_cost="{2}{U}{R}{W}",
    colors={Color.BLUE, Color.RED, Color.WHITE},
    subtypes={"Dragon", "Spirit"},
    supertypes={"Legendary"},
    text="Flying, vigilance\nWhen Shiko enters, exile target nonland card with mana value 3 or less from your graveyard. Copy it, then you may cast the copy without paying its mana cost. (A copy of a permanent spell becomes a token.)",
    rarity="mythic",
)

SKIRMISH_RHINO = make_creature(
    name="Skirmish Rhino",
    power=3, toughness=4,
    mana_cost="{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Rhino"},
    text="Trample\nWhen this creature enters, each opponent loses 2 life and you gain 2 life.",
    rarity="uncommon",
)

SONGCRAFTER_MAGE = make_creature(
    name="Songcrafter Mage",
    power=3, toughness=2,
    mana_cost="{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Bard", "Human"},
    text="Flash\nWhen this creature enters, target instant or sorcery card in your graveyard gains harmonize until end of turn. Its harmonize cost is equal to its mana cost. (You may cast that card from your graveyard for its harmonize cost. You may tap a creature you control to reduce that cost by {X}, where X is its power. Then exile the spell.)",
    rarity="rare",
)

SONIC_SHRIEKER = make_creature(
    name="Sonic Shrieker",
    power=4, toughness=4,
    mana_cost="{2}{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, it deals 2 damage to any target and you gain 2 life. If a player is dealt damage this way, they discard a card.",
    rarity="uncommon",
    setup_interceptors=sonic_shrieker_setup,
)

STALWART_SUCCESSOR = make_creature(
    name="Stalwart Successor",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warrior"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever one or more counters are put on a creature you control, if it's the first time counters have been put on that creature this turn, put a +1/+1 counter on that creature.",
    rarity="uncommon",
)

TEMUR_BATTLECRIER = make_creature(
    name="Temur Battlecrier",
    power=4, toughness=3,
    mana_cost="{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Orc", "Ranger"},
    text="During your turn, spells you cast cost {1} less to cast for each creature you control with power 4 or greater.",
    rarity="rare",
)

TEMUR_TAWNYBACK = make_creature(
    name="Temur Tawnyback",
    power=4, toughness=3,
    mana_cost="{2/G}{2/U}{2/R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Beast"},
    text="When this creature enters, draw a card, then discard a card.",
    rarity="common",
)

TEVAL_ARBITER_OF_VIRTUE = make_creature(
    name="Teval, Arbiter of Virtue",
    power=6, toughness=6,
    mana_cost="{2}{B}{G}{U}",
    colors={Color.BLACK, Color.BLUE, Color.GREEN},
    subtypes={"Dragon", "Spirit"},
    supertypes={"Legendary"},
    text="Flying, lifelink\nSpells you cast have delve. (Each card you exile from your graveyard while casting those spells pays for {1}.)\nWhenever you cast a spell, you lose life equal to its mana value.",
    rarity="mythic",
)

THUNDER_OF_UNITY = make_enchantment(
    name="Thunder of Unity",
    mana_cost="{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — You draw two cards and you lose 2 life.\nII, III — Whenever a creature you control enters this turn, each opponent loses 1 life and you gain 1 life.",
    rarity="rare",
    subtypes={"Saga"},
)

TWINMAW_STORMBROOD = make_creature(
    name="Twinmaw Stormbrood",
    power=5, toughness=4,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Dragon"},
    text="Flying\nWhen this creature enters, you gain 5 life.\n// Adventure — Charring Bite {1}{R} (Sorcery)\nCharring Bite deals 5 damage to target creature without flying. (Then shuffle this card into its owner's library.)",
    rarity="uncommon",
)

URENI_THE_SONG_UNENDING = make_creature(
    name="Ureni, the Song Unending",
    power=10, toughness=10,
    mana_cost="{5}{G}{U}{R}",
    colors={Color.BLUE, Color.GREEN, Color.RED},
    subtypes={"Dragon", "Spirit"},
    supertypes={"Legendary"},
    text="Flying, protection from white and from black\nWhen Ureni enters, it deals X damage divided as you choose among any number of target creatures and/or planeswalkers your opponents control, where X is the number of lands you control.",
    rarity="mythic",
)

WHIRLWING_STORMBROOD = make_creature(
    name="Whirlwing Stormbrood",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Dragon"},
    text="Flash\nFlying\nYou may cast sorcery spells and Dragon spells as though they had flash.\n// Adventure — Dynamic Soar {2}{G} (Sorcery)\nPut three +1/+1 counters on target creature you control. (Then shuffle this card into its owner's library.)",
    rarity="uncommon",
)

WINDCRAG_SIEGE = make_enchantment(
    name="Windcrag Siege",
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="As this enchantment enters, choose Mardu or Jeskai.\n• Mardu — If a creature attacking causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.\n• Jeskai — At the beginning of your upkeep, create a 1/1 red Goblin creature token. It gains lifelink and haste until end of turn.",
    rarity="rare",
)

YATHAN_ROADWATCHER = make_creature(
    name="Yathan Roadwatcher",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}{G}",
    colors={Color.BLACK, Color.GREEN, Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When this creature enters, if you cast it, mill four cards. When you do, return target creature card with mana value 3 or less from your graveyard to the battlefield.",
    rarity="rare",
)

ZURGO_THUNDERS_DECREE = make_creature(
    name="Zurgo, Thunder's Decree",
    power=2, toughness=4,
    mana_cost="{R}{W}{B}",
    colors={Color.BLACK, Color.RED, Color.WHITE},
    subtypes={"Orc", "Warrior"},
    supertypes={"Legendary"},
    text="Mobilize 2 (Whenever this creature attacks, create two tapped and attacking 1/1 red Warrior creature tokens. Sacrifice them at the beginning of the next end step.)\nDuring your end step, Warrior tokens you control have \"This token can't be sacrificed.\"",
    rarity="rare",
)

ABZAN_MONUMENT = make_artifact(
    name="Abzan Monument",
    mana_cost="{2}",
    text="When this artifact enters, search your library for a basic Plains, Swamp, or Forest card, reveal it, put it into your hand, then shuffle.\n{1}{W}{B}{G}, {T}, Sacrifice this artifact: Create an X/X white Spirit creature token, where X is the greatest toughness among creatures you control. Activate only as a sorcery.",
    rarity="uncommon",
)

BOULDERBORN_DRAGON = make_artifact_creature(
    name="Boulderborn Dragon",
    power=3, toughness=3,
    mana_cost="{5}",
    colors=set(),
    subtypes={"Dragon"},
    text="Flying, vigilance\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    rarity="common",
)

DRAGONFIRE_BLADE = make_artifact(
    name="Dragonfire Blade",
    mana_cost="{1}",
    text="Equipped creature gets +2/+2 and has hexproof from monocolored.\nEquip {4}. This ability costs {1} less to activate for each color of the creature it targets.",
    rarity="rare",
    subtypes={"Equipment"},
)

DRAGONSTORM_GLOBE = make_artifact(
    name="Dragonstorm Globe",
    mana_cost="{3}",
    text="Each Dragon you control enters with an additional +1/+1 counter on it.\n{T}: Add one mana of any color.",
    rarity="common",
)

EMBERMOUTH_SENTINEL = make_artifact_creature(
    name="Embermouth Sentinel",
    power=2, toughness=1,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Chimera"},
    text="When this creature enters, you may search your library for a basic land card, reveal it, then shuffle and put that card on top. If you control a Dragon, put that card onto the battlefield tapped instead.",
    rarity="common",
)

JADECAST_SENTINEL = make_artifact_creature(
    name="Jade-Cast Sentinel",
    power=1, toughness=5,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Ape", "Snake"},
    text="Reach\n{2}, {T}: Put target card from a graveyard on the bottom of its owner's library.",
    rarity="common",
)

JESKAI_MONUMENT = make_artifact(
    name="Jeskai Monument",
    mana_cost="{2}",
    text="When this artifact enters, search your library for a basic Island, Mountain, or Plains card, reveal it, put it into your hand, then shuffle.\n{1}{U}{R}{W}, {T}, Sacrifice this artifact: Create two 1/1 white Bird creature tokens with flying. Activate only as a sorcery.",
    rarity="uncommon",
)

MARDU_MONUMENT = make_artifact(
    name="Mardu Monument",
    mana_cost="{2}",
    text="When this artifact enters, search your library for a basic Mountain, Plains, or Swamp card, reveal it, put it into your hand, then shuffle.\n{2}{R}{W}{B}, {T}, Sacrifice this artifact: Create three 1/1 red Warrior creature tokens. They gain menace and haste until end of turn. Activate only as a sorcery. (A creature with menace can't be blocked except by two or more creatures.)",
    rarity="uncommon",
)

MOX_JASPER = make_artifact(
    name="Mox Jasper",
    mana_cost="{0}",
    text="{T}: Add one mana of any color. Activate only if you control a Dragon.",
    rarity="mythic",
    supertypes={"Legendary"},
)

SULTAI_MONUMENT = make_artifact(
    name="Sultai Monument",
    mana_cost="{2}",
    text="When this artifact enters, search your library for a basic Swamp, Forest, or Island card, reveal it, put it into your hand, then shuffle.\n{2}{B}{G}{U}, {T}, Sacrifice this artifact: Create two 2/2 black Zombie Druid creature tokens. Activate only as a sorcery.",
    rarity="uncommon",
)

TEMUR_MONUMENT = make_artifact(
    name="Temur Monument",
    mana_cost="{2}",
    text="When this artifact enters, search your library for a basic Forest, Island, or Mountain card, reveal it, put it into your hand, then shuffle.\n{3}{G}{U}{R}, {T}, Sacrifice this artifact: Create a 5/5 green Elephant creature token. Activate only as a sorcery.",
    rarity="uncommon",
)

WATCHER_OF_THE_WAYSIDE = make_artifact_creature(
    name="Watcher of the Wayside",
    power=3, toughness=2,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Golem"},
    text="When this creature enters, target player mills two cards. You gain 2 life. (To mill two cards, a player puts the top two cards of their library into their graveyard.)",
    rarity="common",
    setup_interceptors=watcher_of_the_wayside_setup,
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

CORI_MOUNTAIN_MONASTERY = make_land(
    name="Cori Mountain Monastery",
    text="This land enters tapped unless you control a Plains or an Island.\n{T}: Add {R}.\n{3}{R}, {T}: Exile the top card of your library. Until the end of your next turn, you may play that card.",
    rarity="rare",
)

DALKOVAN_ENCAMPMENT = make_land(
    name="Dalkovan Encampment",
    text="This land enters tapped unless you control a Swamp or a Mountain.\n{T}: Add {W}.\n{2}{W}, {T}: Whenever you attack this turn, create two 1/1 red Warrior creature tokens that are tapped and attacking. Sacrifice them at the beginning of the next end step.",
    rarity="rare",
)

DISMAL_BACKWATER = make_land(
    name="Dismal Backwater",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {U} or {B}.",
    rarity="common",
)

EVOLVING_WILDS = make_land(
    name="Evolving Wilds",
    text="{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
    rarity="common",
)

FRONTIER_BIVOUAC = make_land(
    name="Frontier Bivouac",
    text="This land enters tapped.\n{T}: Add {G}, {U}, or {R}.",
    rarity="uncommon",
)

GREAT_ARASHIN_CITY = make_land(
    name="Great Arashin City",
    text="This land enters tapped unless you control a Forest or a Plains.\n{T}: Add {B}.\n{1}{B}, {T}, Exile a creature card from your graveyard: Create a 1/1 white Spirit creature token.",
    rarity="rare",
)

JUNGLE_HOLLOW = make_land(
    name="Jungle Hollow",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {B} or {G}.",
    rarity="common",
)

KISHLA_VILLAGE = make_land(
    name="Kishla Village",
    text="This land enters tapped unless you control an Island or a Swamp.\n{T}: Add {G}.\n{3}{G}, {T}: Surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    rarity="rare",
)

MAELSTROM_OF_THE_SPIRIT_DRAGON = make_land(
    name="Maelstrom of the Spirit Dragon",
    text="{T}: Add {C}.\n{T}: Add one mana of any color. Spend this mana only to cast a Dragon spell or an Omen spell.\n{4}, {T}, Sacrifice this land: Search your library for a Dragon card, reveal it, put it into your hand, then shuffle.",
    rarity="rare",
)

MISTRISE_VILLAGE = make_land(
    name="Mistrise Village",
    text="This land enters tapped unless you control a Mountain or a Forest.\n{T}: Add {U}.\n{U}, {T}: The next spell you cast this turn can't be countered.",
    rarity="rare",
)

MYSTIC_MONASTERY = make_land(
    name="Mystic Monastery",
    text="This land enters tapped.\n{T}: Add {U}, {R}, or {W}.",
    rarity="uncommon",
)

NOMAD_OUTPOST = make_land(
    name="Nomad Outpost",
    text="This land enters tapped.\n{T}: Add {R}, {W}, or {B}.",
    rarity="uncommon",
)

OPULENT_PALACE = make_land(
    name="Opulent Palace",
    text="This land enters tapped.\n{T}: Add {B}, {G}, or {U}.",
    rarity="uncommon",
)

RUGGED_HIGHLANDS = make_land(
    name="Rugged Highlands",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {R} or {G}.",
    rarity="common",
)

SANDSTEPPE_CITADEL = make_land(
    name="Sandsteppe Citadel",
    text="This land enters tapped.\n{T}: Add {W}, {B}, or {G}.",
    rarity="uncommon",
)

SCOURED_BARRENS = make_land(
    name="Scoured Barrens",
    text="This land enters tapped.\nWhen this land enters, you gain 1 life.\n{T}: Add {W} or {B}.",
    rarity="common",
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

TARKIR_DRAGONSTORM_CARDS = {
    "Ugin, Eye of the Storms": UGIN_EYE_OF_THE_STORMS,
    "Anafenza, Unyielding Lineage": ANAFENZA_UNYIELDING_LINEAGE,
    "Arashin Sunshield": ARASHIN_SUNSHIELD,
    "Bearer of Glory": BEARER_OF_GLORY,
    "Clarion Conqueror": CLARION_CONQUEROR,
    "Coordinated Maneuver": COORDINATED_MANEUVER,
    "Dalkovan Packbeasts": DALKOVAN_PACKBEASTS,
    "Descendant of Storms": DESCENDANT_OF_STORMS,
    "Dragonback Lancer": DRAGONBACK_LANCER,
    "Duty Beyond Death": DUTY_BEYOND_DEATH,
    "Elspeth, Storm Slayer": ELSPETH_STORM_SLAYER,
    "Fortress Kin-Guard": FORTRESS_KINGUARD,
    "Furious Forebear": FURIOUS_FOREBEAR,
    "Lightfoot Technique": LIGHTFOOT_TECHNIQUE,
    "Loxodon Battle Priest": LOXODON_BATTLE_PRIEST,
    "Mardu Devotee": MARDU_DEVOTEE,
    "Osseous Exhale": OSSEOUS_EXHALE,
    "Poised Practitioner": POISED_PRACTITIONER,
    "Rally the Monastery": RALLY_THE_MONASTERY,
    "Rebellious Strike": REBELLIOUS_STRIKE,
    "Riling Dawnbreaker": RILING_DAWNBREAKER,
    "Sage of the Skies": SAGE_OF_THE_SKIES,
    "Salt Road Packbeast": SALT_ROAD_PACKBEAST,
    "Smile at Death": SMILE_AT_DEATH,
    "Starry-Eyed Skyrider": STARRYEYED_SKYRIDER,
    "Static Snare": STATIC_SNARE,
    "Stormbeacon Blade": STORMBEACON_BLADE,
    "Stormplain Detainment": STORMPLAIN_DETAINMENT,
    "Sunpearl Kirin": SUNPEARL_KIRIN,
    "Teeming Dragonstorm": TEEMING_DRAGONSTORM,
    "Tempest Hawk": TEMPEST_HAWK,
    "United Battlefront": UNITED_BATTLEFRONT,
    "Voice of Victory": VOICE_OF_VICTORY,
    "Wayspeaker Bodyguard": WAYSPEAKER_BODYGUARD,
    "Aegis Sculptor": AEGIS_SCULPTOR,
    "Agent of Kotis": AGENT_OF_KOTIS,
    "Ambling Stormshell": AMBLING_STORMSHELL,
    "Bewildering Blizzard": BEWILDERING_BLIZZARD,
    "Constrictor Sage": CONSTRICTOR_SAGE,
    "Dirgur Island Dragon": DIRGUR_ISLAND_DRAGON,
    "Dispelling Exhale": DISPELLING_EXHALE,
    "Dragonologist": DRAGONOLOGIST,
    "Dragonstorm Forecaster": DRAGONSTORM_FORECASTER,
    "Essence Anchor": ESSENCE_ANCHOR,
    "Focus the Mind": FOCUS_THE_MIND,
    "Fresh Start": FRESH_START,
    "Highspire Bell-Ringer": HIGHSPIRE_BELLRINGER,
    "Humbling Elder": HUMBLING_ELDER,
    "Iceridge Serpent": ICERIDGE_SERPENT,
    "Kishla Trawlers": KISHLA_TRAWLERS,
    "Marang River Regent": MARANG_RIVER_REGENT,
    "Naga Fleshcrafter": NAGA_FLESHCRAFTER,
    "Ringing Strike Mastery": RINGING_STRIKE_MASTERY,
    "Riverwalk Technique": RIVERWALK_TECHNIQUE,
    "Roiling Dragonstorm": ROILING_DRAGONSTORM,
    "Sibsig Appraiser": SIBSIG_APPRAISER,
    "Snowmelt Stag": SNOWMELT_STAG,
    "Spectral Denial": SPECTRAL_DENIAL,
    "Stillness in Motion": STILLNESS_IN_MOTION,
    "Taigam, Master Opportunist": TAIGAM_MASTER_OPPORTUNIST,
    "Temur Devotee": TEMUR_DEVOTEE,
    "Unending Whisper": UNENDING_WHISPER,
    "Ureni's Rebuff": URENIS_REBUFF,
    "Veteran Ice Climber": VETERAN_ICE_CLIMBER,
    "Wingblade Disciple": WINGBLADE_DISCIPLE,
    "Wingspan Stride": WINGSPAN_STRIDE,
    "Winternight Stories": WINTERNIGHT_STORIES,
    "Abzan Devotee": ABZAN_DEVOTEE,
    "Adorned Crocodile": ADORNED_CROCODILE,
    "Aggressive Negotiations": AGGRESSIVE_NEGOTIATIONS,
    "Alchemist's Assistant": ALCHEMISTS_ASSISTANT,
    "Alesha's Legacy": ALESHAS_LEGACY,
    "Avenger of the Fallen": AVENGER_OF_THE_FALLEN,
    "Caustic Exhale": CAUSTIC_EXHALE,
    "Corroding Dragonstorm": CORRODING_DRAGONSTORM,
    "Cruel Truths": CRUEL_TRUTHS,
    "Delta Bloodflies": DELTA_BLOODFLIES,
    "Desperate Measures": DESPERATE_MEASURES,
    "Dragon's Prey": DRAGONS_PREY,
    "Feral Deathgorger": FERAL_DEATHGORGER,
    "Gurmag Rakshasa": GURMAG_RAKSHASA,
    "Hundred-Battle Veteran": HUNDREDBATTLE_VETERAN,
    "Kin-Tree Nurturer": KINTREE_NURTURER,
    "Krumar Initiate": KRUMAR_INITIATE,
    "Nightblade Brigade": NIGHTBLADE_BRIGADE,
    "Qarsi Revenant": QARSI_REVENANT,
    "Rot-Curse Rakshasa": ROTCURSE_RAKSHASA,
    "Salt Road Skirmish": SALT_ROAD_SKIRMISH,
    "Sandskitter Outrider": SANDSKITTER_OUTRIDER,
    "Scavenger Regent": SCAVENGER_REGENT,
    "The Sibsig Ceremony": THE_SIBSIG_CEREMONY,
    "Sidisi, Regent of the Mire": SIDISI_REGENT_OF_THE_MIRE,
    "Sinkhole Surveyor": SINKHOLE_SURVEYOR,
    "Strategic Betrayal": STRATEGIC_BETRAYAL,
    "Unburied Earthcarver": UNBURIED_EARTHCARVER,
    "Unrooted Ancestor": UNROOTED_ANCESTOR,
    "Venerated Stormsinger": VENERATED_STORMSINGER,
    "Wail of War": WAIL_OF_WAR,
    "Worthy Cost": WORTHY_COST,
    "Yathan Tombguard": YATHAN_TOMBGUARD,
    "Breaching Dragonstorm": BREACHING_DRAGONSTORM,
    "Channeled Dragonfire": CHANNELED_DRAGONFIRE,
    "Cori-Steel Cutter": CORISTEEL_CUTTER,
    "A-Cori-Steel Cutter": ACORISTEEL_CUTTER,
    "Devoted Duelist": DEVOTED_DUELIST,
    "Dracogenesis": DRACOGENESIS,
    "Equilibrium Adept": EQUILIBRIUM_ADEPT,
    "Fire-Rim Form": FIRERIM_FORM,
    "Fleeting Effigy": FLEETING_EFFIGY,
    "Iridescent Tiger": IRIDESCENT_TIGER,
    "Jeskai Devotee": JESKAI_DEVOTEE,
    "Magmatic Hellkite": MAGMATIC_HELLKITE,
    "Meticulous Artisan": METICULOUS_ARTISAN,
    "Molten Exhale": MOLTEN_EXHALE,
    "Narset's Rebuke": NARSETS_REBUKE,
    "Overwhelming Surge": OVERWHELMING_SURGE,
    "Rescue Leopard": RESCUE_LEOPARD,
    "Reverberating Summons": REVERBERATING_SUMMONS,
    "Sarkhan, Dragon Ascendant": SARKHAN_DRAGON_ASCENDANT,
    "Seize Opportunity": SEIZE_OPPORTUNITY,
    "Shock Brigade": SHOCK_BRIGADE,
    "Shocking Sharpshooter": SHOCKING_SHARPSHOOTER,
    "Stadium Headliner": STADIUM_HEADLINER,
    "Stormscale Scion": STORMSCALE_SCION,
    "Stormshriek Feral": STORMSHRIEK_FERAL,
    "Summit Intimidator": SUMMIT_INTIMIDATOR,
    "Sunset Strikemaster": SUNSET_STRIKEMASTER,
    "Tersa Lightshatter": TERSA_LIGHTSHATTER,
    "Twin Bolt": TWIN_BOLT,
    "Underfoot Underdogs": UNDERFOOT_UNDERDOGS,
    "Unsparing Boltcaster": UNSPARING_BOLTCASTER,
    "War Effort": WAR_EFFORT,
    "Wild Ride": WILD_RIDE,
    "Zurgo's Vanguard": ZURGOS_VANGUARD,
    "Ainok Wayfarer": AINOK_WAYFARER,
    "Attuned Hunter": ATTUNED_HUNTER,
    "Bloomvine Regent": BLOOMVINE_REGENT,
    "Champion of Dusan": CHAMPION_OF_DUSAN,
    "Craterhoof Behemoth": CRATERHOOF_BEHEMOTH,
    "Dragon Sniper": DRAGON_SNIPER,
    "Dragonbroods' Relic": DRAGONBROODS_RELIC,
    "Dusyut Earthcarver": DUSYUT_EARTHCARVER,
    "Encroaching Dragonstorm": ENCROACHING_DRAGONSTORM,
    "Formation Breaker": FORMATION_BREAKER,
    "Herd Heirloom": HERD_HEIRLOOM,
    "Heritage Reclamation": HERITAGE_RECLAMATION,
    "Inspirited Vanguard": INSPIRITED_VANGUARD,
    "Knockout Maneuver": KNOCKOUT_MANEUVER,
    "Krotiq Nestguard": KROTIQ_NESTGUARD,
    "Lasyd Prowler": LASYD_PROWLER,
    "Nature's Rhythm": NATURES_RHYTHM,
    "Piercing Exhale": PIERCING_EXHALE,
    "Rainveil Rejuvenator": RAINVEIL_REJUVENATOR,
    "Rite of Renewal": RITE_OF_RENEWAL,
    "Roamer's Routine": ROAMERS_ROUTINE,
    "Sage of the Fang": SAGE_OF_THE_FANG,
    "Sagu Pummeler": SAGU_PUMMELER,
    "Sagu Wildling": SAGU_WILDLING,
    "Sarkhan's Resolve": SARKHANS_RESOLVE,
    "Snakeskin Veil": SNAKESKIN_VEIL,
    "Sultai Devotee": SULTAI_DEVOTEE,
    "Surrak, Elusive Hunter": SURRAK_ELUSIVE_HUNTER,
    "Synchronized Charge": SYNCHRONIZED_CHARGE,
    "Trade Route Envoy": TRADE_ROUTE_ENVOY,
    "Traveling Botanist": TRAVELING_BOTANIST,
    "Undergrowth Leopard": UNDERGROWTH_LEOPARD,
    "Warden of the Grove": WARDEN_OF_THE_GROVE,
    "All-Out Assault": ALLOUT_ASSAULT,
    "Armament Dragon": ARMAMENT_DRAGON,
    "Auroral Procession": AURORAL_PROCESSION,
    "Awaken the Honored Dead": AWAKEN_THE_HONORED_DEAD,
    "Barrensteppe Siege": BARRENSTEPPE_SIEGE,
    "Betor, Kin to All": BETOR_KIN_TO_ALL,
    "Bone-Cairn Butcher": BONECAIRN_BUTCHER,
    "Call the Spirit Dragons": CALL_THE_SPIRIT_DRAGONS,
    "Cori Mountain Stalwart": CORI_MOUNTAIN_STALWART,
    "Death Begets Life": DEATH_BEGETS_LIFE,
    "Defibrillating Current": DEFIBRILLATING_CURRENT,
    "Disruptive Stormbrood": DISRUPTIVE_STORMBROOD,
    "Dragonback Assault": DRAGONBACK_ASSAULT,
    "Dragonclaw Strike": DRAGONCLAW_STRIKE,
    "Effortless Master": EFFORTLESS_MASTER,
    "Eshki Dragonclaw": ESHKI_DRAGONCLAW,
    "Fangkeeper's Familiar": FANGKEEPERS_FAMILIAR,
    "Felothar, Dawn of the Abzan": FELOTHAR_DAWN_OF_THE_ABZAN,
    "Flamehold Grappler": FLAMEHOLD_GRAPPLER,
    "Frontline Rush": FRONTLINE_RUSH,
    "Frostcliff Siege": FROSTCLIFF_SIEGE,
    "Glacial Dragonhunt": GLACIAL_DRAGONHUNT,
    "Glacierwood Siege": GLACIERWOOD_SIEGE,
    "Gurmag Nightwatch": GURMAG_NIGHTWATCH,
    "Hardened Tactician": HARDENED_TACTICIAN,
    "Hollowmurk Siege": HOLLOWMURK_SIEGE,
    "Host of the Hereafter": HOST_OF_THE_HEREAFTER,
    "Inevitable Defeat": INEVITABLE_DEFEAT,
    "Jeskai Brushmaster": JESKAI_BRUSHMASTER,
    "Jeskai Revelation": JESKAI_REVELATION,
    "Jeskai Shrinekeeper": JESKAI_SHRINEKEEPER,
    "Karakyk Guardian": KARAKYK_GUARDIAN,
    "Kheru Goldkeeper": KHERU_GOLDKEEPER,
    "Kin-Tree Severance": KINTREE_SEVERANCE,
    "Kishla Skimmer": KISHLA_SKIMMER,
    "Kotis, the Fangkeeper": KOTIS_THE_FANGKEEPER,
    "Lie in Wait": LIE_IN_WAIT,
    "Lotuslight Dancers": LOTUSLIGHT_DANCERS,
    "Mammoth Bellow": MAMMOTH_BELLOW,
    "Mardu Siegebreaker": MARDU_SIEGEBREAKER,
    "Marshal of the Lost": MARSHAL_OF_THE_LOST,
    "Monastery Messenger": MONASTERY_MESSENGER,
    "Narset, Jeskai Waymaster": NARSET_JESKAI_WAYMASTER,
    "Neriv, Heart of the Storm": NERIV_HEART_OF_THE_STORM,
    "New Way Forward": NEW_WAY_FORWARD,
    "Perennation": PERENNATION,
    "Purging Stormbrood": PURGING_STORMBROOD,
    "Rakshasa's Bargain": RAKSHASAS_BARGAIN,
    "Rediscover the Way": REDISCOVER_THE_WAY,
    "Reigning Victor": REIGNING_VICTOR,
    "Reputable Merchant": REPUTABLE_MERCHANT,
    "Revival of the Ancestors": REVIVAL_OF_THE_ANCESTORS,
    "Riverwheel Sweep": RIVERWHEEL_SWEEP,
    "Roar of Endless Song": ROAR_OF_ENDLESS_SONG,
    "Runescale Stormbrood": RUNESCALE_STORMBROOD,
    "Severance Priest": SEVERANCE_PRIEST,
    "Shiko, Paragon of the Way": SHIKO_PARAGON_OF_THE_WAY,
    "Skirmish Rhino": SKIRMISH_RHINO,
    "Songcrafter Mage": SONGCRAFTER_MAGE,
    "Sonic Shrieker": SONIC_SHRIEKER,
    "Stalwart Successor": STALWART_SUCCESSOR,
    "Temur Battlecrier": TEMUR_BATTLECRIER,
    "Temur Tawnyback": TEMUR_TAWNYBACK,
    "Teval, Arbiter of Virtue": TEVAL_ARBITER_OF_VIRTUE,
    "Thunder of Unity": THUNDER_OF_UNITY,
    "Twinmaw Stormbrood": TWINMAW_STORMBROOD,
    "Ureni, the Song Unending": URENI_THE_SONG_UNENDING,
    "Whirlwing Stormbrood": WHIRLWING_STORMBROOD,
    "Windcrag Siege": WINDCRAG_SIEGE,
    "Yathan Roadwatcher": YATHAN_ROADWATCHER,
    "Zurgo, Thunder's Decree": ZURGO_THUNDERS_DECREE,
    "Abzan Monument": ABZAN_MONUMENT,
    "Boulderborn Dragon": BOULDERBORN_DRAGON,
    "Dragonfire Blade": DRAGONFIRE_BLADE,
    "Dragonstorm Globe": DRAGONSTORM_GLOBE,
    "Embermouth Sentinel": EMBERMOUTH_SENTINEL,
    "Jade-Cast Sentinel": JADECAST_SENTINEL,
    "Jeskai Monument": JESKAI_MONUMENT,
    "Mardu Monument": MARDU_MONUMENT,
    "Mox Jasper": MOX_JASPER,
    "Sultai Monument": SULTAI_MONUMENT,
    "Temur Monument": TEMUR_MONUMENT,
    "Watcher of the Wayside": WATCHER_OF_THE_WAYSIDE,
    "Bloodfell Caves": BLOODFELL_CAVES,
    "Blossoming Sands": BLOSSOMING_SANDS,
    "Cori Mountain Monastery": CORI_MOUNTAIN_MONASTERY,
    "Dalkovan Encampment": DALKOVAN_ENCAMPMENT,
    "Dismal Backwater": DISMAL_BACKWATER,
    "Evolving Wilds": EVOLVING_WILDS,
    "Frontier Bivouac": FRONTIER_BIVOUAC,
    "Great Arashin City": GREAT_ARASHIN_CITY,
    "Jungle Hollow": JUNGLE_HOLLOW,
    "Kishla Village": KISHLA_VILLAGE,
    "Maelstrom of the Spirit Dragon": MAELSTROM_OF_THE_SPIRIT_DRAGON,
    "Mistrise Village": MISTRISE_VILLAGE,
    "Mystic Monastery": MYSTIC_MONASTERY,
    "Nomad Outpost": NOMAD_OUTPOST,
    "Opulent Palace": OPULENT_PALACE,
    "Rugged Highlands": RUGGED_HIGHLANDS,
    "Sandsteppe Citadel": SANDSTEPPE_CITADEL,
    "Scoured Barrens": SCOURED_BARRENS,
    "Swiftwater Cliffs": SWIFTWATER_CLIFFS,
    "Thornwood Falls": THORNWOOD_FALLS,
    "Tranquil Cove": TRANQUIL_COVE,
    "Wind-Scarred Crag": WINDSCARRED_CRAG,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
}

print(f"Loaded {len(TARKIR_DRAGONSTORM_CARDS)} Tarkir: Dragonstorm cards")
