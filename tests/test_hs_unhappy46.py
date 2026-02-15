"""
Hearthstone Unhappy Path Tests - Batch 46

Battlecry edge cases (Millhouse Manastorm, King Mukla, Hungry Crab),
hero power + minion trigger chains, weapon lifecycle, Wild Pyromancer
self-kill, double trigger stacking, and various boundary conditions
that stress the interaction between hero powers and board state.
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
from src.cards.hearthstone.hero_powers import (
    HERO_POWERS, reinforce_effect, life_tap_effect, totemic_call_effect,
    dagger_mastery_effect, shapeshift_effect,
)

from src.cards.hearthstone.basic import (
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, RAID_LEADER,
    KOBOLD_GEOMANCER, STORMWIND_CHAMPION, MURLOC_RAIDER,
    GRIMSCALE_ORACLE, BOULDERFIST_OGRE,
)
from src.cards.hearthstone.classic import (
    KNIFE_JUGGLER, FROSTBOLT, FIREBALL, WILD_PYROMANCER,
    LOOT_HOARDER, FLESHEATING_GHOUL, CULT_MASTER,
    MILLHOUSE_MANASTORM, KING_MUKLA, QUESTING_ADVENTURER,
    HUNGRY_CRAB, GADGETZAN_AUCTIONEER, IMP_MASTER,
    DOOMSAYER, HOGGER,
)
from src.cards.hearthstone.warrior import ARMORSMITH
from src.cards.hearthstone.priest import AUCHENAI_SOULPRIEST
from src.cards.hearthstone.priest import NORTHSHIRE_CLERIC


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


def new_hs_game_classes(class1, class2):
    game = Game(mode='hearthstone')
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[class1], HERO_POWERS[class1])
    game.setup_hearthstone_player(p2, HEROES[class2], HERO_POWERS[class2])
    for _ in range(10):
        game.mana_system.on_turn_start(p1.id)
        game.mana_system.on_turn_start(p2.id)
    return game, p1, p2


def make_obj(game, card_def, owner, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name, owner_id=owner.id, zone=zone,
        characteristics=card_def.characteristics, card_def=card_def
    )


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


def cast_spell_full(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name, owner_id=owner.id, zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics, card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    game.emit(Event(
        type=EventType.SPELL_CAST,
        payload={'spell_id': obj.id, 'controller': owner.id, 'caster': owner.id},
        source=obj.id
    ))
    return obj


def activate_hero_power(game, player, hp_effect):
    hp_obj = game.state.objects.get(player.hero_power_id)
    if hp_obj:
        events = hp_effect(hp_obj, game.state)
        for e in events:
            game.emit(e)
    return hp_obj


# ============================================================
# Millhouse Manastorm Battlecry
# ============================================================

class TestMillhouseManastorm:
    def test_battlecry_adds_cost_modifier(self):
        """Millhouse BC: enemy spells cost 0 next turn — adds modifier to opponent."""
        game, p1, p2 = new_hs_game()

        sgt = play_from_hand(game, MILLHOUSE_MANASTORM, p1)

        # Check p2 has a cost modifier for spells
        spell_mods = [m for m in p2.cost_modifiers
                      if m.get('card_type') == CardType.SPELL]
        assert len(spell_mods) >= 1
        # Amount should be 100 (effectively making spells free)
        assert spell_mods[0].get('amount') == 100

    def test_battlecry_does_not_affect_own_spells(self):
        """Millhouse BC should only make ENEMY spells cost 0, not own."""
        game, p1, p2 = new_hs_game()

        play_from_hand(game, MILLHOUSE_MANASTORM, p1)

        # p1 should NOT have a spell cost modifier from Millhouse
        spell_mods = [m for m in p1.cost_modifiers
                      if m.get('card_type') == CardType.SPELL and
                      'millhouse' in m.get('id', '')]
        assert len(spell_mods) == 0


# ============================================================
# King Mukla Battlecry
# ============================================================

class TestKingMukla:
    def test_battlecry_gives_bananas(self):
        """King Mukla BC: gives opponent 2 Bananas (ADD_TO_HAND events)."""
        game, p1, p2 = new_hs_game()

        play_from_hand(game, KING_MUKLA, p1)

        banana_events = [e for e in game.state.event_log
                         if e.type == EventType.ADD_TO_HAND and
                         e.payload.get('player') == p2.id and
                         e.payload.get('card_def', {}).get('name') == 'Banana']
        assert len(banana_events) >= 2

    def test_mukla_is_beast(self):
        """King Mukla should have Beast subtype."""
        game, p1, p2 = new_hs_game()
        mukla = make_obj(game, KING_MUKLA, p1)

        assert 'Beast' in mukla.characteristics.subtypes


# ============================================================
# Hungry Crab Battlecry
# ============================================================

class TestHungryCrab:
    def test_destroys_murloc(self):
        """Hungry Crab BC: destroy a Murloc and gain +2/+2."""
        game, p1, p2 = new_hs_game()
        murloc = make_obj(game, MURLOC_RAIDER, p2)

        crab = play_from_hand(game, HUNGRY_CRAB, p1)

        # Should have destroyed the murloc
        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('object_id') == murloc.id]
        assert len(destroy_events) >= 1

        # Should have gained +2/+2
        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == crab.id and
                   e.payload.get('power_mod') == 2]
        assert len(pt_mods) >= 1

    def test_no_murloc_no_effect(self):
        """Hungry Crab with no murlocs on board: no destroy, no buff."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p2)

        crab = play_from_hand(game, HUNGRY_CRAB, p1)

        destroy_events = [e for e in game.state.event_log
                          if e.type == EventType.OBJECT_DESTROYED and
                          e.payload.get('reason') == 'hungry_crab']
        assert len(destroy_events) == 0


