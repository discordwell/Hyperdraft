"""
Legend of Zelda: Hyrule Chronicles (LOZ) Card Implementations

Set released January 2026. ~250 cards.
Features mechanics: Dungeon, Triforce, Heart Container
"""

from src.engine import (
    Event, EventType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    GameObject, GameState, ZoneType, CardType, Color,
    Characteristics, ObjectState, CardDefinition,
    make_creature, make_instant, make_enchantment,
    new_id, get_power, get_toughness,
    # New ability system imports
    TriggeredAbility, StaticAbility, KeywordAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, DealsDamageTrigger,
    UpkeepTrigger, SpellCastTrigger, DrawTrigger,
    GainLife, LoseLife, DrawCards, DealDamage, AddCounters, CompositeEffect,
    DiscardCards, Scry, CreateToken,
    PTBoost, KeywordGrant,
    OtherCreaturesYouControlFilter, CreaturesWithSubtypeFilter, CreaturesYouControlFilter,
    EachOpponentTarget,
)
from typing import Optional, Callable


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def make_sorcery(name: str, mana_cost: str, colors: set, text: str, subtypes: set = None, supertypes: set = None, resolve=None):
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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, abilities: list = None):
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
        abilities=abilities
    )


def make_artifact_creature(name: str, power: int, toughness: int, mana_cost: str, colors: set, text: str,
                           subtypes: set = None, supertypes: set = None, abilities: list = None):
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
        abilities=abilities
    )


def make_equipment(name: str, mana_cost: str, text: str, equip_cost: str, subtypes: set = None, supertypes: set = None, abilities: list = None):
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
        abilities=abilities
    )


def make_land(name: str, text: str = "", subtypes: set = None, supertypes: set = None):
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
# ZELDA KEYWORD MECHANICS (Set-specific, kept as interceptor-based)
# =============================================================================

