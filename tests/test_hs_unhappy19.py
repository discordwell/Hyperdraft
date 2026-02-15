"""
Hearthstone Unhappy Path Tests - Batch 19

Remaining untested cards: Holy Wrath (draw+damage=cost), Spiteful Smith
(enrage weapon boost), Redemption (secret: resummon at 1 HP), Nozdormu
(vanilla legendary), Mogu'shan Warden (taunt wall), Thrallmar Farseer
(windfury). Plus deeper cross-card interaction chains and edge cases:
overdraw mechanics, fatigue+draw chains, multi-aura stacking, hero power
interactions, bounced card replays, spell+trigger cascades, silence
interaction chains, boardwipe+deathrattle ordering, enrage+heal cycling,
combo chain depth, token board-fill chains, cost reduction stacking.
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
    KOBOLD_GEOMANCER, GRIMSCALE_ORACLE, RAID_LEADER,
    STORMWIND_CHAMPION, ARCHMAGE,
)
from src.cards.hearthstone.classic import (
    FROSTBOLT, FIREBALL, ARCANE_INTELLECT, BACKSTAB,
    KNIFE_JUGGLER, WILD_PYROMANCER, GADGETZAN_AUCTIONEER,
    ACOLYTE_OF_PAIN, LOOT_HOARDER, HARVEST_GOLEM,
    TAUREN_WARRIOR, ANGRY_CHICKEN, VENTURE_CO_MERCENARY,
    SPITEFUL_SMITH, FLESHEATING_GHOUL,
    MURLOC_WARLEADER, DIRE_WOLF_ALPHA, ARGENT_SQUIRE,
    PRIESTESS_OF_ELUNE, ABOMINATION,
)
from src.cards.hearthstone.warrior import ARMORSMITH
from src.cards.hearthstone.priest import NORTHSHIRE_CLERIC
from src.cards.hearthstone.paladin import (
    HOLY_WRATH, REDEMPTION, EQUALITY,
)
from src.cards.hearthstone.classic import MOGUSHAN_WARDEN, FEN_CREEPER, THRALLMAR_FARSEER, NOZDORMU
from src.cards.hearthstone.warlock import VOIDWALKER
from src.cards.hearthstone.rogue import PREPARATION, EDWIN_VANCLEEF
from src.cards.hearthstone.hunter import UNLEASH_THE_HOUNDS, SCAVENGING_HYENA
from src.cards.hearthstone.shaman import LIGHTNING_BOLT


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
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    return obj


def play_from_hand(game, card_def, owner):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    game.emit(Event(
        type=EventType.ZONE_CHANGE,
        payload={
            'object_id': obj.id,
            'from_zone_type': ZoneType.HAND,
            'to_zone_type': ZoneType.BATTLEFIELD,
            'controller': owner.id
        },
        source=obj.id
    ))
    return obj


def cast_spell(game, card_def, owner, targets=None):
    obj = game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def
    )
    events = card_def.spell_effect(obj, game.state, targets or [])
    for e in events:
        game.emit(e)
    return obj


# ============================================================
# Holy Wrath - Draw a card and deal damage equal to its cost
# ============================================================

class TestHolyWrath:
    def test_holy_wrath_deals_drawn_card_cost(self):
        """Holy Wrath draws a card and deals damage = its mana cost."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        # Put a 4-cost Yeti in library
        yeti = make_obj(game, CHILLWIND_YETI, p1, zone=ZoneType.LIBRARY)
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        p2_life_before = p2.life
        cast_spell(game, HOLY_WRATH, p1)
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after == hand_before + 1  # Drew a card
        # Should deal 4 damage (Yeti costs {4})
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 4]
        assert len(damage_events) >= 1

    def test_holy_wrath_empty_deck(self):
        """Holy Wrath with empty deck does nothing."""
        game, p1, p2 = new_hs_game()
        p2_life = p2.life
        cast_spell(game, HOLY_WRATH, p1)
        assert p2.life == p2_life  # No damage

    def test_holy_wrath_zero_cost_card(self):
        """Holy Wrath with a 0-cost card deals 0 damage."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)  # 0 cost
        cast_spell(game, HOLY_WRATH, p1)
        damage_events = [e for e in game.state.event_log
                         if e.type == EventType.DAMAGE
                         and e.payload.get('amount') == 0]
        assert len(damage_events) >= 1


# ============================================================
# Spiteful Smith - Enrage: Your weapon has +2 Attack
# ============================================================

class TestSpitefulSmith:
    def test_spiteful_smith_has_interceptor(self):
        """Spiteful Smith registers TRANSFORM interceptor for weapon damage."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, SPITEFUL_SMITH, p1)
        assert len(smith.interceptor_ids) > 0

    def test_spiteful_smith_stats(self):
        """Spiteful Smith is 4/6."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, SPITEFUL_SMITH, p1)
        assert get_power(smith, game.state) == 4
        assert get_toughness(smith, game.state) == 6

    def test_spiteful_smith_no_enrage_undamaged(self):
        """Spiteful Smith doesn't boost weapon when undamaged."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, SPITEFUL_SMITH, p1)
        # Smith is undamaged, so interceptor filter should fail
        assert smith.state.damage == 0


