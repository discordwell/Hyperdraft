"""
Duskmourn: House of Horror (DSK) Card Implementations

Set released September 2024. ~250 cards.
Features mechanics: Rooms, Delirium, Manifest Dread, Survival, Eerie
Horror house theme with Valgavoth as main villain.
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


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set, text: str,
                           subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create artifact creature card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ARTIFACT, CardType.CREATURE},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost,
            power=power,
            toughness=toughness
        ),
        text=text,
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


def make_room(name: str, mana_cost: str, colors: set, text: str, supertypes: set = None, setup_interceptors=None):
    """Helper to create Room enchantment card definitions."""
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes={"Room"},
            supertypes=supertypes or set(),
            colors=colors,
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# DUSKMOURN KEYWORD MECHANICS
# =============================================================================

def check_delirium(state: GameState, player_id: str) -> bool:
    """Check if player has delirium (4+ card types in graveyard)."""
    player = state.players.get(player_id)
    if not player:
        return False

    types_in_grave = set()
    for card_id in player.graveyard:
        card = state.objects.get(card_id)
        if card:
            types_in_grave.update(card.characteristics.types)

    return len(types_in_grave) >= 4


def check_survival(state: GameState, player_id: str, source_obj: GameObject) -> bool:
    """Check if player has survival (creature with power 2+ greater than base)."""
    for obj_id, obj in state.objects.items():
        if obj.controller != player_id:
            continue
        if CardType.CREATURE not in obj.characteristics.types:
            continue
        if obj.zone != ZoneType.BATTLEFIELD:
            continue

        base_power = obj.characteristics.power or 0
        current_power = get_power(obj, state)
        if current_power >= base_power + 2:
            return True

    return False


def make_delirium_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Delirium - This creature gets +X/+Y if you have 4+ card types in graveyard."""
    def delirium_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return check_delirium(state, source_obj.controller)

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, delirium_filter)


def make_survival_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """Survival - This creature gets +X/+Y if you control a creature with power 2+ greater than base."""
    def survival_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        return check_survival(state, source_obj.controller, source_obj)

    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, survival_filter)


def make_eerie_trigger(source_obj: GameObject, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """Eerie - Whenever an enchantment enters or you unlock a Room, trigger effect."""
    def eerie_filter(event: Event, state: GameState) -> bool:
        if event.type == EventType.ZONE_CHANGE:
            if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
                return False
            obj_id = event.payload.get('object_id')
            obj = state.objects.get(obj_id)
            if not obj:
                return False
            if obj.controller != source_obj.controller:
                return False
            return CardType.ENCHANTMENT in obj.characteristics.types

        if event.type == EventType.UNLOCK_ROOM:
            return event.payload.get('controller') == source_obj.controller

        return False

    def eerie_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=new_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=eerie_filter,
        handler=eerie_handler,
        duration='while_on_battlefield'
    )


def make_manifest_dread_etb(source_obj: GameObject) -> Interceptor:
    """Manifest Dread - Look at top 2 cards, put one face-down as 2/2, other in graveyard."""
    def manifest_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.MANIFEST_DREAD,
            payload={'controller': source_obj.controller},
            source=source_obj.id
        )]
    return make_etb_trigger(source_obj, manifest_effect)


def survivor_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Survivor creatures you control."""
    return creatures_with_subtype(source, "Survivor")


def spirit_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Spirit creatures you control."""
    return creatures_with_subtype(source, "Spirit")


def demon_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Demon creatures you control."""
    return creatures_with_subtype(source, "Demon")


def nightmare_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Nightmare creatures you control."""
    return creatures_with_subtype(source, "Nightmare")


def horror_filter(source: GameObject) -> Callable[[GameObject, GameState], bool]:
    """Filter for Horror creatures you control."""
    return creatures_with_subtype(source, "Horror")


# =============================================================================
# WHITE CARDS - SURVIVORS, PROTECTION, LIGHT
# =============================================================================

# --- Legendary Creatures ---

def winter_cedric_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survivors you control get +1/+1, Eerie draw"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Survivor")))

    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]

    interceptors.append(make_eerie_trigger(obj, eerie_effect))
    return interceptors

WINTER_CEDRIC = make_creature(
    name="Winter, Cynical Opportunist",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    supertypes={"Legendary"},
    text="Vigilance. Other Survivor creatures you control get +1/+1. Eerie - Whenever an enchantment enters or you unlock a Room, draw a card.",
    setup_interceptors=winter_cedric_setup
)


def niko_aris_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB create Shard tokens, attack trigger scry"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Shard', 'types': {CardType.ENCHANTMENT}, 'subtypes': {'Shard'}, 'colors': {Color.WHITE}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Shard', 'types': {CardType.ENCHANTMENT}, 'subtypes': {'Shard'}, 'colors': {Color.WHITE}}
            }, source=obj.id)
        ]

    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SCRY, payload={'player': obj.controller, 'count': 2}, source=obj.id)]

    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]

NIKO_ARIS = make_creature(
    name="Niko Aris, Bound and Battling",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Survivor"},
    supertypes={"Legendary"},
    text="When Niko Aris enters, create two Shard enchantment tokens. Whenever Niko attacks, scry 2.",
    setup_interceptors=niko_aris_setup
)


def aminatou_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie surveil 2, manifest dread on upkeep"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SURVEIL, payload={'player': obj.controller, 'count': 2}, source=obj.id)]

    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.MANIFEST_DREAD, payload={'controller': obj.controller}, source=obj.id)]

    return [make_eerie_trigger(obj, eerie_effect), make_upkeep_trigger(obj, upkeep_effect)]

AMINATOU_VEIL_PIERCER = make_creature(
    name="Aminatou, Veil Piercer",
    power=2, toughness=4,
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Eerie - Whenever an enchantment enters or you unlock a Room, surveil 2. At the beginning of your upkeep, manifest dread.",
    setup_interceptors=aminatou_setup
)


# --- White Creatures ---

def glimmerburst_guide_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB gain 3 life"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.LIFE_CHANGE, payload={'player': obj.controller, 'amount': 3}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GLIMMERBURST_GUIDE = make_creature(
    name="Glimmerburst Guide",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Scout"},
    text="Flying. When Glimmerburst Guide enters, you gain 3 life.",
    setup_interceptors=glimmerburst_guide_setup
)


def sanctuary_seeker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival - gains +1/+1 and vigilance"""
    interceptors = make_survival_bonus(obj, 1, 1)

    def survival_keyword_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_survival(state, obj.controller, obj)

    interceptors.append(make_keyword_grant(obj, ['vigilance'], survival_keyword_filter))
    return interceptors

SANCTUARY_SEEKER = make_creature(
    name="Sanctuary Seeker",
    power=2, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Survival - As long as you control a creature with power 2 or more greater than its base power, Sanctuary Seeker gets +1/+1 and has vigilance.",
    setup_interceptors=sanctuary_seeker_setup
)


def ethereal_armor_bearer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie trigger - put +1/+1 counter on self"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'count': 1
        }, source=obj.id)]
    return [make_eerie_trigger(obj, eerie_effect)]

ETHEREAL_ARMOR_BEARER = make_creature(
    name="Ethereal Armor Bearer",
    power=1, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Eerie - Whenever an enchantment enters or you unlock a Room, put a +1/+1 counter on Ethereal Armor Bearer.",
    setup_interceptors=ethereal_armor_bearer_setup
)


SHELTERED_WANDERER = make_creature(
    name="Sheltered Wanderer",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="Vigilance. When Sheltered Wanderer enters, you may search your library for a Room card, reveal it, and put it into your hand."
)


def fear_of_exposure_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchantment creature with flash"""
    return []

FEAR_OF_EXPOSURE = make_creature(
    name="Fear of Exposure",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Nightmare"},
    text="Flash. Enchantment creature. When Fear of Exposure enters, tap target creature an opponent controls."
)


def hallowed_respite_keeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB exile target creature until this leaves"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.EXILE_UNTIL, payload={
            'source': obj.id, 'reason': 'enters'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

HALLOWED_RESPITE_KEEPER = make_creature(
    name="Hallowed Respite Keeper",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    text="When Hallowed Respite Keeper enters, exile target creature an opponent controls until Hallowed Respite Keeper leaves the battlefield.",
    setup_interceptors=hallowed_respite_keeper_setup
)


LIGHT_OF_THE_HOUSE = make_creature(
    name="Light of the House",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance. Other creatures you control have ward {1}."
)


def trapped_angel_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Escape from graveyard"""
    return []

TRAPPED_ANGEL = make_creature(
    name="Trapped Angel",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying. Escape - {4}{W}{W}, Exile four other cards from your graveyard."
)


FLICKERING_SURVIVOR = make_creature(
    name="Flickering Survivor",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="When Flickering Survivor enters, you may exile another creature you control, then return it to the battlefield."
)


def house_guardian_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other creatures you control get +0/+1"""
    return make_static_pt_boost(obj, 0, 1, other_creatures_you_control(obj))

HOUSE_GUARDIAN = make_creature(
    name="House Guardian",
    power=1, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="Defender. Other creatures you control get +0/+1.",
    setup_interceptors=house_guardian_setup
)


# --- White Instants/Sorceries ---

FINAL_LIGHT = make_instant(
    name="Final Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature with power 4 or greater."
)

SURVIVAL_INSTINCT = make_instant(
    name="Survival Instinct",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gets +2/+2 until end of turn. If you have survival, it also gains indestructible until end of turn."
)

SHELTER_IN_LIGHT = make_sorcery(
    name="Shelter in Light",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Create a 1/1 white Spirit creature token with flying. If an opponent controls more creatures than you, create two tokens instead."
)

BLESSED_SANCTUARY = make_enchantment(
    name="Blessed Sanctuary",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Prevent all noncombat damage that would be dealt to you and creatures you control. Whenever a creature enters under your control, you gain 2 life."
)


# =============================================================================
# BLUE CARDS - SPIRITS, ILLUSIONS, INVESTIGATION
# =============================================================================

# --- Blue Legendary Creatures ---