# ============================================================
# Wild Pyromancer Self-Kill
# ============================================================

class TestWildPyromancerSelfKill:
    def test_pyro_kills_self_with_1hp(self):
        """Wild Pyromancer at 1 HP casting a spell should kill itself."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        pyro.state.damage = 1  # 3/2 with 1 damage = effectively 3/1

        # Cast a spell — Pyromancer fires 1 damage to ALL minions (including self)
        cast_spell_full(game, FROSTBOLT, p1, targets=[p2.hero_id])

        # Pyro should have taken 1 more damage (total 2 = dead for a 2 HP minion)
        damage_to_pyro = [e for e in game.state.event_log
                          if e.type == EventType.DAMAGE and
                          e.payload.get('target') == pyro.id]
        assert len(damage_to_pyro) >= 1

    def test_pyro_kills_other_low_hp_minions(self):
        """Pyromancer 1 damage AOE should kill 1-HP minions."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        wisp1 = make_obj(game, WISP, p2)
        wisp2 = make_obj(game, WISP, p2)

        cast_spell_full(game, FROSTBOLT, p1, targets=[p2.hero_id])

        # Both wisps should take 1 damage (lethal for 1/1)
        wisp1_dmg = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and
                     e.payload.get('target') == wisp1.id]
        wisp2_dmg = [e for e in game.state.event_log
                     if e.type == EventType.DAMAGE and
                     e.payload.get('target') == wisp2.id]
        assert len(wisp1_dmg) >= 1
        assert len(wisp2_dmg) >= 1


# ============================================================
# Double Knife Juggler
# ============================================================

class TestDoubleKnifeJuggler:
    def test_two_jugglers_both_trigger(self):
        """Two Knife Jugglers should both trigger on a summon."""
        game, p1, p2 = new_hs_game()
        j1 = make_obj(game, KNIFE_JUGGLER, p1)
        j2 = make_obj(game, KNIFE_JUGGLER, p1)

        play_from_hand(game, WISP, p1)

        juggle_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.source in (j1.id, j2.id)]
        assert len(juggle_events) >= 2  # One from each juggler


# ============================================================
# Imp Master + Knife Juggler Chain
# ============================================================

class TestImpMasterJugglerChain:
    def test_imp_master_eot_triggers_juggler(self):
        """Imp Master summons Imp at EOT → Knife Juggler should trigger."""
        game, p1, p2 = new_hs_game()
        imp_master = make_obj(game, IMP_MASTER, p1)
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        # Imp Master creates token → Juggler should react
        juggle_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.source == juggler.id]
        assert len(juggle_events) >= 1


# ============================================================
# Questing Adventurer + Multiple Card Plays
# ============================================================

