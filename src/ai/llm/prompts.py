"""
LLM Prompt Templates

Prompts for generating strategy layers and analysis.
"""

# === Card Strategy (Layer 1) ===

CARD_STRATEGY_SYSTEM = """You are an expert Magic: The Gathering strategist.
Analyze cards and provide strategic guidance for when and how to play them.
Be concise and practical. Focus on competitive play patterns."""

CARD_STRATEGY_PROMPT = """Analyze this Magic: The Gathering card:

Name: {name}
Mana Cost: {cost}
Type: {type}
Text: {text}
Power/Toughness: {pt}

Provide strategic analysis including:
1. Timing: When is best to cast this? (early/mid/late/reactive/any)
2. Priority: How eager should we be to play this? (0.0=low, 1.0=high)
3. Role: What role does this card play? (removal/threat/utility/finisher/engine)
4. Target Priority: If this targets, what should it target? (creature/planeswalker/player)
5. When to Play: Text guidance for when to play this card
6. When NOT to Play: When should we hold this card?
7. Targeting Advice: If it targets, what makes a good target?"""

CARD_STRATEGY_SCHEMA = {
    "timing": "str",
    "base_priority": "float",
    "role": "str",
    "target_priority": "list[str]",
    "when_to_play": "str",
    "when_not_to_play": "str",
    "targeting_advice": "str"
}


# === Deck Role (Layer 2) ===

DECK_ROLE_SYSTEM = """You are an expert Magic: The Gathering deck builder and pilot.
Analyze how a specific card functions within a given deck context.
Consider synergies, curve, and game plan."""

DECK_ROLE_PROMPT = """Analyze how this card functions in this deck:

**Card:**
Name: {card_name}
Mana Cost: {card_cost}
Type: {card_type}
Text: {card_text}

**Deck Context:**
Archetype: {archetype}
Colors: {colors}
Key Cards: {key_cards}
Curve: {curve}

**Other Cards in Deck:**
{deck_list}

Analyze this card's role in the deck:
1. Role Weight: How important is this card to the deck? (0.5=filler, 1.0=normal, 1.5=key)
2. Curve Slot: Ideal turn to play this (1-7+)
3. Synergy Cards: What other cards in the deck does this combo with?
4. Is Key Card: Is this central to the game plan?
5. Deck Role: Text description of what this card does for the deck
6. Play Pattern: When and how to sequence this card
7. Synergy Notes: How this card interacts with other deck cards"""

DECK_ROLE_SCHEMA = {
    "role_weight": "float",
    "curve_slot": "int",
    "synergy_cards": "list[str]",
    "is_key_card": "bool",
    "deck_role": "str",
    "play_pattern": "str",
    "synergy_notes": "str"
}


# === Matchup Guide (Layer 3) ===

MATCHUP_GUIDE_SYSTEM = """You are an expert Magic: The Gathering tournament player.
Analyze how to use cards in specific matchups.
Consider the opponent's threats, answers, and game plan."""

MATCHUP_GUIDE_PROMPT = """Analyze how to use this card against this opponent:

**Our Card:**
Name: {card_name}
Type: {card_type}
Text: {card_text}

**Our Deck:**
Archetype: {our_archetype}
Key Cards: {our_key_cards}

**Opponent's Deck:**
Archetype: {opp_archetype}
Key Cards: {opp_key_cards}
Threats to Watch: {opp_threats}
Their Answers: {opp_answers}

Provide matchup-specific guidance:
1. Priority Modifier: Is this card more/less important here? (0.5=less, 1.0=normal, 1.5=more)
2. Save For: What opponent cards should we save this for?
3. Don't Use On: What opponent cards are NOT worth targeting?
4. Matchup Role: How does this card's role change in this matchup?
5. Key Targets: What should this card target in this matchup?
6. Timing Advice: When to use this card in this matchup?"""

MATCHUP_GUIDE_SCHEMA = {
    "priority_modifier": "float",
    "save_for": "list[str]",
    "dont_use_on": "list[str]",
    "matchup_role": "str",
    "key_targets": "str",
    "timing_advice": "str"
}


# === Deck Analysis ===

DECK_ANALYSIS_SYSTEM = """You are an expert Magic: The Gathering deck analyst.
Identify deck archetypes, game plans, and key cards."""

DECK_ANALYSIS_PROMPT = """Analyze this Magic: The Gathering deck:

**Deck List:**
{deck_list}

**Colors:** {colors}
**Mana Curve:** {curve}

Analyze the deck:
1. Archetype: What type of deck is this? (aggro/control/midrange/combo/tempo)
2. Win Conditions: How does this deck win?
3. Key Cards: What are the most important cards?
4. Game Plan: Text description of how to pilot this deck"""

DECK_ANALYSIS_SCHEMA = {
    "archetype": "str",
    "win_conditions": "list[str]",
    "key_cards": "list[str]",
    "game_plan": "str"
}


# === Matchup Analysis ===

MATCHUP_ANALYSIS_SYSTEM = """You are an expert Magic: The Gathering tournament player.
Analyze matchups between decks and provide strategic guidance."""

MATCHUP_ANALYSIS_PROMPT = """Analyze this matchup:

**Our Deck:**
Archetype: {our_archetype}
Win Conditions: {our_win_cons}
Key Cards: {our_key_cards}

**Opponent's Deck:**
Archetype: {opp_archetype}
Win Conditions: {opp_win_cons}
Key Cards: {opp_key_cards}

Analyze the matchup:
1. Our Role: Are we the beatdown or the control in this matchup?
2. Their Threats: What opponent cards must we answer?
3. Their Answers: What opponent cards answer our key cards?
4. Game Plan: How should we approach this matchup?
5. Key Turns: What turns are critical in this matchup?"""

MATCHUP_ANALYSIS_SCHEMA = {
    "our_role": "str",
    "their_threats": "list[str]",
    "their_answers": "list[str]",
    "game_plan": "str",
    "key_turns": "dict"
}


# === Decision Prompt (for Ultra AI) ===

DECISION_SYSTEM = """You are playing Magic: The Gathering. Make optimal decisions based on the strategic guidance provided."""

DECISION_PROMPT = """You have {card_name} in hand. Here's the strategic guidance:

**General Strategy:**
{when_to_play}
{when_not_to_play}
Targeting: {targeting_advice}

**In Your Deck ({archetype}):**
{deck_role}
{play_pattern}
{synergy_notes}

**Against This Opponent ({our_role}):**
{matchup_role}
{key_targets}
{timing_advice}

**Current Game State:**
Turn: {turn}
Your life: {our_life}
Opponent life: {opp_life}
Your board: {our_board}
Opponent board: {opp_board}
Cards in hand: {hand_count}
Mana available: {mana_available}

**Question:** Should you play {card_name} now? If targeting, what should you target?"""

DECISION_SCHEMA = {
    "should_play": "bool",
    "score": "float",
    "reasoning": "str",
    "target": "str"
}
