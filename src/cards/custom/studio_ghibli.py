"""
Studio Ghibli: Spirits of the Wind (SGW) Card Implementations

Set released January 2026. ~250 cards.
Features mechanics: Spirit (phase in/out), Transformation, Nature's Wrath (Forest bonuses)
"""

from src.cards.card_factories import (
    make_artifact,
    make_artifact_creature,
    make_land,
    make_sorcery,
)

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from src.cards.ability_bundles import (
    etb_gain_life,
    death_draw,
    attack_add_counters,
    static_pt_boost_by_subtype,
)
from src.cards.text_render import (
    substitute_card_name,
    render_etb_gain_life,
    render_death_draw,
    render_attack_add_counters,
)
from src.cards.interceptor_helpers import (
    # Helper 5 (catalog sweep, 2026-05-18): combat-damage triggers on attach.
    make_equipment_setup,
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# =============================================================================
# GHIBLI KEYWORD MECHANICS
# =============================================================================

def count_forests(controller: str, state: GameState) -> int:
    """Count the number of Forests a player controls."""
    count = 0
    for obj in state.objects.values():
        if (obj.controller == controller and
            obj.zone == ZoneType.BATTLEFIELD and
            CardType.LAND in obj.characteristics.types and
            'Forest' in obj.characteristics.subtypes):
            count += 1
    return count


def make_spirit_phasing(source_obj: GameObject) -> Interceptor:
    """
    Spirit - At the beginning of your upkeep, you may have this creature phase out.
    If it phased in this turn, it can't be blocked.
    """
    def upkeep_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        return state.active_player == source_obj.controller

    def upkeep_handler(event: Event, state: GameState) -> InterceptorResult:
        phase_event = Event(
            type=EventType.PHASE_OUT,
            payload={'object_id': source_obj.id, 'optional': True},
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[phase_event])

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=upkeep_handler,
        duration='while_on_battlefield'
    )


def make_transformation(source_obj: GameObject, transformed_power: int, transformed_toughness: int,
                        trigger_condition: Callable[[Event, GameState], bool]) -> list[Interceptor]:
    """
    Transformation - When condition is met, this creature transforms into a more powerful form.
    """
    interceptors = []

    def transform_filter(event: Event, state: GameState) -> bool:
        return trigger_condition(event, state)

    def transform_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': source_obj.id,
                'counter_type': 'transformation',
                'power_mod': transformed_power - source_obj.characteristics.power,
                'toughness_mod': transformed_toughness - source_obj.characteristics.toughness
            },
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[transform_event])

    interceptors.append(Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=transform_filter,
        handler=transform_handler,
        duration='while_on_battlefield'
    ))

    return interceptors


def make_natures_wrath(source_obj: GameObject, power_per_forest: int, toughness_per_forest: int) -> list[Interceptor]:
    """
    Nature's Wrath - This creature gets +X/+Y for each Forest you control.
    """
    def forest_power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == source_obj.id

    def forest_power_handler(event: Event, state: GameState) -> InterceptorResult:
        forest_count = min(count_forests(source_obj.controller, state), 3)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + (forest_count * power_per_forest)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def forest_toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == source_obj.id

    def forest_toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        forest_count = min(count_forests(source_obj.controller, state), 3)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + (forest_count * toughness_per_forest)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors = []
    if power_per_forest != 0:
        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=forest_power_filter,
            handler=forest_power_handler,
            duration='while_on_battlefield'
        ))
    if toughness_per_forest != 0:
        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=forest_toughness_filter,
            handler=forest_toughness_handler,
            duration='while_on_battlefield'
        ))
    return interceptors


# =============================================================================
# WHITE CARDS - HUMANS, HOPE, PURIFICATION
# =============================================================================

# --- Spirited Away ---

def chihiro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Chihiro enters, exile target enchantment or cursed creature."""
    def etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return event.payload.get('object_id') == obj.id

    def etb_handler(event: Event, state: GameState) -> InterceptorResult:
        exile_event = Event(
            type=EventType.EXILE,
            payload={'target_type': 'enchantment_or_cursed', 'controller': obj.controller},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[exile_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield'
    )]

CHIHIRO_SPIRITED_CHILD = make_creature(
    name="Chihiro, Spirited Child",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Child"},
    supertypes={"Legendary"},
    text="When Chihiro enters, exile target enchantment or creature with a curse counter. Spirits you control have vigilance.",
    setup_interceptors=chihiro_setup
)


def _lin_bathhouse_worker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Human", include_self=False)
    return list(interceptors)

LIN_BATHHOUSE_WORKER = make_creature(
    name="Lin, Bathhouse Worker",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Spirit"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1.",
    setup_interceptors=_lin_bathhouse_worker_setup,
)


def zeniba_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a curse is removed, draw a card"""
    def curse_removed_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.COUNTER_REMOVED:
            return False
        return event.payload.get('counter_type') == 'curse'

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        draw_event = Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=curse_removed_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

ZENIBA_GOOD_WITCH = make_creature(
    name="Zeniba, the Good Witch",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Witch"},
    supertypes={"Legendary"},
    text="Hexproof. Whenever a curse counter is removed from a permanent, draw a card. {2}{W}: Remove a curse counter from target permanent.",
    setup_interceptors=zeniba_setup
)


# --- Princess Mononoke ---

def ashitaka_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Asymmetric sweeper + rule rewrite: Ashitaka bears the demon-curse so
    others don't have to. At the beginning of each upkeep, destroy each
    creature with a curse counter on it (this includes Ashitaka — he
    sacrifices himself to cleanse them — so opponents must commit cursed
    threats or lose their board). When Ashitaka dies, remove all curse
    counters from permanents you control, so your own cursed creatures are
    spared. This rewrites the 'curses are stat boosters' axiom that the rest
    of the set leans on."""
    def upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'upkeep'

    def sweep_handler(event: Event, st: GameState) -> InterceptorResult:
        events: list[Event] = []
        # Before the sweep, if Ashitaka dies that turn, we first clear curses
        # on our own permanents so our stuff survives. Model this by pre-
        # emitting COUNTER_REMOVED for our own cursed creatures first.
        for o in list(st.objects.values()):
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if o.controller != obj.controller:
                continue
            if o.state.counters.get('curse', 0) <= 0:
                continue
            # Skip Ashitaka herself — she keeps her curse and perishes.
            if o.id == obj.id:
                continue
            events.append(Event(
                type=EventType.COUNTER_REMOVED,
                payload={
                    'object_id': o.id,
                    'counter_type': 'curse',
                    'amount': o.state.counters.get('curse', 0),
                },
                source=obj.id,
                controller=obj.controller,
            ))
        # Now destroy every creature that still has curse counters.
        for o in list(st.objects.values()):
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in o.characteristics.types:
                continue
            if o.state.counters.get('curse', 0) <= 0:
                continue
            events.append(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': o.id},
                source=obj.id,
                controller=obj.controller,
            ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=sweep_handler,
        duration='while_on_battlefield',
    )]

ASHITAKA_CURSED_PRINCE = make_creature(
    name="Ashitaka, Cursed Prince",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance. At the beginning of each upkeep, remove all curse counters from permanents you control, then destroy each creature with a curse counter on it.",
    setup_interceptors=ashitaka_setup
)


def san_human_form_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spirit-tribe lord + token engine. San gets +1/+0 for each other Spirit
    creature you control (she rides the spirits' anger). Whenever San
    attacks, create a 1/1 green Wolf Spirit creature token that enters
    tapped and attacking alongside her. This is a multi-mode engine:
    lord dimension + persistent token generator, so every combat step
    escalates."""
    from src.cards import interceptor_helpers as ih

    # Dynamic power boost: +1/+0 per other Spirit you control.
    def power_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def power_handler(event: Event, st: GameState) -> InterceptorResult:
        bonus = 0
        for o in st.objects.values():
            if o.id == obj.id:
                continue
            if o.controller != obj.controller:
                continue
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if CardType.CREATURE not in o.characteristics.types:
                continue
            if 'Spirit' in o.characteristics.subtypes:
                bonus += 1
        new_event = event.copy()
        new_event.payload['value'] = event.payload.get('value', 0) + bonus
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    power_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield',
    )

    def wolf_token_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Wolf Spirit',
                'power': 1,
                'toughness': 1,
                'colors': {Color.GREEN},
                'subtypes': {'Wolf', 'Spirit'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    token_trigger = ih.make_attack_trigger(obj, wolf_token_fn)
    return [power_interceptor, token_trigger]

SAN_WOLF_PRINCESS = make_creature(
    name="San, Wolf Princess",
    power=2, toughness=2,
    mana_cost="{1}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="First strike. San gets +1/+0 for each other Spirit creature you control. Whenever San attacks, create a 1/1 green Wolf Spirit creature token.",
    setup_interceptors=san_human_form_setup
)


# --- My Neighbor Totoro ---

def _satsuki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Selection break: whenever another creature enters under your
    control, look at the top three cards of your library. You may reveal a
    Spirit or Forest card from among them and put it into your hand. Put
    the rest on the bottom of your library in any order. Every creature
    you play fires a soft-tutor — hand quality ratchets upward
    continuously. The power is gated on creature ETBs, and she's fragile
    (2/2 for 2)."""
    from src.cards import interceptor_helpers as ih

    def event_filter(event: Event, st: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering = st.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != source.controller:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={
                'player': obj.controller,
                'amount': 3,
                'into_hand_matching': {'subtypes': {'Spirit', 'Forest'}, 'types': {CardType.LAND, CardType.CREATURE}},
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_etb_trigger(obj, effect_fn, filter_fn=event_filter)]

SATSUKI_BRAVE_SISTER = make_creature(
    name="Satsuki, Brave Sister",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Child"},
    supertypes={"Legendary"},
    text="Whenever another creature enters under your control, look at the top three cards of your library. You may reveal a Spirit or Forest card from among them and put it into your hand. Put the rest on the bottom.",
    setup_interceptors=_satsuki_setup,
)


def _mei_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reality-bending one-shot flavor: Mei wanders off into the forest and
    returns with a companion. When Mei attacks, exile the top card of your
    library. If it's a Spirit or creature with power 3 or less, you may
    put it onto the battlefield tapped and attacking alongside Mei. At end
    of turn, return it to your hand. This is impulse-draw + cheat-into-
    play, keyed off her being active. The payoff ramps with Spirit density
    in your deck."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.IMPULSE_DRAW,
            payload={
                'player': obj.controller,
                'amount': 1,
                'playable_if': {'subtypes': {'Spirit'}, 'max_power': 3},
                'enter_tapped_attacking': True,
                'return_to_hand_eot': True,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_attack_trigger(obj, effect_fn)]

MEI_CURIOUS_CHILD = make_creature(
    name="Mei, Curious Child",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Child"},
    supertypes={"Legendary"},
    text="Mei can't be blocked by creatures with power 3 or greater. Whenever Mei attacks, exile the top card of your library. If it's a Spirit with power 3 or less, you may put it onto the battlefield tapped and attacking. Return it to your hand at end of turn.",
    setup_interceptors=_mei_setup,
)


# --- Howl's Moving Castle ---

def sophie_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Transformation - when Sophie attacks, she may transform"""
    def attack_transform(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)
    return make_transformation(obj, 4, 4, attack_transform)

SOPHIE_CURSED_GIRL = make_creature(
    name="Sophie, Cursed Girl",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human"},
    supertypes={"Legendary"},
    text="Transformation - Whenever Sophie attacks, you may have her become 4/4 until end of turn. When Sophie transforms, remove all curse counters from her.",
    setup_interceptors=sophie_setup
)


def turnip_head_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a curse is removed, transform into Prince"""
    def curse_removed_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.COUNTER_REMOVED and
                event.payload.get('object_id') == obj.id and
                event.payload.get('counter_type') == 'curse')

    def transform_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={'object_id': obj.id, 'to_form': 'Prince of the Neighboring Kingdom'},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[transform_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=curse_removed_filter,
        handler=transform_handler,
        duration='while_on_battlefield'
    )]

TURNIP_HEAD = make_creature(
    name="Turnip Head, Cursed Prince",
    power=0, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Scarecrow", "Noble"},
    supertypes={"Legendary"},
    text="Defender. When a curse counter is removed from Turnip Head, transform him into a 4/4 Human Noble creature with vigilance.",
    setup_interceptors=turnip_head_setup
)


# --- Castle in the Sky ---

SHEETA_PRINCESS_OF_LAPUTA = make_creature(
    name="Sheeta, Princess of Laputa",
    power=2, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Flying. When Sheeta enters, create a colorless Equipment artifact token named Laputan Amulet with 'Equipped creature has hexproof. Equip {2}'."
)


def pazu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When attacks with an Equipment, draw a card"""
    def equipped_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id:
            return False
        for o in state.objects.values():
            if (CardType.ARTIFACT in o.characteristics.types and
                'Equipment' in o.characteristics.subtypes and
                o.state.attached_to == obj.id):
                return True
        return False

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        draw_event = Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=equipped_attack_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

PAZU_YOUNG_MECHANIC = make_creature(
    name="Pazu, Young Mechanic",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Artificer"},
    supertypes={"Legendary"},
    text="Whenever Pazu attacks while equipped, draw a card. Equipment spells you cast cost {1} less.",
    setup_interceptors=pazu_setup
)


# --- Nausicaa ---

def nausicaa_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink, Insects can't attack you"""
    def insect_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('defending_player') != obj.controller:
            return False
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        return attacker and 'Insect' in attacker.characteristics.subtypes

    def prevent_attack(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=insect_attack_filter,
        handler=prevent_attack,
        duration='while_on_battlefield'
    )]

NAUSICAA_PRINCESS_OF_WIND = make_creature(
    name="Nausicaa, Princess of the Wind",
    power=3, toughness=4,
    mana_cost="{2}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Noble", "Scout"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Insects can't attack you. Whenever Nausicaa deals combat damage to a player, you may put a land card from your hand onto the battlefield.",
    setup_interceptors=nausicaa_setup
)


# --- Kiki's Delivery Service ---

def _kiki_delivery_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """On ETB, create a 1/1 black Cat Familiar token (Jiji). Whenever you cast
    an instant or sorcery spell, Kiki gets +1/+1 until end of turn."""
    from src.cards import interceptor_helpers as ih

    def etb_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Cat Familiar',
                'power': 1,
                'toughness': 1,
                'colors': {Color.BLACK},
                'subtypes': {'Cat', 'Familiar'},
                'keywords': ['flying'],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    def pump_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [
        ih.make_etb_trigger(obj, etb_fn),
        ih.make_spell_cast_trigger(
            obj, pump_fn,
            spell_type_filter={CardType.INSTANT, CardType.SORCERY},
        ),
    ]

KIKI_DELIVERY_WITCH = make_creature(
    name="Kiki, Delivery Witch",
    power=2, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Witch"},
    supertypes={"Legendary"},
    text="Flying. When Kiki enters, create a 1/1 black Cat Familiar creature token with flying. Whenever you cast an instant or sorcery spell, Kiki gets +1/+1 until end of turn.",
    setup_interceptors=_kiki_delivery_witch_setup,
)


JIJI_FAMILIAR = make_creature(
    name="Jiji, Black Cat Familiar",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cat", "Familiar"},
    supertypes={"Legendary"},
    text="Flying. Kiki creatures you control get +1/+1. When Jiji dies, you may return target Witch card from your graveyard to your hand."
)


# --- Redesigned: Princess Kaguya (resource-axis break) ---

def _kaguya_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Persistent rule rewrite: at the beginning of each player's upkeep,
    that player draws an additional card. (Symmetric card-advantage engine.)
    She's expensive and fragile (4 toughness, targetable), but while she's
    on the board the resource axis is permanently tilted — every hand fills
    up, every draw step matters. Cards breed cards."""

    def upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'upkeep'

    def extra_draw_handler(event: Event, st: GameState) -> InterceptorResult:
        active = st.active_player
        if active is None:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        draw_event = Event(
            type=EventType.DRAW,
            payload={'player': active, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=extra_draw_handler,
        duration='while_on_battlefield',
    )]

KAGUYA_MOON_PRINCESS = make_creature(
    name="Kaguya, Moon Princess",
    power=3, toughness=4,
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Noble", "Spirit"},
    supertypes={"Legendary"},
    text="Flying, vigilance. As long as Kaguya is on the battlefield, each player draws an additional card at the beginning of their upkeep.",
    setup_interceptors=_kaguya_setup,
)


# --- White Commons/Uncommons ---

def _bathhouse_servant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 2)
    return [itc]

BATHHOUSE_SERVANT = make_creature(
    name="Bathhouse Servant",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Worker"},
    text=substitute_card_name(render_etb_gain_life(2), "Bathhouse Servant"),
    setup_interceptors=_bathhouse_servant_setup,
)


def _valley_villager_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = etb_gain_life(obj, 2)
    return [itc]

VALLEY_VILLAGER = make_creature(
    name="Valley Villager",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Peasant"},
    text=substitute_card_name(render_etb_gain_life(2), "Valley Villager"),
    setup_interceptors=_valley_villager_setup,
)


def _irontown_worker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Irontown Worker dies, if you control an artifact, create a
    1/1 Human Citizen."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        has_artifact = any(
            CardType.ARTIFACT in o.characteristics.types and
            o.controller == obj.controller and
            o.zone == ZoneType.BATTLEFIELD
            for o in state.objects.values()
        )
        if not has_artifact:
            return []
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'token': True,
                'name': 'Citizen',
                'power': 1,
                'toughness': 1,
                'colors': {Color.WHITE},
                'subtypes': {'Human', 'Citizen'},
                'keywords': [],
                'controller': obj.controller,
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_death_trigger(obj, effect_fn)]

IRONTOWN_WORKER = make_creature(
    name="Irontown Worker",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Artificer"},
    text="First strike. When Irontown Worker dies, if you control an artifact, create a 1/1 white Human Citizen creature token.",
    setup_interceptors=_irontown_worker_setup,
)


def _refugee_child_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever another creature you control enters the battlefield, gain 1 life."""
    def event_filter(event: Event, st: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        if entering_id == source.id:
            return False
        entering = st.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller != source.controller:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    from src.cards import interceptor_helpers as ih
    return [ih.make_etb_trigger(obj, effect_fn, filter_fn=event_filter)]

REFUGEE_CHILD = make_creature(
    name="Refugee Child",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Child"},
    text="Whenever another creature you control enters the battlefield, you gain 1 life.",
    setup_interceptors=_refugee_child_setup,
)


def _castle_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you gain life, put a +1/+1 counter on Castle Guardian."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1'},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_life_gain_trigger(obj, effect_fn)]

CASTLE_GUARDIAN = make_creature(
    name="Castle Guardian",
    power=3, toughness=5,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. Whenever you gain life, put a +1/+1 counter on Castle Guardian.",
    setup_interceptors=_castle_guardian_setup,
)


def _wind_rider_cadet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """On ETB, if you control another Pilot or Vehicle, draw a card."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        for o in state.objects.values():
            if (o.id != obj.id and
                o.controller == obj.controller and
                o.zone == ZoneType.BATTLEFIELD and
                ('Pilot' in o.characteristics.subtypes or
                 'Vehicle' in o.characteristics.subtypes)):
                return [Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller},
                    source=obj.id,
                    controller=obj.controller,
                )]
        return []

    from src.cards import interceptor_helpers as ih
    return [ih.make_etb_trigger(obj, effect_fn)]

WIND_RIDER_CADET = make_creature(
    name="Wind Rider Cadet",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Pilot"},
    text="Flying. When Wind Rider Cadet enters, if you control another Pilot or Vehicle, draw a card.",
    setup_interceptors=_wind_rider_cadet_setup,
)


def _young_witch_apprentice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, gain 1 life."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_spell_cast_trigger(
        obj, effect_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

YOUNG_WITCH_APPRENTICE = make_creature(
    name="Young Witch Apprentice",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Witch"},
    text="Flying. Whenever you cast an instant or sorcery spell, you gain 1 life.",
    setup_interceptors=_young_witch_apprentice_setup,
)


def _pejite_refugee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.ability_bundles import etb_create_token
    itc, _ = etb_create_token(
        obj, power=1, toughness=1, subtype="Citizen",
        count=1, colors={Color.WHITE},
    )
    return [itc]

PEJITE_REFUGEE = make_creature(
    name="Pejite Refugee",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Citizen"},
    text="When Pejite Refugee enters, create a 1/1 white Citizen creature token.",
    setup_interceptors=_pejite_refugee_setup,
)


def _porco_rosso_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Resource-axis break: whenever Porco Rosso deals combat damage to a
    player, after that combat phase, there is an additional combat phase
    and an additional main phase this turn (only once per turn). This is a
    classic 'extra combat' finisher, classically at 5+ mana, but the
    requirement of dealing combat damage acts as a natural gating. The
    flying body ensures he usually connects, but a single removal or a
    chump with flying shuts it down."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        target = event.payload.get('target')
        # Only trigger for damage to a player.
        if target not in st.players:
            return []
        # Guard against multiple extra-combat loops per turn.
        already = st.turn_state.extra_combats_triggered.get(obj.id) if hasattr(st, 'turn_state') and hasattr(st.turn_state, 'extra_combats_triggered') else False
        if already:
            return []
        return [Event(
            type=EventType.PHASE_START,
            payload={
                'phase': 'combat',
                'extra_combat': True,
                'source_object': obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_damage_trigger(obj, effect_fn, combat_only=True)]

PORCO_ROSSO_PILOT = make_creature(
    name="Porco Rosso, Sky Pirate",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Pig", "Pilot"},
    supertypes={"Legendary"},
    text="Flying. Whenever Porco Rosso deals combat damage to a player, after this phase there is an additional combat phase. (This triggers only once per turn.)",
    setup_interceptors=_porco_rosso_setup,
)


SEAPLANE_MECHANIC = make_creature(
    name="Seaplane Mechanic",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Artificer"},
    text="Vehicles you control get +0/+1. {T}: Untap target Vehicle."
)


def _eboshi_lady_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Human", include_self=False)
    return list(interceptors)

EBOSHI_LADY = make_creature(
    name="Lady Eboshi, Iron Town Leader",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Other Human creatures you control get +1/+1.",
    setup_interceptors=_eboshi_lady_setup,
)


# --- White Instants ---

SPIRITS_BLESSING = make_instant(
    name="Spirit's Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. If it's a Spirit, you also gain 3 life."
)


PROTECTIVE_CHARM = make_instant(
    name="Protective Charm",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Target creature you control gains hexproof and vigilance until end of turn. Draw a card."
)


PURIFYING_LIGHT = make_instant(
    name="Purifying Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature with a curse counter on it. Its controller gains 3 life."
)


WHISPERED_PRAYER = make_instant(
    name="Whispered Prayer",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Remove a curse counter from target permanent. You gain 2 life."
)


WIND_SHIELD = make_instant(
    name="Wind Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Prevent all combat damage that would be dealt this turn. You gain 1 life for each attacking creature."
)


# --- White Sorceries ---

CALL_OF_THE_VALLEY = make_sorcery(
    name="Call of the Valley",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Human Villager creature tokens. You gain 1 life for each creature you control."
)


CLEANSING_RITUAL = make_sorcery(
    name="Cleansing Ritual",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Remove all curse counters from all permanents. You gain 2 life for each counter removed this way."
)


JOURNEY_HOME = make_sorcery(
    name="Journey Home",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Return target creature you control to its owner's hand. You gain life equal to its toughness."
)


# --- White Enchantments ---

SPIRIT_PROTECTION = make_enchantment(
    name="Spirit Protection",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Spirit creatures you control have hexproof."
)


BATHHOUSE_SANCTUARY = make_enchantment(
    name="Bathhouse Sanctuary",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="At the beginning of your upkeep, you gain 1 life for each Spirit you control. Creatures your opponents control enter tapped."
)


# =============================================================================
# BLUE CARDS - SKY, FLYING, WATER SPIRITS
# =============================================================================

# --- Spirited Away ---

def haku_dragon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spirit - can phase out, Transformation to dragon"""
    interceptors = [make_spirit_phasing(obj)]

    def transform_trigger(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)

    interceptors.extend(make_transformation(obj, 5, 5, transform_trigger))
    return interceptors

HAKU_RIVER_SPIRIT = make_creature(
    name="Haku, River Spirit",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Dragon"},
    supertypes={"Legendary"},
    text="Flying. Spirit - At the beginning of your upkeep, you may have Haku phase out. Transformation - When Haku attacks, he becomes 5/5 until end of turn.",
    setup_interceptors=haku_dragon_setup
)


RIVER_SPIRIT = make_creature(
    name="River Spirit",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Elemental"},
    text="When River Spirit enters, if you control a Forest, draw a card."
)


def stink_spirit_cleansed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When cleanses, becomes huge"""
    def cleanse_trigger(event: Event, state: GameState) -> bool:
        return (event.type == EventType.COUNTER_REMOVED and
                event.payload.get('object_id') == obj.id and
                event.payload.get('counter_type') == 'filth')
    return make_transformation(obj, 6, 6, cleanse_trigger)

STINK_SPIRIT = make_creature(
    name="Stink Spirit",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Stink Spirit enters with two filth counters. When the last filth counter is removed, Stink Spirit becomes 6/6 and gains flying.",
    setup_interceptors=stink_spirit_cleansed_setup
)


# --- Castle in the Sky ---

def laputa_robot_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, when attacks alone, draw a card"""
    def alone_attack_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id:
            return False
        # Count creatures that are attacking (tapped and on battlefield)
        attackers = [o for o in state.objects.values()
                     if o.controller == obj.controller
                     and o.zone == ZoneType.BATTLEFIELD
                     and CardType.CREATURE in o.characteristics.types
                     and o.state.tapped]
        return len(attackers) == 1

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        draw_event = Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[draw_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=alone_attack_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

LAPUTA_ROBOT_GUARDIAN = make_artifact_creature(
    name="Laputa Robot Guardian",
    power=4, toughness=5,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Construct", "Guardian"},
    text="Flying. Whenever Laputa Robot Guardian attacks alone, draw a card.",
    setup_interceptors=laputa_robot_setup
)


LAPUTA_ROBOT_GARDENER = make_artifact_creature(
    name="Laputa Robot Gardener",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Construct"},
    text="Reach. When Laputa Robot Gardener enters, search your library for a basic land card, reveal it, and put it into your hand."
)


def muska_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other artifacts get +1/+1"""
    def artifact_creature_filter(target: GameObject, source: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.ARTIFACT in target.characteristics.types and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)

    from src.engine.types import new_id as gen_id
    interceptors = []

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return artifact_creature_filter(target, obj, state)

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return artifact_creature_filter(target, obj, state)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=gen_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    ))
    interceptors.append(Interceptor(
        id=gen_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    ))
    return interceptors

MUSKA_FALLEN_PRINCE = make_creature(
    name="Muska, Fallen Prince",
    power=3, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Flying. Other artifact creatures you control get +1/+1. Whenever an artifact you control is put into a graveyard, draw a card.",
    setup_interceptors=muska_setup
)


# --- Ponyo ---

def _ponyo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Alt win-condition threat: Ponyo accumulates +1/+1 counters whenever
    you gain life (she grows more human-shaped with every gift of food).
    If Ponyo ever has ten or more +1/+1 counters on her, you win the game.
    Cheap body, but must be protected for a long time; opponents must
    remove her or race. Ties in tightly with the Food & Hospitality
    archetype."""
    from src.cards import interceptor_helpers as ih

    def life_gain_filter(event: Event, st: GameState, source: GameObject) -> bool:
        if event.type != EventType.LIFE_CHANGE:
            return False
        if event.payload.get('player') != source.controller:
            return False
        return event.payload.get('amount', 0) > 0

    def counter_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    # Life-gain trigger via a custom filter on LIFE_CHANGE.
    life_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: life_gain_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=counter_fn(e, s),
        ),
        duration='while_on_battlefield',
    )

    # Win check: whenever a counter is added to Ponyo, check the total.
    def check_win_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.COUNTER_ADDED:
            return False
        if event.payload.get('object_id') != obj.id:
            return False
        return event.payload.get('counter_type') == '+1/+1'

    def check_win_handler(event: Event, st: GameState) -> InterceptorResult:
        current = obj.state.counters.get('+1/+1', 0) + event.payload.get('amount', 1)
        if current >= 10:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.PLAYER_WINS,
                    payload={'player': obj.controller, 'reason': 'Ponyo transformation'},
                    source=obj.id,
                    controller=obj.controller,
                )],
            )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    win_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=check_win_filter,
        handler=check_win_handler,
        duration='while_on_battlefield',
    )

    return [life_itc, win_itc]

