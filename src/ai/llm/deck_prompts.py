"""
LLM Prompts for Deck Building

System and user prompts for AI-powered deck construction.
"""

DECK_BUILD_SYSTEM = """You are an expert Magic: The Gathering deck builder with extensive tournament experience.

Your task is to build competitive, balanced 60-card decks with proper mana bases.

Guidelines:
- Mainboard should be exactly 60 cards
- Include 24-26 lands depending on curve
- 4 copies of key cards for consistency
- Curve should match archetype (aggro = low, control = high)
- Sideboard is 15 cards for specific matchups
- Only use cards from the provided card pool

Respond ONLY with valid JSON. No explanations or commentary."""


DECK_BUILD_PROMPT = """Build a {format} deck based on this request:

"{user_request}"

Constraints:
- Colors: {colors}
- Available cards: {card_pool_summary}

Return JSON with this exact structure:
{{
  "name": "Deck Name",
  "archetype": "Aggro|Control|Midrange|Combo|Ramp",
  "colors": ["W", "U", "B", "R", "G"],
  "description": "Brief strategy description",
  "mainboard": [
    {{"card": "Card Name", "qty": 4}},
    ...
  ],
  "sideboard": [
    {{"card": "Sideboard Card", "qty": 2}},
    ...
  ],
  "explanation": "Why these cards work together"
}}

IMPORTANT: Only use cards from the available card pool. Make sure mainboard has exactly 60 cards total."""


DECK_SUGGEST_SYSTEM = """You are an expert MTG deck tuner. Analyze the deck and suggest improvements.

You can suggest:
- Cards to add (from the available pool)
- Cards to remove (give reasons)
- Quantity adjustments
- Sideboard changes

Respond ONLY with valid JSON."""


DECK_SUGGEST_PROMPT = """Analyze this deck and suggest improvements:

Deck: {deck_name}
Archetype: {archetype}
Colors: {colors}

Current mainboard:
{mainboard_list}

Current sideboard:
{sideboard_list}

Deck stats:
- Average CMC: {avg_cmc}
- Land count: {land_count}
- Creature count: {creature_count}

User request: "{user_request}"

Available cards for additions:
{available_cards}

Return JSON with suggestions:
{{
  "analysis": "Brief analysis of current deck",
  "suggestions": [
    {{
      "action": "add|remove|adjust",
      "card": "Card Name",
      "from_qty": 0,
      "to_qty": 4,
      "reason": "Why this change"
    }}
  ],
  "priority_changes": ["List of most important changes"]
}}"""


DECK_SCHEMA = {
    "name": "str",
    "archetype": "str",
    "colors": "list[str]",
    "description": "str",
    "mainboard": "list[dict]",
    "sideboard": "list[dict]",
    "explanation": "str"
}


SUGGEST_SCHEMA = {
    "analysis": "str",
    "suggestions": "list[dict]",
    "priority_changes": "list[str]"
}
