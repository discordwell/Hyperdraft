"""
Yu-Gi-Oh! Optimized Decks

Four competitive archetypes built from classic YGO formats:
- Goat Control (2005 meta: flip effects, heavy removal, BLS)
- Monarch Control (tribute summon value engines)
- Chain Burn (direct damage spells/traps, stall walls)
- Dragon Beatdown (dragon beaters with type support)

Each deck includes AI_STRATEGY hints for the YugiohAIAdapter.
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import Event, EventType, GameState, ZoneType, CardType
from src.engine.yugioh_helpers import (
    destroy_all_monsters, destroy_attacking_monsters,
    revive_from_graveyard, destroy_spell_trap,
)


# =============================================================================
# Shared Staples (used across multiple decks)
# =============================================================================

def _pot_of_greed_resolve(event, state):
    """Draw 2 cards."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    deck = state.zones.get(f"deck_{pid}")
    hand = state.zones.get(f"hand_{pid}")
    if not deck or not hand:
        return events
    for _ in range(min(2, len(deck.objects))):
        card_id = deck.objects.pop(0)
        hand.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.HAND
        events.append(Event(type=EventType.DRAW,
                            payload={'player': pid, 'card_id': card_id}))
    return events

POT_OF_GREED = make_ygo_spell(
    "Pot of Greed", ygo_spell_type="Normal",
    text="Draw 2 cards.",
    resolve=_pot_of_greed_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/55144522.jpg",
)

def _graceful_charity_resolve(event, state):
    """Draw 3 cards, then discard 2. (Simplified: draw 1 net card advantage.)"""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    deck = state.zones.get(f"deck_{pid}")
    hand = state.zones.get(f"hand_{pid}")
    if not deck or not hand:
        return events
    # Draw 3
    drawn = []
    for _ in range(min(3, len(deck.objects))):
        card_id = deck.objects.pop(0)
        hand.objects.append(card_id)
        obj = state.objects.get(card_id)
        if obj:
            obj.zone = ZoneType.HAND
        drawn.append(card_id)
        events.append(Event(type=EventType.DRAW,
                            payload={'player': pid, 'card_id': card_id}))
    # Discard 2 (discard last 2 drawn for simplicity)
    gy = state.zones.get(f"graveyard_{pid}")
    if gy:
        to_discard = hand.objects[-2:] if len(hand.objects) >= 2 else list(hand.objects)
        for cid in to_discard[:2]:
            if cid in hand.objects:
                hand.objects.remove(cid)
                gy.objects.append(cid)
                obj = state.objects.get(cid)
                if obj:
                    obj.zone = ZoneType.GRAVEYARD
                events.append(Event(type=EventType.DISCARD,
                                    payload={'player': pid, 'card_id': cid}))
    return events

GRACEFUL_CHARITY = make_ygo_spell(
    "Graceful Charity", ygo_spell_type="Normal",
    text="Draw 3 cards, then discard 2.",
    resolve=_graceful_charity_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/79571449.jpg",
)

def _heavy_storm_resolve(event, state):
    """Destroy all Spell/Trap Cards on the field."""
    events = []
    for pid in state.players:
        zone = state.zones.get(f"spell_trap_zone_{pid}")
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': obj_id, 'card_name': obj.name}))
        # Also check field spell zone
        field_zone = state.zones.get(f"field_spell_{pid}")
        if field_zone:
            for i, obj_id in enumerate(field_zone.objects):
                if obj_id is None:
                    continue
                obj = state.objects.get(obj_id)
                if obj:
                    field_zone.objects[i] = None
                    gy = state.zones.get(f"graveyard_{obj.owner}")
                    if gy:
                        gy.objects.append(obj_id)
                    obj.zone = ZoneType.GRAVEYARD
                    events.append(Event(type=EventType.YGO_DESTROY,
                                        payload={'card_id': obj_id, 'card_name': obj.name}))
    return events

HEAVY_STORM = make_ygo_spell(
    "Heavy Storm", ygo_spell_type="Normal",
    text="Destroy all Spell and Trap Cards on the field.",
    resolve=_heavy_storm_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/19613556.jpg",
)