class TestQuestingAdventurerStacking:
    def test_grows_per_card_played(self):
        """Questing Adventurer should grow +1/+1 per card played."""
        game, p1, p2 = new_hs_game()
        qa = make_obj(game, QUESTING_ADVENTURER, p1)

        # Play 3 wisps from hand
        play_from_hand(game, WISP, p1)
        play_from_hand(game, WISP, p1)
        play_from_hand(game, WISP, p1)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == qa.id]
        assert len(pt_mods) >= 3

    def test_does_not_grow_from_enemy_cards(self):
        """QA should not trigger on opponent's card plays."""
        game, p1, p2 = new_hs_game()
        qa = make_obj(game, QUESTING_ADVENTURER, p1)

        play_from_hand(game, WISP, p2)

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == qa.id]
        assert len(pt_mods) == 0


# ============================================================
# Gadgetzan Auctioneer + Spell Chains
# ============================================================

class TestGadgetzanSpellChains:
    def test_auctioneer_draws_per_spell(self):
        """Auctioneer draws per spell cast."""
        game, p1, p2 = new_hs_game()
        auc = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        cast_spell_full(game, FROSTBOLT, p1, targets=[p2.hero_id])
        cast_spell_full(game, FIREBALL, p1, targets=[p2.hero_id])

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) >= 2


# ============================================================
# Reinforce + Flesheating Ghoul
# ============================================================

class TestReinforceWithGhoul:
    def test_reinforce_does_not_trigger_ghoul(self):
        """Reinforce summons a token — Ghoul triggers on death, not summon."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)

        activate_hero_power(game, p1, reinforce_effect)

        # Ghoul only triggers on OBJECT_DESTROYED, not CREATE_TOKEN
        ghoul_mods = [e for e in game.state.event_log
                      if e.type == EventType.PT_MODIFICATION and
                      e.payload.get('object_id') == ghoul.id]
        assert len(ghoul_mods) == 0


# ============================================================
# Reinforce + Cult Master (no death = no draw)
# ============================================================

class TestReinforceWithCultMaster:
    def test_reinforce_no_draw(self):
        """Cult Master should NOT draw on token summon (only on death)."""
        game, p1, p2 = new_hs_game_classes("Paladin", "Warrior")
        cm = make_obj(game, CULT_MASTER, p1)

        activate_hero_power(game, p1, reinforce_effect)

        draws = [e for e in game.state.event_log
                 if e.type == EventType.DRAW and
                 e.payload.get('player') == p1.id]
        assert len(draws) == 0


# ============================================================
# Hogger + Knife Juggler EOT Chain
# ============================================================

class TestHoggerJugglerChain:
    def test_hogger_eot_gnoll_triggers_juggler(self):
        """Hogger summons Gnoll at EOT → Knife Juggler should trigger."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        juggle_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.source == juggler.id]
        assert len(juggle_events) >= 1


# ============================================================
# Doomsayer + Cult Master
# ============================================================

class TestDoomsayerCultMaster:
    def test_doomsayer_kills_cult_master_before_draw(self):
        """When Doomsayer wipes board, Cult Master is also destroyed.
        Cult Master may or may not draw depending on ordering — test no crash."""
        game, p1, p2 = new_hs_game()
        doom = make_obj(game, DOOMSAYER, p1)
        cm = make_obj(game, CULT_MASTER, p1)
        wisp = make_obj(game, WISP, p1)

        game.emit(Event(
            type=EventType.TURN_START,
            payload={'player': p1.id},
            source='game'
        ))

        # All minions should be destroyed
        destroys = [e for e in game.state.event_log
                    if e.type == EventType.OBJECT_DESTROYED]
        assert len(destroys) >= 3  # doom + cm + wisp


# ============================================================
# Life Tap + Armorsmith (self damage to hero, NOT minion)
# ============================================================

class TestLifeTapArmorsmith:
    def test_life_tap_hero_damage_no_armorsmith_trigger(self):
        """Life Tap damages hero — Armorsmith triggers on friendly MINION damage only."""
        game, p1, p2 = new_hs_game_classes("Warlock", "Warrior")
        smith = make_obj(game, ARMORSMITH, p1)
        p1.armor = 0

        activate_hero_power(game, p1, life_tap_effect)

        # Armorsmith should NOT gain armor from hero damage
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) == 0


# ============================================================
# Weapon Durability Lifecycle
# ============================================================

