"""
Yu-Gi-Oh! Generic Starter Set

~35 balanced cards for testing all mechanics:
- Normal Monsters (L1-L7)
- Effect Monsters (flip, ignition, trigger, tuner)
- Spells (Normal, Quick-Play, Continuous, Equip, Field, Ritual)
- Traps (Normal, Continuous, Counter)
- Extra Deck (Fusion, Synchro, Xyz)
- Ritual Monster

Two 40-card decks: WARRIOR_DECK and SPELLCASTER_DECK
"""

from src.engine.game import make_ygo_monster, make_ygo_spell, make_ygo_trap
from src.engine.types import Event, EventType, GameState, ZoneType
from src.engine.yugioh_helpers import (
    destroy_all_monsters, destroy_attacking_monsters,
    revive_from_graveyard, destroy_spell_trap,
)


# =============================================================================
# Normal Monsters
# =============================================================================

BATTLE_OX = make_ygo_monster(
    "Battle Ox", atk=1700, def_val=1000, level=4,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Beast-Warrior"}, text="A monster with tremendous power.",
)

GIANT_SOLDIER = make_ygo_monster(
    "Giant Soldier of Stone", atk=1300, def_val=2000, level=3,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Rock"}, text="A huge soldier made of stone.",
)

MYSTICAL_ELF = make_ygo_monster(
    "Mystical Elf", atk=800, def_val=2000, level=4,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Spellcaster"}, text="A protector who chants spells of defense.",
)

DARK_BLADE = make_ygo_monster(
    "Dark Blade", atk=1800, def_val=1500, level=4,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Warrior"}, text="A warrior cloaked in darkness.",
)

ALEXANDRITE_DRAGON = make_ygo_monster(
    "Alexandrite Dragon", atk=2000, def_val=100, level=4,
    attribute="LIGHT", ygo_monster_type="Normal",
    subtypes={"Dragon"}, text="A radiant dragon.",
)

GENE_WARPED_WARWOLF = make_ygo_monster(
    "Gene-Warped Warwolf", atk=2000, def_val=100, level=4,
    attribute="EARTH", ygo_monster_type="Normal",
    subtypes={"Beast-Warrior"}, text="A powerful warped beast.",
)

LUSTER_DRAGON = make_ygo_monster(
    "Luster Dragon", atk=1900, def_val=1600, level=4,
    attribute="WIND", ygo_monster_type="Normal",
    subtypes={"Dragon"}, text="A beautiful dragon with sparkling scales.",
)

VORSE_RAIDER = make_ygo_monster(
    "Vorse Raider", atk=1900, def_val=1200, level=4,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Beast-Warrior"}, text="A vicious raider.",
)

SUMMONED_SKULL = make_ygo_monster(
    "Summoned Skull", atk=2500, def_val=1200, level=6,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A powerful fiend requiring one tribute.",
)

COSMO_QUEEN = make_ygo_monster(
    "Cosmo Queen", atk=2900, def_val=2450, level=8,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Spellcaster"}, text="Queen of the cosmos, requiring two tributes.",
)

KURIBOH_TOKEN = make_ygo_monster(
    "Kuriboh Token", atk=300, def_val=200, level=1,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A small but brave creature.",
)

SANGAN_SCOUT = make_ygo_monster(
    "Sangan Scout", atk=1000, def_val=600, level=3,
    attribute="DARK", ygo_monster_type="Normal",
    subtypes={"Fiend"}, text="A three-eyed scout.",
)

# =============================================================================
# Effect Monsters
# =============================================================================

def _man_eater_bug_flip(obj, state):
    """FLIP: Destroy 1 monster on the field."""
    events = []
    for pid in state.players:
        if pid == obj.controller:
            continue
        zone = state.zones.get(f"monster_zone_{pid}")
        if not zone:
            continue
        for i, oid in enumerate(zone.objects):
            if oid and oid != obj.id:
                target = state.objects.get(oid)
                if target:
                    zone.objects[i] = None
                    gy = state.zones.get(f"graveyard_{target.owner}")
                    if gy:
                        gy.objects.append(oid)
                    target.zone = ZoneType.GRAVEYARD
                    target.state.face_down = False
                    events.append(Event(type=EventType.YGO_DESTROY,
                                        payload={'card_id': oid, 'card_name': target.name}))
                    return events
    return events