def make_dungeon_trigger(source_obj: GameObject, room_count: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Dungeon N - When this creature attacks, venture through the dungeon.
    After N rooms, trigger the effect.
    """
    def dungeon_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.ATTACK_DECLARED and
                event.payload.get('attacker_id') == source_obj.id)

    def dungeon_handler(event: Event, state: GameState) -> InterceptorResult:
        dungeon_event = Event(
            type=EventType.COUNTER_ADDED,
            payload={'object_id': source_obj.id, 'counter_type': 'dungeon_room', 'amount': 1},
            source=source_obj.id
        )
        current_rooms = source_obj.state.counters.get('dungeon_room', 0)
        if current_rooms + 1 >= room_count:
            effect_events = effect_fn(event, state)
            reset_event = Event(
                type=EventType.COUNTER_REMOVED,
                payload={'object_id': source_obj.id, 'counter_type': 'dungeon_room', 'amount': room_count},
                source=source_obj.id
            )
            return InterceptorResult(action=InterceptorAction.REACT, new_events=[dungeon_event, reset_event] + effect_events)
        return InterceptorResult(action=InterceptorAction.REACT, new_events=[dungeon_event])

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=dungeon_filter,
        handler=dungeon_handler,
        duration='while_on_battlefield'
    )


def make_triforce_bonus(source_obj: GameObject, power_bonus: int, toughness_bonus: int, pieces_required: int = 3) -> list[Interceptor]:
    """
    Triforce - This creature gets +X/+Y as long as you control N or more artifacts with 'Triforce' in their name.
    This is a set-specific mechanic that requires custom interceptor logic.
    """
    def triforce_filter(target: GameObject, state: GameState) -> bool:
        if target.id != source_obj.id:
            return False
        triforce_count = sum(1 for obj in state.objects.values()
                            if obj.controller == source_obj.controller
                            and obj.zone == ZoneType.BATTLEFIELD
                            and CardType.ARTIFACT in obj.characteristics.types
                            and 'Triforce' in obj.characteristics.name)
        return triforce_count >= pieces_required

    # Manual interceptor creation for Triforce mechanic
    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj, flt=triforce_filter):
            if event.type != EventType.QUERY_POWER:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt(target, state)

        def power_handler(event, state, mod=power_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=power_filter,
            handler=power_handler,
            duration='while_on_battlefield'
        ))

    if toughness_bonus != 0:
        def toughness_filter(event, state, src=source_obj, flt=triforce_filter):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            target_id = event.payload.get('object_id')
            target = state.objects.get(target_id)
            if not target:
                return False
            return flt(target, state)

        def toughness_handler(event, state, mod=toughness_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(action=InterceptorAction.TRANSFORM, transformed_event=new_event)

        interceptors.append(Interceptor(
            id=new_id(),
            source=source_obj.id,
            controller=source_obj.controller,
            priority=InterceptorPriority.QUERY,
            filter=toughness_filter,
            handler=toughness_handler,
            duration='while_on_battlefield'
        ))

    return interceptors


def make_heart_container_ability(life_amount: int) -> TriggeredAbility:
    """Heart Container - When this permanent enters, you gain N life."""
    return TriggeredAbility(
        trigger=ETBTrigger(),
        effect=GainLife(life_amount)
    )


# Legacy setup function for cards that need Triforce or Dungeon mechanics
def _triforce_and_etb_setup(triforce_power: int, triforce_toughness: int, triforce_required: int, etb_effect):
    """Helper for cards with both Triforce bonus and ETB trigger."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        interceptors = []
        interceptors.extend(make_triforce_bonus(obj, triforce_power, triforce_toughness, triforce_required))
        # ETB effect handled by abilities system
        return interceptors
    return setup


def _triforce_setup(triforce_power: int, triforce_toughness: int, triforce_required: int):
    """Helper for cards with only Triforce bonus."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return make_triforce_bonus(obj, triforce_power, triforce_toughness, triforce_required)
    return setup


def _dungeon_setup(room_count: int, effect_fn):
    """Helper for cards with Dungeon mechanic."""
    def setup(obj: GameObject, state: GameState) -> list[Interceptor]:
        return [make_dungeon_trigger(obj, room_count, effect_fn)]
    return setup


# =============================================================================
# WHITE CARDS - LIGHT, SHEIKAH, PROTECTION
# =============================================================================

# --- Legendary Creatures ---

ZELDA_PRINCESS_OF_HYRULE = make_creature(
    name="Zelda, Princess of Hyrule",
    power=2, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=GainLife(3))
    ],
    setup_interceptors=_triforce_setup(2, 2, 2)
)


ZELDA_WIELDER_OF_WISDOM = make_creature(
    name="Zelda, Wielder of Wisdom",
    power=3, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Hylian", "Noble", "Wizard"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=SpellCastTrigger(controller_only=True), effect=DrawCards(1))
    ]
)


IMPA_SHEIKAH_GUARDIAN = make_creature(
    name="Impa, Sheikah Guardian",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=KeywordGrant(['hexproof']),
            filter=CreaturesWithSubtypeFilter("Sheikah", include_self=False)
        )
    ]
)


RAURU_SAGE_OF_LIGHT = make_creature(
    name="Rauru, Sage of Light",
    power=2, toughness=5,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=GainLife(2))
    ]
)


HYLIA_GODDESS_OF_LIGHT = make_creature(
    name="Hylia, Goddess of Light",
    power=4, toughness=6,
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    subtypes={"God"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(effect=PTBoost(1, 1), filter=OtherCreaturesYouControlFilter())
    ]
)


# --- Regular Creatures ---

SHEIKAH_WARRIOR = make_creature(
    name="Sheikah Warrior",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Warrior"},
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=GainLife(2))
    ]
)


HYRULE_KNIGHT = make_creature(
    name="Hyrule Knight",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
)


TEMPLE_GUARDIAN = make_creature(
    name="Temple Guardian",
    power=1, toughness=4,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Soldier"},
    abilities=[
        make_heart_container_ability(3)
    ]
)


CASTLE_GUARD = make_creature(
    name="Castle Guard",
    power=2, toughness=2,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
)


LIGHT_SPIRIT = make_creature(
    name="Light Spirit",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Spirit"},
)


HYLIAN_PRIESTESS = make_creature(
    name="Hylian Priestess",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Cleric"},
)


SHEIKAH_SCOUT = make_creature(
    name="Sheikah Scout",
    power=2, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Sheikah", "Scout"},
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=Scry(2))
    ]
)


COURAGE_FAIRY = make_creature(
    name="Courage Fairy",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
)


HYRULE_CAPTAIN = make_creature(
    name="Hyrule Captain",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
)


GREAT_FAIRY = make_creature(
    name="Great Fairy",
    power=3, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
)


SACRED_REALM_GUARDIAN = make_creature(
    name="Sacred Realm Guardian",
    power=4, toughness=5,
    mana_cost="{4}{W}",
    colors={Color.WHITE},
    subtypes={"Angel"},
)


# --- Instants/Sorceries ---

DINS_FIRE_SHIELD = make_instant(
    name="Din's Fire Shield",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
)


LIGHT_ARROW = make_instant(
    name="Light Arrow",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
)


NAYRUS_LOVE = make_instant(
    name="Nayru's Love",
    mana_cost="{W}{W}",
    colors={Color.WHITE},
)


SONG_OF_HEALING = make_sorcery(
    name="Song of Healing",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 4 life. If you control an artifact, you gain 6 life instead."
)


BLESSING_OF_HYLIA = make_sorcery(
    name="Blessing of Hylia",
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +2/+2 until end of turn. You gain 1 life for each creature you control."
)


# =============================================================================
# BLUE CARDS - ZORA, WATER, WISDOM
# =============================================================================

# --- Legendary Creatures ---

MIPHA_ZORA_CHAMPION = make_creature(
    name="Mipha, Zora Champion",
    power=2, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Champion"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=GainLife(2))
    ]
)


RUTO_ZORA_PRINCESS = make_creature(
    name="Ruto, Zora Princess",
    power=3, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Zora", include_self=False)
        )
    ]
)


KING_ZORA = make_creature(
    name="King Zora, Domain Ruler",
    power=2, toughness=5,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=DrawCards(2))
    ]
)


NAYRU_ORACLE_OF_WISDOM = make_creature(
    name="Nayru, Oracle of Wisdom",
    power=3, toughness=4,
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=DrawTrigger(), effect=Scry(1))
    ]
)


SIDON_ZORA_PRINCE = make_creature(
    name="Sidon, Zora Prince",
    power=4, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Noble", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=AttackTrigger(), effect=DrawCards(1))
    ]
)


# --- Regular Creatures ---

ZORA_WARRIOR = make_creature(
    name="Zora Warrior",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
)


ZORA_SCHOLAR = make_creature(
    name="Zora Scholar",
    power=1, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=DrawCards(1))
    ]
)


RIVER_ZORA = make_creature(
    name="River Zora",
    power=2, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
)


WATER_SPIRIT = make_creature(
    name="Water Spirit",
    power=3, toughness=3,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental", "Spirit"},
)


OCTOROK = make_creature(
    name="Octorok",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Beast"},
)


LIKE_LIKE = make_creature(
    name="Like-Like",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Ooze"},
)


GYORG = make_creature(
    name="Gyorg",
    power=4, toughness=3,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Fish"},
)


ZORA_DIVER = make_creature(
    name="Zora Diver",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Scout"},
)


ZORA_SPEARMAN = make_creature(
    name="Zora Spearman",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Warrior"},
)


ZORA_SAGE = make_creature(
    name="Zora Sage",
    power=1, toughness=4,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Wizard"},
    abilities=[
        TriggeredAbility(trigger=SpellCastTrigger(), effect=Scry(1))
    ]
)


# --- Instants/Sorceries ---

ZORAS_SAPPHIRE_BLESSING = make_instant(
    name="Zora's Sapphire Blessing",
    mana_cost="{U}",
    colors={Color.BLUE},
)


TORRENTIAL_WAVE = make_instant(
    name="Torrential Wave",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
)


WATER_TEMPLE_FLOOD = make_sorcery(
    name="Water Temple Flood",
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    text="Tap all creatures your opponents control. Those creatures don't untap during their controllers' next untap step."
)


WISDOM_OF_AGES = make_sorcery(
    name="Wisdom of Ages",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


COUNTER_MAGIC = make_instant(
    name="Counter Magic",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
)


# =============================================================================
# BLACK CARDS - GANON, TWILIGHT, DARKNESS
# =============================================================================

# --- Legendary Creatures ---

GANONDORF_KING_OF_EVIL = make_creature(
    name="Ganondorf, King of Evil",
    power=5, toughness=5,
    mana_cost="{3}{B}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Gerudo", "Warlock"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=LoseLife(3, target=EachOpponentTarget())
        )
    ],
    setup_interceptors=_triforce_setup(3, 3, 1)
)


GANON_CALAMITY_INCARNATE = make_creature(
    name="Ganon, Calamity Incarnate",
    power=7, toughness=7,
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Demon", "Beast"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=DiscardCards(1, target=EachOpponentTarget())
        )
    ]
)


ZANT_TWILIGHT_USURPER = make_creature(
    name="Zant, Twilight Usurper",
    power=4, toughness=3,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Warlock"},
    supertypes={"Legendary"},
)


MIDNA_TWILIGHT_PRINCESS = make_creature(
    name="Midna, Twilight Princess",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Twili", "Noble"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=DrawCards(1)
        )
    ]
)


VAATI_WIND_MAGE = make_creature(
    name="Vaati, Wind Mage",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Minish", "Warlock"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=LoseLife(1, target=EachOpponentTarget())
        )
    ]
)


# --- Regular Creatures ---

SHADOW_BEAST = make_creature(
    name="Shadow Beast",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Beast", "Shadow"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Shadow", power=1, toughness=1, colors={'B'}, subtypes={'Shadow'})
        )
    ]
)


STALFOS_WARRIOR = make_creature(
    name="Stalfos Warrior",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Skeleton", "Warrior"},
)


REDEAD = make_creature(
    name="ReDead",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
)


GIBDO = make_creature(
    name="Gibdo",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie"},
)


POES = make_creature(
    name="Poe",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
)


DARK_NUT = make_creature(
    name="Darknut",
    power=4, toughness=4,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Knight"},
)


PHANTOM = make_creature(
    name="Phantom",
    power=3, toughness=5,
    mana_cost="{4}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit", "Knight"},
)


FLOORMASTER = make_creature(
    name="Floormaster",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)


DEAD_HAND = make_creature(
    name="Dead Hand",
    power=1, toughness=5,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Horror"},
)


WALLMASTER = make_creature(
    name="Wallmaster",
    power=2, toughness=3,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)


# --- Instants/Sorceries ---

TWILIGHT_CURSE = make_instant(
    name="Twilight Curse",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
)


DARKNESS_FALLS = make_sorcery(
    name="Darkness Falls",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures with power 2 or less."
)


MALICE_SPREAD = make_sorcery(
    name="Malice Spread",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Each opponent sacrifices a creature. You gain life equal to the total power of creatures sacrificed this way."
)


SOUL_HARVEST = make_instant(
    name="Soul Harvest",
    mana_cost="{B}",
    colors={Color.BLACK},
)


GANONS_WRATH = make_sorcery(
    name="Ganon's Wrath",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. You lose 1 life for each creature destroyed this way."
)


# =============================================================================
# RED CARDS - GORON, FIRE, POWER
# =============================================================================

# --- Legendary Creatures ---

DARUK_GORON_CHAMPION = make_creature(
    name="Daruk, Goron Champion",
    power=5, toughness=5,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Champion"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=DealDamage(2, target=EachOpponentTarget())
        )
    ]
)


DARUNIA_GORON_CHIEF = make_creature(
    name="Darunia, Goron Chief",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Goron", include_self=False)
        )
    ]
)


DIN_ORACLE_OF_POWER = make_creature(
    name="Din, Oracle of Power",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Wizard"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=DealDamage(2, target=EachOpponentTarget())
        )
    ]
)


VOLVAGIA_FIRE_DRAGON = make_creature(
    name="Volvagia, Fire Dragon",
    power=6, toughness=5,
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    subtypes={"Dragon"},
    supertypes={"Legendary"},
)


YUNOBO_GORON_DESCENDANT = make_creature(
    name="Yunobo, Goron Descendant",
    power=3, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=DealDamage(3, target=EachOpponentTarget())
        )
    ]
)


# --- Regular Creatures ---

GORON_WARRIOR = make_creature(
    name="Goron Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
)


GORON_SMITH = make_creature(
    name="Goron Smith",
    power=2, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Artificer"},
)


DODONGO = make_creature(
    name="Dodongo",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Lizard"},
)


FIRE_KEESE = make_creature(
    name="Fire Keese",
    power=1, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Bat"},
)


LIZALFOS = make_creature(
    name="Lizalfos",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Lizard", "Warrior"},
)


LYNEL = make_creature(
    name="Lynel",
    power=5, toughness=4,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Beast", "Warrior"},
)


MOBLIN = make_creature(
    name="Moblin",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Goblin", "Warrior"},
)


HINOX = make_creature(
    name="Hinox",
    power=5, toughness=5,
    mana_cost="{4}{R}",
    colors={Color.RED},
    subtypes={"Giant"},
)


GORON_ELDER = make_creature(
    name="Goron Elder",
    power=2, toughness=4,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Cleric"},
)


FIRE_SPIRIT = make_creature(
    name="Fire Spirit",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Spirit"},
)


# --- Instants/Sorceries ---

DINS_FIRE = make_instant(
    name="Din's Fire",
    mana_cost="{R}",
    colors={Color.RED},
)


FIRE_ARROW = make_instant(
    name="Fire Arrow",
    mana_cost="{1}{R}",
    colors={Color.RED},
)


VOLCANIC_ERUPTION = make_sorcery(
    name="Volcanic Eruption",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Volcanic Eruption deals 4 damage to each creature and each player."
)


GORON_RAGE = make_instant(
    name="Goron Rage",
    mana_cost="{1}{R}",
    colors={Color.RED},
)


BOMB_BARRAGE = make_sorcery(
    name="Bomb Barrage",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Bomb Barrage deals 1 damage to each creature and each opponent. If you control a Goron, it deals 2 damage instead."
)


# =============================================================================
# GREEN CARDS - KOKIRI, FOREST, COURAGE
# =============================================================================

# --- Legendary Creatures ---

def link_hero_of_time_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Link uses both Triforce and Dungeon mechanics."""
    interceptors = []
    interceptors.extend(make_triforce_bonus(obj, 2, 2, 1))
    def dungeon_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.DRAW, payload={'player': obj.controller, 'amount': 1}, source=obj.id)]
    interceptors.append(make_dungeon_trigger(obj, 3, dungeon_effect))
    return interceptors

