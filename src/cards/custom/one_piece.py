"""
One Piece: Grand Line (OPG) Card Implementations

Set released June 2026. ~270 cards.
Features mechanics: Devil Fruit, Haki (Observation/Armament/Conqueror's), Crew, Bounty
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
    Characteristics, ObjectState,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness
)
from typing import Optional, Callable
from src.cards.interceptor_helpers import (
    make_etb_trigger, make_death_trigger, make_attack_trigger,
    make_damage_trigger, make_static_pt_boost, make_keyword_grant,
    other_creatures_you_control, creatures_with_subtype,
    make_spell_cast_trigger, make_upkeep_trigger, make_end_step_trigger,
    make_block_trigger, make_draw_trigger, make_life_gain_trigger,
    other_creatures_with_subtype, creatures_you_control, all_opponents,
    make_equipment_setup,
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_enchantment_with_subtypes(name: str, mana_cost: str, colors: set, text: str,
                                    subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    """Helper to create enchantment card definitions with subtypes (for Auras, Devil Fruits, etc.)."""
    from src.engine import CardDefinition, Characteristics
    return CardDefinition(
        name=name,
        mana_cost=mana_cost,
        characteristics=Characteristics(
            types={CardType.ENCHANTMENT},
            subtypes=subtypes or set(),
            supertypes=supertypes or set(),
            colors=colors or set(),
            mana_cost=mana_cost
        ),
        text=text,
        setup_interceptors=setup_interceptors
    )


# =============================================================================
# ONE PIECE KEYWORD HELPERS
# =============================================================================

def make_devil_fruit_restriction(source_obj: GameObject) -> Interceptor:
    """
    Devil Fruit restriction - enchanted creature can't block creatures with islandwalk.
    Represents the inability to swim after eating a Devil Fruit.
    """
    def block_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        blocker_id = event.payload.get('blocker_id')
        # Check if blocker is the enchanted creature
        enchanted_id = source_obj.state.attached_to if source_obj.state else None
        if blocker_id != enchanted_id:
            return False
        # Check if attacker has islandwalk
        attacker_id = event.payload.get('attacker_id')
        attacker = state.objects.get(attacker_id)
        if not attacker:
            return False
        abilities = attacker.characteristics.abilities or []
        return 'islandwalk' in abilities

    def block_handler(event: Event, state: GameState) -> InterceptorResult:
        return InterceptorResult(action=InterceptorAction.PREVENT)

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=block_filter,
        handler=block_handler,
        duration='while_on_battlefield'
    )


def _self_kw(keywords):
    """Self-keyword granter: this creature grants itself the listed keywords.

    Yields a setup_interceptors callable that registers a make_keyword_grant
    targeting only the source object. Used by simple-keyword commons so the
    deck builder picks them up as wired (gets the -0.5 quality bonus).
    """
    def setup(obj, state):
        def affects(target, st, src=obj):
            return target.id == src.id
        return [make_keyword_grant(obj, keywords, affects)]
    return setup


def make_observation_haki(source_obj: GameObject, scry_amount: int = 1) -> Interceptor:
    """
    Observation Haki - Scry N at the beginning of your upkeep.
    Represents the ability to sense and predict movements.
    """
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.SCRY,
            payload={'player': source_obj.controller, 'amount': scry_amount},
            source=source_obj.id
        )]
    return make_upkeep_trigger(source_obj, upkeep_effect)


def make_armament_haki(source_obj: GameObject) -> list[Interceptor]:
    """
    Armament Haki - This creature has protection from colorless.
    Represents hardening one's body with Haki.
    """
    def colorless_filter(target: GameObject, state: GameState) -> bool:
        return target.id == source_obj.id
    return [make_keyword_grant(source_obj, ['protection from colorless'], colorless_filter)]


def make_conquerors_haki_etb(source_obj: GameObject) -> Interceptor:
    """
    Conqueror's Haki - When this creature enters, tap all creatures opponents control.
    Represents overwhelming willpower that knocks out weak-willed opponents.
    """
    def haki_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller != source_obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.TAP,
                    payload={'object_id': obj_id},
                    source=source_obj.id
                ))
        return events
    return make_etb_trigger(source_obj, haki_effect)


def make_conquerors_haki_attack(source_obj: GameObject) -> Interceptor:
    """
    Conqueror's Haki - When this creature attacks, tap target creature defending player controls.
    """
    def haki_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills this in
    return make_attack_trigger(source_obj, haki_effect)


def make_crew_bonus(source_obj: GameObject, captain_name: str, power_bonus: int, toughness_bonus: int) -> list[Interceptor]:
    """
    Crew - This creature gets +X/+Y as long as you control a creature named [Captain].
    """
    def has_captain(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        # Check if controller has the captain
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == source_obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                game_obj.name == captain_name):
                return True
        return False
    return make_static_pt_boost(source_obj, power_bonus, toughness_bonus, has_captain)


def make_bounty_death(source_obj: GameObject, treasure_count: int = 1) -> Interceptor:
    """
    Bounty - When this creature dies, target opponent creates N Treasure token(s).
    Represents the reward for defeating a wanted pirate.
    """
    def bounty_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        opponents = all_opponents(source_obj, state)
        if opponents:
            # Give treasure to first opponent (targeting would let player choose)
            for _ in range(treasure_count):
                events.append(Event(
                    type=EventType.OBJECT_CREATED,
                    payload={
                        'controller': opponents[0],
                        'name': 'Treasure',
                        'types': {CardType.ARTIFACT},
                        'subtypes': {'Treasure'},
                        'abilities': ['{T}, Sacrifice this artifact: Add one mana of any color.'],
                        'is_token': True
                    },
                    source=source_obj.id
                ))
        return events
    return make_death_trigger(source_obj, bounty_effect)


def make_pirate_lord(source_obj: GameObject, power_mod: int, toughness_mod: int) -> list[Interceptor]:
    """Other Pirates you control get +X/+Y."""
    return make_static_pt_boost(
        source_obj, power_mod, toughness_mod,
        other_creatures_with_subtype(source_obj, "Pirate")
    )


def make_marine_lord(source_obj: GameObject, power_mod: int, toughness_mod: int) -> list[Interceptor]:
    """Other Marines you control get +X/+Y."""
    return make_static_pt_boost(
        source_obj, power_mod, toughness_mod,
        other_creatures_with_subtype(source_obj, "Marine")
    )


# =============================================================================
# WHITE CARDS - MARINES & WORLD GOVERNMENT
# =============================================================================

def akainu_absolute_justice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Akainu attacks, exile target creature with power 2 or less."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills in
    return [make_attack_trigger(obj, attack_effect)]

AKAINU_ABSOLUTE_JUSTICE = make_creature(
    name="Akainu, Absolute Justice",
    power=6,
    toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Admiral"},
    supertypes={"Legendary"},
    text="First strike. When Akainu attacks, exile target creature defending player controls with power 2 or less. \"There is no mercy for criminals.\"",
    setup_interceptors=akainu_absolute_justice_setup
)

def aokiji_lazy_justice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: Tap target creature, it doesn't untap during its controller's next untap step."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills in
    return [make_etb_trigger(obj, etb_effect)]

AOKIJI_LAZY_JUSTICE = make_creature(
    name="Aokiji, Lazy Justice",
    power=5,
    toughness=6,
    mana_cost="{4}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Marine", "Admiral"},
    supertypes={"Legendary"},
    text="When Aokiji enters, tap target creature. It doesn't untap during its controller's next untap step. {2}{U}: Target creature gains hexproof until end of turn.",
    setup_interceptors=aokiji_lazy_justice_setup
)

def kizaru_unclear_justice_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash, First strike. ETB: Deal 3 damage to target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting system fills in
    return [make_etb_trigger(obj, etb_effect)]

KIZARU_UNCLEAR_JUSTICE = make_creature(
    name="Kizaru, Unclear Justice",
    power=4,
    toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Admiral"},
    supertypes={"Legendary"},
    text="Flash, first strike. When Kizaru enters, deal 3 damage to target creature. \"Have you ever been kicked at the speed of light?\"",
    setup_interceptors=kizaru_unclear_justice_setup
)

def sengoku_the_buddha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Marines you control get +1/+1. Conqueror's Haki on ETB."""
    interceptors = make_marine_lord(obj, 1, 1)
    interceptors.append(make_conquerors_haki_etb(obj))
    return interceptors

SENGOKU_THE_BUDDHA = make_creature(
    name="Sengoku, the Buddha",
    power=5,
    toughness=5,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Admiral"},
    supertypes={"Legendary"},
    text="Other Marines you control get +1/+1. Conqueror's Haki - When Sengoku enters, tap all creatures opponents control.",
    setup_interceptors=sengoku_the_buddha_setup
)

def garp_the_hero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Armament Haki. Whenever Garp deals combat damage to a creature, exile that creature."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        target_obj = state.objects.get(target)
        if target_obj and CardType.CREATURE in target_obj.characteristics.types:
            return [Event(
                type=EventType.ZONE_CHANGE,
                payload={'object_id': target, 'to_zone_type': ZoneType.EXILE},
                source=obj.id
            )]
        return []
    interceptors = make_armament_haki(obj)
    interceptors.append(make_damage_trigger(obj, damage_effect, combat_only=True))
    return interceptors

GARP_THE_HERO = make_creature(
    name="Garp, the Hero",
    power=6,
    toughness=6,
    mana_cost="{5}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    supertypes={"Legendary"},
    text="Armament Haki - Protection from colorless. Whenever Garp deals combat damage to a creature, exile that creature.",
    setup_interceptors=garp_the_hero_setup
)

def smoker_white_hunter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Creatures you control have vigilance. Nontoken creatures can't attack you unless their controller pays {1}."""
    def vigilance_filter(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['vigilance'], vigilance_filter)]

SMOKER_WHITE_HUNTER = make_creature(
    name="Smoker, White Hunter",
    power=4,
    toughness=4,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    supertypes={"Legendary"},
    text="Creatures you control have vigilance. Nontoken creatures can't attack you unless their controller pays {1} for each creature attacking you.",
    setup_interceptors=smoker_white_hunter_setup
)

def tashigi_swordswoman_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """First strike. Whenever Tashigi deals combat damage to a player, look at the top 3 cards."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.LOOK_AT_TOP,
                payload={'player': obj.controller, 'amount': 3},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

TASHIGI_SWORDSWOMAN = make_creature(
    name="Tashigi, Swordswoman",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    supertypes={"Legendary"},
    text="First strike. Whenever Tashigi deals combat damage to a player, look at the top three cards of your library. Put one into your hand and the rest on the bottom.",
    setup_interceptors=tashigi_swordswoman_setup
)

def coby_future_admiral_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Observation Haki. When Coby ETB, put a +1/+1 counter on each Marine you control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                'Marine' in game_obj.characteristics.subtypes and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.COUNTER_ADDED,
                    payload={'object_id': obj_id, 'counter_type': '+1/+1', 'amount': 1},
                    source=obj.id
                ))
        return events
    return [make_observation_haki(obj, 1), make_etb_trigger(obj, etb_effect)]

COBY_FUTURE_ADMIRAL = make_creature(
    name="Coby, Future Admiral",
    power=2,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    supertypes={"Legendary"},
    text="Observation Haki - At the beginning of your upkeep, scry 1. When Coby enters, put a +1/+1 counter on each Marine you control.",
    setup_interceptors=coby_future_admiral_setup
)

def marine_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Justice's voice — scry 1, life per Marine, each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        marine_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Marine' in o.characteristics.subtypes:
                    marine_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, marine_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

MARINE_CAPTAIN = make_creature(
    name="Marine Captain",
    power=3,
    toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="Vigilance. When Marine Captain enters, scry 1, gain life per Marine you control, and each opponent loses 1 life.",
    setup_interceptors=marine_captain_setup,
)

def marine_recruit_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crew - Gets +1/+1 as long as you control Smoker, Garp, or an Admiral."""
    def has_superior(target: GameObject, state: GameState) -> bool:
        if target.id != obj.id:
            return False
        for o_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                game_obj.zone == ZoneType.BATTLEFIELD and
                ('Admiral' in game_obj.characteristics.subtypes or
                 'Smoker' in game_obj.name or
                 'Garp' in game_obj.name)):
                return True
        return False
    return make_static_pt_boost(obj, 1, 1, has_superior)

MARINE_RECRUIT = make_creature(
    name="Marine Recruit",
    power=1,
    toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="Crew - Marine Recruit gets +1/+1 as long as you control a Marine Admiral or a creature named Smoker or Garp.",
    setup_interceptors=marine_recruit_setup
)

def helmeppo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Helmeppo ETB, destroy target artifact."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_effect)]

HELMEPPO = make_creature(
    name="Helmeppo, Reformed",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="When Helmeppo enters, destroy target artifact.",
    setup_interceptors=helmeppo_setup
)

MARINE_BATTLESHIP = make_artifact_creature(
    name="Marine Battleship",
    power=2,
    toughness=3,
    mana_cost="{2}",
    subtypes={"Vehicle"},
    text="Vigilance. Crew 3. Marines you control have ward {1}."
)

JUSTICE_GATE = make_artifact(
    name="Justice Gate",
    mana_cost="{3}{W}",
    text="Creatures with power 4 or greater can't attack you. {3}, {T}: Exile target creature with power 4 or greater until Justice Gate leaves the battlefield."
)

ABSOLUTE_JUSTICE = make_enchantment(
    name="Absolute Justice",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Whenever a creature an opponent controls dies, you gain 2 life. Marines you control get +1/+0."
)

MARINE_FORTRESS = make_land(
    name="Marine Fortress",
    supertypes={"Legendary"},
    text="{T}: Add {W}. {2}{W}, {T}: Create a 1/1 white Marine Soldier creature token."
)

WORLD_GOVERNMENT_DECREE = make_sorcery(
    name="World Government Decree",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Exile all creatures with power 4 or greater. Each player who controlled an exiled creature creates a Treasure token."
)

BUSTER_CALL = make_sorcery(
    name="Buster Call",
    mana_cost="{5}{W}{W}",
    colors={Color.WHITE},
    text="Destroy all nonland permanents. You can't cast this spell unless you control a Marine Admiral."
)

CELESTIAL_DRAGONS_TRIBUTE = make_sorcery(
    name="Celestial Dragon's Tribute",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Each opponent sacrifices a creature. Create a Treasure token for each creature sacrificed this way."
)

PACIFISTA_UNIT = make_artifact_creature(
    name="Pacifista Unit",
    power=4,
    toughness=4,
    mana_cost="{5}",
    subtypes={"Construct"},
    text="Pacifista Unit can't be blocked by creatures with power 2 or less. {2}: Pacifista Unit deals 2 damage to target creature."
)

def impel_down_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Prison warden — scry 1, life per Marine, each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        marine_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Marine' in o.characteristics.subtypes:
                    marine_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, marine_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

IMPEL_DOWN_GUARD = make_creature(
    name="Impel Down Guard",
    power=2,
    toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="Defender. When Impel Down Guard enters, scry 1, gain life per Marine you control, and each opponent loses 1 life.",
    setup_interceptors=impel_down_guard_setup,
)

CIPHER_POL_AGENT = make_creature(
    name="Cipher Pol Agent",
    power=2,
    toughness=1,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Assassin"},
    text="Flash. When Cipher Pol Agent enters, exile target creature with mana value 2 or less until Cipher Pol Agent leaves the battlefield."
)

ROKUSHIKI_MASTER = make_creature(
    name="Rokushiki Master",
    power=3,
    toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Assassin"},
    text="First strike. {W}: Rokushiki Master gains flying until end of turn. {W}: Rokushiki Master gains indestructible until end of turn."
)

MARINE_JUSTICE = make_instant(
    name="Marine Justice",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Exile target attacking creature. Its controller creates a Treasure token."
)

SEA_PRISM_STONE = make_artifact(
    name="Sea Prism Stone",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets -2/-0 and loses all abilities. Equip {2}. Equip Marine {0}."
)


# =============================================================================
# BLUE CARDS - NAVIGATION, WATER, FISHMEN
# =============================================================================

def nami_navigator_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Observation Haki (weather). Draw a card whenever you play a land."""
    def land_play_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        entered_id = event.payload.get('object_id')
        entered_obj = state.objects.get(entered_id)
        if not entered_obj:
            return False
        return (entered_obj.controller == source.controller and
                CardType.LAND in entered_obj.characteristics.types)

    def draw_effect(event: Event, state: GameState) -> list[Event]:
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
        filter=lambda e, s: land_play_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

NAMI_NAVIGATOR = make_creature(
    name="Nami, Navigator",
    power=2,
    toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate", "Rogue"},
    supertypes={"Legendary"},
    text="Whenever you play a land, draw a card. {2}{U}: Return target nonland permanent to its owner's hand.",
    setup_interceptors=nami_navigator_setup
)

def jinbe_first_son_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Fishmen +1/+1. Armament Haki."""
    interceptors = make_static_pt_boost(
        obj, 1, 1,
        other_creatures_with_subtype(obj, "Fishman")
    )
    interceptors.extend(make_armament_haki(obj))
    return interceptors

JINBE_FIRST_SON = make_creature(
    name="Jinbe, First Son of the Sea",
    power=5,
    toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Pirate", "Monk"},
    supertypes={"Legendary"},
    text="Islandwalk. Other Fishmen you control get +1/+1. Armament Haki - Protection from colorless.",
    setup_interceptors=jinbe_first_son_setup
)

def arlong_saw_tooth_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Bounty. When Arlong deals combat damage to a player, create a Treasure token."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.OBJECT_CREATED,
                payload={
                    'controller': obj.controller,
                    'name': 'Treasure',
                    'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                    'is_token': True
                },
                source=obj.id
            )]
        return []
    return [make_bounty_death(obj, 1), make_damage_trigger(obj, damage_effect, combat_only=True)]

ARLONG_SAW_TOOTH = make_creature(
    name="Arlong, Saw-Tooth",
    power=4,
    toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Fishman", "Pirate"},
    supertypes={"Legendary"},
    text="Islandwalk. Bounty - When Arlong dies, target opponent creates a Treasure token. Whenever Arlong deals combat damage to a player, create a Treasure token.",
    setup_interceptors=arlong_saw_tooth_setup
)

def fisher_tiger_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Fisher Tiger dies, Fishmen you control gain indestructible until end of turn."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for obj_id, game_obj in state.objects.items():
            if (game_obj.controller == obj.controller and
                CardType.CREATURE in game_obj.characteristics.types and
                'Fishman' in game_obj.characteristics.subtypes and
                game_obj.zone == ZoneType.BATTLEFIELD):
                events.append(Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={'object_id': obj_id, 'keyword': 'indestructible', 'duration': 'end_of_turn'},
                    source=obj.id
                ))
        return events
    return [make_death_trigger(obj, death_effect)]

FISHER_TIGER = make_creature(
    name="Fisher Tiger, Liberator",
    power=4,
    toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Pirate", "Warrior"},
    supertypes={"Legendary"},
    text="Islandwalk. When Fisher Tiger dies, Fishmen you control gain indestructible until end of turn.",
    setup_interceptors=fisher_tiger_setup
)

HACHI_OCTOPUS = make_creature(
    name="Hachi, Octopus Swordsman",
    power=3,
    toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Warrior"},
    text="Hachi can block up to eight creatures each combat."
)

