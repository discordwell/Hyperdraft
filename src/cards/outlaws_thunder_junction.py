"""
Outlaws of Thunder Junction (OTJ) Card Implementations

Set released April 2024. ~250 cards.
Features mechanics: Outlaw, Plot, Crimes, Spree, Saddle (Mount)
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger, make_end_step_trigger,
    make_life_gain_trigger, make_life_loss_trigger, creatures_you_control,
    other_creatures_with_subtype, all_opponents
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create equipment card definitions."""
    base_subtypes = {"Equipment"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            mana_cost=mana_cost
        ),
        text=f"{text}\nEquip {equip_cost}",
        setup_interceptors=setup_interceptors
    )


def make_mount(name: str, power: int, toughness: int, mana_cost: str, colors: set, text: str, saddle: int,
               subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create Mount creature card definitions with Saddle."""
    base_subtypes = {"Mount"}
    if subtypes:
        base_subtypes.update(subtypes)
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.CREATURE},
            subtypes=base_subtypes,
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=f"{text}\nSaddle {saddle}",
        setup_interceptors=setup_interceptors
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
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
        text=text
    )


# =============================================================================
# OTJ KEYWORD MECHANICS
# =============================================================================

# OUTLAW TYPES: Assassin, Mercenary, Pirate, Rogue, Warlock
OUTLAW_SUBTYPES = {"Assassin", "Mercenary", "Pirate", "Rogue", "Warlock"}


def is_outlaw(obj: GameObject) -> bool:
    """Check if a creature is an Outlaw (Assassin, Mercenary, Pirate, Rogue, or Warlock)."""
    return bool(obj.characteristics.subtypes.intersection(OUTLAW_SUBTYPES))


def outlaw_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Outlaw creatures you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                is_outlaw(target) and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def other_outlaws_you_control(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for other Outlaw creatures you control."""
    def filter_fn(target: GameObject, state: GameState) -> bool:
        return (target.id != source.id and
                target.controller == source.controller and
                CardType.CREATURE in target.characteristics.types and
                is_outlaw(target) and
                target.zone == ZoneType.BATTLEFIELD)
    return filter_fn


def make_plot_ability(source_obj: GameObject, plot_cost: str) -> Interceptor:
    """
    Plot - Pay plot cost to exile this card face up. Cast it later for free.
    Note: Full implementation requires exile zone and delayed cast tracking.
    """
    def plot_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'plot')

    def plot_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.ZONE_CHANGE,
                payload={
                    'object_id': source_obj.id,
                    'to_zone_type': ZoneType.EXILE,
                    'plotted': True,
                    'plot_cost': plot_cost
                },
                source=source_obj.id
            )]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=plot_filter,
        handler=plot_handler,
        duration='while_in_hand'
    )


def make_crime_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Crime trigger - Whenever you commit a crime (target opponent or their stuff).
    """
    def crime_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CRIME_COMMITTED:
            return False
        return event.payload.get('criminal') == source_obj.controller

    def crime_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=crime_filter,
        handler=crime_handler,
        duration='while_on_battlefield'
    )


def make_saddle_ability(source_obj: GameObject, saddle_value: int) -> Interceptor:
    """
    Saddle N - Tap creatures with total power N or greater to make this a creature.
    Note: Full implementation requires tracking saddled state.
    """
    def saddle_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'saddle')

    def saddle_handler(event: Event, state: GameState) -> InterceptorResult:
        total_power = event.payload.get('tapped_power', 0)
        if total_power >= saddle_value:
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.STATE_CHANGE,
                    payload={'object_id': source_obj.id, 'saddled': True, 'duration': 'end_of_turn'},
                    source=source_obj.id
                )]
            )
        return InterceptorResult(action=InterceptorAction.PASS)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=saddle_filter,
        handler=saddle_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# WHITE CARDS - LAW, BOUNTY HUNTERS, JUSTICE
# =============================================================================

# --- Legendary Creatures ---

def kellan_daring_traveler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike. Whenever you commit a crime, put a +1/+1 counter on Kellan."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_crime_trigger(obj, crime_effect)]

KELLAN_DARING_TRAVELER = make_creature(
    name="Kellan, Daring Traveler",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Faerie", "Rogue"},
    supertypes={"Legendary"},
    text="Double strike. Whenever you commit a crime, put a +1/+1 counter on Kellan, Daring Traveler.",
    setup_interceptors=kellan_daring_traveler_setup
)


def sheriff_of_safeton_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. Other creatures you control have vigilance."""
    return [make_keyword_grant(obj, ['vigilance'], other_creatures_you_control(obj))]

SHERIFF_OF_SAFETON = make_creature(
    name="Sheriff of Safeton",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance. Other creatures you control have vigilance.",
    setup_interceptors=sheriff_of_safeton_setup
)


def wylie_duke_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Create two 1/1 white Mercenary tokens"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Mercenary', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Mercenary'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Mercenary', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Mercenary'}}
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

WYLIE_DUKE = make_creature(
    name="Wylie Duke, Atiin Hero",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="When Wylie Duke, Atiin Hero enters, create two 1/1 white Human Mercenary creature tokens.",
    setup_interceptors=wylie_duke_setup
)


# --- Regular Creatures ---

def frontier_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Gain 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

FRONTIER_SEEKER = make_creature(
    name="Frontier Seeker",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Frontier Seeker enters, you gain 3 life.",
    setup_interceptors=frontier_seeker_setup
)


PRAIRIE_SENTINEL = make_creature(
    name="Prairie Sentinel",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. First strike as long as it's your turn."
)


def wanted_griffin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. When this attacks, create a 1/1 Mercenary token"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Mercenary', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE}, 'subtypes': {'Human', 'Mercenary'}}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

WANTED_GRIFFIN = make_creature(
    name="Wanted Griffin",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Griffin"},
    text="Flying. Whenever Wanted Griffin attacks, create a 1/1 white Human Mercenary creature token.",
    setup_interceptors=wanted_griffin_setup
)


DUSTY_VANGUARD = make_creature(
    name="Dusty Vanguard",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="First strike"
)


def canyon_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Mounts get +1/+1"""
    return make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Mount"))

CANYON_GUIDE = make_creature(
    name="Canyon Guide",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="Other Mount creatures you control get +1/+1.",
    setup_interceptors=canyon_guide_setup
)


BOUNTY_AGENT = make_creature(
    name="Bounty Agent",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Mercenary"},
    text="Lifelink. {T}, Sacrifice Bounty Agent: Destroy target legendary creature or legendary enchantment."
)


LAWBRINGER_CAVALRY = make_creature(
    name="Lawbringer Cavalry",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance. Whenever Lawbringer Cavalry attacks, tap target creature defending player controls."
)


# --- Mounts ---

SANDSTEPPE_COURSER = make_mount(
    name="Sandsteppe Courser",
    power=3, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="First strike. Whenever this creature attacks while saddled, put a +1/+1 counter on it.",
    saddle=2,
    subtypes={"Horse"}
)


ARMORED_ARMADILLO = make_mount(
    name="Armored Armadillo",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Vigilance. As long as this creature is saddled, it has indestructible.",
    saddle=1,
    subtypes={"Armadillo"}
)


DUSTBRINGER_PEGASUS = make_mount(
    name="Dustbringer Pegasus",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Flying. Whenever this creature becomes saddled, you gain 2 life.",
    saddle=2,
    subtypes={"Pegasus"}
)


# --- Instants and Sorceries ---

SHOWDOWN_OF_THE_SKALDS = make_instant(
    name="Showdown of the Skalds",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Exile the top four cards of your library. Until end of turn, you may play those cards. Whenever you play one of those cards this turn, put a +1/+1 counter on target creature you control."
)


HOLY_COW = make_instant(
    name="Holy Cow",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Flash. When Holy Cow enters, you gain 2 life and scry 1."
)


SPRING_INTO_ACTION = make_sorcery(
    name="Spring into Action",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Human Mercenary creature tokens. Target creature you control gets +2/+2 until end of turn."
)


RUSTLERS_ROUNDUP = make_sorcery(
    name="Rustler's Roundup",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Return all creatures with mana value 3 or less from your graveyard to the battlefield."
)


# =============================================================================
# BLUE CARDS - TRICKERY, INFORMATION, SCHEMING
# =============================================================================

# --- Legendary Creatures ---

def oko_the_ringleader_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Create a 3/3 green Elk token. Whenever you commit a crime, draw a card."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Elk', 'power': 3, 'toughness': 3, 'colors': {Color.GREEN}, 'subtypes': {'Elk'}}
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_crime_trigger(obj, crime_effect))

    return interceptors

OKO_THE_RINGLEADER = make_creature(
    name="Oko, the Ringleader",
    power=3, toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    supertypes={"Legendary"},
    text="When Oko enters, create a 3/3 green Elk creature token. Whenever you commit a crime, draw a card.",
    setup_interceptors=oko_the_ringleader_setup
)


def kaervek_the_spiteful_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash. Whenever an opponent casts a spell, they lose 1 life."""
    def cast_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.CAST:
            return False
        return event.payload.get('caster') != source.controller

    def cast_effect(event: Event, state: GameState) -> list[Event]:
        caster = event.payload.get('caster')
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': caster, 'amount': -1}, source=obj.id)]

    return [make_spell_cast_trigger(obj, cast_effect, controller_only=False)]

ERIETTE_THE_BEGUILER = make_creature(
    name="Eriette, the Beguiler",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Flash. Whenever an opponent casts a spell, they lose 1 life.",
    setup_interceptors=kaervek_the_spiteful_setup
)