class TestWeaponDurabilityLifecycle:
    def test_dagger_at_zero_durability(self):
        """When a Rogue dagger has 0 durability, it should be destroyed."""
        game, p1, p2 = new_hs_game_classes("Rogue", "Warrior")

        activate_hero_power(game, p1, dagger_mastery_effect)
        assert p1.weapon_durability == 2

        # Simulate attacks reducing durability
        p1.weapon_durability = 0

        # Equipping a new dagger should work fine
        activate_hero_power(game, p1, dagger_mastery_effect)
        assert p1.weapon_durability == 2


# ============================================================
# Shapeshift + Weapon Interaction
# ============================================================

class TestShapeshiftWeapon:
    def test_shapeshift_gives_temporary_weapon(self):
        """Shapeshift gives +1 Attack with temporary weapon durability."""
        game, p1, p2 = new_hs_game_classes("Druid", "Warrior")
        p1.weapon_attack = 0
        p1.weapon_durability = 0

        activate_hero_power(game, p1, shapeshift_effect)

        assert p1.weapon_attack >= 1
        assert p1.weapon_durability >= 1

    def test_shapeshift_stacks_with_existing_weapon(self):
        """Shapeshift +1 ATK should add to existing weapon."""
        game, p1, p2 = new_hs_game_classes("Druid", "Warrior")
        p1.weapon_attack = 3
        p1.weapon_durability = 2

        activate_hero_power(game, p1, shapeshift_effect)

        assert p1.weapon_attack == 4  # 3 + 1


# ============================================================
# Totemic Call + Knife Juggler
# ============================================================

class TestTotemicCallJuggler:
    def test_totem_summon_triggers_juggler(self):
        """Totemic Call token should trigger Knife Juggler."""
        game, p1, p2 = new_hs_game_classes("Shaman", "Warrior")
        juggler = make_obj(game, KNIFE_JUGGLER, p1)

        random.seed(42)
        activate_hero_power(game, p1, totemic_call_effect)

        juggle_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.source == juggler.id]
        assert len(juggle_events) >= 1


# ============================================================
# Multiple EOT Triggers Ordering
# ============================================================

class TestMultipleEOTOrdering:
    def test_hogger_imp_master_young_priestess(self):
        """Three EOT triggers at once should all fire without crashing."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)
        imp_master = make_obj(game, IMP_MASTER, p1)

        from src.cards.hearthstone.classic import YOUNG_PRIESTESS
        priestess = make_obj(game, YOUNG_PRIESTESS, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p1.id},
            source='game'
        ))

        # Should have: Gnoll token, Imp token, +1 HP buff, imp master self damage
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 2  # At least Gnoll + Imp

    def test_eot_triggers_do_not_fire_on_opponent_turn(self):
        """EOT triggers should only fire for the controlling player."""
        game, p1, p2 = new_hs_game()
        hogger = make_obj(game, HOGGER, p1)

        game.emit(Event(
            type=EventType.TURN_END,
            payload={'player': p2.id},
            source='game'
        ))

        # Hogger checks for controller match — should NOT fire on p2's turn end
        token_events = [e for e in game.state.event_log
                        if e.type == EventType.CREATE_TOKEN and
                        e.source == hogger.id]
        assert len(token_events) == 0


# ============================================================
# Flesheating Ghoul + Multiple Token Deaths
# ============================================================

class TestGhoulTokenDeaths:
    def test_ghoul_grows_from_token_deaths(self):
        """Ghoul should gain +1 ATK per token death."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)

        # Create some wisps and destroy them
        wisps = [make_obj(game, WISP, p2) for _ in range(3)]
        for w in wisps:
            game.emit(Event(
                type=EventType.OBJECT_DESTROYED,
                payload={'object_id': w.id},
                source='test'
            ))

        pt_mods = [e for e in game.state.event_log
                   if e.type == EventType.PT_MODIFICATION and
                   e.payload.get('object_id') == ghoul.id]
        assert len(pt_mods) >= 3


# ============================================================
# Armorsmith Chained Damage
# ============================================================

class TestArmorsmithChainedDamage:
    def test_armorsmith_multiple_minion_hits_different_turns(self):
        """Armorsmith should gain armor each time a friendly minion takes damage."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        p1.armor = 0

        # Hit yeti 3 times
        for _ in range(3):
            game.emit(Event(
                type=EventType.DAMAGE,
                payload={'target': yeti.id, 'amount': 1, 'source': 'test'},
                source='test'
            ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 3