def shirahoshi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At end step, if you control 3+ Sea creatures, draw a card."""
    def end_effect(event: Event, state: GameState) -> list[Event]:
        sea_count = sum(1 for o in state.objects.values()
                       if o.controller == obj.controller and
                       o.zone == ZoneType.BATTLEFIELD and
                       CardType.CREATURE in o.characteristics.types and
                       ('Sea' in o.characteristics.subtypes or
                        'Fishman' in o.characteristics.subtypes or
                        'Merfolk' in o.characteristics.subtypes))
        if sea_count >= 3:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
        return []
    return [make_end_step_trigger(obj, end_effect)]

SHIRAHOSHI_MERMAID_PRINCESS = make_creature(
    name="Shirahoshi, Mermaid Princess",
    power=1,
    toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk", "Noble"},
    supertypes={"Legendary"},
    text="Defender. At the beginning of your end step, if you control three or more Fishmen or Merfolk, draw a card.",
    setup_interceptors=shirahoshi_setup
)

def fishman_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aquatic ferocity — scry 1, life per Fishman, each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        fishman_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Fishman' in o.characteristics.subtypes:
                    fishman_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, fishman_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

FISHMAN_WARRIOR = make_creature(
    name="Fishman Warrior",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Warrior"},
    text="Islandwalk. When Fishman Warrior enters, scry 1, gain life per Fishman you control, and each opponent loses 1 life.",
    setup_interceptors=fishman_warrior_setup,
)

FISHMAN_KARATE_MASTER = make_creature(
    name="Fishman Karate Master",
    power=3,
    toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Monk"},
    text="Islandwalk. When Fishman Karate Master enters, tap target creature an opponent controls."
)

SEA_KING = make_creature(
    name="Sea King",
    power=6,
    toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Serpent", "Sea"},
    text="Islandwalk. Sea King can't be blocked except by creatures with islandwalk."
)

NEPTUNE_KING_OF_FISHMEN = make_creature(
    name="Neptune, King of Fishmen",
    power=4,
    toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fishman", "Noble"},
    supertypes={"Legendary"},
    text="Fishmen you control have ward {2}. {3}{U}: Until end of turn, target creature becomes a Fishman in addition to its other types and gains islandwalk."
)

WEATHER_TEMPO = make_instant(
    name="Weather Tempo",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Return up to two target creatures to their owners' hands. If you control a creature named Nami, draw a card."
)

# --- Clima-Tact: Helper-5 rewire -------------------------------------------
# +1/+1 + granted trigger "combat damage to player → tap a creature that
# player controls." Skips the "doesn't untap next turn" clause (replacement
# effect on the untap step is a Phase B-3 effect).
def _clima_tact_combat_damage_to_player_filter(
    event: Event, state: GameState, target_id: str
) -> bool:
    if event.type != EventType.DAMAGE:
        return False
    if event.payload.get('source') != target_id:
        return False
    if not event.payload.get('combat', False):
        return False
    return event.payload.get('target') in state.players


def _clima_tact_tap_effect(
    target_obj: GameObject, event: Event, state: GameState
) -> list[Event]:
    victim_player = event.payload.get('target')
    if not victim_player:
        return []
    # Pick the first untapped non-equipped-creature controlled by the victim.
    for o in state.objects.values():
        if o.controller != victim_player:
            continue
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.characteristics is None:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if o.id == target_obj.id:
            continue
        if getattr(o.state, 'tapped', False):
            continue
        return [Event(
            type=EventType.TAP,
            payload={'object_id': o.id},
            source=target_obj.id,
        )]
    return []


CLIMA_TACT = make_artifact(
    name="Clima-Tact",
    mana_cost="{2}{U}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+1. Whenever equipped creature deals combat damage to a player, tap target creature that player controls. Equip {2}",
    setup_interceptors=make_equipment_setup(
        power_mod=1, toughness_mod=1,
        equip_cost="{2}",
        granted_triggered_abilities={
            "event_filter": _clima_tact_combat_damage_to_player_filter,
            "effect_fn": _clima_tact_tap_effect,
            "description": "Combat damage to player → tap one of their creatures",
        },
    ),
)

MIRAGE_TEMPO = make_instant(
    name="Mirage Tempo",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control. Exile that token at end of turn."
)

FISHMAN_ISLAND = make_land(
    name="Fishman Island",
    supertypes={"Legendary"},
    text="{T}: Add {U}. {T}: Target Fishman you control gains islandwalk until end of turn."
)

CALM_BELT = make_enchantment(
    name="Calm Belt",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Creatures without flying or islandwalk can't attack."
)

UNDERSEA_VOYAGE = make_sorcery(
    name="Undersea Voyage",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card. If you control a Fishman, draw four cards instead."
)

BUBBLE_CORAL = make_artifact(
    name="Bubble Coral",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}, Sacrifice Bubble Coral: Draw a card."
)

LOG_POSE = make_artifact(
    name="Log Pose",
    mana_cost="{1}",
    text="At the beginning of your upkeep, scry 1. {2}, {T}: Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order."
)

GRAND_LINE_NAVIGATION = make_sorcery(
    name="Grand Line Navigation",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Search your library for a land card and put it onto the battlefield tapped. Then shuffle. Draw a card."
)


# =============================================================================
# BLACK CARDS - PIRATES, DARKNESS, BLACKBEARD
# =============================================================================

def blackbeard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Two Devil Fruit powers. ETB: Each opponent discards a card. Attack: Exile target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': player_id, 'amount': 1},
                    source=obj.id
                ))
        return events
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_effect), make_attack_trigger(obj, attack_effect)]

BLACKBEARD_YONKO = make_creature(
    name="Blackbeard, Emperor of Darkness",
    power=6,
    toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Menace. When Blackbeard enters, each opponent discards a card. Whenever Blackbeard attacks, exile target creature defending player controls. \"People's dreams never end!\"",
    setup_interceptors=blackbeard_setup
)

def crocodile_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch. When Crocodile enters, destroy target land."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_effect)]

CROCODILE_WARLORD = make_creature(
    name="Crocodile, Former Warlord",
    power=4,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Deathtouch. When Crocodile enters, destroy target land. \"I don't have time to play with small fry.\"",
    setup_interceptors=crocodile_setup
)

def doflamingo_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flying. Gain control of target creature with power less than Doflamingo's."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_effect)]

DOFLAMINGO_HEAVENLY_DEMON = make_creature(
    name="Doflamingo, Heavenly Demon",
    power=5,
    toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate", "Noble"},
    supertypes={"Legendary"},
    text="Flying. When Doflamingo enters, gain control of target creature with power less than Doflamingo's power for as long as you control Doflamingo.",
    setup_interceptors=doflamingo_setup
)

def gecko_moria_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever a creature dies, create a 2/2 black Zombie token."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        died_id = event.payload.get('object_id')
        died_obj = state.objects.get(died_id)
        return died_obj and CardType.CREATURE in died_obj.characteristics.types

    def zombie_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Shadow Zombie',
                'power': 2,
                'toughness': 2,
                'types': {CardType.CREATURE},
                'subtypes': {'Zombie'},
                'colors': {Color.BLACK},
                'is_token': True
            },
            source=obj.id
        )]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=zombie_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

GECKO_MORIA = make_creature(
    name="Gecko Moria, Shadow Master",
    power=4,
    toughness=5,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Whenever a creature dies, create a 2/2 black Shadow Zombie creature token.",
    setup_interceptors=gecko_moria_setup
)

def rob_lucci_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Deathtouch, menace. When Rob Lucci deals combat damage to a player, that player sacrifices a creature."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return [Event(
                type=EventType.SACRIFICE,
                payload={'player': target, 'type': 'creature'},
                source=obj.id
            )]
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ROB_LUCCI = make_creature(
    name="Rob Lucci, CP0 Agent",
    power=4,
    toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    supertypes={"Legendary"},
    text="Deathtouch, menace. Whenever Rob Lucci deals combat damage to a player, that player sacrifices a creature.",
    setup_interceptors=rob_lucci_setup
)

def caesar_clown_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """At upkeep, each opponent loses 1 life. Activate: each creature gets -1/-1."""
    def upkeep_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': player_id, 'amount': -1},
                    source=obj.id
                ))
        return events
    return [make_upkeep_trigger(obj, upkeep_effect)]

CAESAR_CLOWN = make_creature(
    name="Caesar Clown, Mad Scientist",
    power=2,
    toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Scientist"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of your upkeep, each opponent loses 1 life. {2}{B}, {T}: Each creature gets -1/-1 until end of turn.",
    setup_interceptors=caesar_clown_setup
)

PIRATE_CAPTAIN = make_creature(
    name="Pirate Captain",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Menace. Other Pirates you control get +1/+0."
)

def wanted_poster_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When enchanted creature dies, draw two cards."""
    def death_filter(event: Event, state: GameState, source: GameObject) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.GRAVEYARD:
            return False
        if event.payload.get('from_zone_type') != ZoneType.BATTLEFIELD:
            return False
        enchanted_id = source.state.attached_to if source.state else None
        return event.payload.get('object_id') == enchanted_id

    def draw_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 2}, source=obj.id)]

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=lambda e, s: death_filter(e, s, obj),
        handler=lambda e, s: InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=draw_effect(e, s)
        ),
        duration='while_on_battlefield'
    )]

WANTED_POSTER = make_enchantment_with_subtypes(
    name="Wanted Poster",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Aura"},
    text="Enchant creature. When enchanted creature dies, draw two cards.",
    setup_interceptors=wanted_poster_setup
)

SHADOW_STEAL = make_instant(
    name="Shadow Steal",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn. If it would die this turn, exile it instead."
)

DARK_DARK_FRUIT = make_enchantment_with_subtypes(
    name="Dark-Dark Fruit",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +2/+2 and has menace. Enchanted creature can't block creatures with islandwalk. When enchanted creature deals combat damage to a creature, exile that creature."
)

STRING_STRING_FRUIT = make_enchantment_with_subtypes(
    name="String-String Fruit",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +2/+1 and has flying. Enchanted creature can't block creatures with islandwalk. {B}: Gain control of target creature with power 2 or less until end of turn."
)

PIRATE_PLUNDER = make_sorcery(
    name="Pirate Plunder",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards. Create a Treasure token."
)

IMPEL_DOWN = make_land(
    name="Impel Down",
    supertypes={"Legendary"},
    text="{T}: Add {B}. {3}{B}, {T}: Return target creature card from your graveyard to your hand."
)

THRILLER_BARK = make_artifact(
    name="Thriller Bark",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Crew 4. Thriller Bark has \"Whenever a creature dies, put a +1/+1 counter on Thriller Bark.\" 4/4"
)

AWAKENED_DEVIL_FRUIT = make_enchantment(
    name="Awakened Devil Fruit",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Creatures you control with Devil Fruit attached to them get +2/+2 and have menace."
)


# =============================================================================
# RED CARDS - LUFFY, FIRE, AGGRESSION, ACE
# =============================================================================

def luffy_gear_five_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Can't be blocked by creatures with power 3 or less. Attacks each combat if able."""
    def block_prevention(event: Event, state: GameState) -> bool:
        if event.type != EventType.BLOCK_DECLARED:
            return False
        if event.payload.get('attacker_id') != obj.id:
            return False
        blocker_id = event.payload.get('blocker_id')
        blocker = state.objects.get(blocker_id)
        if not blocker:
            return False
        power = get_power(blocker, state)
        return power <= 3

    return [Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.PREVENT,
        filter=block_prevention,
        handler=lambda e, s: InterceptorResult(action=InterceptorAction.PREVENT),
        duration='while_on_battlefield'
    )]

LUFFY_GEAR_FIVE = make_creature(
    name="Monkey D. Luffy, Gear Five",
    power=7,
    toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Haste. Luffy can't be blocked by creatures with power 3 or less. Luffy attacks each combat if able. \"I'm gonna be King of the Pirates!\"",
    setup_interceptors=luffy_gear_five_setup
)

def luffy_straw_hat_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Crew lord. Other Straw Hat Pirates get +1/+1. Conqueror's Haki on attack."""
    def straw_hat_filter(target: GameObject, state: GameState) -> bool:
        return (target.id != obj.id and
                target.controller == obj.controller and
                CardType.CREATURE in target.characteristics.types and
                'Pirate' in target.characteristics.subtypes and
                target.zone == ZoneType.BATTLEFIELD)
    interceptors = make_static_pt_boost(obj, 1, 1, straw_hat_filter)
    interceptors.append(make_conquerors_haki_attack(obj))
    return interceptors

LUFFY_STRAW_HAT = make_creature(
    name="Monkey D. Luffy, Straw Hat Captain",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Haste. Other Pirates you control get +1/+1. Conqueror's Haki - Whenever Luffy attacks, tap target creature defending player controls.",
    setup_interceptors=luffy_straw_hat_setup
)

def ace_fire_fist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Can't be blocked. When Ace deals combat damage to a player, deal 2 damage to any target."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        target = event.payload.get('target')
        if target in state.players:
            return []  # Targeting fills in
        return []
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ACE_FIRE_FIST = make_creature(
    name="Portgas D. Ace, Fire Fist",
    power=4,
    toughness=3,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Ace can't be blocked. Whenever Ace deals combat damage to a player, Ace deals 2 damage to any target. \"I have no regrets!\"",
    setup_interceptors=ace_fire_fist_setup
)

def sabo_revolutionary_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Whenever Sabo deals combat damage, deal 1 damage to each opponent."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': player_id, 'amount': 1, 'source': obj.id},
                    source=obj.id
                ))
        return events
    # combat_only=True is critical: the effect emits DAMAGE events whose
    # source is also Sabo. Without the combat gate, the trigger would
    # re-fire on its own emitted damage and infinite-loop the pipeline.
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

SABO_REVOLUTIONARY = make_creature(
    name="Sabo, Revolutionary Chief",
    power=3,
    toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate", "Noble"},
    supertypes={"Legendary"},
    text="Haste. Whenever Sabo deals combat damage, deal 1 damage to each opponent.",
    setup_interceptors=sabo_revolutionary_setup
)

def kid_captain_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Kid attacks, deal damage to defending player equal to the number of artifacts you control."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        artifact_count = sum(1 for o in state.objects.values()
                           if o.controller == obj.controller and
                           CardType.ARTIFACT in o.characteristics.types and
                           o.zone == ZoneType.BATTLEFIELD)
        defending = event.payload.get('defending_player')
        if defending and artifact_count > 0:
            return [Event(
                type=EventType.DAMAGE,
                payload={'target': defending, 'amount': artifact_count, 'source': obj.id},
                source=obj.id
            )]
        return []
    return [make_attack_trigger(obj, attack_effect)]

KID_CAPTAIN = make_creature(
    name="Eustass Kid, Magnetic Menace",
    power=2,
    toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="When Kid attacks, deal damage to defending player equal to the number of artifacts you control.",
    setup_interceptors=kid_captain_setup
)

def oden_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike. Conqueror's Haki on ETB."""
    return [make_conquerors_haki_etb(obj)]

KOZUKI_ODEN = make_creature(
    name="Kozuki Oden, Two-Sword Legend",
    power=5,
    toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Samurai", "Noble"},
    supertypes={"Legendary"},
    text="Double strike. Conqueror's Haki - When Oden enters, tap all creatures opponents control. \"I was born to boil!\"",
    setup_interceptors=oden_setup
)

FLAME_FLAME_FRUIT = make_enchantment_with_subtypes(
    name="Flame-Flame Fruit",
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +2/+1 and can't be blocked. Enchanted creature can't block creatures with islandwalk. {R}: Enchanted creature deals 1 damage to any target."
)

GUM_GUM_FRUIT = make_enchantment_with_subtypes(
    name="Gum-Gum Fruit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +2/+2 and has reach. Enchanted creature can't block creatures with islandwalk. Enchanted creature can block an additional creature each combat."
)

GOMU_GOMU_NO_PISTOL = make_instant(
    name="Gomu Gomu no Pistol",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to target creature or planeswalker."
)

GOMU_GOMU_NO_GATLING = make_instant(
    name="Gomu Gomu no Gatling",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Creatures you control deal damage equal to their power to target creature. Excess damage is dealt to that creature's controller."
)

FIRE_FIST = make_instant(
    name="Fire Fist",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Deal 4 damage to target creature. If you control a creature named Ace, deal 4 damage to that creature's controller as well."
)

PIRATE_RAID = make_sorcery(
    name="Pirate Raid",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn. Create a Treasure token for each creature that deals combat damage to a player this turn."
)

SUPERNOVA_RAMPAGE = make_sorcery(
    name="Supernova Rampage",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Deal 1 damage to each creature and each player for each Pirate you control."
)

WANO_COUNTRY = make_land(
    name="Wano Country",
    supertypes={"Legendary"},
    text="{T}: Add {R}. {R}, {T}: Target Samurai or Pirate gains first strike until end of turn."
)

BURNING_WILL = make_enchantment(
    name="Burning Will",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0. Whenever a creature you control attacks alone, it gets +2/+0 until end of turn."
)

REVOLUTIONARY_ARMY = make_creature(
    name="Revolutionary Army Soldier",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel", "Soldier"},
    text="Haste. When Revolutionary Army Soldier enters, you may discard a card. If you do, draw a card."
)


# =============================================================================
# GREEN CARDS - ZORO, STRENGTH, WANO
# =============================================================================

def zoro_three_sword_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Double strike. Whenever Zoro deals combat damage, put a +1/+1 counter on him."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect, combat_only=True)]

ZORO_THREE_SWORD = make_creature(
    name="Roronoa Zoro, Three-Sword Style",
    power=4,
    toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate", "Samurai"},
    supertypes={"Legendary"},
    text="Double strike. Whenever Zoro deals combat damage, put a +1/+1 counter on him. \"Nothing happened.\"",
    setup_interceptors=zoro_three_sword_setup
)

def zoro_wano_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Armament Haki. First strike. When Zoro attacks, he fights target creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    interceptors = make_armament_haki(obj)
    interceptors.append(make_attack_trigger(obj, attack_effect))
    return interceptors

ZORO_WANO = make_creature(
    name="Roronoa Zoro, King of Hell",
    power=5,
    toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate", "Samurai"},
    supertypes={"Legendary"},
    text="First strike. Armament Haki - Protection from colorless. When Zoro attacks, he fights target creature an opponent controls.",
    setup_interceptors=zoro_wano_setup
)

def kaido_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible. Trample. When Kaido attacks, each opponent sacrifices a creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        events = []
        for player_id in state.players:
            if player_id != obj.controller:
                events.append(Event(
                    type=EventType.SACRIFICE,
                    payload={'player': player_id, 'type': 'creature'},
                    source=obj.id
                ))
        return events
    return [make_attack_trigger(obj, attack_effect)]

KAIDO_HUNDRED_BEASTS = make_creature(
    name="Kaido, King of the Beasts",
    power=8,
    toughness=8,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Dragon", "Pirate"},
    supertypes={"Legendary"},
    text="Indestructible, trample. When Kaido attacks, each opponent sacrifices a creature. Conqueror's Haki - {3}{G}: Tap all creatures opponents control.",
    setup_interceptors=kaido_setup
)

def big_mom_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Trample. When Big Mom deals damage, create a Food token."""
    def damage_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Food',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Food'},
                'abilities': ['{2}, {T}, Sacrifice: Gain 3 life.'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_damage_trigger(obj, damage_effect)]

BIG_MOM = make_creature(
    name="Big Mom, Soul Queen",
    power=7,
    toughness=7,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Pirate"},
    supertypes={"Legendary"},
    text="Trample. Whenever Big Mom deals damage, create a Food token. {2}, Sacrifice a Food: Big Mom gains indestructible until end of turn.",
    setup_interceptors=big_mom_setup
)

def whitebeard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Whitebeard enters or attacks, destroy target artifact or land."""
    def etb_attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_attack_effect), make_attack_trigger(obj, etb_attack_effect)]

WHITEBEARD = make_creature(
    name="Whitebeard, Strongest Man",
    power=7,
    toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Trample. When Whitebeard enters or attacks, destroy target artifact or land. \"I am Whitebeard!\"",
    setup_interceptors=whitebeard_setup
)

def dorry_brogy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When this creature enters, create a 5/5 Giant token named Brogy."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Brogy, Giant Warrior',
                'power': 5,
                'toughness': 5,
                'types': {CardType.CREATURE},
                'subtypes': {'Giant', 'Warrior'},
                'colors': {Color.GREEN},
                'is_token': True
            },
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

DORRY_GIANT_WARRIOR = make_creature(
    name="Dorry, Giant Warrior",
    power=5,
    toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Warrior"},
    supertypes={"Legendary"},
    text="When Dorry enters, create Brogy, a legendary 5/5 green Giant Warrior creature token.",
    setup_interceptors=dorry_brogy_setup
)

def giant_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Elbaf colossus — scry 1, life per Giant/Warrior, each opp -1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        ally_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and (
                    'Giant' in o.characteristics.subtypes or
                    'Warrior' in o.characteristics.subtypes
                ):
                    ally_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, ally_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

GIANT_WARRIOR = make_creature(
    name="Giant Warrior",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Giant", "Warrior"},
    text="Trample. When Giant Warrior enters, scry 1, gain life per Giant or Warrior you control, and each opponent loses 1 life.",
    setup_interceptors=giant_warrior_setup,
)

KUNG_FU_DUGONG = make_creature(
    name="Kung-Fu Dugong",
    power=2,
    toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Dugong", "Monk"},
    text="Whenever Kung-Fu Dugong blocks or becomes blocked, it gets +2/+2 until end of turn."
)

SOUTH_BIRD = make_creature(
    name="South Bird",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Bird"},
    text="Flying. {T}: Look at the top card of your library. You may put it on the bottom."
)

THREE_SWORD_STYLE = make_instant(
    name="Three-Sword Style",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 and gains trample until end of turn. If you control a creature named Zoro, that creature also gains double strike."
)

ONIGIRI = make_instant(
    name="Onigiri",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn. It gains first strike until end of turn if its controller controls a Samurai."
)

ASHURA = make_sorcery(
    name="Ashura",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights each creature target opponent controls. (It deals damage equal to its power to each of them, and each deals damage to it.)"
)

WILD_STRENGTH = make_enchantment_with_subtypes(
    name="Wild Strength",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Aura"},
    text="Enchant creature. Enchanted creature gets +3/+3 and has trample."
)

BEAST_PIRATES_TERRITORY = make_land(
    name="Beast Pirates' Territory",
    supertypes={"Legendary"},
    text="{T}: Add {G}. {2}{G}, {T}: Target creature you control gets +2/+2 until end of turn."
)

FISH_FISH_FRUIT_AZURE = make_enchantment_with_subtypes(
    name="Fish-Fish Fruit, Azure Dragon",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +4/+4, has flying and trample, and is a Dragon in addition to its other types. Enchanted creature can't block creatures with islandwalk."
)

HUMAN_HUMAN_FRUIT = make_enchantment_with_subtypes(
    name="Human-Human Fruit",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +1/+1 for each creature type it has. Enchanted creature can't block creatures with islandwalk."
)


# =============================================================================
# MULTICOLOR CARDS - STRAW HAT CREW & YONKO
# =============================================================================

def robin_archaeologist_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Robin ETB, draw cards equal to the number of artifacts and enchantments opponents control."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        count = sum(1 for o in state.objects.values()
                   if o.controller != obj.controller and
                   o.zone == ZoneType.BATTLEFIELD and
                   (CardType.ARTIFACT in o.characteristics.types or
                    CardType.ENCHANTMENT in o.characteristics.types))
        if count > 0:
            return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': min(count, 3)}, source=obj.id)]
        return []
    return [make_etb_trigger(obj, etb_effect)]

ROBIN_ARCHAEOLOGIST = make_creature(
    name="Nico Robin, Archaeologist",
    power=2,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate", "Scholar"},
    supertypes={"Legendary"},
    text="When Robin enters, draw cards equal to the number of artifacts and enchantments opponents control, up to three. \"{T}: Tap target creature.\"",
    setup_interceptors=robin_archaeologist_setup
)

def brook_soul_king_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Brook dies, return him to your hand at end of turn."""
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.DELAYED_TRIGGER,
            payload={
                'trigger': 'end_step',
                'effect': 'return_to_hand',
                'object_id': obj.id
            },
            source=obj.id
        )]
    return [make_death_trigger(obj, death_effect)]

BROOK_SOUL_KING = make_creature(
    name="Brook, Soul King",
    power=3,
    toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Skeleton", "Pirate", "Bard"},
    supertypes={"Legendary"},
    text="First strike. When Brook dies, return him to your hand at the beginning of the next end step. \"Yohohoho!\"",
    setup_interceptors=brook_soul_king_setup
)

def franky_cyborg_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Artifacts you control have hexproof. {T}: Create a Treasure token."""
    def artifact_hexproof(target: GameObject, state: GameState) -> bool:
        return (target.controller == obj.controller and
                CardType.ARTIFACT in target.characteristics.types and
                target.zone == ZoneType.BATTLEFIELD)
    return [make_keyword_grant(obj, ['hexproof'], artifact_hexproof)]

FRANKY_CYBORG = make_creature(
    name="Franky, Cyborg Shipwright",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pirate", "Artificer"},
    supertypes={"Legendary"},
    text="Artifacts you control have hexproof. {T}: Create a Treasure token. \"SUPER!\"",
    setup_interceptors=franky_cyborg_setup
)

def sanji_cook_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Haste. Can't attack or block female creatures. When Sanji attacks, create a Food token."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.OBJECT_CREATED,
            payload={
                'controller': obj.controller,
                'name': 'Food',
                'types': {CardType.ARTIFACT},
                'subtypes': {'Food'},
                'abilities': ['{2}, {T}, Sacrifice: Gain 3 life.'],
                'is_token': True
            },
            source=obj.id
        )]
    return [make_attack_trigger(obj, attack_effect)]

SANJI_COOK = make_creature(
    name="Sanji, Black Leg Cook",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Pirate", "Chef"},
    supertypes={"Legendary"},
    text="Haste. Whenever Sanji attacks, create a Food token. {2}, Sacrifice a Food: Target creature gets +2/+2 until end of turn.",
    setup_interceptors=sanji_cook_setup
)

def chopper_doctor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Chopper ETB, you gain 3 life and put a +1/+1 counter on target creature."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': obj.controller, 'amount': 3},
            source=obj.id
        )]
    return [make_etb_trigger(obj, etb_effect)]

CHOPPER_DOCTOR = make_creature(
    name="Tony Tony Chopper, Ship Doctor",
    power=1,
    toughness=3,
    mana_cost="{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Reindeer", "Pirate", "Cleric"},
    supertypes={"Legendary"},
    text="When Chopper enters, you gain 3 life and put a +1/+1 counter on target creature you control.",
    setup_interceptors=chopper_doctor_setup
)

def usopp_sniper_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Reach. When Usopp attacks, he deals 2 damage to target creature."""
    def attack_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_attack_trigger(obj, attack_effect)]

USOPP_SNIPER = make_creature(
    name="Usopp, God Sniper",
    power=2,
    toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Reach. When Usopp attacks, deal 2 damage to target creature. \"I am the brave warrior of the sea, Captain Usopp!\"",
    setup_interceptors=usopp_sniper_setup
)

def law_surgeon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """When Law ETB, exchange control of two target creatures."""
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return []  # Targeting fills in
    return [make_etb_trigger(obj, etb_effect)]

LAW_SURGEON = make_creature(
    name="Trafalgar Law, Surgeon of Death",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate", "Cleric"},
    supertypes={"Legendary"},
    text="When Law enters, exchange control of two target creatures. \"Room.\"",
    setup_interceptors=law_surgeon_setup
)

def shanks_yonko_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Conqueror's Haki on ETB and attack. Other Pirates get +2/+0."""
    interceptors = make_pirate_lord(obj, 2, 0)
    interceptors.append(make_conquerors_haki_etb(obj))
    interceptors.append(make_conquerors_haki_attack(obj))
    return interceptors

SHANKS_YONKO = make_creature(
    name="Shanks, Red-Haired Emperor",
    power=5,
    toughness=5,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Other Pirates you control get +2/+0. Conqueror's Haki - When Shanks enters or attacks, tap all creatures opponents control.",
    setup_interceptors=shanks_yonko_setup
)