def the_gitrog_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Hexproof. At the beginning of your end step, if you committed a crime this turn, draw a card."""
    def end_step_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    return [make_end_step_trigger(obj, end_step_effect)]

SLICKSHOT_SHOWOFF = make_creature(
    name="Slickshot Show-Off",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Bird", "Rogue"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever you cast a noncreature spell, Slickshot Show-Off gets +2/+0 until end of turn.",
    setup_interceptors=the_gitrog_setup
)


# --- Regular Creatures ---

def sneaky_snacker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Whenever you commit a crime, create a Food token."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Food', 'types': {CardType.ARTIFACT}, 'subtypes': {'Food'}}
        }, source=obj.id)]
    return [make_crime_trigger(obj, crime_effect)]

SNEAKY_SNACKER = make_creature(
    name="Sneaky Snacker",
    power=1, toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Faerie", "Rogue"},
    text="Flying. Whenever you commit a crime, create a Food token.",
    setup_interceptors=sneaky_snacker_setup
)


NIMBLE_OUTLAW = make_creature(
    name="Nimble Outlaw",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Rogue"},
    text="Flash. When Nimble Outlaw enters, tap target creature an opponent controls."
)


def thunder_lasso_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Draw two cards, then discard a card"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

TRICKSTER_ROGUE = make_creature(
    name="Trickster Rogue",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When Trickster Rogue enters, draw two cards, then discard a card.",
    setup_interceptors=thunder_lasso_setup
)


DESERT_MIRAGE = make_creature(
    name="Desert Mirage",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Illusion"},
    text="Flash. Hexproof. When Desert Mirage becomes the target of a spell or ability, sacrifice it."
)


CANYON_CRAB = make_creature(
    name="Canyon Crab",
    power=0, toughness=5,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Crab"},
    text="Defender. {3}{U}: Canyon Crab can attack this turn as though it didn't have defender and assigns combat damage equal to its toughness."
)


# --- Instants and Sorceries ---

TRICK_SHOT = make_instant(
    name="Trick Shot",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}."
)


THREE_STEPS_AHEAD = make_instant(
    name="Three Steps Ahead",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Choose one - Counter target spell; or create a token copy of target artifact or creature; or draw two cards."
)


PHANTOM_INTERFERENCE = make_instant(
    name="Phantom Interference",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Its controller may pay {3}. If they do, they draw a card."
)


LOAN_SHARK = make_sorcery(
    name="Loan Shark",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


# =============================================================================
# BLACK CARDS - OUTLAWS, DEATH, VILLAINY
# =============================================================================

# --- Legendary Creatures ---

def tinybones_the_pickpocket_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever Tinybones deals combat damage to a player, you may cast a spell from that player's graveyard."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        # Simplified - just exile top card of opponent's library
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

TINYBONES_THE_PICKPOCKET = make_creature(
    name="Tinybones, the Pickpocket",
    power=1, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Rogue"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Tinybones deals combat damage to a player, you may cast a nonland card from that player's graveyard, and mana of any type can be spent to cast it.",
    setup_interceptors=tinybones_the_pickpocket_setup
)


def rakdos_the_muscle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, trample. Whenever you commit a crime, each opponent loses 3 life."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -3}, source=obj.id))
        return events
    return [make_crime_trigger(obj, crime_effect)]

RAKDOS_THE_MUSCLE = make_creature(
    name="Rakdos, the Muscle",
    power=5, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, trample. Whenever you commit a crime, each opponent loses 3 life.",
    setup_interceptors=rakdos_the_muscle_setup
)


def vraska_the_silencer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever a creature dealt damage by Vraska this turn dies, create a Treasure."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect)]

VRASKA_THE_SILENCER = make_creature(
    name="Vraska, the Silencer",
    power=3, toughness=3,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Gorgon", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever a creature dealt damage by Vraska this turn dies, create a Treasure token.",
    setup_interceptors=vraska_the_silencer_setup
)


def gisa_the_hellraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, create two 2/2 black Zombie tokens."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Zombie', 'power': 2, 'toughness': 2, 'colors': {Color.BLACK}, 'subtypes': {'Zombie'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Zombie', 'power': 2, 'toughness': 2, 'colors': {Color.BLACK}, 'subtypes': {'Zombie'}}
            }, source=obj.id)
        ]
    return [make_crime_trigger(obj, crime_effect)]

GISA_THE_HELLRAISER = make_creature(
    name="Gisa, the Hellraiser",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Ward - Pay 3 life. Whenever you commit a crime, create two 2/2 black Zombie creature tokens.",
    setup_interceptors=gisa_the_hellraiser_setup
)


# --- Regular Creatures ---

def backstage_bandit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this dies, each opponent loses 2 life"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for p_id in all_opponents(obj, state):
            events.append(Event(type=EventType.LIFE_CHANGE, payload={'player': p_id, 'amount': -2}, source=obj.id))
        return events
    return [make_death_trigger(obj, death_effect)]

BACKSTAGE_BANDIT = make_creature(
    name="Backstage Bandit",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Backstage Bandit dies, each opponent loses 2 life.",
    setup_interceptors=backstage_bandit_setup
)


GRAVEDIGGER_GHOUL = make_creature(
    name="Gravedigger Ghoul",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Gravedigger Ghoul enters, exile up to two target cards from graveyards."
)


VADMIR_NEW_BLOOD = make_creature(
    name="Vadmir, New Blood",
    power=2, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Rogue"},
    text="Flying. Whenever you commit a crime, target creature gets -2/-2 until end of turn."
)


SNAKE_OIL_PEDDLER = make_creature(
    name="Snake Oil Peddler",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Snake Oil Peddler enters, create a Treasure token and you lose 1 life."
)


def dark_rider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. Other Outlaws get +1/+0"""
    return make_static_pt_boost(obj, 1, 0, other_outlaws_you_control(obj))

DARK_RIDER = make_creature(
    name="Dark Rider",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace. Other Outlaw creatures you control get +1/+0.",
    setup_interceptors=dark_rider_setup
)


CORRUPTED_SHERIFF = make_creature(
    name="Corrupted Sheriff",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Lifelink. Whenever Corrupted Sheriff deals combat damage to a player, that player discards a card."
)


# --- Instants and Sorceries ---

MAKE_YOUR_OWN_LUCK = make_sorcery(
    name="Make Your Own Luck",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Each player sacrifices two creatures. Create a Treasure token for each creature that died this way."
)


RUSH_OF_DREAD = make_sorcery(
    name="Rush of Dread",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Spree. + {B} - Target player discards two cards. + {2} - Target player sacrifices a creature. + {2} - Target player loses 4 life."
)


MURDER = make_instant(
    name="Murder",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature."
)


FINAL_SHOWDOWN = make_instant(
    name="Final Showdown",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If that creature would die this turn, exile it instead."
)


# =============================================================================
# RED CARDS - CHAOS, EXPLOSIONS, OUTLAWS
# =============================================================================

# --- Legendary Creatures ---

def magda_the_hoardmaster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, create a Treasure. Sacrifice five Treasures: Search for a Dragon or artifact."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_crime_trigger(obj, crime_effect)]

MAGDA_THE_HOARDMASTER = make_creature(
    name="Magda, the Hoardmaster",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Mercenary"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, create a Treasure token. Sacrifice five Treasures: Search your library for a Dragon or Artifact card, put it onto the battlefield, then shuffle.",
    setup_interceptors=magda_the_hoardmaster_setup
)


def vial_smasher_the_gleeful_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace, haste. Whenever you cast your first spell each turn, deal damage to opponent equal to its mana value."""
    def cast_effect(event: Event, state: GameState) -> list[Event]:
        mv = event.payload.get('mana_value', 0)
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(type=EventType.DAMAGE, payload={'target': opponents[0], 'amount': mv, 'source': obj.id}, source=obj.id)]
        return []
    return [make_spell_cast_trigger(obj, cast_effect)]

VIAL_SMASHER = make_creature(
    name="Vial Smasher, Gleeful Grenadier",
    power=3, toughness=2,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Goblin", "Mercenary"},
    supertypes={"Legendary"},
    text="Menace, haste. Whenever you cast your first spell each turn, Vial Smasher deals damage equal to that spell's mana value to target opponent.",
    setup_interceptors=vial_smasher_the_gleeful_setup
)


def hellspur_posse_boss_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Other creatures you control have haste."""
    return [make_keyword_grant(obj, ['haste'], other_creatures_you_control(obj))]

HELLSPUR_POSSE_BOSS = make_creature(
    name="Hellspur Posse Boss",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Devil", "Rogue"},
    supertypes={"Legendary"},
    text="Haste. Other creatures you control have haste.",
    setup_interceptors=hellspur_posse_boss_setup
)


# --- Regular Creatures ---

def goblin_tomb_raider_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. When this attacks, it gets +2/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': 'power_boost', 'amount': 2, 'duration': 'end_of_turn'},
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

GOBLIN_TOMB_RAIDER = make_creature(
    name="Goblin Tomb Raider",
    power=1, toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Haste. Whenever Goblin Tomb Raider attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=goblin_tomb_raider_setup
)


RECKLESS_LACKEY = make_creature(
    name="Reckless Lackey",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Mercenary"},
    text="Haste. Sacrifice Reckless Lackey: Add {R}{R}."
)


OUTLAW_STITCHER = make_creature(
    name="Outlaw Stitcher",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Artificer"},
    text="When Outlaw Stitcher enters, create a 1/1 colorless Construct artifact creature token."
)


THUNDER_JUNCTION_PYROMANCER = make_creature(
    name="Thunder Junction Pyromancer",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Shaman"},
    text="When Thunder Junction Pyromancer enters, it deals 2 damage to any target."
)


def dynamite_miner_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this dies, deal 2 damage to any target"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        # Would need targeting - simplified to dealing damage to opponent
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(type=EventType.DAMAGE, payload={'target': opponents[0], 'amount': 2, 'source': obj.id}, source=obj.id)]
        return []
    return [make_death_trigger(obj, death_effect)]

DYNAMITE_MINER = make_creature(
    name="Dynamite Miner",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Mercenary"},
    text="When Dynamite Miner dies, it deals 2 damage to any target.",
    setup_interceptors=dynamite_miner_setup
)


RAILWAY_BRAWLER = make_creature(
    name="Railway Brawler",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Mercenary"},
    text="Trample. Railway Brawler attacks each combat if able."
)


# --- Mounts ---

TERROR_OF_THE_PEAKS = make_mount(
    name="Terror of the Peaks",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Flying. When a creature enters under your control, Terror of the Peaks deals damage equal to that creature's power to any target.",
    saddle=3,
    subtypes={"Dragon"}
)


HELLSPUR_BRUTE = make_mount(
    name="Hellspur Brute",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Haste. When this creature attacks while saddled, it deals 2 damage to each opponent.",
    saddle=2,
    subtypes={"Devil", "Horse"}
)


# --- Instants and Sorceries ---

LIGHTNING_HELIX = make_instant(
    name="Lightning Helix",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Lightning Helix deals 3 damage to any target and you gain 3 life."
)


HIGHWAY_ROBBERY = make_sorcery(
    name="Highway Robbery",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Gain control of target creature with mana value 3 or less until end of turn. Untap it. It gains haste until end of turn."
)


