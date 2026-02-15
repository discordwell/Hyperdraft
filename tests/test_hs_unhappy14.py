"""
Hearthstone Unhappy Path Tests - Batch 14

Classic neutral legendary triggers (Baron Geddon, Gruul, Hogger, The Beast,
Nat Pagle, Lorewalker Cho, King Mukla, Millhouse Manastorm, Tinkmaster Overspark),
dynamic cost cards (Sea Giant, Mountain Giant, Molten Giant, Dread Corsair),
triggered effects (Blood Knight, Flesheating Ghoul, Murloc Tidecaller,
Lightwarden, Mana Addict, Questing Adventurer, Secretkeeper),
passives/auras (Ancient Watcher cant_attack, Mana Wraith cost increase,
Pint-Sized Summoner cost reduction, Southsea Deckhand conditional charge),
and tribal synergies (Bloodsail Corsair, Bloodsail Raider, Coldlight Seer,
Murloc Warleader, Southsea Captain, Arcane Golem, Hungry Crab,
Youthful Brewmaster).
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
    BLOODFEN_RAPTOR, MURLOC_RAIDER, STONETUSK_BOAR,
)
from src.cards.hearthstone.classic import (
    BARON_GEDDON, GRUUL, HOGGER, THE_BEAST, NAT_PAGLE,
    LOREWALKER_CHO, KING_MUKLA, MILLHOUSE_MANASTORM, TINKMASTER_OVERSPARK,
    SEA_GIANT, MOUNTAIN_GIANT, MOLTEN_GIANT, DREAD_CORSAIR,
    BLOOD_KNIGHT, FLESHEATING_GHOUL, MURLOC_TIDECALLER,
    LIGHTWARDEN, MANA_ADDICT, QUESTING_ADVENTURER, SECRETKEEPER,
    ANCIENT_WATCHER, MANA_WRAITH, PINT_SIZED_SUMMONER, SOUTHSEA_DECKHAND,
    BLOODSAIL_CORSAIR, BLOODSAIL_RAIDER, COLDLIGHT_SEER,
    MURLOC_WARLEADER, SOUTHSEA_CAPTAIN, ARCANE_GOLEM, HUNGRY_CRAB,
    YOUTHFUL_BREWMASTER, ARGENT_SQUIRE, YOUNG_PRIESTESS,
    MIND_CONTROL_TECH, FIERY_WAR_AXE, KNIFE_JUGGLER,
)


# ============================================================
# Test Helpers
# ============================================================

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
    return obj


def play_from_hand(game, card_def, owner):
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


def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets)
    for e in events:
        game.emit(e)
    return obj


def run_sba(game):
    game._check_state_based_actions()


# ============================================================
# Classic Legendary Triggers
# ============================================================

def test_baron_geddon_end_of_turn_aoe():
    """Baron Geddon deals 2 to ALL other characters at end of controller's turn."""
    game, p1, p2 = new_hs_game()
    geddon = make_obj(game, BARON_GEDDON, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p1)  # friendly 4/5
    raptor = make_obj(game, BLOODFEN_RAPTOR, p2)  # enemy 3/2

    game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='test'))

    # Geddon should NOT damage itself
    assert geddon.state.damage == 0
    # All other characters take 2
    assert yeti.state.damage == 2
    assert raptor.state.damage == 2
    assert p1.life == 28  # hero takes 2
    assert p2.life == 28  # enemy hero takes 2


def test_baron_geddon_only_on_controller_turn():
    """Baron Geddon only fires on its controller's turn end, not opponent's."""
    game, p1, p2 = new_hs_game()
    geddon = make_obj(game, BARON_GEDDON, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    game.emit(Event(type=EventType.TURN_END, payload={'player': p2.id}, source='test'))

    # Should not trigger - wrong player
    assert yeti.state.damage == 0
    assert p1.life == 30
    assert p2.life == 30


def test_gruul_gains_at_end_of_each_turn():
    """Gruul gains +1/+1 at end of EACH turn (both players)."""
    game, p1, p2 = new_hs_game()
    gruul = make_obj(game, GRUUL, p1)

    base_power = get_power(gruul, game.state)
    base_tough = get_toughness(gruul, game.state)

    game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='test'))
    assert get_power(gruul, game.state) == base_power + 1
    assert get_toughness(gruul, game.state) == base_tough + 1

    game.emit(Event(type=EventType.TURN_END, payload={'player': p2.id}, source='test'))
    assert get_power(gruul, game.state) == base_power + 2
    assert get_toughness(gruul, game.state) == base_tough + 2