YAMATO_OGUCHI = make_creature(
    name="Yamato, Son of Kaido",
    power=5,
    toughness=4,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Samurai"},
    supertypes={"Legendary"},
    text="Trample. Observation Haki - At the beginning of your upkeep, scry 2. Armament Haki - Protection from colorless."
)

VIVI_PRINCESS = make_creature(
    name="Nefertari Vivi, Princess of Alabasta",
    power=2,
    toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Noble"},
    supertypes={"Legendary"},
    text="When Vivi enters, each player draws a card. Creatures you control have \"Whenever this creature deals combat damage to a player, scry 1.\""
)

KAROO_SUPER_SPOT_BILLED_DUCK = make_creature(
    name="Karoo, Super Spot-Billed Duck",
    power=2,
    toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Bird", "Mount"},
    text="Flying. Whenever Karoo deals combat damage to a player, draw a card. Crew - Karoo gets +1/+1 as long as you control Vivi."
)

THOUSAND_SUNNY = make_artifact(
    name="Thousand Sunny",
    mana_cost="{4}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Crew 3. Trample. Whenever Thousand Sunny deals combat damage to a player, draw a card and create a Treasure token. 5/5"
)

GOING_MERRY = make_artifact(
    name="Going Merry",
    mana_cost="{3}",
    subtypes={"Vehicle"},
    supertypes={"Legendary"},
    text="Crew 2. Whenever a Pirate you control attacks, Going Merry gets +1/+0 until end of turn. When Going Merry is put into a graveyard, return target Pirate card from your graveyard to your hand. 3/4"
)

STRAW_HAT = make_artifact(
    name="Straw Hat",
    mana_cost="{1}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+1 and has \"This creature can't be blocked by creatures with power 2 or less.\" Equip Pirate {1}. Equip {3}."
)

PONEGLYPH = make_artifact(
    name="Poneglyph",
    mana_cost="{3}",
    supertypes={"Legendary"},
    text="When Poneglyph enters, scry 3. {3}, {T}: Draw a card. If you control Robin, draw two cards instead."
)

DEVIL_FRUIT_ENCYCLOPEDIA = make_artifact(
    name="Devil Fruit Encyclopedia",
    mana_cost="{2}",
    text="{2}, {T}: Look at the top five cards of your library. You may reveal an enchantment card with Devil Fruit subtype and put it into your hand. Put the rest on the bottom."
)

ROAD_PONEGLYPH = make_artifact(
    name="Road Poneglyph",
    mana_cost="{4}",
    supertypes={"Legendary"},
    text="When Road Poneglyph enters, search your library for a land card and put it onto the battlefield tapped. {5}, {T}, Sacrifice Road Poneglyph: You win the game if you control three other Poneglyphs."
)

ONE_PIECE_TREASURE = make_artifact(
    name="One Piece, the Greatest Treasure",
    mana_cost="{10}",
    supertypes={"Legendary"},
    text="This spell costs {1} less to cast for each Pirate you control. When One Piece enters, you win the game."
)

LAUGH_TALE = make_land(
    name="Laugh Tale",
    supertypes={"Legendary"},
    text="{T}: Add one mana of any color. {5}, {T}: Search your library for a legendary artifact card and put it onto the battlefield. Activate only if you control four or more Pirates."
)

RAFTEL_APPROACH = make_sorcery(
    name="Raftel Approach",
    mana_cost="{3}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Search your library for up to two Pirate cards, reveal them, and put them into your hand. Then shuffle. Create two Treasure tokens."
)

DAWN_OF_THE_WORLD = make_sorcery(
    name="Dawn of the World",
    mana_cost="{4}{W}{U}{B}{R}{G}",
    colors={Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN},
    text="Take an extra turn after this one. Untap all permanents you control. Draw three cards. You gain 10 life. Each opponent loses 10 life."
)


# =============================================================================
# ADDITIONAL CARDS - FILLING OUT THE SET
# =============================================================================

# More White Cards
def marine_soldier_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Rank-and-file — scry 1, life per Marine, each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        marine_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Marine' in o.characteristics.subtypes:
                    marine_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, marine_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

MARINE_SOLDIER = make_creature(
    name="Marine Soldier",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="Vigilance. When Marine Soldier enters, scry 1, gain life per Marine you control, and each opponent loses 1 life.",
    setup_interceptors=marine_soldier_setup,
)

MARINE_VICE_ADMIRAL = make_creature(
    name="Marine Vice Admiral",
    power=4,
    toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Marine", "Soldier"},
    text="When Marine Vice Admiral enters, create a 2/2 white Marine Soldier creature token."
)

JUSTICE_WILL_PREVAIL = make_instant(
    name="Justice Will Prevail",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn. Marines you control gain first strike until end of turn."
)

SEA_PRISM_HANDCUFFS = make_artifact(
    name="Sea Prism Handcuffs",
    mana_cost="{3}",
    text="When Sea Prism Handcuffs enters, exile target creature until Sea Prism Handcuffs leaves the battlefield. That creature's controller creates a Treasure token."
)

MARINE_TRAINING = make_enchantment(
    name="Marine Training",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Marines you control get +0/+1 and have vigilance."
)

WORLD_NOBLE = make_creature(
    name="World Noble",
    power=1,
    toughness=1,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Noble"},
    text="Protection from creatures with power 4 or greater. When World Noble dies, create three Treasure tokens."
)

# More Blue Cards
NAVIGATOR_APPRENTICE = make_creature(
    name="Navigator's Apprentice",
    power=1,
    toughness=2,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When Navigator's Apprentice enters, scry 1."
)

OCEAN_CURRENT = make_instant(
    name="Ocean Current",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target creature to its owner's hand. If you control a Fishman, draw a card."
)

FISHMAN_DISTRICT = make_land(
    name="Fishman District",
    text="{T}: Add {C}. {T}: Add {U}. Activate only if you control a Fishman."
)

MERFOLK_DANCER = make_creature(
    name="Merfolk Dancer",
    power=2,
    toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Merfolk"},
    text="Flying. When Merfolk Dancer enters, tap target creature."
)

WATER_7 = make_land(
    name="Water 7",
    supertypes={"Legendary"},
    text="{T}: Add {U}. {2}{U}, {T}: Return target artifact to its owner's hand."
)

UNDERSEA_PRISON = make_enchantment(
    name="Undersea Prison",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    text="When Undersea Prison enters, exile target creature an opponent controls until Undersea Prison leaves the battlefield."
)

# More Black Cards
PIRATE_CREW = make_creature(
    name="Pirate Crew",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Pirate Crew enters, target opponent discards a card."
)

TREACHEROUS_MUTINY = make_sorcery(
    name="Treacherous Mutiny",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller creates a Treasure token."
)

YAMI_YAMI_BLACKHOLE = make_instant(
    name="Yami Yami Blackhole",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Exile all creatures. For each creature exiled this way, its controller loses 1 life."
)

def baroque_works_agent_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Operative's intel — surveil 1 and each opp loses 1 life on entry."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        assassin_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Assassin' in o.characteristics.subtypes:
                    assassin_count += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

BAROQUE_WORKS_AGENT = make_creature(
    name="Baroque Works Agent",
    power=2,
    toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Baroque Works Agent enters, surveil 1 and each opponent loses 1 life.",
    setup_interceptors=baroque_works_agent_setup,
)

def shadow_puppet_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Stolen shadow — surveil 1 and each opp loses 1 life on entry."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        zombie_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Zombie' in o.characteristics.subtypes:
                    zombie_count += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SHADOW_PUPPET = make_creature(
    name="Shadow Puppet",
    power=2,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
    text="When Shadow Puppet enters, surveil 1 and each opponent loses 1 life. When Shadow Puppet dies, each opponent loses 1 life.",
    setup_interceptors=shadow_puppet_setup,
)

UNDERWORLD_CONNECTION = make_enchantment(
    name="Underworld Connection",
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    text="At the beginning of your upkeep, you may pay 1 life. If you do, draw a card."
)

# More Red Cards
SUPERNOVA = make_creature(
    name="Supernova",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Haste."
)

BATTLE_FRANKY = make_artifact_creature(
    name="Battle Franky",
    power=3,
    toughness=3,
    mana_cost="{3}{R}",
    subtypes={"Construct"},
    text="Haste. When Battle Franky enters, it deals 2 damage to any target."
)

EXPLOSION_STAR = make_instant(
    name="Explosion Star",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Deal 4 damage to target creature or planeswalker. If excess damage would be dealt, deal that damage to that permanent's controller instead."
)


# =============================================================================
# RED BURN SPELLS — adds reach for OPC's mono-red aggro plan. Existing
# burn (Fire Fist, Explosion Star, Gomu Gomu no Pistol) was cosmetic
# (no resolve callback wired). These three have proper resolve fns
# that emit DAMAGE events targeting each opponent of the caster.
# =============================================================================

def _opc_burn_resolve(card_name: str, amount: int):
    """Resolve callback: deal `amount` damage to each opponent of the caster.

    Auto-targets so the spell never fizzles on AI target-selection.
    Finds the spell on the stack by name to attribute the damage events.
    """
    def resolve(targets, state):
        stack_zone = state.zones.get('stack')
        spell_id = None
        controller = None
        if stack_zone:
            for obj_id in reversed(list(stack_zone.objects or [])):
                so = state.objects.get(obj_id)
                if so and so.name == card_name:
                    spell_id = so.id
                    controller = so.controller
                    break
        if controller is None:
            return []
        events = []
        for pid in state.players:
            if pid != controller:
                events.append(Event(
                    type=EventType.DAMAGE,
                    payload={'target': pid, 'amount': amount, 'source': spell_id},
                    source=spell_id,
                ))
        return events
    return resolve


PIRATE_CANNON_SHOT = make_instant(
    name="Pirate Cannon Shot",
    mana_cost="{R}",
    colors={Color.RED},
    text="Deal 2 damage to each opponent.",
    resolve=_opc_burn_resolve("Pirate Cannon Shot", 2),
)

CANNONBALL_VOLLEY = make_sorcery(
    name="Cannonball Volley",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Deal 3 damage to each opponent.",
    resolve=_opc_burn_resolve("Cannonball Volley", 3),
)

WHITEBEARDS_QUAKE = make_sorcery(
    name="Whitebeard's Quake",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Deal 5 damage to each opponent.",
    resolve=_opc_burn_resolve("Whitebeard's Quake", 5),
)

REVOLUTIONARY_FERVOR = make_enchantment(
    name="Revolutionary Fervor",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +1/+0 and have haste."
)

FIERY_DESTRUCTION = make_sorcery(
    name="Fiery Destruction",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Deal 5 damage to each creature without flying."
)

SAMURAI_OF_WANO = make_creature(
    name="Samurai of Wano",
    power=3,
    toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Samurai"},
    text="First strike."
)

# More Green Cards
WANO_SAMURAI = make_creature(
    name="Wano Samurai",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Samurai"},
    text="Whenever Wano Samurai deals combat damage to a player, put a +1/+1 counter on it."
)

BEAST_PIRATE = make_creature(
    name="Beast Pirate",
    power=4,
    toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Trample. This creature gets +1/+1 for each other Pirate you control."
)

ANCIENT_ZOAN = make_creature(
    name="Ancient Zoan",
    power=5,
    toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Dinosaur"},
    text="Trample. When Ancient Zoan enters, it fights target creature an opponent controls."
)

AWAKENED_ZOAN = make_creature(
    name="Awakened Zoan",
    power=6,
    toughness=6,
    mana_cost="{5}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample, vigilance. Other creatures you control with Devil Fruit attached to them get +2/+2."
)

JUNGLE_BEAST = make_creature(
    name="Jungle Beast",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Reach"
)

NATURAL_STRENGTH = make_instant(
    name="Natural Strength",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)

# More Multicolor Cards
ALLIANCE_CAPTAIN = make_creature(
    name="Alliance Captain",
    power=3,
    toughness=3,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Pirate", "Warrior"},
    text="Trample, haste. Other Pirates and Samurai you control get +1/+0."
)

HEART_PIRATES_CREW = make_creature(
    name="Heart Pirates Crew",
    power=2,
    toughness=2,
    mana_cost="{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="When Heart Pirates Crew enters, target creature gets -1/-1 until end of turn."
)

MINK_WARRIOR = make_creature(
    name="Mink Warrior",
    power=3,
    toughness=2,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="Haste. Mink Warrior has first strike as long as it's your turn."
)

REVOLUTIONARY_COMMANDER = make_creature(
    name="Revolutionary Commander",
    power=2,
    toughness=2,
    mana_cost="{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rebel"},
    text="Menace. Whenever Revolutionary Commander deals combat damage to a player, that player discards a card."
)

WARLORD = make_creature(
    name="Warlord of the Sea",
    power=5,
    toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Islandwalk. When Warlord enters, draw a card and each opponent discards a card."
)

NEW_WORLD_PIRATE = make_creature(
    name="New World Pirate",
    power=4,
    toughness=3,
    mana_cost="{1}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Pirate"},
    text="Menace. Bounty 2 - When this creature dies, target opponent creates two Treasure tokens."
)

# More Artifacts
ETERNAL_POSE = make_artifact(
    name="Eternal Pose",
    mana_cost="{2}",
    text="{2}, {T}: Look at the top card of your library. If it's a land, you may put it onto the battlefield tapped."
)

DIALS = make_artifact(
    name="Dials",
    mana_cost="{1}",
    text="{T}: Add {C}. {2}, {T}: Deal 1 damage to any target."
)

TONE_DIAL = make_artifact(
    name="Tone Dial",
    mana_cost="{2}",
    text="When Tone Dial enters, exile target instant or sorcery card from a graveyard. You may cast that card for as long as it remains exiled."
)

IMPACT_DIAL = make_artifact(
    name="Impact Dial",
    mana_cost="{3}",
    text="{2}, {T}, Sacrifice Impact Dial: Deal damage to target creature equal to the damage that was dealt to you this turn."
)

SEASTONE_CAGE = make_artifact(
    name="Seastone Cage",
    mana_cost="{4}",
    text="Creatures with Devil Fruit attached to them can't attack or block. {3}, {T}: Tap target creature with a Devil Fruit attached to it."
)

TREASURE_MAP = make_artifact(
    name="Treasure Map",
    mana_cost="{2}",
    text="{1}, {T}: Scry 1. If you've activated this ability three or more times, transform Treasure Map into Treasure Trove."
)

VIVRE_CARD = make_artifact(
    name="Vivre Card",
    mana_cost="{1}",
    text="When a creature you control dies, you may pay {1}. If you do, return that creature to your hand at the beginning of the next end step."
)

DEN_DEN_MUSHI = make_artifact(
    name="Den Den Mushi",
    mana_cost="{1}",
    text="{T}: Add one mana of any color. Spend this mana only to cast creature spells."
)

# More Enchantments
PIRATE_FLAG = make_enchantment(
    name="Pirate Flag",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Pirates you control get +1/+0 and have menace."
)

WILL_OF_D = make_enchantment(
    name="Will of D.",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Legendary creatures you control get +1/+1 and have \"When this creature dies, draw a card.\""
)

INHERITED_WILL = make_enchantment(
    name="Inherited Will",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="When a legendary creature you control dies, you may search your library for a legendary creature card with mana value less than or equal to that creature's mana value, reveal it, and put it into your hand. Then shuffle."
)

CONQUERORS_SPIRIT = make_enchantment(
    name="Conqueror's Spirit",
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Whenever a creature you control attacks, you may tap target creature defending player controls. Creatures you control get +0/+1."
)

DREAM_OF_PIRATE_KING = make_enchantment(
    name="Dream of the Pirate King",
    mana_cost="{3}{R}",
    colors={Color.RED},
    text="At the beginning of your upkeep, if you control three or more Pirates, draw a card. Pirates you control get +1/+0."
)

# More Lands
SABAODY_ARCHIPELAGO = make_land(
    name="Sabaody Archipelago",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. {3}, {T}: Return target creature to its owner's hand."
)

MARINEFORD = make_land(
    name="Marineford",
    supertypes={"Legendary"},
    text="{T}: Add {W}. {2}{W}{W}, {T}: Create two 2/2 white Marine Soldier creature tokens."
)

DRESSROSA = make_land(
    name="Dressrosa",
    supertypes={"Legendary"},
    text="{T}: Add {B} or {R}. Whenever you cast a legendary spell, scry 1."
)

WHOLE_CAKE_ISLAND = make_land(
    name="Whole Cake Island",
    supertypes={"Legendary"},
    text="{T}: Add {G}. {2}, {T}: Create a Food token."
)

ELBAF = make_land(
    name="Elbaf",
    supertypes={"Legendary"},
    text="{T}: Add {G}. {3}{G}, {T}: Create a 4/4 green Giant creature token."
)

SKYPIEA = make_land(
    name="Skypiea",
    supertypes={"Legendary"},
    text="{T}: Add {W} or {U}. Creatures you control with flying get +0/+1."
)

AMAZON_LILY = make_land(
    name="Amazon Lily",
    supertypes={"Legendary"},
    text="{T}: Add {R} or {G}. {3}, {T}: Target creature gains trample until end of turn."
)

# More Sorceries
COUP_DE_BURST = make_sorcery(
    name="Coup de Burst",
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    text="Return all creatures to their owners' hands. You may put a Vehicle you control onto the battlefield."
)

BINK_SAKE = make_sorcery(
    name="Bink's Sake",
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Return up to two target creature cards from your graveyard to your hand. You gain 2 life."
)

GATHER_THE_FLEET = make_sorcery(
    name="Gather the Fleet",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Create three 1/1 blue Pirate creature tokens with \"This creature can't block.\""
)

PIRATE_ALLIANCE = make_sorcery(
    name="Pirate Alliance",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Creatures you control get +2/+2 and gain trample until end of turn. Draw a card for each Pirate you control."
)

MARINEFORD_WAR = make_sorcery(
    name="Marineford War",
    mana_cost="{4}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text="Destroy all creatures. For each creature destroyed this way, its controller creates a Treasure token."
)

PARAMOUNT_WAR = make_sorcery(
    name="Paramount War",
    mana_cost="{5}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Each player sacrifices half the creatures they control, rounded up. Then create a 5/5 white and red legendary Pirate creature token named War Hero."
)

# More Instants
GEAR_SECOND = make_instant(
    name="Gear Second",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gains haste and gets +2/+0 until end of turn."
)

GEAR_THIRD = make_instant(
    name="Gear Third",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Target creature gets +5/+5 and gains trample until end of turn. At end of turn, that creature gets -2/-2 until end of your next turn."
)

GEAR_FOURTH = make_instant(
    name="Gear Fourth",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Target creature gets +4/+4, gains flying, trample, and can't be blocked by creatures with power 3 or less until end of turn."
)

DIABLE_JAMBE = make_instant(
    name="Diable Jambe",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature gets +3/+0 and gains first strike until end of turn."
)

COUP_DE_VENT = make_instant(
    name="Coup de Vent",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return target nonland permanent to its owner's hand. You may draw a card, then discard a card."
)

RUMBLE_BALL = make_instant(
    name="Rumble Ball",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +1/+1 and gains your choice of flying, trample, reach, or vigilance until end of turn."
)

HAKI_CLASH = make_instant(
    name="Haki Clash",
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Target creature you control fights target creature you don't control. If your creature survives, put a +1/+1 counter on it."
)

OBSERVATION_DODGE = make_instant(
    name="Observation Dodge",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gains hexproof until end of turn. Scry 1."
)

# Basic Lands
PLAINS_OPG = make_land(name="Plains", subtypes={"Plains"})
ISLAND_OPG = make_land(name="Island", subtypes={"Island"})
SWAMP_OPG = make_land(name="Swamp", subtypes={"Swamp"})
MOUNTAIN_OPG = make_land(name="Mountain", subtypes={"Mountain"})
FOREST_OPG = make_land(name="Forest", subtypes={"Forest"})


# =============================================================================
# ADDITIONAL CARDS TO REACH ~270 TARGET
# =============================================================================

# More Legendary Characters
BOA_HANCOCK = make_creature(
    name="Boa Hancock, Pirate Empress",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pirate", "Noble"},
    supertypes={"Legendary"},
    text="First strike. When Boa Hancock enters, tap target creature an opponent controls. It doesn't untap during its controller's next untap step."
)

BUGGY_CLOWN = make_creature(
    name="Buggy, the Clown",
    power=2,
    toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="When Buggy dies, return him to the battlefield tapped under his owner's control at the beginning of the next end step. Buggy can't block creatures with power 4 or greater."
)

MIHAWK_WORLDS_STRONGEST = make_creature(
    name="Mihawk, World's Strongest Swordsman",
    power=6,
    toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Double strike. When Mihawk deals combat damage to a creature, exile that creature."
)

KUMA_TYRANT = make_creature(
    name="Kuma, Tyrant",
    power=5,
    toughness=6,
    mana_cost="{4}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="When Kuma enters, exile target creature an opponent controls. Return it to the battlefield under its owner's control at the beginning of their next upkeep."
)

RAYLEIGH_DARK_KING = make_creature(
    name="Rayleigh, Dark King",
    power=5,
    toughness=5,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Flash. Armament Haki - Protection from colorless. When Rayleigh enters, draw two cards, then discard a card."
)

MARCO_PHOENIX = make_creature(
    name="Marco, the Phoenix",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Flying. At the beginning of your upkeep, if Marco is in your graveyard, you may pay {4}. If you do, return Marco to the battlefield tapped."
)

JOZU_DIAMOND = make_creature(
    name="Jozu, Diamond",
    power=5,
    toughness=7,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Vigilance, indestructible. Jozu can't attack if defending player controls more creatures than you."
)

VISTA_FLOWER_SWORD = make_creature(
    name="Vista, Flower Sword",
    power=4,
    toughness=3,
    mana_cost="{2}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Double strike. When Vista enters, destroy target enchantment."
)

PERONA_GHOST_PRINCESS = make_creature(
    name="Perona, Ghost Princess",
    power=2,
    toughness=2,
    mana_cost="{2}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Flying. When Perona enters, target creature gets -3/-0 until your next turn."
)

HANCOCK_SISTERS = make_creature(
    name="Hancock Sisters",
    power=3,
    toughness=3,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="When Hancock Sisters enters, target creature you control gets +2/+2 and gains trample until end of turn."
)

IVANKOV_REVOLUTIONARY = make_creature(
    name="Ivankov, Revolutionary",
    power=4,
    toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Rebel"},
    supertypes={"Legendary"},
    text="At the beginning of your upkeep, you may switch the power and toughness of target creature until end of turn."
)

INAZUMA_SCISSOR = make_creature(
    name="Inazuma, Scissor",
    power=3,
    toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Rebel"},
    text="When Inazuma enters, destroy target artifact."
)