def zimone_mystery_unraveler_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Draw triggers investigate"""
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Clue', 'types': {CardType.ARTIFACT}, 'subtypes': {'Clue'}}
        }, source=obj.id)]

    def draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        return event.payload.get('player') == obj.controller

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = draw_effect(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=draw_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

ZIMONE_MYSTERY_UNRAVELER = make_creature(
    name="Zimone, Mystery Unraveler",
    power=2, toughness=3,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Survivor", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you draw a card, if it's the second card you've drawn this turn, investigate.",
    setup_interceptors=zimone_mystery_unraveler_setup
)


def kaito_dancing_shadow_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Ninjutsu-like, unblockable"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'count': 1}, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

KAITO_DANCING_SHADOW = make_creature(
    name="Kaito, Dancing Shadow",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="Whenever Kaito deals combat damage to a player, draw a card. {2}{U}{B}: Return Kaito to its owner's hand. Activate only during combat.",
    setup_interceptors=kaito_dancing_shadow_setup
)


# --- Blue Creatures ---

def phantom_investigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB investigate"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Clue', 'types': {CardType.ARTIFACT}, 'subtypes': {'Clue'}}
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PHANTOM_INVESTIGATOR = make_creature(
    name="Phantom Investigator",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. When Phantom Investigator enters, investigate.",
    setup_interceptors=phantom_investigator_setup
)


def thought_stalker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie - target player mills 2"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(type=EventType.MILL, payload={
                'player': opponents[0], 'count': 2
            }, source=obj.id)]
        return []
    return [make_eerie_trigger(obj, eerie_effect)]

THOUGHT_STALKER = make_creature(
    name="Thought Stalker",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flying. Eerie - Whenever an enchantment enters or you unlock a Room, target player mills two cards.",
    setup_interceptors=thought_stalker_setup
)


def mirror_echo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB copy a creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CLONE_CREATURE, payload={
            'source': obj.id, 'controller': obj.controller
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

MIRROR_ECHO = make_creature(
    name="Mirror Echo",
    power=0, toughness=0,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Shapeshifter"},
    text="You may have Mirror Echo enter as a copy of any creature on the battlefield.",
    setup_interceptors=mirror_echo_setup
)


FEAR_OF_IMPOSTORS = make_creature(
    name="Fear of Impostors",
    power=3, toughness=3,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Nightmare"},
    text="Flash. Enchantment creature. When Fear of Impostors enters, gain control of target creature until end of turn. Untap it. It gains haste."
)


def wandering_apparition_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Damage trigger - bounce a permanent"""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.BOUNCE, payload={
            'controller': obj.controller
        }, source=obj.id)]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

WANDERING_APPARITION = make_creature(
    name="Wandering Apparition",
    power=2, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. Whenever Wandering Apparition deals combat damage to a player, you may return target nonland permanent to its owner's hand.",
    setup_interceptors=wandering_apparition_setup
)


LOST_IN_THE_MAZE = make_creature(
    name="Lost in the Maze",
    power=1, toughness=4,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Illusion"},
    text="Defender. When Lost in the Maze dies, draw two cards."
)


DREAD_SPECTER = make_creature(
    name="Dread Specter",
    power=2, toughness=2,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Horror"},
    text="Flying. Delirium - Dread Specter has hexproof if there are four or more card types among cards in your graveyard."
)


def manifest_dread_seer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB manifest dread"""
    return [make_manifest_dread_etb(obj)]

MANIFEST_DREAD_SEER = make_creature(
    name="Manifest Dread Seer",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="When Manifest Dread Seer enters, manifest dread. (Look at the top two cards of your library. Put one onto the battlefield face down as a 2/2 creature and the other into your graveyard.)",
    setup_interceptors=manifest_dread_seer_setup
)


ECHO_OF_DESPAIR = make_creature(
    name="Echo of Despair",
    power=4, toughness=3,
    mana_cost="{4}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Horror"},
    text="Flying. When Echo of Despair enters, each opponent returns a creature they control to its owner's hand."
)


# --- Blue Instants/Sorceries ---

TERROR_REFLECTED = make_instant(
    name="Terror Reflected",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {3}. If you have delirium, counter it unless its controller pays {5} instead."
)

UNSETTLING_VISION = make_sorcery(
    name="Unsettling Vision",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw two cards. If you have delirium, draw three cards instead."
)

DISTURBING_REVELATION = make_instant(
    name="Disturbing Revelation",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target player mills three cards. You may put one of those cards into their hand."
)


# =============================================================================
# BLACK CARDS - DEMONS, NIGHTMARES, DEATH
# =============================================================================

# --- Black Legendary Creatures ---

def valgavoth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """The main villain - drains on death, grows from enchantments"""
    def death_trigger(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        if CardType.CREATURE not in target.characteristics.types:
            return False
        return target.controller != obj.controller

    def death_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.COUNTER_ADDED, payload={
                    'object_id': obj.id, 'counter_type': '+1/+1', 'count': 1
                }, source=obj.id),
                Event(type=EventType.LIFE_CHANGE, payload={
                    'player': obj.controller, 'amount': 1
                }, source=obj.id)
            ]
        )

    interceptor = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=death_trigger,
        handler=death_handler,
        duration='while_on_battlefield'
    )

    return [interceptor]

VALGAVOTH_HARROWER_OF_SOULS = make_creature(
    name="Valgavoth, Harrower of Souls",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Elder", "Demon"},
    supertypes={"Legendary"},
    text="Flying, trample. Whenever another creature dies, put a +1/+1 counter on Valgavoth and you gain 1 life. At the beginning of your end step, each opponent sacrifices a creature.",
    setup_interceptors=valgavoth_setup
)


def valgavoth_terror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cheaper version - lifelink and deathtouch"""
    return []

VALGAVOTH_TERROR_EATER = make_creature(
    name="Valgavoth, Terror Eater",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying, lifelink, deathtouch. Whenever you sacrifice a creature, draw a card and lose 1 life.",
    setup_interceptors=valgavoth_terror_setup
)


def razorkin_needlehead_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie drain"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        events = []
        for opp in opponents:
            events.append(Event(type=EventType.LIFE_CHANGE, payload={
                'player': opp, 'amount': -1
            }, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={
            'player': obj.controller, 'amount': len(opponents)
        }, source=obj.id))
        return events
    return [make_eerie_trigger(obj, eerie_effect)]

RAZORKIN_NEEDLEHEAD = make_creature(
    name="Razorkin Needlehead",
    power=3, toughness=2,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Flying. Eerie - Whenever an enchantment enters or you unlock a Room, each opponent loses 1 life and you gain that much life.",
    setup_interceptors=razorkin_needlehead_setup
)


# --- Black Creatures ---

def devouring_horror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium +2/+2"""
    return make_delirium_bonus(obj, 2, 2)

DEVOURING_HORROR = make_creature(
    name="Devouring Horror",
    power=3, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Deathtouch. Delirium - Devouring Horror gets +2/+2 if there are four or more card types among cards in your graveyard.",
    setup_interceptors=devouring_horror_setup
)


def skullsnatcher_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB opponent discards"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        if opponents:
            return [Event(type=EventType.DISCARD, payload={
                'player': opponents[0], 'count': 1
            }, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

SKULLSNATCHER = make_creature(
    name="Skullsnatcher",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Menace. When Skullsnatcher enters, target opponent discards a card.",
    setup_interceptors=skullsnatcher_setup
)


FEAR_OF_LOST_TEETH = make_creature(
    name="Fear of Lost Teeth",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Enchantment creature. When Fear of Lost Teeth enters, each player sacrifices a creature."
)


def gravewaker_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB return creature from graveyard"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.RETURN_FROM_GRAVEYARD, payload={
            'controller': obj.controller, 'type': 'creature'
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

GRAVEWAKER = make_creature(
    name="Gravewaker",
    power=3, toughness=3,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Horror"},
    text="When Gravewaker enters, return target creature card from your graveyard to your hand.",
    setup_interceptors=gravewaker_setup
)


def soul_shredder_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack - opponent loses life equal to cards in graveyard"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        player = state.players.get(obj.controller)
        if not player or not opponents:
            return []
        grave_count = min(len(player.graveyard), 5)
        return [Event(type=EventType.LIFE_CHANGE, payload={
            'player': opponents[0], 'amount': -grave_count
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

SOUL_SHREDDER = make_creature(
    name="Soul Shredder",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying. Whenever Soul Shredder attacks, target opponent loses life equal to the number of cards in your graveyard, up to 5.",
    setup_interceptors=soul_shredder_setup
)


BLOOD_CURDLE_IMP = make_creature(
    name="Blood-Curdle Imp",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Imp"},
    text="Flying. When Blood-Curdle Imp dies, each opponent loses 1 life."
)


def lurking_fear_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cant be blocked except by 2+ creatures"""
    return []

LURKING_FEAR = make_creature(
    name="Lurking Fear",
    power=4, toughness=2,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Lurking Fear can't be blocked except by two or more creatures.",
    setup_interceptors=lurking_fear_setup
)


CORPSE_COLLECTOR = make_creature(
    name="Corpse Collector",
    power=2, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Deathtouch. {2}{B}, Sacrifice another creature: Draw a card."
)


MANIFEST_DARKNESS = make_creature(
    name="Manifest Darkness",
    power=3, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="When Manifest Darkness enters, manifest dread."
)


# --- Black Instants/Sorceries ---

FINAL_VENGEANCE = make_instant(
    name="Final Vengeance",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="As an additional cost to cast this spell, sacrifice a creature or pay 4 life. Destroy target creature."
)

SOUL_HARVEST = make_sorcery(
    name="Soul Harvest",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You gain life equal to the total toughness of creatures sacrificed this way."
)

INESCAPABLE_DOOM = make_sorcery(
    name="Inescapable Doom",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If you have delirium, return it to the battlefield under your control instead."
)


# =============================================================================
# RED CARDS - DESTRUCTION, AGGRESSION, FIRE
# =============================================================================

# --- Red Legendary Creatures ---

def arna_kennerud_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double damage from Rooms"""
    return []

ARNA_KENNERUD = make_creature(
    name="Arna Kennerud, Skycaptain",
    power=4, toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    supertypes={"Legendary"},
    text="Flying, vigilance. Whenever an enchantment you control is put into a graveyard from the battlefield, Arna Kennerud deals 3 damage to any target.",
    setup_interceptors=arna_kennerud_setup
)


def hellraiser_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - deal damage to each opponent"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.DAMAGE, payload={
            'target': opp, 'amount': 2, 'source': obj.id
        }, source=obj.id) for opp in opponents]
    return [make_attack_trigger(obj, attack_effect)]

HELLRAISER_SPAWN = make_creature(
    name="Hellraiser Spawn",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
    text="Haste. Whenever Hellraiser Spawn attacks, it deals 2 damage to each opponent.",
    setup_interceptors=hellraiser_setup
)


# --- Red Creatures ---

def inferno_elemental_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival - gets haste and +2/+0"""
    interceptors = make_survival_bonus(obj, 2, 0)

    def survival_keyword_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_survival(state, obj.controller, obj)

    interceptors.append(make_keyword_grant(obj, ['haste'], survival_keyword_filter))
    return interceptors

INFERNO_ELEMENTAL = make_creature(
    name="Inferno Elemental",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Survival - As long as you control a creature with power 2 or more greater than its base power, Inferno Elemental gets +2/+0 and has haste.",
    setup_interceptors=inferno_elemental_setup
)