LINK_HERO_OF_TIME = make_creature(
    name="Link, Hero of Time",
    power=3, toughness=3,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Warrior"},
    supertypes={"Legendary"},
    setup_interceptors=link_hero_of_time_setup
)


LINK_CHAMPION_OF_HYRULE = make_creature(
    name="Link, Champion of Hyrule",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Hylian", "Champion"},
    supertypes={"Legendary"},
)


SARIA_FOREST_SAGE = make_creature(
    name="Saria, Forest Sage",
    power=2, toughness=3,
    mana_cost="{1}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Druid"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Kokiri", include_self=False)
        )
    ]
)


REVALI_RITO_CHAMPION = make_creature(
    name="Revali, Rito Champion",
    power=3, toughness=3,
    mana_cost="{2}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Champion"},
    supertypes={"Legendary"},
)


GREAT_DEKU_TREE = make_creature(
    name="Great Deku Tree",
    power=0, toughness=8,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=CreateToken(name="Deku Sprout", power=1, toughness=1, colors={'G'}, subtypes={'Plant'})
        )
    ]
)


FARORE_ORACLE_OF_COURAGE = make_creature(
    name="Farore, Oracle of Courage",
    power=3, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Druid"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Spirit", power=2, toughness=2, colors={'G'}, subtypes={'Spirit'})
        )
    ]
)


# --- Regular Creatures ---

KOKIRI_CHILD = make_creature(
    name="Kokiri Child",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri"},
)


KOKIRI_WARRIOR = make_creature(
    name="Kokiri Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Kokiri", "Warrior"},
)


SKULL_KID = make_creature(
    name="Skull Kid",
    power=2, toughness=1,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit"},
)


DEKU_SCRUB = make_creature(
    name="Deku Scrub",
    power=1, toughness=2,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
)


FOREST_FAIRY = make_creature(
    name="Forest Fairy",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Fairy"},
)


WOLFOS = make_creature(
    name="Wolfos",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Wolf"},
)


FOREST_TEMPLE_GUARDIAN = make_creature(
    name="Forest Temple Guardian",
    power=4, toughness=4,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
)


DEKU_BABA = make_creature(
    name="Deku Baba",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Plant"},
)


RITO_WARRIOR = make_creature(
    name="Rito Warrior",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Warrior"},
)


KOROKS = make_creature(
    name="Korok",
    power=0, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Spirit"},
)


# --- Instants/Sorceries ---

FARORES_WIND = make_instant(
    name="Farore's Wind",
    mana_cost="{G}",
    colors={Color.GREEN},
)


FOREST_BLESSING = make_sorcery(
    name="Forest Blessing",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a basic Forest card and put it onto the battlefield tapped. Create a 1/1 green Plant creature token."
)


NATURES_FURY = make_sorcery(
    name="Nature's Fury",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +2/+2 and gain trample until end of turn."
)


DEKU_NUT_STUN = make_instant(
    name="Deku Nut Stun",
    mana_cost="{G}",
    colors={Color.GREEN},
)


WILD_GROWTH = make_enchantment(
    name="Wild Growth",
    mana_cost="{G}",
    colors={Color.GREEN},
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

URBOSA_GERUDO_CHAMPION = make_creature(
    name="Urbosa, Gerudo Champion",
    power=4, toughness=4,
    mana_cost="{2}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Gerudo", "Champion"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=DealDamage(2, target=EachOpponentTarget())
        )
    ]
)


FI_SWORD_SPIRIT = make_creature(
    name="Fi, Sword Spirit",
    power=2, toughness=3,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=SpellCastTrigger(), effect=Scry(1))
    ]
)


NABOORU_SPIRIT_SAGE = make_creature(
    name="Nabooru, Spirit Sage",
    power=3, toughness=3,
    mana_cost="{1}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Gerudo", "Cleric"},
    supertypes={"Legendary"},
)


SKULL_KID_MASKED_MENACE = make_creature(
    name="Skull Kid, Masked Menace",
    power=3, toughness=2,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Spirit"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=DiscardCards(1, target=EachOpponentTarget(), random=True)
        )
    ]
)


TETRA_PIRATE_PRINCESS = make_creature(
    name="Tetra, Pirate Princess",
    power=3, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Hylian", "Pirate"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=CreateToken(name="Treasure", power=0, toughness=0, subtypes={'Treasure'})
        )
    ]
)


