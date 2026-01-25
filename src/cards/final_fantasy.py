"""
Final_Fantasy (FIN) Card Implementations

Real card data fetched from Scryfall API.
313 cards in set.
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
    make_etb_trigger,
    make_death_trigger,
    make_attack_trigger,
    make_damage_trigger,
    make_static_pt_boost,
    make_keyword_grant,
    make_upkeep_trigger,
    make_spell_cast_trigger,
    make_life_gain_trigger,
    make_end_step_trigger,
    other_creatures_you_control,
    other_creatures_with_subtype,
    creatures_you_control,
    creatures_with_subtype,
    all_opponents,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_instant(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
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
        resolve=resolve
    )


def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
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
        resolve=resolve
    )


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
        setup_interceptors=setup_interceptors
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set,
                           subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
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
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
        setup_interceptors=setup_interceptors
    )


def make_planeswalker(name: str, mana_cost: str, colors: set, loyalty: int,
                      subtypes: set = None, supertypes: set = None, text: str = "", setup_interceptors=None):
    """Helper to create planeswalker card definitions."""
    base_supertypes = supertypes or set()
    # Note: loyalty is prepended to text since Characteristics doesn't have loyalty field
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
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# INTERCEPTOR SETUP FUNCTIONS
# =============================================================================

# --- WHITE CARDS ---

def aerith_gainsborough_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aerith: Life gain -> +1/+1 counter; Death -> counters to legendary creatures."""
    interceptors = []

    # Life gain trigger - put a +1/+1 counter on Aerith
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    interceptors.append(make_life_gain_trigger(obj, life_gain_effect))

    # Death trigger - put counters on legendary creatures
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        counter_count = obj.state.counters.get('+1/+1', 0)
        if counter_count > 0:
            for target in state.objects.values():
                if (target.controller == obj.controller and
                    CardType.CREATURE in target.characteristics.types and
                    'Legendary' in target.characteristics.supertypes and
                    target.zone == ZoneType.BATTLEFIELD):
                    events.append(Event(
                        type=EventType.COUNTER_ADDED,
                        payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': counter_count},
                        source=obj.id
                    ))
        return events
    interceptors.append(make_death_trigger(obj, death_effect))

    return interceptors


def ambrosia_whiteheart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ambrosia: Landfall -> +1/+0 until end of turn."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def cloudbound_moogle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cloudbound Moogle: ETB -> +1/+1 counter on target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Note: Full targeting not implemented, would need target selection
        return []
    return [make_etb_trigger(obj, etb_effect)]


def dwarven_castle_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dwarven Castle Guard: Death -> create 1/1 Hero token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def delivery_moogle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delivery Moogle: ETB -> search for artifact (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Placeholder - full library search not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def minwu_white_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Minwu: Life gain -> +1/+1 counter on each Cleric."""
    def life_gain_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for target in state.objects.values():
            if (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Cleric' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': target.id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_life_gain_trigger(obj, life_gain_effect)]


def weapons_vendor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Weapons Vendor: ETB -> draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def zack_fair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zack Fair: ETB -> enters with +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- BLUE CARDS ---

def dragoons_wyvern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dragoon's Wyvern: ETB -> create 1/1 Hero token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def edgar_king_of_figaro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Edgar: ETB -> draw card for each artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        artifact_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.ARTIFACT in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD)
        if artifact_count > 0:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': artifact_count},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def ice_flan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ice Flan: ETB -> tap and stun target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Note: Targeting not implemented, would select target
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rook_turret_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rook Turret: Artifact ETB -> draw and discard."""
    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def artifact_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_etb_trigger(obj, artifact_etb_effect, artifact_etb_filter)]


def valkyrie_aerial_unit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valkyrie: ETB -> surveil 2 (simplified: mill 2 cards)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- BLACK CARDS ---

def al_bhed_salvagers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Al Bhed Salvagers: Creature/artifact dies -> opponent loses 1, you gain 1."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller == source.controller and
                (CardType.CREATURE in dying.characteristics.types or
                 CardType.ARTIFACT in dying.characteristics.types))

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1},
                source=obj.id
            ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events

    return [make_death_trigger(obj, death_effect, death_filter)]


def dark_confidant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Confidant: Upkeep -> reveal top card, draw it, lose life = MV."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: draw 1 card, lose 2 life (average mana value)
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -2}, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def hecteyes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hecteyes: ETB -> each opponent discards a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DISCARD,
                payload={'player': opp, 'amount': 1},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def malboro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Malboro: ETB -> opponent discards, loses 2 life, mills 3."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': opp, 'amount': 1}, source=obj.id))
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -2}, source=obj.id))
            events.append(Event(type=EventType.MILL, payload={'player': opp, 'amount': 3}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def namazu_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Namazu Trader: ETB -> lose 1 life, create Treasure token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def shinra_reinforcements_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shinra Reinforcements: ETB -> mill 3, gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 3}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def undercity_dire_rat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Undercity Dire Rat: Death -> create Treasure token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def zodiark_umbral_god_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zodiark: ETB -> each player sacrifices half their non-God creatures; creature sac -> +1/+1."""
    interceptors = []

    # ETB effect (simplified - full sacrifice logic complex)
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Sacrifice logic would need targeting system
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Sacrifice trigger - when creature sacrificed, +1/+1 counter
    def sac_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('cause') != 'sacrifice':
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.id == source.id:
            return False
        return CardType.CREATURE in dying.characteristics.types

    def sac_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_death_trigger(obj, sac_effect, sac_filter))
    return interceptors


def sephiroth_planets_heir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sephiroth: ETB -> creatures opponents control get -2/-2; creature dies -> +1/+1."""
    interceptors = []

    # ETB effect
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for target in state.objects.values():
            if (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': target.id, 'power_mod': -2, 'toughness_mod': -2, 'duration': 'end_of_turn'},
                    source=obj.id
                ))
        return events
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Opponent creature death -> +1/+1
    def opp_death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller != source.controller and
                CardType.CREATURE in dying.characteristics.types)

    def opp_death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_death_trigger(obj, opp_death_effect, opp_death_filter))
    return interceptors


# --- RED CARDS ---

def barret_wallace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Barret: Attack -> deal damage equal to equipped creatures."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        equipped_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.CREATURE in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD and
                           hasattr(o.state, 'attached_equipment') and o.state.attached_equipment)
        if equipped_count > 0:
            defending = event.payload.get('defending_player')
            if defending:
                return [Event(
                    type=EventType.DAMAGE,
                    payload={'target': defending, 'amount': equipped_count, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                )]
        return []
    return [make_attack_trigger(obj, attack_effect)]


def mysidian_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mysidian Elder: ETB -> create 0/1 Wizard token with spell damage trigger."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Wizard',
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Wizard'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def prompto_argentum_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prompto: Cast noncreature spell (4+ mana) -> create Treasure."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        mana_spent = event.payload.get('mana_spent', 0)
        spell_types = set(event.payload.get('types', []))
        return mana_spent >= 4 and CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def queen_brahne_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Queen Brahne: Attack -> create 0/1 Wizard token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Wizard',
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Wizard'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def sabotender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sabotender: Landfall -> deal 1 damage to each opponent."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 1, 'source': obj.id, 'is_combat': False},
                source=obj.id
            ))
        return events

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def sandworm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sandworm: ETB -> destroy target land (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting system
    return [make_etb_trigger(obj, etb_effect)]


# --- GREEN CARDS ---

def balamb_trexaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Balamb T-Rexaur: ETB -> gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def bartz_and_boko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bartz: ETB -> each Bird deals damage equal to its power to target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - would need targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def coliseum_behemoth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Coliseum Behemoth: ETB -> destroy artifact/enchantment OR draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified: just draw a card (modal choice not implemented)
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def jumbo_cactuar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jumbo Cactuar: Attack -> gets +9999/+0 until end of turn."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 9999, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def loporrit_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Loporrit Scout: Creature ETB -> +1/+1 until end of turn."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def sazh_katzroy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sazh: ETB -> search for Bird/land (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Library search not implemented
    return [make_etb_trigger(obj, etb_effect)]


def sazhs_chocobo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sazh's Chocobo: Landfall -> +1/+1 counter."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def tifa_lockhart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tifa: Landfall -> double power until end of turn."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        current_power = get_power(obj, state)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': current_power, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def vanille_cheerful_lcie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vanille: ETB -> mill 2, return permanent card from graveyard (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


# --- MULTICOLOR CARDS ---

def black_waltz_no_3_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Black Waltz No. 3: Cast noncreature spell -> deal 2 damage to each opponent."""
    def spell_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 2, 'source': obj.id, 'is_combat': False},
                source=obj.id
            ))
        return events

    return [make_spell_cast_trigger(obj, spell_effect, controller_only=True,
                                   spell_type_filter={CardType.INSTANT, CardType.SORCERY, CardType.ENCHANTMENT, CardType.ARTIFACT})]


def cloud_of_darkness_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cloud of Darkness: ETB -> target creature gets -X/-X (X = permanent cards in graveyard)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting, placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]


def garnet_princess_of_alexandria_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Garnet: Attack -> remove lore counters from Sagas, get +1/+1 counters."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - would need Saga interaction
        return []
    return [make_attack_trigger(obj, attack_effect)]


def giott_king_of_dwarves_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Giott: Dwarf/Equipment ETB -> may discard to draw."""
    def etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != source.controller:
            return False
        is_dwarf = ('Dwarf' in entering.characteristics.subtypes and
                   CardType.CREATURE in entering.characteristics.types)
        is_equipment = 'Equipment' in entering.characteristics.subtypes
        return is_dwarf or is_equipment

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # May discard/draw - simplified to just draw
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, etb_effect, etb_filter)]


def gladiolus_amicitia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gladiolus: ETB -> search for land (placeholder); Landfall -> creature gets +2/+2 trample."""
    interceptors = []

    # ETB - search land (placeholder)
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Landfall
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting for "another target creature"
        return []

    interceptors.append(make_etb_trigger(obj, landfall_effect, landfall_filter))
    return interceptors


def golbez_crystal_collector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Golbez: Artifact ETB -> surveil 1."""
    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def artifact_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, artifact_etb_effect, artifact_etb_filter)]


def hope_estheim_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hope: End step -> opponents mill X (X = life gained this turn)."""
    # Would need life gained tracking per turn
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Life tracking not implemented
    return [make_end_step_trigger(obj, end_step_effect)]


def ignis_scientia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ignis: ETB -> look at top 6, may put land onto battlefield tapped."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Library manipulation not implemented
    return [make_etb_trigger(obj, etb_effect)]


def jenova_ancient_calamity_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jenova: Combat -> put +1/+1 counters on target creature equal to Jenova's power."""
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        power = get_power(obj, state)
        # Would need targeting
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


def judge_magister_gabranth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Judge Gabranth: Creature/artifact dies -> +1/+1 counter."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.id == source.id:
            return False
        return (dying.controller == source.controller and
                (CardType.CREATURE in dying.characteristics.types or
                 CardType.ARTIFACT in dying.characteristics.types))

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [make_death_trigger(obj, death_effect, death_filter)]


def lightning_army_of_one_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lightning: Combat damage -> double damage to that player until next turn."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        # Stagger effect would need damage modification tracking
        return []
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def locke_cole_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Locke: Combat damage -> draw, then discard."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def rinoa_heartilly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rinoa: ETB -> create Angelo token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Angelo',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Dog'],
                'colors': [Color.GREEN, Color.WHITE],
                'supertypes': ['Legendary']
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def rufus_shinra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rufus: Attack -> create Darkstar token if you don't control one."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        has_darkstar = any(o.characteristics.name == 'Darkstar'
                         for o in state.objects.values()
                         if o.controller == obj.controller and o.zone == ZoneType.BATTLEFIELD)
        if not has_darkstar:
            return [Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': 'Darkstar',
                    'power': 2,
                    'toughness': 2,
                    'types': [CardType.CREATURE],
                    'subtypes': ['Dog'],
                    'colors': [Color.WHITE, Color.BLACK],
                    'supertypes': ['Legendary']
                },
                source=obj.id
            )]
        return []
    return [make_attack_trigger(obj, attack_effect)]


def rydia_summoner_of_mist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rydia: Landfall -> may discard to draw."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # May discard/draw - simplified
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def shantotto_tactician_magician_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shantotto: Noncreature spell -> +X/+0 until EOT, draw if X>=4."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        mana_spent = event.payload.get('mana_spent', 0)
        events = [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': mana_spent, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]
        if mana_spent >= 4:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id
            ))
        return events

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def tellah_great_sage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tellah: Noncreature spell -> create Hero token; 4+ mana -> draw 2; 8+ -> sacrifice and damage."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        mana_spent = event.payload.get('mana_spent', 0)
        events = [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
        if mana_spent >= 4:
            events.append(Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id
            ))
        if mana_spent >= 8:
            events.append(Event(
                type=EventType.ZONE_CHANGE,
                payload={'object_id': obj.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                        'to_zone_type': ZoneType.GRAVEYARD, 'cause': 'sacrifice'},
                source=obj.id
            ))
            for opp in all_opponents(obj, state):
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': opp, 'amount': mana_spent, 'source': obj.id, 'is_combat': False},
                    source=obj.id
                ))
        return events

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def tidus_blitzball_star_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tidus: Artifact ETB -> +1/+1 counter; Attack -> tap target creature."""
    interceptors = []

    # Artifact ETB
    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def artifact_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_etb_trigger(obj, artifact_etb_effect, artifact_etb_filter))

    # Attack trigger (tap would need targeting)
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting not implemented
    interceptors.append(make_attack_trigger(obj, attack_effect))

    return interceptors


def ultimecia_temporal_threat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ultimecia: ETB -> tap all opponent creatures; Combat damage -> draw."""
    interceptors = []

    # ETB - tap all opponent creatures
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for target in state.objects.values():
            if (target.controller != obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': target.id},
                    source=obj.id
                ))
        return events
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Combat damage trigger for any creature you control
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        damage_source_id = event.payload.get('source')
        damage_source = state.objects.get(damage_source_id)
        if not damage_source:
            return False
        if damage_source.controller != source.controller:
            return False
        target = event.payload.get('target')
        return target in state.players  # Damage to a player

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True, filter_fn=damage_filter))
    return interceptors


def vivi_ornitier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vivi: Noncreature spell -> +1/+1 counter and 1 damage to each opponent."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        events = [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 1, 'source': obj.id, 'is_combat': False},
                source=obj.id
            ))
        return events

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def yuna_hope_of_spira_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Yuna: End step -> return enchantment from graveyard (placeholder)."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Graveyard return would need targeting
    return [make_end_step_trigger(obj, end_step_effect)]


def zidane_tantalus_thief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zidane: ETB -> gain control of creature until EOT (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Control change would need targeting
    return [make_etb_trigger(obj, etb_effect)]


# --- ARTIFACT CARDS ---

def instant_ramen_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant Ramen: ETB -> draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def lion_heart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Lion Heart: ETB -> deal 2 damage to any target (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting not implemented
    return [make_etb_trigger(obj, etb_effect)]


def magic_pot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Magic Pot: Death -> create Treasure token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def magitek_armor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Magitek Armor: ETB -> create 1/1 Hero token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def adventurers_inn_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adventurer's Inn: ETB -> gain 2 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def seymour_flux_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Seymour Flux: Upkeep -> may pay 1 life to draw and +1/+1 counter."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - always triggers (may choice not implemented)
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.COUNTER_ADDED, payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1}, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def rosa_resolute_white_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rosa: Combat -> +1/+1 counter and lifelink on target creature."""
    def combat_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_START and
                event.payload.get('phase') == 'combat' and
                state.active_player == obj.controller)

    def combat_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=combat_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=combat_effect(e, s)),
        duration='while_on_battlefield'
    )]


# --- ADDITIONAL WHITE CARD INTERCEPTORS ---

def ashe_princess_of_dalmasca_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ashe: Attack -> look at top 5, may reveal artifact."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Would need library manipulation - placeholder
        return []
    return [make_attack_trigger(obj, attack_effect)]


def graha_tia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """G'raha Tia: Creature/artifact dies -> draw a card (once per turn)."""
    # Track if triggered this turn via a flag (simplified)
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.id == source.id:
            return False
        return (dying.controller == source.controller and
                (CardType.CREATURE in dying.characteristics.types or
                 CardType.ARTIFACT in dying.characteristics.types))

    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [make_death_trigger(obj, death_effect, death_filter)]


def white_auracite_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """White Auracite: ETB -> exile target nonland permanent (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting system
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL BLUE CARD INTERCEPTORS ---

def il_mheg_pixie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Il Mheg Pixie: Attack -> surveil 1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def matoya_archon_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Matoya: Whenever you scry or surveil, draw a card."""
    # Simplified - triggers on mill as a proxy for surveil
    def surveil_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.MILL and
                event.payload.get('player') == obj.controller)

    def surveil_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=surveil_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=surveil_effect(e, s)),
        duration='while_on_battlefield'
    )]