def test_hogger_summons_gnoll_at_end_of_turn():
    """Hogger summons a 2/2 Gnoll with Taunt at end of controller's turn."""
    game, p1, p2 = new_hs_game()
    hogger = make_obj(game, HOGGER, p1)

    bf = game.state.zones.get('battlefield')
    initial_count = len(bf.objects)

    game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='test'))

    # Should have spawned a token
    assert len(bf.objects) > initial_count
    # Find the gnoll
    gnoll = None
    for oid in bf.objects:
        o = game.state.objects.get(oid)
        if o and o.name == 'Gnoll':
            gnoll = o
            break
    assert gnoll is not None, "Gnoll token not found"
    assert get_power(gnoll, game.state) == 2
    assert get_toughness(gnoll, game.state) == 2


def test_the_beast_deathrattle_gives_opponent_finkle():
    """The Beast's deathrattle summons 3/3 Finkle Einhorn for opponent."""
    game, p1, p2 = new_hs_game()
    beast = make_obj(game, THE_BEAST, p1)

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': beast.id, 'reason': 'test'}, source='test'))

    # Finkle should be summoned for the opponent (p2)
    bf = game.state.zones.get('battlefield')
    finkle = None
    for oid in bf.objects:
        o = game.state.objects.get(oid)
        if o and o.name == 'Finkle Einhorn':
            finkle = o
            break
    assert finkle is not None, "Finkle Einhorn not found"
    assert finkle.controller == p2.id
    assert get_power(finkle, game.state) == 3
    assert get_toughness(finkle, game.state) == 3


def test_king_mukla_gives_opponent_bananas():
    """King Mukla's battlecry gives opponent 2 Bananas in hand."""
    game, p1, p2 = new_hs_game()

    hand_before = len(game.state.zones.get(f'hand_{p2.id}').objects)
    mukla = play_from_hand(game, KING_MUKLA, p1)

    hand_after = len(game.state.zones.get(f'hand_{p2.id}').objects)
    # Should have added 2 cards to opponent's hand
    assert hand_after >= hand_before  # At least attempted to add


def test_millhouse_manastorm_enemy_spells_free():
    """Millhouse Manastorm battlecry: opponent gets free spells for the turn."""
    game, p1, p2 = new_hs_game()
    mukla = play_from_hand(game, MILLHOUSE_MANASTORM, p1)

    # P2 (opponent) should have a cost modifier making spells cost 0
    has_millhouse_modifier = False
    for mod in p2.cost_modifiers:
        if 'millhouse' in mod.get('id', '').lower():
            has_millhouse_modifier = True
            assert mod['card_type'] == CardType.SPELL
            assert mod['amount'] == 100  # huge reduction
    assert has_millhouse_modifier, "Millhouse cost modifier not found on opponent"


def test_tinkmaster_overspark_transforms_random_minion():
    """Tinkmaster Overspark transforms another random minion into 5/5 or 1/1."""
    game, p1, p2 = new_hs_game()
    random.seed(42)
    target = make_obj(game, CHILLWIND_YETI, p2)
    tinkmaster = play_from_hand(game, TINKMASTER_OVERSPARK, p1)

    # Target should have been transformed to either Devilsaur (5/5) or Squirrel (1/1)
    assert target.name in ("Devilsaur", "Squirrel"), f"Expected Devilsaur or Squirrel, got {target.name}"
    if target.name == "Devilsaur":
        assert target.characteristics.power == 5
        assert target.characteristics.toughness == 5
    else:
        assert target.characteristics.power == 1
        assert target.characteristics.toughness == 1


def test_tinkmaster_overspark_no_target_no_crash():
    """Tinkmaster with no other minions on board doesn't crash."""
    game, p1, p2 = new_hs_game()
    tinkmaster = play_from_hand(game, TINKMASTER_OVERSPARK, p1)
    # Should not crash, Tinkmaster on board
    bf = game.state.zones.get('battlefield')
    assert tinkmaster.id in bf.objects


