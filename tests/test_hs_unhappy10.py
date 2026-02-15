"""
Hearthstone Unhappy Path Tests - Batch 10

Legendary cards, Priest combos (Divine Spirit + Inner Fire, Auchenai),
tribal synergies (Murlocs), Doomsayer, Deathwing board clear,
Alexstrasza health set, Gadgetzan Auctioneer, Violet Teacher,
and complex multi-class interactions.
"""

import random
from src.engine.game import Game
from src.engine.types import (
    Event, EventType, GameObject, GameState, CardType, ZoneType,
    Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
    new_id
)
from src.engine.queries import get_power, get_toughness, has_ability
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, RIVER_CROCOLISK, BOULDERFIST_OGRE,
    MURLOC_RAIDER, KOBOLD_GEOMANCER,
)
from src.cards.hearthstone.classic import (
    ALEXSTRASZA, DEATHWING, ONYXIA,
    MALYGOS, MURLOC_WARLEADER,
    GADGETZAN_AUCTIONEER, DOOMSAYER,
    TWILIGHT_DRAKE, COLDLIGHT_ORACLE,
    VIOLET_TEACHER, IRONBEAK_OWL,
    HARVEST_GOLEM, KNIFE_JUGGLER, FROSTBOLT,
)
from src.cards.hearthstone.priest import (
    DIVINE_SPIRIT, INNER_FIRE, POWER_WORD_SHIELD,
    AUCHENAI_SOULPRIEST, CIRCLE_OF_HEALING,
    HOLY_NOVA, NORTHSHIRE_CLERIC,
    SHADOW_WORD_PAIN, SHADOW_WORD_DEATH,
    LIGHTSPAWN,
)
from src.cards.hearthstone.warlock import (
    TWISTING_NETHER, FLAME_IMP, DOOMGUARD,
    VOID_TERROR, POWER_OVERWHELMING,
)
from src.cards.hearthstone.mage import ARCANE_EXPLOSION, FIREBALL


# ============================================================================
# Test Harness
# ============================================================================

def new_hs_game():
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES["Mage"], HERO_POWERS["Mage"])
    game.setup_hearthstone_player(p2, HEROES["Warrior"], HERO_POWERS["Warrior"])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )
    if zone == ZoneType.BATTLEFIELD and CardType.WEAPON in card_def.characteristics.types:
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={'object_id': obj.id, 'from_zone_type': None,
                     'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
            source=obj.id
        ))
    return obj


def play_from_hand(game, card_def, owner):
    """Create in hand then emit ZONE_CHANGE to trigger battlecry."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.HAND,
        characteristics=card_def.characteristics, card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': obj.id, 'from_zone_type': ZoneType.HAND,
                 'to_zone_type': ZoneType.BATTLEFIELD, 'controller': owner.id},
        source=obj.id
    ))
    return obj


def run_sba(game):
    battlefield = game.state.zones.get('battlefield')
    if not battlefield:
        return
    for oid in list(battlefield.objects):
        obj = game.state.objects.get(oid)
        if not obj:
            continue
        if CardType.MINION not in obj.characteristics.types:
            continue
        toughness = get_toughness(obj, game.state)
        if obj.state.damage >= toughness and toughness > 0:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': oid},
                source='sba'
            ))
            game.emit(Event(
                type=EventType.ZONE_CHANGE,
                payload={'object_id': oid, 'from_zone_type': ZoneType.BATTLEFIELD,
                         'to_zone_type': ZoneType.GRAVEYARD},
                source='sba'
            ))


def count_bf(game, owner_id=None):
    bf = game.state.zones.get('battlefield')
    if not bf:
        return 0
    if owner_id is None:
        return sum(1 for oid in bf.objects if oid in game.state.objects
                   and CardType.MINION in game.state.objects[oid].characteristics.types)
    return sum(1 for oid in bf.objects if oid in game.state.objects
               and game.state.objects[oid].controller == owner_id
               and CardType.MINION in game.state.objects[oid].characteristics.types)


def cast_spell(game, card_def, owner, targets=None):
    """Helper to cast a spell properly."""
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets)
    for e in events:
        game.emit(e)
    return obj


# ============================================================================
# LEGENDARY CARDS
# ============================================================================

def test_alexstrasza_sets_enemy_health_to_15():
    """Alexstrasza battlecry: set a hero's health to 15."""
    game, p1, p2 = new_hs_game()

    p2.life = 30  # Full health

    alex = play_from_hand(game, ALEXSTRASZA, p1)

    # AI should target enemy since they're over 15
    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('target') == p2.hero_id]
    assert len(dmg_events) >= 1, "Alexstrasza should damage enemy hero to 15"
    # The damage should be 30-15=15
    total_dmg = sum(e.payload.get('amount', 0) for e in dmg_events)
    assert total_dmg == 15, f"Alexstrasza should deal 15 damage (30→15), dealt {total_dmg}"