GROOSE_SKYLOFT_HERO = make_creature(
    name="Groose, Skyloft Hero",
    power=3, toughness=3,
    mana_cost="{2}{R}{W}",
    colors={Color.RED, Color.WHITE},
    subtypes={"Hylian", "Warrior"},
    supertypes={"Legendary"},
)


MALON_RANCH_KEEPER = make_creature(
    name="Malon, Ranch Keeper",
    power=2, toughness=3,
    mana_cost="{1}{G}{W}",
    colors={Color.GREEN, Color.WHITE},
    subtypes={"Hylian", "Druid"},
    supertypes={"Legendary"},
)


# =============================================================================
# ARTIFACTS - TRIFORCE, DIVINE BEASTS, ITEMS
# =============================================================================

# --- Triforce Pieces ---

TRIFORCE_OF_POWER = make_artifact(
    name="Triforce of Power",
    mana_cost="{3}",
    text="Creatures you control get +1/+0. {T}: Target creature gets +3/+0 until end of turn.",
    supertypes={"Legendary"}
)


TRIFORCE_OF_WISDOM = make_artifact(
    name="Triforce of Wisdom",
    mana_cost="{3}",
    text="Whenever you draw a card, you may pay {1}. If you do, scry 1. {T}: Draw a card, then discard a card.",
    supertypes={"Legendary"}
)


TRIFORCE_OF_COURAGE = make_artifact(
    name="Triforce of Courage",
    mana_cost="{3}",
    text="Creatures you control have vigilance. {T}: Target creature gains indestructible until end of turn.",
    supertypes={"Legendary"}
)


# --- Divine Beasts ---

DIVINE_BEAST_VAH_RUTA = make_artifact(
    name="Divine Beast Vah Ruta",
    mana_cost="{5}",
    text="At the beginning of your upkeep, you gain 2 life. {3}, {T}: Return target creature to its owner's hand.",
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=GainLife(2))
    ]
)


DIVINE_BEAST_VAH_RUDANIA = make_artifact(
    name="Divine Beast Vah Rudania",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Divine Beast Vah Rudania deals 2 damage to any target. {3}, {T}: It deals 3 damage to target creature.",
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=DealDamage(2, target=EachOpponentTarget()))
    ]
)


DIVINE_BEAST_VAH_MEDOH = make_artifact(
    name="Divine Beast Vah Medoh",
    mana_cost="{5}",
    text="At the beginning of your upkeep, scry 2. {3}, {T}: Target creature gains flying until end of turn.",
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=Scry(2))
    ]
)


DIVINE_BEAST_VAH_NABORIS = make_artifact(
    name="Divine Beast Vah Naboris",
    mana_cost="{5}",
    text="At the beginning of your upkeep, Vah Naboris deals 1 damage to each opponent. {3}, {T}: Tap target creature.",
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(trigger=UpkeepTrigger(), effect=DealDamage(1, target=EachOpponentTarget()))
    ]
)


# --- Equipment ---

MASTER_SWORD = make_equipment(
    name="Master Sword",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has vigilance. If equipped creature is legendary, it also has indestructible.",
    supertypes={"Legendary"}
)


HYLIAN_SHIELD = make_equipment(
    name="Hylian Shield",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature gets +0/+3 and has hexproof.",
    supertypes={"Legendary"}
)


HEROS_BOW = make_equipment(
    name="Hero's Bow",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: This creature deals 2 damage to target creature with flying.'"
)


BIGGORONS_SWORD = make_equipment(
    name="Biggoron's Sword",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +5/+0 and has trample. Equipped creature can't block.",
    supertypes={"Legendary"}
)


MIRROR_SHIELD = make_equipment(
    name="Mirror Shield",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2. Whenever equipped creature is dealt damage by a source, that source's controller loses that much life."
)


ANCIENT_BOW = make_equipment(
    name="Ancient Bow",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+1 and has '{T}: This creature deals 3 damage to any target.'"
)


KOKIRI_SWORD = make_equipment(
    name="Kokiri Sword",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+1."
)


# --- Masks ---