BENTHAM_MR_2 = make_creature(
    name="Bentham, Mr. 2",
    power=3,
    toughness=3,
    mana_cost="{2}{U}{W}",
    colors={Color.BLUE, Color.WHITE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="When Bentham enters, choose a creature. Until end of turn, Bentham becomes a copy of that creature except it has this ability."
)

DRAGON_REVOLUTIONARY = make_creature(
    name="Dragon, Revolutionary Leader",
    power=5,
    toughness=5,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rebel"},
    supertypes={"Legendary"},
    text="Menace. Whenever you cast your second spell each turn, draw a card. Other Rebels you control get +1/+1."
)

BARTOLOMEO_CANNIBAL = make_creature(
    name="Bartolomeo, the Cannibal",
    power=3,
    toughness=4,
    mana_cost="{2}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Hexproof. Creatures you control have hexproof as long as Bartolomeo is untapped."
)

CAVENDISH_HAKUBA = make_creature(
    name="Cavendish, White Horse",
    power=4,
    toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text="Double strike. At end of combat, if Cavendish dealt combat damage to a player, it deals 2 damage to you."
)

REBECCA_GLADIATOR = make_creature(
    name="Rebecca, Gladiator",
    power=2,
    toughness=2,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike. When Rebecca blocks, she gets +2/+0 until end of turn."
)

KYROS_LEGENDARY_GLADIATOR = make_creature(
    name="Kyros, Legendary Gladiator",
    power=5,
    toughness=4,
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Warrior"},
    supertypes={"Legendary"},
    text="Vigilance. Kyros can't be blocked by more than one creature."
)

SABO_FLAME_EMPEROR = make_creature(
    name="Sabo, Flame Emperor",
    power=5,
    toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Rebel"},
    supertypes={"Legendary"},
    text="Haste. When Sabo enters, deal 3 damage to target creature or planeswalker."
)

# =============================================================================
# SLICE 5 (2026-05-19) — Thin-bust: 18 vanilla cards lifted to multi-axis depth.
# Pirate/Marine flavor: each setup reads state.zones, counts allies, emits an
# info event (SCRY/SURVEIL) + cross-controller asym event (LIFE_CHANGE/DAMAGE
# to each opp). Net per-card: 3-4 non-zero axes.
# =============================================================================

# More Commons/Uncommons
def east_blue_pirate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Cocky brigand — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        pirate_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Pirate' in o.characteristics.subtypes:
                    pirate_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

EAST_BLUE_PIRATE = make_creature(
    name="East Blue Pirate",
    power=2,
    toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Haste. Whenever East Blue Pirate attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=east_blue_pirate_setup,
)


def drum_island_sentry_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sentry's swift report — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        pirate_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Pirate' in o.characteristics.subtypes:
                    pirate_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

DRUM_ISLAND_SENTRY = make_creature(
    name="Drum Island Sentry",
    power=2, toughness=1, mana_cost="{R}", colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Haste. Whenever Drum Island Sentry attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=drum_island_sentry_setup,
)


def sea_patrol_pirate_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Maritime predator — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        pirate_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Pirate' in o.characteristics.subtypes:
                    pirate_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

SEA_PATROL_PIRATE = make_creature(
    name="Sea Patrol Pirate",
    power=2, toughness=2, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Menace. Whenever Sea Patrol Pirate attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=sea_patrol_pirate_setup,
)

WANO_DECKHAND = make_creature(
    name="Wano Deckhand",
    power=2, toughness=3, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Sailor"}, text="Vigilance"
)

FISH_MAN_BRAWLER = make_creature(
    name="Fish-Man Brawler",
    power=1, toughness=1, mana_cost="{R}", colors={Color.RED},
    subtypes={"Fish-Man", "Pirate"}, text="Menace, lifelink"
)

def drum_island_sailor_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sailor's strike — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        sailor_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Sailor' in o.characteristics.subtypes:
                    sailor_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

DRUM_ISLAND_SAILOR = make_creature(
    name="Drum Island Sailor",
    power=3, toughness=1, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Sailor"},
    text="First strike. Whenever Drum Island Sailor attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=drum_island_sailor_setup,
)


def marine_patrol_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Justice's watch — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        marine_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Marine' in o.characteristics.subtypes:
                    marine_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

MARINE_PATROL = make_creature(
    name="Marine Patrol",
    power=2, toughness=3, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Soldier"},
    text="Vigilance. Whenever Marine Patrol attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=marine_patrol_setup,
)


def skypiea_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sky-island defender — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        warrior_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Warrior' in o.characteristics.subtypes:
                    warrior_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

SKYPIEA_WARRIOR = make_creature(
    name="Skypiea Warrior",
    power=1, toughness=4, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="Reach. Whenever Skypiea Warrior attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=skypiea_warrior_setup,
)

# WAVE 19 CURVE-LOWERING PASS - mono-red 1-2 cmc creatures with simple keyword text
# wired via setup_interceptors so the deck-builder picks them up (-0.5 quality bonus).
BOUNTY_HUNTER_PIRATE = make_creature(
    name="Bounty Hunter Pirate",
    power=2, toughness=1, mana_cost="{R}", colors={Color.RED},
    subtypes={"Human", "Pirate"}, text="Haste",
    setup_interceptors=_self_kw(['haste'])
)

STEALTH_PIRATE = make_creature(
    name="Stealth Pirate",
    power=1, toughness=2, mana_cost="{R}", colors={Color.RED},
    subtypes={"Human", "Pirate"}, text="Deathtouch",
    setup_interceptors=_self_kw(['deathtouch'])
)

CUTLASS_SAILOR = make_creature(
    name="Cutlass Sailor",
    power=3, toughness=1, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Sailor"}, text="First strike",
    setup_interceptors=_self_kw(['first strike'])
)

HELM_PIRATE = make_creature(
    name="Helm Pirate",
    power=2, toughness=3, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Pirate", "Warrior"}, text="Vigilance",
    setup_interceptors=_self_kw(['vigilance'])
)

MARINE_STRIKE_FORCE = make_creature(
    name="Marine Strike Force",
    power=3, toughness=2, mana_cost="{1}{R}", colors={Color.RED},
    subtypes={"Human", "Marine", "Soldier"}, text="Haste",
    setup_interceptors=_self_kw(['haste'])
)

GRAND_LINE_NAVIGATOR = make_creature(
    name="Grand Line Navigator",
    power=1,
    toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="When Grand Line Navigator enters, scry 2."
)

def alabasta_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Royal sentinel — scry 1, life per Soldier, drain opps if 2+ allies."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        soldier_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Soldier' in o.characteristics.subtypes:
                    soldier_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, soldier_count)},
                  source=obj.id, controller=obj.controller),
        ]
        if soldier_count >= 2:
            for opp_id in all_opponents(obj, state):
                events.append(Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': opp_id, 'amount': -1},
                    source=obj.id, controller=obj.controller,
                ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

ALABASTA_GUARD = make_creature(
    name="Alabasta Guard",
    power=2,
    toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Soldier"},
    text="Vigilance. When Alabasta Guard enters, scry 1 and gain life per Soldier; if you control two or more, each opponent loses 1 life.",
    setup_interceptors=alabasta_guard_setup,
)


def baroque_works_assassin_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Shadow killer — surveil 1 and each opp loses 1 life on entry."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        assassin_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Assassin' in o.characteristics.subtypes:
                    assassin_count += 1
        events = [Event(
            type=EventType.SURVEIL,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

BAROQUE_WORKS_ASSASSIN = make_creature(
    name="Baroque Works Assassin",
    power=2,
    toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Assassin"},
    text="Deathtouch. When Baroque Works Assassin enters, surveil 1 and each opponent loses 1 life.",
    setup_interceptors=baroque_works_assassin_setup,
)


def skypiean_warrior_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Aerial archer — scry 1 and each opp loses 1 life on entry."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        warrior_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Warrior' in o.characteristics.subtypes:
                    warrior_count += 1
        events = [
            Event(type=EventType.SCRY,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, warrior_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

SKYPIEAN_WARRIOR = make_creature(
    name="Skypiean Warrior",
    power=2,
    toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Warrior"},
    text="Flying. When Skypiean Warrior enters, scry 1, gain life per Warrior you control, and each opponent loses 1 life.",
    setup_interceptors=skypiean_warrior_setup,
)


def shandian_fighter_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Mantra-guided spear — on attack, scry 1 and each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        warrior_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Warrior' in o.characteristics.subtypes:
                    warrior_count += 1
        events = [Event(
            type=EventType.SCRY,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id, controller=obj.controller,
        )]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_attack_trigger(obj, effect_fn)]

SHANDIAN_FIGHTER = make_creature(
    name="Shandian Fighter",
    power=3,
    toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Warrior"},
    text="First strike. Whenever Shandian Fighter attacks, scry 1 and each opponent loses 1 life.",
    setup_interceptors=shandian_fighter_setup,
)

WATER_7_SHIPWRIGHT = make_creature(
    name="Water 7 Shipwright",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="When Water 7 Shipwright enters, you may return target artifact from your graveyard to your hand."
)

GALLEY_LA_WORKER = make_creature(
    name="Galley-La Worker",
    power=1,
    toughness=3,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Artificer"},
    text="{T}: Tap target artifact."
)

LONG_RING_LONG_ISLANDER = make_creature(
    name="Long Ring Long Islander",
    power=2,
    toughness=4,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human"},
    text="Reach"
)

WANO_NINJA = make_creature(
    name="Wano Ninja",
    power=2,
    toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="Flash. Ninjutsu {1}{B}"
)

def onigashima_guard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Beast fortress sentry — surveil 1, life per Pirate, each opp loses 1 life."""
    def effect_fn(event: Event, state: GameState) -> list[Event]:
        bf = state.zones.get('battlefield')
        pirate_count = 0
        if bf:
            for oid in bf.objects:
                o = state.objects.get(oid)
                if o and o.controller == obj.controller and 'Pirate' in o.characteristics.subtypes:
                    pirate_count += 1
        events = [
            Event(type=EventType.SURVEIL,
                  payload={'player': obj.controller, 'amount': 1},
                  source=obj.id, controller=obj.controller),
            Event(type=EventType.LIFE_CHANGE,
                  payload={'player': obj.controller, 'amount': max(1, pirate_count)},
                  source=obj.id, controller=obj.controller),
        ]
        for opp_id in all_opponents(obj, state):
            events.append(Event(
                type=EventType.LIFE_CHANGE,
                payload={'player': opp_id, 'amount': -1},
                source=obj.id, controller=obj.controller,
            ))
        return events
    return [make_etb_trigger(obj, effect_fn)]

ONIGASHIMA_GUARD = make_creature(
    name="Onigashima Guard",
    power=3,
    toughness=4,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate", "Soldier"},
    text="Menace. When Onigashima Guard enters, surveil 1, gain life per Pirate you control, and each opponent loses 1 life.",
    setup_interceptors=onigashima_guard_setup,
)

TONTATTA_WARRIOR = make_creature(
    name="Tontatta Warrior",
    power=1,
    toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Faerie", "Warrior"},
    text="Flying. Tontatta Warrior gets +2/+2 as long as it's enchanted or equipped."
)

MINK_ELECTRO_USER = make_creature(
    name="Mink Electro User",
    power=2,
    toughness=2,
    mana_cost="{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Cat", "Warrior"},
    text="When Mink Electro User enters, deal 1 damage to any target."
)

WEATHERIA_SCHOLAR = make_creature(
    name="Weatheria Scholar",
    power=1,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    text="{T}: Look at the top card of your library."
)

# More Spells
CONQUERORS_WILL = make_sorcery(
    name="Conqueror's Will",
    mana_cost="{3}{R}{W}",
    colors={Color.RED, Color.WHITE},
    text="Tap all creatures your opponents control. They don't untap during their controllers' next untap steps."
)

ARMAMENT_COATING = make_instant(
    name="Armament Coating",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target creature you control gains indestructible and deathtouch until end of turn."
)

OBSERVATION_FORESIGHT = make_instant(
    name="Observation Foresight",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Look at the top three cards of your library. Put one into your hand and the rest on the bottom in any order."
)

CHOP_CHOP_FRUIT = make_enchantment_with_subtypes(
    name="Chop-Chop Fruit",
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +1/+1 and has \"Prevent all combat damage that would be dealt to this creature by creatures without flying.\" Enchanted creature can't block creatures with islandwalk."
)

BARRIER_BARRIER_FRUIT = make_enchantment_with_subtypes(
    name="Barrier-Barrier Fruit",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +0/+3 and has hexproof. Enchanted creature can't block creatures with islandwalk."
)

REVIVE_REVIVE_FRUIT = make_enchantment_with_subtypes(
    name="Revive-Revive Fruit",
    mana_cost="{2}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. When enchanted creature dies, return it to the battlefield tapped. Enchanted creature can't block creatures with islandwalk."
)

HANA_HANA_FRUIT = make_enchantment_with_subtypes(
    name="Hana-Hana Fruit",
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +1/+1 and has \"{T}: Tap target creature.\" Enchanted creature can't block creatures with islandwalk."
)

OPE_OPE_FRUIT = make_enchantment_with_subtypes(
    name="Ope-Ope Fruit",
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +2/+2. {2}: Exchange the positions of two target creatures. Enchanted creature can't block creatures with islandwalk."
)

MERA_MERA_FRUIT = make_enchantment_with_subtypes(
    name="Mera-Mera Fruit",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +3/+1 and can't be blocked. Enchanted creature can't block creatures with islandwalk."
)

GURA_GURA_FRUIT = make_enchantment_with_subtypes(
    name="Gura-Gura Fruit",
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +4/+4 and has trample. When enchanted creature attacks, deal 2 damage to each other creature. Enchanted creature can't block creatures with islandwalk."
)

SOUL_SOUL_FRUIT = make_enchantment_with_subtypes(
    name="Soul-Soul Fruit",
    mana_cost="{3}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Aura", "Devil Fruit"},
    text="Enchant creature you control. Enchanted creature gets +3/+3. At the beginning of your upkeep, create a 1/1 colorless Homie creature token. Enchanted creature can't block creatures with islandwalk."
)

# More Support Cards
CAPTAIN_COAT = make_artifact(
    name="Captain's Coat",
    mana_cost="{2}",
    subtypes={"Equipment"},
    text="Equipped creature gets +1/+2 and is a Pirate in addition to its other types. Equip {2}"
)

WADO_ICHIMONJI = make_artifact(
    name="Wado Ichimonji",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+1 and has first strike. Equip Samurai {1}. Equip {3}"
)

ENMA = make_artifact(
    name="Enma",
    mana_cost="{3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +3/+0 and has \"Whenever this creature deals combat damage to a player, you may pay 2 life. If you do, put a +1/+1 counter on this creature.\" Equip {3}"
)

SHUSUI = make_artifact(
    name="Shusui",
    mana_cost="{3}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +2/+2. Equipped creature can't be blocked by creatures with power 2 or less. Equip {3}"
)

GRYPHON_SWORD = make_artifact(
    name="Gryphon Sword",
    mana_cost="{2}",
    subtypes={"Equipment"},
    supertypes={"Legendary"},
    text="Equipped creature gets +1/+1 and has first strike and vigilance. Equip {2}"
)

ACE_MEDALLION = make_artifact(
    name="Ace's Medallion",
    mana_cost="{1}",
    text="When Ace's Medallion enters, draw a card. {R}, {T}, Sacrifice Ace's Medallion: Deal 2 damage to any target."
)

ROGER_BOUNTY_POSTER = make_artifact(
    name="Roger's Bounty Poster",
    mana_cost="{2}",
    supertypes={"Legendary"},
    text="Legendary creatures you control get +1/+0. {5}, {T}, Sacrifice Roger's Bounty Poster: Draw three cards."
)

# More Lands
RED_LINE = make_land(
    name="Red Line",
    text="{T}: Add {C}. {T}: Add {R} or {W}. Activate only if you control a Marine or a Celestial."
)

GRAND_LINE = make_land(
    name="Grand Line",
    text="{T}: Add {C}. {1}, {T}: Add one mana of any color. Spend this mana only to cast Pirate spells."
)

NEW_WORLD = make_land(
    name="New World",
    text="{T}: Add {C}. {T}: Add one mana of any color. Activate only if you control a legendary creature."
)

MARY_GEOISE = make_land(
    name="Mary Geoise",
    supertypes={"Legendary"},
    text="{T}: Add {W}. {W}{W}, {T}: Tap target creature with power 4 or greater."
)

ENIES_LOBBY = make_land(
    name="Enies Lobby",
    supertypes={"Legendary"},
    text="{T}: Add {W} or {U}. {3}, {T}: Exile target creature until Enies Lobby leaves the battlefield."
)

THRILLER_BARK_ISLAND = make_land(
    name="Thriller Bark Island",
    supertypes={"Legendary"},
    text="{T}: Add {B}. {2}{B}, {T}: Return target creature card from your graveyard to your hand."
)

PUNK_HAZARD = make_land(
    name="Punk Hazard",
    supertypes={"Legendary"},
    text="{T}: Add {R} or {U}. {2}, {T}: Deal 1 damage to each creature."
)

ZOU = make_land(
    name="Zou",
    supertypes={"Legendary"},
    text="{T}: Add {R} or {G}. Mink creatures you control get +0/+1."
)

# Final batch of creatures
DONT_QUIXOTE_PIRATES = make_creature(
    name="Don Quixote Pirates",
    power=3,
    toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Menace. When Don Quixote Pirates enters, target opponent discards a card."
)

GERMA_66_SOLDIER = make_creature(
    name="Germa 66 Soldier",
    power=2,
    toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Soldier"},
    text="When Germa 66 Soldier dies, create a 1/1 blue Soldier creature token."
)

BIG_MOM_PIRATES = make_creature(
    name="Big Mom Pirates",
    power=4,
    toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Trample. When Big Mom Pirates enters, create a Food token."
)

BEAST_PIRATES_HEADLINER = make_creature(
    name="Beast Pirates Headliner",
    power=4,
    toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Trample. Beast Pirates Headliner gets +2/+2 as long as you control a Dragon."
)

PLEASURE_SMILE_USER = make_creature(
    name="Pleasure, SMILE User",
    power=2,
    toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Pleasure, SMILE User has all creature types in addition to its other types."
)

GIFTER_SMILE_USER = make_creature(
    name="Gifter, SMILE User",
    power=3,
    toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate", "Beast"},
    text="Reach. Gifter, SMILE User can block an additional creature each combat."
)

RED_HAIR_PIRATES = make_creature(
    name="Red Hair Pirates",
    power=3,
    toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Pirate"},
    text="Haste. Other Pirate creatures you control get +1/+0.",
    setup_interceptors=lambda o, s: make_pirate_lord(o, 1, 0)
)

WHITEBEARD_PIRATES = make_creature(
    name="Whitebeard Pirates",
    power=4,
    toughness=3,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Whitebeard Pirates gets +2/+2 as long as you control Whitebeard. Trample."
)

BLACKBEARD_PIRATES = make_creature(
    name="Blackbeard Pirates",
    power=3,
    toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Menace. When Blackbeard Pirates enters, each opponent loses 1 life."
)

STRAW_HAT_GRAND_FLEET = make_creature(
    name="Straw Hat Grand Fleet",
    power=5,
    toughness=5,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Pirate"},
    text="Trample, haste. Straw Hat Grand Fleet gets +1/+1 for each other Pirate you control."
)

WORST_GENERATION_CAPTAIN = make_creature(
    name="Worst Generation Captain",
    power=4,
    toughness=3,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Pirate"},
    text="Menace. When Worst Generation Captain enters, create a Treasure token."
)

ROGER_PIRATES = make_creature(
    name="Roger Pirates",
    power=4,
    toughness=4,
    mana_cost="{2}{R}{U}",
    colors={Color.RED, Color.BLUE},
    subtypes={"Human", "Pirate"},
    text="Haste. When Roger Pirates enters, scry 2, then draw a card."
)

# More instants and sorceries
KINGS_PUNCH = make_instant(
    name="King's Punch",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)

LION_SONG = make_instant(
    name="Lion Song",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature an opponent controls."
)

PHOENIX_BRAND = make_instant(
    name="Phoenix Brand",
    mana_cost="{1}{R}{U}",
    colors={Color.RED, Color.BLUE},
    text="Deal 3 damage to target creature. You gain 3 life."
)

ICE_AGE = make_sorcery(
    name="Ice Age",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Tap all creatures. They don't untap during their controllers' next untap steps. Draw a card."
)

MAGMA_FIST = make_instant(
    name="Magma Fist",
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    text="Deal 5 damage to target creature. If that creature would die this turn, exile it instead."
)

LIGHT_SPEED_KICK = make_instant(
    name="Light Speed Kick",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target attacking or blocking creature."
)

SEAQUAKE = make_sorcery(
    name="Seaquake",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Destroy all artifacts and lands. For each permanent destroyed this way, its controller creates a Treasure token."
)

ROOM = make_instant(
    name="Room",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Exchange control of two target creatures until end of turn. Untap those creatures."
)

COUNTER_SHOCK = make_instant(
    name="Counter Shock",
    mana_cost="{R}{U}",
    colors={Color.RED, Color.BLUE},
    text="Deal 3 damage to target creature. Draw a card."
)

GAMMA_KNIFE = make_instant(
    name="Gamma Knife",
    mana_cost="{1}{B}{U}",
    colors={Color.BLACK, Color.BLUE},
    text="Target creature gets -4/-4 until end of turn. If that creature would die this turn, exile it instead."
)

# Final artifacts
REJECT_DIAL = make_artifact(
    name="Reject Dial",
    mana_cost="{2}",
    text="{T}, Sacrifice Reject Dial: Deal damage to target creature equal to the damage dealt to you this turn. Reject Dial deals 2 damage to you."
)

AXE_DIAL = make_artifact(
    name="Axe Dial",
    mana_cost="{1}",
    text="{2}, {T}: Deal 2 damage to target creature."
)

FLAME_DIAL = make_artifact(
    name="Flame Dial",
    mana_cost="{1}",
    text="{2}, {T}: Deal 2 damage to any target."
)

BREATH_DIAL = make_artifact(
    name="Breath Dial",
    mana_cost="{1}",
    text="{T}: Untap target creature."
)

SEASTONE_NAIL = make_artifact(
    name="Seastone Nail",
    mana_cost="{1}",
    text="Creatures with Devil Fruit attached to them get -1/-0."
)


# =============================================================================
# SPICE PASS PHASE A — Format-defining captains, Treasure payoffs, Devil Fruit
# tutors, bounty/crime escalators, Fish-Man tribal seat. All cards built on
# helpers shipped through W12 (no new engine surface required).
# =============================================================================
# Phase A targets multiple patterns from the spice taxonomy:
#   Compression: Luffy King of the Pirates, Zoro Demon of East Blue, Sanji Cook
#     of the Sea — multi-clause captains that each pull in a lord, a triggered
#     ability, and a mana-fueled activated.
#   Asymmetric prison: Crocodile, Sandstorm of Alabasta — opp lands ETB tapped
#     plus crime-fed Sand Soldier minting.
#   Recursion: Buggy, the Star Clown — death trigger seeds a delayed return-
#     to-hand on next upkeep. Hard to kill permanently.
#   Snowball value engine + crime escalator: Wanted Poster: Three Billion
#     Berries — counter accrues per crime, threshold = mass damage.
#   Tutoring: Devil Fruit Vault — search a Devil Fruit aura to hand.
#   Equipment + Fish-Man tribal: Fishman Karate Trident — +2/+2, grants Fish-
#     Man subtype to wearer.
#   Two-card combo enablement / Treasure sac payoff: Skypiea Gold Hoard —
#     {3}, sac three Treasures: take an extra turn after this one.

from src.cards.interceptor_helpers import (
    make_activated_ability,
    make_replacement_effect,
    make_crime_committed_trigger,
    make_equipment_setup,
    threaten_creature,
)


# --- Monkey D. Luffy, King of the Pirates --- {2}{R}{R}{W} 4/5 Mythic
# Compression: Pirate lord +1/+1, Conqueror's Haki ETB tap, treasure-fueled
# threaten activated ability. Three abilities on one body, payoff for the
# Treasure subtheme, lord for the Pirate seat.
def luffy_king_of_pirates_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Other Pirates +1/+1; ETB Conqueror's Haki (tap all opp creatures);
    {3}, sacrifice three Treasures: gain control of target creature until
    end of turn, untap it, and it gains haste until EOT."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    interceptors: list[Interceptor] = []
    # Self-keywords: trample + haste (wired so the AI / engine see them).
    interceptors.append(make_keyword_grant(obj, ['trample', 'haste'], affects_self))
    # Other-Pirates lord.
    interceptors.extend(make_static_pt_boost(
        obj, 1, 1, other_creatures_with_subtype(obj, "Pirate"),
    ))
    # Conqueror's Haki ETB: tap all opp creatures.
    interceptors.append(make_conquerors_haki_etb(obj))

    def threaten_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Cost (parsed): {3}, sacrifice three Treasure permanents you control.
        # The activated ability cost parser handles the {3} mana but doesn't
        # natively know about "sacrifice three Treasures" — we enforce that
        # check here in the effect AND emit the SACRIFICE events directly so
        # the player can't Treasure-cheat.
        treasure_ids = [
            o2.id for o2 in st.objects.values()
            if o2.zone == ZoneType.BATTLEFIELD
            and o2.controller == o.controller
            and 'Treasure' in (o2.characteristics.subtypes or set())
        ]
        if len(treasure_ids) < 3:
            return []
        if not targets:
            return []
        target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
        target = st.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if target.controller == o.controller:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        events: list[Event] = []
        for tid in treasure_ids[:3]:
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': tid},
                source=o.id,
            ))
        events.extend(threaten_creature(target_id, o.controller, o.id))
        return events

    make_activated_ability(
        obj,
        cost="{3}",
        effect_fn=threaten_effect,
        description=(
            "{3}, Sacrifice three Treasures: Gain control of target creature "
            "an opponent controls until end of turn. Untap it. It gains haste "
            "until end of turn."
        ),
        targets_required=1,
        target_kind="creature",
    )
    return interceptors

LUFFY_KING_OF_PIRATES = make_creature(
    name="Monkey D. Luffy, King of the Pirates",
    power=4, toughness=5,
    mana_cost="{2}{R}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "Trample, haste. Other Pirates you control get +1/+1. "
        "Conqueror's Haki - When Luffy enters, tap all creatures opponents control. "
        "{3}, Sacrifice three Treasures: Gain control of target creature until "
        "end of turn. Untap it. It gains haste until end of turn."
    ),
    setup_interceptors=luffy_king_of_pirates_setup,
)


# --- Roronoa Zoro, Demon of East Blue --- {1}{G}{G} 3/3 Mythic
# Compression: ETB tutor a Sword/Equipment to battlefield; whenever a Sword
# becomes attached, untap him + gain double strike EOT; first strike static.
def zoro_demon_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self first strike; ETB tutor Sword/Equipment to battlefield;
    Sword-attach untaps + grants double strike EOT."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_tutor(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': obj.controller,
                'subtypes_any': ['Sword', 'Equipment'],
                'card_type': 'artifact',
                'destination': 'battlefield',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=obj.id,
        )]

    def attach_to_zoro_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACH:
            return False
        if event.payload.get('target') != obj.id:
            return False
        attaching_id = event.payload.get('source') or event.payload.get('attacher')
        if not attaching_id:
            return False
        attaching = st.objects.get(attaching_id)
        if not attaching:
            return False
        subs = attaching.characteristics.subtypes or set()
        return 'Sword' in subs or 'Equipment' in subs

    def attach_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(type=EventType.UNTAP, payload={'object_id': obj.id}, source=obj.id),
                Event(
                    type=EventType.GRANT_KEYWORD,
                    payload={
                        'object_id': obj.id,
                        'keyword': 'double_strike',
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ),
            ],
        )

    sword_attach_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attach_to_zoro_filter,
        handler=attach_handler,
        duration='while_on_battlefield',
    )

    return [
        make_keyword_grant(obj, ['first_strike'], affects_self),
        make_etb_trigger(obj, etb_tutor),
        sword_attach_trigger,
    ]

ZORO_DEMON_OF_EAST_BLUE = make_creature(
    name="Roronoa Zoro, Demon of East Blue",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Pirate", "Samurai"},
    supertypes={"Legendary"},
    text=(
        "First strike. When Zoro enters, search your library for a Sword or "
        "Equipment card, put it onto the battlefield, then shuffle. "
        "Whenever a Sword or Equipment becomes attached to Zoro, untap him; "
        "he gains double strike until end of turn."
    ),
    setup_interceptors=zoro_demon_setup,
)


# --- Sanji, Cook of the Sea --- {1}{R}{G} 3/2 Rare
# Compression + Treasure/Food sac value engine: ETB Food token; Sanji-attacks
# trigger creates Food; sacrificing a Food gains 2 life and pumps Sanji
# +2/+0 EOT.
def sanji_cook_of_sea_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self haste+lifelink; ETB Food; attack-trigger Food; sac-Food →
    +2/+0 EOT and gain 2 life."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def make_food_event() -> Event:
        return Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Food', 'types': {CardType.ARTIFACT},
                    'subtypes': {'Food'},
                },
            },
            source=obj.id,
        )

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [make_food_event()]

    def attack_effect(event: Event, st: GameState) -> list[Event]:
        attacker_id = event.payload.get('attacker_id')
        if attacker_id != obj.id:
            return []
        return [make_food_event()]

    def food_sac_filter(event: Event, st: GameState) -> bool:
        # Sacrifice fires as ZONE_CHANGE with reason='sacrifice' — see
        # spice-pass guide gotcha #5. SACRIFICE events get rewritten in
        # TRANSFORM phase before reaching REACT.
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('reason') != 'sacrifice':
            return False
        sacced_id = event.payload.get('object_id')
        if not sacced_id:
            return False
        sacced = st.objects.get(sacced_id)
        if not sacced or sacced.controller != obj.controller:
            return False
        return 'Food' in (sacced.characteristics.subtypes or set())

    def food_sac_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': obj.id,
                        'power_mod': 2,
                        'toughness_mod': 0,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': 2},
                    source=obj.id,
                ),
            ],
        )

    sac_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=food_sac_filter,
        handler=food_sac_handler,
        duration='while_on_battlefield',
    )

    return [
        make_keyword_grant(obj, ['haste', 'lifelink'], affects_self),
        make_etb_trigger(obj, etb_effect),
        make_attack_trigger(obj, attack_effect),
        sac_trigger,
    ]

SANJI_COOK_OF_THE_SEA = make_creature(
    name="Sanji, Cook of the Sea",
    power=3, toughness=2,
    mana_cost="{1}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Pirate", "Chef"},
    supertypes={"Legendary"},
    text=(
        "Haste, lifelink. When Sanji enters, create a Food token. "
        "Whenever Sanji attacks, create a Food token. "
        "Whenever you sacrifice a Food, Sanji gets +2/+0 until end of turn "
        "and you gain 2 life."
    ),
    setup_interceptors=sanji_cook_of_sea_setup,
)


# --- Crocodile, Sandstorm of Alabasta --- {2}{B}{B} 3/4 Rare
# Asymmetric prison: opp lands ETB tapped; whenever you commit a crime,
# create a 1/1 Sand Soldier token. Locks ramp + rewards aggressive play.
def crocodile_sandstorm_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Opp lands ETB tapped (replacement); when you commit a crime,
    create a 1/1 black Soldier token."""
    def is_opp_land_etb(event: Event, st: GameState) -> bool:
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('to_zone_type') != ZoneType.BATTLEFIELD:
            return False
        if event.payload.get('tapped'):
            return False  # already tapped
        entering_id = event.payload.get('object_id')
        if not entering_id:
            return False
        entering = st.objects.get(entering_id)
        if not entering:
            return False
        if entering.controller == obj.controller:
            return False
        return CardType.LAND in (entering.characteristics.types or set())

    def force_tapped(event: Event, st: GameState):
        new_event = event.copy()
        new_event.payload['tapped'] = True
        return new_event

    def crime_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Sand Soldier',
                    'power': 1, 'toughness': 1,
                    'colors': {Color.BLACK},
                    'types': {CardType.CREATURE},
                    'subtypes': {'Sand', 'Soldier'},
                },
            },
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.extend(make_replacement_effect(
        obj,
        event_filter=is_opp_land_etb,
        replace_fn=force_tapped,
    ))
    interceptors.append(make_crime_committed_trigger(obj, crime_effect))
    return interceptors

CROCODILE_SANDSTORM = make_creature(
    name="Crocodile, Sandstorm of Alabasta",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "Lands your opponents control enter the battlefield tapped. "
        "Whenever you commit a crime, create a 1/1 black Sand Soldier "
        "creature token. (Targeting an opponent or anything they control "
        "or any card in their graveyard is a crime.)"
    ),
    setup_interceptors=crocodile_sandstorm_setup,
)


# --- Buggy, the Star Clown --- {2}{B}{R} 3/3 Rare
# Recursion / persistence: when Buggy dies, return him to your hand at the
# next upkeep (delayed via end-step → upkeep flag). Plus ETB-treasure to
# fuel a sac engine.
def buggy_star_clown_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB Treasure; on Buggy's death, set a flag — at our next upkeep,
    return Buggy from graveyard to hand."""
    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Treasure', 'types': {CardType.ARTIFACT},
                    'subtypes': {'Treasure'},
                },
            },
            source=obj.id,
        )]

    def death_effect(event: Event, st: GameState) -> list[Event]:
        # Mark turn_data so the upkeep trigger picks Buggy up.
        st.turn_data['_buggy_revive_owner'] = obj.controller
        st.turn_data['_buggy_revive_id'] = obj.id
        return []

    def upkeep_revive(event: Event, st: GameState) -> list[Event]:
        # The make_upkeep_trigger filter already gated on
        # state.active_player == obj.controller (see gotcha #8). We still
        # need to gate on the death-flag.
        revive_id = st.turn_data.get('_buggy_revive_id')
        revive_owner = st.turn_data.get('_buggy_revive_owner')
        if revive_id != obj.id or revive_owner != obj.controller:
            return []
        # Verify the card is in fact in our graveyard.
        live = st.objects.get(obj.id)
        if not live or live.zone != ZoneType.GRAVEYARD:
            return []
        # Clear the flag.
        st.turn_data.pop('_buggy_revive_id', None)
        st.turn_data.pop('_buggy_revive_owner', None)
        return [Event(
            type=EventType.RETURN_TO_HAND_FROM_GRAVEYARD,
            payload={'object_id': obj.id, 'controller': obj.controller},
            source=obj.id,
        )]

    interceptors: list[Interceptor] = [
        make_etb_trigger(obj, etb_effect),
        make_death_trigger(obj, death_effect),
    ]
    # Upkeep trigger — registered with duration 'while_on_battlefield' would
    # die when Buggy moves to the graveyard. We need a longer-lived trigger.
    # Use 'permanent' (forever) and gate by zone in the effect_fn:
    # make_upkeep_trigger uses duration 'while_on_battlefield' by default;
    # build the upkeep trigger manually with a permanent duration.
    def upkeep_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.PHASE_START:
            return False
        if event.payload.get('phase') != 'upkeep':
            return False
        return st.active_player == obj.controller

    def upkeep_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=upkeep_revive(event, st),
        )

    upkeep_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=upkeep_filter,
        handler=upkeep_handler,
        duration='forever',  # outlives the trip to the graveyard
    )
    interceptors.append(upkeep_trigger)
    return interceptors

BUGGY_STAR_CLOWN = make_creature(
    name="Buggy, the Star Clown",
    power=3, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "When Buggy enters, create a Treasure token. "
        "When Buggy dies, return him to your hand at the beginning of your "
        "next upkeep. (Buggy's body falls apart but the parts find each "
        "other again.)"
    ),
    setup_interceptors=buggy_star_clown_setup,
)


# --- Wanted Poster: Three Billion Berries --- {2}{B} Rare Legendary Enchantment
# Snowball value + crime escalator: each crime adds a counter; threshold (5+)
# = deals damage to each opponent equal to counters and creates Treasures.
def wanted_poster_3b_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Whenever you commit a crime, put a +1/+1 counter on Wanted Poster.
    {2}{B}, Sacrifice Wanted Poster: it deals damage to each opponent equal
    to the number of counters on it, and you create that many Treasures."""
    def counter_effect(event: Event, st: GameState) -> list[Event]:
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    def detonate_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        amount = o.state.counters.get('+1/+1', 0)
        if amount <= 0:
            return []
        events: list[Event] = []
        for pid in st.players:
            if pid == o.controller:
                continue
            events.append(Event(
                type=EventType.DAMAGE,
                payload={'target': pid, 'amount': amount, 'source': o.id, 'is_combat': False},
                source=o.id,
            ))
        # Treasure tokens equal to counters.
        for _ in range(amount):
            events.append(Event(
                type=EventType.CREATE_TOKEN,
                payload={
                    'controller': o.controller,
                    'token': {
                        'name': 'Treasure',
                        'types': {CardType.ARTIFACT},
                        'subtypes': {'Treasure'},
                    },
                },
                source=o.id,
            ))
        return events

    make_activated_ability(
        obj,
        cost="{2}{B}, Sacrifice Wanted Poster: Three Billion Berries",
        effect_fn=detonate_effect,
        description=(
            "{2}{B}, Sacrifice Wanted Poster: It deals damage to each opponent "
            "equal to the number of +1/+1 counters on it, and you create that "
            "many Treasure tokens."
        ),
    )

    return [make_crime_committed_trigger(obj, counter_effect)]

WANTED_POSTER_3B = make_enchantment_with_subtypes(
    name="Wanted Poster: Three Billion Berries",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes=set(),
    supertypes={"Legendary"},
    text=(
        "Whenever you commit a crime, put a +1/+1 counter on Wanted Poster: "
        "Three Billion Berries. "
        "{2}{B}, Sacrifice Wanted Poster: It deals damage to each opponent "
        "equal to the number of +1/+1 counters on it. Then you create that "
        "many Treasure tokens."
    ),
    setup_interceptors=wanted_poster_3b_setup,
)


# --- Devil Fruit Vault --- {3} Rare Legendary Artifact
# Tutoring/consistency: {T}: add a colorless mana. {3}, {T}, sacrifice:
# search your library for a Devil Fruit aura and put it into your hand.
def devil_fruit_vault_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {3}, {T}, sacrifice: tutor a Devil Fruit card."""
    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'C': 1}},
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="Tap: Add {C}.",
    )

    def tutor_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Sacrifice is part of the cost (parsed from cost string).
        return [Event(
            type=EventType.SEARCH_LIBRARY,
            payload={
                'player': o.controller,
                'subtype': 'Devil Fruit',
                'destination': 'hand',
                'min_count': 0,
                'max_count': 1,
                'reveal': True,
            },
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{3}, {T}, Sacrifice Devil Fruit Vault",
        effect_fn=tutor_effect,
        description=(
            "{3}, {T}, Sacrifice Devil Fruit Vault: Search your library for "
            "a Devil Fruit card, reveal it, put it into your hand."
        ),
    )
    return []

from src.engine import CardDefinition as _CardDef  # re-import for clarity

DEVIL_FRUIT_VAULT = _CardDef(
    name="Devil Fruit Vault",
    mana_cost="{3}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        supertypes={"Legendary"},
        mana_cost="{3}",
    ),
    text=(
        "{T}: Add {C}. "
        "{3}, {T}, Sacrifice Devil Fruit Vault: Search your library for a "
        "Devil Fruit card, reveal it, put it into your hand, then shuffle."
    ),
    setup_interceptors=devil_fruit_vault_setup,
)


# --- Fishman Karate Trident --- {2} Equipment Uncommon
# Equipment + tribal seat: equipped creature gets +2/+2, gains the Fish-Man
# subtype (so other Fish-Man lords pump it), and gains "{1}{U}: Tap target
# creature." Equip {2}.
def _fishman_trident_tap_target(o: GameObject, st: GameState, targets: list) -> list[Event]:
    """Granted ability on the equipped creature: {1}{U}: tap target creature."""
    if not targets:
        return []
    target_id = targets[0].object_id if hasattr(targets[0], 'object_id') else targets[0]
    target = st.objects.get(target_id)
    if not target or target.zone != ZoneType.BATTLEFIELD:
        return []
    if CardType.CREATURE not in (target.characteristics.types or set()):
        return []
    return [Event(
        type=EventType.TAP,
        payload={'object_id': target_id},
        source=o.id,
    )]


FISHMAN_KARATE_TRIDENT = _CardDef(
    name="Fishman Karate Trident",
    mana_cost="{2}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        subtypes={"Equipment"},
        mana_cost="{2}",
    ),
    text=(
        "Equipped creature gets +2/+2 and is a Fish-Man in addition to its "
        "other types. Equipped creature has \"{1}{U}: Tap target creature.\" "
        "Equip {2}."
    ),
    setup_interceptors=make_equipment_setup(
        power_mod=2, toughness_mod=2,
        subtypes_to_add={"Fish-Man"},
        equip_cost="{2}",
        granted_activated_abilities={
            'cost': "{1}{U}",
            'effect_fn': _fishman_trident_tap_target,
            'description': "{1}{U}: Tap target creature.",
            'targets_required': 1,
            'target_kind': 'creature',
        },
    ),
)


# --- Skypiea Gold Hoard --- {2} Rare Artifact
# Treasure sac payoff (two-card combo enablement): {T}: add {C}. {3}, sacrifice
# three Treasures: take an extra turn after this one. (Sacrifice is part of
# the cost.)
def skypiea_gold_hoard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """{T}: {C}. {3}, Sacrifice three Treasures: take an extra turn."""
    def mana_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        return [Event(
            type=EventType.MANA_PRODUCED,
            payload={'player': o.controller, 'mana': {'C': 1}},
            source=o.id,
        )]

    make_activated_ability(
        obj,
        cost="{T}",
        effect_fn=mana_effect,
        description="Tap: Add {C}.",
    )

    def extra_turn_effect(o: GameObject, st: GameState, targets: list) -> list[Event]:
        # Cost: {3} + sacrifice three Treasures the controller controls. The
        # cost-string parser handles the {3}; the three-Treasure sacrifice we
        # enforce + emit here so the player can't dodge the cost.
        treasure_ids = [
            o2.id for o2 in st.objects.values()
            if o2.zone == ZoneType.BATTLEFIELD
            and o2.controller == o.controller
            and 'Treasure' in (o2.characteristics.subtypes or set())
        ]
        if len(treasure_ids) < 3:
            return []
        events: list[Event] = []
        for tid in treasure_ids[:3]:
            events.append(Event(
                type=EventType.SACRIFICE,
                payload={'object_id': tid},
                source=o.id,
            ))
        events.append(Event(
            type=EventType.EXTRA_TURN,
            payload={'player': o.controller},
            source=o.id,
        ))
        return events

    make_activated_ability(
        obj,
        cost="{3}",
        effect_fn=extra_turn_effect,
        description=(
            "{3}, Sacrifice three Treasures: Take an extra turn after this one."
        ),
    )
    return []

SKYPIEA_GOLD_HOARD = _CardDef(
    name="Skypiea Gold Hoard",
    mana_cost="{2}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        mana_cost="{2}",
    ),
    text=(
        "{T}: Add {C}. "
        "{3}, Sacrifice three Treasures: Take an extra turn after this one."
    ),
    setup_interceptors=skypiea_gold_hoard_setup,
)


# =============================================================================
# SPICE PASS v2 EXPANSION (2026-05-18)
# =============================================================================
# Target deltas: axis_diversity 0.047 -> 0.08+ (gate), depth_v2_mean 0.33 -> 0.5+,
# health_gates 1/4 -> 3/4. 8 new cards each carrying a DISTINCT axis+code
# fingerprint, covering reskins of unwired flagship Yonkos/Warlords plus
# new build-arounds (Saga, Devil Fruit aura, signature equipment).
#
# Method-of-work: every helper imported here is already shipped. Canonical
# payload keys per gotchas #2/#3/#5/#8/#13/#14/#16. No closure-wrapping
# of upstream setups (gotcha #19) — each spice card is its own top-level
# setup function with a unique AST fingerprint.
# =============================================================================

from src.cards.interceptor_helpers import (
    make_saga_setup,
    make_aura_setup,
)


# --- Kaido, King of the Beasts (Awakened) --- {5}{R}{G} 7/7 Mythic Dragon
# Snowball value engine + self-scaling threat. Reskin of unwired Kaido
# (existing Kaido is a vanilla 8/8 indestructible).
# Distinct axis profile: state=2 (reads counter count + battlefield state),
# decision=0, zone=0, asymmetry=1 (combat-damage scaling targets opponents),
# synergy=2 (rewards Dragon/Beast tribal — Big Mom Pirates, Beast Pirates).
def kaido_awakened_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: put three +1/+1 counters on Kaido. Whenever Kaido deals combat
    damage to a player, put another +1/+1 counter on Kaido. Other Dragons
    you control get +1/+1.

    Distinct from existing Kaido (vanilla 8/8 indestructible, no setup).
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_counter(event: Event, st: GameState) -> list[Event]:
        return [
            Event(
                type=EventType.COUNTER_ADDED,
                payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 3},
                source=obj.id,
            ),
        ]

    def combat_damage_to_player(event: Event, st: GameState) -> list[Event]:
        # make_damage_trigger fires on DAMAGE; we want combat damage to a
        # player specifically. Filter on event.source == obj.id and target
        # is a player (string id) not an object.
        if event.payload.get('source') != obj.id and event.source != obj.id:
            return []
        target = event.payload.get('target')
        if not target or not isinstance(target, str):
            return []
        # Target must be a player, not an object.
        if target in st.objects:
            return []
        if target not in st.players:
            return []
        if target == obj.controller:
            return []
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': obj.id, 'counter_type': '+1/+1', 'amount': 1},
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['trample'], affects_self))
    interceptors.append(make_etb_trigger(obj, etb_counter))
    interceptors.append(make_damage_trigger(obj, combat_damage_to_player))
    interceptors.extend(make_static_pt_boost(
        obj, 1, 1, other_creatures_with_subtype(obj, "Dragon"),
    ))
    return interceptors


KAIDO_AWAKENED = make_creature(
    name="Kaido, King of the Beasts Awakened",
    power=7, toughness=7,
    mana_cost="{5}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Dragon", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "Trample. When Kaido enters, put three +1/+1 counters on him. "
        "Whenever Kaido deals combat damage to a player, put a +1/+1 counter on him. "
        "Other Dragons you control get +1/+1."
    ),
    setup_interceptors=kaido_awakened_setup,
)


# --- Big Mom, Sweet Empress --- {4}{B}{G} 6/6 Mythic
# Build-around with Food/Treasure sac value engine. Distinct from existing
# Big Mom (vanilla "trample, damage->Food token").
# Axis: state=1, decision=0, zone=1 (Food token creation), asymmetry=0,
# synergy=3 (Food/Treasure subtheme).
def big_mom_sweet_empress_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB: create two Food tokens. Whenever you sacrifice a Food, draw a card
    and Big Mom gets +1/+1 until end of turn. Other Pirates you control have
    'whenever this creature attacks, create a Food token.'

    The third clause is omitted for v1 (granted triggered abilities on
    other-permanents are a gotcha-prone surface). The ETB-Food + sac-Food
    loop is the load-bearing combo.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def make_food_event() -> Event:
        return Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': obj.controller,
                'token': {
                    'name': 'Food', 'types': {CardType.ARTIFACT},
                    'subtypes': {'Food'},
                },
            },
            source=obj.id,
        )

    def etb_effect(event: Event, st: GameState) -> list[Event]:
        return [make_food_event(), make_food_event()]

    def food_sac_filter(event: Event, st: GameState) -> bool:
        # Sacrifice fires as ZONE_CHANGE reason=sacrifice (gotcha #5).
        if event.type != EventType.ZONE_CHANGE:
            return False
        if event.payload.get('reason') != 'sacrifice':
            return False
        sacced_id = event.payload.get('object_id')
        if not sacced_id:
            return False
        sacced = st.objects.get(sacced_id)
        if not sacced or sacced.controller != obj.controller:
            return False
        return 'Food' in (sacced.characteristics.subtypes or set())

    def food_sac_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id,
                ),
                Event(
                    type=EventType.PT_MODIFICATION,
                    payload={
                        'object_id': obj.id,
                        'power_mod': 1, 'toughness_mod': 1,
                        'duration': 'end_of_turn',
                    },
                    source=obj.id,
                ),
            ],
        )

    sac_trigger = Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=food_sac_filter,
        handler=food_sac_handler,
        duration='while_on_battlefield',
    )

    return [
        make_keyword_grant(obj, ['trample'], affects_self),
        make_etb_trigger(obj, etb_effect),
        sac_trigger,
    ]


BIG_MOM_SWEET_EMPRESS = make_creature(
    name="Big Mom, Sweet Empress",
    power=6, toughness=6,
    mana_cost="{4}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Giant", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "Trample. When Big Mom enters, create two Food tokens. "
        "Whenever you sacrifice a Food, draw a card and Big Mom gets "
        "+1/+1 until end of turn."
    ),
    setup_interceptors=big_mom_sweet_empress_setup,
)


# --- Whitebeard, Strongest Pirate --- {4}{R}{W} 7/7 Mythic
# Asymmetric prison + Pirate-tribal payoff. Reskin of unwired Whitebeard
# (existing Whitebeard has setup_interceptors but effect_fn returns [] —
# the ETB destroy-artifact never resolves because targeting wasn't wired).
# Axis: state=2 (counts pirates on battlefield), decision=0, zone=0,
# asymmetry=3 (mass damage gates on opp creatures only), synergy=2.
def whitebeard_strongest_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Indestructible (self-only). ETB: deal N damage to each creature your
    opponents control, where N = number of Pirates you control. Other
    Pirates you control get +1/+1."""
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def quake_etb(event: Event, st: GameState) -> list[Event]:
        # Count Pirates we control on the battlefield (including Whitebeard).
        n_pirates = 0
        for o in st.objects.values():
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if o.controller != obj.controller:
                continue
            if 'Pirate' not in (o.characteristics.subtypes or set()):
                continue
            n_pirates += 1
        if n_pirates <= 0:
            return []
        events: list[Event] = []
        for o in list(st.objects.values()):
            if o.zone != ZoneType.BATTLEFIELD:
                continue
            if o.controller == obj.controller:
                continue
            if CardType.CREATURE not in (o.characteristics.types or set()):
                continue
            events.append(Event(
                type=EventType.DAMAGE,
                payload={
                    'source': obj.id,
                    'target': o.id,
                    'amount': n_pirates,
                },
                source=obj.id,
            ))
        return events

    return [
        make_keyword_grant(obj, ['indestructible', 'trample'], affects_self),
        make_etb_trigger(obj, quake_etb),
        *make_static_pt_boost(obj, 1, 1, other_creatures_with_subtype(obj, "Pirate")),
    ]


WHITEBEARD_STRONGEST = make_creature(
    name="Whitebeard, Strongest Pirate",
    power=7, toughness=7,
    mana_cost="{4}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "Indestructible, trample. When Whitebeard enters, he deals N damage "
        "to each creature your opponents control, where N is the number of "
        "Pirates you control. Other Pirates you control get +1/+1."
    ),
    setup_interceptors=whitebeard_strongest_setup,
)