EXPLOSIVE_ENTRY = make_instant(
    name="Explosive Entry",
    mana_cost="{R}",
    colors={Color.RED},
    text="Destroy target artifact. Explosive Entry deals 2 damage to that artifact's controller."
)


SHOWDOWN_AT_NOON = make_sorcery(
    name="Showdown at Noon",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Choose target creature you control and target creature an opponent controls. Each of those creatures deals damage equal to its power to the other."
)


CAUGHT_IN_THE_CROSSFIRE = make_instant(
    name="Caught in the Crossfire",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Caught in the Crossfire deals 2 damage to each creature."
)


# =============================================================================
# GREEN CARDS - NATURE, GROWTH, BEASTS
# =============================================================================

# --- Legendary Creatures ---

def bonny_pall_clearcutter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. When enters, create a 4/4 green Elemental token with reach."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Elemental', 'power': 4, 'toughness': 4, 'colors': {Color.GREEN}, 'subtypes': {'Elemental'}, 'keywords': ['reach']}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

BONNY_PALL_CLEARCUTTER = make_creature(
    name="Bonny Pall, Clearcutter",
    power=5, toughness=5,
    mana_cost="{4}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Giant", "Scout"},
    supertypes={"Legendary"},
    text="Trample. When Bonny Pall enters, create a 4/4 green Elemental creature token with reach.",
    setup_interceptors=bonny_pall_clearcutter_setup
)


def selvala_eager_trailblazer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Vigilance. Tap: Add mana equal to greatest power among creatures you control."""
    return []  # Activated ability handled separately

SELVALA_EAGER_TRAILBLAZER = make_creature(
    name="Selvala, Eager Trailblazer",
    power=3, toughness=4,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    supertypes={"Legendary"},
    text="Vigilance. {T}: Choose a color. Add an amount of mana of that color equal to the greatest power among creatures you control.",
    setup_interceptors=selvala_eager_trailblazer_setup
)


def bristly_bill_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Landfall - Whenever a land enters, put a +1/+1 counter on target creature."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        obj_id = event.payload.get('object_id')
        land = state.objects.get(obj_id)
        return land and CardType.LAND in land.characteristics.types and land.controller == source.controller

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        # Would target a creature - simplified to put on self
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: landfall_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=landfall_effect(e, s)),
        duration='while_on_battlefield'
    )]

BRISTLY_BILL = make_creature(
    name="Bristly Bill, Spine Sower",
    power=2, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Druid"},
    supertypes={"Legendary"},
    text="Landfall - Whenever a land enters under your control, put a +1/+1 counter on target creature you control.",
    setup_interceptors=bristly_bill_setup
)


# --- Regular Creatures ---

def cactus_serpent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. When enters, search library for basic land, put into hand."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        # Search for land - placeholder
        return []
    return [make_etb_trigger(obj, etb_effect)]

CACTUS_SERPENT = make_creature(
    name="Cactus Serpent",
    power=3, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Serpent"},
    text="Reach. When Cactus Serpent enters, you may search your library for a basic land card, reveal it, put it into your hand, then shuffle.",
    setup_interceptors=cactus_serpent_setup
)


FRONTIER_TRAMPLER = make_creature(
    name="Frontier Trampler",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Elephant"},
    text="Trample"
)


def mesa_cavalier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this attacks, other attacking creatures get +1/+1"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would buff other attackers
    return [make_attack_trigger(obj, attack_effect)]

MESA_CAVALIER = make_creature(
    name="Mesa Cavalier",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Warrior"},
    text="Trample. Whenever Mesa Cavalier attacks, other attacking creatures you control get +1/+1 until end of turn.",
    setup_interceptors=mesa_cavalier_setup
)


GOLD_RUSH_PROSPECTOR = make_creature(
    name="Gold Rush Prospector",
    power=2, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When Gold Rush Prospector enters, create a Treasure token. {2}, Sacrifice a Treasure: Draw a card."
)


TOWERING_BALOTHS = make_creature(
    name="Towering Baloths",
    power=6, toughness=5,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Hexproof from instants."
)


RATTLEBACK_APOTHECARY = make_creature(
    name="Rattleback Apothecary",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Snake", "Druid"},
    text="Deathtouch. {1}{G}, {T}: You gain 2 life."
)


# --- Mounts ---

RAMBLING_POSSUM = make_mount(
    name="Rambling Possum",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Vigilance. As long as this creature is saddled, it has trample and indestructible.",
    saddle=4,
    subtypes={"Possum", "Beast"}
)


OMENPORT_VIGILANTE = make_mount(
    name="Omenport Vigilante",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="When this creature attacks while saddled, untap all lands you control.",
    saddle=2,
    subtypes={"Horse"}
)


# --- Instants and Sorceries ---

RETURN_THE_FAVOR = make_instant(
    name="Return the Favor",
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    text="Copy target activated or triggered ability you control. You may choose new targets for the copy."
)


BITE_DOWN = make_instant(
    name="Bite Down",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker you don't control."
)


OUTCASTER_GREENBLADE = make_sorcery(
    name="Outcaster Greenblade",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle. You gain 4 life."
)


CULTIVATE = make_sorcery(
    name="Cultivate",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle."
)


# =============================================================================
# MULTICOLOR - LEGENDARY OUTLAWS AND KEY CARDS
# =============================================================================

def fblthp_lost_on_the_range_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, draw a card. Whenever you commit a crime, draw another."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_crime_trigger(obj, crime_effect))

    return interceptors

FBLTHP_LOST_ON_THE_RANGE = make_creature(
    name="Fblthp, Lost on the Range",
    power=1, toughness=1,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Homunculus"},
    supertypes={"Legendary"},
    text="When Fblthp enters, draw a card. Whenever you commit a crime, draw a card.",
    setup_interceptors=fblthp_lost_on_the_range_setup
)


def obeka_splitter_of_seconds_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. Whenever you cast a spell from exile, create a copy."""
    return []  # Complex trigger based on exile casting

OBEKA_SPLITTER_OF_SECONDS = make_creature(
    name="Obeka, Splitter of Seconds",
    power=2, toughness=5,
    mana_cost="{1}{U}{B}{R}",
    colors={Color.BLUE, Color.BLACK, Color.RED},
    subtypes={"Ogre", "Warlock"},
    supertypes={"Legendary"},
    text="Menace. Whenever you cast a spell from exile, copy it. You may choose new targets for the copy.",
    setup_interceptors=obeka_splitter_of_seconds_setup
)


def satoru_the_infiltrator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Menace. Whenever a creature you control deals combat damage to a player, draw a card and discard a card."""
    def damage_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if not event.payload.get('is_combat'):
            return False
        attacker_id = event.payload.get('source')
        attacker = state.objects.get(attacker_id)
        return (attacker and attacker.controller == source.controller and
                CardType.CREATURE in attacker.characteristics.types)

    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id),
            Event(type=EventType.DISCARD, payload={'player': obj.controller, 'amount': 1}, source=obj.id)
        ]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: damage_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=damage_effect(e, s)),
        duration='while_on_battlefield'
    )]

SATORU_THE_INFILTRATOR = make_creature(
    name="Satoru, the Infiltrator",
    power=2, toughness=4,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace. Whenever a creature you control deals combat damage to a player, draw a card, then discard a card.",
    setup_interceptors=satoru_the_infiltrator_setup
)


def izzet_inventor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prowess (not implemented). When this dies, draw two cards."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]
    return [make_death_trigger(obj, death_effect)]

IZZET_INVENTOR = make_creature(
    name="Izzet Inventor",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Goblin", "Artificer"},
    text="Prowess. When Izzet Inventor dies, draw two cards.",
    setup_interceptors=izzet_inventor_setup
)


def dust_animus_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, vigilance. Whenever a land enters under your control, put a +1/+1 counter on this."""
    def landfall_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        obj_id = event.payload.get('object_id')
        land = state.objects.get(obj_id)
        return land and CardType.LAND in land.characteristics.types and land.controller == source.controller

    def landfall_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: landfall_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.REACT, new_events=landfall_effect(e, s)),
        duration='while_on_battlefield'
    )]

DUST_ANIMUS = make_creature(
    name="Dust Animus",
    power=4, toughness=4,
    mana_cost="{2}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Elemental"},
    text="Flying, vigilance. Landfall - Whenever a land enters under your control, put a +1/+1 counter on Dust Animus.",
    setup_interceptors=dust_animus_setup
)


def seraph_of_new_capenna_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink. When this attacks, other attacking creatures get +1/+1."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would buff other attackers
    return [make_attack_trigger(obj, attack_effect)]

SERAPH_OF_NEW_CAPENNA = make_creature(
    name="Seraph of New Capenna",
    power=4, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, lifelink. Whenever Seraph of New Capenna attacks, other attacking creatures you control get +1/+1 until end of turn.",
    setup_interceptors=seraph_of_new_capenna_setup
)


# =============================================================================
# ARTIFACTS AND EQUIPMENT
# =============================================================================

LASSO_OF_CLARITY = make_equipment(
    name="Lasso of Clarity",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has first strike. When Lasso of Clarity enters, you may attach it to target creature you control."
)


OUTLAWS_FURY = make_equipment(
    name="Outlaw's Fury",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +2/+0 and has menace. Whenever equipped creature attacks, create a Treasure token."
)


QUICK_DRAW_HOLSTER = make_equipment(
    name="Quick-Draw Holster",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1 and has haste. Whenever equipped creature deals combat damage to a player, untap it."
)


STERLING_KEYKEEPER = make_artifact(
    name="Sterling Keykeeper",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. {2}, {T}: Untap target permanent. Activate only as a sorcery."
)


TREASURE_MAP = make_artifact(
    name="Treasure Map",
    mana_cost="{2}",
    text="{1}, {T}: Scry 1. Put a landmark counter on Treasure Map. If there are three or more landmark counters on it, remove them and transform Treasure Map."
)


WANTED_POSTER = make_artifact(
    name="Wanted Poster",
    mana_cost="{1}",
    text="When Wanted Poster enters, exile target creature an opponent controls until Wanted Poster leaves the battlefield. When it does, you create a Treasure token."
)


