"""
Regression tests for the Hearthstone SECRET legal-action gap.

Audit commit 535b7598 found that both card-play dispatchers
(`src/engine/hearthstone_legal_actions.py::_execute_card_play` and
`src/ai/hearthstone_adapter.py::HearthstoneAIAdapter._execute_card_play`)
had a MINION/WEAPON/SPELL elif chain that silently no-op'd on SECRET
cards: mana was never deducted, the card never moved hand → battlefield,
and the secret's `setup_interceptors` (gated
``duration='while_on_battlefield'``) never went live. 16 secrets across
Mage/Paladin/Hunter were affected, including 3 shipping starter-deck
cards: EXPLOSIVE_TRAP, FREEZING_TRAP, NOBLE_SACRIFICE.

These tests force a secret into hand + sufficient mana, route the play
through each dispatcher, and assert:
  (a) the secret reached the battlefield zone,
  (b) mana was deducted,
  (c) the hand was decremented,
  (d) the secret's interceptor is wired and active,
  (e) the secret triggers on the next opponent action.
"""

import asyncio

import pytest

from src.engine.game import Game
from src.engine.types import CardType, Event, EventType, InterceptorPriority, ZoneType
from src.cards.hearthstone.heroes import HEROES
from src.cards.hearthstone.hero_powers import HERO_POWERS
from src.cards.hearthstone.basic import BLOODFEN_RAPTOR
from src.cards.hearthstone.hunter import EXPLOSIVE_TRAP, FREEZING_TRAP
from src.cards.hearthstone.paladin import NOBLE_SACRIFICE


# ---------------------------------------------------------------------------
# Shared scene helpers
# ---------------------------------------------------------------------------

def _hs_scene(p1_class: str = "Hunter", p2_class: str = "Warrior") -> tuple[Game, "Player", "Player"]:
    """Build a Hearthstone game with two heroes wired up.

    The opponent is given a Bloodfen Raptor on the battlefield so secrets
    that need an attacker (Explosive Trap, Freezing Trap) have something
    real to react to.
    """
    game = Game(mode="hearthstone")
    p1 = game.add_player("Player1", life=30)
    p2 = game.add_player("Player2", life=30)
    game.setup_hearthstone_player(p1, HEROES[p1_class], HERO_POWERS[p1_class])
    game.setup_hearthstone_player(p2, HEROES[p2_class], HERO_POWERS[p2_class])
    game.turn_manager.set_turn_order([p1.id, p2.id])
    return game, p1, p2


def _drop_secret_into_hand(game: Game, owner, card_def):
    """Create a secret card object directly in the owner's hand."""
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.HAND,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _drop_minion(game: Game, owner, card_def):
    """Create a minion on the battlefield (for opp-attacker setups)."""
    return game.create_object(
        name=card_def.name,
        owner_id=owner.id,
        zone=ZoneType.BATTLEFIELD,
        characteristics=card_def.characteristics,
        card_def=card_def,
    )


def _hand_ids(game: Game, player_id: str) -> list[str]:
    return list(game.state.zones[f"hand_{player_id}"].objects)


def _battlefield_ids(game: Game) -> list[str]:
    return list(game.state.zones["battlefield"].objects)


def _set_active(game: Game, player_id: str) -> None:
    """Force the given player to be the active player for the legal-actions
    dispatcher's same-turn check."""
    game.state.active_player = player_id
    game.turn_manager.hs_turn_state.active_player_id = player_id


# ---------------------------------------------------------------------------
# legal_hearthstone_actions / _execute_card_play (engine dispatcher)
# ---------------------------------------------------------------------------

def test_legal_actions_generator_lists_secrets():
    """A secret in hand + enough mana must appear as an HS_PLAY_CARD action."""
    from src.engine.hearthstone_legal_actions import legal_hearthstone_actions

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, EXPLOSIVE_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5

    actions = legal_hearthstone_actions(game, p1.id)
    play_action = next(
        (a for a in actions if a["type"] == "HS_PLAY_CARD" and a["payload"]["card_id"] == secret.id),
        None,
    )
    assert play_action is not None, (
        f"legal_hearthstone_actions did not surface Explosive Trap; "
        f"got actions={[a['id'] for a in actions]}"
    )