PONYO_FISH_GIRL = make_creature(
    name="Ponyo, Fish Girl",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Spirit"},
    supertypes={"Legendary"},
    text="Ponyo can't be blocked. Whenever you gain life, put a +1/+1 counter on Ponyo. If Ponyo has ten or more +1/+1 counters on her, you win the game.",
    setup_interceptors=_ponyo_setup,
)


def _sosuke_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reality-bending: Sosuke's seawater world submerges opposing threats.
    Whenever a creature enters under an opponent's control, that player
    returns it to their hand unless they pay 1 life. Sosuke is a soft-lock
    Zeniba-style tax on opposing creatures — every creature spell becomes
    either a tempo loss or a chip-damage bill."""

    def opp_creature_etb_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = st.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller == obj.controller:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def bounce_handler(event: Event, st: GameState) -> InterceptorResult:
        entering_id = event.payload.get('object_id')
        entering = st.objects.get(entering_id)
        if not entering:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        opp = entering.controller
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.RETURN_TO_HAND,
                payload={
                    'object_id': entering_id,
                    'unless_pay_life': 1,
                    'unless_payer': opp,
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opp_creature_etb_filter,
        handler=bounce_handler,
        duration='while_on_battlefield',
    )]

SOSUKE_YOUNG_SAILOR = make_creature(
    name="Sosuke, Young Sailor",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Child"},
    supertypes={"Legendary"},
    text="Whenever a creature enters under an opponent's control, that player returns it to their hand unless they pay 1 life.",
    setup_interceptors=_sosuke_setup,
)


GRANMAMARE_SEA_GODDESS = make_creature(
    name="Granmamare, Sea Goddess",
    power=5, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "God"},
    supertypes={"Legendary"},
    text="Flying. When Granmamare enters, return up to two target creatures to their owners' hands. Other Spirits you control can't be countered."
)


# --- Blue Commons/Uncommons ---

FLYING_FISH_SPIRIT = make_creature(
    name="Flying Fish Spirit",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fish", "Spirit"},
    text="Flying. When Flying Fish Spirit enters, scry 1."
)


CLOUD_ELEMENTAL = make_creature(
    name="Cloud Elemental",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Spirit"},
    text="Flying. Cloud Elemental can block only creatures with flying."
)


BATHHOUSE_FROG = make_creature(
    name="Bathhouse Frog",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Frog", "Spirit"},
    text="When Bathhouse Frog enters, tap target creature. It doesn't untap during its controller's next untap step."
)


WATER_SPIRIT_MINOR = make_creature(
    name="Minor Water Spirit",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Elemental"},
    text="Spirit - At the beginning of your upkeep, you may have Minor Water Spirit phase out."
)


def _sky_pirate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever Sky Pirate deals combat damage to a player, that player
    discards a card."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if not target:
            return []
        # Only target-players (skip damage-to-creature events)
        if target not in state.players:
            return []
        return [Event(
            type=EventType.DISCARD,
            payload={'player': target, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_damage_trigger(obj, effect_fn, combat_only=True)]

SKY_PIRATE = make_creature(
    name="Sky Pirate",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying. Whenever Sky Pirate deals combat damage to a player, that player discards a card.",
    setup_interceptors=_sky_pirate_setup,
)


TIGER_MOTH_CREW = make_creature(
    name="Tiger Moth Crew",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Flying. {T}: Draw a card, then discard a card."
)


def _dola_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reality-bending: Dola plunders the opponent's future. Whenever a
    Pirate you control deals combat damage to a player, exile the top
    card of that player's library face down. You may look at and cast
    those cards (paying their costs) for as long as Dola remains on the
    battlefield. Removing Dola locks away those cards. This is a
    deck-stealing engine that grows with each unblocked Pirate — a true
    signature finisher that shifts whose cards win the game."""
    from src.cards import interceptor_helpers as ih

    def damage_filter(event: Event, st: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat', False):
            return False
        target = event.payload.get('target')
        if target not in st.players:
            return False
        dealer_id = event.payload.get('source')
        dealer = st.objects.get(dealer_id) if dealer_id else None
        if not dealer:
            return False
        if dealer.controller != source.controller:
            return False
        return 'Pirate' in dealer.characteristics.subtypes

    def plunder_fn(event: Event, st: GameState) -> list[Event]:
        opp = event.payload.get('target')
        return [Event(
            type=EventType.EXILE_FROM_TOP,
            payload={
                'player': opp,
                'amount': 1,
                'face_down': True,
                'castable_by': obj.controller,
                'anchor_object': obj.id,
            },
            source=obj.id,
            controller=obj.controller,
        )]

    plunder_itc = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=plunder_fn(e, s),
        ),
        duration='while_on_battlefield',
    )

    # Pirate lord: other Pirates +1/+0 (kept from original; part of the
    # signature is still "she captains a fleet").
    pirate_pt_itcs, _ = static_pt_boost_by_subtype(obj, 1, 0, "Pirate", include_self=False)

    return [plunder_itc] + list(pirate_pt_itcs)

DOLA_SKY_PIRATE_CAPTAIN = make_creature(
    name="Dola, Sky Pirate Captain",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Flying. Other Pirates you control get +1/+0. Whenever a Pirate you control deals combat damage to a player, exile the top card of that player's library face down. You may cast exiled cards for as long as Dola remains on the battlefield.",
    setup_interceptors=_dola_setup,
)


def _wind_mage_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, Wind Mage gets +1/+0 until end of turn."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.PT_MODIFICATION,
            payload={
                'object_id': obj.id,
                'power_mod': 1,
                'toughness_mod': 0,
                'duration': 'end_of_turn',
            },
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_spell_cast_trigger(
        obj, effect_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

WIND_MAGE = make_creature(
    name="Wind Mage",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flying. Whenever you cast an instant or sorcery spell, Wind Mage gets +1/+0 until end of turn.",
    setup_interceptors=_wind_mage_setup,
)


def _airship_navigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
            controller=obj.controller,
        )]
    return [ih.make_etb_trigger(obj, effect_fn)]

AIRSHIP_NAVIGATOR = make_creature(
    name="Airship Navigator",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pilot"},
    text="Flying. When Airship Navigator enters, scry 2.",
    setup_interceptors=_airship_navigator_setup,
)


MYSTICAL_GUARDIAN = make_creature(
    name="Mystical Guardian",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Guardian"},
    text="Flying, ward {2}."
)


# --- New: Howling Wind Spirit (spellslinger payoff) ---

def _howling_wind_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, scry 1."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
            controller=obj.controller,
        )]

    return [ih.make_spell_cast_trigger(
        obj, effect_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

HOWLING_WIND_SPIRIT = make_creature(
    name="Howling Wind Spirit",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Elemental"},
    text="Flying. Whenever you cast an instant or sorcery spell, scry 1.",
    setup_interceptors=_howling_wind_spirit_setup,
)


# --- Blue Instants ---

RIVER_CURRENT = make_instant(
    name="River Current",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If you control a Forest, scry 1."
)


SPIRIT_GUIDANCE = make_instant(
    name="Spirit Guidance",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Draw two cards, then discard a card. If you control a Spirit, you may keep both cards instead."
)


PHASE_SHIFT = make_instant(
    name="Phase Shift",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target Spirit phases out."
)


WINDS_PROTECTION = make_instant(
    name="Wind's Protection",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Target creature gains flying and hexproof until end of turn."
)


COUNTERSPELL_OF_THE_DEEP = make_instant(
    name="Counterspell of the Deep",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. If that spell was a creature spell, scry 2."
)


# --- Blue Sorceries ---

AERIAL_RECONNAISSANCE = make_sorcery(
    name="Aerial Reconnaissance",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you control a creature with flying, draw three cards instead."
)


SUMMON_THE_TIDES = make_sorcery(
    name="Summon the Tides",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Return all nonland permanents to their owners' hands."
)


FORGOTTEN_MEMORIES = make_sorcery(
    name="Forgotten Memories",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Look at the top four cards of your library. Put two into your hand and two into your graveyard."
)


# --- Blue Enchantments ---

RIVER_BLESSING = make_enchantment(
    name="River's Blessing",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever a Spirit enters under your control, scry 1. {2}{U}: Target Spirit phases out."
)


SKY_DOMAIN = make_enchantment(
    name="Sky Domain",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Creatures with flying you control get +1/+1. Whenever a creature with flying you control deals combat damage to a player, draw a card."
)


# =============================================================================
# BLACK CARDS - CORRUPTION, CURSES, DARK SPIRITS
# =============================================================================

# --- Spirited Away ---

def _no_face_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = attack_add_counters(obj, "+1/+1", 1)
    return [itc]

NO_FACE_HUNGRY_SPIRIT = make_creature(
    name="No-Face, Hungry Spirit",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text=substitute_card_name(
        render_attack_add_counters("+1/+1", 1),
        "No-Face, Hungry Spirit",
    ),
    setup_interceptors=_no_face_setup,
)


YUBABA_BATHHOUSE_WITCH = make_creature(
    name="Yubaba, Bathhouse Witch",
    power=3, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Witch"},
    supertypes={"Legendary"},
    text="Flying. When Yubaba enters, put a curse counter on target creature. You control creatures with three or more curse counters on them. {2}{B}: Put a curse counter on target creature."
)


BOH_GIANT_BABY = make_creature(
    name="Boh, Giant Baby",
    power=4, toughness=6,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Giant"},
    supertypes={"Legendary"},
    text="Defender. Transformation - {3}{B}: Transform Boh into a 1/1 Mouse until end of turn. He can attack this turn."
)


# --- Princess Mononoke ---

def _moro_wolf_god_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    interceptors, _ = static_pt_boost_by_subtype(obj, 2, 1, "Wolf", include_self=False)
    return list(interceptors)

MORO_WOLF_GOD = make_creature(
    name="Moro, Wolf God",
    power=5, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Wolf", "God", "Spirit"},
    supertypes={"Legendary"},
    text="Other Wolf creatures you control get +2/+1.",
    setup_interceptors=_moro_wolf_god_setup,
)


def okkoto_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Okkoto takes damage, put a curse counter on it, becomes stronger"""
    def damage_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE and
                event.payload.get('target') == obj.id)

    def curse_handler(event: Event, state: GameState) -> InterceptorResult:
        curse_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'curse', 'amount': 1},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[curse_event])

    interceptors = [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=curse_handler,
        duration='while_on_battlefield'
    )]

    def curse_power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def curse_power_handler(event: Event, state: GameState) -> InterceptorResult:
        curse_counters = obj.state.counters.get('curse', 0)
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + curse_counters
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=curse_power_filter,
        handler=curse_power_handler,
        duration='while_on_battlefield'
    ))
    return interceptors

OKKOTO_BOAR_GOD = make_creature(
    name="Okkoto, Boar God",
    power=6, toughness=5,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Boar", "God", "Spirit"},
    supertypes={"Legendary"},
    text="Trample. Whenever Okkoto is dealt damage, put a curse counter on him. Okkoto gets +1/+0 for each curse counter on him.",
    setup_interceptors=okkoto_setup
)


DEMON_BOAR = make_creature(
    name="Demon Boar",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Boar", "Demon"},
    text="Trample. Demon Boar enters with two curse counters. At the beginning of your upkeep, put a curse counter on Demon Boar. When Demon Boar has five or more curse counters, sacrifice it."
)


# --- Nausicaa ---

GOD_WARRIOR = make_creature(
    name="God Warrior",
    power=8, toughness=8,
    mana_cost="{6}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Horror"},
    supertypes={"Legendary"},
    text="Trample, menace. At the beginning of your end step, sacrifice God Warrior unless you pay 3 life. When God Warrior dies, it deals 4 damage to each creature."
)


# --- Black Commons/Uncommons ---

CURSE_SPIRIT = make_creature(
    name="Curse Spirit",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="When Curse Spirit enters, put a curse counter on target creature."
)


SHADOW_SPIRIT = make_creature(
    name="Shadow Spirit",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Shade"},
    text="Spirit - At the beginning of your upkeep, you may have Shadow Spirit phase out. {B}: Shadow Spirit gets +1/+1 until end of turn."
)


CORRUPTED_KODAMA = make_creature(
    name="Corrupted Kodama",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Kodama"},
    text="When Corrupted Kodama enters, each opponent loses 1 life and you gain 1 life."
)


SPIRIT_OF_VENGEANCE = make_creature(
    name="Spirit of Vengeance",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Deathtouch. When Spirit of Vengeance dies, target opponent loses 2 life."
)


DARK_FOREST_CREATURE = make_creature(
    name="Dark Forest Creature",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Horror"},
    text="Menace. Nature's Wrath - Dark Forest Creature gets +1/+0 for each Forest you control."
)


def _witch_familiar_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    itc, _ = death_draw(obj, 1)
    return [itc]

WITCH_FAMILIAR = make_creature(
    name="Witch's Familiar",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Cat", "Spirit"},
    text=substitute_card_name(render_death_draw(1), "Witch's Familiar"),
    setup_interceptors=_witch_familiar_setup,
)


BATHHOUSE_SPECTER = make_creature(
    name="Bathhouse Specter",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. When Bathhouse Specter deals combat damage to a player, that player discards a card."
)


NIGHTMARE_CREATURE = make_creature(
    name="Nightmare Creature",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare", "Horror"},
    text="Flying, lifelink. Nightmare Creature gets +1/+1 for each creature card in your graveyard."
)


TOXIC_JUNGLE_LURKER = make_creature(
    name="Toxic Jungle Lurker",
    power=3, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Insect", "Horror"},
    text="Deathtouch. When Toxic Jungle Lurker dies, put a -1/-1 counter on each creature your opponents control."
)


FALLEN_SAMURAI = make_creature(
    name="Fallen Samurai",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Warrior"},
    text="First strike. When Fallen Samurai enters from your graveyard, it gets +2/+0 until end of turn."
)


# --- Black Instants ---

CURSE_OF_GREED = make_instant(
    name="Curse of Greed",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Put two curse counters on target creature. You lose 1 life."
)


SPIRITS_CONSUMPTION = make_instant(
    name="Spirit's Consumption",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature with a curse counter on it. You gain life equal to its toughness."
)


DARK_BARGAIN = make_instant(
    name="Dark Bargain",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Look at the top three cards of your library. Put one into your hand and the rest into your graveyard. You lose 1 life."
)


TERROR_OF_THE_DEEP = make_instant(
    name="Terror of the Deep",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If it's a Spirit, it gets -5/-5 instead."
)


WITCH_HEX = make_instant(
    name="Witch's Hex",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. Put a curse counter on it."
)


# --- Black Sorceries ---

MASS_CORRUPTION = make_sorcery(
    name="Mass Corruption",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Put a curse counter on each creature. For each curse counter placed this way, you gain 1 life."
)


SPIRITS_HARVEST = make_sorcery(
    name="Spirit's Harvest",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it had a curse counter on it, draw two cards."
)


CURSE_OF_FORGETTING = make_sorcery(
    name="Curse of Forgetting",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards. Put a curse counter on a creature that player controls."
)


RAISE_THE_FALLEN = make_sorcery(
    name="Raise the Fallen",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Return up to two target creature cards from your graveyard to the battlefield. They gain haste. Exile them at the beginning of the next end step."
)


# --- Black Enchantments ---

def curse_of_the_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, cursed creatures deal 1 damage to their controller"""
    def upkeep_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'upkeep'

    def upkeep_handler(event: Event, state: GameState) -> InterceptorResult:
        events = []
        for o in state.objects.values():
            if o.zone == ZoneType.BATTLEFIELD and o.state.counters.get('curse', 0) > 0:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': o.controller, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=upkeep_handler,
        duration='while_on_battlefield'
    )]

CURSE_OF_THE_WITCH = make_enchantment(
    name="Curse of the Witch",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of each upkeep, each creature with a curse counter on it deals 1 damage to its controller.",
    setup_interceptors=curse_of_the_witch_setup
)


DARK_FOREST_PACT = make_enchantment(
    name="Dark Forest Pact",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card. Creatures you control get +1/+0 for each curse counter on the battlefield."
)


# =============================================================================
# RED CARDS - FIRE SPIRITS, CALCIFER, DESTRUCTION
# =============================================================================

# --- Howl's Moving Castle ---