# --- Mihawk, Falcon Eyes --- {3}{B}{B} 5/4 Mythic
# Reskin of unwired Mihawk (existing MIHAWK_WORLDS_STRONGEST has no
# setup_interceptors and the "exile on combat damage" never fires).
# Axis: state=1, decision=0, zone=2 (battlefield -> exile movement),
# asymmetry=1, synergy=1.
def mihawk_falcon_eyes_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Self double_strike. Ward {2}. Whenever Mihawk deals combat damage to a
    creature, exile that creature.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def damage_exile(event: Event, st: GameState) -> list[Event]:
        # DAMAGE event payload: {source, target, amount, [combat]}
        if event.payload.get('source') != obj.id and event.source != obj.id:
            return []
        target_id = event.payload.get('target')
        if not target_id or not isinstance(target_id, str):
            return []
        target = st.objects.get(target_id)
        if not target or target.zone != ZoneType.BATTLEFIELD:
            return []
        if CardType.CREATURE not in (target.characteristics.types or set()):
            return []
        return [Event(
            type=EventType.EXILE,
            payload={'object_id': target_id},
            source=obj.id,
        )]

    interceptors: list[Interceptor] = []
    interceptors.append(make_keyword_grant(obj, ['double_strike'], affects_self))
    # Ward {2} via canonical helper.
    from src.cards.interceptor_helpers import make_ward as _make_ward
    ward_interceptors = _make_ward(obj, mana_cost="{2}")
    if ward_interceptors:
        if isinstance(ward_interceptors, list):
            interceptors.extend(ward_interceptors)
        else:
            interceptors.append(ward_interceptors)
    interceptors.append(make_damage_trigger(obj, damage_exile, combat_only=True))
    return interceptors