def pyroclasm_horror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB deal 2 to each creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE_ALL_CREATURES, payload={
            'amount': 2, 'source': obj.id
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

PYROCLASM_HORROR = make_creature(
    name="Pyroclasm Horror",
    power=4, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Horror"},
    text="When Pyroclasm Horror enters, it deals 2 damage to each other creature.",
    setup_interceptors=pyroclasm_horror_setup
)


FEAR_OF_BURNING_ALIVE = make_creature(
    name="Fear of Burning Alive",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Nightmare"},
    text="Enchantment creature. When Fear of Burning Alive enters, it deals 3 damage to target creature or planeswalker."
)


def reckless_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - +2/+0"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.PUMP, payload={
            'object_id': obj.id, 'power': 2, 'toughness': 0, 'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

RECKLESS_SURVIVOR = make_creature(
    name="Reckless Survivor",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Survivor"},
    text="Whenever Reckless Survivor attacks, it gets +2/+0 until end of turn.",
    setup_interceptors=reckless_survivor_setup
)


HOUSE_DEMOLISHER = make_creature(
    name="House Demolisher",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
    text="Trample. When House Demolisher enters, destroy target artifact or enchantment."
)


def ember_screamer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium - gains menace"""
    def delirium_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_delirium(state, obj.controller)
    return [make_keyword_grant(obj, ['menace'], delirium_filter)]

EMBER_SCREAMER = make_creature(
    name="Ember Screamer",
    power=3, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Delirium - Ember Screamer has menace if there are four or more card types among cards in your graveyard.",
    setup_interceptors=ember_screamer_setup
)


FURIOUS_SPECTER = make_creature(
    name="Furious Specter",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Haste. When Furious Specter enters, it deals 1 damage to any target."
)


CHAOTIC_MANIFESTATION = make_creature(
    name="Chaotic Manifestation",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Horror"},
    text="Trample. When Chaotic Manifestation dies, it deals damage equal to its power to any target."
)


# --- Red Instants/Sorceries ---

VOLCANIC_SPITE = make_instant(
    name="Volcanic Spite",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Volcanic Spite deals 3 damage to target creature or planeswalker. You may discard a card. If you do, draw a card."
)

BURN_DOWN_THE_HOUSE = make_sorcery(
    name="Burn Down the House",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Choose one - Burn Down the House deals 5 damage divided as you choose among any number of target creatures and/or planeswalkers; or create three 1/1 red Devil creature tokens with 'When this creature dies, it deals 1 damage to any target.'"
)

DESPERATE_ESCAPE = make_instant(
    name="Desperate Escape",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control gets +2/+0 and gains haste until end of turn. If you have survival, it also gains first strike."
)


# =============================================================================
# GREEN CARDS - GROWTH, NATURE, BEASTS
# =============================================================================

# --- Green Legendary Creatures ---

def tyvar_forest_protector_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Elves get +1/+1, untap on creature ETB"""
    interceptors = []
    interceptors.extend(make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Elf")))

    def creature_etb_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        obj_id = event.payload.get('object_id')
        target = state.objects.get(obj_id)
        if not target:
            return False
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types)

    def creature_etb_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[
            Event(type=EventType.ADD_MANA, payload={
                'player': obj.controller, 'color': 'G', 'amount': 1
            }, source=obj.id)
        ])

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=creature_etb_filter,
        handler=creature_etb_handler,
        duration='while_on_battlefield'
    ))

    return interceptors

TYVAR_FOREST_PROTECTOR = make_creature(
    name="Tyvar, Roaming Hero",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Warrior"},
    supertypes={"Legendary"},
    text="Other Elf creatures you control get +1/+1. Whenever a creature enters under your control, add {G}.",
    setup_interceptors=tyvar_forest_protector_setup
)


def overgrown_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival - gets trample and +3/+3"""
    interceptors = make_survival_bonus(obj, 3, 3)

    def survival_keyword_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_survival(state, obj.controller, obj)

    interceptors.append(make_keyword_grant(obj, ['trample'], survival_keyword_filter))
    return interceptors

OVERGROWN_SURVIVOR = make_creature(
    name="Overgrown Survivor",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor"},
    supertypes={"Legendary"},
    text="Survival - As long as you control a creature with power 2 or more greater than its base power, Overgrown Survivor gets +3/+3 and has trample.",
    setup_interceptors=overgrown_survivor_setup
)


# --- Green Creatures ---

def vine_creeper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB put +1/+1 counter on target creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': 'target', 'counter_type': '+1/+1', 'count': 1
        }, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

VINE_CREEPER = make_creature(
    name="Vine Creeper",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="When Vine Creeper enters, put a +1/+1 counter on target creature.",
    setup_interceptors=vine_creeper_setup
)


def root_horror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium +3/+3"""
    return make_delirium_bonus(obj, 3, 3)

ROOT_HORROR = make_creature(
    name="Root Horror",
    power=3, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="Trample. Delirium - Root Horror gets +3/+3 if there are four or more card types among cards in your graveyard.",
    setup_interceptors=root_horror_setup
)


FEAR_OF_BEING_HUNTED = make_creature(
    name="Fear of Being Hunted",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Nightmare"},
    text="Enchantment creature. Flash. When Fear of Being Hunted enters, it fights target creature you don't control."
)


def undergrowth_beast_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Gets +1/+1 for each card in graveyard"""
    def graveyard_boost_filter(target: GameObject, state: GameState) -> bool:
        return target.id == obj.id

    def power_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_POWER:
            return False
        return event.payload.get('object_id') == obj.id

    def toughness_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        return event.payload.get('object_id') == obj.id

    def get_graveyard_count(state: GameState) -> int:
        player = state.players.get(obj.controller)
        return len(player.graveyard) if player else 0

    def power_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + get_graveyard_count(state)
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    def toughness_handler(event: Event, state: GameState) -> InterceptorResult:
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + get_graveyard_count(state)
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

UNDERGROWTH_BEAST = make_creature(
    name="Undergrowth Beast",
    power=0, toughness=0,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Beast"},
    text="Trample. Undergrowth Beast gets +1/+1 for each creature card in your graveyard.",
    setup_interceptors=undergrowth_beast_setup
)


HIDDEN_PREDATOR = make_creature(
    name="Hidden Predator",
    power=4, toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Flash. Reach. When Hidden Predator enters, you may have it fight target creature an opponent controls."
)


def sprouting_terror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Death trigger - create two 1/1 tokens"""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Saproling', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Saproling'}}
            }, source=obj.id),
            Event(type=EventType.CREATE_TOKEN, payload={
                'controller': obj.controller,
                'token': {'name': 'Saproling', 'power': 1, 'toughness': 1, 'colors': {Color.GREEN}, 'subtypes': {'Saproling'}}
            }, source=obj.id)
        ]
    return [make_death_trigger(obj, death_effect)]

SPROUTING_TERROR = make_creature(
    name="Sprouting Terror",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="When Sprouting Terror dies, create two 1/1 green Saproling creature tokens.",
    setup_interceptors=sprouting_terror_setup
)


ANCIENT_GROVE_KEEPER = make_creature(
    name="Ancient Grove Keeper",
    power=5, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach, vigilance. Other creatures you control have vigilance."
)


MANIFEST_UNDERGROWTH = make_creature(
    name="Manifest Undergrowth",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="When Manifest Undergrowth enters, manifest dread."
)


# --- Green Instants/Sorceries ---

NATURE_RECLAIMS = make_instant(
    name="Nature Reclaims",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Destroy target artifact or enchantment. Its controller gains 3 life."
)

PRIMAL_SURGE = make_sorcery(
    name="Primal Surge",
    mana_cost="{X}{G}{G}",
    colors={Color.GREEN},
    text="Distribute X +1/+1 counters among any number of target creatures you control."
)

OVERGROWTH = make_instant(
    name="Overgrowth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If you have survival, it also gains trample."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Legendary Multicolor Creatures ---

def tyvar_zimone_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Draw and counters synergy"""
    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id, 'counter_type': '+1/+1', 'count': 1
        }, source=obj.id)]

    def draw_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DRAW:
            return False
        return event.payload.get('player') == obj.controller

    def draw_handler(event: Event, state: GameState) -> InterceptorResult:
        new_events = draw_effect(event, state)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=new_events)

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=draw_filter,
        handler=draw_handler,
        duration='while_on_battlefield'
    )]

TYVAR_AND_ZIMONE = make_creature(
    name="Tyvar and Zimone, Partners",
    power=3, toughness=4,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Elf", "Human", "Warrior", "Wizard"},
    supertypes={"Legendary"},
    text="Whenever you draw a card, if it's your second draw this turn, put a +1/+1 counter on Tyvar and Zimone. {T}: Draw a card, then discard a card.",
    setup_interceptors=tyvar_zimone_setup
)


def marina_skovos_witch_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Eerie triggers deal damage"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        return [Event(type=EventType.DAMAGE, payload={
            'target': opp, 'amount': 2, 'source': obj.id
        }, source=obj.id) for opp in opponents]
    return [make_eerie_trigger(obj, eerie_effect)]

MARINA_SKOVOS_WITCH = make_creature(
    name="Marina Vendrell, Gloom Witch",
    power=3, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Warlock"},
    supertypes={"Legendary"},
    text="Deathtouch. Eerie - Whenever an enchantment enters or you unlock a Room, Marina deals 2 damage to each opponent.",
    setup_interceptors=marina_skovos_witch_setup
)


def the_master_of_keys_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rooms enter with both sides unlocked"""
    return []

THE_MASTER_OF_KEYS = make_creature(
    name="The Master of Keys",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit", "Noble"},
    supertypes={"Legendary"},
    text="Flying. Room enchantments you control enter with both doors unlocked. Whenever you unlock a Room, draw a card.",
    setup_interceptors=the_master_of_keys_setup
)


def overlord_of_the_balemurk_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB mill 4, return creature"""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [
            Event(type=EventType.MILL, payload={
                'player': obj.controller, 'count': 4
            }, source=obj.id),
            Event(type=EventType.RETURN_FROM_GRAVEYARD, payload={
                'controller': obj.controller, 'type': 'creature'
            }, source=obj.id)
        ]
    return [make_etb_trigger(obj, etb_effect)]

OVERLORD_OF_THE_BALEMURK = make_creature(
    name="Overlord of the Balemurk",
    power=4, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Elemental", "Horror"},
    supertypes={"Legendary"},
    text="Trample. When Overlord of the Balemurk enters, mill four cards, then return a creature card from your graveyard to your hand.",
    setup_interceptors=overlord_of_the_balemurk_setup
)


def the_wandering_rescuer_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Exile and return creatures"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.FLICKER, payload={
            'controller': obj.controller, 'type': 'creature'
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

THE_WANDERING_RESCUER = make_creature(
    name="The Wandering Rescuer",
    power=3, toughness=4,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit", "Knight"},
    supertypes={"Legendary"},
    text="Vigilance. Whenever The Wandering Rescuer attacks, exile another creature you control, then return it to the battlefield.",
    setup_interceptors=the_wandering_rescuer_setup
)


# --- Other Multicolor Creatures ---

def spectral_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Delirium - flying and lifelink"""
    def delirium_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_delirium(state, obj.controller)
    return [make_keyword_grant(obj, ['flying', 'lifelink'], delirium_filter)]

SPECTRAL_HUNTER = make_creature(
    name="Spectral Hunter",
    power=3, toughness=2,
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Spirit", "Assassin"},
    text="Delirium - Spectral Hunter has flying and lifelink if there are four or more card types among cards in your graveyard.",
    setup_interceptors=spectral_hunter_setup
)


GLOOM_STALKER = make_creature(
    name="Gloom Stalker",
    power=2, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Horror"},
    text="Menace. When Gloom Stalker enters, target opponent reveals their hand. You choose a nonland card from it. That player discards that card."
)


def bloodthorn_survivor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Survival - menace and deathtouch"""
    def survival_filter(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        return check_survival(state, obj.controller, obj)
    return [make_keyword_grant(obj, ['menace', 'deathtouch'], survival_filter)]

BLOODTHORN_SURVIVOR = make_creature(
    name="Bloodthorn Survivor",
    power=3, toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Survivor", "Warrior"},
    text="Survival - Bloodthorn Survivor has menace and deathtouch if you control a creature with power 2 or more greater than its base power.",
    setup_interceptors=bloodthorn_survivor_setup
)


WILDFIRE_ELEMENTAL = make_creature(
    name="Wildfire Elemental",
    power=4, toughness=3,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Elemental"},
    text="Trample, haste. When Wildfire Elemental enters, it deals damage to any target equal to the number of lands you control."
)


def twin_terror_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Attack trigger - create copy token"""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Twin Terror Copy', 'power': 2, 'toughness': 2,
                     'colors': {Color.BLUE, Color.RED}, 'subtypes': {'Illusion'},
                     'abilities': ['haste', 'exile_end_of_turn']}
        }, source=obj.id)]
    return [make_attack_trigger(obj, attack_effect)]

