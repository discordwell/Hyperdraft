"""
Default Layer Values

Fallback values and heuristic inference when LLM is unavailable.
These provide reasonable defaults based on card characteristics.
"""

import re
from typing import Optional, TYPE_CHECKING

from .types import (
    CardStrategy,
    DeckRole,
    MatchupGuide,
    DeckAnalysis,
    MatchupAnalysis
)

if TYPE_CHECKING:
    from src.engine import CardDefinition, CardType


def default_card_strategy(card_name: str) -> CardStrategy:
    """Create a default CardStrategy with neutral values."""
    return CardStrategy(
        card_name=card_name,
        timing="any",
        base_priority=0.5,
        role="utility",
        target_priority=["creature"],
        when_to_play="Play when mana efficient.",
        when_not_to_play="Consider holding if better targets may appear.",
        targeting_advice="Target the most threatening permanent."
    )


def default_deck_role(card_name: str, deck_hash: str) -> DeckRole:
    """Create a default DeckRole with neutral values."""
    return DeckRole(
        card_name=card_name,
        deck_hash=deck_hash,
        role_weight=1.0,
        curve_slot=3,
        synergy_cards=[],
        enables=[],
        is_key_card=False,
        deck_role="Standard inclusion.",
        play_pattern="Play on curve when possible.",
        synergy_notes=""
    )


def default_matchup_guide(card_name: str, matchup_hash: str) -> MatchupGuide:
    """Create a default MatchupGuide with neutral values."""
    return MatchupGuide(
        card_name=card_name,
        matchup_hash=matchup_hash,
        priority_modifier=1.0,
        save_for=[],
        dont_use_on=[],
        threat_level=0.5,
        matchup_role="Standard usage.",
        key_targets="Target based on board state.",
        timing_advice="Play when advantageous."
    )


def default_deck_analysis(deck_hash: str) -> DeckAnalysis:
    """Create a default DeckAnalysis."""
    return DeckAnalysis(
        deck_hash=deck_hash,
        archetype="midrange",
        win_conditions=["creature damage"],
        key_cards=[],
        curve={},
        game_plan="Develop board and attack."
    )


def default_matchup_analysis(matchup_hash: str) -> MatchupAnalysis:
    """Create a default MatchupAnalysis."""
    return MatchupAnalysis(
        matchup_hash=matchup_hash,
        our_role="midrange",
        their_threats=[],
        their_answers=[],
        game_plan="Play reactively based on opponent's actions.",
        key_turns={}
    )


def infer_card_strategy(card_def: 'CardDefinition') -> CardStrategy:
    """
    Infer CardStrategy from card characteristics.

    Uses heuristics based on card type, mana cost, and text.
    """
    from src.engine import CardType, ManaCost

    name = card_def.name
    text = (card_def.text or "").lower()
    types = card_def.characteristics.types
    mana_cost = card_def.characteristics.mana_cost or ""

    # Parse mana value
    try:
        cost = ManaCost.parse(mana_cost)
        mana_value = cost.mana_value
    except:
        mana_value = 0

    # Determine timing
    timing = "any"
    if CardType.INSTANT in types:
        timing = "reactive"
    elif mana_value <= 2:
        timing = "early"
    elif mana_value >= 5:
        timing = "late"
    else:
        timing = "mid"

    # Determine role
    role = "utility"
    if CardType.CREATURE in types:
        power = card_def.characteristics.power or 0
        if power >= 4:
            role = "threat"
        elif "haste" in text or "double strike" in text:
            role = "threat"
        elif "deathtouch" in text or "lifelink" in text:
            role = "utility"
        else:
            role = "threat"
    elif "destroy" in text or "exile" in text or "damage" in text:
        role = "removal"
    elif "counter" in text and "spell" in text:
        role = "removal"
    elif "draw" in text and "card" in text:
        role = "engine"
    elif CardType.LAND in types:
        role = "utility"

    # Determine priority
    base_priority = 0.5
    if role == "removal":
        base_priority = 0.7
    elif role == "threat":
        base_priority = 0.6
    elif role == "engine":
        base_priority = 0.5
    elif role == "finisher":
        base_priority = 0.8

    # Adjust for efficiency
    if CardType.CREATURE in types:
        power = card_def.characteristics.power or 0
        toughness = card_def.characteristics.toughness or 0
        if mana_value > 0:
            efficiency = (power + toughness) / mana_value
            if efficiency >= 2.5:
                base_priority += 0.1

    # Determine target priority
    target_priority = ["creature"]
    if "target player" in text or "target opponent" in text:
        target_priority = ["player"]
    elif "any target" in text:
        target_priority = ["creature", "player"]
    elif "target planeswalker" in text:
        target_priority = ["planeswalker", "creature"]

    # Generate text guidance
    when_to_play = _infer_when_to_play(card_def, role, timing)
    when_not_to_play = _infer_when_not_to_play(card_def, role)
    targeting_advice = _infer_targeting_advice(card_def, role)

    return CardStrategy(
        card_name=name,
        timing=timing,
        base_priority=base_priority,
        role=role,
        target_priority=target_priority,
        when_to_play=when_to_play,
        when_not_to_play=when_not_to_play,
        targeting_advice=targeting_advice
    )