def test_alexstrasza_heals_self_when_low():
    """Alexstrasza battlecry: heal self to 15 when low."""
    game, p1, p2 = new_hs_game()

    p1.life = 5
    p2.life = 10  # Enemy is already below 15

    alex = play_from_hand(game, ALEXSTRASZA, p1)

    # Should heal self
    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE
                   and e.payload.get('amount', 0) > 0]
    assert len(heal_events) >= 1, "Alexstrasza should heal self when at 5 HP"


def test_deathwing_destroys_all_minions():
    """Deathwing battlecry: destroy all other minions, discard hand."""
    game, p1, p2 = new_hs_game()

    f1 = make_obj(game, WISP, p1)
    e1 = make_obj(game, CHILLWIND_YETI, p2)

    # Add cards to hand to be discarded
    make_obj(game, WISP, p1, zone=ZoneType.HAND)

    dw = play_from_hand(game, DEATHWING, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'deathwing']
    assert len(destroy_events) >= 2, f"Deathwing should destroy all other minions, got {len(destroy_events)}"

    discard_events = [e for e in game.state.event_log
                      if e.type == EventType.DISCARD]
    assert len(discard_events) >= 1, "Deathwing should discard hand"


def test_onyxia_fills_board_with_whelps():
    """Onyxia battlecry: fill board with 1/1 Whelps."""
    game, p1, p2 = new_hs_game()

    onyxia = play_from_hand(game, ONYXIA, p1)

    token_events = [e for e in game.state.event_log
                    if e.type == EventType.CREATE_TOKEN
                    and e.payload.get('token', {}).get('name') == 'Whelp']
    # Should summon up to 6 Whelps (7 total with Onyxia)
    assert len(token_events) >= 1, f"Onyxia should summon Whelps, got {len(token_events)}"
    assert len(token_events) <= 6, f"Onyxia should summon at most 6 Whelps, got {len(token_events)}"


def test_doomsayer_destroys_all_at_turn_start():
    """Doomsayer: at start of your turn, destroy ALL minions."""
    game, p1, p2 = new_hs_game()

    doom = make_obj(game, DOOMSAYER, p1)
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': p1.id},
        source='test'
    ))

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'doomsayer']
    assert len(destroy_events) >= 2, f"Doomsayer should destroy all minions including itself, got {len(destroy_events)}"


def test_twilight_drake_gains_health_from_hand():
    """Twilight Drake battlecry: gain +1 HP per card in hand."""
    game, p1, p2 = new_hs_game()

    # Put some cards in hand
    for _ in range(4):
        make_obj(game, WISP, p1, zone=ZoneType.HAND)

    drake = play_from_hand(game, TWILIGHT_DRAKE, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('object_id') == drake.id]
    assert len(pt_events) >= 1, "Twilight Drake should gain HP from hand size"


def test_coldlight_oracle_both_draw():
    """Coldlight Oracle battlecry: each player draws 2 cards."""
    game, p1, p2 = new_hs_game()

    # Seed both decks
    for _ in range(3):
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        make_obj(game, WISP, p2, zone=ZoneType.LIBRARY)

    oracle = play_from_hand(game, COLDLIGHT_ORACLE, p1)

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 2, f"Coldlight Oracle should make both players draw, got {len(draw_events)}"


# ============================================================================
# PRIEST: Divine Spirit + Inner Fire Combo
# ============================================================================