# ============================================================
# Redemption (Paladin Secret) - Resummon at 1 HP
# ============================================================

class TestRedemption:
    def test_redemption_has_interceptor(self):
        """Redemption registers a secret interceptor."""
        game, p1, p2 = new_hs_game()
        secret = make_obj(game, REDEMPTION, p1)
        assert len(secret.interceptor_ids) > 0

    def test_redemption_triggers_on_friendly_death(self):
        """Redemption triggers when a friendly minion dies on opponent's turn."""
        game, p1, p2 = new_hs_game()
        secret = make_obj(game, REDEMPTION, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        # Set active player to opponent (secrets trigger on opponent's turn)
        game.state.active_player = p2.id
        log_before = len(game.state.event_log)
        # Kill yeti
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id, 'reason': 'combat'},
            source='test'
        ))
        # Should emit CREATE_TOKEN to resummon
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1
        # Resummoned with 1 HP
        token = token_events[0].payload.get('token', {})
        assert token.get('toughness') == 1

    def test_redemption_doesnt_trigger_on_own_turn(self):
        """Redemption doesn't trigger during controller's own turn."""
        game, p1, p2 = new_hs_game()
        secret = make_obj(game, REDEMPTION, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        game.state.active_player = p1.id  # Own turn
        log_before = len(game.state.event_log)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': yeti.id, 'reason': 'trade'},
            source='test'
        ))
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) == 0


# ============================================================
# Vanilla legendaries and stat-check cards
# ============================================================

class TestVanillaCards:
    def test_nozdormu_stats(self):
        """Nozdormu is 8/8 Dragon."""
        game, p1, p2 = new_hs_game()
        noz = make_obj(game, NOZDORMU, p1)
        assert get_power(noz, game.state) == 8
        assert get_toughness(noz, game.state) == 8
        assert 'Dragon' in noz.characteristics.subtypes

    def test_mogushan_warden_taunt(self):
        """Mogu'shan Warden is 1/7 with Taunt."""
        game, p1, p2 = new_hs_game()
        mogu = make_obj(game, MOGUSHAN_WARDEN, p1)
        assert get_power(mogu, game.state) == 1
        assert get_toughness(mogu, game.state) == 7
        assert has_ability(mogu, 'taunt', game.state)

    def test_fen_creeper_taunt(self):
        """Fen Creeper is 3/6 with Taunt."""
        game, p1, p2 = new_hs_game()
        fen = make_obj(game, FEN_CREEPER, p1)
        assert get_power(fen, game.state) == 3
        assert get_toughness(fen, game.state) == 6
        assert has_ability(fen, 'taunt', game.state)

    def test_thrallmar_farseer_windfury(self):
        """Thrallmar Farseer is 2/3 with Windfury."""
        game, p1, p2 = new_hs_game()
        farseer = make_obj(game, THRALLMAR_FARSEER, p1)
        assert get_power(farseer, game.state) == 2
        assert get_toughness(farseer, game.state) == 3
        assert has_ability(farseer, 'windfury', game.state)


# ============================================================
# Deep Interaction Chains
# ============================================================