def cache_bandit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enters, create a Treasure. When this attacks, create another."""
    interceptors = []

    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    interceptors.append(make_etb_trigger(obj, etb_effect))

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    interceptors.append(make_attack_trigger(obj, attack_effect))

    return interceptors

CACHE_BANDIT = make_creature(
    name="Cache Bandit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="When Cache Bandit enters, create a Treasure token. Whenever Cache Bandit attacks, create a Treasure token.",
    setup_interceptors=cache_bandit_setup
)


LUCKY_CLOVER = make_artifact(
    name="Lucky Clover",
    mana_cost="{2}",
    text="Whenever you cast an Adventure instant or sorcery spell, copy it. You may choose new targets for the copy."
)


GOLDVEIN_PICK = make_equipment(
    name="Goldvein Pick",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, create a Treasure token."
)


# =============================================================================
# LANDS - DESERTS AND FRONTIER
# =============================================================================

CONDUIT_PYLONS = make_land(
    name="Conduit Pylons",
    text="{T}: Add {C}. {2}, {T}: Target creature gains flying until end of turn.",
    subtypes={"Desert"}
)


MIRAGE_MESA = make_land(
    name="Mirage Mesa",
    text="Mirage Mesa enters tapped. {T}: Add {R} or {W}.",
    subtypes={"Desert"}
)


FESTERING_GULCH = make_land(
    name="Festering Gulch",
    text="Festering Gulch enters tapped. {T}: Add {B} or {G}. When Festering Gulch enters, you may pay 2 life. If you do, it enters untapped instead.",
    subtypes={"Desert"}
)


JAGGED_BARRENS = make_land(
    name="Jagged Barrens",
    text="Jagged Barrens enters tapped. {T}: Add {R} or {B}. {T}, Sacrifice Jagged Barrens: Draw a card.",
    subtypes={"Desert"}
)


ABRADED_BLUFFS = make_land(
    name="Abraded Bluffs",
    text="Abraded Bluffs enters tapped unless you control two or more other lands. {T}: Add {G} or {W}.",
    subtypes={"Desert"}
)


THUNDERING_FALLS = make_land(
    name="Thundering Falls",
    text="Thundering Falls enters tapped. {T}: Add {U} or {G}. {4}, {T}: Draw a card.",
    subtypes={"Desert"}
)


BOOM_TOWN = make_land(
    name="Boom Town",
    text="{T}: Add {C}. {3}, {T}, Sacrifice Boom Town: Destroy target artifact or enchantment."
)


FRONTIER_BIVOUAC = make_land(
    name="Frontier Bivouac",
    text="Frontier Bivouac enters tapped. {T}: Add {G}, {U}, or {R}."
)


OUTLAWS_HIDEOUT = make_land(
    name="Outlaw's Hideout",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast Outlaw creature spells.",
    subtypes={"Desert"}
)


CACTUS_PRESERVE = make_land(
    name="Cactus Preserve",
    text="Cactus Preserve enters tapped. {T}: Add {G} or {R}. Whenever a creature enters under your control, you may pay {1}. If you do, put a +1/+1 counter on it.",
    subtypes={"Desert"}
)


# Basic lands with flavor
PLAINS_OTJ = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"},
    supertypes={"Basic"}
)

ISLAND_OTJ = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"},
    supertypes={"Basic"}
)

SWAMP_OTJ = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"},
    supertypes={"Basic"}
)

MOUNTAIN_OTJ = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"},
    supertypes={"Basic"}
)

FOREST_OTJ = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"},
    supertypes={"Basic"}
)


# =============================================================================
# ADDITIONAL CARDS - FILLING OUT THE SET
# =============================================================================

# More White cards
LARIAT_SPECIALIST = make_creature(
    name="Lariat Specialist",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="When Lariat Specialist enters, tap target creature an opponent controls."
)

FRONTIER_PRIEST = make_creature(
    name="Frontier Priest",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="{T}: You gain 1 life. {2}{W}, {T}: You gain 3 life."
)

SANDSTORM_SENTRY = make_creature(
    name="Sandstorm Sentry",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance, lifelink"
)


# More Blue cards
COYOTE_MESSENGER = make_creature(
    name="Coyote Messenger",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Coyote", "Scout"},
    text="Flying. When Coyote Messenger enters, scry 1."
)

MYSTIC_DESPERADO = make_creature(
    name="Mystic Desperado",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="Flash. When Mystic Desperado enters, draw a card, then discard a card."
)

DUST_DEVIL = make_creature(
    name="Dust Devil",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
    text="Flying. When Dust Devil deals combat damage to a player, return target nonland permanent to its owner's hand."
)


# More Black cards
SCORPION_CULTIST = make_creature(
    name="Scorpion Cultist",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Deathtouch. When Scorpion Cultist dies, target creature gets -2/-2 until end of turn."
)

NIGHTHAWK_ASSAILANT = make_creature(
    name="Nighthawk Assailant",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Vampire", "Assassin"},
    text="Flying, deathtouch, lifelink"
)

BOUNTY_BOARD_BROKER = make_creature(
    name="Bounty Board Broker",
    power=1, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Whenever you commit a crime, each opponent loses 1 life and you gain 1 life."
)


# More Red cards
BLAST_ZONE_MINER = make_creature(
    name="Blast-Zone Miner",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Artificer"},
    text="When Blast-Zone Miner enters, it deals 1 damage to each creature."
)

CANYON_RUNNER = make_creature(
    name="Canyon Runner",
    power=3, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Haste. Canyon Runner can't block."
)

OUTLAW_BRUTE = make_creature(
    name="Outlaw Brute",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Ogre", "Mercenary"},
    text="Trample, haste. Outlaw Brute attacks each combat if able."
)


# More Green cards
BRISTLEBACK_BEAST = make_creature(
    name="Bristleback Beast",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. When Bristleback Beast enters, create a 1/1 green Pest creature token with 'When this creature dies, you gain 1 life.'"
)

CANYON_LURKER = make_creature(
    name="Canyon Lurker",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Snake"},
    text="Reach, deathtouch"
)

WASTELAND_SCORPION = make_creature(
    name="Wasteland Scorpion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Scorpion"},
    text="Deathtouch"
)


# More multicolor/hybrid
RAKDOS_HEADLINER = make_creature(
    name="Rakdos Headliner",
    power=3, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Devil", "Performer"},
    text="Haste. At the beginning of your end step, sacrifice Rakdos Headliner unless you discard a card."
)

SELESNYA_SCOUT = make_creature(
    name="Selesnya Scout",
    power=2, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Scout"},
    text="Vigilance. When Selesnya Scout enters, search your library for a basic land card, reveal it, put it into your hand, then shuffle."
)

DIMIR_INFILTRATOR = make_creature(
    name="Dimir Infiltrator",
    power=1, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Dimir Infiltrator can't be blocked. Whenever Dimir Infiltrator deals combat damage to a player, that player discards a card."
)

GRUUL_WARCHIEF = make_creature(
    name="Gruul Warchief",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Cyclops", "Warrior"},
    text="Trample, haste. Other creatures you control have trample."
)


# Spree cards (modal)
OMINOUS_PARCEL = make_sorcery(
    name="Ominous Parcel",
    mana_cost="{1}",
    colors=set(),
    text="Spree. + {G} - Search your library for a basic land card, reveal it, put it into your hand, then shuffle. + {2} - Destroy target artifact."
)

SEIZE_THE_SPOILS = make_sorcery(
    name="Seize the Spoils",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Spree. + {1} - Discard a card, then draw two cards. + {R} - Create two Treasure tokens."
)

FELL_THE_LEADERS = make_sorcery(
    name="Fell the Leaders",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Spree. + {1} - Destroy target creature with the greatest power. + {B} - Each opponent loses 3 life. + {B} - You gain 3 life."
)


# Plot cards
def freestrider_commando_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB - Target creature gets +2/+2 and trample until end of turn. Plot {2}{G}."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would target a creature
    return [make_etb_trigger(obj, etb_effect)]

FREESTRIDER_COMMANDO = make_creature(
    name="Freestrider Commando",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Centaur", "Mercenary"},
    text="When Freestrider Commando enters, target creature you control gets +2/+2 and gains trample until end of turn. Plot {2}{G}",
    setup_interceptors=freestrider_commando_setup
)


def intimidation_campaign_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Each opponent discards a card. Plot {1}{B}."""
    return []

INTIMIDATION_CAMPAIGN = make_sorcery(
    name="Intimidation Campaign",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Each opponent discards a card. You draw a card. Plot {1}{B}"
)


# Additional instants and sorceries
TAKE_THE_FALL = make_instant(
    name="Take the Fall",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gets -4/-0 until end of turn. Untap it."
)

ARCANE_HEIST = make_sorcery(
    name="Arcane Heist",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Take control of target creature or artifact."
)

BETRAYAL_AT_GHOST_TOWN = make_instant(
    name="Betrayal at Ghost Town",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Destroy target creature if it was dealt damage this turn."
)

RAMPAGE_OF_THE_CLANS = make_sorcery(
    name="Rampage of the Clans",
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    text="Destroy all artifacts and enchantments. For each permanent destroyed this way, its controller creates a 3/3 green Centaur creature token."
)


# Final batch of creatures and cards
RATTLECLAW_MYSTIC = make_creature(
    name="Rattleclaw Mystic",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Shaman"},
    text="{T}: Add {G}, {U}, or {R}."
)

WANTED_SCOUNDRELS = make_creature(
    name="Wanted Scoundrels",
    power=4, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Wanted Scoundrels dies, target opponent creates two Treasure tokens."
)

TREASURE_NABBER = make_creature(
    name="Treasure Nabber",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Whenever an opponent taps an artifact for mana, gain control of that artifact until end of turn."
)

AVEN_INTERRUPTER = make_creature(
    name="Aven Interrupter",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Rogue"},
    text="Flash, flying. When Aven Interrupter enters, exile target spell. Its controller may cast it from exile. It costs {2} more to cast this way."
)


# =============================================================================
# ADDITIONAL CARDS - EXPANDING TO ~250
# =============================================================================

# More Legendary creatures
def annie_flash_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste, first strike. Whenever Annie deals combat damage, create a Treasure."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ANNIE_FLASH = make_creature(
    name="Annie Flash, the Veteran",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Mercenary"},
    supertypes={"Legendary"},
    text="Haste, first strike. Whenever Annie Flash deals combat damage to a player, create a Treasure token.",
    setup_interceptors=annie_flash_setup
)


def doc_aurlock_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ward {2}. Whenever you commit a crime, put a +1/+1 counter on target creature."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_crime_trigger(obj, crime_effect)]

DOC_AURLOCK = make_creature(
    name="Doc Aurlock, Grizzled Genius",
    power=2, toughness=4,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Bear", "Druid"},
    supertypes={"Legendary"},
    text="Ward {2}. Whenever you commit a crime, put a +1/+1 counter on target creature you control.",
    setup_interceptors=doc_aurlock_setup
)


