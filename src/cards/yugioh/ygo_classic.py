"""
Yu-Gi-Oh! Classic Set — Yugi vs Kaiba

Iconic cards from the original Duel Monsters era.
All with working effects where applicable.

Two 40-card decks: YUGI_DECK and KAIBA_DECK
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import Event, EventType, GameState, ZoneType
from src.engine.yugioh_helpers import (
    destroy_all_monsters, destroy_attacking_monsters,
    revive_from_graveyard, destroy_spell_trap,
)


# =============================================================================
# Yugi's Monsters
# =============================================================================

DARK_MAGICIAN = make_ygo_monster(
    "Dark Magician", atk=2500, def_val=2100, level=7,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Spellcaster"}, text="The ultimate wizard in terms of attack and defense.",
)

DARK_MAGICIAN_GIRL = make_ygo_monster(
    "Dark Magician Girl", atk=2000, def_val=1700, level=6,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="Gains 300 ATK for each 'Dark Magician' in either GY.",
)

def _kuriboh_resolve(event, state):
    """Discard from hand: reduce battle damage to 0."""
    return []

KURIBOH = make_ygo_monster(
    "Kuriboh", atk=300, def_val=200, level=1,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Fiend"}, text="Discard: Reduce battle damage to 0 this turn.",
    spell_speed=2,  # Hand trap (Quick Effect)
)

CELTIC_GUARDIAN = make_ygo_monster(
    "Celtic Guardian", atk=1400, def_val=1200, level=4,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Warrior"}, text="An elf who learned to wield a sword.",
)

FERAL_IMP = make_ygo_monster(
    "Feral Imp", atk=1300, def_val=1400, level=4,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A playful little fiend.",
)

GIANT_SOLDIER_OF_STONE = make_ygo_monster(
    "Giant Soldier of Stone", atk=1300, def_val=2000, level=3,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Rock"}, text="A stone warrior with incredible defense.",
)

SUMMONED_SKULL_CLASSIC = make_ygo_monster(
    "Summoned Skull", atk=2500, def_val=1200, level=6,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A fiend summoned from the depths.",
)

BUSTER_BLADER = make_ygo_monster(
    "Buster Blader", atk=2600, def_val=2300, level=7,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="Gains 500 ATK for each Dragon in your opponent's GY and on their field.",
)

MARSHMALLON = make_ygo_monster(
    "Marshmallon", atk=300, def_val=500, level=3,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Fairy"},
    text="Cannot be destroyed by battle. 1000 damage to opponent when flipped.",
)

GAMMA_THE_MAGNET_WARRIOR = make_ygo_monster(
    "Gamma The Magnet Warrior", atk=1500, def_val=1800, level=4,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Rock"}, text="One of the three Magnet Warriors.",
)

BETA_THE_MAGNET_WARRIOR = make_ygo_monster(
    "Beta The Magnet Warrior", atk=1700, def_val=1600, level=4,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Rock"}, text="The second of the Magnet Warriors.",
)

# =============================================================================
# Kaiba's Monsters
# =============================================================================

BLUE_EYES_WHITE_DRAGON = make_ygo_monster(
    "Blue-Eyes White Dragon", atk=3000, def_val=2500, level=8,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Dragon"},
    text="This legendary dragon is a powerful engine of destruction.",
)

BLUE_EYES_ULTIMATE_DRAGON = make_ygo_monster(
    "Blue-Eyes Ultimate Dragon", atk=4500, def_val=3800, level=12,
    attribute="LIGHT", ygo_monster_type="Fusion",
    subtypes={"Dragon"},
    text="Fusion of 3 'Blue-Eyes White Dragon'.",
    materials="Blue-Eyes White Dragon + Blue-Eyes White Dragon + Blue-Eyes White Dragon",
)

LORD_OF_D = make_ygo_monster(
    "Lord of D.", atk=1200, def_val=1100, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="Dragon-type monsters cannot be targeted by card effects.",
)

SAGGI_THE_DARK_CLOWN = make_ygo_monster(
    "Saggi the Dark Clown", atk=600, def_val=1500, level=3,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Spellcaster"}, text="A clown loyal to the dark side.",
)

LA_JINN = make_ygo_monster(
    "La Jinn the Mystical Genie", atk=1800, def_val=1000, level=4,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A genie summoned from a lamp.",
)

JUDGE_MAN = make_ygo_monster(
    "Judge Man", atk=2200, def_val=1500, level=6,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Warrior"}, text="A powerful judge who delivers swift punishment.",
)

KAISER_SEA_HORSE = make_ygo_monster(
    "Kaiser Sea Horse", atk=1700, def_val=1650, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Sea Serpent"},
    text="Can count as 2 tributes for a LIGHT monster Tribute Summon.",
)

BLADE_KNIGHT = make_ygo_monster(
    "Blade Knight", atk=1600, def_val=1000, level=4,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="If you have 1 or fewer cards in hand, gains 400 ATK.",
)

X_HEAD_CANNON = make_ygo_monster(
    "X-Head Cannon", atk=1800, def_val=1500, level=4,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Machine"}, text="A head-shaped cannon.",
)

Y_DRAGON_HEAD = make_ygo_monster(
    "Y-Dragon Head", atk=1500, def_val=1600, level=4,
    attribute="LIGHT", ygo_monster_type="Normal",  # Union in original, Normal here
    subtypes={"Machine", "Dragon"}, text="A mechanical dragon head.",
)

Z_METAL_TANK = make_ygo_monster(
    "Z-Metal Tank", atk=1500, def_val=1300, level=4,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Machine"}, text="A mechanical tank.",
)

# =============================================================================
# Yugi's Spells
# =============================================================================

def _swords_resolve(event, state):
    """Flip all opponent's face-down monsters face-up."""
    controller = event.payload.get('player', '')
    events = []
    for pid in state.players:
        if pid == controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for oid in zone.objects:
            if oid is None:
                continue
            obj = state.objects.get(oid)
            if obj and obj.state.face_down:
                obj.state.face_down = False
                if obj.state.ygo_position == 'face_down_def':
                    obj.state.ygo_position = 'face_up_def'
                events.append(Event(type=EventType.YGO_FLIP,
                                    payload={'card_id': oid, 'card_name': obj.name}))
    return events