def infer_deck_role(
    card_def: 'CardDefinition',
    deck_cards: list[str],
    deck_hash: str,
    archetype: str = "midrange"
) -> DeckRole:
    """
    Infer DeckRole from card and deck context.

    Uses heuristics based on deck composition.
    """
    from src.engine import CardType, ManaCost

    name = card_def.name
    text = (card_def.text or "").lower()
    types = card_def.characteristics.types
    mana_cost = card_def.characteristics.mana_cost or ""

    # Parse mana value
    try:
        cost = ManaCost.parse(mana_cost)
        mana_value = cost.mana_value
    except:
        mana_value = 0

    # Count copies in deck
    card_count = deck_cards.count(name)

    # Determine role weight
    role_weight = 1.0
    if card_count >= 4:
        role_weight = 1.2  # Full playset = important
    elif card_count == 1:
        role_weight = 0.8  # Singleton = less central

    # Check for key card indicators
    is_key_card = False
    power = card_def.characteristics.power or 0

    # High-impact cards
    if CardType.CREATURE in types and power >= 4:
        is_key_card = True
    if "win the game" in text or "you win" in text:
        is_key_card = True
    if card_count >= 4 and ("draw" in text or "destroy" in text):
        is_key_card = True

    # Curve slot
    curve_slot = mana_value if mana_value > 0 else 1

    # Find synergy cards (basic keyword matching)
    synergy_cards = []
    card_keywords = _extract_keywords(text)
    for other_card in set(deck_cards):
        if other_card != name:
            # Would need card database to check synergies properly
            pass

    # Generate text guidance based on archetype
    deck_role = _infer_deck_role_text(card_def, archetype)
    play_pattern = _infer_play_pattern(card_def, archetype, mana_value)
    synergy_notes = ""

    return DeckRole(
        card_name=name,
        deck_hash=deck_hash,
        role_weight=role_weight,
        curve_slot=curve_slot,
        synergy_cards=synergy_cards,
        enables=[],
        is_key_card=is_key_card,
        deck_role=deck_role,
        play_pattern=play_pattern,
        synergy_notes=synergy_notes
    )


def _infer_when_to_play(card_def, role: str, timing: str) -> str:
    """Generate when-to-play guidance."""
    from src.engine import CardType

    types = card_def.characteristics.types
    text = (card_def.text or "").lower()

    if CardType.INSTANT in types:
        if "counter" in text:
            return "Hold for high-value spells. Counter threats and key plays."
        elif "damage" in text or "destroy" in text:
            return "Hold until opponent commits a threat, then respond."
        else:
            return "Play at end of opponent's turn to maximize information."

    if role == "removal":
        return "Use to answer opponent's best threat. Prioritize cards that would otherwise win the game."

    if role == "threat":
        if timing == "early":
            return "Deploy early to start the clock. Pressure opponent's life total."
        else:
            return "Play when the board is stable or you can protect it."

    if timing == "early":
        return "Play early to establish board presence."
    elif timing == "late":
        return "Hold for maximum impact. This is a late-game finisher."

    return "Play when mana efficient and impactful."


def _infer_when_not_to_play(card_def, role: str) -> str:
    """Generate when-not-to-play guidance."""
    from src.engine import CardType

    types = card_def.characteristics.types
    text = (card_def.text or "").lower()

    if CardType.CREATURE in types:
        if "haste" not in text:
            return "Don't play into obvious board wipes. Watch for open mana."

    if role == "removal":
        return "Don't waste on low-value targets. Save for must-answer threats."

    if "counter" in text:
        return "Don't counter low-impact spells. Save for game-changers."

    return "Don't play when a better target may appear soon."


def _infer_targeting_advice(card_def, role: str) -> str:
    """Generate targeting guidance."""
    text = (card_def.text or "").lower()

    if "destroy" in text or "exile" in text:
        return "Target the most threatening permanent. Prioritize cards that win the game."

    if "damage" in text:
        return "Target creatures that trade favorably, or go face if lethal is near."

    if "counter" in text:
        return "Counter spells that would significantly swing the game state."

    return "Target based on current board state and opponent's game plan."


def _infer_deck_role_text(card_def, archetype: str) -> str:
    """Generate deck role description."""
    from src.engine import CardType

    types = card_def.characteristics.types
    text = (card_def.text or "").lower()

    if archetype == "aggro":
        if CardType.CREATURE in types:
            return "Damage source. Attack every turn possible."
        elif "damage" in text:
            return "Reach or removal. Use to push through damage."
        return "Support card. Enable the aggro game plan."

    elif archetype == "control":
        if "destroy" in text or "exile" in text or "counter" in text:
            return "Answer card. Use to handle opponent's threats."
        elif "draw" in text:
            return "Card advantage. Keep the hand full."
        return "Part of the control shell. Survive to win conditions."

    else:  # midrange
        if CardType.CREATURE in types:
            return "Threat. Play to dominate the board."
        elif "destroy" in text or "exile" in text:
            return "Removal. Clear the way for your threats."
        return "Support the midrange game plan."


def _infer_play_pattern(card_def, archetype: str, mana_value: int) -> str:
    """Generate play pattern guidance."""
    if archetype == "aggro":
        return f"Play on curve (turn {mana_value}). Keep pressure up."

    if archetype == "control":
        if mana_value <= 2:
            return "Play early if needed, but value holding mana open."
        return "Play when you can protect it or the board is clear."

    # Midrange
    return f"Optimal on turn {mana_value}. Adapt based on board state."


def _extract_keywords(text: str) -> set:
    """Extract MTG keywords from card text."""
    keywords = {
        "flying", "trample", "haste", "vigilance", "lifelink",
        "deathtouch", "first strike", "double strike", "hexproof",
        "menace", "reach", "flash", "indestructible", "ward"
    }
    found = set()
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            found.add(kw)
    return found