TWIN_TERROR = make_creature(
    name="Twin Terror",
    power=2, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Illusion", "Horror"},
    text="Whenever Twin Terror attacks, create a token that's a copy of it. That token is tapped and attacking. Exile it at end of combat.",
    setup_interceptors=twin_terror_setup
)


EERIE_INTERLUDE_KEEPER = make_creature(
    name="Eerie Interlude Keeper",
    power=2, toughness=4,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Spirit", "Druid"},
    text="Reach. Eerie - Whenever an enchantment enters or you unlock a Room, you gain 2 life."
)


# --- Multicolor Instants/Sorceries ---

HOUSE_DIVIDED = make_sorcery(
    name="House Divided",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Destroy all creatures. Each player creates a 1/1 white and black Spirit creature token with flying for each creature they controlled that was destroyed this way."
)

TERROR_OF_THE_PEAKS = make_instant(
    name="Terror of the Peaks",
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Terror of the Peaks deals 3 damage to any target. Draw a card."
)

ROOTS_OF_DESPAIR = make_sorcery(
    name="Roots of Despair",
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    text="Mill four cards. Return a creature card from your graveyard to the battlefield. It gains haste until end of turn."
)


# =============================================================================
# ROOM ENCHANTMENTS
# =============================================================================

def abandoned_nursery_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room - creatures get +1/+0, or create token"""
    def eerie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.CREATE_TOKEN, payload={
            'controller': obj.controller,
            'token': {'name': 'Spirit', 'power': 1, 'toughness': 1, 'colors': {Color.WHITE},
                     'subtypes': {'Spirit'}, 'abilities': ['flying']}
        }, source=obj.id)]
    return [make_eerie_trigger(obj, eerie_effect)]

ABANDONED_NURSERY = make_room(
    name="Abandoned Nursery // Ghostly Playroom",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+0. // {2}{W}: Unlock. When you unlock this Room, create a 1/1 white Spirit creature token with flying.",
    setup_interceptors=abandoned_nursery_setup
)


def bleeding_walls_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Room - drain life"""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        opponents = all_opponents(obj, state)
        events = []
        for opp in opponents:
            events.append(Event(type=EventType.LIFE_CHANGE, payload={
                'player': opp, 'amount': -1
            }, source=obj.id))
        events.append(Event(type=EventType.LIFE_CHANGE, payload={
            'player': obj.controller, 'amount': len(opponents)
        }, source=obj.id))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

BLEEDING_WALLS = make_room(
    name="Bleeding Walls // Dripping Ceiling",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, each opponent loses 1 life and you gain that much life. // {2}{B}: Unlock. Creatures get -1/-1 until end of turn.",
    setup_interceptors=bleeding_walls_setup
)


GRAND_BALLROOM = make_room(
    name="Grand Ballroom // Haunted Mirror",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Creatures you control have vigilance. // {3}{W}{U}: Unlock. When you unlock this Room, create a token that's a copy of target creature you control."
)


BURNING_KITCHEN = make_room(
    name="Burning Kitchen // Exploding Oven",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature you control attacks, it gets +1/+0 until end of turn. // {2}{R}: Unlock. When you unlock this Room, deal 3 damage to any target."
)


OVERGROWN_GREENHOUSE = make_room(
    name="Overgrown Greenhouse // Carnivorous Garden",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +0/+1. // {2}{G}: Unlock. When you unlock this Room, put two +1/+1 counters on target creature."
)


FLOODED_BASEMENT = make_room(
    name="Flooded Basement // Drowned Cellar",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an instant or sorcery spell, scry 1. // {2}{U}: Unlock. When you unlock this Room, draw two cards, then discard a card."
)


DARK_LIBRARY = make_room(
    name="Dark Library // Forbidden Archives",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, surveil 1. // {3}{B}: Unlock. When you unlock this Room, return target creature card from your graveyard to your hand."
)


PANIC_ROOM = make_room(
    name="Panic Room // Safe Haven",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Creatures you control have ward {1}. // {2}{W}: Unlock. Creatures you control are indestructible until end of turn."
)


TORTURE_CHAMBER = make_room(
    name="Torture Chamber // Execution Room",
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Whenever a creature an opponent controls dies, that player loses 1 life. // {3}{B}{R}: Unlock. Destroy target creature. Its controller loses life equal to its power."
)


FORGOTTEN_ATTIC = make_room(
    name="Forgotten Attic // Hidden Treasure",
    mana_cost="{2}",
    colors=set(),
    text="At the beginning of your upkeep, scry 1. // {3}: Unlock. When you unlock this Room, draw two cards."
)


SHATTERED_CONSERVATORY = make_room(
    name="Shattered Conservatory // Thorny Ruins",
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    text="Whenever a creature enters under your control, you gain 1 life. // {2}{G}{W}: Unlock. Create two 2/2 green and white Elemental creature tokens."
)


HAUNTED_THEATER = make_room(
    name="Haunted Theater // Phantom Stage",
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Creatures you control have menace. // {3}{U}{B}: Unlock. Target creature becomes a copy of another target creature until end of turn."
)


# =============================================================================
# ARTIFACTS
# =============================================================================

def skeleton_key_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature is unblockable, unlock discount"""
    return []

SKELETON_KEY = make_artifact(
    name="Skeleton Key",
    mana_cost="{1}",
    text="Equipped creature can't be blocked. Unlocking a Room costs {1} less. Equip {2}",
    setup_interceptors=skeleton_key_setup
)


HAUNTED_PORTRAIT = make_artifact(
    name="Haunted Portrait",
    mana_cost="{2}",
    text="When Haunted Portrait enters, create a 1/1 white Spirit creature token with flying. {3}, Sacrifice Haunted Portrait: Draw two cards."
)


TRAPPED_SOUL_VESSEL = make_artifact(
    name="Trapped Soul Vessel",
    mana_cost="{3}",
    text="When a creature dies, put a soul counter on Trapped Soul Vessel. {T}, Remove three soul counters: Draw a card and gain 3 life."
)


MYSTERIOUS_MUSIC_BOX = make_artifact(
    name="Mysterious Music Box",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. If you control an enchantment, add two mana of any one color instead."
)


BLOODSTAINED_AXE = make_artifact(
    name="Bloodstained Axe",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +2/+1. When equipped creature dies, draw a card. Equip {2}"
)


SURVEYORS_LANTERN = make_artifact(
    name="Surveyor's Lantern",
    mana_cost="{1}",
    text="{T}: Add one mana of any color. Activate only if you control two or more enchantments."
)


CANDELABRA_OF_SOULS = make_artifact(
    name="Candelabra of Souls",
    mana_cost="{3}",
    text="Whenever an enchantment enters under your control, you may pay {1}. If you do, draw a card."
)


FEAR_COLLECTOR = make_artifact(
    name="Fear Collector",
    mana_cost="{4}",
    text="Whenever a creature an opponent controls dies, create a 2/2 black Nightmare creature token."
)


def dread_mask_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Equipped creature has menace and intimidate"""
    return []

DREAD_MASK = make_artifact(
    name="Dread Mask",
    mana_cost="{1}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+0 and has menace. Equip {1}",
    setup_interceptors=dread_mask_setup
)


VALGAVOTHS_ALTAR = make_artifact(
    name="Valgavoth's Altar",
    mana_cost="{3}",
    text="Sacrifice a creature: Add two mana of any one color. If you sacrificed an enchantment creature, add three mana of any one color instead."
)


# =============================================================================
# LANDS
# =============================================================================

DUSKMOURN_MANOR = make_land(
    name="Duskmourn Manor",
    text="{T}: Add {C}. {2}, {T}: Add one mana of any color. Activate only if you control an enchantment."
)


HAUNTED_THRESHOLD = make_land(
    name="Haunted Threshold",
    text="Haunted Threshold enters tapped. When it enters, scry 1. {T}: Add {W} or {B}.",
    subtypes={"Plains", "Swamp"}
)


FORGOTTEN_HALLWAY = make_land(
    name="Forgotten Hallway",
    text="Forgotten Hallway enters tapped. When it enters, you may mill two cards. {T}: Add {U} or {B}.",
    subtypes={"Island", "Swamp"}
)


OVERGROWN_COURTYARD = make_land(
    name="Overgrown Courtyard",
    text="Overgrown Courtyard enters tapped. When it enters, you gain 1 life. {T}: Add {G} or {W}.",
    subtypes={"Forest", "Plains"}
)


BURNING_RUINS = make_land(
    name="Burning Ruins",
    text="Burning Ruins enters tapped. When it enters, deal 1 damage to any target. {T}: Add {R} or {B}.",
    subtypes={"Mountain", "Swamp"}
)


TWISTED_GARDEN = make_land(
    name="Twisted Garden",
    text="Twisted Garden enters tapped. When it enters, put a +1/+1 counter on target creature. {T}: Add {G} or {B}.",
    subtypes={"Forest", "Swamp"}
)


SPECTRAL_CHAPEL = make_land(
    name="Spectral Chapel",
    text="Spectral Chapel enters tapped. {T}: Add {W}. {1}{W}, {T}: Create a 1/1 white Spirit creature token with flying. Activate only if you control an enchantment."
)


NIGHTMARE_POOL = make_land(
    name="Nightmare Pool",
    text="Nightmare Pool enters tapped. {T}: Add {U} or {B}. {2}{U}{B}, {T}, Sacrifice Nightmare Pool: Draw two cards."
)