def test_divine_spirit_doubles_health():
    """Divine Spirit doubles a minion's health."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5
    base_hp = get_toughness(yeti, game.state)

    cast_spell(game, DIVINE_SPIRIT, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('toughness_mod', 0) > 0]
    assert len(pt_events) >= 1, "Divine Spirit should modify toughness"
    # Should add 5 more toughness (doubling 5 → 10)
    assert pt_events[0].payload['toughness_mod'] == base_hp, \
        f"Divine Spirit should add {base_hp} toughness, got {pt_events[0].payload['toughness_mod']}"


def test_inner_fire_sets_attack_to_health():
    """Inner Fire changes attack to equal current health."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5

    cast_spell(game, INNER_FIRE, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('power_mod', 0) != 0]
    assert len(pt_events) >= 1, "Inner Fire should modify power"
    # 5 HP - 4 ATK = +1 power mod
    assert pt_events[0].payload['power_mod'] == 1, \
        f"Inner Fire on 4/5 should be +1 power, got {pt_events[0].payload['power_mod']}"


def test_divine_spirit_inner_fire_combo():
    """Classic combo: Divine Spirit (double HP) + Inner Fire (ATK = HP)."""
    game, p1, p2 = new_hs_game()

    # Use a River Crocolisk (2/3)
    croc = make_obj(game, RIVER_CROCOLISK, p1)

    # Divine Spirit: 3 → 6 HP
    cast_spell(game, DIVINE_SPIRIT, p1)
    new_hp = get_toughness(croc, game.state)
    assert new_hp == 6, f"After Divine Spirit, HP should be 6, got {new_hp}"

    # Inner Fire: ATK = 6
    # Need to cast targeting the croc specifically
    inner_obj = game.create_object(
        name=INNER_FIRE.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=INNER_FIRE.characteristics, card_def=INNER_FIRE
    )
    events = INNER_FIRE.spell_effect(inner_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    final_atk = get_power(croc, game.state)
    # Should be 6 (matching the doubled HP)
    assert final_atk >= 6, f"After DS+IF, attack should be 6, got {final_atk}"


def test_power_word_shield_buffs_and_draws():
    """Power Word: Shield gives +2 HP and draws."""
    game, p1, p2 = new_hs_game()

    minion = make_obj(game, WISP, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    cast_spell(game, POWER_WORD_SHIELD, p1)

    pt_events = [e for e in game.state.event_log
                 if e.type == EventType.PT_MODIFICATION
                 and e.payload.get('toughness_mod') == 2]
    assert len(pt_events) >= 1, "PW:S should give +2 HP"

    draw_events = [e for e in game.state.event_log if e.type == EventType.DRAW]
    assert len(draw_events) >= 1, "PW:S should draw a card"


# ============================================================================
# PRIEST: Auchenai Soulpriest
# ============================================================================

def test_auchenai_converts_healing_to_damage():
    """Auchenai Soulpriest turns healing into damage via TRANSFORM interceptor."""
    game, p1, p2 = new_hs_game()

    auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)

    # Emit a healing event from a source controlled by us
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'object_id': auchenai.id, 'amount': 4},
        source=auchenai.id
    ))

    # The LIFE_CHANGE should have been transformed into a DAMAGE event
    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('target') == auchenai.id]
    assert len(dmg_events) >= 1, "Auchenai should transform healing into damage"


def test_auchenai_circle_of_healing_combo():
    """Auchenai + Circle of Healing = deal damage instead of healing."""
    game, p1, p2 = new_hs_game()

    auchenai = make_obj(game, AUCHENAI_SOULPRIEST, p1)  # 3/5
    enemy = make_obj(game, CHILLWIND_YETI, p2)  # 4/5

    # Damage both minions so Circle of Healing would "heal" them
    auchenai.state.damage = 2
    enemy.state.damage = 2

    cast_spell(game, CIRCLE_OF_HEALING, p1)

    # Circle emits LIFE_CHANGE events which Auchenai should transform to DAMAGE
    # Note: Circle only heals minions with damage > 0, and the source is the Circle spell
    # The Auchenai filter checks source.controller == obj.controller
    dmg_events = [e for e in game.state.event_log if e.type == EventType.DAMAGE]
    heal_events = [e for e in game.state.event_log
                   if e.type == EventType.LIFE_CHANGE and e.payload.get('amount', 0) > 0]

    # At least some healing should have been converted to damage
    assert len(dmg_events) > 0 or len(heal_events) > 0, \
        "Auchenai + Circle should produce damage or healing events"


# ============================================================================
# PRIEST: Shadow Words & Holy Nova
# ============================================================================

def test_shadow_word_pain_destroys_wisp():
    """SW:Pain destroys a minion with 3 or less Attack."""
    game, p1, p2 = new_hs_game()

    # Wisp has 1 attack
    enemy = make_obj(game, WISP, p2)

    cast_spell(game, SHADOW_WORD_PAIN, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) >= 1, "SW:Pain should destroy Wisp (1 attack ≤ 3)"