def _raigeki_resolve(event, state):
    """Destroy all monsters your opponent controls."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    for opp_id in state.players:
        if opp_id == pid:
            continue
        zone = state.zones.get(f"monster_zone_{opp_id}")
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj:
                zone.objects[i] = None
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(obj_id)
                obj.zone = ZoneType.GRAVEYARD
                obj.state.face_down = False
                obj.state.ygo_position = None
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': obj_id, 'card_name': obj.name}))
    return events

RAIGEKI = make_ygo_spell(
    "Raigeki", ygo_spell_type="Normal",
    text="Destroy all monsters your opponent controls.",
    resolve=_raigeki_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/12580477.jpg",
)

def _premature_burial_resolve(event, state):
    """Pay 800 LP; Special Summon 1 monster from your GY."""
    events = []
    pid = event.payload.get('player')
    targets = event.payload.get('targets', [])
    if not pid or not targets:
        return events
    player = state.players.get(pid)
    if player:
        player.lp = max(0, player.lp - 800)
        events.append(Event(type=EventType.YGO_LP_CHANGE,
                            payload={'player': pid, 'amount': -800, 'source': 'Premature Burial'}))
    events.extend(revive_from_graveyard(state, pid, targets[0]))
    return events

PREMATURE_BURIAL = make_ygo_spell(
    "Premature Burial", ygo_spell_type="Equip",
    text="Pay 800 LP; Special Summon 1 monster from your GY in ATK Position.",
    resolve=_premature_burial_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/70828912.jpg",
)

def _nobleman_resolve(event, state):
    """Destroy 1 face-down monster and banish it."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    for opp_id in state.players:
        if opp_id == pid:
            continue
        zone = state.zones.get(f"monster_zone_{opp_id}")
        if not zone:
            continue
        for i, obj_id in enumerate(zone.objects):
            if obj_id is None:
                continue
            obj = state.objects.get(obj_id)
            if obj and obj.state.face_down:
                zone.objects[i] = None
                banished = state.zones.get(f"banished_{obj.owner}")
                if banished:
                    banished.objects.append(obj_id)
                else:
                    gy = state.zones.get(f"graveyard_{obj.owner}")
                    if gy:
                        gy.objects.append(obj_id)
                obj.zone = ZoneType.EXILE
                obj.state.face_down = False
                events.append(Event(type=EventType.YGO_DESTROY,
                                    payload={'card_id': obj_id, 'card_name': obj.name}))
                return events
    return events

NOBLEMAN_OF_CROSSOUT = make_ygo_spell(
    "Nobleman of Crossout", ygo_spell_type="Normal",
    text="Destroy 1 face-down monster and banish it.",
    resolve=_nobleman_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/71044499.jpg",
)

# Reuse from ygo_starter/ygo_classic (import-friendly copies with consistent names)
from src.cards.yugioh.ygo_starter import (
    DARK_HOLE as _DH, MYSTICAL_SPACE_TYPHOON as _MST,
    MONSTER_REBORN as _MR, MIRROR_FORCE as _MF,
    SAKURETSU_ARMOR as _SA, SOLEMN_JUDGMENT as _SJ,
    CALL_OF_THE_HAUNTED as _COTH, SWORDS_OF_REVEALING_LIGHT as _SORL,
    MAN_EATER_BUG as _MEB, BREAKER_THE_MAGICAL_WARRIOR as _BREAKER,
    MAGICIAN_OF_FAITH as _MOF,
)
from src.cards.yugioh.ygo_classic import (
    RING_OF_DESTRUCTION as _ROD, MAGIC_CYLINDER as _MC,
    BOOK_OF_MOON as _BOM,
)

# Convenient aliases
DARK_HOLE = _DH
MYSTICAL_SPACE_TYPHOON = _MST
MONSTER_REBORN = _MR
MIRROR_FORCE = _MF
SAKURETSU_ARMOR = _SA
SOLEMN_JUDGMENT = _SJ
CALL_OF_THE_HAUNTED = _COTH
SWORDS_OF_REVEALING_LIGHT = _SORL
MAN_EATER_BUG = _MEB
BREAKER_THE_MAGICAL_WARRIOR = _BREAKER
MAGICIAN_OF_FAITH = _MOF
RING_OF_DESTRUCTION = _ROD
MAGIC_CYLINDER = _MC
BOOK_OF_MOON = _BOM

def _torrential_resolve(event, state):
    """Destroy all monsters on the field."""
    return destroy_all_monsters(state)

TORRENTIAL_TRIBUTE = make_ygo_trap(
    "Torrential Tribute", ygo_trap_type="Normal",
    text="When a monster is Summoned: Destroy all monsters on the field.",
    resolve=_torrential_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/53582587.jpg",
)

def _bottomless_resolve(event, state):
    """Destroy and banish the attacking/summoned monster with 1500+ ATK."""
    events = []
    target_id = (event.payload.get('targets') or [None])[0]
    if target_id:
        obj = state.objects.get(target_id)
        if obj:
            for zone in state.zones.values():
                if target_id in zone.objects:
                    for i, oid in enumerate(zone.objects):
                        if oid == target_id:
                            zone.objects[i] = None
                            break
                    while target_id in zone.objects:
                        zone.objects.remove(target_id)
                    break
            banished = state.zones.get(f"banished_{obj.owner}")
            if banished:
                banished.objects.append(target_id)
            else:
                gy = state.zones.get(f"graveyard_{obj.owner}")
                if gy:
                    gy.objects.append(target_id)
            obj.zone = ZoneType.EXILE
            obj.state.face_down = False
            events.append(Event(type=EventType.YGO_DESTROY,
                                payload={'card_id': target_id, 'card_name': obj.name}))
    return events

BOTTOMLESS_TRAP_HOLE = make_ygo_trap(
    "Bottomless Trap Hole", ygo_trap_type="Normal",
    text="When a monster with 1500+ ATK is Summoned: Destroy and banish it.",
    resolve=_bottomless_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/29401950.jpg",
)

def _dimensional_prison_resolve(event, state):
    """Banish the attacking monster."""
    return _bottomless_resolve(event, state)

DIMENSIONAL_PRISON = make_ygo_trap(
    "Dimensional Prison", ygo_trap_type="Normal",
    text="When an opponent's monster declares an attack: Banish it.",
    resolve=_dimensional_prison_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/70342110.jpg",
)


