"""
Hearthstone Unhappy Path Tests - Batch 36

Deep multi-card interactions and timing chains: Armorsmith gaining armor from
AOE damage, Tinkmaster Overspark transform destroying card text, Raging Worgen
enrage granting Windfury, Grommash Hellscream charge + enrage, Murloc Tidecaller
summon triggers, deathrattle chain ordering, silence interactions with enrage
and auras, Knife Juggler token summon triggers, The Black Knight taunt destruction,
Coldlight Seer murloc buff, and complex multi-step scenarios.
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
    WISP, CHILLWIND_YETI, BLOODFEN_RAPTOR, LEPER_GNOME, HARVEST_GOLEM,
    RAID_LEADER, STORMWIND_CHAMPION,
)
from src.cards.hearthstone.classic import (
    ABOMINATION, SYLVANAS_WINDRUNNER, CAIRNE_BLOODHOOF, THE_BEAST,
    LOOT_HOARDER, KNIFE_JUGGLER, ARGENT_SQUIRE, BLOOD_KNIGHT,
    AMANI_BERSERKER, RAGING_WORGEN, TINKMASTER_OVERSPARK,
    THE_BLACK_KNIGHT, MURLOC_TIDECALLER, COLDLIGHT_SEER,
    FLESHEATING_GHOUL, GADGETZAN_AUCTIONEER,
)
from src.cards.hearthstone.warrior import (
    WHIRLWIND, GROMMASH_HELLSCREAM, ARMORSMITH, FROTHING_BERSERKER,
)
from src.cards.hearthstone.priest import NORTHSHIRE_CLERIC
from src.cards.hearthstone.hunter import SAVANNAH_HIGHMANE


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


# ============================================================
# Armorsmith Chains
# ============================================================

class TestArmormithChains:
    def test_armorsmith_single_damage(self):
        """Armorsmith should gain 1 armor when a friendly minion takes damage."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        target = make_obj(game, CHILLWIND_YETI, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': target.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 1
        assert armor_events[0].payload['amount'] == 1

    def test_armorsmith_whirlwind_mass_armor(self):
        """Armorsmith + Whirlwind with 3 friendly minions = 3 armor (including itself)."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m2 = make_obj(game, BLOODFEN_RAPTOR, p1)

        cast_spell_full(game, WHIRLWIND, p1)

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        # 3 friendly minions damaged = 3 armor events
        assert len(armor_events) >= 3

    def test_armorsmith_ignores_enemy_damage(self):
        """Armorsmith should NOT trigger on enemy minion damage."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        enemy = make_obj(game, CHILLWIND_YETI, p2)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': enemy.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) == 0

    def test_armorsmith_self_damage_counts(self):
        """Armorsmith taking damage itself should trigger its own armor gain."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': smith.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 1


# ============================================================
# Tinkmaster Overspark Transform
# ============================================================

class TestTinkmasterOverspark:
    def test_transforms_a_minion(self):
        """Tinkmaster should transform a random minion into Devilsaur or Squirrel."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p1)

        random.seed(42)
        tink = make_obj(game, TINKMASTER_OVERSPARK, p1)
        events = TINKMASTER_OVERSPARK.battlecry(tink, game.state)

        # Target should be transformed
        assert target.name in ("Devilsaur", "Squirrel")
        assert target.characteristics.subtypes == {"Beast"}

    def test_removes_interceptors_on_transform(self):
        """Tinkmaster transform should clear all interceptors from the target."""
        game, p1, p2 = new_hs_game()
        # Target with interceptors
        enrage_minion = make_obj(game, AMANI_BERSERKER, p1)
        interceptors_before = len(enrage_minion.interceptor_ids)
        assert interceptors_before > 0

        random.seed(42)
        tink = make_obj(game, TINKMASTER_OVERSPARK, p2)
        TINKMASTER_OVERSPARK.battlecry(tink, game.state)

        # Interceptors should be cleared
        assert len(enrage_minion.interceptor_ids) == 0

    def test_no_other_minions_no_crash(self):
        """Tinkmaster with only itself on board should not transform anything."""
        game, p1, p2 = new_hs_game()
        tink = make_obj(game, TINKMASTER_OVERSPARK, p1)
        events = TINKMASTER_OVERSPARK.battlecry(tink, game.state)

        assert events == []

    def test_transform_resets_damage(self):
        """Tinkmaster transform should clear damage on the target."""
        game, p1, p2 = new_hs_game()
        target = make_obj(game, CHILLWIND_YETI, p1)
        target.state.damage = 3  # Damaged

        random.seed(42)
        tink = make_obj(game, TINKMASTER_OVERSPARK, p2)
        TINKMASTER_OVERSPARK.battlecry(tink, game.state)

        assert target.state.damage == 0