def kraum_violent_cacophony_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, haste. Whenever opponent casts second spell, draw a card."""
    return []  # Complex trigger

KRAUM_VIOLENT_CACOPHONY = make_creature(
    name="Kraum, Violent Cacophony",
    power=4, toughness=4,
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Zombie", "Horror"},
    supertypes={"Legendary"},
    text="Flying, haste. Whenever an opponent casts their second spell each turn, draw a card.",
    setup_interceptors=kraum_violent_cacophony_setup
)


# More common/uncommon creatures
CACTUSFOLK_SURESHOT = make_creature(
    name="Cactusfolk Sureshot",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Archer"},
    text="Reach. {T}: Cactusfolk Sureshot deals 1 damage to target creature with flying."
)


TUMBLEWEED_RISING = make_creature(
    name="Tumbleweed Rising",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Elemental"},
    text="Trample. Landfall - Whenever a land enters under your control, Tumbleweed Rising gets +1/+1 until end of turn."
)


JAILBREAK_SCHEMER = make_creature(
    name="Jailbreak Schemer",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Rogue"},
    text="When Jailbreak Schemer enters, tap target creature an opponent controls. It doesn't untap during its controller's next untap step."
)


STERLING_SUPPLIER = make_creature(
    name="Sterling Supplier",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Dwarf", "Artificer"},
    text="When Sterling Supplier enters, create two Treasure tokens."
)


VENGEFUL_TRACKER = make_creature(
    name="Vengeful Tracker",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Menace. When Vengeful Tracker enters, destroy target creature that was dealt damage this turn."
)


RAPACIOUS_BANDIT = make_creature(
    name="Rapacious Bandit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Rogue"},
    text="Haste. When Rapacious Bandit enters, you may sacrifice an artifact. If you do, draw a card."
)


FRONTIER_FORTIFICATION = make_creature(
    name="Frontier Fortification",
    power=0, toughness=6,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Wall"},
    text="Defender. {T}: Target creature you control gets +0/+3 until end of turn."
)


STAGECOACH_SECURITY = make_creature(
    name="Stagecoach Security",
    power=3, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Giant", "Soldier"},
    text="Vigilance. Other creatures you control with mana value 2 or less have vigilance."
)


RATTLESNAKE_CHARMER = make_creature(
    name="Rattlesnake Charmer",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="Whenever a Snake creature enters under your control, you gain 2 life."
)


SANDSTORM_ELEMENTAL = make_creature(
    name="Sandstorm Elemental",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. When Sandstorm Elemental enters, it deals 2 damage to each creature with flying."
)


QUICKSAND_STALKER = make_creature(
    name="Quicksand Stalker",
    power=2, toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Whenever Quicksand Stalker becomes blocked, blocking creatures get -2/-0 until end of turn."
)


POSSE_SUPPLIER = make_creature(
    name="Posse Supplier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="When Posse Supplier enters, creatures you control get +1/+0 until end of turn."
)


CLAIM_JUMPER = make_creature(
    name="Claim Jumper",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Scout"},
    text="When Claim Jumper enters, if an opponent controls more lands than you, search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


OMENPORT_RANGER = make_creature(
    name="Omenport Ranger",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="Reach. Plot {1}{G}"
)


DISCERNING_PAWNBROKER = make_creature(
    name="Discerning Pawnbroker",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="When Discerning Pawnbroker enters, you may sacrifice an artifact. If you do, draw two cards."
)


LONESTAR_LAWMAN = make_creature(
    name="Lonestar Lawman",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Knight"},
    text="Vigilance, lifelink. Whenever you commit a crime, Lonestar Lawman gets +1/+1 until end of turn."
)


FORTUNE_OUTLAW = make_creature(
    name="Fortune Outlaw",
    power=3, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="First strike. Whenever Fortune Outlaw deals combat damage to a player, create a Treasure token."
)


SLICKROCK_SCOUT = make_creature(
    name="Slickrock Scout",
    power=2, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="{T}: Add {G}. Spend this mana only to cast creature spells or activate abilities of creatures."
)


MESA_PILLAGER = make_creature(
    name="Mesa Pillager",
    power=2, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Mercenary"},
    text="When Mesa Pillager enters, choose one - Create a Treasure token; or Mesa Pillager deals 2 damage to target creature."
)


INTREPID_STABLEMASTER = make_creature(
    name="Intrepid Stablemaster",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Intrepid Stablemaster enters, create a 1/1 white Horse creature token. Horses you control get +1/+0."
)


# More Mounts
HELL_TO_PAY = make_mount(
    name="Hell to Pay",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Menace. When this creature attacks while saddled, each opponent loses 2 life and you gain 2 life.",
    saddle=3,
    subtypes={"Nightmare", "Horse"}
)


GREAT_TRAIN_HEIST = make_mount(
    name="Great Train Heist",
    power=6, toughness=6,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Trample. When this creature attacks while saddled, create three Treasure tokens.",
    saddle=4,
    subtypes={"Elemental", "Train"}
)


TERRITORIAL_KAVU = make_mount(
    name="Territorial Kavu",
    power=3, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Whenever this creature attacks, it gets +X/+0 until end of turn, where X is the number of basic land types among lands you control.",
    saddle=2,
    subtypes={"Kavu"}
)


DESERT_DROMEDARY = make_mount(
    name="Desert Dromedary",
    power=2, toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Vigilance. As long as this creature is saddled, you may look at the top card of your library any time.",
    saddle=2,
    subtypes={"Camel"}
)


GILDED_ASSAULT_CART = make_mount(
    name="Gilded Assault Cart",
    power=5, toughness=2,
    mana_cost="{3}",
    colors=set(),
    text="Trample. When this creature attacks while saddled, it gets +2/+2 until end of turn.",
    saddle=2,
    subtypes={"Vehicle"}
)


# More spells
AMBUSH_TRAIL = make_instant(
    name="Ambush Trail",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If you committed a crime this turn, that creature also gains trample."
)


OUTLAW_NEGOTIATION = make_sorcery(
    name="Outlaw Negotiation",
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Each player sacrifices a creature. Then each player discards a card."
)


HEIST_PAYOFF = make_sorcery(
    name="Heist Payoff",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw cards equal to the number of Treasures you control, then discard two cards."
)


QUICK_DRAW = make_instant(
    name="Quick Draw",
    mana_cost="{R}",
    colors={Color.RED},
    text="Quick Draw deals 2 damage to any target. If this spell was cast from exile, it deals 4 damage instead."
)


DESERT_FORTITUDE = make_instant(
    name="Desert Fortitude",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If it's a Mount, it also gains indestructible until end of turn."
)


OUTLAW_HIDEOUT = make_enchantment(
    name="Outlaw Hideout",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Outlaw creatures you control have hexproof. At the beginning of your upkeep, you lose 1 life."
)


FRONTIER_JUSTICE = make_sorcery(
    name="Frontier Justice",
    mana_cost="{X}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all creatures with mana value X or less."
)


THUNDER_JUNCTION_EXPRESS = make_sorcery(
    name="Thunder Junction Express",
    mana_cost="{4}{R}",
    colors={Color.RED},
    text="Create three 1/1 colorless Construct artifact creature tokens with haste. They gain menace until end of turn."
)


RUSTLERS_LARIAT = make_instant(
    name="Rustler's Lariat",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Tap target creature. If you committed a crime this turn, exile that creature until end of turn."
)


SALOON_STANDOFF = make_sorcery(
    name="Saloon Standoff",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Saloon Standoff deals 3 damage to each creature. Each player who controlled a creature that died this way creates a Treasure token."
)


VANISHING_TRAIL = make_instant(
    name="Vanishing Trail",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. If you committed a crime this turn, draw a card."
)


SCALDING_VIPER = make_enchantment(
    name="Scalding Viper",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature enters under an opponent's control, Scalding Viper deals 1 damage to that creature."
)


SURVIVAL_OF_THE_FITTEST = make_enchantment(
    name="Survival of the Fittest",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="{G}, Discard a creature card: Search your library for a creature card, reveal it, put it into your hand, then shuffle."
)


OUTLAWS_LAST_STAND = make_instant(
    name="Outlaw's Last Stand",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Target creature you control gains deathtouch and indestructible until end of turn. If it's an Outlaw, it also gets +2/+2."
)


CANYON_AMBUSH = make_instant(
    name="Canyon Ambush",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. If your creature survives, put a +1/+1 counter on it."
)


# More artifacts
PROSPECTORS_PICK = make_equipment(
    name="Prospector's Pick",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0. Whenever equipped creature deals combat damage to a player, create a Treasure token."
)


BOUNTY_BOARD = make_artifact(
    name="Bounty Board",
    mana_cost="{2}",
    text="{2}, {T}: Put a bounty counter on target creature. Whenever a creature with a bounty counter on it dies, you draw a card and create a Treasure token."
)


SALOON_DOORS = make_artifact(
    name="Saloon Doors",
    mana_cost="{3}",
    text="Whenever a creature enters under your control, you may pay {1}. If you do, draw a card."
)


DESERT_WAYFINDER = make_artifact(
    name="Desert Wayfinder",
    mana_cost="{2}",
    text="{T}: Add {C}. {2}, {T}, Sacrifice Desert Wayfinder: Search your library for a Desert card, put it onto the battlefield tapped, then shuffle."
)


SIX_SHOOTER = make_equipment(
    name="Six-Shooter",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature has '{T}: This creature deals 1 damage to any target' and '{2}, {T}: This creature deals 3 damage to any target.'"
)


STAGECOACH = make_artifact(
    name="Stagecoach",
    mana_cost="{3}",
    text="{3}, {T}: Create a Treasure token. When you sacrifice a Treasure, untap Stagecoach."
)


# More lands
BANDIT_CAMP = make_land(
    name="Bandit Camp",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {B} or {R}.",
    subtypes={"Desert"}
)


SCORCHED_MESA = make_land(
    name="Scorched Mesa",
    text="Scorched Mesa enters tapped. {T}: Add {R} or {W}. {2}, {T}, Sacrifice Scorched Mesa: It deals 2 damage to any target.",
    subtypes={"Desert"}
)


OASIS_SPRING = make_land(
    name="Oasis Spring",
    text="Oasis Spring enters tapped. {T}: Add {G} or {U}. When Oasis Spring enters, you gain 1 life.",
    subtypes={"Desert"}
)


PROSPECTORS_CLAIM = make_land(
    name="Prospector's Claim",
    text="{T}: Add {C}. {T}, Sacrifice Prospector's Claim: Create a Treasure token and draw a card."
)


GOLD_MINE = make_land(
    name="Gold Mine",
    text="{T}: Add {C}. {3}, {T}: Create a Treasure token."
)


FRONTIER_OUTPOST = make_land(
    name="Frontier Outpost",
    text="Frontier Outpost enters tapped unless you control two or more other lands. {T}: Add {R} or {W}."
)


GHOST_TOWN = make_land(
    name="Ghost Town",
    text="{T}: Add {C}. {0}: Return Ghost Town to its owner's hand. Activate only if an opponent controls more lands than you.",
    subtypes={"Desert"}
)


RATTLEBACK_DEN = make_land(
    name="Rattleback Den",
    text="{T}: Add {B} or {G}. Rattleback Den enters tapped unless you control a Swamp or Forest.",
    subtypes={"Desert"}
)


# =============================================================================
# FINAL BATCH - REACHING ~250 CARDS
# =============================================================================

# More legendary characters from OTJ
def olivia_opulent_outlaw_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying, lifelink. Whenever you commit a crime, create a Treasure."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Treasure', 'types': {CardType.ARTIFACT}, 'subtypes': {'Treasure'}}
        }, source=obj.id)]
    return [make_crime_trigger(obj, crime_effect)]

OLIVIA_OPULENT_OUTLAW = make_creature(
    name="Olivia, Opulent Outlaw",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}{B}",
    colors={Color.RED, Color.WHITE, Color.BLACK},
    subtypes={"Vampire", "Assassin"},
    supertypes={"Legendary"},
    text="Flying, lifelink. Whenever you commit a crime, create a Treasure token. At the beginning of your end step, if you have five or more Treasures, put a +1/+1 counter on Olivia.",
    setup_interceptors=olivia_opulent_outlaw_setup
)


def geralf_the_fleshwright_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, create a 2/2 blue and black Zombie Rogue token."""
    def crime_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Zombie Rogue', 'power': 2, 'toughness': 2, 'colors': {Color.BLUE, Color.BLACK}, 'subtypes': {'Zombie', 'Rogue'}}
        }, source=obj.id)]
    return [make_crime_trigger(obj, crime_effect)]

