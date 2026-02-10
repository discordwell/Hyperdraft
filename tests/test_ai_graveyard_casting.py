import sys

sys.path.insert(0, "/Users/discordwell/Projects/Hyperdraft")

from src.engine import Game, ZoneType, Color, make_instant, make_land
from src.engine.priority import ActionType
from src.ai import AIEngine


def _make_test_flashback_draw_instant(name: str):
    # Text includes "Draw a card" so AI strategies score it as card advantage.
    def noop_resolve(targets, state):
        return []

    return make_instant(
        name=name,
        mana_cost="{1}{U}",
        colors={Color.BLUE},
        text=(
            "Flashback {2}{U} (You may cast this card from your graveyard for its flashback cost. "
            "Then exile it.)\n"
            "Draw a card."
        ),
        resolve=noop_resolve,
    )


def test_ai_can_choose_graveyard_cast_for_both_players():
    game = Game()
    p1 = game.add_player("P1")
    p2 = game.add_player("P2")

    # Put a flashback spell in each graveyard.
    c1_def = _make_test_flashback_draw_instant("P1 Flashback Draw")
    c2_def = _make_test_flashback_draw_instant("P2 Flashback Draw")
    c1 = game.create_object(
        name=c1_def.name,
        owner_id=p1.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=c1_def.characteristics,
        card_def=c1_def,
    )
    c2 = game.create_object(
        name=c2_def.name,
        owner_id=p2.id,
        zone=ZoneType.GRAVEYARD,
        characteristics=c2_def.characteristics,
        card_def=c2_def,
    )

    # Ensure flashback {2}{U} is payable for both players.
    island_def = make_land("Island", subtypes={"Island"})
    for _ in range(3):
        game.create_object(
            name="Island",
            owner_id=p1.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )
        game.create_object(
            name="Island",
            owner_id=p2.id,
            zone=ZoneType.BATTLEFIELD,
            characteristics=island_def.characteristics,
            card_def=island_def,
        )

    legal_p1 = game.priority_system.get_legal_actions(p1.id)
    legal_p2 = game.priority_system.get_legal_actions(p2.id)

    assert any(a.type == ActionType.CAST_SPELL and a.card_id == c1.id for a in legal_p1)
    assert any(a.type == ActionType.CAST_SPELL and a.card_id == c2.id for a in legal_p2)

    # Ultra difficulty is deterministic (no randomness / no intentional mistakes).
    ai = AIEngine(difficulty="ultra")

    action1 = ai.get_action(p1.id, game.state, legal_p1)
    assert action1.type == ActionType.CAST_SPELL
    assert action1.card_id == c1.id
    # Graveyard cast options include an ability_id to disambiguate flashback/etc.
    assert action1.ability_id is not None

    action2 = ai.get_action(p2.id, game.state, legal_p2)
    assert action2.type == ActionType.CAST_SPELL
    assert action2.card_id == c2.id
    assert action2.ability_id is not None

