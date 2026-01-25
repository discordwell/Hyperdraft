"""
Naruto: Shinobi Clash Card Implementations

~250 cards featuring ninja from the Hidden Leaf and beyond.
Mechanics: Chakra, Jutsu, Jinchuriki
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
from src.engine.abilities import (
    TriggeredAbility, StaticAbility,
    ETBTrigger, DeathTrigger, AttackTrigger, DealsDamageTrigger,
    UpkeepTrigger, SpellCastTrigger, LifeGainTrigger,
    GainLife, DrawCards, CreateToken, Scry,
    PTBoost, KeywordGrant,
    OtherCreaturesYouControlFilter, CreaturesYouControlFilter,
    CreaturesWithSubtypeFilter,
)


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


def make_artifact(name: str, mana_cost: str, text: str, subtypes: set = None, supertypes: set = None, setup_interceptors=None):
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
# NARUTO KEYWORD MECHANICS
# =============================================================================

def make_chakra_ability(source_obj: GameObject, life_cost: int, effect_fn: Callable[[Event, GameState], list[Event]]) -> Interceptor:
    """
    Chakra N - Pay N life to activate this ability.
    """
    def chakra_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.ACTIVATE:
            return False
        return (event.payload.get('source') == source_obj.id and
                event.payload.get('ability') == 'chakra')

    def chakra_handler(event: Event, state: GameState) -> InterceptorResult:
        life_payment = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -life_cost},
            source=source_obj.id
        )
        effect_events = effect_fn(event, state)
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_payment] + effect_events
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=chakra_filter,
        handler=chakra_handler,
        duration='while_on_battlefield'
    )


def make_jutsu_copy(source_obj: GameObject) -> Interceptor:
    """
    Jutsu - When you cast this spell, you may copy it if you pay 2 life.
    """
    def jutsu_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.CAST and
                event.payload.get('spell_id') == source_obj.id)

    def jutsu_handler(event: Event, state: GameState) -> InterceptorResult:
        copy_event = Event(
            type=EventType.COPY_SPELL,
            payload={'spell_id': source_obj.id, 'controller': source_obj.controller},
            source=source_obj.id
        )
        life_cost = Event(
            type=EventType.LIFE_CHANGE,
            payload={'player': source_obj.controller, 'amount': -2},
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[life_cost, copy_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=jutsu_filter,
        handler=jutsu_handler,
        duration='until_leaves'
    )


def make_jinchuriki_transform(source_obj: GameObject, transformed_power: int, transformed_toughness: int) -> Interceptor:
    """
    Jinchuriki - When this creature is dealt damage, transform it.
    """
    def damage_filter(event: Event, state: GameState) -> bool:
        return (event.type == EventType.DAMAGE and
                event.payload.get('target') == source_obj.id)

    def transform_handler(event: Event, state: GameState) -> InterceptorResult:
        transform_event = Event(
            type=EventType.TRANSFORM,
            payload={
                'object_id': source_obj.id,
                'new_power': transformed_power,
                'new_toughness': transformed_toughness
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[transform_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=damage_filter,
        handler=transform_handler,
        duration='while_on_battlefield'
    )


def make_sage_mode_bonus_interceptors(source_obj: GameObject, power_bonus: int, toughness_bonus: int, threshold: int = 15) -> list[Interceptor]:
    """
    Sage Mode - Gets +X/+Y as long as you have N or more life.
    Returns interceptors directly (for use in setup_interceptors functions).
    """
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    interceptors = []

    if power_bonus != 0:
        def power_filter(event, state, src=source_obj, threshold=threshold):
            if event.type != EventType.QUERY_POWER:
                return False
            if event.payload.get('object_id') != src.id:
                return False
            player = state.players.get(src.controller)
            return player and player.life >= threshold

        def power_handler(event, state, mod=power_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

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
        def toughness_filter(event, state, src=source_obj, threshold=threshold):
            if event.type != EventType.QUERY_TOUGHNESS:
                return False
            if event.payload.get('object_id') != src.id:
                return False
            player = state.players.get(src.controller)
            return player and player.life >= threshold

        def toughness_handler(event, state, mod=toughness_bonus):
            current = event.payload.get('value', 0)
            new_event = event.copy()
            new_event.payload['value'] = current + mod
            return InterceptorResult(
                action=InterceptorAction.TRANSFORM,
                transformed_event=new_event
            )

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


def make_sharingan_copy(source_obj: GameObject) -> Interceptor:
    """
    Sharingan - Whenever an opponent casts an instant or sorcery, you may copy it.
    """
    def sharingan_filter(event: Event, state: GameState) -> bool:
        if event.type != EventType.CAST:
            return False
        caster = event.payload.get('caster')
        if caster == source_obj.controller:
            return False
        spell_types = set(event.payload.get('types', []))
        return CardType.INSTANT in spell_types or CardType.SORCERY in spell_types

    def copy_handler(event: Event, state: GameState) -> InterceptorResult:
        copy_event = Event(
            type=EventType.COPY_SPELL,
            payload={
                'spell_id': event.payload.get('spell_id'),
                'controller': source_obj.controller,
                'new_targets': True
            },
            source=source_obj.id
        )
        return InterceptorResult(
            action=InterceptorAction.REACT,
            new_events=[copy_event]
        )

    return Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.REACT,
        filter=sharingan_filter,
        handler=copy_handler,
        duration='while_on_battlefield'
    )


def make_keyword_grant_interceptors(source_obj: GameObject, keywords: list[str], filter_fn: Callable[[GameObject, GameState], bool]) -> list[Interceptor]:
    """Create interceptors to grant keywords to filtered creatures."""
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    def ability_filter(event, state, src=source_obj, flt=filter_fn):
        if event.type != EventType.QUERY_ABILITIES:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def ability_handler(event, state, kws=keywords):
        new_event = event.copy()
        granted = list(new_event.payload.get('granted', []))
        for kw in kws:
            if kw not in granted:
                granted.append(kw)
        new_event.payload['granted'] = granted
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    return [Interceptor(
        id=new_id(),
        source=source_obj.id,
        controller=source_obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=ability_filter,
        handler=ability_handler,
        duration='while_on_battlefield'
    )]


# =============================================================================
# WHITE CARDS - KONOHA, WILL OF FIRE, PROTECTION
# =============================================================================

# --- Team 7 ---

def naruto_uzumaki_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki transform (set-specific mechanic that needs custom interceptor)"""
    return [make_jinchuriki_transform(obj, 7, 7)]

NARUTO_UZUMAKI = make_creature(
    name="Naruto Uzumaki, Child of Prophecy",
    power=3, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CreateToken(name="Shadow Clone", power=2, toughness=2, colors={"R"}, subtypes={"Ninja", "Clone"})
        )
    ],
    setup_interceptors=naruto_uzumaki_setup
)


def sakura_haruno_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Chakra 2 - target creature gets +3/+3 (set-specific mechanic)"""
    def chakra_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'target_type': 'creature',
            'boost': '+3/+3',
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_chakra_ability(obj, 2, chakra_effect)]

SAKURA_HARUNO = make_creature(
    name="Sakura Haruno, Medical Ninja",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Medic"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(4)
        )
    ],
    setup_interceptors=sakura_haruno_setup
)


def kakashi_hatake_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan copy ability (set-specific mechanic)"""
    return [make_sharingan_copy(obj)]

KAKASHI_HATAKE = make_creature(
    name="Kakashi Hatake, Copy Ninja",
    power=3, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Jonin"},
    supertypes={"Legendary"},
    setup_interceptors=kakashi_hatake_setup
)


# --- Hokages ---

HASHIRAMA_SENJU = make_creature(
    name="Hashirama Senju, First Hokage",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter("Ninja", include_self=False)
        )
    ]
)


TOBIRAMA_SENJU = make_creature(
    name="Tobirama Senju, Second Hokage",
    power=4, toughness=4,
    mana_cost="{2}{W}{U}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=SpellCastTrigger(spell_types={CardType.INSTANT}),
            effect=DrawCards(1)
        )
    ]
)


def hiruzen_sarutobi_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """All Ninjas you control have hexproof (using set helper for custom filter)"""
    def ninja_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        return 'Ninja' in target.characteristics.subtypes
    return make_keyword_grant_interceptors(obj, ['hexproof'], ninja_filter)

HIRUZEN_SARUTOBI = make_creature(
    name="Hiruzen Sarutobi, Third Hokage",
    power=3, toughness=5,
    mana_cost="{2}{W}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Hokage"},
    supertypes={"Legendary"},
    setup_interceptors=hiruzen_sarutobi_setup
)


MINATO_NAMIKAZE = make_creature(
    name="Minato Namikaze, Fourth Hokage",
    power=4, toughness=3,
    mana_cost="{2}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Hokage", "Uzumaki"},
    supertypes={"Legendary"},
    text="Flash, haste. When Minato enters, exile target creature. Return it to the battlefield under its owner's control at the beginning of the next end step."
)


TSUNADE = make_creature(
    name="Tsunade, Fifth Hokage",
    power=4, toughness=4,
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hokage", "Senju", "Medic"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=LifeGainTrigger(),
            effect=CreateToken(name="+1/+1 Counter", power=0, toughness=0)  # Placeholder - counters need different handling
        )
    ],
    text="Lifelink. Whenever you gain life, put a +1/+1 counter on target creature you control."
)


# --- Konoha Ninjas ---