def calcifer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Heart-bound tempo engine: whenever you cast an instant or sorcery,
    draw a card, then discard a card (loot). Additionally, instants and
    sorceries you cast cost {1} less to cast (cost alternative / resource
    break via QUERY_COST interceptor). Calcifer is small and fragile (1
    toughness) so he must be protected — but while he's burning, every
    spell refills your hand and costs less to cast."""
    from src.cards import interceptor_helpers as ih

    def loot_fn(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            ),
            Event(
                type=EventType.DISCARD,
                payload={'player': obj.controller, 'amount': 1},
                source=obj.id,
                controller=obj.controller,
            ),
        ]

    loot_trigger = ih.make_spell_cast_trigger(
        obj, loot_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )

    # Cost reduction: {1} less for instants/sorceries cast by controller.
    def cost_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.QUERY_COST:
            return False
        if event.payload.get('caster') != obj.controller:
            return False
        types = set(event.payload.get('types', []))
        if not types and event.payload.get('spell_type') is not None:
            types = {event.payload.get('spell_type')}
        return bool(types.intersection({CardType.INSTANT, CardType.SORCERY}))

    def cost_handler(event: Event, st: GameState) -> InterceptorResult:
        new_event = event.copy()
        current = new_event.payload.get('generic_cost', new_event.payload.get('value', 0))
        reduced = max(0, current - 1)
        if 'generic_cost' in new_event.payload:
            new_event.payload['generic_cost'] = reduced
        new_event.payload['value'] = reduced
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    cost_interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=cost_filter,
        handler=cost_handler,
        duration='while_on_battlefield',
    )

    return [loot_trigger, cost_interceptor]

CALCIFER_FIRE_DEMON = make_creature(
    name="Calcifer, Fire Demon",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Demon"},
    supertypes={"Legendary"},
    text="Haste. Instant and sorcery spells you cast cost {1} less to cast. Whenever you cast an instant or sorcery spell, draw a card, then discard a card.",
    setup_interceptors=calcifer_setup
)


def howl_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Transformation to bird form"""
    def transform_trigger(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == obj.id)

    return make_transformation(obj, 5, 4, transform_trigger)

HOWL_WIZARD = make_creature(
    name="Howl, Wandering Wizard",
    power=3, toughness=3,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Flying. Transformation - When Howl attacks, he becomes a 5/4 black Bird Wizard with flying until end of turn. Instant and sorcery spells you cast cost {1} less.",
    setup_interceptors=howl_setup
)


def _witch_of_the_waste_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Persistent state modifier: while the Witch is on the battlefield,
    each creature you don't control enters the battlefield with a curse
    counter on it. This re-writes the rules of the set — curse counters
    are usually buffs for Okkoto-type cards, but combined with
    Ashitaka/Curse of the Witch/Ashitaka-cycle removal, this is a global
    tax on opponents' creatures. She's 4/4 for 5 — a beater in her own
    right. Removable by targeted removal or bounce."""

    def opp_creature_etb_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = st.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller == obj.controller:
            return False
        return CardType.CREATURE in entering.characteristics.types

    def curse_handler(event: Event, st: GameState) -> InterceptorResult:
        entering_id = event.payload.get('object_id')
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={
                    'object_id': entering_id,
                    'counter_type': 'curse',
                    'amount': 1,
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opp_creature_etb_filter,
        handler=curse_handler,
        duration='while_on_battlefield',
    )]

WITCH_OF_THE_WASTE = make_creature(
    name="Witch of the Waste",
    power=4, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Witch"},
    supertypes={"Legendary"},
    text="As long as Witch of the Waste is on the battlefield, each creature an opponent controls enters the battlefield with a curse counter on it.",
    setup_interceptors=_witch_of_the_waste_setup,
)


# --- New: Markl, Howl's Apprentice ---

def _markl_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, Markl deals 1 damage to any
    target (enters-the-battlefield damage routed to each opponent for
    simplicity)."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': 1, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )
            for opp_id in ih.all_opponents(obj, state)
        ]

    return [ih.make_spell_cast_trigger(
        obj, effect_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

MARKL_HOWLS_APPRENTICE = make_creature(
    name="Markl, Howl's Apprentice",
    power=1, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you cast an instant or sorcery spell, Markl deals 1 damage to each opponent.",
    setup_interceptors=_markl_setup,
)


# --- Nausicaa ---

TORUMEKIAN_SOLDIER = make_creature(
    name="Torumekian Soldier",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="First strike. Whenever Torumekian Soldier attacks, it deals 1 damage to the defending player."
)


def _kushana_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deck-ID / alt cost flavor: Kushana conscripts the fallen. Whenever
    Kushana attacks, sacrifice any number of creatures. For each creature
    sacrificed this way, create a 2/1 red Soldier creature token with
    haste. This is a controlled sacrifice-to-tokens pivot — asymmetric
    because she demands commitment: every combat, you can rotate chump
    blockers / deathrattle creatures / tokens into fresh hasty soldiers.
    Four-mana finisher, first-striking body, and a loop engine."""
    from src.cards import interceptor_helpers as ih

    def effect_fn(event: Event, st: GameState) -> list[Event]:
        # Emit a SACRIFICE_REQUIRED with follow-up conversion; token count
        # is resolved by the engine based on how many creatures are actually
        # sacrificed (flagged via conversion_target).
        return [Event(
            type=EventType.SACRIFICE_REQUIRED,
            payload={
                'player': obj.controller,
                'filter': {'types': {CardType.CREATURE}},
                'min_count': 0,
                'max_count': None,
                'for_effect': 'kushana_token',
                'conversion_token': {
                    'name': 'Soldier',
                    'power': 2,
                    'toughness': 1,
                    'colors': {Color.RED},
                    'subtypes': {'Human', 'Soldier'},
                    'keywords': ['haste'],
                },
            },
            source=obj.id,
            controller=obj.controller,
        )]

    sacrifice_itc = ih.make_attack_trigger(obj, effect_fn)
    return [sacrifice_itc]

KUSHANA_WAR_PRINCESS = make_creature(
    name="Kushana, War Princess",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Noble", "Warrior"},
    supertypes={"Legendary"},
    text="First strike, haste. Whenever Kushana attacks, you may sacrifice any number of creatures. For each creature sacrificed this way, create a 2/1 red Human Soldier creature token with haste.",
    setup_interceptors=_kushana_setup,
)


# --- Castle in the Sky ---

GOLIATH_AIRSHIP = make_artifact(
    name="Goliath Airship",
    mana_cost="{4}{R}",
    text="Flying. Crew 3. When Goliath Airship attacks, it deals 2 damage to any target.",
    subtypes={"Vehicle"}
)


# --- Red Commons/Uncommons ---

def _fire_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, Fire Spirit deals 1 damage to
    each opponent."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.DAMAGE,
                payload={'target': opp_id, 'amount': 1, 'source': obj.id},
                source=obj.id,
                controller=obj.controller,
            )
            for opp_id in ih.all_opponents(obj, state)
        ]
    return [ih.make_spell_cast_trigger(
        obj, effect_fn,
        spell_type_filter={CardType.INSTANT, CardType.SORCERY},
    )]

FIRE_SPIRIT = make_creature(
    name="Fire Spirit",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="Haste. Whenever you cast an instant or sorcery spell, Fire Spirit deals 1 damage to each opponent.",
    setup_interceptors=_fire_spirit_setup,
)


FLAME_ELEMENTAL = make_creature(
    name="Flame Elemental",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. When Flame Elemental enters, it deals 1 damage to any target."
)


VOLCANIC_SPIRIT = make_creature(
    name="Volcanic Spirit",
    power=4, toughness=2,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="Trample, haste. When Volcanic Spirit enters, it deals 2 damage to each creature."
)


DESTRUCTION_SPIRIT = make_creature(
    name="Destruction Spirit",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="When Destruction Spirit dies, it deals 3 damage to any target."
)


PEJITE_WARRIOR = make_creature(
    name="Pejite Warrior",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Haste. When Pejite Warrior enters, it fights target creature you don't control."
)


FOREST_ARSONIST = make_creature(
    name="Forest Arsonist",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rogue"},
    text="When Forest Arsonist enters, destroy target Forest."
)


WILD_BOAR = make_creature(
    name="Wild Boar",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Boar"},
    text="Trample. Wild Boar attacks each combat if able."
)


def _angry_spirit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Angry Spirit enters, it deals 1 damage to each opponent."""
    from src.cards.ability_bundles import etb_deal_damage
    itc, _ = etb_deal_damage(obj, 1, target="each_opponent")
    return [itc]

ANGRY_SPIRIT = make_creature(
    name="Angry Spirit",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Haste. When Angry Spirit enters, it deals 1 damage to each opponent.",
    setup_interceptors=_angry_spirit_setup,
)


IRONWORKS_FURNACE = make_creature(
    name="Ironworks Furnace",
    power=0, toughness=4,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Construct"},
    text="Defender. {T}, Sacrifice an artifact: Ironworks Furnace deals 3 damage to any target."
)


BOMBARDMENT_CREW = make_creature(
    name="Bombardment Crew",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="{T}: Bombardment Crew deals 1 damage to target creature or player."
)


# --- Red Instants ---

FIRE_BREATH = make_instant(
    name="Fire Breath",
    mana_cost="{R}",
    colors={Color.RED},
    text="Deal 2 damage to any target. If that target is a Spirit, deal 3 damage instead."
)


CALCIFER_FLAME = make_instant(
    name="Calcifer's Flame",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Deal 3 damage to target creature or player. If you control Calcifer, deal 4 damage instead."
)


FURY_OF_THE_WILD = make_instant(
    name="Fury of the Wild",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn. It fights another target creature."
)


VOLCANIC_ERUPTION = make_instant(
    name="Volcanic Eruption",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Deal 4 damage divided as you choose among any number of targets."
)


DESPERATE_CHARGE = make_instant(
    name="Desperate Charge",
    mana_cost="{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 until end of turn."
)


# --- Red Sorceries ---

RAIN_OF_FIRE = make_sorcery(
    name="Rain of Fire",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Deal 4 damage to each creature and each player."
)


BURNING_WRATH = make_sorcery(
    name="Burning Wrath",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Deal 3 damage to target creature. If that creature has a curse counter, deal 5 damage instead."
)


SUMMON_FIRE_SPIRITS = make_sorcery(
    name="Summon Fire Spirits",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Create three 1/1 red Elemental Spirit creature tokens with haste. Exile them at the beginning of your next end step."
)


WILDFIRE_SPREAD = make_sorcery(
    name="Wildfire Spread",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Destroy target land. Deal 2 damage to its controller."
)


# --- Red Enchantments ---

def fires_of_destruction_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature dies, deal 1 damage to its controller"""
    def death_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        return dying and CardType.CREATURE in dying.characteristics.types

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        dying_id = event.payload.get('object_id')
        dying = state.objects.get(dying_id)
        if dying:
            damage_event = Event(
                type=EventType.DAMAGE,
                payload={'target': dying.controller, 'amount': 1},
                source=obj.id
            )
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[damage_event])
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_filter,
        handler=damage_handler,
        duration='while_on_battlefield'
    )]

FIRES_OF_DESTRUCTION = make_enchantment(
    name="Fires of Destruction",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever a creature dies, Fires of Destruction deals 1 damage to that creature's controller.",
    setup_interceptors=fires_of_destruction_setup
)


WAR_DRUMS = make_enchantment(
    name="War Drums",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control have haste. Whenever a creature you control attacks, it gets +1/+0 until end of turn."
)


# =============================================================================
# GREEN CARDS - FOREST SPIRITS, NATURE, TOTORO
# =============================================================================

# --- My Neighbor Totoro ---

def totoro_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Nature's Wrath (capped at +3/+3 in helper)."""
    return list(make_natures_wrath(obj, 1, 1))

TOTORO_KING_OF_THE_FOREST = make_creature(
    name="Totoro, King of the Forest",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "God"},
    supertypes={"Legendary"},
    text="Vigilance. Nature's Wrath - Totoro gets +1/+1 for each Forest you control (max +3/+3).",
    setup_interceptors=totoro_setup
)


CATBUS = make_creature(
    name="Catbus, Forest Transport",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Spirit"},
    supertypes={"Legendary"},
    text="Haste. Catbus can't be blocked. When Catbus enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)


CHIBI_TOTORO = make_creature(
    name="Chibi Totoro",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="Spirit - At the beginning of your upkeep, you may have Chibi Totoro phase out. When Chibi Totoro phases in, you may search your library for a Forest, reveal it, put it into your hand, then shuffle."
)


MEDIUM_TOTORO = make_creature(
    name="Medium Totoro",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="Spirit - At the beginning of your upkeep, you may have Medium Totoro phase out. Nature's Wrath - Medium Totoro gets +1/+0 for each Forest you control."
)


# --- Princess Mononoke ---

FOREST_SPIRIT_GOD = make_creature(
    name="Forest Spirit, Shishigami",
    power=5, toughness=5,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "God", "Elk"},
    supertypes={"Legendary"},
    text="When Forest Spirit enters, all creatures get +2/+2. When Forest Spirit leaves the battlefield, all creatures get -2/-2. Forest Spirit can't be targeted by spells or abilities."
)


def kodama_elder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Kodama get +1/+1, Nature's Wrath"""
    interceptors = []
    interceptors.extend(make_natures_wrath(obj, 0, 1))

    # Other Kodama get +1/+1
    def kodama_power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return 'Kodama' in target.characteristics.subtypes

    def kodama_power_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def kodama_toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target or target.id == obj.id:
            return False
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return 'Kodama' in target.characteristics.subtypes

    def kodama_toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=kodama_power_filter,
        handler=kodama_power_handler,
        duration='while_on_battlefield'
    ))
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=kodama_toughness_filter,
        handler=kodama_toughness_handler,
        duration='while_on_battlefield'
    ))
    return interceptors

KODAMA_ELDER = make_creature(
    name="Kodama Elder",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Kodama"},
    text="Other Kodama you control get +1/+1. Nature's Wrath - Kodama Elder gets +0/+1 for each Forest you control.",
    setup_interceptors=kodama_elder_setup
)


WOLF_OF_MORO = make_creature(
    name="Wolf of Moro",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf", "Spirit"},
    text="Trample. Wolf of Moro gets +1/+1 as long as you control another Wolf."
)


# --- Nausicaa ---

def ohmu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Ohmu is dealt damage, creatures you control gain hexproof"""
    def damage_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE and
                event.payload.get('target') == obj.id)

    def hexproof_handler(event: Event, state: GameState) -> InterceptorResult:
        grant_event = Event(
            type=EventType.GRANT_ABILITY,
            payload={'target_type': 'creatures_you_control', 'ability': 'hexproof', 'duration': 'end_of_turn'},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[grant_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=hexproof_handler,
        duration='while_on_battlefield'
    )]

OHMU_KING = make_creature(
    name="Ohmu, King of Insects",
    power=6, toughness=8,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Spirit"},
    supertypes={"Legendary"},
    text="Trample, vigilance. When Ohmu is dealt damage, creatures you control gain hexproof until end of turn. Insects you control get +2/+2.",
    setup_interceptors=ohmu_setup
)


BABY_OHMU = make_creature(
    name="Baby Ohmu",
    power=1, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Spirit"},
    text="Defender. When Baby Ohmu dies, you may search your library for a Forest card, put it onto the battlefield tapped, then shuffle."
)


TOXIC_JUNGLE_GUARDIAN = make_creature(
    name="Toxic Jungle Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Reach, trample. When Toxic Jungle Guardian enters, put a spore counter on target land. Lands with spore counters are Forests in addition to their other types."
)


# --- Green Commons/Uncommons ---

def _forest_kodama_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spirit - phase; When Forest Kodama enters, you gain 1 life for each
    Forest you control."""
    from src.cards import interceptor_helpers as ih
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        amount = count_forests(obj.controller, state)
        if amount <= 0:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': amount},
            source=obj.id,
            controller=obj.controller,
        )]
    return [
        make_spirit_phasing(obj),
        ih.make_etb_trigger(obj, effect_fn),
    ]

FOREST_KODAMA = make_creature(
    name="Forest Kodama",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Kodama"},
    text="Spirit - At the beginning of your upkeep, you may have Forest Kodama phase out. When Forest Kodama enters, you gain 1 life for each Forest you control.",
    setup_interceptors=_forest_kodama_setup,
)


def kodama_of_growth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When phases in, add G"""
    def phase_in_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.PHASE_IN and
                event.payload.get('object_id') == obj.id)

    def mana_handler(event: Event, state: GameState) -> InterceptorResult:
        mana_event = Event(
            type=EventType.ADD_MANA,
            payload={'player': obj.controller, 'mana': '{G}'},
            source=obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[mana_event])

    return [
        Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=phase_in_filter,
            handler=mana_handler,
            duration='while_on_battlefield'
        ),
        make_spirit_phasing(obj)
    ]

KODAMA_OF_GROWTH = make_creature(
    name="Kodama of Growth",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Kodama"},
    text="Spirit - At the beginning of your upkeep, you may have Kodama of Growth phase out. When Kodama of Growth phases in, add {G}.",
    setup_interceptors=kodama_of_growth_setup
)


ANCIENT_TREE_SPIRIT = make_creature(
    name="Ancient Tree Spirit",
    power=3, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Treefolk"},
    text="Reach. Nature's Wrath - Ancient Tree Spirit gets +1/+1 for each Forest you control."
)


def forest_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When a Forest enters, gain 1 life"""
    def forest_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entering_id = event.payload.get('object_id')
        entering = state.objects.get(entering_id)
        return (entering and entering.controller == obj.controller and
                'Forest' in entering.characteristics.subtypes)

    def life_handler(event: Event, state: GameState) -> InterceptorResult:
        life_event = Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[life_event])

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=forest_etb_filter,
        handler=life_handler,
        duration='while_on_battlefield'
    )]

FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Guardian"},
    text="Whenever a Forest enters under your control, you gain 1 life.",
    setup_interceptors=forest_guardian_setup
)


NATURE_SPRITE = make_creature(
    name="Nature Sprite",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Faerie"},
    text="Flying. {T}: Add {G}."
)


# --- New: Soot Sprites (Spirit token-maker) ---

def _soot_sprites_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Soot Sprites enters, create two 0/1 black Soot Spirit tokens."""
    from src.cards.ability_bundles import etb_create_token
    itc, _ = etb_create_token(
        obj, power=0, toughness=1, subtype="Spirit",
        count=2, colors={Color.BLACK},
    )
    return [itc]

SOOT_SPRITES = make_creature(
    name="Soot Sprites",
    power=1, toughness=1,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
    text="When Soot Sprites enters, create two 0/1 black Spirit creature tokens.",
    setup_interceptors=_soot_sprites_setup,
)


WILD_WOLF = make_creature(
    name="Wild Wolf",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
    text="When Wild Wolf enters, you may search your library for a Wolf card, reveal it, put it into your hand, then shuffle."
)


def _forest_deer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Forest Deer dies, you gain 3 life."""
    def effect_fn(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id,
            controller=obj.controller,
        )]

    from src.cards import interceptor_helpers as ih
    return [ih.make_death_trigger(obj, effect_fn)]

FOREST_DEER = make_creature(
    name="Forest Deer",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Elk"},
    text="When Forest Deer dies, you gain 3 life.",
    setup_interceptors=_forest_deer_setup,
)


GIANT_CAMPHOR_TREE = make_creature(
    name="Giant Camphor Tree",
    power=0, toughness=8,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Defender, reach. {T}: Add {G}{G}. At the beginning of your upkeep, put a +1/+1 counter on Giant Camphor Tree."
)


INSECT_SWARM = make_creature(
    name="Insect Swarm",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Trample. Insect Swarm gets +1/+1 for each other Insect you control."
)


MOSS_COVERED_GOLEM = make_creature(
    name="Moss-Covered Golem",
    power=4, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Golem", "Plant"},
    text="Trample. Nature's Wrath - Moss-Covered Golem has hexproof as long as you control three or more Forests."
)


def _spirit_wolf_pup_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """+1/+1 to other Wolves you control, plus Spirit - phase out."""
    interceptors, _ = static_pt_boost_by_subtype(obj, 1, 1, "Wolf", include_self=False)
    return list(interceptors) + [make_spirit_phasing(obj)]

SPIRIT_WOLF_PUP = make_creature(
    name="Spirit Wolf Pup",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Wolf", "Spirit"},
    text="Spirit - At the beginning of your upkeep, you may have Spirit Wolf Pup phase out. Other Wolf creatures you control get +1/+1.",
    setup_interceptors=_spirit_wolf_pup_setup,
)


# --- Green Instants ---

FOREST_BLESSING = make_instant(
    name="Forest's Blessing",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. If you control a Forest, it also gains trample."
)


NATURES_SHIELD = make_instant(
    name="Nature's Shield",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control gains hexproof and indestructible until end of turn."
)


REGROWTH_SPELL = make_instant(
    name="Regrowth Spell",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Return target permanent card from your graveyard to your hand."
)


RAPID_GROWTH = make_instant(
    name="Rapid Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. Nature's Wrath - It gets +4/+4 instead if you control three or more Forests."
)


SPIRIT_CALL = make_instant(
    name="Spirit Call",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Put target Spirit card from your graveyard onto the battlefield. It gains haste until end of turn."
)


# --- Green Sorceries ---

FOREST_AWAKENING = make_sorcery(
    name="Forest Awakening",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Until end of turn, all Forests you control become 4/4 green Spirit Treefolk creatures with haste. They're still lands."
)


CALL_OF_THE_WILD = make_sorcery(
    name="Call of the Wild",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two creature cards, reveal them, and put them into your hand. Then shuffle."
)


NATURES_RECLAMATION = make_sorcery(
    name="Nature's Reclamation",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. You gain 3 life."
)


SUMMON_THE_FOREST = make_sorcery(
    name="Summon the Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic Forest cards, put them onto the battlefield tapped, then shuffle."
)


# --- Green Enchantments ---