# =============================================================================
# DECK 1: Goat Control
# =============================================================================

BLACK_LUSTER_SOLDIER = make_ygo_monster(
    "Black Luster Soldier - Envoy of the Beginning", atk=3000, def_val=2500, level=8,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="Must be Special Summoned by banishing 1 LIGHT and 1 DARK from your GY. Banish 1 monster, or attack twice if it destroys a monster.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/72989439.jpg",
)

AIRKNIGHT_PARSHATH = make_ygo_monster(
    "Airknight Parshath", atk=1900, def_val=1400, level=5,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Fairy"},
    text="Piercing battle damage. When this card inflicts battle damage: Draw 1 card.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/18036057.jpg",
)

TRIBE_INFECTING_VIRUS = make_ygo_monster(
    "Tribe-Infecting Virus", atk=1600, def_val=1000, level=4,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Aqua"},
    text="Discard 1 card, declare a Type: Destroy all face-up monsters of that Type.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/33184167.jpg",
)

SINISTER_SERPENT = make_ygo_monster(
    "Sinister Serpent", atk=300, def_val=250, level=1,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Reptile"},
    text="During your Standby Phase, if this card is in your GY: Add it to your hand.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/8131171.jpg",
)

DD_WARRIOR_LADY = make_ygo_monster(
    "D.D. Warrior Lady", atk=1500, def_val=1600, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="After damage calculation with an opponent's monster: Banish both this card and that monster.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/7572887.jpg",
)

SANGAN = make_ygo_monster(
    "Sangan", atk=1000, def_val=600, level=3,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Fiend"},
    text="If this card is sent from the field to the GY: Add 1 monster with 1500 or less ATK from your Deck to your hand.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/26202165.jpg",
)

MYSTIC_TOMATO = make_ygo_monster(
    "Mystic Tomato", atk=1400, def_val=1100, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Plant"},
    text="When destroyed by battle: Special Summon 1 DARK monster with 1500 or less ATK from your Deck.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/83011278.jpg",
)

def _dekoichi_flip(obj, state):
    """FLIP: Draw 1 card."""
    events = []
    pid = obj.controller
    deck = state.zones.get(f"deck_{pid}")
    hand = state.zones.get(f"hand_{pid}")
    if deck and hand and deck.objects:
        card_id = deck.objects.pop(0)
        hand.objects.append(card_id)
        c = state.objects.get(card_id)
        if c:
            c.zone = ZoneType.HAND
        events.append(Event(type=EventType.DRAW,
                            payload={'player': pid, 'card_id': card_id}))
    return events

DEKOICHI = make_ygo_monster(
    "Dekoichi the Battlechanted Locomotive", atk=1400, def_val=1000, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Machine"},
    text="FLIP: Draw 1 card.",
    flip_effect=_dekoichi_flip,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/87621407.jpg",
)

SPIRIT_REAPER = make_ygo_monster(
    "Spirit Reaper", atk=300, def_val=200, level=3,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Zombie"},
    text="Cannot be destroyed by battle. When this card inflicts battle damage: Opponent discards 1 random card.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/23205979.jpg",
)

SNATCH_STEAL = make_ygo_spell(
    "Snatch Steal", ygo_spell_type="Equip",
    text="Take control of 1 opponent's monster. Opponent gains 1000 LP each Standby Phase.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/45986603.jpg",
)

GOAT_CONTROL_DECK = (
    [BLACK_LUSTER_SOLDIER] * 1 +
    [AIRKNIGHT_PARSHATH] * 1 +
    [TRIBE_INFECTING_VIRUS] * 1 +
    [DD_WARRIOR_LADY] * 1 +
    [BREAKER_THE_MAGICAL_WARRIOR] * 1 +
    [MYSTIC_TOMATO] * 2 +
    [SANGAN] * 1 +
    [SINISTER_SERPENT] * 1 +
    [SPIRIT_REAPER] * 1 +
    [MAGICIAN_OF_FAITH] * 1 +
    [DEKOICHI] * 2 +
    [MAN_EATER_BUG] * 1 +
    # Spells (15)
    [POT_OF_GREED] * 1 +
    [GRACEFUL_CHARITY] * 1 +
    [HEAVY_STORM] * 1 +
    [DARK_HOLE] * 1 +
    [MONSTER_REBORN] * 1 +
    [PREMATURE_BURIAL] * 1 +
    [SNATCH_STEAL] * 1 +
    [NOBLEMAN_OF_CROSSOUT] * 1 +
    [MYSTICAL_SPACE_TYPHOON] * 1 +
    [BOOK_OF_MOON] * 2 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 +
    [RAIGEKI] * 1 +
    # Traps (11)
    [MIRROR_FORCE] * 1 +
    [TORRENTIAL_TRIBUTE] * 1 +
    [RING_OF_DESTRUCTION] * 1 +
    [SAKURETSU_ARMOR] * 2 +
    [CALL_OF_THE_HAUNTED] * 1 +
    [BOTTOMLESS_TRAP_HOLE] * 1 +
    [SOLEMN_JUDGMENT] * 1 +
    [MAGIC_CYLINDER] * 1 +
    [DIMENSIONAL_PRISON] * 2 +
    # Extra monsters to fill 40
    [MYSTIC_TOMATO] * 1 +
    [DD_WARRIOR_LADY] * 1
)
GOAT_CONTROL_EXTRA = []