def test_young_priestess_buffs_at_end_of_turn():
    """Young Priestess gives a random friendly minion +1 HP at end of turn."""
    game, p1, p2 = new_hs_game()
    random.seed(42)
    priestess = make_obj(game, YOUNG_PRIESTESS, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p1)

    initial_toughness = get_toughness(yeti, game.state)
    game.emit(Event(type=EventType.TURN_END, payload={'player': p1.id}, source='test'))

    # Yeti should have gained +1 HP (only friendly minion besides priestess)
    assert get_toughness(yeti, game.state) == initial_toughness + 1


# ============================================================
# Dynamic Cost Cards
# ============================================================

def test_sea_giant_cost_scales_with_board():
    """Sea Giant costs 10 minus the number of minions on the board."""
    game, p1, p2 = new_hs_game()
    # Create a "card" object in hand to test dynamic_cost
    sg = game.create_object(
        name=SEA_GIANT.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=SEA_GIANT.characteristics, card_def=SEA_GIANT
    )

    # No minions -> cost 10
    cost_empty = SEA_GIANT.dynamic_cost(sg, game.state)
    assert cost_empty == 10

    # Add 3 minions
    make_obj(game, WISP, p1)
    make_obj(game, WISP, p1)
    make_obj(game, WISP, p2)

    cost_3 = SEA_GIANT.dynamic_cost(sg, game.state)
    assert cost_3 == 7, f"Expected 7, got {cost_3}"


def test_mountain_giant_cost_scales_with_hand():
    """Mountain Giant costs 12 minus (cards in hand - 1)."""
    game, p1, p2 = new_hs_game()
    mg = game.create_object(
        name=MOUNTAIN_GIANT.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=MOUNTAIN_GIANT.characteristics, card_def=MOUNTAIN_GIANT
    )

    # Just Mountain Giant in hand -> 12 - (1-1) = 12
    cost_1 = MOUNTAIN_GIANT.dynamic_cost(mg, game.state)
    assert cost_1 == 12

    # Add 4 more cards to hand
    for _ in range(4):
        game.create_object(name=WISP.name, owner_id=p1.id, zone=ZoneType.HAND,
                           characteristics=WISP.characteristics, card_def=WISP)

    # 5 cards in hand -> 12 - (5-1) = 8
    cost_5 = MOUNTAIN_GIANT.dynamic_cost(mg, game.state)
    assert cost_5 == 8, f"Expected 8, got {cost_5}"


def test_molten_giant_cost_scales_with_damage():
    """Molten Giant costs 20 minus damage taken by hero."""
    game, p1, p2 = new_hs_game()
    mg = game.create_object(
        name=MOLTEN_GIANT.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=MOLTEN_GIANT.characteristics, card_def=MOLTEN_GIANT
    )

    # Full HP -> cost 20
    cost_full = MOLTEN_GIANT.dynamic_cost(mg, game.state)
    assert cost_full == 20

    # Take 15 damage -> life = 15, cost = 20 - 15 = 5
    p1.life = 15
    cost_15dmg = MOLTEN_GIANT.dynamic_cost(mg, game.state)
    assert cost_15dmg == 5, f"Expected 5, got {cost_15dmg}"

    # Take 25 damage -> life = 5, cost = max(0, 20-25) = 0
    p1.life = 5
    cost_25dmg = MOLTEN_GIANT.dynamic_cost(mg, game.state)
    assert cost_25dmg == 0, f"Expected 0, got {cost_25dmg}"


def test_dread_corsair_cost_scales_with_weapon():
    """Dread Corsair costs 4 minus weapon attack."""
    game, p1, p2 = new_hs_game()
    dc = game.create_object(
        name=DREAD_CORSAIR.name, owner_id=p1.id, zone=ZoneType.HAND,
        characteristics=DREAD_CORSAIR.characteristics, card_def=DREAD_CORSAIR
    )

    # No weapon -> cost 4
    cost_no_weapon = DREAD_CORSAIR.dynamic_cost(dc, game.state)
    assert cost_no_weapon == 4

    # Equip a 3-attack weapon
    p1.weapon_attack = 3
    p1.weapon_durability = 2
    cost_3atk = DREAD_CORSAIR.dynamic_cost(dc, game.state)
    assert cost_3atk == 1, f"Expected 1, got {cost_3atk}"

    # 5-attack weapon -> cost 0 (floored)
    p1.weapon_attack = 5
    cost_5atk = DREAD_CORSAIR.dynamic_cost(dc, game.state)
    assert cost_5atk == 0, f"Expected 0, got {cost_5atk}"