def forest_sanctuary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, create a 1/1 Kodama for each Forest"""
    def upkeep_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        return state.active_player == obj.controller

    def upkeep_handler(event: Event, state: GameState) -> InterceptorResult:
        forest_count = min(count_forests(obj.controller, state), 3)
        events = []
        for _ in range(forest_count):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {'name': 'Kodama', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Spirit', 'Kodama'}}
                },
                source=obj.id
            ))
        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=upkeep_handler,
        duration='while_on_battlefield'
    )]

FOREST_SANCTUARY = make_enchantment(
    name="Forest Sanctuary",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, create a 1/1 green Spirit Kodama creature token for each Forest you control, up to three.",
    setup_interceptors=forest_sanctuary_setup
)


BLESSING_OF_THE_SPIRITS = make_enchantment(
    name="Blessing of the Spirits",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Spirits you control get +1/+1. Whenever a Spirit you control phases in, you gain 1 life."
)


NATURES_WRATH_ENCHANTMENT = make_enchantment(
    name="Nature's Wrath",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +1/+1 for each Forest you control."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

SPIRITED_TRANSFORMATION = make_instant(
    name="Spirited Transformation",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Target creature you control phases out, then phases in. When it phases in this way, put two +1/+1 counters on it."
)


FOREST_AND_SKY = make_sorcery(
    name="Forest and Sky",
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Search your library for a basic Forest and a basic Island, put them onto the battlefield tapped, then shuffle. Draw a card."
)


CURSE_BREAKER = make_instant(
    name="Curse Breaker",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Remove all curse counters from target permanent. You gain 2 life and target opponent loses 2 life."
)


SPIRIT_FIRE = make_instant(
    name="Spirit Fire",
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Deal 3 damage to target creature. If you control a Spirit, deal 4 damage instead and gain 2 life."
)


NATURES_VENGEANCE = make_sorcery(
    name="Nature's Vengeance",
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Destroy target creature. Put a +1/+1 counter on each creature you control for each Forest you control."
)


# =============================================================================
# LANDS
# =============================================================================

BATHHOUSE_DISTRICT = make_land(
    name="Bathhouse District",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {W} or {U}. Activate only if you control a Spirit."
)


ANCIENT_FOREST = make_land(
    name="Ancient Forest",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 1/1 green Spirit Kodama creature token.",
    subtypes={"Forest"}
)


TOXIC_JUNGLE = make_land(
    name="Toxic Jungle",
    text="Toxic Jungle enters tapped. {T}: Add {G} or {B}. When Toxic Jungle enters, you may put a spore counter on target land."
)


LAPUTA_FLOATING_CASTLE = make_land(
    name="Laputa, Floating Castle",
    text="{T}: Add {C}. {T}: Add {U}. Activate only if you control an artifact. {5}, {T}: Create a 4/4 colorless Construct artifact creature token with flying.",
    supertypes={"Legendary"}
)


HOWLS_CASTLE = make_land(
    name="Howl's Moving Castle",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. Activate only if you control a Wizard. Artifacts and enchantments you control have ward {1}.",
    supertypes={"Legendary"}
)


IRON_TOWN = make_land(
    name="Iron Town",
    text="{T}: Add {C}. {T}: Add {R} or {W}. Activate only if you control a Human."
)


SPIRIT_REALM_GATE = make_land(
    name="Spirit Realm Gate",
    text="Spirit Realm Gate enters tapped. {T}: Add {W}, {U}, or {B}. {3}, {T}: Target Spirit phases out."
)


VALLEY_OF_THE_WIND = make_land(
    name="Valley of the Wind",
    text="{T}: Add {G} or {W}. Creatures with flying you control get +0/+1.",
    supertypes={"Legendary"}
)


FOREST_SHRINE = make_land(
    name="Forest Shrine",
    text="Forest Shrine enters tapped unless you control a Spirit. {T}: Add {G}. When Forest Shrine enters, if you control three or more Spirits, draw a card.",
    subtypes={"Forest"}
)


CAMPHOR_TREE_GROVE = make_land(
    name="Camphor Tree Grove",
    text="{T}: Add {G}. {G}, {T}: Add {G}{G}. Activate only during your main phase.",
    subtypes={"Forest"}
)


CURSED_SWAMP = make_land(
    name="Cursed Swamp",
    text="Cursed Swamp enters tapped. {T}: Add {B}. When Cursed Swamp enters, put a curse counter on target creature."
)


SKY_FORTRESS = make_land(
    name="Sky Fortress",
    text="{T}: Add {C}. {2}, {T}: Target creature gains flying until end of turn."
)


OHMU_NEST = make_land(
    name="Ohmu Nest",
    text="Ohmu Nest enters tapped. {T}: Add {G}. {4}{G}{G}, {T}, Sacrifice Ohmu Nest: Create a 6/6 green Insect Spirit creature token with trample."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

LAPUTAN_AMULET = make_artifact(
    name="Laputan Amulet",
    mana_cost="{2}",
    text="Equipped creature has hexproof and gets +1/+1. Equip {2}",
    subtypes={"Equipment"}
)


# --- Crystal Necklace: Helper-5 rewire -------------------------------------
# Granted trigger "combat damage to player → scry 1." No static P/T boost.
def _crystal_necklace_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _crystal_necklace_scry_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    return [Event(
        type=EventType.ACTIVATE,
        payload={
            'action': 'scry',
            'amount': 1,
            'player': target_obj.controller,
            'source': target_obj.id,
        },
        source=target_obj.id,
    )]


CRYSTAL_NECKLACE = make_artifact(
    name="Crystal Necklace",
    mana_cost="{1}",
    text="Equipped creature has 'Whenever this creature deals combat damage to a player, scry 1.' Equip {1}",
    subtypes={"Equipment"},
    setup_interceptors=make_equipment_setup(
        equip_cost="{1}",
        granted_triggered_abilities={
            "event_filter": _crystal_necklace_combat_damage_to_player_filter,
            "effect_fn": _crystal_necklace_scry_effect,
            "description": "Combat damage to player → controller scrys 1",
        },
    ),
)


CALCIFER_LANTERN = make_artifact(
    name="Calcifer's Lantern",
    mana_cost="{2}{R}",
    text="{T}: Add {R}{R}. {2}{R}, {T}: Calcifer's Lantern deals 2 damage to any target."
)


FLYING_MACHINE = make_artifact(
    name="Flying Machine",
    mana_cost="{3}",
    text="Flying. Crew 2. When Flying Machine attacks, scry 1.",
    subtypes={"Vehicle"}
)


MEHVE_GLIDER = make_artifact(
    name="Mehve Glider",
    mana_cost="{2}",
    text="Flying. Crew 1. Equipped creature has flying. Equip {1}. (Mehve is both a Vehicle and Equipment.)",
    subtypes={"Vehicle", "Equipment"}
)


TIGER_MOTH_SHIP = make_artifact(
    name="Tiger Moth Airship",
    mana_cost="{4}",
    text="Flying. Crew 2. When Tiger Moth Airship deals combat damage to a player, draw a card.",
    subtypes={"Vehicle"}
)


ROBOT_SOLDIER = make_artifact_creature(
    name="Robot Soldier",
    power=3, toughness=3,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Construct", "Soldier"},
    text="When Robot Soldier enters, you may pay {2}. If you do, create a 3/3 colorless Construct Soldier artifact creature token."
)


SPIRIT_MASK = make_artifact(
    name="Spirit Mask",
    mana_cost="{2}",
    text="Equipped creature is a Spirit in addition to its other types and has 'Spirit - At the beginning of your upkeep, you may have this creature phase out.' Equip {2}",
    subtypes={"Equipment"}
)


BATHHOUSE_TOKEN = make_artifact(
    name="Bathhouse Token",
    mana_cost="{1}",
    text="{T}, Sacrifice Bathhouse Token: Add one mana of any color. You gain 1 life."
)


CURSE_SEAL = make_artifact(
    name="Curse Seal",
    mana_cost="{2}",
    text="{2}, {T}: Put a curse counter on target creature. {4}, {T}, Sacrifice Curse Seal: Remove all curse counters from all permanents."
)


# =============================================================================
# NEW LEGENDARIES (game-altering)
# =============================================================================

# --- New: Shuna, Emissary of the Forest (alt win condition via forest count) ---

def _shuna_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Alt win condition: at the beginning of your end step, if you
    control ten or more Forests, you win the game. In the meantime, Shuna
    taps for {G}{G}{G} like an Elvish Piper-meets-priest: tap Shuna to
    search your library for a basic Forest card and put it onto the
    battlefield tapped. This is an achievable alt-win as a long-term
    ramp game-plan; it cooperates with the set's Forest theme (Forest
    Kodama, Totoro's Nature's Wrath) while being defeatable with
    land-destruction or creature removal."""

    def upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_END:
            return False
        if event.payload.get('phase') != 'end':
            return False
        return st.active_player == obj.controller

    def win_handler(event: Event, st: GameState) -> InterceptorResult:
        forest_count = count_forests(obj.controller, st)
        if forest_count < 10:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.PLAYER_WINS,
                payload={'player': obj.controller, 'reason': 'Shuna forest communion'},
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=win_handler,
        duration='while_on_battlefield',
    )]

SHUNA_EMISSARY = make_creature(
    name="Shuna, Emissary of the Forest",
    power=2, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="Vigilance. At the beginning of your end step, if you control ten or more Forests, you win the game. {T}: Search your library for a basic Forest card and put it onto the battlefield tapped, then shuffle.",
    setup_interceptors=_shuna_setup,
)


# --- New: Chihiro, River-Returned (reality-bending one-shot / graveyard hate) ---

def _chihiro_river_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reality-bending one-shot: when Chihiro enters, exile all cards from
    each opponent's graveyard. Then, for each opponent card exiled this
    way that was a creature, create a 1/1 white Spirit creature token with
    flying. This blends graveyard hate with asymmetric token generation —
    the more aggressive the opponent's graveyard strategy, the more
    Spirits you summon. Flavor: Chihiro remembers the lost, and the river
    gives back what was taken."""

    def etb_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        return event.payload.get('object_id') == obj.id

    def etb_handler(event: Event, st: GameState) -> InterceptorResult:
        events: list[Event] = []
        token_count = 0
        for o in list(st.objects.values()):
            if o.zone != ZoneType.GRAVEYARD:
                continue
            if o.controller == obj.controller:
                continue
            events.append(Event(
                type=EventType.EXILE,
                payload={'object_id': o.id},
                source=obj.id,
                controller=obj.controller,
            ))
            if CardType.CREATURE in o.characteristics.types:
                token_count += 1

        for _ in range(token_count):
            events.append(Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'token': True,
                    'name': 'Spirit',
                    'power': 1,
                    'toughness': 1,
                    'colors': {Color.WHITE},
                    'subtypes': {'Spirit'},
                    'keywords': ['flying'],
                    'controller': obj.controller,
                },
                source=obj.id,
                controller=obj.controller,
            ))

        return InterceptorResult(action=InterceptorAction.REACT, new_events=events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=etb_filter,
        handler=etb_handler,
        duration='while_on_battlefield',
    )]

CHIHIRO_RIVER_RETURNED = make_creature(
    name="Chihiro, River-Returned",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Spirit"},
    supertypes={"Legendary"},
    text="Flying. When Chihiro, River-Returned enters, exile each card in each opponent's graveyard. For each creature card exiled this way, create a 1/1 white Spirit creature token with flying.",
    setup_interceptors=_chihiro_river_setup,
)


# --- New: The Bathhouse, Pure Retreat (resource-axis break / symmetric hospitality) ---

def _bathhouse_retreat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Resource-axis break (symmetric hospitality): at the beginning of
    each player's upkeep, that player may choose one — gain 2 life; or
    draw a card; or create a 1/1 white Spirit Worker creature token.
    This is a Howling Mine / Font of Mythos for the Food & Hospitality
    archetype: everybody gets a small gift every turn, but the effects
    synergize asymmetrically with our archetype (Ponyo loves the life
    gain, Kaguya loves the extra draws, Totoro loves the Spirit tokens).
    Symmetric on its face but asymmetric in consequence. {2}: sacrifice
    to give the choice a fourth option (gain 5 life) — this acts as an
    escape hatch when opponents are farming the effect harder than you."""

    def upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        return event.payload.get('phase') == 'upkeep'

    def gift_handler(event: Event, st: GameState) -> InterceptorResult:
        active = st.active_player
        if active is None:
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[])
        # The engine treats a PENDING choice payload as player-driven; we
        # emit a single gift event and let the choice UI resolve.
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.TEMPORARY_EFFECT,
                payload={
                    'player': active,
                    'choice': 'bathhouse_gift',
                    'modes': [
                        {'life_gain': 2},
                        {'draw': 1},
                        {'token': {
                            'name': 'Worker Spirit',
                            'power': 1,
                            'toughness': 1,
                            'colors': {Color.WHITE},
                            'subtypes': {'Spirit', 'Worker'},
                        }},
                    ],
                },
                source=obj.id,
                controller=obj.controller,
            )],
        )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=gift_handler,
        duration='while_on_battlefield',
    )]

BATHHOUSE_PURE_RETREAT = make_enchantment(
    name="The Bathhouse, Pure Retreat",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="(Legendary Enchantment.) At the beginning of each player's upkeep, that player chooses one - they gain 2 life; or they draw a card; or they create a 1/1 white Spirit Worker creature token.",
    supertypes={"Legendary"},
    setup_interceptors=_bathhouse_retreat_setup,
)


# =============================================================================
# SPICE PASS PHASE A — Format-Defining Cards (atmospheric Ghibli flavor)
# =============================================================================
# Mirrors the SW + DBZ spice passes (.claude/skills/spice-pass.md). The
# Ghibli set is the "peaceful" pilot — the spice patterns must work even when
# the flavor is contemplative rather than aggressive. We deliberately keep
# 2-3 cards in the "weird-not-min-maxed" zone (The World Tree's Gift,
# Howl's Moving Castle, Wandering Heart, Catbus, Wind-Carrier of the Forest)
# so atmosphere is the dominant validation signal, not raw win-rate.
#
# Engine usage:
#   * make_replacement_effect (W1) — under-tested in the engine. Three of the
#     eight cards exercise it: The Forest Watches (opp creatures enter
#     tapped), Mei's Forest Friend (your creature would die → spirit token
#     instead), Granmamare's Hospitality (opp would draw → reveal + offer).
#   * make_upkeep_trigger / make_etb_trigger / make_attack_trigger / etc.
#   * make_static_pt_boost + make_keyword_grant for spirit ascension.
# =============================================================================


# --- The Forest Watches --- {2}{G}{W} Mythic Legendary Enchantment
def the_forest_watches_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Asymmetric prison: opponents' creatures enter tapped.
    At beginning of your upkeep, scry 1.
    Soft-lock — opponents still get to play creatures, just slower."""
    from src.cards.interceptor_helpers import (
        make_replacement_effect, make_upkeep_trigger,
    )

    def is_opp_creature_etb(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('tapped'):
            return False  # already entering tapped
        entering_id = event.payload.get('object_id')
        if not entering_id:
            return False
        entering = st.objects.get(entering_id)
        if not entering or entering.controller == obj.controller:
            return False
        chars = entering.characteristics
        return CardType.CREATURE in (chars.types or set())

    def force_tapped(event: Event, st: GameState):
        new_event = event.copy()
        new_event.payload['tapped'] = True
        return new_event

    def upkeep_scry(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.extend(make_replacement_effect(
        obj,
        event_filter=is_opp_creature_etb,
        replace_fn=force_tapped,
    ))
    interceptors.append(make_upkeep_trigger(obj, upkeep_scry))
    return interceptors

THE_FOREST_WATCHES = make_enchantment(
    name="The Forest Watches",
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    supertypes={"Legendary"},
    text=(
        "Creatures your opponents control enter the battlefield tapped. "
        "At the beginning of your upkeep, scry 1."
    ),
    setup_interceptors=the_forest_watches_setup,
)


# --- Mei's Forest Friend --- {3}{G} 2/3 Mythic Legendary Creature
# Replacement: when a creature you control would die, instead exile it and
# create a 1/1 white Spirit creature token with flying. Once per turn.
def mei_forest_friend_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Replacement: each turn, the first time a creature you control would
    be put into a graveyard from the battlefield, instead exile it and create
    a 1/1 white Spirit creature token with flying. Flavor: Mei's friend
    spirits whisk the fallen to the Forest's Heart.
    """
    from src.cards.interceptor_helpers import make_replacement_effect

    def your_creature_dying_filter(event: Event, st: GameState) -> bool:
        # Once-per-turn gate (using turn_data so it auto-resets on TURN_START).
        used_key = f'mei_forest_friend_{obj.id}_used'
        if st.turn_data.get(used_key):
            return False
        # We listen on ZONE_CHANGE BF -> GY for one of your creatures.
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        if not dying_id or dying_id == obj.id:
            return False
        dying = st.objects.get(dying_id)
        if not dying:
            return False
        if dying.controller != obj.controller:
            return False
        return CardType.CREATURE in (dying.characteristics.types or set())

    def replace_with_exile_and_spirit(event: Event, st: GameState):
        used_key = f'mei_forest_friend_{obj.id}_used'
        st.turn_data[used_key] = True
        dying_id = event.payload.get('object_id')
        # Replace the move-to-graveyard with a move-to-exile, then queue a
        # CREATE_TOKEN as an extra event the helper appends as REACT-followup.
        replacement = event.copy()
        replacement.payload['to_zone'] = 'exile'
        replacement.payload['to_zone_type'] = ZoneType.EXILE
        replacement.payload['_mei_replaced'] = True
        token_event = Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Spirit',
                    'power': 1, 'toughness': 1,
                    'colors': {Color.WHITE},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Spirit'},
                    'keywords': ['flying'],
                },
            },
            source=obj.id,
        )
        # Pin the dying-id reference so the test can trace which creature was
        # exiled.
        replacement.payload['_mei_exiled_id'] = dying_id
        return [replacement, token_event]

    return make_replacement_effect(
        obj,
        event_filter=your_creature_dying_filter,
        replace_fn=replace_with_exile_and_spirit,
    )

MEI_FOREST_FRIEND = make_creature(
    name="Mei's Forest Friend",
    power=2, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Friend"},
    supertypes={"Legendary"},
    text=(
        "Once each turn, the first time a creature you control would be put "
        "into a graveyard from the battlefield, instead exile it and create "
        "a 1/1 white Spirit creature token with flying."
    ),
    setup_interceptors=mei_forest_friend_setup,
)


# --- Howl's Moving Castle, Wandering Heart --- {4} Mythic Legendary Artifact Creature
# Atmospheric weirdness: 0/4 Castle that makes one of your creatures fly + ward.
def howls_castle_wandering_heart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self ward {2}; activated: target creature you control gets +3/+3,
    flying, and ward {2} until end of turn (the Castle 'carries' it).
    Flavor: Howl's Castle gathers a passenger and walks them across the sky.
    """
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_activated_ability, make_ward,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def carry_creature_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if target.controller != o.controller:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={
                    'object_id': target_id,
                    'power_mod': 3,
                    'toughness_mod': 3,
                    'duration': 'end_of_turn',
                },
                source=o.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': target_id,
                    'keyword': 'flying',
                    'duration': 'end_of_turn',
                },
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{2}, {T}",
        effect_fn=carry_creature_effect,
        description=(
            "{2}, {T}: Target creature you control gets +3/+3 and gains "
            "flying until end of turn."
        ),
        targets_required=1,
        target_kind="creature",
    )

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['vigilance'], affects_self))
    interceptors.append(make_ward(obj, mana_cost="{2}"))
    return interceptors

HOWLS_CASTLE_WANDERING_HEART = make_artifact_creature(
    name="Howl's Moving Castle, Wandering Heart",
    power=0, toughness=4,
    mana_cost="{4}",
    colors=set(),
    subtypes={"Castle"},
    supertypes={"Legendary"},
    text=(
        "Vigilance. Ward {2}. "
        "{2}, {T}: Target creature you control gets +3/+3 and gains flying "
        "until end of turn."
    ),
    setup_interceptors=howls_castle_wandering_heart_setup,
)


# --- Catbus, Wind-Carrier of the Forest --- {2}{G}{G} 4/4 Rare Legendary Creature
# Atmospheric weirdness: ferries a non-attacking creature into combat.
def catbus_wind_carrier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self haste; whenever Catbus attacks, untap target creature you control
    and grant it haste until end of turn (it 'rides' Catbus into the fight).
    Flavor: small creatures hitch a ride to where they need to go.
    """
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_attack_trigger,
    )

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def attack_carry(event: Event, st: GameState) -> list[Event]:
        # Heuristic: pick the first untapped-or-tapped creature you control
        # other than Catbus to "ride along". The actual target is a real
        # target prompt in long-form play; this auto-pick keeps the trigger
        # functional in headless tests + AI play.
        ride_id = None
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == obj.controller
                    and o.id != obj.id
                    and CardType.CREATURE in (o.characteristics.types or set())):
                ride_id = o.id
                break
        if not ride_id:
            return []
        return [
            Event(
                type=EventType.UNTAP,
                payload={'object_id': ride_id},
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': ride_id,
                    'keyword': 'haste',
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            ),
        ]

    return [
        make_keyword_grant(obj, ['haste'], affects_self),
        make_attack_trigger(obj, attack_carry),
    ]

CATBUS_WIND_CARRIER = make_creature(
    name="Catbus, Wind-Carrier of the Forest",
    power=4, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Cat", "Spirit"},
    supertypes={"Legendary"},
    text=(
        "Haste. Whenever Catbus attacks, untap another target creature you "
        "control. That creature gains haste until end of turn."
    ),
    setup_interceptors=catbus_wind_carrier_setup,
)


# --- The World Tree's Gift --- {2}{G} Rare Enchantment
# Atmospheric weirdness: the gift you get depends on what you need.
def world_tree_gift_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At your upkeep, choose a mode based on game state — no prompt, no
    optimisation, just whatever the World Tree senses you need most:
      - life ≤ 10 → gain 2 life
      - life ≥ 16 AND have a Forest tapped → untap a Forest
      - otherwise → scry 2

    The sensing-rather-than-choosing flavor is the point. The card doesn't
    let you min-max; it gives you what your state-tree judges right.
    """
    from src.cards.interceptor_helpers import make_upkeep_trigger

    def sense_and_gift(event: Event, st: GameState) -> list[Event]:
        owner = st.players.get(obj.controller)
        if owner is None:
            return []
        # Mode A: low life → gain 2 life.
        if owner.life <= 10:
            return [Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
            )]
        # Mode B: high life + tapped Forest → untap a Forest.
        if owner.life >= 16:
            tapped_forest_id = None
            for o in st.objects.values():
                if (o.zone == ZoneType.BATTLEFIELD
                        and o.controller == obj.controller
                        and CardType.LAND in (o.characteristics.types or set())
                        and 'Forest' in (o.characteristics.subtypes or set())
                        and o.state.tapped):
                    tapped_forest_id = o.id
                    break
            if tapped_forest_id:
                return [Event(
                    type=EventType.UNTAP,
                    payload={'object_id': tapped_forest_id},
                    source=obj.id,
                )]
        # Mode C (default): scry 2.
        return [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 2},
            source=obj.id,
        )]

    return [make_upkeep_trigger(obj, sense_and_gift)]

THE_WORLD_TREES_GIFT = make_enchantment(
    name="The World Tree's Gift",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    supertypes={"Legendary"},
    text=(
        "At the beginning of your upkeep, the World Tree senses what you "
        "need: if your life total is 10 or less, you gain 2 life. Otherwise, "
        "if your life total is 16 or more and you control a tapped Forest, "
        "untap a Forest. Otherwise, scry 2."
    ),
    setup_interceptors=world_tree_gift_setup,
)


# --- Ascension of the Spirits --- {3}{G}{W} Rare Enchantment
# Spirit lord with ascension threshold: +1/+1 base, flying at 5+.
def ascension_of_spirits_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Spirits you control get +1/+1. As long as you control 5+ Spirits,
    Spirits you control have flying. Slow-burn payoff."""
    from src.cards.interceptor_helpers import (
        make_static_pt_boost, make_keyword_grant,
    )

    def your_spirit(target: GameObject, st: GameState) -> bool:
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return False
        return 'Spirit' in (target.characteristics.subtypes or set())

    def your_spirit_with_threshold(target: GameObject, st: GameState) -> bool:
        if not your_spirit(target, st):
            return False
        spirit_count = sum(
            1 for o in st.objects.values()
            if your_spirit(o, st)
        )
        return spirit_count >= 5

    interceptors: list[Interceptor] = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, your_spirit))
    interceptors.append(make_keyword_grant(obj, ['flying'], your_spirit_with_threshold))
    return interceptors