BLOODFIRE_HEARTH = make_land(
    name="Bloodfire Hearth",
    text="Bloodfire Hearth enters tapped. {T}: Add {B} or {R}. {2}{B}{R}, {T}: Each player sacrifices a creature."
)


THORNWOOD_GROVE = make_land(
    name="Thornwood Grove",
    text="Thornwood Grove enters tapped. {T}: Add {R} or {G}. Whenever you cast a creature spell, you may untap Thornwood Grove."
)


EERIE_GATEWAY = make_land(
    name="Eerie Gateway",
    text="{T}: Add {C}. {T}, Pay 3 life: Add one mana of any color."
)


# Basic lands
PLAINS_DSK = make_land("Plains", "{T}: Add {W}.", subtypes={"Plains"}, supertypes={"Basic"})
ISLAND_DSK = make_land("Island", "{T}: Add {U}.", subtypes={"Island"}, supertypes={"Basic"})
SWAMP_DSK = make_land("Swamp", "{T}: Add {B}.", subtypes={"Swamp"}, supertypes={"Basic"})
MOUNTAIN_DSK = make_land("Mountain", "{T}: Add {R}.", subtypes={"Mountain"}, supertypes={"Basic"})
FOREST_DSK = make_land("Forest", "{T}: Add {G}.", subtypes={"Forest"}, supertypes={"Basic"})


# =============================================================================
# ADDITIONAL WHITE CARDS
# =============================================================================

SANCTUARY_WARDEN = make_creature(
    name="Sanctuary Warden",
    power=5, toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying. When Sanctuary Warden enters, create two Shield counters on target creatures you control. Remove a shield counter from a creature you control: Draw a card."
)


FAITH_OF_THE_DEVOTED = make_enchantment(
    name="Faith of the Devoted",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Whenever you discard a card, you may pay {1}. If you do, each opponent loses 2 life and you gain 2 life."
)


ETHEREAL_ESCORT = make_creature(
    name="Ethereal Escort",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. When Ethereal Escort enters, target creature you control gains protection from the color of your choice until end of turn."
)


BEACON_OF_HOPE = make_instant(
    name="Beacon of Hope",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you have survival, create a 1/1 white Spirit creature token with flying."
)


# =============================================================================
# ADDITIONAL BLUE CARDS
# =============================================================================

SPECTRAL_SCHOLAR = make_creature(
    name="Spectral Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Wizard"},
    text="Flying. Whenever you cast an instant or sorcery spell, scry 1."
)


MIND_DRAIN = make_sorcery(
    name="Mind Drain",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Each opponent mills five cards. For each card milled this way, if it shares a card type with a card in your graveyard, draw a card."
)


ILLUSORY_GUARDIAN = make_creature(
    name="Illusory Guardian",
    power=4, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Illusion"},
    text="When Illusory Guardian becomes the target of a spell or ability, sacrifice it. When Illusory Guardian dies, draw two cards."
)


GLIMPSE_THE_UNKNOWN = make_instant(
    name="Glimpse the Unknown",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest into your graveyard."
)


# =============================================================================
# ADDITIONAL BLACK CARDS
# =============================================================================

NIGHTMARE_SHEPHERD = make_creature(
    name="Nightmare Shepherd",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon"},
    text="Flying. Whenever another nontoken creature you control dies, you may exile it. If you do, create a token that's a copy of that creature, except it's 1/1."
)


FEAST_ON_FEAR = make_sorcery(
    name="Feast on Fear",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards and loses 2 life. If you have delirium, they discard three cards instead."
)


SHADOW_REAPER = make_creature(
    name="Shadow Reaper",
    power=2, toughness=2,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Assassin"},
    text="Deathtouch. When Shadow Reaper enters, you lose 2 life."
)


DARK_BARGAIN = make_instant(
    name="Dark Bargain",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Look at the top three cards of your library. Put two into your hand and one into your graveyard. You lose 2 life."
)


# =============================================================================
# ADDITIONAL RED CARDS
# =============================================================================

RAGE_INCARNATE = make_creature(
    name="Rage Incarnate",
    power=5, toughness=3,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Avatar"},
    text="Trample, haste. At the beginning of your end step, sacrifice Rage Incarnate unless you attacked with three or more creatures this turn."
)


INFERNAL_OUTBURST = make_sorcery(
    name="Infernal Outburst",
    mana_cost="{X}{R}{R}",
    colors={Color.RED},
    text="Infernal Outburst deals X damage to each creature and each player."
)


PYROCLASTIC_SPECTER = make_creature(
    name="Pyroclastic Specter",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Flying. When Pyroclastic Specter deals combat damage to a player, it deals that much damage to target creature that player controls."
)


FIERY_TEMPER = make_instant(
    name="Fiery Temper",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Fiery Temper deals 3 damage to any target. Madness {R}"
)


# =============================================================================
# ADDITIONAL GREEN CARDS
# =============================================================================

ANCIENT_HORROR = make_creature(
    name="Ancient Horror",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Horror", "Beast"},
    text="Reach, trample. When Ancient Horror enters, destroy target artifact or enchantment."
)


NATURE_CLAIMS_ALL = make_sorcery(
    name="Nature Claims All",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Destroy all artifacts and enchantments. Each player creates a 1/1 green Saproling creature token for each permanent destroyed this way."
)


WILD_SURVIVOR = make_creature(
    name="Wild Survivor",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Survivor", "Scout"},
    text="Reach. Survival - Wild Survivor gets +2/+2 as long as you control a creature with power 2 or more greater than its base power."
)


VERDANT_EMBRACE = make_enchantment(
    name="Verdant Embrace",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Enchant creature. Enchanted creature gets +3/+3 and has trample. At the beginning of your upkeep, create a 1/1 green Saproling creature token."
)


# =============================================================================
# ADDITIONAL MULTICOLOR CARDS
# =============================================================================

DOOM_PORTENT = make_creature(
    name="Doom Portent",
    power=4, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Horror"},
    text="Flying. When Doom Portent enters, each opponent reveals their hand. You choose a nonland card from each hand. Those players discard those cards."
)


VENGEFUL_SPIRIT = make_creature(
    name="Vengeful Spirit",
    power=3, toughness=3,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Spirit"},
    text="Flying, lifelink. When Vengeful Spirit dies, exile target creature an opponent controls."
)


PRIMAL_NIGHTMARE = make_creature(
    name="Primal Nightmare",
    power=5, toughness=5,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Nightmare", "Beast"},
    text="Trample. When Primal Nightmare enters, mill four cards. Then return a creature card from your graveyard to the battlefield."
)


EMBER_TWINS = make_creature(
    name="Ember Twins",
    power=2, toughness=2,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="When Ember Twins enters, create a 2/2 red and white Human Survivor creature token."
)


ARCANE_INVESTIGATOR = make_creature(
    name="Arcane Investigator",
    power=2, toughness=3,
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Detective"},
    text="Whenever you draw your second card each turn, put a +1/+1 counter on Arcane Investigator."
)


CHAOS_HORROR = make_creature(
    name="Chaos Horror",
    power=4, toughness=4,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Nightmare", "Horror"},
    text="Menace. At the beginning of your end step, each player sacrifices a creature. You gain 2 life for each creature sacrificed this way."
)


# =============================================================================
# ADDITIONAL COMMON/UNCOMMON WHITE
# =============================================================================

STEADFAST_SURVIVOR = make_creature(
    name="Steadfast Survivor",
    power=2, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Survivor"},
    text="When Steadfast Survivor enters, you gain 2 life."
)

GHOSTLY_ESCORT = make_creature(
    name="Ghostly Escort",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Flying. When Ghostly Escort dies, create a 1/1 white Spirit creature token with flying."
)

PROTECTIVE_SPIRIT = make_creature(
    name="Protective Spirit",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
    text="Defender. Other creatures you control have ward {1}."
)

DAWN_BRINGER = make_creature(
    name="Dawn Bringer",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying. When Dawn Bringer enters, exile target enchantment an opponent controls until Dawn Bringer leaves the battlefield."
)

SANCTIFIED_CHARGE = make_instant(
    name="Sanctified Charge",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+1 and gain first strike until end of turn."
)

GUIDING_LIGHT = make_instant(
    name="Guiding Light",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature gains indestructible until end of turn. Scry 1."
)

HOPE_AGAINST_DARKNESS = make_enchantment(
    name="Hope Against Darkness",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Whenever a creature enters under your control, you gain 1 life. {3}{W}: Create a 1/1 white Spirit creature token with flying."
)

ANGELIC_OBSERVER = make_creature(
    name="Angelic Observer",
    power=2, toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
    text="Flying, vigilance."
)

HOUSE_WARDEN = make_creature(
    name="House Warden",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="First strike. When House Warden enters, exile target creature an opponent controls with power 3 or less until House Warden leaves the battlefield."
)


# =============================================================================
# ADDITIONAL COMMON/UNCOMMON BLUE
# =============================================================================

FLEETING_MEMORY = make_creature(
    name="Fleeting Memory",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. When Fleeting Memory enters, scry 2."
)

PHANTOM_THIEF = make_creature(
    name="Phantom Thief",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit", "Rogue"},
    text="Whenever Phantom Thief deals combat damage to a player, draw a card."
)

REALITY_FRACTURE = make_instant(
    name="Reality Fracture",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If that creature was an enchantment, draw a card."
)

THOUGHT_ERASURE = make_sorcery(
    name="Thought Erasure",
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. Surveil 1."
)

SPECTRAL_SILENCE = make_instant(
    name="Spectral Silence",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target activated or triggered ability."
)

EERIE_INTUITION = make_sorcery(
    name="Eerie Intuition",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card. If you discard an enchantment card, draw another card."
)

HOUSE_SPECTER = make_creature(
    name="House Specter",
    power=3, toughness=1,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. House Specter can't be blocked as long as you control an enchantment."
)

MANIFEST_REFLECTION = make_creature(
    name="Manifest Reflection",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Illusion"},
    text="When Manifest Reflection enters, manifest dread."
)

UNSEEN_WATCHER = make_creature(
    name="Unseen Watcher",
    power=2, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flash. Flying. When Unseen Watcher enters, tap target creature an opponent controls. It doesn't untap during its controller's next untap step."
)


# =============================================================================
# ADDITIONAL COMMON/UNCOMMON BLACK
# =============================================================================

DREAD_HARVESTER = make_creature(
    name="Dread Harvester",
    power=2, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Warlock"},
    text="When Dread Harvester dies, each opponent loses 1 life and you gain 1 life."
)

NIGHTMARE_SPAWN = make_creature(
    name="Nightmare Spawn",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare"},
    text="Menace. Delirium - Nightmare Spawn gets +1/+1 if there are four or more card types among cards in your graveyard."
)

GRIM_AWAKENING = make_sorcery(
    name="Grim Awakening",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. It gains haste. Sacrifice it at the beginning of the next end step."
)

TERROR_WITHIN = make_instant(
    name="Terror Within",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. If that creature would die this turn, exile it instead."
)

SOUL_DRAIN = make_sorcery(
    name="Soul Drain",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. You gain 2 life."
)