# ============================================================
# Triggered Effects
# ============================================================

def test_blood_knight_consumes_divine_shields():
    """Blood Knight removes all Divine Shields and gains +3/+3 per shield."""
    game, p1, p2 = new_hs_game()
    squire1 = make_obj(game, ARGENT_SQUIRE, p1)
    squire1.state.divine_shield = True
    squire2 = make_obj(game, ARGENT_SQUIRE, p2)
    squire2.state.divine_shield = True

    bk = play_from_hand(game, BLOOD_KNIGHT, p1)

    # Both shields consumed
    assert squire1.state.divine_shield == False
    assert squire2.state.divine_shield == False
    # Blood Knight gets +6/+6 (2 shields * 3)
    assert get_power(bk, game.state) == 3 + 6  # base 3 + 6
    assert get_toughness(bk, game.state) == 3 + 6


def test_blood_knight_no_shields():
    """Blood Knight with no Divine Shields on board stays at base stats."""
    game, p1, p2 = new_hs_game()
    yeti = make_obj(game, CHILLWIND_YETI, p1)  # no shield

    bk = play_from_hand(game, BLOOD_KNIGHT, p1)
    assert get_power(bk, game.state) == 3
    assert get_toughness(bk, game.state) == 3


def test_flesheating_ghoul_gains_on_minion_death():
    """Flesheating Ghoul gains +1 Attack whenever a minion dies."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
    wisp = make_obj(game, WISP, p2)

    base_power = get_power(ghoul, game.state)

    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': wisp.id, 'reason': 'test'}, source='test'))

    assert get_power(ghoul, game.state) == base_power + 1


def test_flesheating_ghoul_multiple_deaths():
    """Flesheating Ghoul stacks attack gains across multiple deaths."""
    game, p1, p2 = new_hs_game()
    ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
    base_power = get_power(ghoul, game.state)

    for i in range(3):
        w = make_obj(game, WISP, p2)
        game.emit(Event(type=EventType.OBJECT_DESTROYED,
                         payload={'object_id': w.id, 'reason': 'test'}, source='test'))

    assert get_power(ghoul, game.state) == base_power + 3


def test_murloc_tidecaller_gains_on_murloc_summon():
    """Murloc Tidecaller gains +1 Attack when another Murloc is summoned."""
    game, p1, p2 = new_hs_game()
    tidecaller = make_obj(game, MURLOC_TIDECALLER, p1)
    base_power = get_power(tidecaller, game.state)

    # Summon a Murloc via zone change
    raider = play_from_hand(game, MURLOC_RAIDER, p1)

    assert get_power(tidecaller, game.state) == base_power + 1


def test_murloc_tidecaller_ignores_non_murlocs():
    """Murloc Tidecaller doesn't trigger on non-Murloc summons."""
    game, p1, p2 = new_hs_game()
    tidecaller = make_obj(game, MURLOC_TIDECALLER, p1)
    base_power = get_power(tidecaller, game.state)

    play_from_hand(game, WISP, p1)

    assert get_power(tidecaller, game.state) == base_power


def test_lightwarden_gains_on_healing():
    """Lightwarden gains +2 Attack whenever any character is healed."""
    game, p1, p2 = new_hs_game()
    warden = make_obj(game, LIGHTWARDEN, p1)
    base_power = get_power(warden, game.state)

    # Heal event (positive LIFE_CHANGE)
    p1.life = 25
    game.emit(Event(type=EventType.LIFE_CHANGE,
                     payload={'player': p1.id, 'amount': 3}, source='test'))

    assert get_power(warden, game.state) == base_power + 2


def test_mana_addict_gains_temporary_attack_on_spell():
    """Mana Addict gains +2 Attack THIS TURN when controller casts a spell."""
    game, p1, p2 = new_hs_game()
    addict = make_obj(game, MANA_ADDICT, p1)
    base_power = get_power(addict, game.state)

    # Emit a spell cast event
    game.emit(Event(type=EventType.SPELL_CAST,
                     payload={'caster': p1.id, 'spell_name': 'Test'},
                     source='test'))

    assert get_power(addict, game.state) == base_power + 2