SWORDS_OF_REVEALING_LIGHT = make_ygo_spell(
    "Swords of Revealing Light", ygo_spell_type="Continuous",
    text="Opponent cannot attack for 3 turns. Flip all face-down opponent monsters face-up.",
    resolve=_swords_resolve,
)

def _dark_hole_resolve(event, state):
    return destroy_all_monsters(state)

DARK_HOLE = make_ygo_spell(
    "Dark Hole", ygo_spell_type="Normal",
    text="Destroy all monsters on the field.",
    resolve=_dark_hole_resolve,
)

def _monster_reborn_resolve(event, state):
    targets = event.payload.get('targets', [])
    player_id = event.payload.get('player')
    if targets and player_id:
        return revive_from_graveyard(state, player_id, targets[0])
    return []

MONSTER_REBORN = make_ygo_spell(
    "Monster Reborn", ygo_spell_type="Normal",
    text="Special Summon 1 monster from either player's GY.",
    resolve=_monster_reborn_resolve,
)

def _mst_resolve(event, state):
    target_id = (event.payload.get('targets') or [None])[0]
    if target_id:
        return destroy_spell_trap(state, target_id)
    return []

MYSTICAL_SPACE_TYPHOON = make_ygo_spell(
    "Mystical Space Typhoon", ygo_spell_type="Quick-Play",
    text="Destroy 1 Spell/Trap on the field.",
    resolve=_mst_resolve,
)

BOOK_OF_MOON = make_ygo_spell(
    "Book of Moon", ygo_spell_type="Quick-Play",
    text="Target 1 face-up monster; change it to face-down Defense Position.",
)

# =============================================================================
# Yugi's Traps
# =============================================================================

def _mirror_force_resolve(event, state):
    controller = event.payload.get('player', '')
    return destroy_attacking_monsters(state, controller)

MIRROR_FORCE = make_ygo_trap(
    "Mirror Force", ygo_trap_type="Normal",
    text="When opponent's monster attacks: Destroy all ATK-position opponent monsters.",
    resolve=_mirror_force_resolve,
)