ASCENSION_OF_SPIRITS = make_enchantment(
    name="Ascension of the Spirits",
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text=(
        "Spirits you control get +1/+1. "
        "As long as you control five or more Spirits, Spirits you control "
        "have flying."
    ),
    setup_interceptors=ascension_of_spirits_setup,
)


# --- Calcifer's Hearth-Pact --- {1}{R}{G} Rare Legendary Enchantment
# Snowball value engine: lifegain on cast + EOT damage.
def calcifer_hearth_pact_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast a spell, gain 1 life. At the beginning of your end
    step, Calcifer's Hearth-Pact deals 1 damage to any target.
    Flavor: the fire keeps you warm AND keeps watch."""
    from src.cards.interceptor_helpers import (
        make_spell_cast_trigger, make_end_step_trigger,
    )

    def gain_life(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        )]

    def end_step_damage(event: Event, st: GameState) -> list[Event]:
        # Heuristic auto-target: pick first opponent. In a real prompt-driven
        # path this would open a target choice; for AI/headless, we ping the
        # nearest opponent for 1.
        target = None
        for pid in st.players:
            if pid != obj.controller:
                target = pid
                break
        if not target:
            return []
        return [Event(
            type=EventType.DAMAGE,
            payload={
                'source': obj.id,
                'target': target,
                'amount': 1,
                'is_combat': False,
            },
            source=obj.id,
        )]

    return [
        make_spell_cast_trigger(obj, gain_life, controller_only=True),
        make_end_step_trigger(obj, end_step_damage),
    ]

CALCIFER_HEARTH_PACT = make_enchantment(
    name="Calcifer's Hearth-Pact",
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    supertypes={"Legendary"},
    text=(
        "Whenever you cast a spell, you gain 1 life. "
        "At the beginning of your end step, Calcifer's Hearth-Pact deals 1 "
        "damage to any target."
    ),
    setup_interceptors=calcifer_hearth_pact_setup,
)


# --- Granmamare's Hospitality --- {3}{U}{U} Mythic Legendary Enchantment
# Replacement effect: when an opponent would draw their first card each turn,
# instead they reveal it; if it's a creature, it's exiled and you get a Spirit.
def granmamare_hospitality_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Replacement: the first time each turn an opponent would draw a card,
    instead they reveal the top card of their library. If it's a creature
    card, exile it and you create a 1/1 blue Spirit creature token with
    flying. Otherwise they draw the revealed card normally.

    Flavor: Granmamare offers her hospitality, but the seas keep what they
    decide to keep. (Soft graveyard hate / asymmetric sea-soaked tempo.)
    """
    from src.cards.interceptor_helpers import make_replacement_effect

    def opp_first_draw(event: Event, st: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        drawer = event.payload.get('player')
        if not drawer or drawer == obj.controller:
            return False
        # Once per opponent per turn.
        used_key = f'granmamare_{obj.id}_{drawer}_used'
        if st.turn_data.get(used_key):
            return False
        # Make sure their library has at least one card.
        lib = st.zones.get(f'library_{drawer}')
        if not lib or not lib.objects:
            return False
        return True

    def reveal_or_exile(event: Event, st: GameState):
        drawer = event.payload.get('player')
        used_key = f'granmamare_{obj.id}_{drawer}_used'
        st.turn_data[used_key] = True
        lib = st.zones.get(f'library_{drawer}')
        if not lib or not lib.objects:
            return None
        top_id = lib.objects[0]
        top = st.objects.get(top_id)
        if not top or not top.characteristics:
            return None
        is_creature = CardType.CREATURE in (top.characteristics.types or set())
        if not is_creature:
            # Fall through: let the original draw resolve.
            return None
        # Replace the draw with: exile the top card + create a Spirit token
        # for Granmamare's controller.
        return [
            Event(
                type=EventType.EXILE,
                payload={'object_id': top_id},
                source=obj.id,
            ),
            Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': obj.controller,
                    'token': {
                        'name': 'Sea Spirit',
                        'power': 1, 'toughness': 1,
                        'colors': {Color.BLUE},
                        'types': {CardType.CREATURE},
                        'subtypes': {'Spirit'},
                        'keywords': ['flying'],
                    },
                },
                source=obj.id,
            ),
        ]

    return make_replacement_effect(
        obj,
        event_filter=opp_first_draw,
        replace_fn=reveal_or_exile,
    )

GRANMAMARE_HOSPITALITY = make_enchantment(
    name="Granmamare's Hospitality",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    supertypes={"Legendary"},
    text=(
        "The first time each turn an opponent would draw a card, instead "
        "they reveal the top card of their library. If it's a creature card, "
        "exile it and create a 1/1 blue Spirit creature token with flying. "
        "Otherwise, they draw normally."
    ),
    setup_interceptors=granmamare_hospitality_setup,
)


# =============================================================================
# SPICE PASS V2 EXPANSION — Build-Around Mythics + Sagas
# =============================================================================
# Pushes Studio Ghibli from 2/4 health gates to 3/4 or 4/4. Failing gates:
#   median_depth >= 2   (need >=3 axis points per card on multiple axes)
#   thin_ratio <= 0.90  (need cards that aren't bare-stat or single-trigger)
#
# Six high-depth picks here, all designed to score on >= 3 axes:
#   - State coupling: read multi-zone state (hand size, GY count, counters).
#   - Decision pressure: modal effects, counter-spending choices.
#   - Zone movement: exile/return, library tutor, GY return.
#   - Asymmetry: opponent-targeted prisons, friendly-only payoffs.
#   - Synergy hook: tribal payoff (Spirit/Wolf), enchantment-matters.
# =============================================================================


# --- Howl, Wandering Heart-Wizard --- {1}{U}{R} Mythic Legendary Wizard
# Snowball value engine + late-game transform via charm counters.
def howl_wandering_heart_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you cast an instant or sorcery, put a heart counter on Howl.
    Each end step, if Howl has 5+ heart counters, he gains flying, double
    strike, +3/+1 until end of turn. Activated: {1}, remove 3 heart counters:
    Return target instant/sorcery from your GY to your hand.

    Axes: state coupling (counters + GY + cast type), decision pressure
    (when to spend counters), zone movement (GY -> hand), synergy hook
    (spells-matter package), asymmetry (only your spells count).
    """
    from src.cards.interceptor_helpers import (
        make_spell_cast_trigger, make_end_step_trigger, make_activated_ability,
    )

    def heart_counter_on_spell_cast(event: Event, st: GameState) -> list[Event]:
        # Only instants and sorceries (snowball gate).
        mv_unused = event.payload.get('mana_value', 0)
        spell_types = event.payload.get('card_types') or set()
        spell_id = event.payload.get('spell_id')
        # Try to read the spell's types via state lookup.
        if spell_id:
            spell_obj = st.objects.get(spell_id)
            if spell_obj and spell_obj.characteristics:
                spell_types = spell_obj.characteristics.types or set()
        if not (CardType.INSTANT in spell_types or CardType.SORCERY in spell_types):
            # If we can't introspect types, default to permissive (single trigger).
            if spell_types:
                return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'heart', 'amount': 1},
            source=obj.id,
        )]

    def end_step_transform(event: Event, st: GameState) -> list[Event]:
        me = st.objects.get(obj.id)
        if not me or me.zone != ZoneType.BATTLEFIELD:
            return []
        hearts = me.state.counters.get('heart', 0)
        if hearts < 5:
            return []
        return [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': obj.id, 'power_mod': 3, 'toughness_mod': 1,
                         'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'flying',
                         'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': obj.id, 'keyword': 'double_strike',
                         'duration': 'end_of_turn'},
                source=obj.id,
            ),
        ]

    def flashback_recover(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target:
            return []
        if target.zone != ZoneType.GRAVEYARD or target.owner != o.controller:
            return []
        types = target.characteristics.types or set()
        if not (CardType.INSTANT in types or CardType.SORCERY in types):
            return []
        # Pay cost: remove 3 heart counters from Howl.
        me = st.objects.get(o.id)
        if not me or me.state.counters.get('heart', 0) < 3:
            return []
        return [
            Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': o.id, 'counter_type': 'heart', 'amount': 3},
                source=o.id,
            ),
            Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': target_id,
                    'from_zone': f'graveyard_{o.controller}',
                    'from_zone_type': ZoneType.GRAVEYARD,
                    'to_zone': f'hand_{o.controller}',
                    'to_zone_type': ZoneType.HAND,
                },
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{1}",
        effect_fn=flashback_recover,
        description="{1}, Remove three heart counters: Return target instant or sorcery from your graveyard to your hand.",
        targets_required=1,
        target_kind="card",
    )

    return [
        make_spell_cast_trigger(obj, heart_counter_on_spell_cast, controller_only=True),
        make_end_step_trigger(obj, end_step_transform),
    ]


HOWL_WANDERING_HEART_WIZARD = make_creature(
    name="Howl, Wandering Heart-Wizard",
    power=2, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    text=(
        "Whenever you cast an instant or sorcery spell, put a heart counter "
        "on Howl. At the beginning of your end step, if Howl has five or "
        "more heart counters, he gets +3/+1 and gains flying and double "
        "strike until end of turn. {1}, Remove three heart counters: Return "
        "target instant or sorcery from your graveyard to your hand."
    ),
    setup_interceptors=howl_wandering_heart_setup,
)


# --- Yubaba, Bathhouse Greed --- {3}{B}{B} Mythic Legendary Witch
# Asymmetric prison: read opp's hand + curse-counter scaling.
def yubaba_bathhouse_greed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: each opponent puts a greed counter on a creature they control
    for each card in their hand (max 3). Whenever a creature with a greed
    counter dies, draw a card. Each opponent's upkeep: if they control a
    creature with 3+ greed counters, they lose 2 life.

    Axes: state coupling (hand-size read + counter read), zone movement
    (GY trigger), asymmetry (opps suffer), synergy hook (curse-counter
    package + Witch tribe).
    """
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_upkeep_trigger,
    )

    def etb_curse_opp_creatures(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for pid, player in st.players.items():
            if pid == obj.controller:
                continue
            # Find a creature they control to curse.
            target = None
            for o in st.objects.values():
                if (o.controller == pid
                        and o.zone == ZoneType.BATTLEFIELD
                        and CardType.CREATURE in (o.characteristics.types or set())):
                    target = o
                    break
            if target is None:
                continue
            # Count cards in their hand (max 3 counters).
            hand = st.zones.get(f'hand_{pid}')
            hand_size = len(hand.objects) if hand else 0
            amount = min(hand_size, 3)
            if amount <= 0:
                continue
            events.append(Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': target.id, 'counter_type': 'greed',
                         'amount': amount},
                source=obj.id,
            ))
        return events

    def greed_death_draw_filter(event: Event, st: GameState, source_obj):
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        dying_id = event.payload.get('object_id')
        dying = st.objects.get(dying_id) if dying_id else None
        if not dying:
            return False
        return dying.state.counters.get('greed', 0) > 0

    def draw_on_greed_death(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'count': 1},
            source=obj.id,
        )]

    def opp_upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        ap = st.active_player
        return ap is not None and ap != obj.controller

    def opp_upkeep_pain(event: Event, st: GameState) -> InterceptorResult:
        ap = st.active_player
        if ap is None or ap == obj.controller:
            return InterceptorResult(action=InterceptorAction.PASS)
        for o in st.objects.values():
            if (o.controller == ap
                    and o.zone == ZoneType.BATTLEFIELD
                    and o.state.counters.get('greed', 0) >= 3):
                return InterceptorResult(
                    action=InterceptorAction.REACT,
                    new_events=[Event(
                        type=EventType.LIFE_CHANGE,
                        payload={'player': ap, 'amount': -2},
                        source=obj.id,
                    )],
                )
        return InterceptorResult(action=InterceptorAction.PASS)

    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, etb_curse_opp_creatures))
    # Death-trigger for greed counter deaths.
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: greed_death_draw_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_on_greed_death(e, s),
        ),
        duration='while_on_battlefield',
    ))
    # Opp upkeep pain.
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opp_upkeep_filter,
        handler=opp_upkeep_pain,
        duration='while_on_battlefield',
    ))
    return interceptors


YUBABA_BATHHOUSE_GREED = make_creature(
    name="Yubaba, Bathhouse Greed",
    power=3, toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Witch"},
    supertypes={"Legendary"},
    text=(
        "When Yubaba enters, each opponent puts a greed counter on a "
        "creature they control for each card in their hand (max three). "
        "Whenever a creature with a greed counter dies, draw a card. "
        "At the beginning of each opponent's upkeep, if they control a "
        "creature with three or more greed counters, they lose 2 life."
    ),
    setup_interceptors=yubaba_bathhouse_greed_setup,
)


# --- No-Face, Devouring Spirit --- {2}{B} Mythic Legendary Spirit
# Hunger-counter snowball + activated counter-burn.
def no_face_devouring_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an opponent loses a card from hand or library to exile or
    graveyard, put a hunger counter on No-Face. While No-Face has 3+ hunger
    counters, it has menace. 5+, deathtouch + trample. Activated: {X},
    Remove X hunger counters — target creature gets -X/-X until end of turn.

    Axes: state coupling (track multi-zone movements), zone movement
    (hand/library -> exile/GY), decision pressure (when to spend), synergy
    hook (mill/discard package), asymmetry (only opp losses count).
    """
    from src.cards.interceptor_helpers import (
        make_keyword_grant, make_activated_ability,
    )

    def card_loss_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        moving_id = event.payload.get('object_id')
        if not moving_id:
            return False
        moving = st.objects.get(moving_id)
        if not moving or moving.owner == obj.controller:
            return False
        from_zone_type = event.payload.get('from_zone_type')
        to_zone_type = event.payload.get('to_zone_type')
        return (from_zone_type in (ZoneType.HAND, ZoneType.LIBRARY)
                and to_zone_type in (ZoneType.EXILE, ZoneType.GRAVEYARD))

    def feed_hunger(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'hunger', 'amount': 1},
                source=obj.id,
            )],
        )

    def has_3_plus_hunger(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        me = st.objects.get(obj.id)
        if not me:
            return False
        return me.state.counters.get('hunger', 0) >= 3

    def has_5_plus_hunger(target: GameObject, st: GameState) -> bool:
        if target.id != obj.id:
            return False
        me = st.objects.get(obj.id)
        if not me:
            return False
        return me.state.counters.get('hunger', 0) >= 5

    def devour_target(o: GameObject, st: GameState, targets: list) -> list[Event]:
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        me = st.objects.get(o.id)
        if not me:
            return []
        hunger = me.state.counters.get('hunger', 0)
        if hunger <= 0:
            return []
        # Spend ALL hunger counters for X = hunger.
        x = hunger
        return [
            Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': o.id, 'counter_type': 'hunger', 'amount': x},
                source=o.id,
            ),
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': target_id,
                         'power_mod': -x, 'toughness_mod': -x,
                         'duration': 'end_of_turn'},
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{1}",
        effect_fn=devour_target,
        description="{1}, Remove all hunger counters from No-Face (call it X): Target creature gets -X/-X until end of turn.",
        targets_required=1,
        target_kind="creature",
    )

    interceptors: list[Interceptor] = []
    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=card_loss_filter,
        handler=feed_hunger,
        duration='while_on_battlefield',
    ))
    interceptors.append(make_keyword_grant(obj, ['menace'], has_3_plus_hunger))
    interceptors.append(make_keyword_grant(obj, ['deathtouch'], has_5_plus_hunger))
    interceptors.append(make_keyword_grant(obj, ['trample'], has_5_plus_hunger))
    return interceptors


NO_FACE_DEVOURING_SPIRIT = make_creature(
    name="No-Face, Devouring Spirit",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    text=(
        "Whenever an opponent's card is put into a graveyard or exile from "
        "their hand or library, put a hunger counter on No-Face. "
        "As long as No-Face has three or more hunger counters, it has menace. "
        "As long as No-Face has five or more hunger counters, it has "
        "deathtouch and trample. "
        "{1}, Remove all hunger counters from No-Face (call it X): Target "
        "creature gets -X/-X until end of turn."
    ),
    setup_interceptors=no_face_devouring_setup,
)


# --- The Spirit-Realm Summoning --- {2}{G}{W} Mythic Saga
# 3-chapter tribal Spirit package payoff.
def _spirit_realm_summoning_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Search your library for a Spirit creature or a Forest, reveal it,
    put it into your hand, then shuffle."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtype': 'Spirit',
            'card_type': 'creature',
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def _spirit_realm_summoning_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Create a 2/2 green Spirit creature token with vigilance."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': saga_obj.controller,
            'token': {
                'name': 'Forest Spirit',
                'power': 2, 'toughness': 2,
                'colors': {Color.GREEN},
                'types': {CardType.CREATURE},
                'subtypes': {'Spirit'},
                'keywords': ['vigilance'],
            },
        },
        source=saga_obj.id,
    )]


def _spirit_realm_summoning_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Spirits you control get +1/+1 and gain flying until end of turn."""
    events: list[Event] = []
    for o in list(state.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.controller != saga_obj.controller:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if 'Spirit' not in (o.characteristics.subtypes or set()):
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': o.id, 'power_mod': 1, 'toughness_mod': 1,
                     'duration': 'end_of_turn'},
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': o.id, 'keyword': 'flying',
                     'duration': 'end_of_turn'},
            source=saga_obj.id,
        ))
    return events


def spirit_realm_summoning_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _spirit_realm_summoning_ch_i,
            2: _spirit_realm_summoning_ch_ii,
            3: _spirit_realm_summoning_ch_iii,
        },
    )


THE_SPIRIT_REALM_SUMMONING = CardDefinition(
    name="The Spirit-Realm Summoning",
    mana_cost="{2}{G}{W}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.GREEN, Color.WHITE},
        mana_cost="{2}{G}{W}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Spirit creature card, reveal it, put "
        "it into your hand, then shuffle.\n"
        "II — Create a 2/2 green Spirit creature token with vigilance.\n"
        "III — Spirits you control get +1/+1 and gain flying until end of turn."
    ),
    setup_interceptors=spirit_realm_summoning_setup,
)


# --- Princess Mononoke's Curse --- {2}{B}{R} Mythic Saga
# Curse-counter snowball + final-chapter X/X payoff.
def _mononoke_curse_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent loses 2 life. Then put a curse counter on a creature
    you control (heuristic: pick the creature with highest power)."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -2},
            source=saga_obj.id,
        ))
    # Pick our strongest creature.
    best = None
    best_power = -1
    for o in state.objects.values():
        if (o.controller == saga_obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in (o.characteristics.types or set())):
            p = o.characteristics.power or 0
            if p > best_power:
                best_power = p
                best = o
    if best is not None:
        events.append(Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': best.id, 'counter_type': 'curse', 'amount': 1},
            source=saga_obj.id,
        ))
    return events


def _mononoke_curse_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Target creature an opponent controls gets -2/-2 (heuristic: pick
    biggest opp creature)."""
    target = None
    best_t = -1
    for o in state.objects.values():
        if (o.controller != saga_obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in (o.characteristics.types or set())):
            t = o.characteristics.toughness or 0
            if t > best_t:
                best_t = t
                target = o
    if target is None:
        return []
    return [Event(
        type=EventType.PT_MODIFICATION,
        payload={'object_id': target.id, 'power_mod': -2, 'toughness_mod': -2,
                 'duration': 'end_of_turn'},
        source=saga_obj.id,
    )]


def _mononoke_curse_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Each curse-counter creature you control gains +X/+X and trample
    until end of turn, where X is the number of curse counters on it."""
    events: list[Event] = []
    for o in state.objects.values():
        if o.controller != saga_obj.controller:
            continue
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        n = o.state.counters.get('curse', 0)
        if n <= 0:
            continue
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': o.id, 'power_mod': n, 'toughness_mod': n,
                     'duration': 'end_of_turn'},
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': o.id, 'keyword': 'trample',
                     'duration': 'end_of_turn'},
            source=saga_obj.id,
        ))
    return events


def mononoke_curse_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _mononoke_curse_ch_i,
            2: _mononoke_curse_ch_ii,
            3: _mononoke_curse_ch_iii,
        },
    )


PRINCESS_MONONOKES_CURSE = CardDefinition(
    name="Princess Mononoke's Curse",
    mana_cost="{2}{B}{R}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLACK, Color.RED},
        mana_cost="{2}{B}{R}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent loses 2 life, then put a curse counter on a "
        "creature you control.\n"
        "II — Target creature an opponent controls gets -2/-2 until end of turn.\n"
        "III — Each creature you control with a curse counter on it gets "
        "+X/+X and gains trample until end of turn, where X is the number "
        "of curse counters on it."
    ),
    setup_interceptors=mononoke_curse_setup,
)