GERALF_THE_FLESHWRIGHT = make_creature(
    name="Geralf, the Fleshwright",
    power=2, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Whenever you commit a crime, create a 2/2 blue and black Zombie Rogue creature token. This ability triggers only once each turn.",
    setup_interceptors=geralf_the_fleshwright_setup
)


def kaervek_the_punisher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. Whenever Kaervek deals combat damage to a player, target creature that player controls gets -X/-X until end of turn."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Would need targeting
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

KAERVEK_THE_PUNISHER = make_creature(
    name="Kaervek, the Punisher",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Deathtouch. Whenever Kaervek deals combat damage to a player, exile the top card of that player's library. You may cast it for as long as it remains exiled, and mana of any type can be spent to cast it.",
    setup_interceptors=kaervek_the_punisher_setup
)


# More creatures
DESERT_DESPERADO = make_creature(
    name="Desert Desperado",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Menace. When Desert Desperado enters, target opponent loses 2 life."
)


BUZZARD_RIDER = make_creature(
    name="Buzzard Rider",
    power=2, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="Flying. When Buzzard Rider enters, return target creature card with mana value 2 or less from your graveyard to your hand."
)


PLAINS_WANDERER = make_creature(
    name="Plains Wanderer",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ranger"},
    text="When Plains Wanderer enters, you may put a land card from your hand onto the battlefield tapped."
)


FRONTIER_GUIDE = make_creature(
    name="Frontier Guide",
    power=1, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Scout"},
    text="{T}, {2}: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle."
)


GOLDPAN_MINER = make_creature(
    name="Goldpan Miner",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Artificer"},
    text="When Goldpan Miner dies, create a Treasure token."
)


EXPLOSIVE_SINGULARITY = make_creature(
    name="Explosive Singularity",
    power=5, toughness=5,
    mana_cost="{6}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample. When Explosive Singularity enters, it deals 10 damage to any target."
)


DESERT_MONITOR = make_creature(
    name="Desert Monitor",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Lizard"},
    text="Vigilance. Desert Monitor can't be blocked by creatures with power 2 or less."
)


TUMBLEGUARD = make_creature(
    name="Tumbleguard",
    power=3, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Elemental", "Soldier"},
    text="Vigilance. When Tumbleguard dies, create a 1/1 white Mercenary creature token."
)


VAULT_PLUNDERER = make_creature(
    name="Vault Plunderer",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Whenever Vault Plunderer deals combat damage to a player, create a Treasure token and exile the top card of that player's library."
)


WHISKEY_GREMLIN = make_creature(
    name="Whiskey Gremlin",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Gremlin"},
    text="Haste. When Whiskey Gremlin dies, it deals 2 damage to any target."
)


PRAIRIE_DOG = make_creature(
    name="Prairie Dog",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Dog"},
    text="When Prairie Dog enters, scry 1. Landfall - Whenever a land enters under your control, Prairie Dog gets +1/+1 until end of turn."
)


MAGEBANE_LIZARD = make_creature(
    name="Magebane Lizard",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
    text="Prowess. Magebane Lizard can't be blocked by creatures with power 2 or greater."
)


CACTUS_TYRANT = make_creature(
    name="Cactus Tyrant",
    power=6, toughness=4,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Beast"},
    text="Trample, reach. When Cactus Tyrant enters, it deals damage equal to its power divided as you choose among any number of target creatures without flying."
)


SCALDING_TONGS = make_creature(
    name="Scalding Tongs",
    power=0, toughness=4,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Construct"},
    text="Defender. At the beginning of each end step, if a creature dealt damage by Scalding Tongs this turn died, draw a card."
)


DUELING_PISTOLEER = make_creature(
    name="Dueling Pistoleer",
    power=2, toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="First strike. When Dueling Pistoleer enters, it deals 1 damage to target creature."
)


UNDERTAKERS_COACH = make_creature(
    name="Undertaker's Coach",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
    text="Flying. Whenever another creature you control dies, each opponent loses 1 life."
)


CANYON_PREDATOR = make_creature(
    name="Canyon Predator",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Cat"},
    text="First strike. Canyon Predator attacks each combat if able."
)


RATTLESKULL_HOWLER = make_creature(
    name="Rattleskull Howler",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. When Rattleskull Howler enters, creatures you control get +1/+1 until end of turn."
)


SCRAPYARD_STEELSHAPER = make_creature(
    name="Scrapyard Steelshaper",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Artificer"},
    text="When Scrapyard Steelshaper enters, create a 1/1 colorless Construct artifact creature token."
)


CANYON_WRANGLER = make_creature(
    name="Canyon Wrangler",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Scout"},
    text="When Canyon Wrangler enters, put a +1/+1 counter on target Mount you control."
)


HIRED_BLADE = make_creature(
    name="Hired Blade",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Flash. Deathtouch."
)


SANDSTORM_VERMIN = make_creature(
    name="Sandstorm Vermin",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Rat"},
    text="Deathtouch. When Sandstorm Vermin dies, create a 1/1 black Rat creature token."
)


TERRITORIAL_WITCHSTALKER = make_creature(
    name="Territorial Witchstalker",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Vigilance. Hexproof from instants."
)


LONGHORN_SHARPSHOOTER = make_creature(
    name="Longhorn Sharpshooter",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Minotaur", "Mercenary"},
    text="Reach. {T}: Longhorn Sharpshooter deals 1 damage to target creature or player."
)


COYOTE_SCOUT = make_creature(
    name="Coyote Scout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Coyote", "Scout"},
    text="When Coyote Scout enters, look at the top three cards of your library. You may reveal a land card from among them and put it into your hand. Put the rest on the bottom."
)


MASKED_VANDAL = make_creature(
    name="Masked Vandal",
    power=1, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Shapeshifter"},
    text="Changeling. When Masked Vandal enters, you may exile a creature card from your graveyard. If you do, exile target artifact or enchantment."
)


# More spells
DEAD_EYE = make_instant(
    name="Dead Eye",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Destroy target creature that was dealt damage this turn."
)


CRACK_OPEN = make_sorcery(
    name="Crack Open",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Create two Treasure tokens."
)


TRAIN_HEIST = make_sorcery(
    name="Train Heist",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Gain control of target artifact or creature until end of turn. Untap it. It gains haste until end of turn. Create a Treasure token."
)


DUELIST_CHALLENGE = make_instant(
    name="Duelist's Challenge",
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Target creature you control gets +2/+2 and gains first strike until end of turn. It fights target creature you don't control."
)


WANTED_DEAD = make_sorcery(
    name="Wanted Dead",
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If it was legendary, create two Treasure tokens."
)


DESERT_BLOOM = make_sorcery(
    name="Desert Bloom",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card or Desert card, put it onto the battlefield tapped, then shuffle. You gain 2 life."
)


HARNESS_THE_STORM = make_instant(
    name="Harness the Storm",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Harness the Storm deals 3 damage to any target. If you control a Desert, it deals 4 damage instead."
)


PHANTOM_HOLDUP = make_instant(
    name="Phantom Holdup",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. Create a Treasure token."
)


SUNSET_REVELRY = make_sorcery(
    name="Sunset Revelry",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="If you have less life than an opponent, you gain 4 life. If you control fewer creatures than an opponent, create two 1/1 white Human creature tokens."
)


LAW_OF_THE_LAND = make_enchantment(
    name="Law of the Land",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Whenever you commit a crime, you may exile target creature with power 4 or greater."
)


DESERT_DWELLING = make_enchantment(
    name="Desert Dwelling",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Lands you control have '{T}: Add one mana of any color.' Deserts you control have '{T}: Add two mana in any combination of colors.'"
)


# Final creatures to round out
OASIS_GARDENER = make_creature(
    name="Oasis Gardener",
    power=1, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    text="{T}: Add {G}. {T}: Add one mana of any color. Spend this mana only to cast creature spells."
)


SANDSTONE_WARRIOR = make_creature(
    name="Sandstone Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Warrior"},
    text="First strike. Haste."
)


THUNDERHEAD_SQUADRON = make_creature(
    name="Thunderhead Squadron",
    power=3, toughness=2,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Bird", "Soldier"},
    text="Flying. When Thunderhead Squadron enters, create a 1/1 white Bird creature token with flying."
)