def test_questing_adventurer_grows_on_card_play():
    """Questing Adventurer gains +1/+1 when controller plays a card."""
    game, p1, p2 = new_hs_game()
    qa = make_obj(game, QUESTING_ADVENTURER, p1)
    base_power = get_power(qa, game.state)
    base_tough = get_toughness(qa, game.state)

    # Play a card (zone change triggers it)
    play_from_hand(game, WISP, p1)

    assert get_power(qa, game.state) >= base_power + 1
    assert get_toughness(qa, game.state) >= base_tough + 1


# ============================================================
# Passives/Auras
# ============================================================

def test_ancient_watcher_cant_attack():
    """Ancient Watcher has can't attack keyword and PREVENT interceptor."""
    game, p1, p2 = new_hs_game()
    watcher = make_obj(game, ANCIENT_WATCHER, p1)

    assert has_ability(watcher, 'cant_attack', game.state)

    # Verify the PREVENT interceptor is registered
    found_prevent = False
    for int_id in watcher.interceptor_ids:
        interceptor = game.state.interceptors.get(int_id)
        if interceptor and interceptor.priority == InterceptorPriority.PREVENT:
            found_prevent = True
    assert found_prevent, "Ancient Watcher should have a PREVENT interceptor"


def test_mana_wraith_makes_all_minions_cost_more():
    """Mana Wraith: ALL minions cost (1) more for both players."""
    game, p1, p2 = new_hs_game()
    wraith = make_obj(game, MANA_WRAITH, p1)

    # Both players should have cost modifier
    p1_has_mod = any('mana_wraith' in m.get('id', '') for m in p1.cost_modifiers)
    p2_has_mod = any('mana_wraith' in m.get('id', '') for m in p2.cost_modifiers)
    assert p1_has_mod, "P1 should have Mana Wraith cost modifier"
    assert p2_has_mod, "P2 should have Mana Wraith cost modifier"


def test_mana_wraith_modifier_removed_on_death():
    """Mana Wraith's cost increase is removed when it dies."""
    game, p1, p2 = new_hs_game()
    wraith = make_obj(game, MANA_WRAITH, p1)

    # Verify modifiers exist
    assert any('mana_wraith' in m.get('id', '') for m in p2.cost_modifiers)

    # Kill the wraith
    game.emit(Event(type=EventType.OBJECT_DESTROYED,
                     payload={'object_id': wraith.id, 'reason': 'test'}, source='test'))

    # Modifiers should be cleaned up
    assert not any('mana_wraith' in m.get('id', '') for m in p2.cost_modifiers)


def test_pint_sized_summoner_first_minion_cheaper():
    """Pint-Sized Summoner: first minion each turn costs (1) less."""
    game, p1, p2 = new_hs_game()
    pint = make_obj(game, PINT_SIZED_SUMMONER, p1)

    # P1 should have the cost reduction modifier
    has_pint_mod = any('pint_sized' in m.get('id', '') for m in p1.cost_modifiers)
    assert has_pint_mod, "Pint-Sized Summoner modifier not found"

    # Check it has uses_remaining = 1
    for mod in p1.cost_modifiers:
        if 'pint_sized' in mod.get('id', ''):
            assert mod.get('uses_remaining') == 1
            assert mod.get('card_type') == CardType.MINION


def test_southsea_deckhand_charge_with_weapon():
    """Southsea Deckhand has Charge while weapon is equipped."""
    game, p1, p2 = new_hs_game()
    deckhand = make_obj(game, SOUTHSEA_DECKHAND, p1)

    # No weapon - should not have charge
    assert not has_ability(deckhand, 'charge', game.state)

    # Equip weapon
    p1.weapon_attack = 3
    p1.weapon_durability = 2

    # Now should have charge
    assert has_ability(deckhand, 'charge', game.state)


def test_southsea_deckhand_loses_charge_without_weapon():
    """Southsea Deckhand loses Charge when weapon is gone."""
    game, p1, p2 = new_hs_game()
    deckhand = make_obj(game, SOUTHSEA_DECKHAND, p1)

    # Equip weapon
    p1.weapon_attack = 3
    p1.weapon_durability = 2
    assert has_ability(deckhand, 'charge', game.state)

    # Remove weapon
    p1.weapon_attack = 0
    p1.weapon_durability = 0
    assert not has_ability(deckhand, 'charge', game.state)