GOAT_CONTROL_STRATEGY = {
    'name': 'Goat Control',
    'archetype': 'Control',
    'description': 'The legendary 2005 Goat Format deck. Grind opponents out with flip effects, heavy removal, and card advantage. BLS is your finisher.',
    'priorities': [
        'Set flip monsters (Dekoichi, Man-Eater Bug, Magician of Faith) for card advantage',
        'Save Raigeki/Dark Hole for when opponent overextends with multiple monsters',
        'Use Book of Moon defensively to stop big attackers',
        'BLS is the finisher — protect it and summon when you have board control',
        'Heavy Storm when opponent has 2+ backrow',
        'Nobleman of Crossout face-down monsters to deny flip effects',
        'Spirit Reaper can stall indefinitely against big monsters',
    ],
    'summon_priority': ['Black Luster Soldier - Envoy of the Beginning', 'Airknight Parshath',
                        'Tribe-Infecting Virus', 'D.D. Warrior Lady', 'Breaker the Magical Warrior',
                        'Mystic Tomato'],
    'set_priority': ['Dekoichi the Battlechanted Locomotive', 'Man-Eater Bug', 'Magician of Faith',
                     'Sangan', 'Sinister Serpent'],
}


# =============================================================================
# DECK 2: Monarch Control
# =============================================================================

MOBIUS_THE_FROST_MONARCH = make_ygo_monster(
    "Mobius the Frost Monarch", atk=2400, def_val=1000, level=6,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Aqua"},
    text="When Tribute Summoned: Destroy up to 2 Spell/Trap Cards on the field.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/4929256.jpg",
)

THESTALOS_THE_FIRESTORM_MONARCH = make_ygo_monster(
    "Thestalos the Firestorm Monarch", atk=2400, def_val=1000, level=6,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Pyro"},
    text="When Tribute Summoned: Discard 1 random card from opponent's hand. If it was a Monster, inflict 100 x its Level as damage.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/26205777.jpg",
)

ZABORG_THE_THUNDER_MONARCH = make_ygo_monster(
    "Zaborg the Thunder Monarch", atk=2400, def_val=1000, level=5,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Thunder"},
    text="When Tribute Summoned: Destroy 1 monster on the field.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/51945556.jpg",
)

CAIUS_THE_SHADOW_MONARCH = make_ygo_monster(
    "Caius the Shadow Monarch", atk=2400, def_val=1000, level=6,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Fiend"},
    text="When Tribute Summoned: Banish 1 card on the field. If it was a DARK monster, inflict 1000 damage.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/9748752.jpg",
)

TREEBORN_FROG = make_ygo_monster(
    "Treeborn Frog", atk=100, def_val=100, level=1,
    attribute="WATER", ygo_monster_type="Effect",
    subtypes={"Aqua"},
    text="During your Standby Phase, if this card is in your GY and you control no Spell/Trap Cards: Special Summon this card.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/12538374.jpg",
)

SOUL_EXCHANGE = make_ygo_spell(
    "Soul Exchange", ygo_spell_type="Normal",
    text="Tribute 1 opponent's monster instead of your own for a Tribute Summon. You cannot conduct your Battle Phase this turn.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/68005187.jpg",
)

BRAIN_CONTROL = make_ygo_spell(
    "Brain Control", ygo_spell_type="Normal",
    text="Pay 800 LP; take control of 1 opponent's face-up monster until the End Phase.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/87910978.jpg",
)

ENEMY_CONTROLLER = make_ygo_spell(
    "Enemy Controller", ygo_spell_type="Quick-Play",
    text="Change 1 monster's battle position, OR tribute 1 monster to take control of 1 opponent's monster.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/98045062.jpg",
)

# Tribute fodder
CYBER_DRAGON = make_ygo_monster(
    "Cyber Dragon", atk=2100, def_val=1600, level=5,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Machine"},
    text="If your opponent controls a monster and you control no monsters: Special Summon this card from your hand.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/70095154.jpg",
)

GRAVEKEEPER_SPY = make_ygo_monster(
    "Gravekeeper's Spy", atk=1200, def_val=2000, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="FLIP: Special Summon 1 'Gravekeeper's' monster with 1500 or less ATK from your Deck.",
    flip_effect=_dekoichi_flip,  # Simplified: draw 1 instead of SS
    image_url="https://images.ygoprodeck.com/images/cards_cropped/63695531.jpg",
)