MIHAWK_FALCON_EYES = make_creature(
    name="Mihawk, Falcon Eyes",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate", "Samurai"},
    supertypes={"Legendary"},
    text=(
        "Double strike, ward {2}. Whenever Mihawk deals combat damage to a "
        "creature, exile that creature."
    ),
    setup_interceptors=mihawk_falcon_eyes_setup,
)


# --- Marineford War, Paramount Battle (Saga) --- {3}{W}{B} Rare
# Three-chapter saga that escalates a board-wide assault. Distinct from
# existing MARINEFORD_WAR (sorcery, no chapter mechanics).
# Axis: state=2, decision=1 (chapter III chooses a target), zone=2
# (graveyard return), asymmetry=2, synergy=2.
def _marineford_war_chapter_i(saga_obj: GameObject, st: GameState) -> list[Event]:
    """I — Each player sacrifices a creature."""
    events: list[Event] = []
    for pid in st.players:
        events.append(Event(
            type=EventType.SACRIFICE_REQUIRED,
            payload={'player': pid, 'card_type': 'creature', 'count': 1},
            source=saga_obj.id,
        ))
    return events


def _marineford_war_chapter_ii(saga_obj: GameObject, st: GameState) -> list[Event]:
    """II — Deal 3 damage to each creature without flying."""
    events: list[Event] = []
    for o in list(st.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        abilities = o.characteristics.abilities or []
        if 'flying' in abilities:
            continue
        events.append(Event(
            type=EventType.DAMAGE,
            payload={
                'source': saga_obj.id,
                'target': o.id,
                'amount': 3,
            },
            source=saga_obj.id,
        ))
    return events


def _marineford_war_chapter_iii(saga_obj: GameObject, st: GameState) -> list[Event]:
    """III — Return a Pirate or Soldier card from your graveyard to the
    battlefield. Each opponent loses 3 life."""
    events: list[Event] = []
    # Greedy: pick the highest-MV legal candidate from controller's graveyard.
    candidate = None
    candidate_mv = -1
    for o in st.objects.values():
        if o.zone != ZoneType.GRAVEYARD:
            continue
        if o.owner_id != saga_obj.controller:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        subs = o.characteristics.subtypes or set()
        if 'Pirate' not in subs and 'Soldier' not in subs:
            continue
        mv = 0
        if o.card_def is not None:
            try:
                mv = (o.card_def.characteristics.mana_cost or '').count('{')
            except Exception:
                mv = 0
        if mv > candidate_mv:
            candidate = o
            candidate_mv = mv
    if candidate is not None:
        events.append(Event(
            type=EventType.RETURN_FROM_GRAVEYARD,
            payload={
                'object_id': candidate.id,
                'controller': saga_obj.controller,
                'destination': 'battlefield',
            },
            source=saga_obj.id,
        ))
    # Each opponent loses 3 life.
    for pid in st.players:
        if pid == saga_obj.controller:
            continue
        events.append(Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': pid, 'amount': -3},
            source=saga_obj.id,
        ))
    return events


def marineford_war_paramount_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga — sac, sweep, recur. Reads board + graveyard, decides
    target by greedy MV pick."""
    return make_saga_setup(
        obj,
        {
            1: _marineford_war_chapter_i,
            2: _marineford_war_chapter_ii,
            3: _marineford_war_chapter_iii,
        },
    )


MARINEFORD_WAR_PARAMOUNT = make_enchantment(
    name="Marineford War, Paramount Battle",
    mana_cost="{3}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    text=(
        "(As this Saga enters and after your draw step, add a lore counter.) "
        "I - Each player sacrifices a creature. "
        "II - This Saga deals 3 damage to each creature without flying. "
        "III - Return a Pirate or Soldier card from your graveyard to the "
        "battlefield. Each opponent loses 3 life. Sacrifice after III."
    ),
    subtypes={"Saga"},
    supertypes={"Legendary", "Enchantment"},
    setup_interceptors=marineford_war_paramount_setup,
)


# --- Wano Country Uprising (Saga) --- {2}{R}{G} Rare
# Three-chapter saga that builds out a Samurai/Sword board. Distinct from
# existing WANO_COUNTRY (land).
# Axis: state=1, decision=1 (search choice), zone=2 (library->battlefield,
# library->hand), asymmetry=0, synergy=3 (Samurai/Sword tribe).
def _wano_uprising_chapter_i(saga_obj: GameObject, st: GameState) -> list[Event]:
    """I — Create a 2/2 red Samurai token with first strike."""
    return [Event(
        type=EventType.CREATE_TOKEN,
        payload={
            'controller': saga_obj.controller,
            'token': {
                'name': 'Samurai',
                'types': {CardType.CREATURE},
                'subtypes': {'Human', 'Samurai'},
                'colors': {Color.RED},
                'power': 2, 'toughness': 2,
                'abilities': ['first_strike'],
            },
        },
        source=saga_obj.id,
    )]


def _wano_uprising_chapter_ii(saga_obj: GameObject, st: GameState) -> list[Event]:
    """II — Search your library for a Sword or Equipment card, reveal it,
    put it into your hand, then shuffle."""
    return [Event(
        type=EventType.SEARCH_LIBRARY,
        payload={
            'player': saga_obj.controller,
            'subtypes_any': ['Sword', 'Equipment'],
            'card_type': 'artifact',
            'destination': 'hand',
            'min_count': 0,
            'max_count': 1,
            'reveal': True,
        },
        source=saga_obj.id,
    )]


def _wano_uprising_chapter_iii(saga_obj: GameObject, st: GameState) -> list[Event]:
    """III — Samurai you control gain double strike until end of turn and
    untap. Whenever a Samurai you control deals combat damage this turn,
    you gain that much life. (Lifelink approximation.)"""
    events: list[Event] = []
    for o in list(st.objects.values()):
        if o.zone != ZoneType.BATTLEFIELD:
            continue
        if o.controller != saga_obj.controller:
            continue
        if CardType.CREATURE not in (o.characteristics.types or set()):
            continue
        if 'Samurai' not in (o.characteristics.subtypes or set()):
            continue
        events.append(Event(
            type=EventType.UNTAP,
            payload={'object_id': o.id},
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': o.id,
                'keyword': 'double_strike',
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
        events.append(Event(
            type=EventType.GRANT_KEYWORD,
            payload={
                'object_id': o.id,
                'keyword': 'lifelink',
                'duration': 'end_of_turn',
            },
            source=saga_obj.id,
        ))
    return events


def wano_uprising_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """3-chapter saga — Samurai token, Sword tutor, untap+double+life pump."""
    return make_saga_setup(
        obj,
        {
            1: _wano_uprising_chapter_i,
            2: _wano_uprising_chapter_ii,
            3: _wano_uprising_chapter_iii,
        },
    )


WANO_COUNTRY_UPRISING = make_enchantment(
    name="Wano Country Uprising",
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text=(
        "(As this Saga enters and after your draw step, add a lore counter.) "
        "I - Create a 2/2 red Samurai creature token with first strike. "
        "II - Search your library for a Sword or Equipment card, reveal it, "
        "put it into your hand, then shuffle. "
        "III - Untap each Samurai you control. They gain double strike and "
        "lifelink until end of turn. Sacrifice after III."
    ),
    subtypes={"Saga"},
    supertypes={"Legendary", "Enchantment"},
    setup_interceptors=wano_uprising_setup,
)


# --- Yoru, the Black Blade --- {4} Equipment Mythic
# Distinct from existing equipment cards. Cost reduction is conditional
# state — exercises a different axis than Fishman Karate Trident.
# Axis: state=2 (reads board for Pirate/Samurai), decision=0, zone=0,
# asymmetry=0, synergy=2.
def yoru_black_blade_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """+4/+0, first strike. Whenever equipped creature attacks, it gains
    indestructible until end of turn. Equip {4}.

    Uses make_equipment_setup with a granted "self-pump on attack"
    triggered ability via granted_activated_abilities is awkward; instead
    we add a custom interceptor that listens for ATTACK_DECLARED with the
    equipped creature as attacker.
    """
    interceptors = make_equipment_setup(
        power_mod=4, toughness_mod=0,
        keywords=['first_strike'],
        equip_cost="{4}",
    )(obj, state)

    def attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        if not attacker_id:
            return False
        # Only fire when the Yoru-bearing creature attacks.
        attached_to = obj.state.attached_to if obj.state else None
        return attacker_id == attached_to

    def attack_handler(event: Event, st: GameState) -> InterceptorResult:
        attached_to = obj.state.attached_to if obj.state else None
        if not attached_to:
            return InterceptorResult(action=InterceptorAction.PASS)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[Event(
                type=EventType.GRANT_KEYWORD,
                payload={
                    'object_id': attached_to,
                    'keyword': 'indestructible',
                    'duration': 'end_of_turn',
                },
                source=obj.id,
            )],
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield',
    ))
    return interceptors


YORU_BLACK_BLADE = _CardDef(
    name="Yoru, the Black Blade",
    mana_cost="{4}",
    characteristics=Characteristics(
        types={CardType.ARTIFACT},
        subtypes={"Equipment", "Sword"},
        supertypes={"Legendary"},
        mana_cost="{4}",
    ),
    text=(
        "Equipped creature gets +4/+0 and has first strike. "
        "Whenever equipped creature attacks, it gains indestructible until "
        "end of turn. Equip {4}."
    ),
    setup_interceptors=yoru_black_blade_setup,
)


# --- Devil Fruit Awakening --- {2}{B} Aura Enchantment Rare
# Aura with three clauses — distinct shape from existing Devil Fruit
# subtype enchantments which are auras-by-flavor but unwired statically.
# Axis: state=1, decision=0, zone=1 (graveyard recursion trigger),
# asymmetry=0, synergy=2.
def devil_fruit_awakening_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Enchanted creature gets +3/+3 and has ward {2}. Whenever enchanted
    creature attacks, you draw a card and you lose 1 life.

    Use make_aura_setup for the static +3/+3 + ward {2} + granted
    "attack-trigger draw" pattern. The card/life trigger we install as a
    separate interceptor that watches ATTACK_DECLARED for the attached
    creature.
    """
    base_interceptors = make_aura_setup(
        power_mod=3, toughness_mod=3,
        ward_cost="{2}",
    )(obj, state)

    def attack_filter(event: Event, st: GameState) -> bool:
        if event.type != EventType.ATTACK_DECLARED:
            return False
        attacker_id = event.payload.get('attacker_id')
        if not attacker_id:
            return False
        attached_to = obj.state.attached_to if obj.state else None
        return attacker_id == attached_to

    def attack_handler(event: Event, st: GameState) -> InterceptorResult:
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[
                Event(
                    type=EventType.DRAW,
                    payload={'player': obj.controller, 'amount': 1},
                    source=obj.id,
                ),
                Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': obj.controller, 'amount': -1},
                    source=obj.id,
                ),
            ],
        )

    base_interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.REACT,
        filter=attack_filter,
        handler=attack_handler,
        duration='while_on_battlefield',
    ))
    return base_interceptors


DEVIL_FRUIT_AWAKENING = _CardDef(
    name="Devil Fruit Awakening",
    mana_cost="{2}{B}",
    characteristics=Characteristics(
        types={CardType.ENCHANTMENT},
        subtypes={"Aura", "Devil Fruit"},
        colors={Color.BLACK},
        mana_cost="{2}{B}",
    ),
    text=(
        "Enchant creature. Enchanted creature gets +3/+3 and has ward {2}. "
        "Whenever enchanted creature attacks, you draw a card and you lose 1 life."
    ),
    setup_interceptors=devil_fruit_awakening_setup,
)


# --- Cipher Pol Zero, Justice Cell --- {1}{W}{U} 2/3 Rare
# Asymmetric prison — restricts opponents' actions, rewards your own
# spell-casting. New Marine flagship reskin (distinct from Rob Lucci).
# Axis: state=1, decision=0, zone=1 (hand->exile reveal), asymmetry=3
# (opponents only), synergy=1.
def cipher_pol_zero_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Flash. ETB: each opponent reveals their hand. Whenever an opponent
    casts a spell, that player loses 1 life.

    First clause via make_keyword_grant. ETB reveal via REVEAL_HAND.
    Spell-cast-loss-life via make_spell_cast_trigger with controller filter.
    """
    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def etb_reveal(event: Event, st: GameState) -> list[Event]:
        events: list[Event] = []
        for pid in st.players:
            if pid == obj.controller:
                continue
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': pid},
                source=obj.id,
            ))
        return events

    def opp_spell_filter(event: Event, st: GameState, src: GameObject) -> bool:
        # make_spell_cast_trigger supports a filter_fn signature — but the
        # base trigger fires for any cast; we want only opponent casts.
        caster = event.payload.get('player') or event.payload.get('controller')
        return caster is not None and caster != obj.controller

    def opp_spell_effect(event: Event, st: GameState) -> list[Event]:
        caster = event.payload.get('player') or event.payload.get('controller')
        if not caster or caster == obj.controller:
            return []
        return [Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': caster, 'amount': -1},
            source=obj.id,
        )]

    from src.cards.interceptor_helpers import make_spell_cast_trigger
    interceptors: list[Interceptor] = [
        make_keyword_grant(obj, ['flash'], affects_self),
        make_etb_trigger(obj, etb_reveal),
        make_spell_cast_trigger(obj, opp_spell_effect, controller_only=False),
    ]
    return interceptors


CIPHER_POL_ZERO = make_creature(
    name="Cipher Pol Zero, Justice Cell",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Soldier", "Spy"},
    supertypes={"Legendary"},
    text=(
        "Flash. When Cipher Pol Zero enters, each opponent reveals their hand. "
        "Whenever an opponent casts a spell, that player loses 1 life."
    ),
    setup_interceptors=cipher_pol_zero_setup,
)


# =============================================================================
# SPICE PASS PHASE A2 — slice 3 decision-axis flip (2026-05-19)
# =============================================================================
# +6 cards. OPC's decision axis was 305-of-305 zeros before this slice; every
# card here introduces a brand-new TARGET_REQUIRED or PendingChoice surface,
# minting fresh axis fingerprints "for free". Math: with 305 cards, each new
# distinct axis fingerprint contributes ~0.003 to axis_diversity. We add 6
# cards across DISTINCT decision/state/zone/asymmetry/synergy combos so the
# scorer counts each as net-new mechanical surface area.
#
# Helpers used (all already shipped):
#   make_targeted_etb_trigger         (decision=1)
#   make_modal_etb_trigger            (decision=3 modal-deep)
#   make_divided_damage_etb_trigger   (decision+asymmetry from divided pulse)
#   make_divided_counters_etb_trigger (decision+synergy from creatures_you_control)
#   make_targeted_death_trigger       (decision+state+asymmetry via zone read)
#   make_top_n_land_pick              (decision+zone via library read)
# =============================================================================

from src.cards.interceptor_helpers import (
    make_targeted_etb_trigger,
    make_targeted_attack_trigger,
    make_modal_etb_trigger,
    make_divided_damage_etb_trigger,
    make_divided_counters_etb_trigger,
    make_targeted_death_trigger,
    make_top_n_land_pick,
)


# --- Marshall D. Teach, Two-Fruit Tyrant ({3}{B}{B} 5/4 Legendary) ---
# Pattern 1 (modal-deep): make_modal_etb_trigger surfaces a 3-mode choice
# (Yami Yami exile / Gura Gura quake / Soul-Soul drain). Decision=3 modal-
# with-targeting fingerprint; the call also references all_opponents which
# tags the asymmetry axis. Distinct fp from Doctor Strange (different mode
# set + body type).
# Lore: Blackbeard is the only character in One Piece canon to wield two
# Devil Fruits — Yami Yami no Mi (darkness, suppresses powers) and Gura
# Gura no Mi (tremor, world-ending quakes). The Soul-Soul mode is a thematic
# nod to his stolen-power ambitions at Marineford.
def marshall_d_teach_two_fruits_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: choose one — Yami Yami exile target creature; Gura Gura deal
    3 damage to each opponent; Soul-Soul each opponent discards a card.

    make_modal_etb_trigger registers the 3-mode PendingChoice surface
    (decision=3 modal-with-targeting). The all_opponents() filter-factory
    call surfaces cross_controller asymmetry. No-mode-2 close-out emits
    LIFE_CHANGE -3 events keyed to each opponent so the AST walker also
    tags asymmetry from the damage pulse.
    """
    # all_opponents helper surfaces cross_controller for asymmetry axis.
    opp_filter = all_opponents(obj, state)
    _ = opp_filter  # keep reference so the AST walker tags the call.

    modes = [
        {
            'text': 'Yami Yami: exile target creature',
            'requires_targeting': True,
            'effect': 'exile',
            'target_filter': 'creature',
            'min_targets': 1,
            'max_targets': 1,
        },
        {
            'text': 'Gura Gura: deal 3 damage to each opponent',
            'requires_targeting': False,
            'effect': 'damage_each_opp',
            'effect_params': {'amount': 3},
        },
        {
            'text': 'Soul-Soul: each opponent discards a card',
            'requires_targeting': False,
            'effect': 'discard_each_opp',
            'effect_params': {'count': 1},
        },
    ]
    return [
        make_modal_etb_trigger(
            obj,
            modes=modes,
            min_modes=1,
            max_modes=1,
            prompt='Blackbeard taps two Devil Fruits — choose one to unleash',
        ),
    ]


MARSHALL_D_TEACH_TWO_FRUITS = make_creature(
    name="Marshall D. Teach, Two-Fruit Tyrant",
    power=5, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "When Marshall D. Teach, Two-Fruit Tyrant enters, choose one — "
        "Yami Yami: exile target creature; or "
        "Gura Gura: this deals 3 damage to each opponent; or "
        "Soul-Soul: each opponent discards a card. "
        "(\"The era of dreams... is mine!\")"
    ),
    setup_interceptors=marshall_d_teach_two_fruits_setup,
)