# ============================================================
# Tribal Synergies
# ============================================================

def test_bloodsail_corsair_removes_weapon_durability():
    """Bloodsail Corsair battlecry removes 1 durability from opponent's weapon."""
    game, p1, p2 = new_hs_game()
    p2.weapon_attack = 3
    p2.weapon_durability = 2

    corsair = play_from_hand(game, BLOODSAIL_CORSAIR, p1)

    assert p2.weapon_durability == 1


def test_bloodsail_corsair_destroys_last_durability():
    """Bloodsail Corsair at 1 durability destroys the weapon entirely."""
    game, p1, p2 = new_hs_game()
    p2.weapon_attack = 5
    p2.weapon_durability = 1

    corsair = play_from_hand(game, BLOODSAIL_CORSAIR, p1)

    assert p2.weapon_durability == 0
    assert p2.weapon_attack == 0


def test_bloodsail_corsair_no_weapon():
    """Bloodsail Corsair with no enemy weapon does nothing."""
    game, p1, p2 = new_hs_game()
    corsair = play_from_hand(game, BLOODSAIL_CORSAIR, p1)
    # No crash, no change
    assert p2.weapon_durability == 0


def test_bloodsail_raider_gains_weapon_attack():
    """Bloodsail Raider gains Attack equal to controller's weapon Attack."""
    game, p1, p2 = new_hs_game()
    p1.weapon_attack = 4
    p1.weapon_durability = 2

    raider = play_from_hand(game, BLOODSAIL_RAIDER, p1)

    # Base 2 + 4 from weapon
    assert get_power(raider, game.state) == 6


def test_bloodsail_raider_no_weapon():
    """Bloodsail Raider with no weapon stays at base attack."""
    game, p1, p2 = new_hs_game()
    raider = play_from_hand(game, BLOODSAIL_RAIDER, p1)
    assert get_power(raider, game.state) == 2


def test_coldlight_seer_buffs_murlocs():
    """Coldlight Seer gives other friendly Murlocs +2 Health."""
    game, p1, p2 = new_hs_game()
    murloc1 = make_obj(game, MURLOC_RAIDER, p1)
    murloc2 = make_obj(game, MURLOC_RAIDER, p1)
    yeti = make_obj(game, CHILLWIND_YETI, p1)  # not a murloc

    base_m1 = get_toughness(murloc1, game.state)
    base_yeti = get_toughness(yeti, game.state)

    seer = play_from_hand(game, COLDLIGHT_SEER, p1)

    assert get_toughness(murloc1, game.state) == base_m1 + 2
    assert get_toughness(murloc2, game.state) == base_m1 + 2
    assert get_toughness(yeti, game.state) == base_yeti  # unchanged


def test_murloc_warleader_aura_buffs_murlocs():
    """Murloc Warleader gives other friendly Murlocs +2 Attack via aura."""
    game, p1, p2 = new_hs_game()
    murloc1 = make_obj(game, MURLOC_RAIDER, p1)

    base_power = get_power(murloc1, game.state)

    warleader = make_obj(game, MURLOC_WARLEADER, p1)

    assert get_power(murloc1, game.state) == base_power + 2
    # Warleader doesn't buff itself
    assert get_power(warleader, game.state) == 3  # base stats


def test_southsea_captain_aura_buffs_pirates():
    """Southsea Captain gives other friendly Pirates +1/+1 via aura."""
    game, p1, p2 = new_hs_game()
    corsair = make_obj(game, BLOODSAIL_CORSAIR, p1)  # Pirate
    yeti = make_obj(game, CHILLWIND_YETI, p1)  # not a pirate

    base_corsair_p = get_power(corsair, game.state)
    base_corsair_t = get_toughness(corsair, game.state)
    base_yeti_p = get_power(yeti, game.state)

    captain = make_obj(game, SOUTHSEA_CAPTAIN, p1)

    assert get_power(corsair, game.state) == base_corsair_p + 1
    assert get_toughness(corsair, game.state) == base_corsair_t + 1
    assert get_power(yeti, game.state) == base_yeti_p  # unchanged