HOUSE_OF_DECAY = make_enchantment(
    name="House of Decay",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Whenever a creature dies, its controller loses 1 life."
)

CONSUMING_SHADOWS = make_creature(
    name="Consuming Shadows",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
    text="Menace. When Consuming Shadows enters, target opponent discards a card."
)

CORPSE_CRAWLER = make_creature(
    name="Corpse Crawler",
    power=2, toughness=3,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="Deathtouch. {2}{B}, Exile a creature card from your graveyard: Draw a card."
)

ENDLESS_NIGHTMARE = make_creature(
    name="Endless Nightmare",
    power=5, toughness=4,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare", "Horror"},
    text="Deathtouch. Whenever Endless Nightmare attacks, defending player discards a card."
)


# =============================================================================
# ADDITIONAL COMMON/UNCOMMON RED
# =============================================================================

RAGING_SPECTER = make_creature(
    name="Raging Specter",
    power=3, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Spirit"},
    text="Haste. When Raging Specter enters, it deals 1 damage to any target."
)

INFERNAL_SURGE = make_instant(
    name="Infernal Surge",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn."
)

WRATHFUL_ERUPTION = make_sorcery(
    name="Wrathful Eruption",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Wrathful Eruption deals 4 damage divided as you choose among any number of target creatures and/or planeswalkers."
)

BLAZING_HORROR = make_creature(
    name="Blazing Horror",
    power=4, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Horror"},
    text="Trample. When Blazing Horror dies, it deals 2 damage to any target."
)

CHAOTIC_IMPULSE = make_instant(
    name="Chaotic Impulse",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Exile the top two cards of your library. Until end of turn, you may play those cards."
)

FIRE_OF_DUSKMOURN = make_sorcery(
    name="Fire of Duskmourn",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Fire of Duskmourn deals 4 damage to target creature or planeswalker. If you control an enchantment, it deals 5 damage instead."
)

BLOODFIRE_ELEMENTAL = make_creature(
    name="Bloodfire Elemental",
    power=4, toughness=1,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Haste. Sacrifice Bloodfire Elemental: It deals 4 damage to any target."
)

DESTRUCTIVE_RAMPAGE = make_sorcery(
    name="Destructive Rampage",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Destroy target artifact. Destructive Rampage deals 2 damage to that artifact's controller."
)

HOUSE_ARSONIST = make_creature(
    name="House Arsonist",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Survivor"},
    text="When House Arsonist enters, destroy target artifact or enchantment."
)


# =============================================================================
# ADDITIONAL COMMON/UNCOMMON GREEN
# =============================================================================

FOREST_CREEPER = make_creature(
    name="Forest Creeper",
    power=2, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Forest Creeper gets +1/+1 as long as you control an enchantment."
)

OVERGROWN_HORROR = make_creature(
    name="Overgrown Horror",
    power=5, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="Trample. When Overgrown Horror enters, you may destroy target artifact or enchantment."
)

NATURE_FURY = make_instant(
    name="Nature's Fury",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +2/+2 and gains trample until end of turn."
)

VERDANT_GROWTH = make_sorcery(
    name="Verdant Growth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. You gain 3 life."
)

THORNWOOD_GUARDIAN = make_creature(
    name="Thornwood Guardian",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Treefolk"},
    text="Reach. When Thornwood Guardian enters, put a +1/+1 counter on each other creature you control."
)

PRIMAL_ROAR = make_instant(
    name="Primal Roar",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. If you have survival, your creature gets +2/+2 until end of turn first."
)

WILD_OVERGROWTH = make_enchantment(
    name="Wild Overgrowth",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control have +1/+1. Whenever a creature enters under your control, if it has power 4 or greater, draw a card."
)

GROVE_TENDER = make_creature(
    name="Grove Tender",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Elf", "Druid"},
    text="{T}: Add {G}. If you control an enchantment, add {G}{G} instead."
)

LURKING_VINES = make_creature(
    name="Lurking Vines",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
    text="Flash. Reach. When Lurking Vines enters, you may have it fight target creature with flying."
)


# =============================================================================
# ADDITIONAL MULTICOLOR COMMON/UNCOMMON
# =============================================================================

SPIRIT_GUIDE = make_creature(
    name="Spirit Guide",
    power=2, toughness=2,
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. When Spirit Guide enters, draw a card, then discard a card."
)

SHADOWBLOOD_CULTIST = make_creature(
    name="Shadowblood Cultist",
    power=3, toughness=1,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Warlock"},
    text="Menace. When Shadowblood Cultist dies, it deals 2 damage to any target."
)

NATURE_SPIRIT = make_creature(
    name="Nature's Spirit",
    power=3, toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Spirit"},
    text="Vigilance. When Nature's Spirit enters, you gain 3 life."
)

STORM_WRAITH = make_creature(
    name="Storm Wraith",
    power=3, toughness=2,
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Elemental", "Spirit"},
    text="Flying, haste. When Storm Wraith enters, it deals 1 damage to any target."
)

DEATH_BLOOM = make_creature(
    name="Death Bloom",
    power=2, toughness=2,
    mana_cost="{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Zombie"},
    text="Deathtouch. When Death Bloom dies, return target creature card with mana value 3 or less from your graveyard to your hand."
)

EERIE_MANIFESTATION = make_instant(
    name="Eerie Manifestation",
    mana_cost="{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Exile target creature. Its controller creates a 1/1 white and black Spirit creature token with flying."
)

CHAOTIC_GROWTH = make_sorcery(
    name="Chaotic Growth",
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Target creature gets +4/+4 and gains trample and haste until end of turn."
)

MIND_TERROR = make_sorcery(
    name="Mind Terror",
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Target player discards two cards. You draw a card."
)

BLAZING_SPIRIT = make_creature(
    name="Blazing Spirit",
    power=2, toughness=1,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Spirit"},
    text="Flying, haste. When Blazing Spirit enters, it deals 1 damage to target creature or planeswalker."
)

CORRUPTED_GROWTH = make_creature(
    name="Corrupted Growth",
    power=4, toughness=3,
    mana_cost="{2}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Horror"},
    text="Trample. When Corrupted Growth enters, mill four cards. Return a creature card from your graveyard to your hand."
)


# =============================================================================
# ADDITIONAL ROOMS
# =============================================================================

CRUMBLING_STAIRCASE = make_room(
    name="Crumbling Staircase // Collapsed Landing",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Whenever a creature attacks, it gets +1/+0 until end of turn. // {2}{R}: Unlock. When you unlock this Room, Crumbling Staircase deals 2 damage to each creature."
)

SILENT_NURSERY = make_room(
    name="Silent Nursery // Awakened Crib",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Creature tokens you control get +1/+0. // {3}{B}: Unlock. When you unlock this Room, create two 1/1 black Spirit creature tokens."
)

MISTY_CONSERVATORY = make_room(
    name="Misty Conservatory // Toxic Garden",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Creatures you control have reach. // {2}{G}: Unlock. When you unlock this Room, target creature gets +3/+3 until end of turn."
)

ECHOING_HALLS = make_room(
    name="Echoing Halls // Chamber of Whispers",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever you cast an instant or sorcery, draw a card, then discard a card. // {3}{U}: Unlock. Draw two cards."
)


# =============================================================================
# ADDITIONAL ARTIFACTS
# =============================================================================

SURVIVORS_PACK = make_artifact(
    name="Survivor's Pack",
    mana_cost="{2}",
    text="{T}: Add one mana of any color. {2}, {T}, Sacrifice Survivor's Pack: Draw a card."
)

CURSED_MIRROR = make_artifact(
    name="Cursed Mirror",
    mana_cost="{3}",
    text="When Cursed Mirror enters, create a token that's a copy of target creature you control except it's an artifact in addition to its other types."
)

DUSKMOURN_RELIC = make_artifact(
    name="Duskmourn Relic",
    mana_cost="{1}",
    text="When Duskmourn Relic enters, scry 1. {2}, Sacrifice Duskmourn Relic: Draw a card."
)

RUSTED_CHAINS = make_artifact(
    name="Rusted Chains",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+2. Equipped creature can't attack alone. Equip {1}"
)

SPIRIT_LANTERN = make_artifact(
    name="Spirit Lantern",
    mana_cost="{2}",
    text="{T}: Add {C}. {3}, {T}: Create a 1/1 white Spirit creature token with flying."
)


# =============================================================================
# ADDITIONAL LANDS
# =============================================================================

HIDDEN_CHAMBER = make_land(
    name="Hidden Chamber",
    text="Hidden Chamber enters tapped. {T}: Add {W} or {U}. {4}{W}{U}, {T}, Sacrifice Hidden Chamber: Create a 4/4 white and blue Spirit creature token with flying."
)

TWISTED_CORRIDOR = make_land(
    name="Twisted Corridor",
    text="Twisted Corridor enters tapped. {T}: Add {U} or {R}. When Twisted Corridor enters, scry 1."
)

BLOOD_STAINED_FLOOR = make_land(
    name="Blood-Stained Floor",
    text="Blood-Stained Floor enters tapped. {T}: Add {B} or {R}. {3}{B}{R}, {T}: Each player sacrifices a creature."
)

OVERGROWN_WING = make_land(
    name="Overgrown Wing",
    text="Overgrown Wing enters tapped. {T}: Add {G} or {W}. When Overgrown Wing enters, you gain 1 life."
)


# =============================================================================
# MORE WHITE CARDS
# =============================================================================

CLEANSING_LIGHT = make_instant(
    name="Cleansing Light",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    text="Exile target creature or enchantment."
)

SPIRIT_CONGREGATION = make_sorcery(
    name="Spirit Congregation",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Create three 1/1 white Spirit creature tokens with flying."
)

DUSKMOURN_KNIGHT = make_creature(
    name="Duskmourn Knight",
    power=3, toughness=2,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Knight"},
    text="First strike, vigilance. Duskmourn Knight gets +1/+1 as long as you control an enchantment."
)

BANISHING_LIGHT = make_enchantment(
    name="Banishing Light",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When Banishing Light enters, exile target nonland permanent an opponent controls until Banishing Light leaves the battlefield."
)


# =============================================================================
# MORE BLUE CARDS
# =============================================================================

MEMORY_DELUGE = make_instant(
    name="Memory Deluge",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="Look at the top four cards of your library. Put two into your hand and two into your graveyard. Flashback {5}{U}{U}"
)

SPECTRAL_BINDING = make_enchantment(
    name="Spectral Binding",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Enchant creature. Enchanted creature doesn't untap during its controller's untap step. {3}{U}: Return Spectral Binding to its owner's hand."
)

GHOSTFORM = make_instant(
    name="Ghostform",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Up to two target creatures can't be blocked this turn."
)

HAUNTING_ECHO = make_creature(
    name="Haunting Echo",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Spirit"},
    text="Flying. When Haunting Echo enters, return target instant or sorcery card from your graveyard to your hand."
)


# =============================================================================
# MORE BLACK CARDS
# =============================================================================

VILE_ENTOMBMENT = make_sorcery(
    name="Vile Entombment",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses 2 life."
)