def test_legal_actions_dispatcher_plays_secret_to_battlefield():
    """_execute_card_play (engine path) must move a SECRET hand → battlefield,
    deduct mana, and decrement hand."""
    from src.engine.hearthstone_legal_actions import _execute_card_play

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, EXPLOSIVE_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5
    starting_mana = p1.mana_crystals_available

    events = asyncio.run(_execute_card_play(game, p1.id, secret.id, []))

    # (a) battlefield contains the secret
    assert secret.id in _battlefield_ids(game), (
        f"Secret did not reach battlefield; battlefield={_battlefield_ids(game)}"
    )
    assert game.state.objects[secret.id].zone == ZoneType.BATTLEFIELD
    # (b) mana deducted (Explosive Trap costs {2})
    assert p1.mana_crystals_available == starting_mana - 2, (
        f"Mana not deducted: was {starting_mana}, now {p1.mana_crystals_available}"
    )
    # (c) hand decremented
    assert secret.id not in _hand_ids(game, p1.id)
    # ZONE_CHANGE event emitted
    assert any(e.type == EventType.ZONE_CHANGE for e in events), (
        f"No ZONE_CHANGE event in returned events: {events}"
    )


def test_legal_actions_dispatcher_activates_secret_interceptor():
    """The secret's interceptor must be registered and active once on battlefield."""
    from src.engine.hearthstone_legal_actions import _execute_card_play

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, EXPLOSIVE_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5

    asyncio.run(_execute_card_play(game, p1.id, secret.id, []))

    # The secret_setup wires a REACT interceptor on Explosive Trap.
    secret_interceptors = [
        ic for ic in game.state.interceptors.values() if ic.source == secret.id
    ]
    assert secret_interceptors, "Secret has no registered interceptors after play"

    # Pipeline gating: source must be on battlefield to be considered active.
    active = game.pipeline._get_interceptors(InterceptorPriority.REACT)
    assert any(ic.source == secret.id for ic in active), (
        "Secret interceptor is not gated-active on the battlefield"
    )


def test_explosive_trap_fires_on_opponent_attack_via_legal_actions():
    """End-to-end: play Explosive Trap through the legal-action dispatcher,
    then have the opponent attack the hero. Trap must deal 2 damage to all
    enemies (i.e. p1's hero takes none, p2's hero/minions take 2)."""
    from src.engine.hearthstone_legal_actions import _execute_card_play

    game, p1, p2 = _hs_scene(p1_class="Hunter", p2_class="Warrior")
    _set_active(game, p1.id)
    raptor = _drop_minion(game, p2, BLOODFEN_RAPTOR)  # 3/2 attacker on p2's side
    secret = _drop_secret_into_hand(game, p1, EXPLOSIVE_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5

    asyncio.run(_execute_card_play(game, p1.id, secret.id, []))
    assert secret.id in _battlefield_ids(game)

    # Hand off the turn to the opponent so the secret's filter (active_player != owner) is satisfied.
    _set_active(game, p2.id)
    raptor.state.summoning_sickness = False  # let it attack same turn

    p1_hero = game.state.objects[p1.players_hero_id] if hasattr(p1, "players_hero_id") else game.state.objects[p1.hero_id]
    p1_hero_starting = p1_hero.state.damage
    p2_hero = game.state.objects[p2.hero_id]
    p2_hero_starting = p2_hero.state.damage

    # Opponent's raptor attacks p1's hero — should trigger Explosive Trap.
    asyncio.run(game.combat_manager.declare_attack(raptor.id, p1_hero.id))

    # The secret should have moved to graveyard (consumed) and dealt 2 damage to enemies.
    assert game.state.objects[secret.id].zone == ZoneType.GRAVEYARD, (
        f"Explosive Trap should be consumed; zone={game.state.objects[secret.id].zone}"
    )
    # p2's hero (the opposing hero from the secret's perspective) took 2 damage.
    assert p2_hero.state.damage == p2_hero_starting + 2, (
        f"Opposing hero should have taken 2 damage from Explosive Trap; "
        f"got damage={p2_hero.state.damage}"
    )


# ---------------------------------------------------------------------------
# HearthstoneAIAdapter._execute_card_play (AI dispatcher)
# ---------------------------------------------------------------------------

def test_ai_adapter_dispatcher_plays_secret_to_battlefield():
    """The AI adapter's _execute_card_play must also handle SECRET."""
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, FREEZING_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5
    starting_mana = p1.mana_crystals_available

    adapter = HearthstoneAIAdapter(difficulty="hard")
    card_action = {"card_id": secret.id, "card": secret, "targets": []}

    events = asyncio.run(adapter._execute_card_play(card_action, game.state, game))

    # (a) battlefield contains the secret
    assert secret.id in _battlefield_ids(game), (
        f"AI adapter did not move SECRET to battlefield; battlefield={_battlefield_ids(game)}"
    )
    # (b) mana deducted (Freezing Trap costs {2})
    assert p1.mana_crystals_available == starting_mana - 2
    # (c) hand decremented
    assert secret.id not in _hand_ids(game, p1.id)
    # ZONE_CHANGE in returned events
    assert any(e.type == EventType.ZONE_CHANGE for e in events)
    # cards_played_this_turn ticked (used by combo cards)
    assert p1.cards_played_this_turn >= 1


def test_ai_adapter_chooses_secret_when_playable():
    """The AI adapter's card-selection path should consider secrets playable."""
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, NOBLE_SACRIFICE)  # {1}
    p1.mana_crystals = 3
    p1.mana_crystals_available = 3

    adapter = HearthstoneAIAdapter(difficulty="hard")
    chosen = adapter._choose_card_to_play(game.state, p1.id, game)
    assert chosen is not None, "AI refused to play the only legal card (a secret)"
    assert chosen["card_id"] == secret.id