MONARCH_DECK = (
    # Monarchs (8)
    [MOBIUS_THE_FROST_MONARCH] * 2 +
    [THESTALOS_THE_FIRESTORM_MONARCH] * 2 +
    [ZABORG_THE_THUNDER_MONARCH] * 2 +
    [CAIUS_THE_SHADOW_MONARCH] * 2 +
    # Tribute fodder / utility (12)
    [TREEBORN_FROG] * 2 +
    [CYBER_DRAGON] * 2 +
    [GRAVEKEEPER_SPY] * 2 +
    [SANGAN] * 1 +
    [SPIRIT_REAPER] * 1 +
    [MYSTIC_TOMATO] * 2 +
    [DD_WARRIOR_LADY] * 1 +
    [SINISTER_SERPENT] * 1 +
    # Spells (12)
    [SOUL_EXCHANGE] * 2 +
    [BRAIN_CONTROL] * 1 +
    [ENEMY_CONTROLLER] * 2 +
    [POT_OF_GREED] * 1 +
    [HEAVY_STORM] * 1 +
    [DARK_HOLE] * 1 +
    [MONSTER_REBORN] * 1 +
    [PREMATURE_BURIAL] * 1 +
    [MYSTICAL_SPACE_TYPHOON] * 1 +
    [NOBLEMAN_OF_CROSSOUT] * 1 +
    # Traps (8)
    [TORRENTIAL_TRIBUTE] * 1 +
    [MIRROR_FORCE] * 1 +
    [SAKURETSU_ARMOR] * 2 +
    [BOTTOMLESS_TRAP_HOLE] * 1 +
    [RING_OF_DESTRUCTION] * 1 +
    [SOLEMN_JUDGMENT] * 1 +
    [CALL_OF_THE_HAUNTED] * 1
)
MONARCH_EXTRA = []

MONARCH_STRATEGY = {
    'name': 'Monarch Control',
    'archetype': 'Tribute Control',
    'description': 'Tribute Summon powerful Monarchs that destroy cards on entry. Use Treeborn Frog and floaters as tribute fodder. Each Monarch removes a threat when summoned.',
    'priorities': [
        'Protect Treeborn Frog in the GY — it is free tribute fodder every turn',
        'Set Gravekeeper\'s Spy face-down for a flip + tribute chain',
        'Tribute Summon Monarchs aggressively — their effects clear the way',
        'Zaborg destroys monsters, Mobius destroys backrow, Caius banishes anything',
        'Thestalos disrupts opponent\'s hand — best when their hand is large',
        'Soul Exchange lets you tribute opponent\'s monsters for your Monarchs',
        'Cyber Dragon provides free ATK presence and tribute fodder',
        'Brain Control: take their monster, tribute it for a Monarch',
    ],
    'summon_priority': ['Caius the Shadow Monarch', 'Mobius the Frost Monarch',
                        'Zaborg the Thunder Monarch', 'Thestalos the Firestorm Monarch',
                        'Cyber Dragon'],
    'set_priority': ['Gravekeeper\'s Spy', 'Treeborn Frog', 'Sangan', 'Mystic Tomato'],
}


# =============================================================================
# DECK 3: Chain Burn
# =============================================================================

LAVA_GOLEM = make_ygo_monster(
    "Lava Golem", atk=3000, def_val=2500, level=8,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Fiend"},
    text="Give to opponent by tributing 2 of their monsters. Inflicts 1000 damage to its controller each Standby Phase.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/102380.jpg",
)

def _stealth_bird_flip(obj, state):
    """FLIP: Inflict 1000 damage to opponent."""
    events = []
    for pid in state.players:
        if pid != obj.controller:
            player = state.players.get(pid)
            if player:
                player.lp = max(0, player.lp - 1000)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': pid, 'amount': -1000,
                                             'source': 'Stealth Bird'}))
                if player.lp <= 0:
                    player.has_lost = True
    return events

STEALTH_BIRD = make_ygo_monster(
    "Stealth Bird", atk=700, def_val=1700, level=3,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Winged Beast"},
    text="FLIP: Inflict 1000 damage to your opponent.",
    flip_effect=_stealth_bird_flip,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/3510565.jpg",
)

def _des_koala_flip(obj, state):
    """FLIP: Inflict 400 damage per card in opponent's hand."""
    events = []
    for pid in state.players:
        if pid != obj.controller:
            hand = state.zones.get(f"hand_{pid}")
            cards = len(hand.objects) if hand else 0
            damage = cards * 400
            if damage > 0:
                player = state.players.get(pid)
                if player:
                    player.lp = max(0, player.lp - damage)
                    events.append(Event(type=EventType.YGO_LP_CHANGE,
                                        payload={'player': pid, 'amount': -damage,
                                                 'source': f'Des Koala ({cards} cards)'}))
                    if player.lp <= 0:
                        player.has_lost = True
    return events

DES_KOALA = make_ygo_monster(
    "Des Koala", atk=1100, def_val=1800, level=3,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Beast"},
    text="FLIP: Inflict 400 damage to your opponent for each card in their hand.",
    flip_effect=_des_koala_flip,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/69579761.jpg",
)

MARSHMALLON = make_ygo_monster(
    "Marshmallon", atk=300, def_val=500, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Fairy"},
    text="Cannot be destroyed by battle. When flipped face-up by attack: Inflict 1000 damage to opponent.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/31305911.jpg",
)

GIANT_GERM = make_ygo_monster(
    "Giant Germ", atk=1000, def_val=100, level=2,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Fiend"},
    text="When destroyed by battle: Inflict 500 damage to opponent, then Special Summon up to 2 copies from Deck.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/95178994.jpg",
)