NIGHTMARE_EMBRACE = make_enchantment(
    name="Nightmare Embrace",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="Enchant creature. Enchanted creature gets -3/-3. When enchanted creature dies, return Nightmare Embrace to its owner's hand."
)

DESPAIR_INCARNATE = make_creature(
    name="Despair Incarnate",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Nightmare", "Horror"},
    text="Menace. At the beginning of your upkeep, each opponent discards a card. If a player can't, you draw a card."
)

DREAD_RETURN = make_sorcery(
    name="Dread Return",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Return target creature card from your graveyard to the battlefield. Flashback - Sacrifice three creatures."
)


# =============================================================================
# MORE RED CARDS
# =============================================================================

INFERNAL_GRASP = make_instant(
    name="Infernal Grasp",
    mana_cost="{R}{R}",
    colors={Color.RED},
    text="Infernal Grasp deals 5 damage to target creature or planeswalker."
)

BURNING_VENGEANCE = make_enchantment(
    name="Burning Vengeance",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Whenever you cast a spell from your graveyard, Burning Vengeance deals 2 damage to any target."
)

LIGHTNING_STRIKE = make_instant(
    name="Lightning Strike",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Lightning Strike deals 3 damage to any target."
)

HELLFIRE_ELEMENTAL = make_creature(
    name="Hellfire Elemental",
    power=5, toughness=4,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Elemental"},
    text="Trample. When Hellfire Elemental enters, it deals 3 damage to each other creature."
)


# =============================================================================
# MORE GREEN CARDS
# =============================================================================

BEAST_WITHIN = make_instant(
    name="Beast Within",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Destroy target permanent. Its controller creates a 3/3 green Beast creature token."
)

ABUNDANT_GROWTH = make_enchantment(
    name="Abundant Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Enchant land. When Abundant Growth enters, draw a card. Enchanted land has '{T}: Add one mana of any color.'"
)

TITANIC_GROWTH = make_instant(
    name="Titanic Growth",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)

PRIMORDIAL_HORROR = make_creature(
    name="Primordial Horror",
    power=6, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Beast", "Horror"},
    text="Trample, reach. When Primordial Horror enters, destroy target artifact or enchantment an opponent controls."
)


# =============================================================================
# MORE MULTICOLOR CARDS
# =============================================================================

DIMIR_INFILTRATOR = make_creature(
    name="Dimir Infiltrator",
    power=1, toughness=3,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Spirit"},
    text="Dimir Infiltrator can't be blocked. Transmute {1}{U}{B}"
)

RAKDOS_HEADLINER = make_creature(
    name="Rakdos Headliner",
    power=3, toughness=3,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Devil"},
    text="Haste. Echo - Discard a card."
)

SIMIC_ASCENDANCY = make_enchantment(
    name="Simic Ascendancy",
    mana_cost="{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    text="Whenever you put one or more +1/+1 counters on a creature, put that many growth counters on Simic Ascendancy. At the beginning of your upkeep, if Simic Ascendancy has twenty or more growth counters, you win the game."
)

AZORIUS_CHARM = make_instant(
    name="Azorius Charm",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Choose one - Creatures you control gain lifelink until end of turn; or draw a card; or put target attacking or blocking creature on top of its owner's library."
)

ORZHOV_ENFORCER = make_creature(
    name="Orzhov Enforcer",
    power=1, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Rogue"},
    text="Deathtouch. Afterlife 1"
)

GRUUL_SPELLBREAKER = make_creature(
    name="Gruul Spellbreaker",
    power=3, toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Ogre", "Warrior"},
    text="Riot. Trample. As long as it's your turn, you and Gruul Spellbreaker have hexproof."
)

SELESNYA_EVANGEL = make_creature(
    name="Selesnya Evangel",
    power=1, toughness=2,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Elf", "Cleric"},
    text="{1}, {T}: Create a 1/1 green Saproling creature token."
)

IZZET_CHARM = make_instant(
    name="Izzet Charm",
    mana_cost="{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Choose one - Counter target noncreature spell unless its controller pays {2}; or Izzet Charm deals 2 damage to target creature; or draw two cards, then discard two cards."
)

GOLGARI_ROTWURM = make_creature(
    name="Golgari Rotwurm",
    power=5, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Zombie", "Wurm"},
    text="{B}, Sacrifice a creature: Target player loses 1 life."
)