SCORPION_SENTINEL = make_creature(
    name="Scorpion Sentinel",
    power=1, toughness=4,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Scorpion"},
    text="Defender, deathtouch."
)


DUST_BOWL_AMBUSHER = make_creature(
    name="Dust Bowl Ambusher",
    power=3, toughness=1,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Flash. When Dust Bowl Ambusher enters, target creature gets -2/-2 until end of turn."
)


PROSPECTORS_COMPANION = make_creature(
    name="Prospector's Companion",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dog"},
    text="Whenever you create a Treasure token, Prospector's Companion gets +1/+1 until end of turn."
)


GILDED_PINIONS = make_creature(
    name="Gilded Pinions",
    power=2, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Bird", "Construct"},
    text="Flying. When Gilded Pinions enters, create a Treasure token."
)


OUTLAW_MEDIC = make_creature(
    name="Outlaw Medic",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Cleric"},
    text="When Outlaw Medic enters, you gain 2 life. Whenever you commit a crime, you gain 1 life."
)


RECKLESS_FIREWEAVER = make_creature(
    name="Reckless Fireweaver",
    power=1, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Artificer"},
    text="Whenever an artifact enters under your control, Reckless Fireweaver deals 1 damage to each opponent."
)


SPELL_SWINDLE = make_instant(
    name="Spell Swindle",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Create X Treasure tokens, where X is that spell's mana value."
)


UNLICENSED_HEARSE = make_artifact(
    name="Unlicensed Hearse",
    mana_cost="{2}",
    text="Crew 2. {T}: Exile up to two target cards from graveyards. Unlicensed Hearse's power and toughness are each equal to the number of cards exiled with it."
)


REVEL_IN_RICHES = make_enchantment(
    name="Revel in Riches",
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    text="Whenever a creature an opponent controls dies, create a Treasure token. At the beginning of your upkeep, if you control ten or more Treasures, you win the game."
)


BRASS_BRAWLER = make_creature(
    name="Brass Brawler",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Dwarf", "Warrior"},
    text="Trample. Whenever Brass Brawler attacks, create a Treasure token."
)


VAULTBORN_TYRANT = make_creature(
    name="Vaultborn Tyrant",
    power=6, toughness=6,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample, haste. When Vaultborn Tyrant enters, create two Treasure tokens. Whenever a Treasure you control is put into a graveyard from the battlefield, you gain 1 life."
)


BOUNTY_OF_THE_HUNT = make_instant(
    name="Bounty of the Hunt",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="You may exile a green card from your hand rather than pay this spell's mana cost. Distribute three +1/+1 counters among one, two, or three target creatures."
)


TREASURE_CRUISE = make_sorcery(
    name="Treasure Cruise",
    mana_cost="{7}{U}",
    colors={Color.BLUE},
    text="Delve. Draw three cards."
)