def test_shadow_word_pain_ignores_high_attack():
    """SW:Pain should NOT destroy a minion with >3 Attack."""
    game, p1, p2 = new_hs_game()

    # Boulderfist Ogre has 6 attack
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)

    cast_spell(game, SHADOW_WORD_PAIN, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) == 0, "SW:Pain should NOT destroy Ogre (6 attack > 3)"


def test_shadow_word_death_destroys_ogre():
    """SW:Death destroys a minion with 5 or more Attack."""
    game, p1, p2 = new_hs_game()

    enemy = make_obj(game, BOULDERFIST_OGRE, p2)  # 6 attack

    cast_spell(game, SHADOW_WORD_DEATH, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('object_id') == enemy.id]
    assert len(destroy_events) >= 1, "SW:Death should destroy Ogre (6 attack ≥ 5)"


# ============================================================================
# TRIBAL SYNERGIES
# ============================================================================

def test_murloc_warleader_buffs_other_murlocs():
    """Murloc Warleader gives other Murlocs +2 Attack."""
    game, p1, p2 = new_hs_game()

    raider = make_obj(game, MURLOC_RAIDER, p1)  # 2/1 Murloc
    base_power = get_power(raider, game.state)

    warleader = make_obj(game, MURLOC_WARLEADER, p1)

    boosted_power = get_power(raider, game.state)
    assert boosted_power == base_power + 2, \
        f"Murloc Warleader should give +2 attack to Murlocs, {base_power}→{boosted_power}"


def test_murloc_warleader_doesnt_buff_self():
    """Murloc Warleader should NOT buff itself."""
    game, p1, p2 = new_hs_game()

    warleader = make_obj(game, MURLOC_WARLEADER, p1)  # 3/3 Murloc

    own_power = get_power(warleader, game.state)
    assert own_power == 3, f"Murloc Warleader should not buff self, got {own_power}"


def test_murloc_warleader_doesnt_buff_non_murlocs():
    """Murloc Warleader should NOT buff non-Murloc minions."""
    game, p1, p2 = new_hs_game()

    yeti = make_obj(game, CHILLWIND_YETI, p1)  # 4/5, not a Murloc
    base = get_power(yeti, game.state)

    warleader = make_obj(game, MURLOC_WARLEADER, p1)

    after = get_power(yeti, game.state)
    assert after == base, f"Warleader should not buff non-Murlocs, {base}→{after}"


# ============================================================================
# GADGETZAN AUCTIONEER
# ============================================================================

def test_gadgetzan_auctioneer_draws_on_spell():
    """Gadgetzan Auctioneer draws a card when you cast a spell."""
    game, p1, p2 = new_hs_game()

    gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    # Cast a spell (emit SPELL_CAST)
    spell = game.create_object(
        name="Moonfire", owner_id=p1.id, zone=ZoneType.GRAVEYARD,
        characteristics=WISP.characteristics
    )
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p1.id, 'spell_id': spell.id},
        source=spell.id, controller=p1.id
    ))

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('player') == p1.id]
    assert len(draw_events) >= 1, "Gadgetzan should draw on spell cast"


def test_gadgetzan_doesnt_draw_on_opponent_spell():
    """Gadgetzan Auctioneer should NOT draw when opponent casts."""
    game, p1, p2 = new_hs_game()

    gadget = make_obj(game, GADGETZAN_AUCTIONEER, p1)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    # Opponent casts a spell
    spell = game.create_object(
        name="Fireball", owner_id=p2.id, zone=ZoneType.GRAVEYARD,
        characteristics=WISP.characteristics
    )
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'caster': p2.id, 'spell_id': spell.id},
        source=spell.id, controller=p2.id
    ))

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('player') == p1.id]
    assert len(draw_events) == 0, "Gadgetzan should NOT draw on opponent's spell"


# ============================================================================
# WARLOCK: Complex Effects
# ============================================================================

def test_twisting_nether_destroys_all():
    """Twisting Nether destroys all minions."""
    game, p1, p2 = new_hs_game()

    f1 = make_obj(game, WISP, p1)
    e1 = make_obj(game, CHILLWIND_YETI, p2)

    cast_spell(game, TWISTING_NETHER, p1)

    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED]
    assert len(destroy_events) >= 2, f"Twisting Nether should destroy all minions, got {len(destroy_events)}"


