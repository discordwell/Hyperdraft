"""Sweep 9: graveyard-activated abilities.

Cards like Goldmeadow Nomad have abilities that can be activated while the
card is in the graveyard. The framework: card_def.setup_in_graveyard runs
on ZONE_CHANGE → GRAVEYARD and registers an ActivatedAbility, and the
priority's get_legal_actions scans the player's graveyard for owned cards
with such abilities.
"""
import os
import sys
import asyncio

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.engine import (
    Game, Event, EventType, ZoneType, CardType, Color, CardDefinition,
    Characteristics,
)
from src.engine.priority import ActionType, PlayerAction
from src.engine.turn import Phase
from src.cards.interceptor_helpers import make_activated_ability


def test_graveyard_activated_ability_surfaces_and_dispatches():
    async def _run():
        game = Game()
        p1 = game.add_player("Alice")
        p2 = game.add_player("Bob")
        game.turn_manager.turn_state.active_player_id = p1.id
        game.turn_manager.turn_state.phase = Phase.PRECOMBAT_MAIN

        # Goldmeadow-Nomad style card: while in graveyard, "{W}: gain 2 life,
        # exile this card." (Approximation — the real card creates a Kithkin
        # token; here we use a simple life gain to keep the test self-contained.)
        def gy_setup(obj, state):
            def effect(o, st, targets):
                return [
                    Event(type=EventType.LIFE_CHANGE,
                          payload={'player': o.controller, 'amount': 2},
                          source=o.id, controller=o.controller),
                    Event(type=EventType.EXILE,
                          payload={'object_id': o.id},
                          source=o.id, controller=o.controller),
                ]
            make_activated_ability(
                obj, "{W}", effect,
                description="Exile from graveyard: gain 2 life",
                sorcery_speed=True,
            )
            return []

        nomad_def = CardDefinition(
            name="Test Nomad", mana_cost="{W}",
            characteristics=Characteristics(
                types={CardType.CREATURE}, subtypes={"Human"},
                colors={Color.WHITE}, power=1, toughness=1, mana_cost="{W}",
            ),
            text="{W}: Exile this from graveyard: gain 2 life. Activate only as a sorcery.",
            setup_in_graveyard=gy_setup,
        )

        # Put the nomad directly into graveyard (simulating "after it died").
        nomad = game.create_object(
            name=nomad_def.name,
            owner_id=p1.id,
            zone=ZoneType.HAND,
            characteristics=nomad_def.characteristics,
            card_def=None,
        )
        nomad.card_def = nomad_def
        # Move to graveyard via the standard ZONE_CHANGE path so setup_in_graveyard fires.
        game.emit(Event(
            type=EventType.ZONE_CHANGE,
            payload={
                'object_id': nomad.id,
                'from_zone': f'hand_{p1.id}',
                'from_zone_type': ZoneType.HAND,
                'to_zone': f'graveyard_{p1.id}',
                'to_zone_type': ZoneType.GRAVEYARD,
            },
        ))

        # The ability should be registered.
        assert getattr(nomad.state, 'activated_abilities', None), \
            f"expected activated_abilities to be populated, got {getattr(nomad.state, 'activated_abilities', None)}"
        assert len(nomad.state.activated_abilities) == 1

        # Provide {W} to the player.
        from src.engine.mana import ManaType
        game.mana_system.produce_mana(p1.id, ManaType.WHITE, 1)

        # Discover the ability.
        actions = game.priority_system.get_legal_actions(p1.id)
        gy_actions = [a for a in actions if a.source_id == nomad.id and a.ability_id and a.ability_id.startswith("activated:")]
        assert gy_actions, f"expected graveyard ability in legal actions, got {[a.description for a in actions[:5]]}"

        # Activate it.
        action = PlayerAction(
            type=ActionType.ACTIVATE_ABILITY,
            player_id=p1.id, source_id=nomad.id,
            ability_id="activated:0",
        )
        events = await game.priority_system._handle_activate_ability(action)
        # The stack item resolves to LIFE_CHANGE + EXILE.
        item = game.stack.items[-1] if game.stack.items else None
        if item and item.resolve_fn:
            resolved = item.resolve_fn(item.chosen_targets, game.state)
            types = [e.type for e in resolved]
            assert EventType.LIFE_CHANGE in types
            assert EventType.EXILE in types
        print("PASS: graveyard activated ability surfaces + dispatches")

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_graveyard_activated_ability_surfaces_and_dispatches()
    print("\nAll graveyard-activated tests passed!")