def _ookazi_resolve(event, state):
    """Inflict 800 damage to opponent."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    for opp_id in state.players:
        if opp_id != pid:
            player = state.players.get(opp_id)
            if player:
                player.lp = max(0, player.lp - 800)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': opp_id, 'amount': -800,
                                             'source': 'Ookazi'}))
                if player.lp <= 0:
                    player.has_lost = True
    return events

OOKAZI = make_ygo_spell(
    "Ookazi", ygo_spell_type="Normal",
    text="Inflict 800 damage to your opponent.",
    resolve=_ookazi_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/19523799.jpg",
)

WAVE_MOTION_CANNON = make_ygo_spell(
    "Wave-Motion Cannon", ygo_spell_type="Continuous",
    text="During your Main Phase: Send this face-up card to the GY; inflict 1000 damage per Standby Phase this was on the field.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/38992735.jpg",
)

MESSENGER_OF_PEACE = make_ygo_spell(
    "Messenger of Peace", ygo_spell_type="Continuous",
    text="Monsters with 1500+ ATK cannot attack. Pay 100 LP each Standby Phase or destroy this card.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/44656491.jpg",
)

LEVEL_LIMIT_AREA_B = make_ygo_spell(
    "Level Limit - Area B", ygo_spell_type="Continuous",
    text="All face-up Level 4+ monsters are changed to Defense Position.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/3136426.jpg",
)

GRAVITY_BIND = make_ygo_trap(
    "Gravity Bind", ygo_trap_type="Continuous",
    text="Level 4+ monsters cannot attack.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/85742772.jpg",
)

def _just_desserts_resolve(event, state):
    """Inflict 500 damage per monster opponent controls."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    for opp_id in state.players:
        if opp_id != pid:
            zone = state.zones.get(f"monster_zone_{opp_id}")
            count = 0
            if zone:
                count = sum(1 for oid in zone.objects if oid is not None)
            damage = count * 500
            if damage > 0:
                player = state.players.get(opp_id)
                if player:
                    player.lp = max(0, player.lp - damage)
                    events.append(Event(type=EventType.YGO_LP_CHANGE,
                                        payload={'player': opp_id, 'amount': -damage,
                                                 'source': f'Just Desserts ({count} monsters)'}))
                    if player.lp <= 0:
                        player.has_lost = True
    return events

JUST_DESSERTS = make_ygo_trap(
    "Just Desserts", ygo_trap_type="Normal",
    text="Inflict 500 damage to your opponent for each monster they control.",
    resolve=_just_desserts_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/24068492.jpg",
)

def _secret_barrel_resolve(event, state):
    """Inflict 200 damage per card opponent controls + in hand."""
    events = []
    pid = event.payload.get('player')
    if not pid:
        return events
    for opp_id in state.players:
        if opp_id != pid:
            count = 0
            for zone_name in [f"monster_zone_{opp_id}", f"spell_trap_zone_{opp_id}", f"hand_{opp_id}"]:
                zone = state.zones.get(zone_name)
                if zone:
                    count += sum(1 for oid in zone.objects if oid is not None)
            damage = count * 200
            if damage > 0:
                player = state.players.get(opp_id)
                if player:
                    player.lp = max(0, player.lp - damage)
                    events.append(Event(type=EventType.YGO_LP_CHANGE,
                                        payload={'player': opp_id, 'amount': -damage,
                                                 'source': f'Secret Barrel ({count} cards)'}))
                    if player.lp <= 0:
                        player.has_lost = True
    return events

SECRET_BARREL = make_ygo_trap(
    "Secret Barrel", ygo_trap_type="Normal",
    text="Inflict 200 damage for each card your opponent controls and in their hand.",
    resolve=_secret_barrel_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/27053506.jpg",
)

CHAIN_BURN_DECK = (
    # Monsters (12) — walls and flip burn
    [STEALTH_BIRD] * 3 +
    [DES_KOALA] * 2 +
    [MARSHMALLON] * 2 +
    [GIANT_GERM] * 3 +
    [LAVA_GOLEM] * 2 +
    # Spells (12) — burn and stall
    [OOKAZI] * 3 +
    [POT_OF_GREED] * 1 +
    [GRACEFUL_CHARITY] * 1 +
    [HEAVY_STORM] * 1 +
    [WAVE_MOTION_CANNON] * 2 +
    [MESSENGER_OF_PEACE] * 2 +
    [LEVEL_LIMIT_AREA_B] * 1 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 +
    # Traps (16) — burn and protection
    [JUST_DESSERTS] * 3 +
    [SECRET_BARREL] * 3 +
    [GRAVITY_BIND] * 2 +
    [MAGIC_CYLINDER] * 2 +
    [MIRROR_FORCE] * 2 +
    [SAKURETSU_ARMOR] * 2 +
    [RING_OF_DESTRUCTION] * 1 +
    [TORRENTIAL_TRIBUTE] * 1
)
CHAIN_BURN_EXTRA = []

CHAIN_BURN_STRATEGY = {
    'name': 'Chain Burn',
    'archetype': 'Burn / Stall',
    'description': 'Win by direct damage without attacking. Stall with walls and Gravity Bind while burn spells and traps chip away LP. Lava Golem removes 2 threats and burns 1000/turn.',
    'priorities': [
        'Set Stealth Bird and flip it repeatedly for 1000 burn each time',
        'Des Koala punishes large hands — flip when opponent has 4+ cards',
        'Gravity Bind + Messenger of Peace lock out attacks while you burn',
        'Just Desserts and Secret Barrel deal more damage as opponent builds board',
        'Lava Golem: give to opponent to remove 2 monsters AND burn 1000/turn',
        'Magic Cylinder reflects attack damage — devastating vs high ATK monsters',
        'Ring of Destruction on opponent\'s biggest monster for instant burn damage',
        'DO NOT summon big monsters — your win condition is burn, not battle',
        'Set Marshmallon as an indestructible wall that burns 1000 when flipped',
    ],
    'summon_priority': [],  # Don't Normal Summon aggressively
    'set_priority': ['Stealth Bird', 'Des Koala', 'Marshmallon', 'Giant Germ'],
}