def might_guy_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Chakra 8 - gets +8/+0 until end of turn (set-specific mechanic)"""
    def chakra_effect(event: Event, state: GameState) -> list[Event]:
        return [Event(type=EventType.COUNTER_ADDED, payload={
            'object_id': obj.id,
            'boost': '+8/+0',
            'duration': 'end_of_turn'
        }, source=obj.id)]
    return [make_chakra_ability(obj, 8, chakra_effect)]

MIGHT_GUY = make_creature(
    name="Might Guy, Taijutsu Master",
    power=5, toughness=4,
    mana_cost="{3}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja", "Jonin"},
    supertypes={"Legendary"},
    setup_interceptors=might_guy_setup
)


ROCK_LEE = make_creature(
    name="Rock Lee, Handsome Devil",
    power=4, toughness=3,
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="Haste. Rock Lee can't be blocked by creatures with power 2 or less. Chakra 4 - Pay 4 life: Rock Lee gains double strike until end of turn."
)


NEJI_HYUGA = make_creature(
    name="Neji Hyuga, Prodigy",
    power=3, toughness=3,
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=CreateToken(name="Tap Effect", power=0, toughness=0)  # Placeholder - tap effects need different handling
        )
    ],
    text="First strike. Whenever Neji deals combat damage to a player, tap target creature that player controls. It doesn't untap during its controller's next untap step."
)


HINATA_HYUGA = make_creature(
    name="Hinata Hyuga, Gentle Fist",
    power=2, toughness=3,
    mana_cost="{1}{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Hyuga", include_self=False)
        )
    ]
)


SHIKAMARU_NARA = make_creature(
    name="Shikamaru Nara, Shadow Tactician",
    power=2, toughness=2,
    mana_cost="{1}{W}{B}",
    colors={Color.WHITE, Color.BLACK},
    subtypes={"Human", "Ninja", "Nara"},
    supertypes={"Legendary"},
    text="When Shikamaru enters, tap target creature. It doesn't untap during its controller's next untap step."
)


CHOJI_AKIMICHI = make_creature(
    name="Choji Akimichi, Expansion Jutsu",
    power=3, toughness=5,
    mana_cost="{2}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Human", "Ninja", "Akimichi"},
    supertypes={"Legendary"},
    text="Trample. Chakra 3 - Pay 3 life: Choji gets +4/+4 until end of turn."
)


INO_YAMANAKA = make_creature(
    name="Ino Yamanaka, Mind Transfer",
    power=2, toughness=2,
    mana_cost="{1}{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    subtypes={"Human", "Ninja", "Yamanaka"},
    supertypes={"Legendary"},
    text="{T}: Gain control of target creature until end of turn. Untap it. It gains haste."
)


TENTEN = make_creature(
    name="Tenten, Weapons Master",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="First strike. Equipment spells you cast cost {1} less to cast. Equip costs you pay cost {1} less."
)


# --- Regular Konoha Ninjas ---

KONOHA_GENIN = make_creature(
    name="Konoha Genin",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(2)
        )
    ]
)


KONOHA_CHUNIN = make_creature(
    name="Konoha Chunin",
    power=2, toughness=3,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    abilities=[
        StaticAbility(
            effect=PTBoost(0, 1),
            filter=CreaturesWithSubtypeFilter("Ninja", include_self=False)
        )
    ]
)


KONOHA_JONIN = make_creature(
    name="Konoha Jonin",
    power=3, toughness=3,
    mana_cost="{3}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Jonin"},
    text="First strike, vigilance."
)


ANBU_BLACK_OPS = make_creature(
    name="ANBU Black Ops",
    power=3, toughness=2,
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "ANBU"},
    text="Flash, protection from black."
)


MEDICAL_NINJA = make_creature(
    name="Medical Ninja",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Medic"},
    text="{T}: Prevent the next 3 damage that would be dealt to target creature this turn."
)


HYUGA_BRANCH_MEMBER = make_creature(
    name="Hyuga Branch Member",
    power=2, toughness=2,
    mana_cost="{W}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Hyuga"},
    text="First strike. {W}: Hyuga Branch Member gains lifelink until end of turn."
)


NARA_SHADOW_USER = make_creature(
    name="Nara Shadow User",
    power=1, toughness=3,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja", "Nara"},
    text="{T}: Tap target creature with power less than or equal to Nara Shadow User's power."
)


WILL_OF_FIRE_BEARER = make_creature(
    name="Will of Fire Bearer",
    power=2, toughness=2,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=GainLife(3)
        )
    ],
    text="When Will of Fire Bearer dies, you gain 3 life and scry 1."
)


KONOHA_ACADEMY_STUDENT = make_creature(
    name="Konoha Academy Student",
    power=1, toughness=1,
    mana_cost="{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Ninja", power=1, toughness=1, colors={"W"}, subtypes={"Ninja"})
        )
    ]
)


BARRIER_TEAM_NINJA = make_creature(
    name="Barrier Team Ninja",
    power=0, toughness=4,
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    subtypes={"Human", "Ninja"},
    text="Defender. Creatures you control have hexproof as long as Barrier Team Ninja is untapped."
)


# --- White Instants ---

SUBSTITUTION_JUTSU = make_instant(
    name="Substitution Jutsu",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Target creature you control gains hexproof and indestructible until end of turn."
)


WILL_OF_FIRE = make_instant(
    name="Will of Fire",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Creatures you control get +1/+1 until end of turn. You gain 1 life for each creature you control."
)


GENTLE_FIST = make_instant(
    name="Gentle Fist",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Tap target creature. It doesn't untap during its controller's next untap step. If you control a Hyuga, draw a card."
)


EIGHT_TRIGRAMS_PALM = make_instant(
    name="Eight Trigrams Palm",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    text="Tap all creatures target opponent controls. Those creatures don't untap during their controller's next untap step."
)


HEALING_JUTSU = make_instant(
    name="Healing Jutsu",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="You gain 5 life. If you control a Medic, you gain 8 life instead."
)


KONOHA_SENBON = make_instant(
    name="Konoha Senbon",
    mana_cost="{W}",
    colors={Color.WHITE},
    text="Konoha Senbon deals 1 damage to target attacking or blocking creature. You gain 1 life."
)


PROTECTION_BARRIER = make_instant(
    name="Protection Barrier",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Prevent all damage that would be dealt to you and creatures you control this turn."
)


VILLAGE_DEFENSE = make_instant(
    name="Village Defense",
    mana_cost="{1}{W}",
    colors={Color.WHITE},
    text="Create two 1/1 white Ninja creature tokens with vigilance."
)


# --- White Sorceries ---

KONOHA_REINFORCEMENTS = make_sorcery(
    name="Konoha Reinforcements",
    mana_cost="{3}{W}{W}",
    colors={Color.WHITE},
    text="Create four 1/1 white Human Ninja creature tokens. You gain 1 life for each Ninja you control."
)


HIDDEN_LEAF_DECREE = make_sorcery(
    name="Hidden Leaf Decree",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Exile target creature with power 4 or greater. Its controller gains life equal to its toughness."
)


HOKAGE_MONUMENT = make_sorcery(
    name="Hokage Monument",
    mana_cost="{4}{W}{W}",
    colors={Color.WHITE},
    text="Return all Ninja creature cards from your graveyard to the battlefield."
)


# --- White Enchantments ---

WILL_OF_FIRE_ENCHANTMENT = make_enchantment(
    name="The Will of Fire",
    mana_cost="{2}{W}{W}",
    colors={Color.WHITE},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Ninja")
        )
    ],
    text="Ninja creatures you control get +1/+1. At the beginning of your upkeep, if you control four or more Ninjas, create a 2/2 white Ninja creature token."
)


KONOHA_ALLIANCE = make_enchantment(
    name="Konoha Alliance",
    mana_cost="{2}{W}",
    colors={Color.WHITE},
    text="Creatures your opponents control can't attack you unless their controller pays {2} for each creature attacking you."
)


# =============================================================================
# BLUE CARDS - GENJUTSU, WATER JUTSU, STRATEGY
# =============================================================================

# --- Legendary Ninjas ---

def sasuke_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan copy ability (set-specific mechanic)"""
    return [make_sharingan_copy(obj)]

SASUKE_UCHIHA = make_creature(
    name="Sasuke Uchiha, Avenger",
    power=4, toughness=3,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    setup_interceptors=sasuke_uchiha_setup
)


ZABUZA_MOMOCHI = make_creature(
    name="Zabuza Momochi, Demon of the Mist",
    power=5, toughness=4,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Rogue"},
    supertypes={"Legendary"},
    text="Menace. Whenever Zabuza attacks, prevent all damage that would be dealt to you until end of turn."
)


HAKU = make_creature(
    name="Haku, Ice Mirror",
    power=2, toughness=3,
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    supertypes={"Legendary"},
    text="When Haku dies, return target creature to its owner's hand. {U}: Haku gains hexproof until end of turn."
)


KABUTO_YAKUSHI = make_creature(
    name="Kabuto Yakushi, Spy",
    power=2, toughness=3,
    mana_cost="{1}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Medic"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=SpellCastTrigger(spell_types={CardType.INSTANT, CardType.SORCERY}),
            effect=Scry(1)
        )
    ]
)


SHINO_ABURAME = make_creature(
    name="Shino Aburame, Insect Master",
    power=2, toughness=3,
    mana_cost="{1}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Human", "Ninja", "Aburame"},
    supertypes={"Legendary"},
    text="Whenever an Insect creature enters under your control, draw a card. {T}: Create a 1/1 green Insect creature token with flying."
)


KIBA_INUZUKA = make_creature(
    name="Kiba Inuzuka, Fang over Fang",
    power=3, toughness=2,
    mana_cost="{1}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Ninja", "Inuzuka"},
    supertypes={"Legendary"},
    text="Haste. When Kiba enters, create Akamaru, a legendary 2/2 red Dog creature token with haste."
)


# --- Regular Blue Ninjas ---

MIST_VILLAGE_NINJA = make_creature(
    name="Mist Village Ninja",
    power=2, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=Scry(2)
        )
    ]
)


GENJUTSU_SPECIALIST = make_creature(
    name="Genjutsu Specialist",
    power=1, toughness=3,
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="{T}: Target creature doesn't untap during its controller's next untap step."
)


WATER_CLONE = make_creature(
    name="Water Clone",
    power=2, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Ninja", "Clone"},
    text="When Water Clone enters, it becomes a copy of target creature you control except it's a Clone in addition to its other types."
)


ABURAME_TRACKER = make_creature(
    name="Aburame Tracker",
    power=1, toughness=2,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja", "Aburame"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Insect", power=1, toughness=1, colors={"G"}, subtypes={"Insect"}, keywords=["flying"])
        )
    ]
)


INTELLIGENCE_GATHERER = make_creature(
    name="Intelligence Gatherer",
    power=1, toughness=1,
    mana_cost="{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=DrawCards(1)
        )
    ]
)


SOUND_VILLAGE_SPY = make_creature(
    name="Sound Village Spy",
    power=2, toughness=1,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    text="Flash. When Sound Village Spy enters, look at target opponent's hand."
)


MIST_SWORDSMAN = make_creature(
    name="Mist Swordsman",
    power=3, toughness=2,
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja", "Warrior"},
    text="First strike. Mist Swordsman can't be blocked as long as defending player controls an Island."
)


SENSOR_NINJA = make_creature(
    name="Sensor Ninja",
    power=1, toughness=3,
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    subtypes={"Human", "Ninja"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=Scry(1)
        )
    ]
)


# --- Blue Instants ---

WATER_PRISON_JUTSU = make_instant(
    name="Water Prison Jutsu",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap target creature. It doesn't untap during its controller's next untap step. Draw a card."
)


HIDDEN_MIST_JUTSU = make_instant(
    name="Hidden Mist Jutsu",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Target creature gains hexproof and can't be blocked this turn."
)


WATER_DRAGON_JUTSU = make_instant(
    name="Water Dragon Jutsu",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Jutsu - You may pay 2 life to copy this spell. Return up to two target creatures to their owners' hands."
)


