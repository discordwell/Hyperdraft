"""Round 5 — wire up the 8 deferred Auras flagged by Agent B round 4.

Three trigger shapes (all in `_make_attached_triggered_ability_listener`):
- ``trigger_on="death"`` — fires when the enchanted creature dies.
- ``trigger_on="enchanted_controller_upkeep"`` — fires on enchanted's
  controller's upkeep.
- (no new shapes — all 8 use the two above)

Cards covered:
    Death-trigger Auras:
        - SYMBIOTE_BOND (MOP): return Aura to hand on enchanted death
        - WEB_COCOON (MOP): controller draws on enchanted LBF
        - GENETIC_MUTATION (MOP): create 3/3 Mutant token on enchanted death
        - SUPER_SAIYAN_AURA (DBZ): 3 dmg to opp on enchanted death
        - AVATAR_DESTINY (PA): mill power-equal on enchanted death

    Enchanted-controller-upkeep Auras:
        - MAJIN_MARK (DBZ): controller loses 1 life on their upkeep
        - TRIGGER_DRUG (MHA): enchanted deals 1 dmg to its controller
        - NINE_TAILS_CLOAK (NRT): controller loses 2 life
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


from src.engine import (
    Game, Event, EventType, ZoneType, Color, CardType,
    make_creature, get_power,
)
from src.cards.custom.man_of_pider import (
    SYMBIOTE_BOND, WEB_COCOON, GENETIC_MUTATION,
)
from src.cards.custom.dragon_ball import MAJIN_MARK, SUPER_SAIYAN_AURA
from src.cards.custom.penultimate_avatar import AVATAR_DESTINY
from src.cards.custom.my_hero_academia import TRIGGER_DRUG
from src.cards.custom.naruto import NINE_TAILS_CLOAK


def _new_game():
    game = Game()
    p1 = game.add_player("Alice", life=20)
    p2 = game.add_player("Bob", life=20)
    return game, p1, p2


def _put(game, owner, card_def, zone=ZoneType.BATTLEFIELD):
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=zone,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _plain(name="Plain 1/1"):
    return make_creature(
        name=name, power=1, toughness=1, mana_cost="{1}",
        colors=set(), subtypes={"Human"},
    )


def _attach(game, aura, target):
    game.emit(Event(
        type=EventType.ATTACH,
        payload={'object_id': aura.id, 'target_id': target.id},
        source=aura.id,
    ))


def _destroy(game, obj):
    game.emit(Event(
        type=EventType.DESTROY,
        payload={'object_id': obj.id, 'reason': 'test'},
        source=None,
    ))


# ---------------------------------------------------------------------------
# Death-trigger Auras
# ---------------------------------------------------------------------------


def test_symbiote_bond_returns_to_hand_on_death():
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, SYMBIOTE_BOND)
    _attach(game, aura, target)
    assert aura.zone == ZoneType.BATTLEFIELD

    _destroy(game, target)
    # Aura should be back in p1's hand (not graveyard via 704.5n falloff).
    assert aura.zone == ZoneType.HAND, (
        f"Expected Symbiote Bond in HAND after enchanted death; got {aura.zone}"
    )


def test_web_cocoon_draws_card_on_enchanted_death():
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, WEB_COCOON)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    _destroy(game, target)
    new = game.state.event_log[before:]
    draws = [
        e for e in new
        if e.type == EventType.DRAW and e.payload.get('player') == p1.id
    ]
    assert draws, (
        f"Expected DRAW on p1 from Web Cocoon; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_genetic_mutation_creates_mutant_token_on_death():
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, GENETIC_MUTATION)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    _destroy(game, target)
    new = game.state.event_log[before:]
    tokens = [
        e for e in new
        if e.type == EventType.CREATE_TOKEN
        and 'Mutant' in (e.payload.get('token', {}).get('subtypes', set()))
    ]
    assert tokens, (
        f"Expected CREATE_TOKEN Mutant; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_super_saiyan_aura_deals_damage_on_death():
    game, p1, p2 = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, SUPER_SAIYAN_AURA)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    _destroy(game, target)
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p2.id
        and e.payload.get('amount') == 3
    ]
    assert damages, (
        f"Expected 3 DAMAGE to p2 from Super Saiyan Aura; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_avatar_destiny_mills_power_on_death():
    """AVATAR_DESTINY: when enchanted dies, controller mills cards equal
    to dying creature's power. Aura gives +2/+2, so a 1/1 becomes 3/3 →
    mills 3."""
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, AVATAR_DESTINY)
    _attach(game, aura, target)
    # With +2/+2 the target should read as 3/3.
    assert get_power(target, game.state) == 3, (
        f"Expected enchanted power 3 (1 + 2); got {get_power(target, game.state)}"
    )

    before = len(game.state.event_log)
    _destroy(game, target)
    new = game.state.event_log[before:]
    mills = [
        e for e in new
        if e.type == EventType.MILL
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == 3
    ]
    assert mills, (
        f"Expected MILL 3 on p1 from Avatar Destiny; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ---------------------------------------------------------------------------
# Enchanted-controller-upkeep Auras
# ---------------------------------------------------------------------------


def test_majin_mark_drains_enchanted_controller():
    game, p1, p2 = _new_game()
    target = _put(game, p2, _plain())
    aura = _put(game, p1, MAJIN_MARK)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    game.state.active_player = p2.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p2.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p2.id
        and e.payload.get('amount') == -1
    ]
    assert drains, (
        f"Expected -1 LIFE_CHANGE on p2 (enchanted's controller); "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_trigger_drug_deals_damage_on_upkeep():
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, TRIGGER_DRUG)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    damages = [
        e for e in new
        if e.type == EventType.DAMAGE
        and e.payload.get('target') == p1.id
        and e.payload.get('amount') == 1
    ]
    assert damages, (
        f"Expected 1 DAMAGE to p1 from Trigger Drug; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


def test_nine_tails_cloak_drains_enchanted_controller():
    game, p1, _ = _new_game()
    target = _put(game, p1, _plain())
    aura = _put(game, p1, NINE_TAILS_CLOAK)
    _attach(game, aura, target)

    before = len(game.state.event_log)
    game.state.active_player = p1.id
    game.emit(Event(
        type=EventType.PHASE_START,
        payload={'phase': 'upkeep', 'active_player': p1.id},
    ))
    new = game.state.event_log[before:]
    drains = [
        e for e in new
        if e.type == EventType.LIFE_CHANGE
        and e.payload.get('player') == p1.id
        and e.payload.get('amount') == -2
    ]
    assert drains, (
        f"Expected -2 LIFE_CHANGE on p1 from Nine-Tails Cloak; "
        f"recent={[e.type.name for e in new[-10:]]}"
    )


# ---------------------------------------------------------------------------
# Static-effect verifications (one per Aura to confirm the existing
# behavior wasn't broken by the wiring)
# ---------------------------------------------------------------------------


def test_static_pt_and_keywords_preserved():
    """Spot-check each Aura's static P/T mod after attach to confirm
    make_aura_setup's existing path still runs alongside the new trigger."""
    from src.engine.queries import has_ability
    cases = [
        (SYMBIOTE_BOND, 2, 2, "menace"),
        (GENETIC_MUTATION, 3, 3, "trample"),
        (SUPER_SAIYAN_AURA, 2, 2, "haste"),
        (MAJIN_MARK, 3, 0, "menace"),
        (TRIGGER_DRUG, 3, 1, None),
        (NINE_TAILS_CLOAK, 3, 0, "trample"),
        (AVATAR_DESTINY, 2, 2, None),
        (WEB_COCOON, 0, 0, "defender"),
    ]
    for aura_def, dp, dt, kw in cases:
        game, p1, _ = _new_game()
        target = _put(game, p1, _plain(name=f"target_for_{aura_def.name}"))
        base_p = get_power(target, game.state)
        aura = _put(game, p1, aura_def)
        _attach(game, aura, target)
        new_p = get_power(target, game.state)
        assert new_p == base_p + dp, (
            f"{aura_def.name}: expected power {base_p}+{dp}={base_p+dp}; got {new_p}"
        )
        if kw:
            assert has_ability(target, kw, game.state), (
                f"{aura_def.name}: expected target to have {kw}"
            )


if __name__ == "__main__":
    print("=" * 70)
    print("Deferred Auras wired — Round 5")
    print("=" * 70)
    tests = [
        test_symbiote_bond_returns_to_hand_on_death,
        test_web_cocoon_draws_card_on_enchanted_death,
        test_genetic_mutation_creates_mutant_token_on_death,
        test_super_saiyan_aura_deals_damage_on_death,
        test_avatar_destiny_mills_power_on_death,
        test_majin_mark_drains_enchanted_controller,
        test_trigger_drug_deals_damage_on_upkeep,
        test_nine_tails_cloak_drains_enchanted_controller,
        test_static_pt_and_keywords_preserved,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    print("=" * 70)
    print(f"Total: {passed}/{len(tests)} passed")
    print("=" * 70)