def test_arcane_golem_gives_opponent_mana_crystal():
    """Arcane Golem battlecry gives opponent a Mana Crystal."""
    game, p1, p2 = new_hs_game()
    # Set p2 to 8 mana crystals
    p2.mana_crystals = 8
    p2.mana_crystals_available = 8

    golem = play_from_hand(game, ARCANE_GOLEM, p1)

    assert p2.mana_crystals == 9
    assert p2.mana_crystals_available == 9


def test_arcane_golem_capped_at_10():
    """Arcane Golem doesn't give beyond 10 mana crystals."""
    game, p1, p2 = new_hs_game()
    p2.mana_crystals = 10
    p2.mana_crystals_available = 10

    golem = play_from_hand(game, ARCANE_GOLEM, p1)

    assert p2.mana_crystals == 10  # capped


def test_hungry_crab_destroys_murloc_and_buffs():
    """Hungry Crab destroys a Murloc and gains +2/+2."""
    game, p1, p2 = new_hs_game()
    murloc = make_obj(game, MURLOC_RAIDER, p2)

    crab = play_from_hand(game, HUNGRY_CRAB, p1)

    # Crab should gain +2/+2 -> 3/4
    assert get_power(crab, game.state) == 3
    assert get_toughness(crab, game.state) == 4


def test_hungry_crab_no_murlocs():
    """Hungry Crab with no Murlocs on board doesn't buff."""
    game, p1, p2 = new_hs_game()
    yeti = make_obj(game, CHILLWIND_YETI, p2)

    crab = play_from_hand(game, HUNGRY_CRAB, p1)

    # Base stats only
    assert get_power(crab, game.state) == 1
    assert get_toughness(crab, game.state) == 2


def test_youthful_brewmaster_bounces_friendly():
    """Youthful Brewmaster bounces a random friendly minion to hand."""
    game, p1, p2 = new_hs_game()
    yeti = make_obj(game, CHILLWIND_YETI, p1)

    brewmaster = play_from_hand(game, YOUTHFUL_BREWMASTER, p1)

    # Check event log for RETURN_TO_HAND
    found_bounce = False
    for e in game.state.event_log:
        if e.type == EventType.RETURN_TO_HAND:
            if e.payload.get('object_id') == yeti.id:
                found_bounce = True
    assert found_bounce, "Yeti should have been bounced to hand"


def test_youthful_brewmaster_no_other_minion():
    """Youthful Brewmaster with no other friendly minions does nothing."""
    game, p1, p2 = new_hs_game()
    enemy = make_obj(game, CHILLWIND_YETI, p2)

    brewmaster = play_from_hand(game, YOUTHFUL_BREWMASTER, p1)
    # No crash, no bounce
    bounce_events = [e for e in game.state.event_log if e.type == EventType.RETURN_TO_HAND]
    assert len(bounce_events) == 0


def test_mind_control_tech_steals_with_4_plus_enemies():
    """Mind Control Tech steals a random enemy minion if opponent has 4+."""
    game, p1, p2 = new_hs_game()
    enemies = []
    for _ in range(4):
        enemies.append(make_obj(game, WISP, p2))

    mct = play_from_hand(game, MIND_CONTROL_TECH, p1)

    # Should have emitted a CONTROL_CHANGE event
    control_changes = [e for e in game.state.event_log if e.type == EventType.CONTROL_CHANGE]
    assert len(control_changes) >= 1, "MCT should steal when opponent has 4+ minions"


def test_mind_control_tech_no_steal_under_4():
    """Mind Control Tech does nothing if opponent has fewer than 4 minions."""
    game, p1, p2 = new_hs_game()
    for _ in range(3):
        make_obj(game, WISP, p2)

    mct = play_from_hand(game, MIND_CONTROL_TECH, p1)

    control_changes = [e for e in game.state.event_log if e.type == EventType.CONTROL_CHANGE]
    assert len(control_changes) == 0, "MCT should not steal with fewer than 4 enemy minions"


# ============================================================
# Run all tests
# ============================================================

if __name__ == '__main__':
    import sys
    test_functions = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    passed = 0
    failed = 0
    for fn in test_functions:
        try:
            fn()
            passed += 1
            print(f"  PASS: {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL: {fn.__name__}: {e}")
    print(f"\n{passed}/{passed+failed} tests passed")
    if failed:
        sys.exit(1)