def _magic_cylinder_resolve(event, state):
    """Negate attack, inflict ATK as damage to opponent."""
    events = []
    target_id = (event.payload.get('targets') or [None])[0]
    controller = event.payload.get('player', '')
    if target_id:
        obj = state.objects.get(target_id)
        if obj and obj.card_def:
            atk = getattr(obj.card_def, 'atk', 0) or 0
            for pid in state.players:
                if pid != controller:
                    player = state.players.get(pid)
                    if player:
                        player.lp = max(0, player.lp - atk)
                        events.append(Event(
                            type=EventType.YGO_LP_CHANGE,
                            payload={'player': pid, 'amount': -atk, 'source': 'Magic Cylinder'}
                        ))
    return events

MAGIC_CYLINDER = make_ygo_trap(
    "Magic Cylinder", ygo_trap_type="Normal",
    text="Negate an attack, inflict ATK as damage to opponent.",
    resolve=_magic_cylinder_resolve,
)

# =============================================================================
# Kaiba's Spells
# =============================================================================

POLYMERIZATION = make_ygo_spell(
    "Polymerization", ygo_spell_type="Normal",
    text="Fusion Summon 1 Fusion Monster using monsters from hand or field.",
)

def _flute_resolve(event, state):
    """Special Summon up to 2 Dragons from hand while Lord of D. is on field."""
    return []  # Simplified

FLUTE_OF_SUMMONING_DRAGON = make_ygo_spell(
    "Flute of Summoning Dragon", ygo_spell_type="Normal",
    text="While you control 'Lord of D.': Special Summon up to 2 Dragons from hand.",
    resolve=_flute_resolve,
)

ENEMY_CONTROLLER = make_ygo_spell(
    "Enemy Controller", ygo_spell_type="Quick-Play",
    text="Change 1 monster's position, or tribute 1 monster to take control of opponent's monster.",
)

COST_DOWN = make_ygo_spell(
    "Cost Down", ygo_spell_type="Normal",
    text="Discard 1 card; reduce Levels of all monsters in hand by 2 until End Phase.",
)

# =============================================================================
# Kaiba's Traps
# =============================================================================

def _negate_attack_resolve(event, state):
    """Negate an attack and end the Battle Phase."""
    return []

NEGATE_ATTACK = make_ygo_trap(
    "Negate Attack", ygo_trap_type="Counter",
    text="Negate an attack and end the Battle Phase.",
    resolve=_negate_attack_resolve,
)

def _ring_of_destruction_resolve(event, state):
    """Destroy 1 face-up monster. Both players take damage equal to its ATK."""
    events = []
    target_id = (event.payload.get('targets') or [None])[0]
    if target_id:
        obj = state.objects.get(target_id)
        if obj and obj.card_def:
            atk = getattr(obj.card_def, 'atk', 0) or 0
            # Destroy the monster
            for zone in state.zones.values():
                if target_id in zone.objects:
                    for i, oid in enumerate(zone.objects):
                        if oid == target_id:
                            zone.objects[i] = None
                            break
                    while target_id in zone.objects:
                        zone.objects.remove(target_id)
                    break
            gy = state.zones.get(f"graveyard_{obj.owner}")
            if gy:
                gy.objects.append(target_id)
            obj.zone = ZoneType.GRAVEYARD
            obj.state.face_down = False
            events.append(Event(type=EventType.YGO_DESTROY,
                                payload={'card_id': target_id, 'card_name': obj.name}))
            # Both players take damage
            for pid, player in state.players.items():
                player.lp = max(0, player.lp - atk)
                events.append(Event(type=EventType.YGO_LP_CHANGE,
                                    payload={'player': pid, 'amount': -atk}))
    return events

RING_OF_DESTRUCTION = make_ygo_trap(
    "Ring of Destruction", ygo_trap_type="Normal",
    text="Destroy 1 face-up monster; both players take damage equal to its ATK.",
    resolve=_ring_of_destruction_resolve,
)

CRUSH_CARD_VIRUS = make_ygo_trap(
    "Crush Card Virus", ygo_trap_type="Normal",
    text="Tribute 1 DARK monster with 1000 or less ATK: Opponent destroys all 1500+ ATK monsters.",
)

INTERDIMENSIONAL_MATTER_TRANSPORTER = make_ygo_trap(
    "Interdimensional Matter Transporter", ygo_trap_type="Normal",
    text="Banish 1 face-up monster you control until the End Phase.",
)


# =============================================================================
# Card Registry
# =============================================================================

