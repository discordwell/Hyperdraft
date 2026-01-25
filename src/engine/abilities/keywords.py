"""
Ability System - Keyword Abilities

Keyword abilities are typically checked via has_ability() query,
but some need active interceptors for their effects.
"""

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from src.engine.types import GameObject, GameState, Interceptor


# Keywords that don't need interceptors (checked via has_ability)
PASSIVE_KEYWORDS = {
    "flying",
    "reach",
    "vigilance",
    "haste",
    "defender",
    "hexproof",
    "shroud",
    "indestructible",
    "menace",
    "trample",
    "flash",
    "deathtouch",
    "double strike",
    "first strike",
}

# Reminder text for keywords
KEYWORD_REMINDER_TEXT = {
    "flying": "This creature can't be blocked except by creatures with flying or reach.",
    "reach": "This creature can block creatures with flying.",
    "vigilance": "Attacking doesn't cause this creature to tap.",
    "haste": "This creature can attack and {T} as soon as it comes under your control.",
    "defender": "This creature can't attack.",
    "hexproof": "This creature can't be the target of spells or abilities your opponents control.",
    "shroud": "This creature can't be the target of spells or abilities.",
    "indestructible": "Damage and effects that say \"destroy\" don't destroy this.",
    "menace": "This creature can't be blocked except by two or more creatures.",
    "trample": "This creature can deal excess combat damage to the player or planeswalker it's attacking.",
    "flash": "You may cast this spell any time you could cast an instant.",
    "deathtouch": "Any amount of damage this deals to a creature is enough to destroy it.",
    "double strike": "This creature deals both first-strike and regular combat damage.",
    "first strike": "This creature deals combat damage before creatures without first strike.",
    "lifelink": "Damage dealt by this creature also causes you to gain that much life.",
    "prowess": "Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.",
}


def get_keyword_interceptors(keyword: str, obj: 'GameObject', state: 'GameState') -> list['Interceptor']:
    """
    Get interceptors for keywords that need active effects.

    Most keywords are checked via has_ability() and don't need interceptors.
    Some keywords (lifelink, prowess, etc.) have triggered/replacement effects.
    """
    from src.engine.types import (
        Interceptor, InterceptorPriority, InterceptorAction, InterceptorResult,
        EventType, new_id, CardType
    )

    keyword_lower = keyword.lower()

    if keyword_lower == "lifelink":
        # Lifelink: When this creature deals damage, you gain that much life
        def damage_filter(event, state, src=obj):
            if event.type != EventType.DAMAGE:
                return False
            return event.payload.get('source') == src.id

        def damage_handler(event, state, src=obj):
            from src.engine.types import Event
            amount = event.payload.get('amount', 0)
            return InterceptorResult(
                action=InterceptorAction.REACT,
                new_events=[Event(
                    type=EventType.LIFE_CHANGE,
                    payload={'player': src.controller, 'amount': amount},
                    source=src.id,
                    controller=src.controller
                )]
            )

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=damage_filter,
            handler=damage_handler,
            duration='while_on_battlefield'
        )]

    elif keyword_lower == "prowess":
        # Prowess: Whenever you cast a noncreature spell, +1/+1 until end of turn
        def cast_filter(event, state, src=obj):
            if event.type != EventType.CAST:
                return False
            if event.payload.get('caster') != src.controller:
                return False
            # Check if noncreature
            spell_types = set(event.payload.get('types', []))
            return CardType.CREATURE not in spell_types

        def cast_handler(event, state, src=obj):
            # This would need a temporary P/T boost effect
            # For now, we'd need to create a temporary QUERY interceptor
            # This is complex and deferred for later implementation
            return InterceptorResult(action=InterceptorAction.PASS)

        return [Interceptor(
            id=new_id(),
            source=obj.id,
            controller=obj.controller,
            priority=InterceptorPriority.REACT,
            filter=cast_filter,
            handler=cast_handler,
            duration='while_on_battlefield'
        )]

    elif keyword_lower == "deathtouch":
        # Deathtouch: Damage to creatures is lethal regardless of amount
        # This is typically handled in the damage resolution system
        # by checking has_ability("deathtouch")
        return []

    elif keyword_lower == "first strike" or keyword_lower == "double strike":
        # Combat order - handled by combat manager checking has_ability
        return []

    # Most keywords are passive and don't need interceptors
    return []