# =============================================================================
# DECK 4: Dragon Beatdown
# =============================================================================

RED_EYES_BLACK_DRAGON = make_ygo_monster(
    "Red-Eyes Black Dragon", atk=2400, def_val=2000, level=7,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Dragon"},
    text="A ferocious dragon with a deadly attack.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/74677422.jpg",
)

from src.cards.yugioh.ygo_classic import BLUE_EYES_WHITE_DRAGON

ARMED_DRAGON_LV5 = make_ygo_monster(
    "Armed Dragon LV5", atk=2400, def_val=1700, level=5,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon"},
    text="Discard 1 monster; destroy 1 face-up monster with ATK <= discarded monster's ATK.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/46384672.jpg",
)

ARMED_DRAGON_LV7 = make_ygo_monster(
    "Armed Dragon LV7", atk=2800, def_val=1000, level=7,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon"},
    text="Discard 1 monster; destroy all face-up monsters with ATK <= discarded monster's ATK.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/73879377.jpg",
)

MASKED_DRAGON = make_ygo_monster(
    "Masked Dragon", atk=1400, def_val=1100, level=3,
    attribute="FIRE", ygo_monster_type="Effect",
    subtypes={"Dragon"},
    text="When destroyed by battle: Special Summon 1 Dragon with 1500 or less ATK from your Deck.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/39191307.jpg",
)

LUSTER_DRAGON = make_ygo_monster(
    "Luster Dragon", atk=1900, def_val=1600, level=4,
    attribute="WIND", ygo_monster_type="Normal",
    subtypes={"Dragon"},
    text="A very beautiful dragon covered with sapphire.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/11091375.jpg",
)

SPEAR_DRAGON = make_ygo_monster(
    "Spear Dragon", atk=1900, def_val=0, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon"},
    text="Piercing battle damage. After it attacks, change to Defense Position.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/31553716.jpg",
)

CAVE_DRAGON = make_ygo_monster(
    "Cave Dragon", atk=2000, def_val=100, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon"},
    text="Cannot attack unless you control another Dragon.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/93220472.jpg",
)

def _stamping_destruction_resolve(event, state):
    """Destroy 1 S/T and inflict 500 damage (if you control a Dragon)."""
    events = []
    target_id = (event.payload.get('targets') or [None])[0]
    pid = event.payload.get('player')
    if target_id:
        events.extend(destroy_spell_trap(state, target_id))
    if pid:
        for opp_id in state.players:
            if opp_id != pid:
                player = state.players.get(opp_id)
                if player:
                    player.lp = max(0, player.lp - 500)
                    events.append(Event(type=EventType.YGO_LP_CHANGE,
                                        payload={'player': opp_id, 'amount': -500,
                                                 'source': 'Stamping Destruction'}))
                    if player.lp <= 0:
                        player.has_lost = True
    return events

STAMPING_DESTRUCTION = make_ygo_spell(
    "Stamping Destruction", ygo_spell_type="Normal",
    text="If you control a Dragon: Destroy 1 Spell/Trap and inflict 500 damage.",
    resolve=_stamping_destruction_resolve,
    image_url="https://images.ygoprodeck.com/images/cards_cropped/81385346.jpg",
)

DRAGONS_MIRROR = make_ygo_spell(
    "Dragon's Mirror", ygo_spell_type="Normal",
    text="Fusion Summon 1 Dragon Fusion Monster, banishing materials from field or GY.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/71490127.jpg",
)

MOUNTAIN = make_ygo_spell(
    "Mountain", ygo_spell_type="Field",
    text="All Dragon, Winged Beast, and Thunder monsters gain 200 ATK/DEF.",
    image_url="https://images.ygoprodeck.com/images/cards_cropped/50913601.jpg",
)

DRAGON_BEATDOWN_DECK = (
    # Dragons (20)
    [BLUE_EYES_WHITE_DRAGON] * 2 +
    [RED_EYES_BLACK_DRAGON] * 2 +
    [ARMED_DRAGON_LV7] * 1 +
    [ARMED_DRAGON_LV5] * 2 +
    [LUSTER_DRAGON] * 3 +
    [SPEAR_DRAGON] * 2 +
    [CAVE_DRAGON] * 2 +
    [MASKED_DRAGON] * 3 +
    [SANGAN] * 1 +
    [MAN_EATER_BUG] * 1 +
    [DD_WARRIOR_LADY] * 1 +
    # Spells (12)
    [STAMPING_DESTRUCTION] * 2 +
    [MOUNTAIN] * 1 +
    [POT_OF_GREED] * 1 +
    [HEAVY_STORM] * 1 +
    [DARK_HOLE] * 1 +
    [MONSTER_REBORN] * 1 +
    [PREMATURE_BURIAL] * 1 +
    [MYSTICAL_SPACE_TYPHOON] * 1 +
    [RAIGEKI] * 1 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 +
    [NOBLEMAN_OF_CROSSOUT] * 1 +
    # Traps (8)
    [MIRROR_FORCE] * 1 +
    [TORRENTIAL_TRIBUTE] * 1 +
    [SAKURETSU_ARMOR] * 2 +
    [CALL_OF_THE_HAUNTED] * 1 +
    [BOTTOMLESS_TRAP_HOLE] * 1 +
    [RING_OF_DESTRUCTION] * 1 +
    [SOLEMN_JUDGMENT] * 1
)
DRAGON_BEATDOWN_EXTRA = []