MAN_EATER_BUG = make_ygo_monster(
    "Man-Eater Bug", atk=450, def_val=600, level=2,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Insect"}, text="FLIP: Destroy 1 monster on the field.",
    flip_effect=_man_eater_bug_flip,
)

def _magician_of_faith_flip(obj, state):
    """FLIP: Add 1 Spell from your GY to your hand."""
    events = []
    gy = state.zones.get(f"graveyard_{obj.controller}")
    hand = state.zones.get(f"hand_{obj.controller}")
    if gy and hand:
        for oid in gy.objects:
            spell = state.objects.get(oid)
            if spell and any(t.name == 'YGO_SPELL' for t in spell.characteristics.types):
                gy.objects.remove(oid)
                hand.objects.append(oid)
                spell.zone = ZoneType.HAND
                return events
    return events

MAGICIAN_OF_FAITH = make_ygo_monster(
    "Magician of Faith", atk=300, def_val=400, level=1,
    attribute="LIGHT", ygo_monster_type="Effect",
    subtypes={"Spellcaster"}, text="FLIP: Add 1 Spell from your GY to your hand.",
    flip_effect=_magician_of_faith_flip,
)

SPEAR_DRAGON = make_ygo_monster(
    "Spear Dragon", atk=1900, def_val=0, level=4,
    attribute="WIND", ygo_monster_type="Effect",
    subtypes={"Dragon"}, text="Piercing damage. After attacking, switch to DEF.",
)

BREAKER_THE_MAGICAL_WARRIOR = make_ygo_monster(
    "Breaker the Magical Warrior", atk=1600, def_val=1000, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster", "Warrior"},
    text="Gains 300 ATK on summon. Remove counter to destroy 1 S/T.",
)

EFFECT_VEILER = make_ygo_monster(
    "Effect Veiler", atk=0, def_val=0, level=1,
    attribute="LIGHT", ygo_monster_type="Effect", is_tuner=True,
    subtypes={"Spellcaster"}, text="Tuner. Negate 1 opponent's monster effect (hand trap).",
    spell_speed=2,
)

WITCH_OF_THE_BLACK_FOREST = make_ygo_monster(
    "Witch of the Black Forest", atk=1100, def_val=1200, level=4,
    attribute="DARK", ygo_monster_type="Effect",
    subtypes={"Spellcaster"},
    text="If sent from field to GY: Add 1 monster with 1500 or less DEF from Deck to hand.",
)

MARAUDING_CAPTAIN = make_ygo_monster(
    "Marauding Captain", atk=1200, def_val=400, level=3,
    attribute="EARTH", ygo_monster_type="Effect",
    subtypes={"Warrior"},
    text="When Normal Summoned: Special Summon 1 Level 4 or lower Warrior from hand.",
)

TUNE_WARRIOR = make_ygo_monster(
    "Tune Warrior", atk=1600, def_val=200, level=3,
    attribute="EARTH", ygo_monster_type="Normal", is_tuner=True,
    subtypes={"Warrior"}, text="A warrior who tunes into battle rhythms.",
)

# =============================================================================
# Spells
# =============================================================================

def _dark_hole_resolve(event, state):
    return destroy_all_monsters(state)