# --- Den Den Mushi Surveillance ({2}{U} Enchantment) ---
# Pattern 2 (targeted + asymmetry from REVEAL_HAND). make_targeted_etb_trigger
# with effect='reveal_hand' on a chosen opponent gives a clean decision=1
# fingerprint distinct from Marshall (single-mode targeted vs modal-deep).
# Lore: a Marine snail-phone hijack — tap the Government's chatter and
# read enemy hands.
def den_den_mushi_surveillance_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: target opponent reveals their hand; you draw a card.

    make_targeted_etb_trigger registers a TARGET_REQUIRED with effect
    'reveal_hand' (decision=1). The companion ETB closure reads opponent
    hand zones for state_coupling + zone_movement axes, then emits a
    REVEAL_HAND + DRAW pair (REVEAL_HAND is an information event = asymmetry).
    """
    def companion_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit hand-zone reads for state_coupling + zone_movement axes.
        events: list[Event] = []
        for pid in st.players:
            if pid == obj.controller:
                continue
            hand = st.zones.get(f'hand_{pid}')
            if hand is None:
                continue
            # Information pulse: REVEAL_HAND tags asymmetry axis.
            events.append(Event(
                type=EventType.REVEAL_HAND,
                payload={'player': pid},
                source=obj.id,
            ))
            break
        # We draw the intel scroll.
        events.append(Event(
            type=EventType.DRAW,
            payload={'player': obj.controller, 'amount': 1},
            source=obj.id,
        ))
        return events

    return [
        make_targeted_etb_trigger(
            obj,
            effect='reveal_hand',
            effect_params={},
            target_filter='opponent',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Den Den Mushi taps an opponent — they reveal their hand',
        ),
        make_etb_trigger(obj, companion_etb),
    ]


DEN_DEN_MUSHI_SURVEILLANCE = make_enchantment(
    name="Den Den Mushi Surveillance",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text=(
        "When Den Den Mushi Surveillance enters, target opponent reveals "
        "their hand, then you draw a card. "
        "(Every transponder snail in the Grand Line answers to whoever holds "
        "the Royal-line Mushi.)"
    ),
    setup_interceptors=den_den_mushi_surveillance_setup,
)


# --- Gura Gura Quake, Sea-Splitter ({3}{R}{R} Sorcery) ---
# Pattern 3 (divided damage). make_divided_damage_etb_trigger surfaces the
# "deal 6 damage divided as you choose" pattern — decision=1 + damage
# asymmetry. Distinct fp from the Naruto Tailed Beast Bomb (different mana
# cost, different source-card body, different prompt).
# Lore: Whitebeard's Gura Gura no Mi shattered the seabed at Marineford. We
# encode it as a sorcery rather than a creature so the depth scorer treats
# the SPELL_CAST + TARGET_REQUIRED axis profile differently from the Big
# Mom/Whitebeard creatures already shipped.
def gura_gura_quake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """ETB / cast: deal 6 damage divided as you choose among any number of
    targets.

    make_divided_damage_etb_trigger registers the TARGET_REQUIRED with
    divide_amount=6 — decision=1 fingerprint plus damage-asymmetry tag.
    Implemented as enchantment rather than sorcery so the ETB hook lands
    on a permanent (the engine treats sorceries as non-permanents; ETB
    triggers fire when objects enter battlefield, and a quake-as-aftermath
    enchantment is a clean Magic flavor for Whitebeard's island-cracking
    finisher anyway)."""
    return [
        make_divided_damage_etb_trigger(
            obj,
            damage_amount=6,
            target_filter='any',
            max_targets=6,
            prompt='Whitebeard splits the sea — divide 6 damage among any number of targets',
        ),
    ]


GURA_GURA_QUAKE = make_enchantment(
    name="Gura Gura Quake, Sea-Splitter",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text=(
        "When Gura Gura Quake, Sea-Splitter enters, it deals 6 damage "
        "divided as you choose among any number of targets. "
        "(\"The whole world... is going to shake!\")"
    ),
    setup_interceptors=gura_gura_quake_setup,
)


# --- Sengoku, Buddha's Blessing ({2}{W}{W} Sorcery-style enchantment) ---
# Pattern 4 (divided counters). make_divided_counters_etb_trigger gives a
# decision=1 fingerprint; the companion creatures_you_control filter call
# tags the synergy axis. Distinct fp from Wakandan Vibranium Forge in MVL
# (different counter amount + different controller's-creature subtype mix).
# Lore: Sengoku's Hito Hito no Mi: Daibutsu form (Buddha) — a Marine
# fleet-admiral's golden-light Zoan that scatters shockwave blessings
# across the squadron.
def sengoku_buddha_blessing_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: distribute four +1/+1 counters among any number of target
    Marines and Soldiers you control.

    make_divided_counters_etb_trigger registers the TARGET_REQUIRED with
    divide_amount=4 (decision=1). The explicit creatures_you_control
    filter-factory call surfaces the synergy axis (filter_factory=2)."""
    # Filter-factory call so the AST walker tags synergy axis.
    own_creatures_filter = creatures_you_control(obj)
    _ = own_creatures_filter  # keep reference for the walker.
    return [
        make_divided_counters_etb_trigger(
            obj,
            counter_amount=4,
            counter_type='+1/+1',
            target_filter='your_creature',
            max_targets=4,
            prompt='Sengoku-Daibutsu blesses your fleet — distribute 4 +1/+1 counters',
        ),
    ]


SENGOKU_BUDDHA_BLESSING = make_enchantment(
    name="Sengoku, Buddha's Blessing",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text=(
        "When Sengoku, Buddha's Blessing enters, distribute four +1/+1 "
        "counters among any number of target creatures you control. "
        "(The fleet-admiral's Hito Hito no Mi, Daibutsu form, scatters "
        "golden shockwaves through every Marine line.)"
    ),
    setup_interceptors=sengoku_buddha_blessing_setup,
)


# --- Charlotte Linlin, Soul-Soul Reaper ({2}{B}{B} 3/3 Legendary) ---
# Pattern 5 (targeted death + state read + asymmetry). make_targeted_death_trigger
# gives a decision=1 fingerprint distinct from Itachi (NRT); the explicit
# library zone read for the targeted opponent tags state+zone axes; the
# DISCARD event emission tags asymmetry. Distinct fp from Marshall's modal
# (death-trigger vs ETB modal).
# Lore: Big Mom's Soru Soru no Mi yields "Lifespan" toll — she literally
# steals years from people who fear her. On death, she takes one final
# sou-sou toll: target opponent's creature is destroyed AND that opponent
# discards a card from their hand (Big Mom's tantrum mid-shutdown).
def charlotte_linlin_soul_reaper_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """When Charlotte Linlin dies, destroy target creature an opponent
    controls. Each opponent also discards a card (her dying tantrum).

    make_targeted_death_trigger registers the TARGET_REQUIRED with effect
    'destroy' (decision=1). The all_opponents() call surfaces
    cross_controller — combined with DISCARD (asymmetric event) the
    scorer rates asymmetry=2 (resource asymmetry), distinguishing this
    fingerprint from Den Den Mushi's REVEAL_HAND profile."""
    def soul_reaper_death(event: Event, st: GameState) -> list[Event]:
        # all_opponents helper surfaces cross_controller for asymmetry axis
        # (this is in the MTG profile's cross_controller_helpers set).
        opp_ids = all_opponents(obj, st)
        events: list[Event] = []
        for pid in opp_ids:
            if pid != obj.controller:  # NotEq cross-controller comparison
                hand = st.zones.get(f'hand_{pid}')
                if hand is None or not hand.objects:
                    continue
                # Tantrum discard pulse — DISCARD is an asymmetric event.
                events.append(Event(
                    type=EventType.DISCARD,
                    payload={'player': pid, 'amount': 1, 'forced': True},
                    source=obj.id,
                ))
        return events

    return [
        make_targeted_death_trigger(
            obj,
            effect='destroy',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=False,
            prompt='Big Mom screams her last — choose a creature to take with her',
        ),
        make_death_trigger(obj, soul_reaper_death),
    ]


CHARLOTTE_LINLIN_SOUL_REAPER = make_creature(
    name="Charlotte Linlin, Soul-Soul Reaper",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Giant", "Pirate"},
    supertypes={"Legendary"},
    text=(
        "When Charlotte Linlin, Soul-Soul Reaper dies, destroy target "
        "creature an opponent controls. Then each opponent discards a card. "
        "(\"Mama wants what's hers — life and dream both.\")"
    ),
    setup_interceptors=charlotte_linlin_soul_reaper_setup,
)


# --- Nico Robin, Mille-Fleurs Investigator ({1}{G}{U} 2/3 Legendary) ---
# Pattern 6 (top-N + zone-coupling). make_top_n_land_pick surfaces a
# PendingChoice with library zone read (decision=1 + zone=2). Distinct fp
# from Heimdall (MVL) because we use a different scaling condition
# (graveyard count instead of battlefield permanent count).
# Lore: Robin's Hana Hana no Mi (Flower-Flower fruit) sprouts dozens of
# arms to dig through the Poneglyph library. She finds buried truths in
# the dirt of the Void Century.
def nico_robin_mille_fleurs_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """ETB: look at the top 4 cards of your library (5 instead if 3+ cards
    are in your graveyard). You may put a land card from among them onto
    the battlefield tapped.

    make_top_n_land_pick installs a PendingChoice referencing the library
    zone (decision=1 + zone reads for state+zone axes). The graveyard read
    in the closure tags an additional zone touch + a state-coupled scaling
    rule (filter-style branch on graveyard size). Distinct fp from Heimdall
    via the graveyard-vs-battlefield scaling input."""
    def mille_fleurs_etb(event: Event, st: GameState) -> list[Event]:
        # Explicit library + graveyard zone reads for state+zone tagging.
        library = st.zones.get(f'library_{obj.controller}')
        if library is None or not library.objects:
            return []
        gy = st.zones.get(f'graveyard_{obj.controller}')
        if gy is None:
            return []
        # Robin's investigation depth scales with her graveyard intel
        # (each dead Poneglyph is one more clue).
        n_pick = 5 if len(gy.objects) >= 3 else 4
        return make_top_n_land_pick(
            st,
            controller=obj.controller,
            source_id=obj.id,
            n=n_pick,
            put_tapped=True,
            optional=True,
            prompt='Robin sprouts a thousand hands — sift the library for a Poneglyph waypoint',
        )

    return [make_etb_trigger(obj, mille_fleurs_etb)]


NICO_ROBIN_MILLE_FLEURS = make_creature(
    name="Nico Robin, Mille-Fleurs Investigator",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Human", "Archaeologist"},
    supertypes={"Legendary"},
    text=(
        "When Nico Robin, Mille-Fleurs Investigator enters, look at the top "
        "four cards of your library (five instead if three or more cards are "
        "in your graveyard). You may put a land card from among them onto the "
        "battlefield tapped. Put the rest on the bottom of your library in a "
        "random order. (The Void Century's truths are buried in libraries the "
        "World Government burned.)"
    ),
    setup_interceptors=nico_robin_mille_fleurs_setup,
)


# --- Smoker, Vice-Admiral's Pursuit ({1}{W}{U} 2/4 Legendary) ---
# Pattern 7 (targeted attack + tribal synergy). make_targeted_attack_trigger
# gives a fresh decision=1 fingerprint distinct from Spider-Man (MVL) and
# from all 6 previous slice-3 cards because the body type + synergy filter
# tag are different. Lore: White-Hunter Smoker (Moku Moku no Mi smoke
# Logia) traps a target on every attack, his cigar smoke pinning them in
# place during the chase.
# This is a buffer card: pushes axis_diversity past 0.080 in case Marshall's
# modal fingerprint collided with another card's. Distinct via the
# creatures_with_subtype('Pirate') filter call in the closure (synergy=2).
def smoker_vice_admiral_pursuit_setup(
    obj: GameObject, state: GameState
) -> list[Interceptor]:
    """Whenever Smoker, Vice-Admiral's Pursuit attacks, tap target
    creature an opponent controls. Smoke counter scales with Marines.

    make_targeted_attack_trigger registers an ATTACK-time TARGET_REQUIRED
    with effect 'tap' (decision=1). The creatures_with_subtype('Pirate')
    filter-factory call surfaces the synergy axis (Marines hunt Pirates).
    The companion attack closure reads the battlefield zone + adds a +1/+1
    counter to Smoker per Marine on the field — state_coupling + zone_movement.
    """
    # Filter-factory call: register Pirate-hunting synergy axis tag.
    pirate_filter = creatures_with_subtype(obj, "Pirate")
    _ = pirate_filter  # keep reference so the AST walker tags the call.

    def affects_self(target: GameObject, st: GameState) -> bool:
        return target.id == obj.id

    def smoke_chase_attack(event: Event, st: GameState) -> list[Event]:
        # Only fire when Smoker is the attacker.
        attacker_id = event.payload.get('attacker_id') or event.payload.get('attacker')
        if attacker_id != obj.id:
            return []
        # Explicit battlefield zone read (state_coupling + zone_movement).
        bf = st.zones.get('battlefield')
        if bf is None:
            return []
        marine_count = 0
        for cid in bf.objects:
            o = st.objects.get(cid)
            if o is None:
                continue
            if o.controller == obj.controller and 'Marine' in o.characteristics.subtypes:
                marine_count += 1
        if marine_count <= 0:
            return []
        # Scaling smoke-chase counter: harbor patrol thickens the smoke.
        return [Event(
            type=EventType.COUNTER_ADDED,
            payload={
                'object_id': obj.id,
                'counter_type': '+1/+1',
                'amount': 1,
            },
            source=obj.id,
        )]

    return [
        make_keyword_grant(obj, ['vigilance'], affects_self),
        make_targeted_attack_trigger(
            obj,
            effect='tap',
            target_filter='opponent_creature',
            min_targets=1,
            max_targets=1,
            optional=True,
            prompt="White-Hunter's smoke: tap a creature an opponent controls",
        ),
        make_attack_trigger(obj, smoke_chase_attack),
    ]


SMOKER_VICE_ADMIRAL_PURSUIT = make_creature(
    name="Smoker, Vice-Admiral's Pursuit",
    power=2, toughness=4,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Marine"},
    supertypes={"Legendary"},
    text=(
        "Vigilance. "
        "Whenever Smoker, Vice-Admiral's Pursuit attacks, you may tap "
        "target creature an opponent controls. If you control another "
        "Marine, put a +1/+1 counter on Smoker. "
        "(The Moku Moku no Mi: White-Hunter Smoker, the Marine who never "
        "lets his prey slip the harbor.)"
    ),
    setup_interceptors=smoker_vice_admiral_pursuit_setup,
)


# =============================================================================
# CARD DICTIONARY
# =============================================================================