def quistis_trepe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Quistis: ETB -> may cast instant/sorcery from graveyard (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need graveyard targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def ultros_obnoxious_octopus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ultros: ETB -> each player draws 2, discards 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(type=EventType.DRAW, payload={'player': player_id, 'amount': 2}, source=obj.id))
            events.append(Event(type=EventType.DISCARD, payload={'player': player_id, 'amount': 2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL BLACK CARD INTERCEPTORS ---

def ahriman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ahriman: ETB -> lose 1 life and surveil 1."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
            Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def gaius_van_baelsar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gaius: ETB -> each player sacrifices something (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def reno_and_rude_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reno and Rude: ETB -> destroy creature dealt damage or exile graveyard cards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal targeting not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


def ragnarok_divine_deliverance_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ragnarok: Death -> destroy permanent and return nonlegendary card from graveyard."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_death_trigger(obj, death_effect)]


def ancient_adamantoise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ancient Adamantoise: Death -> create 10 Treasure tokens."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for _ in range(10):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': 'Treasure',
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Treasure'],
                    'colors': []
                },
                source=obj.id
            ))
        return events
    return [make_death_trigger(obj, death_effect)]


# --- ADDITIONAL RED CARD INTERCEPTORS ---

def firion_wild_rose_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Firion: Equipment ETB -> create copy token."""
    def equipment_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                'Equipment' in entering.characteristics.subtypes and
                not getattr(entering, 'is_token', False))

    def equipment_etb_effect(event: Event, state: GameState) -> list[Event]:
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if entering:
            return [Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': entering.characteristics.name,
                    'types': list(entering.characteristics.types),
                    'subtypes': list(entering.characteristics.subtypes),
                    'copy_of': entering_id
                },
                source=obj.id
            )]
        return []

    return [make_etb_trigger(obj, equipment_etb_effect, equipment_etb_filter)]


def gilgamesh_master_at_arms_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gilgamesh: ETB/Attack -> look at top 6, put Equipment onto battlefield."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library manipulation not fully implemented
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []
    interceptors.append(make_attack_trigger(obj, attack_effect))

    return interceptors


def seifer_almasy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Seifer: Combat damage -> cast instant/sorcery from graveyard."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        # Would need graveyard targeting
        return []
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def vaan_street_thief_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vaan: Scouts/Pirates/Rogues deal damage -> exile top card, may cast."""
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        damage_source_id = event.payload.get('source')
        damage_source = state.objects.get(damage_source_id)
        if not damage_source:
            return False
        if damage_source.controller != source.controller:
            return False
        subtypes = damage_source.characteristics.subtypes
        return any(st in subtypes for st in ['Scout', 'Pirate', 'Rogue'])

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Exile/cast from opponent library - placeholder
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]

    return [make_damage_trigger(obj, damage_effect, combat_only=True, filter_fn=damage_filter)]


def zell_dincht_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zell: End step -> return a land to hand."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting for land bounce
        return []
    return [make_end_step_trigger(obj, end_step_effect)]


def chocobo_racetrack_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Chocobo Racetrack: Landfall -> create 2/2 Bird token."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Bird',
                'power': 2,
                'toughness': 2,
                'types': [CardType.CREATURE],
                'subtypes': ['Bird'],
                'colors': [Color.GREEN]
            },
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


# --- ADDITIONAL GREEN CARD INTERCEPTORS ---

def quina_qu_gourmet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Quina: Attack -> mill 3, gain life for creature cards milled."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - mill 3, gain 3 life (assumes 1 creature card)
        return [
            Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 3}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


def town_greeter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Town Greeter: ETB -> mill 4, may put land in hand, +2 life if Town."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 4},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def traveling_chocobo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Traveling Chocobo: Landfall -> +1/+1 until end of turn."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


# --- ADDITIONAL MULTICOLOR CARD INTERCEPTORS ---

def balthier_and_fran_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Balthier and Fran: Vehicles get +1/+1 and vigilance/reach (static)."""
    def vehicle_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                'Vehicle' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)

    interceptors = make_static_pt_boost(obj, 1, 1, vehicle_filter)
    interceptors.append(make_keyword_grant(obj, ['vigilance', 'reach'], vehicle_filter))
    return interceptors


def cid_timeless_artificer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cid: Artifact creatures and Heroes get +1/+1 per Artificer."""
    def affected_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        is_artifact_creature = CardType.ARTIFACT in target.characteristics.types
        is_hero = 'Hero' in target.characteristics.subtypes
        return is_artifact_creature or is_hero

    # Count artificers for dynamic boost
    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return affected_filter(target, state)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        artificer_count = sum(1 for o in state.objects.values()
                            if o.controller == obj.controller and
                            'Artificer' in o.characteristics.subtypes and
                            CardType.CREATURE in o.characteristics.types and
                            o.zone == ZoneType.BATTLEFIELD)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + artificer_count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return affected_filter(target, state)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        artificer_count = sum(1 for o in state.objects.values()
                            if o.controller == obj.controller and
                            'Artificer' in o.characteristics.subtypes and
                            CardType.CREATURE in o.characteristics.types and
                            o.zone == ZoneType.BATTLEFIELD)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + artificer_count
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ),
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        )
    ]


def fire_crystal_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Fire Crystal: Creatures you control have haste."""
    return [make_keyword_grant(obj, ['haste'], creatures_you_control(obj))]


def omega_heartless_evolution_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Omega: ETB -> tap nonland permanents, put stun counters, gain life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        nonbasic_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.LAND in o.characteristics.types and
                           'Basic' not in o.characteristics.supertypes and
                           o.zone == ZoneType.BATTLEFIELD)
        # Would need targeting - simplified
        if nonbasic_count > 0:
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': nonbasic_count},
                source=obj.id
            ))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def sin_spiras_punishment_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sin: ETB/Attack -> exile permanent from graveyard, create copy token."""
    interceptors = []

    def trigger_effect(event: Event, state: GameState) -> list[Event]:
        # Would need graveyard targeting - placeholder
        return []

    interceptors.append(make_etb_trigger(obj, trigger_effect))
    interceptors.append(make_attack_trigger(obj, trigger_effect))
    return interceptors


def squall_seed_mercenary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Squall: Creature attacks alone -> double strike; Combat damage -> return permanent."""
    def combat_damage_effect(event: Event, state: GameState) -> list[Event]:
        # Would need graveyard targeting
        return []
    return [make_damage_trigger(obj, combat_damage_effect, combat_only=True)]


def terra_magical_adept_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Terra: Noncreature spell -> +1/+1 counter and create Shard token."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
                source=obj.id
            ),
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'name': 'Shard',
                    'types': [CardType.ARTIFACT],
                    'subtypes': ['Shard'],
                    'colors': []
                },
                source=obj.id
            )
        ]

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def kefka_court_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kefka: Noncreature spell -> opponent loses 1 life, you gain 1 life."""
    def spell_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        if event.payload.get('caster') != source.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.CREATURE not in spell_types

    def spell_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp, 'amount': -1},
                source=obj.id
            ))
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        ))
        return events

    return [make_spell_cast_trigger(obj, spell_effect, filter_fn=spell_filter)]


def kuja_genome_sorcerer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Kuja: Attack -> draw, then discard."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


def noctis_prince_of_lucis_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Noctis: Attack -> tap target creature, if tapped creature dealt damage, draw."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_attack_trigger(obj, attack_effect)]


def serah_farron_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Serah: ETB -> search for legendary creature or enchantment (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Library search not implemented
        return []
    return [make_etb_trigger(obj, etb_effect)]


# --- ADDITIONAL ARTIFACT CARD INTERCEPTORS ---

def elixir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Elixir: ETB -> gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def iron_giant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Iron Giant: Attack -> +1/+1 until EOT for each artifact you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        artifact_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.ARTIFACT in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD)
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': artifact_count, 'toughness_mod': artifact_count, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def the_regalia_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """The Regalia: Attack -> reveal cards until land, put onto battlefield."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Library manipulation not implemented
        return []
    return [make_attack_trigger(obj, attack_effect)]


def pupu_ufo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """PuPu UFO: ETB -> each player draws 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players.keys():
            events.append(Event(type=EventType.DRAW, payload={'player': player_id, 'amount': 2}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def adventurers_airship_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Adventurer's Airship: Attack -> draw, then discard."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_attack_trigger(obj, attack_effect)]


def coral_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Coral Sword: ETB -> attach to target creature, give first strike (placeholder)."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def magitek_scythe_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Magitek Scythe: ETB -> attach to creature, give first strike."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def ultima_weapon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ultima Weapon: Equipped creature attacks -> destroy target creature."""
    # Need to track if equipped creature attacks
    def attack_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        # Check if this equipment is attached to the attacker
        attached_to = getattr(source.state, 'attached_to', None)
        return attached_to == attacker_id

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []

    return [make_attack_trigger(obj, attack_effect, attack_filter)]


# --- ADDITIONAL MISSING SETUP FUNCTIONS ---

def ashe_princess_of_dalmasca_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ashe: Attack -> look at top 5, may reveal artifact."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        # Library manipulation placeholder
        return []
    return [make_attack_trigger(obj, attack_effect)]


def dwarven_castle_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dwarven Castle Guard: Death -> create 1/1 Hero token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def weapons_vendor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Weapons Vendor: ETB -> draw a card."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def zack_fair_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zack Fair: ETB -> enter with +1/+1 counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def dragoons_wyvern_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dragoon's Wyvern: ETB -> create 1/1 Hero token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Hero',
                'power': 1,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Hero'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def edgar_king_of_figaro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Edgar: ETB -> draw card for each artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        artifact_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.ARTIFACT in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD)
        if artifact_count > 0:
            return [Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': artifact_count},
                source=obj.id
            )]
        return []
    return [make_etb_trigger(obj, etb_effect)]


def ice_flan_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ice Flan: ETB -> tap target and put stun counter."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def rook_turret_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rook Turret: Artifact ETB -> draw, discard."""
    def artifact_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                CardType.ARTIFACT in entering.characteristics.types)

    def artifact_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [make_etb_trigger(obj, artifact_etb_effect, artifact_etb_filter)]


def valkyrie_aerial_unit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Valkyrie Aerial Unit: ETB -> surveil 2."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MILL,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def al_bhed_salvagers_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Al Bhed Salvagers: Creature/artifact dies -> drain 1."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying:
            return False
        return (dying.controller == source.controller and
                (CardType.CREATURE in dying.characteristics.types or
                 CardType.ARTIFACT in dying.characteristics.types))

    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -1}, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id))
        return events

    return [make_death_trigger(obj, death_effect, death_filter)]


def dark_confidant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Dark Confidant: Upkeep -> reveal top card, draw, lose life."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - always loses 2 life (placeholder)
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -2}, source=obj.id)
        ]
    return [make_upkeep_trigger(obj, upkeep_effect)]


def hecteyes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hecteyes: ETB -> each opponent discards."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': opp, 'amount': 1}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def malboro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Malboro: ETB -> discard, life loss, mill for opponents."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(type=EventType.DISCARD, payload={'player': opp, 'amount': 1}, source=obj.id))
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': opp, 'amount': -2}, source=obj.id))
            events.append(Event(type=EventType.MILL, payload={'player': opp, 'amount': 3}, source=obj.id))
        return events
    return [make_etb_trigger(obj, etb_effect)]


def namazu_trader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Namazu Trader: ETB -> lose 1 life, create Treasure."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': -1}, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def shinra_reinforcements_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shinra Reinforcements: ETB -> mill 3, gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.MILL, payload={'player': obj.controller, 'amount': 3}, source=obj.id),
            Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]


def undercity_dire_rat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Undercity Dire Rat: Death -> create Treasure token."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Treasure',
                'types': [CardType.ARTIFACT],
                'subtypes': ['Treasure'],
                'colors': []
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]


def zodiark_umbral_god_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Zodiark: ETB -> each player sacrifices half creatures."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need sacrifice targeting
        return []
    interceptors.append(make_etb_trigger(obj, etb_effect))

    # Sacrifice trigger
    def sac_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('sacrifice') != True:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if not dying or dying.id == obj.id:
            return False
        return CardType.CREATURE in dying.characteristics.types

    def sac_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sac_filter,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=sac_effect(e, s)),
        duration='while_on_battlefield'
    ))

    return interceptors


def barret_wallace_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Barret: Attack -> deal damage equal to equipped creatures."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        equipped_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.CREATURE in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD and
                           any('Equipment' in eq.characteristics.subtypes for eq in state.objects.values()
                               if getattr(eq.state, 'attached_to', None) == o.id))
        # Would need defending player targeting
        return []
    return [make_attack_trigger(obj, attack_effect)]


def mysidian_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mysidian Elder: ETB -> create 0/1 Wizard token."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Wizard',
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Wizard'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def queen_brahne_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Queen Brahne: Attack -> create 0/1 Wizard token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'name': 'Wizard',
                'power': 0,
                'toughness': 1,
                'types': [CardType.CREATURE],
                'subtypes': ['Wizard'],
                'colors': [Color.BLACK]
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


def sabotender_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sabotender: Landfall -> deal 1 damage to each opponent."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering:
            return False
        return (entering.controller == source.controller and
                CardType.LAND in entering.characteristics.types)

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for opp in all_opponents(obj, state):
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': opp, 'amount': 1, 'source': obj.id},
                source=obj.id
            ))
        return events

    return [make_etb_trigger(obj, landfall_effect, landfall_filter)]


def balamb_trexaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Balamb T-Rexaur: ETB -> gain 3 life."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def bartz_and_boko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bartz and Boko: ETB -> Birds deal damage."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting
        return []
    return [make_etb_trigger(obj, etb_effect)]


def coliseum_behemoth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Coliseum Behemoth: ETB -> destroy artifact/enchantment or draw."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Modal choice not implemented - default to draw
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]