MAJORAS_MASK = make_equipment(
    name="Majora's Mask",
    mana_cost="{3}",
    equip_cost="{2}",
    text="Equipped creature gets +3/+3 and has menace. At the beginning of your upkeep, you lose 1 life.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


FIERCE_DEITY_MASK = make_equipment(
    name="Fierce Deity Mask",
    mana_cost="{4}",
    equip_cost="{3}",
    text="Equipped creature gets +4/+4 and has double strike. Equip only to a legendary creature.",
    subtypes={"Mask"},
    supertypes={"Legendary"}
)


DEKU_MASK = make_equipment(
    name="Deku Mask",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature has '{T}: Add {G}.' and is a Plant in addition to its other types.",
    subtypes={"Mask"}
)


GORON_MASK = make_equipment(
    name="Goron Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +2/+2, has trample, and is a Goron in addition to its other types.",
    subtypes={"Mask"}
)


ZORA_MASK = make_equipment(
    name="Zora Mask",
    mana_cost="{2}",
    equip_cost="{2}",
    text="Equipped creature gets +1/+2, can't be blocked, and is a Zora in addition to its other types.",
    subtypes={"Mask"}
)


BUNNY_HOOD = make_equipment(
    name="Bunny Hood",
    mana_cost="{1}",
    equip_cost="{1}",
    text="Equipped creature gets +1/+0 and has haste.",
    subtypes={"Mask"}
)


STONE_MASK = make_equipment(
    name="Stone Mask",
    mana_cost="{2}",
    equip_cost="{1}",
    text="Equipped creature has hexproof and can't attack or block.",
    subtypes={"Mask"}
)


# --- Other Artifacts ---

OCARINA_OF_TIME = make_artifact(
    name="Ocarina of Time",
    mana_cost="{3}",
    text="{2}, {T}: Choose one - Return target creature to its owner's hand; or untap all creatures you control; or scry 3.",
    supertypes={"Legendary"}
)


SHEIKAH_SLATE = make_artifact(
    name="Sheikah Slate",
    mana_cost="{2}",
    text="{T}: Look at the top card of your library. {1}, {T}: Scry 2.",
    supertypes={"Legendary"}
)


BOMB_BAG = make_artifact(
    name="Bomb Bag",
    mana_cost="{2}",
    text="{2}, {T}: Bomb Bag deals 2 damage to any target."
)


FAIRY_BOTTLE = make_artifact(
    name="Fairy Bottle",
    mana_cost="{1}",
    text="Sacrifice Fairy Bottle: You gain 5 life."
)


MAGIC_BOOMERANG = make_artifact(
    name="Magic Boomerang",
    mana_cost="{2}",
    text="{1}, {T}: Tap target creature. It doesn't untap during its controller's next untap step."
)


HOOKSHOT = make_artifact(
    name="Hookshot",
    mana_cost="{2}",
    text="{2}, {T}: Put target creature you control on top of its owner's library. Draw a card."
)


HEART_CONTAINER_ARTIFACT = make_artifact(
    name="Heart Container",
    mana_cost="{2}",
    text="When Heart Container enters, you gain 4 life. Sacrifice Heart Container: You gain 2 life.",
    abilities=[
        TriggeredAbility(trigger=ETBTrigger(), effect=GainLife(4))
    ]
)


LENS_OF_TRUTH = make_artifact(
    name="Lens of Truth",
    mana_cost="{2}",
    text="{1}, {T}: Look at target player's hand. You may look at face-down cards on the battlefield."
)


ANCIENT_CORE = make_artifact(
    name="Ancient Core",
    mana_cost="{3}",
    text="{T}: Add {C}{C}. Activate only if you control an artifact creature."
)


GUARDIAN_PARTS = make_artifact(
    name="Guardian Parts",
    mana_cost="{1}",
    text="Sacrifice Guardian Parts: Add {C}{C}. Spend this mana only to cast artifact spells or activate abilities of artifacts."
)


# =============================================================================
# ENCHANTMENTS
# =============================================================================

SACRED_PROTECTION = make_enchantment(
    name="Sacred Protection",
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
)


ZORAS_DOMAIN = make_enchantment(
    name="Zora's Domain",
    mana_cost="{2}{U}{U}",
    colors={Color.BLUE},
)


TWILIGHT_REALM = make_enchantment(
    name="Twilight Realm",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
)


GORON_STRENGTH = make_enchantment(
    name="Goron Strength",
    mana_cost="{1}{R}",
    colors={Color.RED},
)


KOKIRI_FOREST = make_enchantment(
    name="Kokiri Forest",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
)


HYLIA_BLESSING = make_enchantment(
    name="Hylia's Blessing",
    mana_cost="{W}",
    colors={Color.WHITE},
)


ANCIENT_TECHNOLOGY = make_enchantment(
    name="Ancient Technology",
    mana_cost="{2}",
    colors=set(),
)


SPIRIT_TRACKS = make_enchantment(
    name="Spirit Tracks",
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
)


# =============================================================================
# LANDS
# =============================================================================

HYRULE_CASTLE = make_land(
    name="Hyrule Castle",
    text="{T}: Add {W}. {2}, {T}: Create a 1/1 white Soldier creature token.",
    supertypes={"Legendary"}
)


DEATH_MOUNTAIN = make_land(
    name="Death Mountain",
    text="{T}: Add {R}. {T}: Add {R}{R}. Spend this mana only to cast Goron spells.",
    supertypes={"Legendary"}
)


ZORAS_DOMAIN_LAND = make_land(
    name="Zora's Domain",
    text="{T}: Add {U}. {2}, {T}: Target creature can't be blocked this turn.",
    supertypes={"Legendary"}
)


LOST_WOODS = make_land(
    name="Lost Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast Kokiri or Plant spells.",
    supertypes={"Legendary"}
)


GERUDO_DESERT = make_land(
    name="Gerudo Desert",
    text="{T}: Add {R} or {B}.",
    supertypes={"Legendary"}
)


TEMPLE_OF_TIME = make_land(
    name="Temple of Time",
    text="{T}: Add {C}. {T}: Add one mana of any color. Spend this mana only to cast legendary spells.",
    supertypes={"Legendary"}
)


KAKARIKO_VILLAGE = make_land(
    name="Kakariko Village",
    text="{T}: Add {W}. When Kakariko Village enters, you gain 1 life."
)


LAKE_HYLIA = make_land(
    name="Lake Hylia",
    text="{T}: Add {U}. {2}, {T}: Draw a card, then discard a card."
)


LON_LON_RANCH = make_land(
    name="Lon Lon Ranch",
    text="{T}: Add {G} or {W}."
)


GREAT_PLATEAU = make_land(
    name="Great Plateau",
    text="{T}: Add {C}. {3}, {T}: Add one mana of any color."
)


AKKALA_CITADEL = make_land(
    name="Akkala Citadel",
    text="{T}: Add {R} or {W}."
)


FARON_WOODS = make_land(
    name="Faron Woods",
    text="{T}: Add {G}. {T}: Add {G}{G}. Spend this mana only to cast creature spells."
)


ELDIN_VOLCANO = make_land(
    name="Eldin Volcano",
    text="{T}: Add {R}. Eldin Volcano enters tapped unless you control a Goron."
)


LANAYRU_WETLANDS = make_land(
    name="Lanayru Wetlands",
    text="{T}: Add {U}. Lanayru Wetlands enters tapped unless you control a Zora."
)


LURELIN_VILLAGE = make_land(
    name="Lurelin Village",
    text="{T}: Add {U} or {G}."
)


SKYLOFT = make_land(
    name="Skyloft",
    text="{T}: Add {W} or {U}. {T}: Add {C}. Spend this mana only to activate abilities.",
    supertypes={"Legendary"}
)


SHADOW_TEMPLE = make_land(
    name="Shadow Temple",
    text="{T}: Add {B}. {1}{B}, {T}: Target creature gets -1/-1 until end of turn."
)


FIRE_TEMPLE = make_land(
    name="Fire Temple",
    text="{T}: Add {R}. {1}{R}, {T}: Fire Temple deals 1 damage to any target."
)


WATER_TEMPLE = make_land(
    name="Water Temple",
    text="{T}: Add {U}. {1}{U}, {T}: Tap target creature."
)


FOREST_TEMPLE = make_land(
    name="Forest Temple",
    text="{T}: Add {G}. {1}{G}, {T}: Target creature gets +1/+1 until end of turn."
)


SPIRIT_TEMPLE = make_land(
    name="Spirit Temple",
    text="{T}: Add {W} or {R}. {2}, {T}: Exile target card from a graveyard."
)


# --- Basic Lands ---

PLAINS_LOZ = make_land(
    name="Plains",
    text="{T}: Add {W}.",
    subtypes={"Plains"}
)


ISLAND_LOZ = make_land(
    name="Island",
    text="{T}: Add {U}.",
    subtypes={"Island"}
)


SWAMP_LOZ = make_land(
    name="Swamp",
    text="{T}: Add {B}.",
    subtypes={"Swamp"}
)


MOUNTAIN_LOZ = make_land(
    name="Mountain",
    text="{T}: Add {R}.",
    subtypes={"Mountain"}
)


FOREST_LOZ = make_land(
    name="Forest",
    text="{T}: Add {G}.",
    subtypes={"Forest"}
)


# =============================================================================
# ADDITIONAL CREATURES TO REACH ~250
# =============================================================================

# More White
FAIRY_COMPANION = make_creature(
    name="Fairy Companion",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Fairy"},
)

HYRULE_SOLDIER = make_creature(
    name="Hyrule Soldier",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Soldier"},
)

LIGHT_SAGE = make_creature(
    name="Light Sage",
    power=1, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Spirit", "Cleric"},
)

SACRED_KNIGHT = make_creature(
    name="Sacred Knight",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Knight"},
)

# More Blue
ZORA_GUARD = make_creature(
    name="Zora Guard",
    power=2, toughness=3,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Zora", "Soldier"},
)

DEEP_SEA_ZORA = make_creature(
    name="Deep Sea Zora",
    power=3, toughness=4,
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Zora"},
)

WISDOM_FAIRY = make_creature(
    name="Wisdom Fairy",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Fairy"},
)

RIVER_GUARDIAN = make_creature(
    name="River Guardian",
    power=2, toughness=4,
    mana_cost="{3}{U}",
    colors={Color.BLUE},
    subtypes={"Elemental"},
)

# More Black
SHADOW_LINK = make_creature(
    name="Shadow Link",
    power=3, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Hylian", "Shadow"},
)

DARK_INTERLOPERS = make_creature(
    name="Dark Interlopers",
    power=4, toughness=4,
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Horror"},
)

TWILIGHT_MESSENGER = make_creature(
    name="Twilight Messenger",
    power=2, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Spirit"},
)

CURSED_BOKOBLIN = make_creature(
    name="Cursed Bokoblin",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Goblin", "Skeleton"},
)

# More Red
FIRE_TEMPLE_GORON = make_creature(
    name="Fire Temple Goron",
    power=4, toughness=3,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Goron", "Warrior"},
)

BOKOBLIN_HORDE = make_creature(
    name="Bokoblin Horde",
    power=4, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Goblin"},
)

VOLCANIC_KEESE = make_creature(
    name="Volcanic Keese",
    power=2, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Bat"},
)

TALUS = make_creature(
    name="Stone Talus",
    power=6, toughness=6,
    mana_cost="{5}{R}",
    colors={Color.RED},
    subtypes={"Elemental", "Giant"},
)

# More Green
FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=4, toughness=5,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Spirit", "Warrior"},
)

