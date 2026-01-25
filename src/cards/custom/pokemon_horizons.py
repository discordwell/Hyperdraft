"""
Pokemon Horizons (PKH) Card Implementations

Set featuring Pokemon mechanics: Evolve, Catch, Type Advantage
~250 cards across all colors

Converted to use the declarative ability system.
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness,
    # Ability system imports
    TriggeredAbility, StaticAbility, KeywordAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, DealsDamageTrigger,
    UpkeepTrigger, SpellCastTrigger,
    GainLife, LoseLife, DrawCards, DealDamage, CompositeEffect,
    PTBoost, KeywordGrant,
    SelfTarget, AnotherCreature, AnotherCreatureYouControl,
    OtherCreaturesYouControlFilter, CreaturesWithSubtypeFilter, CreaturesYouControlFilter,
    OpponentCreaturesFilter,
    EachOpponentTarget,
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
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(types={CardType.SORCERY}, subtypes=subtypes or set(), supertypes=supertypes or set(), colors=colors, mana_cost=mana_cost),
        text=text, resolve=resolve
    )

def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(types={CardType.ARTIFACT}, subtypes=subtypes or set(), supertypes=supertypes or set(), mana_cost=mana_cost),
        text=text, setup_interceptors=setup_interceptors
    )

def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, setup_interceptors=None):
    base_subtypes = {"Equipment"}
    if subtypes: base_subtypes.update(subtypes)
    return CardDefinition(
        name=name, mana_cost=mana_cost,
        characteristics=Characteristics(types={CardType.ARTIFACT}, subtypes=base_subtypes, mana_cost=mana_cost),
        text=f"{text}\nEquip {equip_cost}", setup_interceptors=setup_interceptors
    )

def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
    return CardDefinition(
        name=name, mana_cost="",
        characteristics=Characteristics(types={CardType.LAND}, subtypes=subtypes or set(), supertypes=supertypes or set(), mana_cost=""),
        text=text
    )


# =============================================================================
# POKEMON KEYWORD MECHANICS
# =============================================================================

def pokemon_filter(source: GameObject, subtype: str) -> Callable[[GameObject, GameState], bool]:
    return creatures_with_subtype(source, subtype)

def make_evolve_trigger(source_obj: GameObject, evolved_name: str, evolved_power: int, evolved_toughness: int, mana_cost: str) -> Interceptor:
    """Evolve - Pay cost to transform into evolved form."""
    def evolve_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ACTIVATE and
                event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'evolve')

    def evolve_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={
                'object_id': source_obj.id,
                'new_name': evolved_name,
                'new_power': evolved_power,
                'new_toughness': evolved_toughness
            },
            source=source_obj.id
        )
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[transform_event])

    return Interceptor(
        id=new_id(), source=source_obj.id, controller=source_obj.controller,
        priority=InterceptorPriority.REACT, filter=evolve_filter, handler=evolve_handler,
        duration='while_on_battlefield'
    )

def make_type_advantage(source_obj: GameObject, bonus_damage: int, target_subtypes: set[str]) -> Interceptor:
    """Type Advantage - Deal extra damage to certain types."""
    def damage_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.DAMAGE:
            return False
        if event.payload.get('source') != source_obj.id:
            return False
        target_id = event.payload.get('target')
        target = state.objects.get(target_id)
        if not target:
            return False
        return bool(target.characteristics.subtypes & target_subtypes)

    def damage_handler(event: Event, state: GameState) -> InterceptorResult:
        new_event = event.copy()
        new_event.payload['amount'] = event.payload.get('amount', 0) + bonus_damage
        return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

    return Interceptor(
        id=new_id(), source=source_obj.id, controller=source_obj.controller,
        priority=InterceptorPriority.TRANSFORM, filter=damage_filter, handler=damage_handler,
        duration='while_on_battlefield'
    )


# =============================================================================
# WHITE CARDS - NORMAL, FAIRY
# =============================================================================

# --- Legendary Pokemon ---

ARCEUS = make_creature(
    name="Arceus, The Original One",
    power=6, toughness=6,
    mana_cost="{3}{W}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Normal"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Flying"),
        KeywordAbility("Vigilance"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(5)
        ),
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=OtherCreaturesYouControlFilter()
        )
    ]
)

TOGEKISS = make_creature(
    name="Togekiss, Jubilee Pokemon",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy", "Flying"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Flying"),
        KeywordAbility("Lifelink"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(3)
        )
    ]
)

CLEFABLE = make_creature(
    name="Clefable, Fairy Queen",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["hexproof"]),
            filter=CreaturesWithSubtypeFilter("Fairy", include_self=False)
        )
    ]
)

SYLVEON = make_creature(
    name="Sylveon, Intertwining Pokemon",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Pokemon", "Fairy"},
    supertypes={"Legendary"},
    text="Lifelink. Whenever Sylveon deals combat damage to a player, you may return target creature to its owner's hand."
)

# --- Regular White Pokemon ---

def eevee_w_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Sylveon", 2, 3, "{W}{W}")]

EEVEE_W = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Evolve {W}{W}: Transform Eevee into Sylveon.",
    setup_interceptors=eevee_w_setup
)

def clefairy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Clefable", 3, 3, "{1}{W}{W}")]

CLEFAIRY = make_creature(
    name="Clefairy", power=1, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="Evolve {1}{W}{W}: Transform Clefairy into Clefable.",
    setup_interceptors=clefairy_setup
)

def togepi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Togetic", 2, 2, "{1}{W}")]

TOGEPI = make_creature(
    name="Togepi", power=0, toughness=2, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="Defender. Evolve {1}{W}: Transform Togepi into Togetic.",
    setup_interceptors=togepi_setup
)

TOGETIC = make_creature(
    name="Togetic", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy", "Flying"},
    text="Flying. Evolve {2}{W}{W}: Transform Togetic into Togekiss."
)

CHANSEY = make_creature(
    name="Chansey", power=1, toughness=5, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="{T}: Prevent the next 3 damage that would be dealt to target creature this turn."
)

BLISSEY = make_creature(
    name="Blissey", power=2, toughness=6, mana_cost="{3}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Lifelink. When Blissey enters, you gain life equal to the number of creatures you control."
)

SNORLAX = make_creature(
    name="Snorlax", power=5, toughness=6, mana_cost="{4}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Defender, vigilance. Snorlax can't attack unless you pay {2}."
)

JIGGLYPUFF = make_creature(
    name="Jigglypuff", power=1, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Fairy"},
    text="When Jigglypuff enters, tap target creature. It doesn't untap during its controller's next untap step."
)

WIGGLYTUFF = make_creature(
    name="Wigglytuff", power=2, toughness=4, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Fairy"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Fairy", include_self=False)
        )
    ]
)

PERSIAN = make_creature(
    name="Persian", power=3, toughness=2, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="First strike. When Persian deals combat damage to a player, create a Treasure token."
)

MEOWTH = make_creature(
    name="Meowth", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="When Meowth dies, create a Treasure token."
)

PIDGEOT = make_creature(
    name="Pidgeot", power=3, toughness=3, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Flying"},
    text="Flying, vigilance. When Pidgeot enters, look at the top three cards of your library. Put one into your hand and the rest on the bottom."
)

PIDGEY = make_creature(
    name="Pidgey", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal", "Flying"},
    abilities=[KeywordAbility("Flying")]
)

RATTATA = make_creature(
    name="Rattata", power=1, toughness=1, mana_cost="{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    abilities=[KeywordAbility("Haste")]
)

RATICATE = make_creature(
    name="Raticate", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    abilities=[KeywordAbility("First strike"), KeywordAbility("Haste")]
)

FURRET = make_creature(
    name="Furret", power=2, toughness=2, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="When Furret enters, you may search your library for a basic land card, reveal it, and put it into your hand. Then shuffle."
)

AUDINO = make_creature(
    name="Audino", power=2, toughness=3, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(2)
        )
    ]
)

DITTO = make_creature(
    name="Ditto", power=0, toughness=1, mana_cost="{1}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Ditto enters as a copy of any creature on the battlefield."
)

SLAKING = make_creature(
    name="Slaking", power=6, toughness=6, mana_cost="{4}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Vigilance. Slaking doesn't untap during your untap step. At the beginning of your upkeep, you may pay {2}. If you do, untap Slaking."
)

MILTANK = make_creature(
    name="Miltank", power=2, toughness=4, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="{T}: You gain 2 life."
)

TAUROS = make_creature(
    name="Tauros", power=3, toughness=3, mana_cost="{2}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Normal"},
    text="Trample. Tauros attacks each combat if able."
)

GRANBULL = make_creature(
    name="Granbull", power=4, toughness=3, mana_cost="{3}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    text="When Granbull enters, destroy target enchantment."
)

FLORGES = make_creature(
    name="Florges", power=2, toughness=4, mana_cost="{2}{W}{W}",
    colors={Color.WHITE}, subtypes={"Pokemon", "Fairy"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(["lifelink"]),
            filter=CreaturesWithSubtypeFilter("Fairy", include_self=False)
        )
    ]
)

# --- White Trainers (Instants/Sorceries) ---

POTION = make_instant(
    name="Potion", mana_cost="{W}", colors={Color.WHITE},
    text="You gain 3 life."
)

SUPER_POTION = make_instant(
    name="Super Potion", mana_cost="{1}{W}", colors={Color.WHITE},
    text="You gain 5 life. If you control a Pokemon, draw a card."
)

HYPER_POTION = make_instant(
    name="Hyper Potion", mana_cost="{2}{W}", colors={Color.WHITE},
    text="You gain 7 life and prevent all damage that would be dealt to you this turn."
)

FULL_RESTORE = make_instant(
    name="Full Restore", mana_cost="{2}{W}{W}", colors={Color.WHITE},
    text="Target creature you control gains indestructible until end of turn. You gain life equal to its toughness."
)

POKEMON_CENTER = make_sorcery(
    name="Pokemon Center", mana_cost="{1}{W}", colors={Color.WHITE},
    text="You gain 2 life for each Pokemon you control."
)

PROFESSOR_OAK = make_sorcery(
    name="Professor Oak's Advice", mana_cost="{2}{W}", colors={Color.WHITE},
    text="Draw two cards. You gain 2 life."
)

HEAL_BELL = make_instant(
    name="Heal Bell", mana_cost="{1}{W}", colors={Color.WHITE},
    text="Remove all counters from target creature. You gain 3 life."
)

PROTECT = make_instant(
    name="Protect", mana_cost="{W}", colors={Color.WHITE},
    text="Target creature you control gains protection from the color of your choice until end of turn."
)

SAFEGUARD = make_instant(
    name="Safeguard", mana_cost="{1}{W}", colors={Color.WHITE},
    text="Creatures you control gain hexproof until end of turn."
)

MOONBLAST = make_instant(
    name="Moonblast", mana_cost="{2}{W}", colors={Color.WHITE},
    text="Target creature gets -3/-0 until end of turn. You gain 3 life."
)


# =============================================================================
# BLUE CARDS - WATER, ICE, PSYCHIC
# =============================================================================

# --- Legendary Pokemon ---

MEWTWO = make_creature(
    name="Mewtwo, Genetic Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=SpellCastTrigger(spell_types={CardType.INSTANT, CardType.SORCERY}, controller_only=True),
            effect=DrawCards(1)
        )
    ]
)

MEW = make_creature(
    name="Mew, New Species Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Flying"),
        KeywordAbility("Hexproof"),
        StaticAbility(
            effect=KeywordGrant(["hexproof"]),
            filter=CreaturesYouControlFilter()
        )
    ],
    text="Flying, hexproof. {U}: Mew becomes a copy of another target creature until end of turn."
)

LUGIA = make_creature(
    name="Lugia, Diving Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic", "Flying"},
    supertypes={"Legendary"},
    text="Flying. When Lugia enters, return up to two target nonland permanents to their owners' hands."
)

SUICUNE = make_creature(
    name="Suicune, Aurora Pokemon",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="Hexproof. Whenever Suicune deals combat damage to a player, scry 2, then draw a card."
)

ARTICUNO = make_creature(
    name="Articuno, Freeze Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{U}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Ice", "Flying"},
    supertypes={"Legendary"},
    text="Flying. When Articuno enters, tap all creatures your opponents control. They don't untap during their controllers' next untap steps."
)

KYOGRE = make_creature(
    name="Kyogre, Sea Basin Pokemon",
    power=6, toughness=6,
    mana_cost="{4}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="When Kyogre enters, return all other creatures to their owners' hands."
)

def blastoise_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_type_advantage(obj, 2, {"Fire"})

BLASTOISE = make_creature(
    name="Blastoise, Shellfish Pokemon",
    power=4, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Water"},
    supertypes={"Legendary"},
    text="Type Advantage - Blastoise deals 2 extra damage to Fire Pokemon. {T}: Blastoise deals 2 damage to any target.",
    setup_interceptors=blastoise_setup
)

ALAKAZAM = make_creature(
    name="Alakazam, Psi Pokemon",
    power=3, toughness=2,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Pokemon", "Psychic"},
    supertypes={"Legendary"},
    text="Flash. When Alakazam enters, counter target spell unless its controller pays {3}."
)

# --- Regular Blue Pokemon ---

def squirtle_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Wartortle", 2, 3, "{1}{U}")]

SQUIRTLE = make_creature(
    name="Squirtle", power=1, toughness=2, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {1}{U}: Transform Squirtle into Wartortle.",
    setup_interceptors=squirtle_setup
)

WARTORTLE = make_creature(
    name="Wartortle", power=2, toughness=3, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {2}{U}{U}: Transform Wartortle into Blastoise."
)

def psyduck_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Golduck", 3, 3, "{1}{U}{U}")]

PSYDUCK = make_creature(
    name="Psyduck", power=1, toughness=2, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="Evolve {1}{U}{U}: Transform Psyduck into Golduck.",
    setup_interceptors=psyduck_setup
)

GOLDUCK = make_creature(
    name="Golduck", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(1)
        )
    ]
)

VAPOREON = make_creature(
    name="Vaporeon", power=3, toughness=3, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="When Vaporeon enters, draw a card then discard a card."
)

def eevee_u_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Vaporeon", 3, 3, "{U}{U}")]

EEVEE_U = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Normal"},
    text="Evolve {U}{U}: Transform Eevee into Vaporeon.",
    setup_interceptors=eevee_u_setup
)

SLOWPOKE = make_creature(
    name="Slowpoke", power=1, toughness=3, mana_cost="{1}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="Evolve {2}{U}{U}: Transform Slowpoke into Slowbro."
)

SLOWBRO = make_creature(
    name="Slowbro", power=2, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    text="When Slowbro enters, tap target creature. It doesn't untap during its controller's next untap step."
)

LAPRAS = make_creature(
    name="Lapras", power=3, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="When Lapras enters, scry 3."
)

DEWGONG = make_creature(
    name="Dewgong", power=3, toughness=3, mana_cost="{2}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="When Dewgong enters, tap target creature an opponent controls."
)

STARMIE = make_creature(
    name="Starmie", power=2, toughness=3, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Psychic"},
    abilities=[
        KeywordAbility("Flash"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(1)
        )
    ]
)

STARYU = make_creature(
    name="Staryu", power=1, toughness=2, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {U}{U}: Transform Staryu into Starmie."
)

TENTACRUEL = make_creature(
    name="Tentacruel", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Poison"},
    text="Flash. When Tentacruel enters, return target creature to its owner's hand."
)

GYARADOS = make_creature(
    name="Gyarados", power=5, toughness=4, mana_cost="{3}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Flying"},
    text="Flying. When Gyarados enters, each opponent discards a card."
)

MAGIKARP = make_creature(
    name="Magikarp", power=0, toughness=1, mana_cost="{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="Evolve {3}{U}{U}: Transform Magikarp into Gyarados. This ability costs {2} less if a creature died this turn."
)

MILOTIC = make_creature(
    name="Milotic", power=3, toughness=4, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water"},
    text="When Milotic enters, you may return target enchantment to its owner's hand."
)

ESPEON = make_creature(
    name="Espeon", power=3, toughness=2, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic"},
    text="When Espeon enters, look at target opponent's hand."
)

GARDEVOIR = make_creature(
    name="Gardevoir", power=3, toughness=3, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic", "Fairy"},
    text="Flash. When Gardevoir enters, counter target spell unless its controller pays {2}."
)

GALLADE = make_creature(
    name="Gallade", power=4, toughness=2, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic", "Fighting"},
    abilities=[
        KeywordAbility("First strike"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(1)
        )
    ]
)

WOBBUFFET = make_creature(
    name="Wobbuffet", power=1, toughness=5, mana_cost="{2}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Psychic"},
    text="Defender. Whenever Wobbuffet is dealt damage, it deals that much damage to any target."
)

GLACEON = make_creature(
    name="Glaceon", power=3, toughness=2, mana_cost="{1}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Ice"},
    text="When Glaceon enters, tap target creature. It doesn't untap during its controller's next untap step."
)

WALREIN = make_creature(
    name="Walrein", power=4, toughness=4, mana_cost="{3}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Ice", "Water"},
    text="When Walrein enters, tap up to two target creatures."
)

CLOYSTER = make_creature(
    name="Cloyster", power=2, toughness=5, mana_cost="{2}{U}{U}",
    colors={Color.BLUE}, subtypes={"Pokemon", "Water", "Ice"},
    text="Defender. {U}: Cloyster gains hexproof until end of turn."
)

# --- Blue Trainers ---

DIVE_BALL = make_instant(
    name="Dive Ball", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Search your library for a Water Pokemon card, reveal it, and put it into your hand. Then shuffle."
)

MISTY_DETERMINATION = make_instant(
    name="Misty's Determination", mana_cost="{U}{U}", colors={Color.BLUE},
    text="Draw two cards, then discard a card."
)

CONFUSION = make_instant(
    name="Confusion", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)

PSYCHIC = make_instant(
    name="Psychic", mana_cost="{2}{U}{U}", colors={Color.BLUE},
    text="Counter target spell."
)

HYDRO_PUMP = make_instant(
    name="Hydro Pump", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Return target creature to its owner's hand. Draw a card."
)

BLIZZARD = make_sorcery(
    name="Blizzard", mana_cost="{3}{U}{U}", colors={Color.BLUE},
    text="Tap all creatures your opponents control. They don't untap during their controllers' next untap steps."
)

SURF = make_sorcery(
    name="Surf", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Draw three cards, then discard two cards."
)

TELEKINESIS = make_instant(
    name="Telekinesis", mana_cost="{U}", colors={Color.BLUE},
    text="Return target creature with mana value 2 or less to its owner's hand."
)

AMNESIA = make_sorcery(
    name="Amnesia", mana_cost="{2}{U}", colors={Color.BLUE},
    text="Target opponent reveals their hand. You choose a nonland card from it. That player discards that card."
)

FUTURE_SIGHT_SPELL = make_sorcery(
    name="Future Sight", mana_cost="{1}{U}", colors={Color.BLUE},
    text="Scry 3, then draw a card."
)


# =============================================================================
# BLACK CARDS - DARK, GHOST, POISON
# =============================================================================

# --- Legendary Pokemon ---

GENGAR = make_creature(
    name="Gengar, Shadow Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Ghost", "Poison"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Menace"),
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(3, target=EachOpponentTarget())
        )
    ]
)

DARKRAI = make_creature(
    name="Darkrai, Pitch-Black Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(your_upkeep=True),
            effect=LoseLife(1, target=EachOpponentTarget())
        )
    ],
    text="At the beginning of your upkeep, each opponent loses 1 life. Creatures your opponents control enter the battlefield tapped."
)

YVELTAL = make_creature(
    name="Yveltal, Destruction Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark", "Flying"},
    supertypes={"Legendary"},
    text="Flying, lifelink. When Yveltal enters, destroy target creature."
)

GIRATINA = make_creature(
    name="Giratina, Renegade Pokemon",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Ghost", "Dragon"},
    supertypes={"Legendary"},
    text="Flying. When Giratina enters, exile target creature. When Giratina leaves the battlefield, return that card to the battlefield."
)

UMBREON = make_creature(
    name="Umbreon, Moonlight Pokemon",
    power=3, toughness=3,
    mana_cost="{1}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Hexproof"),
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=LoseLife(2, target=EachOpponentTarget())
        )
    ]
)

ABSOL = make_creature(
    name="Absol, Disaster Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Pokemon", "Dark"},
    supertypes={"Legendary"},
    text="First strike. Whenever a creature an opponent controls dies, you draw a card and lose 1 life."
)

# --- Regular Black Pokemon ---

def gastly_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Haunter", 2, 2, "{1}{B}")]

GASTLY = make_creature(
    name="Gastly", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Poison"},
    text="Flying. Evolve {1}{B}: Transform Gastly into Haunter.",
    setup_interceptors=gastly_setup
)

HAUNTER = make_creature(
    name="Haunter", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Poison"},
    text="Flying. Evolve {1}{B}{B}: Transform Haunter into Gengar."
)

def eevee_b_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Umbreon", 3, 3, "{B}{B}")]

EEVEE_B = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Normal"},
    text="Evolve {B}{B}: Transform Eevee into Umbreon.",
    setup_interceptors=eevee_b_setup
)

MUK = make_creature(
    name="Muk", power=4, toughness=4, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    abilities=[
        KeywordAbility("Deathtouch"),
        StaticAbility(
            effect=PTBoost(-1, -1),
            filter=OpponentCreaturesFilter()
        )
    ]
)

GRIMER = make_creature(
    name="Grimer", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="Deathtouch. Evolve {2}{B}{B}: Transform Grimer into Muk."
)

WEEZING = make_creature(
    name="Weezing", power=3, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="When Weezing dies, it deals 3 damage to each creature."
)

KOFFING = make_creature(
    name="Koffing", power=1, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison"},
    text="When Koffing dies, it deals 1 damage to each creature."
)

DUSKNOIR = make_creature(
    name="Dusknoir", power=4, toughness=4, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="When Dusknoir enters, exile target creature from a graveyard. You gain life equal to its power."
)

MISDREAVUS = make_creature(
    name="Misdreavus", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="Flying. When Misdreavus enters, target opponent discards a card."
)

MISMAGIUS = make_creature(
    name="Mismagius", power=3, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost"},
    text="Flying. When Mismagius enters, each opponent discards a card."
)

HOUNDOOM = make_creature(
    name="Houndoom", power=4, toughness=3, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Fire"},
    text="Menace. When Houndoom enters, it deals 2 damage to target creature."
)

HOUNDOUR = make_creature(
    name="Houndour", power=2, toughness=1, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Fire"},
    text="Menace. Evolve {1}{B}{B}: Transform Houndour into Houndoom."
)

MURKROW = make_creature(
    name="Murkrow", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Flying"},
    text="Flying. When Murkrow deals combat damage to a player, that player discards a card."
)

HONCHKROW = make_creature(
    name="Honchkrow", power=4, toughness=3, mana_cost="{3}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Flying"},
    abilities=[
        KeywordAbility("Flying"),
        StaticAbility(
            effect=PTBoost(1, 0),
            filter=CreaturesWithSubtypeFilter("Dark", include_self=False)
        )
    ]
)

SPIRITOMB = make_creature(
    name="Spiritomb", power=2, toughness=4, mana_cost="{1}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Ghost", "Dark"},
    text="Spiritomb can't be blocked. Spiritomb can't block."
)

SABLEYE = make_creature(
    name="Sableye", power=2, toughness=2, mana_cost="{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Dark", "Ghost"},
    text="When Sableye enters, look at the top card of target opponent's library. You may put that card into their graveyard."
)

TOXICROAK = make_creature(
    name="Toxicroak", power=3, toughness=3, mana_cost="{2}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Fighting"},
    text="Deathtouch. Whenever Toxicroak deals combat damage to a player, that player loses 2 life."
)

CROBAT = make_creature(
    name="Crobat", power=3, toughness=2, mana_cost="{2}{B}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    abilities=[
        KeywordAbility("Flying"),
        KeywordAbility("Lifelink"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=LoseLife(2, target=EachOpponentTarget())
        )
    ]
)

ZUBAT = make_creature(
    name="Zubat", power=1, toughness=1, mana_cost="{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    text="Flying. Evolve {1}{B}: Transform Zubat into Golbat."
)

GOLBAT = make_creature(
    name="Golbat", power=2, toughness=2, mana_cost="{1}{B}",
    colors={Color.BLACK}, subtypes={"Pokemon", "Poison", "Flying"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=LoseLife(1, target=EachOpponentTarget())
        )
    ]
)

# --- Black Trainers ---

NIGHT_SHADE = make_instant(
    name="Night Shade", mana_cost="{1}{B}", colors={Color.BLACK},
    text="Target creature gets -2/-2 until end of turn."
)

SHADOW_BALL = make_instant(
    name="Shadow Ball", mana_cost="{2}{B}", colors={Color.BLACK},
    text="Destroy target creature with power 3 or less."
)

DARK_PULSE = make_instant(
    name="Dark Pulse", mana_cost="{1}{B}{B}", colors={Color.BLACK},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)

DESTINY_BOND = make_instant(
    name="Destiny Bond", mana_cost="{B}{B}", colors={Color.BLACK},
    text="Until end of turn, if a creature you control would die, destroy target creature an opponent controls."
)

HEX = make_sorcery(
    name="Hex", mana_cost="{4}{B}{B}", colors={Color.BLACK},
    text="Destroy up to six target creatures."
)

MEAN_LOOK = make_instant(
    name="Mean Look", mana_cost="{B}", colors={Color.BLACK},
    text="Target creature can't block this turn. Its controller loses 2 life."
)

NIGHTMARE_SPELL = make_sorcery(
    name="Nightmare", mana_cost="{2}{B}", colors={Color.BLACK},
    text="Target opponent discards two cards."
)

TOXIC = make_instant(
    name="Toxic", mana_cost="{B}", colors={Color.BLACK},
    text="Target creature gets -1/-1 until end of turn. At the beginning of its controller's next upkeep, it gets an additional -1/-1."
)

SUCKER_PUNCH = make_instant(
    name="Sucker Punch", mana_cost="{B}", colors={Color.BLACK},
    text="Target attacking creature gets +2/+0 and gains deathtouch until end of turn."
)

PERISH_SONG = make_sorcery(
    name="Perish Song", mana_cost="{2}{B}{B}", colors={Color.BLACK},
    text="At the beginning of your next upkeep, destroy all creatures."
)


# =============================================================================
# RED CARDS - FIRE, FIGHTING, ELECTRIC
# =============================================================================

# --- Legendary Pokemon ---

def charizard_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_type_advantage(obj, 2, {"Grass", "Bug", "Ice"})

CHARIZARD = make_creature(
    name="Charizard, Flame Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire", "Flying"},
    supertypes={"Legendary"},
    text="Flying. Type Advantage - Charizard deals 2 extra damage to Grass, Bug, and Ice Pokemon. {R}: Charizard gets +1/+0 until end of turn.",
    setup_interceptors=charizard_setup
)

def pikachu_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return make_type_advantage(obj, 2, {"Water", "Flying"})

PIKACHU = make_creature(
    name="Pikachu, Mouse Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric"},
    supertypes={"Legendary"},
    text="Haste. Type Advantage - Pikachu deals 2 extra damage to Water and Flying Pokemon.",
    setup_interceptors=pikachu_setup
)

RAICHU = make_creature(
    name="Raichu, Mouse Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric"},
    supertypes={"Legendary"},
    text="Haste. When Raichu enters, it deals 3 damage to any target."
)

def moltres_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def death_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DAMAGE, payload={'target': c_id, 'amount': 3, 'source': obj.id}, source=obj.id)
                for c_id, c in state.objects.items() if CardType.CREATURE in c.characteristics.types and c.zone == ZoneType.BATTLEFIELD]
    return [make_death_trigger(obj, death_effect)]

MOLTRES = make_creature(
    name="Moltres, Flame Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire", "Flying"},
    supertypes={"Legendary"},
    text="Flying, haste. When Moltres dies, it deals 3 damage to each creature.",
    setup_interceptors=moltres_setup
)

ENTEI = make_creature(
    name="Entei, Volcano Pokemon",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fire"},
    supertypes={"Legendary"},
    text="Haste, trample. When Entei enters, it deals 2 damage to each creature your opponents control."
)

GROUDON = make_creature(
    name="Groudon, Continent Pokemon",
    power=7, toughness=7,
    mana_cost="{4}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Ground"},
    supertypes={"Legendary"},
    text="Trample. When Groudon enters, destroy all lands your opponents control."
)

MACHAMP = make_creature(
    name="Machamp, Superpower Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Fighting"},
    supertypes={"Legendary"},
    text="Double strike. Machamp must attack each combat if able."
)

ZAPDOS = make_creature(
    name="Zapdos, Electric Pokemon",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}{R}",
    colors={Color.RED},
    subtypes={"Pokemon", "Electric", "Flying"},
    supertypes={"Legendary"},
    text="Flying, haste. When Zapdos enters, it deals 4 damage divided as you choose among any number of target creatures."
)

# --- Regular Red Pokemon ---

def charmander_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Charmeleon", 3, 2, "{1}{R}")]

CHARMANDER = make_creature(
    name="Charmander", power=2, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {1}{R}: Transform Charmander into Charmeleon.",
    setup_interceptors=charmander_setup
)

CHARMELEON = make_creature(
    name="Charmeleon", power=3, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {2}{R}{R}: Transform Charmeleon into Charizard."
)

FLAREON = make_creature(
    name="Flareon", power=4, toughness=2, mana_cost="{1}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Flareon enters, it deals 2 damage to any target."
)

def eevee_r_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Flareon", 4, 2, "{R}{R}")]

EEVEE_R = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Normal"},
    text="Evolve {R}{R}: Transform Eevee into Flareon.",
    setup_interceptors=eevee_r_setup
)

JOLTEON = make_creature(
    name="Jolteon", power=3, toughness=2, mana_cost="{1}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    abilities=[KeywordAbility("First strike"), KeywordAbility("Haste")]
)

ARCANINE = make_creature(
    name="Arcanine", power=5, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    abilities=[KeywordAbility("Haste"), KeywordAbility("Trample")]
)

GROWLITHE = make_creature(
    name="Growlithe", power=2, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Haste. Evolve {2}{R}{R}: Transform Growlithe into Arcanine."
)

NINETALES = make_creature(
    name="Ninetales", power=3, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Ninetales enters, it deals 2 damage to each creature your opponents control."
)

VULPIX = make_creature(
    name="Vulpix", power=1, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="Evolve {1}{R}{R}: Transform Vulpix into Ninetales."
)

RAPIDASH = make_creature(
    name="Rapidash", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    abilities=[KeywordAbility("Haste"), KeywordAbility("First strike")]
)

PONYTA = make_creature(
    name="Ponyta", power=2, toughness=2, mana_cost="{1}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    abilities=[KeywordAbility("Haste")]
)

MAGMAR = make_creature(
    name="Magmar", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="When Magmar enters, it deals 2 damage to target creature."
)

MAGMORTAR = make_creature(
    name="Magmortar", power=4, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire"},
    text="{R}, {T}: Magmortar deals 3 damage to any target."
)

ELECTABUZZ = make_creature(
    name="Electabuzz", power=3, toughness=2, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Haste. When Electabuzz enters, it deals 1 damage to any target."
)

ELECTIVIRE = make_creature(
    name="Electivire", power=4, toughness=4, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="When Electivire enters, it deals 3 damage to each opponent."
)

HITMONLEE = make_creature(
    name="Hitmonlee", power=4, toughness=2, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="First strike. Hitmonlee can't be blocked by creatures with power 2 or less."
)

HITMONCHAN = make_creature(
    name="Hitmonchan", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="First strike. {R}: Hitmonchan gets +1/+0 until end of turn."
)

PRIMEAPE = make_creature(
    name="Primeape", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    text="Haste. Primeape attacks each combat if able."
)

MANKEY = make_creature(
    name="Mankey", power=2, toughness=1, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting"},
    abilities=[KeywordAbility("Haste")]
)

LUCARIO = make_creature(
    name="Lucario", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fighting", "Steel"},
    text="First strike. When Lucario enters, it deals damage equal to its power to target creature."
)

BLAZIKEN = make_creature(
    name="Blaziken", power=5, toughness=3, mana_cost="{3}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire", "Fighting"},
    abilities=[KeywordAbility("Haste"), KeywordAbility("Double strike")]
)

INFERNAPE = make_creature(
    name="Infernape", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Fire", "Fighting"},
    abilities=[KeywordAbility("Haste"), KeywordAbility("First strike")]
)

LUXRAY = make_creature(
    name="Luxray", power=4, toughness=3, mana_cost="{2}{R}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="First strike. When Luxray enters, it deals 2 damage to target creature."
)

ELECTRODE = make_creature(
    name="Electrode", power=3, toughness=3, mana_cost="{2}{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Haste. Sacrifice Electrode: It deals 4 damage to any target."
)

VOLTORB = make_creature(
    name="Voltorb", power=1, toughness=2, mana_cost="{R}",
    colors={Color.RED}, subtypes={"Pokemon", "Electric"},
    text="Sacrifice Voltorb: It deals 2 damage to any target."
)

# --- Red Trainers ---

FLAMETHROWER = make_instant(
    name="Flamethrower", mana_cost="{2}{R}", colors={Color.RED},
    text="Flamethrower deals 4 damage to target creature."
)

THUNDERBOLT = make_instant(
    name="Thunderbolt", mana_cost="{1}{R}", colors={Color.RED},
    text="Thunderbolt deals 3 damage to any target."
)

FIRE_BLAST = make_sorcery(
    name="Fire Blast", mana_cost="{3}{R}{R}", colors={Color.RED},
    text="Fire Blast deals 5 damage to any target."
)

EARTHQUAKE_SPELL = make_sorcery(
    name="Earthquake", mana_cost="{2}{R}{R}", colors={Color.RED},
    text="Earthquake deals 3 damage to each creature without flying."
)

THUNDER = make_sorcery(
    name="Thunder", mana_cost="{2}{R}{R}", colors={Color.RED},
    text="Thunder deals 4 damage to any target. If that target is a Flying creature, Thunder deals 6 damage instead."
)

BRICK_BREAK = make_instant(
    name="Brick Break", mana_cost="{1}{R}", colors={Color.RED},
    text="Destroy target artifact. Brick Break deals 2 damage to that artifact's controller."
)

CLOSE_COMBAT = make_instant(
    name="Close Combat", mana_cost="{R}{R}", colors={Color.RED},
    text="Target creature you control gets +3/+0 and gains first strike until end of turn."
)

OVERHEAT = make_instant(
    name="Overheat", mana_cost="{1}{R}", colors={Color.RED},
    text="Target creature gets +4/+0 until end of turn. At end of turn, it gets -2/-0 until end of your next turn."
)

WILD_CHARGE = make_instant(
    name="Wild Charge", mana_cost="{R}", colors={Color.RED},
    text="Target creature gets +2/+0 and gains haste until end of turn."
)

ERUPTION = make_sorcery(
    name="Eruption", mana_cost="{3}{R}{R}{R}", colors={Color.RED},
    text="Eruption deals 6 damage to each creature and each player."
)


# =============================================================================
# GREEN CARDS - GRASS, GROUND, BUG
# =============================================================================

# --- Legendary Pokemon ---

VENUSAUR = make_creature(
    name="Venusaur, Seed Pokemon",
    power=5, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Poison"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Trample"),
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Grass", include_self=False)
        )
    ]
)

CELEBI = make_creature(
    name="Celebi, Time Travel Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Psychic"},
    supertypes={"Legendary"},
    text="Flying. When Celebi enters, return target card from your graveyard to your hand."
)

RAYQUAZA = make_creature(
    name="Rayquaza, Sky High Pokemon",
    power=7, toughness=6,
    mana_cost="{4}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Dragon", "Flying"},
    supertypes={"Legendary"},
    text="Flying, trample. When Rayquaza enters, destroy all enchantments."
)

SCEPTILE = make_creature(
    name="Sceptile, Forest Pokemon",
    power=4, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    text="Haste. {T}: Add {G}{G}."
)

def torterra_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    def etb_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.SEARCH_LIBRARY, payload={'player': obj.controller, 'card_type': 'basic_land', 'to_zone': ZoneType.BATTLEFIELD}, source=obj.id)]
    return [make_etb_trigger(obj, etb_effect)]

TORTERRA = make_creature(
    name="Torterra, Continent Pokemon",
    power=5, toughness=6,
    mana_cost="{3}{G}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass", "Ground"},
    supertypes={"Legendary"},
    text="Trample. When Torterra enters, search your library for a basic land card and put it onto the battlefield tapped. Then shuffle.",
    setup_interceptors=torterra_setup
)

LEAFEON = make_creature(
    name="Leafeon, Verdant Pokemon",
    power=3, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    text="When Leafeon enters, search your library for a basic Forest card, reveal it, and put it into your hand. Then shuffle."
)

SHAYMIN = make_creature(
    name="Shaymin, Gratitude Pokemon",
    power=2, toughness=2,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Pokemon", "Grass"},
    supertypes={"Legendary"},
    abilities=[
        KeywordAbility("Flying"),
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CompositeEffect([GainLife(3), DrawCards(1)])
        )
    ]
)

# --- Regular Green Pokemon ---

def bulbasaur_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Ivysaur", 2, 3, "{1}{G}")]

BULBASAUR = make_creature(
    name="Bulbasaur", power=1, toughness=2, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="Evolve {1}{G}: Transform Bulbasaur into Ivysaur.",
    setup_interceptors=bulbasaur_setup
)

IVYSAUR = make_creature(
    name="Ivysaur", power=2, toughness=3, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="Evolve {2}{G}{G}: Transform Ivysaur into Venusaur."
)

def eevee_g_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    return [make_evolve_trigger(obj, "Leafeon", 3, 3, "{G}{G}")]

EEVEE_G = make_creature(
    name="Eevee", power=1, toughness=1, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Normal"},
    text="Evolve {G}{G}: Transform Eevee into Leafeon.",
    setup_interceptors=eevee_g_setup
)

EXEGGUTOR = make_creature(
    name="Exeggutor", power=4, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Psychic"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DrawCards(2)
        )
    ]
)

EXEGGCUTE = make_creature(
    name="Exeggcute", power=1, toughness=2, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Psychic"},
    text="Evolve {2}{G}{G}: Transform Exeggcute into Exeggutor."
)

TANGROWTH = make_creature(
    name="Tangrowth", power=4, toughness=5, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass"},
    text="Reach. When Tangrowth enters, put two +1/+1 counters on target creature."
)

VILEPLUME = make_creature(
    name="Vileplume", power=3, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    text="When Vileplume enters, destroy target artifact or enchantment."
)

VICTREEBEL = make_creature(
    name="Victreebel", power=4, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Grass", "Poison"},
    abilities=[KeywordAbility("Deathtouch"), KeywordAbility("Reach")]
)

PARASECT = make_creature(
    name="Parasect", power=3, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Grass"},
    text="When Parasect enters, tap target creature. It doesn't untap during its controller's next untap step."
)

BUTTERFREE = make_creature(
    name="Butterfree", power=2, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Flying"},
    text="Flying. When Butterfree enters, you may search your library for a Grass Pokemon card, reveal it, and put it into your hand."
)

CATERPIE = make_creature(
    name="Caterpie", power=1, toughness=1, mana_cost="{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Evolve {G}: Transform Caterpie into Metapod."
)

METAPOD = make_creature(
    name="Metapod", power=0, toughness=3, mana_cost="{1}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Defender. Evolve {1}{G}: Transform Metapod into Butterfree."
)

BEEDRILL = make_creature(
    name="Beedrill", power=3, toughness=2, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Poison"},
    abilities=[KeywordAbility("Flying"), KeywordAbility("Deathtouch")]
)

SCYTHER = make_creature(
    name="Scyther", power=4, toughness=2, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Flying"},
    abilities=[KeywordAbility("Flying"), KeywordAbility("First strike")]
)

PINSIR = make_creature(
    name="Pinsir", power=4, toughness=3, mana_cost="{2}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug"},
    text="Trample. When Pinsir enters, fight target creature you don't control."
)

HERACROSS = make_creature(
    name="Heracross", power=5, toughness=3, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Bug", "Fighting"},
    text="Trample. Heracross gets +2/+2 as long as you control a Forest."
)

SANDSLASH = make_creature(
    name="Sandslash", power=3, toughness=3, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground"},
    text="First strike. When Sandslash dies, you may search your library for a basic land card and put it into your hand."
)

DUGTRIO = make_creature(
    name="Dugtrio", power=3, toughness=2, mana_cost="{2}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground"},
    text="Dugtrio can't be blocked except by creatures with flying or reach."
)

GOLEM = make_creature(
    name="Golem", power=5, toughness=5, mana_cost="{4}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Rock", "Ground"},
    text="Trample. When Golem enters, it deals 3 damage to any target."
)

RHYDON = make_creature(
    name="Rhydon", power=5, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ground", "Rock"},
    text="Trample. Protection from Lightning."
)

MAMOSWINE = make_creature(
    name="Mamoswine", power=5, toughness=5, mana_cost="{4}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Ice", "Ground"},
    text="Trample. When Mamoswine attacks, it gets +2/+0 until end of turn."
)

NIDOKING = make_creature(
    name="Nidoking", power=4, toughness=4, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Poison", "Ground"},
    abilities=[KeywordAbility("Trample"), KeywordAbility("Deathtouch")]
)

NIDOQUEEN = make_creature(
    name="Nidoqueen", power=3, toughness=5, mana_cost="{3}{G}{G}",
    colors={Color.GREEN}, subtypes={"Pokemon", "Poison", "Ground"},
    text="When Nidoqueen enters, put a +1/+1 counter on each other creature you control."
)

# --- Green Trainers ---

RAZOR_LEAF = make_instant(
    name="Razor Leaf", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature gets +2/+2 until end of turn."
)

SOLAR_BEAM = make_sorcery(
    name="Solar Beam", mana_cost="{3}{G}{G}", colors={Color.GREEN},
    text="Solar Beam deals 5 damage to target creature or planeswalker."
)

LEECH_SEED = make_enchantment(
    name="Leech Seed", mana_cost="{1}{G}", colors={Color.GREEN},
    text="Enchant creature. At the beginning of your upkeep, enchanted creature's controller loses 2 life and you gain 2 life."
)

SYNTHESIS = make_instant(
    name="Synthesis", mana_cost="{1}{G}", colors={Color.GREEN},
    text="You gain 5 life."
)

INGRAIN = make_instant(
    name="Ingrain", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature you control gains hexproof until end of turn. You gain 2 life."
)

GIGA_DRAIN = make_instant(
    name="Giga Drain", mana_cost="{2}{G}", colors={Color.GREEN},
    text="Target creature gets -3/-3 until end of turn. You gain 3 life."
)

GROWTH = make_instant(
    name="Growth", mana_cost="{G}", colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn."
)

VINE_WHIP = make_instant(
    name="Vine Whip", mana_cost="{1}{G}", colors={Color.GREEN},
    text="Tap target creature. It doesn't untap during its controller's next untap step."
)

SUNNY_DAY = make_sorcery(
    name="Sunny Day", mana_cost="{2}{G}", colors={Color.GREEN},
    text="Search your library for up to two basic land cards, reveal them, and put them into your hand. Then shuffle."
)

PHOTOSYNTHESIS = make_sorcery(
    name="Photosynthesis", mana_cost="{1}{G}", colors={Color.GREEN},
    text="You gain 1 life for each creature you control. Draw a card."
)


# =============================================================================
# ITEMS (ARTIFACTS)
# =============================================================================

POKE_BALL = make_artifact(
    name="Poke Ball", mana_cost="{2}",
    text="{2}, {T}, Sacrifice Poke Ball: Gain control of target creature with power 2 or less."
)

GREAT_BALL = make_artifact(
    name="Great Ball", mana_cost="{3}",
    text="{2}, {T}, Sacrifice Great Ball: Gain control of target creature with power 3 or less."
)

ULTRA_BALL = make_artifact(
    name="Ultra Ball", mana_cost="{4}",
    text="{2}, {T}, Sacrifice Ultra Ball: Gain control of target creature."
)

MASTER_BALL = make_artifact(
    name="Master Ball", mana_cost="{5}",
    text="{T}, Sacrifice Master Ball: Gain control of target creature. It gains haste.",
    supertypes={"Legendary"}
)

RARE_CANDY = make_artifact(
    name="Rare Candy", mana_cost="{2}",
    text="{T}, Sacrifice Rare Candy: Target creature you control evolves without paying its evolve cost."
)

EXP_SHARE = make_equipment(
    name="Exp. Share", mana_cost="{2}",
    text="Whenever another creature you control dies, put a +1/+1 counter on equipped creature.",
    equip_cost="{1}"
)

LUCKY_EGG = make_artifact(
    name="Lucky Egg", mana_cost="{2}",
    text="Whenever a creature you control deals combat damage to a player, draw a card."
)

LEFTOVERS = make_artifact(
    name="Leftovers", mana_cost="{2}",
    text="At the beginning of your upkeep, you gain 1 life."
)

CHOICE_BAND = make_equipment(
    name="Choice Band", mana_cost="{2}",
    text="Equipped creature gets +2/+0. Equipped creature can only attack.",
    equip_cost="{1}"
)

FOCUS_SASH = make_equipment(
    name="Focus Sash", mana_cost="{2}",
    text="If equipped creature would be destroyed, instead remove all damage from it and sacrifice Focus Sash.",
    equip_cost="{1}"
)

EVIOLITE = make_equipment(
    name="Eviolite", mana_cost="{2}",
    text="Equipped creature gets +0/+2. If it can evolve, it gets +1/+3 instead.",
    equip_cost="{1}"
)

SCOPE_LENS = make_equipment(
    name="Scope Lens", mana_cost="{1}",
    text="Equipped creature has 'Whenever this creature deals combat damage to a creature, destroy that creature.'",
    equip_cost="{2}"
)

QUICK_CLAW = make_equipment(
    name="Quick Claw", mana_cost="{1}",
    text="Equipped creature has first strike.",
    equip_cost="{1}"
)

MUSCLE_BAND = make_equipment(
    name="Muscle Band", mana_cost="{1}",
    text="Equipped creature gets +1/+1.",
    equip_cost="{1}"
)

ROCKY_HELMET = make_equipment(
    name="Rocky Helmet", mana_cost="{2}",
    text="Whenever equipped creature is dealt combat damage, Rocky Helmet deals 2 damage to the source's controller.",
    equip_cost="{1}"
)

POKEDEX = make_artifact(
    name="Pokedex", mana_cost="{1}",
    text="{1}, {T}: Look at the top card of your library. You may put it on the bottom of your library."
)

SILPH_SCOPE = make_artifact(
    name="Silph Scope", mana_cost="{2}",
    text="Creatures your opponents control lose hexproof."
)

BERRY = make_artifact(
    name="Oran Berry", mana_cost="{1}",
    text="{T}, Sacrifice Oran Berry: You gain 3 life."
)

SITRUS_BERRY = make_artifact(
    name="Sitrus Berry", mana_cost="{2}",
    text="{T}, Sacrifice Sitrus Berry: You gain 5 life and draw a card."
)

MAX_REVIVE = make_artifact(
    name="Max Revive", mana_cost="{3}",
    text="{2}, {T}, Sacrifice Max Revive: Return target creature card from your graveyard to the battlefield."
)


# =============================================================================
# LOCATIONS (LANDS)
# =============================================================================

PALLET_TOWN = make_land(
    name="Pallet Town",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {W} or {G}.",
    supertypes={"Legendary"}
)

CERULEAN_CITY = make_land(
    name="Cerulean City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {U}.",
    supertypes={"Legendary"}
)

VERMILION_CITY = make_land(
    name="Vermilion City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {R}.",
    supertypes={"Legendary"}
)

LAVENDER_TOWN = make_land(
    name="Lavender Town",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {B}.",
    supertypes={"Legendary"}
)

CELADON_CITY = make_land(
    name="Celadon City",
    text="{T}: Add {C}. {T}, Pay 1 life: Add {G}.",
    supertypes={"Legendary"}
)

POKEMON_LEAGUE = make_land(
    name="Pokemon League",
    text="{T}: Add {C}. {2}, {T}: Target Pokemon gets +1/+1 until end of turn.",
    supertypes={"Legendary"}
)

VIRIDIAN_FOREST = make_land(
    name="Viridian Forest",
    text="{T}: Add {G}. {1}, {T}, Sacrifice Viridian Forest: Search your library for a basic Forest card, put it onto the battlefield tapped, then shuffle."
)

MT_MOON = make_land(
    name="Mt. Moon",
    text="{T}: Add {C}. {3}, {T}: Add three mana of any one color."
)

POWER_PLANT = make_land(
    name="Power Plant",
    text="{T}: Add {C}{C}. Use this mana only to cast artifact spells or activate abilities of artifacts."
)

SAFARI_ZONE = make_land(
    name="Safari Zone",
    text="{T}: Add {C}. {2}, {T}: Create a 1/1 green Pokemon creature token."
)

VICTORY_ROAD = make_land(
    name="Victory Road",
    text="{T}: Add {C}. Whenever a creature you control evolves, you may pay {1}. If you do, draw a card."
)

POKEMON_CENTER_LAND = make_land(
    name="Pokemon Center",
    text="{T}: Add {C}. {2}, {T}: Regenerate target Pokemon."
)

SILPH_CO = make_land(
    name="Silph Co.",
    text="{T}: Add {C}. {3}, {T}: Search your library for an Equipment card, reveal it, and put it into your hand. Then shuffle."
)

CERULEAN_CAVE = make_land(
    name="Cerulean Cave",
    text="{T}: Add {U} or {B}. Cerulean Cave enters the battlefield tapped.",
    supertypes={"Legendary"}
)

INDIGO_PLATEAU = make_land(
    name="Indigo Plateau",
    text="{T}: Add one mana of any color. Use this mana only to cast legendary spells.",
    supertypes={"Legendary"}
)

# Basic Lands
PLAINS_PKH = make_land(name="Plains", subtypes={"Plains"}, supertypes={"Basic"})
ISLAND_PKH = make_land(name="Island", subtypes={"Island"}, supertypes={"Basic"})
SWAMP_PKH = make_land(name="Swamp", subtypes={"Swamp"}, supertypes={"Basic"})
MOUNTAIN_PKH = make_land(name="Mountain", subtypes={"Mountain"}, supertypes={"Basic"})
FOREST_PKH = make_land(name="Forest", subtypes={"Forest"}, supertypes={"Basic"})


# =============================================================================
# CARD DICTIONARY
# =============================================================================

POKEMON_HORIZONS_CARDS = {
    # WHITE - NORMAL, FAIRY
    "Arceus, The Original One": ARCEUS,
    "Togekiss, Jubilee Pokemon": TOGEKISS,
    "Clefable, Fairy Queen": CLEFABLE,
    "Sylveon, Intertwining Pokemon": SYLVEON,
    "Eevee (White)": EEVEE_W,
    "Clefairy": CLEFAIRY,
    "Togepi": TOGEPI,
    "Togetic": TOGETIC,
    "Chansey": CHANSEY,
    "Blissey": BLISSEY,
    "Snorlax": SNORLAX,
    "Jigglypuff": JIGGLYPUFF,
    "Wigglytuff": WIGGLYTUFF,
    "Persian": PERSIAN,
    "Meowth": MEOWTH,
    "Pidgeot": PIDGEOT,
    "Pidgey": PIDGEY,
    "Rattata": RATTATA,
    "Raticate": RATICATE,
    "Furret": FURRET,
    "Audino": AUDINO,
    "Ditto": DITTO,
    "Slaking": SLAKING,
    "Miltank": MILTANK,
    "Tauros": TAUROS,
    "Granbull": GRANBULL,
    "Florges": FLORGES,
    "Potion": POTION,
    "Super Potion": SUPER_POTION,
    "Hyper Potion": HYPER_POTION,
    "Full Restore": FULL_RESTORE,
    "Pokemon Center": POKEMON_CENTER,
    "Professor Oak's Advice": PROFESSOR_OAK,
    "Heal Bell": HEAL_BELL,
    "Protect": PROTECT,
    "Safeguard": SAFEGUARD,
    "Moonblast": MOONBLAST,

    # BLUE - WATER, ICE, PSYCHIC
    "Mewtwo, Genetic Pokemon": MEWTWO,
    "Mew, New Species Pokemon": MEW,
    "Lugia, Diving Pokemon": LUGIA,
    "Suicune, Aurora Pokemon": SUICUNE,
    "Articuno, Freeze Pokemon": ARTICUNO,
    "Kyogre, Sea Basin Pokemon": KYOGRE,
    "Blastoise, Shellfish Pokemon": BLASTOISE,
    "Alakazam, Psi Pokemon": ALAKAZAM,
    "Squirtle": SQUIRTLE,
    "Wartortle": WARTORTLE,
    "Psyduck": PSYDUCK,
    "Golduck": GOLDUCK,
    "Vaporeon": VAPOREON,
    "Eevee (Blue)": EEVEE_U,
    "Slowpoke": SLOWPOKE,
    "Slowbro": SLOWBRO,
    "Lapras": LAPRAS,
    "Dewgong": DEWGONG,
    "Starmie": STARMIE,
    "Staryu": STARYU,
    "Tentacruel": TENTACRUEL,
    "Gyarados": GYARADOS,
    "Magikarp": MAGIKARP,
    "Milotic": MILOTIC,
    "Espeon": ESPEON,
    "Gardevoir": GARDEVOIR,
    "Gallade": GALLADE,
    "Wobbuffet": WOBBUFFET,
    "Glaceon": GLACEON,
    "Walrein": WALREIN,
    "Cloyster": CLOYSTER,
    "Dive Ball": DIVE_BALL,
    "Misty's Determination": MISTY_DETERMINATION,
    "Confusion": CONFUSION,
    "Psychic": PSYCHIC,
    "Hydro Pump": HYDRO_PUMP,
    "Blizzard": BLIZZARD,
    "Surf": SURF,
    "Telekinesis": TELEKINESIS,
    "Amnesia": AMNESIA,
    "Future Sight": FUTURE_SIGHT_SPELL,

    # BLACK - DARK, GHOST, POISON
    "Gengar, Shadow Pokemon": GENGAR,
    "Darkrai, Pitch-Black Pokemon": DARKRAI,
    "Yveltal, Destruction Pokemon": YVELTAL,
    "Giratina, Renegade Pokemon": GIRATINA,
    "Umbreon, Moonlight Pokemon": UMBREON,
    "Absol, Disaster Pokemon": ABSOL,
    "Gastly": GASTLY,
    "Haunter": HAUNTER,
    "Eevee (Black)": EEVEE_B,
    "Muk": MUK,
    "Grimer": GRIMER,
    "Weezing": WEEZING,
    "Koffing": KOFFING,
    "Dusknoir": DUSKNOIR,
    "Misdreavus": MISDREAVUS,
    "Mismagius": MISMAGIUS,
    "Houndoom": HOUNDOOM,
    "Houndour": HOUNDOUR,
    "Murkrow": MURKROW,
    "Honchkrow": HONCHKROW,
    "Spiritomb": SPIRITOMB,
    "Sableye": SABLEYE,
    "Toxicroak": TOXICROAK,
    "Crobat": CROBAT,
    "Zubat": ZUBAT,
    "Golbat": GOLBAT,
    "Night Shade": NIGHT_SHADE,
    "Shadow Ball": SHADOW_BALL,
    "Dark Pulse": DARK_PULSE,
    "Destiny Bond": DESTINY_BOND,
    "Hex": HEX,
    "Mean Look": MEAN_LOOK,
    "Nightmare": NIGHTMARE_SPELL,
    "Toxic": TOXIC,
    "Sucker Punch": SUCKER_PUNCH,
    "Perish Song": PERISH_SONG,

    # RED - FIRE, FIGHTING, ELECTRIC
    "Charizard, Flame Pokemon": CHARIZARD,
    "Pikachu, Mouse Pokemon": PIKACHU,
    "Raichu, Mouse Pokemon": RAICHU,
    "Moltres, Flame Pokemon": MOLTRES,
    "Entei, Volcano Pokemon": ENTEI,
    "Groudon, Continent Pokemon": GROUDON,
    "Machamp, Superpower Pokemon": MACHAMP,
    "Zapdos, Electric Pokemon": ZAPDOS,
    "Charmander": CHARMANDER,
    "Charmeleon": CHARMELEON,
    "Flareon": FLAREON,
    "Eevee (Red)": EEVEE_R,
    "Jolteon": JOLTEON,
    "Arcanine": ARCANINE,
    "Growlithe": GROWLITHE,
    "Ninetales": NINETALES,
    "Vulpix": VULPIX,
    "Rapidash": RAPIDASH,
    "Ponyta": PONYTA,
    "Magmar": MAGMAR,
    "Magmortar": MAGMORTAR,
    "Electabuzz": ELECTABUZZ,
    "Electivire": ELECTIVIRE,
    "Hitmonlee": HITMONLEE,
    "Hitmonchan": HITMONCHAN,
    "Primeape": PRIMEAPE,
    "Mankey": MANKEY,
    "Lucario": LUCARIO,
    "Blaziken": BLAZIKEN,
    "Infernape": INFERNAPE,
    "Luxray": LUXRAY,
    "Electrode": ELECTRODE,
    "Voltorb": VOLTORB,
    "Flamethrower": FLAMETHROWER,
    "Thunderbolt": THUNDERBOLT,
    "Fire Blast": FIRE_BLAST,
    "Earthquake": EARTHQUAKE_SPELL,
    "Thunder": THUNDER,
    "Brick Break": BRICK_BREAK,
    "Close Combat": CLOSE_COMBAT,
    "Overheat": OVERHEAT,
    "Wild Charge": WILD_CHARGE,
    "Eruption": ERUPTION,

    # GREEN - GRASS, GROUND, BUG
    "Venusaur, Seed Pokemon": VENUSAUR,
    "Celebi, Time Travel Pokemon": CELEBI,
    "Rayquaza, Sky High Pokemon": RAYQUAZA,
    "Sceptile, Forest Pokemon": SCEPTILE,
    "Torterra, Continent Pokemon": TORTERRA,
    "Leafeon, Verdant Pokemon": LEAFEON,
    "Shaymin, Gratitude Pokemon": SHAYMIN,
    "Bulbasaur": BULBASAUR,
    "Ivysaur": IVYSAUR,
    "Eevee (Green)": EEVEE_G,
    "Exeggutor": EXEGGUTOR,
    "Exeggcute": EXEGGCUTE,
    "Tangrowth": TANGROWTH,
    "Vileplume": VILEPLUME,
    "Victreebel": VICTREEBEL,
    "Parasect": PARASECT,
    "Butterfree": BUTTERFREE,
    "Caterpie": CATERPIE,
    "Metapod": METAPOD,
    "Beedrill": BEEDRILL,
    "Scyther": SCYTHER,
    "Pinsir": PINSIR,
    "Heracross": HERACROSS,
    "Sandslash": SANDSLASH,
    "Dugtrio": DUGTRIO,
    "Golem": GOLEM,
    "Rhydon": RHYDON,
    "Mamoswine": MAMOSWINE,
    "Nidoking": NIDOKING,
    "Nidoqueen": NIDOQUEEN,
    "Razor Leaf": RAZOR_LEAF,
    "Solar Beam": SOLAR_BEAM,
    "Leech Seed": LEECH_SEED,
    "Synthesis": SYNTHESIS,
    "Ingrain": INGRAIN,
    "Giga Drain": GIGA_DRAIN,
    "Growth": GROWTH,
    "Vine Whip": VINE_WHIP,
    "Sunny Day": SUNNY_DAY,
    "Photosynthesis": PHOTOSYNTHESIS,

    # ITEMS (ARTIFACTS)
    "Poke Ball": POKE_BALL,
    "Great Ball": GREAT_BALL,
    "Ultra Ball": ULTRA_BALL,
    "Master Ball": MASTER_BALL,
    "Rare Candy": RARE_CANDY,
    "Exp. Share": EXP_SHARE,
    "Lucky Egg": LUCKY_EGG,
    "Leftovers": LEFTOVERS,
    "Choice Band": CHOICE_BAND,
    "Focus Sash": FOCUS_SASH,
    "Eviolite": EVIOLITE,
    "Scope Lens": SCOPE_LENS,
    "Quick Claw": QUICK_CLAW,
    "Muscle Band": MUSCLE_BAND,
    "Rocky Helmet": ROCKY_HELMET,
    "Pokedex": POKEDEX,
    "Silph Scope": SILPH_SCOPE,
    "Oran Berry": BERRY,
    "Sitrus Berry": SITRUS_BERRY,
    "Max Revive": MAX_REVIVE,

    # LOCATIONS (LANDS)
    "Pallet Town": PALLET_TOWN,
    "Cerulean City": CERULEAN_CITY,
    "Vermilion City": VERMILION_CITY,
    "Lavender Town": LAVENDER_TOWN,
    "Celadon City": CELADON_CITY,
    "Pokemon League": POKEMON_LEAGUE,
    "Viridian Forest": VIRIDIAN_FOREST,
    "Mt. Moon": MT_MOON,
    "Power Plant": POWER_PLANT,
    "Safari Zone": SAFARI_ZONE,
    "Victory Road": VICTORY_ROAD,
    "Pokemon Center (Land)": POKEMON_CENTER_LAND,
    "Silph Co.": SILPH_CO,
    "Cerulean Cave": CERULEAN_CAVE,
    "Indigo Plateau": INDIGO_PLATEAU,
    "Plains": PLAINS_PKH,
    "Island": ISLAND_PKH,
    "Swamp": SWAMP_PKH,
    "Mountain": MOUNTAIN_PKH,
    "Forest": FOREST_PKH,
}

print(f"Loaded {len(POKEMON_HORIZONS_CARDS)} Pokemon Horizons cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ARCEUS,
    TOGEKISS,
    CLEFABLE,
    SYLVEON,
    EEVEE_W,
    CLEFAIRY,
    TOGEPI,
    TOGETIC,
    CHANSEY,
    BLISSEY,
    SNORLAX,
    JIGGLYPUFF,
    WIGGLYTUFF,
    PERSIAN,
    MEOWTH,
    PIDGEOT,
    PIDGEY,
    RATTATA,
    RATICATE,
    FURRET,
    AUDINO,
    DITTO,
    SLAKING,
    MILTANK,
    TAUROS,
    GRANBULL,
    FLORGES,
    POTION,
    SUPER_POTION,
    HYPER_POTION,
    FULL_RESTORE,
    POKEMON_CENTER,
    PROFESSOR_OAK,
    HEAL_BELL,
    PROTECT,
    SAFEGUARD,
    MOONBLAST,
    MEWTWO,
    MEW,
    LUGIA,
    SUICUNE,
    ARTICUNO,
    KYOGRE,
    BLASTOISE,
    ALAKAZAM,
    SQUIRTLE,
    WARTORTLE,
    PSYDUCK,
    GOLDUCK,
    VAPOREON,
    EEVEE_U,
    SLOWPOKE,
    SLOWBRO,
    LAPRAS,
    DEWGONG,
    STARMIE,
    STARYU,
    TENTACRUEL,
    GYARADOS,
    MAGIKARP,
    MILOTIC,
    ESPEON,
    GARDEVOIR,
    GALLADE,
    WOBBUFFET,
    GLACEON,
    WALREIN,
    CLOYSTER,
    DIVE_BALL,
    MISTY_DETERMINATION,
    CONFUSION,
    PSYCHIC,
    HYDRO_PUMP,
    BLIZZARD,
    SURF,
    TELEKINESIS,
    AMNESIA,
    FUTURE_SIGHT_SPELL,
    GENGAR,
    DARKRAI,
    YVELTAL,
    GIRATINA,
    UMBREON,
    ABSOL,
    GASTLY,
    HAUNTER,
    EEVEE_B,
    MUK,
    GRIMER,
    WEEZING,
    KOFFING,
    DUSKNOIR,
    MISDREAVUS,
    MISMAGIUS,
    HOUNDOOM,
    HOUNDOUR,
    MURKROW,
    HONCHKROW,
    SPIRITOMB,
    SABLEYE,
    TOXICROAK,
    CROBAT,
    ZUBAT,
    GOLBAT,
    NIGHT_SHADE,
    SHADOW_BALL,
    DARK_PULSE,
    DESTINY_BOND,
    HEX,
    MEAN_LOOK,
    NIGHTMARE_SPELL,
    TOXIC,
    SUCKER_PUNCH,
    PERISH_SONG,
    CHARIZARD,
    PIKACHU,
    RAICHU,
    MOLTRES,
    ENTEI,
    GROUDON,
    MACHAMP,
    ZAPDOS,
    CHARMANDER,
    CHARMELEON,
    FLAREON,
    EEVEE_R,
    JOLTEON,
    ARCANINE,
    GROWLITHE,
    NINETALES,
    VULPIX,
    RAPIDASH,
    PONYTA,
    MAGMAR,
    MAGMORTAR,
    ELECTABUZZ,
    ELECTIVIRE,
    HITMONLEE,
    HITMONCHAN,
    PRIMEAPE,
    MANKEY,
    LUCARIO,
    BLAZIKEN,
    INFERNAPE,
    LUXRAY,
    ELECTRODE,
    VOLTORB,
    FLAMETHROWER,
    THUNDERBOLT,
    FIRE_BLAST,
    EARTHQUAKE_SPELL,
    THUNDER,
    BRICK_BREAK,
    CLOSE_COMBAT,
    OVERHEAT,
    WILD_CHARGE,
    ERUPTION,
    VENUSAUR,
    CELEBI,
    RAYQUAZA,
    SCEPTILE,
    TORTERRA,
    LEAFEON,
    SHAYMIN,
    BULBASAUR,
    IVYSAUR,
    EEVEE_G,
    EXEGGUTOR,
    EXEGGCUTE,
    TANGROWTH,
    VILEPLUME,
    VICTREEBEL,
    PARASECT,
    BUTTERFREE,
    CATERPIE,
    METAPOD,
    BEEDRILL,
    SCYTHER,
    PINSIR,
    HERACROSS,
    SANDSLASH,
    DUGTRIO,
    GOLEM,
    RHYDON,
    MAMOSWINE,
    NIDOKING,
    NIDOQUEEN,
    RAZOR_LEAF,
    SOLAR_BEAM,
    LEECH_SEED,
    SYNTHESIS,
    INGRAIN,
    GIGA_DRAIN,
    GROWTH,
    VINE_WHIP,
    SUNNY_DAY,
    PHOTOSYNTHESIS,
    POKE_BALL,
    GREAT_BALL,
    ULTRA_BALL,
    MASTER_BALL,
    RARE_CANDY,
    EXP_SHARE,
    LUCKY_EGG,
    LEFTOVERS,
    CHOICE_BAND,
    FOCUS_SASH,
    EVIOLITE,
    SCOPE_LENS,
    QUICK_CLAW,
    MUSCLE_BAND,
    ROCKY_HELMET,
    POKEDEX,
    SILPH_SCOPE,
    BERRY,
    SITRUS_BERRY,
    MAX_REVIVE,
    PALLET_TOWN,
    CERULEAN_CITY,
    VERMILION_CITY,
    LAVENDER_TOWN,
    CELADON_CITY,
    POKEMON_LEAGUE,
    VIRIDIAN_FOREST,
    MT_MOON,
    POWER_PLANT,
    SAFARI_ZONE,
    VICTORY_ROAD,
    POKEMON_CENTER_LAND,
    SILPH_CO,
    CERULEAN_CAVE,
    INDIGO_PLATEAU,
    PLAINS_PKH,
    ISLAND_PKH,
    SWAMP_PKH,
    MOUNTAIN_PKH,
    FOREST_PKH
]