GENJUTSU_RELEASE = make_instant(
    name="Genjutsu: Release",
    mana_cost="{U}",
    colors={Color.BLUE},
    text="Counter target spell unless its controller pays {2}."
)


DEMONIC_ILLUSION = make_instant(
    name="Demonic Illusion",
    mana_cost="{1}{U}{U}",
    colors={Color.BLUE},
    text="Counter target spell. Scry 2."
)


SUBSTITUTION = make_instant(
    name="Substitution",
    mana_cost="{U}{U}",
    colors={Color.BLUE},
    text="Return target creature you control to its owner's hand. Draw two cards."
)


MIND_CONFUSION_JUTSU = make_instant(
    name="Mind Confusion Jutsu",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Target opponent puts the top five cards of their library into their graveyard. If you control a Yamanaka, that player discards a card."
)


WATER_WALL = make_instant(
    name="Water Wall",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Tap all attacking creatures. Draw a card."
)


# --- Blue Sorceries ---

WATER_STYLE_TRAINING = make_sorcery(
    name="Water Style Training",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Draw three cards, then discard a card."
)


CLONE_JUTSU = make_sorcery(
    name="Clone Jutsu",
    mana_cost="{3}{U}{U}",
    colors={Color.BLUE},
    text="Create a token that's a copy of target creature you control."
)


TACTICAL_RETREAT = make_sorcery(
    name="Tactical Retreat",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Return all creatures you control to their owners' hands. Draw a card for each creature returned this way."
)


# --- Blue Enchantments ---

GENJUTSU_WEB = make_enchantment(
    name="Genjutsu Web",
    mana_cost="{2}{U}",
    colors={Color.BLUE},
    text="Whenever a creature enters under an opponent's control, tap it. It doesn't untap during its controller's next untap step."
)


HIDDEN_MIST = make_enchantment(
    name="Hidden Mist",
    mana_cost="{1}{U}",
    colors={Color.BLUE},
    text="Creatures you control have hexproof. Creatures you control can't be blocked except by creatures with flying."
)


# =============================================================================
# BLACK CARDS - AKATSUKI, UCHIHA REVENGE, DARKNESS
# =============================================================================

# --- Akatsuki Leaders ---

def itachi_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan (set-specific mechanic)"""
    return [make_sharingan_copy(obj)]

ITACHI_UCHIHA = make_creature(
    name="Itachi Uchiha, Tragic Genius",
    power=4, toughness=3,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha", "Akatsuki"},
    supertypes={"Legendary"},
    setup_interceptors=itachi_uchiha_setup,
    text="Deathtouch. Sharingan - Copy opponent's instants/sorceries. Whenever Itachi attacks, defending player sacrifices a creature."
)


PAIN = make_creature(
    name="Pain, Six Paths of Destruction",
    power=6, toughness=6,
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="When Pain enters, destroy all other creatures. Almighty Push - {2}{B}: Each opponent loses 3 life."
)


def obito_uchiha_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sharingan (set-specific mechanic)"""
    return [make_sharingan_copy(obj)]

OBITO_UCHIHA = make_creature(
    name="Obito Uchiha, Masked Man",
    power=5, toughness=4,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Uchiha", "Akatsuki"},
    supertypes={"Legendary"},
    setup_interceptors=obito_uchiha_setup,
    text="Obito has indestructible while attacking. Sharingan - Copy opponent's spells. Kamui - {B}: Exile Obito, then return him at end step."
)


MADARA_UCHIHA = make_creature(
    name="Madara Uchiha, Ghost of the Uchiha",
    power=7, toughness=7,
    mana_cost="{5}{B}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    text="This spell can't be countered. Flying, trample. When Madara enters, you get an extra turn after this one."
)


KISAME_HOSHIGAKI = make_creature(
    name="Kisame Hoshigaki, Monster of the Mist",
    power=5, toughness=5,
    mana_cost="{3}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Shark", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Whenever Kisame deals combat damage to a player, that player discards that many cards. {U}: Kisame gets +1/+1 until end of turn."
)


DEIDARA = make_creature(
    name="Deidara, Art is an Explosion",
    power=3, toughness=2,
    mana_cost="{2}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Flying. Whenever Deidara attacks, he deals 2 damage to each creature defending player controls."
)


SASORI = make_creature(
    name="Sasori, Puppet Master",
    power=3, toughness=4,
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="When Sasori enters, create two 2/2 black Puppet artifact creature tokens. Puppets you control have deathtouch."
)


HIDAN = make_creature(
    name="Hidan, Immortal Zealot",
    power=4, toughness=3,
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Indestructible. Whenever Hidan deals damage, you lose that much life. Chakra 3 - Pay 3 life: Target creature gets -3/-3 until end of turn."
)


KAKUZU = make_creature(
    name="Kakuzu, Five Hearts",
    power=5, toughness=5,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="When Kakuzu would die, instead remove a +1/+1 counter from him. Kakuzu enters with four +1/+1 counters."
)


KONAN = make_creature(
    name="Konan, Angel of Ame",
    power=3, toughness=4,
    mana_cost="{2}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    subtypes={"Human", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=CreateToken(name="Paper", power=1, toughness=1, colors={"U"}, subtypes={"Paper"}, keywords=["flying"])
        )
    ],
    text="Flying. At the beginning of your upkeep, create a 1/1 blue Paper creature token with flying. Sacrifice five Papers: Destroy target permanent."
)


ZETSU = make_creature(
    name="Zetsu, White and Black",
    power=2, toughness=4,
    mana_cost="{1}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Plant", "Ninja", "Akatsuki"},
    supertypes={"Legendary"},
    text="Deathtouch. At the beginning of your end step, create a 1/1 black and green Zetsu creature token."
)


# --- Other Black Ninjas ---

OROCHIMARU = make_creature(
    name="Orochimaru, Sannin of Ambition",
    power=4, toughness=4,
    mana_cost="{3}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Human", "Ninja", "Sannin"},
    supertypes={"Legendary"},
    text="Deathtouch. When Orochimaru dies, you may pay 3 life. If you do, return him to your hand. {B}{G}: Put a -1/-1 counter on target creature."
)


def curse_mark_sasuke_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki - transform when damaged (set-specific mechanic)"""
    return [make_jinchuriki_transform(obj, 6, 5)]

CURSE_MARK_SASUKE = make_creature(
    name="Sasuke, Curse Mark Awakened",
    power=4, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    supertypes={"Legendary"},
    setup_interceptors=curse_mark_sasuke_setup
)


SOUND_VILLAGE_JONIN = make_creature(
    name="Sound Village Jonin",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Jonin"},
    text="Menace. When Sound Village Jonin enters, target opponent discards a card."
)


CURSE_MARK_BEARER = make_creature(
    name="Curse Mark Bearer",
    power=2, toughness=2,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="Chakra 2 - Pay 2 life: Curse Mark Bearer gets +2/+2 until end of turn."
)


ANBU_ASSASSIN = make_creature(
    name="ANBU Assassin",
    power=2, toughness=1,
    mana_cost="{B}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "ANBU"},
    text="Deathtouch, menace."
)


UCHIHA_AVENGER = make_creature(
    name="Uchiha Avenger",
    power=3, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Uchiha"},
    text="Whenever another creature you control dies, Uchiha Avenger gets +1/+1 until end of turn."
)


ROGUE_NINJA = make_creature(
    name="Rogue Ninja",
    power=3, toughness=1,
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja", "Rogue"},
    text="Rogue Ninja can't block. When Rogue Ninja dies, each opponent loses 2 life."
)


PUPPET_ASSASSIN = make_creature(
    name="Puppet Assassin",
    power=2, toughness=2,
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    subtypes={"Construct", "Puppet"},
    text="Deathtouch. When Puppet Assassin dies, you may pay {1}{B}. If you do, return it to the battlefield tapped."
)


FORBIDDEN_JUTSU_USER = make_creature(
    name="Forbidden Jutsu User",
    power=1, toughness=1,
    mana_cost="{B}",
    colors={Color.BLACK},
    subtypes={"Human", "Ninja"},
    text="{B}, Sacrifice Forbidden Jutsu User: Target creature gets -2/-2 until end of turn."
)


REANIMATED_SHINOBI = make_creature(
    name="Reanimated Shinobi",
    power=3, toughness=3,
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    subtypes={"Zombie", "Ninja"},
    text="When Reanimated Shinobi enters, you may return target creature card from your graveyard to your hand."
)


# --- Black Instants ---

TSUKUYOMI = make_instant(
    name="Tsukuyomi",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. Its controller loses life equal to that creature's power."
)


AMATERASU = make_instant(
    name="Amaterasu",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Amaterasu deals 5 damage to target creature. That creature can't be regenerated this turn. If it would die, exile it instead."
)


SOUL_EXTRACTION = make_instant(
    name="Soul Extraction",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player sacrifices a creature. You gain life equal to that creature's toughness."
)


CURSE_MARK_ACTIVATION = make_instant(
    name="Curse Mark Activation",
    mana_cost="{B}",
    colors={Color.BLACK},
    text="Target creature you control gets +3/+0 until end of turn. You lose 3 life."
)


DEATH_SEAL = make_instant(
    name="Death Seal",
    mana_cost="{3}{B}",
    colors={Color.BLACK},
    text="Destroy target creature. If that creature was legendary, draw two cards."
)


SHADOW_POSSESSION = make_instant(
    name="Shadow Possession",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Gain control of target creature until end of turn. Untap it. It gains haste."
)


REAPER_DEATH_SEAL = make_instant(
    name="Reaper Death Seal",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    text="Exile target creature. You lose life equal to that creature's mana value."
)


PAINFUL_MEMORIES = make_instant(
    name="Painful Memories",
    mana_cost="{1}{B}",
    colors={Color.BLACK},
    text="Target player discards two cards. You lose 2 life."
)


# --- Black Sorceries ---

EDO_TENSEI = make_sorcery(
    name="Edo Tensei",
    mana_cost="{4}{B}{B}",
    colors={Color.BLACK},
    text="Return up to three target creature cards from your graveyard to the battlefield. They gain indestructible."
)


SHINRA_TENSEI = make_sorcery(
    name="Shinra Tensei",
    mana_cost="{5}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all creatures. Each opponent loses life equal to the number of creatures they controlled that were destroyed this way."
)


UCHIHA_MASSACRE = make_sorcery(
    name="Uchiha Massacre",
    mana_cost="{3}{B}{B}",
    colors={Color.BLACK},
    text="Destroy all non-Uchiha creatures."
)


IZANAGI = make_sorcery(
    name="Izanagi",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Return target permanent card from your graveyard to the battlefield. You lose 4 life."
)


# --- Black Enchantments ---

CURSE_OF_HATRED = make_enchantment(
    name="Curse of Hatred",
    mana_cost="{2}{B}",
    colors={Color.BLACK},
    text="Enchant player. At the beginning of enchanted player's upkeep, they sacrifice a creature. If they can't, they lose 3 life."
)


AKATSUKI_HIDEOUT = make_enchantment(
    name="Akatsuki Hideout",
    mana_cost="{2}{B}{B}",
    colors={Color.BLACK},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Akatsuki")
        )
    ],
    text="Akatsuki creatures you control get +1/+1 and have menace. {2}{B}: Return target Akatsuki creature card from your graveyard to your hand."
)


# =============================================================================
# RED CARDS - FIRE JUTSU, PASSION, NARUTO'S DETERMINATION
# =============================================================================

# --- Legendary Red Characters ---

def naruto_sage_mode_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sage Mode bonus (set-specific mechanic)"""
    return make_sage_mode_bonus_interceptors(obj, 3, 3)