BOROS_CHALLENGER = make_creature(
    name="Boros Challenger",
    power=2, toughness=3,
    mana_cost="{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Mentor. {2}{R}{W}: Boros Challenger gets +1/+1 until end of turn."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

DUSKMOURN_CARDS = {
    # WHITE LEGENDARY
    "Winter, Cynical Opportunist": WINTER_CEDRIC,
    "Niko Aris, Bound and Battling": NIKO_ARIS,
    "Aminatou, Veil Piercer": AMINATOU_VEIL_PIERCER,

    # WHITE CREATURES
    "Glimmerburst Guide": GLIMMERBURST_GUIDE,
    "Sanctuary Seeker": SANCTUARY_SEEKER,
    "Ethereal Armor Bearer": ETHEREAL_ARMOR_BEARER,
    "Sheltered Wanderer": SHELTERED_WANDERER,
    "Fear of Exposure": FEAR_OF_EXPOSURE,
    "Hallowed Respite Keeper": HALLOWED_RESPITE_KEEPER,
    "Light of the House": LIGHT_OF_THE_HOUSE,
    "Trapped Angel": TRAPPED_ANGEL,
    "Flickering Survivor": FLICKERING_SURVIVOR,
    "House Guardian": HOUSE_GUARDIAN,
    "Sanctuary Warden": SANCTUARY_WARDEN,
    "Ethereal Escort": ETHEREAL_ESCORT,

    # WHITE SPELLS
    "Final Light": FINAL_LIGHT,
    "Survival Instinct": SURVIVAL_INSTINCT,
    "Shelter in Light": SHELTER_IN_LIGHT,
    "Blessed Sanctuary": BLESSED_SANCTUARY,
    "Faith of the Devoted": FAITH_OF_THE_DEVOTED,
    "Beacon of Hope": BEACON_OF_HOPE,

    # BLUE LEGENDARY
    "Zimone, Mystery Unraveler": ZIMONE_MYSTERY_UNRAVELER,
    "Kaito, Dancing Shadow": KAITO_DANCING_SHADOW,

    # BLUE CREATURES
    "Phantom Investigator": PHANTOM_INVESTIGATOR,
    "Thought Stalker": THOUGHT_STALKER,
    "Mirror Echo": MIRROR_ECHO,
    "Fear of Impostors": FEAR_OF_IMPOSTORS,
    "Wandering Apparition": WANDERING_APPARITION,
    "Lost in the Maze": LOST_IN_THE_MAZE,
    "Dread Specter": DREAD_SPECTER,
    "Manifest Dread Seer": MANIFEST_DREAD_SEER,
    "Echo of Despair": ECHO_OF_DESPAIR,
    "Spectral Scholar": SPECTRAL_SCHOLAR,
    "Illusory Guardian": ILLUSORY_GUARDIAN,

    # BLUE SPELLS
    "Terror Reflected": TERROR_REFLECTED,
    "Unsettling Vision": UNSETTLING_VISION,
    "Disturbing Revelation": DISTURBING_REVELATION,
    "Mind Drain": MIND_DRAIN,
    "Glimpse the Unknown": GLIMPSE_THE_UNKNOWN,

    # BLACK LEGENDARY
    "Valgavoth, Harrower of Souls": VALGAVOTH_HARROWER_OF_SOULS,
    "Valgavoth, Terror Eater": VALGAVOTH_TERROR_EATER,
    "Razorkin Needlehead": RAZORKIN_NEEDLEHEAD,

    # BLACK CREATURES
    "Devouring Horror": DEVOURING_HORROR,
    "Skullsnatcher": SKULLSNATCHER,
    "Fear of Lost Teeth": FEAR_OF_LOST_TEETH,
    "Gravewaker": GRAVEWAKER,
    "Soul Shredder": SOUL_SHREDDER,
    "Blood-Curdle Imp": BLOOD_CURDLE_IMP,
    "Lurking Fear": LURKING_FEAR,
    "Corpse Collector": CORPSE_COLLECTOR,
    "Manifest Darkness": MANIFEST_DARKNESS,
    "Nightmare Shepherd": NIGHTMARE_SHEPHERD,
    "Shadow Reaper": SHADOW_REAPER,

    # BLACK SPELLS
    "Final Vengeance": FINAL_VENGEANCE,
    "Soul Harvest": SOUL_HARVEST,
    "Inescapable Doom": INESCAPABLE_DOOM,
    "Feast on Fear": FEAST_ON_FEAR,
    "Dark Bargain": DARK_BARGAIN,

    # RED LEGENDARY
    "Arna Kennerud, Skycaptain": ARNA_KENNERUD,
    "Hellraiser Spawn": HELLRAISER_SPAWN,

    # RED CREATURES
    "Inferno Elemental": INFERNO_ELEMENTAL,
    "Pyroclasm Horror": PYROCLASM_HORROR,
    "Fear of Burning Alive": FEAR_OF_BURNING_ALIVE,
    "Reckless Survivor": RECKLESS_SURVIVOR,
    "House Demolisher": HOUSE_DEMOLISHER,
    "Ember Screamer": EMBER_SCREAMER,
    "Furious Specter": FURIOUS_SPECTER,
    "Chaotic Manifestation": CHAOTIC_MANIFESTATION,
    "Rage Incarnate": RAGE_INCARNATE,
    "Pyroclastic Specter": PYROCLASTIC_SPECTER,

    # RED SPELLS
    "Volcanic Spite": VOLCANIC_SPITE,
    "Burn Down the House": BURN_DOWN_THE_HOUSE,
    "Desperate Escape": DESPERATE_ESCAPE,
    "Infernal Outburst": INFERNAL_OUTBURST,
    "Fiery Temper": FIERY_TEMPER,

    # GREEN LEGENDARY
    "Tyvar, Roaming Hero": TYVAR_FOREST_PROTECTOR,
    "Overgrown Survivor": OVERGROWN_SURVIVOR,

    # GREEN CREATURES
    "Vine Creeper": VINE_CREEPER,
    "Root Horror": ROOT_HORROR,
    "Fear of Being Hunted": FEAR_OF_BEING_HUNTED,
    "Undergrowth Beast": UNDERGROWTH_BEAST,
    "Hidden Predator": HIDDEN_PREDATOR,
    "Sprouting Terror": SPROUTING_TERROR,
    "Ancient Grove Keeper": ANCIENT_GROVE_KEEPER,
    "Manifest Undergrowth": MANIFEST_UNDERGROWTH,
    "Ancient Horror": ANCIENT_HORROR,
    "Wild Survivor": WILD_SURVIVOR,

    # GREEN SPELLS
    "Nature Reclaims": NATURE_RECLAIMS,
    "Primal Surge": PRIMAL_SURGE,
    "Overgrowth": OVERGROWTH,
    "Nature Claims All": NATURE_CLAIMS_ALL,
    "Verdant Embrace": VERDANT_EMBRACE,

    # MULTICOLOR LEGENDARY
    "Tyvar and Zimone, Partners": TYVAR_AND_ZIMONE,
    "Marina Vendrell, Gloom Witch": MARINA_SKOVOS_WITCH,
    "The Master of Keys": THE_MASTER_OF_KEYS,
    "Overlord of the Balemurk": OVERLORD_OF_THE_BALEMURK,
    "The Wandering Rescuer": THE_WANDERING_RESCUER,

    # MULTICOLOR CREATURES
    "Spectral Hunter": SPECTRAL_HUNTER,
    "Gloom Stalker": GLOOM_STALKER,
    "Bloodthorn Survivor": BLOODTHORN_SURVIVOR,
    "Wildfire Elemental": WILDFIRE_ELEMENTAL,
    "Twin Terror": TWIN_TERROR,
    "Eerie Interlude Keeper": EERIE_INTERLUDE_KEEPER,
    "Doom Portent": DOOM_PORTENT,
    "Vengeful Spirit": VENGEFUL_SPIRIT,
    "Primal Nightmare": PRIMAL_NIGHTMARE,
    "Ember Twins": EMBER_TWINS,
    "Arcane Investigator": ARCANE_INVESTIGATOR,
    "Chaos Horror": CHAOS_HORROR,

    # MULTICOLOR SPELLS
    "House Divided": HOUSE_DIVIDED,
    "Terror of the Peaks": TERROR_OF_THE_PEAKS,
    "Roots of Despair": ROOTS_OF_DESPAIR,

    # ROOMS
    "Abandoned Nursery // Ghostly Playroom": ABANDONED_NURSERY,
    "Bleeding Walls // Dripping Ceiling": BLEEDING_WALLS,
    "Grand Ballroom // Haunted Mirror": GRAND_BALLROOM,
    "Burning Kitchen // Exploding Oven": BURNING_KITCHEN,
    "Overgrown Greenhouse // Carnivorous Garden": OVERGROWN_GREENHOUSE,
    "Flooded Basement // Drowned Cellar": FLOODED_BASEMENT,
    "Dark Library // Forbidden Archives": DARK_LIBRARY,
    "Panic Room // Safe Haven": PANIC_ROOM,
    "Torture Chamber // Execution Room": TORTURE_CHAMBER,
    "Forgotten Attic // Hidden Treasure": FORGOTTEN_ATTIC,
    "Shattered Conservatory // Thorny Ruins": SHATTERED_CONSERVATORY,
    "Haunted Theater // Phantom Stage": HAUNTED_THEATER,

    # ARTIFACTS
    "Skeleton Key": SKELETON_KEY,
    "Haunted Portrait": HAUNTED_PORTRAIT,
    "Trapped Soul Vessel": TRAPPED_SOUL_VESSEL,
    "Mysterious Music Box": MYSTERIOUS_MUSIC_BOX,
    "Bloodstained Axe": BLOODSTAINED_AXE,
    "Surveyor's Lantern": SURVEYORS_LANTERN,
    "Candelabra of Souls": CANDELABRA_OF_SOULS,
    "Fear Collector": FEAR_COLLECTOR,
    "Dread Mask": DREAD_MASK,
    "Valgavoth's Altar": VALGAVOTHS_ALTAR,

    # LANDS
    "Duskmourn Manor": DUSKMOURN_MANOR,
    "Haunted Threshold": HAUNTED_THRESHOLD,
    "Forgotten Hallway": FORGOTTEN_HALLWAY,
    "Overgrown Courtyard": OVERGROWN_COURTYARD,
    "Burning Ruins": BURNING_RUINS,
    "Twisted Garden": TWISTED_GARDEN,
    "Spectral Chapel": SPECTRAL_CHAPEL,
    "Nightmare Pool": NIGHTMARE_POOL,
    "Bloodfire Hearth": BLOODFIRE_HEARTH,
    "Thornwood Grove": THORNWOOD_GROVE,
    "Eerie Gateway": EERIE_GATEWAY,

    # BASIC LANDS
    "Plains": PLAINS_DSK,
    "Island": ISLAND_DSK,
    "Swamp": SWAMP_DSK,
    "Mountain": MOUNTAIN_DSK,
    "Forest": FOREST_DSK,

    # ADDITIONAL WHITE
    "Steadfast Survivor": STEADFAST_SURVIVOR,
    "Ghostly Escort": GHOSTLY_ESCORT,
    "Protective Spirit": PROTECTIVE_SPIRIT,
    "Dawn Bringer": DAWN_BRINGER,
    "Sanctified Charge": SANCTIFIED_CHARGE,
    "Guiding Light": GUIDING_LIGHT,
    "Hope Against Darkness": HOPE_AGAINST_DARKNESS,
    "Angelic Observer": ANGELIC_OBSERVER,
    "House Warden": HOUSE_WARDEN,

    # ADDITIONAL BLUE
    "Fleeting Memory": FLEETING_MEMORY,
    "Phantom Thief": PHANTOM_THIEF,
    "Reality Fracture": REALITY_FRACTURE,
    "Thought Erasure": THOUGHT_ERASURE,
    "Spectral Silence": SPECTRAL_SILENCE,
    "Eerie Intuition": EERIE_INTUITION,
    "House Specter": HOUSE_SPECTER,
    "Manifest Reflection": MANIFEST_REFLECTION,
    "Unseen Watcher": UNSEEN_WATCHER,

    # ADDITIONAL BLACK
    "Dread Harvester": DREAD_HARVESTER,
    "Nightmare Spawn": NIGHTMARE_SPAWN,
    "Grim Awakening": GRIM_AWAKENING,
    "Terror Within": TERROR_WITHIN,
    "Soul Drain": SOUL_DRAIN,
    "House of Decay": HOUSE_OF_DECAY,
    "Consuming Shadows": CONSUMING_SHADOWS,
    "Corpse Crawler": CORPSE_CRAWLER,
    "Endless Nightmare": ENDLESS_NIGHTMARE,

    # ADDITIONAL RED
    "Raging Specter": RAGING_SPECTER,
    "Infernal Surge": INFERNAL_SURGE,
    "Wrathful Eruption": WRATHFUL_ERUPTION,
    "Blazing Horror": BLAZING_HORROR,
    "Chaotic Impulse": CHAOTIC_IMPULSE,
    "Fire of Duskmourn": FIRE_OF_DUSKMOURN,
    "Bloodfire Elemental": BLOODFIRE_ELEMENTAL,
    "Destructive Rampage": DESTRUCTIVE_RAMPAGE,
    "House Arsonist": HOUSE_ARSONIST,

    # ADDITIONAL GREEN
    "Forest Creeper": FOREST_CREEPER,
    "Overgrown Horror": OVERGROWN_HORROR,
    "Nature's Fury": NATURE_FURY,
    "Verdant Growth": VERDANT_GROWTH,
    "Thornwood Guardian": THORNWOOD_GUARDIAN,
    "Primal Roar": PRIMAL_ROAR,
    "Wild Overgrowth": WILD_OVERGROWTH,
    "Grove Tender": GROVE_TENDER,
    "Lurking Vines": LURKING_VINES,

    # ADDITIONAL MULTICOLOR
    "Spirit Guide": SPIRIT_GUIDE,
    "Shadowblood Cultist": SHADOWBLOOD_CULTIST,
    "Nature's Spirit": NATURE_SPIRIT,
    "Storm Wraith": STORM_WRAITH,
    "Death Bloom": DEATH_BLOOM,
    "Eerie Manifestation": EERIE_MANIFESTATION,
    "Chaotic Growth": CHAOTIC_GROWTH,
    "Mind Terror": MIND_TERROR,
    "Blazing Spirit": BLAZING_SPIRIT,
    "Corrupted Growth": CORRUPTED_GROWTH,

    # ADDITIONAL ROOMS
    "Crumbling Staircase // Collapsed Landing": CRUMBLING_STAIRCASE,
    "Silent Nursery // Awakened Crib": SILENT_NURSERY,
    "Misty Conservatory // Toxic Garden": MISTY_CONSERVATORY,
    "Echoing Halls // Chamber of Whispers": ECHOING_HALLS,

    # ADDITIONAL ARTIFACTS
    "Survivor's Pack": SURVIVORS_PACK,
    "Cursed Mirror": CURSED_MIRROR,
    "Duskmourn Relic": DUSKMOURN_RELIC,
    "Rusted Chains": RUSTED_CHAINS,
    "Spirit Lantern": SPIRIT_LANTERN,

    # ADDITIONAL LANDS
    "Hidden Chamber": HIDDEN_CHAMBER,
    "Twisted Corridor": TWISTED_CORRIDOR,
    "Blood-Stained Floor": BLOOD_STAINED_FLOOR,
    "Overgrown Wing": OVERGROWN_WING,

    # MORE WHITE
    "Cleansing Light": CLEANSING_LIGHT,
    "Spirit Congregation": SPIRIT_CONGREGATION,
    "Duskmourn Knight": DUSKMOURN_KNIGHT,
    "Banishing Light": BANISHING_LIGHT,

    # MORE BLUE
    "Memory Deluge": MEMORY_DELUGE,
    "Spectral Binding": SPECTRAL_BINDING,
    "Ghostform": GHOSTFORM,
    "Haunting Echo": HAUNTING_ECHO,

    # MORE BLACK
    "Vile Entombment": VILE_ENTOMBMENT,
    "Nightmare Embrace": NIGHTMARE_EMBRACE,
    "Despair Incarnate": DESPAIR_INCARNATE,
    "Dread Return": DREAD_RETURN,

    # MORE RED
    "Infernal Grasp": INFERNAL_GRASP,
    "Burning Vengeance": BURNING_VENGEANCE,
    "Lightning Strike": LIGHTNING_STRIKE,
    "Hellfire Elemental": HELLFIRE_ELEMENTAL,

    # MORE GREEN
    "Beast Within": BEAST_WITHIN,
    "Abundant Growth": ABUNDANT_GROWTH,
    "Titanic Growth": TITANIC_GROWTH,
    "Primordial Horror": PRIMORDIAL_HORROR,

    # MORE MULTICOLOR
    "Dimir Infiltrator": DIMIR_INFILTRATOR,
    "Rakdos Headliner": RAKDOS_HEADLINER,
    "Simic Ascendancy": SIMIC_ASCENDANCY,
    "Azorius Charm": AZORIUS_CHARM,
    "Orzhov Enforcer": ORZHOV_ENFORCER,
    "Gruul Spellbreaker": GRUUL_SPELLBREAKER,
    "Selesnya Evangel": SELESNYA_EVANGEL,
    "Izzet Charm": IZZET_CHARM,
    "Golgari Rotwurm": GOLGARI_ROTWURM,
    "Boros Challenger": BOROS_CHALLENGER,
}

print(f"Loaded {len(DUSKMOURN_CARDS)} Duskmourn: House of Horror cards")