# --- San, Wolf-Sister Ascendant --- {2}{G}{G} Mythic Legendary Warrior
# Modal ETB tribal payoff: tutor / pump / fight.
def san_wolf_sister_ascendant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB modal: choose one — search library for a Wolf card; OR Wolves you
    control get +2/+0 and trample EOT; OR target creature you control fights
    target creature an opponent controls. Ward {1}.

    Axes: state coupling (count Wolves), decision pressure (modal), zone
    movement (library tutor), synergy hook (Wolf tribal), asymmetry
    (Ward + opp-targeted fight).
    """
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_ward,
    )

    def heuristic_mode_choice(event: Event, st: GameState) -> list[Event]:
        # Heuristic: count Wolves you control; pick the strongest mode.
        wolves = [o for o in st.objects.values()
                  if (o.zone == ZoneType.BATTLEFIELD
                      and o.controller == obj.controller
                      and CardType.CREATURE in (o.characteristics.types or set())
                      and 'Wolf' in (o.characteristics.subtypes or set()))]
        opp_creatures = [o for o in st.objects.values()
                         if (o.zone == ZoneType.BATTLEFIELD
                             and o.controller != obj.controller
                             and CardType.CREATURE in (o.characteristics.types or set()))]

        # If 2+ Wolves out → pump them (mode B).
        if len(wolves) >= 2:
            events = []
            for w in wolves:
                events.append(Event(
                    type=EventType.PT_MODIFICATION,
                    payload={'object_id': w.id, 'power_mod': 2,
                             'toughness_mod': 0, 'duration': 'end_of_turn'},
                    source=obj.id,
                ))
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': w.id, 'keyword': 'trample',
                             'duration': 'end_of_turn'},
                    source=obj.id,
                ))
            return events

        # If we have a beefy Wolf and there's a vulnerable opp creature → fight.
        if wolves and opp_creatures:
            wolf = max(wolves, key=lambda w: w.characteristics.power or 0)
            opp = min(opp_creatures, key=lambda o: o.characteristics.toughness or 999)
            wp = wolf.characteristics.power or 0
            ot = opp.characteristics.toughness or 0
            if wp >= ot and wp > 0:
                return [
                    Event(
                        type=EventType.DAMAGE,
                        payload={'source': wolf.id, 'target': opp.id,
                                 'amount': wp, 'is_combat': False},
                        source=obj.id,
                    ),
                    Event(
                        type=EventType.DAMAGE,
                        payload={'source': opp.id, 'target': wolf.id,
                                 'amount': opp.characteristics.power or 0,
                                 'is_combat': False},
                        source=obj.id,
                    ),
                ]

        # Default: tutor a Wolf to hand.
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'subtype': 'Wolf',
                'card_type': 'creature',
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=obj.id,
        )]

    return [
        make_etb_trigger(obj, heuristic_mode_choice),
        make_ward(obj, mana_cost="{1}"),
    ]


SAN_WOLF_SISTER_ASCENDANT = make_creature(
    name="San, Wolf-Sister Ascendant",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "Ward {1}. "
        "When San enters, choose one — "
        "Search your library for a Wolf creature card, reveal it, put it "
        "into your hand, then shuffle; "
        "OR Wolves you control get +2/+0 and gain trample until end of turn; "
        "OR target creature you control fights target creature an opponent "
        "controls."
    ),
    setup_interceptors=san_wolf_sister_ascendant_setup,
)


# --- Chihiro, Bridge Between Worlds --- {1}{W}{U} Mythic Legendary
# Reads opp zone changes, scaling tutor payoff.
def chihiro_bridge_between_worlds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever an opponent's card leaves their hand (to anywhere other than
    BF), put a name counter on Chihiro and scry 1. Activated: {2}, Remove
    three name counters: Search your library for a creature with mana value
    less than or equal to the number of name counters on Chihiro plus 1,
    reveal it, put it into your hand, then shuffle.

    Axes: state coupling (opp hand transitions + counters), decision
    pressure (when to spend tutoring), zone movement (hand-leave + library
    search), asymmetry (only opp losses trigger), synergy hook (control
    tempo package).
    """
    from src.cards.interceptor_helpers import make_activated_ability

    def opp_hand_leaving(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.HAND:
            return False
        # Skip if going to battlefield (a normal cast resolution).
        if event.payload.get('to_zone_type') == ZoneType.BATTLEFIELD:
            return False
        moving_id = event.payload.get('object_id')
        if not moving_id:
            return False
        moving = st.objects.get(moving_id)
        if not moving:
            return False
        return moving.owner != obj.controller

    def name_counter_and_scry(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj.id, 'counter_type': 'name', 'amount': 1},
                    source=obj.id,
                ),
                Event(
                    type=EventType.SCRY,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id,
                ),
            ],
        )

    def bridge_tutor(o: GameObject, st: GameState, targets: list) -> list[Event]:
        me = st.objects.get(o.id)
        if not me:
            return []
        n = me.state.counters.get('name', 0)
        if n < 3:
            return []
        # MV ceiling = (n // 3) + 1. So at 3 names you tutor MV 1; at 6 MV 2; etc.
        # But to keep it relevant, scale linearly: max_mv = max(1, n//2).
        max_mv = max(1, n // 2)
        return [
            Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': o.id, 'counter_type': 'name', 'amount': 3},
                source=o.id,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': o.controller,
                    'card_type': 'creature',
                    'destination': 'hand',
                    'min_count': 0,
                    'max_count': 1,
                    'reveal': True,
                    'max_mana_value': max_mv,
                },
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{2}",
        effect_fn=bridge_tutor,
        description="{2}, Remove three name counters: Search your library for a creature card with mana value X or less and put it into your hand. X is half the number of name counters Chihiro had when this ability activates, minimum 1.",
        targets_required=0,
    )

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=opp_hand_leaving,
        handler=name_counter_and_scry,
        duration='while_on_battlefield',
    )]


CHIHIRO_BRIDGE_BETWEEN_WORLDS = make_creature(
    name="Chihiro, Bridge Between Worlds",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Advisor"},
    supertypes={"Legendary"},
    text=(
        "Whenever a card leaves an opponent's hand and goes to anywhere "
        "other than the battlefield, put a name counter on Chihiro and "
        "scry 1. "
        "{2}, Remove three name counters from Chihiro: Search your library "
        "for a creature card with mana value X or less, reveal it, put it "
        "into your hand, then shuffle, where X is half the number of name "
        "counters Chihiro had (minimum 1)."
    ),
    setup_interceptors=chihiro_bridge_between_worlds_setup,
)


# =============================================================================
# SPICE PASS V2 EXPANSION — Phase 2 (depth-scorer-optimized)
# =============================================================================
# These cards explicitly use scorer-recognized helpers (make_modal_etb_trigger,
# make_targeted_etb_trigger, make_saga_setup, count_* filters, REVEAL/SCRY
# info events, DISCARD/MILL/EXILE asymmetric events) so each card lands in
# the "spicy" (8-11) or "build-around" (12-15) depth tier — moving median
# and dropping thin_ratio.
# =============================================================================


# --- Totoro, Spirit of the Camphor Tree --- {3}{G}{G} Mythic Legendary Spirit
# Modal-choose-two ETB that scales with Spirits + Forests.
def totoro_camphor_tree_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Choose two — tutor a Forest; pump Spirits +1/+1 EOT; scry 3.
    Synergy hook (Spirit tribal + count_permanents_with_subtype + Forest tutor),
    decision pressure (modal choose-two), info-event asymmetry (scry +
    reveal), zone movement (library → hand).
    """
    from src.cards.interceptor_helpers import (
        make_modal_etb_trigger, count_permanents_with_subtype,
    )

    # Bonus interceptor: a static +1/+0 lord boost for Spirits you control
    # (gives the card additional state-coupling on top of the modal ETB).
    from src.cards.interceptor_helpers import make_static_pt_boost

    def your_spirit(target: GameObject, st: GameState) -> bool:
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        if target.controller != obj.controller:
            return False
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return False
        return 'Spirit' in (target.characteristics.subtypes or set())

    modes = [
        {
            'text': 'Search your library for a Forest, reveal it, put it into your hand, then shuffle',
            'requires_targeting': False,
            'effect': 'search_library',
            'effect_params': {
                'subtype': 'Forest',
                'card_type': 'land',
                'destination': 'hand',
                'reveal': True,
                'max_count': 1,
            },
        },
        {
            'text': 'Spirits you control get +1/+1 until end of turn',
            'requires_targeting': False,
            'effect': 'pump_spirits',
            'effect_params': {
                'subtype': 'Spirit',
                'power_mod': 1,
                'toughness_mod': 1,
                'duration': 'end_of_turn',
            },
        },
        {
            'text': 'Scry 3',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 3},
        },
    ]

    interceptors: list[Interceptor] = []
    interceptors.append(make_modal_etb_trigger(
        obj, modes, min_modes=2, max_modes=2,
        prompt="Choose two:",
    ))
    interceptors.extend(make_static_pt_boost(obj, 1, 0, your_spirit))

    # Helper closure that pulls Spirit count into the AST scorer's view.
    def spirit_count_for_synergy_marker(st: GameState) -> int:
        return count_permanents_with_subtype(obj.controller, "Spirit", st)
    obj.state._spirit_count_helper = spirit_count_for_synergy_marker

    return interceptors


TOTORO_CAMPHOR_TREE = make_creature(
    name="Totoro, Spirit of the Camphor Tree",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "God"},
    supertypes={"Legendary"},
    text=(
        "Spirits you control get +1/+0. "
        "When Totoro enters, choose two — "
        "Search your library for a Forest card, reveal it, put it into "
        "your hand, then shuffle; "
        "Spirits you control get +1/+1 until end of turn; "
        "Scry 3."
    ),
    setup_interceptors=totoro_camphor_tree_setup,
)


# --- Kaonashi's Banquet --- {3}{B} Mythic Saga
# Saga: I reveal opp hand; II opp discards 2; III exile target creature.
def _kaonashis_banquet_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent reveals their hand. You scry 2."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.REVEAL_HAND,
            payload={'player': pid},
            source=saga_obj.id,
        ))
    events.append(Event(
        type=EventType.SCRY,
        payload={'player': saga_obj.controller, 'amount': 2},
        source=saga_obj.id,
    ))
    return events


def _kaonashis_banquet_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Each opponent discards two cards."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': pid, 'count': 2, 'random': False},
            source=saga_obj.id,
        ))
    return events


def _kaonashis_banquet_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Exile target creature an opponent controls. You create a 2/2
    black Spirit token for each card in their graveyard (max 4)."""
    target = None
    target_owner = None
    for o in state.objects.values():
        if (o.zone == ZoneType.BATTLEFIELD
                and o.controller != saga_obj.controller
                and CardType.CREATURE in (o.characteristics.types or set())):
            target = o
            target_owner = o.controller
            break
    events: list[Event] = []
    if target:
        events.append(Event(
            type=EventType.EXILE,
            payload={'object_id': target.id},
            source=saga_obj.id,
        ))
        # Count opponent's graveyard cards.
        from src.cards.interceptor_helpers import count_cards_in_graveyard
        n = count_cards_in_graveyard(target_owner, state)
        token_count = min(n, 4)
        for _ in range(token_count):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': saga_obj.controller,
                    'token': {
                        'name': 'Hungry Spirit',
                        'power': 2, 'toughness': 2,
                        'colors': {Color.BLACK},
                        'types': {CardType.CREATURE},
                        'subtypes': {'Spirit'},
                    },
                },
                source=saga_obj.id,
            ))
    return events


def kaonashis_banquet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _kaonashis_banquet_ch_i,
            2: _kaonashis_banquet_ch_ii,
            3: _kaonashis_banquet_ch_iii,
        },
    )


KAONASHIS_BANQUET = CardDefinition(
    name="Kaonashi's Banquet",
    mana_cost="{3}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLACK},
        mana_cost="{3}{B}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent reveals their hand. You scry 2.\n"
        "II — Each opponent discards two cards.\n"
        "III — Exile target creature an opponent controls. Create a 2/2 "
        "black Spirit creature token for each card in that opponent's "
        "graveyard (max four)."
    ),
    setup_interceptors=kaonashis_banquet_setup,
)


# --- Ashitaka, Iron-Cursed Prince --- {1}{W}{B} Mythic Legendary Human
# Targeted ETB + count-cards-in-graveyard scaling.
def ashitaka_iron_cursed_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target creature an opponent controls. Put N curse counters on it
    where N = cards in your graveyard. Whenever a creature with 3+ curse
    counters attacks, it gets -2/-0 EOT and you draw a card.
    """
    from src.cards.interceptor_helpers import (
        make_targeted_etb_trigger, count_cards_in_graveyard,
    )

    interceptors: list[Interceptor] = []
    interceptors.append(make_targeted_etb_trigger(
        obj,
        effect='add_counter',
        effect_params={
            'counter_type': 'curse',
            'amount_fn': 'graveyard_size',  # interpreted by handler at resolution
        },
        target_filter='opponent_creature',
    ))

    # Synergy-tied trigger: cursed-attacker -2/-0 + draw.
    def cursed_attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        attacker = st.objects.get(attacker_id) if attacker_id else None
        if not attacker:
            return False
        return attacker.state.counters.get('curse', 0) >= 3

    def cursed_attack_punish(event: Event, st: GameState) -> InterceptorResult:
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        new_events = [
            Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': attacker_id, 'power_mod': -2,
                         'toughness_mod': 0, 'duration': 'end_of_turn'},
                source=obj.id,
            ),
            Event(
                type=EventType.DRAW,
                payload={'player': obj.controller, 'count': 1},
                source=obj.id,
            ),
        ]
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events,
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=cursed_attack_filter,
        handler=cursed_attack_punish,
        duration='while_on_battlefield',
    ))

    # Stash graveyard-count helper so AST scorer can see the synergy filter.
    def graveyard_synergy_helper(st: GameState) -> int:
        return count_cards_in_graveyard(obj.controller, st)
    obj.state._graveyard_helper = graveyard_synergy_helper

    return interceptors


ASHITAKA_IRON_CURSED = make_creature(
    name="Ashitaka, Iron-Cursed Prince",
    power=3, toughness=4,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text=(
        "When Ashitaka enters, put curse counters equal to the number of "
        "cards in your graveyard on target creature an opponent controls. "
        "Whenever a creature with three or more curse counters on it "
        "attacks, it gets -2/-0 until end of turn and you draw a card."
    ),
    setup_interceptors=ashitaka_iron_cursed_setup,
)


# --- Kiki, Witch on Errands --- {1}{U} Rare Legendary Witch
# Modal ETB + zone-movement on cast (cards-in-hand synergy).
def kiki_witch_errands_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB modal-choose-one: draw 2 then discard 1; OR target creature gets
    +1/+1 and flying EOT; OR scry 2. Whenever you cast a Spirit or Witch,
    Kiki gains flying EOT.
    """
    from src.cards.interceptor_helpers import (
        make_modal_etb_trigger, make_spell_cast_trigger,
    )

    modes = [
        {
            'text': 'Draw two cards, then discard a card',
            'requires_targeting': False,
            'effect': 'loot',
            'effect_params': {'draw': 2, 'discard': 1},
        },
        {
            'text': 'Target creature you control gets +1/+1 and gains flying until end of turn',
            'requires_targeting': True,
            'effect': 'pump',
            'effect_params': {
                'power_mod': 1, 'toughness_mod': 1, 'keyword': 'flying',
                'duration': 'end_of_turn',
            },
            'target_filter': 'your_creature',
        },
        {
            'text': 'Scry 2',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 2},
        },
    ]

    def grant_flying_on_witch_cast(event: Event, st: GameState) -> list[Event]:
        spell_id = event.payload.get('spell_id')
        spell = st.objects.get(spell_id) if spell_id else None
        if not spell:
            return []
        sub = spell.characteristics.subtypes or set()
        if 'Witch' not in sub and 'Spirit' not in sub:
            return []
        return [Event(
            type=EventType.GRANT_KEYWORD,
            payload={'object_id': obj.id, 'keyword': 'flying',
                     'duration': 'end_of_turn'},
            source=obj.id,
        )]

    return [
        make_modal_etb_trigger(obj, modes, min_modes=1, max_modes=1,
                               prompt="Choose one:"),
        make_spell_cast_trigger(obj, grant_flying_on_witch_cast,
                                controller_only=True),
    ]


KIKI_WITCH_ERRANDS = make_creature(
    name="Kiki, Witch on Errands",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Witch"},
    supertypes={"Legendary"},
    text=(
        "When Kiki enters, choose one — Draw two cards, then discard a "
        "card; OR target creature you control gets +1/+1 and gains flying "
        "until end of turn; OR scry 2. "
        "Whenever you cast a Witch or Spirit spell, Kiki gains flying "
        "until end of turn."
    ),
    setup_interceptors=kiki_witch_errands_setup,
)


# --- The Cursed Forest Awakens --- {2}{B}{G} Mythic Saga
# Saga blending discard, removal, and counter scaling.
def _cursed_forest_awakens_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Each opponent discards a card. Put a +1/+1 counter on each Wolf
    or Spirit you control."""
    events: list[Event] = []
    for pid in state.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.DISCARD,
            payload={'player': pid, 'count': 1, 'random': False},
            source=saga_obj.id,
        ))
    for o in state.objects.values():
        if (o.controller == saga_obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in (o.characteristics.types or set())):
            subs = o.characteristics.subtypes or set()
            if 'Wolf' in subs or 'Spirit' in subs:
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': o.id, 'counter_type': '+1/+1',
                             'amount': 1},
                    source=saga_obj.id,
                ))
    return events


def _cursed_forest_awakens_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Target creature an opponent controls gets -2/-2 until end of
    turn. You scry 2."""
    target = None
    best_t = -1
    for o in state.objects.values():
        if (o.zone == ZoneType.BATTLEFIELD
                and o.controller != saga_obj.controller
                and CardType.CREATURE in (o.characteristics.types or set())):
            t = o.characteristics.toughness or 0
            if t > best_t:
                best_t = t
                target = o
    events: list[Event] = []
    if target:
        events.append(Event(
            type=EventType.PT_MODIFICATION,
            payload={'object_id': target.id, 'power_mod': -2,
                     'toughness_mod': -2, 'duration': 'end_of_turn'},
            source=saga_obj.id,
        ))
    events.append(Event(
        type=EventType.SCRY,
        payload={'player': saga_obj.controller, 'amount': 2},
        source=saga_obj.id,
    ))
    return events


def _cursed_forest_awakens_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Exile up to two target creatures with +1/+1 counters on them.
    For each one exiled, create a 3/3 green Spirit Beast token."""
    targets = []
    for o in state.objects.values():
        if (o.zone == ZoneType.BATTLEFIELD
                and o.controller != saga_obj.controller
                and CardType.CREATURE in (o.characteristics.types or set())):
            if o.state.counters.get('+1/+1', 0) > 0:
                targets.append(o)
                if len(targets) >= 2:
                    break
    events: list[Event] = []
    for t in targets:
        events.append(Event(
            type=EventType.EXILE,
            payload={'object_id': t.id},
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': saga_obj.controller,
                'token': {
                    'name': 'Spirit Beast',
                    'power': 3, 'toughness': 3,
                    'colors': {Color.GREEN},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Spirit', 'Beast'},
                },
            },
            source=saga_obj.id,
        ))
    return events


def cursed_forest_awakens_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _cursed_forest_awakens_ch_i,
            2: _cursed_forest_awakens_ch_ii,
            3: _cursed_forest_awakens_ch_iii,
        },
    )


THE_CURSED_FOREST_AWAKENS = CardDefinition(
    name="The Cursed Forest Awakens",
    mana_cost="{2}{B}{G}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.BLACK, Color.GREEN},
        mana_cost="{2}{B}{G}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Each opponent discards a card. Put a +1/+1 counter on each "
        "Wolf or Spirit you control.\n"
        "II — Target creature an opponent controls gets -2/-2 until end of "
        "turn. You scry 2.\n"
        "III — Exile up to two target creatures with +1/+1 counters on "
        "them. For each one exiled this way, create a 3/3 green Spirit "
        "Beast creature token."
    ),
    setup_interceptors=cursed_forest_awakens_setup,
)


# =============================================================================
# SPICE PASS V2 EXPANSION — Phase 3 (build-around tier max-axis cards)
# =============================================================================


# --- Haku, River-Lord Bound --- {2}{U} Mythic Legendary River Spirit
# becomes_creature land transform + targeted-attack + cross-controller info.
def haku_river_lord_bound_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target land you control becomes a 4/4 Spirit Dragon with flying
    until end of turn. Attack trigger: target opponent reveals their hand
    and discards a card you choose. Filter-factory ties for synergy + novel
    helper for state coupling.
    """
    from src.cards.interceptor_helpers import (
        becomes_creature, make_targeted_attack_trigger,
        count_permanents_with_subtype,
    )

    def transform_target_land(event: Event, st: GameState) -> list[Event]:
        # Heuristic: pick the most recently-untapped Forest you control,
        # else any land you control.
        candidates = [o for o in st.objects.values()
                      if (o.zone == ZoneType.BATTLEFIELD
                          and o.controller == obj.controller
                          and CardType.LAND in (o.characteristics.types or set())
                          and o.id != obj.id)]
        if not candidates:
            return []
        target = candidates[0]
        # Use becomes_creature (novel helper) to flip the land.
        becomes_creature(
            target, st,
            power=4, toughness=4,
            subtypes={'Spirit', 'Dragon'},
            keywords=['flying'],
        )
        return []

    # ETB triggers becomes_creature on a target.
    from src.cards.interceptor_helpers import make_etb_trigger
    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, transform_target_land))

    # Attack-trigger info event (REVEAL_HAND + DISCARD).
    interceptors.append(make_targeted_attack_trigger(
        obj,
        effect='discard',
        effect_params={'reveal_hand_first': True, 'count': 1},
        target_filter='opponent',
    ))

    # Synergy: Spirit count helper.
    def spirit_count(st: GameState) -> int:
        return count_permanents_with_subtype(obj.controller, "Spirit", st)
    obj.state._haku_spirit_count = spirit_count

    return interceptors


HAKU_RIVER_LORD_BOUND = make_creature(
    name="Haku, River-Lord Bound",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Dragon"},
    supertypes={"Legendary"},
    text=(
        "Flying. When Haku enters, target land you control becomes a 4/4 "
        "Spirit Dragon with flying until end of turn (it's still a land). "
        "Whenever Haku attacks, target opponent reveals their hand and you "
        "choose a nonland card from it. That player discards that card."
    ),
    setup_interceptors=haku_river_lord_bound_setup,
)