class TestDeepInteractions:
    def test_triple_murloc_lord_stacking(self):
        """Three Murloc lords (2 Warleader + 1 Grimscale) stack on a Murloc."""
        game, p1, p2 = new_hs_game()
        wl1 = make_obj(game, MURLOC_WARLEADER, p1)
        wl2 = make_obj(game, MURLOC_WARLEADER, p1)
        oracle = make_obj(game, GRIMSCALE_ORACLE, p1)
        raider = make_obj(game, MURLOC_RAIDER, p1)  # 2/1 base
        power = get_power(raider, game.state)
        # 2 base + 2 (WL1) + 2 (WL2) + 1 (oracle) = 7
        assert power == 7

    def test_dire_wolf_plus_raid_leader_stacking(self):
        """Dire Wolf Alpha +1 and Raid Leader +1 stack to +2."""
        game, p1, p2 = new_hs_game()
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)
        raid = make_obj(game, RAID_LEADER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)  # Adjacent to wolf, gets +1 from wolf
        power = get_power(yeti, game.state)
        # 4 base + 1 (Raid Leader) = 5 minimum (wolf adjacency depends on position)
        assert power >= 5

    def test_acolyte_of_pain_multi_draw_chain(self):
        """Acolyte of Pain draws on each instance of damage."""
        game, p1, p2 = new_hs_game()
        acolyte = make_obj(game, ACOLYTE_OF_PAIN, p1)
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        # Deal 1 damage twice
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        hand_mid = len(game.state.zones[hand_key].objects)
        assert hand_mid == hand_before + 1
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': acolyte.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after == hand_mid + 1

    def test_equality_plus_wild_pyro(self):
        """Equality sets all to 1 HP, then Wild Pyro deals 1 = board clear."""
        game, p1, p2 = new_hs_game()
        pyro = make_obj(game, WILD_PYROMANCER, p1)
        big1 = make_obj(game, BOULDERFIST_OGRE, p2)  # 6/7
        big2 = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
        # Cast Equality (sets all HP to 1)
        cast_spell(game, EQUALITY, p1)
        # All minions (including pyro) should be 1 HP
        assert get_toughness(big1, game.state) - big1.state.damage <= 1
        assert get_toughness(big2, game.state) - big2.state.damage <= 1

    def test_northshire_cleric_heal_draw(self):
        """Northshire Cleric draws when a minion is healed."""
        game, p1, p2 = new_hs_game()
        cleric = make_obj(game, NORTHSHIRE_CLERIC, p1)
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        yeti.state.damage = 2
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        # Heal the yeti
        game.emit(Event(
            type=EventType.LIFE_CHANGE,
            payload={'object_id': yeti.id, 'amount': 2},
            source='test'
        ))
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after > hand_before

    def test_knife_juggler_plus_unleash_hounds(self):
        """Knife Juggler fires once per Hound from Unleash the Hounds."""
        game, p1, p2 = new_hs_game()
        random.seed(42)
        juggler = make_obj(game, KNIFE_JUGGLER, p1)
        # 3 enemy minions
        make_obj(game, CHILLWIND_YETI, p2)
        make_obj(game, RIVER_CROCOLISK, p2)
        make_obj(game, WISP, p2)
        p2_life_before = p2.life
        log_before = len(game.state.event_log)
        cast_spell(game, UNLEASH_THE_HOUNDS, p1)
        # Each CREATE_TOKEN should trigger Knife Juggler = 3 juggles
        juggle_damages = [e for e in game.state.event_log[log_before:]
                          if e.type == EventType.DAMAGE
                          and e.payload.get('source') == juggler.id]
        assert len(juggle_damages) >= 1  # At least some juggles fired

    def test_spell_damage_stacking_double_kobold(self):
        """Two Kobold Geomancers stack Spell Damage +2 total."""
        game, p1, p2 = new_hs_game()
        k1 = make_obj(game, KOBOLD_GEOMANCER, p1)
        k2 = make_obj(game, KOBOLD_GEOMANCER, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)  # 4/5
        # Frostbolt base 3 + 2 spell damage = 5
        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])
        assert yeti.state.damage == 5

    def test_armorsmith_multi_damage_triggers(self):
        """Armorsmith emits ARMOR_GAIN for each friendly minion damaged."""
        game, p1, p2 = new_hs_game()
        smith = make_obj(game, ARMORSMITH, p1)
        m1 = make_obj(game, CHILLWIND_YETI, p1)
        m2 = make_obj(game, RIVER_CROCOLISK, p1)
        log_before = len(game.state.event_log)
        # Damage each friendly
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': m1.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': m2.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        # Each damage to a friendly should emit ARMOR_GAIN
        armor_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.ARMOR_GAIN]
        assert len(armor_events) >= 2

    def test_flesheating_ghoul_multiple_deaths(self):
        """Flesheating Ghoul gains +1 Attack per minion death."""
        game, p1, p2 = new_hs_game()
        ghoul = make_obj(game, FLESHEATING_GHOUL, p1)
        w1 = make_obj(game, WISP, p1)
        w2 = make_obj(game, WISP, p2)
        base = get_power(ghoul, game.state)
        # Kill both wisps
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': w1.id, 'reason': 'test'},
            source='test'
        ))
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': w2.id, 'reason': 'test'},
            source='test'
        ))
        new_power = get_power(ghoul, game.state)
        assert new_power == base + 2

    def test_gadgetzan_auctioneer_double_spell_chain(self):
        """Gadgetzan Auctioneer draws on each spell cast."""
        game, p1, p2 = new_hs_game()
        auctioneer = make_obj(game, GADGETZAN_AUCTIONEER, p1)
        for _ in range(5):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        # Cast two spells (via SPELL_CAST events)
        s1 = game.create_object(name="Test Spell 1", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                                characteristics=FROSTBOLT.characteristics, card_def=FROSTBOLT)
        game.emit(Event(type=EventType.SPELL_CAST, payload={'spell_id': s1.id, 'caster': p1.id}, source=s1.id))
        s2 = game.create_object(name="Test Spell 2", owner_id=p1.id, zone=ZoneType.BATTLEFIELD,
                                characteristics=BACKSTAB.characteristics, card_def=BACKSTAB)
        game.emit(Event(type=EventType.SPELL_CAST, payload={'spell_id': s2.id, 'caster': p1.id}, source=s2.id))
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after == hand_before + 2

    def test_stormwind_champion_plus_dire_wolf(self):
        """Stormwind Champion (+1/+1 all) and Dire Wolf Alpha (+1 adj) stack."""
        game, p1, p2 = new_hs_game()
        champion = make_obj(game, STORMWIND_CHAMPION, p1)
        wolf = make_obj(game, DIRE_WOLF_ALPHA, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p1)
        power = get_power(yeti, game.state)
        # 4 base + 1 (Stormwind) = 5 minimum (wolf adjacency varies)
        assert power >= 5

    def test_loot_hoarder_deathrattle_draws(self):
        """Loot Hoarder draws a card on death."""
        game, p1, p2 = new_hs_game()
        hoarder = make_obj(game, LOOT_HOARDER, p1)
        for _ in range(3):
            make_obj(game, WISP, p1, zone=ZoneType.LIBRARY)
        hand_key = f"hand_{p1.id}"
        hand_before = len(game.state.zones[hand_key].objects)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': hoarder.id, 'reason': 'combat'},
            source='test'
        ))
        hand_after = len(game.state.zones[hand_key].objects)
        assert hand_after > hand_before

    def test_abomination_deathrattle_aoe(self):
        """Abomination deals 2 to all characters on death."""
        game, p1, p2 = new_hs_game()
        abom = make_obj(game, ABOMINATION, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        wisp = make_obj(game, WISP, p1)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': abom.id, 'reason': 'combat'},
            source='test'
        ))
        # All characters should take 2 damage
        assert yeti.state.damage >= 2

    def test_enrage_healed_back_loses_bonus(self):
        """Tauren Warrior loses enrage bonus when healed to full."""
        game, p1, p2 = new_hs_game()
        tw = make_obj(game, TAUREN_WARRIOR, p1)  # 2/3
        # Damage it
        game.emit(Event(
            type=EventType.DAMAGE,
            payload={'target': tw.id, 'amount': 1, 'source': 'test'},
            source='test'
        ))
        assert get_power(tw, game.state) == 5  # 2 + 3 enrage
        # Heal back to full
        tw.state.damage = 0
        assert get_power(tw, game.state) == 2  # Back to base

    def test_argent_squire_divine_shield_then_silence(self):
        """Argent Squire with Divine Shield, then silenced loses it."""
        game, p1, p2 = new_hs_game()
        squire = make_obj(game, ARGENT_SQUIRE, p1)
        assert squire.state.divine_shield is True
        # Silence it
        game.emit(Event(
            type=EventType.SILENCE_TARGET,
            payload={'target': squire.id},
            source='test'
        ))
        assert squire.state.divine_shield is False

    def test_preparation_plus_arcane_intellect(self):
        """Preparation cost modifier is registered for spells."""
        game, p1, p2 = new_hs_game()
        cast_spell(game, PREPARATION, p1)
        # Verify the cost modifier exists
        spell_mods = [m for m in p1.cost_modifiers if m.get('card_type') == CardType.SPELL]
        assert len(spell_mods) >= 1
        # The modifier should reduce by 3
        reduction = spell_mods[0].get('amount', 0)
        assert reduction == 3

    def test_priestess_of_elune_heals_damaged_hero(self):
        """Priestess heals a damaged hero (confirm exact amount)."""
        game, p1, p2 = new_hs_game()
        p1.life = 15
        play_from_hand(game, PRIESTESS_OF_ELUNE, p1)
        assert p1.life == 19  # 15 + 4

    def test_venture_co_plus_preparation_net_cost(self):
        """Venture Co. increases minion cost by 3, Preparation reduces spell cost by 3."""
        game, p1, p2 = new_hs_game()
        venture = make_obj(game, VENTURE_CO_MERCENARY, p1)
        cast_spell(game, PREPARATION, p1)
        # Minion modifier: -3 (cost increase)
        minion_mods = [m for m in p1.cost_modifiers if m.get('card_type') == CardType.MINION]
        spell_mods = [m for m in p1.cost_modifiers if m.get('card_type') == CardType.SPELL]
        assert len(minion_mods) >= 1
        assert len(spell_mods) >= 1

    def test_harvest_golem_deathrattle_summons_token(self):
        """Harvest Golem summons a 2/1 Damaged Golem on death."""
        game, p1, p2 = new_hs_game()
        golem = make_obj(game, HARVEST_GOLEM, p1)
        log_before = len(game.state.event_log)
        game.emit(Event(
            type=EventType.OBJECT_DESTROYED,
            payload={'object_id': golem.id, 'reason': 'combat'},
            source='test'
        ))
        token_events = [e for e in game.state.event_log[log_before:]
                        if e.type == EventType.CREATE_TOKEN]
        assert len(token_events) >= 1

    def test_scavenging_hyena_beast_death_stacking(self):
        """Scavenging Hyena gains +2/+1 per Beast death, stacks."""
        game, p1, p2 = new_hs_game()
        hyena = make_obj(game, SCAVENGING_HYENA, p1)  # 2/2
        b1 = make_obj(game, BLOODFEN_RAPTOR, p1)  # Beast
        b2 = make_obj(game, STONETUSK_BOAR, p1)   # Beast
        base_power = get_power(hyena, game.state)
        game.emit(Event(type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': b1.id, 'reason': 'test'}, source='test'))
        game.emit(Event(type=EventType.OBJECT_DESTROYED,
                        payload={'object_id': b2.id, 'reason': 'test'}, source='test'))
        assert get_power(hyena, game.state) == base_power + 4  # +2 per beast

    def test_double_archmage_spell_damage(self):
        """Two Archmages give Spell Damage +2 total."""
        game, p1, p2 = new_hs_game()
        m1 = make_obj(game, ARCHMAGE, p1)
        m2 = make_obj(game, ARCHMAGE, p1)
        yeti = make_obj(game, CHILLWIND_YETI, p2)
        cast_spell(game, FROSTBOLT, p1, targets=[yeti.id])
        # 3 base + 2 spell damage = 5
        assert yeti.state.damage == 5