DARK_HOLE = make_ygo_spell(
    "Dark Hole", ygo_spell_type="Normal",
    text="Destroy all monsters on the field.",
    resolve=_dark_hole_resolve,
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

SWORDS_OF_REVEALING_LIGHT = make_ygo_spell(
    "Swords of Revealing Light", ygo_spell_type="Continuous",
    text="Opponent's monsters cannot attack for 3 turns.",
)

SWORD_OF_DARK_DESTRUCTION = make_ygo_spell(
    "Sword of Dark Destruction", ygo_spell_type="Equip",
    text="DARK monster gains +400 ATK and -200 DEF.",
)

MOUNTAIN_FIELD = make_ygo_spell(
    "Mountain", ygo_spell_type="Field",
    text="Dragon, Winged Beast, and Thunder gain 200 ATK/DEF.",
)

def _monster_reborn_resolve(event, state):
    targets = event.payload.get('targets', [])
    player_id = event.payload.get('player')
    if targets and player_id:
        return revive_from_graveyard(state, player_id, targets[0])
    return []

MONSTER_REBORN = make_ygo_spell(
    "Monster Reborn", ygo_spell_type="Normal",
    text="Special Summon 1 monster from either GY.",
    resolve=_monster_reborn_resolve,
)

# Ritual Spell
def _ritual_resolve(event, state):
    """Placeholder: actual ritual logic handled by summon manager."""
    return []

BLACK_ILLUSION_RITUAL = make_ygo_spell(
    "Black Illusion Ritual", ygo_spell_type="Ritual",
    text="This card is used to Ritual Summon 'Relinquished'.",
    resolve=_ritual_resolve,
)

# =============================================================================
# Traps
# =============================================================================

def _mirror_force_resolve(event, state):
    controller = event.payload.get('player', '')
    return destroy_attacking_monsters(state, controller)

MIRROR_FORCE = make_ygo_trap(
    "Mirror Force", ygo_trap_type="Normal",
    text="When an opponent's monster attacks: Destroy all ATK-position monsters your opponent controls.",
    resolve=_mirror_force_resolve,
)

def _sakuretsu_resolve(event, state):
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
            gy = state.zones.get(f"graveyard_{obj.owner}")
            if gy:
                gy.objects.append(target_id)
            obj.zone = ZoneType.GRAVEYARD
            return [Event(type=EventType.YGO_DESTROY,
                          payload={'card_id': target_id, 'card_name': obj.name})]
    return []

SAKURETSU_ARMOR = make_ygo_trap(
    "Sakuretsu Armor", ygo_trap_type="Normal",
    text="When an opponent's monster attacks: Destroy that monster.",
    resolve=_sakuretsu_resolve,
)

CALL_OF_THE_HAUNTED = make_ygo_trap(
    "Call of the Haunted", ygo_trap_type="Continuous",
    text="Special Summon 1 monster from your GY. If this card leaves, destroy that monster.",
)

def _solemn_judgment_resolve(event, state):
    """Negate a summon or spell/trap activation (pay half LP)."""
    player_id = event.payload.get('player')
    if player_id:
        player = state.players.get(player_id)
        if player:
            player.lp = player.lp // 2
    return []

SOLEMN_JUDGMENT = make_ygo_trap(
    "Solemn Judgment", ygo_trap_type="Counter",
    text="Pay half LP: Negate a Summon or Spell/Trap activation and destroy it.",
    resolve=_solemn_judgment_resolve,
)

# =============================================================================
# Extra Deck Monsters
# =============================================================================

FLAME_SWORDSMAN_FUSION = make_ygo_monster(
    "Flame Swordsman", atk=1800, def_val=1600, level=5,
    attribute="FIRE", ygo_monster_type="Fusion",
    subtypes={"Warrior"}, text="Fusion of 'Flame Manipulator' + 'Masaki the Legendary Swordsman'.",
    materials="Flame Manipulator + Masaki the Legendary Swordsman",
)

STARDUST_WARRIOR = make_ygo_monster(
    "Stardust Warrior", atk=2500, def_val=2000, level=7,
    attribute="WIND", ygo_monster_type="Synchro",
    subtypes={"Warrior"}, text="1 Tuner + 1+ non-Tuner monsters.",
    materials="1 Tuner + 1+ non-Tuner monsters",
)

UTOPIA_KNIGHT = make_ygo_monster(
    "Utopia Knight", atk=2500, def_val=2000, level=4,
    attribute="LIGHT", ygo_monster_type="Xyz",
    subtypes={"Warrior"}, text="2 Level 4 monsters. Detach 1: Negate an attack.",
)

# Ritual Monster
RELINQUISHED = make_ygo_monster(
    "Relinquished", atk=0, def_val=0, level=1,
    attribute="DARK", ygo_monster_type="Ritual",
    subtypes={"Spellcaster"},
    text="Equipped with 1 opponent's monster. Gains that monster's ATK/DEF.",
)


# =============================================================================
# Card Registry
# =============================================================================

YGO_STARTER_CARDS = {card.name: card for card in [
    BATTLE_OX, GIANT_SOLDIER, MYSTICAL_ELF, DARK_BLADE, ALEXANDRITE_DRAGON,
    GENE_WARPED_WARWOLF, LUSTER_DRAGON, VORSE_RAIDER, SUMMONED_SKULL, COSMO_QUEEN,
    KURIBOH_TOKEN, SANGAN_SCOUT,
    MAN_EATER_BUG, MAGICIAN_OF_FAITH, SPEAR_DRAGON, BREAKER_THE_MAGICAL_WARRIOR,
    EFFECT_VEILER, WITCH_OF_THE_BLACK_FOREST, MARAUDING_CAPTAIN, TUNE_WARRIOR,
    DARK_HOLE, MYSTICAL_SPACE_TYPHOON, SWORDS_OF_REVEALING_LIGHT,
    SWORD_OF_DARK_DESTRUCTION, MOUNTAIN_FIELD, MONSTER_REBORN, BLACK_ILLUSION_RITUAL,
    MIRROR_FORCE, SAKURETSU_ARMOR, CALL_OF_THE_HAUNTED, SOLEMN_JUDGMENT,
    FLAME_SWORDSMAN_FUSION, STARDUST_WARRIOR, UTOPIA_KNIGHT, RELINQUISHED,
]}


# =============================================================================
# Pre-built Decks (40 cards each)
# =============================================================================

WARRIOR_DECK = (
    [DARK_BLADE] * 3 + [BATTLE_OX] * 3 + [VORSE_RAIDER] * 3 +
    [MARAUDING_CAPTAIN] * 2 + [TUNE_WARRIOR] * 2 + [GENE_WARPED_WARWOLF] * 2 +
    [SUMMONED_SKULL] * 2 + [KURIBOH_TOKEN] * 2 + [SANGAN_SCOUT] * 2 +
    [MAN_EATER_BUG] * 2 + [GIANT_SOLDIER] * 1 +
    [DARK_HOLE] * 1 + [MONSTER_REBORN] * 1 + [MYSTICAL_SPACE_TYPHOON] * 2 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 + [SWORD_OF_DARK_DESTRUCTION] * 2 +
    [MOUNTAIN_FIELD] * 1 +
    [MIRROR_FORCE] * 2 + [SAKURETSU_ARMOR] * 2 + [CALL_OF_THE_HAUNTED] * 1 +
    [SOLEMN_JUDGMENT] * 2 + [LUSTER_DRAGON] * 1
)
WARRIOR_EXTRA_DECK = [FLAME_SWORDSMAN_FUSION, STARDUST_WARRIOR, UTOPIA_KNIGHT]

SPELLCASTER_DECK = (
    [MYSTICAL_ELF] * 3 + [MAGICIAN_OF_FAITH] * 3 + [BREAKER_THE_MAGICAL_WARRIOR] * 3 +
    [WITCH_OF_THE_BLACK_FOREST] * 2 + [EFFECT_VEILER] * 2 + [ALEXANDRITE_DRAGON] * 2 +
    [LUSTER_DRAGON] * 2 + [COSMO_QUEEN] * 1 + [GIANT_SOLDIER] * 2 +
    [KURIBOH_TOKEN] * 2 + [SANGAN_SCOUT] * 1 +
    [DARK_HOLE] * 1 + [MONSTER_REBORN] * 1 + [MYSTICAL_SPACE_TYPHOON] * 2 +
    [SWORDS_OF_REVEALING_LIGHT] * 1 + [BLACK_ILLUSION_RITUAL] * 1 +
    [SWORD_OF_DARK_DESTRUCTION] * 1 + [MOUNTAIN_FIELD] * 1 +
    [MIRROR_FORCE] * 2 + [SAKURETSU_ARMOR] * 2 + [SOLEMN_JUDGMENT] * 2 +
    [CALL_OF_THE_HAUNTED] * 1 + [RELINQUISHED] * 1 + [MAN_EATER_BUG] * 1
)
SPELLCASTER_EXTRA_DECK = [FLAME_SWORDSMAN_FUSION, STARDUST_WARRIOR, UTOPIA_KNIGHT]