DEKU_TREE_SPROUT = make_creature(
    name="Deku Tree Sprout",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Plant", "Treefolk"},
)

WILD_HORSE = make_creature(
    name="Wild Horse",
    power=3, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Horse"},
)

RITO_ELDER = make_creature(
    name="Rito Elder",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Rito", "Druid"},
)

MASTER_KOHGA = make_creature(
    name="Master Kohga",
    power=2, toughness=4,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Rogue"},
    supertypes={"Legendary"},
)

GHIRAHIM_DEMON_LORD = make_creature(
    name="Ghirahim, Demon Lord",
    power=4, toughness=3,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon"},
    supertypes={"Legendary"},
)

DEMISE_DEMON_KING = make_creature(
    name="Demise, Demon King",
    power=7, toughness=6,
    mana_cost="{4}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Demon", "God"},
    supertypes={"Legendary"},
)

KING_RHOAM = make_creature(
    name="King Rhoam Bosphoramus",
    power=3, toughness=4,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Hylian", "Noble", "Spirit"},
    supertypes={"Legendary"},
)

KASS_RITO_BARD = make_creature(
    name="Kass, Rito Bard",
    power=2, toughness=3,
    mana_cost="{1}{G}{U}",
    colors={Color.GREEN, Color.BLUE},
    subtypes={"Rito", "Bard"},
    supertypes={"Legendary"},
)

BEEDLE_TRAVELING_MERCHANT = make_creature(
    name="Beedle, Traveling Merchant",
    power=1, toughness=2,
    mana_cost="{2}",
    colors=set(),
    subtypes={"Human", "Merchant"},
    supertypes={"Legendary"},
)

PURAH_SHEIKAH_RESEARCHER = make_creature(
    name="Purah, Sheikah Researcher",
    power=1, toughness=3,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
)