DIRE_FLEET_DAREDEVIL = make_creature(
    name="Dire Fleet Daredevil",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="First strike. When Dire Fleet Daredevil enters, exile target instant or sorcery card from an opponent's graveyard. You may cast it this turn, and mana of any type can be spent to cast it."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

OUTLAWS_THUNDER_JUNCTION_CARDS = {
    # WHITE - LEGENDARY
    "Kellan, Daring Traveler": KELLAN_DARING_TRAVELER,
    "Sheriff of Safeton": SHERIFF_OF_SAFETON,
    "Wylie Duke, Atiin Hero": WYLIE_DUKE,

    # WHITE - CREATURES
    "Frontier Seeker": FRONTIER_SEEKER,
    "Prairie Sentinel": PRAIRIE_SENTINEL,
    "Wanted Griffin": WANTED_GRIFFIN,
    "Dusty Vanguard": DUSTY_VANGUARD,
    "Canyon Guide": CANYON_GUIDE,
    "Bounty Agent": BOUNTY_AGENT,
    "Lawbringer Cavalry": LAWBRINGER_CAVALRY,
    "Lariat Specialist": LARIAT_SPECIALIST,
    "Frontier Priest": FRONTIER_PRIEST,
    "Sandstorm Sentry": SANDSTORM_SENTRY,
    "Aven Interrupter": AVEN_INTERRUPTER,

    # WHITE - MOUNTS
    "Sandsteppe Courser": SANDSTEPPE_COURSER,
    "Armored Armadillo": ARMORED_ARMADILLO,
    "Dustbringer Pegasus": DUSTBRINGER_PEGASUS,

    # WHITE - SPELLS
    "Showdown of the Skalds": SHOWDOWN_OF_THE_SKALDS,
    "Holy Cow": HOLY_COW,
    "Spring into Action": SPRING_INTO_ACTION,
    "Rustler's Roundup": RUSTLERS_ROUNDUP,

    # BLUE - LEGENDARY
    "Oko, the Ringleader": OKO_THE_RINGLEADER,
    "Eriette, the Beguiler": ERIETTE_THE_BEGUILER,
    "Slickshot Show-Off": SLICKSHOT_SHOWOFF,

    # BLUE - CREATURES
    "Sneaky Snacker": SNEAKY_SNACKER,
    "Nimble Outlaw": NIMBLE_OUTLAW,
    "Trickster Rogue": TRICKSTER_ROGUE,
    "Desert Mirage": DESERT_MIRAGE,
    "Canyon Crab": CANYON_CRAB,
    "Coyote Messenger": COYOTE_MESSENGER,
    "Mystic Desperado": MYSTIC_DESPERADO,
    "Dust Devil": DUST_DEVIL,

    # BLUE - SPELLS
    "Trick Shot": TRICK_SHOT,
    "Three Steps Ahead": THREE_STEPS_AHEAD,
    "Phantom Interference": PHANTOM_INTERFERENCE,
    "Loan Shark": LOAN_SHARK,
    "Take the Fall": TAKE_THE_FALL,
    "Arcane Heist": ARCANE_HEIST,

    # BLACK - LEGENDARY
    "Tinybones, the Pickpocket": TINYBONES_THE_PICKPOCKET,
    "Rakdos, the Muscle": RAKDOS_THE_MUSCLE,
    "Vraska, the Silencer": VRASKA_THE_SILENCER,
    "Gisa, the Hellraiser": GISA_THE_HELLRAISER,

    # BLACK - CREATURES
    "Backstage Bandit": BACKSTAGE_BANDIT,
    "Gravedigger Ghoul": GRAVEDIGGER_GHOUL,
    "Vadmir, New Blood": VADMIR_NEW_BLOOD,
    "Snake Oil Peddler": SNAKE_OIL_PEDDLER,
    "Dark Rider": DARK_RIDER,
    "Corrupted Sheriff": CORRUPTED_SHERIFF,
    "Scorpion Cultist": SCORPION_CULTIST,
    "Nighthawk Assailant": NIGHTHAWK_ASSAILANT,
    "Bounty Board Broker": BOUNTY_BOARD_BROKER,
    "Wanted Scoundrels": WANTED_SCOUNDRELS,

    # BLACK - SPELLS
    "Make Your Own Luck": MAKE_YOUR_OWN_LUCK,
    "Rush of Dread": RUSH_OF_DREAD,
    "Murder": MURDER,
    "Final Showdown": FINAL_SHOWDOWN,
    "Intimidation Campaign": INTIMIDATION_CAMPAIGN,
    "Betrayal at Ghost Town": BETRAYAL_AT_GHOST_TOWN,
    "Fell the Leaders": FELL_THE_LEADERS,

    # RED - LEGENDARY
    "Magda, the Hoardmaster": MAGDA_THE_HOARDMASTER,
    "Vial Smasher, Gleeful Grenadier": VIAL_SMASHER,
    "Hellspur Posse Boss": HELLSPUR_POSSE_BOSS,

    # RED - CREATURES
    "Goblin Tomb Raider": GOBLIN_TOMB_RAIDER,
    "Reckless Lackey": RECKLESS_LACKEY,
    "Outlaw Stitcher": OUTLAW_STITCHER,
    "Thunder Junction Pyromancer": THUNDER_JUNCTION_PYROMANCER,
    "Dynamite Miner": DYNAMITE_MINER,
    "Railway Brawler": RAILWAY_BRAWLER,
    "Cache Bandit": CACHE_BANDIT,
    "Blast-Zone Miner": BLAST_ZONE_MINER,
    "Canyon Runner": CANYON_RUNNER,
    "Outlaw Brute": OUTLAW_BRUTE,
    "Treasure Nabber": TREASURE_NABBER,

    # RED - MOUNTS
    "Terror of the Peaks": TERROR_OF_THE_PEAKS,
    "Hellspur Brute": HELLSPUR_BRUTE,

    # RED - SPELLS
    "Lightning Helix": LIGHTNING_HELIX,
    "Highway Robbery": HIGHWAY_ROBBERY,
    "Explosive Entry": EXPLOSIVE_ENTRY,
    "Showdown at Noon": SHOWDOWN_AT_NOON,
    "Caught in the Crossfire": CAUGHT_IN_THE_CROSSFIRE,
    "Seize the Spoils": SEIZE_THE_SPOILS,

    # GREEN - LEGENDARY
    "Bonny Pall, Clearcutter": BONNY_PALL_CLEARCUTTER,
    "Selvala, Eager Trailblazer": SELVALA_EAGER_TRAILBLAZER,
    "Bristly Bill, Spine Sower": BRISTLY_BILL,

    # GREEN - CREATURES
    "Cactus Serpent": CACTUS_SERPENT,
    "Frontier Trampler": FRONTIER_TRAMPLER,
    "Mesa Cavalier": MESA_CAVALIER,
    "Gold Rush Prospector": GOLD_RUSH_PROSPECTOR,
    "Towering Baloths": TOWERING_BALOTHS,
    "Rattleback Apothecary": RATTLEBACK_APOTHECARY,
    "Freestrider Commando": FREESTRIDER_COMMANDO,
    "Bristleback Beast": BRISTLEBACK_BEAST,
    "Canyon Lurker": CANYON_LURKER,
    "Wasteland Scorpion": WASTELAND_SCORPION,
    "Rattleclaw Mystic": RATTLECLAW_MYSTIC,

    # GREEN - MOUNTS
    "Rambling Possum": RAMBLING_POSSUM,
    "Omenport Vigilante": OMENPORT_VIGILANTE,

    # GREEN - SPELLS
    "Return the Favor": RETURN_THE_FAVOR,
    "Bite Down": BITE_DOWN,
    "Outcaster Greenblade": OUTCASTER_GREENBLADE,
    "Cultivate": CULTIVATE,
    "Ominous Parcel": OMINOUS_PARCEL,
    "Rampage of the Clans": RAMPAGE_OF_THE_CLANS,

    # MULTICOLOR - LEGENDARY
    "Fblthp, Lost on the Range": FBLTHP_LOST_ON_THE_RANGE,
    "Obeka, Splitter of Seconds": OBEKA_SPLITTER_OF_SECONDS,
    "Satoru, the Infiltrator": SATORU_THE_INFILTRATOR,

    # MULTICOLOR - CREATURES
    "Izzet Inventor": IZZET_INVENTOR,
    "Dust Animus": DUST_ANIMUS,
    "Seraph of New Capenna": SERAPH_OF_NEW_CAPENNA,
    "Rakdos Headliner": RAKDOS_HEADLINER,
    "Selesnya Scout": SELESNYA_SCOUT,
    "Dimir Infiltrator": DIMIR_INFILTRATOR,
    "Gruul Warchief": GRUUL_WARCHIEF,

    # EQUIPMENT
    "Lasso of Clarity": LASSO_OF_CLARITY,
    "Outlaw's Fury": OUTLAWS_FURY,
    "Quick-Draw Holster": QUICK_DRAW_HOLSTER,
    "Goldvein Pick": GOLDVEIN_PICK,

    # ARTIFACTS
    "Sterling Keykeeper": STERLING_KEYKEEPER,
    "Treasure Map": TREASURE_MAP,
    "Wanted Poster": WANTED_POSTER,
    "Lucky Clover": LUCKY_CLOVER,

    # LANDS - DESERTS
    "Conduit Pylons": CONDUIT_PYLONS,
    "Mirage Mesa": MIRAGE_MESA,
    "Festering Gulch": FESTERING_GULCH,
    "Jagged Barrens": JAGGED_BARRENS,
    "Abraded Bluffs": ABRADED_BLUFFS,
    "Thundering Falls": THUNDERING_FALLS,
    "Outlaw's Hideout": OUTLAWS_HIDEOUT,
    "Cactus Preserve": CACTUS_PRESERVE,

    # LANDS - OTHER
    "Boom Town": BOOM_TOWN,
    "Frontier Bivouac": FRONTIER_BIVOUAC,

    # BASIC LANDS
    "Plains": PLAINS_OTJ,
    "Island": ISLAND_OTJ,
    "Swamp": SWAMP_OTJ,
    "Mountain": MOUNTAIN_OTJ,
    "Forest": FOREST_OTJ,

    # ADDITIONAL LEGENDARY
    "Annie Flash, the Veteran": ANNIE_FLASH,
    "Doc Aurlock, Grizzled Genius": DOC_AURLOCK,
    "Kraum, Violent Cacophony": KRAUM_VIOLENT_CACOPHONY,

    # ADDITIONAL CREATURES
    "Cactusfolk Sureshot": CACTUSFOLK_SURESHOT,
    "Tumbleweed Rising": TUMBLEWEED_RISING,
    "Jailbreak Schemer": JAILBREAK_SCHEMER,
    "Sterling Supplier": STERLING_SUPPLIER,
    "Vengeful Tracker": VENGEFUL_TRACKER,
    "Rapacious Bandit": RAPACIOUS_BANDIT,
    "Frontier Fortification": FRONTIER_FORTIFICATION,
    "Stagecoach Security": STAGECOACH_SECURITY,
    "Rattlesnake Charmer": RATTLESNAKE_CHARMER,
    "Sandstorm Elemental": SANDSTORM_ELEMENTAL,
    "Quicksand Stalker": QUICKSAND_STALKER,
    "Posse Supplier": POSSE_SUPPLIER,
    "Claim Jumper": CLAIM_JUMPER,
    "Omenport Ranger": OMENPORT_RANGER,
    "Discerning Pawnbroker": DISCERNING_PAWNBROKER,
    "Lonestar Lawman": LONESTAR_LAWMAN,
    "Fortune Outlaw": FORTUNE_OUTLAW,
    "Slickrock Scout": SLICKROCK_SCOUT,
    "Mesa Pillager": MESA_PILLAGER,
    "Intrepid Stablemaster": INTREPID_STABLEMASTER,

    # ADDITIONAL MOUNTS
    "Hell to Pay": HELL_TO_PAY,
    "Great Train Heist": GREAT_TRAIN_HEIST,
    "Territorial Kavu": TERRITORIAL_KAVU,
    "Desert Dromedary": DESERT_DROMEDARY,
    "Gilded Assault Cart": GILDED_ASSAULT_CART,

    # ADDITIONAL SPELLS
    "Ambush Trail": AMBUSH_TRAIL,
    "Outlaw Negotiation": OUTLAW_NEGOTIATION,
    "Heist Payoff": HEIST_PAYOFF,
    "Quick Draw": QUICK_DRAW,
    "Desert Fortitude": DESERT_FORTITUDE,
    "Outlaw Hideout": OUTLAW_HIDEOUT,
    "Frontier Justice": FRONTIER_JUSTICE,
    "Thunder Junction Express": THUNDER_JUNCTION_EXPRESS,
    "Rustler's Lariat": RUSTLERS_LARIAT,
    "Saloon Standoff": SALOON_STANDOFF,
    "Vanishing Trail": VANISHING_TRAIL,
    "Scalding Viper": SCALDING_VIPER,
    "Survival of the Fittest": SURVIVAL_OF_THE_FITTEST,
    "Outlaw's Last Stand": OUTLAWS_LAST_STAND,
    "Canyon Ambush": CANYON_AMBUSH,

    # ADDITIONAL EQUIPMENT
    "Prospector's Pick": PROSPECTORS_PICK,
    "Six-Shooter": SIX_SHOOTER,

    # ADDITIONAL ARTIFACTS
    "Bounty Board": BOUNTY_BOARD,
    "Saloon Doors": SALOON_DOORS,
    "Desert Wayfinder": DESERT_WAYFINDER,
    "Stagecoach": STAGECOACH,

    # ADDITIONAL LANDS
    "Bandit Camp": BANDIT_CAMP,
    "Scorched Mesa": SCORCHED_MESA,
    "Oasis Spring": OASIS_SPRING,
    "Prospector's Claim": PROSPECTORS_CLAIM,
    "Gold Mine": GOLD_MINE,
    "Frontier Outpost": FRONTIER_OUTPOST,
    "Ghost Town": GHOST_TOWN,
    "Rattleback Den": RATTLEBACK_DEN,

    # FINAL BATCH - LEGENDARY
    "Olivia, Opulent Outlaw": OLIVIA_OPULENT_OUTLAW,
    "Geralf, the Fleshwright": GERALF_THE_FLESHWRIGHT,
    "Kaervek, the Punisher": KAERVEK_THE_PUNISHER,

    # FINAL BATCH - CREATURES
    "Desert Desperado": DESERT_DESPERADO,
    "Buzzard Rider": BUZZARD_RIDER,
    "Plains Wanderer": PLAINS_WANDERER,
    "Frontier Guide": FRONTIER_GUIDE,
    "Goldpan Miner": GOLDPAN_MINER,
    "Explosive Singularity": EXPLOSIVE_SINGULARITY,
    "Desert Monitor": DESERT_MONITOR,
    "Tumbleguard": TUMBLEGUARD,
    "Vault Plunderer": VAULT_PLUNDERER,
    "Whiskey Gremlin": WHISKEY_GREMLIN,
    "Prairie Dog": PRAIRIE_DOG,
    "Magebane Lizard": MAGEBANE_LIZARD,
    "Cactus Tyrant": CACTUS_TYRANT,
    "Scalding Tongs": SCALDING_TONGS,
    "Dueling Pistoleer": DUELING_PISTOLEER,
    "Undertaker's Coach": UNDERTAKERS_COACH,
    "Canyon Predator": CANYON_PREDATOR,
    "Rattleskull Howler": RATTLESKULL_HOWLER,
    "Scrapyard Steelshaper": SCRAPYARD_STEELSHAPER,
    "Canyon Wrangler": CANYON_WRANGLER,
    "Hired Blade": HIRED_BLADE,
    "Sandstorm Vermin": SANDSTORM_VERMIN,
    "Territorial Witchstalker": TERRITORIAL_WITCHSTALKER,
    "Longhorn Sharpshooter": LONGHORN_SHARPSHOOTER,
    "Coyote Scout": COYOTE_SCOUT,
    "Masked Vandal": MASKED_VANDAL,

    # FINAL BATCH - SPELLS
    "Dead Eye": DEAD_EYE,
    "Crack Open": CRACK_OPEN,
    "Train Heist": TRAIN_HEIST,
    "Duelist's Challenge": DUELIST_CHALLENGE,
    "Wanted Dead": WANTED_DEAD,
    "Desert Bloom": DESERT_BLOOM,
    "Harness the Storm": HARNESS_THE_STORM,
    "Phantom Holdup": PHANTOM_HOLDUP,
    "Sunset Revelry": SUNSET_REVELRY,
    "Law of the Land": LAW_OF_THE_LAND,
    "Desert Dwelling": DESERT_DWELLING,

    # FINAL ADDITIONS
    "Oasis Gardener": OASIS_GARDENER,
    "Sandstone Warrior": SANDSTONE_WARRIOR,
    "Thunderhead Squadron": THUNDERHEAD_SQUADRON,
    "Scorpion Sentinel": SCORPION_SENTINEL,
    "Dust Bowl Ambusher": DUST_BOWL_AMBUSHER,
    "Prospector's Companion": PROSPECTORS_COMPANION,
    "Gilded Pinions": GILDED_PINIONS,
    "Outlaw Medic": OUTLAW_MEDIC,
    "Reckless Fireweaver": RECKLESS_FIREWEAVER,
    "Spell Swindle": SPELL_SWINDLE,
    "Unlicensed Hearse": UNLICENSED_HEARSE,
    "Revel in Riches": REVEL_IN_RICHES,
    "Brass Brawler": BRASS_BRAWLER,
    "Vaultborn Tyrant": VAULTBORN_TYRANT,
    "Bounty of the Hunt": BOUNTY_OF_THE_HUNT,
    "Treasure Cruise": TREASURE_CRUISE,
    "Dire Fleet Daredevil": DIRE_FLEET_DAREDEVIL,
}

print(f"Loaded {len(OUTLAWS_THUNDER_JUNCTION_CARDS)} Outlaws of Thunder Junction cards")