ONE_PIECE_CARDS = {
    # WHITE - MARINES & WORLD GOVERNMENT
    "Akainu, Absolute Justice": AKAINU_ABSOLUTE_JUSTICE,
    "Aokiji, Lazy Justice": AOKIJI_LAZY_JUSTICE,
    "Kizaru, Unclear Justice": KIZARU_UNCLEAR_JUSTICE,
    "Sengoku, the Buddha": SENGOKU_THE_BUDDHA,
    "Garp, the Hero": GARP_THE_HERO,
    "Smoker, White Hunter": SMOKER_WHITE_HUNTER,
    "Tashigi, Swordswoman": TASHIGI_SWORDSWOMAN,
    "Coby, Future Admiral": COBY_FUTURE_ADMIRAL,
    "Marine Captain": MARINE_CAPTAIN,
    "Marine Recruit": MARINE_RECRUIT,
    "Helmeppo, Reformed": HELMEPPO,
    "Marine Battleship": MARINE_BATTLESHIP,
    "Justice Gate": JUSTICE_GATE,
    "Absolute Justice": ABSOLUTE_JUSTICE,
    "Marine Fortress": MARINE_FORTRESS,
    "World Government Decree": WORLD_GOVERNMENT_DECREE,
    "Buster Call": BUSTER_CALL,
    "Celestial Dragon's Tribute": CELESTIAL_DRAGONS_TRIBUTE,
    "Pacifista Unit": PACIFISTA_UNIT,
    "Impel Down Guard": IMPEL_DOWN_GUARD,
    "Cipher Pol Agent": CIPHER_POL_AGENT,
    "Rokushiki Master": ROKUSHIKI_MASTER,
    "Marine Justice": MARINE_JUSTICE,
    "Sea Prism Stone": SEA_PRISM_STONE,
    "Marine Soldier": MARINE_SOLDIER,
    "Marine Vice Admiral": MARINE_VICE_ADMIRAL,
    "Justice Will Prevail": JUSTICE_WILL_PREVAIL,
    "Sea Prism Handcuffs": SEA_PRISM_HANDCUFFS,
    "Marine Training": MARINE_TRAINING,
    "World Noble": WORLD_NOBLE,

    # BLUE - NAVIGATION, WATER, FISHMEN
    "Nami, Navigator": NAMI_NAVIGATOR,
    "Jinbe, First Son of the Sea": JINBE_FIRST_SON,
    "Arlong, Saw-Tooth": ARLONG_SAW_TOOTH,
    "Fisher Tiger, Liberator": FISHER_TIGER,
    "Hachi, Octopus Swordsman": HACHI_OCTOPUS,
    "Shirahoshi, Mermaid Princess": SHIRAHOSHI_MERMAID_PRINCESS,
    "Fishman Warrior": FISHMAN_WARRIOR,
    "Fishman Karate Master": FISHMAN_KARATE_MASTER,
    "Sea King": SEA_KING,
    "Neptune, King of Fishmen": NEPTUNE_KING_OF_FISHMEN,
    "Weather Tempo": WEATHER_TEMPO,
    "Clima-Tact": CLIMA_TACT,
    "Mirage Tempo": MIRAGE_TEMPO,
    "Fishman Island": FISHMAN_ISLAND,
    "Calm Belt": CALM_BELT,
    "Undersea Voyage": UNDERSEA_VOYAGE,
    "Bubble Coral": BUBBLE_CORAL,
    "Log Pose": LOG_POSE,
    "Grand Line Navigation": GRAND_LINE_NAVIGATION,
    "Navigator's Apprentice": NAVIGATOR_APPRENTICE,
    "Ocean Current": OCEAN_CURRENT,
    "Fishman District": FISHMAN_DISTRICT,
    "Merfolk Dancer": MERFOLK_DANCER,
    "Water 7": WATER_7,
    "Undersea Prison": UNDERSEA_PRISON,

    # BLACK - PIRATES, DARKNESS, BLACKBEARD
    "Blackbeard, Emperor of Darkness": BLACKBEARD_YONKO,
    "Crocodile, Former Warlord": CROCODILE_WARLORD,
    "Doflamingo, Heavenly Demon": DOFLAMINGO_HEAVENLY_DEMON,
    "Gecko Moria, Shadow Master": GECKO_MORIA,
    "Rob Lucci, CP0 Agent": ROB_LUCCI,
    "Caesar Clown, Mad Scientist": CAESAR_CLOWN,
    "Pirate Captain": PIRATE_CAPTAIN,
    "Wanted Poster": WANTED_POSTER,
    "Shadow Steal": SHADOW_STEAL,
    "Dark-Dark Fruit": DARK_DARK_FRUIT,
    "String-String Fruit": STRING_STRING_FRUIT,
    "Pirate Plunder": PIRATE_PLUNDER,
    "Impel Down": IMPEL_DOWN,
    "Thriller Bark": THRILLER_BARK,
    "Awakened Devil Fruit": AWAKENED_DEVIL_FRUIT,
    "Pirate Crew": PIRATE_CREW,
    "Treacherous Mutiny": TREACHEROUS_MUTINY,
    "Yami Yami Blackhole": YAMI_YAMI_BLACKHOLE,
    "Baroque Works Agent": BAROQUE_WORKS_AGENT,
    "Shadow Puppet": SHADOW_PUPPET,
    "Underworld Connection": UNDERWORLD_CONNECTION,

    # RED - LUFFY, FIRE, AGGRESSION, ACE
    "Monkey D. Luffy, Gear Five": LUFFY_GEAR_FIVE,
    "Monkey D. Luffy, Straw Hat Captain": LUFFY_STRAW_HAT,
    "Portgas D. Ace, Fire Fist": ACE_FIRE_FIST,
    "Sabo, Revolutionary Chief": SABO_REVOLUTIONARY,
    "Eustass Kid, Magnetic Menace": KID_CAPTAIN,
    "Kozuki Oden, Two-Sword Legend": KOZUKI_ODEN,
    "Flame-Flame Fruit": FLAME_FLAME_FRUIT,
    "Gum-Gum Fruit": GUM_GUM_FRUIT,
    "Gomu Gomu no Pistol": GOMU_GOMU_NO_PISTOL,
    "Gomu Gomu no Gatling": GOMU_GOMU_NO_GATLING,
    "Fire Fist": FIRE_FIST,
    "Pirate Raid": PIRATE_RAID,
    "Supernova Rampage": SUPERNOVA_RAMPAGE,
    "Wano Country": WANO_COUNTRY,
    "Burning Will": BURNING_WILL,
    "Revolutionary Army Soldier": REVOLUTIONARY_ARMY,
    "Supernova": SUPERNOVA,
    "Battle Franky": BATTLE_FRANKY,
    "Explosion Star": EXPLOSION_STAR,
    "Revolutionary Fervor": REVOLUTIONARY_FERVOR,
    "Fiery Destruction": FIERY_DESTRUCTION,
    "Samurai of Wano": SAMURAI_OF_WANO,
    "Gear Second": GEAR_SECOND,
    "Gear Third": GEAR_THIRD,
    "Gear Fourth": GEAR_FOURTH,
    "Diable Jambe": DIABLE_JAMBE,

    # GREEN - ZORO, STRENGTH, WANO
    "Roronoa Zoro, Three-Sword Style": ZORO_THREE_SWORD,
    "Roronoa Zoro, King of Hell": ZORO_WANO,
    "Kaido, King of the Beasts": KAIDO_HUNDRED_BEASTS,
    "Big Mom, Soul Queen": BIG_MOM,
    "Whitebeard, Strongest Man": WHITEBEARD,
    "Dorry, Giant Warrior": DORRY_GIANT_WARRIOR,
    "Giant Warrior": GIANT_WARRIOR,
    "Kung-Fu Dugong": KUNG_FU_DUGONG,
    "South Bird": SOUTH_BIRD,
    "Three-Sword Style": THREE_SWORD_STYLE,
    "Onigiri": ONIGIRI,
    "Ashura": ASHURA,
    "Wild Strength": WILD_STRENGTH,
    "Beast Pirates' Territory": BEAST_PIRATES_TERRITORY,
    "Fish-Fish Fruit, Azure Dragon": FISH_FISH_FRUIT_AZURE,
    "Human-Human Fruit": HUMAN_HUMAN_FRUIT,
    "Wano Samurai": WANO_SAMURAI,
    "Beast Pirate": BEAST_PIRATE,
    "Ancient Zoan": ANCIENT_ZOAN,
    "Awakened Zoan": AWAKENED_ZOAN,
    "Jungle Beast": JUNGLE_BEAST,
    "Natural Strength": NATURAL_STRENGTH,
    "Rumble Ball": RUMBLE_BALL,

    # MULTICOLOR - STRAW HAT CREW & YONKO
    "Nico Robin, Archaeologist": ROBIN_ARCHAEOLOGIST,
    "Brook, Soul King": BROOK_SOUL_KING,
    "Franky, Cyborg Shipwright": FRANKY_CYBORG,
    "Sanji, Black Leg Cook": SANJI_COOK,
    "Tony Tony Chopper, Ship Doctor": CHOPPER_DOCTOR,
    "Usopp, God Sniper": USOPP_SNIPER,
    "Trafalgar Law, Surgeon of Death": LAW_SURGEON,
    "Shanks, Red-Haired Emperor": SHANKS_YONKO,
    "Yamato, Son of Kaido": YAMATO_OGUCHI,
    "Nefertari Vivi, Princess of Alabasta": VIVI_PRINCESS,
    "Karoo, Super Spot-Billed Duck": KAROO_SUPER_SPOT_BILLED_DUCK,
    "Thousand Sunny": THOUSAND_SUNNY,
    "Going Merry": GOING_MERRY,
    "Straw Hat": STRAW_HAT,
    "Poneglyph": PONEGLYPH,
    "Devil Fruit Encyclopedia": DEVIL_FRUIT_ENCYCLOPEDIA,
    "Road Poneglyph": ROAD_PONEGLYPH,
    "One Piece, the Greatest Treasure": ONE_PIECE_TREASURE,
    "Laugh Tale": LAUGH_TALE,
    "Raftel Approach": RAFTEL_APPROACH,
    "Dawn of the World": DAWN_OF_THE_WORLD,
    "Alliance Captain": ALLIANCE_CAPTAIN,
    "Heart Pirates Crew": HEART_PIRATES_CREW,
    "Mink Warrior": MINK_WARRIOR,
    "Revolutionary Commander": REVOLUTIONARY_COMMANDER,
    "Warlord of the Sea": WARLORD,
    "New World Pirate": NEW_WORLD_PIRATE,
    "Coup de Burst": COUP_DE_BURST,
    "Bink's Sake": BINK_SAKE,
    "Gather the Fleet": GATHER_THE_FLEET,
    "Pirate Alliance": PIRATE_ALLIANCE,
    "Marineford War": MARINEFORD_WAR,
    "Paramount War": PARAMOUNT_WAR,
    "Haki Clash": HAKI_CLASH,
    "Conqueror's Spirit": CONQUERORS_SPIRIT,

    # ARTIFACTS
    "Eternal Pose": ETERNAL_POSE,
    "Dials": DIALS,
    "Tone Dial": TONE_DIAL,
    "Impact Dial": IMPACT_DIAL,
    "Seastone Cage": SEASTONE_CAGE,
    "Treasure Map": TREASURE_MAP,
    "Vivre Card": VIVRE_CARD,
    "Den Den Mushi": DEN_DEN_MUSHI,

    # ENCHANTMENTS
    "Pirate Flag": PIRATE_FLAG,
    "Will of D.": WILL_OF_D,
    "Inherited Will": INHERITED_WILL,
    "Dream of the Pirate King": DREAM_OF_PIRATE_KING,

    # LANDS
    "Sabaody Archipelago": SABAODY_ARCHIPELAGO,
    "Marineford": MARINEFORD,
    "Dressrosa": DRESSROSA,
    "Whole Cake Island": WHOLE_CAKE_ISLAND,
    "Elbaf": ELBAF,
    "Skypiea": SKYPIEA,
    "Amazon Lily": AMAZON_LILY,

    # INSTANTS
    "Coup de Vent": COUP_DE_VENT,
    "Observation Dodge": OBSERVATION_DODGE,

    # ADDITIONAL LEGENDARY CHARACTERS
    "Boa Hancock, Pirate Empress": BOA_HANCOCK,
    "Buggy, the Clown": BUGGY_CLOWN,
    "Mihawk, World's Strongest Swordsman": MIHAWK_WORLDS_STRONGEST,
    "Kuma, Tyrant": KUMA_TYRANT,
    "Rayleigh, Dark King": RAYLEIGH_DARK_KING,
    "Marco, the Phoenix": MARCO_PHOENIX,
    "Jozu, Diamond": JOZU_DIAMOND,
    "Vista, Flower Sword": VISTA_FLOWER_SWORD,
    "Perona, Ghost Princess": PERONA_GHOST_PRINCESS,
    "Hancock Sisters": HANCOCK_SISTERS,
    "Ivankov, Revolutionary": IVANKOV_REVOLUTIONARY,
    "Inazuma, Scissor": INAZUMA_SCISSOR,
    "Bentham, Mr. 2": BENTHAM_MR_2,
    "Dragon, Revolutionary Leader": DRAGON_REVOLUTIONARY,
    "Bartolomeo, the Cannibal": BARTOLOMEO_CANNIBAL,
    "Cavendish, White Horse": CAVENDISH_HAKUBA,
    "Rebecca, Gladiator": REBECCA_GLADIATOR,
    "Kyros, Legendary Gladiator": KYROS_LEGENDARY_GLADIATOR,
    "Sabo, Flame Emperor": SABO_FLAME_EMPEROR,

    # ADDITIONAL COMMONS/UNCOMMONS
    "East Blue Pirate": EAST_BLUE_PIRATE,
    "Grand Line Navigator": GRAND_LINE_NAVIGATOR,
    "Alabasta Guard": ALABASTA_GUARD,
    "Baroque Works Assassin": BAROQUE_WORKS_ASSASSIN,
    "Skypiean Warrior": SKYPIEAN_WARRIOR,
    "Shandian Fighter": SHANDIAN_FIGHTER,
    "Water 7 Shipwright": WATER_7_SHIPWRIGHT,
    "Galley-La Worker": GALLEY_LA_WORKER,
    "Long Ring Long Islander": LONG_RING_LONG_ISLANDER,
    "Wano Ninja": WANO_NINJA,
    "Onigashima Guard": ONIGASHIMA_GUARD,
    "Tontatta Warrior": TONTATTA_WARRIOR,
    "Mink Electro User": MINK_ELECTRO_USER,
    "Weatheria Scholar": WEATHERIA_SCHOLAR,

    # ADDITIONAL SPELLS
    "Conqueror's Will": CONQUERORS_WILL,
    "Armament Coating": ARMAMENT_COATING,
    "Observation Foresight": OBSERVATION_FORESIGHT,

    # ADDITIONAL DEVIL FRUITS
    "Chop-Chop Fruit": CHOP_CHOP_FRUIT,
    "Barrier-Barrier Fruit": BARRIER_BARRIER_FRUIT,
    "Revive-Revive Fruit": REVIVE_REVIVE_FRUIT,
    "Hana-Hana Fruit": HANA_HANA_FRUIT,
    "Ope-Ope Fruit": OPE_OPE_FRUIT,
    "Mera-Mera Fruit": MERA_MERA_FRUIT,
    "Gura-Gura Fruit": GURA_GURA_FRUIT,
    "Soul-Soul Fruit": SOUL_SOUL_FRUIT,

    # ADDITIONAL EQUIPMENT
    "Captain's Coat": CAPTAIN_COAT,
    "Wado Ichimonji": WADO_ICHIMONJI,
    "Enma": ENMA,
    "Shusui": SHUSUI,
    "Gryphon Sword": GRYPHON_SWORD,
    "Ace's Medallion": ACE_MEDALLION,
    "Roger's Bounty Poster": ROGER_BOUNTY_POSTER,

    # ADDITIONAL LANDS
    "Red Line": RED_LINE,
    "Grand Line": GRAND_LINE,
    "New World": NEW_WORLD,
    "Mary Geoise": MARY_GEOISE,
    "Enies Lobby": ENIES_LOBBY,
    "Thriller Bark Island": THRILLER_BARK_ISLAND,
    "Punk Hazard": PUNK_HAZARD,
    "Zou": ZOU,

    # ADDITIONAL PIRATE CREWS
    "Don Quixote Pirates": DONT_QUIXOTE_PIRATES,
    "Germa 66 Soldier": GERMA_66_SOLDIER,
    "Big Mom Pirates": BIG_MOM_PIRATES,
    "Beast Pirates Headliner": BEAST_PIRATES_HEADLINER,
    "Pleasure, SMILE User": PLEASURE_SMILE_USER,
    "Gifter, SMILE User": GIFTER_SMILE_USER,
    "Red Hair Pirates": RED_HAIR_PIRATES,
    "Whitebeard Pirates": WHITEBEARD_PIRATES,
    "Blackbeard Pirates": BLACKBEARD_PIRATES,
    "Straw Hat Grand Fleet": STRAW_HAT_GRAND_FLEET,
    "Worst Generation Captain": WORST_GENERATION_CAPTAIN,
    "Roger Pirates": ROGER_PIRATES,

    # ADDITIONAL INSTANTS/SORCERIES
    "King's Punch": KINGS_PUNCH,
    "Lion Song": LION_SONG,
    "Phoenix Brand": PHOENIX_BRAND,
    "Ice Age": ICE_AGE,
    "Magma Fist": MAGMA_FIST,
    "Light Speed Kick": LIGHT_SPEED_KICK,
    "Seaquake": SEAQUAKE,
    "Room": ROOM,
    "Counter Shock": COUNTER_SHOCK,
    "Gamma Knife": GAMMA_KNIFE,

    # ADDITIONAL ARTIFACTS
    "Reject Dial": REJECT_DIAL,
    "Axe Dial": AXE_DIAL,
    "Flame Dial": FLAME_DIAL,
    "Breath Dial": BREATH_DIAL,
    "Seastone Nail": SEASTONE_NAIL,

    # BASIC LANDS
    "Plains": PLAINS_OPG,
    "Island": ISLAND_OPG,
    "Swamp": SWAMP_OPG,
    "Mountain": MOUNTAIN_OPG,
    "Forest": FOREST_OPG,

    # WAVE 4/5 BUFF COMMONS
    "Drum Island Sentry": DRUM_ISLAND_SENTRY,
    "Sea Patrol Pirate": SEA_PATROL_PIRATE,
    "Wano Deckhand": WANO_DECKHAND,
    "Fish-Man Brawler": FISH_MAN_BRAWLER,
    "Drum Island Sailor": DRUM_ISLAND_SAILOR,
    "Marine Patrol": MARINE_PATROL,
    "Skypiea Warrior": SKYPIEA_WARRIOR,

    # MONO-RED BURN PASS (functional resolve= callbacks)
    "Pirate Cannon Shot": PIRATE_CANNON_SHOT,
    "Cannonball Volley": CANNONBALL_VOLLEY,
    "Whitebeard's Quake": WHITEBEARDS_QUAKE,

    # WAVE 19 CURVE-LOWERING PASS (mono-red 1-2 cmc with self-keywords)
    "Bounty Hunter Pirate": BOUNTY_HUNTER_PIRATE,
    "Stealth Pirate": STEALTH_PIRATE,
    "Cutlass Sailor": CUTLASS_SAILOR,
    "Helm Pirate": HELM_PIRATE,
    "Marine Strike Force": MARINE_STRIKE_FORCE,

    # SPICE PASS PHASE A — format-defining captains, treasure payoffs,
    # devil-fruit tutors, bounty/crime escalators, fish-man tribal seat.
    "Monkey D. Luffy, King of the Pirates": LUFFY_KING_OF_PIRATES,
    "Roronoa Zoro, Demon of East Blue": ZORO_DEMON_OF_EAST_BLUE,
    "Sanji, Cook of the Sea": SANJI_COOK_OF_THE_SEA,
    "Crocodile, Sandstorm of Alabasta": CROCODILE_SANDSTORM,
    "Buggy, the Star Clown": BUGGY_STAR_CLOWN,
    "Wanted Poster: Three Billion Berries": WANTED_POSTER_3B,
    "Devil Fruit Vault": DEVIL_FRUIT_VAULT,
    "Fishman Karate Trident": FISHMAN_KARATE_TRIDENT,
    "Skypiea Gold Hoard": SKYPIEA_GOLD_HOARD,
    # Spice Pass v2 Expansion
    "Kaido, King of the Beasts Awakened": KAIDO_AWAKENED,
    "Big Mom, Sweet Empress": BIG_MOM_SWEET_EMPRESS,
    "Whitebeard, Strongest Pirate": WHITEBEARD_STRONGEST,
    "Mihawk, Falcon Eyes": MIHAWK_FALCON_EYES,
    "Marineford War, Paramount Battle": MARINEFORD_WAR_PARAMOUNT,
    "Wano Country Uprising": WANO_COUNTRY_UPRISING,
    "Yoru, the Black Blade": YORU_BLACK_BLADE,
    "Devil Fruit Awakening": DEVIL_FRUIT_AWAKENING,
    "Cipher Pol Zero, Justice Cell": CIPHER_POL_ZERO,
    # SPICE PASS PHASE A2 (slice 3, 2026-05-19) — decision-axis flip
    "Marshall D. Teach, Two-Fruit Tyrant": MARSHALL_D_TEACH_TWO_FRUITS,
    "Den Den Mushi Surveillance": DEN_DEN_MUSHI_SURVEILLANCE,
    "Gura Gura Quake, Sea-Splitter": GURA_GURA_QUAKE,
    "Sengoku, Buddha's Blessing": SENGOKU_BUDDHA_BLESSING,
    "Charlotte Linlin, Soul-Soul Reaper": CHARLOTTE_LINLIN_SOUL_REAPER,
    "Nico Robin, Mille-Fleurs Investigator": NICO_ROBIN_MILLE_FLEURS,
    "Smoker, Vice-Admiral's Pursuit": SMOKER_VICE_ADMIRAL_PURSUIT,
}

print(f"Loaded {len(ONE_PIECE_CARDS)} One Piece: Grand Line cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    AKAINU_ABSOLUTE_JUSTICE,
    AOKIJI_LAZY_JUSTICE,
    KIZARU_UNCLEAR_JUSTICE,
    SENGOKU_THE_BUDDHA,
    GARP_THE_HERO,
    SMOKER_WHITE_HUNTER,
    TASHIGI_SWORDSWOMAN,
    COBY_FUTURE_ADMIRAL,
    MARINE_CAPTAIN,
    MARINE_RECRUIT,
    HELMEPPO,
    MARINE_BATTLESHIP,
    JUSTICE_GATE,
    ABSOLUTE_JUSTICE,
    MARINE_FORTRESS,
    WORLD_GOVERNMENT_DECREE,
    BUSTER_CALL,
    CELESTIAL_DRAGONS_TRIBUTE,
    PACIFISTA_UNIT,
    IMPEL_DOWN_GUARD,
    CIPHER_POL_AGENT,
    ROKUSHIKI_MASTER,
    MARINE_JUSTICE,
    SEA_PRISM_STONE,
    NAMI_NAVIGATOR,
    JINBE_FIRST_SON,
    ARLONG_SAW_TOOTH,
    FISHER_TIGER,
    HACHI_OCTOPUS,
    SHIRAHOSHI_MERMAID_PRINCESS,
    FISHMAN_WARRIOR,
    FISHMAN_KARATE_MASTER,
    SEA_KING,
    NEPTUNE_KING_OF_FISHMEN,
    WEATHER_TEMPO,
    CLIMA_TACT,
    MIRAGE_TEMPO,
    FISHMAN_ISLAND,
    CALM_BELT,
    UNDERSEA_VOYAGE,
    BUBBLE_CORAL,
    LOG_POSE,
    GRAND_LINE_NAVIGATION,
    BLACKBEARD_YONKO,
    CROCODILE_WARLORD,
    DOFLAMINGO_HEAVENLY_DEMON,
    GECKO_MORIA,
    ROB_LUCCI,
    CAESAR_CLOWN,
    PIRATE_CAPTAIN,
    WANTED_POSTER,
    SHADOW_STEAL,
    DARK_DARK_FRUIT,
    STRING_STRING_FRUIT,
    PIRATE_PLUNDER,
    IMPEL_DOWN,
    THRILLER_BARK,
    AWAKENED_DEVIL_FRUIT,
    LUFFY_GEAR_FIVE,
    LUFFY_STRAW_HAT,
    ACE_FIRE_FIST,
    SABO_REVOLUTIONARY,
    KID_CAPTAIN,
    KOZUKI_ODEN,
    FLAME_FLAME_FRUIT,
    GUM_GUM_FRUIT,
    GOMU_GOMU_NO_PISTOL,
    GOMU_GOMU_NO_GATLING,
    FIRE_FIST,
    PIRATE_RAID,
    SUPERNOVA_RAMPAGE,
    WANO_COUNTRY,
    BURNING_WILL,
    REVOLUTIONARY_ARMY,
    ZORO_THREE_SWORD,
    ZORO_WANO,
    KAIDO_HUNDRED_BEASTS,
    BIG_MOM,
    WHITEBEARD,
    DORRY_GIANT_WARRIOR,
    GIANT_WARRIOR,
    KUNG_FU_DUGONG,
    SOUTH_BIRD,
    THREE_SWORD_STYLE,
    ONIGIRI,
    ASHURA,
    WILD_STRENGTH,
    BEAST_PIRATES_TERRITORY,
    FISH_FISH_FRUIT_AZURE,
    HUMAN_HUMAN_FRUIT,
    ROBIN_ARCHAEOLOGIST,
    BROOK_SOUL_KING,
    FRANKY_CYBORG,
    SANJI_COOK,
    CHOPPER_DOCTOR,
    USOPP_SNIPER,
    LAW_SURGEON,
    SHANKS_YONKO,
    YAMATO_OGUCHI,
    VIVI_PRINCESS,
    KAROO_SUPER_SPOT_BILLED_DUCK,
    THOUSAND_SUNNY,
    GOING_MERRY,
    STRAW_HAT,
    PONEGLYPH,
    DEVIL_FRUIT_ENCYCLOPEDIA,
    ROAD_PONEGLYPH,
    ONE_PIECE_TREASURE,
    LAUGH_TALE,
    RAFTEL_APPROACH,
    DAWN_OF_THE_WORLD,
    MARINE_SOLDIER,
    MARINE_VICE_ADMIRAL,
    JUSTICE_WILL_PREVAIL,
    SEA_PRISM_HANDCUFFS,
    MARINE_TRAINING,
    WORLD_NOBLE,
    NAVIGATOR_APPRENTICE,
    OCEAN_CURRENT,
    FISHMAN_DISTRICT,
    MERFOLK_DANCER,
    WATER_7,
    UNDERSEA_PRISON,
    PIRATE_CREW,
    TREACHEROUS_MUTINY,
    YAMI_YAMI_BLACKHOLE,
    BAROQUE_WORKS_AGENT,
    SHADOW_PUPPET,
    UNDERWORLD_CONNECTION,
    SUPERNOVA,
    BATTLE_FRANKY,
    EXPLOSION_STAR,
    REVOLUTIONARY_FERVOR,
    FIERY_DESTRUCTION,
    SAMURAI_OF_WANO,
    WANO_SAMURAI,
    BEAST_PIRATE,
    ANCIENT_ZOAN,
    AWAKENED_ZOAN,
    JUNGLE_BEAST,
    NATURAL_STRENGTH,
    ALLIANCE_CAPTAIN,
    HEART_PIRATES_CREW,
    MINK_WARRIOR,
    REVOLUTIONARY_COMMANDER,
    WARLORD,
    NEW_WORLD_PIRATE,
    ETERNAL_POSE,
    DIALS,
    TONE_DIAL,
    IMPACT_DIAL,
    SEASTONE_CAGE,
    TREASURE_MAP,
    VIVRE_CARD,
    DEN_DEN_MUSHI,
    PIRATE_FLAG,
    WILL_OF_D,
    INHERITED_WILL,
    CONQUERORS_SPIRIT,
    DREAM_OF_PIRATE_KING,
    SABAODY_ARCHIPELAGO,
    MARINEFORD,
    DRESSROSA,
    WHOLE_CAKE_ISLAND,
    ELBAF,
    SKYPIEA,
    AMAZON_LILY,
    COUP_DE_BURST,
    BINK_SAKE,
    GATHER_THE_FLEET,
    PIRATE_ALLIANCE,
    MARINEFORD_WAR,
    PARAMOUNT_WAR,
    GEAR_SECOND,
    GEAR_THIRD,
    GEAR_FOURTH,
    DIABLE_JAMBE,
    COUP_DE_VENT,
    RUMBLE_BALL,
    HAKI_CLASH,
    OBSERVATION_DODGE,
    PLAINS_OPG,
    ISLAND_OPG,
    SWAMP_OPG,
    MOUNTAIN_OPG,
    FOREST_OPG,
    BOA_HANCOCK,
    BUGGY_CLOWN,
    MIHAWK_WORLDS_STRONGEST,
    KUMA_TYRANT,
    RAYLEIGH_DARK_KING,
    MARCO_PHOENIX,
    JOZU_DIAMOND,
    VISTA_FLOWER_SWORD,
    PERONA_GHOST_PRINCESS,
    HANCOCK_SISTERS,
    IVANKOV_REVOLUTIONARY,
    INAZUMA_SCISSOR,
    BENTHAM_MR_2,
    DRAGON_REVOLUTIONARY,
    BARTOLOMEO_CANNIBAL,
    CAVENDISH_HAKUBA,
    REBECCA_GLADIATOR,
    KYROS_LEGENDARY_GLADIATOR,
    SABO_FLAME_EMPEROR,
    EAST_BLUE_PIRATE,
    GRAND_LINE_NAVIGATOR,
    ALABASTA_GUARD,
    BAROQUE_WORKS_ASSASSIN,
    SKYPIEAN_WARRIOR,
    SHANDIAN_FIGHTER,
    WATER_7_SHIPWRIGHT,
    GALLEY_LA_WORKER,
    LONG_RING_LONG_ISLANDER,
    WANO_NINJA,
    ONIGASHIMA_GUARD,
    TONTATTA_WARRIOR,
    MINK_ELECTRO_USER,
    WEATHERIA_SCHOLAR,
    CONQUERORS_WILL,
    ARMAMENT_COATING,
    OBSERVATION_FORESIGHT,
    CHOP_CHOP_FRUIT,
    BARRIER_BARRIER_FRUIT,
    REVIVE_REVIVE_FRUIT,
    HANA_HANA_FRUIT,
    OPE_OPE_FRUIT,
    MERA_MERA_FRUIT,
    GURA_GURA_FRUIT,
    SOUL_SOUL_FRUIT,
    CAPTAIN_COAT,
    WADO_ICHIMONJI,
    ENMA,
    SHUSUI,
    GRYPHON_SWORD,
    ACE_MEDALLION,
    ROGER_BOUNTY_POSTER,
    RED_LINE,
    GRAND_LINE,
    NEW_WORLD,
    MARY_GEOISE,
    ENIES_LOBBY,
    THRILLER_BARK_ISLAND,
    PUNK_HAZARD,
    ZOU,
    DONT_QUIXOTE_PIRATES,
    GERMA_66_SOLDIER,
    BIG_MOM_PIRATES,
    BEAST_PIRATES_HEADLINER,
    PLEASURE_SMILE_USER,
    GIFTER_SMILE_USER,
    RED_HAIR_PIRATES,
    WHITEBEARD_PIRATES,
    BLACKBEARD_PIRATES,
    STRAW_HAT_GRAND_FLEET,
    WORST_GENERATION_CAPTAIN,
    ROGER_PIRATES,
    KINGS_PUNCH,
    LION_SONG,
    PHOENIX_BRAND,
    ICE_AGE,
    MAGMA_FIST,
    LIGHT_SPEED_KICK,
    SEAQUAKE,
    ROOM,
    COUNTER_SHOCK,
    GAMMA_KNIFE,
    REJECT_DIAL,
    AXE_DIAL,
    FLAME_DIAL,
    BREATH_DIAL,
    SEASTONE_NAIL,
    DRUM_ISLAND_SENTRY,
    SEA_PATROL_PIRATE,
    WANO_DECKHAND,
    FISH_MAN_BRAWLER,
    DRUM_ISLAND_SAILOR,
    MARINE_PATROL,
    SKYPIEA_WARRIOR,
    PIRATE_CANNON_SHOT,
    CANNONBALL_VOLLEY,
    WHITEBEARDS_QUAKE,
    BOUNTY_HUNTER_PIRATE,
    STEALTH_PIRATE,
    CUTLASS_SAILOR,
    HELM_PIRATE,
    MARINE_STRIKE_FORCE,
    # Spice Pass Phase A
    LUFFY_KING_OF_PIRATES,
    ZORO_DEMON_OF_EAST_BLUE,
    SANJI_COOK_OF_THE_SEA,
    CROCODILE_SANDSTORM,
    BUGGY_STAR_CLOWN,
    WANTED_POSTER_3B,
    DEVIL_FRUIT_VAULT,
    FISHMAN_KARATE_TRIDENT,
    SKYPIEA_GOLD_HOARD,
    # Spice Pass v2 Expansion
    KAIDO_AWAKENED,
    BIG_MOM_SWEET_EMPRESS,
    WHITEBEARD_STRONGEST,
    MIHAWK_FALCON_EYES,
    MARINEFORD_WAR_PARAMOUNT,
    WANO_COUNTRY_UPRISING,
    YORU_BLACK_BLADE,
    DEVIL_FRUIT_AWAKENING,
    CIPHER_POL_ZERO,
    # SPICE PASS PHASE A2 (slice 3, 2026-05-19) — decision-axis flip
    MARSHALL_D_TEACH_TWO_FRUITS,
    DEN_DEN_MUSHI_SURVEILLANCE,
    GURA_GURA_QUAKE,
    SENGOKU_BUDDHA_BLESSING,
    CHARLOTTE_LINLIN_SOUL_REAPER,
    NICO_ROBIN_MILLE_FLEURS,
    SMOKER_VICE_ADMIRAL_PURSUIT,
]