def test_noble_sacrifice_reaches_battlefield_via_ai_path():
    """Noble Sacrifice is one of the 3 shipping starter-deck secrets the
    audit flagged. Confirm it now reaches the battlefield via the AI path."""
    from src.ai.hearthstone_adapter import HearthstoneAIAdapter

    game, p1, _p2 = _hs_scene(p1_class="Paladin", p2_class="Warrior")
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, NOBLE_SACRIFICE)
    p1.mana_crystals = 3
    p1.mana_crystals_available = 3

    adapter = HearthstoneAIAdapter(difficulty="hard")
    asyncio.run(
        adapter._execute_card_play(
            {"card_id": secret.id, "card": secret, "targets": []},
            game.state,
            game,
        )
    )
    assert secret.id in _battlefield_ids(game)
    assert game.state.objects[secret.id].zone == ZoneType.BATTLEFIELD


def test_freezing_trap_reaches_battlefield_via_legal_actions():
    """Freezing Trap is the second of the 3 shipping starter-deck secrets."""
    from src.engine.hearthstone_legal_actions import _execute_card_play

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, FREEZING_TRAP)
    p1.mana_crystals = 5
    p1.mana_crystals_available = 5

    asyncio.run(_execute_card_play(game, p1.id, secret.id, []))
    assert secret.id in _battlefield_ids(game)


# ---------------------------------------------------------------------------
# Smoke test: insufficient mana still blocks
# ---------------------------------------------------------------------------

def test_secret_with_insufficient_mana_is_not_played():
    """Regression safety: if the player can't pay, SECRET must NOT slip
    through (the dispatcher's mana-gate runs before the type branch)."""
    from src.engine.hearthstone_legal_actions import _execute_card_play

    game, p1, _p2 = _hs_scene()
    _set_active(game, p1.id)
    secret = _drop_secret_into_hand(game, p1, EXPLOSIVE_TRAP)  # costs {2}
    p1.mana_crystals = 1
    p1.mana_crystals_available = 1

    asyncio.run(_execute_card_play(game, p1.id, secret.id, []))
    # Still in hand, still no mana spent
    assert secret.id in _hand_ids(game, p1.id)
    assert secret.id not in _battlefield_ids(game)
    assert p1.mana_crystals_available == 1