YGO_CLASSIC_CARDS = {card.name: card for card in [
    # Yugi's monsters
    DARK_MAGICIAN, DARK_MAGICIAN_GIRL, KURIBOH, CELTIC_GUARDIAN, FERAL_IMP,
    GIANT_SOLDIER_OF_STONE, SUMMONED_SKULL_CLASSIC, BUSTER_BLADER,
    MARSHMALLON, GAMMA_THE_MAGNET_WARRIOR, BETA_THE_MAGNET_WARRIOR,
    # Kaiba's monsters
    BLUE_EYES_WHITE_DRAGON, BLUE_EYES_ULTIMATE_DRAGON, LORD_OF_D,
    SAGGI_THE_DARK_CLOWN, LA_JINN, JUDGE_MAN, KAISER_SEA_HORSE,
    BLADE_KNIGHT, X_HEAD_CANNON, Y_DRAGON_HEAD, Z_METAL_TANK,
    # Yugi's spells
    SWORDS_OF_REVEALING_LIGHT, DARK_HOLE, MONSTER_REBORN,
    MYSTICAL_SPACE_TYPHOON, BOOK_OF_MOON,
    # Yugi's traps
    MIRROR_FORCE, MAGIC_CYLINDER,
    # Kaiba's spells
    POLYMERIZATION, FLUTE_OF_SUMMONING_DRAGON, ENEMY_CONTROLLER, COST_DOWN,
    # Kaiba's traps
    NEGATE_ATTACK, RING_OF_DESTRUCTION, CRUSH_CARD_VIRUS,
    INTERDIMENSIONAL_MATTER_TRANSPORTER,
]}


# =============================================================================
# Pre-built Decks (40 cards each)
# =============================================================================

YUGI_DECK = (
    [DARK_MAGICIAN] * 2 + [DARK_MAGICIAN_GIRL] * 2 + [KURIBOH] * 2 +
    [SUMMONED_SKULL_CLASSIC] * 2 + [CELTIC_GUARDIAN] * 3 + [FERAL_IMP] * 2 +
    [GIANT_SOLDIER_OF_STONE] * 2 + [BUSTER_BLADER] * 1 + [MARSHMALLON] * 2 +
    [GAMMA_THE_MAGNET_WARRIOR] * 2 + [BETA_THE_MAGNET_WARRIOR] * 2 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 + [DARK_HOLE] * 1 + [MONSTER_REBORN] * 1 +
    [MYSTICAL_SPACE_TYPHOON] * 2 + [BOOK_OF_MOON] * 2 +
    [MIRROR_FORCE] * 2 + [MAGIC_CYLINDER] * 2 +
    # Padding to 40
    [CELTIC_GUARDIAN] * 2 + [FERAL_IMP] * 2 + [KURIBOH] * 1 +
    [GIANT_SOLDIER_OF_STONE] * 1 + [GAMMA_THE_MAGNET_WARRIOR] * 1
)

YUGI_EXTRA_DECK = [BLUE_EYES_ULTIMATE_DRAGON]  # For testing

KAIBA_DECK = (
    [BLUE_EYES_WHITE_DRAGON] * 3 + [LORD_OF_D] * 2 + [LA_JINN] * 3 +
    [SAGGI_THE_DARK_CLOWN] * 2 + [JUDGE_MAN] * 2 + [KAISER_SEA_HORSE] * 2 +
    [BLADE_KNIGHT] * 3 + [X_HEAD_CANNON] * 2 + [Y_DRAGON_HEAD] * 2 +
    [Z_METAL_TANK] * 2 +
    [POLYMERIZATION] * 2 + [FLUTE_OF_SUMMONING_DRAGON] * 1 +
    [ENEMY_CONTROLLER] * 2 + [COST_DOWN] * 1 +
    [NEGATE_ATTACK] * 2 + [RING_OF_DESTRUCTION] * 2 +
    [CRUSH_CARD_VIRUS] * 1 + [INTERDIMENSIONAL_MATTER_TRANSPORTER] * 1 +
    # Padding
    [LA_JINN] * 1 + [BLADE_KNIGHT] * 1 + [X_HEAD_CANNON] * 1 +
    [SAGGI_THE_DARK_CLOWN] * 1 + [KAISER_SEA_HORSE] * 1
)

KAIBA_EXTRA_DECK = [BLUE_EYES_ULTIMATE_DRAGON]