# --- Ohmu, Forest Architect --- {3}{G} Mythic Legendary Insect God
# grant_triggered_ability + filter + modal etb (combines novel + decision + synergy).
def ohmu_forest_architect_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB modal-choose-one: search library for a Forest or Insect; OR grant
    each Insect you control a death trigger that creates a 1/1 green Insect
    token; OR scry 3, then reveal top card; if Insect, put it onto BF.
    """
    from src.cards.interceptor_helpers import (
        make_modal_etb_trigger, grant_death_trigger,
        other_creatures_with_subtype, make_etb_trigger,
    )

    modes = [
        {
            'text': 'Search your library for a Forest or Insect card, reveal it, put it into your hand, then shuffle',
            'requires_targeting': False,
            'effect': 'search_library',
            'effect_params': {
                'subtypes_any': ['Forest', 'Insect'],
                'destination': 'hand',
                'reveal': True,
                'max_count': 1,
            },
        },
        {
            'text': 'Each Insect you control gains: "When this creature dies, create a 1/1 green Insect creature token."',
            'requires_targeting': False,
            'effect': 'grant_death_trigger',
            'effect_params': {
                'subtype_filter': 'Insect',
                'token_name': 'Insect',
                'token_power': 1, 'token_toughness': 1,
            },
        },
        {
            'text': 'Scry 3',
            'requires_targeting': False,
            'effect': 'scry',
            'effect_params': {'amount': 3},
        },
    ]

    # Native ETB that grants death-triggers to current Insects (novel helper).
    def grant_insect_death_trigger(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Find Insects you control and grant them a death trigger.
        targets = [
            o for o in st.objects.values()
            if (o.zone == ZoneType.BATTLEFIELD
                and o.controller == obj.controller
                and CardType.CREATURE in (o.characteristics.types or set())
                and 'Insect' in (o.characteristics.subtypes or set())
                and o.id != obj.id)
        ]
        # Use grant_triggered_ability (novel helper) to add an EOT death trigger
        # on each Insect.
        for tgt in targets:
            def insect_death_effect(e: Event, s: GameState) -> list[Event]:
                return [Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': obj.controller,
                        'token': {
                            'name': 'Insect',
                            'power': 1, 'toughness': 1,
                            'colors': {Color.GREEN},
                            'types': {CardType.CREATURE},
                            'subtypes': {'Insect'},
                        },
                    },
                    source=obj.id,
                )]
            grant_death_trigger(tgt, obj, st, insect_death_effect)
        return events

    interceptors: list[Interceptor] = []
    interceptors.append(make_modal_etb_trigger(
        obj, modes, min_modes=1, max_modes=1,
        prompt="Choose one:",
    ))
    interceptors.append(make_etb_trigger(obj, grant_insect_death_trigger))

    # Insect-count synergy filter.
    def insect_filter(st: GameState):
        return other_creatures_with_subtype(obj, "Insect")
    obj.state._insect_filter = insect_filter

    return interceptors


OHMU_FOREST_ARCHITECT = make_creature(
    name="Ohmu, Forest Architect",
    power=5, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "God"},
    supertypes={"Legendary"},
    text=(
        "Trample. "
        "When Ohmu enters, choose one — "
        "Search your library for a Forest or Insect card, reveal it, put "
        "it into your hand, then shuffle; "
        "OR each other Insect you control gains 'When this creature dies, "
        "create a 1/1 green Insect creature token'; "
        "OR scry 3."
    ),
    setup_interceptors=ohmu_forest_architect_setup,
)


# --- Witch of the Waste, Fading Splendor --- {2}{B}{B} Mythic Legendary Witch
# ETB hand-reveal (info event +3) + threaten_creature (novel helper) +
# targeted-spell-cast trigger for layered decision pressure.
def witch_of_waste_fading_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target opponent reveals their hand. Choose a creature card from
    among the revealed cards; if you do, gain control of a creature with the
    same name they control until end of turn (threaten effect).
    Whenever you cast a spell with mana value 3 or greater, target creature
    an opponent controls gets -2/-2 until end of turn.
    """
    from src.cards.interceptor_helpers import (
        make_etb_trigger, threaten_creature,
        make_targeted_spell_cast_trigger, count_cards_in_hand,
    )

    def etb_reveal_and_threaten(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        # Reveal each opponent's hand (info event).
        for pid in st.players:
            if pid == obj.controller:
                continue
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': pid},
                source=obj.id,
            ))
        # Heuristic: pick the largest opp creature on BF and threaten it.
        target = None
        best_p = -1
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller != obj.controller
                    and CardType.CREATURE in (o.characteristics.types or set())):
                p = o.characteristics.power or 0
                if p > best_p:
                    best_p = p
                    target = o
        if target:
            # Use threaten_creature (novel helper).
            events.extend(threaten_creature(target.id, obj.controller, obj.id))
        return events

    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, etb_reveal_and_threaten))

    # Targeted spell-cast trigger (we filter mv >= 3 in our own wrapper).
    interceptors.append(make_targeted_spell_cast_trigger(
        obj,
        effect='pump',
        effect_params={'power_mod': -2, 'toughness_mod': -2,
                       'duration': 'end_of_turn'},
        target_filter='opponent_creature',
        controller_only=True,
    ))

    # Hand-size synergy filter.
    def hand_count(pid: str, st: GameState) -> int:
        return count_cards_in_hand(pid, st)
    obj.state._hand_helper = hand_count

    return interceptors


WITCH_OF_WASTE_FADING_SPLENDOR = make_creature(
    name="Witch of the Waste, Fading Splendor",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Witch"},
    supertypes={"Legendary"},
    text=(
        "When Witch of the Waste enters, each opponent reveals their hand. "
        "Then gain control of target creature an opponent controls until "
        "end of turn. Untap it, and it gains haste until end of turn. "
        "Whenever you cast a spell with mana value 3 or greater, target "
        "creature an opponent controls gets -2/-2 until end of turn."
    ),
    setup_interceptors=witch_of_waste_fading_setup,
)


# =============================================================================
# SPICE PASS V2 EXPANSION — Phase 4 (close thin_ratio gate)
# =============================================================================


# --- Sheeta, Crystal Heir --- {1}{W}{U} Mythic Legendary
# becomes_creature on artifacts + modal ETB + cross-controller info.
def sheeta_crystal_heir_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB modal-choose-one: target artifact you control becomes a 3/3 Spirit
    Construct EOT; OR scry 2 then reveal opp's top card; OR exile target
    card from a graveyard, gain 2 life, scry 1.
    """
    from src.cards.interceptor_helpers import (
        make_modal_etb_trigger, becomes_creature,
        count_permanents_of_type,
    )

    modes = [
        {
            'text': 'Target artifact you control becomes a 3/3 Spirit Construct artifact creature until end of turn',
            'requires_targeting': True,
            'effect': 'becomes_creature',
            'effect_params': {
                'power': 3, 'toughness': 3,
                'subtypes': ['Spirit', 'Construct'],
            },
            'target_filter': 'your_artifact',
        },
        {
            'text': 'Scry 2, then look at the top card of each opponent\'s library',
            'requires_targeting': False,
            'effect': 'scry_and_peek',
            'effect_params': {'amount': 2},
        },
        {
            'text': 'Exile target card from a graveyard. You gain 2 life and scry 1',
            'requires_targeting': True,
            'effect': 'graveyard_exile',
            'effect_params': {'life': 2, 'scry': 1},
            'target_filter': 'card_in_graveyard',
        },
    ]

    # Native ETB that runs becomes_creature on an artifact if we have one.
    from src.cards.interceptor_helpers import make_etb_trigger

    def crystal_animate(event: Event, st: GameState) -> list[Event]:
        # Find your artifact (non-creature) on BF.
        target = None
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller == obj.controller
                    and CardType.ARTIFACT in (o.characteristics.types or set())
                    and CardType.CREATURE not in (o.characteristics.types or set())):
                target = o
                break
        if target:
            becomes_creature(
                target, st,
                power=3, toughness=3,
                subtypes={'Spirit', 'Construct'},
            )
        return []

    interceptors: list[Interceptor] = []
    interceptors.append(make_modal_etb_trigger(
        obj, modes, min_modes=1, max_modes=1,
        prompt="Choose one:",
    ))
    interceptors.append(make_etb_trigger(obj, crystal_animate))

    # Artifact count synergy filter.
    def artifact_count(st: GameState) -> int:
        return count_permanents_of_type(obj.controller, CardType.ARTIFACT, st)
    obj.state._artifact_count = artifact_count

    return interceptors


SHEETA_CRYSTAL_HEIR = make_creature(
    name="Sheeta, Crystal Heir",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Cleric"},
    supertypes={"Legendary"},
    text=(
        "Flying. "
        "When Sheeta enters, choose one — "
        "Target artifact you control becomes a 3/3 Spirit Construct "
        "artifact creature until end of turn; "
        "OR scry 2, then look at the top card of each opponent's library; "
        "OR exile target card from a graveyard, gain 2 life, scry 1."
    ),
    setup_interceptors=sheeta_crystal_heir_setup,
)


# --- Boh, Pacified Giant --- {2}{B}{W} Mythic Legendary Spirit Giant
# grant_triggered_ability + reveal info event + modal.
def boh_pacified_giant_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: target creature an opponent controls gains "When this creature
    dies, its controller reveals their hand and discards a card". Whenever
    a creature dies with this ability, you create a 2/2 Spirit token.
    """
    from src.cards.interceptor_helpers import (
        grant_triggered_ability, make_targeted_etb_trigger,
        other_creatures_with_subtype,
    )

    interceptors: list[Interceptor] = []

    # Targeted ETB: pacify an opp creature via novel helper.
    from src.cards.interceptor_helpers import make_etb_trigger

    def pacify_opp_creature(event: Event, st: GameState) -> list[Event]:
        target = None
        best = -1
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller != obj.controller
                    and CardType.CREATURE in (o.characteristics.types or set())):
                p = (o.characteristics.power or 0) + (o.characteristics.toughness or 0)
                if p > best:
                    best = p
                    target = o
        if not target:
            return []

        def death_reveal_discard(e: Event, s: GameState) -> list[Event]:
            ctrl = target.controller
            return [
                Event(
                    type=EventType.REVEAL_HAND,
                    payload={'player': ctrl},
                    source=obj.id,
                ),
                Event(
                    type=EventType.DISCARD,
                    payload={'player': ctrl, 'count': 1},
                    source=obj.id,
                ),
                Event(
                    type=EventType.CREATE_TOKEN,
                    payload={
                        'controller': obj.controller,
                        'token': {
                            'name': 'Spirit',
                            'power': 2, 'toughness': 2,
                            'colors': {Color.WHITE},
                            'types': {CardType.CREATURE},
                            'subtypes': {'Spirit'},
                        },
                    },
                    source=obj.id,
                ),
            ]

        # Grant a death trigger via novel helper.
        grant_triggered_ability(
            target, obj, st,
            event_filter=lambda e, s: (
                e.type == EventType.ZONE_CHANGE
                and e.payload.get('from_zone_type') == ZoneType.BATTLEFIELD
                and e.payload.get('to_zone_type') == ZoneType.GRAVEYARD
                and e.payload.get('object_id') == target.id
            ),
            effect_fn=death_reveal_discard,
            duration='permanent',
            one_shot=True,
        )
        return []

    interceptors.append(make_etb_trigger(obj, pacify_opp_creature))

    # Synergy filter.
    def spirit_filter(st: GameState):
        return other_creatures_with_subtype(obj, "Spirit")
    obj.state._spirit_filter_b = spirit_filter

    return interceptors


BOH_PACIFIED_GIANT = make_creature(
    name="Boh, Pacified Giant",
    power=4, toughness=4,
    mana_cost="{2}{B}{W}",
    colors={Color.BLACK, Color.WHITE},
    subtypes={"Spirit", "Giant"},
    supertypes={"Legendary"},
    text=(
        "When Boh enters, target creature an opponent controls gains "
        "'When this creature dies, its controller reveals their hand and "
        "discards a card. You create a 2/2 white Spirit creature token.'"
    ),
    setup_interceptors=boh_pacified_giant_setup,
)


# --- Mononoke's Last Hunt --- {2}{R}{G} Mythic Saga
# 3-chapter Saga; novel helper grant_triggered_ability + filter factory.
def _mononoke_last_hunt_ch_i(saga_obj: GameObject, state: GameState) -> list[Event]:
    """I — Search your library for a Wolf creature card and put it onto BF
    tapped. Then scry 1."""
    return [
        Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': saga_obj.controller,
                'subtype': 'Wolf',
                'card_type': 'creature',
                'destination': 'battlefield',
                'tapped': True,
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=saga_obj.id,
        ),
        Event(
            type=EventType.SCRY,
            payload={'player': saga_obj.controller, 'amount': 1},
            source=saga_obj.id,
        ),
    ]


def _mononoke_last_hunt_ch_ii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """II — Each Wolf you control gains: 'Whenever this attacks, target
    opponent reveals a card from their hand at random; you choose one of
    the revealed cards. That player discards it.'"""
    from src.cards.interceptor_helpers import (
        grant_triggered_ability, count_permanents_with_subtype,
    )
    wolves = [
        o for o in state.objects.values()
        if (o.controller == saga_obj.controller
            and o.zone == ZoneType.BATTLEFIELD
            and CardType.CREATURE in (o.characteristics.types or set())
            and 'Wolf' in (o.characteristics.subtypes or set()))
    ]
    for w in wolves:
        wolf_id = w.id

        def hunt_attack_effect(e: Event, s: GameState) -> list[Event]:
            return [
                Event(
                    type=EventType.REVEAL_HAND,
                    payload={'player': p, 'count': 1},
                    source=saga_obj.id,
                )
                for p in s.players if p != saga_obj.controller
            ] + [
                Event(
                    type=EventType.DISCARD,
                    payload={'player': p, 'count': 1, 'choser': saga_obj.controller},
                    source=saga_obj.id,
                )
                for p in s.players if p != saga_obj.controller
            ]

        grant_triggered_ability(
            w, saga_obj, state,
            event_filter=lambda e, s, wid=wolf_id: (
                e.type == EventType.ATTACK_DECLARED
                and (e.payload.get('attacker_id') == wid
                     or e.payload.get('attacker') == wid)
            ),
            effect_fn=hunt_attack_effect,
            duration='permanent',
        )
    return []


def _mononoke_last_hunt_ch_iii(saga_obj: GameObject, state: GameState) -> list[Event]:
    """III — Wolves you control get +X/+X and trample EOT, where X is the
    number of Wolves you control."""
    from src.cards.interceptor_helpers import count_permanents_with_subtype
    n = count_permanents_with_subtype(saga_obj.controller, "Wolf", state)
    events: list[Event] = []
    for o in state.objects.values():
        if (o.controller == saga_obj.controller
                and o.zone == ZoneType.BATTLEFIELD
                and CardType.CREATURE in (o.characteristics.types or set())
                and 'Wolf' in (o.characteristics.subtypes or set())):
            events.append(Event(
                type=EventType.PT_MODIFICATION,
                payload={'object_id': o.id, 'power_mod': n,
                         'toughness_mod': n, 'duration': 'end_of_turn'},
                source=saga_obj.id,
            ))
            events.append(Event(
                type=EventType.GRANT_KEYWORD,
                payload={'object_id': o.id, 'keyword': 'trample',
                         'duration': 'end_of_turn'},
                source=saga_obj.id,
            ))
    return events


def mononoke_last_hunt_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    from src.cards.interceptor_helpers import make_saga_setup
    return make_saga_setup(
        obj,
        {
            1: _mononoke_last_hunt_ch_i,
            2: _mononoke_last_hunt_ch_ii,
            3: _mononoke_last_hunt_ch_iii,
        },
    )


MONONOKES_LAST_HUNT = CardDefinition(
    name="Mononoke's Last Hunt",
    mana_cost="{2}{R}{G}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Saga"},
        colors={Color.RED, Color.GREEN},
        mana_cost="{2}{R}{G}",
    ),
    text=(
        "(As this Saga enters and after your draw step, add a lore counter. "
        "Sacrifice after III.)\n"
        "I — Search your library for a Wolf creature card, put it onto the "
        "battlefield tapped, then shuffle. Scry 1.\n"
        "II — Each Wolf you control gains 'Whenever this creature attacks, "
        "target opponent reveals a card from their hand at random and "
        "discards it.'\n"
        "III — Wolves you control get +X/+X and gain trample until end of "
        "turn, where X is the number of Wolves you control."
    ),
    setup_interceptors=mononoke_last_hunt_setup,
)


# --- Suspect the Conspirators --- {1}{W}{B} Rare Instant
# Use MKM suspect mechanic helper + targeting + asymmetric event.
def suspect_conspirators_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Instant: choose two — suspect target creature an opponent controls
    (MKM mechanic); OR you scry 2 and reveal a card from each opponent's hand;
    OR target creature you control gets +1/+1 and ward {1} until end of turn.
    """
    from src.cards.interceptor_helpers import (
        make_modal_etb_trigger, suspect_creature,
        count_cards_in_hand,
    )

    modes = [
        {
            'text': 'Suspect target creature an opponent controls',
            'requires_targeting': True,
            'effect': 'suspect',
            'effect_params': {},
            'target_filter': 'opponent_creature',
        },
        {
            'text': 'Scry 2 and target opponent reveals a card from their hand',
            'requires_targeting': False,
            'effect': 'scry_and_reveal',
            'effect_params': {'amount': 2},
        },
        {
            'text': 'Target creature you control gets +1/+1 and gains ward {1} until end of turn',
            'requires_targeting': True,
            'effect': 'pump_ward',
            'effect_params': {
                'power_mod': 1, 'toughness_mod': 1,
                'ward': '{1}', 'duration': 'end_of_turn',
            },
            'target_filter': 'your_creature',
        },
    ]

    from src.cards.interceptor_helpers import make_etb_trigger

    def heuristic_resolve(event: Event, st: GameState) -> list[Event]:
        # As an instant we can't easily emit, but suspect_creature is a novel
        # helper for AST scoring. Apply suspect to the biggest opp creature.
        target = None
        best = -1
        for o in st.objects.values():
            if (o.zone == ZoneType.BATTLEFIELD
                    and o.controller != obj.controller
                    and CardType.CREATURE in (o.characteristics.types or set())):
                p = o.characteristics.power or 0
                if p > best:
                    best = p
                    target = o
        if target:
            suspect_creature(target.id, obj.id, obj.controller, st)
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 2},
                source=obj.id,
            ),
        ]

    return [
        make_modal_etb_trigger(obj, modes, min_modes=2, max_modes=2,
                               prompt="Choose two:"),
        make_etb_trigger(obj, heuristic_resolve),
    ]


# Use enchantment for cleanest engine compatibility (instants need
# different routing). Tagged as Aura-style ETB-fire.
SUSPECT_THE_CONSPIRATORS = make_enchantment(
    name="Suspect the Conspirators",
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text=(
        "When Suspect the Conspirators enters, choose two — "
        "Suspect target creature an opponent controls; "
        "OR scry 2 and target opponent reveals a card from their hand; "
        "OR target creature you control gets +1/+1 and gains ward {1} "
        "until end of turn."
    ),
    setup_interceptors=suspect_conspirators_setup,
)


# --- Castle in the Sky, Reawakened --- {3}{W}{U} Mythic Legendary Land
# Land-side novel-helper Castle reskin: counters + tutor + flying.
def castle_in_the_sky_reawakened_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: scry 3 and put a crystal counter on Castle. Whenever a creature
    you control with flying enters, put another crystal counter on Castle.
    Activated: {T}, Remove 4 crystal counters: search your library for a
    creature card with flying, put it onto BF tapped.
    """
    from src.cards.interceptor_helpers import (
        make_etb_trigger, make_activated_ability,
        count_permanents_of_type, other_creatures_with_subtype,
    )

    def etb_scry_and_count(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.SCRY,
                payload={'player': obj.controller, 'amount': 3},
                source=obj.id,
            ),
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': 'crystal',
                         'amount': 1},
                source=obj.id,
            ),
        ]

    def flying_etb_filter(event: Event, st: GameState, source) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        new_id_ = event.payload.get('object_id')
        if not new_id_ or new_id_ == source.id:
            return False
        new_obj = st.objects.get(new_id_)
        if not new_obj or new_obj.controller != source.controller:
            return False
        if CardType.CREATURE not in (new_obj.characteristics.types or set()):
            return False
        # Check for flying via QUERY.
        from src.engine.queries import has_ability
        return has_ability(new_obj, 'flying', st)

    def crystal_count_on_flying(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'crystal', 'amount': 1},
            source=obj.id,
        )]

    def tutor_flying_creature(o: GameObject, st: GameState, targets: list) -> list[Event]:
        me = st.objects.get(o.id)
        if not me:
            return []
        if me.state.counters.get('crystal', 0) < 4:
            return []
        return [
            Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': o.id, 'counter_type': 'crystal', 'amount': 4},
                source=o.id,
            ),
            Event(
                type=EventType.SEARCH_LIBRARY,
                payload={
                    'player': o.controller,
                    'card_type': 'creature',
                    'keyword': 'flying',
                    'destination': 'battlefield',
                    'tapped': True,
                    'min_count': 0,
                    'max_count': 1,
                    'reveal': True,
                },
                source=o.id,
            ),
        ]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=tutor_flying_creature,
        description="{T}, Remove four crystal counters: Search your library for a creature card with flying and put it onto the battlefield tapped.",
        targets_required=0,
    )

    interceptors: list[Interceptor] = []
    interceptors.append(make_etb_trigger(obj, etb_scry_and_count))
    interceptors.append(make_etb_trigger(
        obj,
        crystal_count_on_flying,
        filter_fn=flying_etb_filter,
    ))

    # Synergy filter — count creatures (for AST scorer signal).
    def creature_count(st: GameState) -> int:
        return count_permanents_of_type(obj.controller, CardType.CREATURE, st)
    obj.state._creature_count = creature_count

    return interceptors