DRAGON_BEATDOWN_STRATEGY = {
    'name': 'Dragon Beatdown',
    'archetype': 'Beatdown / Aggro',
    'description': 'Overwhelm with massive Dragon monsters. Masked Dragon chains into bigger Dragons. Blue-Eyes and Red-Eyes are your finishers. Stamping Destruction is Dragon-exclusive S/T removal with burn.',
    'priorities': [
        'Summon Luster Dragon or Spear Dragon for immediate 1900 ATK pressure',
        'Cave Dragon is 2000 ATK but needs another Dragon on field — pair with Masked Dragon',
        'Masked Dragon is ideal tribute fodder — when destroyed, it searches another Dragon',
        'Tribute Summon Armed Dragon LV5 (1 tribute) or Blue-Eyes/Red-Eyes (2 tributes)',
        'Stamping Destruction destroys backrow AND deals 500 burn — use with Dragons on field',
        'Mountain boosts all Dragons by 200 ATK/DEF — makes Luster Dragon 2100 ATK',
        'Monster Reborn / Call of the Haunted to revive Blue-Eyes or Red-Eyes from GY',
        'Attack aggressively — this deck wins through battle damage, not grinding',
    ],
    'summon_priority': ['Luster Dragon', 'Spear Dragon', 'Cave Dragon', 'Armed Dragon LV5',
                        'Blue-Eyes White Dragon', 'Red-Eyes Black Dragon', 'Armed Dragon LV7'],
    'set_priority': ['Man-Eater Bug', 'Masked Dragon', 'Sangan'],
}


# =============================================================================
# Card Registry
# =============================================================================

YGO_OPTIMIZED_CARDS = {}
for card in [
    # Shared staples
    POT_OF_GREED, GRACEFUL_CHARITY, HEAVY_STORM, RAIGEKI, PREMATURE_BURIAL,
    NOBLEMAN_OF_CROSSOUT, TORRENTIAL_TRIBUTE, BOTTOMLESS_TRAP_HOLE, DIMENSIONAL_PRISON,
    # Goat Control
    BLACK_LUSTER_SOLDIER, AIRKNIGHT_PARSHATH, TRIBE_INFECTING_VIRUS, SINISTER_SERPENT,
    DD_WARRIOR_LADY, SANGAN, MYSTIC_TOMATO, DEKOICHI, SPIRIT_REAPER, SNATCH_STEAL,
    # Monarch
    MOBIUS_THE_FROST_MONARCH, THESTALOS_THE_FIRESTORM_MONARCH, ZABORG_THE_THUNDER_MONARCH,
    CAIUS_THE_SHADOW_MONARCH, TREEBORN_FROG, SOUL_EXCHANGE, BRAIN_CONTROL, ENEMY_CONTROLLER,
    CYBER_DRAGON, GRAVEKEEPER_SPY,
    # Chain Burn
    LAVA_GOLEM, STEALTH_BIRD, DES_KOALA, MARSHMALLON, GIANT_GERM,
    OOKAZI, WAVE_MOTION_CANNON, MESSENGER_OF_PEACE, LEVEL_LIMIT_AREA_B,
    GRAVITY_BIND, JUST_DESSERTS, SECRET_BARREL,
    # Dragon Beatdown
    RED_EYES_BLACK_DRAGON, ARMED_DRAGON_LV5, ARMED_DRAGON_LV7, MASKED_DRAGON,
    LUSTER_DRAGON, SPEAR_DRAGON, CAVE_DRAGON, STAMPING_DESTRUCTION, DRAGONS_MIRROR, MOUNTAIN,
]:
    YGO_OPTIMIZED_CARDS[card.name] = card


# =============================================================================
# Deck + Strategy Registry
# =============================================================================

YGO_OPTIMIZED_DECKS = {
    'goat_control': {
        'deck': GOAT_CONTROL_DECK,
        'extra': GOAT_CONTROL_EXTRA,
        'strategy': GOAT_CONTROL_STRATEGY,
    },
    'monarch_control': {
        'deck': MONARCH_DECK,
        'extra': MONARCH_EXTRA,
        'strategy': MONARCH_STRATEGY,
    },
    'chain_burn': {
        'deck': CHAIN_BURN_DECK,
        'extra': CHAIN_BURN_EXTRA,
        'strategy': CHAIN_BURN_STRATEGY,
    },
    'dragon_beatdown': {
        'deck': DRAGON_BEATDOWN_DECK,
        'extra': DRAGON_BEATDOWN_EXTRA,
        'strategy': DRAGON_BEATDOWN_STRATEGY,
    },
}