ROBBIE_ANCIENT_TECH = make_creature(
    name="Robbie, Ancient Tech Expert",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Sheikah", "Artificer"},
    supertypes={"Legendary"},
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

LEGEND_OF_ZELDA_CARDS = {
    # WHITE LEGENDARIES
    "Zelda, Princess of Hyrule": ZELDA_PRINCESS_OF_HYRULE,
    "Zelda, Wielder of Wisdom": ZELDA_WIELDER_OF_WISDOM,
    "Impa, Sheikah Guardian": IMPA_SHEIKAH_GUARDIAN,
    "Rauru, Sage of Light": RAURU_SAGE_OF_LIGHT,
    "Hylia, Goddess of Light": HYLIA_GODDESS_OF_LIGHT,

    # WHITE CREATURES
    "Sheikah Warrior": SHEIKAH_WARRIOR,
    "Hyrule Knight": HYRULE_KNIGHT,
    "Temple Guardian": TEMPLE_GUARDIAN,
    "Castle Guard": CASTLE_GUARD,
    "Light Spirit": LIGHT_SPIRIT,
    "Hylian Priestess": HYLIAN_PRIESTESS,
    "Sheikah Scout": SHEIKAH_SCOUT,
    "Courage Fairy": COURAGE_FAIRY,
    "Hyrule Captain": HYRULE_CAPTAIN,
    "Great Fairy": GREAT_FAIRY,
    "Sacred Realm Guardian": SACRED_REALM_GUARDIAN,
    "Fairy Companion": FAIRY_COMPANION,
    "Hyrule Soldier": HYRULE_SOLDIER,
    "Light Sage": LIGHT_SAGE,
    "Sacred Knight": SACRED_KNIGHT,
    "King Rhoam Bosphoramus": KING_RHOAM,

    # WHITE SPELLS
    "Din's Fire Shield": DINS_FIRE_SHIELD,
    "Light Arrow": LIGHT_ARROW,
    "Nayru's Love": NAYRUS_LOVE,
    "Song of Healing": SONG_OF_HEALING,
    "Blessing of Hylia": BLESSING_OF_HYLIA,

    # BLUE LEGENDARIES
    "Mipha, Zora Champion": MIPHA_ZORA_CHAMPION,
    "Ruto, Zora Princess": RUTO_ZORA_PRINCESS,
    "King Zora, Domain Ruler": KING_ZORA,
    "Nayru, Oracle of Wisdom": NAYRU_ORACLE_OF_WISDOM,
    "Sidon, Zora Prince": SIDON_ZORA_PRINCE,

    # BLUE CREATURES
    "Zora Warrior": ZORA_WARRIOR,
    "Zora Scholar": ZORA_SCHOLAR,
    "River Zora": RIVER_ZORA,
    "Water Spirit": WATER_SPIRIT,
    "Octorok": OCTOROK,
    "Like-Like": LIKE_LIKE,
    "Gyorg": GYORG,
    "Zora Diver": ZORA_DIVER,
    "Zora Spearman": ZORA_SPEARMAN,
    "Zora Sage": ZORA_SAGE,
    "Zora Guard": ZORA_GUARD,
    "Deep Sea Zora": DEEP_SEA_ZORA,
    "Wisdom Fairy": WISDOM_FAIRY,
    "River Guardian": RIVER_GUARDIAN,
    "Robbie, Ancient Tech Expert": ROBBIE_ANCIENT_TECH,

    # BLUE SPELLS
    "Zora's Sapphire Blessing": ZORAS_SAPPHIRE_BLESSING,
    "Torrential Wave": TORRENTIAL_WAVE,
    "Water Temple Flood": WATER_TEMPLE_FLOOD,
    "Wisdom of Ages": WISDOM_OF_AGES,
    "Counter Magic": COUNTER_MAGIC,

    # BLACK LEGENDARIES
    "Ganondorf, King of Evil": GANONDORF_KING_OF_EVIL,
    "Ganon, Calamity Incarnate": GANON_CALAMITY_INCARNATE,
    "Zant, Twilight Usurper": ZANT_TWILIGHT_USURPER,
    "Midna, Twilight Princess": MIDNA_TWILIGHT_PRINCESS,
    "Vaati, Wind Mage": VAATI_WIND_MAGE,

    # BLACK CREATURES
    "Shadow Beast": SHADOW_BEAST,
    "Stalfos Warrior": STALFOS_WARRIOR,
    "ReDead": REDEAD,
    "Gibdo": GIBDO,
    "Poe": POES,
    "Darknut": DARK_NUT,
    "Phantom": PHANTOM,
    "Floormaster": FLOORMASTER,
    "Dead Hand": DEAD_HAND,
    "Wallmaster": WALLMASTER,
    "Shadow Link": SHADOW_LINK,
    "Dark Interlopers": DARK_INTERLOPERS,
    "Twilight Messenger": TWILIGHT_MESSENGER,
    "Cursed Bokoblin": CURSED_BOKOBLIN,

    # BLACK SPELLS
    "Twilight Curse": TWILIGHT_CURSE,
    "Darkness Falls": DARKNESS_FALLS,
    "Malice Spread": MALICE_SPREAD,
    "Soul Harvest": SOUL_HARVEST,
    "Ganon's Wrath": GANONS_WRATH,

    # RED LEGENDARIES
    "Daruk, Goron Champion": DARUK_GORON_CHAMPION,
    "Darunia, Goron Chief": DARUNIA_GORON_CHIEF,
    "Din, Oracle of Power": DIN_ORACLE_OF_POWER,
    "Volvagia, Fire Dragon": VOLVAGIA_FIRE_DRAGON,
    "Yunobo, Goron Descendant": YUNOBO_GORON_DESCENDANT,

    # RED CREATURES
    "Goron Warrior": GORON_WARRIOR,
    "Goron Smith": GORON_SMITH,
    "Dodongo": DODONGO,
    "Fire Keese": FIRE_KEESE,
    "Lizalfos": LIZALFOS,
    "Lynel": LYNEL,
    "Moblin": MOBLIN,
    "Hinox": HINOX,
    "Goron Elder": GORON_ELDER,
    "Fire Spirit": FIRE_SPIRIT,
    "Fire Temple Goron": FIRE_TEMPLE_GORON,
    "Bokoblin Horde": BOKOBLIN_HORDE,
    "Volcanic Keese": VOLCANIC_KEESE,
    "Stone Talus": TALUS,

    # RED SPELLS
    "Din's Fire": DINS_FIRE,
    "Fire Arrow": FIRE_ARROW,
    "Volcanic Eruption": VOLCANIC_ERUPTION,
    "Goron Rage": GORON_RAGE,
    "Bomb Barrage": BOMB_BARRAGE,

    # GREEN LEGENDARIES
    "Link, Hero of Time": LINK_HERO_OF_TIME,
    "Link, Champion of Hyrule": LINK_CHAMPION_OF_HYRULE,
    "Saria, Forest Sage": SARIA_FOREST_SAGE,
    "Revali, Rito Champion": REVALI_RITO_CHAMPION,
    "Great Deku Tree": GREAT_DEKU_TREE,
    "Farore, Oracle of Courage": FARORE_ORACLE_OF_COURAGE,

    # GREEN CREATURES
    "Kokiri Child": KOKIRI_CHILD,
    "Kokiri Warrior": KOKIRI_WARRIOR,
    "Skull Kid": SKULL_KID,
    "Deku Scrub": DEKU_SCRUB,
    "Forest Fairy": FOREST_FAIRY,
    "Wolfos": WOLFOS,
    "Forest Temple Guardian": FOREST_TEMPLE_GUARDIAN,
    "Deku Baba": DEKU_BABA,
    "Rito Warrior": RITO_WARRIOR,
    "Korok": KOROKS,
    "Forest Guardian": FOREST_GUARDIAN,
    "Deku Tree Sprout": DEKU_TREE_SPROUT,
    "Wild Horse": WILD_HORSE,
    "Rito Elder": RITO_ELDER,

    # GREEN SPELLS
    "Farore's Wind": FARORES_WIND,
    "Forest Blessing": FOREST_BLESSING,
    "Nature's Fury": NATURES_FURY,
    "Deku Nut Stun": DEKU_NUT_STUN,
    "Wild Growth": WILD_GROWTH,

    # MULTICOLOR LEGENDARIES
    "Urbosa, Gerudo Champion": URBOSA_GERUDO_CHAMPION,
    "Fi, Sword Spirit": FI_SWORD_SPIRIT,
    "Nabooru, Spirit Sage": NABOORU_SPIRIT_SAGE,
    "Skull Kid, Masked Menace": SKULL_KID_MASKED_MENACE,
    "Tetra, Pirate Princess": TETRA_PIRATE_PRINCESS,
    "Groose, Skyloft Hero": GROOSE_SKYLOFT_HERO,
    "Malon, Ranch Keeper": MALON_RANCH_KEEPER,
    "Master Kohga": MASTER_KOHGA,
    "Ghirahim, Demon Lord": GHIRAHIM_DEMON_LORD,
    "Demise, Demon King": DEMISE_DEMON_KING,
    "Kass, Rito Bard": KASS_RITO_BARD,
    "Purah, Sheikah Researcher": PURAH_SHEIKAH_RESEARCHER,

    # TRIFORCE ARTIFACTS
    "Triforce of Power": TRIFORCE_OF_POWER,
    "Triforce of Wisdom": TRIFORCE_OF_WISDOM,
    "Triforce of Courage": TRIFORCE_OF_COURAGE,

    # DIVINE BEASTS
    "Divine Beast Vah Ruta": DIVINE_BEAST_VAH_RUTA,
    "Divine Beast Vah Rudania": DIVINE_BEAST_VAH_RUDANIA,
    "Divine Beast Vah Medoh": DIVINE_BEAST_VAH_MEDOH,
    "Divine Beast Vah Naboris": DIVINE_BEAST_VAH_NABORIS,

    # EQUIPMENT
    "Master Sword": MASTER_SWORD,
    "Hylian Shield": HYLIAN_SHIELD,
    "Hero's Bow": HEROS_BOW,
    "Biggoron's Sword": BIGGORONS_SWORD,
    "Mirror Shield": MIRROR_SHIELD,
    "Ancient Bow": ANCIENT_BOW,
    "Kokiri Sword": KOKIRI_SWORD,

    # MASKS
    "Majora's Mask": MAJORAS_MASK,
    "Fierce Deity Mask": FIERCE_DEITY_MASK,
    "Deku Mask": DEKU_MASK,
    "Goron Mask": GORON_MASK,
    "Zora Mask": ZORA_MASK,
    "Bunny Hood": BUNNY_HOOD,
    "Stone Mask": STONE_MASK,

    # OTHER ARTIFACTS
    "Ocarina of Time": OCARINA_OF_TIME,
    "Sheikah Slate": SHEIKAH_SLATE,
    "Bomb Bag": BOMB_BAG,
    "Fairy Bottle": FAIRY_BOTTLE,
    "Magic Boomerang": MAGIC_BOOMERANG,
    "Hookshot": HOOKSHOT,
    "Heart Container": HEART_CONTAINER_ARTIFACT,
    "Lens of Truth": LENS_OF_TRUTH,
    "Ancient Core": ANCIENT_CORE,
    "Guardian Parts": GUARDIAN_PARTS,
    "Beedle, Traveling Merchant": BEEDLE_TRAVELING_MERCHANT,

    # ENCHANTMENTS
    "Sacred Protection": SACRED_PROTECTION,
    "Zora's Domain (Enchantment)": ZORAS_DOMAIN,
    "Twilight Realm": TWILIGHT_REALM,
    "Goron Strength": GORON_STRENGTH,
    "Kokiri Forest (Enchantment)": KOKIRI_FOREST,
    "Hylia's Blessing": HYLIA_BLESSING,
    "Ancient Technology": ANCIENT_TECHNOLOGY,
    "Spirit Tracks": SPIRIT_TRACKS,

    # LANDS
    "Hyrule Castle": HYRULE_CASTLE,
    "Death Mountain": DEATH_MOUNTAIN,
    "Zora's Domain (Land)": ZORAS_DOMAIN_LAND,
    "Lost Woods": LOST_WOODS,
    "Gerudo Desert": GERUDO_DESERT,
    "Temple of Time": TEMPLE_OF_TIME,
    "Kakariko Village": KAKARIKO_VILLAGE,
    "Lake Hylia": LAKE_HYLIA,
    "Lon Lon Ranch": LON_LON_RANCH,
    "Great Plateau": GREAT_PLATEAU,
    "Akkala Citadel": AKKALA_CITADEL,
    "Faron Woods": FARON_WOODS,
    "Eldin Volcano": ELDIN_VOLCANO,
    "Lanayru Wetlands": LANAYRU_WETLANDS,
    "Lurelin Village": LURELIN_VILLAGE,
    "Skyloft": SKYLOFT,
    "Shadow Temple": SHADOW_TEMPLE,
    "Fire Temple": FIRE_TEMPLE,
    "Water Temple": WATER_TEMPLE,
    "Forest Temple": FOREST_TEMPLE,
    "Spirit Temple": SPIRIT_TEMPLE,

    # BASIC LANDS
    "Plains": PLAINS_LOZ,
    "Island": ISLAND_LOZ,
    "Swamp": SWAMP_LOZ,
    "Mountain": MOUNTAIN_LOZ,
    "Forest": FOREST_LOZ,
}

print(f"Loaded {len(LEGEND_OF_ZELDA_CARDS)} Legend of Zelda: Hyrule Chronicles cards")


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    ZELDA_PRINCESS_OF_HYRULE,
    ZELDA_WIELDER_OF_WISDOM,
    IMPA_SHEIKAH_GUARDIAN,
    RAURU_SAGE_OF_LIGHT,
    HYLIA_GODDESS_OF_LIGHT,
    SHEIKAH_WARRIOR,
    HYRULE_KNIGHT,
    TEMPLE_GUARDIAN,
    CASTLE_GUARD,
    LIGHT_SPIRIT,
    HYLIAN_PRIESTESS,
    SHEIKAH_SCOUT,
    COURAGE_FAIRY,
    HYRULE_CAPTAIN,
    GREAT_FAIRY,
    SACRED_REALM_GUARDIAN,
    DINS_FIRE_SHIELD,
    LIGHT_ARROW,
    NAYRUS_LOVE,
    SONG_OF_HEALING,
    BLESSING_OF_HYLIA,
    MIPHA_ZORA_CHAMPION,
    RUTO_ZORA_PRINCESS,
    KING_ZORA,
    NAYRU_ORACLE_OF_WISDOM,
    SIDON_ZORA_PRINCE,
    ZORA_WARRIOR,
    ZORA_SCHOLAR,
    RIVER_ZORA,
    WATER_SPIRIT,
    OCTOROK,
    LIKE_LIKE,
    GYORG,
    ZORA_DIVER,
    ZORA_SPEARMAN,
    ZORA_SAGE,
    ZORAS_SAPPHIRE_BLESSING,
    TORRENTIAL_WAVE,
    WATER_TEMPLE_FLOOD,
    WISDOM_OF_AGES,
    COUNTER_MAGIC,
    GANONDORF_KING_OF_EVIL,
    GANON_CALAMITY_INCARNATE,
    ZANT_TWILIGHT_USURPER,
    MIDNA_TWILIGHT_PRINCESS,
    VAATI_WIND_MAGE,
    SHADOW_BEAST,
    STALFOS_WARRIOR,
    REDEAD,
    GIBDO,
    POES,
    DARK_NUT,
    PHANTOM,
    FLOORMASTER,
    DEAD_HAND,
    WALLMASTER,
    TWILIGHT_CURSE,
    DARKNESS_FALLS,
    MALICE_SPREAD,
    SOUL_HARVEST,
    GANONS_WRATH,
    DARUK_GORON_CHAMPION,
    DARUNIA_GORON_CHIEF,
    DIN_ORACLE_OF_POWER,
    VOLVAGIA_FIRE_DRAGON,
    YUNOBO_GORON_DESCENDANT,
    GORON_WARRIOR,
    GORON_SMITH,
    DODONGO,
    FIRE_KEESE,
    LIZALFOS,
    LYNEL,
    MOBLIN,
    HINOX,
    GORON_ELDER,
    FIRE_SPIRIT,
    DINS_FIRE,
    FIRE_ARROW,
    VOLCANIC_ERUPTION,
    GORON_RAGE,
    BOMB_BARRAGE,
    LINK_HERO_OF_TIME,
    LINK_CHAMPION_OF_HYRULE,
    SARIA_FOREST_SAGE,
    REVALI_RITO_CHAMPION,
    GREAT_DEKU_TREE,
    FARORE_ORACLE_OF_COURAGE,
    KOKIRI_CHILD,
    KOKIRI_WARRIOR,
    SKULL_KID,
    DEKU_SCRUB,
    FOREST_FAIRY,
    WOLFOS,
    FOREST_TEMPLE_GUARDIAN,
    DEKU_BABA,
    RITO_WARRIOR,
    KOROKS,
    FARORES_WIND,
    FOREST_BLESSING,
    NATURES_FURY,
    DEKU_NUT_STUN,
    WILD_GROWTH,
    URBOSA_GERUDO_CHAMPION,
    FI_SWORD_SPIRIT,
    NABOORU_SPIRIT_SAGE,
    SKULL_KID_MASKED_MENACE,
    TETRA_PIRATE_PRINCESS,
    GROOSE_SKYLOFT_HERO,
    MALON_RANCH_KEEPER,
    TRIFORCE_OF_POWER,
    TRIFORCE_OF_WISDOM,
    TRIFORCE_OF_COURAGE,
    DIVINE_BEAST_VAH_RUTA,
    DIVINE_BEAST_VAH_RUDANIA,
    DIVINE_BEAST_VAH_MEDOH,
    DIVINE_BEAST_VAH_NABORIS,
    MASTER_SWORD,
    HYLIAN_SHIELD,
    HEROS_BOW,
    BIGGORONS_SWORD,
    MIRROR_SHIELD,
    ANCIENT_BOW,
    KOKIRI_SWORD,
    MAJORAS_MASK,
    FIERCE_DEITY_MASK,
    DEKU_MASK,
    GORON_MASK,
    ZORA_MASK,
    BUNNY_HOOD,
    STONE_MASK,
    OCARINA_OF_TIME,
    SHEIKAH_SLATE,
    BOMB_BAG,
    FAIRY_BOTTLE,
    MAGIC_BOOMERANG,
    HOOKSHOT,
    HEART_CONTAINER_ARTIFACT,
    LENS_OF_TRUTH,
    ANCIENT_CORE,
    GUARDIAN_PARTS,
    SACRED_PROTECTION,
    ZORAS_DOMAIN,
    TWILIGHT_REALM,
    GORON_STRENGTH,
    KOKIRI_FOREST,
    HYLIA_BLESSING,
    ANCIENT_TECHNOLOGY,
    SPIRIT_TRACKS,
    HYRULE_CASTLE,
    DEATH_MOUNTAIN,
    ZORAS_DOMAIN_LAND,
    LOST_WOODS,
    GERUDO_DESERT,
    TEMPLE_OF_TIME,
    KAKARIKO_VILLAGE,
    LAKE_HYLIA,
    LON_LON_RANCH,
    GREAT_PLATEAU,
    AKKALA_CITADEL,
    FARON_WOODS,
    ELDIN_VOLCANO,
    LANAYRU_WETLANDS,
    LURELIN_VILLAGE,
    SKYLOFT,
    SHADOW_TEMPLE,
    FIRE_TEMPLE,
    WATER_TEMPLE,
    FOREST_TEMPLE,
    SPIRIT_TEMPLE,
    PLAINS_LOZ,
    ISLAND_LOZ,
    SWAMP_LOZ,
    MOUNTAIN_LOZ,
    FOREST_LOZ,
    FAIRY_COMPANION,
    HYRULE_SOLDIER,
    LIGHT_SAGE,
    SACRED_KNIGHT,
    ZORA_GUARD,
    DEEP_SEA_ZORA,
    WISDOM_FAIRY,
    RIVER_GUARDIAN,
    SHADOW_LINK,
    DARK_INTERLOPERS,
    TWILIGHT_MESSENGER,
    CURSED_BOKOBLIN,
    FIRE_TEMPLE_GORON,
    BOKOBLIN_HORDE,
    VOLCANIC_KEESE,
    TALUS,
    FOREST_GUARDIAN,
    DEKU_TREE_SPROUT,
    WILD_HORSE,
    RITO_ELDER,
    MASTER_KOHGA,
    GHIRAHIM_DEMON_LORD,
    DEMISE_DEMON_KING,
    KING_RHOAM,
    KASS_RITO_BARD,
    BEEDLE_TRAVELING_MERCHANT,
    PURAH_SHEIKAH_RESEARCHER,
    ROBBIE_ANCIENT_TECH
]