def loporrit_scout_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Loporrit Scout: Creature ETB -> get +1/+1."""
    def creature_etb_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        if not entering or entering.id == source.id:
            return False
        return (entering.controller == source.controller and
                CardType.CREATURE in entering.characteristics.types)

    def creature_etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': 1, 'toughness_mod': 1, 'duration': 'end_of_turn'},
            source=obj.id
        )]

    return [make_etb_trigger(obj, creature_etb_effect, creature_etb_filter)]


def tifa_lockhart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Tifa: Attack -> +1/+0 for each untapped land."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        untapped_lands = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.LAND in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD and
                           not getattr(o.state, 'tapped', False))
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': obj.id, 'power_mod': untapped_lands, 'toughness_mod': 0, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]


# =============================================================================
# CARD DEFINITIONS
# =============================================================================

SUMMON_BAHAMUT = make_creature(
    name="Summon: Bahamut",
    power=9, toughness=9,
    mana_cost="{9}",
    colors=set(),
    subtypes={"Dragon", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II — Destroy up to one target nonland permanent.\nIII — Draw two cards.\nIV — Mega Flare — This creature deals damage equal to the total mana value of other permanents you control to each opponent.\nFlying",
)

ULTIMA_ORIGIN_OF_OBLIVION = make_creature(
    name="Ultima, Origin of Oblivion",
    power=4, toughness=4,
    mana_cost="{5}",
    colors=set(),
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Ultima attacks, put a blight counter on target land. For as long as that land has a blight counter on it, it loses all land types and abilities and has \"{T}: Add {C}.\"\nWhenever you tap a land for {C}, add an additional {C}.",
)

ADELBERT_STEINER = make_creature(
    name="Adelbert Steiner",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Lifelink\nAdelbert Steiner gets +1/+1 for each Equipment you control.",
)

AERITH_GAINSBOROUGH = make_creature(
    name="Aerith Gainsborough",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever you gain life, put a +1/+1 counter on Aerith Gainsborough.\nWhen Aerith Gainsborough dies, put X +1/+1 counters on each legendary creature you control, where X is the number of +1/+1 counters on Aerith Gainsborough.",
    setup_interceptors=aerith_gainsborough_setup,
)

AERITH_RESCUE_MISSION = make_sorcery(
    name="Aerith Rescue Mission",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Take the Elevator — Create three 1/1 colorless Hero creature tokens.\n• Take 59 Flights of Stairs — Tap up to three target creatures. Put a stun counter on one of them. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

AMBROSIA_WHITEHEART = make_creature(
    name="Ambrosia Whiteheart",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    text="Flash\nWhen Ambrosia Whiteheart enters, you may return another permanent you control to its owner's hand.\nLandfall — Whenever a land you control enters, Ambrosia Whiteheart gets +1/+0 until end of turn.",
    setup_interceptors=ambrosia_whiteheart_setup,
)

ASHE_PRINCESS_OF_DALMASCA = make_creature(
    name="Ashe, Princess of Dalmasca",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble", "Rebel"},
    supertypes={"Legendary"},
    text="Whenever Ashe attacks, look at the top five cards of your library. You may reveal an artifact card from among them and put it into your hand. Put the rest on the bottom of your library in a random order.",
)

AURONS_INSPIRATION = make_instant(
    name="Auron's Inspiration",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Attacking creatures get +2/+0 until end of turn.\nFlashback {2}{W}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

BATTLE_MENU = make_instant(
    name="Battle Menu",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Choose one —\n• Attack — Create a 2/2 white Knight creature token.\n• Ability — Target creature gets +0/+4 until end of turn.\n• Magic — Destroy target creature with power 4 or greater.\n• Item — You gain 4 life.",
)

CLOUD_MIDGAR_MERCENARY = make_creature(
    name="Cloud, Midgar Mercenary",
    power=2, toughness=1,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary", "Soldier"},
    supertypes={"Legendary"},
    text="When Cloud enters, search your library for an Equipment card, reveal it, put it into your hand, then shuffle.\nAs long as Cloud is equipped, if an ability of Cloud or an Equipment attached to it triggers, that ability triggers an additional time.",
)

CLOUDBOUND_MOOGLE = make_creature(
    name="Cloudbound Moogle",
    power=2, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    text="Flying\nWhen this creature enters, put a +1/+1 counter on target creature.\nPlainscycling {2} ({2}, Discard this card: Search your library for a Plains card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=cloudbound_moogle_setup,
)

COEURL = make_creature(
    name="Coeurl",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Beast", "Cat"},
    text="{1}{W}, {T}: Tap target nonenchantment creature.",
)

CRYSTAL_FRAGMENTS = make_artifact_creature(
    name="Crystal Fragments",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Equipment"},
    text="",
)

THE_CRYSTALS_CHOSEN = make_sorcery(
    name="The Crystal's Chosen",
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 colorless Hero creature tokens. Then put a +1/+1 counter on each creature you control.",
)

DELIVERY_MOOGLE = make_creature(
    name="Delivery Moogle",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    text="Flying\nWhen this creature enters, search your library and/or graveyard for an artifact card with mana value 2 or less, reveal it, and put it into your hand. If you search your library this way, shuffle.",
)

DION_BAHAMUTS_DOMINANT = make_creature(
    name="Dion, Bahamut's Dominant",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Knight", "Legendary", "Noble"},
    supertypes={"Legendary"},
    text="",
)

DRAGOONS_LANCE = make_artifact(
    name="Dragoon's Lance",
    mana_cost="{1}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0 and is a Knight in addition to its other types.\nDuring your turn, equipped creature has flying.\nGae Bolg — Equip {4}",
    subtypes={"Equipment"},
)

DWARVEN_CASTLE_GUARD = make_creature(
    name="Dwarven Castle Guard",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Soldier"},
    text="When this creature dies, create a 1/1 colorless Hero creature token.",
    setup_interceptors=dwarven_castle_guard_setup,
)

FATE_OF_THE_SUNCRYST = make_instant(
    name="Fate of the Sun-Cryst",
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    text="This spell costs {2} less to cast if it targets a tapped creature.\nDestroy target nonland permanent.",
)

FROM_FATHER_TO_SON = make_sorcery(
    name="From Father to Son",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Search your library for a Vehicle card, reveal it, and put it into your hand. If this spell was cast from a graveyard, put that card onto the battlefield instead. Then shuffle.\nFlashback {4}{W}{W}{W} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

GRAHA_TIA = make_creature(
    name="G'raha Tia",
    power=3, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Archer", "Cat"},
    supertypes={"Legendary"},
    text="Reach\nThe Allagan Eye — Whenever one or more other creatures and/or artifacts you control die, draw a card. This ability triggers only once each turn.",
    setup_interceptors=graha_tia_setup,
)

GAELICAT = make_creature(
    name="Gaelicat",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Cat"},
    text="Flying, vigilance\nAs long as you control two or more artifacts, this creature gets +2/+0.",
)

MACHINISTS_ARSENAL = make_artifact(
    name="Machinist's Arsenal",
    mana_cost="{4}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2 for each artifact you control and is an Artificer in addition to its other types.\nMachina — Equip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

MAGITEK_ARMOR = make_artifact(
    name="Magitek Armor",
    mana_cost="{3}{W}",
    text="When this Vehicle enters, create a 1/1 colorless Hero creature token.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

MAGITEK_INFANTRY = make_artifact_creature(
    name="Magitek Infantry",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Robot", "Soldier"},
    text="This creature gets +1/+0 as long as you control another artifact.\n{2}{W}: Search your library for a card named Magitek Infantry, put it onto the battlefield tapped, then shuffle.",
)

MINWU_WHITE_MAGE = make_creature(
    name="Minwu, White Mage",
    power=3, toughness=3,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="Vigilance, lifelink\nWhenever you gain life, put a +1/+1 counter on each Cleric you control.",
    setup_interceptors=minwu_white_mage_setup,
)

MOOGLES_VALOR = make_instant(
    name="Moogles' Valor",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="For each creature you control, create a 1/2 white Moogle creature token with lifelink. Then creatures you control gain indestructible until end of turn.",
)

PALADINS_ARMS = make_artifact(
    name="Paladin's Arms",
    mana_cost="{2}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+1, has ward {1}, and is a Knight in addition to its other types.\nLightbringer and Hero's Shield — Equip {4} ({4}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

PHOENIX_DOWN = make_artifact(
    name="Phoenix Down",
    mana_cost="{W}",
    text="{1}{W}, {T}, Exile this artifact: Choose one —\n• Return target creature card with mana value 4 or less from your graveyard to the battlefield tapped.\n• Exile target Skeleton, Spirit, or Zombie.",
)

RESTORATION_MAGIC = make_instant(
    name="Restoration Magic",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Tiered (Choose one additional cost.)\n• Cure — {0} — Target permanent gains hexproof and indestructible until end of turn.\n• Cura — {1} — Target permanent gains hexproof and indestructible until end of turn. You gain 3 life.\n• Curaga — {3}{W} — Permanents you control gain hexproof and indestructible until end of turn. You gain 6 life.",
)

SIDEQUEST_CATCH_A_FISH = make_enchantment(
    name="Sidequest: Catch a Fish",
    mana_cost="",
    colors=set(),
    text="",
)

SLASH_OF_LIGHT = make_instant(
    name="Slash of Light",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Slash of Light deals damage equal to the number of creatures you control plus the number of Equipment you control to target creature.",
)

SNOW_VILLIERS = make_creature(
    name="Snow Villiers",
    power=0, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Monk", "Rebel"},
    supertypes={"Legendary"},
    text="Vigilance\nSnow Villiers's power is equal to the number of creatures you control.",
)

STILTZKIN_MOOGLE_MERCHANT = make_creature(
    name="Stiltzkin, Moogle Merchant",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Moogle"},
    supertypes={"Legendary"},
    text="Lifelink\n{2}, {T}: Target opponent gains control of another target permanent you control. If they do, you draw a card.",
)

SUMMON_CHOCOMOG = make_creature(
    name="Summon: Choco/Mog",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Moogle", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III, IV — Stampede! — Other creatures you control get +1/+0 until end of turn.",
)

SUMMON_KNIGHTS_OF_ROUND = make_creature(
    name="Summon: Knights of Round",
    power=3, toughness=3,
    mana_cost="{6}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after V.)\nI, II, III, IV — Create three 2/2 white Knight creature tokens.\nV — Ultimate End — Other creatures you control get +2/+2 until end of turn. Put an indestructible counter on each of them.\nIndestructible",
)

SUMMON_PRIMAL_GARUDA = make_creature(
    name="Summon: Primal Garuda",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Harpy", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Aerial Blast — This creature deals 4 damage to target tapped creature an opponent controls.\nII, III — Slipstream — Another target creature you control gets +1/+0 and gains flying until end of turn.\nFlying",
)

ULTIMA = make_sorcery(
    name="Ultima",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all artifacts and creatures. End the turn. (Exile all spells and abilities from the stack, including this card. The player whose turn it is discards down to their maximum hand size. Damage wears off, and \"this turn\" and \"until end of turn\" effects end.)",
)

VENAT_HEART_OF_HYDAELYN = make_creature(
    name="Venat, Heart of Hydaelyn",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Elder", "Legendary", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

WEAPONS_VENDOR = make_creature(
    name="Weapons Vendor",
    power=2, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Artificer", "Human"},
    text="When this creature enters, draw a card.\nAt the beginning of combat on your turn, if you control an Equipment, you may pay {1}. When you do, attach target Equipment you control to target creature you control.",
    setup_interceptors=weapons_vendor_setup,
)

WHITE_AURACITE = make_artifact(
    name="White Auracite",
    mana_cost="{2}{W}{W}",
    text="When this artifact enters, exile target nonland permanent an opponent controls until this artifact leaves the battlefield.\n{T}: Add {W}.",
    setup_interceptors=white_auracite_setup,
)

WHITE_MAGES_STAFF = make_artifact(
    name="White Mage's Staff",
    mana_cost="{1}{W}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+1, has \"Whenever this creature attacks, you gain 1 life,\" and is a Cleric in addition to its other types.\nEquip {3} ({3}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

THE_WIND_CRYSTAL = make_artifact(
    name="The Wind Crystal",
    mana_cost="{2}{W}{W}",
    text="White spells you cast cost {1} less to cast.\nIf you would gain life, you gain twice that much life instead.\n{4}{W}{W}, {T}: Creatures you control gain flying and lifelink until end of turn.",
    supertypes={"Legendary"},
)

YOURE_NOT_ALONE = make_instant(
    name="You're Not Alone",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If you control three or more creatures, it gets +4/+4 until end of turn instead.",
)

ZACK_FAIR = make_creature(
    name="Zack Fair",
    power=0, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Zack Fair enters with a +1/+1 counter on it.\n{1}, Sacrifice Zack Fair: Target creature you control gains indestructible until end of turn. Put Zack Fair's counters on that creature and attach an Equipment that was attached to Zack Fair to that creature.",
    setup_interceptors=zack_fair_setup,
)

ASTROLOGIANS_PLANISPHERE = make_artifact(
    name="Astrologian's Planisphere",
    mana_cost="{1}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature is a Wizard in addition to its other types and has \"Whenever you cast a noncreature spell and whenever you draw your third card each turn, put a +1/+1 counter on this creature.\"\nDiana — Equip {2}",
    subtypes={"Equipment"},
)

CARGO_SHIP = make_artifact(
    name="Cargo Ship",
    mana_cost="{1}{U}",
    text="Flying, vigilance\n{T}: Add {C}. Spend this mana only to cast an artifact spell or activate an ability of an artifact source.\nCrew 1 (Tap any number of creatures you control with total power 1 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

COMBAT_TUTORIAL = make_sorcery(
    name="Combat Tutorial",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target player draws two cards. Put a +1/+1 counter on up to one target creature you control.",
)

DRAGOONS_WYVERN = make_creature(
    name="Dragoon's Wyvern",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Drake"},
    text="Flying\nWhen this creature enters, create a 1/1 colorless Hero creature token.",
    setup_interceptors=dragoons_wyvern_setup,
)

DREAMS_OF_LAGUNA = make_instant(
    name="Dreams of Laguna",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Surveil 1, then draw a card. (To surveil 1, look at the top card of your library. You may put it into your graveyard.)\nFlashback {3}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

EDGAR_KING_OF_FIGARO = make_creature(
    name="Edgar, King of Figaro",
    power=4, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Artificer", "Human", "Noble"},
    supertypes={"Legendary"},
    text="When Edgar enters, draw a card for each artifact you control.\nTwo-Headed Coin — The first time you flip one or more coins each turn, those coins come up heads and you win those flips.",
    setup_interceptors=edgar_king_of_figaro_setup,
)

EJECT = make_instant(
    name="Eject",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="This spell can't be countered.\nReturn target nonland permanent to its owner's hand.\nDraw a card.",
)

ETHER = make_artifact(
    name="Ether",
    mana_cost="{3}{U}",
    text="{T}, Exile this artifact: Add {U}. When you next cast an instant or sorcery spell this turn, copy that spell. You may choose new targets for the copy.",
)

GOGO_MASTER_OF_MIMICRY = make_creature(
    name="Gogo, Master of Mimicry",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{X}{X}, {T}: Copy target activated or triggered ability you control X times. You may choose new targets for the copies. This ability can't be copied and X can't be 0. (Mana abilities can't be targeted.)",
)

ICE_FLAN = make_creature(
    name="Ice Flan",
    power=5, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Ooze"},
    text="When this creature enters, tap target artifact or creature an opponent controls. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nIslandcycling {2} ({2}, Discard this card: Search your library for an Island card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=ice_flan_setup,
)

ICE_MAGIC = make_instant(
    name="Ice Magic",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tiered (Choose one additional cost.)\n• Blizzard — {0} — Return target creature to its owner's hand.\n• Blizzara — {2} — Target creature's owner puts it on their choice of the top or bottom of their library.\n• Blizzaga — {5}{U} — Target creature's owner shuffles it into their library.",
)

IL_MHEG_PIXIE = make_creature(
    name="Il Mheg Pixie",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Faerie"},
    text="Flying\nWhenever this creature attacks, surveil 1. (Look at the top card of your library. You may put it into your graveyard.)",
    setup_interceptors=il_mheg_pixie_setup,
)

JILL_SHIVAS_DOMINANT = make_creature(
    name="Jill, Shiva's Dominant",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Legendary", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

LOUISOIXS_SACRIFICE = make_instant(
    name="Louisoix's Sacrifice",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="As an additional cost to cast this spell, sacrifice a legendary creature or pay {2}.\nCounter target activated ability, triggered ability, or noncreature spell.",
)

THE_LUNAR_WHALE = make_artifact(
    name="The Lunar Whale",
    mana_cost="{3}{U}",
    text="Flying\nYou may look at the top card of your library any time.\nAs long as The Lunar Whale attacked this turn, you may play the top card of your library.\nCrew 1",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

MAGIC_DAMPER = make_instant(
    name="Magic Damper",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature you control gets +1/+1 and gains hexproof until end of turn. Untap it.",
)

MATOYA_ARCHON_ELDER = make_creature(
    name="Matoya, Archon Elder",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you scry or surveil, draw a card. (Draw after you scry or surveil.)",
    setup_interceptors=matoya_archon_elder_setup,
)

MEMORIES_RETURNING = make_sorcery(
    name="Memories Returning",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Reveal the top five cards of your library. Put one of them into your hand. Then choose an opponent. They put one on the bottom of your library. Then you put one into your hand. Then they put one on the bottom of your library. Put the other into your hand.\nFlashback {7}{U}{U}",
)

THE_PRIMA_VISTA = make_artifact(
    name="The Prima Vista",
    mana_cost="{4}{U}",
    text="Flying\nWhenever you cast a noncreature spell, if at least four mana was spent to cast it, The Prima Vista becomes an artifact creature until end of turn.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

QIQIRN_MERCHANT = make_creature(
    name="Qiqirn Merchant",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Beast", "Citizen"},
    text="{1}, {T}: Draw a card, then discard a card.\n{7}, {T}, Sacrifice this creature: Draw three cards. This ability costs {1} less to activate for each Town you control.",
)

QUISTIS_TREPE = make_creature(
    name="Quistis Trepe",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Blue Magic — When Quistis Trepe enters, you may cast target instant or sorcery card from a graveyard, and mana of any type can be spent to cast that spell. If that spell would be put into a graveyard, exile it instead.",
    setup_interceptors=quistis_trepe_setup,
)

RELMS_SKETCHING = make_sorcery(
    name="Relm's Sketching",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target artifact, creature, or land.",
)

RETRIEVE_THE_ESPER = make_sorcery(
    name="Retrieve the Esper",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create a 3/3 blue Robot Warrior artifact creature token. Then if this spell was cast from a graveyard, put two +1/+1 counters on that token.\nFlashback {5}{U} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

ROOK_TURRET = make_artifact_creature(
    name="Rook Turret",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Flying\nWhenever another artifact you control enters, you may draw a card. If you do, discard a card.",
    setup_interceptors=rook_turret_setup,
)

SAGES_NOULITHS = make_artifact(
    name="Sage's Nouliths",
    mana_cost="{1}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0, has \"Whenever this creature attacks, untap target attacking creature,\" and is a Cleric in addition to its other types.\nHagneia — Equip {3}",
    subtypes={"Equipment"},
)

SAHAGIN = make_creature(
    name="Sahagin",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Warrior"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, put a +1/+1 counter on this creature and it can't be blocked this turn.",
)

SCORPION_SENTINEL = make_artifact_creature(
    name="Scorpion Sentinel",
    power=1, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Robot", "Scorpion"},
    text="As long as you control seven or more lands, this creature gets +3/+0.",
)

SIDEQUEST_CARD_COLLECTION = make_enchantment(
    name="Sidequest: Card Collection",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Vehicle"},
)

SLEEP_MAGIC = make_enchantment(
    name="Sleep Magic",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Enchant creature\nWhen this Aura enters, tap enchanted creature.\nEnchanted creature doesn't untap during its controller's untap step.\nWhen enchanted creature is dealt damage, sacrifice this Aura.",
    subtypes={"Aura"},
)

STOLEN_UNIFORM = make_instant(
    name="Stolen Uniform",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Choose target creature you control and target Equipment. Gain control of that Equipment until end of turn. Attach it to the chosen creature. When you lose control of that Equipment this turn, if it's attached to a creature you control, unattach it.",
)

STUCK_IN_SUMMONERS_SANCTUM = make_enchantment(
    name="Stuck in Summoner's Sanctum",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Flash\nEnchant artifact or creature\nWhen this Aura enters, tap enchanted permanent.\nEnchanted permanent doesn't untap during its controller's untap step and its activated abilities can't be activated.",
    subtypes={"Aura"},
)

SUMMON_LEVIATHAN = make_creature(
    name="Summon: Leviathan",
    power=6, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Leviathan", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Return each creature that isn't a Kraken, Leviathan, Merfolk, Octopus, or Serpent to its owner's hand.\nII, III — Until end of turn, whenever a Kraken, Leviathan, Merfolk, Octopus, or Serpent attacks, draw a card.\nWard {2}",
)

SUMMON_SHIVA = make_creature(
    name="Summon: Shiva",
    power=4, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI, II — Heavenly Strike — Tap target creature an opponent controls. Put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nIII — Diamond Dust — Draw a card for each tapped creature your opponents control.",
)

SWALLOWED_BY_LEVIATHAN = make_instant(
    name="Swallowed by Leviathan",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Choose target spell. Surveil 2, then counter the chosen spell unless its controller pays {1} for each card in your graveyard. (To surveil 2, look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
)

SYNCOPATE = make_instant(
    name="Syncopate",
    mana_cost="{X}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {X}. If that spell is countered this way, exile it instead of putting it into its owner's graveyard.",
)

THIEFS_KNIFE = make_artifact(
    name="Thief's Knife",
    mana_cost="{2}{U}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+1, has \"Whenever this creature deals combat damage to a player, draw a card,\" and is a Rogue in addition to its other types.\nEquip {4}",
    subtypes={"Equipment"},
)

TRAVEL_THE_OVERWORLD = make_sorcery(
    name="Travel the Overworld",
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    text="Affinity for Towns (This spell costs {1} less to cast for each Town you control.)\nDraw four cards.",
)

ULTROS_OBNOXIOUS_OCTOPUS = make_creature(
    name="Ultros, Obnoxious Octopus",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Octopus"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, tap target creature an opponent controls and put a stun counter on it. (If a permanent with a stun counter would become untapped, remove one from it instead.)\nWhenever you cast a noncreature spell, if at least eight mana was spent to cast it, put eight +1/+1 counters on Ultros.",
)

VALKYRIE_AERIAL_UNIT = make_artifact_creature(
    name="Valkyrie Aerial Unit",
    power=5, toughness=4,
    mana_cost="{5}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Affinity for artifacts (This spell costs {1} less to cast for each artifact you control.)\nFlying\nWhen this creature enters, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=valkyrie_aerial_unit_setup,
)

THE_WATER_CRYSTAL = make_artifact(
    name="The Water Crystal",
    mana_cost="{2}{U}{U}",
    text="Blue spells you cast cost {1} less to cast.\nIf an opponent would mill one or more cards, they mill that many cards plus four instead.\n{4}{U}{U}, {T}: Each opponent mills cards equal to the number of cards in your hand.",
    supertypes={"Legendary"},
)

YSHTOLA_RHUL = make_creature(
    name="Y'shtola Rhul",
    power=3, toughness=5,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Cat", "Druid"},
    supertypes={"Legendary"},
    text="At the beginning of your end step, exile target creature you control, then return it to the battlefield under its owner's control. Then if it's the first end step of the turn, there is an additional end step after this step.",
)

AHRIMAN = make_creature(
    name="Ahriman",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Eye", "Horror"},
    text="Flying, deathtouch\n{3}, Sacrifice another creature or artifact: Draw a card.",
)

AL_BHED_SALVAGERS = make_creature(
    name="Al Bhed Salvagers",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Artificer", "Human", "Warrior"},
    text="Whenever this creature or another creature or artifact you control dies, target opponent loses 1 life and you gain 1 life.",
    setup_interceptors=al_bhed_salvagers_setup,
)

ARDYN_THE_USURPER = make_creature(
    name="Ardyn, the Usurper",
    power=4, toughness=4,
    mana_cost="{5}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elder", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Demons you control have menace, lifelink, and haste.\nStarscourge — At the beginning of combat on your turn, exile up to one target creature card from a graveyard. If you exiled a card this way, create a token that's a copy of that card, except it's a 5/5 black Demon.",
)

BLACK_MAGES_ROD = make_artifact(
    name="Black Mage's Rod",
    mana_cost="{1}{B}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0, has \"Whenever you cast a noncreature spell, this creature deals 1 damage to each opponent,\" and is a Wizard in addition to its other types.\nEquip {3}",
    subtypes={"Equipment"},
)

CECIL_DARK_KNIGHT = make_creature(
    name="Cecil, Dark Knight",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Knight", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

CIRCLE_OF_POWER = make_sorcery(
    name="Circle of Power",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="You draw two cards and you lose 2 life. Create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"\nWizards you control get +1/+0 and gain lifelink until end of turn.",
)

CORNERED_BY_BLACK_MAGES = make_sorcery(
    name="Cornered by Black Mages",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Target opponent sacrifices a creature of their choice.\nCreate a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
)

DARK_CONFIDANT = make_creature(
    name="Dark Confidant",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Wizard"},
    text="At the beginning of your upkeep, reveal the top card of your library and put that card into your hand. You lose life equal to its mana value.",
    setup_interceptors=dark_confidant_setup,
)

DARK_KNIGHTS_GREATSWORD = make_artifact(
    name="Dark Knight's Greatsword",
    mana_cost="{2}{B}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +3/+0 and is a Knight in addition to its other types.\nChaosbringer — Equip—Pay 3 life. Activate only once each turn.",
    subtypes={"Equipment"},
)

THE_DARKNESS_CRYSTAL = make_artifact(
    name="The Darkness Crystal",
    mana_cost="{2}{B}{B}",
    text="Black spells you cast cost {1} less to cast.\nIf a nontoken creature an opponent controls would die, instead exile it and you gain 2 life.\n{4}{B}{B}, {T}: Put target creature card exiled with The Darkness Crystal onto the battlefield tapped under your control with two additional +1/+1 counters on it.",
    supertypes={"Legendary"},
)

DEMON_WALL = make_artifact_creature(
    name="Demon Wall",
    power=3, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Wall"},
    text="Defender\nMenace (This creature can't be blocked except by two or more creatures.)\nAs long as this creature has a counter on it, it can attack as though it didn't have defender.\n{5}{B}: Put two +1/+1 counters on this creature.",
)

EVIL_REAWAKENED = make_sorcery(
    name="Evil Reawakened",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield with two additional +1/+1 counters on it.",
)

FANG_FEARLESS_LCIE = make_creature(
    name="Fang, Fearless l'Cie",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever one or more cards leave your graveyard, you draw a card and you lose 1 life. This ability triggers only once each turn.\n(Melds with Vanille, Cheerful l'Cie.)",
)

RAGNAROK_DIVINE_DELIVERANCE = make_creature(
    name="Ragnarok, Divine Deliverance",
    power=7, toughness=6,
    mana_cost="",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Avatar", "Beast"},
    supertypes={"Legendary"},
    text="Vigilance, menace, trample, reach, haste\nWhen Ragnarok dies, destroy target permanent and return target nonlegendary permanent card from your graveyard to the battlefield.",
)

FIGHT_ON = make_instant(
    name="Fight On!",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand.",
)

THE_FINAL_DAYS = make_sorcery(
    name="The Final Days",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Create two tapped 2/2 black Horror creature tokens. If this spell was cast from a graveyard, instead create X of those tokens, where X is the number of creature cards in your graveyard.\nFlashback {4}{B}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

GAIUS_VAN_BAELSAR = make_creature(
    name="Gaius van Baelsar",
    power=3, toughness=2,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="When Gaius van Baelsar enters, choose one —\n• Each player sacrifices a creature token of their choice.\n• Each player sacrifices a nontoken creature of their choice.\n• Each player sacrifices an enchantment of their choice.",
)

HECTEYES = make_creature(
    name="Hecteyes",
    power=1, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Ooze"},
    text="When this creature enters, each opponent discards a card.",
    setup_interceptors=hecteyes_setup,
)

JECHT_RELUCTANT_GUARDIAN = make_creature(
    name="Jecht, Reluctant Guardian",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Legendary", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

KAIN_TRAITOROUS_DRAGOON = make_creature(
    name="Kain, Traitorous Dragoon",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Jump — During your turn, Kain has flying.\nWhenever Kain deals combat damage to a player, that player gains control of Kain. If they do, you draw that many cards, create that many tapped Treasure tokens, then lose that much life.",
)

MALBORO = make_creature(
    name="Malboro",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Plant"},
    text="Bad Breath — When this creature enters, each opponent discards a card, loses 2 life, and exiles the top three cards of their library.\nSwampcycling {2} ({2}, Discard this card: Search your library for a Swamp card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=malboro_setup,
)

NAMAZU_TRADER = make_creature(
    name="Namazu Trader",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Citizen", "Fish"},
    text="When this creature enters, you lose 1 life and create a Treasure token.\nWhenever this creature attacks, you may sacrifice another creature or artifact. If you do, surveil 2. (Look at the top two cards of your library, then put any number of them into your graveyard and the rest on top of your library in any order.)",
    setup_interceptors=namazu_trader_setup,
)

NINJAS_BLADES = make_artifact(
    name="Ninja's Blades",
    mana_cost="{2}{B}",
    text="Job select\nEquipped creature gets +1/+1, is a Ninja in addition to its other types, and has \"Whenever this creature deals combat damage to a player, draw a card, then discard a card. That player loses life equal to the discarded card's mana value.\"\nMutsunokami — Equip {2}",
    subtypes={"Equipment"},
)

OVERKILL = make_instant(
    name="Overkill",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target creature gets -0/-9999 until end of turn.",
)

PHANTOM_TRAIN = make_artifact(
    name="Phantom Train",
    mana_cost="{3}{B}",
    text="Trample\nSacrifice another artifact or creature: Put a +1/+1 counter on this Vehicle. It becomes a Spirit artifact creature in addition to its other types until end of turn.",
    subtypes={"Vehicle"},
)

POISON_THE_WATERS = make_sorcery(
    name="Poison the Waters",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Choose one —\n• All creatures get -1/-1 until end of turn.\n• Target player reveals their hand. You choose an artifact or creature card from it. That player discards that card.",
)

QUTRUB_FORAYER = make_creature(
    name="Qutrub Forayer",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Zombie"},
    text="When this creature enters, choose one —\n• Destroy target creature that was dealt damage this turn.\n• Exile up to two target cards from a single graveyard.",
)

RENO_AND_RUDE = make_creature(
    name="Reno and Rude",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Assassin", "Human"},
    supertypes={"Legendary"},
    text="Menace\nWhenever Reno and Rude deals combat damage to a player, exile the top card of that player's library. Then you may sacrifice another creature or artifact. If you do, you may play the exiled card this turn, and mana of any type can be spent to cast it.",
)

RESENTFUL_REVELATION = make_sorcery(
    name="Resentful Revelation",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard.\nFlashback {6}{B} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SEPHIROTH_FABLED_SOLDIER = make_creature(
    name="Sephiroth, Fabled SOLDIER",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Avatar", "Creature", "Human", "Legendary", "Soldier"},
    supertypes={"Legendary"},
    text="",
)

SEPHIROTHS_INTERVENTION = make_instant(
    name="Sephiroth's Intervention",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. You gain 2 life.",
)

SHAMBLING_CIETH = make_creature(
    name="Shambling Cie'th",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Mutant"},
    text="This creature enters tapped.\nWhenever you cast a noncreature spell, you may pay {B}. If you do, return this card from your graveyard to your hand.",
)

SHINRA_REINFORCEMENTS = make_creature(
    name="Shinra Reinforcements",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Soldier"},
    text="When this creature enters, mill three cards and you gain 3 life. (To mill three cards, put the top three cards of your library into your graveyard.)",
    setup_interceptors=shinra_reinforcements_setup,
)

SIDEQUEST_HUNT_THE_MARK = make_creature(
    name="Sidequest: Hunt the Mark",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Dragon"},
    supertypes={"Legendary"},
    text="",
)

SUMMON_ANIMA = make_creature(
    name="Summon: Anima",
    power=4, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II, III — Pain — You draw a card and you lose 1 life.\nIV — Oblivion — Each opponent sacrifices a creature of their choice and loses 3 life.\nMenace",
)

SUMMON_PRIMAL_ODIN = make_creature(
    name="Summon: Primal Odin",
    power=5, toughness=3,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Gungnir — Destroy target creature an opponent controls.\nII — Zantetsuken — This creature gains \"Whenever this creature deals combat damage to a player, that player loses the game.\"\nIII — Hall of Sorrow — Draw two cards. Each player loses 2 life.",
)

TONBERRY = make_creature(
    name="Tonberry",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Horror", "Salamander"},
    text="This creature enters tapped with a stun counter on it. (If it would become untapped, remove a stun counter from it instead.)\nChef's Knife — During your turn, this creature has first strike and deathtouch.",
)

UNDERCITY_DIRE_RAT = make_creature(
    name="Undercity Dire Rat",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="Rat Tail — When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")",
    setup_interceptors=undercity_dire_rat_setup,
)

VAYNES_TREACHERY = make_instant(
    name="Vayne's Treachery",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Kicker—Sacrifice an artifact or creature. (You may sacrifice an artifact or creature in addition to any other costs as you cast this spell.)\nTarget creature gets -2/-2 until end of turn. If this spell was kicked, that creature gets -6/-6 until end of turn instead.",
)

VINCENT_VALENTINE = make_creature(
    name="Vincent Valentine",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Assassin", "Creature", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

VINCENTS_LIMIT_BREAK = make_instant(
    name="Vincent's Limit Break",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Tiered (Choose one additional cost.)\nUntil end of turn, target creature you control gains \"When this creature dies, return it to the battlefield tapped under its owner's control\" and has the chosen base power and toughness.\n• Galian Beast — {0} — 3/2.\n• Death Gigas — {1} — 5/2.\n• Hellmasker — {3} — 7/2.",
)

ZENOS_YAE_GALVUS = make_creature(
    name="Zenos yae Galvus",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

ZODIARK_UMBRAL_GOD = make_creature(
    name="Zodiark, Umbral God",
    power=5, toughness=5,
    mana_cost="{B}{B}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"God"},
    supertypes={"Legendary"},
    text="Indestructible\nWhen Zodiark enters, each player sacrifices half the non-God creatures they control of their choice, rounded down.\nWhenever a player sacrifices another creature, put a +1/+1 counter on Zodiark.",
    setup_interceptors=zodiark_umbral_god_setup,
)

BARRET_WALLACE = make_creature(
    name="Barret Wallace",
    power=4, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel"},
    supertypes={"Legendary"},
    text="Reach\nWhenever Barret Wallace attacks, it deals damage equal to the number of equipped creatures you control to defending player.",
    setup_interceptors=barret_wallace_setup,
)

BLAZING_BOMB = make_creature(
    name="Blazing Bomb",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Whenever you cast a noncreature spell, if at least four mana was spent to cast it, put a +1/+1 counter on this creature.\nBlow Up — {T}, Sacrifice this creature: It deals damage equal to its power to target creature. Activate only as a sorcery.",
)

CALL_THE_MOUNTAIN_CHOCOBO = make_sorcery(
    name="Call the Mountain Chocobo",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Search your library for a Mountain card, reveal it, put it into your hand, then shuffle. Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nFlashback {5}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

CHOCOCOMET = make_sorcery(
    name="Choco-Comet",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Choco-Comet deals X damage to any target.\nCreate a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"",
)

CLIVE_IFRITS_DOMINANT = make_creature(
    name="Clive, Ifrit's Dominant",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Legendary", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="",
)

CORAL_SWORD = make_artifact(
    name="Coral Sword",
    mana_cost="{R}",
    text="Flash\nWhen this Equipment enters, attach it to target creature you control. That creature gains first strike until end of turn.\nEquipped creature gets +1/+0.\nEquip {1}",
    subtypes={"Equipment"},
)

THE_FIRE_CRYSTAL = make_artifact(
    name="The Fire Crystal",
    mana_cost="{2}{R}{R}",
    text="Red spells you cast cost {1} less to cast.\nCreatures you control have haste.\n{4}{R}{R}, {T}: Create a token that's a copy of target creature you control. Sacrifice it at the beginning of the next end step.",
    supertypes={"Legendary"},
    setup_interceptors=fire_crystal_setup,
)

FIRE_MAGIC = make_instant(
    name="Fire Magic",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tiered (Choose one additional cost.)\n• Fire — {0} — Fire Magic deals 1 damage to each creature.\n• Fira — {2} — Fire Magic deals 2 damage to each creature.\n• Firaga — {5} — Fire Magic deals 3 damage to each creature.",
)

FIRION_WILD_ROSE_WARRIOR = make_creature(
    name="Firion, Wild Rose Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel", "Warrior"},
    supertypes={"Legendary"},
    text="Equipped creatures you control have haste.\nWhenever a nontoken Equipment you control enters, create a token that's a copy of it, except it has \"This Equipment's equip abilities cost {2} less to activate.\" Sacrifice that token at the beginning of the next upkeep.",
    setup_interceptors=firion_wild_rose_warrior_setup,
)

FREYA_CRESCENT = make_creature(
    name="Freya Crescent",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Knight", "Rat"},
    supertypes={"Legendary"},
    text="Jump — During your turn, Freya Crescent has flying.\n{T}: Add {R}. Spend this mana only to cast an Equipment spell or activate an equip ability.",
)

GILGAMESH_MASTERATARMS = make_creature(
    name="Gilgamesh, Master-at-Arms",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Samurai"},
    supertypes={"Legendary"},
    text="Whenever Gilgamesh enters or attacks, look at the top six cards of your library. You may put any number of Equipment cards from among them onto the battlefield. Put the rest on the bottom of your library in a random order. When you put one or more Equipment onto the battlefield this way, you may attach one of them to a Samurai you control.",
    setup_interceptors=gilgamesh_master_at_arms_setup,
)

HASTE_MAGIC = make_instant(
    name="Haste Magic",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+1 and gains haste until end of turn. Exile the top card of your library. You may play it until your next end step.",
)

HILL_GIGAS = make_creature(
    name="Hill Gigas",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Trample, haste\nMountaincycling {2} ({2}, Discard this card: Search your library for a Mountain card, reveal it, put it into your hand, then shuffle.)",
)

ITEM_SHOPKEEP = make_creature(
    name="Item Shopkeep",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Citizen", "Human"},
    text="Whenever you attack, target attacking equipped creature gains menace until end of turn. (It can't be blocked except by two or more creatures.)",
)

LAUGHING_MAD = make_instant(
    name="Laughing Mad",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="As an additional cost to cast this spell, discard a card.\nDraw two cards.\nFlashback {3}{R} (You may cast this card from your graveyard for its flashback cost and any additional costs. Then exile it.)",
)

LIGHT_OF_JUDGMENT = make_instant(
    name="Light of Judgment",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Light of Judgment deals 6 damage to target creature. Destroy up to one Equipment attached to that creature.",
)

MYSIDIAN_ELDER = make_creature(
    name="Mysidian Elder",
    power=1, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    text="When this creature enters, create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
    setup_interceptors=mysidian_elder_setup,
)

NIBELHEIM_AFLAME = make_sorcery(
    name="Nibelheim Aflame",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Choose target creature you control. It deals damage equal to its power to each other creature. If this spell was cast from a graveyard, discard your hand and draw four cards.\nFlashback {5}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

OPERA_LOVE_SONG = make_instant(
    name="Opera Love Song",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Exile the top two cards of your library. You may play those cards until your next end step.\n• One or two target creatures each get +2/+0 until end of turn.",
)

PROMPTO_ARGENTUM = make_creature(
    name="Prompto Argentum",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Haste\nSelfie Shot — Whenever you cast a noncreature spell, if at least four mana was spent to cast it, create a Treasure token.",
)

QUEEN_BRAHNE = make_creature(
    name="Queen Brahne",
    power=2, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\nWhenever Queen Brahne attacks, create a 0/1 black Wizard creature token with \"Whenever you cast a noncreature spell, this token deals 1 damage to each opponent.\"",
    setup_interceptors=queen_brahne_setup,
)

RANDOM_ENCOUNTER = make_sorcery(
    name="Random Encounter",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Shuffle your library, then mill four cards. Put each creature card milled this way onto the battlefield. They gain haste. At the beginning of the next end step, return those creatures to their owner's hand.\nFlashback {6}{R}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

RAUBAHN_BULL_OF_ALA_MHIGO = make_creature(
    name="Raubahn, Bull of Ala Mhigo",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Ward—Pay life equal to Raubahn's power.\nWhenever Raubahn attacks, attach up to one target Equipment you control to target attacking creature.",
)

RED_MAGES_RAPIER = make_artifact(
    name="Red Mage's Rapier",
    mana_cost="{1}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature has \"Whenever you cast a noncreature spell, this creature gets +2/+0 until end of turn\" and is a Wizard in addition to its other types.\nEquip {3}",
    subtypes={"Equipment"},
)

SABOTENDER = make_creature(
    name="Sabotender",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Plant"},
    text="Reach\nLandfall — Whenever a land you control enters, this creature deals 1 damage to each opponent.",
    setup_interceptors=sabotender_setup,
)

SAMURAIS_KATANA = make_artifact(
    name="Samurai's Katana",
    mana_cost="{2}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2, has trample and haste, and is a Samurai in addition to its other types.\nMurasame — Equip {5}",
    subtypes={"Equipment"},
)

SANDWORM = make_creature(
    name="Sandworm",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Worm"},
    text="Haste\nWhen this creature enters, destroy target land. Its controller may search their library for a basic land card, put it onto the battlefield tapped, then shuffle.",
)

SEIFER_ALMASY = make_creature(
    name="Seifer Almasy",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Whenever a creature you control attacks alone, it gains double strike until end of turn.\nFire Cross — Whenever Seifer Almasy deals combat damage to a player, you may cast target instant or sorcery card with mana value 3 or less from your graveyard without paying its mana cost. If that spell would be put into your graveyard, exile it instead.",
)

SELFDESTRUCT = make_instant(
    name="Self-Destruct",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control deals X damage to any other target and X damage to itself, where X is its power.",
)

SIDEQUEST_PLAY_BLITZBALL = make_enchantment(
    name="Sidequest: Play Blitzball",
    mana_cost="",
    colors=set(),
    text="",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

SORCERESSS_SCHEMES = make_sorcery(
    name="Sorceress's Schemes",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Return target instant or sorcery card from your graveyard or exiled card with flashback you own to your hand. Add {R}.\nFlashback {4}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

SUMMON_BRYNHILDR = make_creature(
    name="Summon: Brynhildr",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Knight", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Chain — Exile the top card of your library. During any turn you put a lore counter on this Saga, you may play that card.\nII, III — Gestalt Mode — When you next cast a creature spell this turn, it gains haste until end of turn.",
)

SUMMON_ESPER_RAMUH = make_creature(
    name="Summon: Esper Ramuh",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Saga", "Wizard"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Judgment Bolt — This creature deals damage equal to the number of noncreature, nonland cards in your graveyard to target creature an opponent controls.\nII, III — Wizards you control get +1/+0 until end of turn.",
)

SUMMON_GF_CERBERUS = make_creature(
    name="Summon: G.F. Cerberus",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Dog", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\nII — Double — When you next cast an instant or sorcery spell this turn, copy it. You may choose new targets for the copy.\nIII — Triple — When you next cast an instant or sorcery spell this turn, copy it twice. You may choose new targets for the copies.",
)

SUMMON_GF_IFRIT = make_creature(
    name="Summon: G.F. Ifrit",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Demon", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI, II — You may discard a card. If you do, draw a card.\nIII, IV — Add {R}.",
)

SUPLEX = make_sorcery(
    name="Suplex",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Choose one —\n• Suplex deals 3 damage to target creature. If that creature would die this turn, exile it instead.\n• Exile target artifact.",
)

THUNDER_MAGIC = make_instant(
    name="Thunder Magic",
    mana_cost="{R}",
    colors={Color.RED},
    text="Tiered (Choose one additional cost.)\n• Thunder — {0} — Thunder Magic deals 2 damage to target creature.\n• Thundara — {3} — Thunder Magic deals 4 damage to target creature.\n• Thundaga — {5}{R} — Thunder Magic deals 8 damage to target creature.",
)

TRIPLE_TRIAD = make_enchantment(
    name="Triple Triad",
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, each player exiles the top card of their library. Until end of turn, you may play the card you own exiled this way and each other card exiled this way with lesser mana value than it without paying their mana costs.",
)

UNEXPECTED_REQUEST = make_sorcery(
    name="Unexpected Request",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. You may attach an Equipment you control to that creature. If you do, unattach it at the beginning of the next end step.",
)

VAAN_STREET_THIEF = make_creature(
    name="Vaan, Street Thief",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Scout"},
    supertypes={"Legendary"},
    text="Whenever one or more Scouts, Pirates, and/or Rogues you control deal combat damage to a player, exile the top card of that player's library. You may cast it. If you don't, create a Treasure token.\nWhenever you cast a spell you don't own, put a +1/+1 counter on each Scout, Pirate, and Rogue you control.",
)

WARRIORS_SWORD = make_artifact(
    name="Warrior's Sword",
    mana_cost="{3}{R}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +3/+2 and is a Warrior in addition to its other types.\nEquip {5} ({5}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

ZELL_DINCHT = make_creature(
    name="Zell Dincht",
    power=0, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="You may play an additional land on each of your turns.\nZell Dincht gets +1/+0 for each land you control.\nAt the beginning of your end step, return a land you control to its owner's hand.",
)

AIRSHIP_CRASH = make_instant(
    name="Airship Crash",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact, enchantment, or creature with flying.\nCycling {2} ({2}, Discard this card: Draw a card.)",
)

ANCIENT_ADAMANTOISE = make_creature(
    name="Ancient Adamantoise",
    power=8, toughness=20,
    mana_cost="{5}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Turtle"},
    text="Vigilance, ward {3}\nDamage isn't removed from this creature during cleanup steps.\nAll damage that would be dealt to you and other permanents you control is dealt to this creature instead.\nWhen this creature dies, exile it and create ten tapped Treasure tokens.",
    setup_interceptors=ancient_adamantoise_setup,
)

BALAMB_TREXAUR = make_creature(
    name="Balamb T-Rexaur",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample\nWhen this creature enters, you gain 3 life.\nForestcycling {2} ({2}, Discard this card: Search your library for a Forest card, reveal it, put it into your hand, then shuffle.)",
    setup_interceptors=balamb_trexaur_setup,
)

BARDS_BOW = make_artifact(
    name="Bard's Bow",
    mana_cost="{2}{G}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +2/+2, has reach, and is a Bard in addition to its other types.\nPerseus's Bow — Equip {6} ({6}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

BARTZ_AND_BOKO = make_creature(
    name="Bartz and Boko",
    power=4, toughness=3,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Human"},
    supertypes={"Legendary"},
    text="Affinity for Birds (This spell costs {1} less to cast for each Bird you control.)\nWhen Bartz and Boko enters, each other Bird you control deals damage equal to its power to target creature an opponent controls.",
    setup_interceptors=bartz_and_boko_setup,
)

BLITZBALL_SHOT = make_instant(
    name="Blitzball Shot",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn.",
)

CACTUAR = make_creature(
    name="Cactuar",
    power=3, toughness=3,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Trample\nAt the beginning of your end step, if this creature didn't enter the battlefield this turn, return it to its owner's hand.",
)

CHOCOBO_KICK = make_sorcery(
    name="Chocobo Kick",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Kicker—Return a land you control to its owner's hand. (You may return a land you control to its owner's hand in addition to any other costs as you cast this spell.)\nTarget creature you control deals damage equal to its power to target creature an opponent controls. If this spell was kicked, the creature you control deals twice that much damage instead.",
)

CHOCOBO_RACETRACK = make_artifact(
    name="Chocobo Racetrack",
    mana_cost="{3}{G}{G}",
    text="Landfall — Whenever a land you control enters, create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"",
    setup_interceptors=chocobo_racetrack_setup,
)

CLASH_OF_THE_EIKONS = make_sorcery(
    name="Clash of the Eikons",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Choose one or more —\n• Target creature you control fights target creature an opponent controls.\n• Remove a lore counter from target Saga you control. (Removing lore counters doesn't cause chapter abilities to trigger.)\n• Put a lore counter on target Saga you control.",
)

COLISEUM_BEHEMOTH = make_creature(
    name="Coliseum Behemoth",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample\nWhen this creature enters, choose one —\n• Destroy target artifact or enchantment.\n• Draw a card.",
    setup_interceptors=coliseum_behemoth_setup,
)

COMMUNE_WITH_BEAVERS = make_sorcery(
    name="Commune with Beavers",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Look at the top three cards of your library. You may reveal an artifact, creature, or land card from among them and put it into your hand. Put the rest on the bottom of your library in any order.",
)

DIAMOND_WEAPON = make_artifact_creature(
    name="Diamond Weapon",
    power=8, toughness=8,
    mana_cost="{7}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elemental"},
    supertypes={"Legendary"},
    text="This spell costs {1} less to cast for each permanent card in your graveyard.\nReach\nImmune — Prevent all combat damage that would be dealt to Diamond Weapon.",
)

THE_EARTH_CRYSTAL = make_artifact(
    name="The Earth Crystal",
    mana_cost="{2}{G}{G}",
    text="Green spells you cast cost {1} less to cast.\nIf one or more +1/+1 counters would be put on a creature you control, twice that many +1/+1 counters are put on that creature instead.\n{4}{G}{G}, {T}: Distribute two +1/+1 counters among one or two target creatures you control.",
    supertypes={"Legendary"},
)

ESPER_ORIGINS = make_creature(
    name="Esper Origins",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Elemental", "Saga"},
    text="",
)

GALUFS_FINAL_ACT = make_instant(
    name="Galuf's Final Act",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Until end of turn, target creature gets +1/+0 and gains \"When this creature dies, put a number of +1/+1 counters equal to its power on up to one target creature.\"",
)

GIGANTOAD = make_creature(
    name="Gigantoad",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Frog"},
    text="As long as you control seven or more lands, this creature gets +2/+2.",
)

GOOBBUE_GARDENER = make_creature(
    name="Goobbue Gardener",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="{T}: Add {G}.",
)

GRAN_PULSE_OCHU = make_creature(
    name="Gran Pulse Ochu",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Plant"},
    text="Deathtouch\n{8}: Until end of turn, this creature gets +1/+1 for each permanent card in your graveyard.",
)

GYSAHL_GREENS = make_sorcery(
    name="Gysahl Greens",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nFlashback {6}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.)",
)

JUMBO_CACTUAR = make_creature(
    name="Jumbo Cactuar",
    power=1, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="10,000 Needles — Whenever this creature attacks, it gets +9999/+0 until end of turn.",
)

LOPORRIT_SCOUT = make_creature(
    name="Loporrit Scout",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rabbit", "Scout"},
    text="Whenever another creature you control enters, this creature gets +1/+1 until end of turn.",
    setup_interceptors=loporrit_scout_setup,
)

PRISHES_WANDERINGS = make_instant(
    name="Prishe's Wanderings",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card or Town card, put it onto the battlefield tapped, then shuffle. When you search your library this way, put a +1/+1 counter on target creature you control.",
)

QUINA_QU_GOURMET = make_creature(
    name="Quina, Qu Gourmet",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Qu"},
    supertypes={"Legendary"},
    text="If one or more tokens would be created under your control, those tokens plus a 1/1 green Frog creature token are created instead.\n{2}, Sacrifice a Frog: Put a +1/+1 counter on Quina.",
)

REACH_THE_HORIZON = make_sorcery(
    name="Reach the Horizon",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards and/or Town cards with different names, put them onto the battlefield tapped, then shuffle.",
)

A_REALM_REBORN = make_enchantment(
    name="A Realm Reborn",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Other permanents you control have \"{T}: Add one mana of any color.\"",
)

RIDE_THE_SHOOPUF = make_enchantment(
    name="Ride the Shoopuf",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature you control.\n{5}{G}{G}: This enchantment becomes a 7/7 Beast creature in addition to its other types.",
)

RYDIAS_RETURN = make_sorcery(
    name="Rydia's Return",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Choose one —\n• Creatures you control get +3/+3 until end of turn.\n• Return up to two target permanent cards from your graveyard to your hand.",
)

SAZH_KATZROY = make_creature(
    name="Sazh Katzroy",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pilot"},
    supertypes={"Legendary"},
    text="When Sazh Katzroy enters, you may search your library for a Bird or basic land card, reveal it, put it into your hand, then shuffle.\nWhenever Sazh Katzroy attacks, put a +1/+1 counter on target creature, then double the number of +1/+1 counters on that creature.",
)

SAZHS_CHOCOBO = make_creature(
    name="Sazh's Chocobo",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Landfall — Whenever a land you control enters, put a +1/+1 counter on this creature.",
)

SIDEQUEST_RAISE_A_CHOCOBO = make_creature(
    name="Sidequest: Raise a Chocobo",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"Bird"},
    text="",
)

SUMMON_FAT_CHOCOBO = make_creature(
    name="Summon: Fat Chocobo",
    power=4, toughness=4,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Bird", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after IV.)\nI — Wark — Create a 2/2 green Bird creature token with \"Whenever a land you control enters, this token gets +1/+0 until end of turn.\"\nII, III, IV — Kerplunk — Creatures you control gain trample until end of turn.",
)

SUMMON_FENRIR = make_creature(
    name="Summon: Fenrir",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Saga", "Wolf"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Crescent Fang — Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.\nII — Heavenward Howl — When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it.\nIII — Ecliptic Growl — Draw a card if you control the creature with the greatest power or tied for the greatest power.",
)

SUMMON_TITAN = make_creature(
    name="Summon: Titan",
    power=7, toughness=7,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Saga"},
    text="(As this Saga enters and after your draw step, add a lore counter. Sacrifice after III.)\nI — Mill five cards.\nII — Return all land cards from your graveyard to the battlefield tapped.\nIII — Until end of turn, another target creature you control gains trample and gets +X/+X, where X is the number of lands you control.\nReach, trample",
)

SUMMONERS_GRIMOIRE = make_artifact(
    name="Summoner's Grimoire",
    mana_cost="{3}{G}",
    text="Job select\nEquipped creature is a Shaman in addition to its other types and has \"Whenever this creature attacks, you may put a creature card from your hand onto the battlefield. If that card is an enchantment card, it enters tapped and attacking.\"\nAbraxas — Equip {3}",
    subtypes={"Equipment"},
)

TIFA_LOCKHART = make_creature(
    name="Tifa Lockhart",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Monk"},
    supertypes={"Legendary"},
    text="Trample\nLandfall — Whenever a land you control enters, double Tifa Lockhart's power until end of turn.",
    setup_interceptors=tifa_lockhart_setup,
)

TIFAS_LIMIT_BREAK = make_instant(
    name="Tifa's Limit Break",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Tiered (Choose one additional cost.)\n• Somersault — {0} — Target creature gets +2/+2 until end of turn.\n• Meteor Strikes — {2} — Double target creature's power and toughness until end of turn.\n• Final Heaven — {6}{G} — Triple target creature's power and toughness until end of turn.",
)

TORGAL_A_FINE_HOUND = make_creature(
    name="Torgal, A Fine Hound",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    supertypes={"Legendary"},
    text="Whenever you cast your first Human creature spell each turn, that creature enters with an additional +1/+1 counter on it for each Dog and/or Wolf you control.\n{T}: Add one mana of any color.",
)

TOWN_GREETER = make_creature(
    name="Town Greeter",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Citizen", "Human"},
    text="When this creature enters, mill four cards. You may put a land card from among them into your hand. If you put a Town card into your hand this way, you gain 2 life. (To mill four cards, a player puts the top four cards of their library into their graveyard.)",
    setup_interceptors=town_greeter_setup,
)

TRAVELING_CHOCOBO = make_creature(
    name="Traveling Chocobo",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="You may look at the top card of your library any time.\nYou may play lands and cast Bird spells from the top of your library.\nIf a land or Bird you control entering the battlefield causes a triggered ability of a permanent you control to trigger, that ability triggers an additional time.",
)

VANILLE_CHEERFUL_LCIE = make_creature(
    name="Vanille, Cheerful l'Cie",
    power=3, toughness=2,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="When Vanille enters, mill two cards, then return a permanent card from your graveyard to your hand.\nAt the beginning of your first main phase, if you both own and control Vanille and a creature named Fang, Fearless l'Cie, you may pay {3}{B}{G}. If you do, exile them, then meld them into Ragnarok, Divine Deliverance.",
)

ABSOLUTE_VIRTUE = make_creature(
    name="Absolute Virtue",
    power=8, toughness=8,
    mana_cost="{6}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Avatar", "Warrior"},
    supertypes={"Legendary"},
    text="This spell can't be countered.\nFlying\nYou have protection from each of your opponents. (You can't be dealt damage, enchanted, or targeted by anything controlled by your opponents.)",
)

BALTHIER_AND_FRAN = make_creature(
    name="Balthier and Fran",
    power=4, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Rabbit"},
    supertypes={"Legendary"},
    text="Reach\nVehicles you control get +1/+1 and have vigilance and reach.\nWhenever a Vehicle crewed by Balthier and Fran this turn attacks, if it's the first combat phase of the turn, you may pay {1}{R}{G}. If you do, after this phase, there is an additional combat phase.",
)

BLACK_WALTZ_NO_3 = make_creature(
    name="Black Waltz No. 3",
    power=2, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="Flying, deathtouch\nWhenever you cast a noncreature spell, Black Waltz No. 3 deals 2 damage to each opponent.",
)

CHOCO_SEEKER_OF_PARADISE = make_creature(
    name="Choco, Seeker of Paradise",
    power=3, toughness=5,
    mana_cost="{1}{G}{W}{U}",
    colors={Color.GREEN, Color.BLUE, Color.WHITE},
    subtypes={"Bird"},
    supertypes={"Legendary"},
    text="Whenever one or more Birds you control attack, look at that many cards from the top of your library. You may put one of them into your hand. Then put any number of land cards from among them onto the battlefield tapped and the rest into your graveyard.\nLandfall — Whenever a land you control enters, Choco gets +1/+0 until end of turn.",
)

CID_TIMELESS_ARTIFICER = make_creature(
    name="Cid, Timeless Artificer",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Artificer", "Human"},
    supertypes={"Legendary"},
    text="Artifact creatures and Heroes you control get +1/+1 for each Artificer you control and each Artificer card in your graveyard.\nA deck can have any number of cards named Cid, Timeless Artificer.\nCycling {W}{U} ({W}{U}, Discard this card: Draw a card.)",
)

CLOUD_OF_DARKNESS = make_creature(
    name="Cloud of Darkness",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Avatar"},
    supertypes={"Legendary"},
    text="Flying\nParticle Beam — When Cloud of Darkness enters, target creature an opponent controls gets -X/-X until end of turn, where X is the number of permanent cards in your graveyard.",
)

EMETSELCH_UNSUNDERED = make_creature(
    name="Emet-Selch, Unsundered",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Elder", "Legendary", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

THE_EMPEROR_OF_PALAMECIA = make_creature(
    name="The Emperor of Palamecia",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

EXDEATH_VOID_WARLOCK = make_creature(
    name="Exdeath, Void Warlock",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Legendary", "Spirit", "Warlock"},
    supertypes={"Legendary"},
    text="",
)

GARLAND_KNIGHT_OF_CORNELIA = make_creature(
    name="Garland, Knight of Cornelia",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Knight", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

GARNET_PRINCESS_OF_ALEXANDRIA = make_creature(
    name="Garnet, Princess of Alexandria",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cleric", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Lifelink\nWhenever Garnet attacks, you may remove a lore counter from each of any number of Sagas you control. Put a +1/+1 counter on Garnet for each lore counter removed this way.",
)

GIOTT_KING_OF_THE_DWARVES = make_creature(
    name="Giott, King of the Dwarves",
    power=1, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Dwarf", "Noble"},
    supertypes={"Legendary"},
    text="Double strike\nWhenever Giott or another Dwarf you control enters and whenever an Equipment you control enters, you may discard a card. If you do, draw a card.",
)

GLADIOLUS_AMICITIA = make_creature(
    name="Gladiolus Amicitia",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="When Gladiolus Amicitia enters, search your library for a land card, put it onto the battlefield tapped, then shuffle.\nLandfall — Whenever a land you control enters, another target creature you control gets +2/+2 and gains trample until end of turn.",
)

GOLBEZ_CRYSTAL_COLLECTOR = make_creature(
    name="Golbez, Crystal Collector",
    power=1, toughness=4,
    mana_cost="{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, surveil 1.\nAt the beginning of your end step, if you control four or more artifacts, return target creature card from your graveyard to your hand. Then if you control eight or more artifacts, each opponent loses life equal to that card's power.",
)

HOPE_ESTHEIM = make_creature(
    name="Hope Estheim",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Lifelink\nAt the beginning of your end step, each opponent mills X cards, where X is the amount of life you gained this turn.",
)

IGNIS_SCIENTIA = make_creature(
    name="Ignis Scientia",
    power=2, toughness=2,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Advisor", "Human"},
    supertypes={"Legendary"},
    text="When Ignis Scientia enters, look at the top six cards of your library. You may put a land card from among them onto the battlefield tapped. Put the rest on the bottom of your library in a random order.\nI've Come Up with a New Recipe! — {1}{G}{U}, {T}: Exile target card from a graveyard. If a creature card was exiled this way, create a Food token.",
)

JENOVA_ANCIENT_CALAMITY = make_creature(
    name="Jenova, Ancient Calamity",
    power=1, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Alien"},
    supertypes={"Legendary"},
    text="At the beginning of combat on your turn, put a number of +1/+1 counters equal to Jenova's power on up to one other target creature. That creature becomes a Mutant in addition to its other types.\nWhenever a Mutant you control dies during your turn, you draw cards equal to its power.",
)

JOSHUA_PHOENIXS_DOMINANT = make_creature(
    name="Joshua, Phoenix's Dominant",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Legendary", "Noble", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

JUDGE_MAGISTER_GABRANTH = make_creature(
    name="Judge Magister Gabranth",
    power=2, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Advisor", "Human", "Knight"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever another creature or artifact you control dies, put a +1/+1 counter on Judge Magister Gabranth.",
)

KEFKA_COURT_MAGE = make_creature(
    name="Kefka, Court Mage",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

KUJA_GENOME_SORCERER = make_creature(
    name="Kuja, Genome Sorcerer",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Mutant", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

LIGHTNING_ARMY_OF_ONE = make_creature(
    name="Lightning, Army of One",
    power=3, toughness=2,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="First strike, trample, lifelink\nStagger — Whenever Lightning deals combat damage to a player, until your next turn, if a source would deal damage to that player or a permanent that player controls, it deals double that damage instead.",
)

LOCKE_COLE = make_creature(
    name="Locke Cole",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
    text="Deathtouch, lifelink\nWhenever Locke Cole deals combat damage to a player, draw a card, then discard a card.",
)

NOCTIS_PRINCE_OF_LUCIS = make_creature(
    name="Noctis, Prince of Lucis",
    power=4, toughness=3,
    mana_cost="{1}{W}{U}{B}",
    colors={Color.BLACK, Color.BLUE, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Lifelink\nYou may cast artifact spells from your graveyard by paying 3 life in addition to paying their other costs. If you cast a spell this way, that artifact enters with a finality counter on it.",
)

OMEGA_HEARTLESS_EVOLUTION = make_artifact_creature(
    name="Omega, Heartless Evolution",
    power=8, toughness=8,
    mana_cost="{5}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Robot"},
    supertypes={"Legendary"},
    text="Wave Cannon — When Omega enters, for each opponent, tap up to one target nonland permanent that opponent controls. Put X stun counters on each of those permanents and you gain X life, where X is the number of nonbasic lands you control. (If a permanent with a stun counter would become untapped, remove one from it instead.)",
)

RINOA_HEARTILLY = make_creature(
    name="Rinoa Heartilly",
    power=4, toughness=4,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Rebel", "Warlock"},
    supertypes={"Legendary"},
    text="When Rinoa Heartilly enters, create Angelo, a legendary 1/1 green and white Dog creature token.\nAngelo Cannon — Whenever Rinoa Heartilly attacks, another target creature you control gets +1/+1 until end of turn for each creature you control.",
)

RUFUS_SHINRA = make_creature(
    name="Rufus Shinra",
    power=2, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Whenever Rufus Shinra attacks, if you don't control a creature named Darkstar, create Darkstar, a legendary 2/2 white and black Dog creature token.",
)

RYDIA_SUMMONER_OF_MIST = make_creature(
    name="Rydia, Summoner of Mist",
    power=1, toughness=2,
    mana_cost="{R}{G}",
    colors={Color.GREEN, Color.RED},
    subtypes={"Human", "Shaman"},
    supertypes={"Legendary"},
    text="Landfall — Whenever a land you control enters, you may discard a card. If you do, draw a card.\nSummon — {X}, {T}: Return target Saga card with mana value X from your graveyard to the battlefield with a finality counter on it. It gains haste until end of turn. Activate only as a sorcery.",
)

SERAH_FARRON = make_artifact_creature(
    name="Serah Farron",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Artifact", "Citizen", "Human", "Legendary"},
    supertypes={"Legendary"},
    text="",
)

SHANTOTTO_TACTICIAN_MAGICIAN = make_creature(
    name="Shantotto, Tactician Magician",
    power=0, toughness=4,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Dwarf", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, Shantotto gets +X/+0 until end of turn, where X is the amount of mana spent to cast that spell. If X is 4 or more, draw a card.",
)

SIN_SPIRAS_PUNISHMENT = make_creature(
    name="Sin, Spira's Punishment",
    power=7, toughness=7,
    mana_cost="{4}{B}{G}{U}",
    colors={Color.BLACK, Color.GREEN, Color.BLUE},
    subtypes={"Avatar", "Leviathan"},
    supertypes={"Legendary"},
    text="Flying\nWhenever Sin enters or attacks, exile a permanent card from your graveyard at random, then create a tapped token that's a copy of that card. If the exiled card is a land card, repeat this process.",
)

SQUALL_SEED_MERCENARY = make_creature(
    name="Squall, SeeD Mercenary",
    power=3, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Human", "Knight", "Mercenary"},
    supertypes={"Legendary"},
    text="Rough Divide — Whenever a creature you control attacks alone, it gains double strike until end of turn.\nWhenever Squall deals combat damage to a player, return target permanent card with mana value 3 or less from your graveyard to the battlefield.",
)

TELLAH_GREAT_SAGE = make_creature(
    name="Tellah, Great Sage",
    power=3, toughness=3,
    mana_cost="{3}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast a noncreature spell, create a 1/1 colorless Hero creature token. If four or more mana was spent to cast that spell, draw two cards. If eight or more mana was spent to cast that spell, sacrifice Tellah and it deals that much damage to each opponent.",
)

TERRA_MAGICAL_ADEPT = make_creature(
    name="Terra, Magical Adept",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Enchantment", "Human", "Legendary", "Warrior", "Wizard"},
    supertypes={"Legendary"},
    text="",
)

TIDUS_BLITZBALL_STAR = make_creature(
    name="Tidus, Blitzball Star",
    power=2, toughness=1,
    mana_cost="{1}{W}{U}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Whenever an artifact you control enters, put a +1/+1 counter on Tidus.\nWhenever Tidus attacks, tap target creature an opponent controls.",
)

ULTIMECIA_TIME_SORCERESS = make_creature(
    name="Ultimecia, Time Sorceress",
    power=0, toughness=0,
    mana_cost="",
    colors=set(),
    subtypes={"//", "Creature", "Human", "Legendary", "Warlock"},
    supertypes={"Legendary"},
    text="",
)

VIVI_ORNITIER = make_creature(
    name="Vivi Ornitier",
    power=0, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{0}: Add X mana in any combination of {U} and/or {R}, where X is Vivi Ornitier's power. Activate only during your turn and only once each turn.\nWhenever you cast a noncreature spell, put a +1/+1 counter on Vivi Ornitier and it deals 1 damage to each opponent.",
)

AVIVI_ORNITIER = make_creature(
    name="A-Vivi Ornitier",
    power=0, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Wizard"},
    supertypes={"Legendary"},
    text="{T}: Add X mana in any combination of {U} and/or {R}, where X is Vivi Ornitier's power.\nWhenever you cast a noncreature spell, put a +1/+1 counter on Vivi Ornitier and it deals 1 damage to each opponent.",
)

THE_WANDERING_MINSTREL = make_creature(
    name="The Wandering Minstrel",
    power=1, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bard", "Human"},
    supertypes={"Legendary"},
    text="Lands you control enter untapped.\nThe Minstrel's Ballad — At the beginning of combat on your turn, if you control five or more Towns, create a 2/2 Elemental creature token that's all colors.\n{3}{W}{U}{B}{R}{G}: Other creatures you control get +X/+X until end of turn, where X is the number of Towns you control.",
)

YUNA_HOPE_OF_SPIRA = make_creature(
    name="Yuna, Hope of Spira",
    power=3, toughness=5,
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Cleric", "Human"},
    supertypes={"Legendary"},
    text="During your turn, Yuna and enchantment creatures you control have trample, lifelink, and ward {2}.\nAt the beginning of your end step, return up to one target enchantment card from your graveyard to the battlefield with a finality counter on it. (If a permanent with a finality counter on it would be put into a graveyard from the battlefield, exile it instead.)",
)

ZIDANE_TANTALUS_THIEF = make_creature(
    name="Zidane, Tantalus Thief",
    power=3, toughness=3,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mutant", "Scout"},
    supertypes={"Legendary"},
    text="When Zidane enters, gain control of target creature an opponent controls until end of turn. Untap it. It gains lifelink and haste until end of turn.\nWhenever an opponent gains control of a permanent from you, you create a Treasure token.",
)

ADVENTURERS_AIRSHIP = make_artifact(
    name="Adventurer's Airship",
    mana_cost="{3}",
    text="Flying\nWhenever this Vehicle attacks, draw a card, then discard a card.\nCrew 2 (Tap any number of creatures you control with total power 2 or more: This Vehicle becomes an artifact creature until end of turn.)",
    subtypes={"Vehicle"},
)

AETTIR_AND_PRIWEN = make_artifact(
    name="Aettir and Priwen",
    mana_cost="{6}",
    text="Equipped creature has base power and toughness X/X, where X is your life total.\nEquip {5}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

BLITZBALL = make_artifact(
    name="Blitzball",
    mana_cost="{3}",
    text="{T}: Add one mana of any color.\nGOOOOAAAALLL! — {T}, Sacrifice this artifact: Draw two cards. Activate only if an opponent was dealt combat damage by a legendary creature this turn.",
)

BUSTER_SWORD = make_artifact(
    name="Buster Sword",
    mana_cost="{3}",
    text="Equipped creature gets +3/+2.\nWhenever equipped creature deals combat damage to a player, draw a card, then you may cast a spell from your hand with mana value less than or equal to that damage without paying its mana cost.\nEquip {2}",
    subtypes={"Equipment"},
)

ELIXIR = make_artifact(
    name="Elixir",
    mana_cost="{1}",
    text="This artifact enters tapped.\n{5}, {T}, Exile this artifact: Shuffle all nonland cards from your graveyard into your library. You gain life equal to the number of cards shuffled into your library this way.",
)

EXCALIBUR_II = make_artifact(
    name="Excalibur II",
    mana_cost="{1}",
    text="Whenever you gain life, put a charge counter on Excalibur II.\nEquipped creature gets +1/+1 for each charge counter on Excalibur II.\nEquip {3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

GENJI_GLOVE = make_artifact(
    name="Genji Glove",
    mana_cost="{5}",
    text="Equipped creature has double strike.\nWhenever equipped creature attacks, if it's the first combat phase of the turn, untap it. After this phase, there is an additional combat phase.\nEquip {3}",
    subtypes={"Equipment"},
)

INSTANT_RAMEN = make_artifact(
    name="Instant Ramen",
    mana_cost="{2}",
    text="Flash\nWhen this artifact enters, draw a card.\n{2}, {T}, Sacrifice this artifact: You gain 3 life.",
    subtypes={"Food"},
)

IRON_GIANT = make_artifact_creature(
    name="Iron Giant",
    power=6, toughness=6,
    mana_cost="{7}",
    colors=set(),
    subtypes={"Demon"},
    text="Vigilance, reach, trample",
)

LION_HEART = make_artifact(
    name="Lion Heart",
    mana_cost="{4}",
    text="When this Equipment enters, it deals 2 damage to any target.\nEquipped creature gets +2/+1.\nEquip {2}",
    subtypes={"Equipment"},
)

LUNATIC_PANDORA = make_artifact(
    name="Lunatic Pandora",
    mana_cost="{1}",
    text="{2}, {T}: Surveil 1. (Look at the top card of your library. You may put it into your graveyard.)\n{6}, {T}, Sacrifice Lunatic Pandora: Destroy target nonland permanent.",
    supertypes={"Legendary"},
)

MAGIC_POT = make_artifact_creature(
    name="Magic Pot",
    power=1, toughness=4,
    mana_cost="{3}",
    colors=set(),
    subtypes={"Construct", "Goblin"},
    text="When this creature dies, create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")\n{2}, {T}: Exile target card from a graveyard.",
)

THE_MASAMUNE = make_artifact(
    name="The Masamune",
    mana_cost="{3}",
    text="As long as equipped creature is attacking, it has first strike and must be blocked if able.\nEquipped creature has \"If a creature dying causes a triggered ability of this creature or an emblem you own to trigger, that ability triggers an additional time.\"\nEquip {2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

MONKS_FIST = make_artifact(
    name="Monk's Fist",
    mana_cost="{2}",
    text="Job select (When this Equipment enters, create a 1/1 colorless Hero creature token, then attach this to it.)\nEquipped creature gets +1/+0 and is a Monk in addition to its other types.\nEquip {2} ({2}: Attach to target creature you control. Equip only as a sorcery.)",
    subtypes={"Equipment"},
)

PUPU_UFO = make_artifact_creature(
    name="PuPu UFO",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Alien", "Construct"},
    text="Flying\n{T}: You may put a land card from your hand onto the battlefield.\n{3}: Until end of turn, this creature's base power becomes equal to the number of Towns you control.",
)

THE_REGALIA = make_artifact(
    name="The Regalia",
    mana_cost="{4}",
    text="Haste\nWhenever The Regalia attacks, reveal cards from the top of your library until you reveal a land card. Put that card onto the battlefield tapped and the rest on the bottom of your library in a random order.\nCrew 1",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
)

RELENTLESS_XATM092 = make_artifact_creature(
    name="Relentless X-ATM092",
    power=6, toughness=5,
    mana_cost="{6}",
    colors=set(),
    subtypes={"Robot", "Spider"},
    text="This creature can't be blocked except by three or more creatures.\n{8}: Return this card from your graveyard to the battlefield tapped with a finality counter on it. (If a creature with a finality counter on it would die, exile it instead.)",
)

RING_OF_THE_LUCII = make_artifact(
    name="Ring of the Lucii",
    mana_cost="{4}",
    text="{T}: Add {C}{C}.\n{2}, {T}, Pay 1 life: Tap target nonland permanent.",
    supertypes={"Legendary"},
)

WORLD_MAP = make_artifact(
    name="World Map",
    mana_cost="{1}",
    text="{1}, {T}, Sacrifice this artifact: Search your library for a basic land card, reveal it, put it into your hand, then shuffle.\n{3}, {T}, Sacrifice this artifact: Search your library for a land card, reveal it, put it into your hand, then shuffle.",
)

ADVENTURERS_INN = make_land(
    name="Adventurer's Inn",
    text="When this land enters, you gain 2 life.\n{T}: Add {C}.",
    subtypes={"Town"},
)

BALAMB_GARDEN_SEED_ACADEMY = make_artifact(
    name="Balamb Garden, SeeD Academy",
    mana_cost="",
    text="",
    subtypes={"//", "Artifact", "Legendary", "Town"},
)

BARON_AIRSHIP_KINGDOM = make_land(
    name="Baron, Airship Kingdom",
    text="This land enters tapped.\n{T}: Add {U} or {R}.",
    subtypes={"Town"},
)

CAPITAL_CITY = make_land(
    name="Capital City",
    text="{T}: Add {C}.\n{1}, {T}: Add one mana of any color.\nCycling {2} ({2}, Discard this card: Draw a card.)",
    subtypes={"Town"},
)

CLIVES_HIDEAWAY = make_land(
    name="Clive's Hideaway",
    text="Hideaway 4 (When this land enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom in a random order.)\n{T}: Add {C}.\n{2}, {T}: You may play the exiled card without paying its mana cost if you control four or more legendary creatures.",
    subtypes={"Town"},
)

CROSSROADS_VILLAGE = make_land(
    name="Crossroads Village",
    text="This land enters tapped. As it enters, choose a color.\n{T}: Add one mana of the chosen color.",
    subtypes={"Town"},
)

EDEN_SEAT_OF_THE_SANCTUM = make_land(
    name="Eden, Seat of the Sanctum",
    text="{T}: Add {C}.\n{5}, {T}: Mill two cards. Then you may sacrifice this land. When you do, return another target permanent card from your graveyard to your hand.",
    subtypes={"Town"},
)

GOHN_TOWN_OF_RUIN = make_land(
    name="Gohn, Town of Ruin",
    text="This land enters tapped.\n{T}: Add {B} or {G}.",
    subtypes={"Town"},
)

THE_GOLD_SAUCER = make_land(
    name="The Gold Saucer",
    text="{T}: Add {C}.\n{2}, {T}: Flip a coin. If you win the flip, create a Treasure token.\n{3}, {T}, Sacrifice two artifacts: Draw a card.",
    subtypes={"Town"},
)

GONGAGA_REACTOR_TOWN = make_land(
    name="Gongaga, Reactor Town",
    text="This land enters tapped.\n{T}: Add {R} or {G}.",
    subtypes={"Town"},
)

GUADOSALAM_FARPLANE_GATEWAY = make_land(
    name="Guadosalam, Farplane Gateway",
    text="This land enters tapped.\n{T}: Add {G} or {U}.",
    subtypes={"Town"},
)

INSOMNIA_CROWN_CITY = make_land(
    name="Insomnia, Crown City",
    text="This land enters tapped.\n{T}: Add {W} or {B}.",
    subtypes={"Town"},
)

ISHGARD_THE_HOLY_SEE = make_sorcery(
    name="Ishgard, the Holy See",
    mana_cost="{3}{W}{W}",
    colors=set(),
    text="",
    subtypes={"//", "Sorcery", "Town"},
)

JIDOOR_ARISTOCRATIC_CAPITAL = make_sorcery(
    name="Jidoor, Aristocratic Capital",
    mana_cost="{4}{U}{U}",
    colors=set(),
    text="",
    subtypes={"//", "Sorcery", "Town"},
)

LINDBLUM_INDUSTRIAL_REGENCY = make_instant(
    name="Lindblum, Industrial Regency",
    mana_cost="{2}{R}",
    colors=set(),
    text="",
    subtypes={"//", "Instant", "Town"},
)

MIDGAR_CITY_OF_MAKO = make_sorcery(
    name="Midgar, City of Mako",
    mana_cost="{2}{B}",
    colors=set(),
    text="",
    subtypes={"//", "Sorcery", "Town"},
)

RABANASTRE_ROYAL_CITY = make_land(
    name="Rabanastre, Royal City",
    text="This land enters tapped.\n{T}: Add {R} or {W}.",
    subtypes={"Town"},
)

SHARLAYAN_NATION_OF_SCHOLARS = make_land(
    name="Sharlayan, Nation of Scholars",
    text="This land enters tapped.\n{T}: Add {W} or {U}.",
    subtypes={"Town"},
)

STARTING_TOWN = make_land(
    name="Starting Town",
    text="This land enters tapped unless it's your first, second, or third turn of the game.\n{T}: Add {C}.\n{T}, Pay 1 life: Add one mana of any color.",
    subtypes={"Town"},
)

TRENO_DARK_CITY = make_land(
    name="Treno, Dark City",
    text="This land enters tapped.\n{T}: Add {U} or {B}.",
    subtypes={"Town"},
)

VECTOR_IMPERIAL_CAPITAL = make_land(
    name="Vector, Imperial Capital",
    text="This land enters tapped.\n{T}: Add {B} or {R}.",
    subtypes={"Town"},
)

WINDURST_FEDERATION_CENTER = make_land(
    name="Windurst, Federation Center",
    text="This land enters tapped.\n{T}: Add {G} or {W}.",
    subtypes={"Town"},
)

ZANARKAND_ANCIENT_METROPOLIS = make_sorcery(
    name="Zanarkand, Ancient Metropolis",
    mana_cost="{4}{G}{G}",
    colors=set(),
    text="",
    subtypes={"//", "Sorcery", "Town"},
)

PLAINS = make_land(
    name="Plains",
    text="({T}: Add {W}.)",
    subtypes={"Plains"},
    supertypes={"Basic"},
)

ISLAND = make_land(
    name="Island",
    text="({T}: Add {U}.)",
    subtypes={"Island"},
    supertypes={"Basic"},
)

SWAMP = make_land(
    name="Swamp",
    text="({T}: Add {B}.)",
    subtypes={"Swamp"},
    supertypes={"Basic"},
)

MOUNTAIN = make_land(
    name="Mountain",
    text="({T}: Add {R}.)",
    subtypes={"Mountain"},
    supertypes={"Basic"},
)

FOREST = make_land(
    name="Forest",
    text="({T}: Add {G}.)",
    subtypes={"Forest"},
    supertypes={"Basic"},
)

WASTES = make_land(
    name="Wastes",
    text="{T}: Add {C}.",
    supertypes={"Basic"},
)

CLOUD_PLANETS_CHAMPION = make_creature(
    name="Cloud, Planet's Champion",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary", "Soldier"},
    supertypes={"Legendary"},
    text="During your turn, as long as Cloud is equipped, it has double strike and indestructible. (This creature deals both first-strike and regular combat damage. Damage and effects that say \"destroy\" don't destroy this creature.)\nEquip abilities you activate that target Cloud cost {2} less to activate.",
)

SEPHIROTH_PLANETS_HEIR = make_creature(
    name="Sephiroth, Planet's Heir",
    power=4, toughness=4,
    mana_cost="{4}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Avatar", "Human", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nWhen Sephiroth enters, creatures your opponents control get -2/-2 until end of turn.\nWhenever a creature an opponent controls dies, put a +1/+1 counter on Sephiroth.",
)

BEATRIX_LOYAL_GENERAL = make_creature(
    name="Beatrix, Loyal General",
    power=4, toughness=4,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Vigilance (Attacking doesn't cause this creature to tap.)\nAt the beginning of combat on your turn, you may attach any number of Equipment you control to target creature you control.",
)

ROSA_RESOLUTE_WHITE_MAGE = make_creature(
    name="Rosa, Resolute White Mage",
    power=2, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Cleric", "Human", "Noble"},
    supertypes={"Legendary"},
    text="Reach (This creature can block creatures with flying.)\nAt the beginning of combat on your turn, put a +1/+1 counter on target creature you control. It gains lifelink until end of turn. (Damage dealt by the creature also causes you to gain that much life.)",
)

ULTIMECIA_TEMPORAL_THREAT = make_creature(
    name="Ultimecia, Temporal Threat",
    power=4, toughness=4,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="When Ultimecia enters, tap all creatures your opponents control.\nWhenever a creature you control deals combat damage to a player, draw a card.",
)

DEADLY_EMBRACE = make_sorcery(
    name="Deadly Embrace",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature an opponent controls. Then draw a card for each creature that died this turn.",
)

SEYMOUR_FLUX = make_creature(
    name="Seymour Flux",
    power=5, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Avatar", "Spirit"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card and put a +1/+1 counter on Seymour Flux.",
)

JUDGMENT_BOLT = make_instant(
    name="Judgment Bolt",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Judgment Bolt deals 5 damage to target creature and X damage to that creature's controller, where X is the number of Equipment you control.",
)

LIGHTNING_SECURITY_SERGEANT = make_creature(
    name="Lightning, Security Sergeant",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nWhenever Lightning deals combat damage to a player, exile the top card of your library. You may play that card for as long as you control Lightning.",
)

XANDE_DARK_MAGE = make_creature(
    name="Xande, Dark Mage",
    power=3, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Menace (This creature can't be blocked except by two or more creatures.)\nXande gets +1/+1 for each noncreature, nonland card in your graveyard.",
)

MAGITEK_SCYTHE = make_artifact(
    name="Magitek Scythe",
    mana_cost="{4}",
    text="A Test of Your Reflexes! — When this Equipment enters, you may attach it to target creature you control. If you do, that creature gains first strike until end of turn and must be blocked this turn if able.\nEquipped creature gets +2/+1.\nEquip {2}",
    subtypes={"Equipment"},
)

ULTIMA_WEAPON = make_artifact(
    name="Ultima Weapon",
    mana_cost="{7}",
    text="Whenever equipped creature attacks, destroy target creature an opponent controls.\nEquipped creature gets +7/+7.\nEquip {7}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
)

# =============================================================================
# CARD REGISTRY
# =============================================================================

FINAL_FANTASY_CARDS = {
    "Summon: Bahamut": SUMMON_BAHAMUT,
    "Ultima, Origin of Oblivion": ULTIMA_ORIGIN_OF_OBLIVION,
    "Adelbert Steiner": ADELBERT_STEINER,
    "Aerith Gainsborough": AERITH_GAINSBOROUGH,
    "Aerith Rescue Mission": AERITH_RESCUE_MISSION,
    "Ambrosia Whiteheart": AMBROSIA_WHITEHEART,
    "Ashe, Princess of Dalmasca": ASHE_PRINCESS_OF_DALMASCA,
    "Auron's Inspiration": AURONS_INSPIRATION,
    "Battle Menu": BATTLE_MENU,
    "Cloud, Midgar Mercenary": CLOUD_MIDGAR_MERCENARY,
    "Cloudbound Moogle": CLOUDBOUND_MOOGLE,
    "Coeurl": COEURL,
    "Crystal Fragments": CRYSTAL_FRAGMENTS,
    "The Crystal's Chosen": THE_CRYSTALS_CHOSEN,
    "Delivery Moogle": DELIVERY_MOOGLE,
    "Dion, Bahamut's Dominant": DION_BAHAMUTS_DOMINANT,
    "Dragoon's Lance": DRAGOONS_LANCE,
    "Dwarven Castle Guard": DWARVEN_CASTLE_GUARD,
    "Fate of the Sun-Cryst": FATE_OF_THE_SUNCRYST,
    "From Father to Son": FROM_FATHER_TO_SON,
    "G'raha Tia": GRAHA_TIA,
    "Gaelicat": GAELICAT,
    "Machinist's Arsenal": MACHINISTS_ARSENAL,
    "Magitek Armor": MAGITEK_ARMOR,
    "Magitek Infantry": MAGITEK_INFANTRY,
    "Minwu, White Mage": MINWU_WHITE_MAGE,
    "Moogles' Valor": MOOGLES_VALOR,
    "Paladin's Arms": PALADINS_ARMS,
    "Phoenix Down": PHOENIX_DOWN,
    "Restoration Magic": RESTORATION_MAGIC,
    "Sidequest: Catch a Fish": SIDEQUEST_CATCH_A_FISH,
    "Slash of Light": SLASH_OF_LIGHT,
    "Snow Villiers": SNOW_VILLIERS,
    "Stiltzkin, Moogle Merchant": STILTZKIN_MOOGLE_MERCHANT,
    "Summon: Choco/Mog": SUMMON_CHOCOMOG,
    "Summon: Knights of Round": SUMMON_KNIGHTS_OF_ROUND,
    "Summon: Primal Garuda": SUMMON_PRIMAL_GARUDA,
    "Ultima": ULTIMA,
    "Venat, Heart of Hydaelyn": VENAT_HEART_OF_HYDAELYN,
    "Weapons Vendor": WEAPONS_VENDOR,
    "White Auracite": WHITE_AURACITE,
    "White Mage's Staff": WHITE_MAGES_STAFF,
    "The Wind Crystal": THE_WIND_CRYSTAL,
    "You're Not Alone": YOURE_NOT_ALONE,
    "Zack Fair": ZACK_FAIR,
    "Astrologian's Planisphere": ASTROLOGIANS_PLANISPHERE,
    "Cargo Ship": CARGO_SHIP,
    "Combat Tutorial": COMBAT_TUTORIAL,
    "Dragoon's Wyvern": DRAGOONS_WYVERN,
    "Dreams of Laguna": DREAMS_OF_LAGUNA,
    "Edgar, King of Figaro": EDGAR_KING_OF_FIGARO,
    "Eject": EJECT,
    "Ether": ETHER,
    "Gogo, Master of Mimicry": GOGO_MASTER_OF_MIMICRY,
    "Ice Flan": ICE_FLAN,
    "Ice Magic": ICE_MAGIC,
    "Il Mheg Pixie": IL_MHEG_PIXIE,
    "Jill, Shiva's Dominant": JILL_SHIVAS_DOMINANT,
    "Louisoix's Sacrifice": LOUISOIXS_SACRIFICE,
    "The Lunar Whale": THE_LUNAR_WHALE,
    "Magic Damper": MAGIC_DAMPER,
    "Matoya, Archon Elder": MATOYA_ARCHON_ELDER,
    "Memories Returning": MEMORIES_RETURNING,
    "The Prima Vista": THE_PRIMA_VISTA,
    "Qiqirn Merchant": QIQIRN_MERCHANT,
    "Quistis Trepe": QUISTIS_TREPE,
    "Relm's Sketching": RELMS_SKETCHING,
    "Retrieve the Esper": RETRIEVE_THE_ESPER,
    "Rook Turret": ROOK_TURRET,
    "Sage's Nouliths": SAGES_NOULITHS,
    "Sahagin": SAHAGIN,
    "Scorpion Sentinel": SCORPION_SENTINEL,
    "Sidequest: Card Collection": SIDEQUEST_CARD_COLLECTION,
    "Sleep Magic": SLEEP_MAGIC,
    "Stolen Uniform": STOLEN_UNIFORM,
    "Stuck in Summoner's Sanctum": STUCK_IN_SUMMONERS_SANCTUM,
    "Summon: Leviathan": SUMMON_LEVIATHAN,
    "Summon: Shiva": SUMMON_SHIVA,
    "Swallowed by Leviathan": SWALLOWED_BY_LEVIATHAN,
    "Syncopate": SYNCOPATE,
    "Thief's Knife": THIEFS_KNIFE,
    "Travel the Overworld": TRAVEL_THE_OVERWORLD,
    "Ultros, Obnoxious Octopus": ULTROS_OBNOXIOUS_OCTOPUS,
    "Valkyrie Aerial Unit": VALKYRIE_AERIAL_UNIT,
    "The Water Crystal": THE_WATER_CRYSTAL,
    "Y'shtola Rhul": YSHTOLA_RHUL,
    "Ahriman": AHRIMAN,
    "Al Bhed Salvagers": AL_BHED_SALVAGERS,
    "Ardyn, the Usurper": ARDYN_THE_USURPER,
    "Black Mage's Rod": BLACK_MAGES_ROD,
    "Cecil, Dark Knight": CECIL_DARK_KNIGHT,
    "Circle of Power": CIRCLE_OF_POWER,
    "Cornered by Black Mages": CORNERED_BY_BLACK_MAGES,
    "Dark Confidant": DARK_CONFIDANT,
    "Dark Knight's Greatsword": DARK_KNIGHTS_GREATSWORD,
    "The Darkness Crystal": THE_DARKNESS_CRYSTAL,
    "Demon Wall": DEMON_WALL,
    "Evil Reawakened": EVIL_REAWAKENED,
    "Fang, Fearless l'Cie": FANG_FEARLESS_LCIE,
    "Ragnarok, Divine Deliverance": RAGNAROK_DIVINE_DELIVERANCE,
    "Fight On!": FIGHT_ON,
    "The Final Days": THE_FINAL_DAYS,
    "Gaius van Baelsar": GAIUS_VAN_BAELSAR,
    "Hecteyes": HECTEYES,
    "Jecht, Reluctant Guardian": JECHT_RELUCTANT_GUARDIAN,
    "Kain, Traitorous Dragoon": KAIN_TRAITOROUS_DRAGOON,
    "Malboro": MALBORO,
    "Namazu Trader": NAMAZU_TRADER,
    "Ninja's Blades": NINJAS_BLADES,
    "Overkill": OVERKILL,
    "Phantom Train": PHANTOM_TRAIN,
    "Poison the Waters": POISON_THE_WATERS,
    "Qutrub Forayer": QUTRUB_FORAYER,
    "Reno and Rude": RENO_AND_RUDE,
    "Resentful Revelation": RESENTFUL_REVELATION,
    "Sephiroth, Fabled SOLDIER": SEPHIROTH_FABLED_SOLDIER,
    "Sephiroth's Intervention": SEPHIROTHS_INTERVENTION,
    "Shambling Cie'th": SHAMBLING_CIETH,
    "Shinra Reinforcements": SHINRA_REINFORCEMENTS,
    "Sidequest: Hunt the Mark": SIDEQUEST_HUNT_THE_MARK,
    "Summon: Anima": SUMMON_ANIMA,
    "Summon: Primal Odin": SUMMON_PRIMAL_ODIN,
    "Tonberry": TONBERRY,
    "Undercity Dire Rat": UNDERCITY_DIRE_RAT,
    "Vayne's Treachery": VAYNES_TREACHERY,
    "Vincent Valentine": VINCENT_VALENTINE,
    "Vincent's Limit Break": VINCENTS_LIMIT_BREAK,
    "Zenos yae Galvus": ZENOS_YAE_GALVUS,
    "Zodiark, Umbral God": ZODIARK_UMBRAL_GOD,
    "Barret Wallace": BARRET_WALLACE,
    "Blazing Bomb": BLAZING_BOMB,
    "Call the Mountain Chocobo": CALL_THE_MOUNTAIN_CHOCOBO,
    "Choco-Comet": CHOCOCOMET,
    "Clive, Ifrit's Dominant": CLIVE_IFRITS_DOMINANT,
    "Coral Sword": CORAL_SWORD,
    "The Fire Crystal": THE_FIRE_CRYSTAL,
    "Fire Magic": FIRE_MAGIC,
    "Firion, Wild Rose Warrior": FIRION_WILD_ROSE_WARRIOR,
    "Freya Crescent": FREYA_CRESCENT,
    "Gilgamesh, Master-at-Arms": GILGAMESH_MASTERATARMS,
    "Haste Magic": HASTE_MAGIC,
    "Hill Gigas": HILL_GIGAS,
    "Item Shopkeep": ITEM_SHOPKEEP,
    "Laughing Mad": LAUGHING_MAD,
    "Light of Judgment": LIGHT_OF_JUDGMENT,
    "Mysidian Elder": MYSIDIAN_ELDER,
    "Nibelheim Aflame": NIBELHEIM_AFLAME,
    "Opera Love Song": OPERA_LOVE_SONG,
    "Prompto Argentum": PROMPTO_ARGENTUM,
    "Queen Brahne": QUEEN_BRAHNE,
    "Random Encounter": RANDOM_ENCOUNTER,
    "Raubahn, Bull of Ala Mhigo": RAUBAHN_BULL_OF_ALA_MHIGO,
    "Red Mage's Rapier": RED_MAGES_RAPIER,
    "Sabotender": SABOTENDER,
    "Samurai's Katana": SAMURAIS_KATANA,
    "Sandworm": SANDWORM,
    "Seifer Almasy": SEIFER_ALMASY,
    "Self-Destruct": SELFDESTRUCT,
    "Sidequest: Play Blitzball": SIDEQUEST_PLAY_BLITZBALL,
    "Sorceress's Schemes": SORCERESSS_SCHEMES,
    "Summon: Brynhildr": SUMMON_BRYNHILDR,
    "Summon: Esper Ramuh": SUMMON_ESPER_RAMUH,
    "Summon: G.F. Cerberus": SUMMON_GF_CERBERUS,
    "Summon: G.F. Ifrit": SUMMON_GF_IFRIT,
    "Suplex": SUPLEX,
    "Thunder Magic": THUNDER_MAGIC,
    "Triple Triad": TRIPLE_TRIAD,
    "Unexpected Request": UNEXPECTED_REQUEST,
    "Vaan, Street Thief": VAAN_STREET_THIEF,
    "Warrior's Sword": WARRIORS_SWORD,
    "Zell Dincht": ZELL_DINCHT,
    "Airship Crash": AIRSHIP_CRASH,
    "Ancient Adamantoise": ANCIENT_ADAMANTOISE,
    "Balamb T-Rexaur": BALAMB_TREXAUR,
    "Bard's Bow": BARDS_BOW,
    "Bartz and Boko": BARTZ_AND_BOKO,
    "Blitzball Shot": BLITZBALL_SHOT,
    "Cactuar": CACTUAR,
    "Chocobo Kick": CHOCOBO_KICK,
    "Chocobo Racetrack": CHOCOBO_RACETRACK,
    "Clash of the Eikons": CLASH_OF_THE_EIKONS,
    "Coliseum Behemoth": COLISEUM_BEHEMOTH,
    "Commune with Beavers": COMMUNE_WITH_BEAVERS,
    "Diamond Weapon": DIAMOND_WEAPON,
    "The Earth Crystal": THE_EARTH_CRYSTAL,
    "Esper Origins": ESPER_ORIGINS,
    "Galuf's Final Act": GALUFS_FINAL_ACT,
    "Gigantoad": GIGANTOAD,
    "Goobbue Gardener": GOOBBUE_GARDENER,
    "Gran Pulse Ochu": GRAN_PULSE_OCHU,
    "Gysahl Greens": GYSAHL_GREENS,
    "Jumbo Cactuar": JUMBO_CACTUAR,
    "Loporrit Scout": LOPORRIT_SCOUT,
    "Prishe's Wanderings": PRISHES_WANDERINGS,
    "Quina, Qu Gourmet": QUINA_QU_GOURMET,
    "Reach the Horizon": REACH_THE_HORIZON,
    "A Realm Reborn": A_REALM_REBORN,
    "Ride the Shoopuf": RIDE_THE_SHOOPUF,
    "Rydia's Return": RYDIAS_RETURN,
    "Sazh Katzroy": SAZH_KATZROY,
    "Sazh's Chocobo": SAZHS_CHOCOBO,
    "Sidequest: Raise a Chocobo": SIDEQUEST_RAISE_A_CHOCOBO,
    "Summon: Fat Chocobo": SUMMON_FAT_CHOCOBO,
    "Summon: Fenrir": SUMMON_FENRIR,
    "Summon: Titan": SUMMON_TITAN,
    "Summoner's Grimoire": SUMMONERS_GRIMOIRE,
    "Tifa Lockhart": TIFA_LOCKHART,
    "Tifa's Limit Break": TIFAS_LIMIT_BREAK,
    "Torgal, A Fine Hound": TORGAL_A_FINE_HOUND,
    "Town Greeter": TOWN_GREETER,
    "Traveling Chocobo": TRAVELING_CHOCOBO,
    "Vanille, Cheerful l'Cie": VANILLE_CHEERFUL_LCIE,
    "Absolute Virtue": ABSOLUTE_VIRTUE,
    "Balthier and Fran": BALTHIER_AND_FRAN,
    "Black Waltz No. 3": BLACK_WALTZ_NO_3,
    "Choco, Seeker of Paradise": CHOCO_SEEKER_OF_PARADISE,
    "Cid, Timeless Artificer": CID_TIMELESS_ARTIFICER,
    "Cloud of Darkness": CLOUD_OF_DARKNESS,
    "Emet-Selch, Unsundered": EMETSELCH_UNSUNDERED,
    "The Emperor of Palamecia": THE_EMPEROR_OF_PALAMECIA,
    "Exdeath, Void Warlock": EXDEATH_VOID_WARLOCK,
    "Garland, Knight of Cornelia": GARLAND_KNIGHT_OF_CORNELIA,
    "Garnet, Princess of Alexandria": GARNET_PRINCESS_OF_ALEXANDRIA,
    "Giott, King of the Dwarves": GIOTT_KING_OF_THE_DWARVES,
    "Gladiolus Amicitia": GLADIOLUS_AMICITIA,
    "Golbez, Crystal Collector": GOLBEZ_CRYSTAL_COLLECTOR,
    "Hope Estheim": HOPE_ESTHEIM,
    "Ignis Scientia": IGNIS_SCIENTIA,
    "Jenova, Ancient Calamity": JENOVA_ANCIENT_CALAMITY,
    "Joshua, Phoenix's Dominant": JOSHUA_PHOENIXS_DOMINANT,
    "Judge Magister Gabranth": JUDGE_MAGISTER_GABRANTH,
    "Kefka, Court Mage": KEFKA_COURT_MAGE,
    "Kuja, Genome Sorcerer": KUJA_GENOME_SORCERER,
    "Lightning, Army of One": LIGHTNING_ARMY_OF_ONE,
    "Locke Cole": LOCKE_COLE,
    "Noctis, Prince of Lucis": NOCTIS_PRINCE_OF_LUCIS,
    "Omega, Heartless Evolution": OMEGA_HEARTLESS_EVOLUTION,
    "Rinoa Heartilly": RINOA_HEARTILLY,
    "Rufus Shinra": RUFUS_SHINRA,
    "Rydia, Summoner of Mist": RYDIA_SUMMONER_OF_MIST,
    "Serah Farron": SERAH_FARRON,
    "Shantotto, Tactician Magician": SHANTOTTO_TACTICIAN_MAGICIAN,
    "Sin, Spira's Punishment": SIN_SPIRAS_PUNISHMENT,
    "Squall, SeeD Mercenary": SQUALL_SEED_MERCENARY,
    "Tellah, Great Sage": TELLAH_GREAT_SAGE,
    "Terra, Magical Adept": TERRA_MAGICAL_ADEPT,
    "Tidus, Blitzball Star": TIDUS_BLITZBALL_STAR,
    "Ultimecia, Time Sorceress": ULTIMECIA_TIME_SORCERESS,
    "Vivi Ornitier": VIVI_ORNITIER,
    "A-Vivi Ornitier": AVIVI_ORNITIER,
    "The Wandering Minstrel": THE_WANDERING_MINSTREL,
    "Yuna, Hope of Spira": YUNA_HOPE_OF_SPIRA,
    "Zidane, Tantalus Thief": ZIDANE_TANTALUS_THIEF,
    "Adventurer's Airship": ADVENTURERS_AIRSHIP,
    "Aettir and Priwen": AETTIR_AND_PRIWEN,
    "Blitzball": BLITZBALL,
    "Buster Sword": BUSTER_SWORD,
    "Elixir": ELIXIR,
    "Excalibur II": EXCALIBUR_II,
    "Genji Glove": GENJI_GLOVE,
    "Instant Ramen": INSTANT_RAMEN,
    "Iron Giant": IRON_GIANT,
    "Lion Heart": LION_HEART,
    "Lunatic Pandora": LUNATIC_PANDORA,
    "Magic Pot": MAGIC_POT,
    "The Masamune": THE_MASAMUNE,
    "Monk's Fist": MONKS_FIST,
    "PuPu UFO": PUPU_UFO,
    "The Regalia": THE_REGALIA,
    "Relentless X-ATM092": RELENTLESS_XATM092,
    "Ring of the Lucii": RING_OF_THE_LUCII,
    "World Map": WORLD_MAP,
    "Adventurer's Inn": ADVENTURERS_INN,
    "Balamb Garden, SeeD Academy": BALAMB_GARDEN_SEED_ACADEMY,
    "Baron, Airship Kingdom": BARON_AIRSHIP_KINGDOM,
    "Capital City": CAPITAL_CITY,
    "Clive's Hideaway": CLIVES_HIDEAWAY,
    "Crossroads Village": CROSSROADS_VILLAGE,
    "Eden, Seat of the Sanctum": EDEN_SEAT_OF_THE_SANCTUM,
    "Gohn, Town of Ruin": GOHN_TOWN_OF_RUIN,
    "The Gold Saucer": THE_GOLD_SAUCER,
    "Gongaga, Reactor Town": GONGAGA_REACTOR_TOWN,
    "Guadosalam, Farplane Gateway": GUADOSALAM_FARPLANE_GATEWAY,
    "Insomnia, Crown City": INSOMNIA_CROWN_CITY,
    "Ishgard, the Holy See": ISHGARD_THE_HOLY_SEE,
    "Jidoor, Aristocratic Capital": JIDOOR_ARISTOCRATIC_CAPITAL,
    "Lindblum, Industrial Regency": LINDBLUM_INDUSTRIAL_REGENCY,
    "Midgar, City of Mako": MIDGAR_CITY_OF_MAKO,
    "Rabanastre, Royal City": RABANASTRE_ROYAL_CITY,
    "Sharlayan, Nation of Scholars": SHARLAYAN_NATION_OF_SCHOLARS,
    "Starting Town": STARTING_TOWN,
    "Treno, Dark City": TRENO_DARK_CITY,
    "Vector, Imperial Capital": VECTOR_IMPERIAL_CAPITAL,
    "Windurst, Federation Center": WINDURST_FEDERATION_CENTER,
    "Zanarkand, Ancient Metropolis": ZANARKAND_ANCIENT_METROPOLIS,
    "Plains": PLAINS,
    "Island": ISLAND,
    "Swamp": SWAMP,
    "Mountain": MOUNTAIN,
    "Forest": FOREST,
    "Wastes": WASTES,
    "Cloud, Planet's Champion": CLOUD_PLANETS_CHAMPION,
    "Sephiroth, Planet's Heir": SEPHIROTH_PLANETS_HEIR,
    "Beatrix, Loyal General": BEATRIX_LOYAL_GENERAL,
    "Rosa, Resolute White Mage": ROSA_RESOLUTE_WHITE_MAGE,
    "Ultimecia, Temporal Threat": ULTIMECIA_TEMPORAL_THREAT,
    "Deadly Embrace": DEADLY_EMBRACE,
    "Seymour Flux": SEYMOUR_FLUX,
    "Judgment Bolt": JUDGMENT_BOLT,
    "Lightning, Security Sergeant": LIGHTNING_SECURITY_SERGEANT,
    "Xande, Dark Mage": XANDE_DARK_MAGE,
    "Magitek Scythe": MAGITEK_SCYTHE,
    "Ultima Weapon": ULTIMA_WEAPON,
}

print(f"Loaded {len(FINAL_FANTASY_CARDS)} Final_Fantasy cards")