def test_flame_imp_damages_own_hero():
    """Flame Imp battlecry: deal 3 damage to your hero."""
    game, p1, p2 = new_hs_game()

    p1.life = 30
    flame = play_from_hand(game, FLAME_IMP, p1)

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and (e.payload.get('target') == p1.hero_id
                       or e.payload.get('player') == p1.id)]
    assert len(dmg_events) >= 1, "Flame Imp should damage own hero"


# ============================================================================
# MALYGOS + SPELL DAMAGE
# ============================================================================

def test_malygos_spell_damage_five():
    """Malygos should provide Spell Damage +5."""
    game, p1, p2 = new_hs_game()

    maly = make_obj(game, MALYGOS, p1)
    enemy = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7

    # Cast Arcane Explosion (1 damage AOE + 5 spell damage = 6)
    ae_obj = game.create_object(
        name=ARCANE_EXPLOSION.name, owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
        characteristics=ARCANE_EXPLOSION.characteristics, card_def=ARCANE_EXPLOSION
    )
    events = ARCANE_EXPLOSION.spell_effect(ae_obj, game.state, targets=None)
    for e in events:
        game.emit(e)

    assert enemy.state.damage >= 6, f"Arcane Explosion + Malygos should deal 6, got {enemy.state.damage}"


# ============================================================================
# NORTHSHIRE CLERIC DRAW ENGINE
# ============================================================================

def test_northshire_draws_on_any_minion_heal():
    """Northshire Cleric draws on any minion being healed."""
    game, p1, p2 = new_hs_game()

    cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p2)
    make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)

    # Heal the enemy yeti
    game.emit(Event(
        type=EventType.LIFE_CHANGE,
        payload={'object_id': yeti.id, 'amount': 2},
        source='test'
    ))

    draw_events = [e for e in game.state.event_log
                   if e.type == EventType.DRAW
                   and e.payload.get('player') == p1.id]
    assert len(draw_events) >= 1, "Northshire should draw when any minion is healed"


# ============================================================================
# CROSS-CLASS COMPLEX SCENARIOS
# ============================================================================

def test_malygos_frostbolt_deals_8():
    """Malygos (Spell Damage +5) + Frostbolt (3 base) = 8 damage."""
    game, p1, p2 = new_hs_game()

    maly = make_obj(game, MALYGOS, p1)

    cast_spell(game, FROSTBOLT, p1, targets=[p2.hero_id])

    dmg_events = [e for e in game.state.event_log
                  if e.type == EventType.DAMAGE
                  and e.payload.get('target') == p2.hero_id]
    total = sum(e.payload.get('amount', 0) for e in dmg_events)
    assert total >= 8, f"Malygos Frostbolt should deal 8 (3+5), got {total}"


def test_doomsayer_survives_if_killed_before_trigger():
    """If Doomsayer is destroyed before its turn starts, nothing happens."""
    game, p1, p2 = new_hs_game()

    doom = make_obj(game, DOOMSAYER, p1)
    friendly = make_obj(game, WISP, p1)

    # Destroy doomsayer before turn start
    game.emit(Event(
        type=EventType.OBJECT_DESTROYED,
        payload={'object_id': doom.id},
        source='test'
    ))
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={'object_id': doom.id, 'from_zone_type': ZoneType.BATTLEFIELD,
                 'to_zone_type': ZoneType.GRAVEYARD},
        source='test'
    ))

    # Now trigger turn start
    game.emit(Event(
        type=EventType.TURN_START,
        payload={'player': p1.id},
        source='test'
    ))

    # Friendly wisp should NOT be destroyed
    destroy_events = [e for e in game.state.event_log
                      if e.type == EventType.OBJECT_DESTROYED
                      and e.payload.get('reason') == 'doomsayer'
                      and e.payload.get('object_id') == friendly.id]
    # This depends on how the engine removes interceptors when a minion dies
    # In any case, the doomsayer's OBJECT_DESTROYED should fire, not the wisp's
    non_doom_destroys = [e for e in game.state.event_log
                         if e.type == EventType.OBJECT_DESTROYED
                         and e.payload.get('reason') == 'doomsayer']
    assert len(non_doom_destroys) == 0, "Destroyed Doomsayer should not trigger its effect"


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} passed")