NARUTO_SAGE_MODE = make_creature(
    name="Naruto, Sage of Mount Myoboku",
    power=4, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Uzumaki", "Sage"},
    supertypes={"Legendary"},
    setup_interceptors=naruto_sage_mode_setup
)


def jiraiya_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Sage Mode bonus (set-specific mechanic)"""
    return make_sage_mode_bonus_interceptors(obj, 2, 2)

JIRAIYA = make_creature(
    name="Jiraiya, Toad Sage",
    power=4, toughness=4,
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Sannin", "Sage"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=CreateToken(name="Toad", power=3, toughness=3, colors={"G"}, subtypes={"Toad"})
        )
    ],
    setup_interceptors=jiraiya_setup
)


def killer_bee_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki transform (set-specific mechanic)"""
    return [make_jinchuriki_transform(obj, 8, 8)]

KILLER_BEE = make_creature(
    name="Killer Bee, Eight-Tails Jinchuriki",
    power=4, toughness=4,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Jinchuriki"},
    supertypes={"Legendary"},
    setup_interceptors=killer_bee_setup
)


def gaara_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Jinchuriki transform (set-specific mechanic)"""
    return [make_jinchuriki_transform(obj, 6, 6)]

GAARA = make_creature(
    name="Gaara, One-Tail Jinchuriki",
    power=3, toughness=4,
    mana_cost="{2}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Human", "Ninja", "Jinchuriki", "Kazekage"},
    supertypes={"Legendary"},
    setup_interceptors=gaara_setup
)


A_FOURTH_RAIKAGE = make_creature(
    name="A, Fourth Raikage",
    power=5, toughness=4,
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Raikage"},
    supertypes={"Legendary"},
    text="Haste, first strike. Lightning Armor - A has hexproof as long as it's your turn."
)


MEI_TERUMI = make_creature(
    name="Mei Terumi, Fifth Mizukage",
    power=3, toughness=4,
    mana_cost="{2}{U}{R}",
    colors={Color.BLUE, Color.RED},
    subtypes={"Human", "Ninja", "Mizukage"},
    supertypes={"Legendary"},
    text="When Mei attacks, she deals 2 damage to each creature defending player controls. {U}{R}: Target creature gets -2/-0 until end of turn."
)


# --- Regular Red Ninjas ---

FIRE_STYLE_USER = make_creature(
    name="Fire Style User",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="When Fire Style User enters, it deals 2 damage to any target."
)


CLOUD_VILLAGE_NINJA = make_creature(
    name="Cloud Village Ninja",
    power=3, toughness=2,
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="Haste. First strike."
)


UZUMAKI_DESCENDANT = make_creature(
    name="Uzumaki Descendant",
    power=2, toughness=3,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Uzumaki"},
    text="Uzumaki Descendant has haste as long as you have 10 or less life."
)


SHADOW_CLONE = make_creature(
    name="Shadow Clone",
    power=2, toughness=2,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Ninja", "Clone"},
    text="When Shadow Clone dies, it deals 2 damage to target creature or player."
)


EXPLOSIVE_TAG_NINJA = make_creature(
    name="Explosive Tag Ninja",
    power=2, toughness=1,
    mana_cost="{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="When Explosive Tag Ninja dies, it deals 2 damage to each opponent."
)


SAND_VILLAGE_WARRIOR = make_creature(
    name="Sand Village Warrior",
    power=3, toughness=3,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Warrior"},
    text="Menace."
)


TAIJUTSU_SPECIALIST = make_creature(
    name="Taijutsu Specialist",
    power=4, toughness=2,
    mana_cost="{3}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="Double strike. Taijutsu Specialist can't be blocked by more than one creature."
)


RAGE_FILLED_JINCHURIKI = make_creature(
    name="Rage-Filled Jinchuriki",
    power=3, toughness=3,
    mana_cost="{2}{R}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja", "Jinchuriki"},
    text="Haste, trample. When Rage-Filled Jinchuriki enters, it deals damage equal to its power to target creature."
)


LIGHTNING_BLADE_USER = make_creature(
    name="Lightning Blade User",
    power=3, toughness=2,
    mana_cost="{2}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="First strike. Chakra 2 - Pay 2 life: Lightning Blade User gets +2/+0 until end of turn."
)


BERSERKER_NINJA = make_creature(
    name="Berserker Ninja",
    power=4, toughness=1,
    mana_cost="{1}{R}",
    colors={Color.RED},
    subtypes={"Human", "Ninja"},
    text="Berserker Ninja attacks each combat if able."
)


# --- Red Instants ---

FIRE_BALL_JUTSU = make_instant(
    name="Fire Ball Jutsu",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Fire Ball Jutsu deals 3 damage to any target."
)


RASENGAN = make_instant(
    name="Rasengan",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Jutsu - You may pay 2 life to copy this spell. Rasengan deals 4 damage to target creature or planeswalker."
)


CHIDORI = make_instant(
    name="Chidori",
    mana_cost="{1}{R}{R}",
    colors={Color.RED},
    text="Chidori deals 5 damage to target creature. If that creature dies this turn, draw a card."
)


RASENSHURIKEN = make_instant(
    name="Rasenshuriken",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Jutsu - You may pay 2 life to copy this spell. Rasenshuriken deals 4 damage to target creature and 2 damage to each other creature that player controls."
)


LIGHTNING_BLADE = make_instant(
    name="Lightning Blade",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Lightning Blade deals 4 damage to target creature. That creature can't block this turn."
)


EIGHT_GATES_RELEASE = make_instant(
    name="Eight Gates Release",
    mana_cost="{R}",
    colors={Color.RED},
    text="Target creature gets +4/+0 until end of turn. At end of turn, that creature deals 4 damage to itself."
)


FIRE_DRAGON_JUTSU = make_instant(
    name="Fire Dragon Jutsu",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Fire Dragon Jutsu deals 6 damage divided as you choose among any number of targets."
)


EXPLOSIVE_KUNAI = make_instant(
    name="Explosive Kunai",
    mana_cost="{R}",
    colors={Color.RED},
    text="Explosive Kunai deals 2 damage to target creature or player. If a creature dealt damage this way dies, it deals 2 damage to its controller."
)


LARIAT = make_instant(
    name="Lariat",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Target creature you control deals damage equal to its power to target creature you don't control."
)


WIND_ENHANCED_RASENGAN = make_instant(
    name="Wind-Enhanced Rasengan",
    mana_cost="{3}{R}{G}",
    colors={Color.RED, Color.GREEN},
    text="Wind-Enhanced Rasengan deals 6 damage to target creature. You gain life equal to the damage dealt."
)


# --- Red Sorceries ---

PLANETARY_RASENGAN = make_sorcery(
    name="Planetary Rasengan",
    mana_cost="{4}{R}{R}",
    colors={Color.RED},
    text="Planetary Rasengan deals 5 damage to each creature and each opponent."
)


TAILED_BEAST_BOMB = make_sorcery(
    name="Tailed Beast Bomb",
    mana_cost="{5}{R}{R}",
    colors={Color.RED},
    text="Tailed Beast Bomb deals 10 damage to any target."
)


MULTI_SHADOW_CLONE = make_sorcery(
    name="Multi Shadow Clone Jutsu",
    mana_cost="{3}{R}{R}",
    colors={Color.RED},
    text="Create X 2/2 red Ninja Clone creature tokens, where X is the number of cards in your hand."
)


BURNING_WILL = make_sorcery(
    name="Burning Will",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Creatures you control get +2/+0 and gain haste until end of turn."
)


# --- Red Enchantments ---

NINE_TAILS_CLOAK = make_enchantment(
    name="Nine-Tails Cloak",
    mana_cost="{2}{R}",
    colors={Color.RED},
    text="Enchant creature. Enchanted creature gets +3/+0 and has trample. At the beginning of your upkeep, you lose 2 life."
)


BATTLE_FRENZY = make_enchantment(
    name="Battle Frenzy",
    mana_cost="{1}{R}",
    colors={Color.RED},
    text="Creatures you control have haste. Whenever a creature you control attacks, it gets +1/+0 until end of turn."
)


# =============================================================================
# GREEN CARDS - NATURE CHAKRA, SAGE MODE, SUMMONS
# =============================================================================

# --- Legendary Green Characters ---

NARUTO_KYUBI_MODE = make_creature(
    name="Naruto, Kyubi Chakra Mode",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Human", "Ninja", "Uzumaki", "Jinchuriki"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(1, 1),
            filter=CreaturesWithSubtypeFilter("Ninja", include_self=False)
        )
    ],
    text="Haste, trample. Whenever Naruto attacks, he deals 3 damage to each opponent. Other Ninja creatures you control get +1/+1."
)


HASHIRAMA_WOOD_STYLE = make_creature(
    name="Hashirama, Wood Style Master",
    power=5, toughness=6,
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Hokage", "Senju"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=AttackTrigger(),
            effect=CreateToken(name="Treant", power=3, toughness=3, colors={"G"}, subtypes={"Treant"})
        )
    ]
)


YAMATO = make_creature(
    name="Yamato, Wood Style User",
    power=3, toughness=4,
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "ANBU"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(0, 2),
            filter=OtherCreaturesYouControlFilter()
        )
    ]
)


GAMABUNTA = make_creature(
    name="Gamabunta, Toad Boss",
    power=7, toughness=7,
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Toad", "Summon"},
    supertypes={"Legendary"},
    text="Trample. When Gamabunta enters, it deals 4 damage to each creature your opponents control."
)


MANDA = make_creature(
    name="Manda, Snake Boss",
    power=8, toughness=6,
    mana_cost="{5}{B}{G}",
    colors={Color.BLACK, Color.GREEN},
    subtypes={"Snake", "Summon"},
    supertypes={"Legendary"},
    text="Trample, deathtouch. At the beginning of your end step, sacrifice a creature other than Manda."
)


KATSUYU = make_creature(
    name="Katsuyu, Slug Princess",
    power=4, toughness=8,
    mana_cost="{4}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Slug", "Summon"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(6)
        )
    ]
)


# --- Tailed Beasts ---

KURAMA = make_creature(
    name="Kurama, Nine-Tailed Fox",
    power=9, toughness=9,
    mana_cost="{6}{R}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Fox", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample, haste. Kurama can't be countered. When Kurama enters, it deals 9 damage divided as you choose among any number of targets."
)


SHUKAKU = make_creature(
    name="Shukaku, One-Tail",
    power=6, toughness=6,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Tanuki", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. Shukaku has indestructible as long as you control a Desert. {2}{R}: Shukaku deals 2 damage to target creature or player."
)


MATATABI = make_creature(
    name="Matatabi, Two-Tails",
    power=5, toughness=4,
    mana_cost="{3}{R}{B}",
    colors={Color.RED, Color.BLACK},
    subtypes={"Cat", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Haste. When Matatabi attacks, it deals 2 damage to each creature defending player controls."
)


ISOBU = make_creature(
    name="Isobu, Three-Tails",
    power=4, toughness=7,
    mana_cost="{3}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Turtle", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Hexproof. Isobu can block any number of creatures."
)


SON_GOKU = make_creature(
    name="Son Goku, Four-Tails",
    power=7, toughness=5,
    mana_cost="{4}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Ape", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. Whenever Son Goku deals combat damage to a player, add that much {R} or {G}."
)


KOKUO = make_creature(
    name="Kokuo, Five-Tails",
    power=5, toughness=5,
    mana_cost="{3}{W}{G}",
    colors={Color.WHITE, Color.GREEN},
    subtypes={"Horse", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=GainLife(5)
        )
    ]
)


SAIKEN = make_creature(
    name="Saiken, Six-Tails",
    power=4, toughness=6,
    mana_cost="{3}{U}{G}",
    colors={Color.BLUE, Color.GREEN},
    subtypes={"Slug", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    abilities=[
        TriggeredAbility(
            trigger=DealsDamageTrigger(combat_only=True, to_player=True),
            effect=DrawCards(2)
        )
    ]
)


CHOMEI = make_creature(
    name="Chomei, Seven-Tails",
    power=4, toughness=4,
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    subtypes={"Insect", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 2),
            filter=CreaturesWithSubtypeFilter("Insect", include_self=False)
        )
    ]
)


GYUKI = make_creature(
    name="Gyuki, Eight-Tails",
    power=8, toughness=8,
    mana_cost="{5}{R}{G}",
    colors={Color.RED, Color.GREEN},
    subtypes={"Octopus", "Spirit", "Tailed Beast"},
    supertypes={"Legendary"},
    text="Trample. Gyuki has first strike as long as it's attacking."
)


# --- Regular Green Creatures ---

TOAD_SUMMON = make_creature(
    name="Toad Summon",
    power=3, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Toad", "Summon"},
    text="When Toad Summon enters, you may return target instant or sorcery card from your graveyard to your hand."
)


SNAKE_SUMMON = make_creature(
    name="Snake Summon",
    power=2, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Snake", "Summon"},
    text="Deathtouch."
)


SLUG_SUMMON = make_creature(
    name="Slug Summon",
    power=1, toughness=4,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Slug", "Summon"},
    abilities=[
        TriggeredAbility(
            trigger=ETBTrigger(),
            effect=GainLife(3)
        )
    ]
)


FOREST_OF_DEATH_BEAST = make_creature(
    name="Forest of Death Beast",
    power=5, toughness=5,
    mana_cost="{4}{G}",
    colors={Color.GREEN},
    subtypes={"Beast"},
    text="Trample. Forest of Death Beast gets +2/+2 as long as you control a Forest."
)


NATURE_CHAKRA_USER = make_creature(
    name="Nature Chakra User",
    power=2, toughness=3,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Sage"},
    text="{T}: Add {G}. Sage Mode - If you have 15 or more life, add {G}{G} instead."
)


WOOD_STYLE_CLONE = make_creature(
    name="Wood Style Clone",
    power=2, toughness=3,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Treant", "Ninja", "Clone"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Sapling", power=1, toughness=1, colors={"G"}, subtypes={"Sapling"})
        )
    ]
)


SAGE_APPRENTICE = make_creature(
    name="Sage Apprentice",
    power=2, toughness=2,
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    subtypes={"Human", "Ninja", "Sage"},
    text="Sage Mode - Sage Apprentice gets +1/+1 as long as you have 15 or more life."
)


GIANT_CENTIPEDE = make_creature(
    name="Giant Centipede",
    power=4, toughness=2,
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    text="Menace."
)


ABURAME_INSECT_SWARM = make_creature(
    name="Aburame Insect Swarm",
    power=1, toughness=1,
    mana_cost="{G}",
    colors={Color.GREEN},
    subtypes={"Insect"},
    abilities=[
        TriggeredAbility(
            trigger=DeathTrigger(),
            effect=CreateToken(name="Insect", power=1, toughness=1, colors={"G"}, subtypes={"Insect"}, keywords=["flying"])
        )
    ]
)


FOREST_GUARDIAN = make_creature(
    name="Forest Guardian",
    power=3, toughness=5,
    mana_cost="{3}{G}",
    colors={Color.GREEN},
    subtypes={"Treant"},
    text="Reach. Forest Guardian can block an additional creature each combat."
)


# --- Green Instants ---

SUMMONING_JUTSU = make_instant(
    name="Summoning Jutsu",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Create a 3/3 green Beast creature token with trample."
)


WOOD_STYLE_WALL = make_instant(
    name="Wood Style: Wall",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Prevent all combat damage that would be dealt this turn. Create a 0/4 green Wall creature token with defender."
)


NATURE_ENERGY = make_instant(
    name="Nature Energy",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +3/+3 until end of turn. If you have 15 or more life, that creature also gains trample."
)


FROG_KUMITE = make_instant(
    name="Frog Kumite",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="Target creature you control fights target creature you don't control. You gain life equal to the damage dealt."
)


FOREST_BINDING = make_instant(
    name="Forest Binding",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Tap all creatures target opponent controls. Those creatures don't untap during their controller's next untap step."
)


REJUVENATION_JUTSU = make_instant(
    name="Rejuvenation Jutsu",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="You gain 6 life. If you control a Sage, draw a card."
)


GIANT_GROWTH_JUTSU = make_instant(
    name="Giant Growth Jutsu",
    mana_cost="{G}",
    colors={Color.GREEN},
    text="Target creature gets +4/+4 until end of turn."
)


SAGE_ART_AWAKENING = make_instant(
    name="Sage Art: Awakening",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Target creature you control gets +3/+3 and gains trample until end of turn. If you have 15 or more life, put two +1/+1 counters on it instead."
)


# --- Green Sorceries ---

MASS_SUMMONING = make_sorcery(
    name="Mass Summoning",
    mana_cost="{4}{G}{G}",
    colors={Color.GREEN},
    text="Create three 3/3 green Beast creature tokens with trample."
)


WOOD_STYLE_DEEP_FOREST = make_sorcery(
    name="Wood Style: Deep Forest",
    mana_cost="{5}{G}{G}",
    colors={Color.GREEN},
    text="Create a 10/10 green Treant creature token with trample and vigilance."
)


SAGE_TRAINING = make_sorcery(
    name="Sage Training",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Search your library for a creature card with mana value 3 or less, reveal it, and put it into your hand. You gain 3 life. Shuffle."
)


NATURAL_REBIRTH = make_sorcery(
    name="Natural Rebirth",
    mana_cost="{3}{G}{G}",
    colors={Color.GREEN},
    text="Return all creature cards from your graveyard to your hand. You gain 2 life for each card returned this way."
)


# --- Green Enchantments ---

SAGE_MODE_ENCHANTMENT = make_enchantment(
    name="Sage Mode",
    mana_cost="{2}{G}",
    colors={Color.GREEN},
    text="Creatures you control get +1/+1 for each enchantment you control. You gain 1 life at the beginning of your upkeep."
)


FOREST_OF_DEATH = make_enchantment(
    name="Forest of Death",
    mana_cost="{2}{G}{G}",
    colors={Color.GREEN},
    text="Creatures you control have trample. Whenever a creature you control deals combat damage to a player, put a +1/+1 counter on it."
)


NATURE_CHAKRA_FIELD = make_enchantment(
    name="Nature Chakra Field",
    mana_cost="{1}{G}",
    colors={Color.GREEN},
    text="At the beginning of your upkeep, if you have 15 or more life, create a 1/1 green Sapling creature token."
)


# =============================================================================
# ARTIFACTS - WEAPONS, SCROLLS, SHARINGAN
# =============================================================================

KUNAI = make_equipment(
    name="Kunai",
    mana_cost="{1}",
    text="Equipped creature gets +1/+0 and has first strike.",
    equip_cost="{1}"
)


SHURIKEN = make_equipment(
    name="Shuriken",
    mana_cost="{1}",
    text="Equipped creature gets +1/+1. {T}, Unattach Shuriken: It deals 1 damage to any target.",
    equip_cost="{2}"
)


SAMEHADA = make_equipment(
    name="Samehada, Shark Skin",
    mana_cost="{3}",
    text="Equipped creature gets +3/+2. Whenever equipped creature deals combat damage to a player, you gain that much life.",
    equip_cost="{3}",
    supertypes={"Legendary"}
)


EXECUTIONERS_BLADE = make_equipment(
    name="Executioner's Blade",
    mana_cost="{2}",
    text="Equipped creature gets +3/+0. Whenever equipped creature destroys a creature, put a +1/+1 counter on it.",
    equip_cost="{2}",
    supertypes={"Legendary"}
)


SCROLL_OF_SEALING = make_artifact(
    name="Scroll of Sealing",
    mana_cost="{2}",
    text="{2}, {T}, Sacrifice Scroll of Sealing: Exile target creature."
)


CHAKRA_PILLS = make_artifact(
    name="Chakra Pills",
    mana_cost="{1}",
    text="{T}, Sacrifice Chakra Pills: Target creature gets +3/+3 until end of turn. You lose 3 life at end of turn."
)


FORBIDDEN_SCROLL = make_artifact(
    name="Forbidden Scroll",
    mana_cost="{3}",
    text="{T}: Draw a card. You lose 2 life.",
    supertypes={"Legendary"}
)


HEADBAND_OF_THE_LEAF = make_equipment(
    name="Headband of the Leaf",
    mana_cost="{1}",
    text="Equipped creature gets +0/+1 and is a Ninja in addition to its other types. Equipped creature has vigilance.",
    equip_cost="{1}"
)


SHARINGAN_CONTACT = make_artifact(
    name="Sharingan Contact",
    mana_cost="{2}",
    text="{T}: Copy target instant or sorcery spell. You may choose new targets for the copy. Activate only if you control an Uchiha.",
    supertypes={"Legendary"}
)


RINNEGAN_EYE = make_artifact(
    name="Rinnegan Eye",
    mana_cost="{4}",
    text="{T}: Choose one - Return target creature to its owner's hand; or target creature gains indestructible until end of turn; or you gain 4 life.",
    supertypes={"Legendary"}
)


BYAKUGAN_EYE = make_artifact(
    name="Byakugan Eye",
    mana_cost="{2}",
    text="{T}: Look at target opponent's hand. If you control a Hyuga, you may tap target creature.",
    supertypes={"Legendary"}
)


PUPPET_CORE = make_artifact(
    name="Puppet Core",
    mana_cost="{2}",
    text="{3}, {T}: Create a 2/2 black Puppet artifact creature token with deathtouch."
)


EXPLOSIVE_TAG = make_artifact(
    name="Explosive Tag",
    mana_cost="{1}",
    text="{1}, {T}, Sacrifice Explosive Tag: It deals 2 damage to any target."
)


SMOKE_BOMB = make_artifact(
    name="Smoke Bomb",
    mana_cost="{1}",
    text="{T}, Sacrifice Smoke Bomb: Target creature you control gains hexproof until end of turn and can't be blocked this turn."
)


SUMMONING_CONTRACT = make_artifact(
    name="Summoning Contract",
    mana_cost="{3}",
    text="{3}, {T}: Create a 3/3 green Beast creature token with trample."
)


# =============================================================================
# LANDS
# =============================================================================

HIDDEN_LEAF_VILLAGE = make_land(
    name="Hidden Leaf Village",
    text="{T}: Add {C}. {T}: Add {W} or {R}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_MIST_VILLAGE = make_land(
    name="Hidden Mist Village",
    text="{T}: Add {C}. {T}: Add {U} or {B}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_SAND_VILLAGE = make_land(
    name="Hidden Sand Village",
    text="{T}: Add {C}. {T}: Add {R} or {G}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_CLOUD_VILLAGE = make_land(
    name="Hidden Cloud Village",
    text="{T}: Add {C}. {T}: Add {U} or {R}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


HIDDEN_STONE_VILLAGE = make_land(
    name="Hidden Stone Village",
    text="{T}: Add {C}. {T}: Add {R} or {B}. Activate only if you control a Ninja.",
    supertypes={"Legendary"}
)


VALLEY_OF_THE_END = make_land(
    name="Valley of the End",
    text="{T}: Add {C}. {2}, {T}: Target creature you control fights target creature you don't control.",
    supertypes={"Legendary"}
)


AKATSUKI_HIDEOUT_LAND = make_land(
    name="Akatsuki Hideout",
    text="{T}: Add {B}. Akatsuki creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


FOREST_OF_DEATH_LAND = make_land(
    name="Forest of Death",
    text="{T}: Add {G}. {2}{G}, {T}: Create a 1/1 green Insect creature token."
)


MOUNT_MYOBOKU = make_land(
    name="Mount Myoboku",
    text="{T}: Add {G}. {T}: Add {R} or {G}. Activate only if you control a Toad or Sage.",
    supertypes={"Legendary"}
)


RYUCHI_CAVE = make_land(
    name="Ryuchi Cave",
    text="{T}: Add {B}. {T}: Add {B} or {G}. Activate only if you control a Snake.",
    supertypes={"Legendary"}
)


SHIKKOTSU_FOREST = make_land(
    name="Shikkotsu Forest",
    text="{T}: Add {W}. {T}: Add {W} or {G}. Activate only if you control a Slug.",
    supertypes={"Legendary"}
)


UCHIHA_COMPOUND = make_land(
    name="Uchiha Compound",
    text="{T}: Add {B} or {R}. Uchiha creatures you control get +1/+0.",
    supertypes={"Legendary"}
)


HYUGA_COMPOUND = make_land(
    name="Hyuga Compound",
    text="{T}: Add {W}. Hyuga creatures you control get +0/+1.",
    supertypes={"Legendary"}
)


TRAINING_GROUND = make_land(
    name="Training Ground",
    text="{T}: Add {C}. {1}, {T}: Target Ninja creature you control gets +1/+1 until end of turn."
)


CHUNIN_EXAM_ARENA = make_land(
    name="Chunin Exam Arena",
    text="{T}: Add {C}. {3}, {T}: Two target creatures you control fight each other. The creature that survives gets a +1/+1 counter."
)


HOKAGE_MONUMENT_LAND = make_land(
    name="Hokage Rock",
    text="{T}: Add {W}. {W}, {T}: Target Ninja creature you control gains vigilance until end of turn."
)


# =============================================================================
# MULTICOLOR CARDS
# =============================================================================

# --- Gold Cards ---

def team_7_formation_setup(obj: GameObject, state: GameState) -> list[Interceptor]:
    """Custom filter for Naruto, Sasuke, and Sakura (set-specific)"""
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id
    )

    def team7_filter(target: GameObject, state: GameState) -> bool:
        if target.controller != obj.controller:
            return False
        if target.zone != ZoneType.BATTLEFIELD:
            return False
        name = target.characteristics.name
        return 'Naruto' in name or 'Sasuke' in name or 'Sakura' in name

    interceptors = []

    def power_filter(event, state, src=obj, flt=team7_filter):
        if event.type != EventType.QUERY_POWER:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def power_handler(event, state):
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=power_filter,
        handler=power_handler,
        duration='while_on_battlefield'
    ))

    def toughness_filter(event, state, src=obj, flt=team7_filter):
        if event.type != EventType.QUERY_TOUGHNESS:
            return False
        target_id = event.payload.get('object_id')
        target = state.objects.get(target_id)
        if not target:
            return False
        return flt(target, state)

    def toughness_handler(event, state):
        current = event.payload.get('value', 0)
        new_event = event.copy()
        new_event.payload['value'] = current + 1
        return InterceptorResult(
            action=InterceptorAction.TRANSFORM,
            transformed_event=new_event
        )

    interceptors.append(Interceptor(
        id=new_id(),
        source=obj.id,
        controller=obj.controller,
        priority=InterceptorPriority.QUERY,
        filter=toughness_filter,
        handler=toughness_handler,
        duration='while_on_battlefield'
    ))

    return interceptors

TEAM_7_FORMATION = make_enchantment(
    name="Team 7 Formation",
    mana_cost="{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    setup_interceptors=team_7_formation_setup
)


NEW_GENERATION = make_sorcery(
    name="New Generation",
    mana_cost="{2}{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Create three 2/2 white and red Ninja creature tokens. They gain haste until end of turn."
)


BONDS_OF_FRIENDSHIP = make_instant(
    name="Bonds of Friendship",
    mana_cost="{W}{R}",
    colors={Color.WHITE, Color.RED},
    text="Target creature you control gets +3/+3 and gains indestructible until end of turn. If you control a creature named Naruto and a creature named Sasuke, draw two cards."
)


SHINOBI_WAR = make_sorcery(
    name="Shinobi War",
    mana_cost="{3}{B}{R}",
    colors={Color.BLACK, Color.RED},
    text="Each player sacrifices two creatures. Then Shinobi War deals 3 damage to each player."
)


ALLIED_SHINOBI_FORCES = make_enchantment(
    name="Allied Shinobi Forces",
    mana_cost="{2}{W}{U}{R}",
    colors={Color.WHITE, Color.BLUE, Color.RED},
    abilities=[
        StaticAbility(
            effect=PTBoost(2, 1),
            filter=CreaturesWithSubtypeFilter("Ninja")
        ),
        TriggeredAbility(
            trigger=UpkeepTrigger(),
            effect=CreateToken(name="Ninja", power=1, toughness=1, colors={"W"}, subtypes={"Ninja"})
        )
    ]
)


SANNIN_SHOWDOWN = make_sorcery(
    name="Sannin Showdown",
    mana_cost="{3}{W}{B}{G}",
    colors={Color.WHITE, Color.BLACK, Color.GREEN},
    text="Create a 4/4 green Toad token, a 4/4 black Snake token, and a 4/4 white Slug token."
)


FINAL_VALLEY_BATTLE = make_sorcery(
    name="Final Valley Battle",
    mana_cost="{4}{W}{B}{R}",
    colors={Color.WHITE, Color.BLACK, Color.RED},
    text="Destroy all creatures except for two target creatures. Those creatures fight each other."
)


INFINITE_TSUKUYOMI = make_sorcery(
    name="Infinite Tsukuyomi",
    mana_cost="{6}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Tap all creatures your opponents control. They don't untap during their controllers' next untap steps. You draw cards equal to the number of creatures tapped this way."
)


TALK_NO_JUTSU = make_instant(
    name="Talk no Jutsu",
    mana_cost="{W}{U}",
    colors={Color.WHITE, Color.BLUE},
    text="Gain control of target creature until end of turn. Untap it. It can't attack this turn. You gain 3 life."
)


SUSANOO = make_enchantment(
    name="Susanoo",
    mana_cost="{4}{U}{B}",
    colors={Color.BLUE, Color.BLACK},
    text="Enchant creature you control. Enchanted creature gets +5/+5 and has flying and indestructible."
)


# =============================================================================
# EXPORT DICTIONARY
# =============================================================================

NARUTO_CARDS = {
    # WHITE - KONOHA, WILL OF FIRE
    "Naruto Uzumaki, Child of Prophecy": NARUTO_UZUMAKI,
    "Sakura Haruno, Medical Ninja": SAKURA_HARUNO,
    "Kakashi Hatake, Copy Ninja": KAKASHI_HATAKE,
    "Hashirama Senju, First Hokage": HASHIRAMA_SENJU,
    "Tobirama Senju, Second Hokage": TOBIRAMA_SENJU,
    "Hiruzen Sarutobi, Third Hokage": HIRUZEN_SARUTOBI,
    "Minato Namikaze, Fourth Hokage": MINATO_NAMIKAZE,
    "Tsunade, Fifth Hokage": TSUNADE,
    "Might Guy, Taijutsu Master": MIGHT_GUY,
    "Rock Lee, Handsome Devil": ROCK_LEE,
    "Neji Hyuga, Prodigy": NEJI_HYUGA,
    "Hinata Hyuga, Gentle Fist": HINATA_HYUGA,
    "Shikamaru Nara, Shadow Tactician": SHIKAMARU_NARA,
    "Choji Akimichi, Expansion Jutsu": CHOJI_AKIMICHI,
    "Ino Yamanaka, Mind Transfer": INO_YAMANAKA,
    "Tenten, Weapons Master": TENTEN,
    "Konoha Genin": KONOHA_GENIN,
    "Konoha Chunin": KONOHA_CHUNIN,
    "Konoha Jonin": KONOHA_JONIN,
    "ANBU Black Ops": ANBU_BLACK_OPS,
    "Medical Ninja": MEDICAL_NINJA,
    "Hyuga Branch Member": HYUGA_BRANCH_MEMBER,
    "Nara Shadow User": NARA_SHADOW_USER,
    "Will of Fire Bearer": WILL_OF_FIRE_BEARER,
    "Konoha Academy Student": KONOHA_ACADEMY_STUDENT,
    "Barrier Team Ninja": BARRIER_TEAM_NINJA,
    "Substitution Jutsu": SUBSTITUTION_JUTSU,
    "Will of Fire": WILL_OF_FIRE,
    "Gentle Fist": GENTLE_FIST,
    "Eight Trigrams Palm": EIGHT_TRIGRAMS_PALM,
    "Healing Jutsu": HEALING_JUTSU,
    "Konoha Senbon": KONOHA_SENBON,
    "Protection Barrier": PROTECTION_BARRIER,
    "Village Defense": VILLAGE_DEFENSE,
    "Konoha Reinforcements": KONOHA_REINFORCEMENTS,
    "Hidden Leaf Decree": HIDDEN_LEAF_DECREE,
    "Hokage Monument": HOKAGE_MONUMENT,
    "The Will of Fire": WILL_OF_FIRE_ENCHANTMENT,
    "Konoha Alliance": KONOHA_ALLIANCE,

    # BLUE - GENJUTSU, WATER, STRATEGY
    "Sasuke Uchiha, Avenger": SASUKE_UCHIHA,
    "Zabuza Momochi, Demon of the Mist": ZABUZA_MOMOCHI,
    "Haku, Ice Mirror": HAKU,
    "Kabuto Yakushi, Spy": KABUTO_YAKUSHI,
    "Shino Aburame, Insect Master": SHINO_ABURAME,
    "Kiba Inuzuka, Fang over Fang": KIBA_INUZUKA,
    "Mist Village Ninja": MIST_VILLAGE_NINJA,
    "Genjutsu Specialist": GENJUTSU_SPECIALIST,
    "Water Clone": WATER_CLONE,
    "Aburame Tracker": ABURAME_TRACKER,
    "Intelligence Gatherer": INTELLIGENCE_GATHERER,
    "Sound Village Spy": SOUND_VILLAGE_SPY,
    "Mist Swordsman": MIST_SWORDSMAN,
    "Sensor Ninja": SENSOR_NINJA,
    "Water Prison Jutsu": WATER_PRISON_JUTSU,
    "Hidden Mist Jutsu": HIDDEN_MIST_JUTSU,
    "Water Dragon Jutsu": WATER_DRAGON_JUTSU,
    "Genjutsu: Release": GENJUTSU_RELEASE,
    "Demonic Illusion": DEMONIC_ILLUSION,
    "Substitution": SUBSTITUTION,
    "Mind Confusion Jutsu": MIND_CONFUSION_JUTSU,
    "Water Wall": WATER_WALL,
    "Water Style Training": WATER_STYLE_TRAINING,
    "Clone Jutsu": CLONE_JUTSU,
    "Tactical Retreat": TACTICAL_RETREAT,
    "Genjutsu Web": GENJUTSU_WEB,
    "Hidden Mist": HIDDEN_MIST,

    # BLACK - AKATSUKI, UCHIHA, DARKNESS
    "Itachi Uchiha, Tragic Genius": ITACHI_UCHIHA,
    "Pain, Six Paths of Destruction": PAIN,
    "Obito Uchiha, Masked Man": OBITO_UCHIHA,
    "Madara Uchiha, Ghost of the Uchiha": MADARA_UCHIHA,
    "Kisame Hoshigaki, Monster of the Mist": KISAME_HOSHIGAKI,
    "Deidara, Art is an Explosion": DEIDARA,
    "Sasori, Puppet Master": SASORI,
    "Hidan, Immortal Zealot": HIDAN,
    "Kakuzu, Five Hearts": KAKUZU,
    "Konan, Angel of Ame": KONAN,
    "Zetsu, White and Black": ZETSU,
    "Orochimaru, Sannin of Ambition": OROCHIMARU,
    "Sasuke, Curse Mark Awakened": CURSE_MARK_SASUKE,
    "Sound Village Jonin": SOUND_VILLAGE_JONIN,
    "Curse Mark Bearer": CURSE_MARK_BEARER,
    "ANBU Assassin": ANBU_ASSASSIN,
    "Uchiha Avenger": UCHIHA_AVENGER,
    "Rogue Ninja": ROGUE_NINJA,
    "Puppet Assassin": PUPPET_ASSASSIN,
    "Forbidden Jutsu User": FORBIDDEN_JUTSU_USER,
    "Reanimated Shinobi": REANIMATED_SHINOBI,
    "Tsukuyomi": TSUKUYOMI,
    "Amaterasu": AMATERASU,
    "Soul Extraction": SOUL_EXTRACTION,
    "Curse Mark Activation": CURSE_MARK_ACTIVATION,
    "Death Seal": DEATH_SEAL,
    "Shadow Possession": SHADOW_POSSESSION,
    "Reaper Death Seal": REAPER_DEATH_SEAL,
    "Painful Memories": PAINFUL_MEMORIES,
    "Edo Tensei": EDO_TENSEI,
    "Shinra Tensei": SHINRA_TENSEI,
    "Uchiha Massacre": UCHIHA_MASSACRE,
    "Izanagi": IZANAGI,
    "Curse of Hatred": CURSE_OF_HATRED,
    "Akatsuki Hideout": AKATSUKI_HIDEOUT,

    # RED - FIRE JUTSU, PASSION
    "Naruto, Sage of Mount Myoboku": NARUTO_SAGE_MODE,
    "Jiraiya, Toad Sage": JIRAIYA,
    "Killer Bee, Eight-Tails Jinchuriki": KILLER_BEE,
    "Gaara, One-Tail Jinchuriki": GAARA,
    "A, Fourth Raikage": A_FOURTH_RAIKAGE,
    "Mei Terumi, Fifth Mizukage": MEI_TERUMI,
    "Fire Style User": FIRE_STYLE_USER,
    "Cloud Village Ninja": CLOUD_VILLAGE_NINJA,
    "Uzumaki Descendant": UZUMAKI_DESCENDANT,
    "Shadow Clone": SHADOW_CLONE,
    "Explosive Tag Ninja": EXPLOSIVE_TAG_NINJA,
    "Sand Village Warrior": SAND_VILLAGE_WARRIOR,
    "Taijutsu Specialist": TAIJUTSU_SPECIALIST,
    "Rage-Filled Jinchuriki": RAGE_FILLED_JINCHURIKI,
    "Lightning Blade User": LIGHTNING_BLADE_USER,
    "Berserker Ninja": BERSERKER_NINJA,
    "Fire Ball Jutsu": FIRE_BALL_JUTSU,
    "Rasengan": RASENGAN,
    "Chidori": CHIDORI,
    "Rasenshuriken": RASENSHURIKEN,
    "Lightning Blade": LIGHTNING_BLADE,
    "Eight Gates Release": EIGHT_GATES_RELEASE,
    "Fire Dragon Jutsu": FIRE_DRAGON_JUTSU,
    "Explosive Kunai": EXPLOSIVE_KUNAI,
    "Lariat": LARIAT,
    "Wind-Enhanced Rasengan": WIND_ENHANCED_RASENGAN,
    "Planetary Rasengan": PLANETARY_RASENGAN,
    "Tailed Beast Bomb": TAILED_BEAST_BOMB,
    "Multi Shadow Clone Jutsu": MULTI_SHADOW_CLONE,
    "Burning Will": BURNING_WILL,
    "Nine-Tails Cloak": NINE_TAILS_CLOAK,
    "Battle Frenzy": BATTLE_FRENZY,

    # GREEN - NATURE CHAKRA, SAGE MODE, SUMMONS
    "Naruto, Kyubi Chakra Mode": NARUTO_KYUBI_MODE,
    "Hashirama, Wood Style Master": HASHIRAMA_WOOD_STYLE,
    "Yamato, Wood Style User": YAMATO,
    "Gamabunta, Toad Boss": GAMABUNTA,
    "Manda, Snake Boss": MANDA,
    "Katsuyu, Slug Princess": KATSUYU,
    "Kurama, Nine-Tailed Fox": KURAMA,
    "Shukaku, One-Tail": SHUKAKU,
    "Matatabi, Two-Tails": MATATABI,
    "Isobu, Three-Tails": ISOBU,
    "Son Goku, Four-Tails": SON_GOKU,
    "Kokuo, Five-Tails": KOKUO,
    "Saiken, Six-Tails": SAIKEN,
    "Chomei, Seven-Tails": CHOMEI,
    "Gyuki, Eight-Tails": GYUKI,
    "Toad Summon": TOAD_SUMMON,
    "Snake Summon": SNAKE_SUMMON,
    "Slug Summon": SLUG_SUMMON,
    "Forest of Death Beast": FOREST_OF_DEATH_BEAST,
    "Nature Chakra User": NATURE_CHAKRA_USER,
    "Wood Style Clone": WOOD_STYLE_CLONE,
    "Sage Apprentice": SAGE_APPRENTICE,
    "Giant Centipede": GIANT_CENTIPEDE,
    "Aburame Insect Swarm": ABURAME_INSECT_SWARM,
    "Forest Guardian": FOREST_GUARDIAN,
    "Summoning Jutsu": SUMMONING_JUTSU,
    "Wood Style: Wall": WOOD_STYLE_WALL,
    "Nature Energy": NATURE_ENERGY,
    "Frog Kumite": FROG_KUMITE,
    "Forest Binding": FOREST_BINDING,
    "Rejuvenation Jutsu": REJUVENATION_JUTSU,
    "Giant Growth Jutsu": GIANT_GROWTH_JUTSU,
    "Sage Art: Awakening": SAGE_ART_AWAKENING,
    "Mass Summoning": MASS_SUMMONING,
    "Wood Style: Deep Forest": WOOD_STYLE_DEEP_FOREST,
    "Sage Training": SAGE_TRAINING,
    "Natural Rebirth": NATURAL_REBIRTH,
    "Sage Mode": SAGE_MODE_ENCHANTMENT,
    "Forest of Death": FOREST_OF_DEATH,
    "Nature Chakra Field": NATURE_CHAKRA_FIELD,

    # ARTIFACTS
    "Kunai": KUNAI,
    "Shuriken": SHURIKEN,
    "Samehada, Shark Skin": SAMEHADA,
    "Executioner's Blade": EXECUTIONERS_BLADE,
    "Scroll of Sealing": SCROLL_OF_SEALING,
    "Chakra Pills": CHAKRA_PILLS,
    "Forbidden Scroll": FORBIDDEN_SCROLL,
    "Headband of the Leaf": HEADBAND_OF_THE_LEAF,
    "Sharingan Contact": SHARINGAN_CONTACT,
    "Rinnegan Eye": RINNEGAN_EYE,
    "Byakugan Eye": BYAKUGAN_EYE,
    "Puppet Core": PUPPET_CORE,
    "Explosive Tag": EXPLOSIVE_TAG,
    "Smoke Bomb": SMOKE_BOMB,
    "Summoning Contract": SUMMONING_CONTRACT,

    # LANDS
    "Hidden Leaf Village": HIDDEN_LEAF_VILLAGE,
    "Hidden Mist Village": HIDDEN_MIST_VILLAGE,
    "Hidden Sand Village": HIDDEN_SAND_VILLAGE,
    "Hidden Cloud Village": HIDDEN_CLOUD_VILLAGE,
    "Hidden Stone Village": HIDDEN_STONE_VILLAGE,
    "Valley of the End": VALLEY_OF_THE_END,
    "Akatsuki Hideout": AKATSUKI_HIDEOUT_LAND,
    "Forest of Death": FOREST_OF_DEATH_LAND,
    "Mount Myoboku": MOUNT_MYOBOKU,
    "Ryuchi Cave": RYUCHI_CAVE,
    "Shikkotsu Forest": SHIKKOTSU_FOREST,
    "Uchiha Compound": UCHIHA_COMPOUND,
    "Hyuga Compound": HYUGA_COMPOUND,
    "Training Ground": TRAINING_GROUND,
    "Chunin Exam Arena": CHUNIN_EXAM_ARENA,
    "Hokage Rock": HOKAGE_MONUMENT_LAND,

    # MULTICOLOR
    "Team 7 Formation": TEAM_7_FORMATION,
    "New Generation": NEW_GENERATION,
    "Bonds of Friendship": BONDS_OF_FRIENDSHIP,
    "Shinobi War": SHINOBI_WAR,
    "Allied Shinobi Forces": ALLIED_SHINOBI_FORCES,
    "Sannin Showdown": SANNIN_SHOWDOWN,
    "Final Valley Battle": FINAL_VALLEY_BATTLE,
    "Infinite Tsukuyomi": INFINITE_TSUKUYOMI,
    "Talk no Jutsu": TALK_NO_JUTSU,
    "Susanoo": SUSANOO,
}


# =============================================================================
# CARDS EXPORT
# =============================================================================

CARDS = [
    NARUTO_UZUMAKI,
    SAKURA_HARUNO,
    KAKASHI_HATAKE,
    HASHIRAMA_SENJU,
    TOBIRAMA_SENJU,
    HIRUZEN_SARUTOBI,
    MINATO_NAMIKAZE,
    TSUNADE,
    MIGHT_GUY,
    ROCK_LEE,
    NEJI_HYUGA,
    HINATA_HYUGA,
    SHIKAMARU_NARA,
    CHOJI_AKIMICHI,
    INO_YAMANAKA,
    TENTEN,
    KONOHA_GENIN,
    KONOHA_CHUNIN,
    KONOHA_JONIN,
    ANBU_BLACK_OPS,
    MEDICAL_NINJA,
    HYUGA_BRANCH_MEMBER,
    NARA_SHADOW_USER,
    WILL_OF_FIRE_BEARER,
    KONOHA_ACADEMY_STUDENT,
    BARRIER_TEAM_NINJA,
    SUBSTITUTION_JUTSU,
    WILL_OF_FIRE,
    GENTLE_FIST,
    EIGHT_TRIGRAMS_PALM,
    HEALING_JUTSU,
    KONOHA_SENBON,
    PROTECTION_BARRIER,
    VILLAGE_DEFENSE,
    KONOHA_REINFORCEMENTS,
    HIDDEN_LEAF_DECREE,
    HOKAGE_MONUMENT,
    WILL_OF_FIRE_ENCHANTMENT,
    KONOHA_ALLIANCE,
    SASUKE_UCHIHA,
    ZABUZA_MOMOCHI,
    HAKU,
    KABUTO_YAKUSHI,
    SHINO_ABURAME,
    KIBA_INUZUKA,
    MIST_VILLAGE_NINJA,
    GENJUTSU_SPECIALIST,
    WATER_CLONE,
    ABURAME_TRACKER,
    INTELLIGENCE_GATHERER,
    SOUND_VILLAGE_SPY,
    MIST_SWORDSMAN,
    SENSOR_NINJA,
    WATER_PRISON_JUTSU,
    HIDDEN_MIST_JUTSU,
    WATER_DRAGON_JUTSU,
    GENJUTSU_RELEASE,
    DEMONIC_ILLUSION,
    SUBSTITUTION,
    MIND_CONFUSION_JUTSU,
    WATER_WALL,
    WATER_STYLE_TRAINING,
    CLONE_JUTSU,
    TACTICAL_RETREAT,
    GENJUTSU_WEB,
    HIDDEN_MIST,
    ITACHI_UCHIHA,
    PAIN,
    OBITO_UCHIHA,
    MADARA_UCHIHA,
    KISAME_HOSHIGAKI,
    DEIDARA,
    SASORI,
    HIDAN,
    KAKUZU,
    KONAN,
    ZETSU,
    OROCHIMARU,
    CURSE_MARK_SASUKE,
    SOUND_VILLAGE_JONIN,
    CURSE_MARK_BEARER,
    ANBU_ASSASSIN,
    UCHIHA_AVENGER,
    ROGUE_NINJA,
    PUPPET_ASSASSIN,
    FORBIDDEN_JUTSU_USER,
    REANIMATED_SHINOBI,
    TSUKUYOMI,
    AMATERASU,
    SOUL_EXTRACTION,
    CURSE_MARK_ACTIVATION,
    DEATH_SEAL,
    SHADOW_POSSESSION,
    REAPER_DEATH_SEAL,
    PAINFUL_MEMORIES,
    EDO_TENSEI,
    SHINRA_TENSEI,
    UCHIHA_MASSACRE,
    IZANAGI,
    CURSE_OF_HATRED,
    AKATSUKI_HIDEOUT,
    NARUTO_SAGE_MODE,
    JIRAIYA,
    KILLER_BEE,
    GAARA,
    A_FOURTH_RAIKAGE,
    MEI_TERUMI,
    FIRE_STYLE_USER,
    CLOUD_VILLAGE_NINJA,
    UZUMAKI_DESCENDANT,
    SHADOW_CLONE,
    EXPLOSIVE_TAG_NINJA,
    SAND_VILLAGE_WARRIOR,
    TAIJUTSU_SPECIALIST,
    RAGE_FILLED_JINCHURIKI,
    LIGHTNING_BLADE_USER,
    BERSERKER_NINJA,
    FIRE_BALL_JUTSU,
    RASENGAN,
    CHIDORI,
    RASENSHURIKEN,
    LIGHTNING_BLADE,
    EIGHT_GATES_RELEASE,
    FIRE_DRAGON_JUTSU,
    EXPLOSIVE_KUNAI,
    LARIAT,
    WIND_ENHANCED_RASENGAN,
    PLANETARY_RASENGAN,
    TAILED_BEAST_BOMB,
    MULTI_SHADOW_CLONE,
    BURNING_WILL,
    NINE_TAILS_CLOAK,
    BATTLE_FRENZY,
    NARUTO_KYUBI_MODE,
    HASHIRAMA_WOOD_STYLE,
    YAMATO,
    GAMABUNTA,
    MANDA,
    KATSUYU,
    KURAMA,
    SHUKAKU,
    MATATABI,
    ISOBU,
    SON_GOKU,
    KOKUO,
    SAIKEN,
    CHOMEI,
    GYUKI,
    TOAD_SUMMON,
    SNAKE_SUMMON,
    SLUG_SUMMON,
    FOREST_OF_DEATH_BEAST,
    NATURE_CHAKRA_USER,
    WOOD_STYLE_CLONE,
    SAGE_APPRENTICE,
    GIANT_CENTIPEDE,
    ABURAME_INSECT_SWARM,
    FOREST_GUARDIAN,
    SUMMONING_JUTSU,
    WOOD_STYLE_WALL,
    NATURE_ENERGY,
    FROG_KUMITE,
    FOREST_BINDING,
    REJUVENATION_JUTSU,
    GIANT_GROWTH_JUTSU,
    SAGE_ART_AWAKENING,
    MASS_SUMMONING,
    WOOD_STYLE_DEEP_FOREST,
    SAGE_TRAINING,
    NATURAL_REBIRTH,
    SAGE_MODE_ENCHANTMENT,
    FOREST_OF_DEATH,
    NATURE_CHAKRA_FIELD,
    KUNAI,
    SHURIKEN,
    SAMEHADA,
    EXECUTIONERS_BLADE,
    SCROLL_OF_SEALING,
    CHAKRA_PILLS,
    FORBIDDEN_SCROLL,
    HEADBAND_OF_THE_LEAF,
    SHARINGAN_CONTACT,
    RINNEGAN_EYE,
    BYAKUGAN_EYE,
    PUPPET_CORE,
    EXPLOSIVE_TAG,
    SMOKE_BOMB,
    SUMMONING_CONTRACT,
    HIDDEN_LEAF_VILLAGE,
    HIDDEN_MIST_VILLAGE,
    HIDDEN_SAND_VILLAGE,
    HIDDEN_CLOUD_VILLAGE,
    HIDDEN_STONE_VILLAGE,
    VALLEY_OF_THE_END,
    AKATSUKI_HIDEOUT_LAND,
    FOREST_OF_DEATH_LAND,
    MOUNT_MYOBOKU,
    RYUCHI_CAVE,
    SHIKKOTSU_FOREST,
    UCHIHA_COMPOUND,
    HYUGA_COMPOUND,
    TRAINING_GROUND,
    CHUNIN_EXAM_ARENA,
    HOKAGE_MONUMENT_LAND,
    TEAM_7_FORMATION,
    NEW_GENERATION,
    BONDS_OF_FRIENDSHIP,
    SHINOBI_WAR,
    ALLIED_SHINOBI_FORCES,
    SANNIN_SHOWDOWN,
    FINAL_VALLEY_BATTLE,
    INFINITE_TSUKUYOMI,
    TALK_NO_JUTSU,
    SUSANOO
]