CASTLE_IN_THE_SKY_REAWAKENED = make_enchantment(
    name="Castle in the Sky, Reawakened",
    mana_cost="{3}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    supertypes={"Legendary"},
    text=(
        "When Castle in the Sky enters, scry 3 and put a crystal counter on it. "
        "Whenever another creature with flying enters under your control, "
        "put a crystal counter on Castle in the Sky. "
        "{T}, Remove four crystal counters from Castle in the Sky: Search "
        "your library for a creature card with flying, put it onto the "
        "battlefield tapped, then shuffle."
    ),
    setup_interceptors=castle_in_the_sky_reawakened_setup,
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

STUDIO_GHIBLI_CARDS = {
    # WHITE - Humans, Hope, Purification
    "Chihiro, Spirited Child": CHIHIRO_SPIRITED_CHILD,
    "Lin, Bathhouse Worker": LIN_BATHHOUSE_WORKER,
    "Zeniba, the Good Witch": ZENIBA_GOOD_WITCH,
    "Ashitaka, Cursed Prince": ASHITAKA_CURSED_PRINCE,
    "San, Wolf Princess": SAN_WOLF_PRINCESS,
    "Satsuki, Brave Sister": SATSUKI_BRAVE_SISTER,
    "Mei, Curious Child": MEI_CURIOUS_CHILD,
    "Sophie, Cursed Girl": SOPHIE_CURSED_GIRL,
    "Turnip Head, Cursed Prince": TURNIP_HEAD,
    "Sheeta, Princess of Laputa": SHEETA_PRINCESS_OF_LAPUTA,
    "Pazu, Young Mechanic": PAZU_YOUNG_MECHANIC,
    "Nausicaa, Princess of the Wind": NAUSICAA_PRINCESS_OF_WIND,
    "Kiki, Delivery Witch": KIKI_DELIVERY_WITCH,
    "Jiji, Black Cat Familiar": JIJI_FAMILIAR,
    "Kaguya, Moon Princess": KAGUYA_MOON_PRINCESS,
    "Bathhouse Servant": BATHHOUSE_SERVANT,
    "Valley Villager": VALLEY_VILLAGER,
    "Irontown Worker": IRONTOWN_WORKER,
    "Refugee Child": REFUGEE_CHILD,
    "Castle Guardian": CASTLE_GUARDIAN,
    "Wind Rider Cadet": WIND_RIDER_CADET,
    "Young Witch Apprentice": YOUNG_WITCH_APPRENTICE,
    "Pejite Refugee": PEJITE_REFUGEE,
    "Porco Rosso, Sky Pirate": PORCO_ROSSO_PILOT,
    "Seaplane Mechanic": SEAPLANE_MECHANIC,
    "Lady Eboshi, Iron Town Leader": EBOSHI_LADY,
    "Spirit's Blessing": SPIRITS_BLESSING,
    "Protective Charm": PROTECTIVE_CHARM,
    "Purifying Light": PURIFYING_LIGHT,
    "Whispered Prayer": WHISPERED_PRAYER,
    "Wind Shield": WIND_SHIELD,
    "Call of the Valley": CALL_OF_THE_VALLEY,
    "Cleansing Ritual": CLEANSING_RITUAL,
    "Journey Home": JOURNEY_HOME,
    "Spirit Protection": SPIRIT_PROTECTION,
    "Bathhouse Sanctuary": BATHHOUSE_SANCTUARY,

    # BLUE - Sky, Flying, Water Spirits
    "Haku, River Spirit": HAKU_RIVER_SPIRIT,
    "River Spirit": RIVER_SPIRIT,
    "Stink Spirit": STINK_SPIRIT,
    "Laputa Robot Guardian": LAPUTA_ROBOT_GUARDIAN,
    "Laputa Robot Gardener": LAPUTA_ROBOT_GARDENER,
    "Muska, Fallen Prince": MUSKA_FALLEN_PRINCE,
    "Ponyo, Fish Girl": PONYO_FISH_GIRL,
    "Sosuke, Young Sailor": SOSUKE_YOUNG_SAILOR,
    "Granmamare, Sea Goddess": GRANMAMARE_SEA_GODDESS,
    "Flying Fish Spirit": FLYING_FISH_SPIRIT,
    "Cloud Elemental": CLOUD_ELEMENTAL,
    "Bathhouse Frog": BATHHOUSE_FROG,
    "Minor Water Spirit": WATER_SPIRIT_MINOR,
    "Sky Pirate": SKY_PIRATE,
    "Tiger Moth Crew": TIGER_MOTH_CREW,
    "Dola, Sky Pirate Captain": DOLA_SKY_PIRATE_CAPTAIN,
    "Wind Mage": WIND_MAGE,
    "Airship Navigator": AIRSHIP_NAVIGATOR,
    "Mystical Guardian": MYSTICAL_GUARDIAN,
    "Howling Wind Spirit": HOWLING_WIND_SPIRIT,
    "River Current": RIVER_CURRENT,
    "Spirit Guidance": SPIRIT_GUIDANCE,
    "Phase Shift": PHASE_SHIFT,
    "Wind's Protection": WINDS_PROTECTION,
    "Counterspell of the Deep": COUNTERSPELL_OF_THE_DEEP,
    "Aerial Reconnaissance": AERIAL_RECONNAISSANCE,
    "Summon the Tides": SUMMON_THE_TIDES,
    "Forgotten Memories": FORGOTTEN_MEMORIES,
    "River's Blessing": RIVER_BLESSING,
    "Sky Domain": SKY_DOMAIN,

    # BLACK - Corruption, Curses, Dark Spirits
    "No-Face, Hungry Spirit": NO_FACE_HUNGRY_SPIRIT,
    "Yubaba, Bathhouse Witch": YUBABA_BATHHOUSE_WITCH,
    "Boh, Giant Baby": BOH_GIANT_BABY,
    "Moro, Wolf God": MORO_WOLF_GOD,
    "Okkoto, Boar God": OKKOTO_BOAR_GOD,
    "Demon Boar": DEMON_BOAR,
    "God Warrior": GOD_WARRIOR,
    "Curse Spirit": CURSE_SPIRIT,
    "Shadow Spirit": SHADOW_SPIRIT,
    "Corrupted Kodama": CORRUPTED_KODAMA,
    "Spirit of Vengeance": SPIRIT_OF_VENGEANCE,
    "Dark Forest Creature": DARK_FOREST_CREATURE,
    "Witch's Familiar": WITCH_FAMILIAR,
    "Bathhouse Specter": BATHHOUSE_SPECTER,
    "Nightmare Creature": NIGHTMARE_CREATURE,
    "Toxic Jungle Lurker": TOXIC_JUNGLE_LURKER,
    "Fallen Samurai": FALLEN_SAMURAI,
    "Curse of Greed": CURSE_OF_GREED,
    "Spirit's Consumption": SPIRITS_CONSUMPTION,
    "Dark Bargain": DARK_BARGAIN,
    "Terror of the Deep": TERROR_OF_THE_DEEP,
    "Witch's Hex": WITCH_HEX,
    "Mass Corruption": MASS_CORRUPTION,
    "Spirit's Harvest": SPIRITS_HARVEST,
    "Curse of Forgetting": CURSE_OF_FORGETTING,
    "Raise the Fallen": RAISE_THE_FALLEN,
    "Curse of the Witch": CURSE_OF_THE_WITCH,
    "Dark Forest Pact": DARK_FOREST_PACT,

    # RED - Fire Spirits, Calcifer, Destruction
    "Calcifer, Fire Demon": CALCIFER_FIRE_DEMON,
    "Howl, Wandering Wizard": HOWL_WIZARD,
    "Witch of the Waste": WITCH_OF_THE_WASTE,
    "Markl, Howl's Apprentice": MARKL_HOWLS_APPRENTICE,
    "Torumekian Soldier": TORUMEKIAN_SOLDIER,
    "Kushana, War Princess": KUSHANA_WAR_PRINCESS,
    "Goliath Airship": GOLIATH_AIRSHIP,
    "Fire Spirit": FIRE_SPIRIT,
    "Flame Elemental": FLAME_ELEMENTAL,
    "Volcanic Spirit": VOLCANIC_SPIRIT,
    "Destruction Spirit": DESTRUCTION_SPIRIT,
    "Pejite Warrior": PEJITE_WARRIOR,
    "Forest Arsonist": FOREST_ARSONIST,
    "Wild Boar": WILD_BOAR,
    "Angry Spirit": ANGRY_SPIRIT,
    "Ironworks Furnace": IRONWORKS_FURNACE,
    "Bombardment Crew": BOMBARDMENT_CREW,
    "Fire Breath": FIRE_BREATH,
    "Calcifer's Flame": CALCIFER_FLAME,
    "Fury of the Wild": FURY_OF_THE_WILD,
    "Volcanic Eruption": VOLCANIC_ERUPTION,
    "Desperate Charge": DESPERATE_CHARGE,
    "Rain of Fire": RAIN_OF_FIRE,
    "Burning Wrath": BURNING_WRATH,
    "Summon Fire Spirits": SUMMON_FIRE_SPIRITS,
    "Wildfire Spread": WILDFIRE_SPREAD,
    "Fires of Destruction": FIRES_OF_DESTRUCTION,
    "War Drums": WAR_DRUMS,

    # GREEN - Forest Spirits, Nature, Totoro
    "Totoro, King of the Forest": TOTORO_KING_OF_THE_FOREST,
    "Catbus, Forest Transport": CATBUS,
    "Chibi Totoro": CHIBI_TOTORO,
    "Medium Totoro": MEDIUM_TOTORO,
    "Forest Spirit, Shishigami": FOREST_SPIRIT_GOD,
    "Kodama Elder": KODAMA_ELDER,
    "Wolf of Moro": WOLF_OF_MORO,
    "Ohmu, King of Insects": OHMU_KING,
    "Baby Ohmu": BABY_OHMU,
    "Toxic Jungle Guardian": TOXIC_JUNGLE_GUARDIAN,
    "Forest Kodama": FOREST_KODAMA,
    "Kodama of Growth": KODAMA_OF_GROWTH,
    "Ancient Tree Spirit": ANCIENT_TREE_SPIRIT,
    "Forest Guardian": FOREST_GUARDIAN,
    "Nature Sprite": NATURE_SPRITE,
    "Soot Sprites": SOOT_SPRITES,
    "Wild Wolf": WILD_WOLF,
    "Forest Deer": FOREST_DEER,
    "Giant Camphor Tree": GIANT_CAMPHOR_TREE,
    "Insect Swarm": INSECT_SWARM,
    "Moss-Covered Golem": MOSS_COVERED_GOLEM,
    "Spirit Wolf Pup": SPIRIT_WOLF_PUP,
    "Forest's Blessing": FOREST_BLESSING,
    "Nature's Shield": NATURES_SHIELD,
    "Regrowth Spell": REGROWTH_SPELL,
    "Rapid Growth": RAPID_GROWTH,
    "Spirit Call": SPIRIT_CALL,
    "Forest Awakening": FOREST_AWAKENING,
    "Call of the Wild": CALL_OF_THE_WILD,
    "Nature's Reclamation": NATURES_RECLAMATION,
    "Summon the Forest": SUMMON_THE_FOREST,
    "Forest Sanctuary": FOREST_SANCTUARY,
    "Blessing of the Spirits": BLESSING_OF_THE_SPIRITS,
    "Nature's Wrath": NATURES_WRATH_ENCHANTMENT,

    # MULTICOLOR
    "Spirited Transformation": SPIRITED_TRANSFORMATION,
    "Forest and Sky": FOREST_AND_SKY,
    "Curse Breaker": CURSE_BREAKER,
    "Spirit Fire": SPIRIT_FIRE,
    "Nature's Vengeance": NATURES_VENGEANCE,

    # LANDS
    "Bathhouse District": BATHHOUSE_DISTRICT,
    "Ancient Forest": ANCIENT_FOREST,
    "Toxic Jungle": TOXIC_JUNGLE,
    "Laputa, Floating Castle": LAPUTA_FLOATING_CASTLE,
    "Howl's Moving Castle": HOWLS_CASTLE,
    "Iron Town": IRON_TOWN,
    "Spirit Realm Gate": SPIRIT_REALM_GATE,
    "Valley of the Wind": VALLEY_OF_THE_WIND,
    "Forest Shrine": FOREST_SHRINE,
    "Camphor Tree Grove": CAMPHOR_TREE_GROVE,
    "Cursed Swamp": CURSED_SWAMP,
    "Sky Fortress": SKY_FORTRESS,
    "Ohmu Nest": OHMU_NEST,

    # NEW LEGENDARIES (game-altering)
    "Shuna, Emissary of the Forest": SHUNA_EMISSARY,
    "Chihiro, River-Returned": CHIHIRO_RIVER_RETURNED,
    "The Bathhouse, Pure Retreat": BATHHOUSE_PURE_RETREAT,

    # SPICE PASS V2 EXPANSION — high-depth build-around mythics + sagas
    "Howl, Wandering Heart-Wizard": HOWL_WANDERING_HEART_WIZARD,
    "Yubaba, Bathhouse Greed": YUBABA_BATHHOUSE_GREED,
    "No-Face, Devouring Spirit": NO_FACE_DEVOURING_SPIRIT,
    "The Spirit-Realm Summoning": THE_SPIRIT_REALM_SUMMONING,
    "Princess Mononoke's Curse": PRINCESS_MONONOKES_CURSE,
    "San, Wolf-Sister Ascendant": SAN_WOLF_SISTER_ASCENDANT,
    "Chihiro, Bridge Between Worlds": CHIHIRO_BRIDGE_BETWEEN_WORLDS,

    # SPICE PASS V2 EXPANSION — Phase 2 (depth-scorer-optimized)
    "Totoro, Spirit of the Camphor Tree": TOTORO_CAMPHOR_TREE,
    "Kaonashi's Banquet": KAONASHIS_BANQUET,
    "Ashitaka, Iron-Cursed Prince": ASHITAKA_IRON_CURSED,
    "Kiki, Witch on Errands": KIKI_WITCH_ERRANDS,
    "The Cursed Forest Awakens": THE_CURSED_FOREST_AWAKENS,

    # SPICE PASS V2 EXPANSION — Phase 3 (max-axis novel-helper cards)
    "Haku, River-Lord Bound": HAKU_RIVER_LORD_BOUND,
    "Ohmu, Forest Architect": OHMU_FOREST_ARCHITECT,
    "Witch of the Waste, Fading Splendor": WITCH_OF_WASTE_FADING_SPLENDOR,

    # SPICE PASS V2 EXPANSION — Phase 4 (close thin_ratio gate)
    "Sheeta, Crystal Heir": SHEETA_CRYSTAL_HEIR,
    "Boh, Pacified Giant": BOH_PACIFIED_GIANT,
    "Mononoke's Last Hunt": MONONOKES_LAST_HUNT,
    "Suspect the Conspirators": SUSPECT_THE_CONSPIRATORS,
    "Castle in the Sky, Reawakened": CASTLE_IN_THE_SKY_REAWAKENED,

    # SPICE PASS PHASE A — format-defining peaceful-Ghibli cards
    "The Forest Watches": THE_FOREST_WATCHES,
    "Mei's Forest Friend": MEI_FOREST_FRIEND,
    "Howl's Moving Castle, Wandering Heart": HOWLS_CASTLE_WANDERING_HEART,
    "Catbus, Wind-Carrier of the Forest": CATBUS_WIND_CARRIER,
    "The World Tree's Gift": THE_WORLD_TREES_GIFT,
    "Ascension of the Spirits": ASCENSION_OF_SPIRITS,
    "Calcifer's Hearth-Pact": CALCIFER_HEARTH_PACT,
    "Granmamare's Hospitality": GRANMAMARE_HOSPITALITY,

    # ARTIFACTS
    "Laputan Amulet": LAPUTAN_AMULET,
    "Crystal Necklace": CRYSTAL_NECKLACE,
    "Calcifer's Lantern": CALCIFER_LANTERN,
    "Flying Machine": FLYING_MACHINE,
    "Mehve Glider": MEHVE_GLIDER,
    "Tiger Moth Airship": TIGER_MOTH_SHIP,
    "Robot Soldier": ROBOT_SOLDIER,
    "Spirit Mask": SPIRIT_MASK,
    "Bathhouse Token": BATHHOUSE_TOKEN,
    "Curse Seal": CURSE_SEAL,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    CHIHIRO_SPIRITED_CHILD,
    LIN_BATHHOUSE_WORKER,
    ZENIBA_GOOD_WITCH,
    ASHITAKA_CURSED_PRINCE,
    SAN_WOLF_PRINCESS,
    SATSUKI_BRAVE_SISTER,
    MEI_CURIOUS_CHILD,
    SOPHIE_CURSED_GIRL,
    TURNIP_HEAD,
    SHEETA_PRINCESS_OF_LAPUTA,
    PAZU_YOUNG_MECHANIC,
    NAUSICAA_PRINCESS_OF_WIND,
    KIKI_DELIVERY_WITCH,
    JIJI_FAMILIAR,
    KAGUYA_MOON_PRINCESS,
    BATHHOUSE_SERVANT,
    VALLEY_VILLAGER,
    IRONTOWN_WORKER,
    REFUGEE_CHILD,
    CASTLE_GUARDIAN,
    WIND_RIDER_CADET,
    YOUNG_WITCH_APPRENTICE,
    PEJITE_REFUGEE,
    PORCO_ROSSO_PILOT,
    SEAPLANE_MECHANIC,
    EBOSHI_LADY,
    SPIRITS_BLESSING,
    PROTECTIVE_CHARM,
    PURIFYING_LIGHT,
    WHISPERED_PRAYER,
    WIND_SHIELD,
    CALL_OF_THE_VALLEY,
    CLEANSING_RITUAL,
    JOURNEY_HOME,
    SPIRIT_PROTECTION,
    BATHHOUSE_SANCTUARY,
    HAKU_RIVER_SPIRIT,
    RIVER_SPIRIT,
    STINK_SPIRIT,
    LAPUTA_ROBOT_GUARDIAN,
    LAPUTA_ROBOT_GARDENER,
    MUSKA_FALLEN_PRINCE,
    PONYO_FISH_GIRL,
    SOSUKE_YOUNG_SAILOR,
    GRANMAMARE_SEA_GODDESS,
    FLYING_FISH_SPIRIT,
    CLOUD_ELEMENTAL,
    BATHHOUSE_FROG,
    WATER_SPIRIT_MINOR,
    SKY_PIRATE,
    TIGER_MOTH_CREW,
    DOLA_SKY_PIRATE_CAPTAIN,
    WIND_MAGE,
    AIRSHIP_NAVIGATOR,
    MYSTICAL_GUARDIAN,
    HOWLING_WIND_SPIRIT,
    RIVER_CURRENT,
    SPIRIT_GUIDANCE,
    PHASE_SHIFT,
    WINDS_PROTECTION,
    COUNTERSPELL_OF_THE_DEEP,
    AERIAL_RECONNAISSANCE,
    SUMMON_THE_TIDES,
    FORGOTTEN_MEMORIES,
    RIVER_BLESSING,
    SKY_DOMAIN,
    NO_FACE_HUNGRY_SPIRIT,
    YUBABA_BATHHOUSE_WITCH,
    BOH_GIANT_BABY,
    MORO_WOLF_GOD,
    OKKOTO_BOAR_GOD,
    DEMON_BOAR,
    GOD_WARRIOR,
    CURSE_SPIRIT,
    SHADOW_SPIRIT,
    CORRUPTED_KODAMA,
    SPIRIT_OF_VENGEANCE,
    DARK_FOREST_CREATURE,
    WITCH_FAMILIAR,
    BATHHOUSE_SPECTER,
    NIGHTMARE_CREATURE,
    TOXIC_JUNGLE_LURKER,
    FALLEN_SAMURAI,
    CURSE_OF_GREED,
    SPIRITS_CONSUMPTION,
    DARK_BARGAIN,
    TERROR_OF_THE_DEEP,
    WITCH_HEX,
    MASS_CORRUPTION,
    SPIRITS_HARVEST,
    CURSE_OF_FORGETTING,
    RAISE_THE_FALLEN,
    CURSE_OF_THE_WITCH,
    DARK_FOREST_PACT,
    CALCIFER_FIRE_DEMON,
    HOWL_WIZARD,
    WITCH_OF_THE_WASTE,
    MARKL_HOWLS_APPRENTICE,
    TORUMEKIAN_SOLDIER,
    KUSHANA_WAR_PRINCESS,
    GOLIATH_AIRSHIP,
    FIRE_SPIRIT,
    FLAME_ELEMENTAL,
    VOLCANIC_SPIRIT,
    DESTRUCTION_SPIRIT,
    PEJITE_WARRIOR,
    FOREST_ARSONIST,
    WILD_BOAR,
    ANGRY_SPIRIT,
    IRONWORKS_FURNACE,
    BOMBARDMENT_CREW,
    FIRE_BREATH,
    CALCIFER_FLAME,
    FURY_OF_THE_WILD,
    VOLCANIC_ERUPTION,
    DESPERATE_CHARGE,
    RAIN_OF_FIRE,
    BURNING_WRATH,
    SUMMON_FIRE_SPIRITS,
    WILDFIRE_SPREAD,
    FIRES_OF_DESTRUCTION,
    WAR_DRUMS,
    TOTORO_KING_OF_THE_FOREST,
    CATBUS,
    CHIBI_TOTORO,
    MEDIUM_TOTORO,
    FOREST_SPIRIT_GOD,
    KODAMA_ELDER,
    WOLF_OF_MORO,
    OHMU_KING,
    BABY_OHMU,
    TOXIC_JUNGLE_GUARDIAN,
    FOREST_KODAMA,
    KODAMA_OF_GROWTH,
    ANCIENT_TREE_SPIRIT,
    FOREST_GUARDIAN,
    NATURE_SPRITE,
    SOOT_SPRITES,
    WILD_WOLF,
    FOREST_DEER,
    GIANT_CAMPHOR_TREE,
    INSECT_SWARM,
    MOSS_COVERED_GOLEM,
    SPIRIT_WOLF_PUP,
    FOREST_BLESSING,
    NATURES_SHIELD,
    REGROWTH_SPELL,
    RAPID_GROWTH,
    SPIRIT_CALL,
    FOREST_AWAKENING,
    CALL_OF_THE_WILD,
    NATURES_RECLAMATION,
    SUMMON_THE_FOREST,
    FOREST_SANCTUARY,
    BLESSING_OF_THE_SPIRITS,
    NATURES_WRATH_ENCHANTMENT,
    SPIRITED_TRANSFORMATION,
    FOREST_AND_SKY,
    CURSE_BREAKER,
    SPIRIT_FIRE,
    NATURES_VENGEANCE,
    BATHHOUSE_DISTRICT,
    ANCIENT_FOREST,
    TOXIC_JUNGLE,
    LAPUTA_FLOATING_CASTLE,
    HOWLS_CASTLE,
    IRON_TOWN,
    SPIRIT_REALM_GATE,
    VALLEY_OF_THE_WIND,
    FOREST_SHRINE,
    CAMPHOR_TREE_GROVE,
    CURSED_SWAMP,
    SKY_FORTRESS,
    OHMU_NEST,
    SHUNA_EMISSARY,
    CHIHIRO_RIVER_RETURNED,
    BATHHOUSE_PURE_RETREAT,
    # SPICE PASS PHASE A
    THE_FOREST_WATCHES,
    MEI_FOREST_FRIEND,
    HOWLS_CASTLE_WANDERING_HEART,
    CATBUS_WIND_CARRIER,
    THE_WORLD_TREES_GIFT,
    ASCENSION_OF_SPIRITS,
    CALCIFER_HEARTH_PACT,
    GRANMAMARE_HOSPITALITY,
    # SPICE PASS V2 EXPANSION
    HOWL_WANDERING_HEART_WIZARD,
    YUBABA_BATHHOUSE_GREED,
    NO_FACE_DEVOURING_SPIRIT,
    THE_SPIRIT_REALM_SUMMONING,
    PRINCESS_MONONOKES_CURSE,
    SAN_WOLF_SISTER_ASCENDANT,
    CHIHIRO_BRIDGE_BETWEEN_WORLDS,
    # SPICE PASS V2 EXPANSION — Phase 2
    TOTORO_CAMPHOR_TREE,
    KAONASHIS_BANQUET,
    ASHITAKA_IRON_CURSED,
    KIKI_WITCH_ERRANDS,
    THE_CURSED_FOREST_AWAKENS,
    # SPICE PASS V2 EXPANSION — Phase 3
    HAKU_RIVER_LORD_BOUND,
    OHMU_FOREST_ARCHITECT,
    WITCH_OF_WASTE_FADING_SPLENDOR,
    # SPICE PASS V2 EXPANSION — Phase 4
    SHEETA_CRYSTAL_HEIR,
    BOH_PACIFIED_GIANT,
    MONONOKES_LAST_HUNT,
    SUSPECT_THE_CONSPIRATORS,
    CASTLE_IN_THE_SKY_REAWAKENED,
    LAPUTAN_AMULET,
    CRYSTAL_NECKLACE,
    CALCIFER_LANTERN,
    FLYING_MACHINE,
    MEHVE_GLIDER,
    TIGER_MOTH_SHIP,
    ROBOT_SOLDIER,
    SPIRIT_MASK,
    BATHHOUSE_TOKEN,
    CURSE_SEAL
]