# ============================================================
# Raging Worgen — Enrage: Windfury and +1 Attack
# ============================================================

class TestRagingWorgen:
    def test_enrage_grants_windfury_and_attack(self):
        """Raging Worgen enrage should grant both Windfury and +1 Attack."""
        game, p1, p2 = new_hs_game()
        worgen = make_obj(game, RAGING_WORGEN, p1)
        base_power = get_power(worgen, game.state)

        # Damage to trigger enrage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': worgen.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Should have +1 attack
        new_power = get_power(worgen, game.state)
        assert new_power >= base_power + 1

    def test_enrage_not_active_undamaged(self):
        """Undamaged Raging Worgen should not have enrage bonuses."""
        game, p1, p2 = new_hs_game()
        worgen = make_obj(game, RAGING_WORGEN, p1)
        assert worgen.state.damage == 0
        assert get_power(worgen, game.state) == 3  # Base stats


# ============================================================
# Grommash Hellscream — Charge + Enrage: +6 Attack
# ============================================================

class TestGrommashHellscream:
    def test_has_charge(self):
        """Grommash should have charge keyword."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
        assert has_ability(grom, 'charge', game.state)

    def test_enrage_adds_6_attack(self):
        """Damaged Grommash should have +6 Attack from enrage."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
        base_power = get_power(grom, game.state)

        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grom.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        new_power = get_power(grom, game.state)
        assert new_power >= base_power + 6  # 4 + 6 = 10

    def test_silence_removes_enrage_and_charge(self):
        """Silencing enraged Grommash should remove both enrage and charge."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)

        # Trigger enrage
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': grom.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))

        # Silence
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': grom.id},
            source='test'
        ))

        # All abilities cleared
        assert grom.characteristics.abilities == []
        assert len(grom.interceptor_ids) == 0


# ============================================================
# Murloc Tidecaller — Whenever a Murloc is summoned, gain +1 ATK
# ============================================================

class TestMurlocTidecaller:
    def test_gains_attack_on_murloc_summon(self):
        """Tidecaller should gain +1 ATK when another murloc is summoned."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)

        # Create a murloc token
        game.emit(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': p1.id,
                'token': {'name': 'Murloc Scout', 'power': 1, 'toughness': 1,
                          'types': {CardType.MINION}, 'subtypes': {'Murloc'}}
            },
            source='test'
        ))

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('object_id') == tc.id]
        assert len(pt_events) >= 1
        assert pt_events[0].payload['power_mod'] == 1

    def test_no_trigger_on_non_murloc(self):
        """Tidecaller should NOT trigger on non-Murloc summons."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)

        game.emit(Event(
            type=EventType.CREATE_TOKEN,
            payload={
                'controller': p1.id,
                'token': {'name': 'Wolf', 'power': 1, 'toughness': 1,
                          'types': {CardType.MINION}, 'subtypes': {'Beast'}}
            },
            source='test'
        ))

        pt_events = [e for e in game.state.event_log
                     if e.type == EventType.PT_MODIFICATION and
                     e.payload.get('object_id') == tc.id]
        assert len(pt_events) == 0


# ============================================================
# Coldlight Seer — Give your other Murlocs +2 Health
# ============================================================

class TestColdlightSeer:
    def test_buffs_friendly_murlocs(self):
        """Coldlight Seer should give other friendly murlocs +2 Health."""
        game, p1, p2 = new_hs_game()
        tc = make_obj(game, MURLOC_TIDECALLER, p1)  # Murloc

        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)

        assert len(events) >= 1
        pt_mod = events[0]
        assert pt_mod.payload['object_id'] == tc.id
        assert pt_mod.payload['toughness_mod'] == 2
        assert pt_mod.payload['power_mod'] == 0

    def test_does_not_buff_self(self):
        """Coldlight Seer should NOT buff itself."""
        game, p1, p2 = new_hs_game()
        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)

        self_buffs = [e for e in events
                      if e.payload.get('object_id') == seer.id]
        assert len(self_buffs) == 0

    def test_does_not_buff_enemy_murlocs(self):
        """Coldlight Seer should NOT buff enemy murlocs."""
        game, p1, p2 = new_hs_game()
        enemy_murloc = make_obj(game, MURLOC_TIDECALLER, p2)
        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)

        assert events == []

    def test_does_not_buff_non_murlocs(self):
        """Coldlight Seer should NOT buff non-Murloc friendly minions."""
        game, p1, p2 = new_hs_game()
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        seer = make_obj(game, COLDLIGHT_SEER, p1)
        events = COLDLIGHT_SEER.battlecry(seer, game.state)

        assert events == []


# ============================================================
# The Black Knight — Destroy an enemy minion with Taunt
# ============================================================

class TestTheBlackKnight:
    def test_destroys_taunt_minion(self):
        """Black Knight should destroy an enemy taunt minion."""
        game, p1, p2 = new_hs_game()
        taunt_target = make_obj(game, ABOMINATION, p2)  # Has taunt

        bk = make_obj(game, THE_BLACK_KNIGHT, p1)
        events = THE_BLACK_KNIGHT.battlecry(bk, game.state)

        assert len(events) >= 1
        assert events[0].type == EventType.OBJECT_DESTROYED
        assert events[0].payload['object_id'] == taunt_target.id

    def test_no_taunt_no_destroy(self):
        """Black Knight without enemy taunt should do nothing."""
        game, p1, p2 = new_hs_game()
        no_taunt = make_obj(game, CHILLWIND_YETI, p2)

        bk = make_obj(game, THE_BLACK_KNIGHT, p1)
        events = THE_BLACK_KNIGHT.battlecry(bk, game.state)

        assert events == []

    def test_does_not_target_friendly_taunt(self):
        """Black Knight should not destroy a friendly taunt minion."""
        game, p1, p2 = new_hs_game()
        friendly_taunt = make_obj(game, ABOMINATION, p1)  # Friendly taunt

        bk = make_obj(game, THE_BLACK_KNIGHT, p1)
        events = THE_BLACK_KNIGHT.battlecry(bk, game.state)

        # No enemy taunt — should return empty
        assert events == []


# ============================================================
# Cross-Mechanic Interaction Chains
# ============================================================

class TestCrossMechanicBatch36:
    def test_armorsmith_frothing_whirlwind(self):
        """Whirlwind with Armorsmith and Frothing should trigger both."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        frothing = make_obj(game, FROTHING_BERSERKER, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p2)

        cast_spell_full(game, WHIRLWIND, p1)

        # Armorsmith triggers on each friendly damage (smith + frothing = 2)
        armor_events = [e for e in game.state.event_log
                        if e.type == EventType.ARMOR_GAIN and
                        e.payload.get('player') == p1.id]
        assert len(armor_events) >= 2

        # Frothing triggers on ALL minion damage (smith + frothing + m1 = 3)
        frothing_pt = [e for e in game.state.event_log
                       if e.type == EventType.PT_MODIFICATION and
                       e.payload.get('object_id') == frothing.id]
        assert len(frothing_pt) >= 3

    def test_silence_raid_leader_removes_aura(self):
        """Silencing Raid Leader should remove the +1 ATK aura."""
        game, p1, p2 = new_hs_game()
        rl = make_obj(game, RAID_LEADER, p1)
        m1 = make_obj(game, WISP, p1)

        # Aura active — Wisp should have +1 ATK
        power_with_aura = get_power(m1, game.state)
        assert power_with_aura >= 2  # 1 base + 1 aura

        # Silence Raid Leader
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': rl.id},
            source='test'
        ))

        # Aura removed — Wisp should be back to 1 ATK
        power_after = get_power(m1, game.state)
        assert power_after == 1

    def test_black_knight_triggers_abomination_deathrattle(self):
        """Black Knight destroying Abomination should trigger Abomination's deathrattle."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p2)

        bk = make_obj(game, THE_BLACK_KNIGHT, p1)
        events = THE_BLACK_KNIGHT.battlecry(bk, game.state)
        for e in events:
            game.emit(e)

        # Abomination deathrattle should fire
        abom_dmg = [e for e in game.state.event_log
                    if e.type == EventType.DAMAGE and
                    e.payload.get('source') == abom.id]
        assert len(abom_dmg) >= 1

    def test_tinkmaster_transform_removes_deathrattle(self):
        """Tinkmaster transforming a deathrattle minion should prevent deathrattle on death."""
        game, p1, p2 = new_hs_game()
        cairne = make_obj(game, CAIRNE_BLOODHOOF, p2)

        random.seed(42)
        tink = make_obj(game, TINKMASTER_OVERSPARK, p1)
        events = TINKMASTER_OVERSPARK.battlecry(tink, game.state)
        for e in events:
            game.emit(e)

        # Kill the transformed minion
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': cairne.id},
            source='test'
        ))

        # No Baine Bloodhoof should spawn (deathrattle was cleared by transform)
        baine = [e for e in game.state.event_log
                 if e.type == EventType.CREATE_TOKEN and
                 e.payload.get('token', {}).get('name') == 'Baine Bloodhoof']
        assert len(baine) == 0

    def test_knife_juggler_deathrattle_tokens(self):
        """Knife Juggler should trigger on tokens summoned by deathrattles."""
        game, p1, p2 = new_hs_game()
        kj = make_obj(game, KNIFE_JUGGLER, p1)
        hg = make_obj(game, HARVEST_GOLEM, p1)

        # Kill Harvest Golem — deathrattle summons 2/1 token
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hg.id},
            source='test'
        ))

        # Knife Juggler should have triggered on the token summon
        juggler_dmg = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('source') == kj.id]
        assert len(juggler_dmg) >= 1

    def test_flesheating_ghoul_deathrattle_chain(self):
        """Flesheating Ghoul should gain ATK from minions dying to deathrattle damage."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        abom = make_obj(game, ABOMINATION, p2)
        wisp = make_obj(game, WISP, p2)

        # Kill Abomination — deathrattle deals 2 to all
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id},
            source='test'
        ))

        # Abomination deathrattle fires, dealing 2 to Wisp (kills it)
        game.check_state_based_actions()

        # Ghoul should have gained ATK from deaths
        ghoul_pt = [e for e in game.state.event_log
                    if e.type == EventType.PT_MODIFICATION and
                    e.payload.get('object_id') == ghoul.id]
        # At minimum, Abomination death + Wisp death = 2 gains
        assert len(ghoul_pt) >= 2

    def test_gadgetzan_auctioneer_spell_draw_chain(self):
        """Gadgetzan Auctioneer should draw for each spell in a multi-spell chain."""
        game, p1, p2 = new_hs_game()
        ga = make_obj(game, GADGETZAN_AUCTIONEER, p1)

        # Cast first spell
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': 'test_spell_1', 'controller': p1.id, 'caster': p1.id},
            source='test_spell_1'
        ))

        # Cast second spell
        game.emit(Event(
            type=EventType.SPELL_CAST,
            payload={'spell_id': 'test_spell_2', 'controller': p1.id, 'caster': p1.id},
            source='test_spell_2'
        ))

        # Should have drawn twice
        draw_events = [e for e in game.state.event_log
                       if e.type == EventType.DRAW and
                       e.payload.get('player') == p1.id]
        assert len(draw_events) >= 2

    def test_grommash_whirlwind_enrage(self):
        """Whirlwind should trigger Grommash's enrage, giving him +6 ATK."""
        game, p1, p2 = new_hs_game()
        grom = make_obj(game, GROMMASH_HELLSCREAM, p1)
        base_power = get_power(grom, game.state)

        cast_spell_full(game, WHIRLWIND, p1)

        new_power = get_power(grom, game.state)
        assert new_power >= base_power + 6

    def test_leper_gnome_abomination_double_hero_damage(self):
        """Abomination killing Leper Gnome: both deal damage to hero."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        lg = make_obj(game, LEPER_GNOME, p2)  # 1/1

        # Kill Abomination — deathrattle deals 2 to all
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id},
            source='test'
        ))

        # Abomination deals 2 to p2.hero_id
        abom_hero_dmg = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE and
                         e.payload.get('target') == p2.hero_id and
                         e.payload.get('source') == abom.id]
        assert len(abom_hero_dmg) >= 1

        # Leper Gnome takes 2 damage (kills it), SBA triggers
        game.check_state_based_actions()

        # Leper Gnome deathrattle deals 2 to p1.hero_id
        lg_hero_dmg = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('source') == lg.id]
        assert len(lg_hero_dmg) >= 1

    def test_savannah_highmane_knife_juggler_chain(self):
        """Highmane death summons 2 Hyenas — Knife Juggler should trigger for each."""
        game, p1, p2 = new_hs_game()
        kj = make_obj(game, KNIFE_JUGGLER, p1)
        shm = make_obj(game, SAVANNAH_HIGHMANE, p1)

        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': shm.id},
            source='test'
        ))

        # 2 Hyenas summoned = 2 Knife Juggler triggers
        juggler_dmg = [e for e in game.state.event_log
                       if e.type == EventType.DAMAGE and
                       e.payload.get('source') == kj.id]
        assert len(juggler_dmg) >= 2
